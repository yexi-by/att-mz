# Contract Amnesia Review Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the approved A.T.T MZ contract-amnesia review spec as a read-only, parallel, evidence-based review that produces 10 batch reports and one final merged report.

**Architecture:** The work is split into independent read-only review batches by system domain. Each batch writes one Markdown report under `docs/records/reviews/contract-amnesia/batches/`, and the main agent merges those reports into `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md`.

**Tech Stack:** PowerShell, `rg`, `git`, Markdown review reports, optional Codex subagents.

---

## Source Spec

Read this approved design before executing any task:

- `docs/superpowers/specs/2026-06-09-contract-amnesia-review-design.md`

The review axis is strict: current runtime, schema, user text, tests, docs, and Skill contracts must express only the current contract. Historical forms may be recorded only in proper historical documentation and must not become current runtime concepts.

## File Structure

Create these review output files during execution:

- `docs/records/reviews/contract-amnesia/batches/batch-01-cli-config-runtime.md`
- `docs/records/reviews/contract-amnesia/batches/batch-02-sqlite-persistence.md`
- `docs/records/reviews/contract-amnesia/batches/batch-03-text-fact-index-scope.md`
- `docs/records/reviews/contract-amnesia/batches/batch-04-workspace-rules-agent-toolkit.md`
- `docs/records/reviews/contract-amnesia/batches/batch-05-translation-llm-prompt-quality.md`
- `docs/records/reviews/contract-amnesia/batches/batch-06-writeback-rmmz-file-safety.md`
- `docs/records/reviews/contract-amnesia/batches/batch-07-rust-native-python-adapters.md`
- `docs/records/reviews/contract-amnesia/batches/batch-08-skill-readme-current-docs.md`
- `docs/records/reviews/contract-amnesia/batches/batch-09-tests-fixtures-helpers.md`
- `docs/records/reviews/contract-amnesia/batches/batch-10-release-build-history-records.md`
- `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md`

No source, schema, test, Skill, README, docs, config, script, database, log, output, temporary, build, or game data file may be modified. The only allowed writes are the Markdown review reports listed above.

## Shared Rules For Every Task

- Do not read `data/`, `logs/`, `outputs/`, `tmp/`, `dist/`, `target/`, `.venv/`, `.pytest_cache/`, or `__pycache__/`.
- Do not run state-changing commands such as `add-game`, `reset-game`, `translate`, `write-back`, `rebuild-active-runtime`, `import-*`, `reset-translations`, or `run-all`.
- Treat legitimate ecosystem versions as allowed unless they are used to express A.T.T MZ internal history.
- Use P0-P3 severity exactly as defined in the design spec.
- Every finding needs file and line evidence.
- If a reviewed sub-scope has no findings, write a concrete "已查无发现" statement in the batch report.
- Do not commit during review execution unless the user separately asks for a commit.

## Report Template

Use this exact structure for each batch report:

```markdown
# 批次 NN：标题

## 范围

## 事实源

## 只读命令

## 结论

PASS | FAIL | NEEDS_REVIEW

## 发现

### P0：标题

- 证据：`path/to/file.ext:line`
- 违反准则：运行时失忆化 | schema 失忆化 | 文案失忆化 | 测试失忆化 | 文档分层
- 影响范围：说明影响当前执行路径、用户文案、测试模型或文档事实源。
- 建议收束：说明后续清理应删除、改名、合并、改文案或改测试模型的对象。
- 后续验证：说明后续清理后可运行的命令或静态检查。

## 交叉引用

## 已查无发现范围
```

If a severity level has no findings, omit that severity heading. If the whole batch has no findings, write `无确认发现。` under `## 发现` and set the conclusion to `PASS`.

## Task 1: Prepare Review Baseline

**Files:**
- Create directory: `docs/records/reviews/contract-amnesia/`
- Create directory: `docs/records/reviews/contract-amnesia/batches/`
- Read: `docs/superpowers/specs/2026-06-09-contract-amnesia-review-design.md`

- [ ] **Step 1: Confirm workspace state**

Run:

```powershell
git status --short
```

