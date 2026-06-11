use super::models::{
    MvVirtualNameboxFactTemplate, MvVirtualNameboxRule, MvVirtualSpeakerPolicy,
    PluginSourceTextRule, TextFactRenderPart, TranslationItem,
};
use crate::native_core::models::NativeSourceResidualRule;
use crate::native_core::rule_runtime::adapters::mv_virtual_namebox::compile_mv_virtual_namebox_pattern;
use crate::native_core::text_facts::CURRENT_TEXT_FACT_CONTRACT_VERSION;
use rusqlite::{Connection, OpenFlags, params_from_iter};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::path::Path;

const SQLITE_IN_CLAUSE_CHUNK_SIZE: usize = 500;
const WRITE_BACK_TEXT_FACT_DOMAINS: &[&str] = &[
    "standard_data",
    "mv_virtual_namebox",
    "plugin_config",
    "event_command",
    "note_tag",
    "nonstandard_data",
    "plugin_source",
];

struct TranslationFactRow {
    location_path: String,
    translation_lines_text: String,
    fact_id: String,
    domain: String,
    item_type: String,
    role: String,
    selector: String,
    raw_text: String,
    visible_text: String,
    translatable_text: String,
    raw_hash: String,
    source_line_paths_text: String,
}

struct FactTemplateRow {
    location_path: String,
    fact_id: String,
    domain: String,
    role: String,
    raw_text: String,
    translatable_text: String,
    source_line_paths_text: String,
}

struct RuntimeRulePayload {
    matcher_value: String,
    payload_json: Value,
}

pub(super) fn open_readonly_connection(db_path: &Path) -> Result<Connection, String> {
    Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|error| format!("只读打开数据库失败 {}: {error}", db_path.display()))
}

