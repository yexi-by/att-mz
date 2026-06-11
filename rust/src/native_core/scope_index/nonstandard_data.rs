//! 非标准 data JSON 候选扫描。

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

use super::path_templates::{
    PathTemplateError, json_path_parts_to_parent_slash_path, json_path_parts_to_slash_path,
    jsonpath_matches_template, parse_json_path, parse_json_path_message,
};
use super::plugin_source::{
    CompiledRuleCandidateTextRules, ENGLISH_ASSET_EXTENSION_RE, ENGLISH_ASSET_PATH_RE,
    NUMBER_LIKE_RE, compile_rule_candidate_text_rules, normalize_extraction_text,
    should_translate_plugin_source_text,
};
use super::{RuleCandidateOutput, RuleCandidateTextRules};
use crate::native_core::write_back_plan::normalize_visible_text_for_extraction;

#[derive(Debug, Deserialize)]
pub(super) struct NonstandardDataFileInput {
    pub(super) file_name: String,
    pub(super) data: Value,
    #[serde(default)]
    pub(super) raw_text: String,
}

#[derive(Debug, Serialize)]
pub(super) struct NonstandardDataFileScanOutput {
    file: String,
    string_leaf_count: usize,
    candidate_count: usize,
    leaves: Vec<NonstandardDataLeafOutput>,
}

#[derive(Debug, Clone, Serialize)]
struct NonstandardDataLeafOutput {
    path: String,
    value: Value,
    value_type: &'static str,
    from_json_string: bool,
}

pub(super) struct NonstandardDataRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) file_scans: Vec<NonstandardDataFileScanOutput>,
    pub(super) nonstandard_file_count: usize,
}

#[derive(Debug, Clone)]
pub(super) struct NonstandardDataTextRuleInput {
    pub(super) file_name: String,
    pub(super) file_hash: String,
    pub(super) path_templates: Vec<String>,
    pub(super) excluded_path_templates: Vec<String>,
    pub(super) skipped: bool,
}

#[derive(Debug, Clone)]
pub(super) struct NonstandardDataManagedText {
    pub(super) file_name: String,
    pub(super) json_path: String,
    pub(super) raw_text: String,
}

pub(super) enum NonstandardDataManagedTextError {
    Stale(String),
    ReviewIncomplete { unreviewed_count: usize },
}

#[derive(Debug, Deserialize)]
pub(super) struct NonstandardDataRuleCoverageInput {
    #[serde(default)]
    rules: Vec<NonstandardDataRuleCoverageRuleInput>,
    #[serde(default)]
    files: Vec<NonstandardDataRuleCoverageFileInput>,
    #[serde(default)]
    candidates: Vec<NonstandardDataRuleCoverageCandidateInput>,
}

#[derive(Debug, Deserialize)]
struct NonstandardDataRuleCoverageRuleInput {
    file: String,
    #[serde(default)]
    file_hash: Option<String>,
    #[serde(default)]
    paths: Vec<String>,
    #[serde(default)]
    excluded_paths: Vec<String>,
    #[serde(default)]
    skipped: bool,
}

#[derive(Debug, Deserialize)]
struct NonstandardDataRuleCoverageFileInput {
    file: String,
    #[serde(default)]
    file_hash: Option<String>,
    #[serde(default)]
    leaves: Vec<NonstandardDataRuleCoverageLeafInput>,
}

#[derive(Debug, Deserialize)]
struct NonstandardDataRuleCoverageLeafInput {
    path: String,
    value_type: String,
    #[serde(default)]
    value: Value,
}

#[derive(Debug, Deserialize)]
struct NonstandardDataRuleCoverageCandidateInput {
    file: String,
    json_path: String,
}

#[derive(Debug, Serialize)]
struct NonstandardDataRuleHitDetailOutput {
    file: String,
    json_path: String,
    location_path: String,
    original_text: String,
    path_template: String,
    role: &'static str,
    rule_index: usize,
    translation_prefix: String,
}

#[derive(Debug, Serialize)]
struct NonstandardDataPathHitCountOutput {
    candidate_hit_count: usize,
    path_template: String,
    role: &'static str,
    string_hit_count: usize,
}

#[derive(Debug, Serialize)]
struct NonstandardDataRuleSummaryOutput {
    excluded_path_hit_counts: Vec<NonstandardDataPathHitCountOutput>,
    file: String,
    rule_index: usize,
    skipped: bool,
    path_hit_counts: Vec<NonstandardDataPathHitCountOutput>,
}

#[derive(Debug, Serialize)]
struct NonstandardDataStaleReasonOutput {
    code: &'static str,
    file: String,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    path_template: Option<String>,
}

#[derive(Debug)]
struct NonstandardDataCoverageHits {
    candidate_hits: BTreeSet<(String, String)>,
    details: Vec<NonstandardDataRuleHitDetailOutput>,
    path_hit_counts: Vec<NonstandardDataPathHitCountOutput>,
    stale_reasons: Vec<NonstandardDataStaleReasonOutput>,
}

