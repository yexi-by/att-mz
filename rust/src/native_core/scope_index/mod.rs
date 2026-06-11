//! Scope/Index Engine 原生核心。
//!
//! 本模块统一承载范围索引构建、规则候选扫描、门禁评估、schema 指纹、
//! 存储检查、持久写入和冷重建入口。

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, BTreeSet};

use super::models::{NativeCustomPlaceholderRule, NativeStructuredPlaceholderRule};
use super::pool;

mod contracts;
mod event_commands;
mod mv_virtual_namebox;
mod nonstandard_data;
mod note_tags;
mod path_templates;
mod placeholders;
mod plugin_config;
mod plugin_source;
mod rebuild;
mod storage;
mod structured_placeholders;

use self::contracts::{ContractVersionsOutput, current_contract_versions};
use self::plugin_source::{
    PluginSourceFileInput, PluginSourceTextRuleInput, scan_plugin_source_rule_candidates_with_rules,
};

const RULE_CANDIDATES_SCHEMA_VERSION: usize = 1;

#[derive(Debug, Deserialize)]
struct BuildScopeIndexPayload {
    source_snapshot_fingerprint: String,
    rules_fingerprint: String,
    #[serde(default)]
    entries: Vec<ScopeEntryInput>,
    #[serde(default)]
    data_files: Vec<ScopeIndexDataFileInput>,
    #[serde(default)]
    rule_hits: Vec<RuleHitInput>,
    #[serde(default)]
    candidate_groups: Vec<CandidateGroupOutput>,
    #[serde(default)]
    stale_rule_details: Vec<StaleRuleDetailOutput>,
}