Expected: command succeeds. Record any pre-existing modified or untracked files in the final report's read-only boundary statement. Do not revert, stage, or clean them.

- [ ] **Step 2: Create report directories**

Run:

```powershell
New-Item -ItemType Directory -Force -Path 'docs\records\reviews\contract-amnesia\batches' | Out-Null
```

Expected: command succeeds and creates only the review report directories.

- [ ] **Step 3: Read the approved review spec**

Run:

```powershell
Get-Content -Raw -LiteralPath 'docs\superpowers\specs\2026-06-09-contract-amnesia-review-design.md'
```

Expected: command succeeds. Confirm the execution still matches the approved scope: read-only review, 10 batch reports, one final report.

- [ ] **Step 4: Capture repository file inventory without private runtime directories**

Run:

```powershell
rg --files app rust tests skills docs scripts .github README.md CHANGELOG.md pyproject.toml setting.example.toml
```

Expected: command succeeds. Do not include `data/`, `logs/`, `outputs/`, `tmp/`, `dist/`, `target/`, `.venv/`, `.pytest_cache/`, or `__pycache__/`.

## Task 2: Batch 01 CLI, Config, Runtime Paths

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-01-cli-config-runtime.md`
- Read: `app/cli_main.py`
- Read: `app/cli/`
- Read: `app/config/`
- Read: `app/runtime_paths.py`
- Read: `setting.example.toml`
- Read: `tests/test_cli_json_output.py`
- Read: `tests/test_config_overrides.py`
- Read: `tests/test_runtime_paths.py`

- [ ] **Step 1: Run contract-memory keyword scan**

Run:

```powershell
rg -n 'legacy|deprecated|fallback|compat|old|schema_version|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本' app/cli_main.py app/cli app/config app/runtime_paths.py setting.example.toml tests/test_cli_json_output.py tests/test_config_overrides.py tests/test_runtime_paths.py
```

Expected: command may return matches or no matches. Inspect every match that refers to A.T.T MZ internal runtime/config history; ignore legitimate external API or dependency version usage.

- [ ] **Step 2: Inspect CLI and config failure wording**

Run:

```powershell
rg -n 'raise|ValueError|RuntimeError|error|错误|失败|无法|请|旧|兼容|回退|废弃' app/cli_main.py app/cli app/config app/runtime_paths.py tests/test_cli_json_output.py tests/test_config_overrides.py
```

Expected: command returns candidate error paths. Check whether messages explain current requirements rather than historical forms.

- [ ] **Step 3: Write the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-01-cli-config-runtime.md` with actual findings, cross-references, commands run, and no-found sub-scopes.

- [ ] **Step 4: Self-check the batch report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-01-cli-config-runtime.md' -Pattern $patterns
```

Expected: no output.

## Task 3: Batch 02 SQLite Schema And Persistence

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-02-sqlite-persistence.md`
- Read: `app/persistence/`
- Read: `app/persistence/schema/current.sql`
- Read: `rust/src/native_core/scope_index/storage.rs`
- Read: `rust/src/native_core/write_back_plan/repository.rs`
- Read: `tests/test_persistence.py`

- [ ] **Step 1: Run schema and persistence keyword scan**

Run:

```powershell
rg -n 'schema_version|legacy|deprecated|fallback|compat|old|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本|过期' app/persistence rust/src/native_core/scope_index/storage.rs rust/src/native_core/write_back_plan/repository.rs tests/test_persistence.py
```

Expected: command returns schema and persistence candidates. Classify each match as legitimate current integrity metadata, legitimate ecosystem version, or internal historical memory.

- [ ] **Step 2: Inspect current schema naming**

Run:

```powershell
Get-Content -Raw -LiteralPath 'app\persistence\schema\current.sql'
```

Expected: command succeeds. Check table names, field names, metadata, scope, cache, runtime map, and error-facing names against schema失忆化.

- [ ] **Step 3: Inspect Python/Rust schema constants**

Run:

```powershell
rg -n 'CURRENT_SCHEMA_VERSION|TEXT_FACT_SCHEMA_VERSION|schema_version|text_facts_v2|text_fact_scope_v2|translation_items' app/persistence rust/src/native_core
```

