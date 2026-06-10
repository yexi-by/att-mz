# Rust 主路径总重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按总重构蓝图把候选扫描、规则命中、gate、stale、scope hash、metadata/cache contract 收束到 Rust/native 单一事实源，并删除对应 Python 生产事实源。

**Architecture:** 先建立 Rust facts contract 和跨层错误码，再让 text index metadata 保存真实 gate facts 和 contract version；随后迁移插件源码、非标准 data、path template、Note 标签等业务事实到 Rust 输出，Python 只消费 contract 并组装报告。最后删除旧 Python scanner/extractor/oracle，补齐生命周期测试、Rust contract 测试和真实 CLI 性能证据。

**Tech Stack:** Rust 2024, PyO3, serde, SQLite, Python 3.14, pydantic v2, uv, pytest, basedpyright, cargo fmt/clippy/test.

---

## Source Spec And Review Inputs

执行前必须阅读：

- `docs/superpowers/specs/2026-06-11-rust-primary-total-refactor-blueprint-design.md`
- `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-01-fact-sources-contract.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-02-rust-primary-path.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-03-cross-command-lifecycle.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-04-cache-metadata-fast-path.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-05-tests-acceptance.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-06-migration-deletion.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-07-performance-concurrency.md`

本计划覆盖全部 P0、P1、P2。执行时可以按阶段分批提交，但不能只完成阶段 1 或只修 P0 后宣称总重构完成。

## Global Guardrails

- 不在 Python 新增 selector fallback、stale 二次判断、风险阈值补丁或 path template 兼容分支。
- 不让 Python 和 Rust 长期保留同一候选事实的双实现。
- 不继续使用 `workflow_gate_prechecked:* = passed` 表示当前 gate 已审查。
- 不保留旧 Python scanner/extractor/oracle 作为包根公共 API 等调用方自觉不用。
- 不用中文文案正则替代错误码和事实状态断言。
- 不把 scan budget 或旧性能报告写成当前 HEAD 真实 CLI 性能通过。
- 旧数据库、旧规则、旧 metadata、旧 cache 不符合当前 contract 时显式失效。
- 每个阶段完成后必须能指出：新增 Rust contract、Python 消费迁移、旧路径删除、测试覆盖、验证命令。

## Finding Coverage Map

| 严重度 | 发现 | 任务 |
| --- | --- | --- |
| P0 | workflow gate metadata 不是当前候选 gate 事实 | Task 4, Task 5, Task 13 |
| P0 | 插件源码排除 selector fast path 可绕过当前 AST / selector 新鲜度 | Task 6, Task 7, Task 13 |
| P0 | 空规则确认 scope hash 有 Python 冷路径与 Rust warm index 双事实源 | Task 2, Task 11 |
| P1 | `path_template` / JSONPath 语法和 `location_path` 展开仍由 Python 与 Rust 分别维护 | Task 2, Task 9 |
| P1 | 插件源码候选、selector、stale 和风险判断仍在 Python 二次实现 | Task 7, Task 8 |
| P1 | Note 标签规则验证仍由 Python 执行精确匹配和可翻译判断 | Task 10 |
| P1 | 插件源码 `excluded_selectors` fast path 只比对已存规则 | Task 6, Task 7 |
| P1 | text index metadata 没有持久记录 Rust/native contract version | Task 4, Task 5 |
| P1 | 当前运行插件源码持久 scan cache 只按文件 hash 命中 | Task 6 |
| P1 | 缺少“规则导入成功后冷重建不能立刻 stale”的非空规则生命周期回归 | Task 13 |
| P1 | 插件源码规则已宣称 Rust 主路径，但 Python 仍承担 selector 校验、stale 判断和覆盖门禁 | Task 7, Task 8 |
| P1 | 非标准 data 文本范围仍通过 Python 提取器展开规则命中 | Task 9 |
| P2 | schema/version 契约常量在 SQL、Python、Rust 和测试中重复硬编码 | Task 2, Task 4 |
| P2 | 插件源码 selector 与插件源码 `location_path` 身份算法仍存在 Python/Rust 双实现 | Task 7, Task 8 |
| P2 | 普通 placeholder 生产路径已转 native，但旧 Python 扫描器仍在 `app` 包导出 | Task 12 |
| P2 | 测试把“不在 Python 热路径偷扫”固定成“后续命令不消费插件源码高风险” | Task 5, Task 13 |
| P2 | 写回验收 helper 在测试层手工构造 current text fact | Task 13 |
| P2 | 部分直接写入命令只断言异常文案，没有固定错误码与事实状态 | Task 14 |
| P2 | 旧 Python 提取器和 helper 仍作为包根公共 API 暴露 | Task 12 |
| P2 | 测试仍把 Python 旧实现当 native 对照 oracle | Task 12 |
| P2 | 性能验收仍缺当前 HEAD 的真实 CLI 计时闭环 | Task 15 |

## Target File Structure

新增或重点修改的文件按职责分组：

### Rust Contract And Storage

- Create: `rust/src/native_core/scope_index/contracts.rs`
- Modify: `rust/src/native_core/scope_index/mod.rs`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Modify: `rust/src/native_core/scope_index/plugin_source.rs`
- Modify: `rust/src/native_core/scope_index/nonstandard_data.rs`
- Modify: `rust/src/native_core/scope_index/note_tags.rs`
- Modify: `rust/src/native_core/text_facts.rs`
- Modify: `rust/src/lib.rs`

### Python Native Adapter And Persistence

