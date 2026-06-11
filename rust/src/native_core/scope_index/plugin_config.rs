//! 插件参数规则候选扫描。

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet};

use super::path_templates::{
    JsonPathPart, jsonpath_matches_template, parse_json_path_message as parse_json_path,
};
use super::plugin_source::{
    compile_rule_candidate_text_rules, sha256_text, should_translate_plugin_source_text,
};
use super::{RuleCandidateOutput, RuleCandidateTextRules};
use crate::native_core::write_back_plan::normalize_visible_text_for_extraction;
use crate::native_core::write_protocol::decode_json_container_text;

#[derive(Debug, Deserialize)]
pub(super) struct PluginConfigInput {
    pub(super) plugin_index: usize,
    pub(super) plugin_name: String,
    pub(super) plugin: Value,
}

#[derive(Debug, Clone, Deserialize)]
pub(super) struct PluginConfigRuleInput {
    pub(super) plugin_index: usize,
    pub(super) plugin_name: String,
    #[serde(default)]
    pub(super) plugin_hash: Option<String>,
    #[serde(default)]
    pub(super) path_templates: Vec<String>,
}

#[derive(Debug, Serialize)]
pub(super) struct PluginConfigHitDetailOutput {
    json_path: String,
    location_path: String,
    original_text: String,
    path_template: String,
    plugin_index: usize,
    plugin_name: String,
    rule_index: usize,
}

#[derive(Debug, Serialize)]
pub(super) struct PluginConfigPathHitCountOutput {
    path_template: String,
    string_hit_count: usize,
    translatable_hit_count: usize,
}

#[derive(Debug, Serialize)]
pub(super) struct PluginConfigRuleSummaryOutput {
    path_hit_counts: Vec<PluginConfigPathHitCountOutput>,
    plugin_hash: String,
    plugin_index: usize,
    plugin_name: String,
    rule_index: usize,
}

#[derive(Debug, Serialize)]
pub(super) struct PluginConfigPluginSummaryOutput {
    plugin_index: usize,
    plugin_name: String,
    plugin_hash: String,
    string_leaf_count: usize,
    candidate_count: usize,
    leaves: Vec<PluginConfigLeafOutput>,
}

#[derive(Debug, Clone, Serialize)]
pub(super) struct PluginConfigLeafOutput {
    path: String,
    value_type: &'static str,
    from_json_string: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    text: Option<String>,
}

pub(super) struct PluginConfigRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) candidate_count: usize,
    pub(super) hit_details: Vec<PluginConfigHitDetailOutput>,
    pub(super) plugin_count: usize,
    pub(super) plugins: Vec<PluginConfigPluginSummaryOutput>,
    pub(super) rule_summaries: Vec<PluginConfigRuleSummaryOutput>,
    pub(super) string_leaf_count: usize,
}

#[derive(Debug)]
struct PluginConfigScan {
    plugin_index: usize,
    plugin_name: String,
    plugin_hash: String,
    leaves: Vec<PluginConfigLeaf>,
}

#[derive(Debug)]
struct PluginConfigLeaf {
    path: String,
    text: String,
    from_json_string: bool,
}

struct PluginConfigRuleStats {
    path_hit_counts: BTreeMap<String, (usize, usize)>,
    path_templates: Vec<String>,
    plugin_hash: String,
    plugin_index: usize,
    plugin_name: String,
    rule_index: usize,
}

