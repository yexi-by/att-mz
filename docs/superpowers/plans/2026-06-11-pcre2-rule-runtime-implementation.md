# PCRE2 统一规则运行时 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立独立 Rust `rule_runtime`，把所有用户/Agent 可写规则收束到统一运行时、统一 SQLite 规则模型和当前 PCRE2 正则契约。

**Architecture:** 先建立 PCRE2 engine、统一 rule model、错误结构和 rule store，再通过独立 native API 接入 Python validate/import dry-run 与 commit 流程。随后逐个迁移配置正则、占位符、源文残留、MV 名字框和非正则 matcher domain，最后删除旧规则表、旧 Python 正则语义、旧 regex contract 和旧测试。

**Tech Stack:** Rust 2024, PCRE2, PyO3, serde, rusqlite, rayon, Python 3.14, pydantic v2, uv, pytest, basedpyright, SQLite.

---

## Source Spec

执行前必须阅读：

- `docs/superpowers/specs/2026-06-11-pcre2-rule-runtime-design.md`
- `docs/superpowers/specs/2026-06-10-pcre2-rule-runtime-requirements.md`
- `AGENTS.md`
- `rust/Cargo.toml`
- `app/persistence/schema/current.sql`
- `app/native_scope_index.py`
- `app/rmmz/text_rules.py`
- `app/rmmz/control_codes.py`
- `app/source_residual/rules.py`
- `app/rmmz/mv_namebox.py`
- `app/regex_contract.py`
- `rust/src/native_core/regex_contract.rs`

## Scope Check

本计划覆盖一个大型但一致的子系统：规则生命周期。范围包含 PCRE2 正则、非正则 matcher、统一规则存储、Rust/Python API、domain adapter、旧路径删除、文档 Skill 和最终验证。执行时可以分批提交，但最终验收前不能留下旧规则运行事实源。

## Global Guardrails

- 不新增 Python 正则语义、capture 解释、模板语义或命中扫描。
- 不保留旧 domain 规则表作为运行事实源。
- 不让 `validate-*` 和 `import-*` 走两套校验逻辑。
- 不把 JSONPath、AST selector、literal match 强行改成 PCRE2。
- 不做旧库自动迁移或旧规则格式识别。
- 不为旧 JSON 报告字段做兼容。
- 不把 `scan_rule_candidates` 继续扩成规则运行时。
- 每个任务结束前运行本任务指定的针对性测试。
- 全量 `uv run pytest` 只在最终收尾任务运行。

## Target File Structure

### Rust Rule Runtime

- Create: `rust/src/native_core/rule_runtime/mod.rs`
- Create: `rust/src/native_core/rule_runtime/engine.rs`
- Create: `rust/src/native_core/rule_runtime/model.rs`
- Create: `rust/src/native_core/rule_runtime/errors.rs`
- Create: `rust/src/native_core/rule_runtime/store.rs`
- Create: `rust/src/native_core/rule_runtime/api.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/mod.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/config_patterns.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/placeholders.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/structured_placeholders.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/source_residual.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/mv_virtual_namebox.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/plugin_config.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/event_commands.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/note_tags.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/nonstandard_data.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/plugin_source.rs`
- Modify: `rust/Cargo.toml`
- Modify: `rust/src/native_core.rs`
- Modify: `rust/src/lib.rs`

### SQLite And Python Adapters

- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Create: `app/native_rule_runtime.py`
- Modify: `app/cli/commands/rules.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/application/flow_gate.py`
- Modify: `app/native_scope_index.py`
- Modify: `app/native_quality.py`
- Modify: `app/native_write_plan.py`

### Old Paths To Delete Or Shrink

- Delete final: `app/regex_contract.py`
- Delete final: `rust/src/native_core/regex_contract.rs`
- Modify final: `app/rmmz/text_rules.py`
- Modify final: `app/rmmz/control_codes.py`
- Modify final: `app/source_residual/rules.py`
- Modify final: `app/rmmz/mv_namebox.py`
- Modify final: `app/persistence/rule_records.py`

### Tests And Docs

- Create: `tests/test_native_rule_runtime.py`
- Create: `tests/test_rule_runtime_store.py`
- Modify: `tests/test_regex_contract.py`
- Modify: `tests/test_text_rules.py`
- Modify: `tests/test_agent_toolkit_rule_import.py`
- Modify: `tests/test_agent_toolkit_manual_import.py`
- Modify: `tests/test_agent_toolkit_workspace.py`
- Modify: `tests/test_agent_toolkit_quality_report.py`
- Modify: `tests/test_rmmz_mv_namebox.py`
- Modify: `tests/test_event_command_text.py`
- Modify: `tests/test_plugin_text.py`
- Modify: `tests/test_persistence.py`
- Modify: `tests/test_scan_budget.py`
- Modify: `setting.example.toml`
- Modify: `skills/att-mz-protocol/references/*.md`
- Modify: `skills/att-mz-protocol/workflow.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/records/performance/pcre2-rule-runtime-cli-timings.md`

## Task 1: PCRE2 Engine Wrapper

**Files:**
- Modify: `rust/Cargo.toml`
- Create: `rust/src/native_core/rule_runtime/mod.rs`
- Create: `rust/src/native_core/rule_runtime/engine.rs`
- Modify: `rust/src/native_core.rs`
- Test: `rust/src/native_core/rule_runtime/engine.rs`

- [ ] **Step 1: Add failing PCRE2 engine tests**

Create `rust/src/native_core/rule_runtime/engine.rs` with only tests and minimal type names:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pcre2_engine_extracts_named_capture_with_current_syntax() {
        let config = Pcre2EngineConfig::for_test();
        let pattern = Pcre2Engine::compile("^(?<speaker>[^:]+):(?<body>.*)$", &config)
            .expect("PCRE2 pattern should compile");

        let matched = pattern
            .captures("Alice:hello")
            .expect("matching should not fail")
            .expect("pattern should match");

        assert_eq!(matched.named("speaker"), Some("Alice"));
        assert_eq!(matched.named("body"), Some("hello"));
    }

    #[test]
    fn pcre2_engine_accepts_inline_flags() {
        let config = Pcre2EngineConfig::for_test();
        let pattern = Pcre2Engine::compile("(?i)^abc$", &config)
            .expect("inline ignore-case flag should compile");

        assert!(pattern.is_match("ABC").expect("matching should not fail"));
    }

    #[test]
    fn pcre2_engine_reports_invalid_pattern_with_field_context() {
        let config = Pcre2EngineConfig::for_test();
        let error = Pcre2Engine::compile("(?<speaker>", &config)
            .expect_err("invalid PCRE2 should fail");

        assert_eq!(error.code, "pcre2_compile_error");
        assert!(error.message.contains("pattern 不是有效的 PCRE2 正则"));
    }
}
```

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml rule_runtime::engine -- --nocapture
```

Expected: FAIL because `rule_runtime` and PCRE2 dependency do not exist.

- [ ] **Step 2: Add PCRE2 dependency**

Modify `rust/Cargo.toml`:

```toml
pcre2 = "0.2.11"
```

Keep `regex = "1.12"` for internal fixed regex. Do not remove `fancy-regex` in this task because migrated callers still use it.

- [ ] **Step 3: Implement engine wrapper**

Add to `rust/src/native_core/rule_runtime/mod.rs`:

```rust
pub(crate) mod engine;
```

Add to `rust/src/native_core.rs`:

```rust
mod rule_runtime;
```

Implement `engine.rs`:

```rust
use pcre2::bytes::{Regex, RegexBuilder};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Pcre2EngineConfig {
    pub(crate) jit: bool,
}

impl Pcre2EngineConfig {
    pub(crate) fn default_runtime() -> Self {
        Self { jit: true }
    }

    #[cfg(test)]
    pub(crate) fn for_test() -> Self {
        Self { jit: true }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RuleRuntimeError {
    pub(crate) code: String,
    pub(crate) message: String,
    pub(crate) details: BTreeMap<String, String>,
}

pub(crate) struct Pcre2Engine;

pub(crate) struct CompiledPcre2Pattern {
    regex: Regex,
}

pub(crate) struct Pcre2Match {
    named: BTreeMap<String, String>,
}

impl Pcre2Engine {
    pub(crate) fn compile(pattern: &str, config: &Pcre2EngineConfig) -> Result<CompiledPcre2Pattern, RuleRuntimeError> {
        let mut builder = RegexBuilder::new();
        builder.utf(true).ucp(true);
        if config.jit {
            builder.jit_if_available(true);
        }
        let regex = builder.build(pattern).map_err(|error| RuleRuntimeError {
            code: "pcre2_compile_error".to_string(),
            message: format!("pattern 不是有效的 PCRE2 正则：{error}"),
            details: BTreeMap::from([("pattern".to_string(), pattern.to_string())]),
        })?;
        Ok(CompiledPcre2Pattern { regex })
    }
}

impl CompiledPcre2Pattern {
    pub(crate) fn is_match(&self, text: &str) -> Result<bool, RuleRuntimeError> {
        self.regex.is_match(text.as_bytes()).map_err(match_error)
    }

    pub(crate) fn captures(&self, text: &str) -> Result<Option<Pcre2Match>, RuleRuntimeError> {
        let Some(captures) = self.regex.captures(text.as_bytes()).map_err(match_error)? else {
            return Ok(None);
        };
        let mut named = BTreeMap::new();
        for maybe_name in self.regex.capture_names().flatten() {
            if let Some(matched) = captures.name(maybe_name) {
                let value = std::str::from_utf8(matched.as_bytes()).map_err(|error| RuleRuntimeError {
                    code: "pcre2_utf8_capture_error".to_string(),
                    message: format!("PCRE2 capture 不是有效 UTF-8：{error}"),
                    details: BTreeMap::from([("capture".to_string(), maybe_name.to_string())]),
                })?;
                named.insert(maybe_name.to_string(), value.to_string());
            }
        }
        Ok(Some(Pcre2Match { named }))
    }
}

impl Pcre2Match {
    pub(crate) fn named(&self, name: &str) -> Option<&str> {
        self.named.get(name).map(String::as_str)
    }
}

fn match_error(error: pcre2::Error) -> RuleRuntimeError {
    RuleRuntimeError {
        code: "pcre2_match_error".to_string(),
        message: format!("PCRE2 匹配失败：{error}"),
        details: BTreeMap::new(),
    }
}
```

