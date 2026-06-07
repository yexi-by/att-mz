# Text Fact Contract v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the breaking `Text Fact Contract v2` described in `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`.

**Architecture:** Rust becomes the only producer of text facts: `rebuild-text-index` scans source files, classifies text, writes v2 fact tables, render parts, hashes, scope, and existing warm index summaries in one SQLite transaction. Python reads typed v2 facts through a thin adapter, keeps CLI/config/report orchestration, and removes migrated Python full-scope fact reconstruction paths.

**Tech Stack:** Python 3.14, pydantic v2, argparse, aiosqlite, pytest, basedpyright, Rust 2024, PyO3, maturin, rusqlite, rayon, serde_json, cargo fmt, clippy, cargo test.

---

## Scope Check

The spec intentionally spans multiple subsystems. Treat this file as the master implementation plan and each numbered task as a separately reviewable batch. Do not merge two tasks into one large change; each task must leave the project in a testable state and must not introduce a production v1/v2 double fact source for the commands already migrated in that task.

Hard stop and return to design discussion if any migrated command can only work by rebuilding a full Python text scope, if render parts cannot reconstruct raw source text, if v2 schema starts pushing core fields into JSON blobs, or if compatibility with old databases becomes the main implementation work.

## File Structure

- Modify `app/persistence/schema/current.sql`: bump the database schema and add `text_facts_v2`, `text_fact_render_parts_v2`, `text_fact_domain_payloads_v2`, `text_fact_scope_v2`, plus declared indexes.
- Modify `app/persistence/sql.py`: add v2 table constants, create/select/delete/insert SQL, include v2 tables in `EXPECTED_STATIC_TABLE_NAMES`, and bump `CURRENT_SCHEMA_VERSION`.
- Modify `app/persistence/records.py`: add typed dataclasses for v2 facts, render parts, payloads, scope, and fact read filters.
- Create `app/persistence/text_fact_records.py`: own all Python reads of v2 fact tables and explicit v2 contract failures.
- Modify `app/persistence/repository.py`: mix `TextFactRecordSessionMixin` into `TargetGameSession`.
- Modify `app/native_scope_index.py`: expose native v2 rebuild/storage contract fields and convert Rust structured errors without fallback.
- Modify `app/text_index.py`: replace migrated command adapters with v2 fact adapters while keeping existing index summary helpers only where not yet migrated.
- Create `app/text_facts.py`: Python-side typed adapter from v2 facts to translation prompt items, coverage rows, placeholder scan text inputs, and user-facing report samples.
- Modify `app/application/handler.py`: migrate `translate` and source flow gates to v2 facts.
- Modify `app/application/use_cases/translation_run.py`: deduplicate and batch by `translatable_text` identity instead of old `original_lines` identity for migrated paths.
- Modify `app/translation/context.py`, `app/translation/batch.py`, `app/translation/verify.py`: ensure prompt construction and quality verification use `translatable_text` for正文 and do not expose raw selector, `location_path`, or internal field names in user prompts.
- Modify `app/agent_toolkit/services/text_index.py`: surface v2 fact counts, scope status, and Rust timings from `rebuild-text-index`.
- Modify `app/agent_toolkit/services/coverage.py`: migrate `text-scope` and `audit-coverage` to v2 facts.
- Modify `app/agent_toolkit/services/quality.py`: migrate `quality-report`, `translation-status --refresh-scope`, feedback, active runtime diagnostics, and quality gate reads in their assigned tasks.
- Modify `app/agent_toolkit/services/workspace.py`: write/read v2 workspace scope, validate v2 scope, and stop accepting old workspace candidates for migrated rule flows.
- Modify `app/agent_toolkit/services/placeholder_rules.py`: consume v2 fact text inputs and Rust rule-hit facts for placeholder and structured placeholder flows.
- Modify `app/agent_toolkit/services/rule_validation.py`: migrate MV namebox, plugin, event command, note tag, nonstandard data, and plugin source rule import validation to v2 facts in assigned tasks.
- Modify `app/agent_toolkit/services/manual_translation.py`: export/import manual translations by v2 fact identity.
- Modify `app/native_write_plan.py`: parse v2 write-back summaries and runtime map hashes from Rust.
- Modify `app/native_quality.py`, `app/native_placeholder_scan.py`, `app/native_structured_placeholder_scan.py`, `app/native_note_tag_scan.py`, `app/native_javascript_ast.py`: remove migrated Python-shaped payload builders once v2 fact readers provide the inputs.
- Modify `app/plugin_source_text/runtime_mapping.py`, `app/plugin_source_text/runtime_audit.py`, `app/nonstandard_data/runtime_audit.py`: use v2 runtime literal facts and v2 hashes.
- Modify `rust/src/lib.rs`: bump native contract version and expose any new native inspection helpers required by Python tests.
- Modify `rust/src/native_core.rs`: wire new text fact modules.
- Create `rust/src/native_core/text_facts.rs`: own v2 schema constants, domains, hash inputs, render part model, fact id construction, validation, and common tests.
- Modify `rust/src/native_core/scope_index/storage.rs`: write and inspect v2 fact tables in the same transaction as warm index summaries.
- Modify `rust/src/native_core/scope_index/rebuild.rs`: build v2 facts from the cold scan, write fact scope metadata, and report fact/domain counts and cold/stale status.
- Modify `rust/src/native_core/scope_index/mv_virtual_namebox.rs`: preserve raw body whitespace and produce speaker/body render parts.
- Modify `rust/src/native_core/scope_index/{event_commands.rs,plugin_config.rs,note_tags.rs,nonstandard_data.rs,plugin_source.rs,placeholders.rs,structured_placeholders.rs}`: emit or refine v2 domain payloads in the assigned batches.
- Modify `rust/src/native_core/write_back_plan/{repository.rs,models.rs,mod.rs,data_writer.rs,command_writer.rs,mv_virtual_namebox.rs,plugin_config_writer.rs,plugin_source.rs,nonstandard_data_writer.rs,note_writer.rs,terminology.rs}`: consume v2 facts/render parts and remove old text index reconstruction for migrated domains.
- Modify tests in `tests/test_persistence.py`, `tests/test_native_scope_index.py`, `tests/test_text_index.py`, `tests/test_agent_toolkit_coverage.py`, `tests/test_agent_toolkit_quality_report.py`, `tests/test_agent_toolkit_workspace.py`, `tests/test_agent_toolkit_manual_import.py`, `tests/test_agent_toolkit_rule_import.py`, `tests/test_agent_toolkit_feedback.py`, `tests/test_translation_cache_context.py`, `tests/test_translation_run_limits.py`, `tests/test_scan_budget.py`, `tests/test_rmmz_mv_namebox.py`, `tests/test_rmmz_write_plan.py`, `tests/test_plugin_source_text.py`, `tests/test_nonstandard_data.py`, and Rust unit tests under `rust/src/native_core`.
- Modify `docs/`, `README.md`, `skills/att-mz-protocol/`, `skills/att-mz/`, and `skills/att-mz-release/` only in the final documentation task if user-visible facts, troubleshooting, or Skill protocol text changed.

