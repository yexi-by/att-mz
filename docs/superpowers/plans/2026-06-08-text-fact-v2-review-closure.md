# Text Fact v2 Review Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Text Fact Contract v2 review gaps by making saved translations use v2 fact identity end to end, removing production old fact reconstruction paths, and making the current runtime-literal contract explicit.

**Architecture:** `text_facts_v2.fact_id` becomes the saved-translation identity for migrated flows. Python remains the orchestration and report layer, but all current-source decisions are made from v2 fact rows or Rust/native candidate outputs. Rust write-back reads translations by `fact_id` and render parts, so `location_path` is only a user-facing locator and secondary index, not the correctness key.

**Tech Stack:** Python 3.14, pydantic v2, argparse, aiosqlite, pytest, basedpyright, Rust 2024, PyO3, maturin, rusqlite, rayon, serde_json, cargo fmt, clippy, cargo test.

---

## Scope Check

This plan is a corrective follow-up to the committed Text Fact Contract v2 refactor. It is intentionally breaking because the current database and workspace are test assets, and long-term correctness is more important than preserving an internal v1-shaped table layout.

This plan does not claim real-game performance success. Implementation must avoid obvious performance regressions by using indexed SQL joins, batch reads, Rust-side joins, no full Python text-scope rebuilds on migrated production paths, and existing configurable Rust thread pools. Real-game timing on the target project is a separate maintainer acceptance step after this plan is implemented.

Hard stop and return to design discussion if the implementation needs a v1/v2 dual saved-translation source, if `location_path` remains the primary saved-translation key for migrated flows, if write-back cannot resolve translations by `fact_id`, or if a migrated production command needs `TextScopeService.build()` to succeed.

## File Structure

- Modify `app/persistence/schema/current.sql`: bump schema version and make `translation_items` keyed by `fact_id`; add fact identity columns and indexes.
- Modify `app/persistence/sql.py`: mirror the schema, update translation SQL to insert/read/delete by `fact_id`, and keep path-based helpers only as secondary filters.
- Modify `app/rmmz/schema.py`: add excluded internal v2 identity fields to `TranslationItem` and `TranslationErrorItem` inputs where needed.
- Modify `app/persistence/translation_records.py`: require v2 identity for persisted translations, expose fact-id delete/read helpers, and preserve path helpers as secondary operations.
- Modify `app/persistence/run_records.py`: store quality/translation errors with `fact_id` when the error belongs to a v2 fact.
- Modify `app/text_facts.py`: attach v2 identity to `TranslationItem`, change all pending/translated/stale SQL to join by `fact_id`, and keep `location_path` only for display and path sampling.
- Modify `app/application/handler.py`: save translation results with fact identity and clear quality errors by fact identity.
- Modify `app/application/use_cases/translation_run.py`: preserve fact identity through dedupe expansion and error expansion.
- Modify `app/agent_toolkit/services/manual_translation.py`: import/export by `fact_id` and delete quality errors by fact identity.
- Modify `app/agent_toolkit/services/quality.py`: compute coverage and stale saved translations from current v2 fact identity, not path equality.
- Modify `rust/src/native_core/write_back_plan/repository.rs`: read saved translations by `fact_id`; remove duplicate-`location_path` failure as a correctness gate.
- Modify `rust/src/native_core/write_back_plan/models.rs`: carry `fact_id` through write-back planning models where needed.
- Modify `rust/src/native_core/text_facts.rs`: remove unsupported v2 fact domains from the current supported-domain list and add tests that prove only current supported domains are accepted.
- Modify `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`: document saved translation identity and the explicit runtime-literal domain decision.
- Modify `docs/superpowers/plans/2026-06-07-text-fact-contract-v2-implementation.md`: mark the original plan historical or add a note pointing to this closure plan so new agents do not execute stale unchecked tasks.
- Modify `app/agent_toolkit/services/common.py`, `app/agent_toolkit/services/rule_validation.py`, `app/agent_toolkit/services/workspace.py`: remove production rule-validation use of `PluginSourceTextExtraction` and `NoteTagTextExtraction`.
- Modify tests in `tests/test_persistence.py`, `tests/test_agent_toolkit_manual_import.py`, `tests/test_agent_toolkit_quality_report.py`, `tests/test_rmmz_write_plan.py`, `tests/test_scan_budget.py`, `tests/test_translation_cache_context.py`, `tests/test_native_scope_index.py`, and Rust tests under `rust/src/native_core/write_back_plan`.

