//! Scope/Index Engine 最小核心。
//!
//! 本模块先固定三个 Rust 原生入口的结构化 JSON 契约，并把范围索引行、
//! 规则候选摘要和门禁摘要收敛到同一个 Rust 边界。

use rayon::prelude::*;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::Digest;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::LazyLock;

use super::controls::replace_control_sequences;
use super::javascript_ast::{
    JavaScriptStringAstContext, JavaScriptStringSpan, parse_javascript_string_spans,
};
use super::models::{
    CompiledRules, NativeCustomPlaceholderRule, NativeStructuredPlaceholderRule, NativeTextRules,
};
use super::pool;
use super::rules::compile_rules;
use super::write_back_plan::{
    candidate_selector_for_span, normalize_visible_text_for_extraction, unescape_js_text,
};

mod event_commands;
mod mv_virtual_namebox;
mod nonstandard_data;
mod note_tags;
mod placeholders;
mod plugin_config;
mod structured_placeholders;

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
    #[serde(default)]
    translated_paths: Vec<String>,
    #[serde(default)]
    quality_error_paths: Vec<String>,
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

#[derive(Debug, Deserialize)]
struct PluginSourceFileInput {
    file_name: String,
    source: String,
    active: bool,
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
    candidates: Vec<RuleCandidateOutput>,
    candidate_summary: Vec<CandidateGroupOutput>,
    scan_summary: BTreeMap<String, Value>,
}

struct CompiledRuleCandidateTextRules {
    control_rules: CompiledRules,
    source_text_required_re: Regex,
    source_text_exclusion_profile: String,
    strip_wrapping_punctuation_pairs: Vec<(String, String)>,
}

struct PluginSourceRuleCandidateScan {
    candidates: Vec<RuleCandidateOutput>,
    scanned_file_count: usize,
    ignored_file_count: usize,
    syntax_error_file_count: usize,
    syntax_errors: Vec<Value>,
}

struct PluginSourceFileRuleCandidateScan {
    file_name: String,
    candidates: Vec<RuleCandidateOutput>,
    active: bool,
    syntax_error: bool,
}

