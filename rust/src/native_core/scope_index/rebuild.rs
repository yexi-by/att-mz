//! Rust 直连冷重建 text index。
//!
//! 本入口服务生产 `rebuild-text-index` 冷路径：Python 只传配置和路径，
//! Rust 读取 DB/source snapshot/规则表、扫描游戏 data 文件，并在一个 SQLite
//! 事务中写入持久 text index。

use rayon::prelude::*;
use regex::Regex;
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::Digest;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use super::contracts::{
    ContractVersionsOutput, SourceBranchGateFact, current_contract_versions,
    source_branch_pass_fact,
};
use super::event_commands::{EventCommandDataFileInput, EventCommandRuleInput};
use super::fingerprint::stable_json_fingerprint;
use super::mv_virtual_namebox::{
    MvVirtualNameboxActorNameInput, MvVirtualNameboxDataFileInput, MvVirtualNameboxFactParts,
    MvVirtualNameboxFactPartsInput, MvVirtualNameboxFactRenderPart,
    build_mv_virtual_namebox_fact_parts, weak_split_colon_speaker_parts,
};
use super::nonstandard_data::{
    NonstandardDataFileInput, NonstandardDataManagedTextError, NonstandardDataTextRuleInput,
    collect_nonstandard_data_managed_texts,
};
use super::placeholders::{PlaceholderTextInput, scan_placeholder_rule_candidates};
use super::plugin_config::{PluginConfigInput, PluginConfigRuleInput};
use super::plugin_source::{
    PluginSourceFileInput, PluginSourceManagedTextError, PluginSourceTextRuleInput,
    collect_plugin_source_managed_texts,
};
use super::pool;
use super::storage;
use super::structured_placeholders::{
    StructuredPlaceholderTextInput, scan_structured_placeholder_rule_candidates,
};
use super::{RuleCandidateOutput, RuleCandidateTextRules};
use crate::native_core::rule_runtime::adapters::mv_virtual_namebox::compile_mv_virtual_namebox_pattern;
use crate::native_core::rule_runtime::engine::{
    Pcre2CaptureMatch, Pcre2Engine, Pcre2EngineConfig, Pcre2Pattern,
};
use crate::native_core::text_facts::{
    CURRENT_TEXT_FACT_CONTRACT_VERSION, TextFact, TextFactDomainPayload, TextFactRenderPart,
    TextFactScope, build_fact_id, domains,
};
use crate::native_core::write_back_plan::normalize_visible_text_for_extraction;

const TEXT_INDEX_PROMPT_CONTEXT_VERSION_KEY: &str = "prompt_context_version";
const PLUGIN_TEXT_RULE_DOMAIN: &str = "plugin_text";
const EVENT_COMMAND_TEXT_RULE_DOMAIN: &str = "event_command_text";
const NOTE_TAG_TEXT_RULE_DOMAIN: &str = "note_tag_text";
const MV_VIRTUAL_NAMEBOX_RULE_DOMAIN: &str = "mv_virtual_namebox";
const TEXT_INDEX_PLACEHOLDER_GATE_PREFIX: &str = "workflow_gate:placeholder_rules";
const TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX: &str =
    "workflow_gate:structured_placeholder_rules";

#[derive(Debug, Deserialize)]
struct RebuildStoragePayload {
    db_path: String,
    game_path: String,
    source_snapshot_fingerprint: Option<String>,
    rules_fingerprint: Option<String>,
    source_language: String,
    target_language: String,
    engine_kind: String,
    text_rules_setting: Value,
    rule_candidate_text_rules: RuleCandidateTextRules,
    event_command_scope_codes: Vec<i64>,
    source_text_required_pattern: String,
    created_at: String,
}

#[derive(Debug, Serialize)]
struct RebuildStorageOutput {
    contract_versions: ContractVersionsOutput,
    status: &'static str,
    index_status: &'static str,
    source_snapshot_fingerprint: String,
    rules_fingerprint: String,
    source_snapshot_hash: String,
    rule_hash: String,
    text_rules_hash: String,
    indexed_count: usize,
    text_fact_count: usize,
    render_part_count: usize,
    scope_key: String,
    scope_hash: String,
    text_fact_schema_version: i64,
    domain_fact_counts: BTreeMap<String, usize>,
    scan_file_count: usize,
    standard_data_file_count: usize,
    native_thread_count: usize,
    written_item_count: usize,
    internal_stage_timings: BTreeMap<String, u64>,
}

#[derive(Debug)]
struct RebuildContext {
    source_snapshot_fingerprint: String,
    rules_fingerprint: String,
    source_text_required_re: Pcre2Pattern,
    plugin_text_rules: Vec<PluginConfigRuleInput>,
    event_command_rules: Vec<EventCommandRuleInput>,
    note_tag_rules: Vec<NoteTagTextRuleInput>,
    plugin_source_rules: Vec<PluginSourceTextRuleInput>,
    rule_candidate_text_rules: RuleCandidateTextRules,
    nonstandard_data_rules: Vec<NonstandardDataTextRuleInput>,
    mv_virtual_namebox_rules: Vec<CompiledMvVirtualNameboxRule>,
    actor_names_by_id: BTreeMap<i64, String>,
    database_owner_terms_by_key: BTreeMap<String, Vec<String>>,
    system_owner_terms: Vec<String>,
    map_display_names_by_file: BTreeMap<String, String>,
}

#[derive(Debug)]
struct SourceLayout {
    data_dir: PathBuf,
    plugins_path: PathBuf,
    plugin_source_dir: PathBuf,
}

#[derive(Debug)]
struct ParsedDataFile {
    file_name: String,
    data: Value,
}

#[derive(Clone, Debug, Serialize)]
struct DirectTextIndexRow {
    location_path: String,
    item_type: String,
    role: Option<String>,
    original_lines: Vec<String>,
    source_line_paths: Vec<String>,
    source_type: String,
    source_file: String,
    writable: bool,
    source_snapshot_fingerprint: String,
    rules_fingerprint: String,
    locator_json: String,
    fact_raw_text: Option<String>,
    fact_visible_text: Option<String>,
    fact_selector: Option<String>,
    fact_domain_payload_json: Option<String>,
}

#[derive(Debug, Serialize)]
struct DirectScopeSummary {
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
}

#[derive(Debug, Serialize)]
struct DirectDomainSummary {
    domain: String,
    item_count: usize,
    active_count: usize,
    writable_count: usize,
    unwritable_count: usize,
    inactive_rule_hit_count: usize,
}

struct DirectTextFactStoragePayload {
    text_facts: Vec<TextFact>,
    render_parts: Vec<TextFactRenderPart>,
    domain_payloads: Vec<TextFactDomainPayload>,
    domain_fact_counts: BTreeMap<String, usize>,
}

#[derive(Debug)]
struct PendingLongText {
    location_path: String,
    role: String,
    original_lines: Vec<String>,
    source_line_paths: Vec<String>,
}

#[derive(Debug)]
struct RawMvVirtualNameboxRule {
    rule_name: String,
    pattern_text: String,
    speaker_group: String,
    body_group: String,
    speaker_policy: String,
    render_template: String,
}

#[derive(Debug)]
struct CompiledMvVirtualNameboxRule {
    rule_name: String,
    pattern: Pcre2Pattern,
    speaker_group: String,
    body_group: String,
    speaker_policy: String,
    render_template: String,
}

#[derive(Debug)]
struct NoteTagTextRuleInput {
    file_name: String,
    tag_names: BTreeSet<String>,
}

#[derive(Debug)]
struct ParsedMvVirtualSpeaker {
    speaker: String,
    source_speaker: String,
    body_text: String,
    rule_name: String,
    speaker_policy: String,
    fact_parts: MvVirtualNameboxFactParts,
}

pub(crate) fn rebuild_scope_index_storage_impl(payload_json: &str) -> Result<String, String> {
    let payload: RebuildStoragePayload = serde_json::from_str(payload_json).map_err(|error| {
        structured_error(
            "scope_index_rebuild_payload_invalid",
            format!("Scope/Index rebuild 输入 JSON 解析失败: {error}"),
        )
    })?;
    let connection = open_connection_readonly(Path::new(&payload.db_path))?;
    let source_snapshot_fingerprint = match &payload.source_snapshot_fingerprint {
        Some(fingerprint) => fingerprint.clone(),
        None => read_source_snapshot_fingerprint(&connection)?,
    };
    let rules_fingerprint = match &payload.rules_fingerprint {
        Some(fingerprint) => fingerprint.clone(),
        None => read_rules_fingerprint(&connection, &payload)?,
    };
    let plugin_text_rules = read_plugin_text_rule_records(&connection)?;
    let event_command_rules = read_event_command_text_rule_inputs(&connection)?;
    let note_tag_rules = read_note_tag_text_rule_inputs(&connection)?;
    let plugin_source_rules = read_plugin_source_text_rule_inputs(&connection)?;
    let mv_virtual_namebox_rules =
        compile_mv_virtual_namebox_rules(read_mv_virtual_namebox_rule_inputs(&connection)?)?;
    let nonstandard_data_rules = read_nonstandard_data_text_rule_inputs(&connection)?;
    drop(connection);

    let source_text_required_re = Pcre2Engine::compile(
        &payload.source_text_required_pattern,
        &Pcre2EngineConfig::default_runtime(),
    )
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_text_rule_invalid",
            format!("源文识别 PCRE2 pattern 无效: {}", error.message),
        )
    })?;
    let context = RebuildContext {
        source_snapshot_fingerprint,
        rules_fingerprint,
        source_text_required_re,
        plugin_text_rules,
        event_command_rules,
        note_tag_rules,
        plugin_source_rules,
        rule_candidate_text_rules: rule_candidate_text_rules(&payload),
        nonstandard_data_rules,
        mv_virtual_namebox_rules,
        actor_names_by_id: BTreeMap::new(),
        database_owner_terms_by_key: BTreeMap::new(),
        system_owner_terms: Vec::new(),
        map_display_names_by_file: BTreeMap::new(),
    };
    pool::run_with_optional_pool(|| rebuild_with_context(payload, context))?
}

fn rebuild_with_context(
    payload: RebuildStoragePayload,
    mut context: RebuildContext,
) -> Result<String, String> {
    let mut internal_stage_timings = BTreeMap::new();

    let stage_started = Instant::now();
    let layout = resolve_source_layout(Path::new(&payload.game_path))?;
    record_stage(
        &mut internal_stage_timings,
        "resolve_source_layout",
        stage_started,
    );
    let stage_started = Instant::now();
    let data_files = read_standard_data_files(&layout.data_dir)?;
    record_stage(
        &mut internal_stage_timings,
        "read_standard_data_files",
        stage_started,
    );
    let stage_started = Instant::now();
    let nonstandard_data_files =
        read_nonstandard_data_files(&layout.data_dir, &context.nonstandard_data_rules)?;
    record_stage(
        &mut internal_stage_timings,
        "read_nonstandard_data_files",
        stage_started,
    );
    let stage_started = Instant::now();
    context.actor_names_by_id = actor_names_by_id(&data_files);
    context.database_owner_terms_by_key = database_owner_terms_by_key(&data_files);
    context.system_owner_terms = system_owner_terms(&data_files);
    context.map_display_names_by_file = map_display_names_by_file(&data_files);
    record_stage(
        &mut internal_stage_timings,
        "derive_standard_data_context",
        stage_started,
    );
    let stage_started = Instant::now();
    let plugin_config_inputs = read_plugin_config_inputs(&layout.plugins_path)?;
    record_stage(
        &mut internal_stage_timings,
        "read_plugin_config",
        stage_started,
    );
    let stage_started = Instant::now();
    let (fresh_plugin_text_rules, stale_plugin_rule_count) = if context.plugin_text_rules.is_empty()
    {
        (Vec::new(), 0usize)
    } else {
        let (fresh_plugin_text_rules, stale_plugin_rule_count) =
            filter_fresh_plugin_text_rules(&context.plugin_text_rules, &plugin_config_inputs)?;
        (fresh_plugin_text_rules, stale_plugin_rule_count)
    };
    record_stage(
        &mut internal_stage_timings,
        "filter_plugin_config_rules",
        stage_started,
    );
    let stage_started = Instant::now();
    let plugin_source_files = if context.plugin_source_rules.is_empty() {
        Vec::new()
    } else {
        read_plugin_source_file_inputs(
            &layout.plugin_source_dir,
            &plugin_config_inputs,
            &context.plugin_source_rules,
        )?
    };
    record_stage(
        &mut internal_stage_timings,
        "read_plugin_source_files",
        stage_started,
    );
    let stage_started = Instant::now();
    let native_thread_count = pool::read_configured_thread_count()
        .map(|thread_count| thread_count.unwrap_or_else(rayon::current_num_threads))
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_thread_config_invalid",
                format!("读取 Rust 线程配置失败: {error}"),
            )
        })?;
    record_stage(
        &mut internal_stage_timings,
        "read_thread_config",
        stage_started,
    );
    let stage_started = Instant::now();
    let mut rows = scan_text_index_rows(&data_files, &context)?;
    record_stage(
        &mut internal_stage_timings,
        "scan_standard_data",
        stage_started,
    );
    let stage_started = Instant::now();
    rows.extend(scan_nonstandard_data_rows(
        &nonstandard_data_files,
        &context,
    )?);
    record_stage(
        &mut internal_stage_timings,
        "scan_nonstandard_data",
        stage_started,
    );
    let stage_started = Instant::now();
    rows.extend(scan_plugin_parameter_rows(
        &plugin_config_inputs,
        &fresh_plugin_text_rules,
        &context,
    )?);
    record_stage(
        &mut internal_stage_timings,
        "scan_plugin_config",
        stage_started,
    );
    let stage_started = Instant::now();
    rows.extend(scan_plugin_source_rows(&plugin_source_files, &context)?);
    record_stage(
        &mut internal_stage_timings,
        "scan_plugin_source",
        stage_started,
    );
    let stage_started = Instant::now();
    rows.extend(scan_event_command_rule_rows(&data_files, &context)?);
    record_stage(
        &mut internal_stage_timings,
        "scan_event_commands",
        stage_started,
    );
    let stage_started = Instant::now();
    rows.extend(scan_note_tag_rows(&data_files, &context)?);
    record_stage(&mut internal_stage_timings, "scan_note_tags", stage_started);
    let stage_started = Instant::now();
    let mut fact_rows = rows;
    fact_rows.sort_by(|left, right| {
        left.location_path
            .cmp(&right.location_path)
            .then(left.source_type.cmp(&right.source_type))
            .then(left.fact_selector.cmp(&right.fact_selector))
            .then(left.original_lines.cmp(&right.original_lines))
    });
    let warm_index_rows = warm_index_rows_from_fact_rows(&fact_rows);
    record_stage(
        &mut internal_stage_timings,
        "sort_dedup_rows",
        stage_started,
    );
    let stage_started = Instant::now();
    let domain_summary = domain_summary_from_rows(&warm_index_rows);
    let item_count = warm_index_rows.len();
    let scope_summary = DirectScopeSummary {
        total_count: item_count,
        active_count: item_count,
        writable_count: warm_index_rows.iter().filter(|row| row.writable).count(),
        unwritable_count: warm_index_rows.iter().filter(|row| !row.writable).count(),
        stale_rule_count: stale_plugin_rule_count,
        native_thread_count,
    };
    record_stage(
        &mut internal_stage_timings,
        "build_summaries",
        stage_started,
    );

    let source_snapshot_fingerprint = context.source_snapshot_fingerprint.clone();
    let rules_fingerprint = context.rules_fingerprint.clone();
    let stage_started = Instant::now();
    let workflow_gate_scope_hashes = build_workflow_gate_scope_hashes(
        &payload,
        &context,
        &data_files,
        &plugin_config_inputs,
        &warm_index_rows,
        &mut internal_stage_timings,
    )?;
    let text_rules_hash = rebuild_text_rules_hash(&payload)?;
    let text_fact_scope = TextFactScope::from_hashes(
        source_snapshot_fingerprint.clone(),
        rules_fingerprint.clone(),
        text_rules_hash.clone(),
        payload.created_at.clone(),
    );
    let workflow_gate_facts =
        build_workflow_gate_facts(&warm_index_rows, &text_fact_scope.scope_hash);
    record_stage(
        &mut internal_stage_timings,
        "build_workflow_gate_metadata",
        stage_started,
    );
    let contract_versions = current_contract_versions();
    let stage_started = Instant::now();
    let text_fact_payload = build_text_fact_storage_payload_with_context(
        &fact_rows,
        &text_fact_scope,
        &data_files,
        Some(&context),
    )?;
    let write_payload = storage::WriteStoragePayload {
        db_path: payload.db_path,
        metadata: storage::TextIndexMetadataInput {
            source_snapshot_fingerprint: source_snapshot_fingerprint.clone(),
            rules_fingerprint: rules_fingerprint.clone(),
            text_rules_hash: Some(text_rules_hash),
            item_count,
            workflow_gate_scope_hashes,
            workflow_gate_facts,
            rust_contract_version: contract_versions.rust_scope_facts,
            parser_contract_version: contract_versions.parser,
            source_branch_contract_version: contract_versions.source_branch,
            text_fact_schema_version: contract_versions.text_fact_schema,
            created_at: payload.created_at,
        },
        text_index_rows: warm_index_rows
            .into_iter()
            .map(|row| {
                let text_fact_identity =
                    text_index_row_fact_identity(&row, &data_files, Some(&context))?;
                Ok(storage::TextIndexRowInput {
                    location_path: row.location_path,
                    item_type: row.item_type,
                    role: text_fact_identity.role,
                    original_lines: row.original_lines,
                    text_fact_raw_text: text_fact_identity.raw_text,
                    source_line_paths: row.source_line_paths,
                    source_type: row.source_type,
                    source_file: row.source_file,
                    writable: row.writable,
                    source_snapshot_fingerprint: row.source_snapshot_fingerprint,
                    rules_fingerprint: row.rules_fingerprint,
                    locator_json: row.locator_json,
                })
            })
            .collect::<Result<Vec<_>, String>>()?,
        scope_summary: storage::ScopeSummaryInput {
            total_count: scope_summary.total_count,
            active_count: scope_summary.active_count,
            writable_count: scope_summary.writable_count,
            unwritable_count: scope_summary.unwritable_count,
            stale_rule_count: scope_summary.stale_rule_count,
            native_thread_count: scope_summary.native_thread_count,
        },
        domain_summary: domain_summary
            .into_iter()
            .map(|row| storage::DomainSummaryInput {
                domain: row.domain,
                item_count: row.item_count,
                active_count: row.active_count,
                writable_count: row.writable_count,
                unwritable_count: row.unwritable_count,
                inactive_rule_hit_count: row.inactive_rule_hit_count,
            })
            .collect(),
        rule_hit_summary: Vec::new(),
        text_fact_scope: Some(text_fact_scope.clone()),
        text_facts: text_fact_payload.text_facts,
        text_fact_render_parts: text_fact_payload.render_parts,
        text_fact_domain_payloads: text_fact_payload.domain_payloads,
    };
    record_stage(
        &mut internal_stage_timings,
        "build_write_payload",
        stage_started,
    );
    let stage_started = Instant::now();
    let write_output = storage::write_scope_index_storage_direct(&write_payload)?;
    record_stage(&mut internal_stage_timings, "write_storage", stage_started);
    let written_item_count = write_output.written_item_count;
    serialize_output(&RebuildStorageOutput {
        contract_versions: current_contract_versions(),
        status: "ok",
        index_status: "rebuilt",
        source_snapshot_fingerprint,
        rules_fingerprint,
        source_snapshot_hash: text_fact_scope.source_snapshot_hash,
        rule_hash: text_fact_scope.rule_hash,
        text_rules_hash: text_fact_scope.text_rules_hash,
        indexed_count: written_item_count,
        text_fact_count: write_output.text_fact_count,
        render_part_count: write_output.render_part_count,
        scope_key: write_output.scope_key,
        scope_hash: write_output.scope_hash,
        text_fact_schema_version: write_output.text_fact_schema_version,
        domain_fact_counts: text_fact_payload.domain_fact_counts,
        scan_file_count: data_files.len(),
        standard_data_file_count: data_files.len(),
        native_thread_count,
        written_item_count,
        internal_stage_timings,
    })
}

