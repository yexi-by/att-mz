use serde_json::Value;

use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_note_tag_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(files) = payload.as_object() else {
        return Err(vec![note_tags_issue(
            "note_tag_rules_shape_invalid",
            "Note 标签规则必须是文件名到标签名数组的对象".to_string(),
            "rules_payload",
            serde_json::json!({}),
        )]);
    };

    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (file_name, value) in files {
        if file_name.trim().is_empty() {
            issues.push(note_tags_issue(
                "note_tag_file_name_empty",
                "Note 标签规则文件名不能为空".to_string(),
                "file_name",
                serde_json::json!({}),
            ));
            continue;
        }
        let Some(tags) = value.as_array() else {
            issues.push(note_tags_issue(
                "note_tag_names_invalid",
                "Note 标签规则值必须是标签名数组".to_string(),
                "tag_names",
                serde_json::json!({"file_name": file_name}),
            ));
            continue;
        };
        for tag in tags {
            let Some(tag_name) = tag.as_str().map(str::trim).filter(|text| !text.is_empty()) else {
                issues.push(note_tags_issue(
                    "note_tag_name_empty",
                    "Note 标签名不能为空".to_string(),
                    "tag_names",
                    serde_json::json!({"file_name": file_name}),
                ));
                continue;
            };
            rules.push(NormalizedRuleInput {
                domain: RuleDomain::NoteTags,
                rule_order: rules.len() as i64,
                matcher_kind: MatcherKind::Literal,
                matcher_value: format!("{file_name}:{tag_name}"),
                payload_json: serde_json::json!({
                    "file_name": file_name,
                    "tag_name": tag_name,
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

fn note_tags_issue(code: &str, message: String, field: &str, details: Value) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::NoteTags),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}
