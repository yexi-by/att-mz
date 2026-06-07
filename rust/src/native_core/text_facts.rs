//! Text Fact Contract v2 的 Rust 公共事实模型。

use serde::{Deserialize, Serialize};
use sha2::Digest;

/// Text Fact Contract 的当前事实 schema version。
pub(crate) const TEXT_FACT_SCHEMA_VERSION: i64 = 2;

/// Text Fact Contract v2 支持的文本域常量。
pub(crate) mod domains {
    /// 标准 data JSON 文本。
    pub(crate) const STANDARD_DATA: &str = "standard_data";
    /// MV 虚拟名字框文本。
    pub(crate) const MV_VIRTUAL_NAMEBOX: &str = "mv_virtual_namebox";
    /// 插件配置文本。
    pub(crate) const PLUGIN_CONFIG: &str = "plugin_config";
    /// 事件指令文本。
    pub(crate) const EVENT_COMMAND: &str = "event_command";
    /// Note 标签文本。
    pub(crate) const NOTE_TAG: &str = "note_tag";
    /// 非标准 data 文本。
    pub(crate) const NONSTANDARD_DATA: &str = "nonstandard_data";
    /// 插件源码文本。
    pub(crate) const PLUGIN_SOURCE: &str = "plugin_source";
    /// 普通 placeholder 候选文本。
    pub(crate) const PLACEHOLDER_CANDIDATE: &str = "placeholder_candidate";
    /// 结构化 placeholder 候选文本。
    pub(crate) const STRUCTURED_PLACEHOLDER_CANDIDATE: &str = "structured_placeholder_candidate";
    /// 运行时字面量事实。
    pub(crate) const ACTIVE_RUNTIME_LITERAL: &str = "active_runtime_literal";

    /// 当前 v2 契约允许写入的文本域集合。
    pub(crate) const SUPPORTED: [&str; 10] = [
        STANDARD_DATA,
        MV_VIRTUAL_NAMEBOX,
        PLUGIN_CONFIG,
        EVENT_COMMAND,
        NOTE_TAG,
        NONSTANDARD_DATA,
        PLUGIN_SOURCE,
        PLACEHOLDER_CANDIDATE,
        STRUCTURED_PLACEHOLDER_CANDIDATE,
        ACTIVE_RUNTIME_LITERAL,
    ];
}

/// 创建一条 v2 文本事实所需的无派生字段输入。
#[cfg(test)]
#[derive(Debug, Clone)]
pub(crate) struct TextFactInput {
    /// 文本域。
    pub(crate) domain: String,
    /// 游戏内部位置。
    pub(crate) location_path: String,
    /// 来源文件名。
    pub(crate) source_file: String,
    /// 来源类型。
    pub(crate) source_type: String,
    /// 文本项类型。
    pub(crate) item_type: String,
    /// 角色或 speaker；无角色时为空字符串。
    pub(crate) role: String,
    /// domain 内稳定 selector。
    pub(crate) selector: String,
    /// 原始协议文本。
    pub(crate) raw_text: String,
    /// 玩家可见文本。
    pub(crate) visible_text: String,
    /// 送模型翻译的正文。
    pub(crate) translatable_text: String,
}

/// Text Fact Contract v2 的单条文本事实。
#[derive(Debug, Clone, Deserialize, Serialize)]
pub(crate) struct TextFact {
    /// 稳定事实身份。
    pub(crate) fact_id: String,
    /// 事实 schema version。
    pub(crate) schema_version: i64,
    /// 文本域。
    pub(crate) domain: String,
    /// 游戏内部位置。
    pub(crate) location_path: String,
    /// 来源文件名。
    pub(crate) source_file: String,
    /// 来源类型。
    pub(crate) source_type: String,
    /// 文本项类型。
    pub(crate) item_type: String,
    /// 角色或 speaker；无角色时为空字符串。
    pub(crate) role: String,
    /// domain 内稳定 selector。
    pub(crate) selector: String,
    /// 原始协议文本。
    pub(crate) raw_text: String,
    /// 玩家可见文本。
    pub(crate) visible_text: String,
    /// 送模型翻译的正文。
    pub(crate) translatable_text: String,
    /// 基于 raw_text 的 SHA-256。
    pub(crate) raw_hash: String,
    /// 基于 visible_text 的 SHA-256。
    pub(crate) visible_hash: String,
    /// 基于 translatable_text 的 SHA-256。
    pub(crate) translatable_hash: String,
    /// 所属 v2 scope key。
    pub(crate) scope_key: String,
}

