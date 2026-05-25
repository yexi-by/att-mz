use super::models::{MvVirtualNameboxRule, MvVirtualSpeaker, MvVirtualSpeakerPolicy};
use super::utils::render_format_template;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};

pub(super) fn parse_mv_virtual_speaker_line(
    data_files: &BTreeMap<String, Value>,
    text: &str,
    rules: &[MvVirtualNameboxRule],
    location_path: &str,
) -> Result<Option<MvVirtualSpeaker>, String> {
    let normalized_text = text.trim();
    if normalized_text.is_empty() {
        return Ok(None);
    }
    let mut matches: Vec<MvVirtualSpeaker> = Vec::new();
    for rule in rules {
        let captures = rule
            .pattern
            .captures(normalized_text)
            .map_err(|error| format!("MV 虚拟名字框规则匹配失败 {}: {error}", rule.rule_name))?;
        let Some(captures) = captures else {
            continue;
        };
        let Some(full_match) = captures.get(0) else {
            continue;
        };
        if full_match.start() != 0 || full_match.end() != normalized_text.len() {
            continue;
        }
        matches.push(build_mv_virtual_speaker(
            data_files,
            rule,
            &captures,
            normalized_text,
        )?);
    }
    if matches.len() > 1 {
        let rule_names = matches
            .iter()
            .map(|matched| matched.rule_name.as_str())
            .collect::<Vec<_>>()
            .join(", ");
        return Err(format!(
            "MV 虚拟名字框规则命中冲突; 文本路径={location_path}: 规则={rule_names}; 文本={normalized_text}"
        ));
    }
    Ok(matches.into_iter().next())
}

pub(super) fn build_mv_virtual_speaker(
    data_files: &BTreeMap<String, Value>,
    rule: &MvVirtualNameboxRule,
    captures: &fancy_regex::Captures<'_>,
    matched_text: &str,
) -> Result<MvVirtualSpeaker, String> {
    let mut group_values: HashMap<String, String> = HashMap::new();
    for group_name in &rule.group_names {
        let value = captures
            .name(group_name)
            .map(|matched| matched.as_str().to_string())
            .unwrap_or_default();
        group_values.insert(group_name.clone(), value);
    }
    let source_speaker_text = captures
        .name(&rule.speaker_group)
        .map(|matched| matched.as_str().trim().to_string())
        .unwrap_or_default();
    if source_speaker_text.is_empty() {
        return Err(format!(
            "MV 虚拟名字框规则 {} 命中了空说话人",
            rule.rule_name
        ));
    }
    let body_text = if rule.body_group.is_empty() {
        String::new()
    } else {
        captures
            .name(&rule.body_group)
            .map(|matched| matched.as_str().to_string())
            .unwrap_or_default()
    };
    let speaker = match rule.speaker_policy {
        MvVirtualSpeakerPolicy::ActorName => {
            actor_name_from_control(data_files, &source_speaker_text)?
        }
        MvVirtualSpeakerPolicy::Translate | MvVirtualSpeakerPolicy::Preserve => {
            source_speaker_text.clone()
        }
    };
    Ok(MvVirtualSpeaker {
        speaker_line_path: String::new(),
        speaker,
        body_text,
        matched_text: matched_text.to_string(),
        rule_name: rule.rule_name.clone(),
        speaker_policy: match rule.speaker_policy {
            MvVirtualSpeakerPolicy::Translate => MvVirtualSpeakerPolicy::Translate,
            MvVirtualSpeakerPolicy::Preserve => MvVirtualSpeakerPolicy::Preserve,
            MvVirtualSpeakerPolicy::ActorName => MvVirtualSpeakerPolicy::ActorName,
        },
        source_speaker_text,
        render_template: rule.render_template.clone(),
        group_values,
        speaker_group: rule.speaker_group.clone(),
        body_group: rule.body_group.clone(),
    })
}

