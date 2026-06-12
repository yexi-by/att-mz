# Pytest Contract Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete a one-pass pytest governance cleanup so remaining Python tests only protect current `app/`, Rust/native, and public CLI contracts while cutting pytest count, test lines, and local full-suite time substantially.

**Architecture:** Delete pytest suites that do not protect current production contracts, rewrite surviving Python tests into thin observable contract checks, and move core native behavior coverage into Rust `#[cfg(test)]` or narrow native contract tests. The cleanup must cover the whole test tree, update `AGENTS.md`, and finish with a single full pytest command that runs locally in under 60 seconds.

**Tech Stack:** Python 3.14, pytest, pytest-xdist, uv, PowerShell, Rust 2024, PyO3/maturin native extension.

---

## File Structure

- Modify `AGENTS.md`: replace old pytest/release/docs/Skill validation language with the new pytest boundary and final local full-suite command.
- Delete whole-file pytest suites that do not test current `app/`, Rust/native, or public CLI contracts:
  - `tests/test_benchmark_active_runtime_audit.py`
  - `tests/test_benchmark_rebuild_active_runtime.py`
  - `tests/test_benchmark_small_tasks.py`
  - `tests/test_release_notes.py`
  - `tests/test_release_package_layout.py`
  - `tests/test_scan_budget.py`
  - `tests/test_skill_protocol.py`
- Replace or heavily shrink historical/full-flow canaries:
  - `tests/test_stage0_canaries.py`
  - create `tests/test_cli_public_contract.py` only if the remaining public CLI smoke tests fit better in a new small file.
- Shrink pytest infrastructure:
  - `tests/conftest.py`
  - `tests/agent_toolkit_contract_fixtures.py`
  - `tests/rmmz_writeback_contract_fixtures.py`
  - `tests/current_text_fact_scope.py`
  - `tests/_native_write_plan_helper.py`
  - `tests/native_rule_seed.py`
- Rewrite or delete implementation-path-heavy pytest suites:
  - `tests/test_agent_toolkit_rule_import.py`
  - `tests/test_agent_toolkit_manual_import.py`
  - `tests/test_agent_toolkit_workspace.py`
  - `tests/test_agent_toolkit_workflow_gate.py`
  - `tests/test_agent_toolkit_quality_report.py`
  - `tests/test_agent_toolkit_feedback.py`
  - `tests/test_agent_toolkit_coverage.py`
  - `tests/test_agent_toolkit_translation_limits.py`
- Shrink native boundary and core owner tests:
  - `tests/test_native_adapters.py`
  - `tests/test_native_rule_runtime.py`
  - `tests/test_native_scope_index.py`
  - `tests/test_rule_runtime_store.py`
  - `tests/test_regex_contract.py`
  - `tests/test_quality_gate_result.py`
- Shrink RMMZ/write-back/text contract tests:
  - `tests/test_rmmz_write_plan.py`
  - `tests/test_rmmz_file_transaction.py`
  - `tests/test_rmmz_font_transaction.py`
  - `tests/test_rmmz_mv_namebox.py`
  - `tests/test_rmmz_note_nonstandard_data.py`
  - `tests/test_rmmz_post_write_audit.py`
  - `tests/test_rmmz_source_snapshot.py`
  - `tests/test_plugin_source_text.py`
  - `tests/test_plugin_text.py`
  - `tests/test_nonstandard_data.py`
  - `tests/test_event_command_text.py`
  - `tests/test_text_index.py`
  - `tests/test_text_rules.py`
  - `tests/test_text_protocol.py`
  - `tests/test_translation_cache_context.py`
  - `tests/test_translation_line_alignment.py`
  - `tests/test_translation_run_limits.py`
- Keep and shrink current production-contract pytest:
  - `tests/test_cli_json_output.py`
  - `tests/test_config_overrides.py`
  - `tests/test_external_input.py`
  - `tests/test_game_data_external_input.py`
  - `tests/test_game_reset.py`
  - `tests/test_llm_retry.py`
  - `tests/test_manual_translation_scope.py`
  - `tests/test_observability.py`
  - `tests/test_persistence.py`
  - `tests/test_runtime_paths.py`
  - `tests/test_source_language_probe.py`
  - `tests/test_terminology.py`
  - `tests/test_workflow_gate.py`
  - `tests/test_workspace_manifest.py`
  - `tests/test_write_back_transactions.py`