/// Text Fact Contract v2 的写回渲染片段。
#[derive(Debug, Clone, Deserialize, Serialize)]
pub(crate) struct TextFactRenderPart {
    /// 片段所属事实。
    pub(crate) fact_id: String,
    /// 片段顺序，从 0 开始。
    pub(crate) part_order: i64,
    /// 片段类型。
    pub(crate) part_kind: String,
    /// 片段原始文本。
    pub(crate) raw_text: String,
    /// 片段语义文本。
    pub(crate) semantic_text: String,
    /// 写回模板键。
    pub(crate) template_key: String,
}

/// Text Fact Contract v2 的 domain 小扩展 JSON。
#[derive(Debug, Clone, Deserialize, Serialize)]
pub(crate) struct TextFactDomainPayload {
    /// payload 所属事实。
    pub(crate) fact_id: String,
    /// JSON 对象文本。
    pub(crate) payload_json: String,
}

/// Text Fact Contract v2 的当前 scope 元数据。
#[derive(Debug, Clone, Deserialize, Serialize)]
pub(crate) struct TextFactScope {
    /// 稳定 scope key。
    pub(crate) scope_key: String,
    /// 事实 schema version。
    pub(crate) schema_version: i64,
    /// 绑定源快照、规则、文本规则和 schema version 的 hash。
    pub(crate) scope_hash: String,
    /// 源快照 hash。
    pub(crate) source_snapshot_hash: String,
    /// 规则 hash。
    pub(crate) rule_hash: String,
    /// 文本规则 hash。
    pub(crate) text_rules_hash: String,
    /// 创建时间。
    pub(crate) created_at: String,
}

impl TextFact {
    /// 从无派生字段输入创建完整 v2 文本事实。
    #[cfg(test)]
    pub(crate) fn from_input(input: TextFactInput, scope_key: String) -> Result<Self, String> {
        let raw_hash = sha256_text(&input.raw_text);
        let visible_hash = sha256_text(&input.visible_text);
        let translatable_hash = sha256_text(&input.translatable_text);
        let fact_id = build_fact_id(
            TEXT_FACT_SCHEMA_VERSION,
            &input.domain,
            &input.location_path,
            &input.selector,
            &raw_hash,
        );
        let fact = Self {
            fact_id,
            schema_version: TEXT_FACT_SCHEMA_VERSION,
            domain: input.domain,
            location_path: input.location_path,
            source_file: input.source_file,
            source_type: input.source_type,
            item_type: input.item_type,
            role: input.role,
            selector: input.selector,
            raw_text: input.raw_text,
            visible_text: input.visible_text,
            translatable_text: input.translatable_text,
            raw_hash,
            visible_hash,
            translatable_hash,
            scope_key,
        };
        fact.validate()?;
        Ok(fact)
    }

