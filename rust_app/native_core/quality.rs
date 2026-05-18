//! 翻译质量检查。
//!
//! 本模块负责并行收集源文残留、文本结构、占位符风险和行宽问题。

use rayon::prelude::*;
use regex::{Regex, RegexBuilder};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::Arc;

use super::controls::{iter_control_sequence_spans, replace_control_sequences};
use super::details::{base_detail, collect_sorted_details};
use super::models::{
    CompiledRules, NativeSourceResidualRule, NativeTranslationItem, QualityPayload,
    QualityScanOutput,
};
use super::placeholders::{
    LITERAL_LINE_BREAK_MARKER, LITERAL_LINE_BREAK_PLACEHOLDER, REAL_LINE_BREAK_PLACEHOLDER,
    build_placeholders, collect_placeholder_tokens, mask_translation_controls, verify_placeholders,
};
use super::pool::run_with_optional_pool;
use super::rules::{PLACEHOLDER_RE, compile_rules};

pub fn scan_quality_impl(payload_json: &str) -> Result<String, String> {
    let payload: QualityPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("Rust 质检输入 JSON 解析失败: {error}"))?;
    let rules = Arc::new(compile_rules(payload.text_rules)?);
    let residual_rules = Arc::new(index_residual_rules(payload.source_residual_rules)?);
    let items = Arc::new(payload.items);

    let output = run_with_optional_pool(|| {
        let source_residual_items = collect_sorted_details(
            items
                .par_iter()
                .filter_map(|item| collect_residual_detail(item, &rules, &residual_rules))
                .collect(),
        );
        let text_structure_items = collect_sorted_details(
            items
                .par_iter()
                .filter_map(|item| collect_text_structure_detail(item, &rules))
                .collect(),
        );
        let placeholder_risk_items = collect_sorted_details(
            items
                .par_iter()
                .filter_map(|item| collect_placeholder_detail(item, &rules))
                .collect(),
        );
        let overwide_line_items = collect_sorted_details(
            items
                .par_iter()
                .flat_map(|item| collect_overwide_details(item, &rules))
                .collect(),
        );

        QualityScanOutput {
            source_residual_items,
            text_structure_items,
            placeholder_risk_items,
            overwide_line_items,
        }
    });

    serde_json::to_string(&output)
        .map_err(|error| format!("Rust 质检输出 JSON 序列化失败: {error}"))
}

#[derive(Debug, Clone)]
pub(crate) struct IndexedResidualRules {
    pub(crate) position_rules: HashMap<String, NativeSourceResidualRule>,
    pub(crate) structural_rules: Vec<CompiledStructuralResidualRule>,
}

#[derive(Debug, Clone)]
pub(crate) struct CompiledStructuralResidualRule {
    pub(crate) pattern: Regex,
    pub(crate) allowed_terms: Vec<String>,
    pub(crate) check_group: String,
}

pub(crate) fn index_residual_rules(
    records: Vec<NativeSourceResidualRule>,
) -> Result<IndexedResidualRules, String> {
    let mut position_rules = HashMap::new();
    let mut structural_rules = Vec::new();
    for record in records {
        match record.rule_type.as_str() {
            "structural" => {
                if record.pattern_text.is_empty() || record.check_group.is_empty() {
                    return Err(format!(
                        "结构性源文保留规则缺少 pattern_text 或 check_group: {}",
                        record.rule_id
                    ));
                }
                let pattern = Regex::new(&record.pattern_text).map_err(|error| {
                    format!(
                        "结构性源文保留规则正则损坏: {}: {error}",
                        record.pattern_text
                    )
                })?;
                if !pattern
                    .capture_names()
                    .any(|name| name == Some(record.check_group.as_str()))
                {
                    return Err(format!(
                        "结构性源文保留规则缺少命名分组: {}",
                        record.check_group
                    ));
                }
                structural_rules.push(CompiledStructuralResidualRule {
                    pattern,
                    allowed_terms: record.allowed_terms,
                    check_group: record.check_group,
                });
            }
            "position" => {
                if record.location_path.is_empty() {
                    return Err(format!("位置源文保留规则缺少内部位置: {}", record.rule_id));
                }
                if record.allowed_terms.is_empty() {
                    return Err(format!(
                        "位置源文保留规则缺少允许保留的源文片段: {}",
                        record.rule_id
                    ));
                }
                position_rules.insert(record.location_path.clone(), record);
            }
            unknown_rule_type => {
                return Err(format!(
                    "源文保留规则类型无效: {}: {}",
                    record.rule_id, unknown_rule_type
                ));
            }
        }
    }
    Ok(IndexedResidualRules {
        position_rules,
        structural_rules,
    })
}

