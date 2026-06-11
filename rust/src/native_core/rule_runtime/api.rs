use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::adapters::config_patterns::validate_runtime_config_patterns;
use super::errors::RuleRuntimeIssue;
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

    serialize_report(RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: Some(plan_token_for(&payload)?),
        summary: serde_json::json!({"mode": payload.mode}),
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
        "rule_runtime_contract_version": RULE_RUNTIME_CONTRACT_VERSION,
    });
    let bytes = serde_json::to_vec(&value)
        .map_err(|error| format!("规则导入计划 token 编码失败: {error}"))?;
    Ok(format!("plan:{:x}", Sha256::digest(bytes)))
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
