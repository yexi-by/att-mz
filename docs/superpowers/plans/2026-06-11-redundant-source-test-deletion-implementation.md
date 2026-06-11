# 冗余源码与测试删除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已批准设计对全仓库源码与测试做生产事实源反推审计，物理删除不再服务当前生产契约的旧代码、旧测试和旧辅助层。

**Architecture:** 主线程从 CLI、发行入口、当前 schema、Rust/native 主路径和用户可见契约反推可保留路径，并按模块批次执行删除和重接线。子代理只做并行发现、审核和复核，不直接改文件；验证在删除之后执行，且全量 `pytest` 只在最终收尾阶段运行。

**Tech Stack:** Python 3.14, uv, pytest, basedpyright, Rust 2024, PyO3, SQLite, pydantic v2, PowerShell, ripgrep.

---

## Source Spec

执行前必须阅读：

- `docs/superpowers/specs/2026-06-11-redundant-source-test-deletion-design.md`
- `AGENTS.md`
- `pyproject.toml`

本计划有意覆盖 `writing-plans` 默认 TDD 模板：用户和 spec 明确禁止用 TDD 推进本次工作。实现时不能先写失败测试驱动删除，不能为了让测试绿而新增 adapter、fallback、mock 成功或兼容层。

## Global Guardrails

- 旧代码必须证明自己仍属于当前生产契约；证明不了或证据不足就删除。
- 测试不是需求来源；测试依赖某个旧对象不是保留理由。
- Python/Rust 内部 public symbol、包根 re-export、`__all__` 和测试导入路径不是外部契约。
- 旧模块整体身份是历史包袱时，优先删整模块；当前生产需要的少量能力按当前边界重建或重接。
- 不修改 `docs/`、`skills/`、`README.md`、`CHANGELOG.md`、历史 records 和历史 plans，除本实施计划文件自身外。
- 主线程执行文件修改；子代理可并行发现、审核、复核，但不直接改文件。
- 执行中可以跑针对性测试、静态搜索、`uv run basedpyright` 和 CLI 抽样；全量 `uv run pytest` 只在最终收尾阶段运行。
- 如果触及 Rust 原生扩展、Rust 主路径、构建流程或发行流程，最终必须执行 `cargo fmt --check`、`cargo clippy`、`cargo test`。

## Target File Map

### Production Source Candidates

- Modify/Delete: `app/plugin_source_text/extraction.py`
- Modify/Delete: `app/plugin_source_text/scanner.py`
- Modify: `app/plugin_source_text/__init__.py`
- Modify: `app/plugin_source_text/importer.py`
- Modify: `app/plugin_source_text/rules.py`
- Modify: `app/plugin_source_text/runtime_audit.py`
- Modify/Delete: `app/note_tag_text/extraction.py`
- Modify: `app/note_tag_text/__init__.py`
- Modify: `app/native_note_tag_scan.py`
- Modify/Delete: `app/nonstandard_data/extraction.py`
- Modify: `app/nonstandard_data/__init__.py`
- Modify: `app/nonstandard_data/rules.py`
- Modify: `app/text_scope/write_probe.py`
- Modify: `app/text_scope/models.py`
- Modify: `app/agent_toolkit/placeholder_scan.py`
- Modify: `app/agent_toolkit/__init__.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/coverage.py`
- Modify: `app/agent_toolkit/services/manual_translation.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/agent_toolkit/services/workspace.py`

### Tests And Fixtures

- Modify/Delete: `tests/test_plugin_source_text.py`
- Modify/Delete: `tests/test_nonstandard_data.py`
- Modify/Delete: `tests/test_rmmz_note_nonstandard_data.py`
- Modify/Delete: `tests/test_agent_toolkit_rule_import.py`
- Modify/Delete: `tests/test_agent_toolkit_workspace.py`
- Modify/Delete: `tests/test_agent_toolkit_coverage.py`
- Modify/Delete: `tests/test_agent_toolkit_quality_report.py`
- Modify/Delete: `tests/test_agent_toolkit_feedback.py`
- Modify/Delete: `tests/test_agent_toolkit_manual_import.py`
- Modify/Delete: `tests/test_scan_budget.py`
- Modify/Delete: `tests/scan_budget_contract.py`
- Modify/Delete: `tests/test_stage0_canaries.py`
- Modify/Delete: `tests/current_text_fact_scope.py`
- Modify/Delete: `tests/agent_toolkit_contract_fixtures.py`
- Modify/Delete: `tests/rmmz_writeback_contract_fixtures.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_native_adapters.py`

