//! 写回与重建热路径计划生成。
//!
//! 本模块面向大规模游戏目录，直接读取 SQLite 和可信源文件，在 Rust 侧并发生成
//! 待替换文件内容。Python 仍负责 CLI、事务替换、数据库写入和报告渲染。

mod command_writer;
mod data_writer;
mod font;
mod layout;
mod models;
mod mv_virtual_namebox;
mod note_writer;
mod plugin_config_writer;
mod plugin_source;
mod quality_gate;
mod repository;
mod terminology;
#[cfg(test)]
mod test_support;
mod text_prepare;
mod utils;

use self::command_writer::{
    CommandSortKey, command_sort_key, is_event_command_item, write_command_item,
};
use self::data_writer::{write_base_item, write_system_item};
use self::font::apply_font_replacement;
use self::layout::{
    assert_active_plugin_sources_readable, origin_data_file_names, read_origin_data_files,
    read_origin_plugin_source_files, read_plugins_origin_file, read_selected_origin_data_files,
    resolve_layout,
};
use self::models::{
    COMMON_EVENTS_FILE_NAME, FontPlanSummary, MvVirtualNameboxRule, MvVirtualSpeakerPolicy,
    PLUGINS_FILE_NAME, PlanSummary, PlannedFile, SYSTEM_FILE_NAME, SettingPayload,
    TROOPS_FILE_NAME, TextPlanRules, TranslationItem, WriteBackPlan, WritePlanMode,
};
use self::note_writer::{is_note_tag_path, write_note_tag_item};
use self::plugin_config_writer::write_plugin_config_item;
use self::plugin_source::write_plugin_source_files;
use self::quality_gate::{
    assert_saved_translation_quality_passed, quality_gate_items_for_write_plan,
};
use self::repository::{
    filter_translation_items_by_policy, open_readonly_connection, read_mv_virtual_namebox_rules,
    read_source_residual_rules, read_terminology_terms, read_translation_items,
};
use self::terminology::apply_terminology;
use self::utils::{build_changed_file, externalize_planned_file_contents, is_map_file};
use crate::native_core::pool::run_with_optional_pool;
use rayon::prelude::*;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;
use std::time::Instant;

/// 构建写回或重建计划。
pub(crate) fn build_write_back_plan_impl(
    game_path: &str,
    db_path: &str,
    setting_payload_json: &str,
    mode: &str,
    confirm_font_overwrite: bool,
) -> Result<String, String> {
    run_with_optional_pool(|| {
        build_write_back_plan_inner(
            game_path,
            db_path,
            setting_payload_json,
            mode,
            confirm_font_overwrite,
        )
    })?
}