pub(super) fn read_mv_render_speaker(
    terminology: &HashMap<String, HashMap<String, String>>,
    virtual_speaker: &MvVirtualSpeaker,
    location_path: &str,
) -> Result<String, String> {
    if matches!(
        virtual_speaker.speaker_policy,
        MvVirtualSpeakerPolicy::Preserve
    ) {
        if !virtual_speaker.source_speaker_text.is_empty() {
            return Ok(virtual_speaker.source_speaker_text.clone());
        }
        return Ok(virtual_speaker.speaker.clone());
    }
    let translated_speaker = terminology
        .get("speaker_names")
        .and_then(|speaker_names| speaker_names.get(&virtual_speaker.speaker))
        .map(|value| value.trim())
        .filter(|value| !value.is_empty());
    match translated_speaker {
        Some(value) => Ok(value.to_string()),
        None => Err(format!(
            "MV 说话人缺少术语译名，请先导入 speaker_names: 文本路径={location_path}; 触发路径={}; 规则={}; 原始匹配={}; 原始说话人={}; 术语键={}",
            virtual_speaker.speaker_line_path,
            virtual_speaker.rule_name,
            virtual_speaker.matched_text,
            virtual_speaker.source_speaker_text,
            virtual_speaker.speaker,
        )),
    }
}

pub(super) fn render_mv_virtual_speaker_line(
    virtual_speaker: &MvVirtualSpeaker,
    translated_speaker: &str,
    translated_body: Option<&str>,
) -> Result<String, String> {
    let mut values = virtual_speaker.group_values.clone();
    values.insert(
        virtual_speaker.speaker_group.clone(),
        translated_speaker.to_string(),
    );
    let body_text = translated_body.unwrap_or_default().to_string();
    if !virtual_speaker.body_group.is_empty() {
        values.insert(virtual_speaker.body_group.clone(), body_text.clone());
    }
    values.insert("speaker".to_string(), translated_speaker.to_string());
    values.insert("body".to_string(), body_text);
    render_format_template(&virtual_speaker.render_template, &values)
}

pub(super) fn ensure_mv_translation_body_is_clean(
    source_speaker: &str,
    translated_speaker: &str,
    translation_lines: &[String],
    location_path: &str,
) -> Result<(), String> {
    let Some(first_line) = translation_lines.first() else {
        return Ok(());
    };
    let first_line = first_line.trim();
    let forbidden_prefixes = [
        format!("{source_speaker}:"),
        format!("{source_speaker}："),
        format!("{source_speaker}「"),
        format!("{source_speaker}（"),
        format!("{translated_speaker}:"),
        format!("{translated_speaker}："),
        format!("{translated_speaker}「"),
        format!("{translated_speaker}（"),
    ];
    if forbidden_prefixes
        .iter()
        .any(|prefix| first_line.starts_with(prefix))
    {
        return Err(format!(
            "MV 译文正文仍包含说话人前缀，请先执行 reset-translations --all 后重新翻译: {location_path}"
        ));
    }
    Ok(())
}

pub(super) fn actor_name_from_control(
    data_files: &BTreeMap<String, Value>,
    text: &str,
) -> Result<String, String> {
    let pattern = regex::Regex::new(r"^\\[Nn]\[(?P<actor_id>\d+)\]$")
        .map_err(|error| format!("MV actor_name 控制符正则初始化失败: {error}"))?;
    let captures = pattern
        .captures(text)
        .ok_or_else(|| format!("actor_name 规则命中的说话人不是角色名控制符: {text}"))?;
    let actor_id = captures
        .name("actor_id")
        .ok_or_else(|| format!("actor_name 规则无法解析角色 ID: {text}"))?
        .as_str()
        .parse::<usize>()
        .map_err(|error| format!("actor_name 规则角色 ID 不是数字: {text}: {error}"))?;
    let actor_name = data_files
        .get("Actors.json")
        .and_then(Value::as_array)
        .and_then(|actors| actors.get(actor_id))
        .and_then(Value::as_object)
        .and_then(|actor| actor.get("name"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty());
    match actor_name {
        Some(value) => Ok(value.to_string()),
        None => Err(format!("actor_name 规则无法解析角色 ID: {actor_id}")),
    }
}