fn record_stage(stage_timings: &mut BTreeMap<String, u64>, stage_name: &str, started: Instant) {
    let elapsed_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    stage_timings.insert(stage_name.to_string(), elapsed_ms);
}

fn build_workflow_gate_scope_hashes(
    payload: &RebuildStoragePayload,
    context: &RebuildContext,
    data_files: &[ParsedDataFile],
    plugin_config_inputs: &[PluginConfigInput],
    rows: &[DirectTextIndexRow],
    stage_timings: &mut BTreeMap<String, u64>,
) -> Result<BTreeMap<String, String>, String> {
    let mut metadata = BTreeMap::new();

    if context.plugin_text_rules.is_empty() {
        let stage_started = Instant::now();
        let plugins_payload = Value::Array(
            plugin_config_inputs
                .iter()
                .map(|input| input.plugin.clone())
                .collect(),
        );
        metadata.insert(
            PLUGIN_TEXT_RULE_DOMAIN.to_string(),
            stable_json_fingerprint(&plugins_payload)?,
        );
        record_stage(
            stage_timings,
            "workflow_gate_plugin_config_hash",
            stage_started,
        );
    }

    if payload.event_command_scope_codes.is_empty() {
        return Err(structured_error(
            "scope_index_rebuild_event_command_codes_invalid",
            "事件指令范围编码为空，请检查按引擎配置".to_string(),
        ));
    }
    if context.event_command_rules.is_empty() {
        let stage_started = Instant::now();
        let event_data_files = event_command_data_file_inputs(data_files);
        let event_payload = super::event_commands::event_command_scope_hash_payload(
            &event_data_files,
            &payload.event_command_scope_codes,
        );
        metadata.insert(
            EVENT_COMMAND_TEXT_RULE_DOMAIN.to_string(),
            stable_json_fingerprint(&event_payload)?,
        );
        record_stage(
            stage_timings,
            "workflow_gate_event_command_hash",
            stage_started,
        );
    }

    if context.note_tag_rules.is_empty() {
        let stage_started = Instant::now();
        let note_data_files = note_tag_data_file_refs(data_files);
        let note_scan = super::note_tags::scan_note_tag_rule_candidates_from_refs(
            &note_data_files,
            context.rule_candidate_text_rules.clone(),
        )?;
        metadata.insert(
            NOTE_TAG_TEXT_RULE_DOMAIN.to_string(),
            stable_json_fingerprint(&to_json_value(&note_scan.candidates, "Note 标签候选")?)?,
        );
        record_stage(stage_timings, "workflow_gate_note_tag_hash", stage_started);
    }

    if payload.engine_kind == "mv" && context.mv_virtual_namebox_rules.is_empty() {
        let stage_started = Instant::now();
        let mv_data_files = mv_virtual_namebox_data_file_inputs(data_files);
        let actor_names = context
            .actor_names_by_id
            .iter()
            .map(|(actor_id, name)| MvVirtualNameboxActorNameInput {
                actor_id: *actor_id,
                name: name.clone(),
            })
            .collect::<Vec<_>>();
        let mv_scan = super::mv_virtual_namebox::scan_mv_virtual_namebox_rule_candidates(
            &mv_data_files,
            &actor_names,
            &[],
        )?;
        metadata.insert(
            MV_VIRTUAL_NAMEBOX_RULE_DOMAIN.to_string(),
            mv_scan.scope_hash,
        );
        record_stage(
            stage_timings,
            "workflow_gate_mv_virtual_namebox_hash",
            stage_started,
        );
    }

    let stage_started = Instant::now();
    let placeholder_texts = placeholder_text_inputs(rows);
    let placeholder_scan = scan_placeholder_rule_candidates(
        &placeholder_texts,
        context.rule_candidate_text_rules.clone(),
    )?;
    insert_candidate_coverage_metadata(
        &mut metadata,
        TEXT_INDEX_PLACEHOLDER_GATE_PREFIX,
        context
            .rule_candidate_text_rules
            .custom_placeholder_rules
            .len(),
        &to_json_value(&placeholder_scan.candidates, "普通占位符候选")?,
        placeholder_scan.candidates.len(),
        placeholder_scan
            .candidates
            .iter()
            .filter(|candidate| candidate.covered)
            .count(),
    )?;
    record_stage(
        stage_timings,
        "workflow_gate_placeholder_hash",
        stage_started,
    );

    let stage_started = Instant::now();
    let structured_placeholder_texts = structured_placeholder_text_inputs(rows);
    let structured_scan = scan_structured_placeholder_rule_candidates(
        &structured_placeholder_texts,
        context.rule_candidate_text_rules.clone(),
    )?;
    insert_candidate_coverage_metadata(
        &mut metadata,
        TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX,
        context
            .rule_candidate_text_rules
            .structured_placeholder_rules
            .len(),
        &to_json_value(&structured_scan.candidates, "结构化占位符候选")?,
        structured_scan.candidates.len(),
        structured_scan
            .candidates
            .iter()
            .filter(|candidate| candidate.covered)
            .count(),
    )?;
    record_stage(
        stage_timings,
        "workflow_gate_structured_placeholder_hash",
        stage_started,
    );

    Ok(metadata)
}

fn build_workflow_gate_facts(
    rows: &[DirectTextIndexRow],
    text_fact_scope_hash: &str,
) -> BTreeMap<String, SourceBranchGateFact> {
    let mut gate_facts = BTreeMap::new();
    gate_facts.insert(
        "plugin_source_text".to_string(),
        source_branch_pass_fact(
            "plugin_source_text",
            source_branch_scope_hash("plugin_source_text", rows, text_fact_scope_hash),
        ),
    );
    gate_facts.insert(
        "nonstandard_data".to_string(),
        source_branch_pass_fact(
            "nonstandard_data",
            source_branch_scope_hash("nonstandard_data", rows, text_fact_scope_hash),
        ),
    );
    gate_facts
}

fn source_branch_scope_hash(
    source_branch: &str,
    rows: &[DirectTextIndexRow],
    text_fact_scope_hash: &str,
) -> String {
    let mut parts = vec![
        format!("text_fact_scope_hash={text_fact_scope_hash}"),
        format!("source_branch={source_branch}"),
    ];
    for row in rows
        .iter()
        .filter(|row| row_belongs_to_source_branch(row, source_branch))
    {
        parts.push(format!(
            "{}\u{1e}{}\u{1e}{}\u{1e}{}\u{1e}{}\u{1e}{}\u{1e}{}",
            row.location_path,
            row.source_type,
            row.source_file,
            row.fact_selector.as_deref().unwrap_or(""),
            row.source_snapshot_fingerprint,
            row.rules_fingerprint,
            row.original_lines.join("\u{1f}")
        ));
    }
    sha256_text(&parts.join("\n"))
}

fn row_belongs_to_source_branch(row: &DirectTextIndexRow, source_branch: &str) -> bool {
    match source_branch {
        "plugin_source_text" => text_fact_domain_for_row(row) == domains::PLUGIN_SOURCE,
        "nonstandard_data" => text_fact_domain_for_row(row) == domains::NONSTANDARD_DATA,
        _ => false,
    }
}

fn insert_candidate_coverage_metadata(
    metadata: &mut BTreeMap<String, String>,
    prefix: &str,
    rule_count: usize,
    candidates: &Value,
    candidate_count: usize,
    covered_count: usize,
) -> Result<(), String> {
    metadata.insert(
        format!("{prefix}:scope_hash"),
        stable_json_fingerprint(candidates)?,
    );
    metadata.insert(format!("{prefix}:rule_count"), rule_count.to_string());
    metadata.insert(
        format!("{prefix}:candidate_count"),
        candidate_count.to_string(),
    );
    metadata.insert(format!("{prefix}:covered_count"), covered_count.to_string());
    metadata.insert(
        format!("{prefix}:uncovered_count"),
        (candidate_count - covered_count).to_string(),
    );
    Ok(())
}

fn to_json_value<T: Serialize>(value: &T, label: &str) -> Result<Value, String> {
    serde_json::to_value(value).map_err(|error| {
        structured_error(
            "scope_index_rebuild_workflow_gate_metadata_failed",
            format!("{label} JSON 序列化失败: {error}"),
        )
    })
}

fn note_tag_data_file_refs(data_files: &[ParsedDataFile]) -> Vec<(&str, &Value)> {
    data_files
        .iter()
        .map(|file| (file.file_name.as_str(), &file.data))
        .collect()
}

fn event_command_data_file_inputs(data_files: &[ParsedDataFile]) -> Vec<EventCommandDataFileInput> {
    data_files
        .iter()
        .map(|file| EventCommandDataFileInput {
            file_name: file.file_name.clone(),
            data: file.data.clone(),
        })
        .collect()
}

fn mv_virtual_namebox_data_file_inputs(
    data_files: &[ParsedDataFile],
) -> Vec<MvVirtualNameboxDataFileInput> {
    data_files
        .iter()
        .map(|file| MvVirtualNameboxDataFileInput {
            file_name: file.file_name.clone(),
            data: file.data.clone(),
        })
        .collect()
}

fn placeholder_text_inputs(rows: &[DirectTextIndexRow]) -> Vec<PlaceholderTextInput> {
    rows.iter()
        .flat_map(|row| {
            row.original_lines
                .iter()
                .enumerate()
                .filter(|(_line_index, text)| text.contains('\\'))
                .map(|(line_index, text)| PlaceholderTextInput {
                    source_name: format!("{}#{line_index}", row.location_path),
                    text: text.clone(),
                })
        })
        .collect()
}

fn structured_placeholder_text_inputs(
    rows: &[DirectTextIndexRow],
) -> Vec<StructuredPlaceholderTextInput> {
    rows.iter()
        .flat_map(|row| {
            row.original_lines
                .iter()
                .enumerate()
                .filter(|(_line_index, text)| may_contain_structured_shell_candidate(text))
                .map(|(line_index, text)| StructuredPlaceholderTextInput {
                    location_path: row.location_path.clone(),
                    line_number: line_index + 1,
                    text: text.clone(),
                })
        })
        .collect()
}

fn may_contain_structured_shell_candidate(text: &str) -> bool {
    (text.contains('<') && text.contains('>')) || (text.contains('【') && text.contains('】'))
}

fn open_connection_readonly(db_path: &Path) -> Result<Connection, String> {
    Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|error| {
        structured_error(
            "scope_index_rebuild_db_open_failed",
            format!("只读打开数据库失败 {}: {error}", db_path.display()),
        )
    })
}

fn read_source_snapshot_fingerprint(connection: &Connection) -> Result<String, String> {
    let mut statement = connection
        .prepare(
            "SELECT relative_path, sha256, byte_size \
             FROM source_snapshot_files \
             ORDER BY relative_path",
        )
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_source_snapshot_unreadable",
                format!("读取可信源快照 manifest 失败: {error}"),
            )
        })?;
    let records = statement
        .query_map([], |row| {
            Ok(json!({
                "relative_path": row.get::<_, String>(0)?,
                "sha256": row.get::<_, String>(1)?,
                "byte_size": row.get::<_, i64>(2)?,
            }))
        })
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_source_snapshot_unreadable",
                format!("读取可信源快照 manifest 失败: {error}"),
            )
        })?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_source_snapshot_unreadable",
                format!("解析可信源快照 manifest 失败: {error}"),
            )
        })?;
    stable_json_fingerprint(&Value::Array(records))
}

