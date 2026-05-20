//! 游戏文本控制符扫描。
//!
//! 本模块负责识别 RMMZ 标准控制符、自定义控制符和未保护控制片段。

use regex::Regex;
use std::collections::HashMap;

use super::models::{CompiledRules, ControlSpan, SpanSource};
use super::placeholders::LITERAL_LINE_BREAK_PLACEHOLDER;
use super::rules::{
    INDEXED_STANDARD_RE, LITERAL_DYNAMIC_HEX_RE, LITERAL_DYNAMIC_OCTAL_RE,
    LITERAL_DYNAMIC_UNICODE_RE, RAW_CONTROL_RE, SYMBOL_STANDARD_RE, TERMS_PERCENT_RE,
};

pub(crate) fn replace_control_sequences<F>(
    text: &str,
    rules: &CompiledRules,
    mut replacer: F,
) -> Result<String, String>
where
    F: FnMut(&ControlSpan) -> String,
{
    let spans = iter_control_sequence_spans(text, rules)?;
    if spans.is_empty() {
        return Ok(text.to_string());
    }
    let mut output = String::new();
    let mut last_end = 0usize;
    for span in spans {
        output.push_str(&text[last_end..span.start]);
        output.push_str(&replacer(&span));
        last_end = span.end;
    }
    output.push_str(&text[last_end..]);
    Ok(output)
}

pub(crate) fn iter_control_sequence_spans(
    text: &str,
    rules: &CompiledRules,
) -> Result<Vec<ControlSpan>, String> {
    let mut base_spans = Vec::new();
    base_spans.extend(iter_indexed_standard_spans(text));
    base_spans.extend(iter_no_param_standard_spans(text));
    base_spans.extend(iter_symbol_standard_spans(text));
    base_spans.extend(iter_terms_percent_spans(text));
    base_spans.extend(iter_literal_escape_spans(text));
    base_spans.extend(iter_custom_placeholder_spans(text, rules));
    let structured_result = iter_structured_placeholder_spans(text, rules)?;
    validate_structured_placeholder_conflicts(
        &base_spans,
        &structured_result.spans,
        &structured_result.translatable_ranges,
    )?;
    let mut spans = base_spans;
    spans.extend(structured_result.spans);
    Ok(select_non_overlapping_spans(spans))
}

pub(crate) fn iter_control_sequence_spans_lossy(
    text: &str,
    rules: &CompiledRules,
) -> Vec<ControlSpan> {
    let mut spans = Vec::new();
    spans.extend(iter_indexed_standard_spans(text));
    spans.extend(iter_no_param_standard_spans(text));
    spans.extend(iter_symbol_standard_spans(text));
    spans.extend(iter_terms_percent_spans(text));
    spans.extend(iter_literal_escape_spans(text));
    spans.extend(iter_custom_placeholder_spans(text, rules));
    if let Ok(structured_result) = iter_structured_placeholder_spans(text, rules)
        && validate_structured_placeholder_conflicts(
            &spans,
            &structured_result.spans,
            &structured_result.translatable_ranges,
        )
        .is_ok()
    {
        spans.extend(structured_result.spans);
    }
    select_non_overlapping_spans(spans)
}

pub(crate) fn iter_indexed_standard_spans(text: &str) -> Vec<ControlSpan> {
    INDEXED_STANDARD_RE
        .captures_iter(text)
        .filter_map(|captures| {
            let matched = captures.get(0)?;
            let code = captures.name("code")?.as_str().to_uppercase();
            let param = captures.name("param")?.as_str();
            let code_name = match code.as_str() {
                "V" => "VARIABLE",
                "N" => "ACTOR_NAME",
                "P" => "PARTY_MEMBER_NAME",
                "C" => "TEXT_COLOR",
                "I" => "ICON",
                "PX" => "TEXT_X_POSITION",
                "PY" => "TEXT_Y_POSITION",
                "FS" => "FONT_SIZE",
                _ => return None,
            };
            Some(ControlSpan {
                start: matched.start(),
                end: matched.end(),
                original: matched.as_str().to_string(),
                placeholder: Some(format!("[RMMZ_{}_{}]", code_name, param)),
                custom_template: None,
                custom_index_key: None,
                source: SpanSource::Standard,
                priority: 0,
            })
        })
        .collect()
}

