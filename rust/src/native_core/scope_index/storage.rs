//! Scope/Index Engine 的 SQLite、游戏文件和持久 text index 存储基础。
//!
//! 本模块负责共享 schema 指纹、DB/source 摘要读取，以及 text index 持久写入；
//! 冷重建扫描由 `rebuild` 模块编排并复用这里的存储写入能力。

use rusqlite::{Connection, OpenFlags, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::Digest;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::native_core::text_facts::{
    TEXT_FACT_SCHEMA_VERSION, TextFact, TextFactDomainPayload, TextFactRenderPart, TextFactScope,
};

const CURRENT_SCHEMA_SQL: &str = include_str!("../../../../app/persistence/schema/current.sql");
const CURRENT_SCHEMA_VERSION: i64 = 16;
const SCHEMA_VERSION_KEY: &str = "current";
const TEXT_INDEX_META_KEY: &str = "current";
type TextFactIdentity = (String, String, String, String, String, String);

#[derive(Debug, Deserialize)]
struct InspectStoragePayload {
    db_path: String,
    game_path: String,
}

#[derive(Debug, Serialize)]
struct InspectStorageOutput {
    status: &'static str,
    schema: SchemaSummary,
    database: DatabaseSummary,
    game_files: GameFileSummary,
}

#[derive(Debug, Serialize)]
struct SchemaSummary {
    version: i64,
    schema_fingerprint: String,
}

#[derive(Debug, Serialize)]
struct DatabaseSummary {
    plugin_text_rule_count: i64,
    plugin_source_text_rule_count: i64,
    nonstandard_data_text_rule_count: i64,
    note_tag_text_rule_count: i64,
    event_command_text_rule_group_count: i64,
    event_command_text_rule_path_count: i64,
    mv_virtual_namebox_rule_count: i64,
    placeholder_rule_count: i64,
    structured_placeholder_rule_count: i64,
    source_residual_rule_count: i64,
    translation_item_count: i64,
    translation_quality_error_count: i64,
    text_index_item_count: i64,
}

#[derive(Debug, Serialize)]
struct GameFileSummary {
    content_root: String,
    standard_data_file_count: usize,
    map_data_file_count: usize,
    nonstandard_data_file_count: usize,
    plugins_js_bytes: usize,
    plugin_source_file_count: usize,
    plugin_source_bytes: usize,
    standard_data_file_names: Vec<String>,
    nonstandard_data_file_names: Vec<String>,
    plugin_source_file_names: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct WriteStoragePayload {
    pub(crate) db_path: String,
    pub(crate) metadata: TextIndexMetadataInput,
    pub(crate) text_index_rows: Vec<TextIndexRowInput>,
    pub(crate) scope_summary: ScopeSummaryInput,
    #[serde(default)]
    pub(crate) domain_summary: Vec<DomainSummaryInput>,
    #[serde(default)]
    pub(crate) rule_hit_summary: Vec<RuleHitSummaryInput>,
    #[serde(default)]
    pub(crate) text_fact_scope: Option<TextFactScope>,
    #[serde(default)]
    pub(crate) text_facts: Vec<TextFact>,
    #[serde(default)]
    pub(crate) text_fact_render_parts: Vec<TextFactRenderPart>,
    #[serde(default)]
    pub(crate) text_fact_domain_payloads: Vec<TextFactDomainPayload>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct TextIndexMetadataInput {
    pub(crate) source_snapshot_fingerprint: String,
    pub(crate) rules_fingerprint: String,
    #[serde(default)]
    pub(crate) text_rules_hash: Option<String>,
    pub(crate) item_count: usize,
    #[serde(default)]
    pub(crate) workflow_gate_scope_hashes: BTreeMap<String, String>,
    pub(crate) created_at: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct TextIndexRowInput {
    pub(crate) location_path: String,
    pub(crate) item_type: String,
    pub(crate) role: Option<String>,
    pub(crate) original_lines: Vec<String>,
    #[serde(default)]
    pub(crate) text_fact_raw_text: Option<String>,
    #[serde(default)]
    pub(crate) source_line_paths: Vec<String>,
    pub(crate) source_type: String,
    pub(crate) source_file: String,
    pub(crate) writable: bool,
    pub(crate) source_snapshot_fingerprint: String,
    pub(crate) rules_fingerprint: String,
    pub(crate) locator_json: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ScopeSummaryInput {
    pub(crate) total_count: usize,
    pub(crate) active_count: usize,
    pub(crate) writable_count: usize,
    pub(crate) unwritable_count: usize,
    pub(crate) stale_rule_count: usize,
    pub(crate) native_thread_count: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct DomainSummaryInput {
    pub(crate) domain: String,
    pub(crate) item_count: usize,
    pub(crate) active_count: usize,
    pub(crate) writable_count: usize,
    pub(crate) unwritable_count: usize,
    pub(crate) inactive_rule_hit_count: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RuleHitSummaryInput {
    pub(crate) domain: String,
    pub(crate) rule_key: String,
    pub(crate) hit_count: usize,
    pub(crate) extractable_count: usize,
    pub(crate) writable_count: usize,
    pub(crate) unwritable_count: usize,
}

#[derive(Debug, Serialize)]
pub(crate) struct WriteStorageOutput {
    status: &'static str,
    pub(crate) written_item_count: usize,
    domain_summary_count: usize,
    rule_hit_summary_count: usize,
    pub(crate) text_fact_count: usize,
    pub(crate) render_part_count: usize,
    domain_payload_count: usize,
    pub(crate) scope_key: String,
    pub(crate) scope_hash: String,
    pub(crate) text_fact_schema_version: i64,
}

pub(crate) fn current_schema_fingerprint() -> String {
    sha256_text(CURRENT_SCHEMA_SQL)
}

pub(crate) fn inspect_scope_index_storage_impl(payload_json: &str) -> Result<String, String> {
    let payload: InspectStoragePayload = serde_json::from_str(payload_json).map_err(|error| {
        structured_error(
            "scope_index_storage_payload_invalid",
            format!("Scope/Index storage 输入 JSON 解析失败: {error}"),
        )
    })?;
    let connection = open_connection_readonly(Path::new(&payload.db_path))?;
    validate_schema_version(&connection)?;
    let output = InspectStorageOutput {
        status: "ok",
        schema: SchemaSummary {
            version: CURRENT_SCHEMA_VERSION,
            schema_fingerprint: current_schema_fingerprint(),
        },
        database: read_database_summary(&connection)?,
        game_files: read_game_file_summary(Path::new(&payload.game_path))?,
    };
    serialize_output(&output, "scope_index_storage_inspect")
}

pub(crate) fn write_scope_index_storage_impl(payload_json: &str) -> Result<String, String> {
    let payload: WriteStoragePayload = serde_json::from_str(payload_json).map_err(|error| {
        structured_error(
            "scope_index_storage_payload_invalid",
            format!("Scope/Index storage 写入输入 JSON 解析失败: {error}"),
        )
    })?;
    serialize_output(
        &write_scope_index_storage_direct(&payload)?,
        "scope_index_storage_write",
    )
}

pub(crate) fn write_scope_index_storage_direct(
    payload: &WriteStoragePayload,
) -> Result<WriteStorageOutput, String> {
    if payload.metadata.item_count != payload.text_index_rows.len() {
        return Err(structured_error(
            "scope_index_storage_item_count_mismatch",
            format!(
                "text index 元信息 item_count={} 与 rows 数量 {} 不一致",
                payload.metadata.item_count,
                payload.text_index_rows.len()
            ),
        ));
    }
    let text_fact_scope = effective_text_fact_scope(payload)?;
    validate_text_fact_write_payload(payload, &text_fact_scope)?;
    let mut connection = open_connection_readwrite(Path::new(&payload.db_path))?;
    validate_schema_version(&connection)?;
    write_text_index_storage(&mut connection, payload, &text_fact_scope)?;
    Ok(WriteStorageOutput {
        status: "ok",
        written_item_count: payload.text_index_rows.len(),
        domain_summary_count: payload.domain_summary.len(),
        rule_hit_summary_count: payload.rule_hit_summary.len(),
        text_fact_count: payload.text_facts.len(),
        render_part_count: payload.text_fact_render_parts.len(),
        domain_payload_count: payload.text_fact_domain_payloads.len(),
        scope_key: text_fact_scope.scope_key,
        scope_hash: text_fact_scope.scope_hash,
        text_fact_schema_version: TEXT_FACT_SCHEMA_VERSION,
    })
}

fn open_connection_readonly(db_path: &Path) -> Result<Connection, String> {
    Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|error| {
        structured_error(
            "scope_index_storage_db_open_failed",
            format!("只读打开数据库失败 {}: {error}", db_path.display()),
        )
    })
}

fn open_connection_readwrite(db_path: &Path) -> Result<Connection, String> {
    let connection = Connection::open(db_path).map_err(|error| {
        structured_error(
            "scope_index_storage_db_open_failed",
            format!("打开数据库失败 {}: {error}", db_path.display()),
        )
    })?;
    connection
        .execute("PRAGMA foreign_keys = ON", [])
        .map_err(|error| {
            structured_error(
                "scope_index_storage_db_pragma_failed",
                format!("启用 SQLite 外键失败 {}: {error}", db_path.display()),
            )
        })?;
    Ok(connection)
}

fn validate_schema_version(connection: &Connection) -> Result<(), String> {
    let version = connection
        .query_row(
            "SELECT version FROM schema_version WHERE schema_key = ?1 LIMIT 1",
            [SCHEMA_VERSION_KEY],
            |row| row.get::<_, i64>(0),
        )
        .map_err(|error| {
            structured_error(
                "scope_index_storage_schema_version_unreadable",
                format!("数据库 schema_version 不可读取: {error}"),
            )
        })?;
    if version != CURRENT_SCHEMA_VERSION {
        return Err(structured_error(
            "scope_index_storage_schema_version_mismatch",
            format!("数据库 schema_version={version}，当前要求 {CURRENT_SCHEMA_VERSION}"),
        ));
    }
    Ok(())
}

fn read_database_summary(connection: &Connection) -> Result<DatabaseSummary, String> {
    Ok(DatabaseSummary {
        plugin_text_rule_count: count_table(connection, "plugin_text_rules")?,
        plugin_source_text_rule_count: count_table(connection, "plugin_source_text_rules")?,
        nonstandard_data_text_rule_count: count_table(connection, "nonstandard_data_text_rules")?,
        note_tag_text_rule_count: count_table(connection, "note_tag_text_rules")?,
        event_command_text_rule_group_count: count_table(
            connection,
            "event_command_text_rule_groups",
        )?,
        event_command_text_rule_path_count: count_table(
            connection,
            "event_command_text_rule_paths",
        )?,
        mv_virtual_namebox_rule_count: count_table(connection, "mv_virtual_namebox_rules")?,
        placeholder_rule_count: count_table(connection, "placeholder_rules")?,
        structured_placeholder_rule_count: count_table(connection, "structured_placeholder_rules")?,
        source_residual_rule_count: count_table(connection, "source_residual_rules")?,
        translation_item_count: count_table(connection, "translation_items")?,
        translation_quality_error_count: count_table(connection, "translation_quality_errors")?,
        text_index_item_count: count_table(connection, "text_index_items")?,
    })
}

fn count_table(connection: &Connection, table_name: &str) -> Result<i64, String> {
    let sql = format!("SELECT COUNT(*) FROM [{table_name}]");
    connection
        .query_row(&sql, [], |row| row.get::<_, i64>(0))
        .map_err(|error| {
            structured_error(
                "scope_index_storage_db_read_failed",
                format!("读取表 {table_name} 数量失败: {error}"),
            )
        })
}

fn read_game_file_summary(game_path: &Path) -> Result<GameFileSummary, String> {
    let content_root = resolve_content_root(game_path);
    let data_dir = content_root.join("data");
    let js_dir = content_root.join("js");
    let plugins_js_path = js_dir.join("plugins.js");
    let plugins_js = read_text_file(
        &plugins_js_path,
        "scope_index_storage_plugins_js_read_failed",
    )?;
    let data_files = read_json_data_files(&data_dir)?;
    let plugin_sources = read_plugin_source_files(&js_dir.join("plugins"))?;

    let mut standard_data_file_names = Vec::new();
    let mut nonstandard_data_file_names = Vec::new();
    let mut map_data_file_count = 0usize;
    for file_name in data_files {
        if is_map_data_file(&file_name) {
            map_data_file_count += 1;
        }
        if is_standard_data_file(&file_name) {
            standard_data_file_names.push(file_name);
        } else {
            nonstandard_data_file_names.push(file_name);
        }
    }
    standard_data_file_names.sort();
    nonstandard_data_file_names.sort();

    let plugin_source_bytes = plugin_sources
        .iter()
        .map(|(_, source)| source.len())
        .sum::<usize>();
    let mut plugin_source_file_names = plugin_sources
        .into_iter()
        .map(|(file_name, _)| file_name)
        .collect::<Vec<_>>();
    plugin_source_file_names.sort();
    Ok(GameFileSummary {
        content_root: content_root.to_string_lossy().to_string(),
        standard_data_file_count: standard_data_file_names.len(),
        map_data_file_count,
        nonstandard_data_file_count: nonstandard_data_file_names.len(),
        plugins_js_bytes: plugins_js.len(),
        plugin_source_file_count: plugin_source_file_names.len(),
        plugin_source_bytes,
        standard_data_file_names,
        nonstandard_data_file_names,
        plugin_source_file_names,
    })
}

fn resolve_content_root(game_path: &Path) -> PathBuf {
    let mv_content_root = game_path.join("www");
    if mv_content_root.join("data").is_dir() && mv_content_root.join("js").is_dir() {
        mv_content_root
    } else {
        game_path.to_path_buf()
    }
}

fn read_json_data_files(data_dir: &Path) -> Result<Vec<String>, String> {
    let entries = fs::read_dir(data_dir).map_err(|error| {
        structured_error(
            "scope_index_storage_data_dir_read_failed",
            format!("读取 data 目录失败 {}: {error}", data_dir.display()),
        )
    })?;
    let mut file_names = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|error| {
            structured_error(
                "scope_index_storage_data_dir_read_failed",
                format!("读取 data 目录项失败 {}: {error}", data_dir.display()),
            )
        })?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let file_name = file_name_from_path(&path)?;
        let text = read_text_file(&path, "scope_index_storage_data_file_read_failed")?;
        let _: Value = serde_json::from_str(&text).map_err(|error| {
            structured_error(
                "scope_index_storage_data_json_invalid",
                format!("data 文件 JSON 解析失败 {}: {error}", path.display()),
            )
        })?;
        file_names.push(file_name);
    }
    Ok(file_names)
}

fn read_plugin_source_files(plugin_source_dir: &Path) -> Result<Vec<(String, String)>, String> {
    if !plugin_source_dir.is_dir() {
        return Ok(Vec::new());
    }
    let entries = fs::read_dir(plugin_source_dir).map_err(|error| {
        structured_error(
            "scope_index_storage_plugin_source_dir_read_failed",
            format!(
                "读取插件源码目录失败 {}: {error}",
                plugin_source_dir.display()
            ),
        )
    })?;
    let mut files = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|error| {
            structured_error(
                "scope_index_storage_plugin_source_dir_read_failed",
                format!(
                    "读取插件源码目录项失败 {}: {error}",
                    plugin_source_dir.display()
                ),
            )
        })?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("js") {
            continue;
        }
        let file_name = file_name_from_path(&path)?;
        let source = read_text_file(&path, "scope_index_storage_plugin_source_read_failed")?;
        files.push((file_name, source));
    }
    Ok(files)
}

fn read_text_file(path: &Path, code: &'static str) -> Result<String, String> {
    fs::read_to_string(path).map_err(|error| {
        structured_error(code, format!("读取文件失败 {}: {error}", path.display()))
    })
}

fn file_name_from_path(path: &Path) -> Result<String, String> {
    path.file_name()
        .and_then(|value| value.to_str())
        .map(str::to_string)
        .ok_or_else(|| {
            structured_error(
                "scope_index_storage_path_invalid",
                format!("路径缺少有效文件名: {}", path.display()),
            )
        })
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

fn effective_text_fact_scope(payload: &WriteStoragePayload) -> Result<TextFactScope, String> {
    if let Some(scope) = &payload.text_fact_scope {
        return Ok(scope.clone());
    }
    let text_rules_hash = match &payload.metadata.text_rules_hash {
        Some(value) if !value.trim().is_empty() => value.clone(),
        _ => {
            let text = serde_json::to_string(&payload.metadata.workflow_gate_scope_hashes)
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_payload_invalid",
                        format!("workflow_gate_scope_hashes 序列化失败: {error}"),
                    )
                })?;
            sha256_text(&text)
        }
    };
    Ok(TextFactScope::from_hashes(
        payload.metadata.source_snapshot_fingerprint.clone(),
        payload.metadata.rules_fingerprint.clone(),
        text_rules_hash,
        payload.metadata.created_at.clone(),
    ))
}