- Add or expand Rust `#[cfg(test)]` only where Python deletion would otherwise remove core safety:
  - `rust/src/native_core/rule_runtime/**`
  - `rust/src/native_core/scope_index/**`
  - `rust/src/native_core/write_back_plan/**`
  - `rust/src/native_core/quality/**`
  - `rust/src/native_core/text_facts.rs`
  - `rust/src/native_core/write_protocol.rs`

## Task 1: Record Baseline and Dirty-Tree Boundaries

**Files:**
- Read-only: full repository
- Do not modify files in this task

- [ ] **Step 1: Capture git state before cleanup**

Run:

```powershell
git status --short
```

Expected: note every pre-existing modified file. Do not revert or stage unrelated work.

- [ ] **Step 2: Capture pytest count baseline**

Run:

```powershell
uv run pytest --collect-only -q
```

Expected: output ends with the current collected test count. Record the number as `BASE_PYTEST_COUNT`.

- [ ] **Step 3: Capture test line baseline**

Run:

```powershell
$testLines = rg --files tests |
  Where-Object { $_ -like '*.py' } |
  ForEach-Object { (Get-Content -LiteralPath $_ | Measure-Object -Line).Lines } |
  Measure-Object -Sum
$testLines.Sum
```

Expected: record the number as `BASE_TEST_LINES`.

- [ ] **Step 4: Capture file and large-file baseline**

Run:

```powershell
rg --files tests | Where-Object { $_ -like '*.py' } | Measure-Object
rg --files tests |
  Where-Object { $_ -like '*.py' } |
  ForEach-Object { [pscustomobject]@{ Lines=(Get-Content -LiteralPath $_ | Measure-Object -Line).Lines; File=$_ } } |
  Sort-Object Lines -Descending |
  Select-Object -First 30 |
  Format-Table -AutoSize
```

Expected: record total pytest Python file count and every file above 1000 lines.

- [ ] **Step 5: Capture implementation-sentinel baseline**

Run:

```powershell
rg -n "forbidden_|without_python|without_full|does_not_call|scan_budget|benchmark|release|skill|monkeypatch" tests --glob "*.py"
```

Expected: record count and major files. Later tasks must remove disallowed uses, not just reduce them.

- [ ] **Step 6: Capture current full pytest time**

Run the current project command:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n 6 --durations=30 --durations-min=0.5 }
```

Expected: record total elapsed time and slowest tests. This may fail because of pre-existing worktree changes; if it fails, record failure reason and continue with deletion tasks only after understanding whether failure is unrelated.

- [ ] **Step 7: Commit nothing**

Expected: no files are staged and no commit is created in this task.

## Task 2: Rewrite `AGENTS.md` Testing Contract

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Remove pytest requirements for docs, Skill, release notes, and release layout**

Edit section 7 so it no longer says docs/Skill/README/release-note changes are protected by pytest assertions. Replace that rule with:

```markdown
- pytest 只保护 `app/` 当前生产契约、Rust/native 边界和公开 CLI 行为；不得用 pytest 固定发行包布局、Skill 协议、发布说明、README、docs 生成物或测试基础设施。
```

Expected: no rule remains that requires release/docs/Skill pytest.

- [ ] **Step 2: Add the new pytest existence boundary**

In section 5 or section 7, add:

```markdown
- Python pytest 必须保持薄契约定位：CLI 参数链路、配置覆盖、JSON 报告、用户文案、错误映射、数据库读写结果和 write-back 文件副作用；严禁用 Python 大集成测试兜 Rust 内部逻辑、测试基础设施、benchmark runner、历史 canary 或实现路径哨兵。
```

Expected: the rule explicitly blocks `forbidden_*`/`without_python` style tests unless they isolate external dependencies.

- [ ] **Step 3: Replace full pytest command after final timing is known**

Temporarily leave the existing command in place until Task 12 selects the final worker count. Add this marker comment in the plan notes, not in `AGENTS.md`:

```text
Task 12 must update AGENTS.md with the final pytest worker argument.
```

Expected: `AGENTS.md` is not left with a placeholder.

- [ ] **Step 4: Run a text check**

Run:

```powershell
rg -n "Skill|发布说明|release|发行包|pytest|测试基础设施|benchmark" AGENTS.md
```

Expected: any remaining mentions of Skill/release/docs pytest are explanatory or explicitly say they are not protected by pytest.

- [ ] **Step 5: Commit AGENTS contract update**

Run:

```powershell
git add AGENTS.md
git diff --cached -- AGENTS.md
git commit -m "docs: 收束 pytest 验证边界"
```

Expected: only `AGENTS.md` is staged.

## Task 3: Delete Whole-File Non-Production Pytest Suites

**Files:**
- Delete:
  - `tests/test_benchmark_active_runtime_audit.py`
  - `tests/test_benchmark_rebuild_active_runtime.py`
  - `tests/test_benchmark_small_tasks.py`
  - `tests/test_release_notes.py`
  - `tests/test_release_package_layout.py`
  - `tests/test_scan_budget.py`
  - `tests/test_skill_protocol.py`

- [ ] **Step 1: Delete the disallowed files**

Run:

```powershell
Remove-Item -LiteralPath `
  tests/test_benchmark_active_runtime_audit.py,`
  tests/test_benchmark_rebuild_active_runtime.py,`
  tests/test_benchmark_small_tasks.py,`
  tests/test_release_notes.py,`
  tests/test_release_package_layout.py,`
  tests/test_scan_budget.py,`
  tests/test_skill_protocol.py
```