---

### Task 1: v2 SQLite Contract And Python Persistence Adapter

**Files:**
- Modify: `app/persistence/schema/current.sql`
- Modify: `app/persistence/sql.py`
- Modify: `app/persistence/records.py`
- Create: `app/persistence/text_fact_records.py`
- Modify: `app/persistence/repository.py`
- Test: `tests/test_persistence.py`

- [ ] **Step 1: Write failing schema tests**

Add tests proving the shared schema creates all four v2 tables, v2 indexes, `schema_version=current` at the new database version, and exact table signatures. Add a persistence test that writes minimal v2 rows with render parts and reads them back in deterministic order.

- [ ] **Step 2: Run focused RED tests**

Run:

```powershell
uv run pytest tests/test_persistence.py::test_shared_current_schema_resource_creates_declared_static_table_set tests/test_persistence.py::test_text_fact_v2_records_replace_read_and_require_scope -q
```

Expected: FAIL because v2 tables and `TextFactRecordSessionMixin` do not exist.

- [ ] **Step 3: Add schema and SQL constants**

Add the four v2 tables exactly as the design states, add declared indexes, bump `CURRENT_SCHEMA_VERSION`, and include the v2 table names in `EXPECTED_STATIC_TABLE_NAMES`. Keep `app/persistence/schema/current.sql` as the single source used by Python and Rust.

- [ ] **Step 4: Add typed persistence records**

Add dataclasses for:

- `TextFactV2Record`
- `TextFactRenderPartV2Record`
- `TextFactDomainPayloadV2Record`
- `TextFactScopeV2Record`
- `TextFactV2ReadFilter`

Each record must carry `schema_version`, `domain`, `location_path`, `raw_text`, `visible_text`, `translatable_text`, `raw_hash`, `visible_hash`, `translatable_hash`, and `scope_key` without trimming.

- [ ] **Step 5: Add `TextFactRecordSessionMixin`**

Implement replace/read helpers:

- `replace_text_facts_v2(...)`
- `read_text_fact_scope_v2(scope_key: str)`
- `require_current_text_fact_scope_v2(scope_key: str)`
- `read_text_facts_v2(filter: TextFactV2ReadFilter | None = None)`
- `read_text_fact_render_parts_v2(fact_ids: Sequence[str])`
- `read_text_fact_domain_payloads_v2(fact_ids: Sequence[str])`
- `count_text_facts_v2()`

The required-scope helper must fail explicitly for missing table, missing scope, unsupported schema version, and scope mismatch messages that explain what happened, what command is affected, and the next command to run.

- [ ] **Step 6: Run focused GREEN tests**

Run:

```powershell
uv run pytest tests/test_persistence.py -q
```

Expected: PASS for persistence and schema tests.

- [ ] **Step 7: Commit**

```powershell
git add app/persistence/schema/current.sql app/persistence/sql.py app/persistence/records.py app/persistence/text_fact_records.py app/persistence/repository.py tests/test_persistence.py
git commit -m "feat: add text fact v2 persistence contract"
```

---

### Task 2: Rust v2 Fact Model, Hashes, And Storage Writer

**Files:**
- Create: `rust/src/native_core/text_facts.rs`
- Modify: `rust/src/native_core.rs`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Modify: `rust/src/lib.rs`
- Modify: `app/native_contract.py`
- Modify: `app/native_scope_index.py`
- Test: `rust/src/native_core/text_facts.rs`
- Test: `rust/src/native_core/scope_index/storage.rs`
- Test: `tests/test_native_scope_index.py`

- [ ] **Step 1: Write failing Rust storage tests**

