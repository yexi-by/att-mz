use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::path::Path;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use rusqlite::Connection;

use super::adapters::config_patterns::validate_runtime_config_patterns;
use super::adapters::event_commands::normalize_event_command_rules;
use super::adapters::mv_virtual_namebox::normalize_mv_virtual_namebox_rules;
use super::adapters::nonstandard_data::normalize_nonstandard_data_rules;
use super::adapters::note_tags::normalize_note_tag_rules;
use super::adapters::placeholders::normalize_placeholder_rules;
use super::adapters::plugin_config::normalize_plugin_config_rules;
use super::adapters::plugin_source::normalize_plugin_source_rules;
use super::adapters::source_residual::normalize_source_residual_rules;
use super::adapters::structured_placeholders::normalize_structured_placeholder_rules;
use super::errors::RuleRuntimeIssue;
use super::model::{NormalizedRuleInput, RuleDomain, StoredRule, stable_rule_id};
use super::model::{RULE_RUNTIME_CONTRACT_VERSION, RULE_STORE_SCHEMA_VERSION};
use super::store::{
    DomainStateDraft, RuleImportStorePlan, build_rules_fingerprint, commit_rule_import_store,
};

#[derive(Debug, Deserialize)]
struct PrepareRuleImportPayload {
    mode: String,
    #[serde(default)]
    db_path: Option<String>,
    domain: String,
    #[serde(default)]
    rules_payload: Value,
    #[serde(default)]
    game_context: Value,
    #[serde(default)]
    settings_runtime_patterns: Value,
    #[serde(default)]
    confirm_empty: bool,
    #[serde(default)]
    cleanup_input: CleanupInput,
}