static NUMBER_LIKE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[-+]?\d+(?:\.\d+)?$")
        .unwrap_or_else(|error| panic!("内置插件源码数字正则编译失败: {error}"))
});
static RESOURCE_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\.(?:png|jpg|jpeg|webp|gif|ogg|m4a|mp3|wav|json|js|css|ttf|woff2?)$")
        .unwrap_or_else(|error| panic!("内置插件源码资源路径正则编译失败: {error}"))
});
static IDENTIFIER_OR_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[A-Za-z0-9_./:$-]+$")
        .unwrap_or_else(|error| panic!("内置插件源码标识符正则编译失败: {error}"))
});
static ENGLISH_ASSET_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:^|[\\/])(?:img|audio|fonts|icon|js|data)[\\/]")
        .unwrap_or_else(|error| panic!("内置英文资源目录正则编译失败: {error}"))
});
static ENGLISH_ASSET_EXTENSION_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"\.(?:png|jpe?g|webp|gif|ogg|m4a|mp3|wav|webm|json|js|css|html|ttf|otf|woff2?|rpgmvp|rpgmvo|rpgmvm)$",
    )
    .unwrap_or_else(|error| panic!("内置英文资源扩展名正则编译失败: {error}"))
});
static ENGLISH_THIS_EXPR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\bthis\s*(?:\.[A-Za-z_$]|\[)")
        .unwrap_or_else(|error| panic!("内置英文 this 表达式正则编译失败: {error}"))
});
static ENGLISH_CONSOLE_OR_MATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(?:console|math)\s*\.")
        .unwrap_or_else(|error| panic!("内置英文协议对象正则编译失败: {error}"))
});
static ENGLISH_VAR_DECL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b(?:var|let|const)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=")
        .unwrap_or_else(|error| panic!("内置英文变量声明正则编译失败: {error}"))
});
static ENGLISH_FUNCTION_DECL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\bfunction(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\(")
        .unwrap_or_else(|error| panic!("内置英文函数声明正则编译失败: {error}"))
});
static ENGLISH_RETURN_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\breturn\b.*(?:[;=<>+\-*/]|\b(?:true|false|null|undefined)\b)")
        .unwrap_or_else(|error| panic!("内置英文 return 协议正则编译失败: {error}"))
});
static ENGLISH_DOTTED_CALL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\s*\([^)]*\)")
        .unwrap_or_else(|error| panic!("内置英文链式调用正则编译失败: {error}"))
});
static ENGLISH_OPERATOR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[+\-*/<>=]=?|&&|\|\|")
        .unwrap_or_else(|error| panic!("内置英文运算符正则编译失败: {error}"))
});
static ENGLISH_WORD_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[A-Za-z]{2,}").unwrap_or_else(|error| panic!("内置英文单词正则编译失败: {error}"))
});
static ENGLISH_PATH_ONLY_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[A-Za-z0-9_./\\:-]+$")
        .unwrap_or_else(|error| panic!("内置英文路径正则编译失败: {error}"))
});
static ENGLISH_CAMEL_IDENTIFIER_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[a-z][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*$")
        .unwrap_or_else(|error| panic!("内置英文驼峰标识符正则编译失败: {error}"))
});
static ENGLISH_TEMPLATE_EXPR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\$\{[^}]+\}")
        .unwrap_or_else(|error| panic!("内置英文模板表达式正则编译失败: {error}"))
});
static ENGLISH_DOLLAR_EXPR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\$[A-Za-z_$][A-Za-z0-9_$]*(?:\s*(?:\.|\[|\())")
        .unwrap_or_else(|error| panic!("内置英文美元表达式正则编译失败: {error}"))
});
static ENGLISH_ARROW_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*(?:[{(]|[A-Za-z_$][A-Za-z0-9_$]*\s*[+*/<>=])")
        .unwrap_or_else(|error| panic!("内置英文箭头函数协议正则编译失败: {error}"))
});
static ENGLISH_OBJECT_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\{[^{}]*(?:\b(?:var|let|const|return|function|if|for|while)\b|[A-Za-z_$][A-Za-z0-9_$]*\s*:|[A-Za-z_$][A-Za-z0-9_$]*\s*=|;)[^{}]*\}")
        .unwrap_or_else(|error| panic!("内置英文对象协议正则编译失败: {error}"))
});
static ENGLISH_STATEMENT_PROTOCOL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:\b(?:return|var|let|const|throw|break|continue)\b|[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[[^\]]+\])*\s*(?:[-+*/]?=)|\b[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\s*\([^)]*\))[^.;!?]*;")
        .unwrap_or_else(|error| panic!("内置英文语句协议正则编译失败: {error}"))
});

fn default_source_text_exclusion_profile() -> String {
    "none".to_string()
}

#[derive(Debug, Serialize)]
struct ScopeGateOutput {
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
        let plugin_source_scan =
            scan_plugin_source_rule_candidates(&plugin_source_files, text_rules)?;
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
                "scanned_file_count": plugin_source_scan.scanned_file_count,
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
                "scanned_command_count": mv_virtual_namebox_scan.scanned_command_count,
                "scanned_file_count": mv_virtual_namebox_scan.scanned_file_count,
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
    let output = RuleCandidatesOutput {
        candidates,
        candidate_summary: summary_by_domain
            .into_iter()
            .map(|(domain, candidate_count)| CandidateGroupOutput {
                domain,
                candidate_count,
            })
            .collect(),
        scan_summary,
    };
    serde_json::to_string(&output).map_err(|error| format!("规则候选输出 JSON 序列化失败: {error}"))
}

