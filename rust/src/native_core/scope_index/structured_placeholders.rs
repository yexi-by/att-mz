//! 结构化占位符候选扫描。

use rayon::prelude::*;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::LazyLock;

use super::RuleCandidateTextRules;
use super::plugin_source::compile_rule_candidate_text_rules;
use crate::native_core::models::{CompiledRules, CompiledStructuredRule};

pub(super) static STRUCTURED_SHELL_CANDIDATE_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"<[^<>\r\n]{1,160}(?:[:：=])[^<>\r\n]{0,240}>")
            .unwrap_or_else(|error| panic!("结构化占位符候选正则编译失败: {error}")),
        Regex::new(r"◆<[^<>\r\n]{1,160}>[^\s<>\r\n]?")
            .unwrap_or_else(|error| panic!("结构化占位符候选正则编译失败: {error}")),
        Regex::new(r"【[^】\r\n]{1,160}[:：][^】\r\n]{0,240}】")
            .unwrap_or_else(|error| panic!("结构化占位符候选正则编译失败: {error}")),
    ]
});

#[derive(Debug, Deserialize)]
pub(super) struct StructuredPlaceholderTextInput {
    pub(super) location_path: String,
    pub(super) line_number: usize,
    pub(super) text: String,
}

#[derive(Debug, Clone, Serialize)]
pub(super) struct StructuredPlaceholderCandidateOutput {
    pub(super) location_path: String,
    pub(super) line_number: usize,
    pub(super) candidate: String,
    pub(super) covered: bool,
    pub(super) matching_rules: Vec<String>,
}

pub(super) struct StructuredPlaceholderRuleCandidateScan {
    pub(super) candidates: Vec<StructuredPlaceholderCandidateOutput>,
    pub(super) scanned_text_count: usize,
}

struct StructuredCandidateMatch {
    start: usize,
    end: usize,
    candidate: String,
}

struct StructuredCoveredRange {
    start: usize,
    end: usize,
    rule_name: String,
}

pub(super) fn scan_structured_placeholder_rule_candidates(
    texts: &[StructuredPlaceholderTextInput],
    text_rules: RuleCandidateTextRules,
) -> Result<StructuredPlaceholderRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let candidates_by_text = texts
        .par_iter()
        .map(|input| scan_structured_placeholder_text(input, &compiled_rules.control_rules))
        .collect::<Result<Vec<_>, String>>()?;
    Ok(StructuredPlaceholderRuleCandidateScan {
        candidates: candidates_by_text.into_iter().flatten().collect(),
        scanned_text_count: texts.len(),
    })
}

fn scan_structured_placeholder_text(
    input: &StructuredPlaceholderTextInput,
    rules: &CompiledRules,
) -> Result<Vec<StructuredPlaceholderCandidateOutput>, String> {
    let candidate_matches = iter_structured_shell_candidate_matches(&input.text);
    if candidate_matches.is_empty() {
        return Ok(Vec::new());
    }
    let covered_ranges =
        structured_rule_covered_ranges(&input.text, &rules.structured_placeholder_rules)?;
    let candidates = candidate_matches
        .into_iter()
        .map(|candidate_match| {
            let matching_rules = covered_ranges
                .iter()
                .filter(|range| {
                    range.start <= candidate_match.start && range.end >= candidate_match.end
                })
                .map(|range| range.rule_name.clone())
                .collect::<Vec<_>>();
            StructuredPlaceholderCandidateOutput {
                location_path: input.location_path.clone(),
                line_number: input.line_number,
                candidate: candidate_match.candidate,
                covered: !matching_rules.is_empty(),
                matching_rules,
            }
        })
        .collect();
    Ok(candidates)
}

