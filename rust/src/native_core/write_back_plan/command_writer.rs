use super::models::{
    COMMON_EVENTS_FILE_NAME, MvVirtualNameboxRule, MvVirtualSpeaker, TROOPS_FILE_NAME,
    TextFactRenderPart, TextPlanRules, TranslationItem,
};
use super::mv_virtual_namebox::{
    ensure_mv_translation_body_is_clean, parse_mv_virtual_speaker_line, read_mv_render_speaker,
    render_mv_virtual_speaker_line,
};
use super::plugin_config_writer::set_nested_text_value;
use super::text_prepare::{prepared_lines, prepared_long_lines, prepared_single_text};
use super::utils::{is_map_file, parse_i64, parse_usize};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, HashMap};

pub(super) type CommandSortKey = (String, Vec<i64>, i64);

pub(super) fn command_sort_key(item: &TranslationItem) -> Result<CommandSortKey, String> {
    let anchor_path = if item.item_type == "long_text" && !item.source_line_paths.is_empty() {
        item.source_line_paths
            .last()
            .cloned()
            .unwrap_or_else(|| item.location_path.clone())
    } else {
        item.location_path.clone()
    };
    let parts: Vec<&str> = anchor_path.split('/').collect();
    let file_name = parts.first().copied().unwrap_or_default().to_string();
    if is_map_file(&file_name) {
        return Ok((
            file_name,
            vec![
                parse_sort_path_number(&parts, 1, &anchor_path)?,
                parse_sort_path_number(&parts, 2, &anchor_path)?,
            ],
            parse_sort_path_number(&parts, 3, &anchor_path)?,
        ));
    }
    if file_name == COMMON_EVENTS_FILE_NAME {
        return Ok((
            file_name,
            vec![parse_sort_path_number(&parts, 1, &anchor_path)?],
            parse_sort_path_number(&parts, 2, &anchor_path)?,
        ));
    }
    Ok((
        file_name,
        vec![
            parse_sort_path_number(&parts, 1, &anchor_path)?,
            parse_sort_path_number(&parts, 2, &anchor_path)?,
        ],
        parse_sort_path_number(&parts, 3, &anchor_path)?,
    ))
}

fn parse_sort_path_number(
    parts: &[&str],
    index: usize,
    location_path: &str,
) -> Result<i64, String> {
    let text = parts
        .get(index)
        .copied()
        .ok_or_else(|| format!("事件指令排序路径不完整: {location_path}"))?;
    parse_i64(text, location_path)
}

pub(super) fn is_event_command_item(location_path: &str) -> bool {
    let Some(file_name) = location_path.split('/').next() else {
        return false;
    };
    is_map_file(file_name) || file_name == COMMON_EVENTS_FILE_NAME || file_name == TROOPS_FILE_NAME
}

pub(super) fn write_command_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    terminology: &HashMap<String, HashMap<String, String>>,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let command_code = {
        let (commands, command_index) = locate_commands_mut(data_files, &item.location_path)?;
        commands
            .get(command_index)
            .and_then(Value::as_object)
            .and_then(|command| command.get("code"))
            .and_then(Value::as_i64)
            .ok_or_else(|| format!("事件指令 code 无效: {}", item.location_path))?
    };
    if item.item_type == "short_text" {
        return write_event_command_text_item(data_files, item, rules);
    }
    if item.item_type == "array" {
        let (commands, command_index) = locate_commands_mut(data_files, &item.location_path)?;
        let command = commands
            .get_mut(command_index)
            .and_then(Value::as_object_mut)
            .ok_or_else(|| format!("事件指令不是对象: {}", item.location_path))?;
        if command.get("code").and_then(Value::as_i64) != Some(102) {
            return Err(format!("路径不是 CHOICES 指令: {}", item.location_path));
        }
        let parameters = command
            .get_mut("parameters")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("事件指令 parameters 不是数组: {}", item.location_path))?;
        if parameters.is_empty() {
            parameters.push(Value::Array(
                prepared_lines(item, rules)?
                    .into_iter()
                    .map(Value::String)
                    .collect(),
            ));
        } else {
            parameters[0] = Value::Array(
                prepared_lines(item, rules)?
                    .into_iter()
                    .map(Value::String)
                    .collect(),
            );
        }
        return Ok(());
    }
    if item.item_type == "long_text" {
        if command_code == 101
            && !mv_virtual_namebox_rules.is_empty()
            && let Some(virtual_speaker) = find_mv_virtual_speaker_for_name_command(
                data_files,
                item,
                mv_virtual_namebox_rules,
            )?
        {
            return write_mv_virtual_name_text_item(
                data_files,
                item,
                &virtual_speaker,
                terminology,
                rules,
            );
        }
        let expected_code = if command_code == 405 { 405 } else { 401 };
        return write_line_commands_by_paths(data_files, item, expected_code, rules);
    }
    Err(format!("事件指令 item_type 无法处理: {}", item.item_type))
}