Expected: the files no longer exist.

- [ ] **Step 2: Remove references to deleted tests**

Run:

```powershell
rg -n "test_benchmark_|test_release_|test_skill_protocol|test_scan_budget|benchmark_small_tasks|extract_release_notes" tests docs AGENTS.md .github pyproject.toml
```

Expected: remove references that only exist for pytest execution. Do not modify release scripts or Skill files in this task.

- [ ] **Step 3: Run collection smoke**

Run:

```powershell
uv run pytest --collect-only -q
```

Expected: collection succeeds and count decreases. Failures from missing imports must be fixed by deleting obsolete imports or helper references.

- [ ] **Step 4: Commit whole-file deletion**

Run:

```powershell
git add -A tests AGENTS.md docs .github pyproject.toml
git diff --cached --name-only
git commit -m "test: 删除非生产契约 pytest"
```

Expected: staged files are the deleted pytest files and any direct reference cleanup only.

## Task 4: Replace Historical Stage 0 Canary With Thin Public CLI Contracts

**Files:**
- Modify or delete: `tests/test_stage0_canaries.py`
- Create if clearer: `tests/test_cli_public_contract.py`
- May reuse: `tests/conftest.py`

- [ ] **Step 1: Identify the current production entrypoints that need smoke coverage**

Keep at most these public CLI smoke flows:

```text
add-game -> prepare-agent-workspace -> validate-agent-workspace
translate --max-items 1 with fake OpenAI-compatible server
quality-report -> write-back on a pretranslated minimal game
```

Expected: no smoke flow imports private service internals except existing fixture builders.

- [ ] **Step 2: Delete the full stage0 historical flow**

Remove tests that import terminology workspaces, every branch rule import, feedback, and multi-stage historical checks from `tests/test_stage0_canaries.py`.

Expected: the remaining file has at most three tests and no helper that only exists for the deleted full flow.

- [ ] **Step 3: Move thin tests to `tests/test_cli_public_contract.py` if file naming is clearer**

If creating the new file, use this file-level responsibility:

```python
"""公开 CLI 主链路薄契约测试。"""
```

Expected: `tests/test_stage0_canaries.py` is deleted if all useful tests moved; otherwise it is renamed by content, not left as a stage0 concept.

- [ ] **Step 4: Run the thin CLI contract tests**

Run:

```powershell
uv run pytest tests/test_cli_public_contract.py tests/test_stage0_canaries.py -q
```

Expected: command passes if both files exist; if `tests/test_stage0_canaries.py` was deleted, run only `tests/test_cli_public_contract.py`.

- [ ] **Step 5: Commit canary replacement**

Run:

```powershell
git add -A tests/test_stage0_canaries.py tests/test_cli_public_contract.py
git diff --cached --name-only
git commit -m "test: 改写公开 CLI 薄契约"
```

Expected: the commit removes the historical stage0 full-flow shape.

## Task 5: Slim Test Fixtures and Remove Test-Infrastructure Self-Tests

**Files:**
- Modify: `tests/conftest.py`
- Modify or delete if orphaned:
  - `tests/agent_toolkit_contract_fixtures.py`
  - `tests/rmmz_writeback_contract_fixtures.py`
  - `tests/current_text_fact_scope.py`
  - `tests/_native_write_plan_helper.py`
  - `tests/native_rule_seed.py`
  - `tests/test_workspace_manifest.py`

- [ ] **Step 1: Remove test scheduling metadata that only served the old suite**

In `tests/conftest.py`, remove priority maps and nodeid lists that only tune old heavy tests after their target tests are deleted:

```text
HEAVY_TEST_FILE_PRIORITIES
HEAVY_TEST_NODEID_PRIORITIES
PRE_REGISTERED_MINIMAL_GAME_FILE_PREFIXES
PRE_REGISTERED_MINIMAL_GAME_NODEID_PREFIXES
PRE_REGISTERED_MINIMAL_GAME_NODEIDS
CLEAN_MINIMAL_GAME_NODEIDS
```

Expected: no pytest hook depends on deleted nodeids.

- [ ] **Step 2: Keep only production-contract fixtures**

Keep fixture builders that create current minimal RPG Maker MV/MZ games, app home, fake LLM server, and isolated DB paths. Delete helpers that only precompute state for deleted implementation-path tests.

Expected: fixture code supports remaining tests without testing fixture behavior itself.

- [ ] **Step 3: Delete or merge `tests/test_workspace_manifest.py`**

If the cleanup behavior is still a current `app.agent_toolkit` contract, move one thin assertion into an agent toolkit contract file. If it only protects test workspace manifest semantics, delete the file.

Expected: there is no standalone pytest whose purpose is testing test-workspace manifest mechanics.

- [ ] **Step 4: Delete orphan helper files**

Run:

```powershell
rg -n "agent_toolkit_contract_fixtures|rmmz_writeback_contract_fixtures|current_text_fact_scope|_native_write_plan_helper|native_rule_seed" tests app rust
```

Expected: delete helper files with zero remaining references. For helper files still referenced, shrink them to only functions used by retained production-contract tests.

- [ ] **Step 5: Run collection and selected fixture consumers**

Run:

```powershell
uv run pytest --collect-only -q
uv run pytest tests/test_runtime_paths.py tests/test_persistence.py tests/test_cli_public_contract.py -q
```

Expected: collection and selected tests pass.

- [ ] **Step 6: Commit fixture shrink**

Run:

```powershell
git add -A tests
git diff --cached --name-only
git commit -m "test: 精简 pytest 夹具"
```

Expected: commit contains fixture/helper deletion or shrink only.

## Task 6: Move Native Core Coverage Out of Python Adapter Tests

**Files:**
- Modify:
  - `tests/test_native_adapters.py`
  - `tests/test_native_rule_runtime.py`
  - `tests/test_native_scope_index.py`
  - `tests/test_rule_runtime_store.py`
  - `tests/test_regex_contract.py`
  - `tests/test_quality_gate_result.py`
- Add or expand Rust tests in:
  - `rust/src/native_core/rule_runtime/**`
  - `rust/src/native_core/scope_index/**`
  - `rust/src/native_core/write_back_plan/**`
  - `rust/src/native_core/quality/**`
  - `rust/src/native_core/write_protocol.rs`

- [ ] **Step 1: Delete fake native module adapter tests that assert private calls**

In `tests/test_native_adapters.py`, remove fake-module classes and tests that only prove a Python wrapper calls a specific private native function or refuses to call another.

Expected: the file keeps only native input/output schema, contract version, and error mapping tests that are visible from Python.

- [ ] **Step 2: Keep Python native contract tests thin**

Limit Python native tests to:

```text
native function accepts current payload schema
native function rejects malformed payload with current error code
Python wrapper maps native error to current report/error type
SQLite/file side effect is visible after native call
```

