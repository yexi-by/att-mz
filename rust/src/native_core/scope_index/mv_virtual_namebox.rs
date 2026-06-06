//! MV 虚拟名字框候选和规则命中扫描。

use fancy_regex::{Captures, Regex};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

use super::RuleCandidateOutput;

const COMMAND_NAME: i64 = 101;
const COMMAND_TEXT: i64 = 401;

#[derive(Debug, Deserialize)]
pub(super) struct MvVirtualNameboxDataFileInput {
    pub(super) file_name: String,
    pub(super) data: Value,
}

#[derive(Debug, Deserialize)]
pub(super) struct MvVirtualNameboxActorNameInput {
    pub(super) actor_id: i64,
    pub(super) name: String,
}

#[derive(Debug, Clone, Deserialize)]
pub(super) struct MvVirtualNameboxRuleInput {
    #[serde(default)]
    rule_order: usize,
    rule_name: String,
    pattern_text: String,
    speaker_group: String,
    #[serde(default)]
    body_group: String,
    speaker_policy: String,
    render_template: String,
}

#[derive(Debug, Clone, Serialize)]
pub(super) struct MvVirtualNameboxCandidateOutput {
    location_path: String,
    text: String,
    following_lines: Vec<String>,
}

#[derive(Debug, Serialize)]
pub(super) struct MvVirtualNameboxMatchOutput {
    rule_name: String,
    speaker: String,
    source_speaker: String,
    speaker_policy: String,
}

#[derive(Debug, Serialize)]
pub(super) struct MvVirtualNameboxHitDetailOutput {
    location_path: String,
    text: String,
    following_lines: Vec<String>,
    matching_rules: Vec<String>,
    matches: Vec<MvVirtualNameboxMatchOutput>,
}

#[derive(Debug, Serialize)]
pub(super) struct MvVirtualNameboxRuleSummaryOutput {
    matched_candidate_count: usize,
    matched_candidate_location_paths: Vec<String>,
    rule_index: usize,
    rule_name: String,
}

#[derive(Debug, Serialize)]
pub(super) struct MvVirtualNameboxErrorOutput {
    location_path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    rule_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    source_speaker: Option<String>,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    source: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    rendered: Option<String>,
}

pub(super) struct MvVirtualNameboxRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) candidate_details: Vec<MvVirtualNameboxCandidateOutput>,
    pub(super) errors: Vec<MvVirtualNameboxErrorOutput>,
    pub(super) hit_details: Vec<MvVirtualNameboxHitDetailOutput>,
    pub(super) rule_summaries: Vec<MvVirtualNameboxRuleSummaryOutput>,
    pub(super) scanned_command_count: usize,
    pub(super) scanned_file_count: usize,
}

#[derive(Debug)]
struct EventCommandSnapshot {
    location_path: String,
    code: i64,
    parameters: Vec<Value>,
}

#[derive(Debug)]
struct CompiledMvVirtualNameboxRule {
    rule_index: usize,
    rule_name: String,
    pattern: Regex,
    speaker_group: String,
    body_group: String,
    speaker_policy: String,
    render_template: String,
}

#[derive(Debug)]
struct VirtualSpeaker {
    rule_name: String,
    speaker: String,
    source_speaker: String,
    speaker_policy: String,
    rendered_source: String,
}

struct RuleStats {
    rule_index: usize,
    rule_name: String,
    matched_candidate_location_paths: BTreeSet<String>,
}