    /// 校验事实是否满足当前 v2 契约。
    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.schema_version != TEXT_FACT_SCHEMA_VERSION {
            return Err(format!(
                "text fact v2 schema_version 不受支持: {}，当前要求 {}",
                self.schema_version, TEXT_FACT_SCHEMA_VERSION
            ));
        }
        if !domains::SUPPORTED.contains(&self.domain.as_str()) {
            return Err(format!("text fact v2 domain 不受支持: {}", self.domain));
        }
        if self.fact_id.trim().is_empty() {
            return Err("text fact v2 fact_id 为空".to_string());
        }
        if self.scope_key.trim().is_empty() {
            return Err("text fact v2 scope_key 为空".to_string());
        }
        if self.location_path.trim().is_empty() {
            return Err("text fact v2 location_path 为空".to_string());
        }
        if self.source_file.trim().is_empty() {
            return Err("text fact v2 source_file 为空".to_string());
        }
        if self.domain == domains::MV_VIRTUAL_NAMEBOX && self.role.trim().is_empty() {
            return Err("MV 虚拟名字框 speaker 为空，无法写入 v2 文本事实".to_string());
        }
        validate_hash("raw_hash", &self.raw_hash, &self.raw_text)?;
        validate_hash("visible_hash", &self.visible_hash, &self.visible_text)?;
        validate_hash(
            "translatable_hash",
            &self.translatable_hash,
            &self.translatable_text,
        )?;
        let expected_fact_id = build_fact_id(
            self.schema_version,
            &self.domain,
            &self.location_path,
            &self.selector,
            &self.raw_hash,
        );
        if self.fact_id != expected_fact_id {
            return Err(format!(
                "text fact v2 fact_id 与 schema/domain/location/selector/raw_hash 不一致: {}",
                self.fact_id
            ));
        }
        Ok(())
    }
}

impl TextFactRenderPart {
    /// 创建一个写回渲染片段。
    #[cfg(test)]
    pub(crate) fn new(
        fact_id: String,
        part_order: i64,
        part_kind: &str,
        raw_text: &str,
        semantic_text: &str,
        template_key: &str,
    ) -> Self {
        Self {
            fact_id,
            part_order,
            part_kind: part_kind.to_string(),
            raw_text: raw_text.to_string(),
            semantic_text: semantic_text.to_string(),
            template_key: template_key.to_string(),
        }
    }

    /// 校验渲染片段基础字段。
    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.fact_id.trim().is_empty() {
            return Err("text fact v2 render part 缺少 fact_id".to_string());
        }
        if self.part_order < 0 {
            return Err(format!(
                "text fact v2 render part part_order 不能为负数: {}",
                self.part_order
            ));
        }
        if self.part_kind.trim().is_empty() {
            return Err("text fact v2 render part 缺少 part_kind".to_string());
        }
        if self.template_key.trim().is_empty() {
            return Err("text fact v2 render part 缺少 template_key".to_string());
        }
        Ok(())
    }
}

impl TextFactDomainPayload {
    /// 创建一个 domain payload。
    #[cfg(test)]
    pub(crate) fn new(fact_id: String, payload_json: String) -> Self {
        Self {
            fact_id,
            payload_json,
        }
    }

    /// 校验 payload 基础字段和 JSON 对象格式。
    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.fact_id.trim().is_empty() {
            return Err("text fact v2 domain payload 缺少 fact_id".to_string());
        }
        let value: serde_json::Value = serde_json::from_str(&self.payload_json)
            .map_err(|error| format!("text fact v2 domain payload_json 不是有效 JSON: {error}"))?;
        if !value.is_object() {
            return Err("text fact v2 domain payload_json 必须是 JSON 对象".to_string());
        }
        Ok(())
    }
}

impl TextFactScope {
    /// 根据三类 scope 输入 hash 创建当前 v2 scope。
    pub(crate) fn from_hashes(
        source_snapshot_hash: String,
        rule_hash: String,
        text_rules_hash: String,
        created_at: String,
    ) -> Self {
        let scope_hash = build_scope_hash(
            TEXT_FACT_SCHEMA_VERSION,
            &source_snapshot_hash,
            &rule_hash,
            &text_rules_hash,
        );
        Self {
            scope_key: build_scope_key(&source_snapshot_hash, &rule_hash, &text_rules_hash),
            schema_version: TEXT_FACT_SCHEMA_VERSION,
            scope_hash,
            source_snapshot_hash,
            rule_hash,
            text_rules_hash,
            created_at,
        }
    }

