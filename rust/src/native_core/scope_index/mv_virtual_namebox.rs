//! MV 虚拟名字框候选和规则命中扫描。

use fancy_regex::{Captures, Regex};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::Digest;
use std::collections::{BTreeMap, BTreeSet};

use super::RuleCandidateOutput;

const COMMAND_NAME: i64 = 101;
const COMMAND_TEXT: i64 = 401;

#[derive(Debug, Deserialize)]
pub(super) struct MvVirtualNameboxDataFileInput {
    pub(super) file_name: String,
    pub(super) data: Value,
}

#[derive(Debug, Serialize, Deserialize)]
pub(super) struct MvVirtualNameboxActorNameInput {
    pub(super) actor_id: i64,
    pub(super) name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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

#[derive(Debug, Clone, Serialize)]
pub(super) struct MvVirtualNameboxSpeakerRequirementOutput {
    source_text: String,
    policy: String,
    requires_speaker_name: bool,
    rule_name: String,
    location_paths: Vec<String>,
    sample_body_lines: Vec<String>,
    render_template: String,
    confidence: String,
}

pub(super) struct MvVirtualNameboxRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) candidate_details: Vec<MvVirtualNameboxCandidateOutput>,
    pub(super) errors: Vec<MvVirtualNameboxErrorOutput>,
    pub(super) hit_details: Vec<MvVirtualNameboxHitDetailOutput>,
    pub(super) rule_summaries: Vec<MvVirtualNameboxRuleSummaryOutput>,
    pub(super) speaker_requirements: Vec<MvVirtualNameboxSpeakerRequirementOutput>,
    pub(super) scope_hash: String,
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
    body_text: String,
    speaker_policy: String,
    render_template: String,
    rendered_source: String,
}

struct WeakSplitSpeaker {
    speaker: String,
    body_text: String,
}

pub(super) fn weak_split_colon_speaker_parts(
    source_speaker: &str,
    body_text: &str,
) -> Option<(String, String)> {
    weak_split_colon_speaker(source_speaker, body_text)
        .map(|parts| (parts.speaker, parts.body_text))
}

#[derive(Debug, Clone)]
pub(super) struct MvVirtualNameboxFactParts {
    pub(super) raw_text: String,
    pub(super) visible_text: String,
    pub(super) translatable_text: String,
    pub(super) role: String,
    pub(super) render_parts: Vec<MvVirtualNameboxFactRenderPart>,
}

#[derive(Debug, Clone)]
pub(super) struct MvVirtualNameboxFactRenderPart {
    pub(super) part_kind: String,
    pub(super) raw_text: String,
    pub(super) semantic_text: String,
    pub(super) template_key: String,
}

pub(super) struct MvVirtualNameboxFactPartsInput<'a> {
    pub(super) raw_text: &'a str,
    pub(super) source_speaker: &'a str,
    pub(super) role: &'a str,
    pub(super) body_text: &'a str,
    pub(super) render_template: &'a str,
    pub(super) speaker_group: &'a str,
    pub(super) body_group: &'a str,
    pub(super) rule_name: &'a str,
    pub(super) template_values: &'a BTreeMap<String, String>,
}

struct RuleStats {
    rule_index: usize,
    rule_name: String,
    matched_candidate_location_paths: BTreeSet<String>,
}

pub(super) fn build_mv_virtual_namebox_fact_parts(
    input: MvVirtualNameboxFactPartsInput<'_>,
) -> Result<MvVirtualNameboxFactParts, String> {
    if !has_visible_text(input.source_speaker) {
        return Err(format!(
            "MV 虚拟名字框规则 {} 命中了空白或不可见 speaker",
            input.rule_name
        ));
    }
    if !has_visible_text(input.role) {
        return Err(format!(
            "MV 虚拟名字框规则 {} 解析后的 speaker 为空白或不可见",
            input.rule_name
        ));
    }
    let semantic_parts = weak_split_colon_speaker(input.role, input.body_text)
        .ok_or_else(|| format!("MV 虚拟名字框规则 {} 命中了空说话人", input.rule_name))?;
    let mut render_parts = render_parts_from_template(
        input.render_template,
        input.source_speaker,
        input.role,
        input.body_text,
        input.speaker_group,
        input.body_group,
        input.template_values,
    )?;
    reconcile_render_parts_with_raw_text(&mut render_parts, input.raw_text, input.rule_name)?;
    Ok(MvVirtualNameboxFactParts {
        raw_text: input.raw_text.to_string(),
        visible_text: input.raw_text.to_string(),
        translatable_text: semantic_parts.body_text,
        role: semantic_parts.speaker,
        render_parts,
    })
}

