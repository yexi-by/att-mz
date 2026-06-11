use serde::Deserialize;
use serde_json::Value;

use super::super::engine::{Pcre2Engine, Pcre2EngineConfig};
use super::super::errors::RuleRuntimeIssue;

#[derive(Debug, Deserialize)]
pub(crate) struct RuntimeConfigPatterns {
    pub(crate) source_text_required_pattern: String,
    pub(crate) source_residual_segment_pattern: String,
    pub(crate) line_width_count_pattern: String,
    pub(crate) residual_escape_sequence_pattern: String,
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