Add tests for:

- hash inputs: `raw_hash=sha256(raw_text)`, `visible_hash=sha256(visible_text)`, `translatable_hash=sha256(translatable_text)`;
- reject empty or whitespace-only MV speaker facts;
- write one fact with four MV render parts and one domain payload;
- reject metadata item/fact count mismatch;
- delete old v2 facts atomically when a new rebuild writes a new scope.

- [ ] **Step 2: Write failing Python native contract tests**

Extend `tests/test_native_scope_index.py` to assert that native rebuild/write output includes `text_fact_count`, `render_part_count`, `scope_key`, `scope_hash`, and `text_fact_schema_version`.

- [ ] **Step 3: Run RED tests**

Run:

```powershell
cd rust
cargo test text_fact
cd ..
uv run pytest tests/test_native_scope_index.py -q
```

Expected: Rust tests fail because `text_facts` does not exist; Python tests fail because native output has no v2 counts.

- [ ] **Step 4: Implement Rust common fact model**

Create the native model with:

- `TEXT_FACT_SCHEMA_VERSION: i64 = 2`
- domain constants from the design
- `TextFact`
- `TextFactRenderPart`
- `TextFactDomainPayload`
- `TextFactScope`
- stable SHA-256 helpers
- `fact_id` builder based on schema version, domain, location path, selector, and raw hash
- `scope_key` builder that includes schema version and source/rule/text-rule hashes

- [ ] **Step 5: Write v2 tables in storage transaction**

Extend `WriteStoragePayload` and `write_text_index_storage` so one transaction deletes and rewrites old warm index summaries plus v2 fact tables. Keep foreign keys enabled and use prepared statements for all fact/render/payload inserts.

- [ ] **Step 6: Expose native contract fields**

Bump `NATIVE_CONTRACT_VERSION`, update `app/native_contract.py`, parse new native output fields in `app/native_scope_index.py`, and keep structured Rust errors surfaced through `NativeScopeIndexStorageError`.

- [ ] **Step 7: Run GREEN tests**

Run:

```powershell
cd rust
cargo test text_fact
cargo test scope_index::storage
cd ..
uv run pytest tests/test_native_scope_index.py -q
```

Expected: Rust fact/storage tests pass and Python native adapter tests pass.

- [ ] **Step 8: Commit**

```powershell
git add rust/src/native_core/text_facts.rs rust/src/native_core.rs rust/src/native_core/scope_index/storage.rs rust/src/lib.rs app/native_contract.py app/native_scope_index.py tests/test_native_scope_index.py
git commit -m "feat: write text fact v2 from native storage"
```

---

### Task 3: Batch 1 Rebuild Facts And MV Virtual Namebox Semantics

**Files:**
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/scope_index/mv_virtual_namebox.rs`
- Modify: `rust/src/native_core/write_back_plan/mv_virtual_namebox.rs`
- Modify: `app/text_index.py`
- Modify: `app/agent_toolkit/services/text_index.py`
- Test: `rust/src/native_core/scope_index/rebuild.rs`
- Test: `rust/src/native_core/scope_index/mv_virtual_namebox.rs`
- Test: `tests/test_native_scope_index.py`
- Test: `tests/test_text_index.py`
- Test: `tests/test_rmmz_mv_namebox.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing MV fact tests**

Add tests using raw text `"\n<Dan:> Hello"` and assert:

- `raw_text == "\n<Dan:> Hello"`;
- `visible_text == "\n<Dan:> Hello"`;
- `translatable_text == "Hello"`;
- `role == "Dan"`;
- render parts are `literal`, `speaker`, `literal`, `translated_body`;
- source reconstruction from raw parts equals the original raw text;
- translated reconstruction preserves `:> ` spacing.

- [ ] **Step 2: Write failing rebuild tests**

Extend native rebuild tests so `rebuild_scope_index_storage` writes v2 facts for `standard_data`, `event_command`, and `mv_virtual_namebox`. For domains not yet specialized, the first batch may use a single `translated_body` render part only when `raw_text == visible_text == translatable_text`.

- [ ] **Step 3: Run RED tests**

Run:

```powershell
cd rust
cargo test mv_virtual_namebox
cargo test rebuild_scope_index_storage
cd ..
uv run pytest tests/test_native_scope_index.py tests/test_text_index.py tests/test_rmmz_mv_namebox.py tests/test_scan_budget.py -q
```

Expected: tests fail because rebuild does not write v2 facts and MV body whitespace is still mixed with translatable body.

- [ ] **Step 4: Generate facts during Rust cold rebuild**

In `rebuild.rs`, build v2 facts alongside current `DirectTextIndexRow` values. Keep existing warm `text_index_items` summaries for commands not yet migrated, but make v2 facts the source of all new semantic fields.

- [ ] **Step 5: Preserve MV raw/render/translatable split**

Stop trimming the candidate before fact construction. Capture raw prefix, source speaker, separator, and raw body shell into render parts; set only the semantic body as `translatable_text`. Reject empty, invisible, or whitespace-only speakers with a structured error.

- [ ] **Step 6: Surface v2 rebuild summary**

Add `text_fact_count`, `render_part_count`, `scope_key`, `scope_hash`, `source_snapshot_hash`, `rule_hash`, `text_rules_hash`, `domain_fact_counts`, `scan_file_count`, and `index_status` to `rebuild-text-index` reports.