fn reconcile_render_parts_with_raw_text(
    parts: &mut Vec<MvVirtualNameboxFactRenderPart>,
    raw_text: &str,
    rule_name: &str,
) -> Result<(), String> {
    let rebuilt_raw = rebuild_raw_from_parts(parts);
    if rebuilt_raw == raw_text {
        return Ok(());
    }
    if rebuilt_raw.is_empty() {
        return Err(render_template_rebuild_error(rule_name));
    }
    let Some(start_index) = raw_text.find(&rebuilt_raw) else {
        return Err(render_template_rebuild_error(rule_name));
    };
    let end_index = start_index + rebuilt_raw.len();
    let prefix = &raw_text[..start_index];
    let suffix = &raw_text[end_index..];
    if !is_format_shell(prefix) || !is_format_shell(suffix) {
        return Err(render_template_rebuild_error(rule_name));
    }
    if !prefix.is_empty() {
        prepend_literal_shell(parts, prefix);
    }
    if !suffix.is_empty() {
        append_literal_shell(parts, suffix);
    }
    if rebuild_raw_from_parts(parts) != raw_text {
        return Err(render_template_rebuild_error(rule_name));
    }
    Ok(())
}

fn rebuild_raw_from_parts(parts: &[MvVirtualNameboxFactRenderPart]) -> String {
    parts
        .iter()
        .map(|part| part.raw_text.as_str())
        .collect::<String>()
}

fn render_template_rebuild_error(rule_name: &str) -> String {
    format!("MV 虚拟名字框规则 {rule_name} 的 render_template 无法重建源文本")
}

fn is_format_shell(text: &str) -> bool {
    text.chars()
        .all(|character| character.is_whitespace() || is_invisible_character(character))
}

fn prepend_literal_shell(parts: &mut Vec<MvVirtualNameboxFactRenderPart>, raw_text: &str) {
    if let Some(first) = parts.first_mut()
        && first.part_kind == "literal"
    {
        first.raw_text = format!("{raw_text}{}", first.raw_text);
        first.semantic_text = format!("{raw_text}{}", first.semantic_text);
        return;
    }
    parts.insert(
        0,
        MvVirtualNameboxFactRenderPart {
            part_kind: "literal".to_string(),
            raw_text: raw_text.to_string(),
            semantic_text: raw_text.to_string(),
            template_key: "literal".to_string(),
        },
    );
}

fn append_literal_shell(parts: &mut Vec<MvVirtualNameboxFactRenderPart>, raw_text: &str) {
    if let Some(last) = parts.last_mut()
        && last.part_kind == "literal"
    {
        last.raw_text.push_str(raw_text);
        last.semantic_text.push_str(raw_text);
        return;
    }
    parts.push(MvVirtualNameboxFactRenderPart {
        part_kind: "literal".to_string(),
        raw_text: raw_text.to_string(),
        semantic_text: raw_text.to_string(),
        template_key: "literal".to_string(),
    });
}

fn render_parts_from_template(
    render_template: &str,
    source_speaker: &str,
    role: &str,
    body_text: &str,
    speaker_group: &str,
    body_group: &str,
    template_values: &BTreeMap<String, String>,
) -> Result<Vec<MvVirtualNameboxFactRenderPart>, String> {
    let mut parts = Vec::new();
    let mut literal = String::new();
    let chars = render_template.chars().collect::<Vec<_>>();
    let mut index = 0usize;
    while index < chars.len() {
        match chars[index] {
            '{' => {
                if chars.get(index + 1) == Some(&'{') {
                    literal.push('{');
                    index += 2;
                    continue;
                }
                flush_literal_part(&mut parts, &mut literal);
                let start_index = index + 1;
                let mut end_index = start_index;
                while end_index < chars.len() && chars[end_index] != '}' {
                    end_index += 1;
                }
                if end_index >= chars.len() {
                    return Err(format!(
                        "MV 虚拟名字框模板缺少闭合大括号: {render_template}"
                    ));
                }
                let field_expression = chars[start_index..end_index].iter().collect::<String>();
                let field_name = normalize_template_field_name(&field_expression);
                parts.push(render_part_for_template_field(
                    field_name,
                    source_speaker,
                    role,
                    body_text,
                    speaker_group,
                    body_group,
                    template_values,
                )?);
                index = end_index + 1;
            }
            '}' => {
                if chars.get(index + 1) == Some(&'}') {
                    literal.push('}');
                    index += 2;
                    continue;
                }
                return Err(format!(
                    "MV 虚拟名字框模板存在孤立闭合大括号: {render_template}"
                ));
            }
            character => {
                literal.push(character);
                index += 1;
            }
        }
    }
    flush_literal_part(&mut parts, &mut literal);
    Ok(parts)
}

