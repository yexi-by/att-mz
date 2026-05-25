use super::models::{
    MvVirtualNameboxRule, MvVirtualSpeakerPolicy, PluginSourceTextRule, TranslationItem,
};
use super::utils::collect_python_named_groups;
use crate::native_core::models::NativeSourceResidualRule;
use fancy_regex::Regex as FancyRegex;
use rusqlite::{Connection, OpenFlags};
use std::collections::{HashMap, HashSet};
use std::path::Path;

pub(super) fn open_readonly_connection(db_path: &Path) -> Result<Connection, String> {
    Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|error| format!("只读打开数据库失败 {}: {error}", db_path.display()))
}
pub(super) fn read_translation_items(
    connection: &Connection,
) -> Result<Vec<TranslationItem>, String> {
    let mut statement = connection
        .prepare(
            "SELECT location_path, item_type, role, original_lines, source_line_paths, translation_lines \
             FROM translation_items ORDER BY location_path",
        )
        .map_err(|error| format!("读取译文记录 SQL 准备失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            let location_path: String = row.get(0)?;
            let item_type: String = row.get(1)?;
            let role: Option<String> = row.get(2)?;
            let original_lines_text: String = row.get(3)?;
            let source_line_paths_text: String = row.get(4)?;
            let translation_lines_text: String = row.get(5)?;
            Ok((
                location_path,
                item_type,
                role,
                original_lines_text,
                source_line_paths_text,
                translation_lines_text,
            ))
        })
        .map_err(|error| format!("读取译文记录失败: {error}"))?;
    let mut items: Vec<TranslationItem> = Vec::new();
    for row in rows {
        let (
            location_path,
            item_type,
            role,
            original_lines_text,
            source_line_paths_text,
            translation_lines_text,
        ) = row.map_err(|error| format!("读取译文记录行失败: {error}"))?;
        let original_lines = parse_string_array(&original_lines_text, "original_lines")?;
        let source_line_paths = parse_string_array(&source_line_paths_text, "source_line_paths")?;
        let translation_lines = parse_string_array(&translation_lines_text, "translation_lines")?;
        if translation_lines.is_empty()
            || translation_lines.iter().all(|line| line.trim().is_empty())
        {
            return Err(format!("译文行为空，不能写进游戏文件: {location_path}"));
        }
        items.push(TranslationItem {
            location_path,
            item_type,
            role,
            original_lines,
            source_line_paths,
            translation_lines,
        });
    }
    Ok(items)
}

pub(super) fn parse_string_array(text: &str, label: &str) -> Result<Vec<String>, String> {
    serde_json::from_str(text).map_err(|error| format!("{label} 不是字符串数组 JSON: {error}"))
}

pub(super) fn filter_translation_items_by_policy(
    items: Vec<TranslationItem>,
    allowed_paths: &[String],
) -> Result<Vec<TranslationItem>, String> {
    let allowed: HashSet<&str> = allowed_paths.iter().map(String::as_str).collect();
    let mut disallowed_paths: Vec<&str> = items
        .iter()
        .map(|item| item.location_path.as_str())
        .filter(|path| !allowed.contains(path))
        .collect();
    if !disallowed_paths.is_empty() {
        disallowed_paths.sort_unstable();
        let samples = disallowed_paths
            .iter()
            .take(5)
            .copied()
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
    Ok(items)
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