pub(super) fn write_line_commands_by_paths(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    expected_code: i64,
    rules: &TextPlanRules,
) -> Result<(), String> {
    if item.source_line_paths.is_empty() {
        return Err(format!("长文本缺少逐行写入路径: {}", item.location_path));
    }
    let translation_lines = prepared_long_lines(item, rules)?;
    let insertion_anchor_path = item
        .source_line_paths
        .last()
        .ok_or_else(|| format!("长文本缺少插入锚点: {}", item.location_path))?;
    write_prepared_line_commands_by_paths(
        data_files,
        expected_code,
        &item.source_line_paths,
        insertion_anchor_path,
        &translation_lines,
    )
}

pub(super) fn write_prepared_line_commands_by_paths(
    data_files: &mut BTreeMap<String, Value>,
    expected_code: i64,
    source_line_paths: &[String],
    insertion_anchor_path: &str,
    translation_lines: &[String],
) -> Result<(), String> {
    let existing_line_count = source_line_paths.len();
    let write_line_count = existing_line_count.min(translation_lines.len());
    for (source_line_path, translated_text) in source_line_paths
        .iter()
        .take(write_line_count)
        .zip(translation_lines.iter().take(write_line_count))
    {
        write_command_first_parameter(
            data_files,
            source_line_path,
            expected_code,
            translated_text,
        )?;
    }
    if translation_lines.len() < existing_line_count {
        delete_surplus_line_commands(
            data_files,
            expected_code,
            &source_line_paths[translation_lines.len()..],
        )?;
        return Ok(());
    }
    let extra_lines = &translation_lines[existing_line_count..];
    if extra_lines.is_empty() {
        return Ok(());
    }
    insert_extra_line_commands(
        data_files,
        expected_code,
        insertion_anchor_path,
        extra_lines,
    )
}

pub(super) fn find_mv_virtual_speaker_for_name_command(
    data_files: &BTreeMap<String, Value>,
    item: &TranslationItem,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
) -> Result<Option<MvVirtualSpeaker>, String> {
    let (commands, command_index) = locate_commands_ref(data_files, &item.location_path)?;
    let command_path_prefix = command_list_parent_path(&item.location_path)?;
    let Some((_speaker_line_path, virtual_speaker)) = find_mv_virtual_speaker_command_ref(
        data_files,
        commands,
        command_index,
        &command_path_prefix,
        mv_virtual_namebox_rules,
    )?
    else {
        return Ok(None);
    };
    Ok(Some(virtual_speaker))
}

