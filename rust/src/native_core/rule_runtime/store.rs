use rusqlite::{Connection, params};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::model::{
    RULE_RUNTIME_CONTRACT_VERSION, RULE_STORE_SCHEMA_VERSION, RuleDomain, StoredRule,
};

/// 某个规则 domain 的确认状态草稿。
#[derive(Debug, Clone)]
pub(crate) struct DomainStateDraft {
    /// 要写入 rule_domain_states.state_json 的当前状态。
    pub(crate) state_json: Value,
    /// 当前确认所覆盖的游戏文本/候选范围 hash。
    pub(crate) scope_hash: String,
}

/// Rust rule_runtime 提交统一规则导入计划时使用的存储草稿。
#[derive(Debug, Clone)]
pub(crate) struct RuleImportStorePlan {
    /// 本次导入所属 domain。
    pub(crate) domain: RuleDomain,
    /// 本次导入后的完整当前规则集合。
    pub(crate) rules: Vec<StoredRule>,
    /// 当前 domain 状态；None 表示清除旧的空规则确认状态。
    pub(crate) domain_state: Option<DomainStateDraft>,
    /// 本次导入对应的上下文 hash。
    pub(crate) context_hash: String,
    /// 已经备份并应在同一事务内删除的译文 fact_id。
    pub(crate) cleanup_fact_ids: Vec<String>,
}

/// Rust rule_runtime 统一规则提交结果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RuleImportStoreOutcome {
    /// 实际删除的已保存译文数量。
    pub(crate) deleted_translation_count: usize,
}

/// 安装当前统一规则存储 schema。
#[cfg(test)]
pub(crate) fn install_rule_store_schema(connection: &Connection) -> Result<(), String> {
    connection
        .execute_batch(include_str!(
            "../../../../app/persistence/schema/current.sql"
        ))
        .map_err(|error| format!("统一规则表 schema 初始化失败: {error}"))
}

/// 在一个 SQLite 事务内提交完整规则导入计划。
pub(crate) fn commit_rule_import_store(
    connection: &Connection,
    plan: &RuleImportStorePlan,
    imported_at: &str,
) -> Result<RuleImportStoreOutcome, String> {
    let transaction = connection
        .unchecked_transaction()
        .map_err(|error| format!("统一规则导入事务创建失败: {error}"))?;
    let domain_text = contract_text(plan.domain, "domain")?;
    transaction
        .execute("DELETE FROM rules WHERE domain = ?1", params![&domain_text])
        .map_err(|error| format!("清理当前 domain 规则失败: {error}"))?;

    for rule in &plan.rules {
        let rule_domain = contract_text(rule.domain, "domain")?;
        if rule_domain != domain_text {
            return Err(format!(
                "统一规则导入计划包含其他 domain 规则: 当前 {domain_text}，实际 {rule_domain}"
            ));
        }
        let matcher_kind = contract_text(rule.matcher_kind, "matcher_kind")?;
        transaction
            .execute(
                "INSERT INTO rules(rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
                params![
                    &rule.rule_id,
                    &rule_domain,
                    rule.rule_order,
                    &matcher_kind,
                    &rule.matcher_value,
                    rule.payload_json.to_string(),
                    if rule.enabled { 1 } else { 0 },
                    &rule.source_kind,
                    &rule.rule_hash,
                ],
            )
            .map_err(|error| format!("写入统一规则失败: {error}"))?;
    }

    let rules_hash = rules_hash_for_domain(plan.domain, &plan.rules)?;
    transaction
        .execute(
            "INSERT OR REPLACE INTO rule_sets(domain, source_kind, rule_count, context_hash, rules_hash, rule_runtime_contract_version, rule_store_schema_version, imported_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                &domain_text,
                "external_import",
                plan.rules.len() as i64,
                &plan.context_hash,
                &rules_hash,
                RULE_RUNTIME_CONTRACT_VERSION,
                RULE_STORE_SCHEMA_VERSION,
                imported_at,
            ],
        )
        .map_err(|error| format!("写入规则集合状态失败: {error}"))?;

    if let Some(state) = &plan.domain_state {
        transaction
            .execute(
                "INSERT OR REPLACE INTO rule_domain_states(domain, state_json, scope_hash, confirmed_at, rule_runtime_contract_version, rule_store_schema_version)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    &domain_text,
                    state.state_json.to_string(),
                    &state.scope_hash,
                    imported_at,
                    RULE_RUNTIME_CONTRACT_VERSION,
                    RULE_STORE_SCHEMA_VERSION,
                ],
            )
            .map_err(|error| format!("写入规则 domain 状态失败: {error}"))?;
    } else {
        transaction
            .execute(
                "DELETE FROM rule_domain_states WHERE domain = ?1",
                params![&domain_text],
            )
            .map_err(|error| format!("清理规则 domain 状态失败: {error}"))?;
    }

    if plan.domain == RuleDomain::PluginSource {
        transaction
            .execute("DELETE FROM plugin_source_runtime_write_map", [])
            .map_err(|error| format!("清理插件源码写回映射缓存失败: {error}"))?;
    }

    let mut deleted_translation_count = 0usize;
    for fact_id in &plan.cleanup_fact_ids {
        let changed = transaction
            .execute(
                "DELETE FROM translation_items WHERE fact_id = ?1",
                params![fact_id],
            )
            .map_err(|error| format!("清理失效译文失败: {error}"))?;
        deleted_translation_count += changed;
    }

    transaction
        .commit()
        .map_err(|error| format!("提交统一规则导入事务失败: {error}"))?;
    Ok(RuleImportStoreOutcome {
        deleted_translation_count,
    })
}