pub(crate) fn collect_residual_detail(
    item: &NativeTranslationItem,
    rules: &CompiledRules,
    residual_rules: &IndexedResidualRules,
) -> Option<Value> {
    let allowed_terms = residual_rules
        .position_rules
        .get(&item.location_path)
        .map(|rule| rule.allowed_terms.as_slice())
        .unwrap_or(&[]);
    let checked_lines = mask_allowed_terms(
        &item.translation_lines,
        allowed_terms,
        rules.source_residual_terms_ignore_case,
    );
    let checked_lines = mask_structural_terms(
        &checked_lines,
        &residual_rules.structural_rules,
        rules.source_residual_terms_ignore_case,
    );
    let checked_lines = mask_allowed_terms(
        &checked_lines,
        &rules.allowed_source_residual_terms,
        rules.source_residual_terms_ignore_case,
    );
    match check_source_residual(&checked_lines, rules) {
        Ok(()) => None,
        Err(reason) => {
            let mut detail = base_detail(item);
            detail.insert("reason".to_string(), json!(reason));
            if let Some(rule) = residual_rules.position_rules.get(&item.location_path)
                && !rule.allowed_terms.is_empty()
            {
                detail.insert("allowed_terms".to_string(), json!(rule.allowed_terms));
                detail.insert("exception_reason".to_string(), json!(rule.reason));
            }
            Some(Value::Object(detail))
        }
    }
}

pub(crate) fn mask_structural_terms(
    lines: &[String],
    structural_rules: &[CompiledStructuralResidualRule],
    ignore_case: bool,
) -> Vec<String> {
    if structural_rules.is_empty() {
        return lines.to_vec();
    }
    lines
        .iter()
        .map(|line| mask_structural_terms_in_line(line, structural_rules, ignore_case))
        .collect()
}

fn mask_structural_terms_in_line(
    line: &str,
    structural_rules: &[CompiledStructuralResidualRule],
    ignore_case: bool,
) -> String {
    let mut masked = line.to_string();
    for rule in structural_rules {
        masked = mask_one_structural_rule_in_line(&masked, rule, ignore_case);
    }
    masked
}

fn mask_one_structural_rule_in_line(
    line: &str,
    rule: &CompiledStructuralResidualRule,
    ignore_case: bool,
) -> String {
    let mut mask_ranges = Vec::new();
    for captures in rule.pattern.captures_iter(line) {
        let Some(full_match) = captures.get(0) else {
            continue;
        };
        let Some(group_match) = captures.name(&rule.check_group) else {
            continue;
        };
        if group_match.as_str().trim().is_empty() {
            continue;
        }
        let outside_ranges = [
            (full_match.start(), group_match.start()),
            (group_match.end(), full_match.end()),
        ];
        for term in &rule.allowed_terms {
            mask_ranges.extend(find_term_ranges_outside_group(
                line,
                term,
                &outside_ranges,
                ignore_case,
            ));
        }
    }
    replace_byte_ranges_with_spaces(line, &mask_ranges)
}

fn find_term_ranges_outside_group(
    line: &str,
    term: &str,
    outside_ranges: &[(usize, usize)],
    ignore_case: bool,
) -> Vec<(usize, usize)> {
    if term.is_empty() {
        return Vec::new();
    }
    let mut ranges = Vec::new();
    let Ok(pattern) = RegexBuilder::new(&regex::escape(term))
        .case_insensitive(ignore_case)
        .build()
    else {
        return ranges;
    };
    for (start, end) in outside_ranges {
        if *start >= *end || *end > line.len() {
            continue;
        }
        let segment = &line[*start..*end];
        for term_match in pattern.find_iter(segment) {
            ranges.push((*start + term_match.start(), *start + term_match.end()));
        }
    }
    ranges
}

fn replace_byte_ranges_with_spaces(line: &str, ranges: &[(usize, usize)]) -> String {
    if ranges.is_empty() {
        return line.to_string();
    }
    line.char_indices()
        .map(|(index, char_value)| {
            if ranges
                .iter()
                .any(|(start, end)| index >= *start && index < *end)
            {
                ' '
            } else {
                char_value
            }
        })
        .collect()
}