fn scan_plugin_source_rule_candidates(
    files: &[PluginSourceFileInput],
    text_rules: RuleCandidateTextRules,
) -> Result<PluginSourceRuleCandidateScan, String> {
    let compiled_rules = compile_rule_candidate_text_rules(text_rules)?;
    let mut file_refs: Vec<&PluginSourceFileInput> = files.iter().collect();
    file_refs.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let file_scans = file_refs
        .par_iter()
        .map(|file| scan_plugin_source_rule_candidate_file(file, &compiled_rules))
        .collect::<Result<Vec<_>, String>>()?;
    let scanned_file_count = file_scans.iter().filter(|scan| !scan.syntax_error).count();
    let ignored_file_count = file_scans
        .iter()
        .filter(|scan| !scan.syntax_error && !scan.active)
        .count();
    let syntax_error_file_count = file_scans.iter().filter(|scan| scan.syntax_error).count();
    let syntax_errors = file_scans
        .iter()
        .filter(|scan| scan.syntax_error)
        .map(|scan| {
            json!({
                "file": scan.file_name,
                "active": scan.active,
                "syntax_error": "原生 AST 解析报告 JS 语法错误"
            })
        })
        .collect();
    let candidates = file_scans
        .into_iter()
        .flat_map(|scan| scan.candidates)
        .collect();
    Ok(PluginSourceRuleCandidateScan {
        candidates,
        scanned_file_count,
        ignored_file_count,
        syntax_error_file_count,
        syntax_errors,
    })
}

fn compile_rule_candidate_text_rules(
    text_rules: RuleCandidateTextRules,
) -> Result<CompiledRuleCandidateTextRules, String> {
    let source_text_exclusion_profile = match text_rules.source_text_exclusion_profile.as_str() {
        "none" | "english_protocol_noise" => text_rules.source_text_exclusion_profile,
        unknown => {
            return Err(format!("插件源码候选源文排除模式无效: {unknown}"));
        }
    };
    let control_rules = compile_rules(NativeTextRules {
        custom_placeholder_rules: text_rules.custom_placeholder_rules,
        structured_placeholder_rules: text_rules.structured_placeholder_rules,
        source_residual_allowed_chars: Vec::new(),
        source_residual_allowed_tail_chars: Vec::new(),
        source_residual_segment_pattern: r"[\s\S]+".to_string(),
        source_residual_label: "源文".to_string(),
        allowed_source_residual_terms: Vec::new(),
        source_residual_terms_ignore_case: false,
        source_residual_detection_profile: "japanese_strict".to_string(),
        english_source_copy_min_words: 4,
        english_source_copy_min_letters: 12,
        line_width_count_pattern: r"\S".to_string(),
        residual_escape_sequence_pattern: r"\\[nrt]".to_string(),
        long_text_line_width_limit: 999,
    })?;
    let source_text_required_re = Regex::new(&text_rules.source_text_required_pattern)
        .map_err(|error| format!("插件源码源文识别正则无效: {error}"))?;
    Ok(CompiledRuleCandidateTextRules {
        control_rules,
        source_text_required_re,
        source_text_exclusion_profile,
        strip_wrapping_punctuation_pairs: text_rules.strip_wrapping_punctuation_pairs,
    })
}