#[derive(Debug, Deserialize)]
struct ScopeGatePayload {
    entries: Vec<ScopeEntryInput>,
    matched_translation_fact_ids: Vec<String>,
    quality_error_fact_ids: Vec<String>,
    #[serde(default)]
    required_paths: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct ScopeIndexDataFileInput {
    file_name: String,
    data: Value,
}

#[derive(Debug, Deserialize)]
struct RuleCandidatesPayload {
    #[serde(default)]
    candidates: Vec<RuleCandidateOutput>,
    #[serde(default)]
    plugin_source_files: Vec<PluginSourceFileInput>,
    #[serde(default)]
    plugin_source_text_rules: Vec<PluginSourceTextRuleInput>,
    #[serde(default)]
    plugin_source_read_error_file_count: usize,
    #[serde(default)]
    nonstandard_data_files: Vec<nonstandard_data::NonstandardDataFileInput>,
    #[serde(default)]
    nonstandard_data_leaves: Vec<nonstandard_data::NonstandardDataFileInput>,
    nonstandard_data_rule_coverage: Option<nonstandard_data::NonstandardDataRuleCoverageInput>,
    #[serde(default)]
    placeholder_texts: Vec<placeholders::PlaceholderTextInput>,
    #[serde(default)]
    structured_placeholder_texts: Vec<structured_placeholders::StructuredPlaceholderTextInput>,
    #[serde(default)]
    note_tag_data_files: BTreeMap<String, Value>,
    #[serde(default)]
    event_command_data_files: Vec<event_commands::EventCommandDataFileInput>,
    #[serde(default)]
    event_command_codes: Vec<i64>,
    #[serde(default)]
    event_command_rules: Vec<event_commands::EventCommandRuleInput>,
    #[serde(default)]
    plugin_config_plugins: Vec<plugin_config::PluginConfigInput>,
    #[serde(default)]
    plugin_config_rules: Vec<plugin_config::PluginConfigRuleInput>,
    #[serde(default)]
    mv_virtual_namebox_data_files: Vec<mv_virtual_namebox::MvVirtualNameboxDataFileInput>,
    #[serde(default)]
    mv_virtual_namebox_actor_names: Vec<mv_virtual_namebox::MvVirtualNameboxActorNameInput>,
    #[serde(default)]
    mv_virtual_namebox_rules: Vec<mv_virtual_namebox::MvVirtualNameboxRuleInput>,
    text_rules: Option<RuleCandidateTextRules>,
}

#[derive(Debug, Clone, Deserialize)]
struct RuleCandidateTextRules {
    #[serde(default)]
    custom_placeholder_rules: Vec<NativeCustomPlaceholderRule>,
    #[serde(default)]
    structured_placeholder_rules: Vec<NativeStructuredPlaceholderRule>,
    #[serde(default)]
    strip_wrapping_punctuation_pairs: Vec<(String, String)>,
    source_text_required_pattern: String,
    #[serde(default = "default_source_text_exclusion_profile")]
    source_text_exclusion_profile: String,
}

#[derive(Debug, Deserialize)]
struct ScopeEntryInput {
    #[serde(default)]
    fact_id: Option<String>,
    location_path: String,
    item_type: String,
    role: Option<String>,
    original_lines: Vec<String>,
    #[serde(default)]
    source_line_paths: Vec<String>,
    source_type: String,
    source_file: String,
    #[serde(default)]
    rule_source: String,
    #[serde(default)]
    enters_translation: bool,
    #[serde(default)]
    can_write_back: bool,
    #[serde(default)]
    cannot_process_reason: String,
    #[serde(default)]
    locator: Value,
}

#[derive(Debug, Deserialize)]
struct RuleHitInput {
    domain: String,
    rule_key: String,
    location_path: String,
    extractable: bool,
    writable: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
struct CandidateGroupOutput {
    domain: String,
    candidate_count: usize,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
struct StaleRuleDetailOutput {
    domain: String,
    rule_key: String,
    reason: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
struct RuleCandidateOutput {
    domain: String,
    location_path: String,
    rule_key: String,
    original_text: String,
    source_file: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    json_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    source_text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    field_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    sibling_field_names: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    parent_object_keys: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    selector: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    raw_text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    quote: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    line: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    start_index: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    end_index: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    content_start_index: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    content_end_index: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    context: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    api: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    ast_context: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    active: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    confidence: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    structural_flags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    file_hash: Option<String>,
}

#[derive(Debug, Serialize)]
struct BuildScopeIndexOutput {
    contract_versions: ContractVersionsOutput,
    text_index_rows: Vec<TextIndexRowOutput>,
    scope_summary: ScopeSummaryOutput,
    domain_summary: Vec<DomainSummaryOutput>,
    rule_hit_summary: Vec<RuleHitSummaryOutput>,
    candidate_summary: Vec<CandidateGroupOutput>,
    unwritable_reasons: Vec<UnwritableReasonOutput>,
    stale_rule_details: Vec<StaleRuleDetailOutput>,
    writable_location_paths: Vec<String>,
}

#[derive(Debug, Serialize)]
struct RuleCandidatesOutput {
    schema_version: usize,
    contract_versions: ContractVersionsOutput,
    candidates: Vec<RuleCandidateOutput>,
    candidate_summary: Vec<CandidateGroupOutput>,
    scan_summary: BTreeMap<String, Value>,
    timings_ms: BTreeMap<String, u64>,
    counters: BTreeMap<String, usize>,
}

fn default_source_text_exclusion_profile() -> String {
    "none".to_string()
}

#[derive(Debug, Serialize)]
struct ScopeGateOutput {
    contract_versions: ContractVersionsOutput,
    workflow_gate: WorkflowGateOutput,
    quality_gate: QualityGateOutput,
    pending_count: usize,
    translated_count: usize,
    quality_error_count: usize,
    writable_location_paths: Vec<String>,
}

#[derive(Debug, Serialize)]
struct TextIndexRowOutput {
    location_path: String,
    item_type: String,
    role: Option<String>,
    original_lines: Vec<String>,
    source_line_paths: Vec<String>,
    source_type: String,
    source_file: String,
    rule_source: String,
    writable: bool,
    source_snapshot_fingerprint: String,
    rules_fingerprint: String,
    locator_json: String,
}

#[derive(Debug, Serialize)]
struct ScopeSummaryOutput {
    total_count: usize,
    active_count: usize,
    writable_count: usize,
    unwritable_count: usize,
    stale_rule_count: usize,
    native_thread_count: usize,
}

#[derive(Debug, Default)]
struct DomainCounter {
    item_count: usize,
    active_count: usize,
    writable_count: usize,
    unwritable_count: usize,
    inactive_rule_hit_count: usize,
}

#[derive(Debug, Serialize)]
struct DomainSummaryOutput {
    domain: String,
    item_count: usize,
    active_count: usize,
    writable_count: usize,
    unwritable_count: usize,
    inactive_rule_hit_count: usize,
}

#[derive(Debug, Default)]
struct RuleHitCounter {
    hit_count: usize,
    extractable_count: usize,
    writable_count: usize,
    unwritable_count: usize,
    location_paths: BTreeSet<String>,
}

#[derive(Debug, Serialize)]
struct RuleHitSummaryOutput {
    domain: String,
    rule_key: String,
    hit_count: usize,
    location_count: usize,
    extractable_count: usize,
    writable_count: usize,
    unwritable_count: usize,
}

#[derive(Debug, Serialize)]
struct UnwritableReasonOutput {
    location_path: String,
    reason: String,
}

#[derive(Debug, Serialize)]
struct WorkflowGateOutput {
    status: &'static str,
    missing_required_paths: Vec<String>,
}

#[derive(Debug, Serialize)]
struct QualityGateOutput {
    status: &'static str,
    quality_error_count: usize,
}

pub(crate) fn build_scope_index_impl(payload_json: &str) -> Result<String, String> {
    let payload: BuildScopeIndexPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("Scope/Index 输入 JSON 解析失败: {error}"))?;
    pool::run_with_optional_pool(|| build_scope_index(payload))?
}

pub(crate) fn scan_rule_candidates_impl(payload_json: &str) -> Result<String, String> {
    let payload: RuleCandidatesPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则候选输入 JSON 解析失败: {error}"))?;
    pool::run_with_optional_pool(|| scan_rule_candidates(payload))?
}

pub(crate) fn evaluate_scope_gate_impl(payload_json: &str) -> Result<String, String> {
    let payload: ScopeGatePayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("范围门禁输入 JSON 解析失败: {error}"))?;
    pool::run_with_optional_pool(|| evaluate_scope_gate(payload))?
}

pub(crate) fn native_schema_fingerprint_impl() -> String {
    storage::current_schema_fingerprint()
}

pub(crate) fn inspect_scope_index_storage_impl(payload_json: &str) -> Result<String, String> {
    storage::inspect_scope_index_storage_impl(payload_json)
}

pub(crate) fn write_scope_index_storage_impl(payload_json: &str) -> Result<String, String> {
    storage::write_scope_index_storage_impl(payload_json)
}

pub(crate) fn rebuild_scope_index_storage_impl(payload_json: &str) -> Result<String, String> {
    rebuild::rebuild_scope_index_storage_impl(payload_json)
}

fn build_scope_index(payload: BuildScopeIndexPayload) -> Result<String, String> {
    let BuildScopeIndexPayload {
        source_snapshot_fingerprint,
        rules_fingerprint,
        mut entries,
        data_files,
        rule_hits,
        candidate_groups,
        stale_rule_details,
    } = payload;
    entries.extend(scan_data_files(&data_files));

    let native_thread_count = pool::read_configured_thread_count()
        .map(|thread_count| thread_count.unwrap_or_else(rayon::current_num_threads))?;
    let mut text_index_rows: Vec<TextIndexRowOutput> = Vec::with_capacity(entries.len());
    let mut domain_counters: BTreeMap<String, DomainCounter> = BTreeMap::new();
    let mut writable_location_paths: Vec<String> = Vec::new();
    let mut unwritable_reasons: Vec<UnwritableReasonOutput> = Vec::new();

    for entry in &entries {
        update_domain_counter(&mut domain_counters, entry);
        if entry.enters_translation && entry.can_write_back {
            writable_location_paths.push(entry.location_path.clone());
        }
        if entry.enters_translation && !entry.can_write_back {
            unwritable_reasons.push(UnwritableReasonOutput {
                location_path: entry.location_path.clone(),
                reason: entry.cannot_process_reason.clone(),
            });
        }
        if entry.enters_translation {
            text_index_rows.push(text_index_row_from_entry(
                entry,
                &source_snapshot_fingerprint,
                &rules_fingerprint,
            )?);
        }
    }
    writable_location_paths.sort();
    unwritable_reasons.sort_by(|left, right| left.location_path.cmp(&right.location_path));

    for rule_hit in &rule_hits {
        if !rule_hit.extractable {
            domain_counters
                .entry(rule_hit.domain.clone())
                .or_default()
                .inactive_rule_hit_count += 1;
        }
    }

    let scope_summary = ScopeSummaryOutput {
        total_count: entries.len(),
        active_count: entries
            .iter()
            .filter(|entry| entry.enters_translation)
            .count(),
        writable_count: entries
            .iter()
            .filter(|entry| entry.enters_translation && entry.can_write_back)
            .count(),
        unwritable_count: entries
            .iter()
            .filter(|entry| entry.enters_translation && !entry.can_write_back)
            .count(),
        stale_rule_count: stale_rule_details.len(),
        native_thread_count,
    };

    let output = BuildScopeIndexOutput {
        contract_versions: current_contract_versions(),
        text_index_rows,
        scope_summary,
        domain_summary: domain_summary_outputs(domain_counters),
        rule_hit_summary: rule_hit_summary_outputs(&rule_hits),
        candidate_summary: sorted_candidate_summary(candidate_groups),
        unwritable_reasons,
        stale_rule_details,
        writable_location_paths,
    };
    serde_json::to_string(&output)
        .map_err(|error| format!("Scope/Index 输出 JSON 序列化失败: {error}"))
}

fn scan_data_files(data_files: &[ScopeIndexDataFileInput]) -> Vec<ScopeEntryInput> {
    let mut entries = Vec::new();
    for data_file in data_files {
        scan_standard_data_file(data_file, &mut entries);
        scan_event_command_data_file(data_file, &mut entries);
    }
    entries
}

fn scan_standard_data_file(
    data_file: &ScopeIndexDataFileInput,
    entries: &mut Vec<ScopeEntryInput>,
) {
    if data_file.file_name != "System.json" {
        return;
    }
    let Some(object) = data_file.data.as_object() else {
        return;
    };
    let Some(game_title) = object.get("gameTitle").and_then(Value::as_str) else {
        return;
    };
    if game_title.is_empty() {
        return;
    }

    entries.push(ScopeEntryInput {
        fact_id: None,
        location_path: "System.json/gameTitle".to_owned(),
        item_type: "short_text".to_owned(),
        role: None,
        original_lines: vec![game_title.to_owned()],
        source_line_paths: Vec::new(),
        source_type: "standard_data".to_owned(),
        source_file: data_file.file_name.clone(),
        rule_source: "standard_data".to_owned(),
        enters_translation: true,
        can_write_back: true,
        cannot_process_reason: String::new(),
        locator: json!({
            "kind": "standard_data",
            "path": ["gameTitle"]
        }),
    });
}

fn scan_event_command_data_file(
    data_file: &ScopeIndexDataFileInput,
    entries: &mut Vec<ScopeEntryInput>,
) {
    let mut path_parts: Vec<String> = Vec::new();
    scan_event_command_value(
        &data_file.file_name,
        &data_file.data,
        &mut path_parts,
        entries,
    );
}

fn scan_event_command_value(
    file_name: &str,
    value: &Value,
    path_parts: &mut Vec<String>,
    entries: &mut Vec<ScopeEntryInput>,
) {
    match value {
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                path_parts.push(index.to_string());
                scan_event_command_value(file_name, item, path_parts, entries);
                path_parts.pop();
            }
        }
        Value::Object(object) => {
            append_event_command_entry(file_name, object, path_parts, entries);
            for (key, child) in object {
                path_parts.push(key.clone());
                scan_event_command_value(file_name, child, path_parts, entries);
                path_parts.pop();
            }
        }
        _ => {}
    }
}