pub(super) fn scan_mv_virtual_namebox_rule_candidates(
    data_files: &[MvVirtualNameboxDataFileInput],
    actor_names: &[MvVirtualNameboxActorNameInput],
    rules: &[MvVirtualNameboxRuleInput],
) -> Result<MvVirtualNameboxRuleCandidateScan, String> {
    let actor_names_by_id = actor_names
        .iter()
        .filter(|actor| !actor.name.trim().is_empty())
        .map(|actor| (actor.actor_id, actor.name.trim().to_string()))
        .collect::<BTreeMap<_, _>>();
    let compiled_rules = compile_rules(rules)?;
    let mut rule_stats = compiled_rules
        .iter()
        .map(|rule| RuleStats {
            rule_index: rule.rule_index,
            rule_name: rule.rule_name.clone(),
            matched_candidate_location_paths: BTreeSet::new(),
        })
        .collect::<Vec<_>>();

    let mut command_groups = Vec::new();
    let mut scanned_command_count = 0usize;
    let mut sorted_files = data_files.iter().collect::<Vec<_>>();
    sorted_files.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let file_group_sets = sorted_files
        .par_iter()
        .map(|file| collect_command_groups(file))
        .collect::<Vec<_>>();
    for groups in file_group_sets {
        scanned_command_count += groups.iter().map(std::vec::Vec::len).sum::<usize>();
        command_groups.extend(groups);
    }

    let mut candidate_details = Vec::new();
    for group in command_groups {
        append_candidates_from_group(&group, &mut candidate_details);
    }
    candidate_details.sort_by(|left, right| left.location_path.cmp(&right.location_path));

    let candidates = candidate_details
        .iter()
        .map(candidate_to_rule_candidate)
        .collect::<Vec<_>>();
    let mut errors = Vec::new();
    let mut hit_details = Vec::new();
    for candidate in &candidate_details {
        let mut matching_rules = Vec::new();
        let mut matches = Vec::new();
        for (rule_index, rule) in compiled_rules.iter().enumerate() {
            let Some(virtual_speaker) =
                match_candidate_rule(candidate, rule, &actor_names_by_id, &mut errors)?
            else {
                continue;
            };
            rule_stats[rule_index]
                .matched_candidate_location_paths
                .insert(candidate.location_path.clone());
            matching_rules.push(rule.rule_name.clone());
            if virtual_speaker.speaker_policy == "translate"
                && is_actor_name_control_text(&virtual_speaker.source_speaker)
            {
                errors.push(MvVirtualNameboxErrorOutput {
                    location_path: candidate.location_path.clone(),
                    rule_name: Some(rule.rule_name.clone()),
                    text: Some(candidate.text.clone()),
                    source_speaker: Some(virtual_speaker.source_speaker.clone()),
                    message: "标准角色名控制符被 translate 规则命中，请改用 preserve 或 actor_name 规则，并收紧普通规则".to_string(),
                    source: None,
                    rendered: None,
                });
            }
            if virtual_speaker.rendered_source != candidate.text.trim() {
                errors.push(MvVirtualNameboxErrorOutput {
                    location_path: candidate.location_path.clone(),
                    rule_name: Some(virtual_speaker.rule_name.clone()),
                    text: None,
                    source_speaker: None,
                    message: "规则模板无法重建源文本".to_string(),
                    source: Some(candidate.text.trim().to_string()),
                    rendered: Some(virtual_speaker.rendered_source.clone()),
                });
            }
            matches.push(MvVirtualNameboxMatchOutput {
                rule_name: virtual_speaker.rule_name,
                speaker: virtual_speaker.speaker,
                source_speaker: virtual_speaker.source_speaker,
                speaker_policy: virtual_speaker.speaker_policy,
            });
        }
        if matching_rules.len() > 1 {
            errors.push(MvVirtualNameboxErrorOutput {
                location_path: candidate.location_path.clone(),
                rule_name: None,
                text: None,
                source_speaker: None,
                message: format!("同一候选命中多条规则: {}", matching_rules.join(", ")),
                source: None,
                rendered: None,
            });
        }
        if !matching_rules.is_empty() {
            hit_details.push(MvVirtualNameboxHitDetailOutput {
                location_path: candidate.location_path.clone(),
                text: candidate.text.clone(),
                following_lines: candidate.following_lines.iter().take(3).cloned().collect(),
                matching_rules,
                matches,
            });
        }
    }

    Ok(MvVirtualNameboxRuleCandidateScan {
        candidates,
        candidate_details: candidate_details
            .into_iter()
            .map(|candidate| MvVirtualNameboxCandidateOutput {
                location_path: candidate.location_path,
                text: candidate.text,
                following_lines: candidate.following_lines.into_iter().take(3).collect(),
            })
            .collect(),
        errors,
        hit_details,
        rule_summaries: rule_stats.into_iter().map(RuleStats::into_output).collect(),
        scanned_command_count,
        scanned_file_count: data_files.len(),
    })
}

fn compile_rules(
    rules: &[MvVirtualNameboxRuleInput],
) -> Result<Vec<CompiledMvVirtualNameboxRule>, String> {
    let mut sorted_rules = rules.iter().enumerate().collect::<Vec<_>>();
    sorted_rules.sort_by_key(|(rule_index, rule)| (rule.rule_order, *rule_index));
    sorted_rules
        .into_iter()
        .map(|(rule_index, rule)| {
            let pattern = Regex::new(&rule.pattern_text).map_err(|error| {
                format!(
                    "MV 虚拟名字框规则 {} 无法编译 Rust 正则: {error}",
                    rule.rule_name
                )
            })?;
            Ok(CompiledMvVirtualNameboxRule {
                rule_index,
                rule_name: rule.rule_name.clone(),
                pattern,
                speaker_group: rule.speaker_group.clone(),
                body_group: rule.body_group.clone(),
                speaker_policy: rule.speaker_policy.clone(),
                render_template: rule.render_template.clone(),
            })
        })
        .collect()
}

