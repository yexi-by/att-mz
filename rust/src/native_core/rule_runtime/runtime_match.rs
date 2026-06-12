//! 用户/Agent 可写规则的运行时匹配入口。

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::native_core::controls::iter_control_sequence_spans;
use crate::native_core::models::{
    ControlSpan, NativeCustomPlaceholderRule, NativeStructuredPlaceholderRule, NativeTextRules,
    SpanSource,
};
use crate::native_core::rule_runtime::adapters::mv_virtual_namebox::compile_mv_virtual_namebox_pattern;
use crate::native_core::rules::compile_rules;

#[derive(Debug, Deserialize)]
struct ControlSpanPayload {
    text: String,
    #[serde(default)]
    custom_placeholder_rules: Vec<NativeCustomPlaceholderRule>,
    #[serde(default)]
    structured_placeholder_rules: Vec<NativeStructuredPlaceholderRule>,
}

#[derive(Debug, Serialize)]
struct ControlSpanOutput {
    start_index: usize,
    end_index: usize,
    original: String,
    source: &'static str,
    placeholder: Option<String>,
    custom_template: Option<String>,
    priority: i32,
    custom_index_key: Option<String>,
}

#[derive(Debug, Serialize)]
struct ControlSpanResponse {
    spans: Vec<ControlSpanOutput>,
}

#[derive(Debug, Deserialize)]
struct MvVirtualNameboxPayload {
    text: String,
    #[serde(default)]
    rules: Vec<MvVirtualNameboxRuntimeRule>,
}

#[derive(Debug, Deserialize)]
struct MvVirtualNameboxRuntimeRule {
    rule_order: i64,
    rule_name: String,
    pattern_text: String,
    speaker_group: String,
    #[serde(default)]
    body_group: String,
}

#[derive(Debug, Serialize)]
struct MvVirtualNameboxMatchOutput {
    rule_order: i64,
    rule_name: String,
    matched_text: String,
    group_values: BTreeMap<String, String>,
}

#[derive(Debug, Serialize)]
struct MvVirtualNameboxMatchResponse {
    matches: Vec<MvVirtualNameboxMatchOutput>,
}

pub(crate) fn collect_control_sequence_spans_impl(payload_json: &str) -> Result<String, String> {
    let payload: ControlSpanPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("rule_runtime 控制符扫描输入不是合法 JSON: {error}"))?;
    let rules = compile_control_rules(
        payload.custom_placeholder_rules,
        payload.structured_placeholder_rules,
    )?;
    let spans = iter_control_sequence_spans(&payload.text, &rules)?
        .into_iter()
        .map(|span| control_span_output(&payload.text, span))
        .collect::<Result<Vec<_>, String>>()?;
    serde_json::to_string(&ControlSpanResponse { spans })
        .map_err(|error| format!("rule_runtime 控制符扫描输出序列化失败: {error}"))
}

pub(crate) fn match_mv_virtual_namebox_rules_impl(payload_json: &str) -> Result<String, String> {
    let payload: MvVirtualNameboxPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("rule_runtime MV 虚拟名字框输入不是合法 JSON: {error}"))?;
    let normalized_text = payload.text.trim();
    if normalized_text.is_empty() {
        return serde_json::to_string(&MvVirtualNameboxMatchResponse {
            matches: Vec::new(),
        })
        .map_err(|error| format!("rule_runtime MV 虚拟名字框输出序列化失败: {error}"));
    }

    let mut matches = Vec::new();
    for rule in payload.rules {
        let pattern = compile_mv_virtual_namebox_pattern(
            &rule.rule_name,
            &rule.pattern_text,
            &rule.speaker_group,
            &rule.body_group,
        )?;
        let Some(captures) = pattern
            .captures_full_match(normalized_text)
            .map_err(|error| {
                format!(
                    "MV 虚拟名字框规则 {} 匹配失败: {}",
                    rule.rule_name, error.message
                )
            })?
        else {
            continue;
        };
        let group_values = pattern
            .capture_names()
            .into_iter()
            .map(|name| {
                let value = captures.named(&name).unwrap_or_default().to_string();
                (name, value)
            })
            .collect::<BTreeMap<_, _>>();
        matches.push(MvVirtualNameboxMatchOutput {
            rule_order: rule.rule_order,
            rule_name: rule.rule_name,
            matched_text: normalized_text.to_string(),
            group_values,
        });
    }

    serde_json::to_string(&MvVirtualNameboxMatchResponse { matches })
        .map_err(|error| format!("rule_runtime MV 虚拟名字框输出序列化失败: {error}"))
}