- [ ] **Step 7: Run GREEN tests**

Run:

```powershell
cd rust
cargo test mv_virtual_namebox
cargo test rebuild_scope_index_storage
cd ..
uv run pytest tests/test_native_scope_index.py tests/test_text_index.py tests/test_rmmz_mv_namebox.py tests/test_scan_budget.py -q
```

Expected: Batch 1 tests pass and scan budget still proves warm-index commands do not build Python full text scope.

- [ ] **Step 8: Record Batch 1 performance evidence**

Run on the configured fixture or user-provided sample:

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```

Record in the task notes: command duration, fact count, render part count, scanned file count, native thread count, and internal Rust stage timings. Do not commit local benchmark artifacts.

- [ ] **Step 9: Commit**

```powershell
git add rust/src/native_core/scope_index/rebuild.rs rust/src/native_core/scope_index/mv_virtual_namebox.rs rust/src/native_core/write_back_plan/mv_virtual_namebox.rs app/text_index.py app/agent_toolkit/services/text_index.py tests/test_native_scope_index.py tests/test_text_index.py tests/test_rmmz_mv_namebox.py tests/test_scan_budget.py
git commit -m "feat: rebuild text fact v2 index"
```

---

### Task 4: Python v2 Adapter And Core Translation Commands

**Files:**
- Create: `app/text_facts.py`
- Modify: `app/application/handler.py`
- Modify: `app/application/use_cases/translation_run.py`
- Modify: `app/translation/context.py`
- Modify: `app/translation/batch.py`
- Modify: `app/translation/verify.py`
- Modify: `app/text_index.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Test: `tests/test_translation_cache_context.py`
- Test: `tests/test_translation_run_limits.py`
- Test: `tests/test_agent_toolkit_translation_limits.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_quality_report.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing adapter tests**

Add tests proving v2 facts convert to prompt items using `translatable_text`, deduplicate by `translatable_hash`, preserve `role` separately, and never include raw selector, `location_path`, source file names, `translated_text`, or `位置:` in the final user prompt.

- [ ] **Step 2: Write failing core command tests**

Update `translate`, `translation-status --refresh-scope`, and pending export tests so warm v2 facts are used and old `text_index_items.original_lines` is not the semantic source for migrated flows.

- [ ] **Step 3: Run RED tests**

Run:

```powershell
uv run pytest tests/test_translation_cache_context.py tests/test_translation_run_limits.py tests/test_agent_toolkit_translation_limits.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_quality_report.py tests/test_scan_budget.py -q
```

Expected: tests fail because Python still builds prompt items from old index rows.

- [ ] **Step 4: Add `app/text_facts.py` adapter**

Implement typed adapters for:

- fact-to-translation prompt item;
- pending fact SQL reads;
- fact-to-quality input using `visible_text` only where quality needs player-visible source;
- fact-to-manual template entry;
- fact-to-coverage row for migrated reports.

Adapters must refuse unsupported schema versions and missing v2 scope with user-actionable Chinese errors.

- [ ] **Step 5: Migrate `translate` to v2 facts**

Replace `read_pending_text_index_items` and `text_index_items_to_translation_data_map` in the production translate path with v2 pending fact readers. Keep existing run tables for saved translations and quality errors, but treat saved translation identity as v2 fact identity.

- [ ] **Step 6: Migrate prompt and verification contract**

Ensure prompt construction uses `translatable_text` and the verifier checks translation output against the same semantic body. Raw shell, selector, render parts, and domain payloads must not enter model prompts.

- [ ] **Step 7: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_translation_cache_context.py tests/test_translation_run_limits.py tests/test_agent_toolkit_translation_limits.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_quality_report.py tests/test_scan_budget.py -q
```

Expected: core translation commands read v2 facts and prompt leakage tests pass.

- [ ] **Step 8: Commit**

```powershell
git add app/text_facts.py app/application/handler.py app/application/use_cases/translation_run.py app/translation/context.py app/translation/batch.py app/translation/verify.py app/text_index.py app/agent_toolkit/services/quality.py tests/test_translation_cache_context.py tests/test_translation_run_limits.py tests/test_agent_toolkit_translation_limits.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_quality_report.py tests/test_scan_budget.py
git commit -m "feat: translate from text fact v2"
```

---

### Task 5: Core Reports Use v2 Facts

**Files:**
- Modify: `app/agent_toolkit/services/coverage.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Modify: `app/agent_toolkit/reports.py`
- Modify: `app/text_facts.py`
- Modify: `app/text_index.py`
- Test: `tests/test_agent_toolkit_coverage.py`
- Test: `tests/test_agent_toolkit_quality_report.py`
- Test: `tests/test_cli_json_output.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing report tests**

Update `text-scope`, `audit-coverage`, and `quality-report` tests to require v2 fact counts, `used/cold_rebuilt/stale_rebuilt/rebuild_failed` index status, and visible/raw short samples in error details. Add a regression where raw formatting whitespace must not count as正文 quality failure.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py tests/test_cli_json_output.py tests/test_scan_budget.py -q
```

Expected: tests fail where reports still depend on old index row semantics.

- [ ] **Step 3: Migrate `text-scope` and `audit-coverage`**

Read v2 facts through `app/text_facts.py`, use SQL counts where possible, and keep report detail sampling bounded. Do not load game data or build full Python scope in warm mode.

- [ ] **Step 4: Migrate `quality-report`**

Use v2 facts for source inputs, saved translation joins, quality error joins, and write-back probe allowed paths. Quality checks that need player-visible source use `visible_text`; checks that need model正文 use `translatable_text`.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py tests/test_cli_json_output.py tests/test_scan_budget.py -q
```