fn read_rules_fingerprint(
    connection: &Connection,
    payload: &RebuildStoragePayload,
) -> Result<String, String> {
    let mut root = serde_json::Map::new();
    root.insert(
        "source_language".to_string(),
        Value::String(payload.source_language.clone()),
    );
    root.insert(
        "target_language".to_string(),
        Value::String(payload.target_language.clone()),
    );
    root.insert(
        TEXT_INDEX_PROMPT_CONTEXT_VERSION_KEY.to_string(),
        Value::String(
            payload
                .text_rules_setting
                .get(TEXT_INDEX_PROMPT_CONTEXT_VERSION_KEY)
                .and_then(Value::as_str)
                .unwrap_or("display_name_owner_system_terms_v3")
                .to_string(),
        ),
    );
    root.insert(
        "text_rules".to_string(),
        sanitized_text_rules_setting(&payload.text_rules_setting),
    );
    root.insert(
        "plugin_text_rules".to_string(),
        read_plugin_text_rules(connection)?,
    );
    root.insert(
        "plugin_source_text_rules".to_string(),
        read_plugin_source_text_rules(connection)?,
    );
    root.insert(
        "event_command_text_rules".to_string(),
        read_event_command_text_rules(connection)?,
    );
    root.insert(
        "note_tag_text_rules".to_string(),
        read_note_tag_text_rules(connection)?,
    );
    root.insert(
        "nonstandard_data_text_rules".to_string(),
        read_nonstandard_data_text_rules(connection)?,
    );
    root.insert(
        "placeholder_rules".to_string(),
        read_placeholder_rules(connection)?,
    );
    root.insert(
        "structured_placeholder_rules".to_string(),
        read_structured_placeholder_rules(connection)?,
    );
    root.insert(
        "mv_virtual_namebox_rules".to_string(),
        read_mv_virtual_namebox_rules(connection)?,
    );
    stable_json_fingerprint(&Value::Object(root))
}

fn sanitized_text_rules_setting(raw_setting: &Value) -> Value {
    let mut setting = raw_setting.clone();
    if let Value::Object(object) = &mut setting {
        object.remove(TEXT_INDEX_PROMPT_CONTEXT_VERSION_KEY);
    }
    setting
}

fn rebuild_text_rules_hash(payload: &RebuildStoragePayload) -> Result<String, String> {
    stable_json_fingerprint(&rebuild_text_rules_hash_payload(payload))
}

fn rebuild_text_rules_hash_payload(payload: &RebuildStoragePayload) -> Value {
    json!({
        "engine_kind": payload.engine_kind,
        "event_command_scope_codes": payload.event_command_scope_codes,
        "rule_candidate_text_rules": rule_candidate_text_rules_value(&payload.rule_candidate_text_rules),
        "source_text_required_pattern": payload.source_text_required_pattern,
        "text_rules_setting": payload.text_rules_setting,
    })
}

fn rule_candidate_text_rules_value(text_rules: &RuleCandidateTextRules) -> Value {
    let custom_placeholder_rules = text_rules
        .custom_placeholder_rules
        .iter()
        .map(|rule| {
            json!({
                "pattern_text": rule.pattern_text,
                "placeholder_template": rule.placeholder_template,
            })
        })
        .collect::<Vec<_>>();
    let structured_placeholder_rules = text_rules
        .structured_placeholder_rules
        .iter()
        .map(|rule| {
            let protected_groups = rule
                .protected_groups
                .iter()
                .map(|(key, value)| (key.clone(), Value::String(value.clone())))
                .collect::<serde_json::Map<_, _>>();
            json!({
                "rule_name": rule.rule_name,
                "rule_type": rule.rule_type,
                "pattern_text": rule.pattern_text,
                "translatable_group": rule.translatable_group,
                "protected_groups": Value::Object(protected_groups),
            })
        })
        .collect::<Vec<_>>();
    json!({
        "custom_placeholder_rules": custom_placeholder_rules,
        "structured_placeholder_rules": structured_placeholder_rules,
        "strip_wrapping_punctuation_pairs": text_rules.strip_wrapping_punctuation_pairs,
        "source_text_required_pattern": text_rules.source_text_required_pattern,
        "source_text_exclusion_profile": text_rules.source_text_exclusion_profile,
    })
}

fn rule_candidate_text_rules(payload: &RebuildStoragePayload) -> RuleCandidateTextRules {
    payload.rule_candidate_text_rules.clone()
}

#[derive(Debug)]
struct RuntimeRulePayload {
    rule_order: i64,
    matcher_value: String,
    payload_json: Value,
}

fn read_runtime_rule_payloads(
    connection: &Connection,
    domain: &str,
    error_label: &str,
) -> Result<Vec<RuntimeRulePayload>, String> {
    let mut statement = connection
        .prepare(
            "SELECT rule_order, matcher_value, payload_json \
             FROM rules \
             WHERE domain = ?1 AND enabled = 1 \
             ORDER BY rule_order, rule_id",
        )
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("{error_label}: {error}"),
            )
        })?;
    let rows = statement
        .query_map([domain], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("{error_label}: {error}"),
            )
        })?;
    let mut rules = Vec::new();
    for row in rows {
        let (rule_order, matcher_value, payload_text) = row.map_err(|error| {
            structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("{error_label}: {error}"),
            )
        })?;
        let payload_json = serde_json::from_str::<Value>(&payload_text).map_err(|error| {
            structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("{error_label}: payload_json 无效: {error}"),
            )
        })?;
        if !payload_json.is_object() {
            return Err(structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("{error_label}: payload_json 必须是对象"),
            ));
        }
        rules.push(RuntimeRulePayload {
            rule_order,
            matcher_value,
            payload_json,
        });
    }
    Ok(rules)
}

fn payload_string(payload: &Value, field: &str, error_label: &str) -> Result<String, String> {
    payload
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| {
            structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("{error_label}: payload_json.{field} 必须是字符串"),
            )
        })
}

fn payload_optional_string(payload: &Value, field: &str) -> Option<String> {
    payload
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn payload_i64(payload: &Value, field: &str, error_label: &str) -> Result<i64, String> {
    payload.get(field).and_then(Value::as_i64).ok_or_else(|| {
        structured_error(
            "scope_index_rebuild_rules_unreadable",
            format!("{error_label}: payload_json.{field} 必须是整数"),
        )
    })
}

fn payload_array(payload: &Value, field: &str) -> Value {
    payload.get(field).cloned().unwrap_or_else(|| json!([]))
}

fn payload_object(payload: &Value, field: &str) -> Value {
    payload.get(field).cloned().unwrap_or_else(|| json!({}))
}

fn read_plugin_text_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(connection, "plugin_config", "读取插件规则失败")?;
    let mut grouped: BTreeMap<(i64, String, String), Vec<String>> = BTreeMap::new();
    for row in rows {
        let plugin_index = payload_i64(&row.payload_json, "plugin_index", "解析插件规则失败")?;
        let plugin_name = payload_string(&row.payload_json, "plugin_name", "解析插件规则失败")?;
        let plugin_hash =
            payload_optional_string(&row.payload_json, "plugin_hash").unwrap_or_default();
        let path_template =
            payload_optional_string(&row.payload_json, "path").unwrap_or(row.matcher_value);
        grouped
            .entry((plugin_index, plugin_name, plugin_hash))
            .or_default()
            .push(path_template);
    }
    Ok(Value::Array(
        grouped
            .into_iter()
            .map(
                |((plugin_index, plugin_name, plugin_hash), path_templates)| {
                    json!({
                        "plugin_index": plugin_index,
                        "plugin_name": plugin_name,
                        "plugin_hash": plugin_hash,
                        "path_templates": path_templates,
                    })
                },
            )
            .collect(),
    ))
}

fn read_plugin_text_rule_records(
    connection: &Connection,
) -> Result<Vec<PluginConfigRuleInput>, String> {
    serde_json::from_value(read_plugin_text_rules(connection)?).map_err(|error| {
        structured_error(
            "scope_index_rebuild_rules_unreadable",
            format!("解析插件规则失败: {error}"),
        )
    })
}

fn read_plugin_source_text_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(connection, "plugin_source", "读取插件源码规则失败")?;
    let mut grouped: BTreeMap<(String, String), (Vec<String>, Vec<String>)> = BTreeMap::new();
    for row in rows {
        let file_name = payload_optional_string(&row.payload_json, "file_name")
            .or_else(|| payload_optional_string(&row.payload_json, "file"))
            .ok_or_else(|| {
                structured_error(
                    "scope_index_rebuild_rules_unreadable",
                    "解析插件源码规则失败: payload_json.file_name 必须是字符串".to_string(),
                )
            })?;
        let file_hash = payload_optional_string(&row.payload_json, "file_hash").unwrap_or_default();
        let selector =
            payload_optional_string(&row.payload_json, "selector").unwrap_or(row.matcher_value);
        let selector_kind = payload_optional_string(&row.payload_json, "selector_kind")
            .unwrap_or_else(|| "translate".to_string());
        let entry = grouped.entry((file_name, file_hash)).or_default();
        if selector_kind == "excluded" {
            entry.1.push(selector);
        } else {
            entry.0.push(selector);
        }
    }
    Ok(Value::Array(
        grouped
            .into_iter()
            .map(
                |((file_name, file_hash), (selectors, excluded_selectors))| {
                    json!({
                        "file_name": file_name,
                        "file_hash": file_hash,
                        "selectors": selectors,
                        "excluded_selectors": excluded_selectors,
                    })
                },
            )
            .collect(),
    ))
}

fn read_plugin_source_text_rule_inputs(
    connection: &Connection,
) -> Result<Vec<PluginSourceTextRuleInput>, String> {
    serde_json::from_value(read_plugin_source_text_rules(connection)?).map_err(|error| {
        structured_error(
            "scope_index_rebuild_rules_unreadable",
            format!("解析插件源码规则失败: {error}"),
        )
    })
}

fn read_event_command_text_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(connection, "event_commands", "读取事件指令规则失败")?;
    let mut grouped: BTreeMap<(i64, String), (Value, Vec<String>)> = BTreeMap::new();
    for row in rows {
        let command_code = payload_i64(&row.payload_json, "command_code", "解析事件指令规则失败")?;
        let parameter_filters = payload_array(&row.payload_json, "parameter_filters");
        let filters_key = serde_json::to_string(&parameter_filters).map_err(|error| {
            structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!("解析事件指令规则失败: {error}"),
            )
        })?;
        let path_template =
            payload_optional_string(&row.payload_json, "path").unwrap_or(row.matcher_value);
        let entry = grouped
            .entry((command_code, filters_key))
            .or_insert_with(|| (parameter_filters, Vec::new()));
        entry.1.push(path_template);
    }
    Ok(Value::Array(
        grouped
            .into_iter()
            .map(|((command_code, _), (parameter_filters, path_templates))| {
                json!({
                    "command_code": command_code,
                    "parameter_filters": parameter_filters,
                    "path_templates": path_templates,
                })
            })
            .collect(),
    ))
}

fn read_event_command_text_rule_inputs(
    connection: &Connection,
) -> Result<Vec<EventCommandRuleInput>, String> {
    serde_json::from_value(read_event_command_text_rules(connection)?).map_err(|error| {
        structured_error(
            "scope_index_rebuild_rules_unreadable",
            format!("解析事件指令规则失败: {error}"),
        )
    })
}

fn read_note_tag_text_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(connection, "note_tags", "读取 Note 标签规则失败")?;
    let mut grouped: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for row in rows {
        let file_name = payload_string(&row.payload_json, "file_name", "解析 Note 标签规则失败")?;
        let tag_name = payload_string(&row.payload_json, "tag_name", "解析 Note 标签规则失败")?;
        grouped.entry(file_name).or_default().push(tag_name);
    }
    Ok(Value::Array(
        grouped
            .into_iter()
            .map(|(file_name, tag_names)| json!({"file_name": file_name, "tag_names": tag_names}))
            .collect(),
    ))
}

fn read_note_tag_text_rule_inputs(
    connection: &Connection,
) -> Result<Vec<NoteTagTextRuleInput>, String> {
    let rows = read_runtime_rule_payloads(connection, "note_tags", "读取 Note 标签规则失败")?;
    let mut grouped: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for row in rows {
        let file_name = payload_string(&row.payload_json, "file_name", "解析 Note 标签规则失败")?;
        let tag_name = payload_string(&row.payload_json, "tag_name", "解析 Note 标签规则失败")?;
        grouped.entry(file_name).or_default().insert(tag_name);
    }
    Ok(grouped
        .into_iter()
        .map(|(file_name, tag_names)| NoteTagTextRuleInput {
            file_name,
            tag_names,
        })
        .collect())
}

fn read_nonstandard_data_text_rules(connection: &Connection) -> Result<Value, String> {
    let rows =
        read_runtime_rule_payloads(connection, "nonstandard_data", "读取非标准 data 规则失败")?;
    type NonstandardRuleBuckets = BTreeMap<(String, String), (Vec<String>, Vec<String>, bool)>;

    let mut grouped: NonstandardRuleBuckets = BTreeMap::new();
    for row in rows {
        let file_name = payload_optional_string(&row.payload_json, "file_name")
            .or_else(|| payload_optional_string(&row.payload_json, "file"))
            .ok_or_else(|| {
                structured_error(
                    "scope_index_rebuild_rules_unreadable",
                    "解析非标准 data 规则失败: payload_json.file_name 必须是字符串".to_string(),
                )
            })?;
        let file_hash = payload_optional_string(&row.payload_json, "file_hash").unwrap_or_default();
        let path_template =
            payload_optional_string(&row.payload_json, "path").unwrap_or(row.matcher_value);
        let mut path_kind = payload_optional_string(&row.payload_json, "path_kind")
            .or_else(|| payload_optional_string(&row.payload_json, "rule_type"))
            .unwrap_or_else(|| "translate".to_string());
        if path_kind == "translated" {
            path_kind = "translate".to_string();
        }
        let entry = grouped.entry((file_name, file_hash)).or_default();
        match path_kind.as_str() {
            "excluded" => entry.1.push(path_template),
            "skipped" => entry.2 = true,
            _ => entry.0.push(path_template),
        }
    }
    Ok(Value::Array(
        grouped
            .into_iter()
            .map(
                |((file_name, file_hash), (path_templates, excluded_path_templates, skipped))| {
                    json!({
                        "file_name": file_name,
                        "file_hash": file_hash,
                        "path_templates": path_templates,
                        "excluded_path_templates": excluded_path_templates,
                        "skipped": skipped,
                    })
                },
            )
            .collect(),
    ))
}

fn read_nonstandard_data_text_rule_inputs(
    connection: &Connection,
) -> Result<Vec<NonstandardDataTextRuleInput>, String> {
    let rows = read_runtime_rule_payloads(
        connection,
        "nonstandard_data",
        "读取非标准 data 文件文本规则失败",
    )?;
    let mut grouped: BTreeMap<String, NonstandardDataTextRuleInput> = BTreeMap::new();
    for row in rows {
        let file_name = payload_optional_string(&row.payload_json, "file_name")
            .or_else(|| payload_optional_string(&row.payload_json, "file"))
            .ok_or_else(|| {
                structured_error(
                    "scope_index_rebuild_rules_unreadable",
                    "解析非标准 data 文件文本规则失败: payload_json.file_name 必须是字符串"
                        .to_string(),
                )
            })?;
        let file_hash = payload_optional_string(&row.payload_json, "file_hash").unwrap_or_default();
        let path_template =
            payload_optional_string(&row.payload_json, "path").unwrap_or(row.matcher_value);
        let mut path_kind = payload_optional_string(&row.payload_json, "path_kind")
            .or_else(|| payload_optional_string(&row.payload_json, "rule_type"))
            .unwrap_or_else(|| "translate".to_string());
        if path_kind == "translated" {
            path_kind = "translate".to_string();
        }
        let entry =
            grouped
                .entry(file_name.clone())
                .or_insert_with(|| NonstandardDataTextRuleInput {
                    file_name,
                    file_hash: file_hash.clone(),
                    path_templates: Vec::new(),
                    excluded_path_templates: Vec::new(),
                    skipped: false,
                });
        if entry.file_hash != file_hash {
            return Err(structured_error(
                "scope_index_rebuild_rules_unreadable",
                format!(
                    "非标准 data 规则文件哈希不一致，请重新导入规则: {}",
                    entry.file_name
                ),
            ));
        }
        match path_kind.as_str() {
            "translate" => entry.path_templates.push(path_template),
            "excluded" => entry.excluded_path_templates.push(path_template),
            "skipped" => {
                if !path_template.is_empty() {
                    return Err(structured_error(
                        "scope_index_rebuild_rules_unreadable",
                        format!(
                            "非标准 data 跳过规则不应包含路径，请重新导入规则: {}",
                            entry.file_name
                        ),
                    ));
                }
                entry.skipped = true;
            }
            _ => {
                return Err(structured_error(
                    "scope_index_rebuild_rules_unreadable",
                    format!("非标准 data 规则 path_kind 非法，请重新导入规则: {path_kind}"),
                ));
            }
        }
    }
    Ok(grouped.into_values().collect())
}