fn read_runtime_rule_payloads(
    connection: &Connection,
    domain: &str,
    error_label: &str,
) -> Result<Vec<RuntimeRulePayload>, String> {
    let mut statement = connection
        .prepare(
            "SELECT matcher_value, payload_json \
             FROM rules \
             WHERE domain = ?1 AND enabled = 1 \
             ORDER BY rule_order, rule_id",
        )
        .map_err(|error| format!("{error_label} SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([domain], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|error| format!("{error_label}失败: {error}"))?;
    let mut rules = Vec::new();
    for row in rows {
        let (matcher_value, payload_text) =
            row.map_err(|error| format!("{error_label}行失败: {error}"))?;
        let payload_json = serde_json::from_str::<Value>(&payload_text)
            .map_err(|error| format!("{error_label} payload_json 无效: {error}"))?;
        if !payload_json.is_object() {
            return Err(format!("{error_label} payload_json 必须是对象"));
        }
        rules.push(RuntimeRulePayload {
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
        .ok_or_else(|| format!("{error_label}: rules.payload_json.{field} 必须是字符串"))
}

fn payload_optional_string(payload: &Value, field: &str) -> Option<String> {
    payload
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn payload_string_array(
    payload: &Value,
    field: &str,
    error_label: &str,
) -> Result<Vec<String>, String> {
    let values = payload
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{error_label}: rules.payload_json.{field} 必须是字符串数组"))?;
    values
        .iter()
        .map(|value| {
            value.as_str().map(str::to_string).ok_or_else(|| {
                format!("{error_label}: rules.payload_json.{field} 必须是字符串数组")
            })
        })
        .collect()
}

#[derive(Clone, Copy)]
enum TranslationReadScope {
    FullWritableIndex,
    AllowedPaths,
}

pub(super) fn read_translation_items_for_writable_text_index(
    connection: &Connection,
) -> Result<Vec<TranslationItem>, String> {
    let scope_key = read_current_text_fact_scope_key(connection)?;
    let allowed_paths = read_writable_text_index_location_paths_for_scope(connection, &scope_key)?;
    read_translation_items_for_paths(
        connection,
        &scope_key,
        &allowed_paths,
        TranslationReadScope::FullWritableIndex,
    )
}

pub(super) fn read_translation_items_for_allowed_paths(
    connection: &Connection,
    allowed_paths: &[String],
) -> Result<Vec<TranslationItem>, String> {
    let scope_key = read_current_text_fact_scope_key(connection)?;
    read_translation_items_for_paths(
        connection,
        &scope_key,
        allowed_paths,
        TranslationReadScope::AllowedPaths,
    )
}

fn read_translation_items_for_paths(
    connection: &Connection,
    scope_key: &str,
    allowed_paths: &[String],
    read_scope: TranslationReadScope,
) -> Result<Vec<TranslationItem>, String> {
    assert_no_disallowed_translation_items(connection, scope_key, allowed_paths, read_scope)?;
    if allowed_paths.is_empty() && matches!(read_scope, TranslationReadScope::AllowedPaths) {
        return Ok(Vec::new());
    }
    let mut fact_rows: Vec<TranslationFactRow> = Vec::new();
    let mut resolved_fact_ids: HashSet<String> = HashSet::new();
    for chunk in allowed_paths.chunks(SQLITE_IN_CLAUSE_CHUNK_SIZE) {
        let placeholders = std::iter::repeat_n("?", chunk.len())
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "SELECT facts.location_path, translations.translation_lines, \
                    facts.fact_id, facts.domain, facts.item_type, facts.role, \
                    facts.selector, facts.raw_text, facts.visible_text, \
                    facts.translatable_text, facts.raw_hash, indexed.source_line_paths \
             FROM translation_items AS translations \
             INNER JOIN text_facts AS facts \
                ON facts.fact_id = translations.fact_id \
               AND facts.raw_hash = translations.source_fact_raw_hash \
               AND facts.translatable_hash = translations.source_fact_translatable_hash \
               AND facts.scope_key = ? \
             INNER JOIN text_index_items AS indexed \
                ON indexed.location_path = facts.location_path \
               AND indexed.writable = 1 \
             WHERE facts.location_path IN ({placeholders}) \
             ORDER BY facts.location_path, facts.domain, facts.fact_id"
        );
        let mut statement = connection.prepare(&sql).map_err(|error| {
            format!("按 current text fact 可写范围读取译文记录 SQL 准备失败: {error}")
        })?;
        let parameters = std::iter::once(scope_key).chain(chunk.iter().map(String::as_str));
        let rows = statement
            .query_map(params_from_iter(parameters), |row| {
                let location_path: String = row.get(0)?;
                let translation_lines_text: String = row.get(1)?;
                let fact_id: String = row.get(2)?;
                let domain: String = row.get(3)?;
                let item_type: String = row.get(4)?;
                let role: String = row.get(5)?;
                let selector: String = row.get(6)?;
                let raw_text: String = row.get(7)?;
                let visible_text: String = row.get(8)?;
                let translatable_text: String = row.get(9)?;
                let raw_hash: String = row.get(10)?;
                let source_line_paths_text: String = row.get(11)?;
                Ok(TranslationFactRow {
                    location_path,
                    translation_lines_text,
                    fact_id,
                    domain,
                    item_type,
                    role,
                    selector,
                    raw_text,
                    visible_text,
                    translatable_text,
                    raw_hash,
                    source_line_paths_text,
                })
            })
            .map_err(|error| format!("按 current text fact 可写范围读取译文记录失败: {error}"))?;
        for row in rows {
            let fact_row =
                row.map_err(|error| format!("读取 current text fact 译文记录行失败: {error}"))?;
            resolved_fact_ids.insert(fact_row.fact_id.clone());
            fact_rows.push(fact_row);
        }
    }
    match read_scope {
        TranslationReadScope::FullWritableIndex => {
            assert_all_translations_resolved_to_text_facts_for_full_write_back(
                connection,
                &resolved_fact_ids,
            )?;
        }
        TranslationReadScope::AllowedPaths => {
            assert_all_translations_resolved_to_text_facts(
                connection,
                allowed_paths,
                &resolved_fact_ids,
            )?;
        }
    }
    let render_parts_by_fact = read_render_parts_by_fact_id(
        connection,
        &fact_rows
            .iter()
            .map(|row| row.fact_id.clone())
            .collect::<Vec<_>>(),
    )?;
    let mut items: Vec<TranslationItem> = Vec::new();
    for row in fact_rows {
        let render_parts = render_parts_by_fact
            .get(&row.fact_id)
            .cloned()
            .unwrap_or_default();
        items.push(translation_item_from_text_fact_row(row, render_parts)?);
    }
    items.sort_by(|left, right| {
        left.location_path
            .cmp(&right.location_path)
            .then_with(|| left.fact_id.cmp(&right.fact_id))
    });
    Ok(items)
}

fn read_writable_text_index_location_paths_for_scope(
    connection: &Connection,
    scope_key: &str,
) -> Result<Vec<String>, String> {
    let mut statement = connection
        .prepare(
            "SELECT DISTINCT facts.location_path \
             FROM text_facts AS facts \
             INNER JOIN text_index_items AS indexed \
                ON indexed.location_path = facts.location_path \
               AND indexed.writable = 1 \
             WHERE facts.scope_key = ? \
             ORDER BY facts.location_path",
        )
        .map_err(|error| {
            format!(
                "写回计划缺少 allowed_translation_paths，且数据库当前文本范围索引不可读，请重新运行 rebuild-text-index: {error}"
            )
        })?;
    let rows = statement
        .query_map([scope_key], |row| {
            let location_path: String = row.get(0)?;
            Ok(location_path)
        })
        .map_err(|error| format!("读取 current text fact 可写范围失败: {error}"))?;
    let mut paths: Vec<String> = Vec::new();
    for row in rows {
        paths.push(row.map_err(|error| format!("读取 current text fact 可写范围行失败: {error}"))?);
    }
    Ok(paths)
}

pub(super) fn read_mv_virtual_namebox_fact_templates(
    connection: &Connection,
) -> Result<Vec<MvVirtualNameboxFactTemplate>, String> {
    let scope_key = read_current_text_fact_scope_key(connection)?;
    let mut statement = connection
        .prepare(
            "SELECT facts.location_path, facts.fact_id, facts.domain, facts.role, \
                    facts.raw_text, facts.translatable_text, indexed.source_line_paths \
             FROM text_facts AS facts \
             INNER JOIN text_index_items AS indexed \
                ON indexed.location_path = facts.location_path \
             WHERE facts.scope_key = ? \
                AND facts.domain = 'mv_virtual_namebox' \
             ORDER BY facts.location_path, facts.fact_id",
        )
        .map_err(|error| format!("读取 MV 虚拟名字框 current text facts SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([scope_key.as_str()], |row| {
            Ok(FactTemplateRow {
                location_path: row.get(0)?,
                fact_id: row.get(1)?,
                domain: row.get(2)?,
                role: row.get(3)?,
                raw_text: row.get(4)?,
                translatable_text: row.get(5)?,
                source_line_paths_text: row.get(6)?,
            })
        })
        .map_err(|error| format!("读取 MV 虚拟名字框 current text facts 失败: {error}"))?;
    let mut fact_rows: Vec<FactTemplateRow> = Vec::new();
    for row in rows {
        fact_rows.push(
            row.map_err(|error| format!("读取 MV 虚拟名字框 current text fact 行失败: {error}"))?,
        );
    }
    let render_parts_by_fact = read_render_parts_by_fact_id(
        connection,
        &fact_rows
            .iter()
            .map(|row| row.fact_id.clone())
            .collect::<Vec<_>>(),
    )?;
    let mut templates = Vec::new();
    for row in fact_rows {
        let render_parts = render_parts_by_fact
            .get(&row.fact_id)
            .cloned()
            .unwrap_or_default();
        validate_text_fact_render_parts_for_domain(
            &row.domain,
            &row.location_path,
            &row.raw_text,
            &render_parts,
        )?;
        let source_line_paths =
            parse_string_array(&row.source_line_paths_text, "source_line_paths")?;
        templates.push(MvVirtualNameboxFactTemplate {
            location_path: row.location_path,
            role: row.role,
            raw_text: row.raw_text,
            body_text: row.translatable_text,
            source_line_paths,
            render_parts,
        });
    }
    Ok(templates)
}

pub(super) fn parse_string_array(text: &str, label: &str) -> Result<Vec<String>, String> {
    serde_json::from_str(text).map_err(|error| format!("{label} 不是字符串数组 JSON: {error}"))
}

fn assert_no_disallowed_translation_items(
    connection: &Connection,
    scope_key: &str,
    allowed_paths: &[String],
    read_scope: TranslationReadScope,
) -> Result<(), String> {
    if allowed_paths.is_empty() && matches!(read_scope, TranslationReadScope::AllowedPaths) {
        return Ok(());
    }
    let allowed: HashSet<&str> = allowed_paths.iter().map(String::as_str).collect();
    let mut disallowed_paths: Vec<String> = Vec::new();
    match read_scope {
        TranslationReadScope::FullWritableIndex => {
            let mut statement = connection
                .prepare(
                    "SELECT facts.location_path \
                     FROM translation_items AS translations \
                     INNER JOIN text_facts AS facts \
                        ON facts.fact_id = translations.fact_id \
                       AND facts.raw_hash = translations.source_fact_raw_hash \
                       AND facts.translatable_hash = translations.source_fact_translatable_hash \
                      WHERE facts.scope_key = ? \
                     ORDER BY facts.location_path, facts.fact_id",
                )
                .map_err(|error| format!("读取译文路径 SQL 准备失败: {error}"))?;
            let rows = statement
                .query_map([scope_key], |row| {
                    let location_path: String = row.get(0)?;
                    Ok(location_path)
                })
                .map_err(|error| format!("读取译文路径失败: {error}"))?;
            for row in rows {
                let location_path = row.map_err(|error| format!("读取译文路径行失败: {error}"))?;
                if !allowed.contains(location_path.as_str()) {
                    disallowed_paths.push(location_path);
                }
            }
        }
        TranslationReadScope::AllowedPaths => {
            for chunk in allowed_paths.chunks(SQLITE_IN_CLAUSE_CHUNK_SIZE) {
                let placeholders = std::iter::repeat_n("?", chunk.len())
                    .collect::<Vec<_>>()
                    .join(",");
                let sql = format!(
                    "SELECT facts.location_path \
                     FROM translation_items AS translations \
                     INNER JOIN text_facts AS facts \
                        ON facts.fact_id = translations.fact_id \
                       AND facts.raw_hash = translations.source_fact_raw_hash \
                       AND facts.translatable_hash = translations.source_fact_translatable_hash \
                      WHERE facts.scope_key = ? \
                        AND facts.location_path IN ({placeholders}) \
                     ORDER BY facts.location_path, facts.fact_id"
                );
                let mut statement = connection
                    .prepare(&sql)
                    .map_err(|error| format!("读取译文路径 SQL 准备失败: {error}"))?;
                let parameters = std::iter::once(scope_key).chain(chunk.iter().map(String::as_str));
                let rows = statement
                    .query_map(params_from_iter(parameters), |row| {
                        let location_path: String = row.get(0)?;
                        Ok(location_path)
                    })
                    .map_err(|error| format!("读取译文路径失败: {error}"))?;
                for row in rows {
                    let location_path =
                        row.map_err(|error| format!("读取译文路径行失败: {error}"))?;
                    if !allowed.contains(location_path.as_str()) {
                        disallowed_paths.push(location_path);
                    }
                }
            }
        }
    }
    if !disallowed_paths.is_empty() {
        disallowed_paths.sort_unstable();
        let samples = disallowed_paths
            .iter()
            .take(5)
            .map(String::as_str)
            .collect::<Vec<_>>()
            .join("、");
        let suffix = if disallowed_paths.len() > 5 {
            format!(" 等 {} 条", disallowed_paths.len())
        } else {
            String::new()
        };
        return Err(format!(
            "发现已保存译文不在当前可写文本范围内，不能继续写进游戏文件: {samples}{suffix}"
        ));
    }
    Ok(())
}

fn read_current_text_fact_scope_key(connection: &Connection) -> Result<String, String> {
    let mut statement = connection
        .prepare(
            "SELECT scope_key, schema_version \
             FROM text_fact_scope \
             ORDER BY created_at DESC, scope_key",
        )
        .map_err(|error| {
            format!(
                "当前数据库缺少 当前文本事实 scope，请重新运行 rebuild-text-index 后再写进游戏文件: {error}"
            )
        })?;
    let mut rows = statement
        .query([])
        .map_err(|error| format!("读取 当前文本事实 scope 失败: {error}"))?;
    let first = rows
        .next()
        .map_err(|error| format!("读取 当前文本事实 scope 行失败: {error}"))?
        .ok_or_else(|| {
            "当前数据库缺少 当前文本事实 scope，请重新运行 rebuild-text-index 后再写进游戏文件"
                .to_string()
        })?;
    let scope_key: String = first
        .get(0)
        .map_err(|error| format!("读取 当前文本事实 scope_key 失败: {error}"))?;
    let schema_version: i64 = first
        .get(1)
        .map_err(|error| format!("读取 当前文本事实 schema_version 失败: {error}"))?;
    if schema_version != CURRENT_TEXT_FACT_CONTRACT_VERSION {
        return Err(
            "当前文本事实范围不符合当前要求，不能写进游戏文件；请重新运行 rebuild-text-index"
                .to_string(),
        );
    }
    if rows
        .next()
        .map_err(|error| format!("读取 当前文本事实 scope 额外行失败: {error}"))?
        .is_some()
    {
        return Err(
            "当前数据库存在多个 当前文本事实 scope，请重新运行 rebuild-text-index".to_string(),
        );
    }
    let mismatch_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM text_facts WHERE scope_key <> ?",
            [scope_key.as_str()],
            |row| row.get(0),
        )
        .map_err(|error| format!("确认 当前文本事实 scope 一致性失败: {error}"))?;
    if mismatch_count > 0 {
        return Err(format!(
            "当前文本事实 scope 不一致: {mismatch_count} 条文本事实不属于当前 scope {scope_key}；请重新运行 rebuild-text-index"
        ));
    }
    Ok(scope_key)
}

fn assert_all_translations_resolved_to_text_facts(
    connection: &Connection,
    allowed_paths: &[String],
    resolved_fact_ids: &HashSet<String>,
) -> Result<(), String> {
    if allowed_paths.is_empty() {
        return Ok(());
    }
    let mut unresolved_paths: Vec<String> = Vec::new();
    for chunk in allowed_paths.chunks(SQLITE_IN_CLAUSE_CHUNK_SIZE) {
        let placeholders = std::iter::repeat_n("?", chunk.len())
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "SELECT fact_id, location_path \
             FROM translation_items \
             WHERE location_path IN ({placeholders}) \
             ORDER BY location_path, fact_id"
        );
        let mut statement = connection
            .prepare(&sql)
            .map_err(|error| format!("读取译文路径 SQL 准备失败: {error}"))?;
        let rows = statement
            .query_map(params_from_iter(chunk.iter().map(String::as_str)), |row| {
                let fact_id: String = row.get(0)?;
                let location_path: String = row.get(1)?;
                Ok((fact_id, location_path))
            })
            .map_err(|error| format!("读取译文路径失败: {error}"))?;
        for row in rows {
            let (fact_id, location_path) =
                row.map_err(|error| format!("读取译文路径行失败: {error}"))?;
            if !resolved_fact_ids.contains(&fact_id) {
                unresolved_paths.push(location_path);
            }
        }
    }
    assert_no_unresolved_translation_paths(unresolved_paths)
}

fn assert_all_translations_resolved_to_text_facts_for_full_write_back(
    connection: &Connection,
    resolved_fact_ids: &HashSet<String>,
) -> Result<(), String> {
    let mut statement = connection
        .prepare(
            "SELECT fact_id, location_path \
             FROM translation_items \
             ORDER BY location_path, fact_id",
        )
        .map_err(|error| format!("读取译文路径 SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            let fact_id: String = row.get(0)?;
            let location_path: String = row.get(1)?;
            Ok((fact_id, location_path))
        })
        .map_err(|error| format!("读取译文路径失败: {error}"))?;
    let mut unresolved_paths: Vec<String> = Vec::new();
    for row in rows {
        let (fact_id, location_path) =
            row.map_err(|error| format!("读取译文路径行失败: {error}"))?;
        if !resolved_fact_ids.contains(&fact_id) {
            unresolved_paths.push(location_path);
        }
    }
    assert_no_unresolved_translation_paths(unresolved_paths)
}

fn assert_no_unresolved_translation_paths(unresolved_paths: Vec<String>) -> Result<(), String> {
    if unresolved_paths.is_empty() {
        return Ok(());
    }
    let samples = unresolved_paths
        .iter()
        .take(5)
        .map(String::as_str)
        .collect::<Vec<_>>()
        .join("、");
    let suffix = if unresolved_paths.len() > 5 {
        format!(" 等 {} 条", unresolved_paths.len())
    } else {
        String::new()
    };
    Err(format!(
        "已保存译文不再匹配当前文本事实，不能写进游戏文件；请重新运行 rebuild-text-index 后重新翻译或手动导入: {samples}{suffix}"
    ))
}

fn read_render_parts_by_fact_id(
    connection: &Connection,
    fact_ids: &[String],
) -> Result<HashMap<String, Vec<TextFactRenderPart>>, String> {
    let mut parts_by_fact: HashMap<String, Vec<TextFactRenderPart>> = HashMap::new();
    if fact_ids.is_empty() {
        return Ok(parts_by_fact);
    }
    let unique_fact_ids: Vec<String> = fact_ids
        .iter()
        .cloned()
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    for chunk in unique_fact_ids.chunks(SQLITE_IN_CLAUSE_CHUNK_SIZE) {
        let placeholders = std::iter::repeat_n("?", chunk.len())
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "SELECT fact_id, part_order, part_kind, raw_text, template_key \
             FROM text_fact_render_parts \
             WHERE fact_id IN ({placeholders}) \
             ORDER BY fact_id, part_order"
        );
        let mut statement = connection
            .prepare(&sql)
            .map_err(|error| format!("读取写回所需源文结构 SQL 准备失败: {error}"))?;
        let rows = statement
            .query_map(params_from_iter(chunk.iter().map(String::as_str)), |row| {
                Ok(TextFactRenderPart {
                    fact_id: row.get(0)?,
                    part_order: row.get(1)?,
                    part_kind: row.get(2)?,
                    raw_text: row.get(3)?,
                    template_key: row.get(4)?,
                })
            })
            .map_err(|error| format!("读取写回所需源文结构失败: {error}"))?;
        for row in rows {
            let part = row.map_err(|error| format!("读取写回所需源文结构行失败: {error}"))?;
            parts_by_fact
                .entry(part.fact_id.clone())
                .or_default()
                .push(part);
        }
    }
    for parts in parts_by_fact.values_mut() {
        parts.sort_by_key(|part| part.part_order);
    }
    Ok(parts_by_fact)
}

fn translation_item_from_text_fact_row(
    row: TranslationFactRow,
    render_parts: Vec<TextFactRenderPart>,
) -> Result<TranslationItem, String> {
    validate_text_fact_render_parts(&row, &render_parts)?;
    let source_line_paths = parse_string_array(&row.source_line_paths_text, "source_line_paths")?;
    let translation_lines = parse_string_array(&row.translation_lines_text, "translation_lines")?;
    if translation_lines.is_empty() || translation_lines.iter().all(|line| line.trim().is_empty()) {
        return Err(format!(
            "译文行为空，不能写进游戏文件: {}",
            row.location_path
        ));
    }
    let original_lines = text_fact_lines(&row.translatable_text, &row.item_type)?;
    let role = if row.role.trim().is_empty() {
        None
    } else {
        Some(row.role)
    };
    Ok(TranslationItem {
        fact_id: row.fact_id,
        location_path: row.location_path,
        item_type: row.item_type,
        role,
        selector: row.selector,
        raw_text: row.raw_text,
        visible_text: row.visible_text,
        raw_hash: row.raw_hash,
        render_parts,
        original_lines,
        source_line_paths,
        translation_lines,
    })
}

fn validate_text_fact_render_parts(
    row: &TranslationFactRow,
    render_parts: &[TextFactRenderPart],
) -> Result<(), String> {
    validate_text_fact_render_parts_for_domain(
        &row.domain,
        &row.location_path,
        &row.raw_text,
        render_parts,
    )
}

fn validate_text_fact_render_parts_for_domain(
    domain: &str,
    location_path: &str,
    raw_text: &str,
    render_parts: &[TextFactRenderPart],
) -> Result<(), String> {
    if !WRITE_BACK_TEXT_FACT_DOMAINS.contains(&domain) {
        return Ok(());
    }
    if render_parts.is_empty() {
        return Err(format!(
            "当前文本事实缺少写回所需源文结构，不能写进游戏文件；请重新运行 rebuild-text-index: {}",
            location_path
        ));
    }
    let rendered_raw = render_parts
        .iter()
        .map(|part| part.raw_text.as_str())
        .collect::<String>();
    if rendered_raw != raw_text {
        return Err(format!(
            "当前文本事实写回所需源文结构不一致，不能写进游戏文件；请重新运行 rebuild-text-index: {}",
            location_path
        ));
    }
    if !render_parts
        .iter()
        .any(|part| part.part_kind == "translated_body" || part.template_key == "body")
    {
        return Err(format!(
            "当前文本事实缺少译文写入位置，不能写进游戏文件；请重新运行 rebuild-text-index: {}",
            location_path
        ));
    }
    Ok(())
}

fn text_fact_lines(text: &str, item_type: &str) -> Result<Vec<String>, String> {
    match item_type {
        "long_text" | "array" => Ok(text.split('\n').map(str::to_string).collect()),
        "short_text" => Ok(vec![text.to_string()]),
        _ => Err(format!(
            "当前文本事实 item_type 不受支持: {item_type}；请重新运行 rebuild-text-index"
        )),
    }
}

pub(super) fn read_plugin_source_text_rules(
    connection: &Connection,
) -> Result<Vec<PluginSourceTextRule>, String> {
    let rows = read_runtime_rule_payloads(connection, "plugin_source", "读取插件源码规则")?;
    let mut rules_by_file: HashMap<String, PluginSourceTextRule> = HashMap::new();
    for row in rows {
        let file_name =
            payload_optional_string(&row.payload_json, "file_name").ok_or_else(|| {
                "读取插件源码规则: rules.payload_json.file_name 必须是字符串".to_string()
            })?;
        let file_hash = payload_optional_string(&row.payload_json, "file_hash").unwrap_or_default();
        let selector =
            payload_optional_string(&row.payload_json, "selector").unwrap_or(row.matcher_value);
        let selector_kind = payload_optional_string(&row.payload_json, "selector_kind")
            .unwrap_or_else(|| "translate".to_string());
        let record =
            rules_by_file
                .entry(file_name.clone())
                .or_insert_with(|| PluginSourceTextRule {
                    file_name,
                    file_hash: file_hash.clone(),
                    selectors: Vec::new(),
                    excluded_selectors: Vec::new(),
                });
        if record.file_hash != file_hash {
            return Err(format!("插件源码规则文件哈希不一致: {}", record.file_name));
        }
        match selector_kind.as_str() {
            "translate" => record.selectors.push(selector),
            "excluded" => record.excluded_selectors.push(selector),
            _ => return Err(format!("插件源码规则 selector 类型无效: {selector_kind}")),
        }
    }
    let mut rules: Vec<PluginSourceTextRule> = rules_by_file.into_values().collect();
    rules.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    Ok(rules)
}

pub(super) fn read_source_residual_rules(
    connection: &Connection,
) -> Result<Vec<NativeSourceResidualRule>, String> {
    let rows = read_runtime_rule_payloads(connection, "source_residual", "读取源文残留例外规则")?;
    let mut rules = Vec::new();
    for row in rows {
        let rule_type = payload_string(&row.payload_json, "rule_type", "读取源文残留例外规则")?;
        rules.push(NativeSourceResidualRule {
            rule_id: payload_string(&row.payload_json, "rule_id", "读取源文残留例外规则")?,
            rule_type,
            location_path: payload_optional_string(&row.payload_json, "location_path")
                .unwrap_or_else(|| row.matcher_value.clone()),
            pattern_text: payload_optional_string(&row.payload_json, "pattern_text")
                .unwrap_or(row.matcher_value),
            allowed_terms: payload_string_array(
                &row.payload_json,
                "allowed_terms",
                "读取源文残留例外规则",
            )?,
            check_group: payload_optional_string(&row.payload_json, "check_group")
                .unwrap_or_default(),
            reason: payload_string(&row.payload_json, "reason", "读取源文残留例外规则")?,
        });
    }
    Ok(rules)
}
pub(super) fn read_terminology_terms(
    connection: &Connection,
) -> Result<HashMap<String, HashMap<String, String>>, String> {
    let actor_name_control_pattern = regex::Regex::new(r"\\[Nn]\[\d+\]")
        .map_err(|error| format!("角色名控制符正则初始化失败: {error}"))?;
    let mut statement = connection
        .prepare("SELECT category, source_text, translated_text FROM terminology_field_terms")
        .map_err(|error| format!("读取字段译名表 SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            let category: String = row.get(0)?;
            let source_text: String = row.get(1)?;
            let translated_text: String = row.get(2)?;
            Ok((category, source_text, translated_text))
        })
        .map_err(|error| format!("读取字段译名表失败: {error}"))?;
    let mut terms: HashMap<String, HashMap<String, String>> = HashMap::new();
    for row in rows {
        let (category, source_text, translated_text) =
            row.map_err(|error| format!("读取字段译名表行失败: {error}"))?;
        if source_text.trim().is_empty()
            || actor_name_control_pattern.is_match(source_text.trim())
            || translated_text.trim().is_empty()
        {
            continue;
        }
        terms.entry(category).or_default().insert(
            source_text.trim().to_string(),
            translated_text.trim().to_string(),
        );
    }
    Ok(terms)
}

pub(super) fn read_mv_virtual_namebox_rules(
    connection: &Connection,
) -> Result<Vec<MvVirtualNameboxRule>, String> {
    let rows =
        read_runtime_rule_payloads(connection, "mv_virtual_namebox", "读取 MV 虚拟名字框规则")?;
    let mut rules = Vec::new();
    for row in rows {
        let rule_name = payload_string(&row.payload_json, "name", "读取 MV 虚拟名字框规则")?;
        let pattern_text =
            payload_optional_string(&row.payload_json, "pattern").unwrap_or(row.matcher_value);
        let speaker_group =
            payload_string(&row.payload_json, "speaker_group", "读取 MV 虚拟名字框规则")?;
        let body_group =
            payload_optional_string(&row.payload_json, "body_group").unwrap_or_default();
        let speaker_policy = payload_string(
            &row.payload_json,
            "speaker_policy",
            "读取 MV 虚拟名字框规则",
        )?;
        let render_template = payload_string(
            &row.payload_json,
            "render_template",
            "读取 MV 虚拟名字框规则",
        )?;
        let pattern = compile_mv_virtual_namebox_pattern(
            &rule_name,
            &pattern_text,
            &speaker_group,
            &body_group,
        )
        .map_err(|error| format!("MV 虚拟名字框规则正则损坏 {rule_name}: {error}"))?;
        let group_names = pattern.capture_names();
        rules.push(MvVirtualNameboxRule {
            rule_name,
            group_names,
            pattern,
            speaker_group,
            body_group,
            speaker_policy: parse_mv_virtual_speaker_policy(&speaker_policy)?,
            render_template,
        });
    }
    Ok(rules)
}

pub(super) fn parse_mv_virtual_speaker_policy(
    value: &str,
) -> Result<MvVirtualSpeakerPolicy, String> {
    match value {
        "translate" => Ok(MvVirtualSpeakerPolicy::Translate),
        "preserve" => Ok(MvVirtualSpeakerPolicy::Preserve),
        "actor_name" => Ok(MvVirtualSpeakerPolicy::ActorName),
        _ => Err("rules.payload_json.speaker_policy 非法，请重新导入规则".to_string()),
    }
}
