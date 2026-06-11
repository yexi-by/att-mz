//! 事件指令候选扫描。

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, BTreeSet};

use super::RuleCandidateOutput;
use super::path_templates::{
    JsonPathPart, jsonpath_matches_template, parse_json_path_message as parse_json_path,
};
use crate::native_core::write_back_plan::normalize_visible_text_for_extraction;
use crate::native_core::write_protocol::decode_json_container_text;

#[derive(Debug, Deserialize)]
pub(super) struct EventCommandDataFileInput {
    pub(super) file_name: String,
    pub(super) data: Value,
}

#[derive(Debug, Deserialize)]
pub(super) struct EventCommandRuleInput {
    pub(super) command_code: i64,
    #[serde(default)]
    pub(super) parameter_filters: Vec<EventCommandParameterFilterInput>,
    #[serde(default)]
    pub(super) path_templates: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(super) struct EventCommandParameterFilterInput {
    pub(super) index: usize,
    pub(super) value: String,
}

#[derive(Debug, Serialize)]
pub(super) struct EventCommandHitDetailOutput {
    pub(super) command_code: i64,
    pub(super) command_location_path: String,
    pub(super) file_name: String,
    pub(super) json_path: String,
    pub(super) location_path: String,
    pub(super) original_text: String,
    pub(super) path_template: String,
    #[serde(skip_serializing)]
    pub(super) raw_text: String,
    pub(super) rule_index: usize,
}

#[derive(Debug, Serialize)]
pub(super) struct EventCommandPathHitCountOutput {
    path_template: String,
    hit_count: usize,
}

#[derive(Debug, Serialize)]
pub(super) struct EventCommandRuleSummaryOutput {
    command_code: i64,
    matched_command_count: usize,
    matched_command_location_paths: Vec<String>,
    path_hit_counts: Vec<EventCommandPathHitCountOutput>,
    rule_index: usize,
}

pub(super) struct EventCommandRuleCandidateScan {
    pub(super) candidates: Vec<RuleCandidateOutput>,
    pub(super) command_codes: Vec<i64>,
    pub(super) hit_details: Vec<EventCommandHitDetailOutput>,
    pub(super) matched_command_count: usize,
    pub(super) rule_summaries: Vec<EventCommandRuleSummaryOutput>,
    pub(super) sample_count: usize,
    pub(super) samples_by_code: BTreeMap<String, Vec<Value>>,
    pub(super) scanned_command_count: usize,
}

#[derive(Debug)]
struct EventCommandSnapshot {
    file_name: String,
    command_location_path: String,
    command_code: i64,
    parameters: Vec<Value>,
}

#[derive(Debug)]
struct EventCommandLeaf {
    path: String,
    text: String,
}

#[derive(Debug)]
struct EventCommandRuleStats {
    command_code: i64,
    matched_command_count: usize,
    matched_command_location_paths: BTreeSet<String>,
    path_hit_counts: BTreeMap<String, usize>,
    path_templates: Vec<String>,
    rule_index: usize,
}

pub(super) fn scan_event_command_rule_candidates(
    data_files: &[EventCommandDataFileInput],
    event_command_codes: &[i64],
    rules: &[EventCommandRuleInput],
) -> Result<EventCommandRuleCandidateScan, String> {
    let explicit_command_codes = event_command_codes.iter().copied().collect::<BTreeSet<_>>();
    let command_code_set = event_command_codes
        .iter()
        .copied()
        .chain(rules.iter().map(|rule| rule.command_code))
        .collect::<BTreeSet<_>>();
    let command_codes = command_code_set.iter().copied().collect::<Vec<_>>();
    let mut samples_by_code = command_codes
        .iter()
        .map(|code| (code.to_string(), Vec::new()))
        .collect::<BTreeMap<_, _>>();
    let mut seen_samples = BTreeSet::new();
    let mut seen_candidates = BTreeSet::new();
    let mut candidates = Vec::new();
    let mut hit_details = Vec::new();
    let mut rule_stats = rules
        .iter()
        .enumerate()
        .map(|(rule_index, rule)| EventCommandRuleStats::new(rule_index, rule))
        .collect::<Vec<_>>();
    let mut scanned_command_count = 0usize;
    let mut matched_command_count = 0usize;

    let mut sorted_files = data_files.iter().collect::<Vec<_>>();
    sorted_files.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let snapshot_groups = sorted_files
        .par_iter()
        .map(|file| collect_event_command_snapshots(file))
        .collect::<Vec<_>>();
    for snapshots in snapshot_groups {
        scanned_command_count += snapshots.len();
        for snapshot in snapshots {
            if !command_code_set.contains(&snapshot.command_code) {
                continue;
            }
            matched_command_count += 1;
            append_event_command_sample(&snapshot, &mut samples_by_code, &mut seen_samples)?;
            let leaves = resolve_event_command_leaves(&snapshot.parameters);
            if explicit_command_codes.contains(&snapshot.command_code) {
                for leaf in leaves.iter() {
                    append_event_command_candidate(
                        &snapshot,
                        leaf,
                        &format!("event_command.{}.default", snapshot.command_code),
                        &mut seen_candidates,
                        &mut candidates,
                    )?;
                }
            }
            for (rule_index, rule) in rules.iter().enumerate() {
                if rule.command_code != snapshot.command_code
                    || !command_matches_filters(&snapshot.parameters, &rule.parameter_filters)
                {
                    continue;
                }
                rule_stats[rule_index].record_matched_command(&snapshot.command_location_path);
                for path_template in &rule.path_templates {
                    let matched_leaves = expand_rule_to_leaf_paths(path_template, &leaves)?;
                    rule_stats[rule_index].record_path_hits(path_template, matched_leaves.len());
                    for leaf in matched_leaves {
                        let location_path = jsonpath_to_event_command_location_path(
                            &leaf.path,
                            &snapshot.command_location_path,
                        )?;
                        let original_text = normalize_visible_text_for_extraction(&leaf.text);
                        hit_details.push(EventCommandHitDetailOutput {
                            command_code: snapshot.command_code,
                            command_location_path: snapshot.command_location_path.clone(),
                            file_name: snapshot.file_name.clone(),
                            json_path: leaf.path.clone(),
                            location_path: location_path.clone(),
                            original_text,
                            path_template: path_template.clone(),
                            raw_text: leaf.text.clone(),
                            rule_index,
                        });
                        append_event_command_candidate(
                            &snapshot,
                            leaf,
                            &format!("event_command.{}.rule.{rule_index}", snapshot.command_code),
                            &mut seen_candidates,
                            &mut candidates,
                        )?;
                    }
                }
            }
        }
    }

    let sample_count = samples_by_code
        .values()
        .map(std::vec::Vec::len)
        .sum::<usize>();
    Ok(EventCommandRuleCandidateScan {
        candidates,
        command_codes,
        hit_details,
        matched_command_count,
        rule_summaries: rule_stats
            .into_iter()
            .map(EventCommandRuleStats::into_output)
            .collect(),
        sample_count,
        samples_by_code,
        scanned_command_count,
    })
}

pub(super) fn scan_event_command_rule_hit_details(
    data_files: &[EventCommandDataFileInput],
    rules: &[EventCommandRuleInput],
) -> Result<Vec<EventCommandHitDetailOutput>, String> {
    if rules.is_empty() {
        return Ok(Vec::new());
    }
    let command_code_set = rules
        .iter()
        .map(|rule| rule.command_code)
        .collect::<BTreeSet<_>>();
    let mut sorted_files = data_files.iter().collect::<Vec<_>>();
    sorted_files.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let snapshot_groups = sorted_files
        .par_iter()
        .map(|file| collect_event_command_snapshots(file))
        .collect::<Vec<_>>();
    let mut hit_details = Vec::new();
    for snapshot in snapshot_groups.into_iter().flatten() {
        if !command_code_set.contains(&snapshot.command_code) {
            continue;
        }
        let leaves = resolve_event_command_leaves(&snapshot.parameters);
        for (rule_index, rule) in rules.iter().enumerate() {
            if rule.command_code != snapshot.command_code
                || !command_matches_filters(&snapshot.parameters, &rule.parameter_filters)
            {
                continue;
            }
            for path_template in &rule.path_templates {
                let matched_leaves = expand_rule_to_leaf_paths(path_template, &leaves)?;
                for leaf in matched_leaves {
                    let location_path = jsonpath_to_event_command_location_path(
                        &leaf.path,
                        &snapshot.command_location_path,
                    )?;
                    let original_text = normalize_visible_text_for_extraction(&leaf.text);
                    hit_details.push(EventCommandHitDetailOutput {
                        command_code: snapshot.command_code,
                        command_location_path: snapshot.command_location_path.clone(),
                        file_name: snapshot.file_name.clone(),
                        json_path: leaf.path.clone(),
                        location_path,
                        original_text,
                        path_template: path_template.clone(),
                        raw_text: leaf.text.clone(),
                        rule_index,
                    });
                }
            }
        }
    }
    Ok(hit_details)
}

pub(super) fn event_command_scope_hash_payload(
    data_files: &[EventCommandDataFileInput],
    event_command_codes: &[i64],
) -> Value {
    let command_code_set = event_command_codes.iter().copied().collect::<BTreeSet<_>>();
    let command_snapshots = python_event_command_scope_order(data_files)
        .par_iter()
        .map(|file| {
            collect_event_command_snapshots(file)
                .into_iter()
                .filter(|snapshot| command_code_set.contains(&snapshot.command_code))
                .map(|snapshot| {
                    json!({
                        "path": command_location_path_parts(&snapshot.command_location_path),
                        "code": snapshot.command_code,
                        "parameters": snapshot.parameters,
                    })
                })
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>()
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    json!({
        "command_codes": command_code_set.into_iter().collect::<Vec<_>>(),
        "commands": command_snapshots,
    })
}

fn python_event_command_scope_order(
    data_files: &[EventCommandDataFileInput],
) -> Vec<&EventCommandDataFileInput> {
    let mut map_files = data_files
        .iter()
        .filter(|file| file.file_name.starts_with("Map") && file.file_name.ends_with(".json"))
        .collect::<Vec<_>>();
    map_files.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    let mut ordered_files = map_files;
    if let Some(common_events) = data_files
        .iter()
        .find(|file| file.file_name == "CommonEvents.json")
    {
        ordered_files.push(common_events);
    }
    if let Some(troops) = data_files
        .iter()
        .find(|file| file.file_name == "Troops.json")
    {
        ordered_files.push(troops);
    }
    ordered_files
}

fn command_location_path_parts(command_location_path: &str) -> Vec<Value> {
    command_location_path
        .split('/')
        .enumerate()
        .map(|(index, part)| {
            if index == 0 {
                return Value::String(part.to_string());
            }
            match part.parse::<i64>() {
                Ok(value) => Value::from(value),
                Err(_) => Value::String(part.to_string()),
            }
        })
        .collect()
}

impl EventCommandRuleStats {
    fn new(rule_index: usize, rule: &EventCommandRuleInput) -> Self {
        Self {
            command_code: rule.command_code,
            matched_command_count: 0,
            matched_command_location_paths: BTreeSet::new(),
            path_hit_counts: BTreeMap::new(),
            path_templates: rule.path_templates.clone(),
            rule_index,
        }
    }

    fn record_matched_command(&mut self, command_location_path: &str) {
        self.matched_command_count += 1;
        self.matched_command_location_paths
            .insert(command_location_path.to_string());
    }

    fn record_path_hits(&mut self, path_template: &str, hit_count: usize) {
        let path_hit_count = self
            .path_hit_counts
            .entry(path_template.to_string())
            .or_default();
        *path_hit_count += hit_count;
    }

    fn into_output(self) -> EventCommandRuleSummaryOutput {
        let path_hit_counts = self
            .path_templates
            .into_iter()
            .map(|path_template| {
                let hit_count = self
                    .path_hit_counts
                    .get(&path_template)
                    .copied()
                    .unwrap_or_default();
                EventCommandPathHitCountOutput {
                    path_template,
                    hit_count,
                }
            })
            .collect();
        EventCommandRuleSummaryOutput {
            command_code: self.command_code,
            matched_command_count: self.matched_command_count,
            matched_command_location_paths: self
                .matched_command_location_paths
                .into_iter()
                .collect(),
            path_hit_counts,
            rule_index: self.rule_index,
        }
    }
}

fn append_event_command_sample(
    snapshot: &EventCommandSnapshot,
    samples_by_code: &mut BTreeMap<String, Vec<Value>>,
    seen_samples: &mut BTreeSet<(i64, String)>,
) -> Result<(), String> {
    let sample_value = Value::Array(snapshot.parameters.clone());
    let sample_key = canonical_json_text(&sample_value)?;
    if seen_samples.insert((snapshot.command_code, sample_key)) {
        samples_by_code
            .entry(snapshot.command_code.to_string())
            .or_default()
            .push(sample_value);
    }
    Ok(())
}

fn append_event_command_candidate(
    snapshot: &EventCommandSnapshot,
    leaf: &EventCommandLeaf,
    rule_key: &str,
    seen_candidates: &mut BTreeSet<(String, String)>,
    candidates: &mut Vec<RuleCandidateOutput>,
) -> Result<(), String> {
    let location_path =
        jsonpath_to_event_command_location_path(&leaf.path, &snapshot.command_location_path)?;
    if !seen_candidates.insert((location_path.clone(), rule_key.to_string())) {
        return Ok(());
    }
    let original_text = normalize_visible_text_for_extraction(&leaf.text);
    candidates.push(RuleCandidateOutput {
        domain: "event_commands".to_string(),
        location_path,
        rule_key: rule_key.to_string(),
        original_text: original_text.clone(),
        source_file: snapshot.file_name.clone(),
        file: Some(snapshot.file_name.clone()),
        json_path: Some(leaf.path.clone()),
        source_text: Some(original_text.clone()),
        field_name: None,
        sibling_field_names: None,
        parent_object_keys: None,
        selector: None,
        text: Some(original_text),
        raw_text: Some(leaf.text.clone()),
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
    });
    Ok(())
}

fn command_matches_filters(
    parameters: &[Value],
    filters: &[EventCommandParameterFilterInput],
) -> bool {
    for filter in filters {
        let Some(Value::String(value)) = parameters.get(filter.index) else {
            return false;
        };
        if value != &filter.value {
            return false;
        }
    }
    true
}

fn collect_event_command_snapshots(file: &EventCommandDataFileInput) -> Vec<EventCommandSnapshot> {
    if is_map_file(&file.file_name) {
        return collect_map_event_command_snapshots(file);
    }
    match file.file_name.as_str() {
        "CommonEvents.json" => collect_common_event_command_snapshots(file),
        "Troops.json" => collect_troop_event_command_snapshots(file),
        _ => {
            let mut snapshots = Vec::new();
            collect_generic_event_command_snapshots(
                &file.file_name,
                &file.data,
                &mut Vec::new(),
                &mut snapshots,
            );
            snapshots
        }
    }
}

fn collect_map_event_command_snapshots(
    file: &EventCommandDataFileInput,
) -> Vec<EventCommandSnapshot> {
    let mut snapshots = Vec::new();
    let Some(events) = file.data.get("events").and_then(Value::as_array) else {
        return snapshots;
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
            for (command_index, command_value) in commands.iter().enumerate() {
                if let Some(snapshot) = snapshot_from_command_value(
                    &file.file_name,
                    format!("{}/{event_id}/{page_index}/{command_index}", file.file_name),
                    command_value,
                ) {
                    snapshots.push(snapshot);
                }
            }
        }
    }
    snapshots
}

fn collect_common_event_command_snapshots(
    file: &EventCommandDataFileInput,
) -> Vec<EventCommandSnapshot> {
    let mut snapshots = Vec::new();
    let Some(common_events) = file.data.as_array() else {
        return snapshots;
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
        for (command_index, command_value) in commands.iter().enumerate() {
            if let Some(snapshot) = snapshot_from_command_value(
                &file.file_name,
                format!("{}/{common_event_id}/{command_index}", file.file_name),
                command_value,
            ) {
                snapshots.push(snapshot);
            }
        }
    }
    snapshots
}

fn collect_troop_event_command_snapshots(
    file: &EventCommandDataFileInput,
) -> Vec<EventCommandSnapshot> {
    let mut snapshots = Vec::new();
    let Some(troops) = file.data.as_array() else {
        return snapshots;
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
            for (command_index, command_value) in commands.iter().enumerate() {
                if let Some(snapshot) = snapshot_from_command_value(
                    &file.file_name,
                    format!("{}/{troop_id}/{page_index}/{command_index}", file.file_name),
                    command_value,
                ) {
                    snapshots.push(snapshot);
                }
            }
        }
    }
    snapshots
}

fn collect_generic_event_command_snapshots(
    file_name: &str,
    value: &Value,
    path_parts: &mut Vec<String>,
    snapshots: &mut Vec<EventCommandSnapshot>,
) {
    match value {
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                path_parts.push(index.to_string());
                collect_generic_event_command_snapshots(file_name, item, path_parts, snapshots);
                let _ = path_parts.pop();
            }
        }
        Value::Object(object) => {
            if let Some(snapshot) = snapshot_from_command_value(
                file_name,
                generic_command_location_path(file_name, path_parts),
                value,
            ) {
                snapshots.push(snapshot);
                return;
            }
            for (key, child) in object {
                path_parts.push(key.clone());
                collect_generic_event_command_snapshots(file_name, child, path_parts, snapshots);
                let _ = path_parts.pop();
            }
        }
        _ => {}
    }
}

