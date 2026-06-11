use serde_json::Value;

use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_event_command_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    if let Some(items) = payload.as_array() {
        return normalize_event_command_record_array(items);
    }
    let Some(commands) = payload.as_object() else {
        return Err(vec![event_commands_issue(
            "event_command_rules_shape_invalid",
            "事件指令规则必须是指令码到规则数组的对象，或当前事件指令规则记录数组".to_string(),
            "rules_payload",
            serde_json::json!({}),
        )]);
    };

    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (command_code, value) in commands {
        if command_code.trim().is_empty() || command_code.parse::<i64>().is_err() {
            issues.push(event_commands_issue(
                "event_command_code_invalid",
                "事件指令规则的指令码必须是整数字符串".to_string(),
                "command_code",
                serde_json::json!({"command_code": command_code}),
            ));
            continue;
        }
        let Some(command_rules) = value.as_array() else {
            issues.push(event_commands_issue(
                "event_command_rules_invalid",
                "事件指令规则值必须是规则数组".to_string(),
                "rules",
                serde_json::json!({"command_code": command_code}),
            ));
            continue;
        };
        for (rule_index, rule) in command_rules.iter().enumerate() {
            let Some(object) = rule.as_object() else {
                issues.push(event_commands_issue(
                    "event_command_rule_invalid",
                    "事件指令规则项必须是对象".to_string(),
                    "rules",
                    serde_json::json!({"command_code": command_code, "index": rule_index}),
                ));
                continue;
            };
            let Some(paths) = object.get("paths").and_then(Value::as_array) else {
                issues.push(event_commands_issue(
                    "event_command_paths_invalid",
                    "事件指令规则 paths 必须是字符串数组".to_string(),
                    "paths",
                    serde_json::json!({"command_code": command_code, "index": rule_index}),
                ));
                continue;
            };
            for path in paths {
                let Some(path_template) =
                    path.as_str().map(str::trim).filter(|text| !text.is_empty())
                else {
                    issues.push(event_commands_issue(
                        "event_command_path_empty",
                        "事件指令规则 path template 不能为空".to_string(),
                        "paths",
                        serde_json::json!({"command_code": command_code, "index": rule_index}),
                    ));
                    continue;
                };
                rules.push(NormalizedRuleInput {
                    domain: RuleDomain::EventCommands,
                    rule_order: rules.len() as i64,
                    matcher_kind: MatcherKind::JsonPathTemplate,
                    matcher_value: path_template.to_string(),
                    payload_json: serde_json::json!({
                        "command_code": command_code,
                        "match": object.get("match").cloned().unwrap_or(Value::Null),
                        "path": path_template,
                    }),
                });
            }
        }
    }

    if issues.is_empty() {
        Ok(rules)
    } else {
        Err(issues)
    }
}

fn normalize_event_command_record_array(
    items: &[Value],
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (item_index, item) in items.iter().enumerate() {
        let Some(object) = item.as_object() else {
            issues.push(event_commands_issue(
                "event_command_rule_invalid",
                "事件指令规则记录必须是对象".to_string(),
                "rules_payload",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let Some(command_code) = object.get("command_code").and_then(Value::as_i64) else {
            issues.push(event_commands_issue(
                "event_command_code_invalid",
                "事件指令规则记录缺少 command_code".to_string(),
                "command_code",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let Some(paths) = object
            .get("paths")
            .or_else(|| object.get("path_templates"))
            .and_then(Value::as_array)
        else {
            issues.push(event_commands_issue(
                "event_command_paths_invalid",
                "事件指令规则记录 paths 必须是字符串数组".to_string(),
                "paths",
                serde_json::json!({"index": item_index, "command_code": command_code}),
            ));
            continue;
        };
        for path in paths {
            let Some(path_template) = path.as_str().map(str::trim).filter(|text| !text.is_empty())
            else {
                issues.push(event_commands_issue(
                    "event_command_path_empty",
                    "事件指令规则 path template 不能为空".to_string(),
                    "paths",
                    serde_json::json!({"index": item_index, "command_code": command_code}),
                ));
                continue;
            };
            rules.push(NormalizedRuleInput {
                domain: RuleDomain::EventCommands,
                rule_order: rules.len() as i64,
                matcher_kind: MatcherKind::JsonPathTemplate,
                matcher_value: path_template.to_string(),
                payload_json: serde_json::json!({
                    "command_code": command_code,
                    "parameter_filters": object.get("parameter_filters").cloned().unwrap_or(Value::Null),
                    "path": path_template,
                }),
            });
        }
    }

    if issues.is_empty() {
        Ok(rules)
    } else {
        Err(issues)
    }
}

fn event_commands_issue(
    code: &str,
    message: String,
    field: &str,
    details: Value,
) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::EventCommands),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}
