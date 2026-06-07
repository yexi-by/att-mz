//! Note 标签候选扫描。

use rayon::prelude::*;
use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

use super::RuleCandidateTextRules;
use super::plugin_source::{
    compile_rule_candidate_text_rules, normalize_extraction_text,
    should_translate_plugin_source_text,
};
use crate::native_core::note_sources::collect_note_tag_sources_in_value;
use crate::native_core::rules::{MAP_FILE_RE, NOTE_TAG_RE};
use crate::native_core::write_back_plan::normalize_visible_text_for_extraction;

#[derive(Debug, Clone, Serialize)]
pub(super) struct NoteTagCandidateOutput {
    pub(super) file_name: String,
    pub(super) tag_name: String,
    pub(super) hit_count: usize,
    pub(super) value_hit_count: usize,
    pub(super) translatable_hit_count: usize,
    pub(super) matched_file_count: usize,
    pub(super) sample_locations: Vec<String>,
    pub(super) sample_values: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub(super) struct NoteTagHitOutput {
    pub(super) file_name: String,
    pub(super) tag_name: String,
    pub(super) location_path: String,
    pub(super) original_text: String,
    #[serde(skip_serializing)]
    pub(super) raw_text: String,
    pub(super) translatable: bool,
}

#[derive(Debug, Clone, Serialize)]
pub(super) struct NoteTagSourceDetailOutput {
    pub(super) file_name: String,
    pub(super) location_prefix: String,
}

pub(super) struct NoteTagRuleCandidateScan {
    pub(super) candidates: Vec<NoteTagCandidateOutput>,
    pub(super) hit_details: Vec<NoteTagHitOutput>,
    pub(super) source_details: Vec<NoteTagSourceDetailOutput>,
    pub(super) scanned_source_count: usize,
    pub(super) candidate_value_count: usize,
    pub(super) value_hit_count: usize,
    pub(super) translatable_value_count: usize,
}

struct NoteTagCandidateAccumulator {
    file_name: String,
    tag_name: String,
    hit_count: usize,
    value_hit_count: usize,
    translatable_hit_count: usize,
    matched_files: BTreeSet<String>,
    sample_locations: Vec<String>,
    sample_values: Vec<String>,
}

pub(super) fn scan_note_tag_rule_candidates(
    data_files: &BTreeMap<String, Value>,
    text_rules: RuleCandidateTextRules,
) -> Result<NoteTagRuleCandidateScan, String> {
    let data_file_refs = data_files
        .iter()
        .map(|(file_name, data)| (file_name.as_str(), data))
        .collect::<Vec<_>>();
    scan_note_tag_rule_candidates_from_refs(&data_file_refs, text_rules)
}

pub(super) fn scan_note_tag_rule_candidates_from_refs(
    data_files: &[(&str, &Value)],
    text_rules: RuleCandidateTextRules,
) -> Result<NoteTagRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let source_groups = data_files
        .par_iter()
        .filter(|(file_name, data)| {
            *file_name != "plugins.js" && file_name.ends_with(".json") && !data.is_string()
        })
        .map(|(file_name, data)| {
            let mut sources = Vec::new();
            collect_note_tag_sources_in_value(file_name, data, &mut Vec::new(), &mut sources);
            sources
        })
        .collect::<Vec<_>>();
    let sources = source_groups.into_iter().flatten().collect::<Vec<_>>();

    let mut candidates_by_key: BTreeMap<(String, String), NoteTagCandidateAccumulator> =
        BTreeMap::new();
    let mut hit_details = Vec::new();
    for source in &sources {
        let file_pattern = candidate_file_pattern(&source.file_name);
        for captures in NOTE_TAG_RE.captures_iter(&source.note_text) {
            let Some(tag_match) = captures.name("tag") else {
                continue;
            };
            let tag_name = tag_match.as_str().trim();
            if tag_name.is_empty() {
                continue;
            }
            let key = (file_pattern.clone(), tag_name.to_string());
            let accumulator =
                candidates_by_key
                    .entry(key)
                    .or_insert_with(|| NoteTagCandidateAccumulator {
                        file_name: file_pattern.clone(),
                        tag_name: tag_name.to_string(),
                        hit_count: 0,
                        value_hit_count: 0,
                        translatable_hit_count: 0,
                        matched_files: BTreeSet::new(),
                        sample_locations: Vec::new(),
                        sample_values: Vec::new(),
                    });
            accumulator.hit_count += 1;
            accumulator.matched_files.insert(source.file_name.clone());

            let Some(value_match) = captures.name("value") else {
                continue;
            };
            accumulator.value_hit_count += 1;
            let normalized_value = normalize_extraction_text(
                &normalize_visible_text_for_extraction(value_match.as_str()),
                &compiled_rules.strip_wrapping_punctuation_pairs,
            );
            let translatable =
                should_translate_plugin_source_text(&normalized_value, &compiled_rules)?;
            if translatable {
                accumulator.translatable_hit_count += 1;
            }
            let location = format!("{}/note/{}", source.location_prefix, tag_name);
            hit_details.push(NoteTagHitOutput {
                file_name: source.file_name.clone(),
                tag_name: tag_name.to_string(),
                location_path: location.clone(),
                original_text: normalized_value.clone(),
                raw_text: value_match.as_str().to_string(),
                translatable,
            });
            push_sample(&mut accumulator.sample_values, &normalized_value);
            push_sample(&mut accumulator.sample_locations, &location);
        }
    }