fn collect_command_groups(file: &MvVirtualNameboxDataFileInput) -> Vec<Vec<EventCommandSnapshot>> {
    if is_map_file(&file.file_name) {
        return collect_map_command_groups(file);
    }
    match file.file_name.as_str() {
        "CommonEvents.json" => collect_common_event_command_groups(file),
        "Troops.json" => collect_troop_command_groups(file),
        _ => Vec::new(),
    }
}

fn collect_map_command_groups(
    file: &MvVirtualNameboxDataFileInput,
) -> Vec<Vec<EventCommandSnapshot>> {
    let mut groups = Vec::new();
    let Some(events) = file.data.get("events").and_then(Value::as_array) else {
        return groups;
    };
    for (event_index, event_value) in events.iter().enumerate() {
        let Some(event) = event_value.as_object() else {
            continue;
        };
        let event_id = integer_field(event, "id").unwrap_or(event_index as i64);
        let Some(pages) = event.get("pages").and_then(Value::as_array) else {
            continue;
        };
        for (page_index, page_value) in pages.iter().enumerate() {
            let Some(commands) = page_value.get("list").and_then(Value::as_array) else {
                continue;
            };
            groups.push(command_group_from_values(commands, |command_index| {
                format!("{}/{event_id}/{page_index}/{command_index}", file.file_name)
            }));
        }
    }
    groups
}

fn collect_common_event_command_groups(
    file: &MvVirtualNameboxDataFileInput,
) -> Vec<Vec<EventCommandSnapshot>> {
    let mut groups = Vec::new();
    let Some(common_events) = file.data.as_array() else {
        return groups;
    };
    for (common_event_index, common_event_value) in common_events.iter().enumerate() {
        let Some(common_event) = common_event_value.as_object() else {
            continue;
        };
        let common_event_id =
            integer_field(common_event, "id").unwrap_or(common_event_index as i64);
        let Some(commands) = common_event.get("list").and_then(Value::as_array) else {
            continue;
        };
        groups.push(command_group_from_values(commands, |command_index| {
            format!("{}/{common_event_id}/{command_index}", file.file_name)
        }));
    }
    groups
}

fn collect_troop_command_groups(
    file: &MvVirtualNameboxDataFileInput,
) -> Vec<Vec<EventCommandSnapshot>> {
    let mut groups = Vec::new();
    let Some(troops) = file.data.as_array() else {
        return groups;
    };
    for (troop_index, troop_value) in troops.iter().enumerate() {
        let Some(troop) = troop_value.as_object() else {
            continue;
        };
        let troop_id = integer_field(troop, "id").unwrap_or(troop_index as i64);
        let Some(pages) = troop.get("pages").and_then(Value::as_array) else {
            continue;
        };
        for (page_index, page_value) in pages.iter().enumerate() {
            let Some(commands) = page_value.get("list").and_then(Value::as_array) else {
                continue;
            };
            groups.push(command_group_from_values(commands, |command_index| {
                format!("{}/{troop_id}/{page_index}/{command_index}", file.file_name)
            }));
        }
    }
    groups
}

fn command_group_from_values<F>(
    commands: &[Value],
    location_path_for_index: F,
) -> Vec<EventCommandSnapshot>
where
    F: Fn(usize) -> String,
{
    commands
        .iter()
        .enumerate()
        .filter_map(|(command_index, command_value)| {
            let object = command_value.as_object()?;
            let code = object.get("code")?.as_i64()?;
            let parameters = object.get("parameters")?.as_array()?.clone();
            Some(EventCommandSnapshot {
                location_path: location_path_for_index(command_index),
                code,
                parameters,
            })
        })
        .collect()
}

fn append_candidates_from_group(
    command_group: &[EventCommandSnapshot],
    candidates: &mut Vec<MvVirtualNameboxCandidateOutput>,
) {
    for (index, command) in command_group.iter().enumerate() {
        if command.code != COMMAND_NAME {
            continue;
        }
        if let Some(candidate) = candidate_after_name_command(command_group, index) {
            candidates.push(candidate);
        }
    }
}