/// 按 domain 读取当前统一规则。
#[cfg(test)]
pub(crate) fn read_rules_by_domain(
    connection: &Connection,
    domain: RuleDomain,
) -> Result<Vec<StoredRule>, String> {
    let domain_text = contract_text(domain, "domain")?;
    let mut statement = connection
        .prepare(
            "SELECT rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash
             FROM rules
             WHERE domain = ?1
             ORDER BY rule_order, rule_id",
        )
        .map_err(|error| format!("读取统一规则查询准备失败: {error}"))?;
    let rows = statement
        .query_map(params![&domain_text], |row| {
            Ok(StoredRuleRow {
                rule_id: row.get(0)?,
                domain: row.get(1)?,
                rule_order: row.get(2)?,
                matcher_kind: row.get(3)?,
                matcher_value: row.get(4)?,
                payload_json: row.get(5)?,
                enabled: row.get(6)?,
                source_kind: row.get(7)?,
                rule_hash: row.get(8)?,
            })
        })
        .map_err(|error| format!("读取统一规则失败: {error}"))?;

    let mut rules = Vec::new();
    for row in rows {
        rules.push(row_to_stored_rule(
            row.map_err(|error| format!("读取统一规则行失败: {error}"))?,
        )?);
    }
    Ok(rules)
}

/// 构建当前统一规则和 domain 状态的稳定指纹。
pub(crate) fn build_rules_fingerprint(
    connection: &Connection,
    config_patterns_hash: &str,
) -> Result<String, String> {
    let payload = serde_json::json!({
        "rules": read_all_rules_sorted(connection)?,
        "domain_states": read_all_domain_states_sorted(connection)?,
        "config_patterns_hash": config_patterns_hash,
        "rule_runtime_contract_version": RULE_RUNTIME_CONTRACT_VERSION,
        "rule_store_schema_version": RULE_STORE_SCHEMA_VERSION,
    });
    let bytes =
        serde_json::to_vec(&payload).map_err(|error| format!("规则指纹 JSON 编码失败: {error}"))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn read_all_rules_sorted(connection: &Connection) -> Result<Vec<StoredRule>, String> {
    let mut statement = connection
        .prepare(
            "SELECT rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash
             FROM rules
             ORDER BY domain, rule_order, rule_id",
        )
        .map_err(|error| format!("读取统一规则指纹输入失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            Ok(StoredRuleRow {
                rule_id: row.get(0)?,
                domain: row.get(1)?,
                rule_order: row.get(2)?,
                matcher_kind: row.get(3)?,
                matcher_value: row.get(4)?,
                payload_json: row.get(5)?,
                enabled: row.get(6)?,
                source_kind: row.get(7)?,
                rule_hash: row.get(8)?,
            })
        })
        .map_err(|error| format!("读取统一规则指纹输入失败: {error}"))?;
    let mut rules = Vec::new();
    for row in rows {
        rules.push(row_to_stored_rule(
            row.map_err(|error| format!("读取统一规则指纹行失败: {error}"))?,
        )?);
    }
    Ok(rules)
}