struct NonstandardDataFileScan {
    file_name: String,
    candidates: Vec<RuleCandidateOutput>,
    leaves: Vec<NonstandardDataLeafOutput>,
}

pub(super) fn scan_nonstandard_data_rule_coverage(
    input: NonstandardDataRuleCoverageInput,
) -> Result<Value, String> {
    let files_by_name = input
        .files
        .into_iter()
        .map(|file| (file.file.clone(), file))
        .collect::<BTreeMap<_, _>>();
    let candidate_paths = input
        .candidates
        .into_iter()
        .map(|candidate| (candidate.file, candidate.json_path))
        .collect::<BTreeSet<_>>();
    let mut seen_files: BTreeSet<String> = BTreeSet::new();
    let mut translated_candidate_paths: BTreeSet<(String, String)> = BTreeSet::new();
    let mut excluded_candidate_paths: BTreeSet<(String, String)> = BTreeSet::new();
    let mut skipped_files: BTreeSet<String> = BTreeSet::new();
    let mut rule_details = Vec::new();
    let mut hit_details = Vec::new();
    let mut rule_summaries = Vec::new();
    let mut stale_reasons = Vec::new();
    let mut translation_prefixes = BTreeSet::new();

    for (rule_index, rule) in input.rules.into_iter().enumerate() {
        if !seen_files.insert(rule.file.clone()) {
            return Err(format!(
                "非标准 data 文件规则不能重复声明 file: {}",
                rule.file
            ));
        }
        let Some(file_input) = files_by_name.get(&rule.file) else {
            stale_reasons.push(NonstandardDataStaleReasonOutput {
                code: "file_missing",
                file: rule.file.clone(),
                message: format!("非标准 data 文件规则已过期: 文件不存在: {}", rule.file),
                path_template: None,
            });
            rule_summaries.push(NonstandardDataRuleSummaryOutput {
                excluded_path_hit_counts: Vec::new(),
                file: rule.file.clone(),
                rule_index,
                skipped: rule.skipped,
                path_hit_counts: Vec::new(),
            });
            continue;
        };
        let file_leaves = &file_input.leaves;
        if let Some(rule_file_hash) = &rule.file_hash
            && file_input.file_hash.as_ref() != Some(rule_file_hash)
        {
            stale_reasons.push(NonstandardDataStaleReasonOutput {
                code: "file_hash_mismatch",
                file: rule.file.clone(),
                message: format!(
                    "非标准 data 文件规则已过期: 文件 hash 不匹配: {}",
                    rule.file
                ),
                path_template: None,
            });
        }
        if rule.skipped {
            skipped_files.insert(rule.file.clone());
            rule_details.push(json!({
                "file": rule.file,
                "skipped": true,
                "translated_candidate_count": 0,
                "excluded_candidate_count": 0
            }));
            rule_summaries.push(NonstandardDataRuleSummaryOutput {
                excluded_path_hit_counts: Vec::new(),
                file: rule.file,
                rule_index,
                skipped: true,
                path_hit_counts: Vec::new(),
            });
            continue;
        }

        let translated = collect_rule_hits(
            &rule.file,
            &rule.paths,
            file_leaves,
            &candidate_paths,
            true,
            rule_index,
            "translated",
        )?;
        let excluded = collect_rule_hits(
            &rule.file,
            &rule.excluded_paths,
            file_leaves,
            &candidate_paths,
            true,
            rule_index,
            "excluded",
        )?;
        let translated_hits = translated.candidate_hits;
        let excluded_hits = excluded.candidate_hits;
        let overlap = translated_hits
            .intersection(&excluded_hits)
            .cloned()
            .collect::<BTreeSet<_>>();
        if !overlap.is_empty() {
            return Err(format!(
                "非标准 data 文件规则 paths 与 excluded_paths 命中同一候选: {}",
                format_path_pairs(&overlap)
            ));
        }
        translated_candidate_paths.extend(translated_hits.iter().cloned());
        excluded_candidate_paths.extend(excluded_hits.iter().cloned());
        for detail in translated.details {
            translation_prefixes.insert(detail.translation_prefix.clone());
            hit_details.push(detail);
        }
        hit_details.extend(excluded.details);
        stale_reasons.extend(translated.stale_reasons);
        stale_reasons.extend(excluded.stale_reasons);
        rule_summaries.push(NonstandardDataRuleSummaryOutput {
            excluded_path_hit_counts: excluded.path_hit_counts,
            file: rule.file.clone(),
            rule_index,
            skipped: false,
            path_hit_counts: translated.path_hit_counts,
        });
        rule_details.push(json!({
            "file": rule.file,
            "skipped": false,
            "translated_candidate_count": translated_hits.len(),
            "excluded_candidate_count": excluded_hits.len(),
            "paths": rule.paths,
            "excluded_paths": rule.excluded_paths
        }));
    }

    let reviewed_paths = translated_candidate_paths
        .union(&excluded_candidate_paths)
        .cloned()
        .collect::<BTreeSet<_>>();
    let skipped_candidate_paths = candidate_paths
        .iter()
        .filter(|(file_name, _path)| skipped_files.contains(file_name))
        .cloned()
        .collect::<BTreeSet<_>>();
    let unreviewed_candidate_paths = candidate_paths
        .difference(&reviewed_paths)
        .cloned()
        .collect::<BTreeSet<_>>()
        .difference(&skipped_candidate_paths)
        .cloned()
        .collect::<BTreeSet<_>>();

    Ok(json!({
        "rules": rule_details,
        "translated_candidates": path_pairs_to_json_array(&translated_candidate_paths),
        "excluded_candidates": path_pairs_to_json_array(&excluded_candidate_paths),
        "hit_details": hit_details,
        "rule_summaries": rule_summaries,
        "skipped_files": skipped_files.into_iter().collect::<Vec<_>>(),
        "stale_reasons": stale_reasons,
        "translation_prefixes": translation_prefixes.into_iter().collect::<Vec<_>>(),
        "unreviewed_candidates": path_pairs_to_json_array(&unreviewed_candidate_paths),
        "reviewed_candidate_count": reviewed_paths.len()
    }))
}