- Modify: `app/native_scope_index.py`
- Modify: `app/native_contract.py`
- Modify: `app/persistence/records.py`
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/text_index_records.py`
- Modify: `app/persistence/rule_records.py`

### Python Consumption Boundaries

- Modify: `app/application/handler.py`
- Modify: `app/application/flow_gate.py`
- Modify: `app/text_index.py`
- Modify: `app/text_scope/rule_hits.py`
- Modify: `app/plugin_source_text/native_scan.py`
- Modify: `app/plugin_source_text/importer.py`
- Modify: `app/plugin_source_text/rules.py`
- Modify: `app/plugin_source_text/extraction.py`
- Modify: `app/plugin_source_text/__init__.py`
- Modify: `app/nonstandard_data/extraction.py`
- Modify: `app/nonstandard_data/rules.py`
- Modify: `app/nonstandard_data/__init__.py`
- Modify: `app/native_note_tag_scan.py`
- Modify: `app/agent_toolkit/placeholder_scan.py`
- Modify: `app/agent_toolkit/__init__.py`
- Modify: `tests/agent_toolkit_contract_fixtures.py`
- Modify: `tests/rmmz_writeback_contract_fixtures.py`

### Tests And Evidence

- Modify: `tests/test_native_scope_index.py`
- Modify: `tests/test_text_index.py`
- Modify: `tests/test_workflow_gate.py`
- Modify: `tests/test_agent_toolkit_workflow_gate.py`
- Modify: `tests/test_agent_toolkit_rule_import.py`
- Modify: `tests/test_agent_toolkit_quality_report.py`
- Modify: `tests/test_rmmz_write_plan.py`
- Modify: `tests/test_nonstandard_data.py`
- Modify: `tests/test_rmmz_note_nonstandard_data.py`
- Modify: `tests/test_scan_budget.py`
- Create: `docs/records/performance/rust-primary-total-refactor-cli-timings.md`

## Task 1: Baseline And Scope Lock

**Files:**
- Read: all source spec and review files listed above
- Read: `git status --short --branch`
- Modify only after this task: none

- [ ] **Step 1: Confirm branch and worktree state**

Run:

```powershell
git status --short --branch
```

Expected: command succeeds. Record any pre-existing untracked or modified files in the task notes. Do not clean, revert, or stage unrelated user changes.

- [ ] **Step 2: Confirm source spec coverage**

Run:

```powershell
Select-String -Path 'docs\superpowers\specs\2026-06-11-rust-primary-total-refactor-blueprint-design.md' -Pattern '\| P0','\| P1','\| P2'
```

Expected: output includes 3 P0 rows, 9 P1 rows, and 9 P2 rows. If the counts differ, stop and reconcile the spec before coding.

- [ ] **Step 3: Capture current contract and shortcut sites**

Run:

```powershell
rg -n 'workflow_gate_prechecked|TEXT_INDEX_WORKFLOW_GATE_PRECHECK|gate_errors|scope_hash|contract_version|schema_version|excluded_selectors|NonstandardDataTextExtraction|PluginSourceTextExtraction|collect_nonstandard_data_rule_hits|scan_placeholder_candidates' app rust tests
```

Expected: command returns the known fact-source and shortcut sites. Save the output in local notes for task execution; do not commit command output.

- [ ] **Step 4: Commit checkpoint if starting from a dirty implementation branch**

Run:

```powershell
git status --short
```

Expected: if this task is being executed in an isolated worktree, status is clean before Task 2. If status is dirty because the user asked to continue from an existing branch, list the dirty files in the task notes and avoid reverting them.

## Task 2: Contract Foundation In Rust

**Files:**
- Create: `rust/src/native_core/scope_index/contracts.rs`
- Modify: `rust/src/native_core/scope_index/mod.rs`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Modify: `rust/src/native_core/text_facts.rs`
- Test: `rust/src/native_core/scope_index/contracts.rs`
- Test: `tests/test_native_scope_index.py`

- [ ] **Step 1: Write Rust contract tests**

Add tests in `rust/src/native_core/scope_index/contracts.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn contract_versions_are_serialized_with_gate_facts() {
        let facts = TextIndexContractFacts::new_for_test();
        let value = serde_json::to_value(&facts).expect("contract facts 应可序列化");

        assert_eq!(value["rust_contract_version"], json!(RUST_SCOPE_FACTS_CONTRACT_VERSION));
        assert_eq!(value["parser_contract_version"], json!(PARSER_CONTRACT_VERSION));
        assert_eq!(value["source_branch_contract_version"], json!(SOURCE_BRANCH_CONTRACT_VERSION));
        assert!(value["gate_facts"].as_object().is_some_and(|object| object.contains_key("plugin_source_text")));
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
            assert!(text.chars().all(|character| character.is_ascii_lowercase() || character == '_'));
        }
    }
}
```

Run:

```powershell
cargo test -p att-mz-native scope_index::contracts -- --nocapture
```

Expected: FAIL because `contracts.rs` and the contract types do not exist yet.

- [ ] **Step 2: Implement Rust contract module**

Create `rust/src/native_core/scope_index/contracts.rs` with these public shapes and Chinese doc comments on all public items:

```rust
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Rust scope facts contract 当前版本。
pub(crate) const RUST_SCOPE_FACTS_CONTRACT_VERSION: i64 = 1;

/// JavaScript / JSON parser 事实契约当前版本。
pub(crate) const PARSER_CONTRACT_VERSION: i64 = 1;

/// source branch 分类契约当前版本。
pub(crate) const SOURCE_BRANCH_CONTRACT_VERSION: i64 = 1;

/// 当前文本索引可持久化的事实契约。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) struct TextIndexContractFacts {
    pub(crate) rust_contract_version: i64,
    pub(crate) parser_contract_version: i64,
    pub(crate) source_branch_contract_version: i64,
    pub(crate) text_fact_schema_version: i64,
    pub(crate) scope_hash: String,
    pub(crate) source_snapshot_fingerprint: String,
    pub(crate) rules_fingerprint: String,
    pub(crate) gate_facts: BTreeMap<String, SourceBranchGateFact>,
}

/// 单个 source branch 的 gate 事实。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) struct SourceBranchGateFact {
    pub(crate) source_branch: String,
    pub(crate) status: GateStatus,
    pub(crate) scope_hash: String,
    pub(crate) error_codes: Vec<String>,
    pub(crate) stale_reasons: Vec<StaleReason>,
}

/// gate 状态。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum GateStatus {
    Pass,
    Fail,
}

/// stale 原因。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) struct StaleReason {
    pub(crate) code: String,
    pub(crate) message: String,
}

/// 稳定 stale 错误码。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum StaleReasonCode {
    AstMissing,
    SelectorFiltered,
    SourceFileChanged,
    PluginDisabled,
    ContractChanged,
}

impl StaleReasonCode {
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
```

Also add `new_for_test()` under `#[cfg(test)]` so Step 1 tests compile.

- [ ] **Step 3: Wire contract module into Rust scope index**

Modify `rust/src/native_core/scope_index/mod.rs`:

```rust
mod contracts;
```

Replace the local `RULE_CANDIDATES_SCHEMA_VERSION` usage with a contract constant exported from `contracts.rs` only if it describes the same schema. If it remains a narrower rule-candidate schema, keep it private and add a test that `RuleCandidatesOutput` includes both `schema_version` and `contract_versions`.

- [ ] **Step 4: Add contract_versions to native JSON outputs**

Modify `RuleCandidatesOutput`, `BuildScopeIndexOutput`, and storage rebuild output to include:

```rust
contract_versions: ContractVersionsOutput,
```

with:

```rust
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
struct ContractVersionsOutput {
    rust_scope_facts: i64,
    parser: i64,
    source_branch: i64,
    text_fact_schema: i64,
}
```

Expected JSON shape:

```json
{
  "contract_versions": {
    "rust_scope_facts": 1,
    "parser": 1,
    "source_branch": 1,
    "text_fact_schema": 2
  }
}
```

- [ ] **Step 5: Add Python adapter schema test**

Add to `tests/test_native_scope_index.py`:

```python
def test_native_scope_index_outputs_contract_versions() -> None:
    result = scan_native_rule_candidates({"candidates": []})

    assert result.contract_versions.rust_scope_facts >= 1
    assert result.contract_versions.parser >= 1
    assert result.contract_versions.source_branch >= 1
    assert result.contract_versions.text_fact_schema >= 1
```

Run:

```powershell
uv run pytest tests/test_native_scope_index.py::test_native_scope_index_outputs_contract_versions -q
```

Expected: FAIL until Task 3 adds Python adapter support.

- [ ] **Step 6: Run Rust contract tests**

Run:

```powershell
cargo test -p att-mz-native scope_index::contracts -- --nocapture
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add rust/src/native_core/scope_index/contracts.rs rust/src/native_core/scope_index/mod.rs rust/src/native_core/scope_index/rebuild.rs rust/src/native_core/scope_index/storage.rs rust/src/native_core/text_facts.rs tests/test_native_scope_index.py
git commit -m "refactor: 建立 Rust scope facts 契约"
```

Expected: commit succeeds.

## Task 3: Python Adapter Consumes Contract Versions

**Files:**
- Modify: `app/native_scope_index.py`
- Modify: `tests/test_native_scope_index.py`

- [ ] **Step 1: Add Python dataclasses for contract versions**

Modify `app/native_scope_index.py`:

```python
@dataclass(frozen=True, slots=True)
class NativeContractVersions:
    """Rust scope/index 输出的契约版本集合。"""

    rust_scope_facts: int
    parser: int
    source_branch: int
    text_fact_schema: int
```

Add `contract_versions: NativeContractVersions` to:

- `NativeScopeIndexResult`
- `NativeRuleCandidatesResult`
- `NativeScopeGateResult`

- [ ] **Step 2: Add strict reader**

Add this helper in `app/native_scope_index.py`:

```python
def _read_contract_versions(result: JsonObject, label: str) -> NativeContractVersions:
    """读取 Rust scope/index 契约版本集合。"""
    raw_versions = ensure_json_object(result["contract_versions"], f"{label}.contract_versions")
    return NativeContractVersions(
        rust_scope_facts=_read_int(raw_versions, "rust_scope_facts", f"{label}.contract_versions"),
        parser=_read_int(raw_versions, "parser", f"{label}.contract_versions"),
        source_branch=_read_int(raw_versions, "source_branch", f"{label}.contract_versions"),
        text_fact_schema=_read_int(raw_versions, "text_fact_schema", f"{label}.contract_versions"),
    )
```

Then call it in all three native result constructors.

- [ ] **Step 3: Export the dataclass**

Add `NativeContractVersions` to `__all__` in `app/native_scope_index.py`.

- [ ] **Step 4: Run adapter tests**

Run:

```powershell
uv run pytest tests/test_native_scope_index.py::test_native_scope_index_outputs_contract_versions -q
```

Expected: PASS.

- [ ] **Step 5: Run type checker for adapter**

Run:

```powershell
uv run basedpyright app/native_scope_index.py tests/test_native_scope_index.py
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add app/native_scope_index.py tests/test_native_scope_index.py
git commit -m "refactor: 让 Python 消费 native 契约版本"
```

Expected: commit succeeds.

## Task 4: Text Index Metadata Stores Real Gate Facts

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/records.py`
- Modify: `app/persistence/text_index_records.py`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Test: `tests/test_persistence.py`
- Test: `tests/test_text_index.py`
- Test: `tests/test_native_scope_index.py`

- [ ] **Step 1: Write failing persistence tests**

Add to `tests/test_text_index.py`:

```python
async def test_text_index_metadata_rejects_prechecked_passed_shortcut(temp_game_session: TargetGameSession) -> None:
    raw = '{"workflow_gate_prechecked:plugin_source_text":"passed"}'