fn snapshot_from_command_value(
    file_name: &str,
    command_location_path: String,
    command_value: &Value,
) -> Option<EventCommandSnapshot> {
    let object = command_value.as_object()?;
    let command_code = object.get("code")?.as_i64()?;
    let parameters = object.get("parameters")?.as_array()?.clone();
    Some(EventCommandSnapshot {
        file_name: file_name.to_string(),
        command_location_path,
        command_code,
        parameters,
    })
}

fn resolve_event_command_leaves(parameters: &[Value]) -> Vec<EventCommandLeaf> {
    let mut leaves = Vec::new();
    for (index, parameter) in parameters.iter().enumerate() {
        walk_event_command_value(parameter, &format!("$['parameters'][{index}]"), &mut leaves);
    }
    leaves
}

fn walk_event_command_value(value: &Value, current_path: &str, leaves: &mut Vec<EventCommandLeaf>) {
    match value {
        Value::Object(object) => {
            for (key, child) in object {
                let child_path = format!("{current_path}[{}]", quote_jsonpath_key(key));
                walk_event_command_value(child, &child_path, leaves);
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                let child_path = format!("{current_path}[{index}]");
                walk_event_command_value(child, &child_path, leaves);
            }
        }
        Value::String(text) => {
            if let Some((container, _shell_depth)) = decode_json_container_text(text) {
                walk_event_command_value(&container, current_path, leaves);
                return;
            }
            leaves.push(EventCommandLeaf {
                path: current_path.to_string(),
                text: text.clone(),
            });
        }
        _ => {}
    }
}