pub(super) fn scan_plugin_config_rule_candidates(
    plugins: &[PluginConfigInput],
    rules: &[PluginConfigRuleInput],
    text_rules: RuleCandidateTextRules,
) -> Result<PluginConfigRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let mut plugin_refs = plugins.iter().collect::<Vec<_>>();
    plugin_refs.sort_by_key(|plugin| plugin.plugin_index);
    let plugin_scans = plugin_refs
        .par_iter()
        .map(|plugin| scan_plugin_config(plugin))
        .collect::<Result<Vec<_>, String>>()?;
    let plugin_scans_by_index = plugin_scans
        .iter()
        .map(|scan| (scan.plugin_index, scan))
        .collect::<BTreeMap<_, _>>();
    let mut seen_rule_plugin_indices = BTreeSet::new();
    let mut candidates = Vec::new();
    let mut seen_candidate_paths = BTreeSet::new();
    let mut hit_details = Vec::new();
    let mut rule_summaries = Vec::new();

    for (rule_index, rule) in rules.iter().enumerate() {
        if !seen_rule_plugin_indices.insert(rule.plugin_index) {
            return Err(format!(
                "插件规则不能重复声明 plugin_index: {}",
                rule.plugin_index
            ));
        }
        let Some(plugin_scan) = plugin_scans_by_index.get(&rule.plugin_index) else {
            return Err(format!(
                "插件规则索引超出当前 plugins.js 范围: {}",
                rule.plugin_index
            ));
        };
        if rule.plugin_name != plugin_scan.plugin_name {
            return Err(format!(
                "插件规则名称与当前 plugins.js 不匹配: plugin_index={}, 规则={}, 当前={}",
                rule.plugin_index, rule.plugin_name, plugin_scan.plugin_name
            ));
        }

        let mut stats = PluginConfigRuleStats::new(rule_index, rule, plugin_scan);
        for path_template in &rule.path_templates {
            let matched_leaves = expand_rule_to_leaf_paths(path_template, &plugin_scan.leaves)?;
            let mut translatable_hit_count = 0usize;
            for leaf in matched_leaves.iter() {
                let original_text = normalize_visible_text_for_extraction(&leaf.text);
                if !should_translate_plugin_source_text(&original_text, &compiled_rules)? {
                    continue;
                }
                translatable_hit_count += 1;
                let location_path =
                    jsonpath_to_plugin_location_path(&leaf.path, plugin_scan.plugin_index)?;
                if seen_candidate_paths.insert(location_path.clone()) {
                    let rule_key = format!("plugin_config.{}.rule.{rule_index}", rule.plugin_index);
                    candidates.push(RuleCandidateOutput {
                        domain: "plugin_config".to_string(),
                        location_path: location_path.clone(),
                        rule_key,
                        original_text: original_text.clone(),
                        source_file: "plugins.js".to_string(),
                        file: None,
                        json_path: Some(leaf.path.clone()),
                        source_text: None,
                        field_name: None,
                        sibling_field_names: None,
                        parent_object_keys: None,
                        selector: None,
                        text: None,
                        raw_text: Some(leaf.text.clone()),
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
                        file_hash: Some(plugin_scan.plugin_hash.clone()),
                    });
                    hit_details.push(PluginConfigHitDetailOutput {
                        json_path: leaf.path.clone(),
                        location_path,
                        original_text,
                        path_template: path_template.clone(),
                        plugin_index: plugin_scan.plugin_index,
                        plugin_name: plugin_scan.plugin_name.clone(),
                        rule_index,
                    });
                }
            }
            stats.record_path_hits(path_template, matched_leaves.len(), translatable_hit_count);
        }
        rule_summaries.push(stats.into_output());
    }

    let candidate_paths_by_plugin_index = candidates
        .iter()
        .filter_map(|candidate| plugin_index_from_location_path(&candidate.location_path))
        .fold(
            BTreeMap::<usize, usize>::new(),
            |mut counts, plugin_index| {
                *counts.entry(plugin_index).or_default() += 1;
                counts
            },
        );
    let plugins = plugin_scans
        .iter()
        .map(|scan| PluginConfigPluginSummaryOutput {
            plugin_index: scan.plugin_index,
            plugin_name: scan.plugin_name.clone(),
            plugin_hash: scan.plugin_hash.clone(),
            string_leaf_count: scan.leaves.len(),
            candidate_count: candidate_paths_by_plugin_index
                .get(&scan.plugin_index)
                .copied()
                .unwrap_or_default(),
            leaves: scan
                .leaves
                .iter()
                .map(|leaf| PluginConfigLeafOutput {
                    path: leaf.path.clone(),
                    value_type: "string",
                    from_json_string: leaf.from_json_string,
                    text: Some(leaf.text.clone()),
                })
                .collect(),
        })
        .collect::<Vec<_>>();
    let string_leaf_count = plugin_scans
        .iter()
        .map(|scan| scan.leaves.len())
        .sum::<usize>();
    Ok(PluginConfigRuleCandidateScan {
        candidate_count: candidates.len(),
        candidates,
        hit_details,
        plugin_count: plugins.len(),
        plugins,
        rule_summaries,
        string_leaf_count,
    })
}