fn validate_text_fact_write_payload(
    payload: &WriteStoragePayload,
    scope: &TextFactScope,
) -> Result<(), String> {
    scope
        .validate()
        .map_err(|message| structured_error("scope_index_storage_text_fact_invalid", message))?;
    let has_explicit_text_fact_payload = payload.text_fact_scope.is_some()
        || !payload.text_facts.is_empty()
        || !payload.text_fact_render_parts.is_empty()
        || !payload.text_fact_domain_payloads.is_empty();
    if has_explicit_text_fact_payload && payload.metadata.item_count != payload.text_facts.len() {
        return Err(structured_error(
            "scope_index_storage_text_fact_count_mismatch",
            format!(
                "text index 元信息 item_count={} 与 v2 fact 数量 {} 不一致",
                payload.metadata.item_count,
                payload.text_facts.len()
            ),
        ));
    }

    let mut fact_ids = BTreeSet::new();
    let mut facts_by_id = BTreeMap::new();
    for fact in &payload.text_facts {
        fact.validate().map_err(|message| {
            structured_error("scope_index_storage_text_fact_invalid", message)
        })?;
        if fact.scope_key != scope.scope_key {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!(
                    "text fact v2 scope_key 与当前 scope 不一致: fact_id={}",
                    fact.fact_id
                ),
            ));
        }
        if fact.schema_version != scope.schema_version {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!(
                    "text fact v2 schema_version 与当前 scope 不一致: fact_id={}",
                    fact.fact_id
                ),
            ));
        }
        if !fact_ids.insert(fact.fact_id.clone()) {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!("text fact v2 fact_id 重复: {}", fact.fact_id),
            ));
        }
        facts_by_id.insert(fact.fact_id.clone(), fact);
    }
    let mut render_part_keys = BTreeSet::new();
    let mut render_parts_by_fact_id: BTreeMap<String, Vec<&TextFactRenderPart>> = BTreeMap::new();
    for part in &payload.text_fact_render_parts {
        part.validate().map_err(|message| {
            structured_error("scope_index_storage_text_fact_invalid", message)
        })?;
        if !fact_ids.contains(&part.fact_id) {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!(
                    "text fact v2 render part 引用了未知 fact_id: {}",
                    part.fact_id
                ),
            ));
        }
        let key = (part.fact_id.clone(), part.part_order);
        if !render_part_keys.insert(key) {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!(
                    "text fact v2 render part 重复: fact_id={}, part_order={}",
                    part.fact_id, part.part_order
                ),
            ));
        }
        render_parts_by_fact_id
            .entry(part.fact_id.clone())
            .or_default()
            .push(part);
    }
    validate_render_parts_rebuild_raw_text(&facts_by_id, &mut render_parts_by_fact_id)?;

    if has_explicit_text_fact_payload {
        validate_text_fact_raw_identity_overrides(payload, &render_parts_by_fact_id)?;
        validate_text_index_fact_identities(payload)?;
    }

    let mut payload_fact_ids = BTreeSet::new();
    for domain_payload in &payload.text_fact_domain_payloads {
        domain_payload.validate().map_err(|message| {
            structured_error("scope_index_storage_text_fact_invalid", message)
        })?;
        if !fact_ids.contains(&domain_payload.fact_id) {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!(
                    "text fact v2 domain payload 引用了未知 fact_id: {}",
                    domain_payload.fact_id
                ),
            ));
        }
        if !payload_fact_ids.insert(domain_payload.fact_id.clone()) {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!(
                    "text fact v2 domain payload 重复: fact_id={}",
                    domain_payload.fact_id
                ),
            ));
        }
    }
    Ok(())
}