fn read_placeholder_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(connection, "placeholders", "读取普通占位符规则失败")?;
    Ok(Value::Array(
        rows.into_iter()
            .map(|row| {
                Ok(json!({
                    "pattern_text": row.matcher_value,
                    "placeholder_template": payload_string(&row.payload_json, "placeholder_template", "解析普通占位符规则失败")?,
                }))
            })
            .collect::<Result<Vec<_>, String>>()?,
    ))
}

fn read_structured_placeholder_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(
        connection,
        "structured_placeholders",
        "读取结构化占位符规则失败",
    )?;
    Ok(Value::Array(
        rows.into_iter()
            .map(|row| {
                Ok(json!({
                    "rule_name": payload_string(&row.payload_json, "rule_name", "解析结构化占位符规则失败")?,
                    "rule_type": payload_string(&row.payload_json, "rule_type", "解析结构化占位符规则失败")?,
                    "pattern_text": payload_optional_string(&row.payload_json, "pattern").unwrap_or(row.matcher_value),
                    "translatable_group": payload_string(&row.payload_json, "translatable_group", "解析结构化占位符规则失败")?,
                    "protected_groups": payload_object(&row.payload_json, "protected_groups"),
                }))
            })
            .collect::<Result<Vec<_>, String>>()?,
    ))
}

fn read_mv_virtual_namebox_rules(connection: &Connection) -> Result<Value, String> {
    let rows = read_runtime_rule_payloads(
        connection,
        "mv_virtual_namebox",
        "读取 MV 虚拟名字框规则失败",
    )?;
    Ok(Value::Array(
        rows.into_iter()
            .map(|row| {
                Ok(json!({
                    "rule_order": row.rule_order,
                    "rule_name": payload_string(&row.payload_json, "name", "解析 MV 虚拟名字框规则失败")?,
                    "pattern_text": payload_optional_string(&row.payload_json, "pattern").unwrap_or(row.matcher_value),
                    "speaker_group": payload_string(&row.payload_json, "speaker_group", "解析 MV 虚拟名字框规则失败")?,
                    "body_group": payload_optional_string(&row.payload_json, "body_group").unwrap_or_default(),
                    "speaker_policy": payload_string(&row.payload_json, "speaker_policy", "解析 MV 虚拟名字框规则失败")?,
                    "render_template": payload_string(&row.payload_json, "render_template", "解析 MV 虚拟名字框规则失败")?,
                }))
            })
            .collect::<Result<Vec<_>, String>>()?,
    ))
}

fn read_mv_virtual_namebox_rule_inputs(
    connection: &Connection,
) -> Result<Vec<RawMvVirtualNameboxRule>, String> {
    let rows = read_runtime_rule_payloads(
        connection,
        "mv_virtual_namebox",
        "读取 MV 虚拟名字框规则失败",
    )?;
    rows.into_iter()
        .map(|row| {
            Ok(RawMvVirtualNameboxRule {
                rule_name: payload_string(&row.payload_json, "name", "解析 MV 虚拟名字框规则失败")?,
                pattern_text: payload_optional_string(&row.payload_json, "pattern")
                    .unwrap_or(row.matcher_value),
                speaker_group: payload_string(
                    &row.payload_json,
                    "speaker_group",
                    "解析 MV 虚拟名字框规则失败",
                )?,
                body_group: payload_optional_string(&row.payload_json, "body_group")
                    .unwrap_or_default(),
                speaker_policy: payload_string(
                    &row.payload_json,
                    "speaker_policy",
                    "解析 MV 虚拟名字框规则失败",
                )?,
                render_template: payload_string(
                    &row.payload_json,
                    "render_template",
                    "解析 MV 虚拟名字框规则失败",
                )?,
            })
        })
        .collect()
}

fn compile_mv_virtual_namebox_rules(
    raw_rules: Vec<RawMvVirtualNameboxRule>,
) -> Result<Vec<CompiledMvVirtualNameboxRule>, String> {
    raw_rules
        .into_iter()
        .map(|rule| {
            if !matches!(
                rule.speaker_policy.as_str(),
                "translate" | "preserve" | "actor_name"
            ) {
                return Err(structured_error(
                    "scope_index_rebuild_rules_unreadable",
                    "rules.payload_json.speaker_policy 非法，请重新导入规则".to_string(),
                ));
            }
            let pattern = compile_mv_virtual_namebox_pattern(
                &rule.rule_name,
                &rule.pattern_text,
                &rule.speaker_group,
                &rule.body_group,
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_rebuild_rules_unreadable",
                    format!("MV 虚拟名字框规则 {} 正则编译失败: {error}", rule.rule_name),
                )
            })?;
            Ok(CompiledMvVirtualNameboxRule {
                rule_name: rule.rule_name,
                pattern,
                speaker_group: rule.speaker_group,
                body_group: rule.body_group,
                speaker_policy: rule.speaker_policy,
                render_template: rule.render_template,
            })
        })
        .collect()
}

fn resolve_source_layout(game_path: &Path) -> Result<SourceLayout, String> {
    let content_root = resolve_content_root(game_path);
    let data_dir = {
        let origin = content_root.join("data_origin");
        if origin.is_dir() {
            origin
        } else {
            content_root.join("data")
        }
    };
    if !data_dir.is_dir() {
        return Err(structured_error(
            "scope_index_rebuild_data_dir_missing",
            format!("找不到可读取的 data 源目录: {}", data_dir.display()),
        ));
    }
    let plugins_path = {
        let origin = content_root.join("js").join("plugins_origin.js");
        if origin.is_file() {
            origin
        } else {
            content_root.join("js").join("plugins.js")
        }
    };
    if !plugins_path.is_file() {
        return Err(structured_error(
            "scope_index_rebuild_plugins_js_missing",
            format!("找不到可读取的插件配置文件: {}", plugins_path.display()),
        ));
    }
    let plugin_source_dir = {
        let origin = content_root.join("js").join("plugins_source_origin");
        if origin.is_dir() {
            origin
        } else {
            content_root.join("js").join("plugins")
        }
    };
    Ok(SourceLayout {
        data_dir,
        plugins_path,
        plugin_source_dir,
    })
}

fn resolve_content_root(game_path: &Path) -> PathBuf {
    let mv_root = game_path.join("www");
    if mv_root.join("data").is_dir() && mv_root.join("js").is_dir() {
        mv_root
    } else {
        game_path.to_path_buf()
    }
}

fn read_standard_data_files(data_dir: &Path) -> Result<Vec<ParsedDataFile>, String> {
    let paths = fs::read_dir(data_dir)
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_data_dir_read_failed",
                format!("读取 data 源目录失败 {}: {error}", data_dir.display()),
            )
        })?
        .map(|entry| entry.map(|item| item.path()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_data_dir_read_failed",
                format!("读取 data 源目录项失败 {}: {error}", data_dir.display()),
            )
        })?;
    let mut json_paths = paths
        .into_iter()
        .filter(|path| path.is_file())
        .filter(|path| {
            path.file_name()
                .and_then(|value| value.to_str())
                .is_some_and(is_standard_data_file)
        })
        .collect::<Vec<_>>();
    json_paths.sort();
    let mut parsed = json_paths
        .par_iter()
        .map(|path| read_parsed_data_file(path))
        .collect::<Result<Vec<_>, String>>()?;
    parsed.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    Ok(parsed)
}

fn read_nonstandard_data_files(
    data_dir: &Path,
    rules: &[NonstandardDataTextRuleInput],
) -> Result<Vec<NonstandardDataFileInput>, String> {
    let file_names = rules
        .iter()
        .filter(|rule| !rule.skipped && !rule.path_templates.is_empty())
        .map(|rule| rule.file_name.as_str())
        .collect::<BTreeSet<_>>();
    if file_names.is_empty() {
        return Ok(Vec::new());
    }
    let mut files = file_names
        .par_iter()
        .map(|file_name| {
            let file_name = *file_name;
            let rule = rules
                .iter()
                .find(|rule| rule.file_name == file_name)
                .ok_or_else(|| {
                    structured_error(
                        "scope_index_rebuild_nonstandard_data_invalid",
                        format!("非标准 data 规则索引缺失，请重新导入规则: {file_name}"),
                    )
                })?;
            read_nonstandard_data_file(data_dir, rule)
        })
        .collect::<Result<Vec<_>, String>>()?;
    files.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    Ok(files)
}

fn read_nonstandard_data_file(
    data_dir: &Path,
    rule: &NonstandardDataTextRuleInput,
) -> Result<NonstandardDataFileInput, String> {
    let file_name = rule.file_name.as_str();
    if file_name.contains('/') || file_name.contains('\\') || !file_name.ends_with(".json") {
        return Err(structured_error(
            "scope_index_rebuild_nonstandard_data_invalid",
            format!("非标准 data 文件名无效，请重新导入规则: {file_name}"),
        ));
    }
    if is_standard_data_file(file_name) {
        return Err(structured_error(
            "scope_index_rebuild_nonstandard_data_invalid",
            format!("非标准 data 规则引用了标准 data 文件，请重新导入规则: {file_name}"),
        ));
    }
    let path = data_dir.join(file_name);
    let raw_text = fs::read_to_string(&path).map_err(|error| {
        structured_error(
            "stale_nonstandard_data_rules",
            format!(
                "非标准 data 规则已过期: {file_name}: 当前源文件不可读取，请重新导出并导入非标准 data 规则: {error}"
            ),
        )
    })?;
    let current_hash = sha256_text(&raw_text);
    if current_hash != rule.file_hash {
        return Err(structured_error(
            "stale_nonstandard_data_rules",
            format!(
                "非标准 data 规则已过期: {file_name}: 当前源文件内容已变化，请重新导出并导入非标准 data 规则"
            ),
        ));
    }
    let data = serde_json::from_str(&raw_text).map_err(|error| {
        structured_error(
            "scope_index_rebuild_nonstandard_data_invalid",
            format!("解析非标准 data 文件 JSON 失败 {}: {error}", path.display()),
        )
    })?;
    Ok(NonstandardDataFileInput {
        file_name: rule.file_name.clone(),
        data,
        raw_text,
    })
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

fn read_parsed_data_file(path: &Path) -> Result<ParsedDataFile, String> {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .map(str::to_string)
        .ok_or_else(|| {
            structured_error(
                "scope_index_rebuild_path_invalid",
                format!("data 文件缺少有效文件名: {}", path.display()),
            )
        })?;
    let text = fs::read_to_string(path).map_err(|error| {
        structured_error(
            "scope_index_rebuild_data_file_read_failed",
            format!("读取 data 文件失败 {}: {error}", path.display()),
        )
    })?;
    let data = serde_json::from_str(&text).map_err(|error| {
        structured_error(
            "scope_index_rebuild_data_json_invalid",
            format!("解析 data 文件 JSON 失败 {}: {error}", path.display()),
        )
    })?;
    Ok(ParsedDataFile { file_name, data })
}

fn is_standard_data_file(file_name: &str) -> bool {
    is_map_data_file(file_name)
        || matches!(
            file_name,
            "Actors.json"
                | "Animations.json"
                | "Armors.json"
                | "Classes.json"
                | "CommonEvents.json"
                | "Enemies.json"
                | "Items.json"
                | "MapInfos.json"
                | "Skills.json"
                | "States.json"
                | "System.json"
                | "Tilesets.json"
                | "Troops.json"
                | "Weapons.json"
        )
}

fn is_map_data_file(file_name: &str) -> bool {
    let Some(number_part) = file_name
        .strip_prefix("Map")
        .and_then(|value| value.strip_suffix(".json"))
    else {
        return false;
    };
    number_part.len() == 3
        && number_part
            .chars()
            .all(|char_value| char_value.is_ascii_digit())
}

fn scan_text_index_rows(
    data_files: &[ParsedDataFile],
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    let row_groups = data_files
        .par_iter()
        .map(|data_file| scan_data_file_rows(data_file, context))
        .collect::<Result<Vec<_>, String>>()?;
    Ok(row_groups.into_iter().flatten().collect())
}

fn scan_nonstandard_data_rows(
    files: &[NonstandardDataFileInput],
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    let managed_texts = collect_nonstandard_data_managed_texts(
        files,
        &context.nonstandard_data_rules,
        context.rule_candidate_text_rules.clone(),
    )
    .map_err(nonstandard_data_managed_text_error)?;
    let mut rows = Vec::new();
    for managed_text in managed_texts {
        let Some(normalized) = normalized_extractable_text(&managed_text.raw_text, context)? else {
            continue;
        };
        let location_path = format!(
            "nonstandard-data/{}/{}",
            managed_text.file_name, managed_text.json_path
        );
        let payload_json = domain_payload_json(
            "非标准 data",
            &json!({
                "json_path": managed_text.json_path,
            }),
        )?;
        rows.push(row_with_fact_options(
            RowInput {
                location_path,
                item_type: "short_text",
                role: None,
                original_lines: vec![normalized],
                source_line_paths: vec![managed_text.json_path],
                source_type: "nonstandard_data",
                source_file: &managed_text.file_name,
            },
            context,
            FactOptions {
                raw_text: Some(managed_text.raw_text),
                visible_text: None,
                selector: None,
                domain_payload_json: Some(payload_json),
            },
        )?);
    }
    Ok(rows)
}

fn nonstandard_data_managed_text_error(error: NonstandardDataManagedTextError) -> String {
    match error {
        NonstandardDataManagedTextError::Stale(message) => {
            structured_error("stale_nonstandard_data_rules", message)
        }
        NonstandardDataManagedTextError::ReviewIncomplete { unreviewed_count } => structured_error(
            "nonstandard_data_review_incomplete",
            format!(
                "非标准 data 文件文本支线还有 {unreviewed_count} 个候选未归类，请补全非标准 data 规则后重新重建文本范围索引"
            ),
        ),
    }
}

fn scan_plugin_parameter_rows(
    plugins: &[PluginConfigInput],
    plugin_text_rules: &[PluginConfigRuleInput],
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    if plugin_text_rules.is_empty() {
        return Ok(Vec::new());
    }
    let candidates = super::plugin_config::scan_plugin_config_rule_text_candidates(
        plugins,
        plugin_text_rules,
        context.rule_candidate_text_rules.clone(),
    )
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_plugin_config_scan_failed",
            format!("扫描插件参数文本失败: {error}"),
        )
    })?;
    candidates
        .iter()
        .map(|candidate| plugin_parameter_row(candidate, context))
        .collect()
}

fn scan_plugin_source_rows(
    files: &[PluginSourceFileInput],
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    if context.plugin_source_rules.is_empty() {
        return Ok(Vec::new());
    }
    collect_plugin_source_managed_texts(
        files,
        &context.plugin_source_rules,
        context.rule_candidate_text_rules.clone(),
    )
    .map_err(plugin_source_managed_text_error)?
    .iter()
    .map(|managed_text| {
        let location_path = format!(
            "js/plugins/{}/{}",
            managed_text.file_name, managed_text.selector
        );
        let payload_json = domain_payload_json(
            "插件源码",
            &json!({
                "line": managed_text.line,
                "start_index": managed_text.start_index,
                "end_index": managed_text.end_index,
                "content_start_index": managed_text.content_start_index,
                "content_end_index": managed_text.content_end_index,
                "quote": managed_text.quote,
            }),
        )?;
        row_with_fact_options(
            RowInput {
                location_path: location_path.clone(),
                item_type: "short_text",
                role: None,
                original_lines: vec![managed_text.text.clone()],
                source_line_paths: vec![location_path],
                source_type: "plugin_source",
                source_file: &managed_text.file_name,
            },
            context,
            FactOptions {
                raw_text: Some(managed_text.raw_text.clone()),
                visible_text: Some(managed_text.text.clone()),
                selector: Some(managed_text.selector.clone()),
                domain_payload_json: Some(payload_json),
            },
        )
    })
    .collect()
}

fn plugin_source_managed_text_error(error: PluginSourceManagedTextError) -> String {
    match error {
        PluginSourceManagedTextError::Stale(message) => {
            structured_error("stale_plugin_source_rules", message)
        }
        PluginSourceManagedTextError::ReviewIncomplete { unreviewed_count } => structured_error(
            "plugin_source_review_incomplete",
            format!(
                "插件源码规则还有 {unreviewed_count} 个候选未归入翻译或排除，请补全插件源码规则后重新重建文本范围索引"
            ),
        ),
        PluginSourceManagedTextError::InvalidCandidate(message) => {
            structured_error("plugin_source_candidate_contract_invalid", message)
        }
    }
}