### Engineering Entrypoints

- Modify: `scripts/benchmark_active_runtime_audit.py`
- Modify: `scripts/benchmark_rebuild_active_runtime.py`
- Modify: `scripts/build_release.py`
- Modify: `pyproject.toml`
- Modify/Delete: `typings/demjson3/__init__.pyi`
- Modify/Delete: `typings/json_repair/__init__.pyi`

## Subagent Use

At execution time, use subagents only for read-only work. If the current environment exposes a multi-agent tool, dispatch these prompts in parallel; otherwise run the listed `rg` commands in the main thread and treat their outputs as the same audit inputs.

### Subagent Prompt A: Production Reachability

```text
只读审计 <项目目录>。不要修改文件。基于 docs/superpowers/specs/2026-06-11-redundant-source-test-deletion-design.md，找出 app/、main.py、scripts/、pyproject.toml 中仍由当前 CLI、发行入口、SQLite schema、Rust/native 主路径或用户可见契约真实依赖的 plugin_source_text、note_tag_text、nonstandard_data、text_scope、agent_toolkit 路径。输出：1) 可证明生产需要保留的符号和文件；2) 无法证明生产需要的旧符号和文件；3) 证据命令或引用位置。不要使用测试引用作为保留证据。
```

### Subagent Prompt B: Test Debt And Fixtures

```text
只读审计 <项目目录>。不要修改文件。基于 docs/superpowers/specs/2026-06-11-redundant-source-test-deletion-design.md，审计 tests/ 中只保护旧实现、legacy 计数、scan_budget 历史账本、canary、mock、stub、fixture、旧 TranslationItem 形状、旧 scanner/extraction/fallback 的测试和 helper。输出：1) 默认应删除的测试函数或文件；2) 可改造成当前黑盒契约的测试；3) 不应保留的 monkeypatch 路径；4) 证据命令或引用位置。
```

### Subagent Prompt C: Post-Change Review

```text
只读复核 <项目目录>。不要修改文件。基于 docs/superpowers/specs/2026-06-11-redundant-source-test-deletion-design.md 和当前 git diff，检查是否仍有为了旧测试保留的源码、旧 fallback、旧 adapter、旧 scanner/extraction、legacy scan_budget 账本、包根 re-export 或只被测试引用的 helper。输出：发现列表、文件行号、为什么违反 spec、建议删除或当前契约重接方向。
```

## Task 1: Baseline And Production Fact Source Map

**Files:**
- Read: `docs/superpowers/specs/2026-06-11-redundant-source-test-deletion-design.md`
- Read: `AGENTS.md`
- Read: `main.py`
- Read: `app/cli_main.py`
- Read: `app/cli/parser.py`
- Read: `app/cli/runtime.py`
- Read: `app/persistence/schema/current.sql`
- Read: `pyproject.toml`

- [ ] **Step 1: Confirm worktree state**

Run:

```powershell
git status --short
git branch --show-current
git log -1 --oneline
```

Expected: know whether execution starts from a clean tree. If local changes exist, do not revert them; classify whether they are part of this cleanup before editing nearby files.

- [ ] **Step 2: Confirm production CLI and package entrypoints**

Run:

```powershell
rg -n "app.cli_main:main|def main|subparsers.add_parser|set_defaults|args.command|AgentToolkitService" main.py app\cli_main.py app\cli app\agent_toolkit pyproject.toml
```

Expected: list current CLI commands, CLI handler dispatch, and `att-mz = app.cli_main:main` entrypoint. Use this list as production reachability root.

- [ ] **Step 3: Map current high-risk imports outside tests**

Run:

