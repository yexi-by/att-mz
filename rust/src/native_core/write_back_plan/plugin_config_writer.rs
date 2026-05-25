use super::models::{PLUGINS_FILE_NAME, TextPlanRules, TranslationItem};
use super::text_prepare::prepared_single_text;
use super::utils::parse_usize;
use crate::native_core::write_protocol::ensure_encoded_text_valid;
use serde_json::Value;

pub(super) fn write_plugin_config_item(
    plugins_js: &mut Value,
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let parts: Vec<&str> = item.location_path.split('/').collect();
    if parts.first().copied() != Some(PLUGINS_FILE_NAME) {
        return Err(format!("插件配置路径文件名无效: {}", item.location_path));
    }
    if parts.len() < 3 {
        return Err(format!("插件配置路径不完整: {}", item.location_path));
    }
    let plugin_index = parse_usize(parts[1], &item.location_path)?;
    let top_key = parts[2];
    let plugin = plugins_js
        .as_array_mut()
        .and_then(|plugins| plugins.get_mut(plugin_index))
        .and_then(Value::as_object_mut)
        .ok_or_else(|| format!("插件配置不存在: {}", item.location_path))?;
    let parameters = plugin
        .get_mut("parameters")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| format!("插件参数不是字典: {}", item.location_path))?;
    let current = parameters
        .get_mut(top_key)
        .ok_or_else(|| format!("插件参数不存在: {}", item.location_path))?;
    set_nested_text_value(
        current,
        &parts[3..],
        &prepared_single_text(item, rules)?,
        &item.location_path,
    )
}

pub(super) fn set_nested_text_value(
    current_value: &mut Value,
    path_parts: &[&str],
    translated_text: &str,
    context: &str,
) -> Result<(), String> {
    if path_parts.is_empty() {
        let Some(original_text) = current_value.as_str() else {
            return Err(format!("{context}: 路径没有指向字符串叶子"));
        };
        let written_text = encode_visible_text_like(original_text, translated_text, context)?;
        ensure_encoded_text_valid(original_text, &written_text, context)?;
        *current_value = Value::String(written_text);
        return Ok(());
    }
    if let Some(object) = current_value.as_object_mut() {
        let child = object
            .get_mut(path_parts[0])
            .ok_or_else(|| format!("{context}: 参数键不存在 {}", path_parts[0]))?;
        return set_nested_text_value(child, &path_parts[1..], translated_text, context);
    }
    if let Some(array) = current_value.as_array_mut() {
        let index = parse_usize(path_parts[0], context)?;
        let child = array
            .get_mut(index)
            .ok_or_else(|| format!("{context}: 参数索引越界 {index}"))?;
        return set_nested_text_value(child, &path_parts[1..], translated_text, context);
    }
    if let Some(text) = current_value.as_str() {
        let Some((mut parsed, _shell_depth)) = decode_json_container_text(text) else {
            return Err(format!("{context}: JSON 字符串容器解析失败"));
        };
        let original_text = text.to_string();
        set_nested_text_value(&mut parsed, path_parts, translated_text, context)?;
        *current_value = Value::String(encode_json_container_like(
            &original_text,
            &parsed,
            context,
        )?);
        return Ok(());
    }
    Err(format!("{context}: 路径无法继续下钻"))
}

pub(super) fn encode_visible_text_like(
    original_raw_text: &str,
    translated_visible_text: &str,
    context: &str,
) -> Result<String, String> {
    let shell_depth = json_string_shell_depth(original_raw_text);
    let mut encoded_text = translated_visible_text.to_string();
    for _ in 0..shell_depth {
        encoded_text = serde_json::to_string(&encoded_text)
            .map_err(|error| format!("{context}: JSON 字符串外壳编码失败: {error}"))?;
    }
    Ok(encoded_text)
}

pub(super) fn json_string_shell_depth(raw_text: &str) -> usize {
    let mut current_text = raw_text.to_string();
    let mut shell_depth = 0usize;
    while let Ok(decoded) = serde_json::from_str::<String>(&current_text) {
        shell_depth += 1;
        current_text = decoded;
    }
    shell_depth
}

pub(super) fn decode_json_container_text(raw_text: &str) -> Option<(Value, usize)> {
    let mut current_text = raw_text.to_string();
    let mut shell_depth = 0usize;
    loop {
        let parsed = serde_json::from_str::<Value>(&current_text).ok()?;
        match parsed {
            Value::Array(_) | Value::Object(_) => return Some((parsed, shell_depth)),
            Value::String(text) => {
                shell_depth += 1;
                current_text = text;
            }
            _ => return None,
        }
    }
}

pub(super) fn encode_json_container_like(
    original_raw_text: &str,
    updated_value: &Value,
    context: &str,
) -> Result<String, String> {
    let Some((_original_value, shell_depth)) = decode_json_container_text(original_raw_text) else {
        return Err(format!("{context}: 原文本不是可解析的 JSON 容器字符串"));
    };
    let mut encoded_text = serde_json::to_string(updated_value)
        .map_err(|error| format!("{context}: JSON 容器编码失败: {error}"))?;
    for _ in 0..shell_depth {
        encoded_text = serde_json::to_string(&encoded_text)
            .map_err(|error| format!("{context}: JSON 字符串外壳编码失败: {error}"))?;
    }
    Ok(encoded_text)
}