---

### Task 1: Saved Translation v2 Identity Schema

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Modify: `app/rmmz/schema.py`
- Modify: `app/persistence/translation_records.py`
- Test: `tests/test_persistence.py`

- [ ] **Step 1: Write failing schema tests**

Add a test that asserts `translation_items` has `fact_id TEXT PRIMARY KEY`, `location_path TEXT NOT NULL`, `source_fact_raw_hash TEXT NOT NULL`, `source_fact_translatable_hash TEXT NOT NULL`, and `translation_lines TEXT NOT NULL`. Assert declared indexes include:

```python
{
    "idx_translation_items_location_path": ("location_path",),
    "idx_translation_items_source_fact_raw_hash": ("source_fact_raw_hash",),
    "idx_translation_items_source_fact_translatable_hash": ("source_fact_translatable_hash",),
}
```

Add a persistence test named `test_translation_items_require_v2_fact_identity`:

```python
item = TranslationItem(
    fact_id="tfv2:rawhash:identity",
    source_fact_raw_hash="rawhash",
    source_fact_translatable_hash="transhash",
    location_path="System.json/gameTitle",
    item_type="short_text",
    original_lines=["原文"],
    source_line_paths=["System.json/gameTitle"],
    translation_lines=["译文"],
)
await session.write_translation_items([item])
assert [saved.fact_id for saved in await session.read_translated_items()] == ["tfv2:rawhash:identity"]
```

Also assert saving a `TranslationItem` without `fact_id`, `source_fact_raw_hash`, or `source_fact_translatable_hash` raises `ValueError` with a message containing `v2 fact identity`.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_persistence.py::test_shared_current_schema_resource_creates_declared_static_table_set tests/test_persistence.py::test_translation_items_require_v2_fact_identity -q
```

Expected: FAIL because the table is still keyed by `location_path` and `TranslationItem` has no v2 identity fields.

- [ ] **Step 3: Change the schema and SQL constants**

In `current.sql` and `sql.py`, replace the translation table shape with:

```sql
CREATE TABLE IF NOT EXISTS [translation_items] (
    fact_id                       TEXT PRIMARY KEY,
    location_path                 TEXT NOT NULL,
    item_type                     TEXT NOT NULL,
    role                          TEXT,
    original_lines                TEXT NOT NULL,
    source_line_paths             TEXT NOT NULL,
    source_fact_raw_hash          TEXT NOT NULL,
    source_fact_translatable_hash TEXT NOT NULL,
    translation_lines             TEXT NOT NULL
)
;
```

Add the three indexes from Step 1. Bump `CURRENT_SCHEMA_VERSION` and the schema insert value by one.

- [ ] **Step 4: Add internal identity fields to `TranslationItem`**

In `app/rmmz/schema.py`, add excluded fields:

```python
fact_id: str | None = Field(default=None, exclude=True)
source_fact_raw_hash: str | None = Field(default=None, exclude=True)
source_fact_translatable_hash: str | None = Field(default=None, exclude=True)
```

Do not expose these fields in prompts, manual template display text, or user-facing natural-language report bodies. They may appear only in JSON contracts that already carry `fact_id`.

- [ ] **Step 5: Update translation persistence**

In `TranslationRecordSessionMixin.write_translation_items`, validate every item before serialization:

```python
def _require_v2_translation_identity(item: TranslationItem) -> tuple[str, str, str]:
    if not item.fact_id or not item.source_fact_raw_hash or not item.source_fact_translatable_hash:
        raise ValueError(
            "已保存译文缺少 v2 fact identity；请从 text_facts_v2 adapter 构造 TranslationItem 后再保存"
        )
    return item.fact_id, item.source_fact_raw_hash, item.source_fact_translatable_hash
