use super::command_writer::{find_mv_virtual_speaker_command_ref, write_command_first_parameter};
use super::models::{
    COMMON_EVENTS_FILE_NAME, EngineKind, Layout, MvVirtualNameboxFactTemplate,
    MvVirtualNameboxRule, MvVirtualSpeakerPolicy, SYSTEM_FILE_NAME, TROOPS_FILE_NAME,
};
use super::utils::is_map_file;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};

pub(super) fn apply_terminology(
    data_files: &mut BTreeMap<String, Value>,
    terminology: &HashMap<String, HashMap<String, String>>,
    layout: &Layout,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
) -> Result<usize, String> {
    let mut written_count = 0usize;
    if let Some(speaker_names) = terminology.get("speaker_names") {
        written_count += match layout.engine_kind {
            EngineKind::Mz => write_mz_speaker_names(data_files, speaker_names)?,
            EngineKind::Mv => write_mv_virtual_speaker_names(
                data_files,
                speaker_names,
                mv_virtual_namebox_rules,
                mv_virtual_namebox_fact_templates,
            )?,
        };
    }
    if let Some(map_names) = terminology.get("map_display_names") {
        for (file_name, value) in data_files.iter_mut() {
            if !is_map_file(file_name) {
                continue;
            }
            let object = value
                .as_object_mut()
                .ok_or_else(|| format!("{file_name} 顶层不是地图对象"))?;
            let Some(source_text) = object.get("displayName").and_then(Value::as_str) else {
                continue;
            };
            if let Some(translated_text) = map_names.get(source_text.trim()) {
                object.insert(
                    "displayName".to_string(),
                    Value::String(translated_text.clone()),
                );
                written_count += 1;
            }
        }
    }
    let base_categories = [
        ("Actors.json", "name", "actor_names"),
        ("Actors.json", "nickname", "actor_nicknames"),
        ("Classes.json", "name", "class_names"),
        ("Skills.json", "name", "skill_names"),
        ("Items.json", "name", "item_names"),
        ("Weapons.json", "name", "weapon_names"),
        ("Armors.json", "name", "armor_names"),
        ("Enemies.json", "name", "enemy_names"),
        ("States.json", "name", "state_names"),
    ];
    for (file_name, key, category) in base_categories {
        let Some(translations) = terminology.get(category) else {
            continue;
        };
        let values = data_files
            .get_mut(file_name)
            .ok_or_else(|| format!("字段译名目标文件不存在: {file_name}"))?
            .as_array_mut()
            .ok_or_else(|| format!("字段译名目标文件不是数组: {file_name}"))?;
        for value in values {
            if value.is_null() {
                continue;
            }
            let Some(object) = value.as_object_mut() else {
                return Err(format!("{file_name} 存在非对象条目，不能写入字段译名"));
            };
            let Some(source_text) = object.get(key).and_then(Value::as_str) else {
                continue;
            };
            if let Some(translated_text) = translations.get(source_text.trim()) {
                object.insert(key.to_string(), Value::String(translated_text.clone()));
                written_count += 1;
            }
        }
    }
    let system_categories = [
        ("elements", "system_elements"),
        ("skillTypes", "system_skill_types"),
        ("weaponTypes", "system_weapon_types"),
        ("armorTypes", "system_armor_types"),
        ("equipTypes", "system_equip_types"),
    ];
    let has_system_terms = system_categories
        .iter()
        .any(|(_field_name, category)| terminology.contains_key(*category));
    if !has_system_terms {
        return Ok(written_count);
    }
    let system = data_files
        .get_mut(SYSTEM_FILE_NAME)
        .ok_or_else(|| "字段译名目标文件不存在: System.json".to_string())?
        .as_object_mut()
        .ok_or_else(|| "System.json 顶层不是对象，不能写入系统字段译名".to_string())?;
    for (field_name, category) in system_categories {
        let Some(translations) = terminology.get(category) else {
            continue;
        };
        let values = system
            .get_mut(field_name)
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("System.{field_name} 不是数组，不能写入系统字段译名"))?;
        for value in values {
            let Some(source_text) = value.as_str() else {
                continue;
            };
            if let Some(translated_text) = translations.get(source_text.trim()) {
                *value = Value::String(translated_text.clone());
                written_count += 1;
            }
        }
    }
    Ok(written_count)
}