pub(crate) fn mask_allowed_terms(
    lines: &[String],
    allowed_terms: &[String],
    ignore_case: bool,
) -> Vec<String> {
    if allowed_terms.is_empty() {
        return lines.to_vec();
    }
    let mut sorted_terms = allowed_terms.to_vec();
    sorted_terms.sort_by_key(|term| usize::MAX - term.chars().count());
    lines
        .iter()
        .map(|line| {
            let mut masked = line.clone();
            for term in &sorted_terms {
                if ignore_case {
                    masked = mask_case_insensitive_term(&masked, term);
                } else {
                    masked = masked.replace(term, " ");
                }
            }
            masked
        })
        .collect()
}

fn mask_case_insensitive_term(text: &str, term: &str) -> String {
    let escaped_term = regex::escape(term);
    let pattern_text = format!(r"(?i)(^|[^A-Za-z0-9_]){escaped_term}($|[^A-Za-z0-9_])");
    let Ok(pattern) = Regex::new(&pattern_text) else {
        return text.to_string();
    };
    pattern
        .replace_all(text, |captures: &regex::Captures<'_>| {
            let left = captures.get(1).map_or("", |matched| matched.as_str());
            let right = captures.get(2).map_or("", |matched| matched.as_str());
            format!("{left} {right}")
        })
        .to_string()
}

pub(crate) fn check_source_residual(lines: &[String], rules: &CompiledRules) -> Result<(), String> {
    for (index, line) in lines.iter().enumerate() {
        let cleaned_line = strip_non_content_for_residual(line, rules);
        let segments: Vec<String> = rules
            .source_residual_segment_re
            .find_iter(&cleaned_line)
            .map(|matched| matched.as_str().to_string())
            .collect();
        if segments.is_empty() {
            continue;
        }

        let has_non_source_content = has_non_source_content(&cleaned_line, rules);
        let mut real_residual_segments = Vec::new();
        for segment in segments {
            let filtered: Vec<char> = segment
                .chars()
                .filter(|char_value| !rules.source_residual_allowed_chars.contains(char_value))
                .collect();
            if filtered.is_empty() {
                if !has_non_source_content {
                    real_residual_segments.push(segment);
                }
                continue;
            }
            if has_non_source_content
                && filtered.iter().all(|char_value| {
                    rules
                        .source_residual_allowed_tail_chars
                        .contains(char_value)
                })
            {
                continue;
            }
            real_residual_segments.push(segment);
        }

        if !real_residual_segments.is_empty() {
            return Err(format!(
                "发现{}残留(第 {} 行): {:?}",
                rules.source_residual_label,
                index + 1,
                real_residual_segments
            ));
        }
    }
    Ok(())
}

pub(crate) fn strip_non_content_for_residual(text: &str, rules: &CompiledRules) -> String {
    let stripped_controls = replace_control_sequences(text, rules, |_| String::new());
    let stripped_placeholders = PLACEHOLDER_RE.replace_all(&stripped_controls, "");
    rules
        .residual_escape_sequence_re
        .replace_all(&stripped_placeholders, " ")
        .to_string()
}

pub(crate) fn has_non_source_content(text: &str, rules: &CompiledRules) -> bool {
    let text_without_source = rules.source_residual_segment_re.replace_all(text, "");
    text_without_source.chars().any(char::is_alphanumeric)
}

pub(crate) fn collect_text_structure_detail(
    item: &NativeTranslationItem,
    rules: &CompiledRules,
) -> Option<Value> {
    match build_placeholders(item, rules).and_then(|placeholder_build| {
        let translation_lines_with_placeholders =
            mask_translation_controls(item, rules, &placeholder_build.placeholder_map);
        collect_text_structure_errors(
            item,
            &item.translation_lines,
            &translation_lines_with_placeholders,
            &placeholder_build.original_lines_with_placeholders,
        )
    }) {
        Ok(errors) if errors.is_empty() => None,
        Ok(errors) => {
            let mut detail = base_detail(item);
            detail.insert("reason".to_string(), json!(errors.join(";\n")));
            Some(Value::Object(detail))
        }
        Err(reason) => {
            let mut detail = base_detail(item);
            detail.insert("reason".to_string(), json!(reason));
            Some(Value::Object(detail))
        }
    }
}

