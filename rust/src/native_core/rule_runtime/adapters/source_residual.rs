use serde_json::{Map, Value};

use super::super::engine::{Pcre2Engine, Pcre2EngineConfig, Pcre2Pattern};
use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_source_residual_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(object) = payload.as_object() else {
        return Err(vec![RuleRuntimeIssue::current_input_error(
            "source_residual_rules_shape_invalid",
            "源文残留例外规则必须是 JSON 对象".to_string(),
        )]);
    };

    let config = Pcre2EngineConfig::default_runtime();
    let mut normalized = Vec::new();
    let mut issues = Vec::new();
    normalize_position_rules(object, &mut normalized, &mut issues);
    normalize_structural_rules(object, &config, &mut normalized, &mut issues);

    if issues.is_empty() {
        Ok(normalized)
    } else {
        Err(issues)
    }
}

pub(crate) fn compile_source_residual_structural_pattern(
    rule_id: &str,
    pattern: &str,
    check_group: &str,
) -> Result<Pcre2Pattern, String> {
    let compiled =
        Pcre2Engine::compile(pattern, &Pcre2EngineConfig::default_runtime()).map_err(|error| {
            format!(
                "结构性源文保留规则 PCRE2 pattern 损坏: {rule_id}: {}",
                error.message
            )
        })?;
    if !compiled
        .capture_names()
        .iter()
        .any(|name| name == check_group)
    {
        return Err(format!("结构性源文保留规则缺少命名分组: {check_group}"));
    }
    Ok(compiled)
}

fn normalize_position_rules(
    object: &Map<String, Value>,
    normalized: &mut Vec<NormalizedRuleInput>,
    issues: &mut Vec<RuleRuntimeIssue>,
) {
    let Some(position_rules_value) = object.get("position_rules") else {
        return;
    };
    let Some(position_rules) = position_rules_value.as_object() else {
        issues.push(source_residual_issue(
            "source_residual_position_rules_invalid",
            "position_rules 必须是定位路径到规则对象的映射".to_string(),
            "position_rules",
            serde_json::json!({}),
        ));
        return;
    };
    for (index, (location_path, rule)) in position_rules.iter().enumerate() {
        let normalized_path = location_path.trim();
        if normalized_path.is_empty() {
            issues.push(source_residual_issue(
                "source_residual_position_path_empty",
                "position_rules 不能包含空定位路径".to_string(),
                "position_rules",
                serde_json::json!({"index": index}),
            ));
            continue;
        }
        let Some(rule_object) = rule.as_object() else {
            issues.push(source_residual_issue(
                "source_residual_position_rule_invalid",
                "源文残留位置规则必须是对象".to_string(),
                "position_rules",
                serde_json::json!({"index": index, "location_path": normalized_path}),
            ));
            continue;
        };
        let allowed_terms = normalized_string_array(rule_object, "allowed_terms");
        if allowed_terms.is_empty() {
            issues.push(source_residual_issue(
                "source_residual_allowed_terms_empty",
                "源文残留例外规则 allowed_terms 不能为空".to_string(),
                "allowed_terms",
                serde_json::json!({"index": index, "location_path": normalized_path}),
            ));
            continue;
        }
        let Some(reason) = required_string(rule_object, "reason") else {
            issues.push(source_residual_issue(
                "source_residual_reason_empty",
                "源文残留例外规则 reason 不能为空".to_string(),
                "reason",
                serde_json::json!({"index": index, "location_path": normalized_path}),
            ));
            continue;
        };
        let rule_id = rule_object
            .get("rule_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|text| !text.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| format!("position:{normalized_path}"));
        normalized.push(NormalizedRuleInput {
            domain: RuleDomain::SourceResidual,
            rule_order: index as i64,
            matcher_kind: MatcherKind::Literal,
            matcher_value: normalized_path.to_string(),
            payload_json: serde_json::json!({
                "rule_id": rule_id,
                "rule_type": "position",
                "location_path": normalized_path,
                "pattern_text": "",
                "allowed_terms": allowed_terms,
                "check_group": "",
                "reason": reason,
            }),
        });
    }
}

fn normalize_structural_rules(
    object: &Map<String, Value>,
    config: &Pcre2EngineConfig,
    normalized: &mut Vec<NormalizedRuleInput>,
    issues: &mut Vec<RuleRuntimeIssue>,
) {
    let Some(structural_rules_value) = object.get("structural_rules") else {
        return;
    };
    let Some(structural_rules) = structural_rules_value.as_array() else {
        issues.push(source_residual_issue(
            "source_residual_structural_rules_invalid",
            "structural_rules 必须是数组".to_string(),
            "structural_rules",
            serde_json::json!({}),
        ));
        return;
    };
    for (index, rule) in structural_rules.iter().enumerate() {
        let Some(rule_object) = rule.as_object() else {
            issues.push(source_residual_issue(
                "source_residual_structural_rule_invalid",
                "结构性源文残留规则必须是对象".to_string(),
                "structural_rules",
                serde_json::json!({"index": index}),
            ));
            continue;
        };
        let Some(pattern) = required_string(rule_object, "pattern") else {
            issues.push(source_residual_issue(
                "source_residual_pattern_empty",
                "结构性源文残留规则 pattern 不能为空".to_string(),
                "pattern",
                serde_json::json!({"index": index}),
            ));
            continue;
        };
        let Some(check_group) = required_string(rule_object, "check_group") else {
            issues.push(source_residual_issue(
                "source_residual_check_group_empty",
                "结构性源文残留规则 check_group 不能为空".to_string(),
                "check_group",
                serde_json::json!({"index": index, "pattern": pattern}),
            ));
            continue;
        };
        let allowed_terms = normalized_string_array(rule_object, "allowed_terms");
        if allowed_terms.is_empty() {
            issues.push(source_residual_issue(
                "source_residual_allowed_terms_empty",
                "源文残留例外规则 allowed_terms 不能为空".to_string(),
                "allowed_terms",
                serde_json::json!({"index": index, "pattern": pattern}),
            ));
            continue;
        }
        let Some(reason) = required_string(rule_object, "reason") else {
            issues.push(source_residual_issue(
                "source_residual_reason_empty",
                "源文残留例外规则 reason 不能为空".to_string(),
                "reason",
                serde_json::json!({"index": index, "pattern": pattern}),
            ));
            continue;
        };
        let rule_id = rule_object
            .get("rule_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|text| !text.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| format!("structural:{index}"));
        let compiled = match Pcre2Engine::compile(pattern, config) {
            Ok(compiled) => compiled,
            Err(error) => {
                issues.push(source_residual_issue(
                    error.code,
                    error.message,
                    "pattern",
                    serde_json::json!({"index": index, "pattern": pattern}),
                ));
                continue;
            }
        };
        let capture_names = compiled.capture_names();
        if !capture_names.iter().any(|name| name == check_group) {
            issues.push(source_residual_issue(
                "source_residual_check_group_missing",
                format!("结构性源文残留规则缺少当前 check_group capture：{check_group}"),
                "check_group",
                serde_json::json!({"index": index, "pattern": pattern, "check_group": check_group}),
            ));
            continue;
        }
        normalized.push(NormalizedRuleInput {
            domain: RuleDomain::SourceResidual,
            rule_order: 10_000 + index as i64,
            matcher_kind: MatcherKind::Pcre2Pattern,
            matcher_value: pattern.to_string(),
            payload_json: serde_json::json!({
                "rule_id": rule_id,
                "rule_type": "structural",
                "location_path": "",
                "pattern_text": pattern,
                "allowed_terms": allowed_terms,
                "check_group": check_group,
                "reason": reason,
            }),
        });
    }
}

fn required_string<'a>(rule: &'a Map<String, Value>, field: &str) -> Option<&'a str> {
    let value = rule.get(field)?.as_str()?.trim();
    if value.is_empty() {
        return None;
    }
    Some(value)
}