pub(super) fn write_mz_speaker_names(
    data_files: &mut BTreeMap<String, Value>,
    translations: &HashMap<String, String>,
) -> Result<usize, String> {
    let mut written_count = 0usize;
    for (file_name, value) in data_files.iter_mut() {
        if is_map_file(file_name) {
            written_count += write_mz_map_speaker_names(file_name, value, translations)?;
        }
    }
    if let Some(value) = data_files.get_mut(COMMON_EVENTS_FILE_NAME) {
        written_count += write_mz_common_event_speaker_names(value, translations)?;
    }
    if let Some(value) = data_files.get_mut(TROOPS_FILE_NAME) {
        written_count += write_mz_troop_speaker_names(value, translations)?;
    }
    Ok(written_count)
}

pub(super) fn write_mz_map_speaker_names(
    file_name: &str,
    value: &mut Value,
    translations: &HashMap<String, String>,
) -> Result<usize, String> {
    let object = value
        .as_object_mut()
        .ok_or_else(|| format!("{file_name} 顶层不是地图对象，不能写入名字框术语"))?;
    let events = object
        .get_mut("events")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| format!("{file_name}.events 不是数组，不能写入名字框术语"))?;
    let mut written_count = 0usize;
    for (event_index, event) in events.iter_mut().enumerate() {
        if event.is_null() {
            continue;
        }
        let event_context = format!("{file_name}/{event_index}");
        let event_object = event
            .as_object_mut()
            .ok_or_else(|| format!("{event_context} 不是事件对象，不能写入名字框术语"))?;
        let pages = event_object
            .get_mut("pages")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("{event_context}.pages 不是数组，不能写入名字框术语"))?;
        for (page_index, page) in pages.iter_mut().enumerate() {
            let page_context = format!("{event_context}/{page_index}");
            let page_object = page
                .as_object_mut()
                .ok_or_else(|| format!("{page_context} 不是事件页对象，不能写入名字框术语"))?;
            let commands = page_object
                .get_mut("list")
                .and_then(Value::as_array_mut)
                .ok_or_else(|| format!("{page_context}.list 不是数组，不能写入名字框术语"))?;
            written_count +=
                write_mz_speaker_names_to_commands(commands, translations, &page_context)?;
        }
    }
    Ok(written_count)
}

pub(super) fn write_mz_common_event_speaker_names(
    value: &mut Value,
    translations: &HashMap<String, String>,
) -> Result<usize, String> {
    let events = value
        .as_array_mut()
        .ok_or_else(|| "CommonEvents.json 顶层不是数组，不能写入名字框术语".to_string())?;
    let mut written_count = 0usize;
    for (event_index, event) in events.iter_mut().enumerate() {
        if event.is_null() {
            continue;
        }
        let event_context = format!("{COMMON_EVENTS_FILE_NAME}/{event_index}");
        let event_object = event
            .as_object_mut()
            .ok_or_else(|| format!("{event_context} 不是公共事件对象，不能写入名字框术语"))?;
        let commands = event_object
            .get_mut("list")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("{event_context}.list 不是数组，不能写入名字框术语"))?;
        written_count +=
            write_mz_speaker_names_to_commands(commands, translations, &event_context)?;
    }
    Ok(written_count)
}

pub(super) fn write_mz_troop_speaker_names(
    value: &mut Value,
    translations: &HashMap<String, String>,
) -> Result<usize, String> {
    let troops = value
        .as_array_mut()
        .ok_or_else(|| "Troops.json 顶层不是数组，不能写入名字框术语".to_string())?;
    let mut written_count = 0usize;
    for (troop_index, troop) in troops.iter_mut().enumerate() {
        if troop.is_null() {
            continue;
        }
        let troop_context = format!("{TROOPS_FILE_NAME}/{troop_index}");
        let troop_object = troop
            .as_object_mut()
            .ok_or_else(|| format!("{troop_context} 不是敌群对象，不能写入名字框术语"))?;
        let pages = troop_object
            .get_mut("pages")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("{troop_context}.pages 不是数组，不能写入名字框术语"))?;
        for (page_index, page) in pages.iter_mut().enumerate() {
            let page_context = format!("{troop_context}/{page_index}");
            let page_object = page
                .as_object_mut()
                .ok_or_else(|| format!("{page_context} 不是敌群事件页对象，不能写入名字框术语"))?;
            let commands = page_object
                .get_mut("list")
                .and_then(Value::as_array_mut)
                .ok_or_else(|| format!("{page_context}.list 不是数组，不能写入名字框术语"))?;
            written_count +=
                write_mz_speaker_names_to_commands(commands, translations, &page_context)?;
        }
    }
    Ok(written_count)
}

