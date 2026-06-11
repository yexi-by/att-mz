use serde_json::Value;

use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_plugin_config_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(items) = payload.as_array() else {
        return Err(vec![plugin_config_issue(
            "plugin_config_rules_shape_invalid",
            "插件配置规则必须是规则对象数组".to_string(),
            "rules_payload",
            serde_json::json!({}),
        )]);
    };

    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (item_index, item) in items.iter().enumerate() {
        let Some(object) = item.as_object() else {
            issues.push(plugin_config_issue(
                "plugin_config_rule_invalid",
                "插件配置规则项必须是对象".to_string(),
                "rules_payload",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let Some(plugin_name) = object.get("plugin_name").and_then(Value::as_str) else {
            issues.push(plugin_config_issue(
                "plugin_config_plugin_name_empty",
                "插件配置规则缺少 plugin_name".to_string(),
                "plugin_name",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let plugin_index = object
            .get("plugin_index")
            .and_then(Value::as_i64)
            .unwrap_or(-1);
        let Some(paths) = object
            .get("paths")
            .or_else(|| object.get("path_templates"))
            .and_then(Value::as_array)
        else {
            issues.push(plugin_config_issue(
                "plugin_config_paths_invalid",
                "插件配置规则 paths 必须是字符串数组".to_string(),
                "paths",
                serde_json::json!({"index": item_index, "plugin_name": plugin_name}),
            ));
            continue;
        };
        for path in paths {
            let Some(path_template) = path.as_str().map(str::trim).filter(|text| !text.is_empty())
            else {
                issues.push(plugin_config_issue(
                    "plugin_config_path_empty",
                    "插件配置规则 path template 不能为空".to_string(),
                    "paths",
                    serde_json::json!({"index": item_index, "plugin_name": plugin_name}),
                ));
                continue;
            };
            rules.push(NormalizedRuleInput {
                domain: RuleDomain::PluginConfig,
                rule_order: rules.len() as i64,
                matcher_kind: MatcherKind::JsonPathTemplate,
                matcher_value: path_template.to_string(),
                payload_json: serde_json::json!({
                    "plugin_index": plugin_index,
                    "plugin_name": plugin_name,
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

fn plugin_config_issue(
    code: &str,
    message: String,
    field: &str,
    details: Value,
) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::PluginConfig),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}