#[derive(Debug, Deserialize)]
struct CommitRuleImportPayload {
    db_path: String,
    domain: String,
    plan_token: String,
    prepared_plan: PreparedRuleImportPlan,
    backup_path: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct CleanupInput {
    #[serde(default)]
    old_translation_identities: Vec<TranslationIdentity>,
    #[serde(default)]
    current_rule_identities: Vec<TranslationIdentity>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
struct TranslationIdentity {
    fact_id: String,
    source_fact_raw_hash: String,
    source_fact_translatable_hash: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct PreparedDomainState {
    state_json: Value,
    scope_hash: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct PreparedCleanupPlan {
    fact_ids: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct PreparedRuleImportPlan {
    domain: String,
    mode: String,
    rules: Vec<StoredRule>,
    domain_state: Option<PreparedDomainState>,
    cleanup_plan: PreparedCleanupPlan,
    db_fingerprint: String,
    config_patterns_hash: String,
    context_hash: String,
    rule_runtime_contract_version: i64,
    rule_store_schema_version: i64,
}

#[derive(Debug, Serialize)]
struct RuleImportReport {
    status: String,
    rule_runtime_contract_version: i64,
    rule_store_schema_version: i64,
    errors: Vec<RuleRuntimeIssue>,
    warnings: Vec<RuleRuntimeIssue>,
    plan_token: Option<String>,
    prepared_plan: Option<Value>,
    summary: Value,
    details: Value,
}

/// 预检规则导入请求并返回当前规则运行时报告。
pub(crate) fn prepare_rule_import_impl(payload_json: &str) -> Result<String, String> {
    let started_at = Instant::now();
    let payload: PrepareRuleImportPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则导入 prepare 输入 JSON 无效: {error}"))?;
    let config_issues = validate_runtime_config_patterns(&payload.settings_runtime_patterns);
    if !config_issues.is_empty() {
        let diagnostics = runtime_diagnostics(RuntimeDiagnosticsInput {
            domain: &payload.domain,
            rule_count: 0,
            compile_ms: elapsed_ms(started_at),
            scan_ms: None,
            store_ms: None,
            errors: &config_issues,
            warnings: &[],
        });
        return serialize_report(RuleImportReport {
            status: "error".to_string(),
            rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
            rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
            errors: config_issues,
            warnings: Vec::new(),
            plan_token: None,
            prepared_plan: None,
            summary: serde_json::json!({
                "mode": payload.mode,
                "diagnostics": diagnostics,
            }),
            details: serde_json::json!({
                "diagnostics": diagnostics,
                "cleanup_plan": cleanup_plan_value(&payload.domain, &[], None),
            }),
        });
    }
    if !is_current_rule_domain(&payload.domain) {
        return invalid_domain_report(&payload.domain);
    }
    let normalized_rules = match normalize_domain_rules(&payload) {
        Ok(rules) => rules,
        Err(errors) => {
            let diagnostics = runtime_diagnostics(RuntimeDiagnosticsInput {
                domain: &payload.domain,
                rule_count: 0,
                compile_ms: elapsed_ms(started_at),
                scan_ms: None,
                store_ms: None,
                errors: &errors,
                warnings: &[],
            });
            return serialize_report(RuleImportReport {
                status: "error".to_string(),
                rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
                rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
                errors,
                warnings: Vec::new(),
                plan_token: None,
                prepared_plan: None,
                summary: serde_json::json!({
                    "mode": &payload.mode,
                    "rule_runtime": {
                        "domain": &payload.domain,
                    },
                    "diagnostics": diagnostics,
                }),
                details: serde_json::json!({
                    "diagnostics": diagnostics,
                    "cleanup_plan": cleanup_plan_value(&payload.domain, &[], None),
                }),
            });
        }
    };

    let domain = rule_domain_from_text(&payload.domain)?;
    let context_hash = game_context_scope_hash(&payload.game_context)?;
    let config_patterns_hash = stable_value_hash(&payload.settings_runtime_patterns)?;
    let cleanup_fact_ids = cleanup_fact_ids(&payload.cleanup_input);
    let rules = stored_rules_from_normalized(&normalized_rules)?;
    let domain_state = prepared_domain_state(&payload, normalized_rules.len(), &context_hash);
    let db_fingerprint = prepare_db_fingerprint(payload.db_path.as_deref(), &config_patterns_hash)?;
    let prepared_plan = PreparedRuleImportPlan {
        domain: payload.domain.clone(),
        mode: payload.mode.clone(),
        rules,
        domain_state,
        cleanup_plan: PreparedCleanupPlan {
            fact_ids: cleanup_fact_ids,
        },
        db_fingerprint,
        config_patterns_hash,
        context_hash: context_hash.clone(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
    };
    let plan_token = plan_token_for(&prepared_plan)?;
    let diagnostics = runtime_diagnostics(RuntimeDiagnosticsInput {
        domain: &payload.domain,
        rule_count: normalized_rules.len(),
        compile_ms: elapsed_ms(started_at),
        scan_ms: None,
        store_ms: None,
        errors: &[],
        warnings: &[],
    });
    let prepared_plan_value = serde_json::to_value(&prepared_plan)
        .map_err(|error| format!("规则导入计划 JSON 编码失败: {error}"))?;
    serialize_report(RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: Some(plan_token),
        prepared_plan: Some(prepared_plan_value),
        summary: serde_json::json!({
            "mode": &payload.mode,
            "rule_runtime": {
                "domain": &payload.domain,
                "rule_count": normalized_rules.len(),
                "matcher_kinds": matcher_kinds(&normalized_rules),
            },
            "domain_state": domain_state_summary(&payload, normalized_rules.len(), &context_hash),
            "cleanup_plan": cleanup_plan_value(
                &payload.domain,
                &prepared_plan.cleanup_plan.fact_ids,
                None,
            ),
            "diagnostics": diagnostics,
        }),
        details: serde_json::json!({
            "diagnostics": diagnostics,
            "cleanup_plan": cleanup_plan_value(
                &payload.domain,
                &prepared_plan.cleanup_plan.fact_ids,
                None,
            ),
            "rule_domain": domain,
        }),
    })
}

/// 提交规则导入计划并返回当前规则运行时报告。
pub(crate) fn commit_rule_import_impl(payload_json: &str) -> Result<String, String> {
    let started_at = Instant::now();
    let payload: CommitRuleImportPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则导入 commit 输入 JSON 无效: {error}"))?;
    if !is_current_rule_domain(&payload.domain) {
        return invalid_domain_report(&payload.domain);
    }
    let domain = rule_domain_from_text(&payload.domain)?;
    if payload.prepared_plan.domain != payload.domain
        || payload.prepared_plan.rule_runtime_contract_version != RULE_RUNTIME_CONTRACT_VERSION
        || payload.prepared_plan.rule_store_schema_version != RULE_STORE_SCHEMA_VERSION
    {
        return commit_error_report(
            &payload.domain,
            "rule_import_plan_stale",
            "规则导入计划已失效，请重新执行导入命令".to_string(),
            elapsed_ms(started_at),
            None,
            payload.backup_path.as_deref(),
            &payload.prepared_plan.cleanup_plan.fact_ids,
        );
    }
    let expected_token = plan_token_for(&payload.prepared_plan)?;
    if payload.plan_token != expected_token {
        return commit_error_report(
            &payload.domain,
            "rule_import_plan_stale",
            "规则导入计划已失效，请重新执行导入命令".to_string(),
            elapsed_ms(started_at),
            None,
            payload.backup_path.as_deref(),
            &payload.prepared_plan.cleanup_plan.fact_ids,
        );
    }
    if !payload.prepared_plan.cleanup_plan.fact_ids.is_empty()
        && !backup_path_exists(payload.backup_path.as_deref())
    {
        return commit_error_report(
            &payload.domain,
            "rule_import_backup_required",
            "规则导入会清理已保存译文，必须先写出备份文件再提交".to_string(),
            elapsed_ms(started_at),
            None,
            payload.backup_path.as_deref(),
            &payload.prepared_plan.cleanup_plan.fact_ids,
        );
    }

    let connection = match Connection::open(&payload.db_path) {
        Ok(connection) => connection,
        Err(error) => {
            return commit_error_report(
                &payload.domain,
                "rule_import_db_open_failed",
                format!("规则导入无法打开当前游戏数据库: {error}"),
                elapsed_ms(started_at),
                None,
                payload.backup_path.as_deref(),
                &payload.prepared_plan.cleanup_plan.fact_ids,
            );
        }
    };
    let current_fingerprint =
        build_rules_fingerprint(&connection, &payload.prepared_plan.config_patterns_hash)?;
    if current_fingerprint != payload.prepared_plan.db_fingerprint {
        return commit_error_report(
            &payload.domain,
            "rule_import_plan_stale",
            "规则导入计划已失效，请重新执行导入命令".to_string(),
            elapsed_ms(started_at),
            None,
            payload.backup_path.as_deref(),
            &payload.prepared_plan.cleanup_plan.fact_ids,
        );
    }

    let store_started_at = Instant::now();
    let store_plan =
        RuleImportStorePlan {
            domain,
            rules: payload.prepared_plan.rules.clone(),
            domain_state: payload.prepared_plan.domain_state.clone().map(|state| {
                DomainStateDraft {
                    state_json: state.state_json,
                    scope_hash: state.scope_hash,
                }
            }),
            context_hash: payload.prepared_plan.context_hash.clone(),
            cleanup_fact_ids: payload.prepared_plan.cleanup_plan.fact_ids.clone(),
        };
    let outcome = commit_rule_import_store(&connection, &store_plan, &current_timestamp_text())?;
    let store_ms = elapsed_ms(store_started_at);
    let diagnostics = runtime_diagnostics(RuntimeDiagnosticsInput {
        domain: &payload.domain,
        rule_count: payload.prepared_plan.rules.len(),
        compile_ms: None,
        scan_ms: None,
        store_ms,
        errors: &[],
        warnings: &[],
    });
    serialize_report(RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: None,
        prepared_plan: None,
        summary: serde_json::json!({
            "domain": &payload.domain,
            "backup_path": &payload.backup_path,
            "cleanup_plan": cleanup_plan_result_value(
                &payload.domain,
                &payload.prepared_plan.cleanup_plan.fact_ids,
                payload.backup_path.as_deref(),
                outcome.deleted_translation_count,
            ),
            "diagnostics": diagnostics,
        }),
        details: serde_json::json!({
            "diagnostics": diagnostics,
            "cleanup_plan": cleanup_plan_result_value(
                &payload.domain,
                &payload.prepared_plan.cleanup_plan.fact_ids,
                payload.backup_path.as_deref(),
                outcome.deleted_translation_count,
            ),
        }),
    })
}

#[derive(Debug, Deserialize)]
struct BuildRulesFingerprintPayload {
    db_path: String,
    #[serde(default)]
    settings_runtime_patterns: Value,
}

/// 读取当前统一规则表并返回 Rust 规则指纹。
pub(crate) fn build_rules_fingerprint_impl(payload_json: &str) -> Result<String, String> {
    let payload: BuildRulesFingerprintPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则指纹输入 JSON 无效: {error}"))?;
    let config_patterns_hash = stable_value_hash(&payload.settings_runtime_patterns)?;
    let connection = Connection::open(&payload.db_path)
        .map_err(|error| format!("规则指纹无法打开当前游戏数据库: {error}"))?;
    build_rules_fingerprint(&connection, &config_patterns_hash)
}

fn plan_token_for(plan: &PreparedRuleImportPlan) -> Result<String, String> {
    let bytes = serde_json::to_vec(plan)
        .map_err(|error| format!("规则导入计划 token 编码失败: {error}"))?;
    Ok(format!("plan:{:x}", Sha256::digest(bytes)))
}

fn domain_state_summary(
    payload: &PrepareRuleImportPayload,
    rule_count: usize,
    context_hash: &str,
) -> Value {
    serde_json::json!({
        "domain": &payload.domain,
        "confirmed_empty": payload.confirm_empty && rule_count == 0,
        "scope_hash": context_hash,
    })
}

fn prepared_domain_state(
    payload: &PrepareRuleImportPayload,
    rule_count: usize,
    context_hash: &str,
) -> Option<PreparedDomainState> {
    if payload.confirm_empty && rule_count == 0 {
        return Some(PreparedDomainState {
            state_json: serde_json::json!({"confirmed_empty": true}),
            scope_hash: context_hash.to_string(),
        });
    }
    None
}

fn game_context_scope_hash(game_context: &Value) -> Result<String, String> {
    if let Some(scope_hash) = game_context.get("scope_hash").and_then(Value::as_str)
        && !scope_hash.trim().is_empty()
    {
        return Ok(scope_hash.to_string());
    }
    let bytes = serde_json::to_vec(game_context)
        .map_err(|error| format!("规则确认范围 JSON 编码失败: {error}"))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn is_current_rule_domain(domain: &str) -> bool {
    matches!(
        domain,
        "placeholders"
            | "structured_placeholders"
            | "source_residual"
            | "mv_virtual_namebox"
            | "plugin_config"
            | "event_commands"
            | "note_tags"
            | "nonstandard_data"
            | "plugin_source"
    )
}

fn rule_domain_from_text(domain: &str) -> Result<RuleDomain, String> {
    serde_json::from_value(Value::String(domain.to_string()))
        .map_err(|error| format!("规则 domain 无效：{domain}: {error}"))
}

fn normalize_domain_rules(
    payload: &PrepareRuleImportPayload,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    if payload.domain == "plugin_config" {
        return normalize_plugin_config_rules(&payload.rules_payload);
    }
    if payload.domain == "event_commands" {
        return normalize_event_command_rules(&payload.rules_payload);
    }
    if payload.domain == "note_tags" {
        return normalize_note_tag_rules(&payload.rules_payload);
    }
    if payload.domain == "nonstandard_data" {
        return normalize_nonstandard_data_rules(&payload.rules_payload);
    }
    if payload.domain == "plugin_source" {
        return normalize_plugin_source_rules(&payload.rules_payload);
    }
    if payload.domain == "placeholders" {
        return normalize_placeholder_rules(&payload.rules_payload);
    }
    if payload.domain == "structured_placeholders" {
        return normalize_structured_placeholder_rules(&payload.rules_payload);
    }
    if payload.domain == "source_residual" {
        return normalize_source_residual_rules(&payload.rules_payload);
    }
    if payload.domain == "mv_virtual_namebox" {
        return normalize_mv_virtual_namebox_rules(&payload.rules_payload);
    }
    Ok(Vec::new())
}

fn matcher_kinds(rules: &[NormalizedRuleInput]) -> Vec<Value> {
    let mut values = Vec::new();
    for rule in rules {
        let value = serde_json::to_value(rule.matcher_kind).unwrap_or(Value::Null);
        if !values.iter().any(|item| item == &value) {
            values.push(value);
        }
    }
    values
}

fn cleanup_plan_value(domain: &str, fact_ids: &[String], backup_path: Option<&str>) -> Value {
    serde_json::json!({
        "domain": domain,
        "deleted_translation_count": 0,
        "backup_required": !fact_ids.is_empty(),
        "backup_path": backup_path,
        "records": fact_ids.iter().map(|fact_id| serde_json::json!({
            "fact_id": fact_id,
        })).collect::<Vec<_>>(),
    })
}

fn cleanup_plan_result_value(
    domain: &str,
    fact_ids: &[String],
    backup_path: Option<&str>,
    deleted_translation_count: usize,
) -> Value {
    serde_json::json!({
        "domain": domain,
        "deleted_translation_count": deleted_translation_count,
        "backup_required": !fact_ids.is_empty(),
        "backup_path": backup_path,
        "records": fact_ids.iter().map(|fact_id| serde_json::json!({
            "fact_id": fact_id,
        })).collect::<Vec<_>>(),
    })
}

struct RuntimeDiagnosticsInput<'a> {
    domain: &'a str,
    rule_count: usize,
    compile_ms: Option<u128>,
    scan_ms: Option<u128>,
    store_ms: Option<u128>,
    errors: &'a [RuleRuntimeIssue],
    warnings: &'a [RuleRuntimeIssue],
}

fn runtime_diagnostics(input: RuntimeDiagnosticsInput<'_>) -> Value {
    let mut rule_count_by_domain = Map::new();
    rule_count_by_domain.insert(
        input.domain.to_string(),
        serde_json::json!(input.rule_count),
    );
    let mut runtime = Map::new();
    runtime.insert("domain".to_string(), serde_json::json!(input.domain));
    if let Some(compile_ms) = input.compile_ms {
        runtime.insert("compile_ms".to_string(), serde_json::json!(compile_ms));
    }
    if let Some(scan_ms) = input.scan_ms {
        runtime.insert("scan_ms".to_string(), serde_json::json!(scan_ms));
    }
    if let Some(store_ms) = input.store_ms {
        runtime.insert("store_ms".to_string(), serde_json::json!(store_ms));
    }
    runtime.insert("domain_timings".to_string(), Value::Object(Map::new()));
    runtime.insert("jit_enabled".to_string(), serde_json::json!(true));
    runtime.insert(
        "thread_count".to_string(),
        serde_json::json!(rayon::current_num_threads()),
    );
    runtime.insert(
        "rule_count_by_domain".to_string(),
        Value::Object(rule_count_by_domain),
    );
    runtime.insert(
        "error_count_by_code".to_string(),
        issue_counts_by_code(input.errors),
    );
    runtime.insert(
        "warning_count_by_code".to_string(),
        issue_counts_by_code(input.warnings),
    );
    serde_json::json!({
        "rule_runtime": Value::Object(runtime),
    })
}

fn issue_counts_by_code(issues: &[RuleRuntimeIssue]) -> Value {
    let mut counts = Map::new();
    for issue in issues {
        let current_count = counts.get(&issue.code).and_then(Value::as_u64).unwrap_or(0);
        counts.insert(issue.code.clone(), serde_json::json!(current_count + 1));
    }
    Value::Object(counts)
}

fn serialize_report(report: RuleImportReport) -> Result<String, String> {
    serde_json::to_string(&report).map_err(|error| format!("规则导入报告 JSON 编码失败: {error}"))
}

fn stored_rules_from_normalized(rules: &[NormalizedRuleInput]) -> Result<Vec<StoredRule>, String> {
    let mut stored = Vec::with_capacity(rules.len());
    for rule in rules {
        let rule_hash = rule_hash_for(rule)?;
        stored.push(StoredRule {
            rule_id: stable_rule_id(rule),
            domain: rule.domain,
            rule_order: rule.rule_order,
            matcher_kind: rule.matcher_kind,
            matcher_value: rule.matcher_value.clone(),
            payload_json: rule.payload_json.clone(),
            enabled: true,
            source_kind: "external_import".to_string(),
            rule_hash,
        });
    }
    Ok(stored)
}

fn rule_hash_for(rule: &NormalizedRuleInput) -> Result<String, String> {
    let payload = serde_json::json!({
        "domain": rule.domain,
        "rule_order": rule.rule_order,
        "matcher_kind": rule.matcher_kind,
        "matcher_value": rule.matcher_value,
        "payload_json": rule.payload_json,
    });
    stable_value_hash(&payload)
}

fn cleanup_fact_ids(input: &CleanupInput) -> Vec<String> {
    let current: BTreeSet<TranslationIdentity> =
        input.current_rule_identities.iter().cloned().collect();
    let mut fact_ids = BTreeSet::new();
    for identity in &input.old_translation_identities {
        if !identity.fact_id.trim().is_empty() && !current.contains(identity) {
            fact_ids.insert(identity.fact_id.clone());
        }
    }
    fact_ids.into_iter().collect()
}

fn stable_value_hash(value: &Value) -> Result<String, String> {
    let bytes = serde_json::to_vec(value)
        .map_err(|error| format!("规则运行时 hash JSON 编码失败: {error}"))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn prepare_db_fingerprint(
    db_path: Option<&str>,
    config_patterns_hash: &str,
) -> Result<String, String> {
    let Some(path_text) = db_path else {
        return Ok("missing".to_string());
    };
    let path = Path::new(path_text);
    if !path.exists() {
        return Ok("missing".to_string());
    }
    let connection = Connection::open(path)
        .map_err(|error| format!("规则导入无法打开当前游戏数据库: {error}"))?;
    build_rules_fingerprint(&connection, config_patterns_hash)
}

fn backup_path_exists(backup_path: Option<&str>) -> bool {
    let Some(path_text) = backup_path else {
        return false;
    };
    !path_text.trim().is_empty() && Path::new(path_text).is_file()
}

fn current_timestamp_text() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    format!("unix:{seconds}")
}

fn elapsed_ms(started_at: Instant) -> Option<u128> {
    Some(started_at.elapsed().as_millis())
}

fn commit_error_report(
    domain: &str,
    code: &str,
    message: String,
    compile_ms: Option<u128>,
    store_ms: Option<u128>,
    backup_path: Option<&str>,
    cleanup_fact_ids: &[String],
) -> Result<String, String> {
    let errors = vec![RuleRuntimeIssue::current_input_error(code, message)];
    let diagnostics = runtime_diagnostics(RuntimeDiagnosticsInput {
        domain,
        rule_count: 0,
        compile_ms,
        scan_ms: None,
        store_ms,
        errors: &errors,
        warnings: &[],
    });
    serialize_report(RuleImportReport {
        status: "error".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors,
        warnings: Vec::new(),
        plan_token: None,
        prepared_plan: None,
        summary: serde_json::json!({
            "domain": domain,
            "diagnostics": diagnostics,
            "cleanup_plan": cleanup_plan_value(domain, cleanup_fact_ids, backup_path),
        }),
        details: serde_json::json!({
            "diagnostics": diagnostics,
            "cleanup_plan": cleanup_plan_value(domain, cleanup_fact_ids, backup_path),
        }),
    })
}

fn invalid_domain_report(domain: &str) -> Result<String, String> {
    let errors = vec![RuleRuntimeIssue::current_input_error(
        "rule_domain_invalid",
        format!("规则 domain 无效：{domain}"),
    )];
    let diagnostics = runtime_diagnostics(RuntimeDiagnosticsInput {
        domain,
        rule_count: 0,
        compile_ms: None,
        scan_ms: None,
        store_ms: None,
        errors: &errors,
        warnings: &[],
    });
    serialize_report(RuleImportReport {
        status: "error".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors,
        warnings: Vec::new(),
        plan_token: None,
        prepared_plan: None,
        summary: serde_json::json!({}),
        details: serde_json::json!({
            "diagnostics": diagnostics,
            "cleanup_plan": cleanup_plan_value(domain, &[], None),
        }),
    })
}

#[cfg(test)]
mod tests {
    use super::super::model::RuleDomain;
    use super::super::store::{install_rule_store_schema, read_rules_by_domain};
    use super::*;
    use rusqlite::{Connection, params};
    use serde_json::json;
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn commit_rule_import_writes_rules_state_and_deletes_backed_up_translations() {
        let db_path = unique_test_db_path("rule_runtime_commit");
        let connection = Connection::open(&db_path).expect("test DB should open");
        install_rule_store_schema(&connection).expect("schema should install");
        insert_translation_item(
            &connection,
            "fact:stale",
            "Map001.json/events/1/pages/0/list/0",
        );
        insert_translation_item(
            &connection,
            "fact:kept",
            "Map001.json/events/1/pages/0/list/1",
        );
        drop(connection);

        let prepare_report = report_json(
            prepare_rule_import_impl(
                &json!({
                    "mode": "import",
                    "db_path": db_path.to_string_lossy(),
                    "domain": "placeholders",
                    "rules_payload": {"\\\\V\\[(?<index>\\d+)\\]": "[CUSTOM_VAR_{index}]"},
                    "game_context": {"scope_hash": "scope:placeholders"},
                    "settings_runtime_patterns": valid_runtime_patterns(),
                    "confirm_empty": false,
                    "cleanup_input": {
                        "old_translation_identities": [
                            {
                                "fact_id": "fact:stale",
                                "source_fact_raw_hash": "raw:old",
                                "source_fact_translatable_hash": "text:old"
                            }
                        ],
                        "current_rule_identities": []
                    }
                })
                .to_string(),
            )
            .expect("prepare should serialize"),
        );
        let plan_token = prepare_report["plan_token"]
            .as_str()
            .expect("prepare should return token");
        let prepared_plan = prepare_report["prepared_plan"].clone();
        let backup_path = unique_test_db_path("rule_runtime_backup");
        fs::write(&backup_path, "backup").expect("backup marker should write");

        let commit_report = report_json(
            commit_rule_import_impl(
                &json!({
                    "db_path": db_path.to_string_lossy(),
                    "domain": "placeholders",
                    "plan_token": plan_token,
                    "prepared_plan": prepared_plan,
                    "backup_path": backup_path.to_string_lossy()
                })
                .to_string(),
            )
            .expect("commit should serialize"),
        );

        assert_eq!(commit_report["status"], "ok");
        assert_eq!(
            commit_report["summary"]["cleanup_plan"]["deleted_translation_count"],
            1
        );
        let connection = Connection::open(&db_path).expect("test DB should reopen");
        assert_eq!(
            read_rules_by_domain(&connection, RuleDomain::Placeholders)
                .expect("rules should read")
                .len(),
            1
        );
        let stale_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM translation_items WHERE fact_id = ?1",
                params!["fact:stale"],
                |row| row.get(0),
            )
            .expect("translation count should read");
        let kept_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM translation_items WHERE fact_id = ?1",
                params!["fact:kept"],
                |row| row.get(0),
            )
            .expect("translation count should read");
        assert_eq!(stale_count, 0);
        assert_eq!(kept_count, 1);
        let state_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM rule_domain_states WHERE domain = 'placeholders'",
                [],
                |row| row.get(0),
            )
            .expect("domain state count should read");
        assert_eq!(state_count, 0);
    }

    #[test]
    fn commit_rule_import_rejects_cleanup_without_existing_backup() {
        let db_path = unique_test_db_path("rule_runtime_commit_requires_backup");
        let connection = Connection::open(&db_path).expect("test DB should open");
        install_rule_store_schema(&connection).expect("schema should install");
        insert_translation_item(
            &connection,
            "fact:stale",
            "Map001.json/events/1/pages/0/list/0",
        );
        drop(connection);

        let prepare_report = report_json(
            prepare_rule_import_impl(
                &json!({
                    "mode": "import",
                    "db_path": db_path.to_string_lossy(),
                    "domain": "placeholders",
                    "rules_payload": {},
                    "game_context": {"scope_hash": "scope:placeholders"},
                    "settings_runtime_patterns": valid_runtime_patterns(),
                    "cleanup_input": {
                        "old_translation_identities": [
                            {
                                "fact_id": "fact:stale",
                                "source_fact_raw_hash": "raw:old",
                                "source_fact_translatable_hash": "text:old"
                            }
                        ],
                        "current_rule_identities": []
                    }
                })
                .to_string(),
            )
            .expect("prepare should serialize"),
        );

        let commit_report = report_json(
            commit_rule_import_impl(
                &json!({
                    "db_path": db_path.to_string_lossy(),
                    "domain": "placeholders",
                    "plan_token": prepare_report["plan_token"],
                    "prepared_plan": prepare_report["prepared_plan"],
                    "backup_path": null
                })
                .to_string(),
            )
            .expect("commit should serialize"),
        );

        assert_eq!(commit_report["status"], "error");
        assert_eq!(
            commit_report["errors"][0]["code"],
            "rule_import_backup_required"
        );
        let connection = Connection::open(&db_path).expect("test DB should reopen");
        let stale_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM translation_items WHERE fact_id = ?1",
                params!["fact:stale"],
                |row| row.get(0),
            )
            .expect("translation count should read");
        assert_eq!(stale_count, 1);
    }