pub(super) fn write_mz_speaker_names_to_commands(
    commands: &mut [Value],
    translations: &HashMap<String, String>,
    command_path_prefix: &str,
) -> Result<usize, String> {
    let mut written_count = 0usize;
    for (command_index, command_value) in commands.iter_mut().enumerate() {
        let command_path = format!("{command_path_prefix}/{command_index}");
        let command = command_value
            .as_object_mut()
            .ok_or_else(|| format!("{command_path} 不是事件指令对象，不能写入名字框术语"))?;
        let code = command
            .get("code")
            .and_then(Value::as_i64)
            .ok_or_else(|| format!("{command_path}.code 不是整数，不能写入名字框术语"))?;
        if code != 101 {
            continue;
        }
        let parameters = command
            .get_mut("parameters")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| format!("{command_path}.parameters 不是数组，不能写入名字框术语"))?;
        if parameters.len() <= 4 {
            continue;
        }
        let source_text = parameters[4]
            .as_str()
            .ok_or_else(|| format!("{command_path}.parameters[4] 不是文本，不能写入名字框术语"))?
            .trim();
        if let Some(translated_text) = translations.get(source_text) {
            parameters[4] = Value::String(translated_text.clone());
            written_count += 1;
        }
    }
    Ok(written_count)
}

pub(super) fn write_mv_virtual_speaker_names(
    data_files: &mut BTreeMap<String, Value>,
    translations: &HashMap<String, String>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
) -> Result<usize, String> {
    if mv_virtual_namebox_rules.is_empty() {
        return Err("MV 术语写回缺少 MV 虚拟名字框规则，不能写入 speaker_names".to_string());
    }
    let targets = collect_mv_virtual_speaker_name_writes(
        data_files,
        translations,
        mv_virtual_namebox_rules,
        mv_virtual_namebox_fact_templates,
    )?;
    let written_count = targets.len();
    for (target_path, translated_text) in targets {
        write_command_first_parameter(data_files, &target_path, 401, &translated_text)?;
    }
    Ok(written_count)
}

pub(super) fn collect_mv_virtual_speaker_name_writes(
    data_files: &BTreeMap<String, Value>,
    translations: &HashMap<String, String>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
) -> Result<Vec<(String, String)>, String> {
    let mut targets = Vec::new();
    for (file_name, value) in data_files {
        if is_map_file(file_name) {
            collect_mv_map_virtual_speaker_name_writes(
                data_files,
                file_name,
                value,
                translations,
                mv_virtual_namebox_rules,
                mv_virtual_namebox_fact_templates,
                &mut targets,
            )?;
        }
    }
    if let Some(value) = data_files.get(COMMON_EVENTS_FILE_NAME) {
        collect_mv_common_event_virtual_speaker_name_writes(
            data_files,
            value,
            translations,
            mv_virtual_namebox_rules,
            mv_virtual_namebox_fact_templates,
            &mut targets,
        )?;
    }
    if let Some(value) = data_files.get(TROOPS_FILE_NAME) {
        collect_mv_troop_virtual_speaker_name_writes(
            data_files,
            value,
            translations,
            mv_virtual_namebox_rules,
            mv_virtual_namebox_fact_templates,
            &mut targets,
        )?;
    }
    Ok(targets)
}

