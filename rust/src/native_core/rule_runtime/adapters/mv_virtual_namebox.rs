use serde_json::{Map, Value};
use std::collections::BTreeSet;

use super::super::engine::{Pcre2Engine, Pcre2EngineConfig};
use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_mv_virtual_namebox_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(rules) = payload.get("rules").and_then(Value::as_array) else {
        return Err(vec![RuleRuntimeIssue::current_input_error(
            "mv_virtual_namebox_rules_shape_invalid",
            "MV 虚拟名字框规则必须包含 rules 数组".to_string(),
        )]);
    };

    let config = Pcre2EngineConfig::default_runtime();
    let mut normalized = Vec::new();
    let mut issues = Vec::new();
    for (index, rule) in rules.iter().enumerate() {
        let Some(rule_object) = rule.as_object() else {
            issues.push(mv_issue(
                "mv_virtual_namebox_rule_invalid",
                "MV 虚拟名字框规则必须是对象".to_string(),
                "rules",
                serde_json::json!({"index": index}),
            ));
            continue;
        };
        let Some(rule_name) = required_string(rule_object, "name") else {
            issues.push(mv_issue(
                "mv_virtual_namebox_rule_name_empty",
                "MV 虚拟名字框规则 name 不能为空".to_string(),
                "name",
                serde_json::json!({"index": index}),
            ));
            continue;
        };
        let Some(pattern) = required_string(rule_object, "pattern") else {
            issues.push(mv_issue(
                "mv_virtual_namebox_pattern_empty",
                format!("MV 虚拟名字框规则 {rule_name} pattern 不能为空"),
                "pattern",
                serde_json::json!({"index": index, "rule_name": rule_name}),
            ));
            continue;
        };
        let Some(speaker_group) = required_string(rule_object, "speaker_group") else {
            issues.push(mv_issue(
                "mv_virtual_namebox_speaker_group_empty",
                format!("MV 虚拟名字框规则 {rule_name} speaker_group 不能为空"),
                "speaker_group",
                serde_json::json!({"index": index, "rule_name": rule_name, "pattern": pattern}),
            ));
            continue;
        };
        let body_group = rule_object
            .get("body_group")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default();
        let Some(render_template) = required_string(rule_object, "render_template") else {
            issues.push(mv_issue(
                "mv_virtual_namebox_render_template_empty",
                format!("MV 虚拟名字框规则 {rule_name} render_template 不能为空"),
                "render_template",
                serde_json::json!({"index": index, "rule_name": rule_name, "pattern": pattern}),
            ));
            continue;
        };
        let compiled = match Pcre2Engine::compile(pattern, &config) {
            Ok(compiled) => compiled,
            Err(error) => {
                issues.push(mv_issue(
                    error.code,
                    error.message,
                    "pattern",
                    serde_json::json!({"index": index, "rule_name": rule_name, "pattern": pattern}),
                ));
                continue;
            }
        };
        let capture_names = compiled.capture_names();
        if !capture_names.iter().any(|name| name == speaker_group) {
            issues.push(mv_issue(
                "mv_virtual_namebox_speaker_capture_missing",
                format!("speaker capture 是必需分组，当前规则未声明：{speaker_group}"),
                "speaker_group",
                serde_json::json!({"index": index, "rule_name": rule_name, "pattern": pattern, "speaker_group": speaker_group}),
            ));
            continue;
        }
        if !body_group.is_empty() && !capture_names.iter().any(|name| name == body_group) {
            issues.push(mv_issue(
                "mv_virtual_namebox_body_capture_missing",
                format!("body_group 指向的 capture 不存在：{body_group}"),
                "body_group",
                serde_json::json!({"index": index, "rule_name": rule_name, "pattern": pattern, "body_group": body_group}),
            ));
            continue;
        }
        if let Err(message) = validate_render_template(
            render_template,
            &capture_names,
            speaker_group,
            body_group,
            rule_name,
        ) {
            issues.push(mv_issue(
                "mv_virtual_namebox_render_template_invalid",
                message,
                "render_template",
                serde_json::json!({"index": index, "rule_name": rule_name, "pattern": pattern}),
            ));
            continue;
        }
        normalized.push(NormalizedRuleInput {
            domain: RuleDomain::MvVirtualNamebox,
            rule_order: index as i64,
            matcher_kind: MatcherKind::Pcre2Pattern,
            matcher_value: pattern.to_string(),
            payload_json: rule.clone(),
        });
    }

    if issues.is_empty() {
        Ok(normalized)
    } else {
        Err(issues)
    }
}

