use super::models::{TextPlanRules, TranslationItem};
use crate::native_core::controls::{
    iter_indexed_standard_spans, iter_literal_escape_spans, iter_no_param_standard_spans,
    iter_symbol_standard_spans, iter_terms_percent_spans,
};
use crate::native_core::rules::{
    RAW_BARE_CONTROL_RE, RAW_BRACKETED_CONTROL_RE, RAW_SYMBOL_CONTROL_RE,
};

pub(super) fn prepared_lines(
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<Vec<String>, String> {
    if item.translation_lines.is_empty() {
        return Err(format!(
            "译文行为空，不能写进游戏文件: {}",
            item.location_path
        ));
    }
    let lines: Vec<String> = item
        .translation_lines
        .iter()
        .map(|line| line.trim().to_string())
        .collect();
    Ok(normalize_translated_wrapping_punctuation(
        &item.original_lines,
        &lines,
        rules,
    ))
}

pub(super) fn prepared_single_text(
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<String, String> {
    prepared_lines(item, rules)?
        .into_iter()
        .next()
        .ok_or_else(|| format!("译文行为空，不能写进游戏文件: {}", item.location_path))
}

pub(super) fn prepared_long_lines(
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<Vec<String>, String> {
    let mut lines = split_overwide_lines(prepared_lines(item, rules)?, rules);
    while lines.last().is_some_and(|line| line.is_empty()) {
        let _ = lines.pop();
    }
    if lines.is_empty() {
        return Err(format!(
            "长文本译文行为空，不能写进游戏文件: {}",
            item.location_path
        ));
    }
    Ok(lines)
}

pub(super) fn split_overwide_lines(lines: Vec<String>, rules: &TextPlanRules) -> Vec<String> {
    let mut split_lines = Vec::new();
    let mut active_wrapping_pair: Option<(String, String)> = None;
    for line in lines {
        if line.is_empty() {
            split_lines.push(line);
            continue;
        }
        let mut current_wrapping_pair = active_wrapping_pair.clone();
        let opening_pair = find_opening_wrapping_pair(&line, rules);
        if current_wrapping_pair.is_none() {
            current_wrapping_pair = opening_pair;
        }
        let first_line_prefix = if active_wrapping_pair.is_some() {
            "　"
        } else {
            ""
        };
        let wrapped_tail_prefix = if current_wrapping_pair.is_some() {
            "　"
        } else {
            ""
        };
        split_lines.extend(split_single_overwide_line(
            &line,
            rules,
            first_line_prefix,
            wrapped_tail_prefix,
        ));
        if let Some(pair) = current_wrapping_pair {
            if closes_wrapping_pair(&line, &pair, rules) {
                active_wrapping_pair = None;
            } else {
                active_wrapping_pair = Some(pair);
            }
        } else {
            active_wrapping_pair = None;
        }
    }
    split_lines
}

pub(super) fn split_single_overwide_line(
    line: &str,
    rules: &TextPlanRules,
    first_line_prefix: &str,
    wrapped_tail_prefix: &str,
) -> Vec<String> {
    let mut result = Vec::new();
    let mut pending_line = prepend_continuation_prefix(line, first_line_prefix);
    while count_line_width_chars(&pending_line, rules) > rules.long_text_line_width_limit {
        let Some(split_position) = find_hard_split_position(&pending_line, rules) else {
            break;
        };
        if split_position == 0 || split_position >= pending_line.len() {
            break;
        }
        let head = pending_line[..split_position].trim_end().to_string();
        let tail = pending_line[split_position..].trim_start().to_string();
        if head.is_empty() || tail.is_empty() {
            break;
        }
        result.push(head);
        pending_line = prepend_continuation_prefix(&tail, wrapped_tail_prefix);
    }
    result.push(pending_line);
    result
}

pub(super) fn find_hard_split_position(text: &str, rules: &TextPlanRules) -> Option<usize> {
    let mut line_width_count = 0usize;
    let protected_spans = protected_control_byte_spans(text, rules);
    for (index, character) in text.char_indices() {
        if is_byte_in_spans(index, &protected_spans) {
            continue;
        }
        if !rules.is_line_width_counted_char(character) {
            continue;
        }
        line_width_count += 1;
        if line_width_count < rules.long_text_line_width_limit {
            continue;
        }
        let mut position = index + character.len_utf8();
        while position < text.len() {
            let Some(next_character) = text[position..].chars().next() else {
                break;
            };
            if !rules
                .line_split_punctuations
                .iter()
                .any(|punctuation| punctuation == &next_character.to_string())
            {
                break;
            }
            position += next_character.len_utf8();
        }
        return Some(position);
    }
    None
}

pub(super) fn count_line_width_chars(text: &str, rules: &TextPlanRules) -> usize {
    let protected_spans = protected_control_byte_spans(text, rules);
    text.char_indices()
        .filter(|(byte_index, character)| {
            !is_byte_in_spans(*byte_index, &protected_spans)
                && rules.is_line_width_counted_char(*character)
        })
        .count()
}

pub(super) fn protected_control_byte_spans(
    text: &str,
    rules: &TextPlanRules,
) -> Vec<(usize, usize)> {
    let mut spans = Vec::new();
    spans.extend(
        iter_indexed_standard_spans(text)
            .into_iter()
            .map(|span| (span.start, span.end)),
    );
    spans.extend(
        iter_no_param_standard_spans(text)
            .into_iter()
            .map(|span| (span.start, span.end)),
    );
    spans.extend(
        iter_symbol_standard_spans(text)
            .into_iter()
            .map(|span| (span.start, span.end)),
    );
    spans.extend(
        iter_terms_percent_spans(text)
            .into_iter()
            .map(|span| (span.start, span.end)),
    );
    spans.extend(
        iter_literal_escape_spans(text)
            .into_iter()
            .map(|span| (span.start, span.end)),
    );
    spans.extend(
        RAW_BRACKETED_CONTROL_RE
            .find_iter(text)
            .map(|matched| (matched.start(), matched.end())),
    );
    spans.extend(
        RAW_BARE_CONTROL_RE
            .find_iter(text)
            .map(|matched| (matched.start(), matched.end())),
    );
    spans.extend(
        RAW_SYMBOL_CONTROL_RE
            .find_iter(text)
            .map(|matched| (matched.start(), matched.end())),
    );
    spans.extend(
        rules
            .protected_macro_pattern
            .find_iter(text)
            .map(|matched| (matched.start(), matched.end())),
    );
    spans.sort_unstable();
    spans
}

pub(super) fn is_byte_in_spans(byte_index: usize, spans: &[(usize, usize)]) -> bool {
    spans
        .iter()
        .any(|(start, end)| *start <= byte_index && byte_index < *end)
}

pub(super) fn find_opening_wrapping_pair(
    line: &str,
    rules: &TextPlanRules,
) -> Option<(String, String)> {
    let stripped_line = line.trim();
    rules
        .preserve_wrapping_punctuation_pairs
        .iter()
        .find(|(left, _right)| stripped_line.starts_with(left))
        .cloned()
}

pub(super) fn closes_wrapping_pair(
    line: &str,
    wrapping_pair: &(String, String),
    _rules: &TextPlanRules,
) -> bool {
    line.trim().ends_with(&wrapping_pair.1)
}

pub(super) fn prepend_continuation_prefix(line: &str, prefix: &str) -> String {
    if prefix.is_empty() || line.is_empty() || line.starts_with(prefix) {
        return line.to_string();
    }
    let Some(first_char) = line.chars().next() else {
        return line.to_string();
    };
    if first_char.is_whitespace() {
        return line.to_string();
    }
    format!("{prefix}{line}")
}

#[derive(Clone)]
struct WrappingBoundary {
    line_index: usize,
    char_index: usize,
    character: String,
}

struct WrappingSpan {
    left: WrappingBoundary,
    right: WrappingBoundary,
    pair: (String, String),
}

pub(super) fn normalize_translated_wrapping_punctuation(
    original_lines: &[String],
    translation_lines: &[String],
    rules: &TextPlanRules,
) -> Vec<String> {
    if rules.preserve_wrapping_punctuation_pairs.is_empty() {
        return translation_lines.to_vec();
    }
    let source_spans = collect_source_wrapping_spans(original_lines, rules);
    if source_spans.is_empty() {
        return translation_lines.to_vec();
    }
    let translated_spans = collect_translated_wrapping_spans(translation_lines, rules);
    if translated_spans.is_empty() {
        return translation_lines.to_vec();
    }
    let mut normalized_lines = translation_lines.to_vec();
    for (source_span, translated_span) in source_spans.iter().zip(translated_spans.iter()) {
        let replace_left = translated_span.left.character != source_span.pair.0;
        let replace_right = translated_span.right.character != source_span.pair.1;
        if translated_span.left.line_index == translated_span.right.line_index
            && translated_span.left.char_index < translated_span.right.char_index
        {
            if replace_right {
                normalized_lines[translated_span.right.line_index] = replace_char_at(
                    &normalized_lines[translated_span.right.line_index],
                    translated_span.right.char_index,
                    &source_span.pair.1,
                );
            }
            if replace_left {
                normalized_lines[translated_span.left.line_index] = replace_char_at(
                    &normalized_lines[translated_span.left.line_index],
                    translated_span.left.char_index,
                    &source_span.pair.0,
                );
            }
        } else {
            if replace_left {
                normalized_lines[translated_span.left.line_index] = replace_char_at(
                    &normalized_lines[translated_span.left.line_index],
                    translated_span.left.char_index,
                    &source_span.pair.0,
                );
            }
            if replace_right {
                normalized_lines[translated_span.right.line_index] = replace_char_at(
                    &normalized_lines[translated_span.right.line_index],
                    translated_span.right.char_index,
                    &source_span.pair.1,
                );
            }
        }
    }
    normalized_lines
}

fn collect_source_wrapping_spans(lines: &[String], rules: &TextPlanRules) -> Vec<WrappingSpan> {
    collect_wrapping_spans(lines, &rules.preserve_wrapping_punctuation_pairs, true)
}

fn collect_translated_wrapping_spans(lines: &[String], rules: &TextPlanRules) -> Vec<WrappingSpan> {
    let mut pairs = rules.preserve_wrapping_punctuation_pairs.clone();
    for pair in [
        ("“", "”"),
        ("‘", "’"),
        ("\"", "\""),
        ("'", "'"),
        ("＂", "＂"),
        ("「", "」"),
        ("『", "』"),
        ("《", "》"),
        ("〈", "〉"),
        ("（", "）"),
        ("(", ")"),
    ] {
        let pair_value = (pair.0.to_string(), pair.1.to_string());
        if !pairs.contains(&pair_value) {
            pairs.push(pair_value);
        }
    }
    collect_wrapping_spans(lines, &pairs, false)
}

fn collect_wrapping_spans(
    lines: &[String],
    pair_definitions: &[(String, String)],
    allow_mismatched_right: bool,
) -> Vec<WrappingSpan> {
    let visible_chars = collect_visible_chars(lines);
    let mut spans = Vec::new();
    let mut stack: Vec<(WrappingBoundary, (String, String))> = Vec::new();
    for boundary in visible_chars {
        let left_pair = pair_definitions
            .iter()
            .find(|(left, _right)| left == &boundary.character)
            .cloned();
        let is_right = pair_definitions
            .iter()
            .any(|(_left, right)| right == &boundary.character);
        if is_right && !stack.is_empty() {
            let Some((left_boundary, expected_pair)) = stack.pop() else {
                continue;
            };
            if expected_pair.1 == boundary.character || allow_mismatched_right {
                let pair = if expected_pair.1 == boundary.character {
                    expected_pair
                } else {
                    (left_boundary.character.clone(), boundary.character.clone())
                };
                spans.push(WrappingSpan {
                    left: left_boundary,
                    right: boundary,
                    pair,
                });
            } else {
                stack.push((left_boundary, expected_pair));
            }
            continue;
        }
        if let Some(pair) = left_pair {
            stack.push((boundary, pair));
        }
    }
    spans
}

fn collect_visible_chars(lines: &[String]) -> Vec<WrappingBoundary> {
    let mut boundaries = Vec::new();
    for (line_index, line) in lines.iter().enumerate() {
        for (char_index, character) in line.chars().enumerate() {
            if character.is_whitespace() {
                continue;
            }
            boundaries.push(WrappingBoundary {
                line_index,
                char_index,
                character: character.to_string(),
            });
        }
    }
    boundaries
}

pub(super) fn replace_char_at(text: &str, char_index: usize, replacement: &str) -> String {
    let Some(byte_index) = text.char_indices().nth(char_index).map(|(index, _)| index) else {
        return text.to_string();
    };
    let next_index = text[byte_index..]
        .chars()
        .next()
        .map(|character| byte_index + character.len_utf8())
        .unwrap_or(byte_index);
    format!(
        "{}{}{}",
        &text[..byte_index],
        replacement,
        &text[next_index..],
    )
}
