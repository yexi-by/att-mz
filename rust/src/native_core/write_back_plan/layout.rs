use super::models::{
    DATA_ORIGIN_DIRECTORY_NAME, EngineKind, Layout, PLUGIN_SOURCE_ORIGIN_DIRECTORY_NAME,
    PLUGINS_FILE_NAME, PLUGINS_ORIGIN_FILE_NAME,
};
use super::utils::is_map_file;
use crate::native_core::javascript_ast::parse_javascript_string_spans;
use rayon::prelude::*;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

pub(super) fn resolve_layout(game_path: &Path) -> Result<Layout, String> {
    let direct_data = game_path.join("data");
    let direct_plugins = game_path.join("js").join(PLUGINS_FILE_NAME);
    let (content_root, engine_kind) = if direct_data.is_dir() && direct_plugins.is_file() {
        (game_path.to_path_buf(), EngineKind::Mz)
    } else {
        let www_root = game_path.join("www");
        let www_data = www_root.join("data");
        let www_plugins = www_root.join("js").join(PLUGINS_FILE_NAME);
        if !www_data.is_dir() || !www_plugins.is_file() {
            return Err(format!(
                "未找到可识别的 RPG Maker 游戏结构: {}",
                game_path.display()
            ));
        }
        (www_root, EngineKind::Mv)
    };
    let js_dir = content_root.join("js");
    Ok(Layout {
        engine_kind,
        content_root: content_root.clone(),
        data_dir: content_root.join("data"),
        data_origin_dir: content_root.join(DATA_ORIGIN_DIRECTORY_NAME),
        plugins_path: js_dir.join(PLUGINS_FILE_NAME),
        plugins_origin_path: js_dir.join(PLUGINS_ORIGIN_FILE_NAME),
        plugin_source_dir: js_dir.join("plugins"),
        plugin_source_origin_dir: js_dir.join(PLUGIN_SOURCE_ORIGIN_DIRECTORY_NAME),
    })
}
pub(super) fn read_origin_data_files(layout: &Layout) -> Result<BTreeMap<String, Value>, String> {
    read_origin_data_files_by_name(layout, None)
}

pub(super) fn read_selected_origin_data_files(
    layout: &Layout,
    file_names: &BTreeSet<String>,
) -> Result<BTreeMap<String, Value>, String> {
    read_origin_data_files_by_name(layout, Some(file_names))
}

pub(super) fn origin_data_file_names(layout: &Layout) -> Result<BTreeSet<String>, String> {
    collect_origin_data_file_paths(layout, None).map(|paths| {
        paths
            .into_iter()
            .filter_map(|path| {
                path.file_name()
                    .and_then(|name| name.to_str())
                    .map(str::to_string)
            })
            .collect()
    })
}

fn read_origin_data_files_by_name(
    layout: &Layout,
    file_names: Option<&BTreeSet<String>>,
) -> Result<BTreeMap<String, Value>, String> {
    let paths = collect_origin_data_file_paths(layout, file_names)?;
    let pairs: Vec<(String, Value)> = paths
        .par_iter()
        .map(|path| read_json_file_pair(path))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(pairs.into_iter().collect())
}

fn collect_origin_data_file_paths(
    layout: &Layout,
    file_names: Option<&BTreeSet<String>>,
) -> Result<Vec<PathBuf>, String> {
    if !layout.data_origin_dir.is_dir() {
        return Err(format!(
            "缺少原始 data 备份，不能生成 Rust 重建计划: {}",
            layout.data_origin_dir.display()
        ));
    }
    if file_names.is_some_and(BTreeSet::is_empty) {
        return Ok(Vec::new());
    }
    let mut paths: Vec<PathBuf> = Vec::new();
    for entry in fs::read_dir(&layout.data_origin_dir)
        .map_err(|error| format!("读取原始 data 目录失败: {error}"))?
    {
        let entry = entry.map_err(|error| format!("读取原始 data 目录项失败: {error}"))?;
        let path = entry.path();
        let file_name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        if path.is_file()
            && path.extension().is_some_and(|ext| ext == "json")
            && is_standard_data_file_name(file_name)
            && file_names.is_none_or(|names| names.contains(file_name))
        {
            paths.push(path);
        }
    }
    paths.sort();
    Ok(paths)
}