fn build_write_back_plan_inner(
    game_path: &str,
    db_path: &str,
    setting_payload_json: &str,
    mode: &str,
    confirm_font_overwrite: bool,
) -> Result<String, String> {
    let started = Instant::now();
    let plan_mode = WritePlanMode::parse(mode)?;
    let mut setting_payload: SettingPayload = serde_json::from_str(setting_payload_json)
        .map_err(|error| format!("写回计划配置 JSON 无效: {error}"))?;
    let text_rules = TextPlanRules::from_payload(&setting_payload)?;
    let quality_text_rules = setting_payload
        .quality_text_rules
        .take()
        .ok_or_else(|| "写回计划缺少 Rust 质检文本规则".to_string())?;
    let allowed_translation_paths = setting_payload
        .allowed_translation_paths
        .as_deref()
        .ok_or_else(|| {
            "写回计划缺少 allowed_translation_paths，不能确定当前可写文本范围".to_string()
        })?;

    let mut timings_ms: BTreeMap<String, u128> = BTreeMap::new();
    let layout = resolve_layout(Path::new(game_path))?;
    let connection = open_readonly_connection(Path::new(db_path))?;

    let load_started = Instant::now();
    let mut plugins_js = read_plugins_origin_file(&layout.plugins_origin_path)?;
    let translated_items = filter_translation_items_by_policy(
        read_translation_items(&connection)?,
        allowed_translation_paths,
    )?;
    let source_residual_rules = read_source_residual_rules(&connection)?;
    let terminology = read_terminology_terms(&connection)?;
    let mv_virtual_namebox_rules = read_mv_virtual_namebox_rules(&connection)?;
    let available_data_file_names = origin_data_file_names(&layout)?;
    let data_file_names_to_load = data_file_names_for_load(
        plan_mode,
        &available_data_file_names,
        &translated_items,
        &terminology,
        &mv_virtual_namebox_rules,
        font_replacement_requested(&setting_payload, confirm_font_overwrite),
    );
    let mut data_files = if data_file_names_to_load == available_data_file_names {
        read_origin_data_files(&layout)?
    } else {
        read_selected_origin_data_files(&layout, &data_file_names_to_load)?
    };
    timings_ms.insert(
        "load_inputs".to_string(),
        load_started.elapsed().as_millis(),
    );

    let active_audit_started = Instant::now();
    assert_active_plugin_sources_readable(&layout, &plugins_js)?;
    timings_ms.insert(
        "active_runtime_audit".to_string(),
        active_audit_started.elapsed().as_millis(),
    );

    let quality_started = Instant::now();
    let quality_gate_items = quality_gate_items_for_write_plan(&translated_items, &text_rules)?;
    assert_saved_translation_quality_passed(
        &quality_gate_items,
        quality_text_rules,
        source_residual_rules,
    )?;
    timings_ms.insert(
        "quality_gate".to_string(),
        quality_started.elapsed().as_millis(),
    );

    let apply_started = Instant::now();
    let mut plugin_source_items: Vec<TranslationItem> = Vec::new();
    let mut command_items: Vec<TranslationItem> = Vec::new();
    let mut data_item_count = 0usize;
    let mut plugin_item_count = 0usize;

    for item in &translated_items {
        if item.location_path.starts_with("js/plugins/") {
            plugin_source_items.push(item.clone());
            plugin_item_count += 1;
            continue;
        }
        if item.location_path.starts_with("plugins.js/") {
            write_plugin_config_item(&mut plugins_js, item, &text_rules)?;
            plugin_item_count += 1;
            continue;
        }
        if is_note_tag_path(&item.location_path) {
            write_note_tag_item(&mut data_files, item, &text_rules)?;
            data_item_count += 1;
            continue;
        }
        if item.location_path.starts_with("System.json/") {
            write_system_item(&mut data_files, item, &text_rules)?;
            data_item_count += 1;
            continue;
        }
        if is_event_command_item(&item.location_path) {
            command_items.push(item.clone());
            data_item_count += 1;
            continue;
        }
        write_base_item(&mut data_files, item, &text_rules)?;
        data_item_count += 1;
    }

    let mut command_items_with_keys: Vec<(CommandSortKey, TranslationItem)> = command_items
        .into_iter()
        .map(|item| command_sort_key(&item).map(|key| (key, item)))
        .collect::<Result<Vec<_>, String>>()?;
    command_items_with_keys.sort_by(|left, right| left.0.cmp(&right.0));
    command_items_with_keys.reverse();
    for (_key, item) in &command_items_with_keys {
        write_command_item(
            &mut data_files,
            item,
            &mv_virtual_namebox_rules,
            &terminology,
            &text_rules,
        )?;
    }

    let terminology_written_count = apply_terminology(
        &mut data_files,
        &terminology,
        &layout,
        &mv_virtual_namebox_rules,
    )?;
    let font_summary = if confirm_font_overwrite {
        apply_font_replacement(
            &layout,
            &mut data_files,
            &mut plugins_js,
            setting_payload.replacement_font_path.as_deref(),
            setting_payload.source_font_names.as_deref(),
        )?
    } else {
        FontPlanSummary::empty()
    };
    let should_restore_all_plugin_sources = plan_mode == WritePlanMode::RebuildActiveRuntime;
    let plugin_source_files =
        if should_restore_all_plugin_sources || !plugin_source_items.is_empty() {
            read_origin_plugin_source_files(&layout.plugin_source_origin_dir)?
        } else {
            BTreeMap::new()
        };
    let plugin_source_result = write_plugin_source_files(
        plugin_source_files,
        plugin_source_items,
        should_restore_all_plugin_sources,
    )?;
    let plugin_source_runtime_map_count = plugin_source_result.runtime_maps.len();
    timings_ms.insert(
        "apply_translations".to_string(),
        apply_started.elapsed().as_millis(),
    );

    if plan_mode == WritePlanMode::QualityGate {
        timings_ms.insert("total".to_string(), started.elapsed().as_millis());
        let summary = PlanSummary {
            data_item_count,
            plugin_item_count,
            terminology_written_count,
            target_font_name: font_summary.target_font_name,
            source_font_count: font_summary.source_font_count,
            replaced_font_reference_count: font_summary.replaced_reference_count,
            font_copied: font_summary.copied,
            planned_file_count: 0,
            skipped_file_count: 0,
            plugin_source_ast_source_scan_file_count: plugin_source_result
                .source_ast_scan_file_count,
            plugin_source_ast_runtime_scan_file_count: plugin_source_result
                .runtime_ast_scan_file_count,
            plugin_source_runtime_map_count,
        };
        let plan = WriteBackPlan {
            status: "ok".to_string(),
            mode: plan_mode.as_str().to_string(),
            files: Vec::new(),
            plugin_source_runtime_write_maps: plugin_source_result.runtime_maps,
            font_replacement_records: font_summary.records,
            summary,
            timings_ms,
        };
        return serde_json::to_string(&plan)
            .map_err(|error| format!("写回计划输出 JSON 失败: {error}"));
    }

    let diff_started = Instant::now();
    let mut files: Vec<PlannedFile> = Vec::new();
    let mut skipped_file_count = 0usize;
    let data_file_names = data_file_names_for_diff(
        plan_mode,
        &data_files,
        &translated_items,
        &terminology,
        &font_summary,
    );
    let data_file_results: Vec<Result<Option<PlannedFile>, String>> = data_files
        .iter()
        .filter(|(file_name, _value)| data_file_names.contains(*file_name))
        .collect::<Vec<_>>()
        .into_par_iter()
        .map(|(file_name, value)| {
            let content = format!(
                "{}\n",
                serde_json::to_string_pretty(&value)
                    .map_err(|error| format!("序列化 data 文件失败 {file_name}: {error}"))?
            );
            let target_path = layout.data_dir.join(file_name);
            build_changed_file(&target_path, &format!("data/{file_name}"), content)
        })
        .collect();
    append_changed_file_results(&mut files, &mut skipped_file_count, data_file_results)?;
    let plugins_content = format!(
        "var $plugins = {};\n",
        serde_json::to_string_pretty(&plugins_js)
            .map_err(|error| format!("序列化插件配置失败: {error}"))?
    );
    append_changed_file_results(
        &mut files,
        &mut skipped_file_count,
        vec![build_changed_file(
            &layout.plugins_path,
            "js/plugins.js",
            plugins_content,
        )],
    )?;
    let plugin_source_results: Vec<Result<Option<PlannedFile>, String>> = plugin_source_result
        .output_files
        .into_iter()
        .collect::<Vec<_>>()
        .into_par_iter()
        .map(|(file_name, content)| {
            let target_path = layout.plugin_source_dir.join(&file_name);
            build_changed_file(&target_path, &format!("js/plugins/{file_name}"), content)
        })
        .collect();
    append_changed_file_results(&mut files, &mut skipped_file_count, plugin_source_results)?;
    timings_ms.insert(
        "diff_outputs".to_string(),
        diff_started.elapsed().as_millis(),
    );
    if let Some(output_dir) = setting_payload.plan_content_output_dir.as_deref() {
        let externalize_started = Instant::now();
        externalize_planned_file_contents(&mut files, output_dir)?;
        timings_ms.insert(
            "externalize_file_contents".to_string(),
            externalize_started.elapsed().as_millis(),
        );
    }
    timings_ms.insert("total".to_string(), started.elapsed().as_millis());

    let summary = PlanSummary {
        data_item_count,
        plugin_item_count,
        terminology_written_count,
        target_font_name: font_summary.target_font_name,
        source_font_count: font_summary.source_font_count,
        replaced_font_reference_count: font_summary.replaced_reference_count,
        font_copied: font_summary.copied,
        planned_file_count: files.len(),
        skipped_file_count,
        plugin_source_ast_source_scan_file_count: plugin_source_result.source_ast_scan_file_count,
        plugin_source_ast_runtime_scan_file_count: plugin_source_result.runtime_ast_scan_file_count,
        plugin_source_runtime_map_count,
    };
    let plan = WriteBackPlan {
        status: "ok".to_string(),
        mode: plan_mode.as_str().to_string(),
        files,
        plugin_source_runtime_write_maps: plugin_source_result.runtime_maps,
        font_replacement_records: font_summary.records,
        summary,
        timings_ms,
    };
    serde_json::to_string(&plan).map_err(|error| format!("写回计划输出 JSON 失败: {error}"))
}