fn expand_rule_to_leaf_paths<'a>(
    path_template: &str,
    leaves: &'a [EventCommandLeaf],
) -> Result<Vec<&'a EventCommandLeaf>, String> {
    let template_parts = parse_json_path(path_template)?;
    let mut matched_leaves = Vec::new();
    for leaf in leaves {
        if jsonpath_matches_template(&template_parts, &parse_json_path(&leaf.path)?) {
            matched_leaves.push(leaf);
        }
    }
    matched_leaves.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(matched_leaves)
}

fn jsonpath_to_event_command_location_path(
    json_path: &str,
    command_location_path: &str,
) -> Result<String, String> {
    let parts = parse_json_path(json_path)?;
    if !matches!(parts.first(), Some(JsonPathPart::Key(key)) if key == "parameters") {
        return Err(format!("事件指令路径必须从 parameters 开始: {json_path}"));
    }
    let mut location_path = command_location_path.to_string();
    for part in parts {
        location_path.push('/');
        match part {
            JsonPathPart::Key(key) => location_path.push_str(&key),
            JsonPathPart::Index(index) => location_path.push_str(&index.to_string()),
            JsonPathPart::Wildcard => {
                return Err(format!("事件指令实际路径不能包含通配符: {json_path}"));
            }
        }
    }
    Ok(location_path)
}