    with pytest.raises(RuntimeError, match="当前文本范围索引不再接受 workflow_gate_prechecked"):
        _decode_workflow_gate_scope_hashes(raw)
```

Add to `tests/test_persistence.py`:

```python
async def test_text_index_metadata_round_trips_contract_gate_facts(temp_game_session: TargetGameSession) -> None:
    metadata = TextIndexMetadata(
        source_snapshot_fingerprint="source-v1",
        rules_fingerprint="rules-v1",
        item_count=0,
        workflow_gate_scope_hashes={},
        workflow_gate_facts={
            "plugin_source_text": {
                "source_branch": "plugin_source_text",
                "status": "pass",
                "scope_hash": "a" * 64,
                "error_codes": [],
                "stale_reasons": [],
            }
        },
        rust_contract_version=1,
        parser_contract_version=1,
        source_branch_contract_version=1,
        text_fact_schema_version=2,
        created_at="2026-06-11T00:00:00+00:00",
    )
    await temp_game_session.replace_text_index(metadata=metadata, items=[])

    saved = await temp_game_session.read_text_index_metadata()

    assert saved is not None
    assert saved.workflow_gate_facts["plugin_source_text"]["status"] == "pass"
    assert saved.rust_contract_version == 1
```

Run:

```powershell
uv run pytest tests/test_text_index.py::test_text_index_metadata_rejects_prechecked_passed_shortcut tests/test_persistence.py::test_text_index_metadata_round_trips_contract_gate_facts -q
```

Expected: FAIL because metadata fields and decoder behavior do not exist yet.

- [ ] **Step 2: Update SQLite current schema**

Modify `app/persistence/schema/current.sql` and `app/persistence/sql.py`:

- increment `CURRENT_SCHEMA_VERSION` from `17` to `18`;
- add these columns to `text_index_meta`:

```sql
workflow_gate_facts          TEXT NOT NULL,
rust_contract_version        INTEGER NOT NULL,
parser_contract_version      INTEGER NOT NULL,
source_branch_contract_version INTEGER NOT NULL,
text_fact_schema_version     INTEGER NOT NULL
```

Keep `workflow_gate_scope_hashes` only as a migration bridge inside the current replacement payload until all readers are migrated. It must no longer accept `workflow_gate_prechecked:*`.

- [ ] **Step 3: Update TextIndexMetadata record**

Modify `app/persistence/records.py` so `TextIndexMetadata` has:

```python
workflow_gate_facts: dict[str, JsonObject]
rust_contract_version: int
parser_contract_version: int
source_branch_contract_version: int
text_fact_schema_version: int
```

Use existing project JSON aliases from `app.rmmz.text_rules` for `JsonObject`.

- [ ] **Step 4: Update Python metadata persistence**

Modify `app/persistence/text_index_records.py`:

- remove `TEXT_INDEX_WORKFLOW_GATE_PRECHECK_PREFIX`;
- remove `TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE`;
- make `_decode_workflow_gate_scope_hashes()` reject any key beginning with `workflow_gate_prechecked:`;
- add `_encode_workflow_gate_facts()` and `_decode_workflow_gate_facts()` with strict object validation;
- update `replace_text_index()`, `read_text_index_metadata()`, and `update_text_index_workflow_gate_scope_hashes()` callers to write/read contract fields.

The rejection message must include:

```text
当前文本范围索引不再接受 workflow_gate_prechecked
```

- [ ] **Step 5: Update Rust storage schema version and writes**

Modify `rust/src/native_core/scope_index/storage.rs`:

- increment `CURRENT_SCHEMA_VERSION` to `18`;
- update insert/select SQL to include the new columns;
- serialize `TextIndexContractFacts.gate_facts` into `workflow_gate_facts`;
- return `rust_contract_version`, `parser_contract_version`, `source_branch_contract_version`, and `text_fact_schema_version` in storage inspect/write/rebuild outputs.

- [ ] **Step 6: Update Rust rebuild gate facts**

Modify `rust/src/native_core/scope_index/rebuild.rs` so `build_workflow_gate_scope_hashes()` no longer writes:

```rust
"workflow_gate_prechecked:plugin_source_text" => "passed"
"workflow_gate_prechecked:nonstandard_data" => "passed"
```

Instead, build gate facts for `plugin_source_text` and `nonstandard_data` with `GateStatus::Pass` only when Rust has current facts for the branch.

- [ ] **Step 7: Run targeted metadata tests**

Run:

```powershell
uv run pytest tests/test_text_index.py::test_text_index_metadata_rejects_prechecked_passed_shortcut tests/test_persistence.py::test_text_index_metadata_round_trips_contract_gate_facts tests/test_native_scope_index.py -q
```

Expected: PASS.

- [ ] **Step 8: Run Rust storage tests**

Run:

```powershell
cargo test -p att-mz-native scope_index::storage -- --nocapture
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

Run:

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py app/persistence/records.py app/persistence/text_index_records.py rust/src/native_core/scope_index/storage.rs rust/src/native_core/scope_index/rebuild.rs tests/test_persistence.py tests/test_text_index.py tests/test_native_scope_index.py
git commit -m "refactor: 让文本索引保存真实 gate facts"
```

Expected: commit succeeds.

## Task 5: Indexed Gate Consumers Reject Old Metadata

**Files:**
- Modify: `app/application/flow_gate.py`
- Modify: `app/application/handler.py`
- Modify: `app/text_index.py`
- Modify: `tests/test_workflow_gate.py`
- Modify: `tests/test_agent_toolkit_workflow_gate.py`
- Modify: `tests/test_agent_toolkit_quality_report.py`

- [ ] **Step 1: Write failing indexed gate tests**

Add to `tests/test_agent_toolkit_workflow_gate.py`:

```python
async def test_indexed_workflow_gate_rejects_old_prechecked_metadata(agent_workspace_fixture: AgentWorkspaceFixture) -> None:
    session = agent_workspace_fixture.session
    await session.update_text_index_workflow_gate_scope_hashes(
        {"workflow_gate_prechecked:plugin_source_text": "passed"}
    )