```

Serialize `fact_id`, `location_path`, `item_type`, `role`, `original_lines`, `source_line_paths`, `source_fact_raw_hash`, `source_fact_translatable_hash`, and `translation_lines`. Update `_translation_item_from_row` to restore the three identity fields.

- [ ] **Step 6: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_persistence.py::test_shared_current_schema_resource_creates_declared_static_table_set tests/test_persistence.py::test_translation_items_require_v2_fact_identity tests/test_persistence.py::test_translation_item_crud -q
```

Expected: PASS after updating any existing persistence tests that construct saved translations by hand to include v2 identity or to insert deliberately stale rows through raw SQL.

- [ ] **Step 7: Commit**

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py app/rmmz/schema.py app/persistence/translation_records.py tests/test_persistence.py
git commit -m "refactor: key saved translations by text fact identity"
```

---

### Task 2: v2 Fact Adapter Uses fact_id For Pending, Translated, And Stale State

**Files:**
- Modify: `app/text_facts.py`
- Modify: `tests/test_agent_toolkit_quality_report.py`
- Modify: `tests/test_agent_toolkit_manual_import.py`
- Modify: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing behavior tests**

Add a test that creates one current v2 fact at `System.json/gameTitle`, inserts a saved translation row with the same `location_path` but a different `fact_id`, and asserts:

```python
assert await count_pending_text_facts_v2(session) == 1
assert await count_translated_text_facts_v2(session) == 0
assert await count_stale_translations_outside_writable_text_facts_v2(session) == 1
```

Add a second test that saves the same path with the current `fact_id` and asserts pending is `0`, translated is `1`, and stale is `0`.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_quality_report.py::test_text_fact_v2_saved_translation_identity_uses_fact_id_not_path tests/test_agent_toolkit_quality_report.py::test_text_fact_v2_saved_translation_with_current_fact_id_counts_as_translated -q
```

Expected: FAIL because current joins still use `location_path`.

- [ ] **Step 3: Attach identity in the adapter**

Update `text_fact_record_to_translation_item` so every item constructed from a v2 fact carries:

```python
fact_id=fact.fact_id,
source_fact_raw_hash=fact.raw_hash,
source_fact_translatable_hash=fact.translatable_hash,
translation_dedupe_key=f"text_fact_v2:{fact.translatable_hash}",
```

- [ ] **Step 4: Change SQL joins to `fact_id`**

Update `count_translated_text_facts_v2`, `count_pending_text_facts_v2`, `read_pending_text_fact_records_v2`, `read_pending_text_fact_path_samples_v2`, quality-error pending queries, stale saved translation count, and stale saved translation samples so current translation state is determined by:

```sql
translations.fact_id = facts.fact_id
AND translations.source_fact_raw_hash = facts.raw_hash
AND translations.source_fact_translatable_hash = facts.translatable_hash
```

Use `location_path` only for sorting, display samples, and path-based user commands.

- [ ] **Step 5: Preserve batch behavior**

Keep existing batched reads for path filters and fact filters. For new fact-id helpers, use the same 500-item batch style already used in `app/persistence/text_fact_records.py`; do not introduce per-row queries.