fn filter_fresh_plugin_text_rules(
    rules: &[PluginConfigRuleInput],
    plugins: &[PluginConfigInput],
) -> Result<(Vec<PluginConfigRuleInput>, usize), String> {
    let mut current_hashes_by_index = BTreeMap::new();
    for plugin in plugins {
        let plugin_hash = super::plugin_config::plugin_hash(&plugin.plugin).map_err(|error| {
            structured_error(
                "scope_index_rebuild_plugin_config_scan_failed",
                format!("计算当前插件配置 hash 失败: {error}"),
            )
        })?;
        current_hashes_by_index.insert(plugin.plugin_index, plugin_hash);
    }

    let mut fresh_rules = Vec::new();
    let mut stale_rule_count = 0usize;
    for rule in rules {
        let Some(rule_hash) = &rule.plugin_hash else {
            stale_rule_count += 1;
            continue;
        };
        let Some(current_hash) = current_hashes_by_index.get(&rule.plugin_index) else {
            stale_rule_count += 1;
            continue;
        };
        if rule_hash != current_hash {
            stale_rule_count += 1;
            continue;
        }
        fresh_rules.push(rule.clone());
    }
    Ok((fresh_rules, stale_rule_count))
}

fn read_plugin_config_inputs(plugins_path: &Path) -> Result<Vec<PluginConfigInput>, String> {
    let plugins_text = fs::read_to_string(plugins_path).map_err(|error| {
        structured_error(
            "scope_index_rebuild_plugins_js_read_failed",
            format!("读取插件配置文件失败 {}: {error}", plugins_path.display()),
        )
    })?;
    let plugins_array = parse_plugins_js_array(&plugins_text)?;
    let plugins = plugins_array
        .into_iter()
        .enumerate()
        .map(|(plugin_index, plugin)| PluginConfigInput {
            plugin_index,
            plugin_name: plugin_name(&plugin, plugin_index),
            plugin,
        })
        .collect();
    Ok(plugins)
}

fn read_plugin_source_file_inputs(
    plugin_source_dir: &Path,
    plugins: &[PluginConfigInput],
    rules: &[PluginSourceTextRuleInput],
) -> Result<Vec<PluginSourceFileInput>, String> {
    if !plugin_source_dir.is_dir() {
        return Ok(Vec::new());
    }
    let enabled_files = enabled_plugin_source_file_names(plugins);
    let required_files = rules
        .iter()
        .map(|rule| rule.file_name.clone())
        .collect::<BTreeSet<_>>();
    required_files
        .into_par_iter()
        .map(|file_name| {
            validate_plugin_source_file_name(&file_name)?;
            let path = plugin_source_dir.join(&file_name);
            if !path.is_file() {
                return Ok(None);
            }
            let source = fs::read_to_string(&path).map_err(|error| {
                structured_error(
                    "scope_index_rebuild_plugin_source_read_failed",
                    format!("读取插件源码文件失败 {}: {error}", path.display()),
                )
            })?;
            Ok(Some(PluginSourceFileInput {
                active: enabled_files.contains(&file_name),
                file_name,
                source,
            }))
        })
        .collect::<Result<Vec<_>, _>>()
        .map(|files| files.into_iter().flatten().collect())
}

fn validate_plugin_source_file_name(file_name: &str) -> Result<(), String> {
    if file_name.is_empty()
        || file_name.contains('/')
        || file_name.contains('\\')
        || file_name.contains("..")
        || !file_name.ends_with(".js")
    {
        return Err(structured_error(
            "stale_plugin_source_rules",
            format!("插件源码规则引用了非法文件名，请重新导入插件源码规则: {file_name}"),
        ));
    }
    Ok(())
}

fn enabled_plugin_source_file_names(plugins: &[PluginConfigInput]) -> BTreeSet<String> {
    plugins
        .iter()
        .filter(|plugin| {
            plugin
                .plugin
                .get("status")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        })
        .map(|plugin| format!("{}.js", plugin.plugin_name))
        .collect()
}

fn parse_plugins_js_array(plugins_text: &str) -> Result<Vec<Value>, String> {
    let plugins_re = Regex::new(r"(?s)var\s+\$plugins\s*=\s*(\[.*\])\s*;").map_err(|error| {
        structured_error(
            "scope_index_rebuild_plugins_js_invalid",
            format!("内置 plugins.js 解析正则无效: {error}"),
        )
    })?;
    let Some(captures) = plugins_re.captures(plugins_text) else {
        return Err(structured_error(
            "scope_index_rebuild_plugins_js_invalid",
            "plugins.js 中未找到 var $plugins = [...] 结构".to_string(),
        ));
    };
    let Some(array_match) = captures.get(1) else {
        return Err(structured_error(
            "scope_index_rebuild_plugins_js_invalid",
            "plugins.js 中未找到插件数组".to_string(),
        ));
    };
    let value: Value = json5::from_str(array_match.as_str()).map_err(|error| {
        structured_error(
            "scope_index_rebuild_plugins_js_invalid",
            format!("plugins.js 插件数组解析失败: {error}"),
        )
    })?;
    let Value::Array(plugins) = value else {
        return Err(structured_error(
            "scope_index_rebuild_plugins_js_invalid",
            "plugins.js 中的 $plugins 必须是数组".to_string(),
        ));
    };
    Ok(plugins)
}

fn plugin_name(plugin: &Value, plugin_index: usize) -> String {
    plugin
        .get("name")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("unnamed_plugin_{plugin_index}"))
}

fn plugin_parameter_row(
    candidate: &RuleCandidateOutput,
    context: &RebuildContext,
) -> Result<DirectTextIndexRow, String> {
    let locator_json = serde_json::to_string(&json!({
        "file_name": "plugins.js",
        "source_type": "plugin_parameter",
        "location_path": candidate.location_path,
        "source_line_paths": [],
        "terminology_owner_terms": [],
        "display_name": null,
        "json_path": candidate.json_path,
        "rule_key": candidate.rule_key,
    }))
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_locator_invalid",
            format!(
                "插件参数 locator JSON 序列化失败 {}: {error}",
                candidate.location_path
            ),
        )
    })?;
    let payload_json = domain_payload_json(
        "插件参数",
        &json!({
            "json_path": candidate.json_path,
        }),
    )?;
    Ok(DirectTextIndexRow {
        location_path: candidate.location_path.clone(),
        item_type: "short_text".to_string(),
        role: None,
        original_lines: vec![candidate.original_text.clone()],
        source_line_paths: Vec::new(),
        source_type: "plugin_parameter".to_string(),
        source_file: "plugins.js".to_string(),
        writable: true,
        source_snapshot_fingerprint: context.source_snapshot_fingerprint.clone(),
        rules_fingerprint: context.rules_fingerprint.clone(),
        locator_json,
        fact_raw_text: candidate.raw_text.clone(),
        fact_visible_text: Some(candidate.original_text.clone()),
        fact_selector: candidate.json_path.clone(),
        fact_domain_payload_json: Some(payload_json),
    })
}

fn scan_note_tag_rows(
    data_files: &[ParsedDataFile],
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    if context.note_tag_rules.is_empty() {
        return Ok(Vec::new());
    }
    let note_tag_data_files = data_files
        .iter()
        .filter(|data_file| data_file.file_name.ends_with(".json") && !data_file.data.is_string())
        .map(|data_file| (data_file.file_name.clone(), data_file.data.clone()))
        .collect::<BTreeMap<_, _>>();
    let scan = super::note_tags::scan_note_tag_rule_candidates(
        &note_tag_data_files,
        context.rule_candidate_text_rules.clone(),
    )
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_note_tag_scan_failed",
            format!("扫描 Note 标签文本失败: {error}"),
        )
    })?;
    scan.hit_details
        .iter()
        .filter(|hit| hit.translatable)
        .filter(|hit| {
            context.note_tag_rules.iter().any(|rule| {
                rule.tag_names.contains(&hit.tag_name)
                    && note_tag_rule_file_matches(&hit.file_name, &rule.file_name)
            })
        })
        .map(|hit| {
            let payload_json = domain_payload_json(
                "Note 标签",
                &json!({
                    "tag_name": hit.tag_name,
                }),
            )?;
            row_with_fact_options(
                RowInput {
                    location_path: hit.location_path.clone(),
                    item_type: "short_text",
                    role: None,
                    original_lines: vec![hit.original_text.clone()],
                    source_line_paths: Vec::new(),
                    source_type: "note_tag",
                    source_file: &hit.file_name,
                },
                context,
                FactOptions {
                    raw_text: Some(hit.raw_text.clone()),
                    visible_text: Some(hit.original_text.clone()),
                    selector: Some(hit.tag_name.clone()),
                    domain_payload_json: Some(payload_json),
                },
            )
        })
        .collect()
}

fn scan_event_command_rule_rows(
    data_files: &[ParsedDataFile],
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    if context.event_command_rules.is_empty() {
        return Ok(Vec::new());
    }
    let event_command_data_files = data_files
        .iter()
        .filter(|data_file| data_file.file_name.ends_with(".json") && !data_file.data.is_string())
        .map(|data_file| EventCommandDataFileInput {
            file_name: data_file.file_name.clone(),
            data: data_file.data.clone(),
        })
        .collect::<Vec<_>>();
    let hit_details = super::event_commands::scan_event_command_rule_hit_details(
        &event_command_data_files,
        &context.event_command_rules,
    )
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_event_command_scan_failed",
            format!("扫描事件指令规则文本失败: {error}"),
        )
    })?;
    hit_details
        .iter()
        .filter_map(
            |hit| match source_text_required_matches(context, &hit.original_text) {
                Ok(true) => Some(Ok(hit)),
                Ok(false) => None,
                Err(error) => Some(Err(error)),
            },
        )
        .map(|hit| {
            let hit = hit?;
            let payload_json = domain_payload_json(
                "事件指令",
                &json!({
                    "command_code": hit.command_code,
                    "parameter_json_path": hit.json_path,
                }),
            )?;
            row_with_fact_options(
                RowInput {
                    location_path: hit.location_path.clone(),
                    item_type: "short_text",
                    role: None,
                    original_lines: vec![hit.original_text.clone()],
                    source_line_paths: Vec::new(),
                    source_type: "event_command",
                    source_file: &hit.file_name,
                },
                context,
                FactOptions {
                    raw_text: Some(hit.raw_text.clone()),
                    visible_text: Some(hit.original_text.clone()),
                    selector: Some(hit.json_path.clone()),
                    domain_payload_json: Some(payload_json),
                },
            )
        })
        .collect()
}

fn note_tag_rule_file_matches(file_name: &str, rule_file_name: &str) -> bool {
    rule_file_name == file_name || (rule_file_name == "Map*.json" && is_map_data_file(file_name))
}

fn scan_data_file_rows(
    data_file: &ParsedDataFile,
    context: &RebuildContext,
) -> Result<Vec<DirectTextIndexRow>, String> {
    let mut rows = Vec::new();
    if data_file.file_name == "System.json" {
        scan_system_rows(data_file, context, &mut rows)?;
    } else if is_base_data_file(&data_file.file_name) {
        scan_base_data_rows(data_file, context, &mut rows)?;
    }
    scan_command_rows(data_file, context, &mut rows)?;
    Ok(rows)
}

fn scan_system_rows(
    data_file: &ParsedDataFile,
    context: &RebuildContext,
    rows: &mut Vec<DirectTextIndexRow>,
) -> Result<(), String> {
    let Some(system) = data_file.data.as_object() else {
        return Ok(());
    };
    if let Some(game_title) = normalized_extractable_string(system.get("gameTitle"), context)? {
        rows.push(row(
            RowInput {
                location_path: "System.json/gameTitle".to_string(),
                item_type: "short_text",
                role: None,
                original_lines: vec![game_title],
                source_line_paths: Vec::new(),
                source_type: "standard_data",
                source_file: &data_file.file_name,
            },
            context,
        )?);
    }
    if let Some(terms) = system.get("terms").and_then(Value::as_object) {
        for key in ["basic", "commands", "params"] {
            if let Some(items) = terms.get(key).and_then(Value::as_array) {
                for (index, item) in items.iter().enumerate() {
                    if let Some(text) = normalized_extractable_string(Some(item), context)? {
                        rows.push(row(
                            RowInput {
                                location_path: format!("System.json/terms/{key}/{index}"),
                                item_type: "short_text",
                                role: None,
                                original_lines: vec![text],
                                source_line_paths: Vec::new(),
                                source_type: "standard_data",
                                source_file: &data_file.file_name,
                            },
                            context,
                        )?);
                    }
                }
            }
        }
        if let Some(messages) = terms.get("messages").and_then(Value::as_object) {
            for (key, value) in messages {
                if let Some(text) = normalized_extractable_string(Some(value), context)? {
                    rows.push(row(
                        RowInput {
                            location_path: format!("System.json/terms/messages/{key}"),
                            item_type: "short_text",
                            role: None,
                            original_lines: vec![text],
                            source_line_paths: Vec::new(),
                            source_type: "standard_data",
                            source_file: &data_file.file_name,
                        },
                        context,
                    )?);
                }
            }
        }
    }
    Ok(())
}

fn is_base_data_file(file_name: &str) -> bool {
    matches!(
        file_name,
        "Actors.json"
            | "Animations.json"
            | "Armors.json"
            | "Classes.json"
            | "Enemies.json"
            | "Items.json"
            | "Skills.json"
            | "States.json"
            | "Tilesets.json"
            | "Weapons.json"
    )
}

fn scan_base_data_rows(
    data_file: &ParsedDataFile,
    context: &RebuildContext,
    rows: &mut Vec<DirectTextIndexRow>,
) -> Result<(), String> {
    let Some(items) = data_file.data.as_array() else {
        return Ok(());
    };
    for item in items {
        let Some(object) = item.as_object() else {
            continue;
        };
        let Some(id) = object.get("id").and_then(Value::as_i64) else {
            continue;
        };
        for field_name in [
            "profile",
            "description",
            "message1",
            "message2",
            "message3",
            "message4",
        ] {
            if let Some(text) = normalized_extractable_string(object.get(field_name), context)? {
                rows.push(row(
                    RowInput {
                        location_path: format!("{}/{id}/{field_name}", data_file.file_name),
                        item_type: "short_text",
                        role: None,
                        original_lines: vec![text],
                        source_line_paths: Vec::new(),
                        source_type: "standard_data",
                        source_file: &data_file.file_name,
                    },
                    context,
                )?);
            }
        }
    }
    Ok(())
}

fn scan_command_rows(
    data_file: &ParsedDataFile,
    context: &RebuildContext,
    rows: &mut Vec<DirectTextIndexRow>,
) -> Result<(), String> {
    if is_map_data_file(&data_file.file_name) {
        let Some(map_object) = data_file.data.as_object() else {
            return Ok(());
        };
        let display_name = map_object
            .get("displayName")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let Some(events) = map_object.get("events").and_then(Value::as_array) else {
            return Ok(());
        };
        for event in events {
            let Some(event_object) = event.as_object() else {
                continue;
            };
            let Some(event_id) = event_object.get("id").and_then(Value::as_i64) else {
                continue;
            };
            let Some(pages) = event_object.get("pages").and_then(Value::as_array) else {
                continue;
            };
            for (page_index, page) in pages.iter().enumerate() {
                if let Some(commands) = page
                    .as_object()
                    .and_then(|object| object.get("list"))
                    .and_then(Value::as_array)
                {
                    scan_command_list(
                        &data_file.file_name,
                        Some(display_name),
                        &format!("{}/{event_id}/{page_index}", data_file.file_name),
                        commands,
                        context,
                        rows,
                    )?;
                }
            }
        }
        return Ok(());
    }

    if data_file.file_name == "CommonEvents.json" {
        let Some(events) = data_file.data.as_array() else {
            return Ok(());
        };
        for event in events {
            let Some(event_object) = event.as_object() else {
                continue;
            };
            let Some(event_id) = event_object.get("id").and_then(Value::as_i64) else {
                continue;
            };
            if let Some(commands) = event_object.get("list").and_then(Value::as_array) {
                scan_command_list(
                    &data_file.file_name,
                    None,
                    &format!("{}/{event_id}", data_file.file_name),
                    commands,
                    context,
                    rows,
                )?;
            }
        }
        return Ok(());
    }

    if data_file.file_name == "Troops.json" {
        let Some(troops) = data_file.data.as_array() else {
            return Ok(());
        };
        for troop in troops {
            let Some(troop_object) = troop.as_object() else {
                continue;
            };
            let Some(troop_id) = troop_object.get("id").and_then(Value::as_i64) else {
                continue;
            };
            let Some(pages) = troop_object.get("pages").and_then(Value::as_array) else {
                continue;
            };
            for (page_index, page) in pages.iter().enumerate() {
                if let Some(commands) = page
                    .as_object()
                    .and_then(|object| object.get("list"))
                    .and_then(Value::as_array)
                {
                    scan_command_list(
                        &data_file.file_name,
                        None,
                        &format!("{}/{troop_id}/{page_index}", data_file.file_name),
                        commands,
                        context,
                        rows,
                    )?;
                }
            }
        }
    }
    Ok(())
}