Expected: command returns all schema constant and table usage sites. Check whether there are duplicate facts or history-specific schema branches.

- [ ] **Step 4: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-02-sqlite-persistence.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-02-sqlite-persistence.md' -Pattern $patterns
```

Expected: no output.

## Task 4: Batch 03 Text Fact, Index, Scope

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-03-text-fact-index-scope.md`
- Read: `app/text_facts.py`
- Read: `app/text_fact_core.py`
- Read: `app/text_fact_counts.py`
- Read: `app/text_fact_identity.py`
- Read: `app/text_fact_quality.py`
- Read: `app/text_fact_readers.py`
- Read: `app/text_scope/`
- Read: `app/text_index.py`
- Read: `rust/src/native_core/scope_index/`
- Read: `tests/test_text_protocol.py`
- Read: `tests/test_text_index.py`
- Read: `tests/test_native_scope_index.py`

- [ ] **Step 1: Run text fact history-memory scan**

Run:

```powershell
rg -n 'v2|schema_version|legacy|fallback|old|stale|warm index|location_path|identity|scope|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' app/text_facts.py app/text_fact_core.py app/text_fact_counts.py app/text_fact_identity.py app/text_fact_quality.py app/text_fact_readers.py app/text_scope app/text_index.py rust/src/native_core/scope_index tests/test_text_protocol.py tests/test_text_index.py tests/test_native_scope_index.py
```

Expected: command returns many matches. Determine whether naming and failures describe the current model or keep an internal memory of previous fact contracts.

- [ ] **Step 2: Inspect location-path identity risks**

Run:

```powershell
rg -n 'location_path.*identity|identity.*location_path|fact_id|raw_hash|translatable_hash|translated.*path|path.*translated' app rust/src/native_core/scope_index tests
```

Expected: command returns identity-related code and tests. For this batch, review only text fact, index, and scope ownership; cross-reference write-back or tests findings to later batches.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-03-text-fact-index-scope.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-03-text-fact-index-scope.md' -Pattern $patterns
```

Expected: no output.

## Task 5: Batch 04 Workspace, Rules, Agent Toolkit

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-04-workspace-rules-agent-toolkit.md`
- Read: `app/agent_toolkit/`
- Read: `app/plugin_text/`
- Read: `app/plugin_source_text/`
- Read: `app/event_command_text/`
- Read: `app/note_tag_text/`
- Read: `app/nonstandard_data/`
- Read: `app/config/structured_placeholder_rules.py`
- Read: `app/config/custom_placeholder_rules.py`
- Read: related `tests/test_agent_toolkit_*.py`

- [ ] **Step 1: Run workspace and rule keyword scan**

Run:

```powershell
rg -n 'manifest|workspace|review|confirm|candidate|sample|legacy|fallback|old|stale|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|旧工作区|旧确认|过期' app/agent_toolkit app/plugin_text app/plugin_source_text app/event_command_text app/note_tag_text app/nonstandard_data app/config/structured_placeholder_rules.py app/config/custom_placeholder_rules.py tests/test_agent_toolkit_*.py
```

Expected: command returns candidates. Check whether current workspace and rule state are derived only from current manifest/current candidates.

- [ ] **Step 2: Inspect manifest as fact source**

Run:

```powershell
rg -n 'manifest\.files|manifest|exists\(\)|cleanup|validate_agent_workspace|prepare_agent_workspace|plugin-source-rules|nonstandard-data-rules' app/agent_toolkit tests/test_agent_toolkit_workspace.py
```

Expected: command returns workspace boundary logic. Check for directory existence as a second fact source.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-04-workspace-rules-agent-toolkit.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-04-workspace-rules-agent-toolkit.md' -Pattern $patterns
```

Expected: no output.

## Task 6: Batch 05 Translation, LLM, Prompt, Quality

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-05-translation-llm-prompt-quality.md`
- Read: `app/translation/`
- Read: `app/llm/`
- Read: `app/llm_request_body_extra.py`
- Read: `prompts/`
- Read: `app/native_quality.py`
- Read: `rust/src/native_core/quality/`
- Read: `tests/test_translation_*.py`
- Read: `tests/test_quality_gate_result.py`