fn scan_plugin_source_rule_candidate_file(
    file: &PluginSourceFileInput,
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<PluginSourceFileRuleCandidateScan, String> {
    let scan = parse_javascript_string_spans(&file.source)
        .map_err(|error| format!("{} JS AST 解析失败: {error}", file.file_name))?;
    if scan.has_error {
        return Ok(PluginSourceFileRuleCandidateScan {
            file_name: file.file_name.clone(),
            candidates: Vec::new(),
            active: file.active,
            syntax_error: true,
        });
    }
    let file_hash = sha256_text(&file.source);
    let newline_indexes = collect_newline_indexes(&file.source);
    let mut candidates = Vec::new();
    for span in scan.spans {
        if let Some(candidate) = plugin_source_candidate_from_span(
            file,
            &span,
            &file_hash,
            &newline_indexes,
            text_rules,
        )? {
            candidates.push(candidate);
        }
    }
    Ok(PluginSourceFileRuleCandidateScan {
        file_name: file.file_name.clone(),
        candidates,
        active: file.active,
        syntax_error: false,
    })
}

fn plugin_source_candidate_from_span(
    file: &PluginSourceFileInput,
    span: &JavaScriptStringSpan,
    file_hash: &str,
    newline_indexes: &[usize],
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<Option<RuleCandidateOutput>, String> {
    let raw_text = file
        .source
        .get(span.content_start_byte_index..span.content_end_byte_index)
        .ok_or_else(|| format!("插件源码字符串范围无效: {}", file.file_name))?;
    let text = normalize_visible_text_for_extraction(&unescape_js_text(raw_text));
    if text.is_empty() || !should_translate_plugin_source_text(&text, text_rules)? {
        return Ok(None);
    }
    let api = span.ast_context.call_name.clone();
    let key = span.ast_context.property_key.clone();
    let structural_flags = plugin_source_text_structural_flags(&text);
    let confidence =
        plugin_source_candidate_confidence(&text, &api, &key, &span.ast_context, &structural_flags);
    let selector = candidate_selector_for_span(span.start_index, span.end_index, raw_text);
    let location_path = format!("js/plugins/{}/{}", file.file_name, selector);
    let line = line_number_for_index(newline_indexes, span.start_index);
    Ok(Some(RuleCandidateOutput {
        domain: "plugin_source".to_string(),
        location_path,
        rule_key: selector.clone(),
        original_text: text.clone(),
        source_file: file.file_name.clone(),
        file: Some(file.file_name.clone()),
        json_path: None,
        source_text: None,
        field_name: None,
        sibling_field_names: None,
        parent_object_keys: None,
        selector: Some(selector),
        text: Some(text),
        raw_text: Some(raw_text.to_string()),
        quote: Some(span.quote.clone()),
        line: Some(line),
        start_index: Some(span.start_index),
        end_index: Some(span.end_index),
        content_start_index: Some(span.content_start_index),
        content_end_index: Some(span.content_end_index),
        context: Some(plugin_source_candidate_context(&api, &key)),
        api: Some(api),
        key: Some(key),
        ast_context: Some(plugin_source_ast_context_json(&span.ast_context)),
        active: Some(file.active),
        confidence: Some(confidence),
        structural_flags: Some(structural_flags),
        file_hash: Some(file_hash.to_string()),
    }))
}

fn should_translate_plugin_source_text(
    text: &str,
    text_rules: &CompiledRuleCandidateTextRules,
) -> Result<bool, String> {
    let normalized_text =
        normalize_extraction_text(text, &text_rules.strip_wrapping_punctuation_pairs);
    if normalized_text.is_empty() {
        return Ok(false);
    }
    if text_rules.source_text_exclusion_profile == "english_protocol_noise"
        && is_english_protocol_noise_text(&normalized_text, &text_rules.control_rules)?
    {
        return Ok(false);
    }
    let detection_text =
        replace_control_sequences(&normalized_text, &text_rules.control_rules, |_span| {
            String::new()
        })?;
    if detection_text.is_empty() {
        return Ok(false);
    }
    Ok(text_rules.source_text_required_re.is_match(&detection_text))
}

fn normalize_extraction_text(text: &str, wrapping_pairs: &[(String, String)]) -> String {
    let mut normalized_text = text.trim().to_string();
    for (left, right) in wrapping_pairs {
        if normalized_text.starts_with(left) && normalized_text.ends_with(right) {
            normalized_text = normalized_text[left.len()..normalized_text.len() - right.len()]
                .trim()
                .to_string();
        }
    }
    normalized_text
}

fn is_english_protocol_noise_text(
    text: &str,
    control_rules: &CompiledRules,
) -> Result<bool, String> {
    let stripped = replace_control_sequences(text, control_rules, |_span| String::new())?
        .trim()
        .to_string();
    if stripped.is_empty() {
        return Ok(true);
    }
    let lowered = stripped.to_ascii_lowercase();
    if matches!(
        lowered.as_str(),
        "true" | "false" | "null" | "undefined" | "gamefont"
    ) {
        return Ok(true);
    }
    Ok(NUMBER_LIKE_RE.is_match(&stripped)
        || ENGLISH_ASSET_PATH_RE.is_match(&lowered)
        || ENGLISH_ASSET_EXTENSION_RE.is_match(&lowered)
        || ENGLISH_THIS_EXPR_RE.is_match(&stripped)
        || ENGLISH_CONSOLE_OR_MATH_RE.is_match(&stripped)
        || ENGLISH_VAR_DECL_RE.is_match(&stripped)
        || ENGLISH_FUNCTION_DECL_RE.is_match(&stripped)
        || ENGLISH_RETURN_PROTOCOL_RE.is_match(&stripped)
        || ENGLISH_DOTTED_CALL_RE.is_match(&stripped)
        || (ENGLISH_OPERATOR_RE.is_match(&stripped)
            && ENGLISH_WORD_RE.find_iter(&stripped).count() < 2)
        || ((stripped.contains('/') || stripped.contains('\\'))
            && ENGLISH_PATH_ONLY_RE.is_match(&stripped))
        || ENGLISH_CAMEL_IDENTIFIER_RE.is_match(&stripped)
        || looks_like_english_script_punctuation(&stripped))
}

fn looks_like_english_script_punctuation(text: &str) -> bool {
    ENGLISH_TEMPLATE_EXPR_RE.is_match(text)
        || ENGLISH_DOLLAR_EXPR_RE.is_match(text)
        || ENGLISH_ARROW_PROTOCOL_RE.is_match(text)
        || ENGLISH_OBJECT_PROTOCOL_RE.is_match(text)
        || ENGLISH_STATEMENT_PROTOCOL_RE.is_match(text)
}

fn plugin_source_text_structural_flags(text: &str) -> Vec<String> {
    let mut flags = Vec::new();
    let lowered_text = text.to_ascii_lowercase();
    if NUMBER_LIKE_RE.is_match(text) {
        flags.push("number_like".to_string());
    }
    if RESOURCE_PATH_RE.is_match(&lowered_text) {
        flags.push("resource_path_like".to_string());
    }
    if IDENTIFIER_OR_PATH_RE.is_match(text) && (text.contains('_') || text.contains('/')) {
        flags.push("identifier_or_path_like".to_string());
    }
    flags
}

fn plugin_source_candidate_confidence(
    text: &str,
    api: &str,
    key: &str,
    ast_context: &JavaScriptStringAstContext,
    structural_flags: &[String],
) -> String {
    if structural_flags
        .iter()
        .any(|flag| flag == "resource_path_like" || flag == "number_like")
    {
        return "weak".to_string();
    }
    if is_strong_plugin_source_call(api) || is_strong_plugin_source_key(key) {
        return "strong".to_string();
    }
    if !ast_context.return_function_name.is_empty()
        || !ast_context.assignment_name.is_empty()
        || !ast_context.property_path.is_empty()
    {
        return "medium".to_string();
    }
    if text.chars().count() >= 8
        && !structural_flags
            .iter()
            .any(|flag| flag == "identifier_or_path_like")
    {
        return "medium".to_string();
    }
    "weak".to_string()
}

fn is_strong_plugin_source_key(key: &str) -> bool {
    matches!(
        key,
        "body"
            | "caption"
            | "description"
            | "help"
            | "helpLines"
            | "label"
            | "longDescription"
            | "message"
            | "name"
            | "nickName"
            | "param1"
            | "param2"
            | "shortDescription"
            | "stanceDescription"
            | "text"
            | "title"
    )
}

fn is_strong_plugin_source_call(api: &str) -> bool {
    [
        "addCommand",
        "addText",
        "drawText",
        "drawTextEx",
        "setText",
        "$gameMessage.add",
    ]
    .iter()
    .any(|suffix| api == *suffix || api.ends_with(suffix))
}

fn plugin_source_candidate_context(api: &str, key: &str) -> String {
    if !api.is_empty() {
        return format!("call:{api}");
    }
    if !key.is_empty() {
        return format!("property:{key}");
    }
    "literal".to_string()
}

fn plugin_source_ast_context_json(context: &JavaScriptStringAstContext) -> Value {
    json!({
        "node_kind": context.node_kind,
        "property_key": context.property_key,
        "property_path": context.property_path,
        "call_name": context.call_name,
        "call_argument_index": context.call_argument_index,
        "return_function_name": context.return_function_name,
        "assignment_name": context.assignment_name
    })
}

fn collect_newline_indexes(source: &str) -> Vec<usize> {
    source
        .chars()
        .enumerate()
        .filter_map(|(index, char_value)| {
            if char_value == '\n' {
                Some(index)
            } else {
                None
            }
        })
        .collect()
}

fn line_number_for_index(newline_indexes: &[usize], index: usize) -> usize {
    newline_indexes.partition_point(|newline_index| *newline_index <= index) + 1
}

fn sha256_text(text: &str) -> String {
    let mut hasher = sha2::Sha256::new();
    hasher.update(text.as_bytes());
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn evaluate_scope_gate(payload: ScopeGatePayload) -> Result<String, String> {
    let active_paths: BTreeSet<String> = payload
        .entries
        .iter()
        .filter(|entry| entry.enters_translation)
        .map(|entry| entry.location_path.clone())
        .collect();
    let mut writable_location_paths: Vec<String> = payload
        .entries
        .iter()
        .filter(|entry| entry.enters_translation && entry.can_write_back)
        .map(|entry| entry.location_path.clone())
        .collect();
    writable_location_paths.sort();

    let translated_paths: BTreeSet<String> = payload.translated_paths.into_iter().collect();
    let quality_error_paths: BTreeSet<String> = payload.quality_error_paths.into_iter().collect();
    let writable_path_set: BTreeSet<String> = writable_location_paths.iter().cloned().collect();
    let missing_required_paths: Vec<String> = payload
        .required_paths
        .into_iter()
        .filter(|path| !active_paths.contains(path))
        .collect();
    let output = ScopeGateOutput {
        workflow_gate: WorkflowGateOutput {
            status: if missing_required_paths.is_empty() {
                "ok"
            } else {
                "error"
            },
            missing_required_paths,
        },
        quality_gate: QualityGateOutput {
            status: if quality_error_paths.is_empty() {
                "ok"
            } else {
                "error"
            },
            quality_error_count: quality_error_paths.len(),
        },
        pending_count: writable_path_set.difference(&translated_paths).count(),
        translated_count: active_paths.intersection(&translated_paths).count(),
        quality_error_count: quality_error_paths.len(),
        writable_location_paths,
    };
    serde_json::to_string(&output).map_err(|error| format!("范围门禁输出 JSON 序列化失败: {error}"))
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
    use super::{build_scope_index_impl, scan_rule_candidates_impl};
    use serde_json::{Value, json};

    #[test]
    fn build_scope_index_outputs_text_rows_and_summaries() {
        let payload = json!({
            "source_snapshot_fingerprint": "snapshot-v1",
            "rules_fingerprint": "rules-v1",
            "entries": [
                {
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

        assert_eq!(value["scope_summary"]["total_count"], json!(1));
        assert_eq!(
            value["text_index_rows"][0]["source_snapshot_fingerprint"],
            json!("snapshot-v1")
        );
    }

    #[test]
    fn build_scope_index_scans_system_title_and_event_command_text() {
        let payload = json!({
            "source_snapshot_fingerprint": "snapshot-v2",
            "rules_fingerprint": "rules-v2",
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
                                {"code": 0, "parameters": []}
                            ]
                        }
                    ]
                }
            ],
            "mv_virtual_namebox_actor_names": [],
            "mv_virtual_namebox_rules": [
                {
                    "rule_order": 0,
                    "rule_name": "standalone-colon",
                    "pattern_text": r"^(?P<speaker>案内人)：$",
                    "speaker_group": "speaker",
                    "body_group": "",
                    "speaker_policy": "translate",
                    "render_template": "{speaker}："
                }
            ]
        });

        let output =
            scan_rule_candidates_impl(&payload.to_string()).expect("MV 虚拟名字框候选扫描应成功");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");

        assert_eq!(
            value["candidate_summary"],
            json!([{"domain": "mv_virtual_namebox", "candidate_count": 1}])
        );
        assert_eq!(
            value["scan_summary"]["mv_virtual_namebox"]["candidate_details"],
            json!([
                {
                    "location_path": "CommonEvents.json/1/1",
                    "text": "案内人：",
                    "following_lines": ["本文です"]
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
                }
            ])
        );
    }
}