fn append_event_command_entry(
    file_name: &str,
    object: &Map<String, Value>,
    path_parts: &[String],
    entries: &mut Vec<ScopeEntryInput>,
) {
    let Some(401) = object.get("code").and_then(Value::as_i64) else {
        return;
    };
    let Some(parameters) = object.get("parameters").and_then(Value::as_array) else {
        return;
    };
    let Some(original_text) = parameters.first().and_then(Value::as_str) else {
        return;
    };
    if original_text.is_empty() {
        return;
    }

    let location_path = command_parameter_location_path(file_name, path_parts, 0);
    entries.push(ScopeEntryInput {
        fact_id: None,
        location_path: location_path.clone(),
        item_type: "long_text".to_owned(),
        role: None,
        original_lines: vec![original_text.to_owned()],
        source_line_paths: vec![location_path],
        source_type: "event_command".to_owned(),
        source_file: file_name.to_owned(),
        rule_source: "event_command.default".to_owned(),
        enters_translation: true,
        can_write_back: true,
        cannot_process_reason: String::new(),
        locator: json!({
            "kind": "event_command",
            "code": 401,
            "parameters_index": 0
        }),
    });
}

fn command_parameter_location_path(
    file_name: &str,
    path_parts: &[String],
    parameter_index: usize,
) -> String {
    let mut location_path = file_name.to_owned();
    for part in path_parts {
        location_path.push('/');
        location_path.push_str(part);
    }
    location_path.push_str("/parameters/");
    location_path.push_str(&parameter_index.to_string());
    location_path
}

