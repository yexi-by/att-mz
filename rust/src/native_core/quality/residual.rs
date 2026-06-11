//! 源文残留检查。
//!
//! 本模块负责索引允许保留的源文规则，并在译文中识别不应出现的原文片段。

use regex::{Regex, RegexBuilder};
use serde_json::{Value, json};
use std::collections::HashMap;

use super::super::details::base_detail;
use super::super::models::{CompiledRules, NativeSourceResidualRule, NativeTranslationItem};
use super::super::placeholders::{build_placeholders, mask_translation_controls};
use super::super::rule_runtime::engine::{Pcre2Engine, Pcre2EngineConfig, Pcre2Pattern};
use super::super::rules::PLACEHOLDER_RE;

#[derive(Debug, Clone)]
pub(super) struct IndexedResidualRules {
    position_rules: HashMap<String, NativeSourceResidualRule>,
    structural_rules: Vec<CompiledStructuralResidualRule>,
}

#[derive(Debug, Clone)]
struct CompiledStructuralResidualRule {
    pattern: Pcre2Pattern,
    allowed_terms: Vec<String>,
    check_group: String,
}

/// 按规则类型索引源文残留例外规则，遇到损坏规则时立即报错。
pub(super) fn index_residual_rules(
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
                let pattern = Pcre2Engine::compile(
                    &record.pattern_text,
                    &Pcre2EngineConfig::default_runtime(),
                )
                .map_err(|error| {
                    format!(
                        "结构性源文保留规则 PCRE2 pattern 损坏: {}: {}",
                        record.pattern_text, error.message
                    )
                })?;
                if !pattern
                    .capture_names()
                    .iter()
                    .any(|name| name == &record.check_group)
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

/// 收集单条译文的源文残留问题明细。
pub(super) fn collect_residual_detail(
    item: &NativeTranslationItem,
    rules: &CompiledRules,
    residual_rules: &IndexedResidualRules,
) -> Option<Value> {
    if !translation_has_residual_candidate(&item.translation_lines, rules) {
        return None;
    }
    let allowed_terms = residual_rules
        .position_rules
        .get(&item.location_path)
        .map(|rule| rule.allowed_terms.as_slice())
        .unwrap_or(&[]);
    let control_masked_lines = match build_placeholders(item, rules)
        .and_then(|placeholder_build| mask_translation_controls(item, rules, &placeholder_build))
    {
        Ok(lines) => lines,
        Err(reason) => {
            let mut detail = base_detail(item);
            detail.insert("reason".to_string(), json!(reason));
            return Some(Value::Object(detail));
        }
    };
    let checked_lines = mask_allowed_terms(
        &control_masked_lines,
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
    match check_source_residual(&item.original_lines, &checked_lines, rules) {
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

fn translation_has_residual_candidate(lines: &[String], rules: &CompiledRules) -> bool {
    lines.iter().any(|line| {
        let cleaned_line = strip_non_content_for_residual(line, rules);
        rules.source_residual_segment_re.is_match(&cleaned_line)
    })
}

fn mask_structural_terms(
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
    let Ok(captures) = rule.pattern.captures_iter(line) else {
        return line.to_string();
    };
    for capture_match in captures {
        let Some(group_span) = capture_match.named_span(&rule.check_group) else {
            continue;
        };
        if line[group_span.start..group_span.end].trim().is_empty() {
            continue;
        }
        let outside_ranges = [
            (capture_match.full_span.start, group_span.start),
            (group_span.end, capture_match.full_span.end),
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

fn mask_allowed_terms(
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

fn check_source_residual(
    original_lines: &[String],
    lines: &[String],
    rules: &CompiledRules,
) -> Result<(), String> {
    if rules.source_residual_detection_profile == "english_source_copy" {
        return check_english_source_copy_residual(original_lines, lines, rules);
    }
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

#[derive(Debug, Clone)]
struct ResidualToken {
    text: String,
    normalized: String,
}

fn check_english_source_copy_residual(
    original_lines: &[String],
    lines: &[String],
    rules: &CompiledRules,
) -> Result<(), String> {
    let original_text = original_lines
        .iter()
        .map(|line| strip_non_content_for_residual(line, rules))
        .collect::<Vec<String>>()
        .join("\n");
    let original_tokens = collect_english_residual_tokens(&original_text, rules);
    if original_tokens.is_empty() {
        return Ok(());
    }
    let original_token_values = original_tokens
        .iter()
        .map(|token| token.normalized.clone())
        .collect::<Vec<String>>();
    for (index, line) in lines.iter().enumerate() {
        let cleaned_line = strip_non_content_for_residual(line, rules);
        let translation_tokens = collect_english_residual_tokens(&cleaned_line, rules);
        let copied_segments =
            find_english_source_copy_segments(&original_token_values, &translation_tokens, rules);
        if !copied_segments.is_empty() {
            return Err(format!(
                "发现{}残留(第 {} 行): {:?}",
                rules.source_residual_label,
                index + 1,
                copied_segments
            ));
        }
    }
    Ok(())
}

fn collect_english_residual_tokens(text: &str, rules: &CompiledRules) -> Vec<ResidualToken> {
    rules
        .source_residual_segment_re
        .find_iter(text)
        .filter_map(|matched| {
            let value = matched.as_str();
            if !has_ascii_letter(value) {
                return None;
            }
            let normalized = if rules.source_residual_terms_ignore_case {
                value.to_ascii_lowercase()
            } else {
                value.to_string()
            };
            Some(ResidualToken {
                text: value.to_string(),
                normalized,
            })
        })
        .collect()
}

fn find_english_source_copy_segments(
    original_tokens: &[String],
    translation_tokens: &[ResidualToken],
    rules: &CompiledRules,
) -> Vec<String> {
    let mut copied_segments = Vec::new();
    let mut start = 0usize;
    while start < translation_tokens.len() {
        let mut best_end = 0usize;
        let first_candidate_end = start + rules.english_source_copy_min_words;
        if first_candidate_end <= translation_tokens.len() {
            for end in first_candidate_end..=translation_tokens.len() {
                let candidate_tokens = &translation_tokens[start..end];
                let letter_count = candidate_tokens
                    .iter()
                    .map(|token| ascii_letter_count(&token.text))
                    .sum::<usize>();
                if letter_count < rules.english_source_copy_min_letters {
                    continue;
                }
                let candidate_values = candidate_tokens
                    .iter()
                    .map(|token| token.normalized.clone())
                    .collect::<Vec<String>>();
                if contains_token_sequence(original_tokens, &candidate_values) {
                    best_end = end;
                }
            }
        }
        if best_end > 0 {
            copied_segments.push(
                translation_tokens[start..best_end]
                    .iter()
                    .map(|token| token.text.as_str())
                    .collect::<Vec<&str>>()
                    .join(" "),
            );
            start = best_end;
            continue;
        }
        start += 1;
    }
    copied_segments
}

fn strip_non_content_for_residual(text: &str, rules: &CompiledRules) -> String {
    let stripped_placeholders = PLACEHOLDER_RE.replace_all(text, "");
    rules
        .residual_escape_sequence_re
        .replace_all(&stripped_placeholders, " ")
        .to_string()
}

fn has_non_source_content(text: &str, rules: &CompiledRules) -> bool {
    let text_without_source = rules.source_residual_segment_re.replace_all(text, "");
    text_without_source.chars().any(char::is_alphanumeric)
}

fn has_ascii_letter(text: &str) -> bool {
    text.chars()
        .any(|char_value| char_value.is_ascii_alphabetic())
}

fn ascii_letter_count(text: &str) -> usize {
    text.chars()
        .filter(|char_value| char_value.is_ascii_alphabetic())
        .count()
}

fn contains_token_sequence(source_tokens: &[String], candidate_tokens: &[String]) -> bool {
    if candidate_tokens.is_empty() || candidate_tokens.len() > source_tokens.len() {
        return false;
    }
    let candidate_len = candidate_tokens.len();
    for start in 0..=(source_tokens.len() - candidate_len) {
        if &source_tokens[start..start + candidate_len] == candidate_tokens {
            return true;
        }
    }
    false
}
