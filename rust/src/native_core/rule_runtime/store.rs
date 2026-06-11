#![allow(dead_code)]

use rusqlite::{Connection, params};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::model::{
    RULE_RUNTIME_CONTRACT_VERSION, RULE_STORE_SCHEMA_VERSION, RuleDomain, StoredRule,
};

/// 安装当前统一规则存储 schema。
pub(crate) fn install_rule_store_schema(connection: &Connection) -> Result<(), String> {
    connection
        .execute_batch(include_str!(
            "../../../../app/persistence/schema/current.sql"
        ))
        .map_err(|error| format!("统一规则表 schema 初始化失败: {error}"))
}

/// 用一组新规则替换指定 domain 的当前规则。
pub(crate) fn replace_domain_rules(
    connection: &Connection,
    domain: RuleDomain,
    rules: &[StoredRule],
) -> Result<(), String> {
    let transaction = connection
        .unchecked_transaction()
        .map_err(|error| format!("统一规则表事务创建失败: {error}"))?;
    let domain_text = contract_text(domain, "domain")?;
    transaction
        .execute("DELETE FROM rules WHERE domain = ?1", params![&domain_text])
        .map_err(|error| format!("清理当前 domain 规则失败: {error}"))?;

    for rule in rules {
        let rule_domain = contract_text(rule.domain, "domain")?;
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

    transaction
        .commit()
        .map_err(|error| format!("提交统一规则事务失败: {error}"))
}

/// 按 domain 读取当前统一规则。
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

/// 替换指定 domain 的当前状态。
pub(crate) fn replace_domain_state(
    connection: &Connection,
    domain: RuleDomain,
    state_json: &Value,
    scope_hash: &str,
    confirmed_at: &str,
) -> Result<(), String> {
    let domain_text = contract_text(domain, "domain")?;
    connection
        .execute(
            "INSERT OR REPLACE INTO rule_domain_states(domain, state_json, scope_hash, confirmed_at, rule_runtime_contract_version, rule_store_schema_version)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                &domain_text,
                state_json.to_string(),
                scope_hash,
                confirmed_at,
                RULE_RUNTIME_CONTRACT_VERSION,
                RULE_STORE_SCHEMA_VERSION,
            ],
        )
        .map_err(|error| format!("写入规则 domain 状态失败: {error}"))?;
    Ok(())
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
    fn replace_domain_rules_replaces_only_current_domain() {
        let connection = Connection::open_in_memory().expect("in-memory DB should open");
        install_rule_store_schema(&connection).expect("schema should install");

        replace_domain_rules(
            &connection,
            RuleDomain::Placeholders,
            &[fixture_rule(RuleDomain::Placeholders, 0)],
        )
        .expect("placeholder rules should save");
        replace_domain_rules(
            &connection,
            RuleDomain::MvVirtualNamebox,
            &[fixture_rule(RuleDomain::MvVirtualNamebox, 0)],
        )
        .expect("mv rules should save");
        replace_domain_rules(
            &connection,
            RuleDomain::Placeholders,
            &[fixture_rule(RuleDomain::Placeholders, 1)],
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
        replace_domain_state(
            &connection,
            RuleDomain::MvVirtualNamebox,
            &json!({"confirmed_empty": true}),
            "scope-hash",
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
}