fn candidate_after_name_command(
    command_group: &[EventCommandSnapshot],
    start_index: usize,
) -> Option<MvVirtualNameboxCandidateOutput> {
    let mut following_lines = Vec::new();
    let mut first_path = None;
    let mut first_text = None;
    let mut next_index = start_index + 1;
    while next_index < command_group.len() {
        let command = &command_group[next_index];
        if command.code != COMMAND_TEXT {
            break;
        }
        if let Some(text) = read_first_parameter_text(command)
            && !text.trim().is_empty()
        {
            following_lines.push(text.to_string());
            if first_text.is_none() {
                first_path = Some(command.location_path.clone());
                first_text = Some(text.trim().to_string());
            }
        }
        next_index += 1;
    }
    Some(MvVirtualNameboxCandidateOutput {
        location_path: first_path?,
        text: first_text?,
        following_lines: following_lines.into_iter().skip(1).collect(),
    })
}

fn read_first_parameter_text(command: &EventCommandSnapshot) -> Option<&str> {
    command.parameters.first()?.as_str()
}

fn candidate_to_rule_candidate(candidate: &MvVirtualNameboxCandidateOutput) -> RuleCandidateOutput {
    let source_file = candidate
        .location_path
        .split('/')
        .next()
        .unwrap_or_default()
        .to_string();
    RuleCandidateOutput {
        domain: "mv_virtual_namebox".to_string(),
        location_path: candidate.location_path.clone(),
        rule_key: "mv_virtual_namebox.default".to_string(),
        original_text: candidate.text.clone(),
        source_file: source_file.clone(),
        file: Some(source_file),
        json_path: None,
        source_text: Some(candidate.text.clone()),
        field_name: None,
        sibling_field_names: None,
        parent_object_keys: None,
        selector: None,
        text: Some(candidate.text.clone()),
        raw_text: Some(candidate.text.clone()),
        quote: None,
        line: None,
        start_index: None,
        end_index: None,
        content_start_index: None,
        content_end_index: None,
        context: None,
        api: None,
        key: None,
        ast_context: None,
        active: None,
        confidence: None,
        structural_flags: None,
        file_hash: None,
    }
}

fn match_candidate_rule(
    candidate: &MvVirtualNameboxCandidateOutput,
    rule: &CompiledMvVirtualNameboxRule,
    actor_names_by_id: &BTreeMap<i64, String>,
    errors: &mut Vec<MvVirtualNameboxErrorOutput>,
) -> Result<Option<VirtualSpeaker>, String> {
    let text = candidate.text.trim();
    let Some(captures) = rule
        .pattern
        .captures(text)
        .map_err(|error| format!("MV 虚拟名字框规则 {} 匹配失败: {error}", rule.rule_name))?
    else {
        return Ok(None);
    };
    let Some(whole_match) = captures.get(0) else {
        return Ok(None);
    };
    if whole_match.start() != 0 || whole_match.end() != text.len() {
        return Ok(None);
    }
    match build_virtual_speaker(text, &captures, rule, actor_names_by_id) {
        Ok(virtual_speaker) => Ok(Some(virtual_speaker)),
        Err(message) => {
            errors.push(MvVirtualNameboxErrorOutput {
                location_path: candidate.location_path.clone(),
                rule_name: Some(rule.rule_name.clone()),
                text: Some(candidate.text.clone()),
                source_speaker: None,
                message,
                source: None,
                rendered: None,
            });
            Ok(None)
        }
    }
}

fn build_virtual_speaker(
    text: &str,
    captures: &Captures<'_>,
    rule: &CompiledMvVirtualNameboxRule,
    actor_names_by_id: &BTreeMap<i64, String>,
) -> Result<VirtualSpeaker, String> {
    let source_speaker = capture_group(captures, &rule.speaker_group)
        .unwrap_or_default()
        .trim()
        .to_string();
    if source_speaker.is_empty() {
        return Err(format!(
            "MV 虚拟名字框规则 {} 命中了空说话人",
            rule.rule_name
        ));
    }
    let body_text = if rule.body_group.is_empty() {
        String::new()
    } else {
        capture_group(captures, &rule.body_group)
            .unwrap_or_default()
            .trim()
            .to_string()
    };
    let speaker = if rule.speaker_policy == "actor_name" {
        actor_name_from_control(actor_names_by_id, &source_speaker)?
    } else {
        source_speaker.clone()
    };
    let rendered_source = render_source_template(
        &rule.render_template,
        captures,
        rule,
        &source_speaker,
        &body_text,
    )
    .unwrap_or_else(|_error| text.to_string());
    Ok(VirtualSpeaker {
        rule_name: rule.rule_name.clone(),
        speaker,
        source_speaker,
        speaker_policy: rule.speaker_policy.clone(),
        rendered_source,
    })
}