fn flush_literal_part(parts: &mut Vec<MvVirtualNameboxFactRenderPart>, literal: &mut String) {
    if literal.is_empty() {
        return;
    }
    let raw_text = std::mem::take(literal);
    parts.push(MvVirtualNameboxFactRenderPart {
        part_kind: "literal".to_string(),
        semantic_text: raw_text.clone(),
        raw_text,
        template_key: "literal".to_string(),
    });
}

fn render_part_for_template_field(
    field_name: &str,
    source_speaker: &str,
    role: &str,
    body_text: &str,
    speaker_group: &str,
    body_group: &str,
    template_values: &BTreeMap<String, String>,
) -> Result<MvVirtualNameboxFactRenderPart, String> {
    if field_name == "speaker" || field_name == speaker_group {
        return Ok(MvVirtualNameboxFactRenderPart {
            part_kind: "speaker".to_string(),
            raw_text: source_speaker.to_string(),
            semantic_text: role.to_string(),
            template_key: "speaker".to_string(),
        });
    }
    if field_name == "body" || (!body_group.is_empty() && field_name == body_group) {
        return Ok(MvVirtualNameboxFactRenderPart {
            part_kind: "translated_body".to_string(),
            raw_text: body_text.to_string(),
            semantic_text: body_text.to_string(),
            template_key: "body".to_string(),
        });
    }
    if let Some(value) = template_values.get(field_name) {
        return Ok(MvVirtualNameboxFactRenderPart {
            part_kind: "literal".to_string(),
            raw_text: value.clone(),
            semantic_text: value.clone(),
            template_key: field_name.to_string(),
        });
    }
    Err(format!("MV 虚拟名字框模板字段未捕获: {field_name}"))
}

fn has_visible_text(text: &str) -> bool {
    text.chars()
        .any(|character| !character.is_whitespace() && !is_invisible_character(character))
}

fn is_invisible_character(character: char) -> bool {
    character.is_control()
        || matches!(
            character,
            '\u{200b}' | '\u{200c}' | '\u{200d}' | '\u{2060}' | '\u{feff}'
        )
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
    let mut speaker_requirements = Vec::new();
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
            append_speaker_requirement(&mut speaker_requirements, candidate, &virtual_speaker);
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
        scope_hash: build_scope_hash(&candidate_details, actor_names, rules)?,
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
        speaker_requirements,
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
    let raw_source_speaker = capture_group(captures, &rule.speaker_group)
        .unwrap_or_default()
        .trim()
        .to_string();
    let raw_body_text = if rule.body_group.is_empty() {
        String::new()
    } else {
        capture_group(captures, &rule.body_group)
            .unwrap_or_default()
            .trim()
            .to_string()
    };
    let Some(semantic_parts) = weak_split_colon_speaker(&raw_source_speaker, &raw_body_text) else {
        return Err(format!(
            "MV 虚拟名字框规则 {} 命中了空说话人",
            rule.rule_name
        ));
    };
    let speaker = if rule.speaker_policy == "actor_name" {
        actor_name_from_control(actor_names_by_id, &semantic_parts.speaker)?
    } else {
        semantic_parts.speaker.clone()
    };
    let rendered_source = render_source_template(
        &rule.render_template,
        captures,
        rule,
        &raw_source_speaker,
        &raw_body_text,
    )
    .unwrap_or_else(|_error| text.to_string());
    Ok(VirtualSpeaker {
        rule_name: rule.rule_name.clone(),
        speaker,
        source_speaker: semantic_parts.speaker,
        body_text: semantic_parts.body_text,
        speaker_policy: rule.speaker_policy.clone(),
        render_template: rule.render_template.clone(),
        rendered_source,
    })
}

