use super::models::{SYSTEM_FILE_NAME, TextPlanRules, TranslationItem};
use super::text_prepare::prepared_single_text;
use super::utils::{parse_i64, parse_usize};
use serde_json::Value;
use std::collections::BTreeMap;

pub(super) fn write_system_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let parts: Vec<&str> = item.location_path.split('/').collect();
    let translated_text = prepared_single_text(item, rules)?;
    let system = data_files
        .get_mut(SYSTEM_FILE_NAME)
        .and_then(Value::as_object_mut)
        .ok_or_else(|| "System.json 顶层不是对象".to_string())?;
    match parts.as_slice() {
        [_, key] => {
            system.insert((*key).to_string(), Value::String(translated_text));
            Ok(())
        }
        [_, key, index] => {
            let target_index = parse_usize(index, &item.location_path)?;
            let values = system
                .get_mut(*key)
                .and_then(Value::as_array_mut)
                .ok_or_else(|| format!("System 路径不是数组: {}", item.location_path))?;
            set_array_string(values, target_index, translated_text, &item.location_path)
        }
        [_, "terms", "messages", key] => {
            let messages = system
                .get_mut("terms")
                .and_then(Value::as_object_mut)
                .and_then(|terms| terms.get_mut("messages"))
                .and_then(Value::as_object_mut)
                .ok_or_else(|| "System.json.terms.messages 不是对象".to_string())?;
            messages.insert((*key).to_string(), Value::String(translated_text));
            Ok(())
        }
        [_, "terms", key, index] => {
            let target_index = parse_usize(index, &item.location_path)?;
            let values = system
                .get_mut("terms")
                .and_then(Value::as_object_mut)
                .and_then(|terms| terms.get_mut(*key))
                .and_then(Value::as_array_mut)
                .ok_or_else(|| format!("System terms 路径不是数组: {}", item.location_path))?;
            set_array_string(values, target_index, translated_text, &item.location_path)
        }
        _ => Err(format!("无法识别的 System 路径: {}", item.location_path)),
    }
}

pub(super) fn set_array_string(
    values: &mut [Value],
    index: usize,
    text: String,
    context: &str,
) -> Result<(), String> {
    let slot = values
        .get_mut(index)
        .ok_or_else(|| format!("数组索引越界: {context}"))?;
    *slot = Value::String(text);
    Ok(())
}

pub(super) fn write_base_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let parts: Vec<&str> = item.location_path.split('/').collect();
    if parts.len() != 3 {
        return Err(format!("无法识别的基础数据库路径: {}", item.location_path));
    }
    let file_name = parts[0];
    let item_id = parse_i64(parts[1], &item.location_path)?;
    let key = parts[2];
    let data = data_files
        .get_mut(file_name)
        .and_then(Value::as_array_mut)
        .ok_or_else(|| format!("{file_name} 顶层不是数组"))?;
    for value in data {
        if value.is_null() {
            continue;
        }
        let Some(object) = value.as_object_mut() else {
            return Err(format!("{file_name} 存在非对象条目，不能按 ID 写回"));
        };
        if object.get("id").and_then(Value::as_i64) == Some(item_id) {
            object.insert(
                key.to_string(),
                Value::String(prepared_single_text(item, rules)?),
            );
            return Ok(());
        }
    }
    Err(format!("基础数据库条目不存在: {}", item.location_path))
}