- [ ] **Step 1: Run translation and quality keyword scan**

Run:

```powershell
rg -n 'prompt|location_path|translated_text|位置:|legacy|fallback|old|stale|pending|quality_error|manual|reset|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' app/translation app/llm app/llm_request_body_extra.py prompts app/native_quality.py rust/src/native_core/quality tests/test_translation_*.py tests/test_quality_gate_result.py
```

Expected: command returns prompt, quality, and failure handling candidates. Check prompt privacy, current-failure wording, and historical test model risks.

- [ ] **Step 2: Inspect prompt files**

Run:

```powershell
Get-Content -Raw -LiteralPath 'prompts\text_translation_ja_to_zh_system.md'
Get-Content -Raw -LiteralPath 'prompts\text_translation_en_to_zh_system.md'
```

Expected: commands succeed. Confirm prompts describe current translation constraints only and do not include internal implementation details.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-05-translation-llm-prompt-quality.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-05-translation-llm-prompt-quality.md' -Pattern $patterns
```

Expected: no output.

## Task 7: Batch 06 Writeback, RMMZ, File Safety

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-06-writeback-rmmz-file-safety.md`
- Read: `app/application/`
- Read: `app/rmmz/`
- Read: `app/native_write_plan.py`
- Read: `rust/src/native_core/write_back_plan/`
- Read: `tests/test_rmmz_*.py`
- Read: `tests/test_write_back_transactions.py`
- Read: `tests/test_font_replacement_transactions.py`

- [ ] **Step 1: Run writeback and RMMZ keyword scan**

Run:

```powershell
rg -n 'write|write-back|snapshot|origin|backup|fallback|compat|legacy|old|stale|load_game_data|require_origin|current runtime|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期|当前运行' app/application app/rmmz app/native_write_plan.py rust/src/native_core/write_back_plan tests/test_rmmz_*.py tests/test_write_back_transactions.py tests/test_font_replacement_transactions.py
```

Expected: command returns writeback candidates. Check whether writeback only trusts current source snapshot and current text facts.

- [ ] **Step 2: Inspect loader and snapshot boundaries**

Run:

```powershell
rg -n 'load_game_data|GameFileView|source_snapshot|origin_backups|require_origin_backups|TRANSLATION_SOURCE|ACTIVE_RUNTIME' app/rmmz app/application tests
```

Expected: command returns loader and view-selection logic. Check for fallback from trusted source to active runtime.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-06-writeback-rmmz-file-safety.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-06-writeback-rmmz-file-safety.md' -Pattern $patterns
```

Expected: no output.

## Task 8: Batch 07 Rust Native And Python Adapter Boundary

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-07-rust-native-python-adapters.md`
- Read: `rust/src/`
- Read: `app/native_contract.py`
- Read: `app/native_*.py`
- Read: `tests/test_native_*.py`
- Read: `rust/src/native_core.rs`

- [ ] **Step 1: Run native adapter keyword scan**

Run:

```powershell
rg -n 'schema_version|legacy|fallback|old|same shape|旧报告|native|adapter|contract|unsupported|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' rust/src app/native_contract.py app/native_*.py tests/test_native_*.py
```

Expected: command returns native schema and adapter candidates. Classify legitimate native version checks separately from A.T.T MZ historical contract memory.

- [ ] **Step 2: Inspect Python adapter boundaries**

Run:

```powershell
rg -n '调用 native|返回旧报告同形|fallback|TextScope|build\(|Python 完整|Rust|adapter|schema_version' app/native_*.py app/agent_toolkit app/application tests
```

Expected: command returns adapter and fallback candidates. Check whether Rust-owned production paths still have Python heavy fallbacks.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-07-rust-native-python-adapters.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-07-rust-native-python-adapters.md' -Pattern $patterns
```

Expected: no output.

## Task 9: Batch 08 Skill, README, Current Docs

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-08-skill-readme-current-docs.md`
- Read: `skills/att-mz-protocol/`
- Read: `skills/att-mz/`
- Read: `skills/att-mz-release/`
- Read: `README.md`
- Read: `docs/wiki/`
- Read: `docs/guides/`
- Read: `tests/test_skill_protocol.py`