- [ ] **Step 6: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_quality_report.py::test_text_fact_v2_saved_translation_identity_uses_fact_id_not_path tests/test_agent_toolkit_quality_report.py::test_text_fact_v2_saved_translation_with_current_fact_id_counts_as_translated tests/test_agent_toolkit_manual_import.py::test_manual_translation_import_uses_v2_fact_id_when_workspace_key_is_stale tests/test_scan_budget.py::test_task11_agent_production_paths_do_not_rebuild_body_from_v1_index_rows -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add app/text_facts.py tests/test_agent_toolkit_quality_report.py tests/test_agent_toolkit_manual_import.py tests/test_scan_budget.py
git commit -m "fix: resolve text fact translation state by fact id"
```

---

### Task 3: Translation Run And Manual Import Preserve v2 Identity

**Files:**
- Modify: `app/application/handler.py`
- Modify: `app/application/use_cases/translation_run.py`
- Modify: `app/agent_toolkit/services/manual_translation.py`
- Modify: `app/persistence/run_records.py`
- Test: `tests/test_translation_cache_context.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_quality_report.py`

- [ ] **Step 1: Write failing dedupe expansion test**

Add a test where two `TranslationItem` objects have the same `translation_dedupe_key` and `original_lines`, but different `fact_id`. After cache expansion, assert both saved items keep their original `fact_id` values.

Expected assertion shape:

```python
assert {item.fact_id for item in expanded_items} == {"fact-a", "fact-b"}
assert all(item.source_fact_raw_hash for item in expanded_items)
```

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_translation_cache_context.py::test_text_fact_cache_expansion_preserves_fact_identity tests/test_agent_toolkit_manual_import.py::test_manual_translation_import_uses_v2_fact_id_when_workspace_key_is_stale -q
```

Expected: FAIL until dedupe and manual import clone paths copy identity fields.

- [ ] **Step 3: Preserve identity in translation cache and error expansion**

Where code clones or expands `TranslationItem` / `TranslationErrorItem`, copy `fact_id`, `source_fact_raw_hash`, and `source_fact_translatable_hash`. This includes duplicate expansion in `translation_run.py` and manual import preparation in `manual_translation.py`.

- [ ] **Step 4: Clear quality errors by fact identity**

Add persistence helpers:

```python
async def delete_translation_quality_errors_by_fact_ids(self, fact_ids: Sequence[str]) -> int:
    ...
```

Use this helper after successful manual import and successful model translation save. Keep `delete_translation_quality_errors_by_paths` only for legacy cleanup paths that are explicitly not v2 fact based.

- [ ] **Step 5: Store fact identity for run errors**

Add `fact_id` to translation quality error persistence for v2 errors. If a non-v2 test path creates a `TranslationErrorItem` without `fact_id`, store an empty string only in tests or legacy-only helpers, and ensure v2 reports do not treat empty fact_id errors as current.

- [ ] **Step 6: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_translation_cache_context.py tests/test_agent_toolkit_manual_import.py::test_manual_pending_import_uses_text_index_without_full_scope_load tests/test_agent_toolkit_manual_import.py::test_manual_translation_import_uses_v2_fact_id_when_workspace_key_is_stale tests/test_agent_toolkit_quality_report.py::test_quality_report_ignores_stale_saved_translation_quality_errors -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add app/application/handler.py app/application/use_cases/translation_run.py app/agent_toolkit/services/manual_translation.py app/persistence/run_records.py tests/test_translation_cache_context.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_quality_report.py
git commit -m "fix: preserve text fact identity through translation saves"
```

---

### Task 4: Rust Write-Back Reads Saved Translations By fact_id

**Files:**
- Modify: `rust/src/native_core/write_back_plan/repository.rs`
- Modify: `rust/src/native_core/write_back_plan/models.rs`
- Modify: `rust/src/native_core/write_back_plan/test_support.rs`
- Test: Rust tests under `rust/src/native_core/write_back_plan`
- Test: `tests/test_rmmz_write_plan.py`

- [ ] **Step 1: Write failing Rust tests**

Add a Rust repository test with two `text_facts_v2` rows sharing the same `location_path` but different `fact_id`. Insert one saved translation matching only the first `fact_id`. Assert the repository returns exactly one translation and does not fail with duplicate `location_path`.

Add a second test where `translation_items.location_path` matches a current fact but `translation_items.fact_id` does not. Assert the row is reported as stale/unresolved and is not written.

- [ ] **Step 2: Run RED Rust tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml write_back_reads_saved_translation_by_fact_id
```

Expected: FAIL because repository SQL joins on `location_path`.

- [ ] **Step 3: Change repository SQL**