Expected: report tests pass and warm report commands do not hit Python full-scope builders.

- [ ] **Step 6: Record Batch 2 performance evidence**

Run:

```powershell
uv run python main.py translation-status --game <游戏标题> --refresh-scope
uv run python main.py text-scope --game <游戏标题>
uv run python main.py audit-coverage --game <游戏标题>
uv run python main.py quality-report --game <游戏标题>
```

Record command durations, fact counts, whether the index was `used/cold_rebuilt/stale_rebuilt`, and whether any Python full scan was added.

- [ ] **Step 7: Commit**

```powershell
git add app/agent_toolkit/services/coverage.py app/agent_toolkit/services/quality.py app/agent_toolkit/reports.py app/text_facts.py app/text_index.py tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py tests/test_cli_json_output.py tests/test_scan_budget.py
git commit -m "feat: report from text fact v2"
```

---

### Task 6: Workspace, Rules, Placeholder, And MV Rule Flows

**Files:**
- Modify: `app/agent_toolkit/services/workspace.py`
- Modify: `app/agent_toolkit/services/placeholder_rules.py`
- Modify: `app/agent_toolkit/services/rule_validation.py`
- Modify: `app/native_placeholder_scan.py`
- Modify: `app/native_structured_placeholder_scan.py`
- Modify: `app/rmmz/mv_namebox_native.py`
- Modify: `app/text_facts.py`
- Modify: `rust/src/native_core/scope_index/placeholders.rs`
- Modify: `rust/src/native_core/scope_index/structured_placeholders.rs`
- Modify: `rust/src/native_core/scope_index/mv_virtual_namebox.rs`
- Test: `tests/test_agent_toolkit_workspace.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_rule_import.py`
- Test: `tests/test_rmmz_mv_namebox.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing workspace scope tests**

Update workspace tests so generated workspace metadata contains v2 `scope_key`, `scope_hash`, and `text_fact_schema_version`. Old workspace files without v2 scope must fail validation with a message telling the user to rerun `prepare-agent-workspace`.

- [ ] **Step 2: Write failing rule tests**

Add or update tests for:

- weak MV rule splitting `<Name:> Body` without requiring the Agent to write separator rules;
- abnormal empty speaker rejection;
- placeholder and structured placeholder coverage from v2 facts;
- no Python data/plugin source rescan in warm workspace validation.

- [ ] **Step 3: Run RED tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_workspace.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_rule_import.py tests/test_rmmz_mv_namebox.py tests/test_scan_budget.py -q
```

Expected: tests fail because workspace and rule commands still trust old scope metadata or old text inputs.

- [ ] **Step 4: Migrate workspace preparation**

Generate all candidate files and rule drafts from v2 facts and Rust rule-hit facts. Save v2 scope metadata in workspace manifest files and candidate payloads.

- [ ] **Step 5: Migrate workspace validation and imports**

Validation must compare workspace v2 scope to current DB v2 scope. Old workspace candidates, old rule scope hash, and missing v2 scope must fail explicitly.

- [ ] **Step 6: Migrate placeholder and structured placeholder flows**

Use v2 fact text inputs. Preserve standard, custom, and structured coverage categories in reports while removing Python fallback scans for migrated commands.

- [ ] **Step 7: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_agent_toolkit_workspace.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_rule_import.py tests/test_rmmz_mv_namebox.py tests/test_scan_budget.py -q
```

Expected: workspace and rule tests pass, and scan budget proves warm workspace validation does not build full Python scope.

- [ ] **Step 8: Record Batch 3 performance evidence**

Run:

```powershell
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区>
uv run python main.py validate-agent-workspace --game <游戏标题> --workspace <工作区>
```

Record command durations, fact counts, rule candidate counts, and index status.

- [ ] **Step 9: Commit**

```powershell
git add app/agent_toolkit/services/workspace.py app/agent_toolkit/services/placeholder_rules.py app/agent_toolkit/services/rule_validation.py app/native_placeholder_scan.py app/native_structured_placeholder_scan.py app/rmmz/mv_namebox_native.py app/text_facts.py rust/src/native_core/scope_index/placeholders.rs rust/src/native_core/scope_index/structured_placeholders.rs rust/src/native_core/scope_index/mv_virtual_namebox.rs tests/test_agent_toolkit_workspace.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_rule_import.py tests/test_rmmz_mv_namebox.py tests/test_scan_budget.py
git commit -m "feat: migrate workspace rules to text fact v2"
```

---

### Task 7: Extended Domains And Runtime Literal Facts

**Files:**
- Modify: `rust/src/native_core/scope_index/plugin_config.rs`
- Modify: `rust/src/native_core/scope_index/event_commands.rs`
- Modify: `rust/src/native_core/scope_index/note_tags.rs`
- Modify: `rust/src/native_core/scope_index/nonstandard_data.rs`
- Modify: `rust/src/native_core/scope_index/plugin_source.rs`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/javascript_ast.rs`
- Modify: `app/native_note_tag_scan.py`
- Modify: `app/native_javascript_ast.py`
- Modify: `app/plugin_source_text/scanner.py`
- Modify: `app/plugin_source_text/runtime_audit.py`
- Modify: `app/nonstandard_data/scanner.py`
- Modify: `app/nonstandard_data/runtime_audit.py`
- Modify: `app/text_facts.py`
- Test: `tests/test_native_scope_index.py`
- Test: `tests/test_event_command_text.py`
- Test: `tests/test_plugin_text.py`
- Test: `tests/test_plugin_source_text.py`
- Test: `tests/test_nonstandard_data.py`
- Test: `tests/test_rmmz_note_nonstandard_data.py`
- Test: `tests/test_agent_toolkit_feedback.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing domain fact tests**

Add Rust and Python tests covering:

- `plugin_config` raw JSON path and visible parameter text;
- `event_command` command code and parameter path payload;
- `note_tag` tag name and raw note value;
- `nonstandard_data` JSON path and skipped/excluded behavior;
- `plugin_source` raw JS span, visible JS string value, and selector;
- `active_runtime_literal` classification from Rust.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
cd rust
cargo test plugin_config
cargo test event_commands
cargo test note_tags
cargo test nonstandard_data
cargo test plugin_source
cd ..
uv run pytest tests/test_native_scope_index.py tests/test_event_command_text.py tests/test_plugin_text.py tests/test_plugin_source_text.py tests/test_nonstandard_data.py tests/test_rmmz_note_nonstandard_data.py tests/test_agent_toolkit_feedback.py tests/test_scan_budget.py -q
```