pub(crate) fn iter_no_param_standard_spans(text: &str) -> Vec<ControlSpan> {
    let mut spans = Vec::new();
    let chars: Vec<(usize, char)> = text.char_indices().collect();
    for (index, (byte_index, char_value)) in chars.iter().enumerate() {
        if *char_value != '\\' {
            continue;
        }
        let Some((next_byte, next_char)) = chars.get(index + 1) else {
            continue;
        };
        if !next_char.eq_ignore_ascii_case(&'G') {
            continue;
        }
        let after = chars.get(index + 2).map(|(_, value)| *value);
        if after.is_some_and(|value| value.is_ascii_alphabetic() || value == '[') {
            continue;
        }
        spans.push(ControlSpan {
            start: *byte_index,
            end: *next_byte + next_char.len_utf8(),
            original: text[*byte_index..*next_byte + next_char.len_utf8()].to_string(),
            placeholder: Some("[RMMZ_CURRENCY_UNIT]".to_string()),
            custom_template: None,
            custom_index_key: None,
            source: SpanSource::Standard,
            priority: 0,
        });
    }
    spans
}

pub(crate) fn iter_symbol_standard_spans(text: &str) -> Vec<ControlSpan> {
    SYMBOL_STANDARD_RE
        .captures_iter(text)
        .filter_map(|captures| {
            let matched = captures.get(0)?;
            let symbol = captures.name("symbol")?.as_str();
            let placeholder = match symbol {
                "{" => "[RMMZ_FONT_LARGER]",
                "}" => "[RMMZ_FONT_SMALLER]",
                "\\" => "[RMMZ_BACKSLASH]",
                "$" => "[RMMZ_SHOW_GOLD_WINDOW]",
                "." => "[RMMZ_WAIT_SHORT]",
                "|" => "[RMMZ_WAIT_LONG]",
                "!" => "[RMMZ_WAIT_INPUT]",
                ">" => "[RMMZ_INSTANT_TEXT_ON]",
                "<" => "[RMMZ_INSTANT_TEXT_OFF]",
                "^" => "[RMMZ_NO_WAIT]",
                _ => return None,
            };
            Some(ControlSpan {
                start: matched.start(),
                end: matched.end(),
                original: matched.as_str().to_string(),
                placeholder: Some(placeholder.to_string()),
                custom_template: None,
                custom_index_key: None,
                source: SpanSource::Standard,
                priority: 0,
            })
        })
        .collect()
}

pub(crate) fn iter_terms_percent_spans(text: &str) -> Vec<ControlSpan> {
    TERMS_PERCENT_RE
        .captures_iter(text)
        .filter_map(|captures| {
            let matched = captures.get(0)?;
            let param = captures.name("param")?.as_str();
            Some(ControlSpan {
                start: matched.start(),
                end: matched.end(),
                original: matched.as_str().to_string(),
                placeholder: Some(format!("[RMMZ_MESSAGE_ARGUMENT_{}]", param)),
                custom_template: None,
                custom_index_key: None,
                source: SpanSource::Standard,
                priority: 0,
            })
        })
        .collect()
}

pub(crate) fn iter_literal_escape_spans(text: &str) -> Vec<ControlSpan> {
    let literal_placeholders = [
        ("\\\"", "[RMMZ_LITERAL_DOUBLE_QUOTE]"),
        ("\\'", "[RMMZ_LITERAL_SINGLE_QUOTE]"),
        ("\\/", "[RMMZ_LITERAL_SLASH]"),
        ("\\?", "[RMMZ_LITERAL_QUESTION_MARK]"),
        ("\\a", "[RMMZ_LITERAL_BELL]"),
        ("\\b", "[RMMZ_LITERAL_BACKSPACE]"),
        ("\\f", "[RMMZ_LITERAL_FORM_FEED]"),
        ("\\n", LITERAL_LINE_BREAK_PLACEHOLDER),
        ("\\r", "[RMMZ_LITERAL_CARRIAGE_RETURN]"),
        ("\\t", "[RMMZ_LITERAL_TAB]"),
        ("\\v", "[RMMZ_LITERAL_VERTICAL_TAB]"),
    ];
    let mut spans = Vec::new();
    for (literal, placeholder) in literal_placeholders {
        let mut offset = 0usize;
        while let Some(index) = text[offset..].find(literal) {
            let start = offset + index;
            let end = start + literal.len();
            spans.push(ControlSpan {
                start,
                end,
                original: literal.to_string(),
                placeholder: Some(placeholder.to_string()),
                custom_template: None,
                custom_index_key: None,
                source: SpanSource::Standard,
                priority: 0,
            });
            offset = end;
        }
    }
    spans.extend(iter_dynamic_literal_escape_spans(
        text,
        "UNICODE",
        &LITERAL_DYNAMIC_UNICODE_RE,
    ));
    spans.extend(iter_dynamic_literal_escape_spans(
        text,
        "HEX",
        &LITERAL_DYNAMIC_HEX_RE,
    ));
    spans.extend(iter_dynamic_literal_escape_spans(
        text,
        "OCTAL",
        &LITERAL_DYNAMIC_OCTAL_RE,
    ));
    spans
}