fn scan_command_list(
    file_name: &str,
    _display_name: Option<&str>,
    list_prefix: &str,
    commands: &[Value],
    context: &RebuildContext,
    rows: &mut Vec<DirectTextIndexRow>,
) -> Result<(), String> {
    let mut pending_scroll: Option<PendingLongText> = None;
    let mut last_scroll_index: Option<usize> = None;

    for (command_index, command) in commands.iter().enumerate() {
        let Some(command_object) = command.as_object() else {
            flush_scroll(file_name, &mut pending_scroll, context, rows)?;
            continue;
        };
        let code = command_object
            .get("code")
            .and_then(Value::as_i64)
            .unwrap_or_default();
        let location_path = format!("{list_prefix}/{command_index}");
        match code {
            101 => {
                flush_scroll(file_name, &mut pending_scroll, context, rows)?;
                let role = command_object
                    .get("parameters")
                    .and_then(Value::as_array)
                    .and_then(|parameters| parameters.get(4))
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .unwrap_or("旁白")
                    .to_string();
                rows.push(row(
                    RowInput {
                        location_path,
                        item_type: "long_text",
                        role: Some(role),
                        original_lines: Vec::new(),
                        source_line_paths: Vec::new(),
                        source_type: "event_command",
                        source_file: file_name,
                    },
                    context,
                )?);
            }
            401 => {
                flush_scroll(file_name, &mut pending_scroll, context, rows)?;
                let Some(text) = command_text(command_object, context)? else {
                    continue;
                };
                if let Some(last) = rows.last_mut()
                    && last.item_type == "long_text"
                    && last.source_file == file_name
                {
                    if last.role.as_deref() == Some("旁白")
                        && last.original_lines.is_empty()
                        && let Some(virtual_speaker) =
                            parse_mv_virtual_speaker_line(context, &text, &location_path)?
                    {
                        last.role = Some(virtual_speaker.speaker);
                        if virtual_speaker.body_text.is_empty() {
                            continue;
                        }
                        last.original_lines.push(virtual_speaker.body_text);
                        last.source_line_paths.push(location_path);
                        continue;
                    }
                    last.original_lines.push(text);
                    last.source_line_paths.push(location_path);
                }
            }
            102 => {
                flush_scroll(file_name, &mut pending_scroll, context, rows)?;
                if let Some(lines) = command_choices(command_object, context)?
                    && !lines.is_empty()
                {
                    rows.push(row(
                        RowInput {
                            location_path,
                            item_type: "array",
                            role: Some("旁白".to_string()),
                            original_lines: lines,
                            source_line_paths: Vec::new(),
                            source_type: "event_command",
                            source_file: file_name,
                        },
                        context,
                    )?);
                }
            }
            405 => {
                let Some(text) = command_text(command_object, context)? else {
                    flush_scroll(file_name, &mut pending_scroll, context, rows)?;
                    last_scroll_index = None;
                    continue;
                };
                if pending_scroll.is_none()
                    || last_scroll_index.is_none_or(|last_index| command_index != last_index + 1)
                {
                    flush_scroll(file_name, &mut pending_scroll, context, rows)?;
                    pending_scroll = Some(PendingLongText {
                        location_path: location_path.clone(),
                        role: "旁白".to_string(),
                        original_lines: Vec::new(),
                        source_line_paths: Vec::new(),
                    });
                }
                if let Some(scroll) = &mut pending_scroll {
                    scroll.original_lines.push(text);
                    scroll.source_line_paths.push(location_path);
                }
                last_scroll_index = Some(command_index);
            }
            _ => {
                flush_scroll(file_name, &mut pending_scroll, context, rows)?;
                last_scroll_index = None;
            }
        }
    }
    flush_scroll(file_name, &mut pending_scroll, context, rows)?;
    rows.retain(|row| !(row.item_type == "long_text" && row.original_lines.is_empty()));
    Ok(())
}

fn command_text(
    command_object: &serde_json::Map<String, Value>,
    context: &RebuildContext,
) -> Result<Option<String>, String> {
    let Some(value) = command_object
        .get("parameters")
        .and_then(Value::as_array)
        .and_then(|parameters| parameters.first())
    else {
        return Ok(None);
    };
    normalized_extractable_string(Some(value), context)
}

fn command_choices(
    command_object: &serde_json::Map<String, Value>,
    context: &RebuildContext,
) -> Result<Option<Vec<String>>, String> {
    let Some(values) = command_object
        .get("parameters")
        .and_then(Value::as_array)
        .and_then(|parameters| parameters.first())
        .and_then(Value::as_array)
    else {
        return Ok(None);
    };
    let mut lines = Vec::new();
    for value in values {
        if let Some(text) = normalized_extractable_string(Some(value), context)? {
            lines.push(text);
        }
    }
    if lines.is_empty() {
        Ok(None)
    } else {
        Ok(Some(lines))
    }
}

fn flush_scroll(
    file_name: &str,
    pending_scroll: &mut Option<PendingLongText>,
    context: &RebuildContext,
    rows: &mut Vec<DirectTextIndexRow>,
) -> Result<(), String> {
    let Some(scroll) = pending_scroll.take() else {
        return Ok(());
    };
    if scroll.original_lines.is_empty() {
        return Ok(());
    }
    rows.push(row(
        RowInput {
            location_path: scroll.location_path,
            item_type: "long_text",
            role: Some(scroll.role),
            original_lines: scroll.original_lines,
            source_line_paths: scroll.source_line_paths,
            source_type: "event_command",
            source_file: file_name,
        },
        context,
    )?);
    Ok(())
}

fn normalized_extractable_string(
    value: Option<&Value>,
    context: &RebuildContext,
) -> Result<Option<String>, String> {
    let Some(text) = value.and_then(Value::as_str) else {
        return Ok(None);
    };
    normalized_extractable_text(text, context)
}

fn normalized_extractable_text(
    text: &str,
    context: &RebuildContext,
) -> Result<Option<String>, String> {
    let normalized = normalize_visible_text_for_extraction(text);
    if normalized.is_empty() || !source_text_required_matches(context, &normalized)? {
        return Ok(None);
    }
    Ok(Some(normalized))
}

fn source_text_required_matches(context: &RebuildContext, text: &str) -> Result<bool, String> {
    context
        .source_text_required_re
        .is_match(text)
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_text_rule_match_failed",
                format!("源文识别 PCRE2 pattern 匹配失败: {}", error.message),
            )
        })
}

fn actor_names_by_id(data_files: &[ParsedDataFile]) -> BTreeMap<i64, String> {
    let Some(actors_file) = data_files
        .iter()
        .find(|file| file.file_name == "Actors.json")
    else {
        return BTreeMap::new();
    };
    let Some(actors) = actors_file.data.as_array() else {
        return BTreeMap::new();
    };
    let mut names = BTreeMap::new();
    for actor in actors {
        let Some(actor_object) = actor.as_object() else {
            continue;
        };
        let Some(actor_id) = actor_object.get("id").and_then(Value::as_i64) else {
            continue;
        };
        let Some(name) = actor_object
            .get("name")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        else {
            continue;
        };
        names.insert(actor_id, name.to_string());
    }
    names
}

fn database_owner_terms_by_key(data_files: &[ParsedDataFile]) -> BTreeMap<String, Vec<String>> {
    let mut owner_terms_by_key = BTreeMap::new();
    for data_file in data_files {
        if !is_terminology_base_name_file(&data_file.file_name) {
            continue;
        }
        let Some(items) = data_file.data.as_array() else {
            continue;
        };
        for item in items {
            let Some(object) = item.as_object() else {
                continue;
            };
            let Some(id) = object.get("id").and_then(Value::as_i64) else {
                continue;
            };
            let mut terms = Vec::new();
            push_unique_trimmed_term(&mut terms, object.get("name").and_then(Value::as_str));
            if data_file.file_name == "Actors.json" {
                push_unique_trimmed_term(
                    &mut terms,
                    object.get("nickname").and_then(Value::as_str),
                );
            }
            if !terms.is_empty() {
                owner_terms_by_key.insert(format!("{}/{}", data_file.file_name, id), terms);
            }
        }
    }
    owner_terms_by_key
}

fn is_terminology_base_name_file(file_name: &str) -> bool {
    matches!(
        file_name,
        "Actors.json"
            | "Classes.json"
            | "Skills.json"
            | "Items.json"
            | "Weapons.json"
            | "Armors.json"
            | "Enemies.json"
            | "States.json"
    )
}

fn system_owner_terms(data_files: &[ParsedDataFile]) -> Vec<String> {
    let Some(system_file) = data_files
        .iter()
        .find(|data_file| data_file.file_name == "System.json")
    else {
        return Vec::new();
    };
    let Some(system) = system_file.data.as_object() else {
        return Vec::new();
    };
    let mut terms = Vec::new();
    for field_name in [
        "elements",
        "skillTypes",
        "weaponTypes",
        "armorTypes",
        "equipTypes",
    ] {
        let Some(values) = system.get(field_name).and_then(Value::as_array) else {
            continue;
        };
        for value in values {
            push_unique_trimmed_term(&mut terms, value.as_str());
        }
    }
    terms
}

fn map_display_names_by_file(data_files: &[ParsedDataFile]) -> BTreeMap<String, String> {
    let mut names = BTreeMap::new();
    for data_file in data_files {
        if !is_map_data_file(&data_file.file_name) {
            continue;
        }
        let Some(display_name) = data_file
            .data
            .as_object()
            .and_then(|object| object.get("displayName"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        else {
            continue;
        };
        names.insert(data_file.file_name.clone(), display_name.to_string());
    }
    names
}

fn push_unique_trimmed_term(terms: &mut Vec<String>, value: Option<&str>) {
    let Some(term) = value.map(str::trim).filter(|term| !term.is_empty()) else {
        return;
    };
    if !terms.iter().any(|existing| existing == term) {
        terms.push(term.to_string());
    }
}

fn terminology_owner_terms(location_path: &str, context: &RebuildContext) -> Vec<String> {
    if location_path.starts_with("System.json/") {
        return context.system_owner_terms.clone();
    }
    let mut parts = location_path.split('/');
    let Some(file_name) = parts.next() else {
        return Vec::new();
    };
    let Some(id) = parts.next() else {
        return Vec::new();
    };
    context
        .database_owner_terms_by_key
        .get(&format!("{file_name}/{id}"))
        .cloned()
        .unwrap_or_default()
}

fn parse_mv_virtual_speaker_line(
    context: &RebuildContext,
    text: &str,
    location_path: &str,
) -> Result<Option<ParsedMvVirtualSpeaker>, String> {
    if context.mv_virtual_namebox_rules.is_empty() {
        return Ok(None);
    }
    let match_text = text.trim();
    if match_text.is_empty() {
        return Ok(None);
    }
    let mut matches: Vec<ParsedMvVirtualSpeaker> = Vec::new();
    let mut matched_rule_names: Vec<String> = Vec::new();
    for rule in &context.mv_virtual_namebox_rules {
        let captures = rule.pattern.captures_iter(match_text).map_err(|error| {
            structured_error(
                "scope_index_rebuild_mv_virtual_namebox_failed",
                format!(
                    "MV 虚拟名字框规则匹配失败 {}: {}",
                    rule.rule_name, error.message
                ),
            )
        })?;
        let Some(capture_match) = captures.into_iter().find(|capture_match| {
            capture_match.full_span.start == 0 && capture_match.full_span.end == match_text.len()
        }) else {
            continue;
        };
        matches.push(build_mv_virtual_speaker(
            context,
            rule,
            &capture_match,
            match_text,
            text,
            location_path,
        )?);
        matched_rule_names.push(rule.rule_name.clone());
    }
    if matches.len() > 1 {
        return Err(structured_error(
            "scope_index_rebuild_mv_virtual_namebox_failed",
            format!(
                "MV 虚拟名字框规则命中冲突; 文本路径={location_path}: 规则={}; 文本={text}",
                matched_rule_names.join(", ")
            ),
        ));
    }
    Ok(matches.into_iter().next())
}

fn build_mv_virtual_speaker(
    context: &RebuildContext,
    rule: &CompiledMvVirtualNameboxRule,
    captures: &Pcre2CaptureMatch,
    match_text: &str,
    raw_text: &str,
    location_path: &str,
) -> Result<ParsedMvVirtualSpeaker, String> {
    let mut group_values = BTreeMap::new();
    for capture_name in rule.pattern.capture_names() {
        if let Some(value) = capture_group(match_text, captures, &capture_name) {
            group_values.insert(capture_name, value.to_string());
        }
    }
    let source_speaker = capture_group(match_text, captures, &rule.speaker_group)
        .unwrap_or_default()
        .to_string();
    let raw_body_text = if rule.body_group.is_empty() {
        String::new()
    } else {
        capture_group(match_text, captures, &rule.body_group)
            .unwrap_or_default()
            .to_string()
    };
    let Some((semantic_speaker, body_text)) =
        weak_split_colon_speaker_parts(&source_speaker, &raw_body_text)
    else {
        return Err(structured_error(
            "scope_index_rebuild_mv_virtual_namebox_failed",
            format!(
                "MV 虚拟名字框规则 {} 命中了空说话人; 文本路径={location_path}",
                rule.rule_name
            ),
        ));
    };
    let speaker = if rule.speaker_policy == "actor_name" {
        actor_name_from_control(context, &semantic_speaker, location_path)?
    } else {
        semantic_speaker
    };
    let fact_parts = build_mv_virtual_namebox_fact_parts(MvVirtualNameboxFactPartsInput {
        raw_text,
        source_speaker: &source_speaker,
        role: &speaker,
        body_text: &raw_body_text,
        render_template: &rule.render_template,
        speaker_group: &rule.speaker_group,
        body_group: &rule.body_group,
        rule_name: &rule.rule_name,
        template_values: &group_values,
    })
    .map_err(|message| {
        structured_error(
            "scope_index_rebuild_mv_virtual_namebox_failed",
            format!("{message}; 文本路径={location_path}"),
        )
    })?;
    Ok(ParsedMvVirtualSpeaker {
        speaker,
        source_speaker,
        body_text,
        rule_name: rule.rule_name.clone(),
        speaker_policy: rule.speaker_policy.clone(),
        fact_parts,
    })
}

fn capture_group<'a>(
    text: &'a str,
    captures: &Pcre2CaptureMatch,
    group_name: &str,
) -> Option<&'a str> {
    captures.named_text(text, group_name)
}

fn actor_name_from_control(
    context: &RebuildContext,
    text: &str,
    location_path: &str,
) -> Result<String, String> {
    let pattern = Regex::new(r"^\\[Nn]\[(?P<actor_id>\d+)\]$").map_err(|error| {
        structured_error(
            "scope_index_rebuild_mv_virtual_namebox_failed",
            format!("MV actor_name 控制符正则初始化失败: {error}"),
        )
    })?;
    let captures = pattern.captures(text).ok_or_else(|| {
        structured_error(
            "scope_index_rebuild_mv_virtual_namebox_failed",
            format!(
                "actor_name 规则命中的说话人不是角色名控制符: {text}; 文本路径={location_path}"
            ),
        )
    })?;
    let actor_id = captures
        .name("actor_id")
        .ok_or_else(|| {
            structured_error(
                "scope_index_rebuild_mv_virtual_namebox_failed",
                format!("actor_name 规则无法解析角色 ID: {text}; 文本路径={location_path}"),
            )
        })?
        .as_str()
        .parse::<i64>()
        .map_err(|error| {
            structured_error(
                "scope_index_rebuild_mv_virtual_namebox_failed",
                format!(
                    "actor_name 规则角色 ID 不是数字: {text}: {error}; 文本路径={location_path}"
                ),
            )
        })?;
    context
        .actor_names_by_id
        .get(&actor_id)
        .cloned()
        .ok_or_else(|| {
            structured_error(
                "scope_index_rebuild_mv_virtual_namebox_failed",
                format!("actor_name 规则无法解析角色 ID: {actor_id}; 文本路径={location_path}"),
            )
        })
}