fn weak_split_colon_speaker(source_speaker: &str, body_text: &str) -> Option<WeakSplitSpeaker> {
    let semantic_speaker = source_speaker.trim();
    let semantic_body = body_text.trim();
    if semantic_speaker.is_empty() {
        return None;
    }
    let stripped_speaker = semantic_speaker.trim_end_matches([':', '：']).trim_end();
    if stripped_speaker.len() != semantic_speaker.len() && !semantic_body.is_empty() {
        if stripped_speaker.is_empty() {
            return None;
        }
        return Some(WeakSplitSpeaker {
            speaker: stripped_speaker.to_string(),
            body_text: semantic_body.to_string(),
        });
    }
    Some(WeakSplitSpeaker {
        speaker: semantic_speaker.to_string(),
        body_text: semantic_body.to_string(),
    })
}

fn append_speaker_requirement(
    requirements: &mut Vec<MvVirtualNameboxSpeakerRequirementOutput>,
    candidate: &MvVirtualNameboxCandidateOutput,
    virtual_speaker: &VirtualSpeaker,
) {
    let source_text = if virtual_speaker.speaker_policy == "actor_name" {
        virtual_speaker.speaker.clone()
    } else {
        virtual_speaker.source_speaker.clone()
    };
    let sample_body_lines = speaker_requirement_sample_lines(candidate, virtual_speaker);
    if let Some(existing) = requirements.iter_mut().find(|requirement| {
        requirement.source_text == source_text
            && requirement.policy == virtual_speaker.speaker_policy
            && requirement.rule_name == virtual_speaker.rule_name
            && requirement.render_template == virtual_speaker.render_template
    }) {
        if !existing
            .location_paths
            .iter()
            .any(|location_path| location_path == &candidate.location_path)
        {
            existing
                .location_paths
                .push(candidate.location_path.clone());
        }
        for line in sample_body_lines {
            if existing.sample_body_lines.len() >= 3 {
                break;
            }
            if !existing
                .sample_body_lines
                .iter()
                .any(|existing| existing == &line)
            {
                existing.sample_body_lines.push(line);
            }
        }
        return;
    }
    requirements.push(MvVirtualNameboxSpeakerRequirementOutput {
        source_text,
        policy: virtual_speaker.speaker_policy.clone(),
        requires_speaker_name: matches!(
            virtual_speaker.speaker_policy.as_str(),
            "translate" | "actor_name"
        ),
        rule_name: virtual_speaker.rule_name.clone(),
        location_paths: vec![candidate.location_path.clone()],
        sample_body_lines,
        render_template: virtual_speaker.render_template.clone(),
        confidence: "rule_match".to_string(),
    });
}

fn speaker_requirement_sample_lines(
    candidate: &MvVirtualNameboxCandidateOutput,
    virtual_speaker: &VirtualSpeaker,
) -> Vec<String> {
    let mut lines = Vec::new();
    if !virtual_speaker.body_text.trim().is_empty() {
        lines.push(virtual_speaker.body_text.trim().to_string());
    }
    for line in &candidate.following_lines {
        if lines.len() >= 3 {
            break;
        }
        if !line.trim().is_empty() {
            lines.push(line.trim().to_string());
        }
    }
    lines
}