fn scan_rule_candidates(payload: RuleCandidatesPayload) -> Result<String, String> {
    let RuleCandidatesPayload {
        mut candidates,
        plugin_source_files,
        plugin_source_text_rules,
        plugin_source_read_error_file_count,
        nonstandard_data_files,
        nonstandard_data_leaves,
        nonstandard_data_rule_coverage,
        placeholder_texts,
        structured_placeholder_texts,
        note_tag_data_files,
        event_command_data_files,
        event_command_codes,
        event_command_rules,
        plugin_config_plugins,
        plugin_config_rules,
        mv_virtual_namebox_data_files,
        mv_virtual_namebox_actor_names,
        mv_virtual_namebox_rules,
        text_rules,
    } = payload;
    let mut scan_summary: BTreeMap<String, Value> = BTreeMap::new();
    let mut extra_summary_by_domain: BTreeMap<String, usize> = BTreeMap::new();
    if !plugin_source_files.is_empty() {
        let text_rules = text_rules
            .clone()
            .ok_or_else(|| "规则候选扫描缺少插件源码提取文本规则 text_rules".to_string())?;
        let plugin_source_scan = scan_plugin_source_rule_candidates_with_rules(
            &plugin_source_files,
            &plugin_source_text_rules,
            text_rules,
            plugin_source_read_error_file_count,
        )?;
        scan_summary.insert(
            "plugin_source".to_string(),
            json!({
                "active_candidate_count": plugin_source_scan
                    .candidates
                    .iter()
                    .filter(|candidate| candidate.active == Some(true))
                    .count(),
                "candidate_count": plugin_source_scan.candidates.len(),
                "ignored_file_count": plugin_source_scan.ignored_file_count,
                "review_summary": plugin_source_scan.review_summary,
                "risk_summary": plugin_source_scan.risk_summary,
                "scanned_file_count": plugin_source_scan.scanned_file_count,
                "scope_hash": plugin_source_scan.scope_hash,
                "selector_facts": plugin_source_scan.selector_facts,
                "syntax_error_file_count": plugin_source_scan.syntax_error_file_count,
                "syntax_errors": plugin_source_scan.syntax_errors
            }),
        );
        candidates.extend(plugin_source_scan.candidates);
    }
    if !placeholder_texts.is_empty() {
        let text_rules = text_rules
            .clone()
            .ok_or_else(|| "规则候选扫描缺少普通占位符提取文本规则 text_rules".to_string())?;
        let placeholder_scan =
            placeholders::scan_placeholder_rule_candidates(&placeholder_texts, text_rules)?;
        let candidate_count = placeholder_scan.candidates.len();
        let covered_count = placeholder_scan
            .candidates
            .iter()
            .filter(|candidate| candidate.covered)
            .count();
        let standard_covered_count = placeholder_scan
            .candidates
            .iter()
            .filter(|candidate| candidate.standard_covered)
            .count();
        let custom_covered_count = placeholder_scan
            .candidates
            .iter()
            .filter(|candidate| candidate.custom_covered)
            .count();
        extra_summary_by_domain.insert("placeholders".to_string(), candidate_count);
        scan_summary.insert(
            "placeholders".to_string(),
            json!({
                "candidate_count": candidate_count,
                "candidates": placeholder_scan.candidates,
                "covered_count": covered_count,
                "custom_covered_count": custom_covered_count,
                "scanned_text_count": placeholder_scan.scanned_text_count,
                "standard_covered_count": standard_covered_count,
                "uncovered_count": candidate_count - covered_count,
            }),
        );
    }
    if !structured_placeholder_texts.is_empty() {
        let text_rules = text_rules
            .clone()
            .ok_or_else(|| "规则候选扫描缺少结构化占位符提取文本规则 text_rules".to_string())?;
        let structured_scan = structured_placeholders::scan_structured_placeholder_rule_candidates(
            &structured_placeholder_texts,
            text_rules,
        )?;
        let candidate_count = structured_scan.candidates.len();
        let covered_count = structured_scan
            .candidates
            .iter()
            .filter(|candidate| candidate.covered)
            .count();
        extra_summary_by_domain.insert("structured_placeholders".to_string(), candidate_count);
        scan_summary.insert(
            "structured_placeholders".to_string(),
            json!({
                "candidate_count": candidate_count,
                "candidates": structured_scan.candidates,
                "covered_count": covered_count,
                "scanned_text_count": structured_scan.scanned_text_count,
                "uncovered_count": candidate_count - covered_count,
            }),
        );
    }
    if !note_tag_data_files.is_empty() {
        let text_rules = text_rules
            .clone()
            .ok_or_else(|| "规则候选扫描缺少 Note 标签提取文本规则 text_rules".to_string())?;
        let note_tag_scan =
            note_tags::scan_note_tag_rule_candidates(&note_tag_data_files, text_rules)?;
        let candidate_count = note_tag_scan.candidates.len();
        extra_summary_by_domain.insert("note_tags".to_string(), candidate_count);
        scan_summary.insert(
            "note_tags".to_string(),
            json!({
                "candidate_count": candidate_count,
                "candidate_value_count": note_tag_scan.candidate_value_count,
                "candidates": note_tag_scan.candidates,
                "hit_details": note_tag_scan.hit_details,
                "scanned_source_count": note_tag_scan.scanned_source_count,
                "source_details": note_tag_scan.source_details,
                "translatable_value_count": note_tag_scan.translatable_value_count,
                "value_hit_count": note_tag_scan.value_hit_count,
            }),
        );
    }
    if !event_command_data_files.is_empty() {
        let event_command_scan = event_commands::scan_event_command_rule_candidates(
            &event_command_data_files,
            &event_command_codes,
            &event_command_rules,
        )?;
        scan_summary.insert(
            "event_commands".to_string(),
            json!({
                "candidate_count": event_command_scan.candidates.len(),
                "command_codes": event_command_scan.command_codes,
                "hit_details": event_command_scan.hit_details,
                "matched_command_count": event_command_scan.matched_command_count,
                "rule_summaries": event_command_scan.rule_summaries,
                "sample_count": event_command_scan.sample_count,
                "samples_by_code": event_command_scan.samples_by_code,
                "scanned_command_count": event_command_scan.scanned_command_count,
            }),
        );
        candidates.extend(event_command_scan.candidates);
    }
    if !plugin_config_plugins.is_empty() || !plugin_config_rules.is_empty() {
        let text_rules = text_rules
            .clone()
            .ok_or_else(|| "规则候选扫描缺少插件参数提取文本规则 text_rules".to_string())?;
        let plugin_config_scan = plugin_config::scan_plugin_config_rule_candidates(
            &plugin_config_plugins,
            &plugin_config_rules,
            text_rules,
        )?;
        scan_summary.insert(
            "plugin_config".to_string(),
            json!({
                "candidate_count": plugin_config_scan.candidate_count,
                "hit_details": plugin_config_scan.hit_details,
                "plugin_count": plugin_config_scan.plugin_count,
                "plugins": plugin_config_scan.plugins,
                "rule_summaries": plugin_config_scan.rule_summaries,
                "string_leaf_count": plugin_config_scan.string_leaf_count,
            }),
        );
        candidates.extend(plugin_config_scan.candidates);
    }
    if !mv_virtual_namebox_data_files.is_empty() || !mv_virtual_namebox_rules.is_empty() {
        let mv_virtual_namebox_scan = mv_virtual_namebox::scan_mv_virtual_namebox_rule_candidates(
            &mv_virtual_namebox_data_files,
            &mv_virtual_namebox_actor_names,
            &mv_virtual_namebox_rules,
        )?;
        scan_summary.insert(
            "mv_virtual_namebox".to_string(),
            json!({
                "candidate_count": mv_virtual_namebox_scan.candidate_details.len(),
                "candidate_details": mv_virtual_namebox_scan.candidate_details,
                "errors": mv_virtual_namebox_scan.errors,
                "hit_details": mv_virtual_namebox_scan.hit_details,
                "matched_candidate_count": mv_virtual_namebox_scan.hit_details.len(),
                "rule_summaries": mv_virtual_namebox_scan.rule_summaries,
                "scope_hash": mv_virtual_namebox_scan.scope_hash,
                "scanned_command_count": mv_virtual_namebox_scan.scanned_command_count,
                "scanned_file_count": mv_virtual_namebox_scan.scanned_file_count,
                "speaker_requirements": mv_virtual_namebox_scan.speaker_requirements,
            }),
        );
        candidates.extend(mv_virtual_namebox_scan.candidates);
    }
    if !nonstandard_data_files.is_empty() {
        let text_rules = text_rules
            .clone()
            .ok_or_else(|| "规则候选扫描缺少非标准 data 提取文本规则 text_rules".to_string())?;
        let nonstandard_data_scan = nonstandard_data::scan_nonstandard_data_rule_candidates(
            &nonstandard_data_files,
            text_rules,
        )?;
        scan_summary.insert(
            "nonstandard_data".to_string(),
            json!({
                "candidate_count": nonstandard_data_scan.candidates.len(),
                "files": nonstandard_data_scan.file_scans,
                "high_risk": !nonstandard_data_scan.candidates.is_empty(),
                "nonstandard_file_count": nonstandard_data_scan.nonstandard_file_count,
                "scanned_file_count": nonstandard_data_scan.nonstandard_file_count,
            }),
        );
        candidates.extend(nonstandard_data_scan.candidates);
    }
    if !nonstandard_data_leaves.is_empty() {
        let file_scans =
            nonstandard_data::scan_nonstandard_data_file_leaves(&nonstandard_data_leaves)?;
        scan_summary.insert(
            "nonstandard_data_leaves".to_string(),
            json!({
                "candidate_count": 0,
                "files": file_scans,
                "high_risk": false,
                "nonstandard_file_count": nonstandard_data_leaves.len(),
                "scanned_file_count": nonstandard_data_leaves.len(),
            }),
        );
    }
    if let Some(coverage_input) = nonstandard_data_rule_coverage {
        scan_summary.insert(
            "nonstandard_data_rule_coverage".to_string(),
            nonstandard_data::scan_nonstandard_data_rule_coverage(coverage_input)?,
        );
    }
    let mut summary_by_domain: BTreeMap<String, usize> = BTreeMap::new();
    for candidate in &candidates {
        *summary_by_domain
            .entry(candidate.domain.clone())
            .or_default() += 1;
    }
    for (domain, candidate_count) in extra_summary_by_domain {
        *summary_by_domain.entry(domain).or_default() += candidate_count;
    }
    let candidate_count = summary_by_domain.values().sum();
    let mut counters = BTreeMap::new();
    counters.insert("candidate_count".to_string(), candidate_count);
    let output = RuleCandidatesOutput {
        schema_version: RULE_CANDIDATES_SCHEMA_VERSION,
        contract_versions: current_contract_versions(),
        candidates,
        candidate_summary: summary_by_domain
            .into_iter()
            .map(|(domain, candidate_count)| CandidateGroupOutput {
                domain,
                candidate_count,
            })
            .collect(),
        scan_summary,
        timings_ms: BTreeMap::new(),
        counters,
    };
    serde_json::to_string(&output).map_err(|error| format!("规则候选输出 JSON 序列化失败: {error}"))
}