    let candidates = candidates_by_key
        .into_values()
        .map(|candidate| NoteTagCandidateOutput {
            file_name: candidate.file_name,
            tag_name: candidate.tag_name,
            hit_count: candidate.hit_count,
            value_hit_count: candidate.value_hit_count,
            translatable_hit_count: candidate.translatable_hit_count,
            matched_file_count: candidate.matched_files.len(),
            sample_locations: candidate.sample_locations,
            sample_values: candidate.sample_values,
        })
        .collect::<Vec<_>>();
    let candidate_value_count = candidates
        .iter()
        .map(|candidate| candidate.hit_count)
        .sum::<usize>();
    let value_hit_count = candidates
        .iter()
        .map(|candidate| candidate.value_hit_count)
        .sum::<usize>();
    let translatable_value_count = candidates
        .iter()
        .map(|candidate| candidate.translatable_hit_count)
        .sum::<usize>();
    let source_details = sources
        .iter()
        .map(|source| NoteTagSourceDetailOutput {
            file_name: source.file_name.clone(),
            location_prefix: source.location_prefix.clone(),
        })
        .collect::<Vec<_>>();

    Ok(NoteTagRuleCandidateScan {
        candidates,
        hit_details,
        source_details,
        scanned_source_count: sources.len(),
        candidate_value_count,
        value_hit_count,
        translatable_value_count,
    })
}

fn candidate_file_pattern(file_name: &str) -> String {
    if MAP_FILE_RE.is_match(file_name) {
        return "Map*.json".to_string();
    }
    file_name.to_string()
}

fn push_sample(samples: &mut Vec<String>, value: &str) {
    if value.is_empty() || samples.len() >= 5 || samples.iter().any(|sample| sample == value) {
        return;
    }
    samples.push(value.to_string());
}

#[cfg(test)]
mod tests {
    use super::scan_note_tag_rule_candidates;
    use crate::native_core::scope_index::RuleCandidateTextRules;
    use serde_json::json;
    use std::collections::BTreeMap;

    fn text_rules() -> RuleCandidateTextRules {
        RuleCandidateTextRules {
            custom_placeholder_rules: Vec::new(),
            structured_placeholder_rules: Vec::new(),
            strip_wrapping_punctuation_pairs: Vec::new(),
            source_text_required_pattern: r"[\s\S]".to_string(),
            source_text_exclusion_profile: "none".to_string(),
        }
    }

    #[test]
    fn note_tag_candidates_group_map_files_and_return_hit_details() {
        let mut data_files = BTreeMap::new();
        data_files.insert(
            "Map001.json".to_string(),
            json!({
                "events": [
                    null,
                    {"id": 1, "note": "<Flavor:古い井戸>\n<Empty:>"}
                ]
            }),
        );
        data_files.insert(
            "Items.json".to_string(),
            json!([null, {"id": 1, "note": "<Flavor:薬草>"}]),
        );

        let scan = scan_note_tag_rule_candidates(&data_files, text_rules()).expect("扫描应成功");

        assert_eq!(scan.scanned_source_count, 2);
        assert_eq!(scan.candidate_value_count, 3);
        assert_eq!(scan.value_hit_count, 3);
        assert_eq!(scan.translatable_value_count, 2);
        assert!(
            scan.candidates
                .iter()
                .any(|candidate| candidate.file_name == "Map*.json"
                    && candidate.tag_name == "Flavor"
                    && candidate.translatable_hit_count == 1)
        );
        assert!(
            scan.hit_details
                .iter()
                .any(|hit| hit.location_path == "Items.json/1/note/Flavor"
                    && hit.original_text == "薬草"
                    && hit.translatable)
        );
    }
}