pub(super) fn find_mv_virtual_speaker_command_ref(
    data_files: &BTreeMap<String, Value>,
    commands: &[Value],
    command_index: usize,
    command_path_prefix: &str,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
) -> Result<Option<(String, MvVirtualSpeaker)>, String> {
    let mut next_index = command_index + 1;
    while next_index < commands.len() {
        let command_path = format!("{command_path_prefix}/{next_index}");
        let command = commands
            .get(next_index)
            .and_then(Value::as_object)
            .ok_or_else(|| {
                format!("{command_path} 不是事件指令对象，不能写入 MV 虚拟名字框术语")
            })?;
        let code = command
            .get("code")
            .and_then(Value::as_i64)
            .ok_or_else(|| format!("{command_path}.code 不是整数，不能写入 MV 虚拟名字框术语"))?;
        if code != 401 {
            break;
        }
        let text = read_first_parameter_text(command, &command_path)?;
        if text.trim().is_empty() {
            next_index += 1;
            continue;
        }
        let Some(mut virtual_speaker) = parse_mv_virtual_speaker_line(
            data_files,
            text,
            mv_virtual_namebox_rules,
            &command_path,
        )?
        else {
            return Ok(None);
        };
        virtual_speaker.speaker_line_path = command_path.clone();
        return Ok(Some((command_path, virtual_speaker)));
    }
    Ok(None)
}

pub(super) fn write_mv_virtual_name_text_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    virtual_speaker: &MvVirtualSpeaker,
    terminology: &HashMap<String, HashMap<String, String>>,
    rules: &TextPlanRules,
) -> Result<(), String> {
    if virtual_speaker.body_text.is_empty()
        && item
            .source_line_paths
            .iter()
            .any(|path| path == &virtual_speaker.speaker_line_path)
    {
        return Err(format!(
            "当前 MV 译文仍包含说话人行，检查没通过，不能继续写进游戏文件；请先精确重置该文本后重新提取和翻译: 文本路径={}; 触发路径={}",
            item.location_path, virtual_speaker.speaker_line_path
        ));
    }
    let render_speaker =
        match read_mv_render_speaker_from_item_fact(terminology, item, virtual_speaker)? {
            Some(value) => value,
            None => read_mv_render_speaker(terminology, virtual_speaker, &item.location_path)?,
        };
    let translation_lines = prepared_long_lines(item, rules)?;
    let source_speaker_for_clean = item
        .role
        .as_deref()
        .filter(|role| !role.trim().is_empty() && has_text_fact_render_parts(item))
        .unwrap_or(&virtual_speaker.speaker);
    ensure_mv_translation_body_is_clean(
        source_speaker_for_clean,
        &render_speaker,
        &translation_lines,
        &item.location_path,
    )?;

    if !virtual_speaker.body_text.is_empty() {
        let first_line = translation_lines
            .first()
            .ok_or_else(|| format!("MV 内联说话人正文缺少译文: {}", item.location_path))?;
        let speaker_line = render_mv_virtual_speaker_line_from_text_fact_parts(
            item,
            &render_speaker,
            Some(first_line),
        )
        .unwrap_or_else(|| {
            render_mv_virtual_speaker_line(virtual_speaker, &render_speaker, Some(first_line))
        })?;
        write_command_first_parameter(
            data_files,
            &virtual_speaker.speaker_line_path,
            401,
            &speaker_line,
        )?;
        write_prepared_line_commands_by_paths(
            data_files,
            401,
            &item.source_line_paths[1..],
            &virtual_speaker.speaker_line_path,
            &translation_lines[1..],
        )?;
        return Ok(());
    }

    let speaker_line = render_mv_virtual_speaker_line(virtual_speaker, &render_speaker, None)?;
    write_command_first_parameter(
        data_files,
        &virtual_speaker.speaker_line_path,
        401,
        &speaker_line,
    )?;
    write_prepared_line_commands_by_paths(
        data_files,
        401,
        &item.source_line_paths,
        &virtual_speaker.speaker_line_path,
        &translation_lines,
    )
}

fn has_text_fact_render_parts(item: &TranslationItem) -> bool {
    !item.render_parts.is_empty()
}