struct RowInput<'a> {
    location_path: String,
    item_type: &'static str,
    role: Option<String>,
    original_lines: Vec<String>,
    source_line_paths: Vec<String>,
    source_type: &'static str,
    source_file: &'a str,
}

#[derive(Default)]
struct FactOptions {
    raw_text: Option<String>,
    visible_text: Option<String>,
    selector: Option<String>,
    domain_payload_json: Option<String>,
}

fn row(input: RowInput<'_>, context: &RebuildContext) -> Result<DirectTextIndexRow, String> {
    row_with_fact_options(input, context, FactOptions::default())
}

fn row_with_fact_options(
    input: RowInput<'_>,
    context: &RebuildContext,
    fact_options: FactOptions,
) -> Result<DirectTextIndexRow, String> {
    let terminology_owner_terms = terminology_owner_terms(&input.location_path, context);
    let display_name = context
        .map_display_names_by_file
        .get(input.source_file)
        .cloned();
    let locator_json = serde_json::to_string(&json!({
        "file_name": input.source_file,
        "source_type": input.source_type,
        "location_path": &input.location_path,
        "source_line_paths": &input.source_line_paths,
        "terminology_owner_terms": terminology_owner_terms,
        "display_name": display_name,
    }))
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_locator_invalid",
            format!(
                "索引 locator JSON 序列化失败 {}: {error}",
                input.location_path
            ),
        )
    })?;
    Ok(DirectTextIndexRow {
        location_path: input.location_path,
        item_type: input.item_type.to_string(),
        role: input.role,
        original_lines: input.original_lines,
        source_line_paths: input.source_line_paths,
        source_type: input.source_type.to_string(),
        source_file: input.source_file.to_string(),
        writable: true,
        source_snapshot_fingerprint: context.source_snapshot_fingerprint.clone(),
        rules_fingerprint: context.rules_fingerprint.clone(),
        locator_json,
        fact_raw_text: fact_options.raw_text,
        fact_visible_text: fact_options.visible_text,
        fact_selector: fact_options.selector,
        fact_domain_payload_json: fact_options.domain_payload_json,
    })
}

fn domain_payload_json(label: &str, value: &Value) -> Result<String, String> {
    serde_json::to_string(value).map_err(|error| {
        structured_error(
            "scope_index_rebuild_text_fact_invalid",
            format!("{label} domain payload 序列化失败: {error}"),
        )
    })
}

fn domain_summary_from_rows(rows: &[DirectTextIndexRow]) -> Vec<DirectDomainSummary> {
    let mut counters: BTreeMap<String, DomainCounter> = BTreeMap::new();
    for row in rows {
        let counter = counters.entry(row.source_type.clone()).or_default();
        counter.item_count += 1;
        counter.active_count += 1;
        if row.writable {
            counter.writable_count += 1;
        } else {
            counter.unwritable_count += 1;
        }
    }
    counters
        .into_iter()
        .map(|(domain, counter)| DirectDomainSummary {
            domain,
            item_count: counter.item_count,
            active_count: counter.active_count,
            writable_count: counter.writable_count,
            unwritable_count: counter.unwritable_count,
            inactive_rule_hit_count: 0,
        })
        .collect()
}

fn warm_index_rows_from_fact_rows(rows: &[DirectTextIndexRow]) -> Vec<DirectTextIndexRow> {
    let mut warm_rows = rows.to_vec();
    warm_rows.sort_by(|left, right| left.location_path.cmp(&right.location_path));
    warm_rows.dedup_by(|left, right| left.location_path == right.location_path);
    warm_rows
}

#[cfg(test)]
fn build_text_fact_storage_payload(
    rows: &[DirectTextIndexRow],
    scope: &TextFactScope,
) -> Result<DirectTextFactStoragePayload, String> {
    build_text_fact_storage_payload_with_context(rows, scope, &[], None)
}

fn build_text_fact_storage_payload_with_context(
    rows: &[DirectTextIndexRow],
    scope: &TextFactScope,
    data_files: &[ParsedDataFile],
    context: Option<&RebuildContext>,
) -> Result<DirectTextFactStoragePayload, String> {
    let mut text_facts = Vec::with_capacity(rows.len());
    let mut render_parts = Vec::new();
    let mut domain_payloads = Vec::new();
    let mut domain_fact_counts = BTreeMap::new();
    for row in rows {
        let fact_content = direct_text_fact_content(row, data_files, context)?;
        let fact = build_text_fact_from_content(row, scope, &fact_content)?;
        for (part_order, part) in fact_content.render_parts.iter().enumerate() {
            render_parts.push(TextFactRenderPart {
                fact_id: fact.fact_id.clone(),
                part_order: part_order as i64,
                part_kind: part.part_kind.clone(),
                raw_text: part.raw_text.clone(),
                semantic_text: part.semantic_text.clone(),
                template_key: part.template_key.clone(),
            });
        }
        if let Some(payload_json) = fact_content.domain_payload_json {
            domain_payloads.push(TextFactDomainPayload {
                fact_id: fact.fact_id.clone(),
                payload_json,
            });
        }
        *domain_fact_counts
            .entry(fact_content.domain.clone())
            .or_insert(0) += 1;
        text_facts.push(fact);
    }
    Ok(DirectTextFactStoragePayload {
        text_facts,
        render_parts,
        domain_payloads,
        domain_fact_counts,
    })
}

struct DirectTextIndexFactIdentity {
    role: Option<String>,
    raw_text: Option<String>,
}

fn text_index_row_fact_identity(
    row: &DirectTextIndexRow,
    data_files: &[ParsedDataFile],
    context: Option<&RebuildContext>,
) -> Result<DirectTextIndexFactIdentity, String> {
    let fact_content = direct_text_fact_content(row, data_files, context)?;
    let row_raw_identity = row.original_lines.join("\n");
    let raw_text = if fact_content.raw_text == row_raw_identity {
        None
    } else {
        Some(fact_content.raw_text)
    };
    let role = if fact_content.role.is_empty() {
        None
    } else {
        Some(fact_content.role)
    };
    Ok(DirectTextIndexFactIdentity { role, raw_text })
}

fn direct_text_fact_content(
    row: &DirectTextIndexRow,
    data_files: &[ParsedDataFile],
    context: Option<&RebuildContext>,
) -> Result<DirectTextFactContent, String> {
    Ok(match context {
        Some(context) => mv_virtual_namebox_fact_content(row, data_files, context)?,
        None => None,
    }
    .unwrap_or_else(|| default_text_fact_content(row)))
}

struct DirectTextFactContent {
    domain: String,
    role: String,
    selector: String,
    raw_text: String,
    visible_text: String,
    translatable_text: String,
    render_parts: Vec<DirectTextFactRenderPart>,
    domain_payload_json: Option<String>,
}

#[derive(Debug, Clone)]
struct DirectTextFactRenderPart {
    part_kind: String,
    raw_text: String,
    semantic_text: String,
    template_key: String,
}

fn default_text_fact_content(row: &DirectTextIndexRow) -> DirectTextFactContent {
    let text = row.original_lines.join("\n");
    let raw_text = row.fact_raw_text.clone().unwrap_or_else(|| text.clone());
    let visible_text = row
        .fact_visible_text
        .clone()
        .unwrap_or_else(|| text.clone());
    DirectTextFactContent {
        domain: text_fact_domain_for_row(row).to_string(),
        role: row.role.clone().unwrap_or_default(),
        selector: row
            .fact_selector
            .clone()
            .unwrap_or_else(|| row.location_path.clone()),
        raw_text: raw_text.clone(),
        visible_text,
        translatable_text: text.clone(),
        render_parts: vec![DirectTextFactRenderPart {
            part_kind: "translated_body".to_string(),
            raw_text,
            semantic_text: text,
            template_key: "body".to_string(),
        }],
        domain_payload_json: row.fact_domain_payload_json.clone(),
    }
}

fn mv_virtual_namebox_fact_content(
    row: &DirectTextIndexRow,
    data_files: &[ParsedDataFile],
    context: &RebuildContext,
) -> Result<Option<DirectTextFactContent>, String> {
    if context.mv_virtual_namebox_rules.is_empty() || row.source_type != "event_command" {
        return Ok(None);
    }
    let translatable_text = row.original_lines.join("\n");
    for source_line_path in &row.source_line_paths {
        let Some(raw_text) = command_text_by_location_path(data_files, source_line_path) else {
            continue;
        };
        let Some(parsed) = parse_mv_virtual_speaker_line(context, &raw_text, source_line_path)?
        else {
            continue;
        };
        if parsed.body_text != translatable_text {
            continue;
        }
        return mv_virtual_namebox_content_from_parsed(parsed, row.location_path.clone()).map(Some);
    }
    if translatable_text.is_empty() {
        return Ok(None);
    }
    let Some(mut parsed) = standalone_mv_virtual_speaker_for_row(row, data_files, context)? else {
        return Ok(None);
    };
    if !parsed.body_text.is_empty() {
        return Ok(None);
    }
    append_standalone_body_to_mv_fact_parts(&mut parsed.fact_parts, &translatable_text);
    parsed.body_text = translatable_text;
    mv_virtual_namebox_content_from_parsed(parsed, row.location_path.clone()).map(Some)
}

fn mv_virtual_namebox_content_from_parsed(
    parsed: ParsedMvVirtualSpeaker,
    selector: String,
) -> Result<DirectTextFactContent, String> {
    let payload_json = serde_json::to_string(&json!({
        "rule_name": parsed.rule_name,
        "speaker_policy": parsed.speaker_policy,
        "source_speaker": parsed.source_speaker,
    }))
    .map_err(|error| {
        structured_error(
            "scope_index_rebuild_text_fact_invalid",
            format!("MV 虚拟名字框 domain payload 序列化失败: {error}"),
        )
    })?;
    Ok(DirectTextFactContent {
        domain: domains::MV_VIRTUAL_NAMEBOX.to_string(),
        role: parsed.fact_parts.role,
        selector,
        raw_text: parsed.fact_parts.raw_text,
        visible_text: parsed.fact_parts.visible_text,
        translatable_text: parsed.fact_parts.translatable_text,
        render_parts: parsed
            .fact_parts
            .render_parts
            .into_iter()
            .map(|part| DirectTextFactRenderPart {
                part_kind: part.part_kind,
                raw_text: part.raw_text,
                semantic_text: part.semantic_text,
                template_key: part.template_key,
            })
            .collect(),
        domain_payload_json: Some(payload_json),
    })
}

fn append_standalone_body_to_mv_fact_parts(
    fact_parts: &mut MvVirtualNameboxFactParts,
    body_text: &str,
) {
    if fact_parts
        .render_parts
        .last()
        .is_some_and(|part| part.part_kind == "translated_body" && part.raw_text.is_empty())
    {
        fact_parts.render_parts.pop();
    }
    append_literal_to_mv_fact_parts(fact_parts, "\n");
    fact_parts
        .render_parts
        .push(MvVirtualNameboxFactRenderPart {
            part_kind: "translated_body".to_string(),
            raw_text: body_text.to_string(),
            semantic_text: body_text.to_string(),
            template_key: "body".to_string(),
        });
    fact_parts.raw_text.push('\n');
    fact_parts.raw_text.push_str(body_text);
    fact_parts.visible_text.push('\n');
    fact_parts.visible_text.push_str(body_text);
    fact_parts.translatable_text = body_text.to_string();
}

fn append_literal_to_mv_fact_parts(fact_parts: &mut MvVirtualNameboxFactParts, literal: &str) {
    if let Some(last) = fact_parts.render_parts.last_mut()
        && last.part_kind == "literal"
    {
        last.raw_text.push_str(literal);
        last.semantic_text.push_str(literal);
        return;
    }
    fact_parts
        .render_parts
        .push(MvVirtualNameboxFactRenderPart {
            part_kind: "literal".to_string(),
            raw_text: literal.to_string(),
            semantic_text: literal.to_string(),
            template_key: "literal".to_string(),
        });
}

fn standalone_mv_virtual_speaker_for_row(
    row: &DirectTextIndexRow,
    data_files: &[ParsedDataFile],
    context: &RebuildContext,
) -> Result<Option<ParsedMvVirtualSpeaker>, String> {
    let Some((commands, command_index, path_prefix)) =
        command_list_by_location_path(data_files, &row.location_path)
    else {
        return Ok(None);
    };
    for next_index in (command_index + 1)..commands.len() {
        let command_path = format!("{path_prefix}/{next_index}");
        let Some(command) = commands.get(next_index).and_then(Value::as_object) else {
            return Ok(None);
        };
        let code = command
            .get("code")
            .and_then(Value::as_i64)
            .unwrap_or_default();
        if code != 401 {
            return Ok(None);
        }
        let Some(text) = command_first_parameter_text(command) else {
            return Ok(None);
        };
        if text.trim().is_empty() {
            continue;
        }
        let Some(parsed) = parse_mv_virtual_speaker_line(context, &text, &command_path)? else {
            return Ok(None);
        };
        return Ok(Some(parsed));
    }
    Ok(None)
}

fn build_text_fact_from_content(
    row: &DirectTextIndexRow,
    scope: &TextFactScope,
    content: &DirectTextFactContent,
) -> Result<TextFact, String> {
    let raw_hash = sha256_text(&content.raw_text);
    let visible_hash = sha256_text(&content.visible_text);
    let translatable_hash = sha256_text(&content.translatable_text);
    let fact_id = build_fact_id(
        CURRENT_TEXT_FACT_CONTRACT_VERSION,
        &content.domain,
        &row.location_path,
        &content.selector,
        &raw_hash,
    );
    let fact = TextFact {
        fact_id,
        schema_version: CURRENT_TEXT_FACT_CONTRACT_VERSION,
        domain: content.domain.clone(),
        location_path: row.location_path.clone(),
        source_file: row.source_file.clone(),
        source_type: row.source_type.clone(),
        item_type: row.item_type.clone(),
        role: content.role.clone(),
        selector: content.selector.clone(),
        raw_text: content.raw_text.clone(),
        visible_text: content.visible_text.clone(),
        translatable_text: content.translatable_text.clone(),
        raw_hash,
        visible_hash,
        translatable_hash,
        scope_key: scope.scope_key.clone(),
    };
    fact.validate().map_err(|message| {
        structured_error(
            "scope_index_rebuild_text_fact_invalid",
            format!("当前文本事实构造失败 {}: {message}", row.location_path),
        )
    })?;
    Ok(fact)
}

fn text_fact_domain_for_row(row: &DirectTextIndexRow) -> &str {
    text_fact_domain_for_row_source_type(&row.source_type)
}

fn text_fact_domain_for_row_source_type(source_type: &str) -> &str {
    match source_type {
        "plugin_parameter" => domains::PLUGIN_CONFIG,
        value => value,
    }
}

fn command_text_by_location_path(
    data_files: &[ParsedDataFile],
    location_path: &str,
) -> Option<String> {
    let parts = location_path.split('/').collect::<Vec<_>>();
    let file_name = *parts.first()?;
    let data = &data_files
        .iter()
        .find(|file| file.file_name == file_name)?
        .data;
    let command = if file_name == "CommonEvents.json" {
        command_from_common_event_path(data, &parts)?
    } else if is_map_data_file(file_name) {
        command_from_map_path(data, &parts)?
    } else if file_name == "Troops.json" {
        command_from_troop_path(data, &parts)?
    } else {
        return None;
    };
    command
        .get("parameters")?
        .as_array()?
        .first()?
        .as_str()
        .map(str::to_string)
}

