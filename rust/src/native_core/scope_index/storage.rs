//! Scope/Index Engine 的 SQLite、游戏文件和持久 text index 存储基础。
//!
//! 本模块负责共享 schema 指纹、DB/source 摘要读取，以及 text index 持久写入；
//! 冷重建扫描由 `rebuild` 模块编排并复用这里的存储写入能力。

use rusqlite::{Connection, OpenFlags, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::Digest;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

const CURRENT_SCHEMA_SQL: &str = include_str!("../../../../app/persistence/schema/current.sql");
const CURRENT_SCHEMA_VERSION: i64 = 15;
const SCHEMA_VERSION_KEY: &str = "current";
const TEXT_INDEX_META_KEY: &str = "current";

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
}

#[derive(Debug, Deserialize)]
pub(crate) struct TextIndexMetadataInput {
    pub(crate) source_snapshot_fingerprint: String,
    pub(crate) rules_fingerprint: String,
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
    let mut connection = open_connection_readwrite(Path::new(&payload.db_path))?;
    validate_schema_version(&connection)?;
    write_text_index_storage(&mut connection, payload)?;
    Ok(WriteStorageOutput {
        status: "ok",
        written_item_count: payload.text_index_rows.len(),
        domain_summary_count: payload.domain_summary.len(),
        rule_hit_summary_count: payload.rule_hit_summary.len(),
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

fn write_text_index_storage(
    connection: &mut Connection,
    payload: &WriteStoragePayload,
) -> Result<(), String> {
    let transaction = connection.transaction().map_err(|error| {
        structured_error(
            "scope_index_storage_transaction_failed",
            format!("开启 text index 写入事务失败: {error}"),
        )
    })?;
    for table_name in [
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
        CURRENT_SCHEMA_SQL, CURRENT_SCHEMA_VERSION, current_schema_fingerprint,
        write_scope_index_storage_impl,
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
}