pub(super) fn scan_plugin_config_rule_text_candidates(
    plugins: &[PluginConfigInput],
    rules: &[PluginConfigRuleInput],
    text_rules: RuleCandidateTextRules,
) -> Result<Vec<RuleCandidateOutput>, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let mut plugin_refs = plugins.iter().collect::<Vec<_>>();
    plugin_refs.sort_by_key(|plugin| plugin.plugin_index);
    let plugin_scans = plugin_refs
        .par_iter()
        .map(|plugin| scan_plugin_config(plugin))
        .collect::<Result<Vec<_>, String>>()?;
    let plugin_scans_by_index = plugin_scans
        .iter()
        .map(|scan| (scan.plugin_index, scan))
        .collect::<BTreeMap<_, _>>();
    let mut seen_rule_plugin_indices = BTreeSet::new();
    let mut candidates = Vec::new();
    let mut seen_candidate_paths = BTreeSet::new();

    for (rule_index, rule) in rules.iter().enumerate() {
        if !seen_rule_plugin_indices.insert(rule.plugin_index) {
            return Err(format!(
                "插件规则不能重复声明 plugin_index: {}",
                rule.plugin_index
            ));
        }
        let Some(plugin_scan) = plugin_scans_by_index.get(&rule.plugin_index) else {
            return Err(format!(
                "插件规则索引超出当前 plugins.js 范围: {}",
                rule.plugin_index
            ));
        };
        if rule.plugin_name != plugin_scan.plugin_name {
            return Err(format!(
                "插件规则名称与当前 plugins.js 不匹配: plugin_index={}, 规则={}, 当前={}",
                rule.plugin_index, rule.plugin_name, plugin_scan.plugin_name
            ));
        }

        for path_template in &rule.path_templates {
            let matched_leaves = expand_rule_to_leaf_paths(path_template, &plugin_scan.leaves)?;
            for leaf in matched_leaves {
                let original_text = normalize_visible_text_for_extraction(&leaf.text);
                if !should_translate_plugin_source_text(&original_text, &compiled_rules)? {
                    continue;
                }
                let location_path =
                    jsonpath_to_plugin_location_path(&leaf.path, plugin_scan.plugin_index)?;
                if seen_candidate_paths.insert(location_path.clone()) {
                    candidates.push(RuleCandidateOutput {
                        domain: "plugin_config".to_string(),
                        location_path: location_path.clone(),
                        rule_key: format!("plugin_config.{}.rule.{rule_index}", rule.plugin_index),
                        original_text: original_text.clone(),
                        source_file: "plugins.js".to_string(),
                        file: None,
                        json_path: Some(leaf.path.clone()),
                        source_text: None,
                        field_name: None,
                        sibling_field_names: None,
                        parent_object_keys: None,
                        selector: None,
                        text: None,
                        raw_text: Some(leaf.text.clone()),
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
                        file_hash: Some(plugin_scan.plugin_hash.clone()),
                    });
                }
            }
        }
    }
    Ok(candidates)
}

impl PluginConfigRuleStats {
    fn new(rule_index: usize, rule: &PluginConfigRuleInput, plugin: &PluginConfigScan) -> Self {
        Self {
            path_hit_counts: BTreeMap::new(),
            path_templates: rule.path_templates.clone(),
            plugin_hash: plugin.plugin_hash.clone(),
            plugin_index: plugin.plugin_index,
            plugin_name: plugin.plugin_name.clone(),
            rule_index,
        }
    }

    fn record_path_hits(
        &mut self,
        path_template: &str,
        string_hit_count: usize,
        translatable_hit_count: usize,
    ) {
        let entry = self
            .path_hit_counts
            .entry(path_template.to_string())
            .or_default();
        entry.0 += string_hit_count;
        entry.1 += translatable_hit_count;
    }

    fn into_output(self) -> PluginConfigRuleSummaryOutput {
        let path_hit_counts = self
            .path_templates
            .into_iter()
            .map(|path_template| {
                let (string_hit_count, translatable_hit_count) = self
                    .path_hit_counts
                    .get(&path_template)
                    .copied()
                    .unwrap_or_default();
                PluginConfigPathHitCountOutput {
                    path_template,
                    string_hit_count,
                    translatable_hit_count,
                }
            })
            .collect();
        PluginConfigRuleSummaryOutput {
            path_hit_counts,
            plugin_hash: self.plugin_hash,
            plugin_index: self.plugin_index,
            plugin_name: self.plugin_name,
            rule_index: self.rule_index,
        }
    }
}