fn build_scope_hash(
    candidate_details: &[MvVirtualNameboxCandidateOutput],
    actor_names: &[MvVirtualNameboxActorNameInput],
    rules: &[MvVirtualNameboxRuleInput],
) -> Result<String, String> {
    let payload = serde_json::to_vec(&(candidate_details, actor_names, rules))
        .map_err(|error| format!("MV 虚拟名字框 scope hash 输入序列化失败: {error}"))?;
    let mut hasher = sha2::Sha256::new();
    hasher.update(payload);
    Ok(hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
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

#[cfg(test)]
mod tests {
    use super::{MvVirtualNameboxFactPartsInput, build_mv_virtual_namebox_fact_parts};
    use std::collections::BTreeMap;

    #[test]
    fn mv_virtual_namebox_fact_parts_preserve_raw_visible_translatable_split_and_spacing() {
        let template_values = BTreeMap::new();
        let parts = build_mv_virtual_namebox_fact_parts(MvVirtualNameboxFactPartsInput {
            raw_text: r"\n<Dan:> Hello",
            source_speaker: "Dan",
            role: "Dan",
            body_text: "Hello",
            render_template: r"\n<{speaker}:> {body}",
            speaker_group: "speaker",
            body_group: "body",
            rule_name: "yep-namebox-with-colon",
            template_values: &template_values,
        })
        .expect("有效 MV 虚拟名字框应可生成 fact 分片");

        assert_eq!(parts.raw_text, r"\n<Dan:> Hello");
        assert_eq!(parts.visible_text, r"\n<Dan:> Hello");
        assert_eq!(parts.translatable_text, "Hello");
        assert_eq!(parts.role, "Dan");
        assert_eq!(
            parts
                .render_parts
                .iter()
                .map(|part| part.part_kind.as_str())
                .collect::<Vec<_>>(),
            ["literal", "speaker", "literal", "translated_body"]
        );
        assert_eq!(
            parts
                .render_parts
                .iter()
                .map(|part| part.raw_text.as_str())
                .collect::<Vec<_>>(),
            [r"\n<", "Dan", ":> ", "Hello"]
        );
        assert_eq!(
            parts
                .render_parts
                .iter()
                .map(|part| part.raw_text.as_str())
                .collect::<String>(),
            r"\n<Dan:> Hello"
        );
        let translated = parts
            .render_parts
            .iter()
            .map(|part| {
                if part.part_kind == "translated_body" {
                    "你好"
                } else {
                    part.raw_text.as_str()
                }
            })
            .collect::<String>();
        assert_eq!(translated, r"\n<Dan:> 你好");
    }

    #[test]
    fn mv_virtual_namebox_fact_parts_preserve_raw_shell_whitespace() {
        let template_values = BTreeMap::new();
        let parts = build_mv_virtual_namebox_fact_parts(MvVirtualNameboxFactPartsInput {
            raw_text: r"  \n<Dan:> Hello  ",
            source_speaker: "Dan",
            role: "Dan",
            body_text: "Hello",
            render_template: r"\n<{speaker}:> {body}",
            speaker_group: "speaker",
            body_group: "body",
            rule_name: "yep-namebox-with-colon",
            template_values: &template_values,
        })
        .expect("MV 虚拟名字框 fact 分片必须保留 raw 外壳空白");

        assert_eq!(parts.raw_text, r"  \n<Dan:> Hello  ");
        assert_eq!(parts.visible_text, r"  \n<Dan:> Hello  ");
        assert_eq!(parts.translatable_text, "Hello");
        assert_eq!(
            parts
                .render_parts
                .iter()
                .map(|part| part.part_kind.as_str())
                .collect::<Vec<_>>(),
            [
                "literal",
                "speaker",
                "literal",
                "translated_body",
                "literal"
            ]
        );
        assert_eq!(
            parts
                .render_parts
                .iter()
                .map(|part| part.raw_text.as_str())
                .collect::<String>(),
            r"  \n<Dan:> Hello  "
        );
        let translated = parts
            .render_parts
            .iter()
            .map(|part| {
                if part.part_kind == "translated_body" {
                    "你好"
                } else {
                    part.raw_text.as_str()
                }
            })
            .collect::<String>();
        assert_eq!(translated, r"  \n<Dan:> 你好  ");
    }

    #[test]
    fn mv_virtual_namebox_fact_parts_reject_invisible_or_whitespace_speaker() {
        let template_values = BTreeMap::new();
        for speaker in ["", " \t ", "\u{200b}"] {
            let error = build_mv_virtual_namebox_fact_parts(MvVirtualNameboxFactPartsInput {
                raw_text: r"\n<:> Hello",
                source_speaker: speaker,
                role: speaker,
                body_text: "Hello",
                render_template: r"\n<{speaker}:> {body}",
                speaker_group: "speaker",
                body_group: "body",
                rule_name: "yep-namebox-with-colon",
                template_values: &template_values,
            })
            .expect_err("空白或不可见 speaker 必须被拒绝");
            assert!(error.contains("speaker"));
        }
    }
}