fn iter_structured_shell_candidate_matches(text: &str) -> Vec<StructuredCandidateMatch> {
    if !may_contain_structured_shell_candidate(text) {
        return Vec::new();
    }
    let mut matches = Vec::new();
    for pattern in STRUCTURED_SHELL_CANDIDATE_PATTERNS.iter() {
        for matched in pattern.find_iter(text) {
            matches.push(StructuredCandidateMatch {
                start: matched.start(),
                end: matched.end(),
                candidate: matched.as_str().to_string(),
            });
        }
    }
    matches.sort_by(|left, right| {
        (
            left.start,
            usize::MAX - (left.end - left.start),
            &left.candidate,
        )
            .cmp(&(
                right.start,
                usize::MAX - (right.end - right.start),
                &right.candidate,
            ))
    });

    let mut selected = Vec::new();
    let mut protected_until = 0usize;
    for candidate_match in matches {
        if candidate_match.start < protected_until {
            continue;
        }
        protected_until = candidate_match.end;
        selected.push(candidate_match);
    }
    selected
}

fn may_contain_structured_shell_candidate(text: &str) -> bool {
    (text.contains('<') && text.contains('>')) || (text.contains('【') && text.contains('】'))
}

fn structured_rule_covered_ranges(
    text: &str,
    rules: &[CompiledStructuredRule],
) -> Result<Vec<StructuredCoveredRange>, String> {
    let mut ranges = Vec::new();
    for rule in rules {
        for captures_result in rule.pattern.captures_iter(text) {
            let captures = captures_result.map_err(|error| {
                format!("结构化占位符规则 {} 匹配失败: {error}", rule.rule_name)
            })?;
            let full_match = captures
                .get(0)
                .ok_or_else(|| format!("结构化占位符规则 {} 缺少完整匹配", rule.rule_name))?;
            ranges.push(StructuredCoveredRange {
                start: full_match.start(),
                end: full_match.end(),
                rule_name: rule.rule_name.clone(),
            });
        }
    }
    Ok(ranges)
}

#[cfg(test)]
mod tests {
    use super::{StructuredPlaceholderTextInput, scan_structured_placeholder_rule_candidates};
    use crate::native_core::models::NativeStructuredPlaceholderRule;
    use crate::native_core::scope_index::RuleCandidateTextRules;
    use std::collections::HashMap;

    fn text_rules(
        structured_placeholder_rules: Vec<NativeStructuredPlaceholderRule>,
    ) -> RuleCandidateTextRules {
        RuleCandidateTextRules {
            custom_placeholder_rules: Vec::new(),
            structured_placeholder_rules,
            strip_wrapping_punctuation_pairs: Vec::new(),
            source_text_required_pattern: r"[\s\S]".to_string(),
            source_text_exclusion_profile: "none".to_string(),
        }
    }

    #[test]
    fn structured_placeholder_candidates_report_covered_and_uncovered_shells() {
        let mut protected_groups = HashMap::new();
        protected_groups.insert("label".to_string(), "[CUSTOM_LABEL_{index}]".to_string());
        let rules = text_rules(vec![NativeStructuredPlaceholderRule {
            rule_name: "angle-label".to_string(),
            rule_type: "paired_shell".to_string(),
            pattern_text: r"<(?P<label>[^:：]+)[:：](?P<body>[^>]+)>".to_string(),
            translatable_group: "body".to_string(),
            protected_groups,
        }]);
        let texts = vec![StructuredPlaceholderTextInput {
            location_path: "Map001.json/1/0".to_string(),
            line_number: 7,
            text: "<名前:アリス> と 【未登録:本文】".to_string(),
        }];

        let scan = scan_structured_placeholder_rule_candidates(&texts, rules).expect("扫描应成功");

        assert_eq!(scan.scanned_text_count, 1);
        assert_eq!(scan.candidates.len(), 2);
        assert_eq!(scan.candidates[0].candidate, "<名前:アリス>");
        assert!(scan.candidates[0].covered);
        assert_eq!(scan.candidates[0].matching_rules, vec!["angle-label"]);
        assert_eq!(scan.candidates[1].candidate, "【未登録:本文】");
        assert!(!scan.candidates[1].covered);
    }
}