pub(crate) fn iter_dynamic_literal_escape_spans(
    text: &str,
    escape_name: &str,
    regex: &Regex,
) -> Vec<ControlSpan> {
    regex
        .find_iter(text)
        .filter(|matched| {
            if escape_name != "OCTAL" {
                return true;
            }
            !text[matched.end()..].starts_with('[')
        })
        .map(|matched| ControlSpan {
            start: matched.start(),
            end: matched.end(),
            original: matched.as_str().to_string(),
            placeholder: Some(format!(
                "[RMMZ_LITERAL_{}_ESCAPE_{}]",
                escape_name,
                encode_upper_hex(matched.as_str())
            )),
            custom_template: None,
            custom_index_key: None,
            source: SpanSource::Standard,
            priority: 0,
        })
        .collect()
}

pub(crate) fn iter_custom_placeholder_spans(text: &str, rules: &CompiledRules) -> Vec<ControlSpan> {
    let mut spans = Vec::new();
    for rule in &rules.custom_placeholder_rules {
        for matched in rule.pattern.find_iter(text).flatten() {
            spans.push(ControlSpan {
                start: matched.start(),
                end: matched.end(),
                original: matched.as_str().to_string(),
                placeholder: None,
                custom_template: Some(rule.placeholder_template.clone()),
                custom_index_key: None,
                source: SpanSource::Custom,
                priority: 1,
            });
        }
    }
    spans
}

pub(crate) fn iter_structured_placeholder_spans(
    text: &str,
    rules: &CompiledRules,
) -> Result<StructuredPlaceholderScanResult, String> {
    let mut spans = Vec::new();
    let mut translatable_ranges = Vec::new();
    for rule in &rules.structured_placeholder_rules {
        for captures_result in rule.pattern.captures_iter(text) {
            let captures = captures_result.map_err(|error| {
                format!("结构化占位符规则 {} 匹配失败: {error}", rule.rule_name)
            })?;
            let full_match = captures
                .get(0)
                .ok_or_else(|| format!("结构化占位符规则 {} 缺少完整匹配", rule.rule_name))?;
            let translatable_match = captures.name(&rule.translatable_group).ok_or_else(|| {
                format!(
                    "结构化占位符规则 {} 的命名分组未命中: {}",
                    rule.rule_name, rule.translatable_group
                )
            })?;
            let translatable_range = ProtectedRange {
                start: translatable_match.start(),
                end: translatable_match.end(),
            };
            translatable_ranges.push(translatable_range.clone());
            let match_key = format!(
                "structured:{}:{}:{}:{}",
                rule.rule_name,
                full_match.start(),
                full_match.end(),
                full_match.as_str()
            );
            let mut group_ranges: Vec<ProtectedRange> = Vec::new();
            for (group_name, placeholder_template) in &rule.protected_groups {
                let group_match = captures.name(group_name).ok_or_else(|| {
                    format!(
                        "结构化占位符规则 {} 的命名分组未命中: {}",
                        rule.rule_name, group_name
                    )
                })?;
                if group_match.start() == group_match.end() {
                    return Err(format!(
                        "结构化占位符规则 {} 的保护分组 {} 命中了空文本",
                        rule.rule_name, group_name
                    ));
                }
                let protected_range = ProtectedRange {
                    start: group_match.start(),
                    end: group_match.end(),
                };
                if ranges_overlap_ranges(&protected_range, &translatable_range) {
                    return Err(format!(
                        "结构化占位符规则 {} 的保护分组 {} 覆盖了可翻译文本分组",
                        rule.rule_name, group_name
                    ));
                }
                for existing_range in &group_ranges {
                    if ranges_overlap_ranges(&protected_range, existing_range) {
                        return Err(format!(
                            "结构化占位符规则 {} 的保护分组互相重叠",
                            rule.rule_name
                        ));
                    }
                }
                group_ranges.push(protected_range.clone());
                spans.push(ControlSpan {
                    start: protected_range.start,
                    end: protected_range.end,
                    original: group_match.as_str().to_string(),
                    placeholder: None,
                    custom_template: Some(placeholder_template.clone()),
                    custom_index_key: Some(match_key.clone()),
                    source: SpanSource::Structured,
                    priority: 2,
                });
            }
        }
    }
    Ok(StructuredPlaceholderScanResult {
        spans,
        translatable_ranges,
    })
}