fn read_all_domain_states_sorted(connection: &Connection) -> Result<Vec<Value>, String> {
    let mut statement = connection
        .prepare(
            "SELECT domain, state_json, scope_hash, confirmed_at, rule_runtime_contract_version, rule_store_schema_version
             FROM rule_domain_states
             ORDER BY domain",
        )
        .map_err(|error| format!("读取规则 domain 状态指纹输入失败: {error}"))?;
    let rows = statement
        .query_map([], |row| {
            Ok(DomainStateRow {
                domain: row.get(0)?,
                state_json: row.get(1)?,
                scope_hash: row.get(2)?,
                confirmed_at: row.get(3)?,
                rule_runtime_contract_version: row.get(4)?,
                rule_store_schema_version: row.get(5)?,
            })
        })
        .map_err(|error| format!("读取规则 domain 状态失败: {error}"))?;
    let mut states = Vec::new();
    for row in rows {
        let row = row.map_err(|error| format!("读取规则 domain 状态行失败: {error}"))?;
        states.push(serde_json::json!({
            "domain": row.domain,
            "state_json": serde_json::from_str::<Value>(&row.state_json)
                .map_err(|error| format!("规则 domain 状态 JSON 无效: {error}"))?,
            "scope_hash": row.scope_hash,
            "confirmed_at": row.confirmed_at,
            "rule_runtime_contract_version": row.rule_runtime_contract_version,
            "rule_store_schema_version": row.rule_store_schema_version,
        }));
    }
    Ok(states)
}

fn rules_hash_for_domain(domain: RuleDomain, rules: &[StoredRule]) -> Result<String, String> {
    let payload = serde_json::json!({
        "domain": domain,
        "rules": rules.iter().map(|rule| serde_json::json!({
            "rule_order": rule.rule_order,
            "matcher_kind": rule.matcher_kind,
            "matcher_value": rule.matcher_value,
            "payload_json": rule.payload_json,
        })).collect::<Vec<_>>(),
    });
    let bytes = serde_json::to_vec(&payload)
        .map_err(|error| format!("统一规则 rules_hash JSON 编码失败: {error}"))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

#[derive(Debug)]
struct DomainStateRow {
    domain: String,
    state_json: String,
    scope_hash: String,
    confirmed_at: String,
    rule_runtime_contract_version: i64,
    rule_store_schema_version: i64,
}

#[derive(Debug)]
struct StoredRuleRow {
    rule_id: String,
    domain: String,
    rule_order: i64,
    matcher_kind: String,
    matcher_value: String,
    payload_json: String,
    enabled: i64,
    source_kind: String,
    rule_hash: String,
}

fn row_to_stored_rule(row: StoredRuleRow) -> Result<StoredRule, String> {
    Ok(StoredRule {
        rule_id: row.rule_id,
        domain: contract_enum(&row.domain, "domain")?,
        rule_order: row.rule_order,
        matcher_kind: contract_enum(&row.matcher_kind, "matcher_kind")?,
        matcher_value: row.matcher_value,
        payload_json: serde_json::from_str(&row.payload_json)
            .map_err(|error| format!("统一规则 payload_json 不是有效 JSON: {error}"))?,
        enabled: match row.enabled {
            0 => false,
            1 => true,
            other => return Err(format!("统一规则 enabled 只能是 0 或 1，实际是 {other}")),
        },
        source_kind: row.source_kind,
        rule_hash: row.rule_hash,
    })
}

fn contract_text<T>(value: T, field: &str) -> Result<String, String>
where
    T: Serialize,
{
    let value = serde_json::to_value(value)
        .map_err(|error| format!("统一规则 {field} 序列化失败: {error}"))?;
    value
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| format!("统一规则 {field} 必须序列化为文本"))
}

