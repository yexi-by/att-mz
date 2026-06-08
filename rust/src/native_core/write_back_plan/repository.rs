use super::models::{
    MvVirtualNameboxFactTemplate, MvVirtualNameboxRule, MvVirtualSpeakerPolicy,
    PluginSourceTextRule, TextFactRenderPart, TranslationItem,
};
use super::utils::collect_python_named_groups;
use crate::native_core::models::NativeSourceResidualRule;
use fancy_regex::Regex as FancyRegex;
use rusqlite::{Connection, OpenFlags, params_from_iter};
use std::collections::{HashMap, HashSet};
use std::path::Path;

const SQLITE_IN_CLAUSE_CHUNK_SIZE: usize = 500;
const TEXT_FACT_SCHEMA_VERSION: i64 = 2;
const MIGRATED_WRITE_BACK_DOMAINS: &[&str] = &[
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

pub(super) fn open_readonly_connection(db_path: &Path) -> Result<Connection, String> {
    Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|error| format!("只读打开数据库失败 {}: {error}", db_path.display()))
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
             INNER JOIN text_facts_v2 AS facts \
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
        let mut statement = connection
            .prepare(&sql)
            .map_err(|error| format!("按 v2 fact 可写范围读取译文记录 SQL 准备失败: {error}"))?;
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
            .map_err(|error| format!("按 v2 fact 可写范围读取译文记录失败: {error}"))?;
        for row in rows {
            let fact_row = row.map_err(|error| format!("读取 v2 fact 译文记录行失败: {error}"))?;
            resolved_fact_ids.insert(fact_row.fact_id.clone());
            fact_rows.push(fact_row);
        }
    }
    match read_scope {
        TranslationReadScope::FullWritableIndex => {
            assert_all_translations_resolved_to_v2_facts_for_full_write_back(
                connection,
                &resolved_fact_ids,
            )?;
        }
        TranslationReadScope::AllowedPaths => {
            assert_all_translations_resolved_to_v2_facts(
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
        items.push(translation_item_from_v2_fact_row(row, render_parts)?);
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
             FROM text_facts_v2 AS facts \
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
        .map_err(|error| format!("读取 v2 text fact 可写范围失败: {error}"))?;
    let mut paths: Vec<String> = Vec::new();
    for row in rows {
        paths.push(row.map_err(|error| format!("读取 v2 text fact 可写范围行失败: {error}"))?);
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
             FROM text_facts_v2 AS facts \
             INNER JOIN text_index_items AS indexed \
                ON indexed.location_path = facts.location_path \
             WHERE facts.scope_key = ? \
                AND facts.domain = 'mv_virtual_namebox' \
             ORDER BY facts.location_path, facts.fact_id",
        )
        .map_err(|error| format!("读取 MV 虚拟名字框 v2 facts SQL 准备失败: {error}"))?;
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
        .map_err(|error| format!("读取 MV 虚拟名字框 v2 facts 失败: {error}"))?;
    let mut fact_rows: Vec<FactTemplateRow> = Vec::new();
    for row in rows {
        fact_rows.push(row.map_err(|error| format!("读取 MV 虚拟名字框 v2 fact 行失败: {error}"))?);
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
                     INNER JOIN text_facts_v2 AS facts \
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
                     INNER JOIN text_facts_v2 AS facts \
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
             FROM text_fact_scope_v2 \
             ORDER BY created_at DESC, scope_key",
        )
        .map_err(|error| {
            format!(
                "当前数据库缺少 text fact v2 scope，请重新运行 rebuild-text-index 后再写进游戏文件: {error}"
            )
        })?;
    let mut rows = statement
        .query([])
        .map_err(|error| format!("读取 text fact v2 scope 失败: {error}"))?;
    let first = rows
        .next()
        .map_err(|error| format!("读取 text fact v2 scope 行失败: {error}"))?
        .ok_or_else(|| {
            "当前数据库缺少 text fact v2 scope，请重新运行 rebuild-text-index 后再写进游戏文件"
                .to_string()
        })?;
    let scope_key: String = first
        .get(0)
        .map_err(|error| format!("读取 text fact v2 scope_key 失败: {error}"))?;
    let schema_version: i64 = first
        .get(1)
        .map_err(|error| format!("读取 text fact v2 schema_version 失败: {error}"))?;
    if schema_version != TEXT_FACT_SCHEMA_VERSION {
        return Err(format!(
            "text fact v2 schema version 不受支持: 数据库是 {schema_version}，当前工具支持 {TEXT_FACT_SCHEMA_VERSION}；请重新运行 rebuild-text-index"
        ));
    }
    if rows
        .next()
        .map_err(|error| format!("读取 text fact v2 scope 额外行失败: {error}"))?
        .is_some()
    {
        return Err(
            "当前数据库存在多个 text fact v2 scope，请重新运行 rebuild-text-index".to_string(),
        );
    }
    let mismatch_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM text_facts_v2 WHERE scope_key <> ?",
            [scope_key.as_str()],
            |row| row.get(0),
        )
        .map_err(|error| format!("确认 text fact v2 scope 一致性失败: {error}"))?;
    if mismatch_count > 0 {
        return Err(format!(
            "text fact v2 scope 不一致: {mismatch_count} 条文本事实不属于当前 scope {scope_key}；请重新运行 rebuild-text-index"
        ));
    }
    Ok(scope_key)
}

fn assert_all_translations_resolved_to_v2_facts(
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

fn assert_all_translations_resolved_to_v2_facts_for_full_write_back(
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
        "已保存译文不再匹配当前 v2 文本事实身份，请 rebuild-text-index 后重新翻译/手动导入: {samples}{suffix}"
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
             FROM text_fact_render_parts_v2 \
             WHERE fact_id IN ({placeholders}) \
             ORDER BY fact_id, part_order"
        );
        let mut statement = connection
            .prepare(&sql)
            .map_err(|error| format!("读取 v2 render parts SQL 准备失败: {error}"))?;
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
            .map_err(|error| format!("读取 v2 render parts 失败: {error}"))?;
        for row in rows {
            let part = row.map_err(|error| format!("读取 v2 render part 行失败: {error}"))?;
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

fn translation_item_from_v2_fact_row(
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
    if !MIGRATED_WRITE_BACK_DOMAINS.contains(&domain) {
        return Ok(());
    }
    if render_parts.is_empty() {
        return Err(format!(
            "当前 v2 文本事实缺少 render parts，不能写进游戏文件，请重新运行 rebuild-text-index: {}",
            location_path
        ));
    }
    let rendered_raw = render_parts
        .iter()
        .map(|part| part.raw_text.as_str())
        .collect::<String>();
    if rendered_raw != raw_text {
        return Err(format!(
            "当前 v2 文本事实 render parts 与 raw_text 不一致，不能写进游戏文件，请重新运行 rebuild-text-index: {}",
            location_path
        ));
    }
    if !render_parts
        .iter()
        .any(|part| part.part_kind == "translated_body" || part.template_key == "body")
    {
        return Err(format!(
            "当前 v2 文本事实 render parts 缺少 translated_body，不能写进游戏文件，请重新运行 rebuild-text-index: {}",
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
            "text fact v2 item_type 不受支持: {item_type}；请重新运行 rebuild-text-index"
        )),
    }
}

pub(super) fn read_plugin_source_text_rules(
    connection: &Connection,
) -> Result<Vec<PluginSourceTextRule>, String> {
    let mut statement = connection
        .prepare(
            "SELECT file_name, file_hash, selector, selector_kind \
             FROM plugin_source_text_rules ORDER BY file_name, selector_kind, selector",
        )
        .map_err(|error| format!("读取插件源码规则 SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            let file_name: String = row.get(0)?;
            let file_hash: String = row.get(1)?;
            let selector: String = row.get(2)?;
            let selector_kind: String = row.get(3)?;
            Ok((file_name, file_hash, selector, selector_kind))
        })
        .map_err(|error| format!("读取插件源码规则失败: {error}"))?;
    let mut rules_by_file: HashMap<String, PluginSourceTextRule> = HashMap::new();
    for row in rows {
        let (file_name, file_hash, selector, selector_kind) =
            row.map_err(|error| format!("读取插件源码规则行失败: {error}"))?;
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
    let mut statement = connection
        .prepare(
            "SELECT rule_id, rule_type, location_path, pattern_text, allowed_terms, check_group, reason \
             FROM source_residual_rules ORDER BY rule_id",
        )
        .map_err(|error| format!("读取源文残留例外规则 SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            let rule_id: String = row.get(0)?;
            let rule_type: String = row.get(1)?;
            let location_path: String = row.get(2)?;
            let pattern_text: String = row.get(3)?;
            let allowed_terms_text: String = row.get(4)?;
            let check_group: String = row.get(5)?;
            let reason: String = row.get(6)?;
            Ok((
                rule_id,
                rule_type,
                location_path,
                pattern_text,
                allowed_terms_text,
                check_group,
                reason,
            ))
        })
        .map_err(|error| format!("读取源文残留例外规则失败: {error}"))?;
    let mut rules = Vec::new();
    for row in rows {
        let (
            rule_id,
            rule_type,
            location_path,
            pattern_text,
            allowed_terms_text,
            check_group,
            reason,
        ) = row.map_err(|error| format!("读取源文残留例外规则行失败: {error}"))?;
        rules.push(NativeSourceResidualRule {
            rule_id,
            rule_type,
            location_path,
            pattern_text,
            allowed_terms: parse_string_array(&allowed_terms_text, "allowed_terms")?,
            check_group,
            reason,
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
    let mut statement = connection
        .prepare(
            "SELECT rule_name, pattern_text, speaker_group, body_group, speaker_policy, render_template \
             FROM mv_virtual_namebox_rules ORDER BY rule_order",
        )
        .map_err(|error| format!("读取 MV 虚拟名字框规则 SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            let rule_name: String = row.get(0)?;
            let pattern_text: String = row.get(1)?;
            let speaker_group: String = row.get(2)?;
            let body_group: String = row.get(3)?;
            let speaker_policy: String = row.get(4)?;
            let render_template: String = row.get(5)?;
            Ok((
                rule_name,
                pattern_text,
                speaker_group,
                body_group,
                speaker_policy,
                render_template,
            ))
        })
        .map_err(|error| format!("读取 MV 虚拟名字框规则失败: {error}"))?;
    let mut rules = Vec::new();
    for row in rows {
        let (rule_name, pattern_text, speaker_group, body_group, speaker_policy, render_template) =
            row.map_err(|error| format!("读取 MV 虚拟名字框规则行失败: {error}"))?;
        let pattern = FancyRegex::new(&pattern_text)
            .map_err(|error| format!("MV 虚拟名字框规则正则损坏 {rule_name}: {error}"))?;
        rules.push(MvVirtualNameboxRule {
            rule_name,
            group_names: collect_python_named_groups(&pattern_text),
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
        _ => Err("mv_virtual_namebox_rules.speaker_policy 非法，请重新导入规则".to_string()),
    }
}