```powershell
rg -n "plugin_source_text|note_tag_text|nonstandard_data|text_scope|placeholder_scan|write_probe|build_plugin_source_scan|scan_plugin_source_files_text_strict|scan_plugin_source_runtime_files_text_strict|TextScopeService|TranslationItem" app main.py scripts pyproject.toml -S
```

Expected: production-side references only. Any symbol that appears only in `tests/` is not preserved by this step.

- [ ] **Step 4: Map current high-risk imports in tests**

Run:

```powershell
rg -n "build_plugin_source_scan|scan_plugin_source_files_text_strict|scan_plugin_source_runtime_files_text_strict|clear_plugin_source_native_scan_cache|TextScopeService|current_text_fact_scope|scan_budget|canary|mock|stub|legacy|旧 scanner|测试专用|仅测试|fallback|兜底" tests -S
```

Expected: candidate deletion list for old tests and helpers.

- [ ] **Step 5: Dispatch read-only subagent discovery**

If subagent tools are available, dispatch Prompt A and Prompt B from the Subagent Use section in parallel. If they are not available, record that main-thread `rg` output from Steps 2-4 is the discovery input.

Expected: no files changed.

## Task 2: Plugin Source Text Legacy Scanner And Test Cleanup

**Files:**
- Modify/Delete: `app/plugin_source_text/extraction.py`
- Modify/Delete: `app/plugin_source_text/scanner.py`
- Modify: `app/plugin_source_text/__init__.py`
- Modify: `app/plugin_source_text/importer.py`
- Modify: `app/plugin_source_text/rules.py`
- Modify: `app/plugin_source_text/runtime_audit.py`
- Modify: `app/text_scope/write_probe.py`
- Modify/Delete: `tests/test_plugin_source_text.py`
- Modify/Delete: `tests/test_scan_budget.py`
- Modify/Delete: `tests/test_stage0_canaries.py`
- Modify: `tests/test_native_adapters.py`

- [ ] **Step 1: Prove current production use or delete old scanner symbols**

Run:

```powershell
rg -n "build_plugin_source_scan|scan_plugin_source_files_text_strict|scan_plugin_source_runtime_files_text_strict|clear_plugin_source_native_scan_cache|PluginSourceTextExtraction|_build_legacy|legacy" app main.py scripts -S
```

Expected: `build_plugin_source_scan`, `_build_legacy*`, `PluginSourceTextExtraction`, and test-only cache reset helpers have no current production proof. Delete their definitions and imports. If `scan_plugin_source_runtime_files_text_strict` is still used by current active-runtime production paths, keep only the production path and remove batch/cache tests that exist solely to protect internals.

- [ ] **Step 2: Remove package export preservation tests and re-exports**

Edit `app/plugin_source_text/__init__.py` and `tests/test_plugin_source_text.py` so package root exports only current production-level capabilities. Remove assertions that keep low-level scanner internals present in `scanner.__all__`.

Expected: no test asserts that old scanner internals remain exportable.

- [ ] **Step 3: Delete old batch/cache mechanism tests**

Remove tests whose purpose is internal old scanner batch/cache validation, including functions matching:

```text
test_plugin_source_scan_batches_native_ast_parse_for_source_files
test_plugin_source_scan_reuses_native_ast_by_file_hash
```

Also remove monkeypatches that only forbid old production paths after those paths are physically gone.

Expected: `rg -n "build_plugin_source_scan|clear_plugin_source_native_scan_cache|旧 scanner|batch/cache" tests\test_plugin_source_text.py tests\test_scan_budget.py tests\test_stage0_canaries.py -S` returns no old-path preservation assertions.

- [ ] **Step 4: Reconnect production callers to current native scan boundary**

Where production code still imports old plugin source scan wrappers, switch it to current native/Rust fact boundary already used by the production command. Do not add a compatibility wrapper with the old name.

Run:

```powershell
rg -n "build_plugin_source_scan|PluginSourceTextExtraction|scan_plugin_source_files_text_strict" app main.py scripts -S
```

Expected: no old production wrapper remains. If a remaining `scan_plugin_source_runtime_files_text_strict` is justified by active-runtime production, its caller must be production CLI reachable and its output must participate in current report or write mapping.

- [ ] **Step 5: Run targeted plugin source checks**

Run:

```powershell
uv run pytest tests/test_plugin_source_text.py tests/test_native_adapters.py -q
uv run basedpyright
```

Expected: targeted tests and type check pass. If failures come from deleted old tests or fixture assumptions, remove or rewrite those tests to current black-box contract rather than restoring old scanner code.

## Task 3: Note Tag And Nonstandard Data Extraction Cleanup

**Files:**
- Modify/Delete: `app/note_tag_text/extraction.py`
- Modify: `app/note_tag_text/__init__.py`
- Modify: `app/native_note_tag_scan.py`
- Modify/Delete: `app/nonstandard_data/extraction.py`
- Modify: `app/nonstandard_data/__init__.py`
- Modify: `app/nonstandard_data/rules.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/agent_toolkit/services/nonstandard_data.py`
- Modify/Delete: `tests/test_nonstandard_data.py`
- Modify/Delete: `tests/test_rmmz_note_nonstandard_data.py`
- Modify/Delete: `tests/test_agent_toolkit_rule_import.py`
- Modify/Delete: `tests/test_rule_import_transactions.py`

- [ ] **Step 1: Audit production references**

Run:

```powershell
rg -n "NoteTagTextExtraction|note_tag_location_path_matches_rule|nonstandard_data\.extraction|NonstandardDataTextExtraction|expand_rule_to_leaf_paths|_collect_rule_hits|native_note_tag_scan" app main.py scripts -S
```

Expected: old extraction classes and old Python rule-hit expansion either have current production proof or are deleted. Test-only references do not count as proof.

- [ ] **Step 2: Delete old extraction modules when unproven**

If `app/note_tag_text/extraction.py` or `app/nonstandard_data/extraction.py` only contains old Python extraction helpers, delete the file. Update `__init__.py` and production imports to current native/current-fact boundary.

Expected:

```powershell
rg -n "note_tag_text\.extraction|nonstandard_data\.extraction|NoteTagTextExtraction|NonstandardDataTextExtraction" app tests scripts -S
```

returns no import that requires the old modules.

- [ ] **Step 3: Remove tests that preserve Python extraction as an oracle**

In the listed test files, remove tests that compare Rust/native output against old Python extraction, old path expansion, or old location matching. Keep tests that verify current CLI-facing rule validation, import reports, stale fact behavior, and JSON report fields.

Expected: remaining tests describe current report/status/error behavior, not old extraction internals.

- [ ] **Step 4: Run targeted note/nonstandard checks**

Run:

```powershell
uv run pytest tests/test_nonstandard_data.py tests/test_rmmz_note_nonstandard_data.py tests/test_agent_toolkit_rule_import.py tests/test_rule_import_transactions.py -q
uv run basedpyright
```

Expected: targeted checks and type check pass. Do not restore old extraction modules to satisfy tests.

## Task 4: Text Scope, Write Probe, And TranslationItem Shape Cleanup

**Files:**
- Modify: `app/text_scope/write_probe.py`
- Modify: `app/text_scope/models.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/coverage.py`
- Modify: `app/agent_toolkit/services/manual_translation.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Modify/Delete: `tests/current_text_fact_scope.py`
- Modify/Delete: `tests/agent_toolkit_contract_fixtures.py`
- Modify/Delete: `tests/rmmz_writeback_contract_fixtures.py`
- Modify/Delete: `tests/test_agent_toolkit_coverage.py`
- Modify/Delete: `tests/test_agent_toolkit_quality_report.py`
- Modify/Delete: `tests/test_agent_toolkit_manual_import.py`
- Modify/Delete: `tests/test_agent_toolkit_feedback.py`

- [ ] **Step 1: Identify old write-probe and TranslationItem-shape callers**

Run:

```powershell
rg -n "collect_write_back_probe_reasons|collect_native_write_protocol_details|include_write_probe|TextScopeService|TranslationItem|current_text_fact_scope|rebuild_current_text_fact_scope_for_test|read_current_text_fact_scope_for_test" app tests -S
```

Expected: production uses of `include_write_probe` map to current Rust/native gate behavior, not Python write probe reconstruction. Test-only helpers that manually build current facts are deletion candidates unless they prove a current black-box contract.

- [ ] **Step 2: Delete or shrink test-only current fact builders**

Delete `tests/current_text_fact_scope.py` if all callers can instead use current production rebuild/index preparation helpers. If a small helper remains necessary, move it into the specific test file and make it call production rebuild/read functions without constructing legacy shapes by hand.

Expected: no global helper exists only to let old tests bypass production flow.

- [ ] **Step 3: Remove old write-probe protection tests**

Delete tests that only assert Python write probe is not called via monkeypatch after the Python probe is removed or no longer reachable. Keep tests that assert user-visible report fields and error codes for current Rust/native write gate.

Expected:

```powershell
rg -n "include_write_probe 不应|write_probe_failed|collect_native_write_protocol_details|collect_write_back_probe_reasons" tests -S
```

shows only current black-box report behavior, not monkeypatch protection for old internals.

- [ ] **Step 4: Run targeted text-scope checks**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py -q
uv run basedpyright
```