fn read_mv_render_speaker_from_item_fact(
    terminology: &HashMap<String, HashMap<String, String>>,
    item: &TranslationItem,
    virtual_speaker: &MvVirtualSpeaker,
) -> Result<Option<String>, String> {
    if !has_text_fact_render_parts(item) {
        return Ok(None);
    }
    let Some(source_speaker) = item
        .role
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    else {
        return Ok(None);
    };
    if matches!(
        virtual_speaker.speaker_policy,
        super::models::MvVirtualSpeakerPolicy::Preserve
    ) {
        return Ok(Some(source_speaker.to_string()));
    }
    let translated_speaker = terminology
        .get("speaker_names")
        .and_then(|speaker_names| speaker_names.get(source_speaker))
        .map(|value| value.trim())
        .filter(|value| !value.is_empty());
    match translated_speaker {
        Some(value) => Ok(Some(value.to_string())),
        None => Err(format!(
            "MV 说话人缺少术语译名，请先导入 speaker_names: 文本路径={}; 触发路径={}; 规则={}; 原始匹配={}; 原始说话人={}; 术语键={}",
            item.location_path,
            virtual_speaker.speaker_line_path,
            virtual_speaker.rule_name,
            virtual_speaker.matched_text,
            source_speaker,
            source_speaker,
        )),
    }
}

fn render_mv_virtual_speaker_line_from_text_fact_parts(
    item: &TranslationItem,
    translated_speaker: &str,
    translated_body: Option<&str>,
) -> Option<Result<String, String>> {
    if item.render_parts.is_empty() {
        return None;
    }
    let Some(source_role) = item
        .role
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    else {
        return Some(Err(format!(
            "MV 虚拟名字框当前文本事实缺少说话人，不能写进游戏文件: {}",
            item.location_path
        )));
    };
    Some(render_mv_virtual_speaker_line_from_render_parts(
        &item.location_path,
        source_role,
        &item.render_parts,
        translated_speaker,
        translated_body,
    ))
}

pub(super) fn render_mv_virtual_speaker_line_from_render_parts(
    location_path: &str,
    source_role: &str,
    render_parts: &[TextFactRenderPart],
    translated_speaker: &str,
    translated_body: Option<&str>,
) -> Result<String, String> {
    if render_parts.is_empty() {
        return Err(format!(
            "MV 虚拟名字框当前文本事实缺少写回所需源文结构，不能写进游戏文件: {location_path}"
        ));
    }
    let body_text = translated_body.unwrap_or_default();
    let mut rendered = String::new();
    let mut has_speaker_part = false;
    let mut rendered_body_part = false;
    for part in render_parts {
        if part.part_kind == "speaker" {
            has_speaker_part = true;
            rendered.push_str(&render_text_fact_speaker_part(
                source_role,
                translated_speaker,
                &part.raw_text,
            ));
            continue;
        }
        if part.part_kind == "translated_body" || part.template_key == "body" {
            if rendered_body_part || translated_body.is_none() {
                break;
            }
            if translated_body.is_some() {
                rendered.push_str(&render_text_fact_body_part(&part.raw_text, body_text));
            }
            rendered_body_part = true;
            continue;
        }
        if rendered_body_part && (part.raw_text.contains('\n') || part.raw_text.contains('\r')) {
            break;
        }
        rendered.push_str(&part.raw_text);
    }
    if !has_speaker_part {
        return Err(format!(
            "MV 虚拟名字框当前文本事实缺少说话人片段，不能写进游戏文件: {location_path}"
        ));
    }
    if translated_body.is_none() {
        while rendered.ends_with('\n') || rendered.ends_with('\r') {
            rendered.pop();
        }
    }
    Ok(rendered)
}

fn render_text_fact_speaker_part(
    source_role: &str,
    translated_speaker: &str,
    raw_speaker_part: &str,
) -> String {
    let Some(suffix) = raw_speaker_part.strip_prefix(source_role) else {
        return translated_speaker.to_string();
    };
    format!("{translated_speaker}{suffix}")
}

fn render_text_fact_body_part(raw_body_part: &str, translated_body: &str) -> String {
    let prefix_len = raw_body_part.len() - raw_body_part.trim_start().len();
    let suffix_len = raw_body_part.len() - raw_body_part.trim_end().len();
    let prefix = &raw_body_part[..prefix_len];
    let suffix = if suffix_len == 0 {
        ""
    } else {
        &raw_body_part[raw_body_part.len() - suffix_len..]
    };
    format!("{prefix}{translated_body}{suffix}")
}
pub(super) fn read_first_parameter_text<'a>(
    command: &'a Map<String, Value>,
    location_path: &str,
) -> Result<&'a str, String> {
    command
        .get("parameters")
        .and_then(Value::as_array)
        .and_then(|parameters| parameters.first())
        .and_then(Value::as_str)
        .ok_or_else(|| format!("事件指令缺少第一个文本参数: {location_path}"))
}