pub(super) fn scan_nonstandard_data_rule_candidates(
    files: &[NonstandardDataFileInput],
    text_rules: RuleCandidateTextRules,
) -> Result<NonstandardDataRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let mut file_refs: Vec<&NonstandardDataFileInput> = files.iter().collect();
    file_refs.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let file_scans = file_refs
        .par_iter()
        .map(|file| scan_nonstandard_data_file(file, Some(&compiled_rules)))
        .collect::<Result<Vec<_>, String>>()?;
    let file_summaries = file_scans
        .iter()
        .map(|scan| NonstandardDataFileScanOutput {
            file: scan.file_name.clone(),
            string_leaf_count: scan
                .leaves
                .iter()
                .filter(|leaf| leaf.value_type == "string")
                .count(),
            candidate_count: scan.candidates.len(),
            leaves: scan.leaves.clone(),
        })
        .collect();
    let candidates = file_scans
        .into_iter()
        .flat_map(|scan| scan.candidates)
        .collect();
    Ok(NonstandardDataRuleCandidateScan {
        candidates,
        file_scans: file_summaries,
        nonstandard_file_count: files.len(),
    })
}

pub(super) fn scan_nonstandard_data_file_leaves(
    files: &[NonstandardDataFileInput],
) -> Result<Vec<NonstandardDataFileScanOutput>, String> {
    let mut file_refs: Vec<&NonstandardDataFileInput> = files.iter().collect();
    file_refs.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let file_scans = file_refs
        .par_iter()
        .map(|file| scan_nonstandard_data_file(file, None))
        .collect::<Result<Vec<_>, String>>()?;
    Ok(file_scans
        .into_iter()
        .map(|scan| NonstandardDataFileScanOutput {
            file: scan.file_name,
            string_leaf_count: scan
                .leaves
                .iter()
                .filter(|leaf| leaf.value_type == "string")
                .count(),
            candidate_count: scan.candidates.len(),
            leaves: scan.leaves,
        })
        .collect())
}