fn scan_plugin_config(plugin: &PluginConfigInput) -> Result<PluginConfigScan, String> {
    let actual_plugin_name = extract_plugin_name(&plugin.plugin, plugin.plugin_index);
    if plugin.plugin_name != actual_plugin_name {
        return Err(format!(
            "插件规则名称与当前 plugins.js 不匹配: plugin_index={}, 规则={}, 当前={}",
            plugin.plugin_index, plugin.plugin_name, actual_plugin_name
        ));
    }
    let plugin_hash = plugin_hash(&plugin.plugin)?;
    let parameters = plugin.plugin.get("parameters").and_then(Value::as_object);
    let mut leaves = Vec::new();
    if let Some(parameters) = parameters {
        walk_plugin_config_value(
            &Value::Object(parameters.clone()),
            "$['parameters']",
            false,
            &mut leaves,
        );
    }
    leaves.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(PluginConfigScan {
        plugin_index: plugin.plugin_index,
        plugin_name: actual_plugin_name,
        plugin_hash,
        leaves,
    })
}

fn walk_plugin_config_value(
    value: &Value,
    current_path: &str,
    from_json_string: bool,
    leaves: &mut Vec<PluginConfigLeaf>,
) {
    match value {
        Value::Object(object) => {
            for (key, child) in object {
                let child_path = format!("{current_path}[{}]", quote_jsonpath_key(key));
                walk_plugin_config_value(child, &child_path, from_json_string, leaves);
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                let child_path = format!("{current_path}[{index}]");
                walk_plugin_config_value(child, &child_path, from_json_string, leaves);
            }
        }
        Value::String(text) => {
            if let Some((container, _shell_depth)) = decode_json_container_text(text) {
                walk_plugin_config_value(&container, current_path, true, leaves);
                return;
            }
            leaves.push(PluginConfigLeaf {
                path: current_path.to_string(),
                text: text.clone(),
                from_json_string,
            });
        }
        _ => {}
    }
}

fn expand_rule_to_leaf_paths<'a>(
    path_template: &str,
    leaves: &'a [PluginConfigLeaf],
) -> Result<Vec<&'a PluginConfigLeaf>, String> {
    let template_parts = parse_json_path(path_template)?;
    let mut matched_leaves = Vec::new();
    for leaf in leaves {
        if jsonpath_matches_template(&template_parts, &parse_json_path(&leaf.path)?) {
            matched_leaves.push(leaf);
        }
    }
    matched_leaves.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(matched_leaves)
}

fn jsonpath_to_plugin_location_path(
    json_path: &str,
    plugin_index: usize,
) -> Result<String, String> {
    let parts = parse_json_path(json_path)?;
    if !matches!(parts.first(), Some(JsonPathPart::Key(key)) if key == "parameters") {
        return Err(format!("插件路径必须从 parameters 开始: {json_path}"));
    }
    let mut location_path = format!("plugins.js/{plugin_index}");
    for part in parts.into_iter().skip(1) {
        location_path.push('/');
        match part {
            JsonPathPart::Key(key) => location_path.push_str(&key),
            JsonPathPart::Index(index) => location_path.push_str(&index.to_string()),
            JsonPathPart::Wildcard => {
                return Err(format!("插件实际路径不能包含通配符: {json_path}"));
            }
        }
    }
    Ok(location_path)
}

fn plugin_index_from_location_path(location_path: &str) -> Option<usize> {
    location_path
        .strip_prefix("plugins.js/")?
        .split('/')
        .next()?
        .parse::<usize>()
        .ok()
}

fn extract_plugin_name(plugin: &Value, plugin_index: usize) -> String {
    plugin
        .get("name")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("unnamed_plugin_{plugin_index}"))
}

pub(super) fn plugin_hash(plugin: &Value) -> Result<String, String> {
    let canonical_text = serde_json::to_string(&canonicalize_json_value(plugin))
        .map_err(|error| format!("插件配置 hash JSON 序列化失败: {error}"))?;
    Ok(sha256_text(&canonical_text))
}

fn canonicalize_json_value(value: &Value) -> Value {
    match value {
        Value::Array(items) => Value::Array(items.iter().map(canonicalize_json_value).collect()),
        Value::Object(object) => {
            let mut keys = object.keys().collect::<Vec<_>>();
            keys.sort();
            let mut sorted_object = Map::new();
            for key in keys {
                if let Some(child) = object.get(key) {
                    sorted_object.insert(key.clone(), canonicalize_json_value(child));
                }
            }
            Value::Object(sorted_object)
        }
        _ => value.clone(),
    }
}

fn quote_jsonpath_key(key: &str) -> String {
    let escaped_key = key.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped_key}'")
}