    #[test]
    fn commit_rule_import_rejects_stale_prepared_plan_when_store_changed() {
        let db_path = unique_test_db_path("rule_runtime_commit_stale");
        let connection = Connection::open(&db_path).expect("test DB should open");
        install_rule_store_schema(&connection).expect("schema should install");
        drop(connection);

        let prepare_report = report_json(
            prepare_rule_import_impl(
                &json!({
                    "mode": "import",
                    "db_path": db_path.to_string_lossy(),
                    "domain": "placeholders",
                    "rules_payload": {},
                    "game_context": {"scope_hash": "scope:placeholders"},
                    "settings_runtime_patterns": valid_runtime_patterns()
                })
                .to_string(),
            )
            .expect("prepare should serialize"),
        );

        let changed_connection = Connection::open(&db_path).expect("test DB should reopen");
        changed_connection
            .execute(
                "INSERT INTO rules(rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
                 VALUES ('rule:changed', 'note_tags', 0, 'literal', 'Actors.json:note', '{}', 1, 'external_import', 'hash:changed')",
                [],
            )
            .expect("store mutation should succeed");
        drop(changed_connection);

        let commit_report = report_json(
            commit_rule_import_impl(
                &json!({
                    "db_path": db_path.to_string_lossy(),
                    "domain": "placeholders",
                    "plan_token": prepare_report["plan_token"],
                    "prepared_plan": prepare_report["prepared_plan"],
                    "backup_path": null
                })
                .to_string(),
            )
            .expect("commit should serialize"),
        );

        assert_eq!(commit_report["status"], "error");
        assert_eq!(commit_report["errors"][0]["code"], "rule_import_plan_stale");
    }