pub(super) fn write_command_first_parameter(
    data_files: &mut BTreeMap<String, Value>,
    source_line_path: &str,
    expected_code: i64,
    translated_text: &str,
) -> Result<(), String> {
    let (commands, command_index) = locate_commands_mut(data_files, source_line_path)?;
    let command = commands
        .get_mut(command_index)
        .and_then(Value::as_object_mut)
        .ok_or_else(|| format!("逐行路径指向的指令不是对象: {source_line_path}"))?;
    if command.get("code").and_then(Value::as_i64) != Some(expected_code) {
        return Err(format!("逐行路径指向的指令类型错误: {source_line_path}"));
    }
    let parameters = command
        .get_mut("parameters")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| format!("逐行路径指令 parameters 不是数组: {source_line_path}"))?;
    if parameters.is_empty() {
        return Err(format!("逐行路径指令缺少文本参数: {source_line_path}"));
    }
    parameters[0] = Value::String(translated_text.to_string());
    Ok(())
}

pub(super) fn delete_surplus_line_commands(
    data_files: &mut BTreeMap<String, Value>,
    expected_code: i64,
    surplus_source_line_paths: &[String],
) -> Result<(), String> {
    let mut indexes: Vec<usize> = Vec::new();
    let mut command_parent_path = String::new();
    for source_line_path in surplus_source_line_paths {
        if command_parent_path.is_empty() {
            command_parent_path = command_list_parent_path(source_line_path)?;
        } else if command_parent_path != command_list_parent_path(source_line_path)? {
            return Err(format!(
                "长文本逐行路径跨事件列表，无法删除多余行: {source_line_path}"
            ));
        }
        let (commands, command_index) = locate_commands_mut(data_files, source_line_path)?;
        let command = commands
            .get(command_index)
            .and_then(Value::as_object)
            .ok_or_else(|| format!("多余行删除锚点不是对象: {source_line_path}"))?;
        if command.get("code").and_then(Value::as_i64) != Some(expected_code) {
            return Err(format!("多余行删除锚点指令类型错误: {source_line_path}"));
        }
        indexes.push(command_index);
    }
    if let Some(first_path) = surplus_source_line_paths.first() {
        let (commands, _command_index) = locate_commands_mut(data_files, first_path)?;
        indexes.sort_unstable();
        indexes.reverse();
        for index in indexes {
            if index < commands.len() {
                let _ = commands.remove(index);
            }
        }
    }
    Ok(())
}

pub(super) fn insert_extra_line_commands(
    data_files: &mut BTreeMap<String, Value>,
    expected_code: i64,
    insertion_anchor_path: &str,
    extra_lines: &[String],
) -> Result<(), String> {
    let (commands, command_index) = locate_commands_mut(data_files, insertion_anchor_path)?;
    let base_command = commands
        .get(command_index)
        .and_then(Value::as_object)
        .ok_or_else(|| format!("额外行插入锚点不是对象: {insertion_anchor_path}"))?
        .clone();
    if base_command.get("code").and_then(Value::as_i64) != Some(expected_code) {
        return Err(format!(
            "额外行插入锚点指令类型错误: {insertion_anchor_path}"
        ));
    }
    let indent = base_command.get("indent").and_then(Value::as_i64);
    for (offset, translated_text) in extra_lines.iter().enumerate() {
        let mut command = Map::new();
        command.insert("code".to_string(), Value::Number(expected_code.into()));
        command.insert(
            "parameters".to_string(),
            Value::Array(vec![Value::String(translated_text.clone())]),
        );
        if let Some(indent_value) = indent {
            command.insert("indent".to_string(), Value::Number(indent_value.into()));
        }
        commands.insert(command_index + offset + 1, Value::Object(command));
    }
    Ok(())
}

