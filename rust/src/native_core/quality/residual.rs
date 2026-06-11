//! 源文残留检查。
//!
//! 本模块负责索引允许保留的源文规则，并在译文中识别不应出现的原文片段。

use regex::{Regex, RegexBuilder};
use serde_json::{Value, json};
use std::collections::HashMap;

use super::super::details::base_detail;
use super::super::models::{CompiledRules, NativeSourceResidualRule, NativeTranslationItem};
use super::super::placeholders::{build_placeholders, mask_translation_controls};
use super::super::rule_runtime::adapters::source_residual::compile_source_residual_structural_pattern;
use super::super::rule_runtime::engine::Pcre2Pattern;
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
                let pattern = compile_source_residual_structural_pattern(
                    &record.rule_id,
                    &record.pattern_text,
                    &record.check_group,
                )?;
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
    match translation_has_residual_candidate(&item.translation_lines, rules) {
        Ok(true) => {}
        Ok(false) => return None,
        Err(reason) => return Some(residual_error_detail(item, reason)),
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

fn residual_error_detail(item: &NativeTranslationItem, reason: String) -> Value {
    let mut detail = base_detail(item);
    detail.insert("reason".to_string(), json!(reason));
    Value::Object(detail)
}

fn translation_has_residual_candidate(
    lines: &[String],
    rules: &CompiledRules,
) -> Result<bool, String> {
    for line in lines {
        let cleaned_line = strip_non_content_for_residual(line, rules)?;
        if rules
            .source_residual_segment_re
            .is_match(&cleaned_line)
            .map_err(|error| format!("源文残留 PCRE2 pattern 匹配失败: {}", error.message))?
        {
            return Ok(true);
        }
    }
    Ok(false)
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
        let cleaned_line = strip_non_content_for_residual(line, rules)?;
        let segments = pcre2_match_texts(
            &rules.source_residual_segment_re,
            &cleaned_line,
            "源文残留 PCRE2 pattern",
        )?
        .into_iter()
        .map(|matched| matched.text)
        .collect::<Vec<String>>();
        if segments.is_empty() {
            continue;
        }

        let has_non_source_content = has_non_source_content(&cleaned_line, rules)?;
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
    start_index: usize,
    end_index: usize,
}

fn check_english_source_copy_residual(
    original_lines: &[String],
    lines: &[String],
    rules: &CompiledRules,
) -> Result<(), String> {
    let original_text = original_lines
        .iter()
        .map(|line| strip_non_content_for_residual(line, rules))
        .collect::<Result<Vec<String>, String>>()?
        .join("\n");
    let original_tokens = collect_english_residual_tokens(&original_text, rules)?;
    if original_tokens.is_empty() {
        return check_english_long_residual_without_original(lines, rules);
    }
    let original_token_values = original_tokens
        .iter()
        .map(|token| token.normalized.clone())
        .collect::<Vec<String>>();
    for (index, line) in lines.iter().enumerate() {
        let cleaned_line = strip_non_content_for_residual(line, rules)?;
        let translation_tokens = collect_english_residual_tokens(&cleaned_line, rules)?;
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

fn collect_english_residual_tokens(
    text: &str,
    rules: &CompiledRules,
) -> Result<Vec<ResidualToken>, String> {
    Ok(pcre2_match_texts(
        &rules.source_residual_segment_re,
        text,
        "英文源文残留 PCRE2 pattern",
    )?
    .into_iter()
    .filter_map(|matched| {
        let value = matched.text.as_str();
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
            start_index: matched.start,
            end_index: matched.end,
        })
    })
    .collect())
}

fn check_english_long_residual_without_original(
    lines: &[String],
    rules: &CompiledRules,
) -> Result<(), String> {
    for (index, line) in lines.iter().enumerate() {
        let cleaned_line = strip_non_content_for_residual(line, rules)?;
        let translation_tokens = collect_english_residual_tokens(&cleaned_line, rules)?;
        let residual_segments =
            find_english_long_residual_segments(&cleaned_line, &translation_tokens, rules);
        if !residual_segments.is_empty() {
            return Err(format!(
                "发现{}残留(第 {} 行): {:?}",
                rules.source_residual_label,
                index + 1,
                residual_segments
            ));
        }
    }
    Ok(())
}

fn find_english_long_residual_segments(
    cleaned_line: &str,
    translation_tokens: &[ResidualToken],
    rules: &CompiledRules,
) -> Vec<String> {
    let mut residual_segments = Vec::new();
    let mut current_run: Vec<&ResidualToken> = Vec::new();
    let mut previous_token: Option<&ResidualToken> = None;
    for token in translation_tokens {
        if let Some(previous) = previous_token {
            let gap = cleaned_line
                .get(previous.end_index..token.start_index)
                .unwrap_or_default();
            if english_token_gap_breaks_run(gap) {
                append_english_run_if_residual(&mut residual_segments, &current_run, rules);
                current_run.clear();
            }
        }
        current_run.push(token);
        previous_token = Some(token);
    }
    append_english_run_if_residual(&mut residual_segments, &current_run, rules);
    residual_segments
}

fn english_token_gap_breaks_run(gap: &str) -> bool {
    for character in gap.chars() {
        if character.is_whitespace() {
            continue;
        }
        if character.is_ascii() && !character.is_ascii_alphanumeric() {
            continue;
        }
        return true;
    }
    false
}

fn append_english_run_if_residual(
    residual_segments: &mut Vec<String>,
    tokens: &[&ResidualToken],
    rules: &CompiledRules,
) {
    if tokens.len() < rules.english_source_copy_min_words {
        return;
    }
    let letter_count = tokens
        .iter()
        .map(|token| ascii_letter_count(&token.text))
        .sum::<usize>();
    if letter_count < rules.english_source_copy_min_letters {
        return;
    }
    residual_segments.push(
        tokens
            .iter()
            .map(|token| token.text.as_str())
            .collect::<Vec<&str>>()
            .join(" "),
    );
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

#[derive(Debug)]
struct Pcre2TextMatch {
    text: String,
    start: usize,
    end: usize,
}

fn strip_non_content_for_residual(text: &str, rules: &CompiledRules) -> Result<String, String> {
    let stripped_placeholders = PLACEHOLDER_RE.replace_all(text, "");
    replace_pcre2_matches(
        &rules.residual_escape_sequence_re,
        &stripped_placeholders,
        " ",
        "残留转义 PCRE2 pattern",
    )
}

fn has_non_source_content(text: &str, rules: &CompiledRules) -> Result<bool, String> {
    let text_without_source = replace_pcre2_matches(
        &rules.source_residual_segment_re,
        text,
        "",
        "源文残留 PCRE2 pattern",
    )?;
    Ok(text_without_source.chars().any(char::is_alphanumeric))
}

fn pcre2_match_texts(
    pattern: &Pcre2Pattern,
    text: &str,
    context: &str,
) -> Result<Vec<Pcre2TextMatch>, String> {
    let spans = pattern
        .find_spans(text)
        .map_err(|error| format!("{context} 匹配失败: {}", error.message))?;
    spans
        .into_iter()
        .map(|span| {
            let matched_text = text
                .get(span.start..span.end)
                .ok_or_else(|| format!("{context} 命中范围不是有效 UTF-8 边界"))?;
            Ok(Pcre2TextMatch {
                text: matched_text.to_string(),
                start: span.start,
                end: span.end,
            })
        })
        .collect()
}

fn replace_pcre2_matches(
    pattern: &Pcre2Pattern,
    text: &str,
    replacement: &str,
    context: &str,
) -> Result<String, String> {
    let spans = pattern
        .find_spans(text)
        .map_err(|error| format!("{context} 匹配失败: {}", error.message))?;
    if spans.is_empty() {
        return Ok(text.to_string());
    }
    let mut output = String::new();
    let mut last_end = 0usize;
    for span in spans {
        let unchanged = text
            .get(last_end..span.start)
            .ok_or_else(|| format!("{context} 替换范围不是有效 UTF-8 边界"))?;
        output.push_str(unchanged);
        output.push_str(replacement);
        last_end = span.end;
    }
    let tail = text
        .get(last_end..)
        .ok_or_else(|| format!("{context} 替换尾部不是有效 UTF-8 边界"))?;
    output.push_str(tail);
    Ok(output)
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
