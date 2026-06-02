//! 用户可写正则契约预检。
//!
//! 这里的入口只编译表达式并检查命名分组，不读取游戏文件、不访问数据库。

use fancy_regex::Regex as FancyRegex;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

#[derive(Debug, Deserialize)]
struct RegexContractPayload {
    #[serde(default)]
    fancy_patterns: Vec<FancyPatternSpec>,
    #[serde(default)]
    regex_patterns: Vec<RustRegexPatternSpec>,
}

#[derive(Debug, Deserialize)]
struct FancyPatternSpec {
    issue_code: String,
    rule_type: String,
    field_name: String,
    pattern: String,
    #[serde(default)]
    required_python_named_groups: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RustRegexPatternSpec {
    issue_code: String,
    rule_type: String,
    field_name: String,
    pattern: String,
    #[serde(default)]
    required_groups: Vec<String>,
}

#[derive(Debug, Serialize)]
struct RegexContractResult {
    errors: Vec<RegexContractError>,
}

#[derive(Debug, Serialize)]
struct RegexContractError {
    issue_code: String,
    rule_type: String,
    field_name: String,
    pattern: String,
    engine: String,
    message: String,
    recovery: String,
}

pub(crate) fn validate_regex_contract_impl(payload_json: &str) -> Result<String, String> {
    let payload: RegexContractPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("正则契约预检输入 JSON 无效: {error}"))?;
    let mut errors = Vec::new();
    for spec in payload.fancy_patterns {
        validate_fancy_pattern(&spec, &mut errors);
    }
    for spec in payload.regex_patterns {
        validate_rust_regex_pattern(&spec, &mut errors);
    }
    serde_json::to_string(&RegexContractResult { errors })
        .map_err(|error| format!("正则契约预检输出 JSON 编码失败: {error}"))
}

fn validate_fancy_pattern(spec: &FancyPatternSpec, errors: &mut Vec<RegexContractError>) {
    let pattern = match FancyRegex::new(&spec.pattern) {
        Ok(pattern) => pattern,
        Err(error) => {
            errors.push(RegexContractError {
                issue_code: spec.issue_code.clone(),
                rule_type: spec.rule_type.clone(),
                field_name: spec.field_name.clone(),
                pattern: spec.pattern.clone(),
                engine: "rust_fancy_regex".to_string(),
                message: format!("Rust fancy-regex 无法编译: {error}"),
                recovery: "请改成 Python re 与 Rust fancy-regex 都支持的正则语法后重新校验或导入。"
                    .to_string(),
            });
            return;
        }
    };

    if spec.required_python_named_groups.is_empty() {
        return;
    }
    let python_named_groups = pattern
        .capture_names()
        .flatten()
        .map(str::to_string)
        .collect::<HashSet<String>>();
    for group_name in &spec.required_python_named_groups {
        if python_named_groups.contains(group_name) {
            continue;
        }
        errors.push(RegexContractError {
            issue_code: spec.issue_code.clone(),
            rule_type: spec.rule_type.clone(),
            field_name: spec.field_name.clone(),
            pattern: spec.pattern.clone(),
            engine: "rust_fancy_regex_group".to_string(),
            message: format!("Rust fancy-regex 缺少命名分组: {group_name}"),
            recovery:
                "请使用 Python 风格命名分组 (?P<name>...)，不要使用其它正则方言的命名分组写法。"
                    .to_string(),
        });
    }
}