pub(super) fn command_list_parent_path(location_path: &str) -> Result<String, String> {
    let parts: Vec<&str> = location_path.split('/').collect();
    let Some(file_name) = parts.first() else {
        return Err(format!("事件定位路径为空: {location_path}"));
    };
    if is_map_file(file_name) || *file_name == TROOPS_FILE_NAME {
        if parts.len() < 4 {
            return Err(format!("事件定位路径不完整: {location_path}"));
        }
        return Ok(parts[..3].join("/"));
    }
    if *file_name == COMMON_EVENTS_FILE_NAME {
        if parts.len() < 3 {
            return Err(format!("事件定位路径不完整: {location_path}"));
        }
        return Ok(parts[..2].join("/"));
    }
    Err(format!("无法识别的事件定位路径: {location_path}"))
}

pub(super) fn write_event_command_text_item(
    data_files: &mut BTreeMap<String, Value>,
    item: &TranslationItem,
    rules: &TextPlanRules,
) -> Result<(), String> {
    let parts: Vec<&str> = item.location_path.split('/').collect();
    let value_path_start = if is_map_file(parts.first().copied().unwrap_or_default())
        || parts.first().copied() == Some(TROOPS_FILE_NAME)
    {
        4
    } else {
        3
    };
    if parts.len() < value_path_start + 2 || parts[value_path_start] != "parameters" {
        return Err(format!(
            "事件指令路径缺少 parameters 段: {}",
            item.location_path
        ));
    }
    let param_index = parse_usize(parts[value_path_start + 1], &item.location_path)?;
    let path_parts = &parts[value_path_start + 2..];
    let (commands, command_index) = locate_commands_mut(data_files, &item.location_path)?;
    let command = commands
        .get_mut(command_index)
        .and_then(Value::as_object_mut)
        .ok_or_else(|| format!("事件指令不是对象: {}", item.location_path))?;
    let parameters = command
        .get_mut("parameters")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| format!("事件指令 parameters 不是数组: {}", item.location_path))?;
    let current = parameters
        .get_mut(param_index)
        .ok_or_else(|| format!("事件指令参数索引越界: {}", item.location_path))?;
    set_nested_text_value(
        current,
        path_parts,
        &prepared_single_text(item, rules)?,
        &item.location_path,
    )
}

pub(super) fn locate_commands_mut<'a>(
    data_files: &'a mut BTreeMap<String, Value>,
    location_path: &str,
) -> Result<(&'a mut Vec<Value>, usize), String> {
    let parts: Vec<&str> = location_path.split('/').collect();
    let file_name = parts.first().copied().unwrap_or_default();
    let data = data_files
        .get_mut(file_name)
        .ok_or_else(|| format!("事件文件不存在: {file_name}"))?;
    if is_map_file(file_name) {
        let event_id = parse_usize(parts.get(1).copied().unwrap_or_default(), location_path)?;
        let page_index = parse_usize(parts.get(2).copied().unwrap_or_default(), location_path)?;
        let command_index = parse_usize(parts.get(3).copied().unwrap_or_default(), location_path)?;
        let commands = data
            .as_object_mut()
            .and_then(|map| map.get_mut("events"))
            .and_then(Value::as_array_mut)
            .and_then(|events| events.get_mut(event_id))
            .and_then(Value::as_object_mut)
            .and_then(|event| event.get_mut("pages"))
            .and_then(Value::as_array_mut)
            .and_then(|pages| pages.get_mut(page_index))
            .and_then(Value::as_object_mut)
            .and_then(|page| page.get_mut("list"))
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("地图事件指令列表无法定位: {location_path}"))?;
        return Ok((commands, command_index));
    }
    if file_name == COMMON_EVENTS_FILE_NAME {
        let event_id = parse_usize(parts.get(1).copied().unwrap_or_default(), location_path)?;
        let command_index = parse_usize(parts.get(2).copied().unwrap_or_default(), location_path)?;
        let commands = data
            .as_array_mut()
            .and_then(|events| events.get_mut(event_id))
            .and_then(Value::as_object_mut)
            .and_then(|event| event.get_mut("list"))
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("公共事件指令列表无法定位: {location_path}"))?;
        return Ok((commands, command_index));
    }
    if file_name == TROOPS_FILE_NAME {
        let troop_id = parse_usize(parts.get(1).copied().unwrap_or_default(), location_path)?;
        let page_index = parse_usize(parts.get(2).copied().unwrap_or_default(), location_path)?;
        let command_index = parse_usize(parts.get(3).copied().unwrap_or_default(), location_path)?;
        let commands = data
            .as_array_mut()
            .and_then(|troops| troops.get_mut(troop_id))
            .and_then(Value::as_object_mut)
            .and_then(|troop| troop.get_mut("pages"))
            .and_then(Value::as_array_mut)
            .and_then(|pages| pages.get_mut(page_index))
            .and_then(Value::as_object_mut)
            .and_then(|page| page.get_mut("list"))
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("敌群事件指令列表无法定位: {location_path}"))?;
        return Ok((commands, command_index));
    }
    Err(format!("无法识别的事件定位路径: {location_path}"))
}