pub(super) fn collect_nonstandard_data_managed_texts(
    files: &[NonstandardDataFileInput],
    rules: &[NonstandardDataTextRuleInput],
    text_rules: RuleCandidateTextRules,
) -> Result<Vec<NonstandardDataManagedText>, NonstandardDataManagedTextError> {
    if rules.is_empty() {
        return Ok(Vec::new());
    }
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)
        .map_err(NonstandardDataManagedTextError::Stale)?;
    let file_by_name = files
        .iter()
        .map(|file| (file.file_name.as_str(), file))
        .collect::<BTreeMap<_, _>>();
    let mut required_files = BTreeSet::new();
    for rule in rules {
        if rule.skipped {
            continue;
        }
        required_files.insert(rule.file_name.as_str());
        let file = file_by_name.get(rule.file_name.as_str()).ok_or_else(|| {
            NonstandardDataManagedTextError::Stale(format!(
                "非标准 data 文件规则已过期: 文件不存在: {}",
                rule.file_name
            ))
        })?;
        let current_hash = sha256_hex(&file.raw_text);
        if current_hash != rule.file_hash {
            return Err(NonstandardDataManagedTextError::Stale(format!(
                "非标准 data 文件规则已过期: 文件 hash 不匹配: {}",
                rule.file_name
            )));
        }
    }

    let scans = required_files
        .into_iter()
        .map(|file_name| {
            let file = file_by_name.get(file_name).ok_or_else(|| {
                NonstandardDataManagedTextError::Stale(format!(
                    "非标准 data 文件规则已过期: 文件不存在: {file_name}"
                ))
            })?;
            scan_nonstandard_data_file(file, Some(&compiled_rules))
                .map(|scan| (file_name.to_string(), scan))
                .map_err(NonstandardDataManagedTextError::Stale)
        })
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    validate_nonstandard_data_review_coverage(&scans, rules)?;

    let mut rows = Vec::new();
    let mut seen_paths: BTreeSet<(String, String)> = BTreeSet::new();
    for rule in rules {
        if rule.skipped || rule.path_templates.is_empty() {
            continue;
        }
        let scan = scans.get(&rule.file_name).ok_or_else(|| {
            NonstandardDataManagedTextError::Stale(format!(
                "非标准 data 文件规则已过期: 文件不存在: {}",
                rule.file_name
            ))
        })?;
        let string_leaf_map = scan
            .leaves
            .iter()
            .filter_map(|leaf| {
                if leaf.value_type != "string" {
                    return None;
                }
                leaf.value.as_str().map(|value| (leaf.path.as_str(), value))
            })
            .collect::<BTreeMap<_, _>>();
        for path_template in &rule.path_templates {
            let matched_paths = expand_rule_to_leaf_output_paths(path_template, &scan.leaves)
                .map_err(NonstandardDataManagedTextError::Stale)?;
            if matched_paths.is_empty() {
                return Err(NonstandardDataManagedTextError::Stale(format!(
                    "非标准 data 文件规则已过期: {} 路径没有命中当前字符串叶子: {}",
                    rule.file_name, path_template
                )));
            }
            for json_path in matched_paths {
                if !seen_paths.insert((rule.file_name.clone(), json_path.clone())) {
                    continue;
                }
                let Some(raw_text) = string_leaf_map.get(json_path.as_str()) else {
                    continue;
                };
                rows.push(NonstandardDataManagedText {
                    file_name: rule.file_name.clone(),
                    json_path,
                    raw_text: (*raw_text).to_string(),
                });
            }
        }
    }
    rows.sort_by(|left, right| {
        left.file_name
            .cmp(&right.file_name)
            .then_with(|| left.json_path.cmp(&right.json_path))
    });
    Ok(rows)
}

fn validate_nonstandard_data_review_coverage(
    scans: &BTreeMap<String, NonstandardDataFileScan>,
    rules: &[NonstandardDataTextRuleInput],
) -> Result<(), NonstandardDataManagedTextError> {
    let candidate_paths = scans
        .values()
        .flat_map(|scan| {
            scan.candidates.iter().filter_map(|candidate| {
                candidate
                    .json_path
                    .as_ref()
                    .map(|json_path| (candidate.source_file.clone(), json_path.clone()))
            })
        })
        .collect::<BTreeSet<_>>();
    let mut reviewed_paths = BTreeSet::new();
    let mut skipped_files = BTreeSet::new();
    for rule in rules {
        if rule.skipped {
            skipped_files.insert(rule.file_name.clone());
            continue;
        }
        let Some(scan) = scans.get(&rule.file_name) else {
            return Err(NonstandardDataManagedTextError::Stale(format!(
                "非标准 data 文件规则已过期: 文件不存在: {}",
                rule.file_name
            )));
        };
        let translated_hits =
            collect_rule_candidate_hits(&rule.file_name, &rule.path_templates, &scan.leaves)?;
        let excluded_hits = collect_rule_candidate_hits(
            &rule.file_name,
            &rule.excluded_path_templates,
            &scan.leaves,
        )?;
        let overlap = translated_hits
            .intersection(&excluded_hits)
            .cloned()
            .collect::<BTreeSet<_>>();
        if !overlap.is_empty() {
            return Err(NonstandardDataManagedTextError::ReviewIncomplete {
                unreviewed_count: overlap.len(),
            });
        }
        reviewed_paths.extend(translated_hits);
        reviewed_paths.extend(excluded_hits);
    }
    let unreviewed_count = candidate_paths
        .iter()
        .filter(|(file_name, _json_path)| !skipped_files.contains(file_name))
        .filter(|path| !reviewed_paths.contains(*path))
        .count();
    if unreviewed_count > 0 {
        return Err(NonstandardDataManagedTextError::ReviewIncomplete { unreviewed_count });
    }
    Ok(())
}

fn collect_rule_candidate_hits(
    file_name: &str,
    path_templates: &[String],
    leaves: &[NonstandardDataLeafOutput],
) -> Result<BTreeSet<(String, String)>, NonstandardDataManagedTextError> {
    let mut hits = BTreeSet::new();
    for path_template in path_templates {
        let matched_paths = expand_rule_to_leaf_output_paths(path_template, leaves)
            .map_err(NonstandardDataManagedTextError::Stale)?;
        if matched_paths.is_empty() {
            return Err(NonstandardDataManagedTextError::Stale(format!(
                "非标准 data 文件规则已过期: {file_name} 路径没有命中当前字符串叶子: {path_template}"
            )));
        }
        hits.extend(
            matched_paths
                .into_iter()
                .map(|json_path| (file_name.to_string(), json_path)),
        );
    }
    Ok(hits)
}