fn validate_text_index_fact_identities(payload: &WriteStoragePayload) -> Result<(), String> {
    let text_index_identities = text_index_identity_counts(&payload.text_index_rows);
    let text_fact_identities = text_fact_identity_counts(&payload.text_facts);
    if text_index_identities != text_fact_identities {
        return Err(structured_error(
            "scope_index_storage_text_fact_identity_mismatch",
            "warm index rows 与 v2 facts 的文本身份不一致，拒绝写入混合来源数据".to_string(),
        ));
    }
    Ok(())
}

fn validate_text_fact_raw_identity_overrides(
    payload: &WriteStoragePayload,
    render_parts_by_fact_id: &BTreeMap<String, Vec<&TextFactRenderPart>>,
) -> Result<(), String> {
    let mut facts_by_identity: BTreeMap<TextFactIdentity, Vec<&TextFact>> = BTreeMap::new();
    for fact in &payload.text_facts {
        facts_by_identity
            .entry(text_fact_identity(fact))
            .or_default()
            .push(fact);
    }
    for row in &payload.text_index_rows {
        let Some(raw_text) = &row.text_fact_raw_text else {
            continue;
        };
        let row_translatable_text = row.original_lines.join("\n");
        let identity = text_index_identity(row, raw_text.clone());
        let Some(facts) = facts_by_identity.get(&identity) else {
            return Err(text_fact_identity_mismatch_error());
        };
        if facts.len() != 1 {
            return Err(text_fact_identity_mismatch_error());
        }
        let fact = facts[0];
        if fact.translatable_text != row_translatable_text {
            return Err(text_fact_identity_mismatch_error());
        }
        if render_parts_by_fact_id
            .get(&fact.fact_id)
            .is_none_or(Vec::is_empty)
        {
            return Err(text_fact_identity_mismatch_error());
        }
    }
    Ok(())
}

