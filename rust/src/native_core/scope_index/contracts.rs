use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::native_core::text_facts::CURRENT_TEXT_FACT_CONTRACT_VERSION;

/// Rust scope facts contract 当前版本。
pub(crate) const RUST_SCOPE_FACTS_CONTRACT_VERSION: i64 = 1;

/// JavaScript / JSON parser 事实契约当前版本。
pub(crate) const PARSER_CONTRACT_VERSION: i64 = 1;

/// source branch 分类契约当前版本。
pub(crate) const SOURCE_BRANCH_CONTRACT_VERSION: i64 = 1;

/// 当前文本索引可持久化的事实契约。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[allow(dead_code)]
pub(crate) struct TextIndexContractFacts {
    /// Rust scope facts contract 版本。
    pub(crate) rust_contract_version: i64,
    /// parser 事实契约版本。
    pub(crate) parser_contract_version: i64,
    /// source branch 分类契约版本。
    pub(crate) source_branch_contract_version: i64,
    /// text fact schema 版本。
    pub(crate) text_fact_schema_version: i64,
    /// 当前 scope hash。
    pub(crate) scope_hash: String,
    /// 当前源快照指纹。
    pub(crate) source_snapshot_fingerprint: String,
    /// 当前规则指纹。
    pub(crate) rules_fingerprint: String,
    /// source branch 到 gate 事实的映射。
    pub(crate) gate_facts: BTreeMap<String, SourceBranchGateFact>,
}

impl TextIndexContractFacts {
    #[cfg(test)]
    pub(crate) fn new_for_test() -> Self {
        let mut gate_facts = BTreeMap::new();
        gate_facts.insert(
            "plugin_source_text".to_string(),
            SourceBranchGateFact {
                source_branch: "plugin_source_text".to_string(),
                status: GateStatus::Pass,
                scope_hash: "scope-hash-for-test".to_string(),
                error_codes: Vec::new(),
                stale_reasons: Vec::new(),
            },
        );
        Self {
            rust_contract_version: RUST_SCOPE_FACTS_CONTRACT_VERSION,
            parser_contract_version: PARSER_CONTRACT_VERSION,
            source_branch_contract_version: SOURCE_BRANCH_CONTRACT_VERSION,
            text_fact_schema_version: CURRENT_TEXT_FACT_CONTRACT_VERSION,
            scope_hash: "scope-hash-for-test".to_string(),
            source_snapshot_fingerprint: "source-fingerprint-for-test".to_string(),
            rules_fingerprint: "rules-fingerprint-for-test".to_string(),
            gate_facts,
        }
    }
}

/// 单个 source branch 的 gate 事实。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[allow(dead_code)]
pub(crate) struct SourceBranchGateFact {
    /// source branch 稳定标识。
    pub(crate) source_branch: String,
    /// gate 状态。
    pub(crate) status: GateStatus,
    /// 生成 gate 事实时的 scope hash。
    pub(crate) scope_hash: String,
    /// 稳定错误码集合。
    pub(crate) error_codes: Vec<String>,
    /// stale 原因集合。
    pub(crate) stale_reasons: Vec<StaleReason>,
}

/// gate 状态。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
#[allow(dead_code)]
pub(crate) enum GateStatus {
    /// gate 通过。
    Pass,
    /// gate 失败。
    Fail,
}

/// stale 原因。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[allow(dead_code)]
pub(crate) struct StaleReason {
    /// 稳定 stale 错误码。
    pub(crate) code: String,
    /// 面向用户或报告的说明。
    pub(crate) message: String,
}

/// 稳定 stale 错误码。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)]
pub(crate) enum StaleReasonCode {
    /// AST 缺失。
    AstMissing,
    /// selector 被当前过滤口径排除。
    SelectorFiltered,
    /// 源文件内容已变化。
    SourceFileChanged,
    /// 插件已停用。
    PluginDisabled,
    /// contract 版本已变化。
    ContractChanged,
}

impl StaleReasonCode {
    /// 返回稳定 snake_case 字符串错误码。
    #[allow(dead_code)]
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::AstMissing => "ast_missing",
            Self::SelectorFiltered => "selector_filtered",
            Self::SourceFileChanged => "source_file_changed",
            Self::PluginDisabled => "plugin_disabled",
            Self::ContractChanged => "contract_changed",
        }
    }
}

/// Rust scope/index JSON 输出的契约版本集合。
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(crate) struct ContractVersionsOutput {
    /// Rust scope facts contract 版本。
    pub(crate) rust_scope_facts: i64,
    /// parser 事实契约版本。
    pub(crate) parser: i64,
    /// source branch 分类契约版本。
    pub(crate) source_branch: i64,
    /// text fact schema 版本。
    pub(crate) text_fact_schema: i64,
}

/// 返回当前 Rust scope/index JSON 输出契约版本集合。
pub(crate) fn current_contract_versions() -> ContractVersionsOutput {
    ContractVersionsOutput {
        rust_scope_facts: RUST_SCOPE_FACTS_CONTRACT_VERSION,
        parser: PARSER_CONTRACT_VERSION,
        source_branch: SOURCE_BRANCH_CONTRACT_VERSION,
        text_fact_schema: CURRENT_TEXT_FACT_CONTRACT_VERSION,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn contract_versions_are_serialized_with_gate_facts() {
        let facts = TextIndexContractFacts::new_for_test();
        let value = serde_json::to_value(&facts).expect("contract facts 应可序列化");

        assert_eq!(
            value["rust_contract_version"],
            json!(RUST_SCOPE_FACTS_CONTRACT_VERSION)
        );
        assert_eq!(
            value["parser_contract_version"],
            json!(PARSER_CONTRACT_VERSION)
        );
        assert_eq!(
            value["source_branch_contract_version"],
            json!(SOURCE_BRANCH_CONTRACT_VERSION)
        );
        assert!(
            value["gate_facts"]
                .as_object()
                .is_some_and(|object| object.contains_key("plugin_source_text"))
        );
    }

    #[test]
    fn stale_reason_codes_are_stable_ascii_identifiers() {
        for code in [
            StaleReasonCode::AstMissing,
            StaleReasonCode::SelectorFiltered,
            StaleReasonCode::SourceFileChanged,
            StaleReasonCode::PluginDisabled,
            StaleReasonCode::ContractChanged,
        ] {
            let text = code.as_str();
            assert!(
                text.chars()
                    .all(|character| character.is_ascii_lowercase() || character == '_')
            );
        }
    }
}