pub(super) fn collect_mv_map_virtual_speaker_name_writes(
    data_files: &BTreeMap<String, Value>,
    file_name: &str,
    value: &Value,
    translations: &HashMap<String, String>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
    targets: &mut Vec<(String, String)>,
) -> Result<(), String> {
    let object = value
        .as_object()
        .ok_or_else(|| format!("{file_name} 顶层不是地图对象，不能写入 MV 虚拟名字框术语"))?;
    let events = object
        .get("events")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{file_name}.events 不是数组，不能写入 MV 虚拟名字框术语"))?;
    for (event_index, event) in events.iter().enumerate() {
        if event.is_null() {
            continue;
        }
        let event_context = format!("{file_name}/{event_index}");
        let event_object = event
            .as_object()
            .ok_or_else(|| format!("{event_context} 不是事件对象，不能写入 MV 虚拟名字框术语"))?;
        let pages = event_object
            .get("pages")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("{event_context}.pages 不是数组，不能写入 MV 虚拟名字框术语"))?;
        for (page_index, page) in pages.iter().enumerate() {
            let page_context = format!("{event_context}/{page_index}");
            let page_object = page.as_object().ok_or_else(|| {
                format!("{page_context} 不是事件页对象，不能写入 MV 虚拟名字框术语")
            })?;
            let commands = page_object
                .get("list")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    format!("{page_context}.list 不是数组，不能写入 MV 虚拟名字框术语")
                })?;
            collect_mv_virtual_speaker_name_writes_from_commands(
                data_files,
                commands,
                &page_context,
                translations,
                mv_virtual_namebox_rules,
                mv_virtual_namebox_fact_templates,
                targets,
            )?;
        }
    }
    Ok(())
}

pub(super) fn collect_mv_common_event_virtual_speaker_name_writes(
    data_files: &BTreeMap<String, Value>,
    value: &Value,
    translations: &HashMap<String, String>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
    targets: &mut Vec<(String, String)>,
) -> Result<(), String> {
    let events = value
        .as_array()
        .ok_or_else(|| "CommonEvents.json 顶层不是数组，不能写入 MV 虚拟名字框术语".to_string())?;
    for (event_index, event) in events.iter().enumerate() {
        if event.is_null() {
            continue;
        }
        let event_context = format!("{COMMON_EVENTS_FILE_NAME}/{event_index}");
        let event_object = event.as_object().ok_or_else(|| {
            format!("{event_context} 不是公共事件对象，不能写入 MV 虚拟名字框术语")
        })?;
        let commands = event_object
            .get("list")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("{event_context}.list 不是数组，不能写入 MV 虚拟名字框术语"))?;
        collect_mv_virtual_speaker_name_writes_from_commands(
            data_files,
            commands,
            &event_context,
            translations,
            mv_virtual_namebox_rules,
            mv_virtual_namebox_fact_templates,
            targets,
        )?;
    }
    Ok(())
}

pub(super) fn collect_mv_troop_virtual_speaker_name_writes(
    data_files: &BTreeMap<String, Value>,
    value: &Value,
    translations: &HashMap<String, String>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
    targets: &mut Vec<(String, String)>,
) -> Result<(), String> {
    let troops = value
        .as_array()
        .ok_or_else(|| "Troops.json 顶层不是数组，不能写入 MV 虚拟名字框术语".to_string())?;
    for (troop_index, troop) in troops.iter().enumerate() {
        if troop.is_null() {
            continue;
        }
        let troop_context = format!("{TROOPS_FILE_NAME}/{troop_index}");
        let troop_object = troop
            .as_object()
            .ok_or_else(|| format!("{troop_context} 不是敌群对象，不能写入 MV 虚拟名字框术语"))?;
        let pages = troop_object
            .get("pages")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("{troop_context}.pages 不是数组，不能写入 MV 虚拟名字框术语"))?;
        for (page_index, page) in pages.iter().enumerate() {
            let page_context = format!("{troop_context}/{page_index}");
            let page_object = page.as_object().ok_or_else(|| {
                format!("{page_context} 不是敌群事件页对象，不能写入 MV 虚拟名字框术语")
            })?;
            let commands = page_object
                .get("list")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    format!("{page_context}.list 不是数组，不能写入 MV 虚拟名字框术语")
                })?;
            collect_mv_virtual_speaker_name_writes_from_commands(
                data_files,
                commands,
                &page_context,
                translations,
                mv_virtual_namebox_rules,
                mv_virtual_namebox_fact_templates,
                targets,
            )?;
        }
    }
    Ok(())
}