pub(crate) fn collect_placeholder_detail(
    item: &NativeTranslationItem,
    rules: &CompiledRules,
) -> Option<Value> {
    let leaked_tokens = collect_placeholder_tokens(&item.translation_lines);
    if !leaked_tokens.is_empty() {
        let mut sorted_tokens: Vec<String> = leaked_tokens.into_iter().collect();
        sorted_tokens.sort();
        let mut detail = base_detail(item);
        detail.insert(
            "reason".to_string(),
            json!(format!(
                "译文残留项目内部占位符，不能写进游戏文件: {}",
                sorted_tokens.join("、")
            )),
        );
        return Some(Value::Object(detail));
    }

    match build_placeholders(item, rules).and_then(|placeholder_build| {
        let translation_lines_with_placeholders =
            mask_translation_controls(item, rules, &placeholder_build.placeholder_map);
        verify_placeholders(
            item,
            rules,
            &placeholder_build,
            &translation_lines_with_placeholders,
        )
    }) {
        Ok(()) => None,
        Err(reason) => {
            let mut detail = base_detail(item);
            detail.insert("reason".to_string(), json!(reason));
            Some(Value::Object(detail))
        }
    }
}

pub(crate) fn collect_overwide_details(
    item: &NativeTranslationItem,
    rules: &CompiledRules,
) -> Vec<Value> {
    let original_text_width_limit = original_short_text_width_limit(item, rules);
    let mut details = Vec::new();
    for (line_index, line, original_line) in iter_line_width_check_lines(item) {
        if line.is_empty() {
            continue;
        }
        let mut effective_limit = rules.long_text_line_width_limit;
        let mut original_width = None;
        if let Some(original_line_text) = original_line {
            let width = count_line_width_chars(&original_line_text, rules);
            effective_limit = effective_limit.max(width);
            original_width = Some(width);
        }
        if let Some(width_limit) = original_text_width_limit {
            effective_limit = effective_limit.max(width_limit);
        }
        let line_width = count_line_width_chars(&line, rules);
        if line_width <= effective_limit {
            continue;
        }
        let mut detail = base_detail(item);
        detail.insert("line_index".to_string(), json!(line_index));
        detail.insert("line".to_string(), json!(line));
        detail.insert("line_width".to_string(), json!(line_width));
        detail.insert("line_width_limit".to_string(), json!(effective_limit));
        if let Some(width) = original_width {
            detail.insert("original_line_width".to_string(), json!(width));
            detail.insert(
                "configured_line_width_limit".to_string(),
                json!(rules.long_text_line_width_limit),
            );
        }
        if let Some(width_limit) = original_text_width_limit {
            detail.insert("original_text_width_limit".to_string(), json!(width_limit));
        }
        details.push(Value::Object(detail));
    }
    details
}

pub(crate) fn collect_text_structure_errors(
    item: &NativeTranslationItem,
    translation_lines: &[String],
    translation_lines_with_placeholders: &[String],
    original_lines_with_placeholders: &[String],
) -> Result<Vec<String>, String> {
    let mut errors = collect_artifact_errors(item, translation_lines);
    if item.item_type != "short_text" {
        return Ok(errors);
    }
    if translation_lines.len() != 1 {
        errors.push(format!(
            "单字段文本必须只提供 1 条中文译文行，当前提供 {} 条",
            translation_lines.len()
        ));
        return Ok(errors);
    }

    let original_real_break_count = count_real_line_breaks(original_lines_with_placeholders);
    let translation_real_break_count = count_real_line_breaks(translation_lines_with_placeholders);
    if original_real_break_count != translation_real_break_count {
        errors.push(format!(
            "译文真实换行数量不一致（原文 {} 个，译文 {} 个）",
            original_real_break_count, translation_real_break_count
        ));
    }

    let original_literal_break_count = count_literal_line_breaks(original_lines_with_placeholders);
    let translation_literal_break_count =
        count_literal_line_breaks(translation_lines_with_placeholders);
    if original_literal_break_count != translation_literal_break_count {
        errors.push(format!(
            "译文字面量换行标记数量不一致（原文 {} 个，译文 {} 个）",
            original_literal_break_count, translation_literal_break_count
        ));
    }
    Ok(errors)
}

