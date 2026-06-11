use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

/// 当前统一规则运行时输入/输出契约版本。
pub(crate) const RULE_RUNTIME_CONTRACT_VERSION: i64 = 1;

/// 当前统一规则 SQLite 存储 schema 版本。
pub(crate) const RULE_STORE_SCHEMA_VERSION: i64 = 1;

/// 统一规则所属的业务 domain。
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub(crate) enum RuleDomain {
    /// 插件配置文本规则。
    PluginConfig,
    /// 事件指令文本规则。
    EventCommands,
    /// note 标签文本规则。
    NoteTags,
    /// 非标准 data 文本规则。
    NonstandardData,
    /// 插件源码文本规则。
    PluginSource,
    /// 普通游戏控制符规则。
    Placeholders,
    /// 结构化游戏控制符规则。
    StructuredPlaceholders,
    /// 源文残留检测规则。
    SourceResidual,
    /// MV 虚拟名字框规则。
    MvVirtualNamebox,
}

/// 统一规则 matcher 的当前契约类型。
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub(crate) enum MatcherKind {
    /// PCRE2 正则 pattern。
    Pcre2Pattern,
    /// JSONPath/path template 类 matcher。
    JsonPathTemplate,
    /// AST selector 类 matcher。
    AstSelector,
    /// literal 精确匹配。
    Literal,
    /// domain payload 自解释 matcher。
    DomainPayload,
}

/// 参与规则 ID 和 hash 计算前的规范化规则输入。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct NormalizedRuleInput {
    /// 规则所属业务 domain。
    pub(crate) domain: RuleDomain,
    /// 同一 domain 内的规则顺序。
    pub(crate) rule_order: i64,
    /// matcher 类型。
    pub(crate) matcher_kind: MatcherKind,
    /// matcher 文本值。
    pub(crate) matcher_value: String,
    /// domain 专用 payload。
    pub(crate) payload_json: Value,
}

/// 已保存到统一规则表中的当前规则记录。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) struct StoredRule {
    /// 稳定规则 ID。
    pub(crate) rule_id: String,
    /// 规则所属业务 domain。
    pub(crate) domain: RuleDomain,
    /// 同一 domain 内的规则顺序。
    pub(crate) rule_order: i64,
    /// matcher 类型。
    pub(crate) matcher_kind: MatcherKind,
    /// matcher 文本值。
    pub(crate) matcher_value: String,
    /// domain 专用 payload。
    pub(crate) payload_json: Value,
    /// 是否启用。
    pub(crate) enabled: bool,
    /// 规则来源类型。
    pub(crate) source_kind: String,
    /// 规则内容 hash。
    pub(crate) rule_hash: String,
}

/// 为规范化规则输入生成稳定 ID。
pub(crate) fn stable_rule_id(input: &NormalizedRuleInput) -> String {
    let payload = serde_json::json!({
        "domain": input.domain,
        "rule_order": input.rule_order,
        "matcher_kind": input.matcher_kind,
        "matcher_value": input.matcher_value,
        "payload_json": input.payload_json,
    });
    let serialized = match serde_json::to_vec(&payload) {
        Ok(serialized) => serialized,
        Err(error) => {
            // payload 只由本模块固定字段和 serde_json::Value 组成，应始终可序列化。
            panic!("normalized rule id payload 应可序列化: {error}");
        }
    };
    let digest = Sha256::digest(serialized);
    format!("rule:{digest:x}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn normalized_rule_id_is_stable_for_same_rule() {
        let rule = NormalizedRuleInput {
            domain: RuleDomain::MvVirtualNamebox,
            rule_order: 0,
            matcher_kind: MatcherKind::Pcre2Pattern,
            matcher_value: "^(?<speaker>[^:]+):$".to_string(),
            payload_json: json!({"speaker_group": "speaker"}),
        };

        assert_eq!(stable_rule_id(&rule), stable_rule_id(&rule));
    }

    #[test]
    fn matcher_kind_serializes_as_current_contract_text() {
        assert_eq!(
            serde_json::to_value(MatcherKind::Pcre2Pattern).unwrap(),
            json!("pcre2_pattern")
        );
        assert_eq!(
            serde_json::to_value(MatcherKind::JsonPathTemplate).unwrap(),
            json!("json_path_template")
        );
        assert_eq!(
            serde_json::to_value(MatcherKind::AstSelector).unwrap(),
            json!("ast_selector")
        );
        assert_eq!(
            serde_json::to_value(MatcherKind::Literal).unwrap(),
            json!("literal")
        );
    }

    #[test]
    fn rule_runtime_versions_start_at_current_contract() {
        assert_eq!(RULE_RUNTIME_CONTRACT_VERSION, 1);
        assert_eq!(RULE_STORE_SCHEMA_VERSION, 1);
    }

    #[test]
    fn stored_rule_serializes_current_contract_fields() {
        let stored = StoredRule {
            rule_id: "rule:abc".to_string(),
            domain: RuleDomain::Placeholders,
            rule_order: 10,
            matcher_kind: MatcherKind::DomainPayload,
            matcher_value: "placeholder-shell".to_string(),
            payload_json: json!({"kind": "paired_shell"}),
            enabled: true,
            source_kind: "agent_import".to_string(),
            rule_hash: "hash:abc".to_string(),
        };

        assert_eq!(
            serde_json::to_value(stored).unwrap(),
            json!({
                "rule_id": "rule:abc",
                "domain": "placeholders",
                "rule_order": 10,
                "matcher_kind": "domain_payload",
                "matcher_value": "placeholder-shell",
                "payload_json": {"kind": "paired_shell"},
                "enabled": true,
                "source_kind": "agent_import",
                "rule_hash": "hash:abc",
            })
        );
    }
}