fn expand_rule_to_leaf_output_paths(
    path_template: &str,
    leaves: &[NonstandardDataLeafOutput],
) -> Result<Vec<String>, String> {
    let template_parts = parse_json_path_message(path_template)?;
    let mut matched_paths = Vec::new();
    for leaf in leaves {
        if leaf.value_type != "string" {
            continue;
        }
        if jsonpath_matches_template(&template_parts, &parse_json_path_message(&leaf.path)?) {
            matched_paths.push(leaf.path.clone());
        }
    }
    matched_paths.sort();
    Ok(matched_paths)
}

fn sha256_hex(text: &str) -> String {
    let digest = Sha256::digest(text.as_bytes());
    format!("{digest:x}")
}

fn collect_rule_hits(
    file_name: &str,
    path_templates: &[String],
    leaves: &[NonstandardDataRuleCoverageLeafInput],
    candidate_paths: &BTreeSet<(String, String)>,
    require_candidate_hit: bool,
    rule_index: usize,
    role: &'static str,
) -> Result<NonstandardDataCoverageHits, String> {
    let mut candidate_hits = BTreeSet::new();
    let mut details = Vec::new();
    let mut path_hit_counts = Vec::new();
    let mut stale_reasons = Vec::new();
    for path_template in path_templates {
        let matched_leaves = match expand_rule_to_leaf_paths(path_template, leaves) {
            Ok(matched_leaves) => matched_leaves,
            Err(error) => {
                stale_reasons.push(path_template_error_stale_reason(
                    file_name,
                    path_template,
                    error,
                ));
                continue;
            }
        };
        let string_hit_count = matched_leaves.len();
        if matched_leaves.is_empty() {
            stale_reasons.push(NonstandardDataStaleReasonOutput {
                code: "path_template_no_string_leaf",
                file: file_name.to_string(),
                message: format!(
                    "非标准 data 文件 {file_name} 的路径没有命中字符串叶子: {path_template}"
                ),
                path_template: Some(path_template.clone()),
            });
            path_hit_counts.push(NonstandardDataPathHitCountOutput {
                candidate_hit_count: 0,
                path_template: path_template.clone(),
                role,
                string_hit_count,
            });
            continue;
        }
        let mut template_candidate_hit_count = 0;
        for leaf in matched_leaves {
            if !candidate_paths.contains(&(file_name.to_string(), leaf.path.clone())) {
                continue;
            }
            template_candidate_hit_count += 1;
            candidate_hits.insert((file_name.to_string(), leaf.path.clone()));
            if let Some(original_text) = leaf.value.as_str() {
                details.push(nonstandard_data_hit_detail(
                    file_name,
                    path_template,
                    leaf,
                    original_text,
                    rule_index,
                    role,
                )?);
            }
        }
        if require_candidate_hit && template_candidate_hit_count == 0 {
            stale_reasons.push(NonstandardDataStaleReasonOutput {
                code: "path_template_no_candidate",
                file: file_name.to_string(),
                message: format!(
                    "非标准 data 文件 {file_name} 的路径没有命中源语言自然文本候选: {path_template}"
                ),
                path_template: Some(path_template.clone()),
            });
        }
        path_hit_counts.push(NonstandardDataPathHitCountOutput {
            candidate_hit_count: template_candidate_hit_count,
            path_template: path_template.clone(),
            role,
            string_hit_count,
        });
    }
    Ok(NonstandardDataCoverageHits {
        candidate_hits,
        details,
        path_hit_counts,
        stale_reasons,
    })
}

fn expand_rule_to_leaf_paths<'a>(
    path_template: &str,
    leaves: &'a [NonstandardDataRuleCoverageLeafInput],
) -> Result<Vec<&'a NonstandardDataRuleCoverageLeafInput>, PathTemplateError> {
    let template_parts = parse_json_path(path_template)?;
    let mut matched_leaves = Vec::new();
    for leaf in leaves {
        if leaf.value_type != "string" {
            continue;
        }
        if jsonpath_matches_template(&template_parts, &parse_json_path(&leaf.path)?) {
            matched_leaves.push(leaf);
        }
    }
    matched_leaves.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(matched_leaves)
}

fn nonstandard_data_hit_detail(
    file_name: &str,
    path_template: &str,
    leaf: &NonstandardDataRuleCoverageLeafInput,
    raw_text: &str,
    rule_index: usize,
    role: &'static str,
) -> Result<NonstandardDataRuleHitDetailOutput, String> {
    let parts = parse_json_path_message(&leaf.path)?;
    let slash_path = json_path_parts_to_slash_path(&parts)?;
    let parent_slash_path = json_path_parts_to_parent_slash_path(&parts)?;
    let translation_prefix = if parent_slash_path.is_empty() {
        file_name.to_string()
    } else {
        format!("{file_name}/{parent_slash_path}")
    };
    Ok(NonstandardDataRuleHitDetailOutput {
        file: file_name.to_string(),
        json_path: leaf.path.clone(),
        location_path: format!("{file_name}/{slash_path}"),
        original_text: normalize_visible_text_for_extraction(raw_text),
        path_template: path_template.to_string(),
        role,
        rule_index,
        translation_prefix,
    })
}

