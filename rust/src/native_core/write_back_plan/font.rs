use super::models::{FontPlanSummary, FontReplacementRecordOut, Layout, PLUGINS_FILE_NAME};
use crate::native_core::font_replacement::{append_json_pointer_part, replace_font_names_in_text};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

pub(super) fn apply_font_replacement(
    layout: &Layout,
    data_files: &mut BTreeMap<String, Value>,
    plugins_js: &mut Value,
    replacement_font_path: Option<&str>,
    source_font_names: Option<&[String]>,
) -> Result<FontPlanSummary, String> {
    let Some(replacement_font_path) = replacement_font_path else {
        return Ok(FontPlanSummary::empty());
    };
    if replacement_font_path.trim().is_empty() {
        return Ok(FontPlanSummary::empty());
    }
    let replacement_path = Path::new(replacement_font_path);
    let Some(target_font_name) = replacement_path
        .file_name()
        .and_then(|name| name.to_str())
        .map(|name| name.to_string())
    else {
        return Err(format!(
            "替换字体路径没有有效文件名: {replacement_font_path}"
        ));
    };
    let old_font_names = match source_font_names {
        Some(names) => names.to_vec(),
        None => collect_replaced_font_names(&layout.content_root.join("fonts"), &target_font_name)?,
    };
    let font_tokens = build_font_reference_tokens(&old_font_names);
    if font_tokens.is_empty() {
        return Ok(FontPlanSummary {
            target_font_name: Some(target_font_name),
            source_font_count: old_font_names.len(),
            replaced_reference_count: 0,
            copied: true,
            records: Vec::new(),
        });
    }
    let mut replaced_count = 0usize;
    let mut records: Vec<FontReplacementRecordOut> = Vec::new();
    for (file_name, value) in data_files.iter_mut() {
        replaced_count += replace_font_references_in_value(
            file_name,
            value,
            "",
            &font_tokens,
            &target_font_name,
            &mut records,
        )?;
    }
    if let Some(plugins) = plugins_js.as_array_mut() {
        for (index, plugin) in plugins.iter_mut().enumerate() {
            replaced_count += replace_font_references_in_value(
                PLUGINS_FILE_NAME,
                plugin,
                &format!("/{index}"),
                &font_tokens,
                &target_font_name,
                &mut records,
            )?;
        }
    }
    records.sort_by(|left, right| {
        (left.file_name.as_str(), left.value_path.as_str())
            .cmp(&(right.file_name.as_str(), right.value_path.as_str()))
    });
    Ok(FontPlanSummary {
        target_font_name: Some(target_font_name),
        source_font_count: old_font_names.len(),
        replaced_reference_count: replaced_count,
        copied: true,
        records,
    })
}

pub(super) fn collect_replaced_font_names(
    font_dir: &Path,
    replacement_font_name: &str,
) -> Result<Vec<String>, String> {
    if !font_dir.exists() {
        return Ok(Vec::new());
    }
    if !font_dir.is_dir() {
        return Err(format!("游戏字体路径不是目录: {}", font_dir.display()));
    }
    let replacement_lower = replacement_font_name.to_lowercase();
    let mut font_names: Vec<String> = Vec::new();
    for entry in fs::read_dir(font_dir).map_err(|error| format!("读取字体目录失败: {error}"))?
    {
        let entry = entry.map_err(|error| format!("读取字体目录项失败: {error}"))?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| format!("字体文件名不是有效 UTF-8: {}", path.display()))?;
        let lower_name = name.to_lowercase();
        if lower_name == replacement_lower {
            continue;
        }
        if !(lower_name.ends_with(".ttf")
            || lower_name.ends_with(".otf")
            || lower_name.ends_with(".woff")
            || lower_name.ends_with(".woff2")
            || lower_name.ends_with(".eot"))
        {
            continue;
        }
        font_names.push(name.to_string());
    }
    font_names.sort();
    Ok(font_names)
}

pub(super) fn build_font_reference_tokens(old_font_names: &[String]) -> Vec<String> {
    let mut tokens: Vec<String> = Vec::new();
    for old_font_name in old_font_names {
        if !tokens.contains(old_font_name) {
            tokens.push(old_font_name.clone());
        }
        let stem = Path::new(old_font_name)
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_string();
        if !stem.is_empty() && !tokens.contains(&stem) {
            tokens.push(stem);
        }
    }
    tokens.sort_by_key(|item| std::cmp::Reverse(item.len()));
    tokens
}

pub(super) fn replace_font_references_in_value(
    file_name: &str,
    value: &mut Value,
    value_path: &str,
    old_font_names: &[String],
    replacement_font_name: &str,
    records: &mut Vec<FontReplacementRecordOut>,
) -> Result<usize, String> {
    match value {
        Value::String(text) => {
            let Some((replaced_text, replaced_count)) =
                replace_font_names_in_text(text, old_font_names, replacement_font_name)
            else {
                return Ok(0);
            };
            let original_text = std::mem::replace(text, replaced_text.clone());
            records.push(FontReplacementRecordOut {
                file_name: file_name.to_string(),
                value_path: value_path.to_string(),
                original_text,
                replaced_text,
                replacement_font_name: replacement_font_name.to_string(),
            });
            Ok(replaced_count)
        }
        Value::Array(values) => {
            let mut replaced_count = 0usize;
            for (index, item) in values.iter_mut().enumerate() {
                let child_path = append_json_pointer_part(value_path, &index.to_string());
                replaced_count += replace_font_references_in_value(
                    file_name,
                    item,
                    &child_path,
                    old_font_names,
                    replacement_font_name,
                    records,
                )?;
            }
            Ok(replaced_count)
        }
        Value::Object(values) => {
            let mut replaced_count = 0usize;
            for (key, item) in values.iter_mut() {
                let child_path = append_json_pointer_part(value_path, key);
                replaced_count += replace_font_references_in_value(
                    file_name,
                    item,
                    &child_path,
                    old_font_names,
                    replacement_font_name,
                    records,
                )?;
            }
            Ok(replaced_count)
        }
        _ => Ok(0),
    }
}