fn capture_group<'a>(captures: &'a Captures<'_>, group_name: &str) -> Option<&'a str> {
    captures.name(group_name).map(|matched| matched.as_str())
}

fn render_source_template(
    template: &str,
    captures: &Captures<'_>,
    rule: &CompiledMvVirtualNameboxRule,
    source_speaker: &str,
    body_text: &str,
) -> Result<String, String> {
    let mut rendered = String::new();
    let chars = template.chars().collect::<Vec<_>>();
    let mut index = 0usize;
    while index < chars.len() {
        match chars[index] {
            '{' => {
                if chars.get(index + 1) == Some(&'{') {
                    rendered.push('{');
                    index += 2;
                    continue;
                }
                let start_index = index + 1;
                let mut end_index = start_index;
                while end_index < chars.len() && chars[end_index] != '}' {
                    end_index += 1;
                }
                if end_index >= chars.len() {
                    return Err(format!("MV 虚拟名字框模板缺少闭合大括号: {template}"));
                }
                let field_expression = chars[start_index..end_index].iter().collect::<String>();
                let field_name = normalize_template_field_name(&field_expression);
                let value =
                    template_field_value(field_name, captures, rule, source_speaker, body_text);
                rendered.push_str(&value);
                index = end_index + 1;
            }
            '}' => {
                if chars.get(index + 1) == Some(&'}') {
                    rendered.push('}');
                    index += 2;
                    continue;
                }
                return Err(format!("MV 虚拟名字框模板存在孤立闭合大括号: {template}"));
            }
            character => {
                rendered.push(character);
                index += 1;
            }
        }
    }
    Ok(rendered)
}

fn normalize_template_field_name(field_expression: &str) -> &str {
    field_expression
        .split(['!', ':'])
        .next()
        .unwrap_or_default()
        .split(['.', '['])
        .next()
        .unwrap_or_default()
}

fn template_field_value(
    field_name: &str,
    captures: &Captures<'_>,
    rule: &CompiledMvVirtualNameboxRule,
    source_speaker: &str,
    body_text: &str,
) -> String {
    if field_name == "speaker" || field_name == rule.speaker_group {
        return source_speaker.to_string();
    }
    if field_name == "body" || (!rule.body_group.is_empty() && field_name == rule.body_group) {
        return body_text.to_string();
    }
    capture_group(captures, field_name)
        .unwrap_or_default()
        .to_string()
}

fn actor_name_from_control(
    actor_names_by_id: &BTreeMap<i64, String>,
    text: &str,
) -> Result<String, String> {
    let Some(actor_id) = actor_id_from_control_text(text) else {
        return Err(format!(
            "actor_name 规则命中的说话人不是角色名控制符: {text}"
        ));
    };
    actor_names_by_id
        .get(&actor_id)
        .cloned()
        .ok_or_else(|| format!("actor_name 规则无法解析角色 ID: {actor_id}"))
}

fn is_actor_name_control_text(text: &str) -> bool {
    actor_id_from_control_text(text).is_some()
}

fn actor_id_from_control_text(text: &str) -> Option<i64> {
    let stripped = text.trim();
    let inner = stripped
        .strip_prefix("\\N[")
        .or_else(|| stripped.strip_prefix("\\n["))?
        .strip_suffix(']')?;
    if inner.is_empty() || !inner.chars().all(|character| character.is_ascii_digit()) {
        return None;
    }
    inner.parse::<i64>().ok()
}

impl RuleStats {
    fn into_output(self) -> MvVirtualNameboxRuleSummaryOutput {
        MvVirtualNameboxRuleSummaryOutput {
            matched_candidate_count: self.matched_candidate_location_paths.len(),
            matched_candidate_location_paths: self
                .matched_candidate_location_paths
                .into_iter()
                .collect(),
            rule_index: self.rule_index,
            rule_name: self.rule_name,
        }
    }
}

fn is_map_file(file_name: &str) -> bool {
    let Some(stem) = file_name
        .strip_prefix("Map")
        .and_then(|value| value.strip_suffix(".json"))
    else {
        return false;
    };
    !stem.is_empty() && stem.chars().all(|character| character.is_ascii_digit())
}

fn integer_field(object: &serde_json::Map<String, Value>, field_name: &str) -> Option<i64> {
    object.get(field_name)?.as_i64()
}
