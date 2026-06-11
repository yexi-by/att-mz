use serde_json::Value;

use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_plugin_source_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(object) = payload.as_object() else {
        return Err(vec![plugin_source_issue(
            "plugin_source_rules_shape_invalid",
            "插件源码规则必须是包含 rules 数组的对象".to_string(),
            "rules_payload",
            serde_json::json!({}),
        )]);
    };
    let Some(items) = object.get("rules").and_then(Value::as_array) else {
        return Err(vec![plugin_source_issue(
            "plugin_source_rules_invalid",
            "插件源码规则 rules 必须是数组".to_string(),
            "rules",
            serde_json::json!({}),
        )]);
    };

    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (item_index, item) in items.iter().enumerate() {
        let Some(rule) = item.as_object() else {
            issues.push(plugin_source_issue(
                "plugin_source_rule_invalid",
                "插件源码规则项必须是对象".to_string(),
                "rules",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let Some(file_name) = rule
            .get("file")
            .or_else(|| rule.get("file_name"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|text| !text.is_empty())
        else {
            issues.push(plugin_source_issue(
                "plugin_source_file_empty",
                "插件源码规则缺少 file".to_string(),
                "file",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let Some(selectors) = rule.get("selectors").and_then(Value::as_array) else {
            issues.push(plugin_source_issue(
                "plugin_source_selectors_invalid",
                "插件源码规则 selectors 必须是字符串数组".to_string(),
                "selectors",
                serde_json::json!({"index": item_index, "file": file_name}),
            ));
            continue;
        };
        let excluded_selectors = normalized_string_array(rule.get("excluded_selectors"));
        for selector in selectors {
            let Some(selector_text) = selector
                .as_str()
                .map(str::trim)
                .filter(|text| !text.is_empty())
            else {
                issues.push(plugin_source_issue(
                    "plugin_source_selector_empty",
                    "插件源码 selector 不能为空".to_string(),
                    "selectors",
                    serde_json::json!({"index": item_index, "file": file_name}),
                ));
                continue;
            };
            rules.push(NormalizedRuleInput {
                domain: RuleDomain::PluginSource,
                rule_order: rules.len() as i64,
                matcher_kind: MatcherKind::AstSelector,
                matcher_value: selector_text.to_string(),
                payload_json: serde_json::json!({
                    "file": file_name,
                    "selector": selector_text,
                    "excluded_selectors": excluded_selectors,
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

fn normalized_string_array(value: Option<&Value>) -> Vec<String> {
    let Some(values) = value.and_then(Value::as_array) else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(Value::as_str)
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .map(str::to_string)
        .collect()
}

fn plugin_source_issue(
    code: &str,
    message: String,
    field: &str,
    details: Value,
) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::PluginSource),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}