pub(super) fn read_json_file_pair(path: &Path) -> Result<(String, Value), String> {
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| format!("data 文件名不是有效 UTF-8: {}", path.display()))?
        .to_string();
    let text = fs::read_to_string(path)
        .map_err(|error| format!("读取 data 文件失败 {}: {error}", path.display()))?;
    let value = serde_json::from_str(&text)
        .map_err(|error| format!("解析 data JSON 失败 {}: {error}", path.display()))?;
    Ok((file_name, value))
}

pub(super) fn is_standard_data_file_name(file_name: &str) -> bool {
    matches!(
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
    ) || is_map_file(file_name)
}

pub(super) fn read_plugins_origin_file(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("读取原始插件配置失败 {}: {error}", path.display()))?;
    let start = text
        .find('[')
        .ok_or_else(|| format!("插件配置缺少数组起点: {}", path.display()))?;
    let end = text
        .rfind(']')
        .ok_or_else(|| format!("插件配置缺少数组终点: {}", path.display()))?;
    if end < start {
        return Err(format!("插件配置数组范围无效: {}", path.display()));
    }
    json5::from_str(&text[start..=end])
        .map_err(|error| format!("解析原始插件配置失败 {}: {error}", path.display()))
}

pub(super) fn assert_active_plugin_sources_readable(
    layout: &Layout,
    plugins_js: &Value,
) -> Result<(), String> {
    let file_names = enabled_plugin_source_file_names(plugins_js)?;
    file_names
        .par_iter()
        .try_for_each(|file_name| -> Result<(), String> {
            let path = layout.plugin_source_dir.join(file_name);
            let source = fs::read_to_string(&path)
                .map_err(|error| format!("插件源码读取失败 {}: {error}", path.display()))?;
            let scan = parse_javascript_string_spans(&source)
                .map_err(|error| format!("插件源码 JS 语法检查失败 {file_name}: {error}"))?;
            if scan.has_error {
                return Err(format!("插件源码 JS 语法检查失败: {file_name}"));
            }
            Ok(())
        })
}

pub(super) fn enabled_plugin_source_file_names(plugins_js: &Value) -> Result<Vec<String>, String> {
    let plugins = plugins_js
        .as_array()
        .ok_or_else(|| "plugins.js 顶层不是数组，不能检查启用插件源码".to_string())?;
    let mut file_names = Vec::new();
    for (plugin_index, plugin) in plugins.iter().enumerate() {
        let Some(plugin_object) = plugin.as_object() else {
            return Err(format!(
                "plugins.js 第 {plugin_index} 个插件不是对象，不能检查启用插件源码"
            ));
        };
        if plugin_object.get("status").and_then(Value::as_bool) != Some(true) {
            continue;
        }
        let plugin_name = plugin_object
            .get("name")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .ok_or_else(|| {
                format!("plugins.js 第 {plugin_index} 个启用插件缺少 name，不能检查插件源码")
            })?;
        file_names.push(format!("{plugin_name}.js"));
    }
    file_names.sort();
    file_names.dedup();
    Ok(file_names)
}

pub(super) fn read_origin_plugin_source_files(
    dir: &Path,
) -> Result<BTreeMap<String, String>, String> {
    if !dir.is_dir() {
        return Err(format!("缺少原始插件源码备份目录: {}", dir.display()));
    }
    let mut paths: Vec<PathBuf> = Vec::new();
    for entry in fs::read_dir(dir).map_err(|error| format!("读取原始插件源码目录失败: {error}"))?
    {
        let entry = entry.map_err(|error| format!("读取原始插件源码目录项失败: {error}"))?;
        let path = entry.path();
        if path.is_file() && path.extension().is_some_and(|ext| ext == "js") {
            paths.push(path);
        }
    }
    paths.sort();
    let pairs: Vec<(String, String)> = paths
        .par_iter()
        .map(|path| {
            let file_name = path
                .file_name()
                .and_then(|name| name.to_str())
                .ok_or_else(|| format!("插件源码文件名不是有效 UTF-8: {}", path.display()))?
                .to_string();
            let text = fs::read_to_string(path)
                .map_err(|error| format!("读取插件源码失败 {}: {error}", path.display()))?;
            Ok((file_name, text))
        })
        .collect::<Result<Vec<_>, String>>()?;
    Ok(pairs.into_iter().collect())
}