    /// 校验 scope 是否属于当前 v2 事实契约。
    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.schema_version != TEXT_FACT_SCHEMA_VERSION {
            return Err(format!(
                "text fact v2 schema_version 不受支持: {}，当前要求 {}",
                self.schema_version, TEXT_FACT_SCHEMA_VERSION
            ));
        }
        if self.source_snapshot_hash.trim().is_empty() {
            return Err("text fact v2 scope 缺少 source_snapshot_hash".to_string());
        }
        if self.rule_hash.trim().is_empty() {
            return Err("text fact v2 scope 缺少 rule_hash".to_string());
        }
        if self.text_rules_hash.trim().is_empty() {
            return Err("text fact v2 scope 缺少 text_rules_hash".to_string());
        }
        if self.created_at.trim().is_empty() {
            return Err("text fact v2 scope 缺少 created_at".to_string());
        }
        let expected_scope_hash = build_scope_hash(
            self.schema_version,
            &self.source_snapshot_hash,
            &self.rule_hash,
            &self.text_rules_hash,
        );
        if self.scope_hash != expected_scope_hash {
            return Err(format!(
                "text fact v2 scope_hash 与 source/rule/text_rules/schema 不一致: {}",
                self.scope_hash
            ));
        }
        let expected_scope_key = build_scope_key(
            &self.source_snapshot_hash,
            &self.rule_hash,
            &self.text_rules_hash,
        );
        if self.scope_key != expected_scope_key {
            return Err(format!(
                "text fact v2 scope_key 与 source/rule/text_rules/schema 不一致: {}",
                self.scope_key
            ));
        }
        Ok(())
    }
}