fn required_string<'a>(rule: &'a Map<String, Value>, field: &str) -> Option<&'a str> {
    let value = rule.get(field)?.as_str()?.trim();
    if value.is_empty() {
        return None;
    }
    Some(value)
}

fn validate_render_template(
    template: &str,
    capture_names: &[String],
    speaker_group: &str,
    body_group: &str,
    rule_name: &str,
) -> Result<(), String> {
    let template_fields = read_template_fields(template)?;
    let allowed_fields = capture_names
        .iter()
        .map(String::as_str)
        .chain(["speaker", "body"])
        .collect::<BTreeSet<_>>();
    let unknown_fields = template_fields
        .iter()
        .filter(|field| !allowed_fields.contains(field.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if !unknown_fields.is_empty() {
        return Err(format!(
            "MV 虚拟名字框规则 {rule_name} 的模板引用未知字段: {}",
            unknown_fields.join(", ")
        ));
    }
    if !template_fields
        .iter()
        .any(|field| field == speaker_group || field == "speaker")
    {
        return Err(format!(
            "MV 虚拟名字框规则 {rule_name} 的模板没有引用说话人分组"
        ));
    }
    if !body_group.is_empty()
        && !template_fields
            .iter()
            .any(|field| field == body_group || field == "body")
    {
        return Err(format!(
            "MV 虚拟名字框规则 {rule_name} 的模板没有引用正文分组"
        ));
    }
    Ok(())
}

pub(crate) fn read_template_fields(template: &str) -> Result<BTreeSet<String>, String> {
    let mut fields = BTreeSet::new();
    let chars = template.chars().collect::<Vec<_>>();
    let mut index = 0usize;
    while index < chars.len() {
        match chars[index] {
            '{' => {
                if chars.get(index + 1) == Some(&'{') {
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
                if !is_template_field_name(field_name) {
                    return Err(format!("MV 虚拟名字框模板字段名非法: {field_expression}"));
                }
                fields.insert(field_name.to_string());
                index = end_index + 1;
            }
            '}' => {
                if chars.get(index + 1) == Some(&'}') {
                    index += 2;
                    continue;
                }
                return Err(format!("MV 虚拟名字框模板存在孤立闭合大括号: {template}"));
            }
            _ => index += 1,
        }
    }
    Ok(fields)
}

pub(crate) fn normalize_template_field_name(field_expression: &str) -> &str {
    field_expression
        .split(['!', ':'])
        .next()
        .unwrap_or_default()
        .split(['.', '['])
        .next()
        .unwrap_or_default()
}

fn is_template_field_name(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if !(first == '_' || first.is_ascii_alphabetic()) {
        return false;
    }
    chars.all(|char| char == '_' || char.is_ascii_alphanumeric())
}

fn mv_issue(code: &str, message: String, field: &str, details: Value) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::MvVirtualNamebox),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn mv_namebox_accepts_current_pcre2_capture() {
        let normalized = normalize_mv_virtual_namebox_rules(&json!({
            "rules": [
                {
                    "name": "colon-name",
                    "pattern": "^(?<speaker>[^：]+)：$",
                    "speaker_group": "speaker",
                    "speaker_policy": "translate",
                    "render_template": "{speaker}："
                }
            ]
        }))
        .expect("PCRE2 MV rule should normalize");

        assert_eq!(normalized.len(), 1);
        assert_eq!(normalized[0].domain, RuleDomain::MvVirtualNamebox);
    }

    #[test]
    fn mv_namebox_requires_speaker_capture() {
        let errors = normalize_mv_virtual_namebox_rules(&json!({
            "rules": [
                {
                    "name": "bad",
                    "pattern": "^(?<name>[^：]+)：$",
                    "speaker_group": "speaker",
                    "speaker_policy": "translate",
                    "render_template": "{speaker}："
                }
            ]
        }))
        .expect_err("missing speaker capture should fail");

        assert_eq!(errors[0].code, "mv_virtual_namebox_speaker_capture_missing");
    }
}
