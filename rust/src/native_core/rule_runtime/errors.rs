use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::model::RuleDomain;

/// 统一规则运行时返回给 Python/CLI 的结构化问题。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub(crate) struct RuleRuntimeIssue {
    /// 稳定问题码。
    pub(crate) code: String,
    /// 相关规则 domain。
    pub(crate) domain: Option<RuleDomain>,
    /// 相关规则 ID。
    pub(crate) rule_id: Option<String>,
    /// 相关输入字段。
    pub(crate) field: Option<String>,
    /// 面向用户的中文问题说明。
    pub(crate) message: String,
    /// 机器可读详情。
    pub(crate) details: Value,
    /// 规则或命中位置。
    pub(crate) location: Option<String>,
}

impl RuleRuntimeIssue {
    /// 构造当前输入不符合规则运行时契约的问题。
    pub(crate) fn current_input_error(code: &str, message: String) -> Self {
        Self {
            code: code.to_string(),
            domain: None,
            rule_id: None,
            field: None,
            message,
            details: Value::Object(Default::default()),
            location: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_input_error_uses_current_contract_shape() {
        let issue = RuleRuntimeIssue::current_input_error(
            "invalid_rule_runtime_input",
            "规则运行时输入无效".to_string(),
        );

        assert_eq!(issue.code, "invalid_rule_runtime_input");
        assert_eq!(issue.message, "规则运行时输入无效");
        assert_eq!(issue.domain, None);
        assert_eq!(issue.rule_id, None);
        assert_eq!(issue.field, None);
        assert_eq!(issue.location, None);
        assert_eq!(issue.details, Value::Object(Default::default()));
    }
}