fn path_template_error_stale_reason(
    file_name: &str,
    path_template: &str,
    error: PathTemplateError,
) -> NonstandardDataStaleReasonOutput {
    NonstandardDataStaleReasonOutput {
        code: error.code,
        file: file_name.to_string(),
        message: error.message,
        path_template: Some(path_template.to_string()),
    }
}

fn path_pairs_to_json_array(path_pairs: &BTreeSet<(String, String)>) -> Vec<Value> {
    path_pairs
        .iter()
        .map(|(file_name, json_path)| {
            json!({
                "file": file_name,
                "json_path": json_path
            })
        })
        .collect()
}

fn format_path_pairs(path_pairs: &BTreeSet<(String, String)>) -> String {
    path_pairs
        .iter()
        .take(20)
        .map(|(file_name, json_path)| format!("{file_name}:{json_path}"))
        .collect::<Vec<_>>()
        .join("、")
}

fn scan_nonstandard_data_file(
    file: &NonstandardDataFileInput,
    text_rules: Option<&CompiledRuleCandidateTextRules>,
) -> Result<NonstandardDataFileScan, String> {
    let mut scan = NonstandardDataFileScan {
        file_name: file.file_name.clone(),
        candidates: Vec::new(),
        leaves: Vec::new(),
    };
    walk_nonstandard_data_value(
        &file.file_name,
        &file.data,
        "$",
        &[],
        "",
        text_rules,
        &mut scan,
    )?;
    Ok(scan)
}

#[allow(clippy::too_many_arguments)]
fn walk_nonstandard_data_value(
    file_name: &str,
    value: &Value,
    current_path: &str,
    parent_object_keys: &[String],
    field_name: &str,
    text_rules: Option<&CompiledRuleCandidateTextRules>,
    scan: &mut NonstandardDataFileScan,
) -> Result<(), String> {
    match value {
        Value::Object(object) => {
            let keys = object.keys().cloned().collect::<Vec<_>>();
            for (key, child) in object {
                let child_path = format!("{current_path}[{}]", quote_jsonpath_key(key));
                walk_nonstandard_data_value(
                    file_name,
                    child,
                    &child_path,
                    &keys,
                    key,
                    text_rules,
                    scan,
                )?;
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                let child_path = format!("{current_path}[{index}]");
                walk_nonstandard_data_value(
                    file_name,
                    child,
                    &child_path,
                    &[],
                    "",
                    text_rules,
                    scan,
                )?;
            }
        }
        Value::String(text) => {
            scan.leaves.push(NonstandardDataLeafOutput {
                path: current_path.to_string(),
                value: Value::String(text.clone()),
                value_type: "string",
                from_json_string: false,
            });
            if let Some(compiled_rules) = text_rules
                && let Some(candidate) = nonstandard_data_candidate_from_string(
                    file_name,
                    current_path,
                    text,
                    field_name,
                    parent_object_keys,
                    compiled_rules,
                )?
            {
                scan.candidates.push(candidate);
            }
        }
        Value::Bool(value) => scan.leaves.push(NonstandardDataLeafOutput {
            path: current_path.to_string(),
            value: Value::Bool(*value),
            value_type: "boolean",
            from_json_string: false,
        }),
        Value::Null => scan.leaves.push(NonstandardDataLeafOutput {
            path: current_path.to_string(),
            value: Value::Null,
            value_type: "null",
            from_json_string: false,
        }),
        Value::Number(number) => scan.leaves.push(NonstandardDataLeafOutput {
            path: current_path.to_string(),
            value: Value::Number(number.clone()),
            value_type: "number",
            from_json_string: false,
        }),
    }
    Ok(())
}