Expected: targeted checks and type check pass. Failures from old helper deletion are resolved by deleting old tests or using production current-fact setup.

## Task 5: Agent Toolkit Service And Placeholder Legacy Cleanup

**Files:**
- Modify/Delete: `app/agent_toolkit/placeholder_scan.py`
- Modify: `app/agent_toolkit/__init__.py`
- Modify: `app/agent_toolkit/service.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/agent_toolkit/services/placeholder_rules.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify/Delete: `tests/test_agent_toolkit_rule_import.py`
- Modify/Delete: `tests/test_agent_toolkit_coverage.py`
- Modify: `tests/test_native_adapters.py`

- [ ] **Step 1: Prove or delete Python placeholder scan module**

Run:

```powershell
rg -n "agent_toolkit\.placeholder_scan|scan_placeholder_candidates\(|placeholder_candidates_to_details|count_uncovered_candidates|PlaceholderCandidate" app tests scripts -S
```

Expected: if `app/agent_toolkit/placeholder_scan.py` has no current production caller, delete it and remove public exports/tests. Current placeholder behavior must rely on native/current text fact coverage paths.

- [ ] **Step 2: Remove service adapters that only preserve old flows**

Run:

```powershell
rg -n "fallback|legacy|old|compat|旧|兜底|mock|stub|TextScopeService|build_.*coverage_result|scan_placeholder_candidates" app\agent_toolkit tests -S
```

Expected: service functions that exist only for old tests are deleted or folded into current production service methods. Do not add wrapper methods to preserve old test imports.

- [ ] **Step 3: Target current placeholder/rule import contract tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_coverage.py tests/test_native_adapters.py -q
uv run basedpyright
```

Expected: current placeholder/rule import behavior passes. Old helper tests are removed rather than repaired.

## Task 6: Scan Budget, Canary, And Historical Ledger Cleanup

**Files:**
- Modify/Delete: `tests/test_scan_budget.py`
- Modify/Delete: `tests/scan_budget_contract.py`
- Modify/Delete: `tests/test_stage0_canaries.py`
- Modify: `tests/test_native_adapters.py`

- [ ] **Step 1: Remove history-ledger assertions**

Run:

```powershell
rg -n "batch|legacy|残留|record|记录|scan_budget_contract|remaining_legacy|classified|公共 API|__all__|canary" tests\test_scan_budget.py tests\scan_budget_contract.py tests\test_stage0_canaries.py tests\test_native_adapters.py -S
```

Expected: identify tests that protect migration records, legacy counts, package export shape, or old canary paths. Delete those tests and supporting contract rows.

- [ ] **Step 2: Keep only current production complexity checks**

If `tests/scan_budget_contract.py` still provides current command complexity contracts, shrink it to commands that are current CLI P0/P1 and assert current production behavior. Delete entries whose only purpose is historical batch accounting.

Expected: `scan_budget` tests no longer refer to batch numbers, legacy residual counts, or record existence.

- [ ] **Step 3: Run targeted budget/canary checks**

Run:

```powershell
uv run pytest tests/test_scan_budget.py tests/test_stage0_canaries.py tests/test_native_adapters.py -q
uv run basedpyright
```