pub(super) fn collect_mv_virtual_speaker_name_writes_from_commands(
    data_files: &BTreeMap<String, Value>,
    commands: &[Value],
    command_path_prefix: &str,
    translations: &HashMap<String, String>,
    mv_virtual_namebox_rules: &[MvVirtualNameboxRule],
    mv_virtual_namebox_fact_templates: &[MvVirtualNameboxFactTemplate],
    targets: &mut Vec<(String, String)>,
) -> Result<(), String> {
    for (command_index, command_value) in commands.iter().enumerate() {
        let command_path = format!("{command_path_prefix}/{command_index}");
        let command = command_value.as_object().ok_or_else(|| {
            format!("{command_path} 不是事件指令对象，不能写入 MV 虚拟名字框术语")
        })?;
        let code = command
            .get("code")
            .and_then(Value::as_i64)
            .ok_or_else(|| format!("{command_path}.code 不是整数，不能写入 MV 虚拟名字框术语"))?;
        if code != 101 {
            continue;
        }
        let Some((speaker_line_path, virtual_speaker)) = find_mv_virtual_speaker_command_ref(
            data_files,
            commands,
            command_index,
            command_path_prefix,
            mv_virtual_namebox_rules,
        )?
        else {
            continue;
        };
        if matches!(
            virtual_speaker.speaker_policy,
            MvVirtualSpeakerPolicy::Preserve
        ) {
            continue;
        }
        let Some(translated_speaker) = translations.get(&virtual_speaker.speaker) else {
            continue;
        };
        let fact_template = mv_virtual_namebox_fact_templates
            .iter()
            .find(|template| {
                template
                    .source_line_paths
                    .iter()
                    .any(|path| path == &speaker_line_path)
            })
            .ok_or_else(|| {
                format!(
                    "MV 虚拟名字框术语写回缺少当前 v2 文本事实，不能写入 speaker_names；请重新运行 rebuild-text-index: {}",
                    speaker_line_path
                )
            })?;
        if fact_template.role != virtual_speaker.speaker {
            return Err(format!(
                "MV 虚拟名字框术语写回 v2 文本事实 speaker 不一致，不能写入 speaker_names；请重新运行 rebuild-text-index: 文本路径={}; 触发路径={}; fact_speaker={}; 当前_speaker={}",
                fact_template.location_path,
                speaker_line_path,
                fact_template.role,
                virtual_speaker.speaker,
            ));
        }
        let translated_text =
            render_mv_virtual_speaker_line_from_fact_template(fact_template, translated_speaker)?;
        targets.push((speaker_line_path, translated_text));
    }
    Ok(())
}

fn render_mv_virtual_speaker_line_from_fact_template(
    fact_template: &MvVirtualNameboxFactTemplate,
    translated_speaker: &str,
) -> Result<String, String> {
    if fact_template.render_parts.is_empty() {
        return Err(format!(
            "MV 虚拟名字框 v2 文本事实缺少 render parts，不能写入 speaker_names；请重新运行 rebuild-text-index: {}",
            fact_template.location_path
        ));
    }
    let mut rendered = String::new();
    let mut has_speaker_part = false;
    for part in &fact_template.render_parts {
        if part.part_kind == "speaker" {
            has_speaker_part = true;
            rendered.push_str(&render_text_fact_speaker_part(
                &fact_template.role,
                translated_speaker,
                &part.raw_text,
            ));
            continue;
        }
        if part.part_kind == "translated_body" || part.template_key == "body" {
            rendered.push_str(&render_text_fact_body_part(
                &part.raw_text,
                &fact_template.body_text,
            ));
            continue;
        }
        rendered.push_str(&part.raw_text);
    }
    if !has_speaker_part {
        return Err(format!(
            "MV 虚拟名字框 v2 文本事实 render parts 缺少 speaker，不能写入 speaker_names；请重新运行 rebuild-text-index: {}",
            fact_template.location_path
        ));
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

fn render_text_fact_body_part(raw_body_part: &str, body_text: &str) -> String {
    let prefix_len = raw_body_part.len() - raw_body_part.trim_start().len();
    let suffix_len = raw_body_part.len() - raw_body_part.trim_end().len();
    let prefix = &raw_body_part[..prefix_len];
    let suffix = if suffix_len == 0 {
        ""
    } else {
        &raw_body_part[raw_body_part.len() - suffix_len..]
    };
    format!("{prefix}{body_text}{suffix}")
}
