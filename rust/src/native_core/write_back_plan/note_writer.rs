use super::models::{TextPlanRules, TranslationItem};
use super::plugin_config_writer::encode_visible_text_like;
use super::text_prepare::prepared_single_text;
use super::utils::parse_usize;
use crate::native_core::write_protocol::ensure_encoded_text_valid;
use serde_json::{Map, Value};
use std::collections::BTreeMap;

pub(super) fn is_note_tag_path(location_path: &str) -> bool {
    let parts: Vec<&str> = location_path.split('/').collect();
    parts.len() >= 3 && parts.get(parts.len().saturating_sub(2)) == Some(&"note")
}

pub(super) fn write_note_tag_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let parts: Vec<&str> = item.location_path.split('/').collect();
    if parts.len() < 3 {
        return Err(format!("Note 路径无效: {}", item.location_path));
    }
    let file_name = parts[0];
    let tag_name = parts[parts.len() - 1];
    let owner_parts = &parts[1..parts.len() - 2];
    let root = data_files
        .get_mut(file_name)
        .ok_or_else(|| format!("Note 目标文件不存在: {file_name}"))?;
    let owner = locate_note_owner_mut(root, owner_parts, &item.location_path)?;
    let note_text = owner
        .get("note")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("Note 字段不是字符串: {}", item.location_path))?;
    let replaced = replace_note_tag_value(
        note_text,
        tag_name,
        &prepared_single_text(item, rules)?,
        &item.location_path,
    )?;
    owner.insert("note".to_string(), Value::String(replaced));
    Ok(())
}

pub(super) fn locate_note_owner_mut<'a>(
    value: &'a mut Value,
    owner_parts: &[&str],
    location_path: &str,
) -> Result<&'a mut Map<String, Value>, String> {
    if owner_parts.is_empty() {
        return value
            .as_object_mut()
            .ok_or_else(|| format!("Note 持有者不是对象: {location_path}"));
    }
    let part = owner_parts[0];
    match value {
        Value::Object(object) => {
            let child = object
                .get_mut(part)
                .ok_or_else(|| format!("Note 路径对象键不存在: {location_path}"))?;
            locate_note_owner_mut(child, &owner_parts[1..], location_path)
        }
        Value::Array(array) => {
            let index = parse_usize(part, location_path)?;
            let target_index = if index < array.len() && !array[index].is_null() {
                Some(index)
            } else {
                array.iter().position(|child| {
                    child
                        .as_object()
                        .and_then(|object| object.get("id"))
                        .and_then(Value::as_i64)
                        == Some(index as i64)
                })
            };
            let Some(target_index) = target_index else {
                return Err(format!("Note 路径数组索引不存在: {location_path}"));
            };
            let child = array
                .get_mut(target_index)
                .ok_or_else(|| format!("Note 路径数组索引不存在: {location_path}"))?;
            locate_note_owner_mut(child, &owner_parts[1..], location_path)
        }
        _ => Err(format!("Note 路径无法继续定位: {location_path}")),
    }
}

pub(super) fn replace_note_tag_value(
    note_text: &str,
    tag_name: &str,
    translated_text: &str,
    context: &str,
) -> Result<String, String> {
    let pattern = regex::Regex::new(r"<(?P<tag>[^<>:\r\n]+)(?::(?P<value>[^<>]*))?>")
        .map_err(|error| format!("Note 标签正则初始化失败: {error}"))?;
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    for captures in pattern.captures_iter(note_text) {
        let Some(tag) = captures.name("tag") else {
            continue;
        };
        if tag.as_str().trim() != tag_name {
            continue;
        }
        if let Some(value) = captures.name("value") {
            ranges.push((value.start(), value.end()));
        }
    }
    if ranges.is_empty() {
        return Err(format!("Note 标签不存在或没有值: {tag_name}"));
    }
    if ranges.len() > 1 {
        return Err(format!("Note 标签重复，无法按唯一定位路径回写: {tag_name}"));
    }
    let (start, end) = ranges[0];
    let written_text = encode_visible_text_like(&note_text[start..end], translated_text, context)?;
    ensure_encoded_text_valid(
        &note_text[start..end],
        &written_text,
        &format!("Note 标签 {tag_name}"),
    )?;
    Ok(format!(
        "{}{}{}",
        &note_text[..start],
        written_text,
        &note_text[end..]
    ))
}