fn append_changed_file_results(
    files: &mut Vec<PlannedFile>,
    skipped_file_count: &mut usize,
    results: Vec<Result<Option<PlannedFile>, String>>,
) -> Result<(), String> {
    for result in results {
        match result? {
            Some(file) => files.push(file),
            None => *skipped_file_count += 1,
        }
    }
    Ok(())
}

fn font_replacement_requested(
    setting_payload: &SettingPayload,
    confirm_font_overwrite: bool,
) -> bool {
    confirm_font_overwrite
        && setting_payload
            .replacement_font_path
            .as_deref()
            .is_some_and(|path| !path.trim().is_empty())
}

fn data_file_names_for_load(
    plan_mode: WritePlanMode,
    available_data_file_names: &BTreeSet<String>,
    translated_items: &[TranslationItem],
    terminology: &HashMap<String, HashMap<String, String>>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    font_replacement_requested: bool,
) -> BTreeSet<String> {
    if plan_mode == WritePlanMode::RebuildActiveRuntime || font_replacement_requested {
        return available_data_file_names.clone();
    }
    let mut names = data_file_names_for_translation_items(translated_items);
    add_terminology_data_file_names(&mut names, available_data_file_names, terminology);
    add_mv_actor_name_dependency(
        &mut names,
        available_data_file_names,
        translated_items,
        terminology,
        mv_virtual_namebox_rules,
    );
    names
}