fn contract_enum<T>(text: &str, field: &str) -> Result<T, String>
where
    T: DeserializeOwned,
{
    serde_json::from_value(Value::String(text.to_string()))
        .map_err(|error| format!("统一规则 {field} 文本无效: {error}"))
}

#[cfg(test)]
mod tests {
    use super::super::model::MatcherKind;
    use super::*;
    use rusqlite::Connection;
    use serde_json::json;

    #[test]
    fn commit_rule_import_store_replaces_only_current_domain() {
        let connection = Connection::open_in_memory().expect("in-memory DB should open");
        install_rule_store_schema(&connection).expect("schema should install");

        commit_rule_import_store(
            &connection,
            &fixture_plan(
                RuleDomain::Placeholders,
                vec![fixture_rule(RuleDomain::Placeholders, 0)],
            ),
            "2026-06-11T00:00:00",
        )
        .expect("placeholder rules should save");
        commit_rule_import_store(
            &connection,
            &fixture_plan(
                RuleDomain::MvVirtualNamebox,
                vec![fixture_rule(RuleDomain::MvVirtualNamebox, 0)],
            ),
            "2026-06-11T00:00:01",
        )
        .expect("mv rules should save");
        commit_rule_import_store(
            &connection,
            &fixture_plan(
                RuleDomain::Placeholders,
                vec![fixture_rule(RuleDomain::Placeholders, 1)],
            ),
            "2026-06-11T00:00:02",
        )
        .expect("placeholder replacement should save");

        assert_eq!(
            read_rules_by_domain(&connection, RuleDomain::Placeholders)
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            read_rules_by_domain(&connection, RuleDomain::MvVirtualNamebox)
                .unwrap()
                .len(),
            1
        );
    }

    #[test]
    fn domain_state_updates_fingerprint_without_creating_rules() {
        let connection = Connection::open_in_memory().expect("in-memory DB should open");
        install_rule_store_schema(&connection).expect("schema should install");

        let before = build_rules_fingerprint(&connection, "config-hash")
            .expect("initial fingerprint should build");
        commit_rule_import_store(
            &connection,
            &RuleImportStorePlan {
                domain: RuleDomain::MvVirtualNamebox,
                rules: Vec::new(),
                domain_state: Some(DomainStateDraft {
                    state_json: json!({"confirmed_empty": true}),
                    scope_hash: "scope-hash".to_string(),
                }),
                context_hash: "scope-hash".to_string(),
                cleanup_fact_ids: Vec::new(),
            },
            "2026-06-11T00:00:00Z",
        )
        .expect("domain state should save");
        let after = build_rules_fingerprint(&connection, "config-hash")
            .expect("updated fingerprint should build");

        assert_ne!(before, after);
        assert_eq!(
            read_rules_by_domain(&connection, RuleDomain::MvVirtualNamebox)
                .unwrap()
                .len(),
            0
        );
    }

    fn fixture_rule(domain: RuleDomain, order: i64) -> StoredRule {
        StoredRule {
            rule_id: format!("rule:{domain:?}:{order}"),
            domain,
            rule_order: order,
            matcher_kind: MatcherKind::DomainPayload,
            matcher_value: String::new(),
            payload_json: json!({}),
            enabled: true,
            source_kind: "external_import".to_string(),
            rule_hash: format!("hash-{order}"),
        }
    }

    fn fixture_plan(domain: RuleDomain, rules: Vec<StoredRule>) -> RuleImportStorePlan {
        RuleImportStorePlan {
            domain,
            rules,
            domain_state: None,
            context_hash: "context-hash".to_string(),
            cleanup_fact_ids: Vec::new(),
        }
    }
}