In `read_translation_items_for_allowed_paths`, join saved translations to facts with:

```sql
INNER JOIN text_facts_v2 AS facts
    ON facts.fact_id = translations.fact_id
   AND facts.raw_hash = translations.source_fact_raw_hash
   AND facts.translatable_hash = translations.source_fact_translatable_hash
   AND facts.scope_key = ?
```

Keep the `allowed_paths` filter as a secondary selection against `facts.location_path`, because CLI path filters are still user-facing. Remove the duplicate `location_path` `HashSet` failure. Track resolved `fact_id` values instead of resolved paths.

- [ ] **Step 4: Update unresolved translation check**

Replace `assert_all_translations_resolved_to_v2_facts(... resolved_paths ...)` with fact-id based logic:

```rust
fn assert_all_translations_resolved_to_v2_facts(
    connection: &Connection,
    allowed_paths: &[String],
    resolved_fact_ids: &HashSet<String>,
) -> Result<(), String>
```

The error message should explain that a saved translation no longer matches the current v2 fact identity and tell the user to rerun translation/manual import after `rebuild-text-index`.

- [ ] **Step 5: Run GREEN Rust and Python write-back tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml write_back
uv run pytest tests/test_rmmz_write_plan.py::test_native_write_back_reads_saved_translation_from_text_fact_v2 tests/test_rmmz_write_plan.py::test_native_write_back_blocks_stale_plugin_source_raw_selector -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add rust/src/native_core/write_back_plan/repository.rs rust/src/native_core/write_back_plan/models.rs rust/src/native_core/write_back_plan/test_support.rs tests/test_rmmz_write_plan.py
git commit -m "fix: write back saved translations by fact id"
```

---

### Task 5: Runtime Literal Domain Contract Cleanup

**Files:**
- Modify: `rust/src/native_core/text_facts.rs`
- Modify: `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`
- Modify: `docs/superpowers/plans/2026-06-07-text-fact-contract-v2-implementation.md`
- Test: `rust/src/native_core/text_facts.rs`
- Test: `tests/test_native_scope_index.py`
- Test: `tests/test_release_notes.py`

- [ ] **Step 1: Write failing contract tests**

Add Rust tests asserting `domains::SUPPORTED` contains exactly the current translation fact domains:

```rust
[
    domains::STANDARD_DATA,
    domains::MV_VIRTUAL_NAMEBOX,
    domains::PLUGIN_CONFIG,
    domains::EVENT_COMMAND,
    domains::NOTE_TAG,
    domains::NONSTANDARD_DATA,
    domains::PLUGIN_SOURCE,
]
```

Add a doc/release test that rejects `active_runtime_literal` under the current v2 fact domains section unless a separate future-design section explicitly says it is not part of current `text_facts_v2`.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml text_fact_supported_domains_are_current_contract
uv run pytest tests/test_release_notes.py -q
```

Expected: FAIL because Rust still lists placeholder and runtime-literal domains as supported.

- [ ] **Step 3: Remove unsupported current domains**

Remove these constants from the supported domain list:

```rust
PLACEHOLDER_CANDIDATE
STRUCTURED_PLACEHOLDER_CANDIDATE
ACTIVE_RUNTIME_LITERAL
```

Keep them out of `text_facts_v2` until there is a separate design that explains whether they are translation facts, audit facts, or workflow-gate facts. Current placeholder and runtime-literal scans may continue using native scan outputs and metadata, but they must not pretend to be current v2 fact rows.

- [ ] **Step 4: Document the decision**

In the v2 design spec, add a short section:

```markdown
## 非翻译事实边界

当前 `text_facts_v2` 只保存会参与翻译、质量检查、手动补译或写回的文本事实。Placeholder 候选和 active runtime literal 诊断仍由 Rust/native scan 输出和 workflow metadata 承载，不属于当前 v2 fact domains。若后续需要把它们持久化，应新开设计，明确它们是否进入独立 audit fact 表，避免污染正文翻译事实表。
```