fn canonical_json_text(value: &Value) -> Result<String, String> {
    serde_json::to_string(&canonicalize_json_value(value))
        .map_err(|error| format!("事件指令样本 JSON 序列化失败: {error}"))
}

fn canonicalize_json_value(value: &Value) -> Value {
    match value {
        Value::Array(items) => Value::Array(items.iter().map(canonicalize_json_value).collect()),
        Value::Object(object) => {
            let mut keys = object.keys().collect::<Vec<_>>();
            keys.sort();
            let mut sorted_object = Map::new();
            for key in keys {
                if let Some(child) = object.get(key) {
                    sorted_object.insert(key.clone(), canonicalize_json_value(child));
                }
            }
            Value::Object(sorted_object)
        }
        _ => value.clone(),
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

fn integer_field(object: &Map<String, Value>, field_name: &str) -> Option<i64> {
    object.get(field_name)?.as_i64()
}

fn generic_command_location_path(file_name: &str, path_parts: &[String]) -> String {
    if path_parts.is_empty() {
        return file_name.to_string();
    }
    format!("{file_name}/{}", path_parts.join("/"))
}

fn quote_jsonpath_key(key: &str) -> String {
    let escaped_key = key.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped_key}'")
}

#[cfg(test)]
mod tests {
    use super::{
        EventCommandDataFileInput, EventCommandRuleInput, scan_event_command_rule_hit_details,
    };
    use serde_json::json;

    #[test]
    fn event_commands_hit_details_include_command_code_parameter_path_and_raw_text() {
        let data_files = vec![EventCommandDataFileInput {
            file_name: "CommonEvents.json".to_string(),
            data: json!([
                null,
                {
                    "id": 1,
                    "list": [
                        {
                            "code": 357,
                            "parameters": [
                                "PluginCommand",
                                "TestPlugin",
                                "show",
                                {"message": "生\n本文"}
                            ]
                        }
                    ]
                }
            ]),
        }];
        let rules = vec![EventCommandRuleInput {
            command_code: 357,
            parameter_filters: Vec::new(),
            path_templates: vec!["$['parameters'][3]['message']".to_string()],
        }];

        let hit_details =
            scan_event_command_rule_hit_details(&data_files, &rules).expect("事件指令命中应可扫描");

        assert_eq!(hit_details.len(), 1);
        let hit = &hit_details[0];
        assert_eq!(hit.command_code, 357);
        assert_eq!(hit.json_path, "$['parameters'][3]['message']");
        assert_eq!(
            hit.location_path,
            "CommonEvents.json/1/0/parameters/3/message"
        );
        assert_eq!(hit.raw_text, "生\n本文");
        assert_eq!(hit.original_text, "生\n本文");
    }
}