fn compile_control_rules(
    custom_placeholder_rules: Vec<NativeCustomPlaceholderRule>,
    structured_placeholder_rules: Vec<NativeStructuredPlaceholderRule>,
) -> Result<crate::native_core::models::CompiledRules, String> {
    compile_rules(NativeTextRules {
        custom_placeholder_rules,
        structured_placeholder_rules,
        source_residual_allowed_chars: Vec::new(),
        source_residual_allowed_tail_chars: Vec::new(),
        source_residual_segment_pattern: r"[\s\S]+".to_string(),
        source_residual_label: "源文".to_string(),
        allowed_source_residual_terms: Vec::new(),
        source_residual_terms_ignore_case: false,
        source_residual_detection_profile: "japanese_strict".to_string(),
        english_source_copy_min_words: 4,
        english_source_copy_min_letters: 12,
        line_width_count_pattern: r"\S".to_string(),
        residual_escape_sequence_pattern: r"\\[nrt]".to_string(),
        long_text_line_width_limit: 999,
    })
}

fn control_span_output(text: &str, span: ControlSpan) -> Result<ControlSpanOutput, String> {
    Ok(ControlSpanOutput {
        start_index: byte_to_char_index(text, span.start)?,
        end_index: byte_to_char_index(text, span.end)?,
        original: span.original,
        source: span_source_name(&span.source),
        placeholder: span.placeholder,
        custom_template: span.custom_template,
        priority: span.priority,
        custom_index_key: span.custom_index_key,
    })
}

fn byte_to_char_index(text: &str, byte_index: usize) -> Result<usize, String> {
    if byte_index > text.len() || !text.is_char_boundary(byte_index) {
        return Err(format!(
            "rule_runtime 返回了非法 UTF-8 字节边界: {byte_index}"
        ));
    }
    Ok(text[..byte_index].chars().count())
}

fn span_source_name(source: &SpanSource) -> &'static str {
    match source {
        SpanSource::Standard => "standard",
        SpanSource::Custom => "custom",
        SpanSource::Structured => "structured",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    #[test]
    fn control_span_runtime_returns_char_offsets_for_pcre2_custom_rule() {
        let output = collect_control_sequence_spans_impl(
            &json!({
                "text": "前\\Shake後",
                "custom_placeholder_rules": [
                    {
                        "pattern_text": r"\\Shake",
                        "placeholder_template": "[CUSTOM_SHAKE_{index}]"
                    }
                ]
            })
            .to_string(),
        )
        .expect("control span scan should succeed");
        let value: Value = serde_json::from_str(&output).expect("output should be JSON");
        let spans = value["spans"].as_array().expect("spans should be array");

        assert_eq!(spans[0]["source"], "custom");
        assert_eq!(spans[0]["start_index"], 1);
        assert_eq!(spans[0]["end_index"], 7);
    }

    #[test]
    fn mv_virtual_namebox_runtime_requires_full_match() {
        let output = match_mv_virtual_namebox_rules_impl(
            &json!({
                "text": "Alice: hello",
                "rules": [
                    {
                        "rule_order": 0,
                        "rule_name": "name-only",
                        "pattern_text": "(?<speaker>Alice)",
                        "speaker_group": "speaker",
                        "body_group": ""
                    }
                ]
            })
            .to_string(),
        )
        .expect("runtime match should succeed");
        let value: Value = serde_json::from_str(&output).expect("output should be JSON");

        assert_eq!(value["matches"].as_array().unwrap().len(), 0);
    }
}