fn nonstandard_data_candidate_from_string(
    file_name: &str,
    json_path: &str,
    raw_text: &str,
    field_name: &str,
    parent_object_keys: &[String],
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<Option<RuleCandidateOutput>, String> {
    if is_structural_nonstandard_string(field_name, raw_text) {
        return Ok(None);
    }
    let visible_text = normalize_visible_text_for_extraction(raw_text);
    if !should_translate_plugin_source_text(&visible_text, text_rules)? {
        return Ok(None);
    }
    let source_text =
        normalize_extraction_text(&visible_text, &text_rules.strip_wrapping_punctuation_pairs);
    let sibling_field_names = parent_object_keys
        .iter()
        .filter(|key| key.as_str() != field_name)
        .cloned()
        .collect::<Vec<_>>();
    Ok(Some(RuleCandidateOutput {
        domain: "nonstandard_data".to_string(),
        location_path: format!("nonstandard-data/{file_name}/{json_path}"),
        rule_key: json_path.to_string(),
        original_text: source_text.clone(),
        source_file: file_name.to_string(),
        file: Some(file_name.to_string()),
        json_path: Some(json_path.to_string()),
        source_text: Some(source_text.clone()),
        field_name: Some(field_name.to_string()),
        sibling_field_names: Some(sibling_field_names),
        parent_object_keys: Some(parent_object_keys.to_vec()),
        selector: None,
        text: Some(source_text),
        raw_text: Some(raw_text.to_string()),
        quote: None,
        line: None,
        start_index: None,
        end_index: None,
        content_start_index: None,
        content_end_index: None,
        context: None,
        api: None,
        key: None,
        ast_context: None,
        active: None,
        confidence: None,
        structural_flags: None,
        file_hash: None,
    }))
}

fn is_structural_nonstandard_string(field_name: &str, value: &str) -> bool {
    let normalized_field_name = field_name.trim().to_ascii_lowercase();
    let stripped_value = value.trim();
    let lowered_value = stripped_value.to_ascii_lowercase();
    matches!(
        normalized_field_name.as_str(),
        "id" | "key"
            | "type"
            | "icon"
            | "image"
            | "picture"
            | "file"
            | "filename"
            | "path"
            | "enabled"
            | "enable"
            | "visible"
            | "switch"
            | "variable"
            | "formula"
            | "condition"
            | "script"
    ) || matches!(
        lowered_value.as_str(),
        "true" | "false" | "null" | "undefined"
    ) || NUMBER_LIKE_RE.is_match(stripped_value)
        || ENGLISH_ASSET_PATH_RE.is_match(&lowered_value)
        || ENGLISH_ASSET_EXTENSION_RE.is_match(&lowered_value)
}

fn quote_jsonpath_key(key: &str) -> String {
    let escaped_key = key.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped_key}'")
}

#[cfg(test)]
mod tests {
    use super::{
        NonstandardDataFileInput, NonstandardDataRuleCoverageInput, NonstandardDataTextRuleInput,
        collect_nonstandard_data_managed_texts, scan_nonstandard_data_rule_candidates,
        scan_nonstandard_data_rule_coverage,
    };
    use crate::native_core::scope_index::RuleCandidateTextRules;
    use crate::native_core::scope_index::path_templates::{
        PATH_TEMPLATE_INVALID_CODE, parse_json_path,
    };
    use serde_json::{Value, json};

    fn text_rules() -> RuleCandidateTextRules {
        RuleCandidateTextRules {
            custom_placeholder_rules: Vec::new(),
            structured_placeholder_rules: Vec::new(),
            strip_wrapping_punctuation_pairs: Vec::new(),
            source_text_required_pattern: r"[\s\S]".to_string(),
            source_text_exclusion_profile: "none".to_string(),
        }
    }

    fn english_protocol_text_rules() -> RuleCandidateTextRules {
        RuleCandidateTextRules {
            custom_placeholder_rules: Vec::new(),
            structured_placeholder_rules: Vec::new(),
            strip_wrapping_punctuation_pairs: Vec::new(),
            source_text_required_pattern: r"[A-Za-z]".to_string(),
            source_text_exclusion_profile: "english_protocol_noise".to_string(),
        }
    }

    #[test]
    fn scan_nonstandard_data_candidates_skips_structural_strings_and_reports_leaf_context() {
        let files = vec![NonstandardDataFileInput {
            file_name: "UnknownPluginData.json".to_string(),
            raw_text: r#"{"title":"古い掲示板","file":"Actor1.png","items":["説明文"]}"#
                .to_string(),
            data: json!({
                "title": "古い掲示板",
                "file": "Actor1.png",
                "items": ["説明文"]
            }),
        }];

        let scan = scan_nonstandard_data_rule_candidates(&files, text_rules()).expect("扫描应成功");

        assert_eq!(scan.nonstandard_file_count, 1);
        assert_eq!(scan.candidates.len(), 2);
        assert_eq!(
            scan.candidates
                .iter()
                .map(|candidate| candidate.json_path.as_deref().unwrap_or(""))
                .collect::<std::collections::BTreeSet<_>>(),
            std::collections::BTreeSet::from(["$['items'][0]", "$['title']"])
        );
        assert!(
            scan.candidates
                .iter()
                .all(|candidate| candidate.original_text != "Actor1.png")
        );
        assert_eq!(scan.file_scans[0].string_leaf_count, 3);
    }