Expected: Python native tests no longer duplicate Rust rule matching, candidate scanning, or write plan internals.

- [ ] **Step 3: Add Rust tests for any deleted core cases**

For every deleted Python case that was the only coverage for native-owned behavior, add Rust tests under the owning module. Use existing Rust test style in the same file.

Expected: core behavior remains covered in Rust, not through Python fake adapters.

- [ ] **Step 4: Run native-focused checks**

Run:

```powershell
uv run pytest tests/test_native_adapters.py tests/test_native_rule_runtime.py tests/test_native_scope_index.py tests/test_rule_runtime_store.py tests/test_regex_contract.py tests/test_quality_gate_result.py -q
```

Then run Rust format, clippy, and tests using the project commands discovered from `pyproject.toml`, `Cargo.toml`, or existing CI.

Expected: Python native contract tests pass; Rust checks pass.

- [ ] **Step 5: Commit native coverage migration**

Run:

```powershell
git add -A tests rust
git diff --cached --name-only
git commit -m "test: 下沉 native 核心测试"
```

Expected: commit contains Python native test shrink and Rust `#[cfg(test)]` additions only.

## Task 7: Collapse Agent Toolkit Rule and Workspace Tests

**Files:**
- Modify:
  - `tests/test_agent_toolkit_rule_import.py`
  - `tests/test_agent_toolkit_manual_import.py`
  - `tests/test_agent_toolkit_workspace.py`
  - `tests/test_agent_toolkit_workflow_gate.py`
  - `tests/test_agent_toolkit_quality_report.py`
  - `tests/test_agent_toolkit_feedback.py`
  - `tests/test_agent_toolkit_coverage.py`
  - `tests/test_agent_toolkit_translation_limits.py`

- [ ] **Step 1: Delete implementation-path sentinels**

Remove tests whose names or bodies contain these patterns unless the `monkeypatch` only isolates an external service:

```text
forbidden_
without_python
without_full
does_not_call
skips_*_scan
uses_warm_text_index_without_full
no_longer_exports
```

Expected: no remaining test fails solely because an internal Python function was called.

- [ ] **Step 2: Keep one thin public contract per command family**

For each command family, retain at most one success case and one current failure case:

```text
prepare-agent-workspace
validate-agent-workspace
import-plugin-rules / import-event-command-rules / import-note-tag-rules
import-placeholder-rules / import-structured-placeholder-rules
export/import manual pending translations
quality-report
verify-feedback-text
translate --max-items
```

Expected: tests assert public report status, JSON fields, DB rows, or output files; they do not assert private scan/cache paths.

- [ ] **Step 3: Merge repeated integer/boolean normalization tests**

Replace repeated per-command tests such as `normalizes_integer_*` and `rejects_boolean_*` with owner-layer table tests in the parser/model that performs validation.

Expected: no command file repeats the same primitive coercion checks unless that command has unique production behavior.

- [ ] **Step 4: Move native-owned rule behavior to Rust/native tests**

If a deleted agent toolkit test was checking rule matching, candidate coverage, stale hash, selector behavior, or source residual matching, add or reuse Rust/native tests from Task 6.

Expected: agent toolkit pytest only checks command orchestration and observable reports.