In the old implementation plan, add a top note that it is historical and this closure plan supersedes unchecked runtime-literal fact tasks.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
cargo test --manifest-path rust/Cargo.toml text_fact
uv run pytest tests/test_native_scope_index.py::test_rebuild_native_scope_index_storage_writes_extended_domain_fact_payloads tests/test_release_notes.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add rust/src/native_core/text_facts.rs docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md docs/superpowers/plans/2026-06-07-text-fact-contract-v2-implementation.md tests/test_release_notes.py tests/test_native_scope_index.py
git commit -m "docs: freeze current text fact v2 domains"
```

---

### Task 6: Remove Production Rule-Validation Python Extractor Fallbacks

**Files:**
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/agent_toolkit/services/workspace.py`
- Modify: `app/native_note_tag_scan.py`
- Modify: `app/plugin_source_text/scanner.py`
- Test: `tests/test_agent_toolkit_rule_import.py`
- Test: `tests/test_agent_toolkit_workspace.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing guard tests**

Add tests that monkeypatch these constructors to raise if called during public rule validation or workspace validation:

```python
PluginSourceTextExtraction
NoteTagTextExtraction
TextScopeService.build
```

Cover:

```powershell
validate-plugin-source-rules
import-plugin-source-rules
validate-note-tag-rules
import-note-tag-rules
validate-agent-workspace
```

The tests should assert the commands still return structured reports and do not rebuild a Python full text scope.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py -k "plugin_source or note_tag" tests/test_agent_toolkit_workspace.py -k "plugin_source or note_tag" tests/test_scan_budget.py::test_batch7_production_paths_do_not_keep_python_text_scope_fallbacks -q
```

Expected: FAIL where production validation still calls old extractors.

- [ ] **Step 3: Replace plugin-source validation source**

Use the existing plugin-source scan object and native candidate coverage to compute:

```python
matched_count
translated_count
writable_count
unwritable_count
sample location paths
```

Do not call `PluginSourceTextExtraction(...).extract_all_text()` in validation/reporting. If saved translations need to be cleaned during rule import, derive affected current paths from v2 facts and native rule hit details; delete by fact identity when possible and by path only for explicit stale cleanup.

- [ ] **Step 4: Replace note-tag validation source**

Use native note-tag candidate/hit details and current v2 facts instead of `NoteTagTextExtraction(...).extract_all_text()`. Keep Python code for report assembly and user messages only.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py tests/test_scan_budget.py::test_batch7_production_paths_do_not_keep_python_text_scope_fallbacks -q
```

Expected: PASS. If the full files are too slow during implementation, first run the new focused tests, then run this command before committing.

- [ ] **Step 6: Commit**

```powershell
git add app/agent_toolkit/services/common.py app/agent_toolkit/services/rule_validation.py app/agent_toolkit/services/workspace.py app/native_note_tag_scan.py app/plugin_source_text/scanner.py tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py tests/test_scan_budget.py
git commit -m "refactor: remove production rule validation extractor fallbacks"
```

---

### Task 7: Code-Side Performance Guardrails And Maintainer Benchmark Handoff

**Files:**
- Modify: `tests/test_scan_budget.py`
- Modify: `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`
- Modify: `CHANGELOG.md`
- Modify: `scripts/benchmark_small_tasks.py`

- [ ] **Step 1: Add static guardrails for the new identity contract**

Extend `tests/test_scan_budget.py` so migrated production paths are forbidden from:

```python
"translations.location_path = facts.location_path"
"ON facts.location_path = translations.location_path"
"当前 v2 文本事实出现重复 location_path"
"TextScopeService().build("
"PluginSourceTextExtraction("
"NoteTagTextExtraction("
```

The test may allow these strings only in tests, historical docs, or explicit legacy helper comments.

- [ ] **Step 2: Add SQL index guardrails**

Add scan-budget or persistence tests that assert the new `translation_items` indexes exist and that fact-id batch helpers use batched `IN (...)` queries instead of per-row reads.

- [ ] **Step 3: Document implementation-time performance rules**

In the spec or CHANGELOG, state:

```markdown
本次闭环不声明真实游戏性能已经通过；真实游戏耗时由维护者在目标样本上执行。代码侧要求是：当前实现不得新增 Python 全量文本范围重建，不得按行查询 v2 facts 或 translation_items，不得把 saved translation 状态退回 location_path join，Rust 写回继续使用可配置 Rayon 线程池。
```

- [ ] **Step 4: Provide maintainer benchmark commands**

Add or reuse a benchmark section with these commands:

```powershell
uv run python main.py rebuild-text-index --game <游戏标题> --debug-timings
uv run python main.py quality-report --game <游戏标题> --debug-timings
uv run python main.py export-pending-translations --game <游戏标题> --output <输出文件> --debug-timings
uv run python main.py write-translated --game <游戏标题> --debug-timings
```

The maintainer should record `text_fact_count`, `render_part_count`, `scan_file_count`, `domain_fact_counts`, `native_thread_count`, total command duration, Rust internal timings, and whether any path performs repeated full scans.

- [ ] **Step 5: Run guardrail tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py tests/test_persistence.py::test_shared_current_schema_resource_creates_declared_static_table_set -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_scan_budget.py docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md CHANGELOG.md scripts/benchmark_small_tasks.py
git commit -m "test: guard text fact v2 identity performance paths"
```