pub(crate) fn collect_artifact_errors(
    item: &NativeTranslationItem,
    translation_lines: &[String],
) -> Vec<String> {
    let mut errors = Vec::new();
    let joined_text = translation_lines.join("\n");
    if !item.location_path.is_empty() && joined_text.contains(&item.location_path) {
        errors.push("译文包含文本在游戏里的内部位置，不能写进游戏文件".to_string());
    }

    for line in translation_lines {
        let stripped = line.trim();
        let lowered = stripped.to_lowercase();
        if stripped.starts_with("译文：")
            || stripped.starts_with("译文:")
            || stripped.starts_with("翻译：")
            || stripped.starts_with("翻译:")
        {
            errors.push("译文包含明显解释性前缀，不是可写入游戏的正文".to_string());
            break;
        }
        if stripped.contains("以下是翻译") {
            errors.push("译文包含明显解释性说明，不是可写入游戏的正文".to_string());
            break;
        }
        if lowered.starts_with("id:")
            || lowered.starts_with("id：")
            || lowered.starts_with("\"id\":")
            || lowered.starts_with("source_lines:")
            || lowered.starts_with("source_lines：")
            || lowered.starts_with("\"source_lines\":")
            || lowered.starts_with("translation_lines:")
            || lowered.starts_with("translation_lines：")
            || lowered.starts_with("\"translation_lines\":")
        {
            errors.push("译文包含模型输出协议字段，不是可写入游戏的正文".to_string());
            break;
        }
    }
    errors
}

pub(crate) fn count_real_line_breaks(lines: &[String]) -> usize {
    if lines.is_empty() {
        return 0;
    }
    lines.join("\n").matches('\n').count()
        + lines
            .iter()
            .map(|line| line.matches(REAL_LINE_BREAK_PLACEHOLDER).count())
            .sum::<usize>()
}

pub(crate) fn count_literal_line_breaks(lines: &[String]) -> usize {
    lines
        .iter()
        .map(|line| {
            line.matches(LITERAL_LINE_BREAK_MARKER).count()
                + line.matches(LITERAL_LINE_BREAK_PLACEHOLDER).count()
        })
        .sum()
}

pub(crate) fn original_short_text_width_limit(
    item: &NativeTranslationItem,
    rules: &CompiledRules,
) -> Option<usize> {
    if item.item_type != "short_text" || item.original_lines.is_empty() {
        return None;
    }
    let original_lines = split_display_line_breaks(&item.original_lines[0]);
    if original_lines.is_empty() {
        return None;
    }
    original_lines
        .iter()
        .map(|line| count_line_width_chars(line, rules))
        .max()
}

pub(crate) fn iter_line_width_check_lines(
    item: &NativeTranslationItem,
) -> Vec<(usize, String, Option<String>)> {
    if item.item_type == "long_text" {
        return item
            .translation_lines
            .iter()
            .enumerate()
            .map(|(index, line)| (index, line.clone(), None))
            .collect();
    }
    if item.item_type != "short_text" || item.translation_lines.is_empty() {
        return Vec::new();
    }
    let original_has_line_break = has_display_line_break(&item.original_lines);
    let translated_text = &item.translation_lines[0];
    if !has_display_line_break(std::slice::from_ref(translated_text)) && !original_has_line_break {
        return Vec::new();
    }
    let translated_lines = split_display_line_breaks(translated_text);
    let original_text = item
        .original_lines
        .first()
        .map(String::as_str)
        .unwrap_or("");
    let original_lines = split_display_line_breaks(original_text);
    translated_lines
        .into_iter()
        .enumerate()
        .map(|(index, line)| {
            let original_line = original_lines.get(index).cloned();
            (index, line, original_line)
        })
        .collect()
}

pub(crate) fn has_display_line_break(lines: &[String]) -> bool {
    lines
        .iter()
        .any(|line| line.contains('\n') || line.contains(LITERAL_LINE_BREAK_MARKER))
}

pub(crate) fn split_display_line_breaks(text: &str) -> Vec<String> {
    text.replace(LITERAL_LINE_BREAK_MARKER, "\n")
        .split('\n')
        .map(str::to_string)
        .collect()
}

pub(crate) fn count_line_width_chars(text: &str, rules: &CompiledRules) -> usize {
    let mut protected_spans: Vec<(usize, usize)> = PLACEHOLDER_RE
        .find_iter(text)
        .map(|matched| (matched.start(), matched.end()))
        .collect();
    protected_spans.extend(
        iter_control_sequence_spans(text, rules)
            .into_iter()
            .map(|span| (span.start, span.end)),
    );
    text.char_indices()
        .filter(|(byte_index, char_value)| {
            !protected_spans
                .iter()
                .any(|(start, end)| *start <= *byte_index && *byte_index < *end)
                && rules.line_width_count_re.is_match(&char_value.to_string())
        })
        .count()
}