- [ ] **Step 5: Run agent toolkit subset**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_*.py -q -n auto
```

Expected: remaining agent toolkit tests pass. Count and line total for these files should be substantially below baseline.

- [ ] **Step 6: Commit agent toolkit shrink**

Run:

```powershell
git add -A tests rust
git diff --cached --name-only
git commit -m "test: 瘦身 agent toolkit 契约测试"
```

Expected: commit removes the majority of agent toolkit pytest lines and does not modify production logic.

## Task 8: Collapse RMMZ, Write-Back, Plugin Source, and Text Tests

**Files:**
- Modify:
  - `tests/test_rmmz_write_plan.py`
  - `tests/test_rmmz_file_transaction.py`
  - `tests/test_rmmz_font_transaction.py`
  - `tests/test_rmmz_mv_namebox.py`
  - `tests/test_rmmz_note_nonstandard_data.py`
  - `tests/test_rmmz_post_write_audit.py`
  - `tests/test_rmmz_source_snapshot.py`
  - `tests/test_plugin_source_text.py`
  - `tests/test_plugin_text.py`
  - `tests/test_nonstandard_data.py`
  - `tests/test_event_command_text.py`
  - `tests/test_text_index.py`
  - `tests/test_text_rules.py`
  - `tests/test_text_protocol.py`
  - `tests/test_translation_cache_context.py`
  - `tests/test_translation_line_alignment.py`
  - `tests/test_translation_run_limits.py`

- [ ] **Step 1: Keep only observable write-back/file contracts in Python**

Retain tests that prove:

```text
write-back changes the expected game file
write-back rolls back file/font/database state on failure
quality_error blocks write-back at public boundary
source snapshot protects active source view when current contract requires it
```

Expected: Python tests do not duplicate Rust write plan internals.

- [ ] **Step 2: Delete source-scan and cache-path sentinels**

Remove tests that only assert a branch does or does not scan plugin source, nonstandard data, note tags, or text index internals.

Expected: surviving tests assert final report and persisted facts, not scan-cache implementation.

- [ ] **Step 3: Move rule/text parsing core cases to Rust or owner-layer tests**

Move or keep at owner layer:

```text
placeholder shell preservation
structured placeholder coverage
source residual matching
line width splitting
write protocol counting
MV namebox fact splitting
plugin source selector behavior
```

Expected: Python integration tests no longer enumerate many lexical variants of the same native-owned rule.

- [ ] **Step 4: Collapse translation response and line-alignment matrices**

In `tests/test_translation_line_alignment.py` and `tests/test_translation_cache_context.py`, keep representative contract cases only:

```text
valid minimal model response saves
invalid JSON records parse failure
placeholder mismatch records quality_error
long text line split preserves placeholders
short text line break structure is enforced
```

Expected: remove large parameter matrices that only protect formatting variants unless they map to distinct production branches.

- [ ] **Step 5: Run RMMZ/text subset**

Run:

```powershell
uv run pytest tests/test_rmmz_*.py tests/test_plugin*_text.py tests/test_nonstandard_data.py tests/test_event_command_text.py tests/test_text_*.py tests/test_translation_*.py -q -n auto
```

Expected: remaining RMMZ/text tests pass.

- [ ] **Step 6: Commit RMMZ/text shrink**

Run:

```powershell
git add -A tests rust
git diff --cached --name-only
git commit -m "test: 瘦身文本与写回契约"
```

Expected: commit materially reduces large text/write-back files.

## Task 9: Slim CLI, Config, Persistence, and Runtime Contract Tests

**Files:**
- Modify:
  - `tests/test_cli_json_output.py`
  - `tests/test_config_overrides.py`
  - `tests/test_external_input.py`
  - `tests/test_game_data_external_input.py`
  - `tests/test_game_reset.py`
  - `tests/test_llm_retry.py`
  - `tests/test_manual_translation_scope.py`
  - `tests/test_observability.py`
  - `tests/test_persistence.py`
  - `tests/test_runtime_paths.py`
  - `tests/test_source_language_probe.py`
  - `tests/test_terminology.py`
  - `tests/test_workflow_gate.py`
  - `tests/test_write_back_transactions.py`

- [ ] **Step 1: Keep public boundary tests**

Retain tests for:

```text
CLI JSON envelope and exit code
config/env precedence
ATT_MZ_HOME runtime paths
SQLite current schema creation and rejection of invalid current DB state
LLM retry observable behavior
write-back transaction rollback
```

Expected: these files stay small and focused.

- [ ] **Step 2: Delete repeated primitive validation spread across command tests**

Remove repeated tests for identical integer string normalization, boolean rejection, parser accepts, parser rejects, and natural-language message order.

Expected: one owner-layer test covers each generic validation rule.

- [ ] **Step 3: Remove fake internal command session tests unless they assert JSON output**

In `tests/test_cli_json_output.py`, keep fake dispatch/session tests only when the fake isolates an external dependency and the assertion is the public JSON/exit contract.

Expected: no test exists just to prove `dispatch_command` or `HandlerSession` was called.

- [ ] **Step 4: Run core Python contract subset**

Run:

```powershell
uv run pytest tests/test_cli_json_output.py tests/test_config_overrides.py tests/test_external_input.py tests/test_game_data_external_input.py tests/test_game_reset.py tests/test_llm_retry.py tests/test_manual_translation_scope.py tests/test_observability.py tests/test_persistence.py tests/test_runtime_paths.py tests/test_source_language_probe.py tests/test_terminology.py tests/test_workflow_gate.py tests/test_write_back_transactions.py -q -n auto
```

Expected: remaining core contract tests pass.

- [ ] **Step 5: Commit CLI/config/persistence shrink**

Run:

```powershell
git add -A tests
git diff --cached --name-only
git commit -m "test: 精简 CLI 与持久化契约"
```

Expected: commit keeps only production boundary tests.

## Task 10: Enforce Global Test Qualification and 50% Shrink Gate

**Files:**
- Modify any remaining `tests/**/*.py`
- Modify Rust tests only if a core gap remains

- [ ] **Step 1: Recount pytest and lines**

Run:

```powershell
$afterCollect = uv run pytest --collect-only -q
$afterCollect
$afterLines = rg --files tests |
  Where-Object { $_ -like '*.py' } |
  ForEach-Object { (Get-Content -LiteralPath $_ | Measure-Object -Line).Lines } |
  Measure-Object -Sum
