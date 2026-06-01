use super::models::{TextPlanRules, TranslationItem};
use super::text_prepare::prepared_single_text;
use super::utils::parse_usize;
use serde_json::Value;
use std::collections::BTreeMap;

const NONSTANDARD_DATA_PREFIX: &str = "nonstandard-data/";

enum JsonPathPart {
    Key(String),
    Index(usize),
}

pub(super) fn is_nonstandard_data_item(location_path: &str) -> bool {
    location_path.starts_with(NONSTANDARD_DATA_PREFIX)
}

pub(super) fn nonstandard_data_file_name(location_path: &str) -> Option<&str> {
    let remain = location_path.strip_prefix(NONSTANDARD_DATA_PREFIX)?;
    let (file_name, json_path) = remain.split_once('/')?;
    if !file_name.ends_with(".json") || !json_path.starts_with('$') {
        return None;
    }
    Some(file_name)
}

pub(super) fn write_nonstandard_data_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let (file_name, json_path) = parse_nonstandard_data_location_path(&item.location_path)?;
    let data = data_files
        .get_mut(file_name)
        .ok_or_else(|| format!("非标准 data 文件没有加载，不能写回: {}", item.location_path))?;
    let target = locate_json_path_mut(data, json_path, &item.location_path)?;
    if !target.is_string() {
        return Err(format!(
            "非标准 data 路径当前不是字符串，不能写回: {}",
            item.location_path
        ));
    }
    *target = Value::String(prepared_single_text(item, rules)?);
    Ok(())
}

fn parse_nonstandard_data_location_path(location_path: &str) -> Result<(&str, &str), String> {
    let remain = location_path
        .strip_prefix(NONSTANDARD_DATA_PREFIX)
        .ok_or_else(|| format!("非标准 data 路径缺少前缀: {location_path}"))?;
    let (file_name, json_path) = remain
        .split_once('/')
        .ok_or_else(|| format!("非标准 data 路径缺少 JSONPath: {location_path}"))?;
    if !file_name.ends_with(".json") {
        return Err(format!("非标准 data 文件名无效: {location_path}"));
    }
    Ok((file_name, json_path))
}

fn locate_json_path_mut<'a>(
    root: &'a mut Value,
    json_path: &str,
    context: &str,
) -> Result<&'a mut Value, String> {
    let parts = parse_json_path_parts(json_path, context)?;
    let mut current = root;
    for part in parts {
        match part {
            JsonPathPart::Key(key) => {
                current = current
                    .as_object_mut()
                    .ok_or_else(|| format!("非标准 data 路径需要对象: {context}"))?
                    .get_mut(&key)
                    .ok_or_else(|| format!("非标准 data 对象键不存在: {context}"))?;
            }
            JsonPathPart::Index(index) => {
                current = current
                    .as_array_mut()
                    .ok_or_else(|| format!("非标准 data 路径需要数组: {context}"))?
                    .get_mut(index)
                    .ok_or_else(|| format!("非标准 data 数组索引越界: {context}"))?;
            }
        }
    }
    Ok(current)
}

fn parse_json_path_parts(json_path: &str, context: &str) -> Result<Vec<JsonPathPart>, String> {
    if !json_path.starts_with('$') {
        return Err(format!("非标准 data JSONPath 必须以 $ 开头: {context}"));
    }
    let chars: Vec<char> = json_path.chars().collect();
    let mut parts: Vec<JsonPathPart> = Vec::new();
    let mut index = 1usize;
    while index < chars.len() {
        if chars[index] != '[' {
            return Err(format!("非标准 data JSONPath 只支持括号路径: {context}"));
        }
        index += 1;
        if index >= chars.len() {
            return Err(format!("非标准 data JSONPath 不完整: {context}"));
        }
        if chars[index] == '\'' {
            let (key, next_index) = parse_quoted_key(&chars, index + 1, context)?;
            parts.push(JsonPathPart::Key(key));
            index = next_index;
            continue;
        }
        let start = index;
        while index < chars.len() && chars[index] != ']' {
            index += 1;
        }
        if index >= chars.len() {
            return Err(format!("非标准 data JSONPath 数组段不完整: {context}"));
        }
        let raw_index: String = chars[start..index].iter().collect();
        if raw_index == "*" {
            return Err(format!("非标准 data 写回路径不能包含通配符: {context}"));
        }
        let value = parse_usize(&raw_index, context)?;
        parts.push(JsonPathPart::Index(value));
        index += 1;
    }
    Ok(parts)
}

fn parse_quoted_key(
    chars: &[char],
    mut index: usize,
    context: &str,
) -> Result<(String, usize), String> {
    let mut key = String::new();
    while index < chars.len() {
        let character = chars[index];
        if character == '\\' {
            index += 1;
            if index >= chars.len() {
                return Err(format!("非标准 data JSONPath 对象键转义不完整: {context}"));
            }
            key.push(chars[index]);
            index += 1;
            continue;
        }
        if character == '\'' {
            index += 1;
            if index >= chars.len() || chars[index] != ']' {
                return Err(format!("非标准 data JSONPath 对象键缺少 ]: {context}"));
            }
            return Ok((key, index + 1));
        }
        key.push(character);
        index += 1;
    }
    Err(format!("非标准 data JSONPath 对象键不完整: {context}"))
}