    with pytest.raises(WorkflowGateError, match="重新生成当前文本范围索引"):
        await agent_workspace_fixture.service.translate(limit=1)
```

Add to `tests/test_agent_toolkit_quality_report.py`:

```python
async def test_quality_report_consumes_contract_gate_facts(agent_workspace_fixture: AgentWorkspaceFixture) -> None:
    await agent_workspace_fixture.rebuild_text_index()

    report = await agent_workspace_fixture.service.quality_report(json_output=True)

    assert report.workflow_gate["source"] == "rust_text_index_gate_facts"
    assert "workflow_gate_prechecked" not in json.dumps(report.workflow_gate, ensure_ascii=False)
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_indexed_workflow_gate_rejects_old_prechecked_metadata tests/test_agent_toolkit_quality_report.py::test_quality_report_consumes_contract_gate_facts -q
```

Expected: FAIL until indexed gate consumers are migrated.

- [ ] **Step 2: Add gate fact reader**

In `app/text_index.py`, add a reader that returns validated gate facts:

```python
@dataclass(frozen=True, slots=True)
class TextIndexGateFacts:
    """当前文本索引保存的 Rust gate facts。"""

    source: str
    facts: dict[str, JsonObject]
    rust_contract_version: int
    parser_contract_version: int
    source_branch_contract_version: int
    text_fact_schema_version: int
```

Add:

```python
async def read_current_text_index_gate_facts(session: TargetGameSession) -> TextIndexGateFacts:
    """读取并校验当前文本索引 gate facts。"""
```

This function must raise a user-facing error when metadata is absent, contract versions are old, or old precheck markers are present.

- [ ] **Step 3: Replace empty plugin/nonstandard gate arrays in handler**

Modify `app/application/handler.py` at translate and quality/write-back gate sites. Replace:

```python
plugin_source_rule_gate_errors=[]
nonstandard_data_rule_gate_errors=[]
```

with gate errors derived from `read_current_text_index_gate_facts()`. The mapped source should be `rust_text_index_gate_facts`.

- [ ] **Step 4: Keep Python full-scope gate only for non-indexed entry**

Modify `app/application/flow_gate.py`:

- `collect_workflow_gate_errors()` remains for full current scope calls.
- `collect_indexed_workflow_gate_errors()` must require validated Rust gate facts for plugin source and nonstandard data.
- It must not silently accept empty lists for source branches covered by text index.

- [ ] **Step 5: Run indexed gate tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_quality_report.py tests/test_workflow_gate.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add app/application/flow_gate.py app/application/handler.py app/text_index.py tests/test_workflow_gate.py tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_quality_report.py
git commit -m "refactor: 让索引命令消费 Rust gate facts"
```

Expected: commit succeeds.

## Task 6: Runtime Plugin Source Scan Cache Contract

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/rule_records.py`
- Modify: `app/plugin_source_text/runtime_audit.py`
- Modify: `app/plugin_source_text/native_scan.py`
- Modify: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Write failing scan cache contract test**

Add to `tests/test_agent_toolkit_rule_import.py` near active runtime scan cache tests:

```python
async def test_plugin_source_runtime_scan_cache_invalidates_contract_change(service_with_plugin_source_runtime: AgentToolkitService) -> None:
    first_report = await service_with_plugin_source_runtime.audit_active_runtime(json_output=True)
    assert first_report.summary["active_runtime_scan_cache_rescan_file_count"] > 0

    async with service_with_plugin_source_runtime.session.connection.execute(
        "UPDATE plugin_source_runtime_scan_cache SET parser_contract_version = parser_contract_version - 1"
    ):
        pass
    await service_with_plugin_source_runtime.session.connection.commit()

    second_report = await service_with_plugin_source_runtime.audit_active_runtime(json_output=True)