fn data_file_names_for_diff(
    plan_mode: WritePlanMode,
    data_files: &BTreeMap<String, serde_json::Value>,
    translated_items: &[TranslationItem],
    terminology: &HashMap<String, HashMap<String, String>>,
    font_summary: &FontPlanSummary,
) -> BTreeSet<String> {
    if plan_mode == WritePlanMode::RebuildActiveRuntime || font_summary.replaced_reference_count > 0
    {
        return data_files.keys().cloned().collect();
    }

    let mut names = data_file_names_for_translation_items(translated_items);
    names.retain(|file_name| data_files.contains_key(file_name));
    add_terminology_data_file_names(
        &mut names,
        &data_files.keys().cloned().collect(),
        terminology,
    );
    names
}

fn data_file_names_for_translation_items(translated_items: &[TranslationItem]) -> BTreeSet<String> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for item in translated_items {
        let Some(file_name) = item.location_path.split('/').next() else {
            continue;
        };
        if file_name == PLUGINS_FILE_NAME || item.location_path.starts_with("js/plugins/") {
            continue;
        }
        names.insert(file_name.to_string());
    }
    names
}

fn add_terminology_data_file_names(
    names: &mut BTreeSet<String>,
    available_data_file_names: &BTreeSet<String>,
    terminology: &HashMap<String, HashMap<String, String>>,
) {
    if terminology.contains_key("speaker_names") {
        add_map_file_names(names, available_data_file_names);
        add_if_present(names, available_data_file_names, COMMON_EVENTS_FILE_NAME);
        add_if_present(names, available_data_file_names, TROOPS_FILE_NAME);
    }
    if terminology.contains_key("map_display_names") {
        add_map_file_names(names, available_data_file_names);
    }
    for (file_name, category) in [
        ("Actors.json", "actor_names"),
        ("Actors.json", "actor_nicknames"),
        ("Classes.json", "class_names"),
        ("Skills.json", "skill_names"),
        ("Items.json", "item_names"),
        ("Weapons.json", "weapon_names"),
        ("Armors.json", "armor_names"),
        ("Enemies.json", "enemy_names"),
        ("States.json", "state_names"),
    ] {
        if terminology.contains_key(category) {
            add_if_present(names, available_data_file_names, file_name);
        }
    }
    if [
        "system_elements",
        "system_skill_types",
        "system_weapon_types",
        "system_armor_types",
        "system_equip_types",
    ]
    .iter()
    .any(|category| terminology.contains_key(*category))
    {
        add_if_present(names, available_data_file_names, SYSTEM_FILE_NAME);
    }
}

fn add_mv_actor_name_dependency(
    names: &mut BTreeSet<String>,
    available_data_file_names: &BTreeSet<String>,
    translated_items: &[TranslationItem],
    terminology: &HashMap<String, HashMap<String, String>>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
) {
    if !mv_virtual_namebox_rules
        .iter()
        .any(|rule| matches!(rule.speaker_policy, MvVirtualSpeakerPolicy::ActorName))
    {
        return;
    }
    let writes_mv_dialogue =
        translated_items
            .iter()
            .any(|item| match item.location_path.split('/').next() {
                Some(file_name) => {
                    file_name == COMMON_EVENTS_FILE_NAME
                        || file_name == TROOPS_FILE_NAME
                        || is_map_file(file_name)
                }
                None => false,
            });
    if writes_mv_dialogue || terminology.contains_key("speaker_names") {
        add_if_present(names, available_data_file_names, "Actors.json");
    }
}

fn add_map_file_names(names: &mut BTreeSet<String>, available_data_file_names: &BTreeSet<String>) {
    for file_name in available_data_file_names
        .iter()
        .filter(|file_name| is_map_file(file_name))
    {
        names.insert(file_name.clone());
    }
}

fn add_if_present(
    names: &mut BTreeSet<String>,
    available_data_file_names: &BTreeSet<String>,
    file_name: &str,
) {
    if available_data_file_names.contains(file_name) {
        names.insert(file_name.to_string());
    }
}