pub(super) fn locate_commands_ref<'a>(
    data_files: &'a BTreeMap<String, Value>,
    location_path: &str,
) -> Result<(&'a Vec<Value>, usize), String> {
    let parts: Vec<&str> = location_path.split('/').collect();
    let file_name = parts.first().copied().unwrap_or_default();
    let data = data_files
        .get(file_name)
        .ok_or_else(|| format!("事件文件不存在: {file_name}"))?;
    if is_map_file(file_name) {
        let event_id = parse_usize(parts.get(1).copied().unwrap_or_default(), location_path)?;
        let page_index = parse_usize(parts.get(2).copied().unwrap_or_default(), location_path)?;
        let command_index = parse_usize(parts.get(3).copied().unwrap_or_default(), location_path)?;
        let commands = data
            .as_object()
            .and_then(|map| map.get("events"))
            .and_then(Value::as_array)
            .and_then(|events| events.get(event_id))
            .and_then(Value::as_object)
            .and_then(|event| event.get("pages"))
            .and_then(Value::as_array)
            .and_then(|pages| pages.get(page_index))
            .and_then(Value::as_object)
            .and_then(|page| page.get("list"))
            .and_then(Value::as_array)
            .ok_or_else(|| format!("地图事件指令列表无法定位: {location_path}"))?;
        return Ok((commands, command_index));
    }
    if file_name == COMMON_EVENTS_FILE_NAME {
        let event_id = parse_usize(parts.get(1).copied().unwrap_or_default(), location_path)?;
        let command_index = parse_usize(parts.get(2).copied().unwrap_or_default(), location_path)?;
        let commands = data
            .as_array()
            .and_then(|events| events.get(event_id))
            .and_then(Value::as_object)
            .and_then(|event| event.get("list"))
            .and_then(Value::as_array)
            .ok_or_else(|| format!("公共事件指令列表无法定位: {location_path}"))?;
        return Ok((commands, command_index));
    }
    if file_name == TROOPS_FILE_NAME {
        let troop_id = parse_usize(parts.get(1).copied().unwrap_or_default(), location_path)?;
        let page_index = parse_usize(parts.get(2).copied().unwrap_or_default(), location_path)?;
        let command_index = parse_usize(parts.get(3).copied().unwrap_or_default(), location_path)?;
        let commands = data
            .as_array()
            .and_then(|troops| troops.get(troop_id))
            .and_then(Value::as_object)
            .and_then(|troop| troop.get("pages"))
            .and_then(Value::as_array)
            .and_then(|pages| pages.get(page_index))
            .and_then(Value::as_object)
            .and_then(|page| page.get("list"))
            .and_then(Value::as_array)
            .ok_or_else(|| format!("敌群事件指令列表无法定位: {location_path}"))?;
        return Ok((commands, command_index));
    }
    Err(format!("无法识别的事件定位路径: {location_path}"))
}