/// 计算 UTF-8 文本的稳定 SHA-256 十六进制摘要。
pub(crate) fn sha256_text(text: &str) -> String {
    let mut hasher = sha2::Sha256::new();
    hasher.update(text.as_bytes());
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// 构建稳定 fact_id。
pub(crate) fn build_fact_id(
    schema_version: i64,
    domain: &str,
    location_path: &str,
    selector: &str,
    raw_hash: &str,
) -> String {
    let identity = stable_identity(&[
        ("schema_version", schema_version.to_string()),
        ("domain", domain.to_string()),
        ("location_path", location_path.to_string()),
        ("selector", selector.to_string()),
        ("raw_hash", raw_hash.to_string()),
    ]);
    let raw_prefix = raw_hash.chars().take(12).collect::<String>();
    format!("tfv2:{raw_prefix}:{}", sha256_text(&identity))
}

/// 构建稳定 scope_key。
pub(crate) fn build_scope_key(
    source_snapshot_hash: &str,
    rule_hash: &str,
    text_rules_hash: &str,
) -> String {
    let scope_hash = build_scope_hash(
        TEXT_FACT_SCHEMA_VERSION,
        source_snapshot_hash,
        rule_hash,
        text_rules_hash,
    );
    format!("tfv2-scope:{scope_hash}")
}

/// 构建稳定 scope_hash。
pub(crate) fn build_scope_hash(
    schema_version: i64,
    source_snapshot_hash: &str,
    rule_hash: &str,
    text_rules_hash: &str,
) -> String {
    sha256_text(&stable_identity(&[
        ("schema_version", schema_version.to_string()),
        ("source_snapshot_hash", source_snapshot_hash.to_string()),
        ("rule_hash", rule_hash.to_string()),
        ("text_rules_hash", text_rules_hash.to_string()),
    ]))
}

fn validate_hash(field_name: &str, actual: &str, source_text: &str) -> Result<(), String> {
    let expected = sha256_text(source_text);
    if actual != expected {
        return Err(format!(
            "text fact v2 {field_name} 与约定输入不一致: expected={expected}, actual={actual}"
        ));
    }
    Ok(())
}

fn stable_identity(fields: &[(&str, String)]) -> String {
    let mut text = String::new();
    for (key, value) in fields {
        text.push_str(&key.len().to_string());
        text.push(':');
        text.push_str(key);
        text.push('=');
        text.push_str(&value.len().to_string());
        text.push(':');
        text.push_str(value);
        text.push('\n');
    }
    text
}

#[cfg(test)]
mod tests {
    use super::{
        TEXT_FACT_SCHEMA_VERSION, TextFact, TextFactInput, TextFactRenderPart, TextFactScope,
        build_scope_key, domains, sha256_text,
    };

    #[test]
    fn text_fact_hashes_use_raw_visible_and_translatable_inputs() {
        let scope_key = build_scope_key("source-v1", "rules-v1", "text-rules-v1");
        let fact = TextFact::from_input(
            TextFactInput {
                domain: domains::STANDARD_DATA.to_string(),
                location_path: "System.json/gameTitle".to_string(),
                source_file: "System.json".to_string(),
                source_type: "standard_data".to_string(),
                item_type: "short_text".to_string(),
                role: String::new(),
                selector: "gameTitle".to_string(),
                raw_text: "  原文  ".to_string(),
                visible_text: "原文".to_string(),
                translatable_text: "正文".to_string(),
            },
            scope_key,
        )
        .expect("有效文本事实应可创建");

        assert_eq!(fact.schema_version, TEXT_FACT_SCHEMA_VERSION);
        assert_eq!(fact.raw_hash, sha256_text("  原文  "));
        assert_eq!(fact.visible_hash, sha256_text("原文"));
        assert_eq!(fact.translatable_hash, sha256_text("正文"));
        assert!(fact.fact_id.contains(&fact.raw_hash[..12]));
    }

    #[test]
    fn text_fact_rejects_empty_mv_virtual_namebox_speaker() {
        let scope_key = build_scope_key("source-v1", "rules-v1", "text-rules-v1");
        let error = TextFact::from_input(
            TextFactInput {
                domain: domains::MV_VIRTUAL_NAMEBOX.to_string(),
                location_path: "Map001.json/events/1/pages/0/list/0".to_string(),
                source_file: "Map001.json".to_string(),
                source_type: "event_command".to_string(),
                item_type: "long_text".to_string(),
                role: " \t ".to_string(),
                selector: "event:1/page:0/list:0".to_string(),
                raw_text: "\\n< :> Hello".to_string(),
                visible_text: "\\n< :> Hello".to_string(),
                translatable_text: "Hello".to_string(),
            },
            scope_key,
        )
        .expect_err("MV 虚拟名字框 speaker 为空必须拒绝");

        assert!(error.contains("MV 虚拟名字框 speaker 为空"));
    }

    #[test]
    fn scope_key_and_scope_hash_include_schema_and_input_hashes() {
        let scope = TextFactScope::from_hashes(
            "source-v1".to_string(),
            "rules-v1".to_string(),
            "text-rules-v1".to_string(),
            "2026-06-05T00:00:00".to_string(),
        );

        assert_eq!(scope.schema_version, TEXT_FACT_SCHEMA_VERSION);
        assert_eq!(
            scope.scope_key,
            build_scope_key("source-v1", "rules-v1", "text-rules-v1")
        );
        assert_eq!(scope.source_snapshot_hash, "source-v1");
        assert_eq!(scope.rule_hash, "rules-v1");
        assert_eq!(scope.text_rules_hash, "text-rules-v1");
        assert_eq!(scope.scope_hash.len(), 64);
    }

    #[test]
    fn render_parts_reconstruct_mv_virtual_namebox_raw_text() {
        let parts = [
            TextFactRenderPart::new(
                "fact-v1".to_string(),
                0,
                "literal",
                "\\n<",
                "\\n<",
                "prefix",
            ),
            TextFactRenderPart::new("fact-v1".to_string(), 1, "speaker", "Dan", "Dan", "speaker"),
            TextFactRenderPart::new(
                "fact-v1".to_string(),
                2,
                "literal",
                ":> ",
                ":> ",
                "separator",
            ),
            TextFactRenderPart::new(
                "fact-v1".to_string(),
                3,
                "translated_body",
                "Hello",
                "Hello",
                "body",
            ),
        ];

        let reconstructed = parts
            .iter()
            .map(|part| part.raw_text.as_str())
            .collect::<String>();
        assert_eq!(reconstructed, "\\n<Dan:> Hello");
    }
}