$afterLines.Sum
```

Expected: pytest count and test lines are at least 50% below the Task 1 baseline.

- [ ] **Step 2: List remaining large files**

Run:

```powershell
rg --files tests |
  Where-Object { $_ -like '*.py' } |
  ForEach-Object { [pscustomobject]@{ Lines=(Get-Content -LiteralPath $_ | Measure-Object -Line).Lines; File=$_ } } |
  Sort-Object Lines -Descending |
  Format-Table -AutoSize
```

Expected: no remaining file over 1000 lines unless it is explicitly justified by current production contract and cannot be split without increasing total complexity. If any file remains over 1000 lines, shrink it before proceeding.

- [ ] **Step 3: Scan for disallowed test categories**

Run:

```powershell
rg -n "benchmark|release|Skill|skill_protocol|scan_budget|stage0|forbidden_|without_python|without_full|does_not_call|no_longer_exports" tests --glob "*.py"
```

Expected: no benchmark/release/docs/Skill/scan-budget/stage0 tests remain. Any remaining `forbidden_` or `monkeypatch` must isolate external dependencies; rewrite or delete the rest.

- [ ] **Step 4: Run full collection**

Run:

```powershell
uv run pytest --collect-only -q
```

Expected: collection succeeds with reduced count.

- [ ] **Step 5: Commit qualification cleanup**

Run:

```powershell
git add -A tests rust
git diff --cached --name-only
git commit -m "test: 完成 pytest 资格清理"
```

Expected: commit contains only final test shrink and safety-net additions.

## Task 11: Optimize Remaining Pytest Runtime Under 60 Seconds

**Files:**
- Modify: `tests/conftest.py`
- Modify remaining tests that dominate `--durations`
- Modify: `AGENTS.md` after final command selected

- [ ] **Step 1: Benchmark worker counts**

Run each command at least once after a clean collection:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n 6 --durations=30 --durations-min=0.5 }
Measure-Command { uv run pytest -q -n 8 --durations=30 --durations-min=0.5 }
Measure-Command { uv run pytest -q -n auto --durations=30 --durations-min=0.5 }
```

Expected: choose the fastest passing command that stays below 60 seconds.

- [ ] **Step 2: Fix slow remaining tests structurally**

For every slow test in `--durations=30`:

```text
If it repeats full game registration, switch to existing isolated template fixture.
If it repeats full command chain, replace setup with direct current DB/file state.
If it parametrizes equivalent cases, reduce to representative branches.
If it waits on fake LLM flow unnecessarily, replace with a public report/db assertion at the nearest boundary.
```

Expected: no slow test is hidden, skipped, or moved out of default collection.

- [ ] **Step 3: Re-run the fastest full command**