- [ ] **Step 1: Run current docs keyword scan**

Run:

```powershell
rg -n 'legacy|deprecated|fallback|compat|old|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本|过期|旧工作区|旧确认' README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release tests/test_skill_protocol.py
```

Expected: command returns current-doc and Skill candidates. Ignore legitimate user-facing release/version references only when they are not internal history memory.

- [ ] **Step 2: Check Skill generation drift**

Run:

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

Expected: command exits 0 if generated Skills match canonical protocol. If it fails, record it as evidence; do not run `--write`.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-08-skill-readme-current-docs.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-08-skill-readme-current-docs.md' -Pattern $patterns
```

Expected: no output.

## Task 10: Batch 09 Tests, Fixtures, Helpers

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-09-tests-fixtures-helpers.md`
- Read: `tests/`

- [ ] **Step 1: Run test history-model scan**

Run:

```powershell
rg -n 'legacy|fallback|old|stale|v[0-9]+|migration|migrate|compat|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期|旧式|测试专用' tests
```

Expected: command returns test helper and fixture candidates. Check whether tests model current invalid input, or maintain a historical success model.

- [ ] **Step 2: Inspect large helper concentration**

Run:

```powershell
Get-ChildItem -File -LiteralPath tests | Sort-Object Length -Descending | Select-Object -First 20 Name,Length
```

Expected: command lists large test files. Use it to decide whether helper responsibility is too broad for current contract clarity.

- [ ] **Step 3: Inspect helper-to-production overlap**

Run:

```powershell
rg -n 'make_current|write_v2|stale|generated_stale|ensure_current|read_current|fact_id|location_path' tests/_native_write_plan_helper.py tests/agent_toolkit_contract_fixtures.py tests/current_v2_scope.py tests/rmmz_writeback_contract_fixtures.py
```

Expected: command returns helper model candidates. Check whether helper naming and behavior encode history as current contract.

- [ ] **Step 4: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-09-tests-fixtures-helpers.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-09-tests-fixtures-helpers.md' -Pattern $patterns
```

Expected: no output.

## Task 11: Batch 10 Release, Build, History Records

**Files:**
- Create: `docs/records/reviews/contract-amnesia/batches/batch-10-release-build-history-records.md`
- Read: `.github/`
- Read: `scripts/`
- Read: `CHANGELOG.md`
- Read: `docs/archive/`
- Read: `docs/records/`
- Read: `tests/test_release_package_layout.py`
- Read: `tests/test_release_notes.py`

- [ ] **Step 1: Run release and history keyword scan**

Run:

```powershell
rg -n 'legacy|deprecated|fallback|compat|old|stale|migration|archive|history|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本|过期|真实路径|本机路径' .github scripts CHANGELOG.md docs/archive docs/records tests/test_release_package_layout.py tests/test_release_notes.py
```

Expected: command returns release and history candidates. Treat `docs/archive/` and `docs/records/` as downgraded historical records; findings there are P3 unless they feed current facts, contain private data, or mislead current docs.

- [ ] **Step 2: Inspect release package boundaries**

Run:

```powershell
rg -n 'release|package|zip|copy|include|exclude|skill|README|CHANGELOG|dist|source|tests|logs|data' .github scripts tests/test_release_package_layout.py tests/test_release_notes.py
```

Expected: command returns packaging logic and tests. Check whether release outputs include only current allowed files.

- [ ] **Step 3: Write and self-check the batch report**

Create `docs/records/reviews/contract-amnesia/batches/batch-10-release-build-history-records.md`, then run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-10-release-build-history-records.md' -Pattern $patterns
```

Expected: no output.

## Task 12: Merge Batch Reports Into Final Report

**Files:**
- Create: `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md`
- Read: all files under `docs/records/reviews/contract-amnesia/batches/`

- [ ] **Step 1: Verify all 10 batch reports exist**

Run:

```powershell
Get-ChildItem -File -LiteralPath 'docs\records\reviews\contract-amnesia\batches' | Sort-Object Name | Select-Object Name,Length
```

