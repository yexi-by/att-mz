//! 普通占位符候选扫描。

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

use super::RuleCandidateTextRules;
use super::plugin_source::compile_rule_candidate_text_rules;
use crate::native_core::controls::{
    RawControlSequenceCandidate, iter_control_sequence_spans, iter_raw_control_sequence_candidates,
    iter_standard_control_sequence_spans,
};
use crate::native_core::models::{CompiledRules, ControlSpan, SpanSource};

#[derive(Debug, Deserialize)]
pub(super) struct PlaceholderTextInput {
    pub(super) source_name: String,
    pub(super) text: String,
}

#[derive(Debug, Clone, Serialize)]
pub(super) struct PlaceholderCandidateOutput {
    pub(super) marker: String,
    pub(super) count: usize,
    pub(super) sources: Vec<String>,
    pub(super) standard_covered: bool,
    pub(super) custom_covered: bool,
    pub(super) covered: bool,
}

pub(super) struct PlaceholderRuleCandidateScan {
    pub(super) candidates: Vec<PlaceholderCandidateOutput>,
    pub(super) scanned_text_count: usize,
}

struct PlaceholderOccurrence {
    marker: String,
    source_name: String,
    standard_covered: bool,
    custom_covered: bool,
}

struct PlaceholderCandidateAccumulator {
    marker: String,
    count: usize,
    sources: BTreeSet<String>,
    standard_covered: bool,
    custom_covered: bool,
    first_order: usize,
}

pub(super) fn scan_placeholder_rule_candidates(
    texts: &[PlaceholderTextInput],
    text_rules: RuleCandidateTextRules,
) -> Result<PlaceholderRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let text_occurrences = texts
        .par_iter()
        .map(|input| scan_placeholder_text(input, &compiled_rules.control_rules))
        .collect::<Result<Vec<_>, String>>()?;
    let mut candidates_by_marker: BTreeMap<String, PlaceholderCandidateAccumulator> =
        BTreeMap::new();
    let mut next_order = 0usize;
    for occurrences in text_occurrences {
        for occurrence in occurrences {
            let accumulator = candidates_by_marker
                .entry(occurrence.marker.clone())
                .or_insert_with(|| {
                    let first_order = next_order;
                    next_order += 1;
                    PlaceholderCandidateAccumulator {
                        marker: occurrence.marker.clone(),
                        count: 0,
                        sources: BTreeSet::new(),
                        standard_covered: false,
                        custom_covered: false,
                        first_order,
                    }
                });
            accumulator.count += 1;
            accumulator.sources.insert(occurrence.source_name);
            accumulator.standard_covered =
                accumulator.standard_covered || occurrence.standard_covered;
            accumulator.custom_covered = accumulator.custom_covered || occurrence.custom_covered;
        }
    }

    let mut candidates = candidates_by_marker
        .into_values()
        .map(|candidate| {
            let covered = candidate.standard_covered || candidate.custom_covered;
            (
                candidate.standard_covered,
                candidate.custom_covered,
                candidate.marker.to_lowercase(),
                candidate.first_order,
                PlaceholderCandidateOutput {
                    marker: candidate.marker,
                    count: candidate.count,
                    sources: candidate.sources.into_iter().collect(),
                    standard_covered: candidate.standard_covered,
                    custom_covered: candidate.custom_covered,
                    covered,
                },
            )
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|left, right| {
        (&left.0, &left.1, &left.2, left.3).cmp(&(&right.0, &right.1, &right.2, right.3))
    });

    Ok(PlaceholderRuleCandidateScan {
        candidates: candidates
            .into_iter()
            .map(|(_standard, _custom, _marker_key, _order, candidate)| candidate)
            .collect(),
        scanned_text_count: texts.len(),
    })
}

fn scan_placeholder_text(
    input: &PlaceholderTextInput,
    rules: &CompiledRules,
) -> Result<Vec<PlaceholderOccurrence>, String> {
    if !input.text.contains('\\') {
        return Ok(Vec::new());
    }
    let raw_candidates = iter_raw_control_sequence_candidates(&input.text);
    if raw_candidates.is_empty() {
        return Ok(Vec::new());
    }
    let covered_spans = if rules.custom_placeholder_rules.is_empty()
        && rules.structured_placeholder_rules.is_empty()
    {
        iter_standard_control_sequence_spans(&input.text)
    } else {
        iter_control_sequence_spans(&input.text, rules)?
    };
    let mut occurrences = Vec::new();
    for raw_candidate in raw_candidates {
        let Some(covered_span) = find_covering_span(&raw_candidate, &covered_spans) else {
            occurrences.push(PlaceholderOccurrence {
                marker: raw_candidate.original,
                source_name: input.source_name.clone(),
                standard_covered: false,
                custom_covered: false,
            });
            continue;
        };
        occurrences.push(PlaceholderOccurrence {
            marker: covered_span.original.clone(),
            source_name: input.source_name.clone(),
            standard_covered: matches!(covered_span.source, SpanSource::Standard),
            custom_covered: matches!(covered_span.source, SpanSource::Custom),
        });
    }
    Ok(occurrences)
}

fn find_covering_span<'a>(
    candidate: &RawControlSequenceCandidate,
    spans: &'a [ControlSpan],
) -> Option<&'a ControlSpan> {
    for span in spans {
        if matches!(span.source, SpanSource::Standard) {
            if span.start <= candidate.start && span.end >= candidate.end {
                return Some(span);
            }
            continue;
        }
        if candidate.start < span.end && candidate.end > span.start {
            return Some(span);
        }
    }
    None
}