---

### Task 8: Final Verification

**Files:**
- No source file changes unless verification reveals defects.

- [ ] **Step 1: Run Python type check**

```powershell
uv run basedpyright
```

Expected: `0 errors, 0 warnings, 0 notes`.

- [ ] **Step 2: Run Python tests**

```powershell
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run Rust formatting**

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
```

Expected: no diff.

- [ ] **Step 4: Run Rust clippy**

```powershell
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

Expected: no warnings.

- [ ] **Step 5: Run Rust tests**

```powershell
cargo test --manifest-path rust/Cargo.toml
```

Expected: all tests pass.

- [ ] **Step 6: Check generated Skill protocol only if docs or Skill sources changed**

If this implementation touches `skills/att-mz-protocol/`, `skills/att-mz/`, or `skills/att-mz-release/`, run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: generated outputs are current.

- [ ] **Step 7: Record deferred real-game performance status**

In the final implementation message, state:

```text
代码侧性能防线已验证：列出 scan-budget、SQL index、Rust test 和 no-full-scope guard 结果。
真实游戏性能尚未由本会话验收：维护者将使用目标游戏样本运行 benchmark 命令后继续深度优化。
```

Do not claim "性能没有退化" until the maintainer has run the real-game benchmark.

- [ ] **Step 8: Commit final verification note if files changed**

If verification required small fixes, commit them:

```powershell
git add <修复文件>
git commit -m "fix: close text fact v2 review verification gaps"
```

---

## Maintainer Real-Game Benchmark Checklist

This checklist is intentionally outside implementation gating. Run it after the code plan above is complete and merged into the test workspace.

```powershell
uv run python main.py rebuild-text-index --game <游戏标题> --debug-timings
uv run python main.py quality-report --game <游戏标题> --debug-timings
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --debug-timings
uv run python main.py validate-agent-workspace --game <游戏标题> --workspace <工作区> --debug-timings
uv run python main.py export-pending-translations --game <游戏标题> --output <输出文件> --debug-timings
uv run python main.py write-translated --game <游戏标题> --debug-timings
```

Record these fields for each command:

- total command duration
- `text_fact_count`
- `render_part_count`
- `scan_file_count`
- `domain_fact_counts`
- `native_thread_count`
- Rust internal timings under `diagnostics.timings`
- whether the command rebuilt text index, reused it, or failed stale checks
- observed CPU saturation and memory pressure

If any command is slower than the pre-v2 baseline, inspect repeated full scans first, then SQL query plans, then Rust parallel stage timings. Do not add Python fallback paths to recover performance; move the hot stage toward Rust or improve the SQLite fact/index layout.
