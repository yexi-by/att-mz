use serde_json::{Map, Value};
use std::collections::HashMap;

use super::super::engine::{Pcre2Engine, Pcre2EngineConfig, Pcre2Pattern};
use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};
use super::placeholders::validate_custom_placeholder_template;

pub(crate) fn normalize_structured_placeholder_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(rules_value) = payload.get("paired_shell_rules").and_then(Value::as_array) else {
        return Err(vec![RuleRuntimeIssue::current_input_error(
            "structured_placeholder_rules_shape_invalid",
            "结构化占位符规则必须包含 paired_shell_rules 数组".to_string(),
        )]);
    };

    let config = Pcre2EngineConfig::default_runtime();
    let mut normalized = Vec::new();
    let mut issues = Vec::new();
    for (index, rule) in rules_value.iter().enumerate() {
        let Some(rule_object) = rule.as_object() else {
            issues.push(structured_issue(
                "structured_placeholder_rule_invalid",
                "结构化占位符规则必须是对象".to_string(),
                "rule",
                serde_json::json!({"index": index}),
            ));
            continue;
        };
        let Some(pattern) = required_string(rule_object, "pattern") else {
            issues.push(structured_issue(
                "structured_placeholder_pattern_invalid",
                "结构化占位符规则 pattern 不能为空".to_string(),
                "pattern",
                serde_json::json!({"index": index}),
            ));
            continue;
        };
        let Some(translatable_group) = required_string(rule_object, "translatable_group") else {
            issues.push(structured_issue(
                "structured_placeholder_translatable_group_invalid",
                "结构化占位符规则 translatable_group 不能为空".to_string(),
                "translatable_group",
                serde_json::json!({"index": index, "pattern": pattern}),
            ));
            continue;
        };
        let Some(protected_groups) = rule_object
            .get("protected_groups")
            .and_then(Value::as_object)
        else {
            issues.push(structured_issue(
                "structured_placeholder_protected_groups_invalid",
                "结构化占位符规则 protected_groups 不能为空".to_string(),
                "protected_groups",
                serde_json::json!({"index": index, "pattern": pattern}),
            ));
            continue;
        };
        let compiled = match Pcre2Engine::compile(pattern, &config) {
            Ok(compiled) => compiled,
            Err(error) => {
                issues.push(structured_issue(
                    error.code,
                    error.message,
                    "pattern",
                    serde_json::json!({"index": index, "pattern": pattern}),
                ));
                continue;
            }
        };
        let capture_names = compiled.capture_names();
        if !capture_names.iter().any(|name| name == translatable_group) {
            issues.push(structured_issue(
                "structured_placeholder_translatable_capture_missing",
                format!("结构化占位符正则缺少可翻译命名分组: {translatable_group}"),
                "translatable_group",
                serde_json::json!({"index": index, "pattern": pattern, "translatable_group": translatable_group}),
            ));
            continue;
        }
        let mut protected_group_error = false;
        for (group_name, template_value) in protected_groups {
            if !capture_names.iter().any(|name| name == group_name) {
                issues.push(structured_issue(
                    "structured_placeholder_protected_capture_missing",
                    format!("结构化占位符正则缺少保护命名分组: {group_name}"),
                    "protected_groups",
                    serde_json::json!({"index": index, "pattern": pattern, "group": group_name}),
                ));
                protected_group_error = true;
                continue;
            }
            let Some(template) = template_value.as_str() else {
                issues.push(structured_issue(
                    "structured_placeholder_template_invalid",
                    format!("结构化占位符保护分组模板必须是字符串: {group_name}"),
                    "protected_groups",
                    serde_json::json!({"index": index, "pattern": pattern, "group": group_name}),
                ));
                protected_group_error = true;
                continue;
            };
            if let Err(message) =
                validate_custom_placeholder_template(template, "结构化占位符保护分组模板")
            {
                issues.push(structured_issue(
                    "structured_placeholder_template_invalid",
                    message,
                    "protected_groups",
                    serde_json::json!({"index": index, "pattern": pattern, "group": group_name, "placeholder_template": template}),
                ));
                protected_group_error = true;
            }
        }
        if protected_group_error {
            continue;
        }
        normalized.push(NormalizedRuleInput {
            domain: RuleDomain::StructuredPlaceholders,
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

pub(crate) fn compile_structured_placeholder_pattern(
    rule_name: &str,
    pattern: &str,
    translatable_group: &str,
    protected_groups: &HashMap<String, String>,
) -> Result<Pcre2Pattern, String> {
    let compiled =
        Pcre2Engine::compile(pattern, &Pcre2EngineConfig::default_runtime()).map_err(|error| {
            format!(
                "结构化占位符规则 {rule_name} PCRE2 pattern 无效: {}",
                error.message
            )
        })?;
    let capture_names = compiled.capture_names();
    if !capture_names.iter().any(|name| name == translatable_group) {
        return Err(format!(
            "结构化占位符规则 {rule_name} 缺少可翻译命名分组: {translatable_group}"
        ));
    }
    for group_name in protected_groups.keys() {
        if !capture_names.iter().any(|name| name == group_name) {
            return Err(format!(
                "结构化占位符规则 {rule_name} 缺少保护命名分组: {group_name}"
            ));
        }
    }
    match compiled.is_match("") {
        Ok(false) => {}
        Ok(true) => {
            return Err(format!(
                "结构化占位符规则 {rule_name} 的 PCRE2 pattern 不能匹配空字符串"
            ));
        }
        Err(error) => {
            return Err(format!(
                "结构化占位符规则 {rule_name} PCRE2 pattern 空串检测失败: {}",
                error.message
            ));
        }
    }
    Ok(compiled)
}

fn required_string<'a>(rule: &'a Map<String, Value>, field: &str) -> Option<&'a str> {
    let value = rule.get(field)?.as_str()?;
    if value.trim().is_empty() {
        return None;
    }
    Some(value)
}

fn structured_issue(code: &str, message: String, field: &str, details: Value) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::StructuredPlaceholders),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}