    fn report_json(report_text: String) -> serde_json::Value {
        serde_json::from_str(&report_text).expect("report should be JSON")
    }

    fn valid_runtime_patterns() -> serde_json::Value {
        json!({
            "source_text_required_pattern": "[ぁ-んァ-ヶ一-龯ー]+",
            "source_residual_segment_pattern": "[ぁ-んァ-ヶー]+",
            "line_width_count_pattern": "\\S",
            "residual_escape_sequence_pattern": "\\\\[nrt]"
        })
    }

    fn unique_test_db_path(label: &str) -> PathBuf {
        let mut path = std::env::temp_dir();
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after unix epoch")
            .as_nanos();
        path.push(format!("att_mz_{label}_{nanos}.sqlite"));
        path
    }

    fn insert_translation_item(connection: &Connection, fact_id: &str, location_path: &str) {
        connection
            .execute(
                "INSERT INTO translation_items(fact_id, location_path, item_type, role, original_lines, source_line_paths, source_fact_raw_hash, source_fact_translatable_hash, translation_lines)
                 VALUES (?1, ?2, 'text', NULL, '[\"原文\"]', '[\"line\"]', 'raw:old', 'text:old', '[\"译文\"]')",
                params![fact_id, location_path],
            )
            .expect("translation item should insert");
    }
}