Expected: tests fail because those domains either have generic facts or still expose old scanner payloads.

- [ ] **Step 3: Emit domain payloads and specialized render parts**

For each domain, write minimal domain payload JSON only for small domain-specific fields. Keep core fields in `text_facts_v2`; do not move `raw_text`, `visible_text`, `translatable_text`, hashes, selector, source file, or role into payload JSON.

- [ ] **Step 4: Move runtime literal classification to Rust facts**

`active_runtime_literal` facts must identify blocking/warning/ignored runtime literals from Rust output. Python may summarize and render messages but must not classify regex/packer/eval by string features for migrated paths.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
cd rust
cargo test plugin_config
cargo test event_commands
cargo test note_tags
cargo test nonstandard_data
cargo test plugin_source
cd ..
uv run pytest tests/test_native_scope_index.py tests/test_event_command_text.py tests/test_plugin_text.py tests/test_plugin_source_text.py tests/test_nonstandard_data.py tests/test_rmmz_note_nonstandard_data.py tests/test_agent_toolkit_feedback.py tests/test_scan_budget.py -q
```

Expected: extended domain tests pass and migrated runtime flows no longer rescan translation source files for unchanged hashes.

- [ ] **Step 6: Record Batch 4 performance evidence**

Run:

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
uv run python main.py audit-active-runtime --game <游戏标题>
```

Record command durations, scanned plugin source file count, runtime literal fact count, blocking/warning/ignored counts, and whether plugin source scans are reused.

- [ ] **Step 7: Commit**

```powershell
git add rust/src/native_core/scope_index/plugin_config.rs rust/src/native_core/scope_index/event_commands.rs rust/src/native_core/scope_index/note_tags.rs rust/src/native_core/scope_index/nonstandard_data.rs rust/src/native_core/scope_index/plugin_source.rs rust/src/native_core/scope_index/rebuild.rs rust/src/native_core/javascript_ast.rs app/native_note_tag_scan.py app/native_javascript_ast.py app/plugin_source_text/scanner.py app/plugin_source_text/runtime_audit.py app/nonstandard_data/scanner.py app/nonstandard_data/runtime_audit.py app/text_facts.py tests/test_native_scope_index.py tests/test_event_command_text.py tests/test_plugin_text.py tests/test_plugin_source_text.py tests/test_nonstandard_data.py tests/test_rmmz_note_nonstandard_data.py tests/test_agent_toolkit_feedback.py tests/test_scan_budget.py
git commit -m "feat: extend text fact v2 domains"
```

---

### Task 8: Write-Back, Runtime Maps, Feedback, And Manual Import

**Files:**
- Modify: `rust/src/native_core/write_back_plan/repository.rs`
- Modify: `rust/src/native_core/write_back_plan/models.rs`
- Modify: `rust/src/native_core/write_back_plan/mod.rs`
- Modify: `rust/src/native_core/write_back_plan/data_writer.rs`
- Modify: `rust/src/native_core/write_back_plan/command_writer.rs`
- Modify: `rust/src/native_core/write_back_plan/mv_virtual_namebox.rs`
- Modify: `rust/src/native_core/write_back_plan/plugin_config_writer.rs`
- Modify: `rust/src/native_core/write_back_plan/plugin_source.rs`
- Modify: `rust/src/native_core/write_back_plan/nonstandard_data_writer.rs`
- Modify: `rust/src/native_core/write_back_plan/note_writer.rs`
- Modify: `rust/src/native_core/write_back_plan/terminology.rs`
- Modify: `app/native_write_plan.py`
- Modify: `app/application/write_plan_applier.py`
- Modify: `app/application/handler.py`
- Modify: `app/agent_toolkit/services/manual_translation.py`
- Modify: `app/agent_toolkit/services/quality.py`
- Modify: `app/plugin_source_text/runtime_mapping.py`
- Test: `tests/test_rmmz_write_plan.py`
- Test: `tests/test_write_back_transactions.py`
- Test: `tests/test_quality_gate_result.py`
- Test: `tests/test_agent_toolkit_manual_import.py`
- Test: `tests/test_agent_toolkit_feedback.py`
- Test: `tests/test_plugin_source_text.py`
- Test: `tests/test_scan_budget.py`

