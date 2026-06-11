use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::super::engine::{Pcre2Engine, Pcre2EngineConfig, Pcre2EngineError};
use super::super::errors::RuleRuntimeIssue;

#[derive(Debug, Deserialize)]
pub(crate) struct RuntimeConfigPatterns {
    pub(crate) source_text_required_pattern: String,
    pub(crate) source_residual_segment_pattern: String,
    pub(crate) line_width_count_pattern: String,
    pub(crate) residual_escape_sequence_pattern: String,
}

#[derive(Debug, Deserialize)]
struct RuntimeConfigEvaluationPayload {
    settings_runtime_patterns: Value,
    texts: Vec<RuntimeConfigEvaluationTextInput>,
}

#[derive(Debug, Deserialize)]
struct RuntimeConfigEvaluationTextInput {
    id: String,
    text: String,
}

#[derive(Debug, Serialize)]
struct RuntimeConfigEvaluationReport {
    status: String,
    errors: Vec<RuleRuntimeIssue>,
    entries: Vec<RuntimeConfigEvaluationEntry>,
}

#[derive(Debug, Serialize)]
struct RuntimeConfigEvaluationEntry {
    id: String,
    source_text_required: bool,
}

pub(crate) fn validate_runtime_config_patterns(value: &Value) -> Vec<RuleRuntimeIssue> {
    let Ok(patterns) = serde_json::from_value::<RuntimeConfigPatterns>(value.clone()) else {
        return vec![RuleRuntimeIssue::current_input_error(
            "runtime_config_patterns_invalid",
            "运行配置正则缺少当前必需字段".to_string(),
        )];
    };

    let config = Pcre2EngineConfig::default_runtime();
    let mut issues = Vec::new();
    for (field, pattern) in [
        (
            "source_text_required_pattern",
            patterns.source_text_required_pattern,
        ),
        (
            "source_residual_segment_pattern",
            patterns.source_residual_segment_pattern,
        ),
        (
            "line_width_count_pattern",
            patterns.line_width_count_pattern,
        ),
        (
            "residual_escape_sequence_pattern",
            patterns.residual_escape_sequence_pattern,
        ),
    ] {
        if let Err(error) = Pcre2Engine::compile(&pattern, &config) {
            issues.push(RuleRuntimeIssue {
                code: error.code.to_string(),
                domain: None,
                rule_id: None,
                field: Some(field.to_string()),
                message: error.message,
                details: serde_json::json!({"pattern": pattern}),
                location: None,
            });
        }
    }
    issues
}

pub(crate) fn evaluate_runtime_config_patterns_impl(payload_json: &str) -> Result<String, String> {
    let payload: RuntimeConfigEvaluationPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("运行配置正则执行输入 JSON 无效: {error}"))?;
    let config_issues = validate_runtime_config_patterns(&payload.settings_runtime_patterns);
    if !config_issues.is_empty() {
        return serialize_report(RuntimeConfigEvaluationReport {
            status: "error".to_string(),
            errors: config_issues,
            entries: Vec::new(),
        });
    }

    let patterns: RuntimeConfigPatterns = serde_json::from_value(payload.settings_runtime_patterns)
        .map_err(|error| format!("运行配置正则缺少当前必需字段: {error}"))?;
    let config = Pcre2EngineConfig::default_runtime();
    let source_text_required_pattern =
        match Pcre2Engine::compile(&patterns.source_text_required_pattern, &config) {
            Ok(pattern) => pattern,
            Err(error) => {
                return serialize_report(RuntimeConfigEvaluationReport {
                    status: "error".to_string(),
                    errors: vec![runtime_config_pattern_issue(
                        "source_text_required_pattern",
                        &patterns.source_text_required_pattern,
                        error,
                    )],
                    entries: Vec::new(),
                });
            }
        };

    let mut entries = Vec::with_capacity(payload.texts.len());
    for text_input in payload.texts {
        let source_text_required = match source_text_required_pattern.is_match(&text_input.text) {
            Ok(matched) => matched,
            Err(error) => {
                return serialize_report(RuntimeConfigEvaluationReport {
                    status: "error".to_string(),
                    errors: vec![runtime_config_pattern_issue(
                        "source_text_required_pattern",
                        &patterns.source_text_required_pattern,
                        error,
                    )],
                    entries: Vec::new(),
                });
            }
        };
        entries.push(RuntimeConfigEvaluationEntry {
            id: text_input.id,
            source_text_required,
        });
    }

    serialize_report(RuntimeConfigEvaluationReport {
        status: "ok".to_string(),
        errors: Vec::new(),
        entries,
    })
}

fn runtime_config_pattern_issue(
    field: &str,
    pattern: &str,
    error: Pcre2EngineError,
) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: error.code.to_string(),
        domain: None,
        rule_id: None,
        field: Some(field.to_string()),
        message: error.message,
        details: serde_json::json!({"pattern": pattern}),
        location: None,
    }
}

fn serialize_report(report: RuntimeConfigEvaluationReport) -> Result<String, String> {
    serde_json::to_string(&report)
        .map_err(|error| format!("运行配置正则执行报告 JSON 编码失败: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_runtime_patterns() -> Value {
        serde_json::json!({
            "source_text_required_pattern": r"[\p{Hiragana}\p{Katakana}\p{Han}ー]+",
            "source_residual_segment_pattern": r"[\p{Hiragana}\p{Katakana}ー]+",
            "line_width_count_pattern": r"\S",
            "residual_escape_sequence_pattern": r"\\[nrt]",
        })
    }

    #[test]
    fn runtime_config_evaluation_uses_pcre2_source_text_pattern() {
        let payload = serde_json::json!({
            "settings_runtime_patterns": valid_runtime_patterns(),
            "texts": [
                {"id": "ja", "text": "こんにちは"},
                {"id": "en", "text": "Inventory"}
            ],
        });

        let report_text = evaluate_runtime_config_patterns_impl(&payload.to_string())
            .expect("runtime config evaluation should serialize");
        let report: Value = serde_json::from_str(&report_text).expect("report should be JSON");

        assert_eq!(report["status"], "ok");
        assert_eq!(report["entries"][0]["source_text_required"], true);
        assert_eq!(report["entries"][1]["source_text_required"], false);
    }
}
