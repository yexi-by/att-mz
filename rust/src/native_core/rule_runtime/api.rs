use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

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
use super::model::NormalizedRuleInput;
use super::model::{RULE_RUNTIME_CONTRACT_VERSION, RULE_STORE_SCHEMA_VERSION};

#[derive(Debug, Deserialize)]
struct PrepareRuleImportPayload {
    mode: String,
    domain: String,
    #[serde(default)]
    rules_payload: Value,
    #[serde(default)]
    game_context: Value,
    #[serde(default)]
    settings_runtime_patterns: Value,
    #[serde(default)]
    confirm_empty: bool,
}

#[derive(Debug, Deserialize)]
struct CommitRuleImportPayload {
    #[serde(rename = "db_path")]
    _db_path: String,
    domain: String,
    plan_token: String,
    backup_path: Option<String>,
}

#[derive(Debug, Serialize)]
struct RuleImportReport {
    status: String,
    rule_runtime_contract_version: i64,
    rule_store_schema_version: i64,
    errors: Vec<RuleRuntimeIssue>,
    warnings: Vec<RuleRuntimeIssue>,
    plan_token: Option<String>,
    summary: Value,
}

/// 预检规则导入请求并返回当前规则运行时报告。
pub(crate) fn prepare_rule_import_impl(payload_json: &str) -> Result<String, String> {
    let payload: PrepareRuleImportPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则导入 prepare 输入 JSON 无效: {error}"))?;
    let config_issues = validate_runtime_config_patterns(&payload.settings_runtime_patterns);
    if !config_issues.is_empty() {
        return serialize_report(RuleImportReport {
            status: "error".to_string(),
            rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
            rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
            errors: config_issues,
            warnings: Vec::new(),
            plan_token: None,
            summary: serde_json::json!({"mode": payload.mode}),
        });
    }
    if !is_current_rule_domain(&payload.domain) {
        return invalid_domain_report(&payload.domain);
    }
    let normalized_rules = match normalize_domain_rules(&payload) {
        Ok(rules) => rules,
        Err(errors) => {
            return serialize_report(RuleImportReport {
                status: "error".to_string(),
                rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
                rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
                errors,
                warnings: Vec::new(),
                plan_token: None,
                summary: serde_json::json!({
                    "mode": &payload.mode,
                    "rule_runtime": {
                        "domain": &payload.domain,
                    },
                }),
            });
        }
    };

    serialize_report(RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: Some(plan_token_for(&payload)?),
        summary: serde_json::json!({
            "mode": &payload.mode,
            "rule_runtime": {
                "domain": &payload.domain,
                "rule_count": normalized_rules.len(),
                "matcher_kinds": matcher_kinds(&normalized_rules),
            },
            "domain_state": domain_state_summary(&payload, normalized_rules.len())?,
        }),
    })
}

/// 提交规则导入计划并返回当前规则运行时报告。
pub(crate) fn commit_rule_import_impl(payload_json: &str) -> Result<String, String> {
    let payload: CommitRuleImportPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则导入 commit 输入 JSON 无效: {error}"))?;
    if !is_current_rule_domain(&payload.domain) {
        return invalid_domain_report(&payload.domain);
    }
    if !payload.plan_token.starts_with("plan:") {
        return serialize_report(RuleImportReport {
            status: "error".to_string(),
            rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
            rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
            errors: vec![RuleRuntimeIssue::current_input_error(
                "rule_import_plan_stale",
                "规则导入计划已失效，请重新执行导入命令".to_string(),
            )],
            warnings: Vec::new(),
            plan_token: None,
            summary: serde_json::json!({}),
        });
    }

    serialize_report(RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: None,
        summary: serde_json::json!({
            "domain": payload.domain,
            "backup_path": payload.backup_path,
        }),
    })
}

fn plan_token_for(payload: &PrepareRuleImportPayload) -> Result<String, String> {
    let value = serde_json::json!({
        "domain": payload.domain,
        "mode": payload.mode,
        "rules_payload": payload.rules_payload,
        "game_context": payload.game_context,
        "settings_runtime_patterns": payload.settings_runtime_patterns,
        "confirm_empty": payload.confirm_empty,
        "rule_runtime_contract_version": RULE_RUNTIME_CONTRACT_VERSION,
    });
    let bytes = serde_json::to_vec(&value)
        .map_err(|error| format!("规则导入计划 token 编码失败: {error}"))?;
    Ok(format!("plan:{:x}", Sha256::digest(bytes)))
}

fn domain_state_summary(
    payload: &PrepareRuleImportPayload,
    rule_count: usize,
) -> Result<Value, String> {
    Ok(serde_json::json!({
        "domain": &payload.domain,
        "confirmed_empty": payload.confirm_empty && rule_count == 0,
        "scope_hash": game_context_scope_hash(&payload.game_context)?,
    }))
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

fn serialize_report(report: RuleImportReport) -> Result<String, String> {
    serde_json::to_string(&report).map_err(|error| format!("规则导入报告 JSON 编码失败: {error}"))
}

fn invalid_domain_report(domain: &str) -> Result<String, String> {
    serialize_report(RuleImportReport {
        status: "error".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: vec![RuleRuntimeIssue::current_input_error(
            "rule_domain_invalid",
            format!("规则 domain 无效：{domain}"),
        )],
        warnings: Vec::new(),
        plan_token: None,
        summary: serde_json::json!({}),
    })
}