pub(crate) fn select_non_overlapping_spans(mut spans: Vec<ControlSpan>) -> Vec<ControlSpan> {
    spans.sort_by(|left, right| {
        (
            left.start,
            -left.priority,
            -(left.end as isize - left.start as isize),
        )
            .cmp(&(
                right.start,
                -right.priority,
                -(right.end as isize - right.start as isize),
            ))
    });
    let mut selected = Vec::new();
    let mut protected_until = 0usize;
    for span in spans {
        if span.start < protected_until {
            continue;
        }
        protected_until = span.end;
        selected.push(span);
    }
    selected
}

fn ranges_overlap(
    left_start: usize,
    left_end: usize,
    right_start: usize,
    right_end: usize,
) -> bool {
    left_start < right_end && right_start < left_end
}

fn ranges_overlap_ranges(left: &ProtectedRange, right: &ProtectedRange) -> bool {
    ranges_overlap(left.start, left.end, right.start, right.end)
}

fn validate_structured_placeholder_conflicts(
    base_spans: &[ControlSpan],
    structured_spans: &[ControlSpan],
    translatable_ranges: &[ProtectedRange],
) -> Result<(), String> {
    for structured_span in structured_spans {
        let structured_range = ProtectedRange {
            start: structured_span.start,
            end: structured_span.end,
        };
        for base_span in base_spans {
            let base_range = ProtectedRange {
                start: base_span.start,
                end: base_span.end,
            };
            if ranges_overlap_ranges(&structured_range, &base_range) {
                return Err(format!(
                    "结构化占位符保护片段与已有控制符规则重叠: {} / {}",
                    structured_span.original, base_span.original
                ));
            }
        }
    }
    for (index, left_span) in structured_spans.iter().enumerate() {
        let left_range = ProtectedRange {
            start: left_span.start,
            end: left_span.end,
        };
        for right_span in structured_spans.iter().skip(index + 1) {
            let right_range = ProtectedRange {
                start: right_span.start,
                end: right_span.end,
            };
            if ranges_overlap_ranges(&left_range, &right_range) {
                return Err(format!(
                    "结构化占位符保护片段互相重叠: {} / {}",
                    left_span.original, right_span.original
                ));
            }
        }
    }
    for translatable_range in translatable_ranges {
        for span in base_spans.iter().chain(structured_spans.iter()) {
            let span_range = ProtectedRange {
                start: span.start,
                end: span.end,
            };
            if ranges_overlap_ranges(translatable_range, &span_range) {
                return Err(format!(
                    "结构化占位符可翻译文本分组被保护规则覆盖: {}",
                    span.original
                ));
            }
        }
    }
    Ok(())
}

#[derive(Clone)]
pub(crate) struct ProtectedRange {
    start: usize,
    end: usize,
}

pub(crate) struct StructuredPlaceholderScanResult {
    spans: Vec<ControlSpan>,
    translatable_ranges: Vec<ProtectedRange>,
}

pub(crate) fn collect_unprotected_control_sequences(
    lines: &[String],
    rules: &CompiledRules,
) -> Result<HashMap<String, usize>, String> {
    let mut counts = HashMap::new();
    for line in lines {
        let protected_spans = iter_control_sequence_spans(line, rules)?;
        for matched in RAW_CONTROL_RE.find_iter(line) {
            let overlaps = protected_spans
                .iter()
                .any(|span| matched.start() < span.end && matched.end() > span.start);
            if overlaps {
                continue;
            }
            *counts.entry(matched.as_str().to_string()).or_insert(0) += 1;
        }
    }
    Ok(counts)
}

pub(crate) fn format_control_counts(counts: &HashMap<String, usize>) -> String {
    if counts.is_empty() {
        return "无".to_string();
    }
    let mut markers: Vec<&String> = counts.keys().collect();
    markers.sort();
    markers
        .into_iter()
        .map(|marker| format!("{}×{}", marker, counts.get(marker).unwrap_or(&0)))
        .collect::<Vec<String>>()
        .join("、")
}

pub(crate) fn format_custom_placeholder(template: &str, index: usize) -> String {
    template
        .replace("{code}", "")
        .replace("{param}", "")
        .replace("{index}", &index.to_string())
}

pub(crate) fn encode_upper_hex(text: &str) -> String {
    text.as_bytes()
        .iter()
        .map(|byte| format!("{:02X}", byte))
        .collect::<String>()
}