Expected: exactly these 10 files are present: `batch-01-cli-config-runtime.md`, `batch-02-sqlite-persistence.md`, `batch-03-text-fact-index-scope.md`, `batch-04-workspace-rules-agent-toolkit.md`, `batch-05-translation-llm-prompt-quality.md`, `batch-06-writeback-rmmz-file-safety.md`, `batch-07-rust-native-python-adapters.md`, `batch-08-skill-readme-current-docs.md`, `batch-09-tests-fixtures-helpers.md`, `batch-10-release-build-history-records.md`.

- [ ] **Step 2: Extract severity headings**

Run:

```powershell
rg -n '^### P[0-3]：' docs/records/reviews/contract-amnesia/batches
```

Expected: command returns confirmed findings, or exits with no matches if every batch passed. Use this output as the first source for the highest-priority index.

- [ ] **Step 3: Write final merged report**

Create `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md` with these sections:

```markdown
# 契约失忆化专项 Review 总报告

## 执行摘要

## 最高优先级问题索引

## 横向矩阵

### 运行时历史记忆
### Schema 历史记忆
### 文案历史记忆
### 测试历史模型
### 文档与 Skill 当前契约漂移
### 归档记录污染风险

## 跨批重复与同根问题

## 建议清理批次

## 剩余不确定项

## 只读边界声明
```

Expected: final report merges duplicate root causes, preserves evidence references, and states `PASS`, `FAIL`, or `BLOCKED`.

- [ ] **Step 4: Confirm final report references every batch**

Run:

```powershell
rg -n 'batch-01|batch-02|batch-03|batch-04|batch-05|batch-06|batch-07|batch-08|batch-09|batch-10' docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md
```

Expected: all 10 batch names or equivalent batch references appear.

## Task 13: Self-Review Review Artifacts

**Files:**
- Read: `docs/records/reviews/contract-amnesia/`

- [ ] **Step 1: Scan for unfinished placeholders**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Get-ChildItem -Recurse -File -LiteralPath 'docs\records\reviews\contract-amnesia' | Select-String -Pattern $patterns
```

Expected: no output.

- [ ] **Step 2: Scan for accidental state-changing command recommendations**

Run:

```powershell
rg -n 'add-game|reset-game|translate|write-back|rebuild-active-runtime|import-|reset-translations|run-all|--write' docs/records/reviews/contract-amnesia
```

Expected: matches are allowed only when explicitly described as prohibited, not as commands executed during review.

- [ ] **Step 3: Confirm only review artifacts changed**

Run:

```powershell
git status --short
```

Expected: the only new files from this review execution are under `docs/records/reviews/contract-amnesia/`. Pre-existing unrelated changes may still be present and must be listed as pre-existing in the final response.

- [ ] **Step 4: Run Markdown-sensitive diff check**

Run:

```powershell
git diff --check -- docs/records/reviews/contract-amnesia
```

Expected: no whitespace errors.

## Task 14: Delivery

**Files:**
- Read: `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md`
- Read: `docs/records/reviews/contract-amnesia/batches/`

- [ ] **Step 1: Summarize result to the user**

Final response must include:

- Path to the final report.
- Overall result: `PASS`, `FAIL`, or `BLOCKED`.
- Count of P0, P1, P2, and P3 findings.
- Whether subagents were used.
- Which commands were run.
- Which checks were not run and why.
- Confirmation that no source, database, game, log, output, temp, build, or private runtime data was modified or read.

- [ ] **Step 2: Ask before committing reports**

Do not commit review reports automatically. Ask the user whether they want the report artifacts staged and committed.

## Plan Self-Review

- Spec coverage: This plan covers the approved spec's read-only scope, 10 batch reports, final report, severity model, allowed/forbidden commands, history directory downgrade, legal version exclusion, and artifact self-check.
- Placeholder scan: The plan contains no incomplete task placeholders. Dynamic review findings are produced during execution and are not known in advance.
- Type and path consistency: All report paths use `docs/records/reviews/contract-amnesia/`; all batch filenames are fixed and reused consistently in creation, merge, and self-check steps.
