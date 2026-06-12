use serde_json::Value;

use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_nonstandard_data_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    if let Some(items) = payload.as_array() {
        return normalize_nonstandard_data_rule_array(items);
    }
    let Some(files) = payload.as_object() else {
        return Err(vec![nonstandard_data_issue(
            "nonstandard_data_rules_shape_invalid",
            "非标准 data 规则必须是文件名到 path template 数组的对象，或当前非标准 data 规则数组"
                .to_string(),
            "rules_payload",
            serde_json::json!({}),
        )]);
    };

    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (file_name, value) in files {
        if file_name.trim().is_empty() {
            issues.push(nonstandard_data_issue(
                "nonstandard_data_file_name_empty",
                "非标准 data 规则文件名不能为空".to_string(),
                "file_name",
                serde_json::json!({}),
            ));
            continue;
        }
        let Some(paths) = value.as_array() else {
            issues.push(nonstandard_data_issue(
                "nonstandard_data_paths_invalid",
                "非标准 data 规则值必须是 path template 数组".to_string(),
                "paths",
                serde_json::json!({"file_name": file_name}),
            ));
            continue;
        };
        for path in paths {
            let Some(path_template) = path.as_str().map(str::trim).filter(|text| !text.is_empty())
            else {
                issues.push(nonstandard_data_issue(
                    "nonstandard_data_path_empty",
                    "非标准 data path template 不能为空".to_string(),
                    "paths",
                    serde_json::json!({"file_name": file_name}),
                ));
                continue;
            };
            rules.push(NormalizedRuleInput {
                domain: RuleDomain::NonstandardData,
                rule_order: rules.len() as i64,
                matcher_kind: MatcherKind::JsonPathTemplate,
                matcher_value: path_template.to_string(),
                payload_json: serde_json::json!({
                    "file_name": file_name,
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

fn normalize_nonstandard_data_rule_array(
    items: &[Value],
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (item_index, item) in items.iter().enumerate() {
        let Some(object) = item.as_object() else {
            issues.push(nonstandard_data_issue(
                "nonstandard_data_rule_invalid",
                "非标准 data 规则项必须是对象".to_string(),
                "rules_payload",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let Some(file_name) = object
            .get("file")
            .or_else(|| object.get("file_name"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|text| !text.is_empty())
        else {
            issues.push(nonstandard_data_issue(
                "nonstandard_data_file_name_empty",
                "非标准 data 规则缺少 file".to_string(),
                "file",
                serde_json::json!({"index": item_index}),
            ));
            continue;
        };
        let file_hash = object
            .get("file_hash")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or("");
        if object
            .get("skipped")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            rules.push(NormalizedRuleInput {
                domain: RuleDomain::NonstandardData,
                rule_order: rules.len() as i64,
                matcher_kind: MatcherKind::DomainPayload,
                matcher_value: String::new(),
                payload_json: serde_json::json!({
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "path": "",
                    "path_kind": "skipped",
                }),
            });
            continue;
        }
        for (field_names, path_kind) in [
            (["paths", "path_templates"], "translate"),
            (["excluded_paths", "excluded_path_templates"], "excluded"),
        ] {
            let Some(paths) = field_names
                .iter()
                .find_map(|field_name| object.get(*field_name).and_then(Value::as_array))
            else {
                continue;
            };
            for path in paths {
                let Some(path_template) =
                    path.as_str().map(str::trim).filter(|text| !text.is_empty())
                else {
                    issues.push(nonstandard_data_issue(
                        "nonstandard_data_path_empty",
                        "非标准 data path template 不能为空".to_string(),
                        path_kind,
                        serde_json::json!({"index": item_index, "file_name": file_name}),
                    ));
                    continue;
                };
                rules.push(NormalizedRuleInput {
                    domain: RuleDomain::NonstandardData,
                    rule_order: rules.len() as i64,
                    matcher_kind: MatcherKind::JsonPathTemplate,
                    matcher_value: path_template.to_string(),
                    payload_json: serde_json::json!({
                        "file_name": file_name,
                        "file_hash": file_hash,
                        "path": path_template,
                        "path_kind": path_kind,
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

fn nonstandard_data_issue(
    code: &str,
    message: String,
    field: &str,
    details: Value,
) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::NonstandardData),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}