fn evaluate_scope_gate(payload: ScopeGatePayload) -> Result<String, String> {
    let active_paths: BTreeSet<String> = payload
        .entries
        .iter()
        .filter(|entry| entry.enters_translation)
        .map(|entry| entry.location_path.clone())
        .collect();
    let mut active_fact_ids: BTreeSet<String> = BTreeSet::new();
    let mut writable_fact_ids: BTreeSet<String> = BTreeSet::new();
    let mut writable_location_paths: Vec<String> = payload
        .entries
        .iter()
        .filter(|entry| entry.enters_translation && entry.can_write_back)
        .map(|entry| entry.location_path.clone())
        .collect();
    writable_location_paths.sort();
    writable_location_paths.dedup();
    for entry in payload
        .entries
        .iter()
        .filter(|entry| entry.enters_translation)
    {
        let fact_id = scope_gate_entry_fact_id(entry)?;
        active_fact_ids.insert(fact_id.clone());
        if entry.can_write_back {
            writable_fact_ids.insert(fact_id);
        }
    }

    let matched_translation_fact_ids: BTreeSet<String> =
        payload.matched_translation_fact_ids.into_iter().collect();
    let quality_error_fact_ids: BTreeSet<String> =
        payload.quality_error_fact_ids.into_iter().collect();
    let missing_required_paths: Vec<String> = payload
        .required_paths
        .into_iter()
        .filter(|path| !active_paths.contains(path))
        .collect();
    let output = ScopeGateOutput {
        contract_versions: current_contract_versions(),
        workflow_gate: WorkflowGateOutput {
            status: if missing_required_paths.is_empty() {
                "ok"
            } else {
                "error"
            },
            missing_required_paths,
        },
        quality_gate: QualityGateOutput {
            status: if quality_error_fact_ids.is_empty() {
                "ok"
            } else {
                "error"
            },
            quality_error_count: quality_error_fact_ids.len(),
        },
        pending_count: writable_fact_ids
            .difference(&matched_translation_fact_ids)
            .count(),
        translated_count: active_fact_ids
            .intersection(&matched_translation_fact_ids)
            .count(),
        quality_error_count: quality_error_fact_ids.len(),
        writable_location_paths,
    };
    serde_json::to_string(&output).map_err(|error| format!("范围门禁输出 JSON 序列化失败: {error}"))
}

fn scope_gate_entry_fact_id(entry: &ScopeEntryInput) -> Result<String, String> {
    let Some(fact_id) = &entry.fact_id else {
        return Err(format!(
            "范围门禁 entry 缺少 current text fact_id，无法判断当前事实身份: {}",
            entry.location_path
        ));
    };
    if fact_id.trim().is_empty() {
        return Err(format!(
            "范围门禁 entry 的 current text fact_id 不能为空，无法判断当前事实身份: {}",
            entry.location_path
        ));
    }
    Ok(fact_id.clone())
}