- [ ] **Step 4: Run engine tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml rule_runtime::engine -- --nocapture
```

Expected: PASS.

- [ ] **Step 5: Record match limit implementation note**

Add a module comment in `engine.rs`:

```rust
//! PCRE2 统一封装。
//!
//! 当前高层 pcre2 crate 未暴露 match limit builder。实现资源限制任务时必须
//! 要么下探 pcre2-sys，要么在本模块内集中封装等价限制，禁止各 domain 自行处理。
```

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add rust/Cargo.toml rust/Cargo.lock rust/src/native_core.rs rust/src/native_core/rule_runtime/mod.rs rust/src/native_core/rule_runtime/engine.rs
git commit -m "feat: 建立 PCRE2 规则引擎封装"
```

Expected: commit succeeds.

## Task 2: Unified Rule Model And Errors

**Files:**
- Create: `rust/src/native_core/rule_runtime/model.rs`
- Create: `rust/src/native_core/rule_runtime/errors.rs`
- Modify: `rust/src/native_core/rule_runtime/mod.rs`
- Test: `rust/src/native_core/rule_runtime/model.rs`

- [ ] **Step 1: Add model serialization tests**

Create tests in `model.rs`:

```rust
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
        assert_eq!(serde_json::to_value(MatcherKind::Pcre2Pattern).unwrap(), json!("pcre2_pattern"));
        assert_eq!(serde_json::to_value(MatcherKind::JsonPathTemplate).unwrap(), json!("json_path_template"));
        assert_eq!(serde_json::to_value(MatcherKind::AstSelector).unwrap(), json!("ast_selector"));
        assert_eq!(serde_json::to_value(MatcherKind::Literal).unwrap(), json!("literal"));
    }
}
```

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml rule_runtime::model -- --nocapture
```

Expected: FAIL until model types exist.

- [ ] **Step 2: Implement model types**

Add to `model.rs`:

```rust
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub(crate) const RULE_RUNTIME_CONTRACT_VERSION: i64 = 1;
pub(crate) const RULE_STORE_SCHEMA_VERSION: i64 = 1;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub(crate) enum RuleDomain {
    PluginConfig,
    EventCommands,
    NoteTags,
    NonstandardData,
    PluginSource,
    Placeholders,
    StructuredPlaceholders,
    SourceResidual,
    MvVirtualNamebox,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub(crate) enum MatcherKind {
    Pcre2Pattern,
    JsonPathTemplate,
    AstSelector,
    Literal,
    DomainPayload,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct NormalizedRuleInput {
    pub(crate) domain: RuleDomain,
    pub(crate) rule_order: i64,
    pub(crate) matcher_kind: MatcherKind,
    pub(crate) matcher_value: String,
    pub(crate) payload_json: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) struct StoredRule {
    pub(crate) rule_id: String,
    pub(crate) domain: RuleDomain,
    pub(crate) rule_order: i64,
    pub(crate) matcher_kind: MatcherKind,
    pub(crate) matcher_value: String,
    pub(crate) payload_json: Value,
    pub(crate) enabled: bool,
    pub(crate) source_kind: String,
    pub(crate) rule_hash: String,
}

pub(crate) fn stable_rule_id(input: &NormalizedRuleInput) -> String {
    let payload = serde_json::json!({
        "domain": input.domain,
        "rule_order": input.rule_order,
        "matcher_kind": input.matcher_kind,
        "matcher_value": input.matcher_value,
        "payload_json": input.payload_json,
    });
    let serialized = serde_json::to_vec(&payload).expect("normalized rule id payload 应可序列化");
    let digest = Sha256::digest(serialized);
    format!("rule:{:x}", digest)
}
```

- [ ] **Step 3: Implement structured errors**

Add `errors.rs`:

```rust
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::model::RuleDomain;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub(crate) struct RuleRuntimeIssue {
    pub(crate) code: String,
    pub(crate) domain: Option<RuleDomain>,
    pub(crate) rule_id: Option<String>,
    pub(crate) field: Option<String>,
    pub(crate) message: String,
    pub(crate) details: Value,
    pub(crate) location: Option<String>,
}

impl RuleRuntimeIssue {
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
```

Update `mod.rs`:

```rust
pub(crate) mod engine;
pub(crate) mod errors;
pub(crate) mod model;
```

- [ ] **Step 4: Run model tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml rule_runtime::model -- --nocapture
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add rust/src/native_core/rule_runtime/model.rs rust/src/native_core/rule_runtime/errors.rs rust/src/native_core/rule_runtime/mod.rs
git commit -m "feat: 定义统一规则模型和错误结构"
```

Expected: commit succeeds.

## Task 3: Unified Rule Store Schema

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Create: `rust/src/native_core/rule_runtime/store.rs`
- Modify: `rust/src/native_core/rule_runtime/mod.rs`
- Test: `rust/src/native_core/rule_runtime/store.rs`
- Test: `tests/test_rule_runtime_store.py`

- [ ] **Step 1: Add Rust store tests**

Add to `store.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use serde_json::json;

    #[test]
    fn replace_domain_rules_replaces_only_current_domain() {
        let connection = Connection::open_in_memory().expect("in-memory DB should open");
        install_rule_store_schema(&connection).expect("schema should install");

        replace_domain_rules(&connection, RuleDomain::Placeholders, &[fixture_rule(RuleDomain::Placeholders, 0)])
            .expect("placeholder rules should save");
        replace_domain_rules(&connection, RuleDomain::MvVirtualNamebox, &[fixture_rule(RuleDomain::MvVirtualNamebox, 0)])
            .expect("mv rules should save");
        replace_domain_rules(&connection, RuleDomain::Placeholders, &[fixture_rule(RuleDomain::Placeholders, 1)])
            .expect("placeholder replacement should save");

        assert_eq!(read_rules_by_domain(&connection, RuleDomain::Placeholders).unwrap().len(), 1);
        assert_eq!(read_rules_by_domain(&connection, RuleDomain::MvVirtualNamebox).unwrap().len(), 1);
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
```

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml rule_runtime::store -- --nocapture
```

Expected: FAIL until schema helpers exist.

- [ ] **Step 2: Add current SQL schema**

Modify `app/persistence/schema/current.sql` to add current unified tables:

```sql
CREATE TABLE IF NOT EXISTS [rule_sets] (
    domain TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    rule_count INTEGER NOT NULL,
    context_hash TEXT NOT NULL,
    rules_hash TEXT NOT NULL,
    rule_runtime_contract_version INTEGER NOT NULL,
    rule_store_schema_version INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS [rules] (
    rule_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    rule_order INTEGER NOT NULL,
    matcher_kind TEXT NOT NULL,
    matcher_value TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    source_kind TEXT NOT NULL,
    rule_hash TEXT NOT NULL,
    UNIQUE(domain, rule_order, rule_id)
);

CREATE TABLE IF NOT EXISTS [rule_domain_states] (
    domain TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    rule_runtime_contract_version INTEGER NOT NULL,
    rule_store_schema_version INTEGER NOT NULL
);
```

Do not remove old domain rule tables in this task.

- [ ] **Step 3: Implement Rust store helpers**

Implement in `store.rs`:

```rust
use rusqlite::{params, Connection};
use serde_json::json;

use super::model::{MatcherKind, RuleDomain, StoredRule};

pub(crate) fn install_rule_store_schema(connection: &Connection) -> Result<(), String> {
    connection.execute_batch(include_str!("../../../app/persistence/schema/current.sql"))
        .map_err(|error| format!("统一规则表 schema 初始化失败: {error}"))
}

pub(crate) fn replace_domain_rules(
    connection: &Connection,
    domain: RuleDomain,
    rules: &[StoredRule],
) -> Result<(), String> {
    let transaction = connection.unchecked_transaction()
        .map_err(|error| format!("统一规则表事务创建失败: {error}"))?;
    let domain_text = serde_json::to_value(domain).map_err(|error| error.to_string())?;
    let domain_text = domain_text.as_str().unwrap_or_default().to_string();
    transaction.execute("DELETE FROM rules WHERE domain = ?1", params![domain_text])
        .map_err(|error| format!("清理当前 domain 规则失败: {error}"))?;
    for rule in rules {
        transaction.execute(
            "INSERT INTO rules(rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                rule.rule_id,
                serde_json::to_value(rule.domain).map_err(|error| error.to_string())?.as_str().unwrap_or_default(),
                rule.rule_order,
                serde_json::to_value(rule.matcher_kind).map_err(|error| error.to_string())?.as_str().unwrap_or_default(),
                rule.matcher_value,
                rule.payload_json.to_string(),
                if rule.enabled { 1 } else { 0 },
                rule.source_kind,
                rule.rule_hash,
            ],
        ).map_err(|error| format!("写入统一规则失败: {error}"))?;
    }
    transaction.commit().map_err(|error| format!("提交统一规则事务失败: {error}"))
}
```

If `include_str!` cannot reference the app schema from Rust cleanly, move the SQL into a Rust-local constant and add a test that it matches the current SQL table names.

- [ ] **Step 4: Add Python schema existence test**

Create `tests/test_rule_runtime_store.py`:

```python
async def test_current_schema_creates_unified_rule_store(temp_game_session: TargetGameSession) -> None:
    rows = await temp_game_session.connection.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('rule_sets', 'rules', 'rule_domain_states')"
    )

    assert {str(row[0]) for row in rows} == {"rule_sets", "rules", "rule_domain_states"}
```

Run:

```powershell
uv run pytest tests/test_rule_runtime_store.py::test_current_schema_creates_unified_rule_store -q
```

Expected: PASS after schema is applied by the test fixture.

- [ ] **Step 5: Run store tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml rule_runtime::store -- --nocapture
uv run pytest tests/test_rule_runtime_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py rust/src/native_core/rule_runtime/store.rs rust/src/native_core/rule_runtime/mod.rs tests/test_rule_runtime_store.py
git commit -m "feat: 建立统一规则存储模型"
```

Expected: commit succeeds.

## Task 4: Native API Prepare And Commit Skeleton

**Files:**
- Create: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `rust/src/native_core/rule_runtime/mod.rs`
- Modify: `rust/src/native_core.rs`
- Modify: `rust/src/lib.rs`
- Create: `app/native_rule_runtime.py`
- Test: `tests/test_native_rule_runtime.py`

- [ ] **Step 1: Add Python native API skeleton tests**

Create `tests/test_native_rule_runtime.py`:

```python
from app.native_rule_runtime import prepare_rule_import


def test_prepare_rule_import_rejects_unknown_domain() -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "unknown_domain",
            "rules_payload": {},
            "game_context": {},
            "settings_runtime_patterns": {},
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "rule_domain_invalid"
```

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py::test_prepare_rule_import_rejects_unknown_domain -q
```

Expected: FAIL because adapter/API does not exist.

- [ ] **Step 2: Implement Rust API skeleton**

Add `api.rs`:

```rust
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::errors::RuleRuntimeIssue;
use super::model::{RULE_RUNTIME_CONTRACT_VERSION, RULE_STORE_SCHEMA_VERSION};

#[derive(Debug, Deserialize)]
struct PrepareRuleImportPayload {
    mode: String,
    domain: String,
    #[serde(default)]
    rules_payload: Value,
    #[serde(default)]
    game_context: Value,
    #[serde(default)]
    settings_runtime_patterns: Value,
}

#[derive(Debug, Serialize)]
struct RuleImportReport {
    status: String,
    rule_runtime_contract_version: i64,
    rule_store_schema_version: i64,
    errors: Vec<RuleRuntimeIssue>,
    warnings: Vec<RuleRuntimeIssue>,
    plan_token: Option<String>,
    summary: Value,
}

pub(crate) fn prepare_rule_import_impl(payload_json: &str) -> Result<String, String> {
    let payload: PrepareRuleImportPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则导入 prepare 输入 JSON 无效: {error}"))?;
    if !matches!(payload.domain.as_str(), "placeholders" | "structured_placeholders" | "source_residual" | "mv_virtual_namebox" | "plugin_config" | "event_commands" | "note_tags" | "nonstandard_data" | "plugin_source") {
        let report = RuleImportReport {
            status: "error".to_string(),
            rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
            rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
            errors: vec![RuleRuntimeIssue::current_input_error(
                "rule_domain_invalid",
                format!("规则 domain 无效：{}", payload.domain),
            )],
            warnings: Vec::new(),
            plan_token: None,
            summary: serde_json::json!({}),
        };
        return serde_json::to_string(&report).map_err(|error| error.to_string());
    }
    let report = RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: Some("prepare-skeleton-token".to_string()),
        summary: serde_json::json!({"mode": payload.mode}),
    };
    serde_json::to_string(&report).map_err(|error| error.to_string())
}
```

Add to `mod.rs`:

```rust
pub(crate) mod api;
```

Add to `rust/src/native_core.rs`:

```rust
pub fn prepare_rule_import_impl(payload_json: &str) -> Result<String, String> {
    rule_runtime::api::prepare_rule_import_impl(payload_json)
}
```

Add PyO3 export in `rust/src/lib.rs` following existing native function style.

- [ ] **Step 3: Implement Python adapter**

Create `app/native_rule_runtime.py`:

```python
"""Rust rule_runtime 原生 API 适配器。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from app.native_contract import ensure_native_contract_version
from app.rmmz.json_types import JsonArray, JsonObject, coerce_json_value, ensure_json_array, ensure_json_object


@dataclass(frozen=True, slots=True)
class RuleRuntimeIssue:
    """Rust rule_runtime 返回的结构化问题。"""

    code: str
    message: str
    field: str | None


@dataclass(frozen=True, slots=True)
class RuleImportPrepareResult:
    """规则导入 prepare 报告。"""

    status: str
    errors: list[RuleRuntimeIssue]
    warnings: list[RuleRuntimeIssue]
    plan_token: str | None
    summary: JsonObject


class _NativeRuleRuntimeModule(Protocol):
    def native_contract_version(self) -> int:
        ...

    def prepare_rule_import(self, payload_json: str) -> str:
        ...


def prepare_rule_import(payload: JsonObject) -> RuleImportPrepareResult:
    """调用 Rust rule_runtime prepare。"""
    native = _load_native_module()
    raw_result = cast(object, json.loads(native.prepare_rule_import(json.dumps(payload, ensure_ascii=False))))
    result = ensure_json_object(coerce_json_value(raw_result), "rule_runtime.prepare_rule_import")
    return RuleImportPrepareResult(
        status=_read_string(result, "status", "rule_runtime.prepare_rule_import"),
        errors=_read_issues(result.get("errors", []), "rule_runtime.prepare_rule_import.errors"),
        warnings=_read_issues(result.get("warnings", []), "rule_runtime.prepare_rule_import.warnings"),
        plan_token=_read_optional_string(result, "plan_token", "rule_runtime.prepare_rule_import"),
        summary=ensure_json_object(result.get("summary", {}), "rule_runtime.prepare_rule_import.summary"),
    )


def _load_native_module() -> _NativeRuleRuntimeModule:
    native_module = cast(object, import_module("app._native"))
    ensure_native_contract_version(native_module)
    return cast(_NativeRuleRuntimeModule, native_module)


def _read_issues(value: object, context: str) -> list[RuleRuntimeIssue]:
    issues: list[RuleRuntimeIssue] = []
    for index, raw_issue in enumerate(ensure_json_array(coerce_json_value(value), context)):
        issue = ensure_json_object(raw_issue, f"{context}[{index}]")
        issues.append(
            RuleRuntimeIssue(
                code=_read_string(issue, "code", f"{context}[{index}]"),
                message=_read_string(issue, "message", f"{context}[{index}]"),
                field=_read_optional_string(issue, "field", f"{context}[{index}]"),
            )
        )
    return issues


def _read_string(payload: JsonObject, field_name: str, context: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise TypeError(f"{context}.{field_name} 必须是字符串")
    return value


def _read_optional_string(payload: JsonObject, field_name: str, context: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{context}.{field_name} 必须是字符串或 null")
    return value
```

- [ ] **Step 4: Run skeleton tests**

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py::test_prepare_rule_import_rejects_unknown_domain -q
```

Expected: PASS.

- [ ] **Step 5: Run type check**

Run:

```powershell
uv run basedpyright app/native_rule_runtime.py tests/test_native_rule_runtime.py
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add rust/src/native_core/rule_runtime/api.rs rust/src/native_core/rule_runtime/mod.rs rust/src/native_core.rs rust/src/lib.rs app/native_rule_runtime.py tests/test_native_rule_runtime.py
git commit -m "feat: 暴露规则运行时 native API"
```

Expected: commit succeeds.

## Task 5: Prepare/Commit Plan Token And Store Write

**Files:**
- Modify: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `rust/src/native_core/rule_runtime/store.rs`
- Modify: `app/native_rule_runtime.py`
- Test: `tests/test_native_rule_runtime.py`
- Test: `tests/test_rule_runtime_store.py`

- [ ] **Step 1: Add validate/import dry-run tests**

Add to `tests/test_native_rule_runtime.py`:

```python
def test_validate_prepare_returns_plan_without_db_write(temp_game_db_path: Path) -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "db_path": str(temp_game_db_path),
            "domain": "placeholders",
            "rules_payload": {},
            "game_context": {},
            "settings_runtime_patterns": {},
        }
    )

    assert result.status == "ok"
    assert result.plan_token is not None
    assert result.summary["mode"] == "validate"
```

Add commit test:

```python
def test_import_commit_rejects_mismatched_plan_token(temp_game_db_path: Path) -> None:
    result = commit_rule_import(
        {
            "db_path": str(temp_game_db_path),
            "domain": "placeholders",
            "plan_token": "wrong-token",
            "backup_path": None,
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "rule_import_plan_stale"
```

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py::test_validate_prepare_returns_plan_without_db_write tests/test_native_rule_runtime.py::test_import_commit_rejects_mismatched_plan_token -q
```

Expected: FAIL until commit API exists.

- [ ] **Step 2: Add Rust commit API**

In `api.rs`, add payload and function:

```rust
#[derive(Debug, Deserialize)]
struct CommitRuleImportPayload {
    db_path: String,
    domain: String,
    plan_token: String,
    backup_path: Option<String>,
}

pub(crate) fn commit_rule_import_impl(payload_json: &str) -> Result<String, String> {
    let payload: CommitRuleImportPayload = serde_json::from_str(payload_json)
        .map_err(|error| format!("规则导入 commit 输入 JSON 无效: {error}"))?;
    if payload.plan_token != "prepare-skeleton-token" {
        let report = RuleImportReport {
            status: "error".to_string(),
            rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
            rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
            errors: vec![RuleRuntimeIssue::current_input_error(
                "rule_import_plan_stale",
                "规则导入计划已失效，请重新执行导入命令".to_string(),
            )],
            warnings: Vec::new(),
            plan_token: None,
            summary: serde_json::json!({}),
        };
        return serde_json::to_string(&report).map_err(|error| error.to_string());
    }
    let report = RuleImportReport {
        status: "ok".to_string(),
        rule_runtime_contract_version: RULE_RUNTIME_CONTRACT_VERSION,
        rule_store_schema_version: RULE_STORE_SCHEMA_VERSION,
        errors: Vec::new(),
        warnings: Vec::new(),
        plan_token: None,
        summary: serde_json::json!({"domain": payload.domain, "backup_path": payload.backup_path}),
    };
    serde_json::to_string(&report).map_err(|error| error.to_string())
}
```

Wire through `native_core.rs`, `lib.rs`, and `app/native_rule_runtime.py`.

- [ ] **Step 3: Replace skeleton token with signed token**

Update prepare token generation to hash:

- domain
- mode
- rules payload
- game context
- settings runtime patterns
- runtime contract version

Add Rust helper:

```rust
fn plan_token_for(payload: &PrepareRuleImportPayload) -> Result<String, String> {
    let value = serde_json::json!({
        "domain": payload.domain,
        "mode": payload.mode,
        "rules_payload": payload.rules_payload,
        "game_context": payload.game_context,
        "settings_runtime_patterns": payload.settings_runtime_patterns,
        "rule_runtime_contract_version": RULE_RUNTIME_CONTRACT_VERSION,
    });
    let bytes = serde_json::to_vec(&value).map_err(|error| error.to_string())?;
    Ok(format!("plan:{:x}", sha2::Sha256::digest(bytes)))
}
```

Commit must recompute or validate against a persisted prepare plan. If no persisted plan exists yet, keep validation strict by requiring the token to begin with `plan:` and record the stronger persisted plan check in Task 17 when import transactions are wired to real services.

- [ ] **Step 4: Run prepare/commit tests**

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py -q
cargo test --manifest-path rust/Cargo.toml rule_runtime -- --nocapture
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add rust/src/native_core/rule_runtime/api.rs rust/src/native_core/rule_runtime/store.rs rust/src/native_core.rs rust/src/lib.rs app/native_rule_runtime.py tests/test_native_rule_runtime.py tests/test_rule_runtime_store.py
git commit -m "feat: 建立规则导入 prepare commit 流程"
```

Expected: commit succeeds.

## Task 6: Config PCRE2 Patterns And Python TextRules Exit

**Files:**
- Create: `rust/src/native_core/rule_runtime/adapters/config_patterns.rs`
- Modify: `rust/src/native_core/rule_runtime/adapters/mod.rs`
- Modify: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `app/rmmz/text_rules.py`
- Modify: `app/native_quality.py`
- Modify: `app/native_scope_index.py`
- Modify: `setting.example.toml`
- Test: `tests/test_text_rules.py`
- Test: `tests/test_native_rule_runtime.py`
- Test: `tests/test_config_overrides.py`

- [ ] **Step 1: Add config pattern validation tests**

Add to `tests/test_native_rule_runtime.py`:

```python
def test_prepare_rejects_invalid_config_pcre2_pattern() -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "placeholders",
            "rules_payload": {},
            "game_context": {},
            "settings_runtime_patterns": {
                "source_text_required_pattern": "(?<bad",
                "source_residual_segment_pattern": "[ぁ-ん]+",
                "line_width_count_pattern": "\\S",
                "residual_escape_sequence_pattern": "\\\\[nrt]",
            },
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "pcre2_compile_error"
    assert result.errors[0].field == "source_text_required_pattern"
```

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py::test_prepare_rejects_invalid_config_pcre2_pattern -q
```

Expected: FAIL until config adapter validates PCRE2.

- [ ] **Step 2: Implement config pattern adapter**

Add `config_patterns.rs`:

```rust
use serde::Deserialize;
use serde_json::Value;

use crate::native_core::rule_runtime::engine::{Pcre2Engine, Pcre2EngineConfig};
use crate::native_core::rule_runtime::errors::RuleRuntimeIssue;

#[derive(Debug, Deserialize)]
pub(crate) struct RuntimeConfigPatterns {
    pub(crate) source_text_required_pattern: String,
    pub(crate) source_residual_segment_pattern: String,
    pub(crate) line_width_count_pattern: String,
    pub(crate) residual_escape_sequence_pattern: String,
}

pub(crate) fn validate_runtime_config_patterns(value: &Value) -> Vec<RuleRuntimeIssue> {
    let Ok(patterns) = serde_json::from_value::<RuntimeConfigPatterns>(value.clone()) else {
        return vec![RuleRuntimeIssue::current_input_error(
            "runtime_config_patterns_invalid",
            "运行配置正则缺少当前必需字段".to_string(),
        )];
    };
    let config = Pcre2EngineConfig::default_runtime();
    let mut issues = Vec::new();
    for (field, pattern) in [
        ("source_text_required_pattern", patterns.source_text_required_pattern),
        ("source_residual_segment_pattern", patterns.source_residual_segment_pattern),
        ("line_width_count_pattern", patterns.line_width_count_pattern),
        ("residual_escape_sequence_pattern", patterns.residual_escape_sequence_pattern),
    ] {
        if let Err(error) = Pcre2Engine::compile(&pattern, &config) {
            issues.push(RuleRuntimeIssue {
                code: error.code,
                domain: None,
                rule_id: None,
                field: Some(field.to_string()),
                message: error.message,
                details: serde_json::json!({"pattern": pattern}),
                location: None,
            });
        }
    }
    issues
}
```

Call this from `prepare_rule_import_impl` before domain validation.

- [ ] **Step 3: Update setting example to PCRE2 style**

Modify `setting.example.toml`:

```toml
source_text_required_pattern = "[ぁ-んァ-ヶ一-龯ー]+"
source_residual_segment_pattern = "[ぁ-んァ-ヶー]+"
line_width_count_pattern = "\\S"
residual_escape_sequence_pattern = "\\\\[nrt]"
```

- [ ] **Step 4: Remove Python regex contract call from TextRules**

Modify `app/rmmz/text_rules.py`:

- remove import of `validate_text_rules_regex_contract`;
- remove `re.compile` for external/config regex fields from `from_setting`;
- replace compiled regex attributes with raw config DTO or remove the class methods after Rust callers exist.

For this task, keep public methods that still have callers but route them through native helper functions added in later tasks. Add explicit `RuntimeError` for any method that would require Python regex semantics:

```python
raise RuntimeError("TextRules 不再执行配置正则语义，请改用 Rust rule_runtime")
```

Tests should only hit this error for old direct helper calls, not production commands.

- [ ] **Step 5: Run config tests**

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py::test_prepare_rejects_invalid_config_pcre2_pattern tests/test_config_overrides.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add rust/src/native_core/rule_runtime/adapters/config_patterns.rs rust/src/native_core/rule_runtime/adapters/mod.rs rust/src/native_core/rule_runtime/api.rs app/rmmz/text_rules.py app/native_quality.py app/native_scope_index.py setting.example.toml tests/test_text_rules.py tests/test_native_rule_runtime.py tests/test_config_overrides.py
git commit -m "refactor: 配置正则切到 PCRE2 runtime"
```

Expected: commit succeeds.

## Task 7: Normal Placeholder Domain Adapter

**Files:**
- Create: `rust/src/native_core/rule_runtime/adapters/placeholders.rs`
- Modify: `rust/src/native_core/rule_runtime/adapters/mod.rs`
- Modify: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `app/config/custom_placeholder_rules.py`
- Modify: `app/rmmz/control_codes.py`
- Modify: `app/agent_toolkit/services/common.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Add placeholder PCRE2 import test**

Add to `tests/test_agent_toolkit_manual_import.py`:

```python
async def test_validate_placeholder_rules_uses_pcre2_named_contract(agent_service: AgentToolkitService, game_title: str) -> None:
    report = await agent_service.validate_placeholder_rules(
        game_title=game_title,
        rules_text='{"(?<control>\\\\V\\\\[\\\\d+\\\\])": "[CUSTOM_VAR_{index}]"}',
    )

    assert report.status == "ok"
    assert report.summary["rule_runtime"]["domain"] == "placeholders"
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_validate_placeholder_rules_uses_pcre2_named_contract -q
```

Expected: FAIL until placeholder adapter and service path use rule_runtime.

- [ ] **Step 2: Implement placeholder adapter normalization**

Add `placeholders.rs`:

```rust
use serde_json::Value;

use crate::native_core::rule_runtime::engine::{Pcre2Engine, Pcre2EngineConfig};
use crate::native_core::rule_runtime::errors::RuleRuntimeIssue;
use crate::native_core::rule_runtime::model::{MatcherKind, NormalizedRuleInput, RuleDomain};

pub(crate) fn normalize_placeholder_rules(payload: &Value) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
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
        if let Err(error) = Pcre2Engine::compile(pattern, &config) {
            issues.push(RuleRuntimeIssue {
                code: error.code,
                domain: Some(RuleDomain::Placeholders),
                rule_id: None,
                field: Some("pattern".to_string()),
                message: error.message,
                details: serde_json::json!({"pattern": pattern}),
                location: None,
            });
            continue;
        }
        let Some(template_text) = template.as_str() else {
            issues.push(RuleRuntimeIssue::current_input_error(
                "placeholder_template_invalid",
                "普通占位符模板必须是字符串".to_string(),
            ));
            continue;
        };
        rules.push(NormalizedRuleInput {
            domain: RuleDomain::Placeholders,
            rule_order: index as i64,
            matcher_kind: MatcherKind::Pcre2Pattern,
            matcher_value: pattern.to_string(),
            payload_json: serde_json::json!({"placeholder_template": template_text}),
        });
    }
    if issues.is_empty() { Ok(rules) } else { Err(issues) }
}
```

Wire it into `prepare_rule_import_impl` for `domain == "placeholders"`.

- [ ] **Step 3: Remove Python placeholder regex creation from import path**

Modify `app/config/custom_placeholder_rules.py` and `app/rmmz/control_codes.py`:

- parsing may still normalize JSON shape;
- remove `CustomPlaceholderRule.create()` usage from validate/import production path;
- service sends raw object to `prepare_rule_import`.

Keep internal fixed placeholder regex constants only for non-external fixed syntax until later quality/write-back integration migrates them.

- [ ] **Step 4: Route validate/import commands**

Modify `app/agent_toolkit/services/common.py` placeholder methods:

- `validate_placeholder_rules` calls `prepare_rule_import` with mode `validate`;
- `import_placeholder_rules` calls prepare, writes backup if plan includes cleanup, then commit;
- report summary contains `rule_runtime.domain = "placeholders"` and `mode`.

- [ ] **Step 5: Run placeholder tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_validate_placeholder_rules_uses_pcre2_named_contract tests/test_agent_toolkit_rule_import.py -q
```

Expected: PASS for targeted placeholder tests.

- [ ] **Step 6: Commit Task 7**

Run:

```powershell
git add rust/src/native_core/rule_runtime/adapters/placeholders.rs rust/src/native_core/rule_runtime/adapters/mod.rs rust/src/native_core/rule_runtime/api.rs app/config/custom_placeholder_rules.py app/rmmz/control_codes.py app/agent_toolkit/services/common.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_rule_import.py
git commit -m "refactor: 普通占位符规则接入 rule_runtime"
```

Expected: commit succeeds.

## Task 8: Structured Placeholder Domain Adapter

**Files:**
- Create: `rust/src/native_core/rule_runtime/adapters/structured_placeholders.rs`
- Modify: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `app/config/structured_placeholder_rules.py`
- Modify: `app/agent_toolkit/services/common.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_workspace.py`

- [ ] **Step 1: Add structured capture contract tests**

Add to `tests/test_agent_toolkit_manual_import.py`:

```python
async def test_structured_placeholder_requires_current_named_capture(agent_service: AgentToolkitService, game_title: str) -> None:
    rules_text = json.dumps(
        {
            "rules": [
                {
                    "name": "COLOR_WRAP",
                    "type": "paired_shell",
                    "pattern": "\\\\C\\[(?<color>\\d+)\\](?<body>.*?)\\\\C\\[0\\]",
                    "translatable_group": "body",
                    "protected_groups": {"color": "[CUSTOM_COLOR_{index}]"},
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await agent_service.validate_structured_placeholder_rules(game_title=game_title, rules_text=rules_text)

    assert report.status == "ok"
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_structured_placeholder_requires_current_named_capture -q
```

Expected: FAIL until adapter validates PCRE2 captures.

- [ ] **Step 2: Implement structured adapter**

Add `structured_placeholders.rs` with normalization:

```rust
pub(crate) fn normalize_structured_placeholder_rules(payload: &Value) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let rules_value = payload.get("rules").and_then(Value::as_array).ok_or_else(|| {
        vec![RuleRuntimeIssue::current_input_error(
            "structured_placeholder_rules_shape_invalid",
            "结构化占位符规则必须包含 rules 数组".to_string(),
        )]
    })?;
    let config = Pcre2EngineConfig::default_runtime();
    let mut normalized = Vec::new();
    let mut issues = Vec::new();
    for (index, rule) in rules_value.iter().enumerate() {
        let pattern = rule.get("pattern").and_then(Value::as_str).unwrap_or_default();
        let translatable_group = rule.get("translatable_group").and_then(Value::as_str).unwrap_or_default();
        match Pcre2Engine::compile(pattern, &config).and_then(|compiled| {
            if compiled.capture_names().contains(&translatable_group.to_string()) {
                Ok(())
            } else {
                Err(compiled.missing_capture_error(translatable_group))
            }
        }) {
            Ok(()) => normalized.push(NormalizedRuleInput {
                domain: RuleDomain::StructuredPlaceholders,
                rule_order: index as i64,
                matcher_kind: MatcherKind::Pcre2Pattern,
                matcher_value: pattern.to_string(),
                payload_json: rule.clone(),
            }),
            Err(error) => issues.push(RuleRuntimeIssue {
                code: error.code,
                domain: Some(RuleDomain::StructuredPlaceholders),
                rule_id: None,
                field: Some("pattern".to_string()),
                message: error.message,
                details: serde_json::json!({"pattern": pattern, "translatable_group": translatable_group}),
                location: None,
            }),
        }
    }
    if issues.is_empty() { Ok(normalized) } else { Err(issues) }
}
```

If `CompiledPcre2Pattern` lacks `capture_names()` and `missing_capture_error()`, add those methods in `engine.rs`.

- [ ] **Step 3: Route Python structured commands**

Modify `app/config/structured_placeholder_rules.py` to parse JSON shape only. Modify `app/agent_toolkit/services/common.py` to call rule_runtime for validate/import.

- [ ] **Step 4: Run structured tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_structured_placeholder_requires_current_named_capture tests/test_agent_toolkit_workspace.py -q
```

Expected: PASS for targeted structured placeholder paths.

- [ ] **Step 5: Commit Task 8**

Run:

```powershell
git add rust/src/native_core/rule_runtime/adapters/structured_placeholders.rs rust/src/native_core/rule_runtime/api.rs rust/src/native_core/rule_runtime/engine.rs app/config/structured_placeholder_rules.py app/agent_toolkit/services/common.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_workspace.py
git commit -m "refactor: 结构化占位符规则接入 rule_runtime"
```

Expected: commit succeeds.

## Task 9: Source Residual Domain Adapter

**Files:**
- Create: `rust/src/native_core/rule_runtime/adapters/source_residual.rs`
- Modify: `app/source_residual/rules.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/native_quality.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_quality_report.py`

- [ ] **Step 1: Add structural source residual PCRE2 test**

Add to `tests/test_agent_toolkit_manual_import.py`:

```python
async def test_source_residual_structural_rules_use_pcre2_capture(agent_service: AgentToolkitService, game_title: str) -> None:
    rules_text = json.dumps(
        {
            "position_rules": {},
            "structural_rules": [
                {
                    "pattern": "^<name>(?<visible>[^<]+)</name>$",
                    "check_group": "visible",
                    "allowed_terms": ["name"],
                    "reason": "协议外壳",
                }
            ],
        },
        ensure_ascii=False,
    )

    report = await agent_service.validate_source_residual_rules(game_title=game_title, rules_text=rules_text)

    assert report.status == "ok"
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_source_residual_structural_rules_use_pcre2_capture -q
```

Expected: FAIL until source residual adapter exists.

- [ ] **Step 2: Implement source residual normalization**

Add `source_residual.rs`:

```rust
pub(crate) fn normalize_source_residual_rules(payload: &Value) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let mut normalized = Vec::new();
    let config = Pcre2EngineConfig::default_runtime();
    if let Some(position_rules) = payload.get("position_rules").and_then(Value::as_object) {
        for (index, (location_path, rule)) in position_rules.iter().enumerate() {
            normalized.push(NormalizedRuleInput {
                domain: RuleDomain::SourceResidual,
                rule_order: index as i64,
                matcher_kind: MatcherKind::Literal,
                matcher_value: location_path.to_string(),
                payload_json: serde_json::json!({"rule_type": "position", "spec": rule}),
            });
        }
    }
    if let Some(structural_rules) = payload.get("structural_rules").and_then(Value::as_array) {
        for (index, rule) in structural_rules.iter().enumerate() {
            let pattern = rule.get("pattern").and_then(Value::as_str).unwrap_or_default();
            let check_group = rule.get("check_group").and_then(Value::as_str).unwrap_or_default();
            let compiled = Pcre2Engine::compile(pattern, &config);
            match compiled {
                Ok(pattern) if pattern.capture_names().contains(&check_group.to_string()) => {
                    normalized.push(NormalizedRuleInput {
                        domain: RuleDomain::SourceResidual,
                        rule_order: 10_000 + index as i64,
                        matcher_kind: MatcherKind::Pcre2Pattern,
                        matcher_value: pattern.pattern_text().to_string(),
                        payload_json: serde_json::json!({"rule_type": "structural", "spec": rule}),
                    });
                }
                Ok(_) => return Err(vec![RuleRuntimeIssue::current_input_error(
                    "source_residual_check_group_missing",
                    format!("结构性源文残留规则缺少当前 check_group capture：{check_group}"),
                )]),
                Err(error) => return Err(vec![RuleRuntimeIssue {
                    code: error.code,
                    domain: Some(RuleDomain::SourceResidual),
                    rule_id: None,
                    field: Some("pattern".to_string()),
                    message: error.message,
                    details: serde_json::json!({"pattern": pattern}),
                    location: None,
                }]),
            }
        }
    }
    Ok(normalized)
}
```

Add `pattern_text()` to `CompiledPcre2Pattern` if needed.

- [ ] **Step 3: Remove Python source residual regex compilation**

Modify `app/source_residual/rules.py`:

- Pydantic validates shape only;
- remove `re.compile` from external structural rule validation;
- quality masking uses Rust/native quality path, not `_compile_structural_records`.

- [ ] **Step 4: Route validate/import**

Modify `app/agent_toolkit/services/common.py` source residual methods to use rule_runtime prepare/commit.

- [ ] **Step 5: Run tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_source_residual_structural_rules_use_pcre2_capture tests/test_agent_toolkit_quality_report.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 9**

Run:

```powershell
git add rust/src/native_core/rule_runtime/adapters/source_residual.rs app/source_residual/rules.py app/agent_toolkit/services/common.py app/native_quality.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_quality_report.py
git commit -m "refactor: 源文残留规则接入 rule_runtime"
```

Expected: commit succeeds.

## Task 10: MV Virtual Namebox Domain Adapter

**Files:**
- Create: `rust/src/native_core/rule_runtime/adapters/mv_virtual_namebox.rs`
- Modify: `rust/src/native_core/scope_index/mv_virtual_namebox.rs`
- Modify: `app/rmmz/mv_namebox.py`
- Modify: `app/rmmz/mv_namebox_native.py`
- Modify: `app/agent_toolkit/services/common.py`
- Test: `tests/test_rmmz_mv_namebox.py`
- Test: `tests/test_agent_toolkit_workflow_gate.py`

- [ ] **Step 1: Add current capture syntax test**

Add to `tests/test_rmmz_mv_namebox.py`:

```python
def test_mv_virtual_namebox_rule_import_accepts_current_pcre2_capture() -> None:
    records = parse_mv_virtual_namebox_rule_import_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "colon-name",
                        "pattern": "^(?<speaker>[^：]+)：$",
                        "speaker_group": "speaker",
                        "speaker_policy": "translate",
                        "render_template": "{speaker}：",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    assert records[0].speaker_group == "speaker"
```

Run:

```powershell
uv run pytest tests/test_rmmz_mv_namebox.py::test_mv_virtual_namebox_rule_import_accepts_current_pcre2_capture -q
```

Expected: FAIL until parser stops Python regex validation and runtime accepts PCRE2.

- [ ] **Step 2: Implement MV adapter normalization**

Add `mv_virtual_namebox.rs`:

```rust
pub(crate) fn normalize_mv_virtual_namebox_rules(payload: &Value) -> Result<Vec<NormalizedRuleInput>, Vec<RuleRuntimeIssue>> {
    let rules = payload.get("rules").and_then(Value::as_array).ok_or_else(|| {
        vec![RuleRuntimeIssue::current_input_error(
            "mv_virtual_namebox_rules_shape_invalid",
            "MV 虚拟名字框规则必须包含 rules 数组".to_string(),
        )]
    })?;
    let config = Pcre2EngineConfig::default_runtime();
    let mut normalized = Vec::new();
    for (index, rule) in rules.iter().enumerate() {
        let pattern = rule.get("pattern").and_then(Value::as_str).unwrap_or_default();
        let speaker_group = rule.get("speaker_group").and_then(Value::as_str).unwrap_or_default();
        let compiled = Pcre2Engine::compile(pattern, &config).map_err(|error| {
            vec![RuleRuntimeIssue {
                code: error.code,
                domain: Some(RuleDomain::MvVirtualNamebox),
                rule_id: None,
                field: Some("pattern".to_string()),
                message: error.message,
                details: serde_json::json!({"pattern": pattern}),
                location: None,
            }]
        })?;
        if !compiled.capture_names().contains(&speaker_group.to_string()) {
            return Err(vec![RuleRuntimeIssue::current_input_error(
                "mv_virtual_namebox_speaker_capture_missing",
                format!("speaker capture 是必需分组，当前规则未声明：{speaker_group}"),
            )]);
        }
        normalized.push(NormalizedRuleInput {
            domain: RuleDomain::MvVirtualNamebox,
            rule_order: index as i64,
            matcher_kind: MatcherKind::Pcre2Pattern,
            matcher_value: pattern.to_string(),
            payload_json: rule.clone(),
        });
    }
    Ok(normalized)
}
```

- [ ] **Step 3: Replace MV scanning pattern engine**

Modify `rust/src/native_core/scope_index/mv_virtual_namebox.rs`:

- replace `fancy_regex::{Captures, Regex}` for external rules with rule_runtime PCRE2 wrapper;
- keep internal fixed actor control parsing in Rust `regex`;
- keep candidate grouping logic in Rust;
- move capture-to-speaker/body interpretation behind adapter helper.

- [ ] **Step 4: Remove Python MV regex runtime**

Modify `app/rmmz/mv_namebox.py`:

- parser builds DTO/records only;
- remove `MvVirtualNameboxRule.pattern`;
- remove `runtime_mv_virtual_namebox_rules` and `parse_mv_virtual_speaker_line` production callers or make them raise explicit error if still imported by tests;
- report and write-back use native rule_runtime facts.

- [ ] **Step 5: Run MV tests**

Run:

```powershell
uv run pytest tests/test_rmmz_mv_namebox.py tests/test_agent_toolkit_workflow_gate.py -q
cargo test --manifest-path rust/Cargo.toml mv_virtual_namebox -- --nocapture
```

Expected: PASS.

- [ ] **Step 6: Commit Task 10**

Run:

```powershell
git add rust/src/native_core/rule_runtime/adapters/mv_virtual_namebox.rs rust/src/native_core/scope_index/mv_virtual_namebox.rs app/rmmz/mv_namebox.py app/rmmz/mv_namebox_native.py app/agent_toolkit/services/common.py tests/test_rmmz_mv_namebox.py tests/test_agent_toolkit_workflow_gate.py
git commit -m "refactor: MV 虚拟名字框规则接入 rule_runtime"
```

Expected: commit succeeds.

## Task 11: Non-Regex Domain Adapters

**Files:**
- Create: `rust/src/native_core/rule_runtime/adapters/plugin_config.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/event_commands.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/note_tags.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/nonstandard_data.rs`
- Create: `rust/src/native_core/rule_runtime/adapters/plugin_source.rs`
- Modify: `app/plugin_text/native_validation.py`
- Modify: `app/event_command_text/native_validation.py`
- Modify: `app/note_tag_text/importer.py`
- Modify: `app/nonstandard_data/rules.py`
- Modify: `app/plugin_source_text/importer.py`
- Test: `tests/test_plugin_text.py`
- Test: `tests/test_event_command_text.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_workspace.py`

- [ ] **Step 1: Add non-regex matcher tests**

Add to `tests/test_native_rule_runtime.py`:

```python
@pytest.mark.parametrize(
    ("domain", "payload", "matcher_kind"),
    [
        ("plugin_config", [{"plugin_index": 0, "plugin_name": "TestPlugin", "paths": ["$['parameters']['Message']"]}], "json_path_template"),
        ("event_commands", {"357": [{"match": {"0": "Speaker"}, "paths": ["$['parameters'][1]['message']"]}]}, "json_path_template"),
        ("note_tags", {"Actors.json": ["profile"]}, "literal"),
        ("plugin_source", {"rules": [{"file": "Foo.js", "selectors": ["string@0:4"], "excluded_selectors": []}]}, "ast_selector"),
    ],
)
def test_prepare_non_regex_domains_do_not_require_pcre2(domain: str, payload: object, matcher_kind: str) -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": domain,
            "rules_payload": payload,
            "game_context": {"allow_empty_context_for_contract_test": True},
            "settings_runtime_patterns": valid_runtime_patterns(),
        }
    )

    assert result.summary["matcher_kinds"][0] == matcher_kind
```

Run:

```powershell
uv run pytest tests/test_native_rule_runtime.py::test_prepare_non_regex_domains_do_not_require_pcre2 -q
```

Expected: FAIL until adapters return matcher kinds.

- [ ] **Step 2: Implement non-regex normalization**

Each adapter must return `NormalizedRuleInput` with matcher kind:

- plugin config path templates: `MatcherKind::JsonPathTemplate`
- event command path templates: `MatcherKind::JsonPathTemplate`
- note tag names and file names: `MatcherKind::Literal`
- nonstandard data path templates: `MatcherKind::JsonPathTemplate`
- plugin source selectors: `MatcherKind::AstSelector`

Each adapter must validate shape and current context when real game context is present. The special `allow_empty_context_for_contract_test` field is accepted only in tests under `#[cfg(test)]` or behind a `test_mode` payload gate that production callers never set.

- [ ] **Step 3: Route existing validate/import services**

Modify existing native validation modules so they call `prepare_rule_import` instead of Python import builders for semantic validation:

- `app/plugin_text/native_validation.py`
- `app/event_command_text/native_validation.py`
- `app/note_tag_text/importer.py`
- `app/nonstandard_data/rules.py`
- `app/plugin_source_text/importer.py`

Python can still parse file shape into DTOs, but all hit validation and stale validation must come from Rust.

- [ ] **Step 4: Run non-regex domain tests**

Run:

```powershell
uv run pytest tests/test_plugin_text.py tests/test_event_command_text.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_workspace.py -q
```

Expected: PASS for migrated targeted paths.

- [ ] **Step 5: Commit Task 11**

Run:

```powershell
git add rust/src/native_core/rule_runtime/adapters/plugin_config.rs rust/src/native_core/rule_runtime/adapters/event_commands.rs rust/src/native_core/rule_runtime/adapters/note_tags.rs rust/src/native_core/rule_runtime/adapters/nonstandard_data.rs rust/src/native_core/rule_runtime/adapters/plugin_source.rs app/plugin_text/native_validation.py app/event_command_text/native_validation.py app/note_tag_text/importer.py app/nonstandard_data/rules.py app/plugin_source_text/importer.py tests/test_native_rule_runtime.py tests/test_plugin_text.py tests/test_event_command_text.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_workspace.py
git commit -m "refactor: 非正则规则进入统一 rule_runtime"
```

Expected: commit succeeds.

## Task 12: Scope Index, Quality, And Write-Back Consume Runtime

**Files:**
- Modify: `rust/src/native_core/scope_index/mod.rs`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/quality/mod.rs`
- Modify: `rust/src/native_core/write_back_plan/mod.rs`
- Modify: `app/native_scope_index.py`
- Modify: `app/native_quality.py`
- Modify: `app/native_write_plan.py`
- Test: `tests/test_native_scope_index.py`
- Test: `tests/test_agent_toolkit_quality_report.py`
- Test: `tests/test_rmmz_write_plan.py`

- [ ] **Step 1: Add no-scope-index-rule-interpretation static test**

Add to `tests/test_scan_budget.py`:

```python
def test_scope_index_no_longer_compiles_external_rule_regex() -> None:
    rust_files = [
        Path("rust/src/native_core/scope_index/mv_virtual_namebox.rs"),
        Path("rust/src/native_core/scope_index/placeholders.rs"),
        Path("rust/src/native_core/scope_index/structured_placeholders.rs"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in rust_files if path.exists())

    assert "fancy_regex" not in combined
    assert "Regex::new(&rule.pattern_text)" not in combined
```

Run:

```powershell
uv run pytest tests/test_scan_budget.py::test_scope_index_no_longer_compiles_external_rule_regex -q
```

Expected: FAIL until scope_index delegates external regex to rule_runtime.

- [ ] **Step 2: Integrate rule_runtime outputs**

Modify Rust modules:

- `scope_index` consumes normalized rules and domain outputs from `rule_runtime`.
- `quality` uses runtime config PCRE2 and source residual adapter outputs.
- `write_back_plan` consumes runtime render/protection facts for MV namebox and placeholders.

No domain should parse `payload_json` outside `rule_runtime::adapters`.

- [ ] **Step 3: Update Python adapters**

Modify:

- `app/native_scope_index.py`
- `app/native_quality.py`
- `app/native_write_plan.py`

Adapters should pass runtime rule context IDs or runtime outputs, not Python `TextRules` objects with compiled regex.

- [ ] **Step 4: Run integration tests**

Run:

```powershell
uv run pytest tests/test_native_scope_index.py tests/test_agent_toolkit_quality_report.py tests/test_rmmz_write_plan.py tests/test_scan_budget.py::test_scope_index_no_longer_compiles_external_rule_regex -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 12**

Run:

```powershell
git add rust/src/native_core/scope_index/mod.rs rust/src/native_core/scope_index/rebuild.rs rust/src/native_core/quality/mod.rs rust/src/native_core/write_back_plan/mod.rs app/native_scope_index.py app/native_quality.py app/native_write_plan.py tests/test_native_scope_index.py tests/test_agent_toolkit_quality_report.py tests/test_rmmz_write_plan.py tests/test_scan_budget.py
git commit -m "refactor: 规则消费者改用 rule_runtime 输出"
```

Expected: commit succeeds.

## Task 13: Domain State, Empty Confirmation, And Fingerprint

**Files:**
- Modify: `rust/src/native_core/rule_runtime/store.rs`
- Modify: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `app/rule_review.py`
- Modify: `app/application/flow_gate.py`
- Test: `tests/test_agent_toolkit_workflow_gate.py`
- Test: `tests/test_rule_runtime_store.py`

- [ ] **Step 1: Add domain state tests**

Add to `tests/test_rule_runtime_store.py`:

```python
async def test_confirm_empty_is_stored_as_domain_state_not_fake_rule(temp_game_session: TargetGameSession) -> None:
    report = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "mv_virtual_namebox",
            "rules_payload": {"rules": []},
            "game_context": {"engine_kind": "mv", "candidates": []},
            "settings_runtime_patterns": valid_runtime_patterns(),
            "confirm_empty": True,
        }
    )

    assert report.status == "ok"
    assert report.summary["rule_count"] == 0
    assert report.summary["domain_state"]["confirmed_empty"] is True
```

Run:

```powershell
uv run pytest tests/test_rule_runtime_store.py::test_confirm_empty_is_stored_as_domain_state_not_fake_rule -q
```

Expected: FAIL until domain state support exists.

- [ ] **Step 2: Implement domain state store**

In `store.rs`, add:

```rust
pub(crate) fn replace_domain_state(
    connection: &Connection,
    domain: RuleDomain,
    state_json: &serde_json::Value,
    scope_hash: &str,
    confirmed_at: &str,
) -> Result<(), String> {
    connection.execute(
        "INSERT OR REPLACE INTO rule_domain_states(domain, state_json, scope_hash, confirmed_at, rule_runtime_contract_version, rule_store_schema_version)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        rusqlite::params![
            serde_json::to_value(domain).map_err(|error| error.to_string())?.as_str().unwrap_or_default(),
            state_json.to_string(),
            scope_hash,
            confirmed_at,
            RULE_RUNTIME_CONTRACT_VERSION,
            RULE_STORE_SCHEMA_VERSION,
        ],
    ).map_err(|error| format!("写入规则 domain 状态失败: {error}"))?;
    Ok(())
}
```

- [ ] **Step 3: Implement unified fingerprint**

Add in `store.rs`:

```rust
pub(crate) fn build_rules_fingerprint(connection: &Connection, config_patterns_hash: &str) -> Result<String, String> {
    let rules = read_all_rules_sorted(connection)?;
    let states = read_all_domain_states_sorted(connection)?;
    let payload = serde_json::json!({
        "rules": rules,
        "domain_states": states,
        "config_patterns_hash": config_patterns_hash,
        "rule_runtime_contract_version": RULE_RUNTIME_CONTRACT_VERSION,
        "rule_store_schema_version": RULE_STORE_SCHEMA_VERSION,
    });
    let bytes = serde_json::to_vec(&payload).map_err(|error| error.to_string())?;
    Ok(format!("{:x}", sha2::Sha256::digest(bytes)))
}
```

- [ ] **Step 4: Route flow gate**

Modify `app/application/flow_gate.py` and `app/rule_review.py` so empty-rule confirmation reads current domain state from rule_runtime/store facts, not old `rule_review_states`.

- [ ] **Step 5: Run domain state tests**

Run:

```powershell
uv run pytest tests/test_rule_runtime_store.py tests/test_agent_toolkit_workflow_gate.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 13**

Run:

```powershell
git add rust/src/native_core/rule_runtime/store.rs rust/src/native_core/rule_runtime/api.rs app/rule_review.py app/application/flow_gate.py tests/test_agent_toolkit_workflow_gate.py tests/test_rule_runtime_store.py
git commit -m "refactor: 规则确认状态进入统一模型"
```

Expected: commit succeeds.

## Task 14: Remove Old Rule Tables And Record APIs

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/rule_records.py`
- Modify: `app/persistence/records.py`
- Test: `tests/test_persistence.py`
- Test: `tests/test_rule_runtime_store.py`

- [ ] **Step 1: Add old table removal test**

Add to `tests/test_persistence.py`:

```python
async def test_current_schema_does_not_create_old_domain_rule_tables(temp_game_session: TargetGameSession) -> None:
    rows = await temp_game_session.connection.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    table_names = {str(row[0]) for row in rows}

    assert "plugin_text_rules" not in table_names
    assert "event_command_text_rule_groups" not in table_names
    assert "placeholder_rules" not in table_names
    assert "structured_placeholder_rules" not in table_names
    assert "source_residual_rules" not in table_names
    assert "mv_virtual_namebox_rules" not in table_names
```

Run:

```powershell
uv run pytest tests/test_persistence.py::test_current_schema_does_not_create_old_domain_rule_tables -q
```

Expected: FAIL until old tables are removed.

- [ ] **Step 2: Remove old SQL schema**

Remove old table creation SQL from `app/persistence/schema/current.sql` and corresponding constants from `app/persistence/sql.py`:

- `plugin_text_rules`
- `plugin_source_text_rules`
- `nonstandard_data_text_rules`
- `note_tag_text_rules`
- `event_command_text_rule_groups`
- `event_command_text_rule_filters`
- `event_command_text_rule_paths`
- `placeholder_rules`
- `structured_placeholder_rules`
- `structured_placeholder_rule_groups`
- `source_residual_rules`
- `mv_virtual_namebox_rules`

Keep non-rule tables needed for translations, facts, runtime mappings, terminology and source snapshots.

- [ ] **Step 3: Remove old Python rule record APIs**

Modify `app/persistence/rule_records.py`:

- delete read/replace methods for old domain rule tables;
- keep only unified rule store accessors if Python still needs read-only diagnostics;
- remove imports from `app/rmmz/schema.py` record types if no longer used.

- [ ] **Step 4: Run persistence tests**

Run:

```powershell
uv run pytest tests/test_persistence.py tests/test_rule_runtime_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 14**

Run:

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py app/persistence/rule_records.py app/persistence/records.py tests/test_persistence.py tests/test_rule_runtime_store.py
git commit -m "refactor: 删除旧规则表事实源"
```

Expected: commit succeeds.

## Task 15: Delete Regex Contract And Fancy Regex

**Files:**
- Delete: `app/regex_contract.py`
- Delete: `rust/src/native_core/regex_contract.rs`
- Modify: `rust/Cargo.toml`
- Modify: `rust/src/native_core.rs`
- Modify: `tests/test_regex_contract.py`
- Modify: `tests/test_scan_budget.py`

- [ ] **Step 1: Add deletion guard test**

Add to `tests/test_scan_budget.py`:

```python
def test_old_regex_contract_files_are_removed() -> None:
    assert not Path("app/regex_contract.py").exists()
    assert not Path("rust/src/native_core/regex_contract.rs").exists()
    assert "fancy-regex" not in Path("rust/Cargo.toml").read_text(encoding="utf-8")
```

Run:

```powershell
uv run pytest tests/test_scan_budget.py::test_old_regex_contract_files_are_removed -q
```

Expected: FAIL until files and dependency are removed.

- [ ] **Step 2: Remove Python imports**

Run:

```powershell
rg -n "regex_contract|validate_.*regex_contract|RegexContract" app tests
```

Expected before edits: existing callers are listed. Remove each import and route behavior through `app/native_rule_runtime.py`.

- [ ] **Step 3: Delete old files and dependency**

Delete:

- `app/regex_contract.py`
- `rust/src/native_core/regex_contract.rs`

Modify:

- remove `mod regex_contract;` and `validate_regex_contract_impl` export from `rust/src/native_core.rs`;
- remove PyO3 `validate_regex_contract` from `rust/src/lib.rs`;
- remove `fancy-regex` from `rust/Cargo.toml`;
- update `rust/Cargo.lock` by running cargo metadata/test.

- [ ] **Step 4: Rewrite regex contract tests**

Replace `tests/test_regex_contract.py` with tests for `native_rule_runtime` PCRE2 errors. Example:

```python
def test_pcre2_rule_runtime_reports_missing_capture() -> None:
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "mv_virtual_namebox",
            "rules_payload": {
                "rules": [
                    {
                        "name": "bad",
                        "pattern": "^(?<name>.+)$",
                        "speaker_group": "speaker",
                        "speaker_policy": "translate",
                        "render_template": "{speaker}",
                    }
                ]
            },
            "game_context": {"engine_kind": "mv", "candidates": []},
            "settings_runtime_patterns": valid_runtime_patterns(),
        }
    )

    assert result.status == "error"
    assert result.errors[0].code == "mv_virtual_namebox_speaker_capture_missing"
```

- [ ] **Step 5: Run deletion tests**

Run:

```powershell
uv run pytest tests/test_regex_contract.py tests/test_scan_budget.py::test_old_regex_contract_files_are_removed -q
cargo test --manifest-path rust/Cargo.toml rule_runtime -- --nocapture
```

Expected: PASS.

- [ ] **Step 6: Commit Task 15**

Run:

```powershell
git add app rust tests/test_regex_contract.py tests/test_scan_budget.py
git commit -m "refactor: 删除旧正则契约实现"
```

Expected: commit succeeds.

## Task 16: Reports, Diagnostics, And Backup Cleanup

**Files:**
- Modify: `rust/src/native_core/rule_runtime/api.rs`
- Modify: `app/native_rule_runtime.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/application/rule_import_backup.py`
- Test: `tests/test_rule_import_transactions.py`
- Test: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Add backup transaction test**

Add to `tests/test_rule_import_transactions.py`:

```python
async def test_rule_import_writes_backup_before_commit(agent_service: AgentToolkitService, game_title: str, tmp_path: Path) -> None:
    report = await agent_service.import_placeholder_rules(
        game_title=game_title,
        rules_text='{"(?<control>\\\\V\\\\[\\\\d+\\\\])": "[CUSTOM_VAR_{index}]"}',
        backup_output_dir=tmp_path,
    )

    if report.summary["cleanup_count"]:
        backup_path = Path(str(report.summary["deleted_translation_backup_path"]))
        assert backup_path.exists()
        assert json.loads(backup_path.read_text(encoding="utf-8"))
```

Run:

```powershell
uv run pytest tests/test_rule_import_transactions.py::test_rule_import_writes_backup_before_commit -q
```

Expected: FAIL until report exposes cleanup plan and backup path.

- [ ] **Step 2: Add diagnostics fields**

In Rust report summary/details include:

```json
{
  "diagnostics": {
    "rule_runtime": {
      "compile_ms": 0,
      "scan_ms": 0,
      "store_ms": 0,
      "domain_timings": {},
      "jit_enabled": true,
      "thread_count": 1,
      "rule_count_by_domain": {},
      "error_count_by_code": {}
    }
  }
}
```

Python adapter should parse diagnostics as `JsonObject` without interpreting internals.

- [ ] **Step 3: Implement backup prepare/commit reporting**

Rust prepare returns:

```json
{
  "cleanup_plan": {
    "deleted_translation_count": 0,
    "backup_required": false,
    "records": []
  }
}
```

Python writes backup when `backup_required` is true, then commit passes:

```json
{
  "backup_path": "<输出目录>/rule-import-backups/<游戏标题>/<时间>.json"
}
```

Use existing `app/application/rule_import_backup.py` path helpers, with real paths only in file operations and report paths sanitized as project output paths.

- [ ] **Step 4: Run report tests**

Run:

```powershell
uv run pytest tests/test_rule_import_transactions.py tests/test_agent_toolkit_rule_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 16**

Run:

```powershell
git add rust/src/native_core/rule_runtime/api.rs app/native_rule_runtime.py app/agent_toolkit/services/common.py app/application/rule_import_backup.py tests/test_rule_import_transactions.py tests/test_agent_toolkit_rule_import.py
git commit -m "feat: 完成规则导入报告和备份事务"
```

Expected: commit succeeds.

## Task 17: Docs, Skill Protocol, And Changelog

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `setting.example.toml`
- Modify: `skills/att-mz-protocol/workflow.toml`
- Modify: `skills/att-mz-protocol/references/mv-virtual-namebox-rules.md`
- Modify: `skills/att-mz-protocol/references/placeholder-rules.md`
- Modify: `skills/att-mz-protocol/references/structured-placeholder-rules.md`
- Modify: `skills/att-mz-protocol/references/external-rules-workflow.md`
- Modify generated: `skills/att-mz/**`
- Modify generated: `skills/att-mz-release/**`

- [ ] **Step 1: Update canonical Skill protocol**

Update canonical references so examples use:

```text
(?<speaker>...)
(?<body>...)
```

Remove mentions of:

- Python re
- fancy-regex
- `(?P<name>...)`
- old rule tables
- old report fields

- [ ] **Step 2: Regenerate Skill outputs**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --write
uv run python scripts/generate_skill_protocol.py --check
```

Expected: both commands succeed.

- [ ] **Step 3: Update README and CHANGELOG**

README should describe current commands and current PCRE2 contract only.

CHANGELOG should include a breaking change entry:

```markdown
### Breaking

- 外部可写正则统一改为 PCRE2 当前契约，命名 capture 使用 `(?<name>...)`。
- 规则存储统一为当前规则模型；旧规则表不迁移。用户需要按当前命令重新导入规则。
```

- [ ] **Step 4: Run docs scans**

Run:

```powershell
rg -n "Python re|fancy-regex|\\(\\?P<|plugin_text_rules|mv_virtual_namebox_rules|placeholder_rules" README.md docs skills setting.example.toml
```

Expected: no matches that describe current runtime behavior. Matches in archived records are acceptable only outside current README/docs/skills contract files.

- [ ] **Step 5: Commit Task 17**

Run:

```powershell
git add README.md CHANGELOG.md setting.example.toml skills/att-mz-protocol skills/att-mz skills/att-mz-release
git commit -m "docs: 更新 PCRE2 规则运行时契约"
```

Expected: commit succeeds.

## Task 18: Performance Evidence And Final Verification

**Files:**
- Create: `docs/records/performance/pcre2-rule-runtime-cli-timings.md`
- Modify: `tests/test_scan_budget.py`

- [ ] **Step 1: Add final scan budget guards**

Add to `tests/test_scan_budget.py`:

```python
def test_no_python_external_regex_runtime_remains() -> None:
    files = [path for path in Path("app").rglob("*.py") if "__pycache__" not in path.parts]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    forbidden = [
        "validate_text_rules_regex_contract",
        "validate_mv_virtual_namebox_regex_contract",
        "validate_source_residual_regex_contract",
        "re.compile(record.pattern_text)",
        "rule.pattern.finditer",
    ]
    for needle in forbidden:
        assert needle not in combined
```

Run:

```powershell
uv run pytest tests/test_scan_budget.py::test_no_python_external_regex_runtime_remains -q
```

Expected: PASS.

- [ ] **Step 2: Collect CLI performance evidence**

Use a non-private fixture path in notes and redact real local paths from the committed file. Run representative commands:

```powershell
Measure-Command { uv run python main.py validate-placeholder-rules --game <游戏标题> --input <工作区>/placeholder-rules.json --json }
Measure-Command { uv run python main.py import-placeholder-rules --game <游戏标题> --input <工作区>/placeholder-rules.json --json }
Measure-Command { uv run python main.py rebuild-text-index --game <游戏标题> --json }
Measure-Command { uv run python main.py quality-report --game <游戏标题> --json }
```

If local fixtures cannot supply a complete game, run the largest available project fixture command and state the limitation.

- [ ] **Step 3: Write performance record**

Create `docs/records/performance/pcre2-rule-runtime-cli-timings.md`:

```markdown
# PCRE2 统一规则运行时 CLI 性能证据

## 环境

## 样本

## 命令结果

| 命令 | 线程 | 总耗时 | rule_runtime.compile_ms | rule_runtime.scan_ms | rule_runtime.store_ms | JIT | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |

## 瓶颈归因

## 剩余风险
```

Use `<游戏标题>`、`<工作区>`、`<项目目录>` placeholders for examples. Do not commit private local paths.

- [ ] **Step 4: Run Rust format**

Run:

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
```

Expected: PASS.

- [ ] **Step 5: Run Rust clippy**

Run:

```powershell
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

Expected: PASS.

- [ ] **Step 6: Run Rust tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml
```

Expected: PASS.

- [ ] **Step 7: Run Python type check**

Run:

```powershell
uv run basedpyright
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 8: Run full Python tests**

Run:

```powershell
uv run pytest
```

Expected: PASS.

- [ ] **Step 9: Run Skill protocol check**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: PASS.

- [ ] **Step 10: Commit final evidence**

Run:

```powershell
git add tests/test_scan_budget.py docs/records/performance/pcre2-rule-runtime-cli-timings.md
git commit -m "test: 补充 PCRE2 规则运行时最终验收证据"
```

Expected: commit succeeds.

## Execution Notes

- 每个任务按 RED -> GREEN -> targeted verification -> commit 执行。
- 中间任务可以只跑 targeted tests，最终任务必须跑全量门禁。
- 如果某个任务发现 spec 与代码现实冲突，先更新 design/spec 并取得确认，再继续实现。
- 如果 PCRE2 高层 crate 无法实现 match limit，必须在 Task 1 或 Task 6 内记录技术结论，并把资源限制实现集中在 `engine.rs`，不能分散到 domain adapter。

## Plan Self-Review

- Spec coverage: Tasks 1-2 cover PCRE2 engine and model; Tasks 3, 5, 13, 14 cover unified store, domain state, fingerprint and old table removal; Tasks 4, 5, 16 cover native API, prepare/commit, plan token and backup; Tasks 6-12 cover all regex and non-regex domain migration; Task 15 removes old regex contracts; Task 17 covers docs/Skill/CHANGELOG; Task 18 covers performance and final verification.
- Red-flag scan: no unresolved planning markers or incomplete sections remain.
- Type consistency: `RuleDomain`, `MatcherKind`, `NormalizedRuleInput`, `StoredRule`, `RuleRuntimeIssue`, `prepare_rule_import`, and `commit_rule_import` are introduced before later tasks consume them.
- Scope check: this plan is intentionally large because the approved spec requires complete收束；任务以可提交批次拆分，最终验收才声明整体完成。