Expected: remaining tests are current production checks. If a test fails because a historical ledger row was deleted, delete the test rather than restoring the row.

## Task 7: Fixtures, Conftest, And Test Data Cleanup

**Files:**
- Modify: `tests/conftest.py`
- Modify/Delete: `tests/agent_toolkit_contract_fixtures.py`
- Modify/Delete: `tests/rmmz_writeback_contract_fixtures.py`
- Modify/Delete: `tests/_native_write_plan_helper.py`
- Modify/Delete: affected `tests/test_*.py` callers found by search

- [ ] **Step 1: Map fixture-only APIs**

Run:

```powershell
rg -n "测试专用|stub|mock|fake|helper|fixture|directly insert|直接插入|TranslationItem|source_snapshot|current text fact|write_plugin_source_stubs|_native_write_plan_helper" tests -S
```

Expected: list test helpers that construct old shapes or bypass current production flow.

- [ ] **Step 2: Delete helpers whose only callers are deleted old tests**

Start with known high-risk helper names, then repeat the same pattern for any additional helpers found in Step 1:

```powershell
rg -n "write_plugin_source_stubs|rebuild_current_text_fact_scope_for_test|read_current_text_fact_scope_for_test|insert_stale_translation_for_test|_create_test_source_snapshot|_native_write_plan_helper" tests app -S
```

If callers are only old tests removed in Tasks 2-6, delete the helper and its exports.

Expected: no orphan fixture exports remain.

- [ ] **Step 3: Keep realistic production setup helpers only**

For remaining tests, prefer helpers that run production registration, rebuild, import, or current text fact read paths. Do not keep helpers that manually construct old `TranslationItem` identities unless the test is about current public import/export behavior and no production alternative exists.

Expected: fixture files shrink or disappear; test setup names describe current user-visible behavior.