    assert second_report.summary["active_runtime_scan_cache_stale_file_count"] > 0
    assert second_report.summary["active_runtime_scan_cache_rescan_file_count"] > 0
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_plugin_source_runtime_scan_cache_invalidates_contract_change -q
```

Expected: FAIL because cache rows do not store parser/native/audit contract versions.

- [ ] **Step 2: Extend scan cache schema**

Modify `plugin_source_runtime_scan_cache` in `app/persistence/schema/current.sql` and `app/persistence/sql.py`:

```sql
rust_contract_version INTEGER NOT NULL,
parser_contract_version INTEGER NOT NULL,
audit_contract_version INTEGER NOT NULL
```

Increment `CURRENT_SCHEMA_VERSION` if Task 4 has not already done it in the current execution branch. If Task 4 already set version 18, use version 19 for this schema change.

- [ ] **Step 3: Update cache record model and queries**

Modify `app/persistence/rule_records.py` so cache records include:

```python
rust_contract_version: int
parser_contract_version: int
audit_contract_version: int
```

Update read and replace methods. A row is stale when any stored version differs from current constants exposed by `app/native_scope_index.py` and `app/plugin_source_text/runtime_audit.py`.

- [ ] **Step 4: Add current audit contract constant**

In `app/plugin_source_text/runtime_audit.py`, add:

```python
PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION = 1
```

Use it when writing cache rows and validating cache hits.

- [ ] **Step 5: Run scan cache tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files tests/test_agent_toolkit_rule_import.py::test_plugin_source_runtime_scan_cache_invalidates_contract_change -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py app/persistence/rule_records.py app/plugin_source_text/runtime_audit.py app/plugin_source_text/native_scan.py tests/test_agent_toolkit_rule_import.py
git commit -m "refactor: 为插件源码运行缓存加入契约校验"
```

Expected: commit succeeds.

## Task 7: Plugin Source Rust Primary Facts

**Files:**
- Modify: `rust/src/native_core/scope_index/plugin_source.rs`
- Modify: `rust/src/native_core/scope_index/mod.rs`
- Modify: `app/plugin_source_text/native_scan.py`
- Modify: `app/plugin_source_text/models.py`
- Modify: `app/plugin_source_text/importer.py`
- Modify: `app/plugin_source_text/rules.py`
- Test: `tests/test_plugin_source_text.py`
- Test: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Write Rust plugin source facts tests**

Add tests in `rust/src/native_core/scope_index/plugin_source.rs`:

```rust
#[test]
fn plugin_source_scan_outputs_selector_facts_and_review_summary() {
    let result = scan_plugin_source_fixture_with_rules();

    assert_eq!(result.review_summary.total_selector_count, 2);
    assert_eq!(result.review_summary.excluded_selector_count, 1);
    assert_eq!(result.selector_facts[0].stale_reason, None);
    assert_eq!(result.risk_summary.high_risk, false);
}

#[test]
fn plugin_source_scan_reports_filtered_selector_reason() {
    let result = scan_plugin_source_fixture_with_filtered_text();

    assert_eq!(
        result.selector_facts[0].stale_reason.as_ref().map(|reason| reason.code.as_str()),
        Some("selector_filtered")
    );
}
```

Run:

```powershell
cargo test -p att-mz-native plugin_source -- --nocapture
```

Expected: FAIL until selector facts and review summary are implemented.

- [ ] **Step 2: Extend Rust plugin source output**

Modify `plugin_source.rs` output structs to include:

```rust
selector_facts: Vec<PluginSourceSelectorFact>,
review_summary: PluginSourceReviewSummary,
risk_summary: PluginSourceRiskSummary,
scope_hash: String,
```

Each selector fact must include:

```rust
file_name: String,
selector: String,
role: String,
active: bool,
file_hash: String,
source_text_hash: String,
stale_reason: Option<StaleReason>,
```

Roles must include `translated`, `excluded`, and `filtered`.

- [ ] **Step 3: Read selector facts in Python adapter**

Modify `app/plugin_source_text/native_scan.py` so `build_native_plugin_source_scan()` consumes Rust `selector_facts`, `review_summary`, `risk_summary`, and `scope_hash` instead of recomputing risk from file payloads.

Delete or make private non-production-only any Python risk calculation that duplicates Rust risk summary. Public reports must use Rust values.

- [ ] **Step 4: Migrate importer and rules to Rust facts**

Modify `app/plugin_source_text/importer.py` and `app/plugin_source_text/rules.py`:

- selector membership comes from Rust `selector_facts`;
- stale reason comes from Rust `stale_reason`;
- review coverage comes from Rust `review_summary`;
- `excluded_selectors` are validated against current Rust selector facts, not only stored database rules.

- [ ] **Step 5: Add excluded-only lifecycle test**

Add to `tests/test_agent_toolkit_rule_import.py`:

```python
async def test_plugin_source_excluded_only_rule_validates_current_selector_facts(plugin_source_rule_fixture: PluginSourceRuleFixture) -> None:
    selector = plugin_source_rule_fixture.current_selector
    import_payload = plugin_source_rule_fixture.import_payload(selectors=[], excluded_selectors=[selector])

    await plugin_source_rule_fixture.service.import_plugin_source_rules(import_payload)
    await plugin_source_rule_fixture.service.rebuild_text_index()
    report = await plugin_source_rule_fixture.service.quality_report(json_output=True)

    assert report.workflow_gate["source"] == "rust_text_index_gate_facts"
    assert report.workflow_gate["plugin_source_text"]["status"] == "pass"
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_plugin_source_excluded_only_rule_validates_current_selector_facts -q
```

Expected: PASS after implementation.

- [ ] **Step 6: Run plugin source tests**

Run:

```powershell
uv run pytest tests/test_plugin_source_text.py tests/test_agent_toolkit_rule_import.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

Run:

```powershell
git add rust/src/native_core/scope_index/plugin_source.rs rust/src/native_core/scope_index/mod.rs app/plugin_source_text/native_scan.py app/plugin_source_text/models.py app/plugin_source_text/importer.py app/plugin_source_text/rules.py tests/test_plugin_source_text.py tests/test_agent_toolkit_rule_import.py
git commit -m "refactor: 由 Rust 输出插件源码规则事实"
```

Expected: commit succeeds.

## Task 8: Remove Python Plugin Source Production Fact Sources

**Files:**
- Modify: `app/plugin_source_text/extraction.py`
- Modify: `app/plugin_source_text/native_scan.py`
- Modify: `app/plugin_source_text/__init__.py`
- Modify: `app/application/flow_gate.py`
- Modify: `tests/test_agent_toolkit_rule_import.py`
- Modify: `tests/test_agent_toolkit_workflow_gate.py`

- [ ] **Step 1: Add production-path guard tests**

Add to `tests/test_agent_toolkit_rule_import.py`:

```python
async def test_plugin_source_public_commands_do_not_construct_python_extraction(monkeypatch: pytest.MonkeyPatch, plugin_source_rule_fixture: PluginSourceRuleFixture) -> None:
    def fail_constructor(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("公共插件源码规则命令不应构造 PluginSourceTextExtraction")

    monkeypatch.setattr(
        "app.plugin_source_text.extraction.PluginSourceTextExtraction",
        fail_constructor,
        raising=True,
    )

    await plugin_source_rule_fixture.service.export_plugin_source_ast_map()
    await plugin_source_rule_fixture.service.validate_plugin_source_rules(plugin_source_rule_fixture.valid_import_payload())
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_plugin_source_public_commands_do_not_construct_python_extraction -q
```

Expected: PASS after public paths consume Rust facts.

- [ ] **Step 2: Remove production export of Python extractor**

Modify `app/plugin_source_text/__init__.py` so `PluginSourceTextExtraction` is not exported as a current production fact source. If a test-only helper remains, name it with a private prefix and keep it out of `__all__`.

- [ ] **Step 3: Make Python extraction non-production or delete it**

Delete `PluginSourceTextExtraction` when no production or test caller needs it. If deletion is too large for this task, leave a private test-only function in `app/plugin_source_text/extraction.py` with a docstring:

```python
"""仅供旧夹具读取历史样本，不参与当前生产事实生成。"""
```

Do not leave public constructors or package exports.

- [ ] **Step 4: Update gate to consume Rust plugin source facts**

Modify `app/application/flow_gate.py`:

- `_plugin_source_rule_gate_errors()` must use Rust plugin source contract facts;
- it must not call `collect_plugin_source_review_coverage()` if that function still computes coverage in Python;
- stale and coverage errors must come from Rust error codes.

- [ ] **Step 5: Run plugin source gate tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_rule_import.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 8**

Run:

```powershell
git add app/plugin_source_text/extraction.py app/plugin_source_text/native_scan.py app/plugin_source_text/__init__.py app/application/flow_gate.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workflow_gate.py
git commit -m "refactor: 删除插件源码 Python 生产事实源"
```

Expected: commit succeeds.

## Task 9: Nonstandard Data And Path Template Rust Facts

**Files:**
- Modify: `rust/src/native_core/scope_index/nonstandard_data.rs`
- Modify: `rust/src/native_core/scope_index/plugin_config.rs`
- Modify: `rust/src/native_core/scope_index/event_commands.rs`
- Modify: `app/native_scope_index.py`
- Modify: `app/nonstandard_data/extraction.py`
- Modify: `app/nonstandard_data/rules.py`
- Modify: `app/text_scope/rule_hits.py`
- Test: `tests/test_nonstandard_data.py`
- Test: `tests/test_rmmz_note_nonstandard_data.py`
- Test: `tests/test_agent_toolkit_rule_import.py`

- [ ] **Step 1: Write Rust path template tests**

Add tests in `rust/src/native_core/scope_index/nonstandard_data.rs`:

```rust
#[test]
fn nonstandard_data_outputs_rule_hit_details_and_translation_prefixes() {
    let output = scan_nonstandard_data_fixture_with_rules();

    assert_eq!(output.hit_details[0].path_template, "$['items'][0]['name']");
    assert_eq!(output.hit_details[0].location_path, "Custom.json/items/0/name");
    assert_eq!(output.translation_prefixes, vec!["Custom.json/items/0"]);
}

#[test]
fn invalid_path_template_returns_stable_error_code() {
    let error = scan_nonstandard_data_invalid_path_template();

    assert_eq!(error.code, "path_template_invalid");
}
```

Run:

```powershell
cargo test -p att-mz-native nonstandard_data -- --nocapture
```

Expected: FAIL until Rust outputs rule hit details and stable errors.

- [ ] **Step 2: Extend Rust nonstandard data output**

Modify `nonstandard_data.rs` so scan summary includes:

```json
{
  "hit_details": [],
  "rule_summaries": [],
  "translation_prefixes": [],
  "stale_reasons": []
}
```

Use the same path template parser for nonstandard data, plugin config, and event commands. The parser must return stable error code `path_template_invalid` for invalid templates.

- [ ] **Step 3: Replace Python rule hit expansion**

Modify `app/text_scope/rule_hits.py`:

- remove production use of `collect_nonstandard_data_rule_hits`;
- read Rust `rule_hit_details` from native scan output;
- keep Python only for converting Rust JSON into current report objects.

Modify `app/nonstandard_data/extraction.py` so `NonstandardDataTextExtraction` no longer expands current rule hits for production.

- [ ] **Step 4: Update nonstandard rule validation**

Modify `app/nonstandard_data/rules.py`:

- validate/import use Rust `hit_details`, `translation_prefixes`, and `stale_reasons`;
- stale file hash checks must be backed by Rust source snapshot facts;
- Python must not walk JSON leaves to create an independent current fact set.

- [ ] **Step 5: Add lifecycle test**

Add to `tests/test_nonstandard_data.py`:

```python
async def test_nonstandard_data_import_cold_rebuild_and_quality_report_use_rust_rule_hits(nonstandard_data_fixture: NonstandardDataFixture) -> None:
    await nonstandard_data_fixture.service.import_nonstandard_data_rules(nonstandard_data_fixture.valid_import_payload())
    await nonstandard_data_fixture.service.rebuild_text_index()

    report = await nonstandard_data_fixture.service.quality_report(json_output=True)

    assert report.workflow_gate["nonstandard_data"]["status"] == "pass"
    assert report.workflow_gate["nonstandard_data"]["source"] == "rust_text_index_gate_facts"
```

Run:

```powershell
uv run pytest tests/test_nonstandard_data.py::test_nonstandard_data_import_cold_rebuild_and_quality_report_use_rust_rule_hits -q
```

Expected: PASS after implementation.

- [ ] **Step 6: Run nonstandard data tests**

Run:

```powershell
uv run pytest tests/test_nonstandard_data.py tests/test_rmmz_note_nonstandard_data.py tests/test_agent_toolkit_rule_import.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 9**

Run:

```powershell
git add rust/src/native_core/scope_index/nonstandard_data.rs rust/src/native_core/scope_index/plugin_config.rs rust/src/native_core/scope_index/event_commands.rs app/native_scope_index.py app/nonstandard_data/extraction.py app/nonstandard_data/rules.py app/text_scope/rule_hits.py tests/test_nonstandard_data.py tests/test_rmmz_note_nonstandard_data.py tests/test_agent_toolkit_rule_import.py
git commit -m "refactor: 由 Rust 输出非标准 data 规则命中事实"
```

Expected: commit succeeds.

## Task 10: Note Tag Rule Validation Contract

**Files:**
- Modify: `rust/src/native_core/scope_index/note_tags.rs`
- Modify: `rust/src/native_core/scope_index/mod.rs`
- Modify: `app/native_note_tag_scan.py`
- Modify: `app/native_scope_index.py`
- Modify: `app/application/flow_gate.py`
- Modify: `tests/test_agent_toolkit_rule_import.py`
- Modify: `tests/test_rmmz_note_nonstandard_data.py`

- [ ] **Step 1: Write Rust Note tag validation tests**

Add tests in `rust/src/native_core/scope_index/note_tags.rs`:

```rust
#[test]
fn note_tag_validation_outputs_rule_coverage_and_scope_hash() {
    let output = validate_note_tag_rules_fixture();

    assert_eq!(output.status, "pass");
    assert_eq!(output.covered_count, output.candidate_count);
    assert!(!output.scope_hash.is_empty());
}

#[test]
fn note_tag_validation_reports_unmatched_rule_code() {
    let output = validate_note_tag_rules_with_missing_tag_fixture();

    assert_eq!(output.status, "fail");
    assert_eq!(output.errors[0].code, "note_tag_rule_unmatched");
}
```

Run:

```powershell
cargo test -p att-mz-native note_tags -- --nocapture
```

Expected: FAIL until Rust Note tag validation facts are implemented.

- [ ] **Step 2: Implement native Note tag validation output**

Modify `note_tags.rs` and `mod.rs` so `scan_rule_candidates` or a dedicated native entry outputs:

```json
{
  "status": "pass",
  "scope_hash": "64-hex",
  "candidate_count": 0,
  "covered_count": 0,
  "translatable_hit_count": 0,
  "errors": []
}
```

Errors must use stable codes:

- `note_tag_rule_unmatched`
- `note_tag_source_changed`
- `note_tag_contract_changed`

- [ ] **Step 3: Migrate Python Note tag adapter**

Modify `app/native_note_tag_scan.py`:

- keep payload construction and JSON coercion;
- consume Rust validation facts;
- remove Python precise source matching and translatable-count business judgment from production paths.

- [ ] **Step 4: Migrate workflow gate**

Modify `app/application/flow_gate.py` so empty Note tag confirmation scope hash and stale checks come from Rust Note tag facts, not Python helper `note_tag_rule_scope_hash_for_text_rules()`.

- [ ] **Step 5: Add Note tag lifecycle test**

Add to `tests/test_agent_toolkit_rule_import.py`:

```python
async def test_note_tag_import_cold_rebuild_and_write_back_gate_use_rust_validation(note_tag_rule_fixture: NoteTagRuleFixture) -> None:
    await note_tag_rule_fixture.service.import_note_tag_rules(note_tag_rule_fixture.valid_import_payload())
    await note_tag_rule_fixture.service.rebuild_text_index()

    report = await note_tag_rule_fixture.service.write_back(dry_run=True, json_output=True)

    assert report.workflow_gate["note_tag"]["status"] == "pass"
    assert report.workflow_gate["note_tag"]["source"] == "rust_text_index_gate_facts"
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_note_tag_import_cold_rebuild_and_write_back_gate_use_rust_validation -q
```

Expected: PASS after implementation.

- [ ] **Step 6: Commit Task 10**

Run:

```powershell
git add rust/src/native_core/scope_index/note_tags.rs rust/src/native_core/scope_index/mod.rs app/native_note_tag_scan.py app/native_scope_index.py app/application/flow_gate.py tests/test_agent_toolkit_rule_import.py tests/test_rmmz_note_nonstandard_data.py
git commit -m "refactor: 由 Rust 验证 Note 标签规则"
```

Expected: commit succeeds.

## Task 11: Scope Hash Single Source

**Files:**
- Modify: `app/rule_review.py`
- Modify: `app/application/flow_gate.py`
- Modify: `app/native_scope_index.py`
- Modify: `tests/test_agent_toolkit_rule_import.py`
- Modify: `tests/test_agent_toolkit_workflow_gate.py`
- Modify: `tests/agent_toolkit_contract_fixtures.py`
- Modify: `tests/rmmz_writeback_contract_fixtures.py`

- [ ] **Step 1: Add guard test for Python scope hash helpers**

Add to `tests/test_agent_toolkit_rule_import.py`:

```python
def test_rule_review_no_longer_exports_python_scope_hash_helpers() -> None:
    import app.rule_review as rule_review

    assert not hasattr(rule_review, "plugin_rule_scope_hash")
    assert not hasattr(rule_review, "note_tag_rule_scope_hash_for_candidates")
```

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_rule_review_no_longer_exports_python_scope_hash_helpers -q
```

Expected: FAIL until Python scope hash helpers are removed or made non-public.

- [ ] **Step 2: Add Rust scope hash accessors to adapter**

Modify `app/native_scope_index.py` so current Rust scan results expose scope hash for:

- plugin source;
- Note tags;
- event commands;
- MV virtual namebox;
- normal placeholders;
- structured placeholders;
- nonstandard data.

The Python adapter may read the hash from native JSON, but must not compute the hash itself.

- [ ] **Step 3: Migrate flow gate empty-rule checks**

Modify `app/application/flow_gate.py`:

- remove imports of Python scope hash helpers from `app.rule_review`;
- use Rust/native scope hash facts from `app/native_scope_index.py`;
- keep `ensure_empty_rule_confirmed()` as user confirmation logic only.

- [ ] **Step 4: Remove public Python scope hash helpers**

Modify `app/rule_review.py`:

- delete production helper functions that compute scope hash from Python payloads;
- keep domain constants and review-decision data structures if still needed;
- remove deleted helpers from `__all__`.

- [ ] **Step 5: Update tests and fixtures**

Modify `tests/agent_toolkit_contract_fixtures.py` and `tests/rmmz_writeback_contract_fixtures.py` so fixtures obtain scope hash from native scan facts or from prebuilt current text facts, not Python helper functions.

- [ ] **Step 6: Run scope hash tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workflow_gate.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 11**

Run:

```powershell
git add app/rule_review.py app/application/flow_gate.py app/native_scope_index.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workflow_gate.py tests/agent_toolkit_contract_fixtures.py tests/rmmz_writeback_contract_fixtures.py
git commit -m "refactor: 收束 scope hash 到 Rust 事实源"
```

Expected: commit succeeds.

## Task 12: Remove Remaining Public Python Oracles

**Files:**
- Modify: `app/agent_toolkit/placeholder_scan.py`
- Modify: `app/agent_toolkit/__init__.py`
- Modify: `app/plugin_source_text/__init__.py`
- Modify: `app/nonstandard_data/__init__.py`
- Modify: `tests/test_agent_toolkit_coverage.py`
- Modify: `tests/test_agent_toolkit_manual_import.py`
- Modify: `tests/test_native_adapters.py`

- [ ] **Step 1: Scan current public old-path exports**

Run:

```powershell
rg -n 'scan_placeholder_candidates|PluginSourceTextExtraction|NonstandardDataTextExtraction|collect_nonstandard_data_rule_hits|__all__' app tests
```

Expected: output lists all remaining public old-path exports and test callers.

- [ ] **Step 2: Add public API removal tests**

Add to `tests/test_native_adapters.py`:

```python
def test_old_python_scanners_are_not_public_agent_toolkit_api() -> None:
    import app.agent_toolkit as agent_toolkit
    import app.plugin_source_text as plugin_source_text
    import app.nonstandard_data as nonstandard_data

    assert not hasattr(agent_toolkit, "scan_placeholder_candidates")
    assert not hasattr(plugin_source_text, "PluginSourceTextExtraction")
    assert not hasattr(nonstandard_data, "NonstandardDataTextExtraction")
```

Run:

```powershell
uv run pytest tests/test_native_adapters.py::test_old_python_scanners_are_not_public_agent_toolkit_api -q
```

Expected: FAIL until exports are removed.

- [ ] **Step 3: Remove public exports and migrate callers**

Modify:

- `app/agent_toolkit/__init__.py`
- `app/agent_toolkit/placeholder_scan.py`
- `app/plugin_source_text/__init__.py`
- `app/nonstandard_data/__init__.py`

Remove old scanner/extractor exports from `__all__`. Migrate tests to service-level or native adapter entry points.

- [ ] **Step 4: Replace Python oracle parity tests**

Modify tests that compare native to Python old implementations. Replace comparisons like:

```python
assert native_result == python_result
```

with contract assertions:

```python
assert native_result.schema_version >= 1
assert native_result.contract_versions.rust_scope_facts >= 1
assert native_result.candidate_summary
```

For empty fixtures, assert explicit empty contract fields rather than Python oracle equality.

- [ ] **Step 5: Run public API and adapter tests**

Run:

```powershell
uv run pytest tests/test_native_adapters.py tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_manual_import.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 12**

Run:

```powershell
git add app/agent_toolkit/placeholder_scan.py app/agent_toolkit/__init__.py app/plugin_source_text/__init__.py app/nonstandard_data/__init__.py tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_manual_import.py tests/test_native_adapters.py
git commit -m "refactor: 移除旧 Python 扫描器公共入口"
```

Expected: commit succeeds.

## Task 13: Lifecycle Regression Tests

**Files:**
- Modify: `tests/test_agent_toolkit_rule_import.py`
- Modify: `tests/test_agent_toolkit_workflow_gate.py`
- Modify: `tests/test_agent_toolkit_quality_report.py`
- Modify: `tests/test_rmmz_write_plan.py`
- Modify: `tests/current_text_fact_scope.py`
- Modify: `tests/_native_write_plan_helper.py`

- [ ] **Step 1: Add plugin source full lifecycle test**

Add to `tests/test_agent_toolkit_rule_import.py`:

```python
async def test_plugin_source_import_cold_rebuild_quality_and_write_back_share_rust_facts(plugin_source_rule_fixture: PluginSourceRuleFixture) -> None:
    await plugin_source_rule_fixture.service.import_plugin_source_rules(plugin_source_rule_fixture.valid_import_payload())
    await plugin_source_rule_fixture.service.rebuild_text_index()

    quality_report = await plugin_source_rule_fixture.service.quality_report(json_output=True)
    write_report = await plugin_source_rule_fixture.service.write_back(dry_run=True, json_output=True)

    assert quality_report.workflow_gate["plugin_source_text"]["source"] == "rust_text_index_gate_facts"
    assert write_report.workflow_gate["plugin_source_text"]["source"] == "rust_text_index_gate_facts"
    assert quality_report.workflow_gate["plugin_source_text"]["scope_hash"] == write_report.workflow_gate["plugin_source_text"]["scope_hash"]
```

- [ ] **Step 2: Add nonstandard data full lifecycle test**

Add to `tests/test_nonstandard_data.py`:

```python
async def test_nonstandard_data_import_cold_rebuild_translate_and_write_back_share_rust_facts(nonstandard_data_fixture: NonstandardDataFixture) -> None:
    await nonstandard_data_fixture.service.import_nonstandard_data_rules(nonstandard_data_fixture.valid_import_payload())
    await nonstandard_data_fixture.service.rebuild_text_index()

    translate_report = await nonstandard_data_fixture.service.translate(limit=1, json_output=True)
    write_report = await nonstandard_data_fixture.service.write_back(dry_run=True, json_output=True)

    assert translate_report.workflow_gate["nonstandard_data"]["source"] == "rust_text_index_gate_facts"
    assert write_report.workflow_gate["nonstandard_data"]["source"] == "rust_text_index_gate_facts"
```

- [ ] **Step 3: Add Note tag full lifecycle test**

Add to `tests/test_agent_toolkit_rule_import.py`:

```python
async def test_note_tag_import_cold_rebuild_quality_and_write_back_share_rust_facts(note_tag_rule_fixture: NoteTagRuleFixture) -> None:
    await note_tag_rule_fixture.service.import_note_tag_rules(note_tag_rule_fixture.valid_import_payload())
    await note_tag_rule_fixture.service.rebuild_text_index()

    quality_report = await note_tag_rule_fixture.service.quality_report(json_output=True)
    write_report = await note_tag_rule_fixture.service.write_back(dry_run=True, json_output=True)

    assert quality_report.workflow_gate["note_tag"]["source"] == "rust_text_index_gate_facts"
    assert write_report.workflow_gate["note_tag"]["source"] == "rust_text_index_gate_facts"
```

- [ ] **Step 4: Remove hand-built current fact bypass**

Modify `tests/current_text_fact_scope.py` and `tests/_native_write_plan_helper.py`:

- helpers that need current text facts must call rebuild helpers or native text fact builders;
- helpers must not fabricate fact IDs, scope hash, or schema version in a way that bypasses Rust cold rebuild facts.

Add this assertion in any write-back helper test:

```python
assert helper_scope.source == "rust_cold_rebuild"
```

- [ ] **Step 5: Run lifecycle tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_quality_report.py tests/test_nonstandard_data.py tests/test_rmmz_write_plan.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 13**

Run:

```powershell
git add tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_quality_report.py tests/test_nonstandard_data.py tests/test_rmmz_write_plan.py tests/current_text_fact_scope.py tests/_native_write_plan_helper.py
git commit -m "test: 固定 Rust facts 跨命令生命周期"
```

Expected: commit succeeds.

## Task 14: Error Codes And User-Facing Mapping

**Files:**
- Modify: `app/application/errors.py`
- Modify: `app/application/flow_gate.py`
- Modify: `app/application/handler.py`
- Modify: `tests/test_workflow_gate.py`
- Modify: `tests/test_write_back_transactions.py`
- Modify: `tests/test_agent_toolkit_quality_report.py`

- [ ] **Step 1: Add error-code assertions**

Add tests that assert both code and message:

```python
async def test_write_back_reports_contract_stale_error_code(write_back_fixture: WriteBackFixture) -> None:
    await write_back_fixture.force_old_text_index_contract()

    report = await write_back_fixture.service.write_back(dry_run=True, json_output=True)

    assert report.errors[0]["code"] == "text_index_contract_changed"
    assert "重新生成当前文本范围索引" in report.errors[0]["message"]
```

Run:

```powershell
uv run pytest tests/test_write_back_transactions.py::test_write_back_reports_contract_stale_error_code -q
```

Expected: FAIL until error mapping exists.

- [ ] **Step 2: Normalize error mapping**

Modify `app/application/errors.py` or existing error mapping module so Rust codes map to user-facing Chinese messages:

- `text_index_contract_changed`
- `plugin_source_selector_filtered`
- `plugin_source_ast_missing`
- `nonstandard_data_rule_unmatched`
- `note_tag_rule_unmatched`
- `path_template_invalid`

Messages must explain: what happened, what is affected, and the next action.

- [ ] **Step 3: Remove broad Chinese regex assertions**

Update tests that only assert partial Chinese messages. Replace them with:

```python
assert error["code"] == "specific_stable_code"
assert "下一步" in error["message"]
```

- [ ] **Step 4: Run error mapping tests**

Run:

```powershell
uv run pytest tests/test_workflow_gate.py tests/test_write_back_transactions.py tests/test_agent_toolkit_quality_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 14**

Run:

```powershell
git add app/application/errors.py app/application/flow_gate.py app/application/handler.py tests/test_workflow_gate.py tests/test_write_back_transactions.py tests/test_agent_toolkit_quality_report.py
git commit -m "refactor: 固定 Rust facts 错误码映射"
```

Expected: commit succeeds.

## Task 15: Performance Evidence And Scan Budget Alignment

**Files:**
- Modify: `tests/test_scan_budget.py`
- Modify: `tests/scan_budget_contract.py`
- Create: `docs/records/performance/rust-primary-total-refactor-cli-timings.md`

- [ ] **Step 1: Update scan budget expectations**

Modify `tests/scan_budget_contract.py` so budgets describe:

- Rust facts source;
- expected scan count;
- cache invalidation path;
- command-level source branch coverage.

Do not use scan budget as performance success evidence.

- [ ] **Step 2: Run scan budget tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py -q
```

Expected: PASS.

- [ ] **Step 3: Collect real CLI timings**

Run the agreed local fixture command set. If no large local fixture is available, use the largest repository test fixture and state that limitation in the performance record.

Commands to collect:

```powershell
Measure-Command { uv run python main.py rebuild-text-index --config setting.example.toml --json }
Measure-Command { uv run python main.py quality-report --config setting.example.toml --json }
```

Run with default threads and with:

```powershell
$env:ATT_MZ_RUST_THREADS='2'
```

Record:

- command;
- fixture identity without real local path;
- total elapsed time;
- Rust stage timings if available;
- Python orchestration timings if available;
- scan count;
- configured Rust thread count;
- observed bottleneck and remaining risk.

- [ ] **Step 4: Write performance evidence**

Create `docs/records/performance/rust-primary-total-refactor-cli-timings.md`:

```markdown
# Rust 主路径总重构 CLI 性能证据

## 环境

## Fixture

## 命令结果

| 命令 | 线程 | 总耗时 | Rust 阶段耗时 | Python 编排耗时 | 扫描次数 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |

## 瓶颈归因

## 剩余风险
```

Use placeholders like `<项目目录>` only when showing command examples. Do not write private local paths.

- [ ] **Step 5: Commit Task 15**

Run:

```powershell
git add tests/test_scan_budget.py tests/scan_budget_contract.py docs/records/performance/rust-primary-total-refactor-cli-timings.md
git commit -m "test: 补充 Rust 主路径真实性能证据"
```

Expected: commit succeeds.

## Task 16: Full Verification

**Files:**
- Read: all modified files

- [ ] **Step 1: Run Rust formatting**

Run:

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
```

Expected: PASS.

- [ ] **Step 2: Run Rust clippy**

Run:

```powershell
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

Expected: PASS.

- [ ] **Step 3: Run Rust tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml
```

Expected: PASS.

- [ ] **Step 4: Run Python type check**

Run:

```powershell
uv run basedpyright
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 5: Run Python tests**

Run:

```powershell
uv run pytest
```

Expected: PASS.

- [ ] **Step 6: Run Skill protocol check if touched**

If any file under `skills/`, Skill generation scripts, README Skill mappings, or release packaging mappings changed, run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: PASS. If those files were not touched, record that this check was not applicable.

- [ ] **Step 7: Run final diff check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 8: Resolve any remaining tracked changes**

Run:

```powershell
git status --short
```

Expected: no output. If output remains, return to the task that owns those files, finish its targeted tests, and commit with that task's commit command. Do not make a catch-all final implementation commit that hides task ownership.

## Task 17: Final Delivery

**Files:**
- Read: `git status --short --branch`
- Read: `git log --oneline -n 10`

- [ ] **Step 1: Confirm clean worktree**

Run:

```powershell
git status --short --branch
```

Expected: no modified or untracked implementation files remain.

- [ ] **Step 2: Summarize completed stages**

Final delivery must state:

- completed phases 1 through 5;
- Rust contract files changed;
- Python fact-source files deleted or downgraded;
- tests added or changed;
- performance evidence path;
- verification commands and results;
- any checks not run, with reason and risk.

- [ ] **Step 3: Offer integration path**

If all verification passed, follow project branch completion workflow. If verification failed, do not merge or mark complete; summarize failing command, first failure, likely cause, and next action.

## Plan Self-Review

- Spec coverage: Tasks 2-3 cover Contract Foundation; Tasks 4-6 cover Gate + Metadata Lifecycle and cache contract; Tasks 7-8 cover Plugin Source Rust Primary Path; Tasks 9-10 cover Nonstandard Data + Path Template + Note Tag; Tasks 11-15 cover deletion, test退场, lifecycle and performance evidence; Task 16 covers final verification.
- P0/P1/P2 coverage: all 3 P0, 9 P1, and 9 P2 findings from the design mapping table are assigned to at least one task.
- Placeholder scan: red-flag implementation markers and incomplete sections were checked and removed.
- Type and path consistency: new Rust contract types are introduced before Python adapters consume them; metadata schema changes precede indexed gate consumers; old Python exports are removed only after Rust replacement facts and lifecycle tests exist.