fn update_domain_counter(
    domain_counters: &mut BTreeMap<String, DomainCounter>,
    entry: &ScopeEntryInput,
) {
    let counter = domain_counters
        .entry(entry.source_type.clone())
        .or_default();
    counter.item_count += 1;
    if entry.enters_translation {
        counter.active_count += 1;
        if entry.can_write_back {
            counter.writable_count += 1;
        } else {
            counter.unwritable_count += 1;
        }
    }
}

fn text_index_row_from_entry(
    entry: &ScopeEntryInput,
    source_snapshot_fingerprint: &str,
    rules_fingerprint: &str,
) -> Result<TextIndexRowOutput, String> {
    let locator_json = serde_json::to_string(&entry.locator)
        .map_err(|error| format!("Scope/Index locator JSON 序列化失败: {error}"))?;
    Ok(TextIndexRowOutput {
        location_path: entry.location_path.clone(),
        item_type: entry.item_type.clone(),
        role: entry.role.clone(),
        original_lines: entry.original_lines.clone(),
        source_line_paths: entry.source_line_paths.clone(),
        source_type: entry.source_type.clone(),
        source_file: entry.source_file.clone(),
        rule_source: entry.rule_source.clone(),
        writable: entry.enters_translation && entry.can_write_back,
        source_snapshot_fingerprint: source_snapshot_fingerprint.to_owned(),
        rules_fingerprint: rules_fingerprint.to_owned(),
        locator_json,
    })
}

fn domain_summary_outputs(
    domain_counters: BTreeMap<String, DomainCounter>,
) -> Vec<DomainSummaryOutput> {
    domain_counters
        .into_iter()
        .map(|(domain, counter)| DomainSummaryOutput {
            domain,
            item_count: counter.item_count,
            active_count: counter.active_count,
            writable_count: counter.writable_count,
            unwritable_count: counter.unwritable_count,
            inactive_rule_hit_count: counter.inactive_rule_hit_count,
        })
        .collect()
}

fn rule_hit_summary_outputs(rule_hits: &[RuleHitInput]) -> Vec<RuleHitSummaryOutput> {
    let mut counters: BTreeMap<(String, String), RuleHitCounter> = BTreeMap::new();
    for rule_hit in rule_hits {
        let counter = counters
            .entry((rule_hit.domain.clone(), rule_hit.rule_key.clone()))
            .or_default();
        counter.hit_count += 1;
        counter
            .location_paths
            .insert(rule_hit.location_path.clone());
        if rule_hit.extractable {
            counter.extractable_count += 1;
        }
        if rule_hit.writable {
            counter.writable_count += 1;
        } else {
            counter.unwritable_count += 1;
        }
    }
    counters
        .into_iter()
        .map(|((domain, rule_key), counter)| RuleHitSummaryOutput {
            domain,
            rule_key,
            hit_count: counter.hit_count,
            location_count: counter.location_paths.len(),
            extractable_count: counter.extractable_count,
            writable_count: counter.writable_count,
            unwritable_count: counter.unwritable_count,
        })
        .collect()
}

fn sorted_candidate_summary(
    mut candidate_groups: Vec<CandidateGroupOutput>,
) -> Vec<CandidateGroupOutput> {
    candidate_groups.sort_by(|left, right| left.domain.cmp(&right.domain));
    candidate_groups
}

#[cfg(test)]
mod tests {
    use super::{build_scope_index_impl, evaluate_scope_gate_impl, scan_rule_candidates_impl};
    use serde_json::{Value, json};

