use serde_json::Value;

use super::super::engine::{Pcre2Engine, Pcre2EngineConfig};
use super::super::errors::RuleRuntimeIssue;
use super::super::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_placeholder_rules(
    payload: &Value,
) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let Some(object) = payload.as_object() else {
        return Err(vec![RuleRuntimeIssue::current_input_error(
            "placeholder_rules_shape_invalid",
            "普通占位符规则必须是 pattern 到模板的对象".to_string(),
        )]);
    };

    let config = Pcre2EngineConfig::default_runtime();
    let mut rules = Vec::new();
    let mut issues = Vec::new();
    for (index, (pattern, template)) in object.iter().enumerate() {
        let compiled_pattern = if pattern.trim().is_empty() {
            issues.push(placeholder_issue(
                "placeholder_pattern_empty",
                "普通占位符规则的 PCRE2 pattern 不能为空".to_string(),
                "pattern",
                serde_json::json!({"pattern": pattern}),
            ));
            continue;
        } else {
            match Pcre2Engine::compile(pattern, &config) {
                Ok(compiled_pattern) => compiled_pattern,
                Err(error) => {
                    issues.push(placeholder_issue(
                        error.code,
                        error.message,
                        "pattern",
                        serde_json::json!({"pattern": pattern}),
                    ));
                    continue;
                }
            }
        };
        match compiled_pattern.is_match("") {
            Ok(false) => {}
            Ok(true) => {
                issues.push(placeholder_issue(
                    "placeholder_pattern_matches_empty",
                    "普通占位符规则的 PCRE2 pattern 不能匹配空字符串".to_string(),
                    "pattern",
                    serde_json::json!({"pattern": pattern}),
                ));
                continue;
            }
            Err(error) => {
                issues.push(placeholder_issue(
                    error.code,
                    error.message,
                    "pattern",
                    serde_json::json!({"pattern": pattern}),
                ));
                continue;
            }
        }
        let Some(template_text) = template.as_str() else {
            issues.push(placeholder_issue(
                "placeholder_template_invalid",
                "普通占位符模板必须是字符串".to_string(),
                "placeholder_template",
                serde_json::json!({"pattern": pattern}),
            ));
            continue;
        };
        if let Err(message) = validate_placeholder_template(template_text) {
            issues.push(placeholder_issue(
                "placeholder_template_invalid",
                message,
                "placeholder_template",
                serde_json::json!({"pattern": pattern, "placeholder_template": template_text}),
            ));
            continue;
        }
        rules.push(NormalizedRuleInput {
            domain: RuleDomain::Placeholders,
            rule_order: index as i64,
            matcher_kind: MatcherKind::Pcre2Pattern,
            matcher_value: pattern.to_string(),
            payload_json: serde_json::json!({"placeholder_template": template_text}),
        });
    }

    if issues.is_empty() {
        Ok(rules)
    } else {
        Err(issues)
    }
}

fn placeholder_issue(code: &str, message: String, field: &str, details: Value) -> RuleRuntimeIssue {
    RuleRuntimeIssue {
        code: code.to_string(),
        domain: Some(RuleDomain::Placeholders),
        rule_id: None,
        field: Some(field.to_string()),
        message,
        details,
        location: None,
    }
}

fn validate_placeholder_template(template: &str) -> Result<(), String> {
    if template.trim().is_empty() {
        return Err("普通占位符模板不能为空".to_string());
    }
    let preview = render_placeholder_template(template)?;
    if !is_custom_placeholder_preview(&preview) {
        return Err(format!(
            "普通占位符模板必须生成形如 [CUSTOM_NAME_1] 的方括号占位符，当前生成: {preview}"
        ));
    }
    Ok(())
}

fn render_placeholder_template(template: &str) -> Result<String, String> {
    let mut output = String::new();
    let mut chars = template.chars().peekable();
    while let Some(char) = chars.next() {
        if char == '{' {
            if chars.peek() == Some(&'{') {
                let _ = chars.next();
                output.push('{');
                continue;
            }
            let mut key = String::new();
            let mut closed = false;
            for inner in chars.by_ref() {
                if inner == '}' {
                    closed = true;
                    break;
                }
                key.push(inner);
            }
            if !closed {
                return Err(format!(
                    "普通占位符模板格式无效，仅支持 code、param、index 变量: {template}"
                ));
            }
            match key.as_str() {
                "code" | "param" => {}
                "index" => output.push('1'),
                _ => {
                    return Err(format!(
                        "普通占位符模板格式无效，仅支持 code、param、index 变量: {template}"
                    ));
                }
            }
            continue;
        }
        if char == '}' {
            if chars.peek() == Some(&'}') {
                let _ = chars.next();
                output.push('}');
                continue;
            }
            return Err(format!(
                "普通占位符模板格式无效，仅支持 code、param、index 变量: {template}"
            ));
        }
        output.push(char);
    }
    Ok(output)
}

fn is_custom_placeholder_preview(value: &str) -> bool {
    let Some(body) = value.strip_prefix("[CUSTOM_") else {
        return false;
    };
    let Some(name) = body.strip_suffix("_1]") else {
        return false;
    };
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if !first.is_ascii_uppercase() {
        return false;
    }
    chars.all(|char| char == '_' || char.is_ascii_uppercase() || char.is_ascii_digit())
}