fn command_first_parameter_text(command: &serde_json::Map<String, Value>) -> Option<String> {
    command
        .get("parameters")?
        .as_array()?
        .first()?
        .as_str()
        .map(str::to_string)
}

fn command_list_by_location_path<'a>(
    data_files: &'a [ParsedDataFile],
    location_path: &str,
) -> Option<(&'a [Value], usize, String)> {
    let parts = location_path.split('/').collect::<Vec<_>>();
    let file_name = *parts.first()?;
    let data = &data_files
        .iter()
        .find(|file| file.file_name == file_name)?
        .data;
    if file_name == "CommonEvents.json" {
        let event_id = parse_i64_path_part(parts.get(1)?)?;
        let command_index = parse_usize_path_part(parts.get(2)?)?;
        let event = data.as_array()?.iter().find(|item| {
            item.as_object()
                .and_then(|object| object.get("id"))
                .and_then(Value::as_i64)
                == Some(event_id)
        })?;
        let commands = event.as_object()?.get("list")?.as_array()?;
        return Some((commands, command_index, format!("{file_name}/{event_id}")));
    }
    if is_map_data_file(file_name) {
        let event_id = parse_i64_path_part(parts.get(1)?)?;
        let page_index = parse_usize_path_part(parts.get(2)?)?;
        let command_index = parse_usize_path_part(parts.get(3)?)?;
        let event = data.get("events")?.as_array()?.iter().find(|item| {
            item.as_object()
                .and_then(|object| object.get("id"))
                .and_then(Value::as_i64)
                == Some(event_id)
        })?;
        let commands = event
            .get("pages")?
            .as_array()?
            .get(page_index)?
            .get("list")?
            .as_array()?;
        return Some((
            commands,
            command_index,
            format!("{file_name}/{event_id}/{page_index}"),
        ));
    }
    if file_name == "Troops.json" {
        let troop_id = parse_i64_path_part(parts.get(1)?)?;
        let page_index = parse_usize_path_part(parts.get(2)?)?;
        let command_index = parse_usize_path_part(parts.get(3)?)?;
        let troop = data.as_array()?.iter().find(|item| {
            item.as_object()
                .and_then(|object| object.get("id"))
                .and_then(Value::as_i64)
                == Some(troop_id)
        })?;
        let commands = troop
            .get("pages")?
            .as_array()?
            .get(page_index)?
            .get("list")?
            .as_array()?;
        return Some((
            commands,
            command_index,
            format!("{file_name}/{troop_id}/{page_index}"),
        ));
    }
    None
}

fn command_from_common_event_path<'a>(
    data: &'a Value,
    parts: &[&str],
) -> Option<&'a serde_json::Map<String, Value>> {
    if parts.len() < 3 {
        return None;
    }
    let event_id = parse_i64_path_part(parts[1])?;
    let command_index = parse_usize_path_part(parts[2])?;
    let event = data.as_array()?.iter().find(|item| {
        item.as_object()
            .and_then(|object| object.get("id"))
            .and_then(Value::as_i64)
            == Some(event_id)
    })?;
    event
        .as_object()?
        .get("list")?
        .as_array()?
        .get(command_index)?
        .as_object()
}

fn command_from_map_path<'a>(
    data: &'a Value,
    parts: &[&str],
) -> Option<&'a serde_json::Map<String, Value>> {
    if parts.len() < 4 {
        return None;
    }
    let event_id = parse_i64_path_part(parts[1])?;
    let page_index = parse_usize_path_part(parts[2])?;
    let command_index = parse_usize_path_part(parts[3])?;
    let event = data.get("events")?.as_array()?.iter().find(|item| {
        item.as_object()
            .and_then(|object| object.get("id"))
            .and_then(Value::as_i64)
            == Some(event_id)
    })?;
    event
        .get("pages")?
        .as_array()?
        .get(page_index)?
        .get("list")?
        .as_array()?
        .get(command_index)?
        .as_object()
}

fn command_from_troop_path<'a>(
    data: &'a Value,
    parts: &[&str],
) -> Option<&'a serde_json::Map<String, Value>> {
    if parts.len() < 4 {
        return None;
    }
    let troop_id = parse_i64_path_part(parts[1])?;
    let page_index = parse_usize_path_part(parts[2])?;
    let command_index = parse_usize_path_part(parts[3])?;
    let troop = data.as_array()?.iter().find(|item| {
        item.as_object()
            .and_then(|object| object.get("id"))
            .and_then(Value::as_i64)
            == Some(troop_id)
    })?;
    troop
        .get("pages")?
        .as_array()?
        .get(page_index)?
        .get("list")?
        .as_array()?
        .get(command_index)?
        .as_object()
}

fn parse_i64_path_part(value: &str) -> Option<i64> {
    value.parse::<i64>().ok()
}

fn parse_usize_path_part(value: &str) -> Option<usize> {
    value.parse::<usize>().ok()
}

fn serialize_output(output: &RebuildStorageOutput) -> Result<String, String> {
    serde_json::to_string(output).map_err(|error| {
        structured_error(
            "scope_index_rebuild_output_failed",
            format!("Scope/Index rebuild 输出 JSON 序列化失败: {error}"),
        )
    })
}

fn structured_error(code: &str, message: String) -> String {
    match serde_json::to_string(&json!({
        "status": "error",
        "error": {
            "code": code,
            "message": message,
        }
    })) {
        Ok(text) => text,
        Err(_) => format!("{code}: {message}"),
    }
}

#[cfg(test)]
mod tests {
    use super::{
        DirectTextIndexRow, RebuildStoragePayload, RuleCandidateTextRules,
        build_text_fact_storage_payload, rebuild_text_rules_hash,
    };
    use crate::native_core::models::{
        NativeCustomPlaceholderRule, NativeStructuredPlaceholderRule,
    };
    use crate::native_core::text_facts::{TextFactScope, domains};
    use serde_json::json;
    use std::collections::HashMap;

    #[test]
    fn rebuild_text_rules_hash_changes_for_scan_affecting_inputs() {
        let base_hash = rebuild_text_rules_hash(&minimal_rebuild_payload())
            .expect("基础 text rule scope hash 应可计算");

        let mut changed_pattern = minimal_rebuild_payload();
        changed_pattern.source_text_required_pattern = "[A-Z]+".to_string();
        assert_ne!(
            base_hash,
            rebuild_text_rules_hash(&changed_pattern).expect("正则变化后应可计算 hash")
        );

        let mut changed_event_codes = minimal_rebuild_payload();
        changed_event_codes.event_command_scope_codes = vec![401];
        assert_ne!(
            base_hash,
            rebuild_text_rules_hash(&changed_event_codes).expect("事件指令编码变化后应可计算 hash")
        );

        let mut changed_candidate_rules = minimal_rebuild_payload();
        changed_candidate_rules
            .rule_candidate_text_rules
            .custom_placeholder_rules
            .push(NativeCustomPlaceholderRule {
                pattern_text: r"\\V\[\d+\]".to_string(),
                placeholder_template: r"\\V[{n}]".to_string(),
            });
        assert_ne!(
            base_hash,
            rebuild_text_rules_hash(&changed_candidate_rules)
                .expect("候选文本规则变化后应可计算 hash")
        );
    }

    #[test]
    fn rebuild_text_rules_hash_is_stable_for_json_object_key_order() {
        let mut first = minimal_rebuild_payload();
        first.text_rules_setting = json!({
            "b": {"second": true, "first": false},
            "a": 1
        });
        let mut second = minimal_rebuild_payload();
        second.text_rules_setting = json!({
            "a": 1,
            "b": {"first": false, "second": true}
        });

        assert_eq!(
            rebuild_text_rules_hash(&first).expect("第一种 JSON key 顺序应可计算 hash"),
            rebuild_text_rules_hash(&second).expect("第二种 JSON key 顺序应可计算 hash")
        );
    }

    #[test]
    fn rebuild_text_fact_storage_payload_builds_default_facts_for_batch1_rows() {
        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let rows = vec![
            DirectTextIndexRow {
                location_path: "System.json/gameTitle".to_string(),
                item_type: "short_text".to_string(),
                role: None,
                original_lines: vec!["Fixture Game".to_string()],
                source_line_paths: Vec::new(),
                source_type: "standard_data".to_string(),
                source_file: "System.json".to_string(),
                writable: true,
                source_snapshot_fingerprint: "snapshot-v1".to_string(),
                rules_fingerprint: "rules-v1".to_string(),
                locator_json: "{}".to_string(),
                fact_raw_text: None,
                fact_visible_text: None,
                fact_selector: None,
                fact_domain_payload_json: None,
            },
            DirectTextIndexRow {
                location_path: "CommonEvents.json/1/0".to_string(),
                item_type: "long_text".to_string(),
                role: Some("Alice".to_string()),
                original_lines: vec!["Hello".to_string()],
                source_line_paths: vec!["CommonEvents.json/1/1".to_string()],
                source_type: "event_command".to_string(),
                source_file: "CommonEvents.json".to_string(),
                writable: true,
                source_snapshot_fingerprint: "snapshot-v1".to_string(),
                rules_fingerprint: "rules-v1".to_string(),
                locator_json: "{}".to_string(),
                fact_raw_text: None,
                fact_visible_text: None,
                fact_selector: None,
                fact_domain_payload_json: None,
            },
        ];

        let fact_payload = build_text_fact_storage_payload(&rows, &scope)
            .expect("batch1 默认文本事实应可由 rows 构建");

        assert_eq!(fact_payload.text_facts.len(), 2);
        assert_eq!(fact_payload.render_parts.len(), 2);
        assert_eq!(fact_payload.domain_fact_counts[domains::STANDARD_DATA], 1);
        assert_eq!(fact_payload.domain_fact_counts[domains::EVENT_COMMAND], 1);
        assert!(fact_payload.domain_payloads.is_empty());
        assert!(fact_payload.text_facts.iter().all(|fact| {
            fact.raw_text == fact.visible_text && fact.visible_text == fact.translatable_text
        }));
    }

    #[test]
    fn rebuild_text_fact_storage_payload_builds_extended_domain_payloads() {
        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let rows = vec![
            test_row(
                "plugins.js/0/Message",
                "plugin_parameter",
                "plugins.js",
                vec!["表示本文".to_string()],
                json!({"json_path": "$['parameters']['Message']"}),
            ),
            test_row(
                "CommonEvents.json/1/0/parameters/3/message",
                "event_command",
                "CommonEvents.json",
                vec!["イベント本文".to_string()],
                json!({
                    "command_code": 357,
                    "parameter_json_path": "$['parameters'][3]['message']"
                }),
            ),
            test_row(
                "Items.json/1/note/Flavor",
                "note_tag",
                "Items.json",
                vec!["薬草".to_string()],
                json!({"tag_name": "Flavor", "raw_text": "薬草"}),
            ),
            test_row(
                "nonstandard-data/Unknown.json/$['title']",
                "nonstandard_data",
                "Unknown.json",
                vec!["外部本文".to_string()],
                json!({"json_path": "$['title']", "raw_text": "外部本文"}),
            ),
            test_row(
                "js/plugins/TestPlugin.js/ast:string:19:28:abcdef123456",
                "plugin_source",
                "TestPlugin.js",
                vec![r"源码\n本文".to_string()],
                json!({
                    "selector": "ast:string:19:28:abcdef123456",
                    "raw_text": r"源码\\n本文",
                    "line": 1,
                    "start_index": 19,
                    "end_index": 28
                }),
            ),
        ];

        let fact_payload =
            build_text_fact_storage_payload(&rows, &scope).expect("扩展 domain 文本事实应可构建");

        assert_eq!(fact_payload.text_facts.len(), 5);
        assert_eq!(fact_payload.domain_payloads.len(), 5);
        let payloads = fact_payload
            .domain_payloads
            .iter()
            .map(|payload| {
                let fact = fact_payload
                    .text_facts
                    .iter()
                    .find(|fact| fact.fact_id == payload.fact_id)
                    .expect("payload fact_id 应存在");
                let value: serde_json::Value =
                    serde_json::from_str(&payload.payload_json).expect("payload_json 应是对象");
                (fact.domain.as_str(), value)
            })
            .collect::<std::collections::BTreeMap<_, _>>();

        assert_eq!(
            payloads[domains::PLUGIN_CONFIG],
            json!({"json_path": "$['parameters']['Message']"})
        );
        assert_eq!(
            payloads[domains::EVENT_COMMAND],
            json!({"command_code": 357, "parameter_json_path": "$['parameters'][3]['message']"})
        );
        assert_eq!(payloads[domains::NOTE_TAG], json!({"tag_name": "Flavor"}));
        assert_eq!(
            payloads[domains::NONSTANDARD_DATA],
            json!({"json_path": "$['title']"})
        );
        assert_eq!(
            fact_payload
                .text_facts
                .iter()
                .find(|fact| fact.domain == domains::PLUGIN_SOURCE)
                .expect("插件源码 fact 应存在")
                .raw_text,
            r"源码\\n本文"
        );
    }

    fn test_row(
        location_path: &str,
        source_type: &str,
        source_file: &str,
        original_lines: Vec<String>,
        locator: serde_json::Value,
    ) -> DirectTextIndexRow {
        let source_type_value = source_type.to_string();
        let domain = super::text_fact_domain_for_row_source_type(&source_type_value);
        let payload_json = match domain {
            domains::PLUGIN_CONFIG => {
                json!({"json_path": locator["json_path"].clone()})
            }
            domains::EVENT_COMMAND => json!({
                "command_code": locator["command_code"].clone(),
                "parameter_json_path": locator["parameter_json_path"].clone(),
            }),
            domains::NOTE_TAG => json!({"tag_name": locator["tag_name"].clone()}),
            domains::NONSTANDARD_DATA => json!({"json_path": locator["json_path"].clone()}),
            domains::PLUGIN_SOURCE => json!({
                "line": locator["line"].clone(),
                "start_index": locator["start_index"].clone(),
                "end_index": locator["end_index"].clone(),
            }),
            _ => json!({}),
        }
        .to_string();
        DirectTextIndexRow {
            location_path: location_path.to_string(),
            item_type: "short_text".to_string(),
            role: None,
            original_lines,
            source_line_paths: Vec::new(),
            source_type: source_type_value,
            source_file: source_file.to_string(),
            writable: true,
            source_snapshot_fingerprint: "snapshot-v1".to_string(),
            rules_fingerprint: "rules-v1".to_string(),
            locator_json: locator.to_string(),
            fact_raw_text: locator
                .get("raw_text")
                .and_then(serde_json::Value::as_str)
                .map(str::to_string),
            fact_visible_text: None,
            fact_selector: locator
                .get("selector")
                .and_then(serde_json::Value::as_str)
                .map(str::to_string),
            fact_domain_payload_json: Some(payload_json),
        }
    }

    fn minimal_rebuild_payload() -> RebuildStoragePayload {
        RebuildStoragePayload {
            db_path: "fixture.db".to_string(),
            game_path: "fixture-game".to_string(),
            source_snapshot_fingerprint: Some("snapshot-v1".to_string()),
            rules_fingerprint: Some("rules-v1".to_string()),
            source_language: "ja".to_string(),
            target_language: "zh-Hans".to_string(),
            engine_kind: "mz".to_string(),
            text_rules_setting: json!({
                "source_text_required_pattern": "[\\u3040-\\u30ff]+",
                "source_text_exclusion_profile": "none"
            }),
            rule_candidate_text_rules: RuleCandidateTextRules {
                custom_placeholder_rules: Vec::new(),
                structured_placeholder_rules: vec![NativeStructuredPlaceholderRule {
                    rule_name: "颜色".to_string(),
                    rule_type: "regex".to_string(),
                    pattern_text: r"\\C\[(?P<code>\d+)\](?P<body>.*?)\\C\[0\]".to_string(),
                    translatable_group: "body".to_string(),
                    protected_groups: HashMap::from([("code".to_string(), "{code}".to_string())]),
                }],
                strip_wrapping_punctuation_pairs: vec![("「".to_string(), "」".to_string())],
                source_text_required_pattern: "[\\u3040-\\u30ff]+".to_string(),
                source_text_exclusion_profile: "none".to_string(),
            },
            event_command_scope_codes: vec![357],
            source_text_required_pattern: "[\\u3040-\\u30ff]+".to_string(),
            created_at: "2026-06-05T00:00:00".to_string(),
        }
    }
}