- [ ] **Step 1: Write failing write-back tests**

Add tests proving:

- MV `:> ` separator spacing survives write-back;
- render parts reconstruct source text before writing;
- stale plugin source raw selector blocks write-back;
- runtime map uses v2 raw/visible/translatable hashes;
- feedback and manual import read v2 fact identity;
- manual import defaults to atomic behavior and explicit partial mode saves valid entries while reporting invalid entries.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_rmmz_write_plan.py tests/test_write_back_transactions.py tests/test_quality_gate_result.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py tests/test_plugin_source_text.py tests/test_scan_budget.py -q
```

Expected: tests fail because write-back still reads old translation item source fields and runtime map hashes.

- [ ] **Step 3: Read v2 facts in Rust write-back plan**

Replace old `translation_items` source-shape reconstruction with joins from saved translations to v2 facts and render parts. Saved translation records still store translated lines, but source identity and write templates come from v2 facts.

- [ ] **Step 4: Rebuild text by render parts**

Implement render part consumption for data, event command, MV namebox, plugin config, note tag, nonstandard data, plugin source, terminology writes, and quality gate mode. Fail if a fact lacks required render parts for a migrated domain.

- [ ] **Step 5: Migrate runtime and feedback commands**

Use v2 hashes for runtime maps and v2 facts for `verify-feedback-text`, `diagnose-active-runtime`, `audit-active-runtime`, and feedback warm-index lookups.

- [ ] **Step 6: Migrate manual import identity**

Import by `fact_id` when present and by current `location_path` only for current v2 facts. Missing old workspace fields must fail with a command to re-export pending translations.

- [ ] **Step 7: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_rmmz_write_plan.py tests/test_write_back_transactions.py tests/test_quality_gate_result.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py tests/test_plugin_source_text.py tests/test_scan_budget.py -q
```

Expected: write-back and manual import tests pass without Python source rescans for migrated flows.

- [ ] **Step 8: Record Batch 5 performance evidence**

Run:

```powershell
uv run python main.py write-back --game <游戏标题> --dry-run
uv run python main.py rebuild-active-runtime --game <游戏标题> --dry-run
uv run python main.py diagnose-active-runtime --game <游戏标题>
uv run python main.py verify-feedback-text --game <游戏标题> --input <输入文件>
```

Record planned file count, runtime map count, necessary current-runtime file reads, command duration, and absence of full source rescans outside required current-runtime reads.

- [ ] **Step 9: Commit**

```powershell
git add rust/src/native_core/write_back_plan/repository.rs rust/src/native_core/write_back_plan/models.rs rust/src/native_core/write_back_plan/mod.rs rust/src/native_core/write_back_plan/data_writer.rs rust/src/native_core/write_back_plan/command_writer.rs rust/src/native_core/write_back_plan/mv_virtual_namebox.rs rust/src/native_core/write_back_plan/plugin_config_writer.rs rust/src/native_core/write_back_plan/plugin_source.rs rust/src/native_core/write_back_plan/nonstandard_data_writer.rs rust/src/native_core/write_back_plan/note_writer.rs rust/src/native_core/write_back_plan/terminology.rs app/native_write_plan.py app/application/write_plan_applier.py app/application/handler.py app/agent_toolkit/services/manual_translation.py app/agent_toolkit/services/quality.py app/plugin_source_text/runtime_mapping.py tests/test_rmmz_write_plan.py tests/test_write_back_transactions.py tests/test_quality_gate_result.py tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_feedback.py tests/test_plugin_source_text.py tests/test_scan_budget.py
git commit -m "feat: write back from text fact v2"
```

---

### Task 9: Delete Old Production Fact Paths

**Files:**
- Modify: `app/text_scope/builder.py`
- Modify: `app/text_scope/rule_hits.py`
- Modify: `app/text_scope/write_probe.py`
- Modify: `app/text_scope/models.py`
- Modify: `app/agent_toolkit/services/common.py`
- Modify: `app/native_scope_index.py`
- Modify: `app/text_index.py`
- Modify: `app/persistence/text_index_records.py`
- Modify: `rust/src/native_core/scope_index/rebuild.rs`
- Modify: `rust/src/native_core/scope_index/storage.rs`
- Test: `tests/test_scan_budget.py`
- Test: `tests/test_text_index.py`
- Test: `tests/test_stage0_canaries.py`
- Test: `tests/test_native_adapters.py`

- [ ] **Step 1: Write failing deletion guard tests**

Add tests that monkeypatch old Python scope builders and old scanner entrypoints to raise if any migrated production command calls them. Add schema fingerprint tests that require v2 tables and indexes.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py tests/test_text_index.py tests/test_stage0_canaries.py tests/test_native_adapters.py -q
```

Expected: tests reveal any production path still using old Python fact construction.

- [ ] **Step 3: Remove or isolate old paths**

Delete migrated production callers of old `translation_items` fact reconstruction, Python full-scope builders, write-probe fallbacks, and scanner payload builders. Keep helper code only for tests or non-migrated utilities when a comment names the remaining owner and no production command depends on it.

- [ ] **Step 4: Make v1 contract failures explicit**

Ensure old databases, old workspace metadata, old rule scope hashes, and old runtime maps fail with messages that state the affected command and the rebuild/export command to run.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
uv run pytest tests/test_scan_budget.py tests/test_text_index.py tests/test_stage0_canaries.py tests/test_native_adapters.py -q
```