fn validate_rust_regex_pattern(spec: &RustRegexPatternSpec, errors: &mut Vec<RegexContractError>) {
    let pattern = match Regex::new(&spec.pattern) {
        Ok(pattern) => pattern,
        Err(error) => {
            errors.push(RegexContractError {
                issue_code: spec.issue_code.clone(),
                rule_type: spec.rule_type.clone(),
                field_name: spec.field_name.clone(),
                pattern: spec.pattern.clone(),
                engine: "rust_regex".to_string(),
                message: format!("Rust regex 无法编译: {error}"),
                recovery: "请改成 Python re 与 Rust regex 都支持的正则语法后重新校验或导入。"
                    .to_string(),
            });
            return;
        }
    };

    if spec.required_groups.is_empty() {
        return;
    }
    let group_names = pattern
        .capture_names()
        .flatten()
        .map(str::to_string)
        .collect::<HashSet<String>>();
    for group_name in &spec.required_groups {
        if group_names.contains(group_name) {
            continue;
        }
        errors.push(RegexContractError {
            issue_code: spec.issue_code.clone(),
            rule_type: spec.rule_type.clone(),
            field_name: spec.field_name.clone(),
            pattern: spec.pattern.clone(),
            engine: "rust_regex_group".to_string(),
            message: format!("Rust regex 缺少命名分组: {group_name}"),
            recovery: "请确保 check_group 对应的分组在 Python re 和 Rust regex 中都能被识别。"
                .to_string(),
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn validate(payload: Value) -> Value {
        let output = validate_regex_contract_impl(&payload.to_string()).expect("预检应返回 JSON");
        serde_json::from_str(&output).expect("输出应是 JSON")
    }

    #[test]
    fn validates_fancy_regex_success_and_failure() {
        let result = validate(json!({
            "fancy_patterns": [
                {
                    "issue_code": "placeholder_rules_invalid",
                    "rule_type": "普通占位符规则",
                    "field_name": "pattern",
                    "pattern": r"\\nn\[[^\]\r\n]+\]"
                },
                {
                    "issue_code": "placeholder_rules_invalid",
                    "rule_type": "普通占位符规则",
                    "field_name": "pattern",
                    "pattern": r"(?a:@PLUGIN\[[^\]]+\])"
                }
            ]
        }));

        let errors = result["errors"].as_array().expect("errors 应是数组");
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0]["engine"], json!("rust_fancy_regex"));
        assert!(
            errors[0]["message"]
                .as_str()
                .is_some_and(|message| message.contains("Rust fancy-regex"))
        );
    }

    #[test]
    fn validates_rust_regex_success_and_failure() {
        let result = validate(json!({
            "regex_patterns": [
                {
                    "issue_code": "source_residual_rules_invalid",
                    "rule_type": "源文残留结构规则",
                    "field_name": "pattern",
                    "pattern": r"^(?P<visible>label)$",
                    "required_groups": ["visible"]
                },
                {
                    "issue_code": "source_residual_rules_invalid",
                    "rule_type": "源文残留结构规则",
                    "field_name": "pattern",
                    "pattern": r"(?<=<label>)(?P<visible>[^<]+)(?=</label>)",
                    "required_groups": ["visible"]
                }
            ]
        }));

        let errors = result["errors"].as_array().expect("errors 应是数组");
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0]["engine"], json!("rust_regex"));
        assert!(
            errors[0]["message"]
                .as_str()
                .is_some_and(|message| message.contains("Rust regex"))
        );
    }

    #[test]
    fn validates_required_python_named_groups() {
        let result = validate(json!({
            "fancy_patterns": [
                {
                    "issue_code": "mv_virtual_namebox_rules_invalid",
                    "rule_type": "MV 虚拟名字框规则",
                    "field_name": "pattern",
                    "pattern": r"(?<speaker>[^:]+):(?<body>.*)",
                    "required_python_named_groups": ["speaker", "body"]
                }
            ]
        }));

        let errors = result["errors"].as_array().expect("errors 应是数组");
        assert_eq!(errors.len(), 0);
    }

    #[test]
    fn validates_python_named_groups_from_fancy_capture_names_not_text_scan() {
        let result = validate(json!({
            "fancy_patterns": [
                {
                    "issue_code": "mv_virtual_namebox_rules_invalid",
                    "rule_type": "MV 虚拟名字框规则",
                    "field_name": "pattern",
                    "pattern": r"[(?P<speaker>]+(?<body>.*)",
                    "required_python_named_groups": ["speaker"]
                }
            ]
        }));

        let errors = result["errors"].as_array().expect("errors 应是数组");
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0]["engine"], json!("rust_fancy_regex_group"));
    }

    #[test]
    fn validates_required_rust_regex_groups() {
        let result = validate(json!({
            "regex_patterns": [
                {
                    "issue_code": "source_residual_rules_invalid",
                    "rule_type": "源文残留结构规则",
                    "field_name": "pattern",
                    "pattern": r"^(?P<visible>label)$",
                    "required_groups": ["missing"]
                }
            ]
        }));

        let errors = result["errors"].as_array().expect("errors 应是数组");
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0]["engine"], json!("rust_regex_group"));
    }
}