- [ ] **Step 4: Run broad targeted fixture users**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_agent_toolkit_workspace.py tests/test_rmmz_write_plan.py tests/test_write_back_transactions.py -q
uv run basedpyright
```

Expected: fixture-dependent current behavior passes. Failures from deleted old fixtures are resolved by removing old tests or switching to production setup helpers.

## Task 8: Scripts, Typings, Config, And Secondary Legacy Modules

**Files:**
- Modify: `scripts/benchmark_active_runtime_audit.py`
- Modify: `scripts/benchmark_rebuild_active_runtime.py`
- Modify: `scripts/build_release.py`
- Modify: `pyproject.toml`
- Modify/Delete: `typings/demjson3/__init__.pyi`
- Modify/Delete: `typings/json_repair/__init__.pyi`
- Modify/Delete: secondary old extraction modules discovered by search

- [ ] **Step 1: Sweep non-doc engineering files**

Run:

```powershell
rg -n "legacy|fallback|deprecated|compat|old|mock|stub|scan_budget|canary|extraction|scanner|TextScopeService|TranslationItem|旧|兜底|测试专用|仅测试" scripts typings pyproject.toml app tests -S
```

Expected: remaining non-doc old references are either current production facts or deletion candidates.

- [ ] **Step 2: Delete secondary old extraction modules**

If files such as `app/event_command_text/extraction.py` or `app/plugin_text/extraction.py` exist and have no current production proof, delete them and update package roots/tests.

Run:

```powershell
Test-Path app\event_command_text\extraction.py
Test-Path app\plugin_text\extraction.py
rg -n "event_command_text\.extraction|plugin_text\.extraction|EventCommandTextExtraction|PluginTextExtraction" app tests scripts -S
```

Expected: no old extraction import remains.

- [ ] **Step 3: Remove unused stubs and dependencies only when proven**

Run:

```powershell
rg -n "demjson3|json_repair" app tests scripts pyproject.toml typings -S
```

Expected: delete a typing stub or dependency only if no production code imports it. Do not remove a dependency used by current external input parsing, release scripts, or CLI paths.

- [ ] **Step 4: Run engineering targeted checks**

Run:

```powershell
uv run pytest tests/test_benchmark_active_runtime_audit.py tests/test_benchmark_rebuild_active_runtime.py tests/test_release_package_layout.py -q
uv run basedpyright
```

Expected: scripts and packaging checks pass if touched.

## Task 9: Read-Only Post-Change Review

**Files:**
- Read: all modified files from `git diff --name-only`

- [ ] **Step 1: Dispatch post-change subagent review**

If subagent tools are available, dispatch Prompt C from the Subagent Use section. If not, run the searches in Steps 2-4 manually.

Expected: read-only findings only.

- [ ] **Step 2: Search for old code categories**

Run:

```powershell
rg -n "legacy|fallback|deprecated|compat|old|mock|stub|scan_budget|canary|TextScopeService|build_plugin_source_scan|PluginSourceTextExtraction|NoteTagTextExtraction|NonstandardDataTextExtraction|旧 scanner|历史批次|迁移残留|测试专用|仅测试|兜底" app tests scripts typings pyproject.toml -S
```

Expected: remaining hits are either user-facing words with current meaning, current production behavior, or removed. No hit should exist solely to protect old tests.

- [ ] **Step 3: Search for package root re-export preservation**

Run:

```powershell
rg -n "__all__|hasattr\(|package_exports|scanner_exports|公共 API|public surface" app tests -S
```

Expected: tests no longer preserve internal package exports as external contract. Production `__all__` lists do not include deleted legacy symbols.

- [ ] **Step 4: Search for test-only production imports**

Run:

```powershell
rg -n "from app\..* import|import app\." tests -S
```

Expected: imports point at current production API used by black-box behavior tests. Imports of deleted helpers are removed.

## Task 10: Final Verification And Commit

**Files:**
- Modify: all source/test files changed by Tasks 2-8

- [ ] **Step 1: Run diff and whitespace checks**

Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors. Status contains only intended source/test/engineering changes.

- [ ] **Step 2: Run final type check**

Run:

```powershell
uv run basedpyright
```

Expected: `0 errors, 0 warnings, 0 notes`.

- [ ] **Step 3: Run final full pytest once**

Run:

```powershell
uv run pytest
```

Expected: full test suite passes. This command is intentionally delayed until final收尾 because it is expensive.

- [ ] **Step 4: Run Rust checks if Rust or build flow was touched**

Run only if `git diff --name-only` includes `rust/`, `Cargo.toml`, `Cargo.lock`, `pyproject.toml` build settings, `scripts/build_release.py`, or release package mapping:

```powershell
cargo fmt --check --manifest-path rust\Cargo.toml
cargo clippy --manifest-path rust\Cargo.toml --all-targets --all-features
cargo test --manifest-path rust\Cargo.toml
```

Expected: all Rust checks pass. If Rust was not touched, record that these checks were not required.

- [ ] **Step 5: Run representative CLI smoke checks**

Run commands selected from the modified domains. Use a temporary game fixture or existing test fixture command pattern, not private user data. Minimum command set:

```powershell
uv run python main.py --help
uv run python main.py scan-placeholder-candidates --help
uv run python main.py validate-placeholder-rules --help
uv run python main.py rebuild-text-index --help
uv run python main.py quality-report --help
```

Expected: commands display help successfully. If a realistic temporary MV/MZ fixture is available from tests, also run one current text index rebuild and one affected rule-scan command against that fixture.

- [ ] **Step 6: Commit implementation**

Run:

```powershell
git add app rust tests scripts typings pyproject.toml main.py
git commit -m "refactor: 删除冗余源码与测试旧路径"
```

Expected: commit contains only intended cleanup implementation. Do not stage `docs/`, `skills/`, generated outputs, logs, data, `.venv`, or build artifacts.

## Plan Self-Review

- Spec coverage: tasks cover production fact source mapping, default deletion, tests as cleanup objects, module batch execution, scan budget/canary cleanup, fixture cleanup, subagent read-only usage, final-only full pytest, and final verification.
- Non-TDD override: every task deletes/audits/reconnects first, then verifies. No step writes a failing test first.
- Scope control: implementation tasks do not modify `docs/`, `skills/`, README, CHANGELOG, records, outputs, data, logs, target, or virtualenv.
- Validation control: targeted tests are allowed during execution; full `uv run pytest` appears only in Task 10 final verification.