    #[test]
    fn build_scope_index_outputs_text_rows_and_summaries() {
        let payload = json!({
            "source_snapshot_fingerprint": "snapshot-v1",
            "rules_fingerprint": "rules-v1",
            "entries": [
                {
                    "fact_id": "fact:event-command:hello",
                    "location_path": "Map001.json/events/1/pages/0/list/0",
                    "item_type": "long_text",
                    "role": "Alice",
                    "original_lines": ["Hello"],
                    "source_line_paths": ["Map001.json/events/1/pages/0/list/1"],
                    "source_type": "event_command",
                    "source_file": "Map001.json",
                    "rule_source": "event_command.default",
                    "enters_translation": true,
                    "can_write_back": true,
                    "cannot_process_reason": "",
                    "locator": {"kind": "event_command"}
                }
            ]
        });

        let output = build_scope_index_impl(&payload.to_string()).expect("Scope/Index 应构建成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(value["contract_versions"]["rust_scope_facts"], json!(1));
        assert_eq!(value["scope_summary"]["total_count"], json!(1));
        assert_eq!(
            value["text_index_rows"][0]["source_snapshot_fingerprint"],
            json!("snapshot-v1")
        );
    }

    #[test]
    fn build_scope_index_scans_system_title_and_event_command_text() {
        let payload = json!({
            "source_snapshot_fingerprint": "snapshot-current",
            "rules_fingerprint": "rules-current",
            "data_files": [
                {
                    "file_name": "System.json",
                    "data": {"gameTitle": "Fixture Game"}
                },
                {
                    "file_name": "Map001.json",
                    "data": {
                        "events": [
                            null,
                            {
                                "pages": [
                                    {
                                        "list": [
                                            {"code": 401, "parameters": ["Hello there"]}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        });

        let output = build_scope_index_impl(&payload.to_string()).expect("Scope/Index 应构建成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(value["scope_summary"]["total_count"], json!(2));
        assert_eq!(
            value["text_index_rows"][0]["location_path"],
            json!("System.json/gameTitle")
        );
        assert_eq!(
            value["text_index_rows"][1]["location_path"],
            json!("Map001.json/events/1/pages/0/list/0/parameters/0")
        );
    }

    #[test]
    fn scan_rule_candidates_summarizes_direct_candidates_by_sorted_domain() {
        let payload = json!({
            "candidates": [
                {
                    "domain": "plugin_source",
                    "location_path": "js/plugins/Foo.js/0",
                    "rule_key": "FooRule",
                    "original_text": "Foo text",
                    "source_file": "Foo.js"
                },
                {
                    "domain": "plugin_source",
                    "location_path": "js/plugins/Foo.js/1",
                    "rule_key": "FooRule",
                    "original_text": "Bar text",
                    "source_file": "Foo.js"
                },
                {
                    "domain": "note_tag",
                    "location_path": "Actors.json/1/note/foo",
                    "rule_key": "note.foo",
                    "original_text": "Note text",
                    "source_file": "Actors.json"
                }
            ]
        });

        let output = scan_rule_candidates_impl(&payload.to_string()).expect("候选汇总应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(value["schema_version"], json!(1));
        assert_eq!(value["contract_versions"]["rust_scope_facts"], json!(1));
        assert_eq!(value["contract_versions"]["text_fact_schema"], json!(2));
        assert!(value["scan_summary"].is_object());
        assert!(value["timings_ms"].is_object());
        assert_eq!(value["counters"]["candidate_count"], json!(3));
        assert_eq!(value["candidates"].as_array().map(Vec::len), Some(3));
        assert_eq!(
            value["candidate_summary"],
            json!([
                {"domain": "note_tag", "candidate_count": 1},
                {"domain": "plugin_source", "candidate_count": 2}
            ])
        );
    }

    #[test]
    fn evaluate_scope_gate_outputs_compact_workflow_and_quality_summary() {
        let payload = json!({
            "entries": [
                {
                    "fact_id": "fact:event-command:hello",
                    "location_path": "Map001.json/events/1/pages/0/list/0",
                    "item_type": "long_text",
                    "role": null,
                    "original_lines": ["Hello"],
                    "source_line_paths": ["Map001.json/events/1/pages/0/list/0"],
                    "source_type": "event_command",
                    "source_file": "Map001.json",
                    "rule_source": "event_command.default",
                    "enters_translation": true,
                    "can_write_back": true,
                    "cannot_process_reason": "",
                    "locator": {"kind": "event_command"}
                },
                {
                    "fact_id": "fact:system:title",
                    "location_path": "System.json/gameTitle",
                    "item_type": "short_text",
                    "role": null,
                    "original_lines": ["Fixture"],
                    "source_line_paths": ["System.json/gameTitle"],
                    "source_type": "system",
                    "source_file": "System.json",
                    "rule_source": "system.title",
                    "enters_translation": true,
                    "can_write_back": false,
                    "cannot_process_reason": "只读",
                    "locator": {"kind": "system"}
                }
            ],
            "matched_translation_fact_ids": ["fact:event-command:hello"],
            "quality_error_fact_ids": ["fact:system:title"],
            "required_paths": [
                "Map001.json/events/1/pages/0/list/0",
                "missing/path"
            ]
        });

        let output = evaluate_scope_gate_impl(&payload.to_string()).expect("范围门禁评估应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(value["pending_count"], json!(0));
        assert_eq!(value["translated_count"], json!(1));
        assert_eq!(value["quality_error_count"], json!(1));
        assert_eq!(
            value["writable_location_paths"],
            json!(["Map001.json/events/1/pages/0/list/0"])
        );
        assert_eq!(value["workflow_gate"]["status"], json!("error"));
        assert_eq!(
            value["workflow_gate"]["missing_required_paths"],
            json!(["missing/path"])
        );
        assert_eq!(value["quality_gate"]["status"], json!("error"));
    }

    #[test]
    fn scan_rule_candidates_scans_event_command_candidates() {
        let payload = json!({
            "event_command_data_files": [
                {
                    "file_name": "Map001.json",
                    "data": {
                        "events": [
                            null,
                            {
                                "id": 1,
                                "pages": [
                                    {
                                        "list": [
                                            {"code": 401, "parameters": ["Hello there"]},
                                            {"code": 401, "parameters": ["Hello there"]},
                                            {
                                                "code": 357,
                                                "parameters": [
                                                    "Speaker",
                                                    "{\"message\":\"Inside JSON\"}"
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ],
            "event_command_codes": [401],
            "event_command_rules": [
                {
                    "command_code": 357,
                    "parameter_filters": [{"index": 0, "value": "Speaker"}],
                    "path_templates": ["$['parameters'][1]['message']"]
                }
            ]
        });

        let output =
            scan_rule_candidates_impl(&payload.to_string()).expect("事件指令候选扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(
            value["candidate_summary"],
            json!([{"domain": "event_commands", "candidate_count": 3}])
        );
        assert_eq!(
            value["scan_summary"]["event_commands"]["command_codes"],
            json!([357, 401])
        );
        assert_eq!(
            value["scan_summary"]["event_commands"]["samples_by_code"],
            json!({
                "357": [["Speaker", "{\"message\":\"Inside JSON\"}"]],
                "401": [["Hello there"]]
            })
        );
        assert_eq!(
            value["scan_summary"]["event_commands"]["hit_details"][0],
            json!({
                "command_code": 357,
                "command_location_path": "Map001.json/1/0/2",
                "file_name": "Map001.json",
                "json_path": "$['parameters'][1]['message']",
                "location_path": "Map001.json/1/0/2/parameters/1/message",
                "original_text": "Inside JSON",
                "path_template": "$['parameters'][1]['message']",
                "rule_index": 0
            })
        );
        assert_eq!(
            value["scan_summary"]["event_commands"]["rule_summaries"],
            json!([
                {
                    "command_code": 357,
                    "matched_command_count": 1,
                    "matched_command_location_paths": ["Map001.json/1/0/2"],
                    "path_hit_counts": [
                        {
                            "path_template": "$['parameters'][1]['message']",
                            "hit_count": 1
                        }
                    ],
                    "rule_index": 0
                }
            ])
        );
    }

    #[test]
    fn scan_rule_candidates_scans_plugin_config_rule_hits() {
        let payload = json!({
            "plugin_config_plugins": [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "plugin": {
                        "name": "TestPlugin",
                        "status": true,
                        "parameters": {
                            "Message": "プラグイン本文",
                            "Nested": "{\"text\":\"ネスト本文\"}",
                            "Count": 3
                        }
                    }
                }
            ],
            "plugin_config_rules": [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "path_templates": [
                        "$['parameters']['Message']",
                        "$['parameters']['Nested']['text']"
                    ]
                }
            ],
            "text_rules": {
                "custom_placeholder_rules": [],
                "structured_placeholder_rules": [],
                "strip_wrapping_punctuation_pairs": [],
                "source_text_required_pattern": "[\\s\\S]",
                "source_text_exclusion_profile": "none"
            }
        });

        let output =
            scan_rule_candidates_impl(&payload.to_string()).expect("插件参数候选扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(
            value["candidate_summary"],
            json!([{"domain": "plugin_config", "candidate_count": 2}])
        );
        assert_eq!(
            value["scan_summary"]["plugin_config"]["candidate_count"],
            json!(2)
        );
        assert_eq!(
            value["scan_summary"]["plugin_config"]["string_leaf_count"],
            json!(2)
        );
        assert_eq!(
            value["scan_summary"]["plugin_config"]["hit_details"],
            json!([
                {
                    "json_path": "$['parameters']['Message']",
                    "location_path": "plugins.js/0/Message",
                    "original_text": "プラグイン本文",
                    "path_template": "$['parameters']['Message']",
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "rule_index": 0
                },
                {
                    "json_path": "$['parameters']['Nested']['text']",
                    "location_path": "plugins.js/0/Nested/text",
                    "original_text": "ネスト本文",
                    "path_template": "$['parameters']['Nested']['text']",
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "rule_index": 0
                }
            ])
        );
        assert_eq!(
            value["scan_summary"]["plugin_config"]["rule_summaries"][0]["path_hit_counts"],
            json!([
                {
                    "path_template": "$['parameters']['Message']",
                    "string_hit_count": 1,
                    "translatable_hit_count": 1
                },
                {
                    "path_template": "$['parameters']['Nested']['text']",
                    "string_hit_count": 1,
                    "translatable_hit_count": 1
                }
            ])
        );
    }

    #[test]
    fn scan_rule_candidates_scans_mv_virtual_namebox_rule_hits() {
        let payload = json!({
            "mv_virtual_namebox_data_files": [
                {
                    "file_name": "CommonEvents.json",
                    "data": [
                        null,
                        {
                            "id": 1,
                            "list": [
                                {"code": 101, "parameters": [0, 0, 0, 2]},
                                {"code": 401, "parameters": ["案内人："]},
                                {"code": 401, "parameters": ["本文です"]},
                                {"code": 101, "parameters": [0, 0, 0, 2]},
                                {"code": 401, "parameters": ["\\N[2]："]},
                                {"code": 401, "parameters": ["二番目の本文"]},
                                {"code": 101, "parameters": [0, 0, 0, 2]},
                                {"code": 401, "parameters": ["\\N[1]："]},
                                {"code": 401, "parameters": ["勇者の本文"]},
                                {"code": 0, "parameters": []}
                            ]
                        }
                    ]
                }
            ],
            "mv_virtual_namebox_actor_names": [{"actor_id": 1, "name": "MV勇者"}],
            "mv_virtual_namebox_rules": [
                {
                    "rule_order": 0,
                    "rule_name": "standalone-colon",
                    "pattern_text": r"^(?P<speaker>案内人)：$",
                    "speaker_group": "speaker",
                    "body_group": "",
                    "speaker_policy": "translate",
                    "render_template": "{speaker}："
                },
                {
                    "rule_order": 1,
                    "rule_name": "preserve-actor-control",
                    "pattern_text": r"^(?P<speaker>\\N\[2\])：$",
                    "speaker_group": "speaker",
                    "body_group": "",
                    "speaker_policy": "preserve",
                    "render_template": "{speaker}："
                },
                {
                    "rule_order": 2,
                    "rule_name": "actor-control",
                    "pattern_text": r"^(?P<speaker>\\N\[1\])：$",
                    "speaker_group": "speaker",
                    "body_group": "",
                    "speaker_policy": "actor_name",
                    "render_template": "{speaker}："
                }
            ]
        });

        let output =
            scan_rule_candidates_impl(&payload.to_string()).expect("MV 虚拟名字框候选扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(
            value["candidate_summary"],
            json!([{"domain": "mv_virtual_namebox", "candidate_count": 3}])
        );
        assert_eq!(
            value["scan_summary"]["mv_virtual_namebox"]["candidate_details"],
            json!([
                {
                    "location_path": "CommonEvents.json/1/1",
                    "text": "案内人：",
                    "following_lines": ["本文です"]
                },
                {
                    "location_path": "CommonEvents.json/1/4",
                    "text": "\\N[2]：",
                    "following_lines": ["二番目の本文"]
                },
                {
                    "location_path": "CommonEvents.json/1/7",
                    "text": "\\N[1]：",
                    "following_lines": ["勇者の本文"]
                }
            ])
        );
        assert_eq!(
            value["scan_summary"]["mv_virtual_namebox"]["hit_details"][0]["matching_rules"],
            json!(["standalone-colon"])
        );
        assert_eq!(
            value["scan_summary"]["mv_virtual_namebox"]["rule_summaries"],
            json!([
                {
                    "matched_candidate_count": 1,
                    "matched_candidate_location_paths": ["CommonEvents.json/1/1"],
                    "rule_index": 0,
                    "rule_name": "standalone-colon"
                },
                {
                    "matched_candidate_count": 1,
                    "matched_candidate_location_paths": ["CommonEvents.json/1/4"],
                    "rule_index": 1,
                    "rule_name": "preserve-actor-control"
                },
                {
                    "matched_candidate_count": 1,
                    "matched_candidate_location_paths": ["CommonEvents.json/1/7"],
                    "rule_index": 2,
                    "rule_name": "actor-control"
                }
            ])
        );
        assert!(
            value["scan_summary"]["mv_virtual_namebox"]["scope_hash"]
                .as_str()
                .is_some_and(|scope_hash| !scope_hash.is_empty())
        );
        assert_eq!(
            value["scan_summary"]["mv_virtual_namebox"]["speaker_requirements"],
            json!([
                {
                    "source_text": "案内人",
                    "policy": "translate",
                    "requires_speaker_name": true,
                    "rule_name": "standalone-colon",
                    "location_paths": ["CommonEvents.json/1/1"],
                    "sample_body_lines": ["本文です"],
                    "render_template": "{speaker}：",
                    "confidence": "rule_match"
                },
                {
                    "source_text": "\\N[2]",
                    "policy": "preserve",
                    "requires_speaker_name": false,
                    "rule_name": "preserve-actor-control",
                    "location_paths": ["CommonEvents.json/1/4"],
                    "sample_body_lines": ["二番目の本文"],
                    "render_template": "{speaker}：",
                    "confidence": "rule_match"
                },
                {
                    "source_text": "MV勇者",
                    "policy": "actor_name",
                    "requires_speaker_name": true,
                    "rule_name": "actor-control",
                    "location_paths": ["CommonEvents.json/1/7"],
                    "sample_body_lines": ["勇者の本文"],
                    "render_template": "{speaker}：",
                    "confidence": "rule_match"
                }
            ])
        );
    }
}