fn normalized_string_array(rule: &Map<String, Value>, field: &str) -> Vec<String> {
    let Some(values) = rule.get(field).and_then(Value::as_array) else {
        return Vec::new();
    };
    let mut normalized = Vec::new();
    for value in values {
        let Some(text) = value.as_str() else {
            continue;
        };
        let text = text.trim();
        if text.is_empty() || normalized.iter().any(|item| item == text) {
            continue;
        }
        normalized.push(text.to_string());
    }
    normalized
}

fn source_residual_issue(
    code: &str,
    message: String,
    field: &str,
    details: Value,
) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::SourceResidual),
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
    fn source_residual_accepts_pcre2_named_capture() {
        let normalized = normalize_source_residual_rules(&json!({
            "position_rules": {},
            "structural_rules": [
                {
                    "pattern": "^<name>(?<visible>[^<]+)</name>$",
                    "check_group": "visible",
                    "allowed_terms": ["name"],
                    "reason": "协议外壳"
                }
            ]
        }))
        .expect("PCRE2 structural rule should normalize");

        assert_eq!(normalized.len(), 1);
        assert_eq!(normalized[0].domain, RuleDomain::SourceResidual);
        assert_eq!(normalized[0].matcher_kind, MatcherKind::Pcre2Pattern);
    }

    #[test]
    fn source_residual_requires_current_check_group_capture() {
        let errors = normalize_source_residual_rules(&json!({
            "position_rules": {},
            "structural_rules": [
                {
                    "pattern": "^<name>(?<visible>[^<]+)</name>$",
                    "check_group": "missing",
                    "allowed_terms": ["name"],
                    "reason": "协议外壳"
                }
            ]
        }))
        .expect_err("missing capture should fail");

        assert_eq!(errors[0].code, "source_residual_check_group_missing");
    }
}