Run exactly one of these commands again, matching the fastest passing command from Step 1:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n 6 --durations=30 --durations-min=0.5 }
```

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n 8 --durations=30 --durations-min=0.5 }
```

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n auto --durations=30 --durations-min=0.5 }
```

Expected: full local pytest passes under 60 seconds.

- [ ] **Step 4: Write final pytest command to `AGENTS.md`**

Replace the old full pytest command in `AGENTS.md` with exactly one of these text variants, matching the fastest passing command:

```markdown
当前全量 pytest 推荐命令为先设置 `$env:ATT_MZ_RUST_THREADS = "1"`，再执行 `uv run pytest -q -n 6 --durations=30 --durations-min=0.5`。
```

```markdown
当前全量 pytest 推荐命令为先设置 `$env:ATT_MZ_RUST_THREADS = "1"`，再执行 `uv run pytest -q -n 8 --durations=30 --durations-min=0.5`。
```

```markdown
当前全量 pytest 推荐命令为先设置 `$env:ATT_MZ_RUST_THREADS = "1"`，再执行 `uv run pytest -q -n auto --durations=30 --durations-min=0.5`。
```

Expected: no outdated `-n 6` requirement remains if another worker count wins.

- [ ] **Step 5: Commit runtime tuning**

Run:

```powershell
git add -A tests AGENTS.md
git diff --cached --name-only
git commit -m "test: 优化全量 pytest 耗时"
```

Expected: commit contains runtime tuning and final command update.

## Task 12: Final Verification and Delivery Evidence

**Files:**
- Read-only unless verification exposes a required fix

- [ ] **Step 1: Run type checking**

Run:

```powershell
uv run basedpyright
```

Expected: 0 errors and 0 warnings.

- [ ] **Step 2: Run final full pytest command**

Run the exact command written to `AGENTS.md`. It must be one of:

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n 6 --durations=30 --durations-min=0.5 }
```

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n 8 --durations=30 --durations-min=0.5 }
```

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
Measure-Command { uv run pytest -q -n auto --durations=30 --durations-min=0.5 }
```

Expected: all tests pass, elapsed time is under 60 seconds, and slowest tests are recorded.

- [ ] **Step 3: Run Rust checks if Rust tests changed**

Run Rust format, clippy, and Rust tests using the repository's current commands. If no canonical command is documented, inspect `.github/workflows`, `pyproject.toml`, and `rust/Cargo.toml`, then run the direct Cargo equivalents from `rust/`.

Expected: Rust checks pass. Record exact commands in final delivery.

- [ ] **Step 4: Compute final deltas**

Run:

```powershell
uv run pytest --collect-only -q
rg --files tests | Where-Object { $_ -like '*.py' } | ForEach-Object { (Get-Content -LiteralPath $_ | Measure-Object -Line).Lines } | Measure-Object -Sum
rg --files tests | Where-Object { $_ -like '*.py' } | Measure-Object
rg --files tests |
  Where-Object { $_ -like '*.py' } |
  ForEach-Object { [pscustomobject]@{ Lines=(Get-Content -LiteralPath $_ | Measure-Object -Line).Lines; File=$_ } } |
  Sort-Object Lines -Descending |
  Select-Object -First 20 |
  Format-Table -AutoSize
```

Expected: pytest count and `tests/**/*.py` lines are at least 50% below Task 1 baseline.

- [ ] **Step 5: Final disallowed-pattern scan**

Run:

```powershell
rg -n "benchmark|release|Skill|skill_protocol|scan_budget|stage0|forbidden_|without_python|without_full|does_not_call|no_longer_exports" tests --glob "*.py"
```

Expected: no disallowed pytest category remains. Any remaining match must be explained as external dependency isolation or user-facing text, not implementation-path protection.

- [ ] **Step 6: Final git review**

Run:

```powershell
git status --short
git log --oneline -n 12
```

Expected: all intended cleanup commits exist. Pre-existing unrelated work is not reverted.

- [ ] **Step 7: Prepare delivery summary**

Final delivery must include:

```text
pytest collect count: before -> after
tests/**/*.py lines: before -> after
pytest file count: before -> after
files over 1000 lines: before -> after
full pytest command and local elapsed time
slowest tests from --durations=30
Rust tests added/changed count and coverage area
basedpyright result
Rust fmt/clippy/test result if applicable
confirmation that production logic was not changed, or exact production changes if unavoidable
```

Expected: the summary proves the qualification gate, 50% shrink gate, and 60-second speed gate all passed.
