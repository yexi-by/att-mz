//! 非标准 data JSON 候选扫描。

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

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
    leaves: Vec<NonstandardDataRuleCoverageLeafInput>,
}

#[derive(Debug, Deserialize)]
struct NonstandardDataRuleCoverageLeafInput {
    path: String,
    value_type: String,
}

#[derive(Debug, Deserialize)]
struct NonstandardDataRuleCoverageCandidateInput {
    file: String,
    json_path: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum JsonPathPart {
    Key(String),
    Index(usize),
    Wildcard,
}

struct NonstandardDataFileScan {
    file_name: String,
    candidates: Vec<RuleCandidateOutput>,
    leaves: Vec<NonstandardDataLeafOutput>,
}

pub(super) fn scan_nonstandard_data_rule_coverage(
    input: NonstandardDataRuleCoverageInput,
) -> Result<Value, String> {
    let leaves_by_file = input
        .files
        .into_iter()
        .map(|file| (file.file, file.leaves))
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

    for rule in input.rules {
        if !seen_files.insert(rule.file.clone()) {
            return Err(format!(
                "非标准 data 文件规则不能重复声明 file: {}",
                rule.file
            ));
        }
        let Some(file_leaves) = leaves_by_file.get(&rule.file) else {
            return Err(format!(
                "非标准 data 文件规则指向不存在的文件: {}",
                rule.file
            ));
        };
        if rule.skipped {
            skipped_files.insert(rule.file.clone());
            rule_details.push(json!({
                "file": rule.file,
                "skipped": true,
                "translated_candidate_count": 0,
                "excluded_candidate_count": 0
            }));
            continue;
        }

        let translated_hits =
            collect_rule_hits(&rule.file, &rule.paths, file_leaves, &candidate_paths, true)?;
        let excluded_hits = collect_rule_hits(
            &rule.file,
            &rule.excluded_paths,
            file_leaves,
            &candidate_paths,
            true,
        )?;
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
        "skipped_files": skipped_files.into_iter().collect::<Vec<_>>(),
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
    let template_parts = parse_json_path(path_template)?;
    let mut matched_paths = Vec::new();
    for leaf in leaves {
        if leaf.value_type != "string" {
            continue;
        }
        if jsonpath_matches_template(&template_parts, &parse_json_path(&leaf.path)?) {
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
) -> Result<BTreeSet<(String, String)>, String> {
    let mut hits = BTreeSet::new();
    for path_template in path_templates {
        let matched_leaf_paths = expand_rule_to_leaf_paths(path_template, leaves)?;
        if matched_leaf_paths.is_empty() {
            return Err(format!(
                "非标准 data 文件 {file_name} 的路径没有命中字符串叶子: {path_template}"
            ));
        }
        let candidate_hits = matched_leaf_paths
            .into_iter()
            .filter(|leaf_path| {
                candidate_paths.contains(&(file_name.to_string(), leaf_path.clone()))
            })
            .map(|leaf_path| (file_name.to_string(), leaf_path))
            .collect::<BTreeSet<_>>();
        if require_candidate_hit && candidate_hits.is_empty() {
            return Err(format!(
                "非标准 data 文件 {file_name} 的路径没有命中源语言自然文本候选: {path_template}"
            ));
        }
        hits.extend(candidate_hits);
    }
    Ok(hits)
}

fn expand_rule_to_leaf_paths(
    path_template: &str,
    leaves: &[NonstandardDataRuleCoverageLeafInput],
) -> Result<Vec<String>, String> {
    let template_parts = parse_json_path(path_template)?;
    let mut matched_paths = Vec::new();
    for leaf in leaves {
        if leaf.value_type != "string" {
            continue;
        }
        if jsonpath_matches_template(&template_parts, &parse_json_path(&leaf.path)?) {
            matched_paths.push(leaf.path.clone());
        }
    }
    matched_paths.sort();
    Ok(matched_paths)
}

fn jsonpath_matches_template(
    template_parts: &[JsonPathPart],
    actual_parts: &[JsonPathPart],
) -> bool {
    if template_parts.len() != actual_parts.len() {
        return false;
    }
    template_parts.iter().zip(actual_parts).all(
        |(template_part, actual_part)| match template_part {
            JsonPathPart::Wildcard => matches!(actual_part, JsonPathPart::Index(_)),
            _ => template_part == actual_part,
        },
    )
}

fn parse_json_path(path: &str) -> Result<Vec<JsonPathPart>, String> {
    let chars = path.chars().collect::<Vec<_>>();
    if chars.first() != Some(&'$') {
        return Err(format!("JSONPath 超出当前规则范围: {path}"));
    }
    let mut index = 1;
    let mut parts = Vec::new();
    while index < chars.len() {
        if chars[index] != '[' {
            return Err(format!("JSONPath 超出当前规则范围: {path}"));
        }
        index += 1;
        if index >= chars.len() {
            return Err(format!("JSONPath 超出当前规则范围: {path}"));
        }
        if chars[index] == '\'' {
            index += 1;
            let mut key = String::new();
            while index < chars.len() {
                let current = chars[index];
                if current == '\\' {
                    index += 1;
                    if index >= chars.len() {
                        return Err(format!("JSONPath 超出当前规则范围: {path}"));
                    }
                    key.push(chars[index]);
                    index += 1;
                    continue;
                }
                if current == '\'' {
                    index += 1;
                    if index >= chars.len() || chars[index] != ']' {
                        return Err(format!("JSONPath 超出当前规则范围: {path}"));
                    }
                    index += 1;
                    parts.push(JsonPathPart::Key(key));
                    break;
                }
                key.push(current);
                index += 1;
            }
            if !matches!(parts.last(), Some(JsonPathPart::Key(_))) {
                return Err(format!("JSONPath 超出当前规则范围: {path}"));
            }
            continue;
        }
        let start_index = index;
        while index < chars.len() && chars[index] != ']' {
            index += 1;
        }
        if index >= chars.len() {
            return Err(format!("JSONPath 超出当前规则范围: {path}"));
        }
        let segment = chars[start_index..index].iter().collect::<String>();
        index += 1;
        if segment == "*" {
            parts.push(JsonPathPart::Wildcard);
            continue;
        }
        let parsed_index = segment
            .parse::<usize>()
            .map_err(|_error| format!("JSONPath 超出当前规则范围: {path}"))?;
        parts.push(JsonPathPart::Index(parsed_index));
    }
    if parts.is_empty() {
        return Err(format!("JSONPath 超出当前规则范围: {path}"));
    }
    Ok(parts)
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
