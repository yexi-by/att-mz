use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::errors::RuleRuntimeIssue;
use super::model::{RULE_RUNTIME_CONTRACT_VERSION, RULE_STORE_SCHEMA_VERSION};

#[derive(Debug, Deserialize)]
struct PrepareRuleImportPayload {
    mode: String,
    domain: String,
    #[serde(default, rename = "rules_payload")]
    _rules_payload: Value,
    #[serde(default, rename = "game_context")]
    _game_context: Value,
    #[serde(default, rename = "settings_runtime_patterns")]
    _settings_runtime_patterns: Value,
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
    if !is_current_rule_domain(&payload.domain) {
        return serialize_report(RuleImportReport {
            status: "error".to_string(),
            rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
            rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
            errors: vec![RuleRuntimeIssue::current_input_error(
                "rule_domain_invalid",
                format!("规则 domain 无效：{}", payload.domain),
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
        plan_token: Some("prepare-skeleton-token".to_string()),
        summary: serde_json::json!({"mode": payload.mode}),
    })
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