Expected: deletion guard tests pass and no migrated command depends on old production fact paths.

- [ ] **Step 6: Commit**

```powershell
git add app/text_scope/builder.py app/text_scope/rule_hits.py app/text_scope/write_probe.py app/text_scope/models.py app/agent_toolkit/services/common.py app/native_scope_index.py app/text_index.py app/persistence/text_index_records.py rust/src/native_core/scope_index/rebuild.rs rust/src/native_core/scope_index/storage.rs tests/test_scan_budget.py tests/test_text_index.py tests/test_stage0_canaries.py tests/test_native_adapters.py
git commit -m "refactor: remove migrated v1 fact paths"
```

---

### Task 10: Documentation, Skill Protocol, And Release Notes

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`
- Modify: `skills/att-mz-protocol/`
- Modify: `skills/att-mz/`
- Modify: `skills/att-mz-release/`
- Modify: `CHANGELOG.md`
- Test: `tests/test_skill_protocol.py`
- Test: `tests/test_release_notes.py`

- [ ] **Step 1: Write failing docs boundary tests**

Add tests only for machine-observable boundaries: generated Skill protocol drift, required entry references, no real local paths in examples, and release notes containing concrete v2 contract changes.

- [ ] **Step 2: Run RED docs checks**

Run:

```powershell
uv run pytest tests/test_skill_protocol.py tests/test_release_notes.py -q
uv run python scripts/generate_skill_protocol.py --check
```

Expected: checks fail if generated Skill outputs are stale or release notes do not mention v2 contract changes.

- [ ] **Step 3: Update user-facing docs**

Explain current behavior only: v2 facts, required `rebuild-text-index`, old workspace failure, old runtime map failure, and the user command to recover. Do not put Agent execution contracts in `docs/`; keep workflow contracts in Skill protocol sources.

- [ ] **Step 4: Regenerate Skill outputs**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --write
```

Review generated `skills/att-mz/` and `skills/att-mz-release/` for semantic drift between development and release entries.

- [ ] **Step 5: Run GREEN docs checks**

Run:

```powershell
uv run pytest tests/test_skill_protocol.py tests/test_release_notes.py -q
uv run python scripts/generate_skill_protocol.py --check
```

Expected: Skill protocol and release note tests pass.

- [ ] **Step 6: Commit**

```powershell
git add README.md CHANGELOG.md docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md skills/att-mz-protocol skills/att-mz skills/att-mz-release tests/test_skill_protocol.py tests/test_release_notes.py
git commit -m "docs: document text fact v2 contract"
```

---

### Task 11: Full Contract Verification And Performance Gate

**Files:**
- All touched files.

- [ ] **Step 1: Run Python type check**

Run:

```powershell
uv run basedpyright
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 2: Run Python tests**

Run:

```powershell
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run Rust formatting**

Run:

```powershell
cd rust
cargo fmt -- --check
```

Expected: no formatting changes required.

- [ ] **Step 4: Run Rust clippy**

Run:

```powershell
cd rust
cargo clippy --all-targets -- -D warnings
```

Expected: 0 clippy warnings.

- [ ] **Step 5: Run Rust tests**

Run:

```powershell
cd rust
cargo test
```

Expected: all Rust tests pass.

- [ ] **Step 6: Run Skill protocol check if Skill files changed**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: generated Skill files have no drift.

- [ ] **Step 7: Run final CLI performance suite**

Run against the agreed real sample:

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区>
uv run python main.py validate-agent-workspace --game <游戏标题> --workspace <工作区>
uv run python main.py quality-report --game <游戏标题>
uv run python main.py audit-coverage --game <游戏标题>
```

Record candidate count, fact count, render part count, scanned file count, command duration, cold/stale/used status, internal Rust stage timings, and whether any Python full scan was added. If performance regresses, stop and fix the repeated scan or Rust concurrency bottleneck before marking complete.

- [ ] **Step 8: Run diff check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 9: Completion audit**

Compare implementation against every bullet in `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`. The final delivery note must state implemented scope, validation commands and results, performance evidence, unverified scope, remaining risks, and any user decision still needed.

---

## Self-Review Checklist

- [ ] Every design goal has at least one task: schema, Rust writer, raw/visible/translatable/render/hash/scope, all listed domains, migrated production commands, old contract failures, Python fallback deletion, performance evidence, docs/Skill updates.
- [ ] Every non-goal is preserved: no old DB migration, no docs-as-runtime dependency, no game-specific special case, no Python fallback rescan, no text dedup table added without evidence.
- [ ] v2 schema core fields are not hidden in `payload_json`.
- [ ] Prompt tests prove internal file names, selectors, `location_path`, internal field names, and `位置:` do not enter user prompts.
- [ ] Warm commands use SQLite v2 facts and scan budget tests catch Python full-scope regressions.
- [ ] All Rust/Python contract version bumps are paired with tests.
- [ ] Each task has a focused RED/GREEN command and a commit boundary.