fn text_fact_identity_mismatch_error() -> String {
    structured_error(
        "scope_index_storage_text_fact_identity_mismatch",
        "warm index rows 与 v2 facts 的文本身份不一致，拒绝写入混合来源数据".to_string(),
    )
}

fn text_index_identity_counts(rows: &[TextIndexRowInput]) -> BTreeMap<TextFactIdentity, usize> {
    let mut counts = BTreeMap::new();
    for row in rows {
        let identity = text_index_identity(
            row,
            row.text_fact_raw_text
                .clone()
                .unwrap_or_else(|| row.original_lines.join("\n")),
        );
        *counts.entry(identity).or_insert(0) += 1;
    }
    counts
}

fn text_index_identity(row: &TextIndexRowInput, raw_text: String) -> TextFactIdentity {
    (
        row.location_path.clone(),
        row.source_file.clone(),
        row.source_type.clone(),
        row.item_type.clone(),
        row.role.clone().unwrap_or_default(),
        raw_text,
    )
}

fn text_fact_identity_counts(facts: &[TextFact]) -> BTreeMap<TextFactIdentity, usize> {
    let mut counts = BTreeMap::new();
    for fact in facts {
        let identity = text_fact_identity(fact);
        *counts.entry(identity).or_insert(0) += 1;
    }
    counts
}

fn text_fact_identity(fact: &TextFact) -> TextFactIdentity {
    (
        fact.location_path.clone(),
        fact.source_file.clone(),
        fact.source_type.clone(),
        fact.item_type.clone(),
        fact.role.clone(),
        fact.raw_text.clone(),
    )
}

fn validate_render_parts_rebuild_raw_text(
    facts_by_id: &BTreeMap<String, &TextFact>,
    render_parts_by_fact_id: &mut BTreeMap<String, Vec<&TextFactRenderPart>>,
) -> Result<(), String> {
    for (fact_id, parts) in render_parts_by_fact_id {
        parts.sort_by_key(|part| part.part_order);
        for (expected_order, part) in parts.iter().enumerate() {
            if part.part_order != expected_order as i64 {
                return Err(structured_error(
                    "scope_index_storage_text_fact_invalid",
                    format!(
                        "text fact v2 render part_order 必须从 0 连续: fact_id={fact_id}, expected={expected_order}, actual={}",
                        part.part_order
                    ),
                ));
            }
        }
        let rebuilt_raw_text = parts
            .iter()
            .map(|part| part.raw_text.as_str())
            .collect::<String>();
        let Some(fact) = facts_by_id.get(fact_id) else {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!("text fact v2 render part 引用了未知 fact_id: {fact_id}"),
            ));
        };
        if rebuilt_raw_text != fact.raw_text {
            return Err(structured_error(
                "scope_index_storage_text_fact_invalid",
                format!("text fact v2 render parts 无法重建 raw_text: fact_id={fact_id}"),
            ));
        }
    }
    Ok(())
}