    #[test]
    fn scan_nonstandard_data_candidates_ignores_english_protocol_noise() {
        let raw_text = r#"[{"id":"recipe_001","icon":"img/pictures/Meal.png","enabled":"true","formula":"a.hpRate() >= 0.5"}]"#;
        let files = vec![NonstandardDataFileInput {
            file_name: "Recipes.json".to_string(),
            raw_text: raw_text.to_string(),
            data: serde_json::from_str::<Value>(raw_text).expect("fixture JSON 应合法"),
        }];

        let scan = scan_nonstandard_data_rule_candidates(&files, english_protocol_text_rules())
            .expect("英文协议噪声扫描应成功");

        assert_eq!(scan.nonstandard_file_count, 1);
        assert!(scan.candidates.is_empty());
        assert_eq!(scan.file_scans[0].string_leaf_count, 4);
        assert_eq!(scan.file_scans[0].candidate_count, 0);
    }

    #[test]
    fn nonstandard_data_rule_coverage_expands_wildcards_and_reports_unreviewed_candidates() {
        let input: NonstandardDataRuleCoverageInput = serde_json::from_value(json!({
            "rules": [
                {
                    "file": "UnknownPluginData.json",
                    "paths": ["$['items'][*]['name']"],
                    "excluded_paths": []
                }
            ],
            "files": [
                {
                    "file": "UnknownPluginData.json",
                    "leaves": [
                        {"path": "$['items'][0]['name']", "value_type": "string"},
                        {"path": "$['items'][1]['name']", "value_type": "string"}
                    ]
                }
            ],
            "candidates": [
                {"file": "UnknownPluginData.json", "json_path": "$['items'][0]['name']"},
                {"file": "UnknownPluginData.json", "json_path": "$['items'][1]['name']"},
                {"file": "UnknownPluginData.json", "json_path": "$['title']"}
            ]
        }))
        .expect("coverage 输入应可解析");

        let output = scan_nonstandard_data_rule_coverage(input).expect("覆盖检查应成功");

        assert_eq!(output["reviewed_candidate_count"], json!(2));
        assert_eq!(
            output["unreviewed_candidates"],
            json!([{"file": "UnknownPluginData.json", "json_path": "$['title']"}])
        );
    }

    #[test]
    fn nonstandard_data_outputs_rule_hit_details_and_translation_prefixes() {
        let input: NonstandardDataRuleCoverageInput = serde_json::from_value(json!({
            "rules": [
                {
                    "file": "Custom.json",
                    "paths": ["$['items'][*]['name']"],
                    "excluded_paths": []
                }
            ],
            "files": [
                {
                    "file": "Custom.json",
                    "leaves": [
                        {
                            "path": "$['items'][0]['name']",
                            "value_type": "string",
                            "value": "古い名前"
                        }
                    ]
                }
            ],
            "candidates": [
                {"file": "Custom.json", "json_path": "$['items'][0]['name']"}
            ]
        }))
        .expect("coverage 输入应可解析");

        let output = scan_nonstandard_data_rule_coverage(input).expect("覆盖检查应成功");

        assert_eq!(
            output["hit_details"][0]["path_template"],
            json!("$['items'][*]['name']")
        );
        assert_eq!(
            output["hit_details"][0]["json_path"],
            json!("$['items'][0]['name']")
        );
        assert_eq!(
            output["hit_details"][0]["location_path"],
            json!("Custom.json/items/0/name")
        );
        assert_eq!(output["hit_details"][0]["original_text"], json!("古い名前"));
        assert_eq!(
            output["translation_prefixes"],
            json!(["Custom.json/items/0"])
        );
    }

    #[test]
    fn invalid_path_template_returns_stable_error_code() {
        let error = parse_json_path("$.Name").expect_err("点号 JSONPath 必须报错");

        assert_eq!(error.code, PATH_TEMPLATE_INVALID_CODE);
    }

    #[test]
    fn collect_nonstandard_data_managed_texts_rejects_incomplete_review() {
        let raw_text = r#"{"title":"古い掲示板","body":"本文"}"#;
        let files = vec![NonstandardDataFileInput {
            file_name: "UnknownPluginData.json".to_string(),
            raw_text: raw_text.to_string(),
            data: serde_json::from_str::<Value>(raw_text).expect("fixture JSON 应合法"),
        }];
        let _scan =
            scan_nonstandard_data_rule_candidates(&files, text_rules()).expect("扫描应成功");
        let file_hash = super::sha256_hex(raw_text);
        let rules = vec![NonstandardDataTextRuleInput {
            file_name: "UnknownPluginData.json".to_string(),
            file_hash,
            path_templates: vec!["$['title']".to_string()],
            excluded_path_templates: Vec::new(),
            skipped: false,
        }];

        match collect_nonstandard_data_managed_texts(&files, &rules, text_rules()) {
            Ok(_) => panic!("未审查 body 候选时应失败"),
            Err(super::NonstandardDataManagedTextError::ReviewIncomplete { unreviewed_count }) => {
                assert_eq!(unreviewed_count, 1);
            }
            Err(super::NonstandardDataManagedTextError::Stale(reason)) => {
                panic!("不应返回过期规则错误: {reason}");
            }
        }
    }
}