fn write_text_index_storage(
    connection: &mut Connection,
    payload: &WriteStoragePayload,
    text_fact_scope: &TextFactScope,
) -> Result<(), String> {
    let transaction = connection.transaction().map_err(|error| {
        structured_error(
            "scope_index_storage_transaction_failed",
            format!("开启 text index 写入事务失败: {error}"),
        )
    })?;
    for table_name in [
        "text_fact_domain_payloads_v2",
        "text_fact_render_parts_v2",
        "text_facts_v2",
        "text_fact_scope_v2",
        "text_index_invalidations",
        "text_index_rule_hit_summary",
        "text_index_domain_summary",
        "text_index_scope_summary",
        "text_index_items",
        "text_index_meta",
    ] {
        transaction
            .execute(&format!("DELETE FROM [{table_name}]"), [])
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("清空 {table_name} 失败: {error}"),
                )
            })?;
    }

    transaction
        .execute(
            "INSERT OR REPLACE INTO text_fact_scope_v2 \
             (scope_key, schema_version, scope_hash, source_snapshot_hash, rule_hash, text_rules_hash, created_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                text_fact_scope.scope_key,
                text_fact_scope.schema_version,
                text_fact_scope.scope_hash,
                text_fact_scope.source_snapshot_hash,
                text_fact_scope.rule_hash,
                text_fact_scope.text_rules_hash,
                text_fact_scope.created_at,
            ],
        )
        .map_err(|error| {
            structured_error(
                "scope_index_storage_write_failed",
                format!("写入 text_fact_scope_v2 失败: {error}"),
            )
        })?;

    {
        let mut insert_fact_statement = transaction
            .prepare_cached(
                "INSERT INTO text_facts_v2 \
                 (fact_id, schema_version, domain, location_path, source_file, source_type, item_type, role, selector, raw_text, visible_text, translatable_text, raw_hash, visible_hash, translatable_hash, scope_key) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("准备 text_facts_v2 写入语句失败: {error}"),
                )
            })?;
        for fact in &payload.text_facts {
            insert_fact_statement
                .execute(params![
                    fact.fact_id,
                    fact.schema_version,
                    fact.domain,
                    fact.location_path,
                    fact.source_file,
                    fact.source_type,
                    fact.item_type,
                    fact.role,
                    fact.selector,
                    fact.raw_text,
                    fact.visible_text,
                    fact.translatable_text,
                    fact.raw_hash,
                    fact.visible_hash,
                    fact.translatable_hash,
                    fact.scope_key,
                ])
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_write_failed",
                        format!("写入 text_facts_v2 失败 {}: {error}", fact.fact_id),
                    )
                })?;
        }
    }

    {
        let mut insert_render_part_statement = transaction
            .prepare_cached(
                "INSERT INTO text_fact_render_parts_v2 \
                 (fact_id, part_order, part_kind, raw_text, semantic_text, template_key) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("准备 text_fact_render_parts_v2 写入语句失败: {error}"),
                )
            })?;
        for part in &payload.text_fact_render_parts {
            insert_render_part_statement
                .execute(params![
                    part.fact_id,
                    part.part_order,
                    part.part_kind,
                    part.raw_text,
                    part.semantic_text,
                    part.template_key,
                ])
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_write_failed",
                        format!(
                            "写入 text_fact_render_parts_v2 失败 {}/{}: {error}",
                            part.fact_id, part.part_order
                        ),
                    )
                })?;
        }
    }

    {
        let mut insert_payload_statement = transaction
            .prepare_cached(
                "INSERT INTO text_fact_domain_payloads_v2 \
                 (fact_id, payload_json) \
                 VALUES (?1, ?2)",
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("准备 text_fact_domain_payloads_v2 写入语句失败: {error}"),
                )
            })?;
        for domain_payload in &payload.text_fact_domain_payloads {
            insert_payload_statement
                .execute(params![domain_payload.fact_id, domain_payload.payload_json])
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_write_failed",
                        format!(
                            "写入 text_fact_domain_payloads_v2 失败 {}: {error}",
                            domain_payload.fact_id
                        ),
                    )
                })?;
        }
    }

    let workflow_gate_scope_hashes =
        serde_json::to_string(&payload.metadata.workflow_gate_scope_hashes).map_err(|error| {
            structured_error(
                "scope_index_storage_payload_invalid",
                format!("workflow_gate_scope_hashes 序列化失败: {error}"),
            )
        })?;
    transaction
        .execute(
            "INSERT OR REPLACE INTO text_index_meta \
             (index_key, source_snapshot_fingerprint, rules_fingerprint, item_count, workflow_gate_scope_hashes, created_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                TEXT_INDEX_META_KEY,
                payload.metadata.source_snapshot_fingerprint,
                payload.metadata.rules_fingerprint,
                payload.metadata.item_count as i64,
                workflow_gate_scope_hashes,
                payload.metadata.created_at,
            ],
        )
        .map_err(|error| {
            structured_error(
                "scope_index_storage_write_failed",
                format!("写入 text_index_meta 失败: {error}"),
            )
        })?;

    {
        let mut insert_item_statement = transaction
            .prepare_cached(
                "INSERT INTO text_index_items \
                 (location_path, item_type, role, original_lines, source_line_paths, source_type, source_file, writable, source_snapshot_fingerprint, rules_fingerprint, locator_json) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("准备 text_index_items 写入语句失败: {error}"),
                )
            })?;
        for row in &payload.text_index_rows {
            let original_lines = serde_json::to_string(&row.original_lines).map_err(|error| {
                structured_error(
                    "scope_index_storage_payload_invalid",
                    format!("original_lines 序列化失败 {}: {error}", row.location_path),
                )
            })?;
            let source_line_paths =
                serde_json::to_string(&row.source_line_paths).map_err(|error| {
                    structured_error(
                        "scope_index_storage_payload_invalid",
                        format!(
                            "source_line_paths 序列化失败 {}: {error}",
                            row.location_path
                        ),
                    )
                })?;
            insert_item_statement
                .execute(params![
                    row.location_path,
                    row.item_type,
                    row.role,
                    original_lines,
                    source_line_paths,
                    row.source_type,
                    row.source_file,
                    if row.writable { 1 } else { 0 },
                    row.source_snapshot_fingerprint,
                    row.rules_fingerprint,
                    row.locator_json,
                ])
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_write_failed",
                        format!("写入 text_index_items 失败 {}: {error}", row.location_path),
                    )
                })?;
        }
    }

    transaction
        .execute(
            "INSERT OR REPLACE INTO text_index_scope_summary \
             (index_key, total_count, active_count, writable_count, unwritable_count, stale_rule_count, native_thread_count) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                TEXT_INDEX_META_KEY,
                payload.scope_summary.total_count as i64,
                payload.scope_summary.active_count as i64,
                payload.scope_summary.writable_count as i64,
                payload.scope_summary.unwritable_count as i64,
                payload.scope_summary.stale_rule_count as i64,
                payload.scope_summary.native_thread_count as i64,
            ],
        )
        .map_err(|error| {
            structured_error(
                "scope_index_storage_write_failed",
                format!("写入 text_index_scope_summary 失败: {error}"),
            )
        })?;

    {
        let mut insert_domain_statement = transaction
            .prepare_cached(
                "INSERT INTO text_index_domain_summary \
                 (domain, item_count, active_count, writable_count, unwritable_count, inactive_rule_hit_count) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("准备 text_index_domain_summary 写入语句失败: {error}"),
                )
            })?;
        for row in &payload.domain_summary {
            insert_domain_statement
                .execute(params![
                    row.domain,
                    row.item_count as i64,
                    row.active_count as i64,
                    row.writable_count as i64,
                    row.unwritable_count as i64,
                    row.inactive_rule_hit_count as i64,
                ])
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_write_failed",
                        format!(
                            "写入 text_index_domain_summary 失败 {}: {error}",
                            row.domain
                        ),
                    )
                })?;
        }
    }

    {
        let mut insert_rule_hit_statement = transaction
            .prepare_cached(
                "INSERT INTO text_index_rule_hit_summary \
                 (domain, rule_key, hit_count, extractable_count, writable_count, unwritable_count) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            )
            .map_err(|error| {
                structured_error(
                    "scope_index_storage_write_failed",
                    format!("准备 text_index_rule_hit_summary 写入语句失败: {error}"),
                )
            })?;
        for row in &payload.rule_hit_summary {
            insert_rule_hit_statement
                .execute(params![
                    row.domain,
                    row.rule_key,
                    row.hit_count as i64,
                    row.extractable_count as i64,
                    row.writable_count as i64,
                    row.unwritable_count as i64,
                ])
                .map_err(|error| {
                    structured_error(
                        "scope_index_storage_write_failed",
                        format!(
                            "写入 text_index_rule_hit_summary 失败 {}/{}: {error}",
                            row.domain, row.rule_key
                        ),
                    )
                })?;
        }
    }

    transaction.commit().map_err(|error| {
        structured_error(
            "scope_index_storage_transaction_failed",
            format!("提交 text index 写入事务失败: {error}"),
        )
    })
}

fn serialize_output<T: Serialize>(output: &T, label: &str) -> Result<String, String> {
    serde_json::to_string(output).map_err(|error| {
        structured_error(
            "scope_index_storage_output_failed",
            format!("{label} 输出 JSON 序列化失败: {error}"),
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

fn sha256_text(text: &str) -> String {
    let mut hasher = sha2::Sha256::new();
    hasher.update(text.as_bytes());
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::{
        CURRENT_SCHEMA_SQL, CURRENT_SCHEMA_VERSION, WriteStoragePayload,
        current_schema_fingerprint, write_scope_index_storage_direct,
        write_scope_index_storage_impl,
    };
    use crate::native_core::text_facts::{
        TextFact, TextFactDomainPayload, TextFactInput, TextFactRenderPart, TextFactScope, domains,
    };
    use rusqlite::Connection;
    use serde_json::{Value, json};
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn shared_schema_resource_creates_current_schema_version() {
        let connection = Connection::open_in_memory().expect("内存数据库应可打开");
        connection
            .execute_batch(CURRENT_SCHEMA_SQL)
            .expect("共享 schema SQL 应可执行");
        let version: i64 = connection
            .query_row(
                "SELECT version FROM schema_version WHERE schema_key = 'current'",
                [],
                |row| row.get(0),
            )
            .expect("schema_version 应可读取");
        assert_eq!(version, CURRENT_SCHEMA_VERSION);
        assert_eq!(current_schema_fingerprint().len(), 64);
    }

    #[test]
    fn write_scope_index_storage_writes_rows_and_summaries() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_scope_storage_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let payload = json!({
            "db_path": db_path.to_string_lossy(),
            "metadata": {
                "source_snapshot_fingerprint": "snapshot-v1",
                "rules_fingerprint": "rules-v1",
                "item_count": 1,
                "workflow_gate_scope_hashes": {"plugin_text_rules": "hash-v1"},
                "created_at": "2026-06-05T00:00:00"
            },
            "text_index_rows": [
                {
                    "location_path": "System.json/gameTitle",
                    "item_type": "short_text",
                    "role": null,
                    "original_lines": ["Fixture"],
                    "source_line_paths": [],
                    "source_type": "standard_data",
                    "source_file": "System.json",
                    "writable": true,
                    "source_snapshot_fingerprint": "snapshot-v1",
                    "rules_fingerprint": "rules-v1",
                    "locator_json": "{\"kind\":\"standard_data\"}"
                }
            ],
            "scope_summary": {
                "total_count": 1,
                "active_count": 1,
                "writable_count": 1,
                "unwritable_count": 0,
                "stale_rule_count": 0,
                "native_thread_count": 4
            },
            "domain_summary": [
                {
                    "domain": "standard_data",
                    "item_count": 1,
                    "active_count": 1,
                    "writable_count": 1,
                    "unwritable_count": 0,
                    "inactive_rule_hit_count": 0
                }
            ],
            "rule_hit_summary": []
        });

        let output = write_scope_index_storage_impl(&payload.to_string())
            .expect("Rust 应能直接写入 text index 存储");
        let value: Value = serde_json::from_str(&output).expect("输出应是 JSON");
        assert_eq!(value["written_item_count"], json!(1));

        {
            let connection = Connection::open(&db_path).expect("测试数据库应可重新打开");
            let item_count: i64 = connection
                .query_row("SELECT COUNT(*) FROM text_index_items", [], |row| {
                    row.get(0)
                })
                .expect("text_index_items 应可读取");
            let summary_count: i64 = connection
                .query_row("SELECT COUNT(*) FROM text_index_scope_summary", [], |row| {
                    row.get(0)
                })
                .expect("text_index_scope_summary 应可读取");
            assert_eq!(item_count, 1);
            assert_eq!(summary_count, 1);
        }

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_writes_text_fact_v2_rows() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_storage_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = TextFact::from_input(
            TextFactInput {
                domain: domains::MV_VIRTUAL_NAMEBOX.to_string(),
                location_path: "Map001.json/events/1/pages/0/list/0".to_string(),
                source_file: "Map001.json".to_string(),
                source_type: "event_command".to_string(),
                item_type: "long_text".to_string(),
                role: "Dan".to_string(),
                selector: "event:1/page:0/list:0".to_string(),
                raw_text: "\\n<Dan:> Hello".to_string(),
                visible_text: "\\n<Dan:> Hello".to_string(),
                translatable_text: "Hello".to_string(),
            },
            scope.scope_key.clone(),
        )
        .expect("MV 虚拟名字框 fact 应可创建");

        let payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact.clone()],
            vec![
                TextFactRenderPart::new(
                    fact.fact_id.clone(),
                    0,
                    "literal",
                    "\\n<",
                    "\\n<",
                    "prefix",
                ),
                TextFactRenderPart::new(
                    fact.fact_id.clone(),
                    1,
                    "speaker",
                    "Dan",
                    "Dan",
                    "speaker",
                ),
                TextFactRenderPart::new(
                    fact.fact_id.clone(),
                    2,
                    "literal",
                    ":> ",
                    ":> ",
                    "separator",
                ),
                TextFactRenderPart::new(
                    fact.fact_id.clone(),
                    3,
                    "translated_body",
                    "Hello",
                    "Hello",
                    "body",
                ),
            ],
            vec![TextFactDomainPayload::new(
                fact.fact_id.clone(),
                json!({"speaker_policy": "translate"}).to_string(),
            )],
        );

        let output = write_scope_index_storage_direct(&payload).expect("写入 v2 fact 应成功");
        assert_eq!(output.text_fact_count, 1);
        assert_eq!(output.render_part_count, 4);
        assert_eq!(output.scope_key, fact.scope_key);

        {
            let connection = Connection::open(&db_path).expect("测试数据库应可重新打开");
            let fact_count: i64 = connection
                .query_row("SELECT COUNT(*) FROM text_facts_v2", [], |row| row.get(0))
                .expect("text_facts_v2 应可读取");
            let render_part_count: i64 = connection
                .query_row(
                    "SELECT COUNT(*) FROM text_fact_render_parts_v2",
                    [],
                    |row| row.get(0),
                )
                .expect("text_fact_render_parts_v2 应可读取");
            let payload_count: i64 = connection
                .query_row(
                    "SELECT COUNT(*) FROM text_fact_domain_payloads_v2",
                    [],
                    |row| row.get(0),
                )
                .expect("text_fact_domain_payloads_v2 应可读取");
            assert_eq!(fact_count, 1);
            assert_eq!(render_part_count, 4);
            assert_eq!(payload_count, 1);
        }

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_text_fact_count_mismatch() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_mismatch_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let mut payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            Vec::new(),
            Vec::new(),
            Vec::new(),
        );
        payload.metadata.item_count = 1;
        payload.text_index_rows.push(dummy_text_index_row());

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("text index item_count 与 v2 fact 数量不一致必须拒绝");
        assert!(error.contains("scope_index_storage_text_fact_count_mismatch"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_replaces_old_text_fact_v2_scope_atomically() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_replace_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let first_scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let first_fact = TextFact::from_input(
            TextFactInput {
                domain: domains::STANDARD_DATA.to_string(),
                location_path: "System.json/gameTitle".to_string(),
                source_file: "System.json".to_string(),
                source_type: "standard_data".to_string(),
                item_type: "short_text".to_string(),
                role: String::new(),
                selector: "gameTitle".to_string(),
                raw_text: "旧标题".to_string(),
                visible_text: "旧标题".to_string(),
                translatable_text: "旧标题".to_string(),
            },
            first_scope.scope_key.clone(),
        )
        .expect("旧 fact 应可创建");
        let first_payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            first_scope,
            vec![first_fact],
            Vec::new(),
            Vec::new(),
        );
        write_scope_index_storage_direct(&first_payload).expect("第一次写入应成功");

        let second_scope = TextFactScope::from_hashes(
            "snapshot-v2".to_string(),
            "rules-v2".to_string(),
            "text-rules-v2".to_string(),
            "2026-06-05T00:01:00".to_string(),
        );
        let second_payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            second_scope.clone(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        );
        write_scope_index_storage_direct(&second_payload).expect("第二次写入应成功");

        {
            let connection = Connection::open(&db_path).expect("测试数据库应可重新打开");
            let fact_count: i64 = connection
                .query_row("SELECT COUNT(*) FROM text_facts_v2", [], |row| row.get(0))
                .expect("text_facts_v2 应可读取");
            let scope_key: String = connection
                .query_row("SELECT scope_key FROM text_fact_scope_v2", [], |row| {
                    row.get(0)
                })
                .expect("text_fact_scope_v2 应可读取");
            assert_eq!(fact_count, 0);
            assert_eq!(scope_key, second_scope.scope_key);
        }

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_text_index_fact_identity_mismatch() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_identity_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = standard_text_fact(&scope, "System.json/gameTitle", "Fixture");
        let mut payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact],
            Vec::new(),
            Vec::new(),
        );
        payload.text_index_rows[0].location_path = "System.json/currencyUnit".to_string();

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("warm index 与 v2 fact 身份不一致必须拒绝");
        assert!(error.contains("scope_index_storage_text_fact_identity_mismatch"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_text_fact_raw_identity_mismatch_without_override() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_raw_identity_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = TextFact::from_input(
            TextFactInput {
                domain: domains::MV_VIRTUAL_NAMEBOX.to_string(),
                location_path: "Map001.json/events/1/pages/0/list/0".to_string(),
                source_file: "Map001.json".to_string(),
                source_type: "event_command".to_string(),
                item_type: "long_text".to_string(),
                role: "Dan".to_string(),
                selector: "event:1/page:0/list:0".to_string(),
                raw_text: "\\n<Dan:> Hello".to_string(),
                visible_text: "\\n<Dan:> Hello".to_string(),
                translatable_text: "Hello".to_string(),
            },
            scope.scope_key.clone(),
        )
        .expect("MV 虚拟名字框 fact 应可创建");
        let mut payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact],
            Vec::new(),
            Vec::new(),
        );
        payload.text_index_rows[0].original_lines = vec!["Hello".to_string()];

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("未显式声明 raw 身份时，warm index 与 fact raw_text 不一致必须拒绝");
        assert!(error.contains("scope_index_storage_text_fact_identity_mismatch"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_accepts_explicit_text_fact_raw_identity_for_mv_split() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_raw_identity_override_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = TextFact::from_input(
            TextFactInput {
                domain: domains::MV_VIRTUAL_NAMEBOX.to_string(),
                location_path: "Map001.json/events/1/pages/0/list/0".to_string(),
                source_file: "Map001.json".to_string(),
                source_type: "event_command".to_string(),
                item_type: "long_text".to_string(),
                role: "Dan".to_string(),
                selector: "event:1/page:0/list:0".to_string(),
                raw_text: "\\n<Dan:> Hello".to_string(),
                visible_text: "\\n<Dan:> Hello".to_string(),
                translatable_text: "Hello".to_string(),
            },
            scope.scope_key.clone(),
        )
        .expect("MV 虚拟名字框 fact 应可创建");
        let fact_id = fact.fact_id.clone();
        let mut payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact],
            vec![
                TextFactRenderPart::new(fact_id.clone(), 0, "literal", "\\n<", "\\n<", "prefix"),
                TextFactRenderPart::new(fact_id.clone(), 1, "speaker", "Dan", "Dan", "speaker"),
                TextFactRenderPart::new(fact_id.clone(), 2, "literal", ":> ", ":> ", "separator"),
                TextFactRenderPart::new(fact_id, 3, "translated_body", "Hello", "Hello", "body"),
            ],
            Vec::new(),
        );
        payload.text_index_rows[0].original_lines = vec!["Hello".to_string()];
        payload.text_index_rows[0].text_fact_raw_text = Some("\\n<Dan:> Hello".to_string());

        let output = write_scope_index_storage_direct(&payload)
            .expect("显式 raw 身份与 fact raw_text 一致时应可写入");
        assert_eq!(output.text_fact_count, 1);

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_raw_identity_override_when_translatable_mismatches() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_non_mv_override_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = standard_text_fact(&scope, "System.json/gameTitle", "Fixture");
        let mut payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact.clone()],
            vec![TextFactRenderPart::new(
                fact.fact_id.clone(),
                0,
                "translated_body",
                "Fixture",
                "Fixture",
                "body",
            )],
            Vec::new(),
        );
        payload.text_index_rows[0].original_lines = vec!["Other".to_string()];
        payload.text_index_rows[0].text_fact_raw_text = Some("Fixture".to_string());

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("raw override 不能绕过 translatable_text 身份不一致");
        assert!(error.contains("scope_index_storage_text_fact_identity_mismatch"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_mv_raw_identity_override_without_render_parts() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_mv_override_without_parts_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = TextFact::from_input(
            TextFactInput {
                domain: domains::MV_VIRTUAL_NAMEBOX.to_string(),
                location_path: "Map001.json/events/1/pages/0/list/0".to_string(),
                source_file: "Map001.json".to_string(),
                source_type: "event_command".to_string(),
                item_type: "long_text".to_string(),
                role: "Dan".to_string(),
                selector: "event:1/page:0/list:0".to_string(),
                raw_text: "\\n<Dan:> Hello".to_string(),
                visible_text: "\\n<Dan:> Hello".to_string(),
                translatable_text: "Hello".to_string(),
            },
            scope.scope_key.clone(),
        )
        .expect("MV 虚拟名字框 fact 应可创建");
        let mut payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact],
            Vec::new(),
            Vec::new(),
        );
        payload.text_index_rows[0].original_lines = vec!["Hello".to_string()];
        payload.text_index_rows[0].text_fact_raw_text = Some("\\n<Dan:> Hello".to_string());

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("MV raw override 必须有 render parts 重建 raw_text");
        assert!(error.contains("scope_index_storage_text_fact_identity_mismatch"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_non_contiguous_render_parts() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_part_gap_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = standard_text_fact(&scope, "System.json/gameTitle", "Fixture");
        let payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact.clone()],
            vec![
                TextFactRenderPart::new(fact.fact_id.clone(), 0, "literal", "Fix", "Fix", "a"),
                TextFactRenderPart::new(
                    fact.fact_id.clone(),
                    2,
                    "translated_body",
                    "ture",
                    "ture",
                    "b",
                ),
            ],
            Vec::new(),
        );

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("render part_order 不连续必须拒绝");
        assert!(error.contains("scope_index_storage_text_fact_invalid"));
        assert!(error.contains("part_order"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    #[test]
    fn write_scope_index_storage_rejects_render_parts_not_rebuilding_raw_text() {
        let fixture = std::env::temp_dir().join(format!(
            "att_mz_text_fact_part_raw_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("系统时间应晚于 UNIX_EPOCH")
                .as_nanos()
        ));
        fs::create_dir_all(&fixture).expect("测试目录应可创建");
        let db_path = fixture.join("game.db");
        {
            let connection = Connection::open(&db_path).expect("测试数据库应可创建");
            connection
                .execute_batch(CURRENT_SCHEMA_SQL)
                .expect("共享 schema SQL 应可执行");
        }

        let scope = TextFactScope::from_hashes(
            "snapshot-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );
        let fact = standard_text_fact(&scope, "System.json/gameTitle", "Fixture");
        let payload = text_fact_payload(
            db_path.to_string_lossy().to_string(),
            scope,
            vec![fact.clone()],
            vec![TextFactRenderPart::new(
                fact.fact_id.clone(),
                0,
                "translated_body",
                "Other",
                "Other",
                "body",
            )],
            Vec::new(),
        );

        let error = write_scope_index_storage_direct(&payload)
            .expect_err("render parts 无法重建 raw_text 必须拒绝");
        assert!(error.contains("scope_index_storage_text_fact_invalid"));
        assert!(error.contains("raw_text"));

        fs::remove_dir_all(fixture).expect("测试目录应可清理");
    }

    fn text_fact_payload(
        db_path: String,
        scope: TextFactScope,
        text_facts: Vec<TextFact>,
        text_fact_render_parts: Vec<TextFactRenderPart>,
        text_fact_domain_payloads: Vec<TextFactDomainPayload>,
    ) -> WriteStoragePayload {
        let text_index_rows = text_facts
            .iter()
            .map(|fact| super::TextIndexRowInput {
                location_path: fact.location_path.clone(),
                item_type: fact.item_type.clone(),
                role: if fact.role.is_empty() {
                    None
                } else {
                    Some(fact.role.clone())
                },
                original_lines: vec![fact.raw_text.clone()],
                text_fact_raw_text: None,
                source_line_paths: Vec::new(),
                source_type: fact.source_type.clone(),
                source_file: fact.source_file.clone(),
                writable: true,
                source_snapshot_fingerprint: scope.source_snapshot_hash.clone(),
                rules_fingerprint: scope.rule_hash.clone(),
                locator_json: "{}".to_string(),
            })
            .collect::<Vec<_>>();
        WriteStoragePayload {
            db_path,
            metadata: super::TextIndexMetadataInput {
                source_snapshot_fingerprint: scope.source_snapshot_hash.clone(),
                rules_fingerprint: scope.rule_hash.clone(),
                text_rules_hash: Some(scope.text_rules_hash.clone()),
                item_count: text_index_rows.len(),
                workflow_gate_scope_hashes: Default::default(),
                created_at: scope.created_at.clone(),
            },
            text_index_rows,
            scope_summary: super::ScopeSummaryInput {
                total_count: 0,
                active_count: 0,
                writable_count: 0,
                unwritable_count: 0,
                stale_rule_count: 0,
                native_thread_count: 1,
            },
            domain_summary: Vec::new(),
            rule_hit_summary: Vec::new(),
            text_fact_scope: Some(scope),
            text_facts,
            text_fact_render_parts,
            text_fact_domain_payloads,
        }
    }

    fn dummy_text_index_row() -> super::TextIndexRowInput {
        super::TextIndexRowInput {
            location_path: "System.json/gameTitle".to_string(),
            item_type: "short_text".to_string(),
            role: None,
            original_lines: vec!["Fixture".to_string()],
            text_fact_raw_text: None,
            source_line_paths: Vec::new(),
            source_type: "standard_data".to_string(),
            source_file: "System.json".to_string(),
            writable: true,
            source_snapshot_fingerprint: "snapshot-v1".to_string(),
            rules_fingerprint: "rules-v1".to_string(),
            locator_json: "{}".to_string(),
        }
    }

    fn standard_text_fact(scope: &TextFactScope, location_path: &str, raw_text: &str) -> TextFact {
        TextFact::from_input(
            TextFactInput {
                domain: domains::STANDARD_DATA.to_string(),
                location_path: location_path.to_string(),
                source_file: "System.json".to_string(),
                source_type: "standard_data".to_string(),
                item_type: "short_text".to_string(),
                role: String::new(),
                selector: location_path.to_string(),
                raw_text: raw_text.to_string(),
                visible_text: raw_text.to_string(),
                translatable_text: raw_text.to_string(),
            },
            scope.scope_key.clone(),
        )
        .expect("标准 data fact 应可创建")
    }
}
