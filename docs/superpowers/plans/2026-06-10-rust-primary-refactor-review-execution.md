# Rust 主路径收束专项 Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已批准的 Rust 主路径收束多子代理 review 设计，执行一次只读、可审计、可合并的结构性 review，产出 7 份轨道报告和 1 份总报告。

**Architecture:** 本计划把 review 拆成 7 条互不写共享状态的审查轨道，每条轨道只读取仓库、运行只读检索命令，并写入一份 Markdown 报告。主代理负责创建报告目录、派发或顺序执行轨道、去重合并发现、统一严重程度，并生成总报告。

**Tech Stack:** PowerShell, `rg`, `git`, Markdown review reports, optional Codex subagents.

---

## Source Spec

执行前必须阅读并遵守：

- `docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md`

本轮目标是大规模重构前的结构审查，不修复、不重构、不提交补丁。审查结论必须服务于 Rust 主路径收束、Python 职责减少、单一事实来源和跨命令契约一致。

## File Structure

执行本计划时只允许新增或更新这些 review 报告文件：

- `docs/records/reviews/rust-primary-refactor/batches/track-01-fact-sources-contract.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-02-rust-primary-path.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-03-cross-command-lifecycle.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-04-cache-metadata-fast-path.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-05-tests-acceptance.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-06-migration-deletion.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-07-performance-concurrency.md`
- `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md`

禁止修改源码、测试、schema、Skill、README、普通 docs、脚本、配置、数据库、日志、输出目录、发行目录、临时目录、构建目录和游戏目录。除上述 Markdown review 报告外，不创建临时 runner、manifest、脚本或生成数据。

## Shared Review Rules

- 不读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。
- 不执行 `import-*`、`translate`、`write-back`、`rebuild-active-runtime`、`reset-game`、`reset-translations`、`run-all` 等会改变状态的命令。
- 只允许 `rg`、`rg --files`、`Get-Content`、`git status`、`git log`、`git show`、`git diff --check`、`Select-String`、文件列表读取等只读命令。
- 每条确认发现必须有文件和行号证据；没有证据的怀疑放入报告的 `## 剩余不确定项` 或轨道报告的 `## 已查无发现范围` 之外的明确待复核说明。
- 严重程度必须使用 `P0`、`P1`、`P2`、`P3`，并按 P0 到 P3 排序。
- 不把 Python 补丁、Python fallback、silent fallback、mock 成功或报告层改文案写成合格长期方向。
- 如果无法使用子代理，主代理必须按 7 个轨道顺序单会话执行，并在总报告写明原因。

## Track Report Template

每份轨道报告使用以下结构；没有确认发现时，`## 关键发现` 写 `无确认发现。`，结论写 `PASS`。

```markdown
# 轨道 NN：标题

## 范围

## 只读命令

## 结论

PASS | FAIL | NEEDS_REVIEW

## 关键发现

### P0：确认发现标题

- 证据：`path/to/file.ext:line`
- 业务事实：候选、规则、selector、scope、hash、cache、写回协议或其他事实对象。
- 违反原则：单一事实来源 | Rust 主路径 | 跨命令生命周期 | fast path | 测试验收 | 迁移删减 | 性能并发
- 影响：说明会导致什么用户可见或工程可见问题。
- Python/Rust 职责判断：说明应由哪一侧承担。
- 建议 Rust 接管点：如适用，写清具体边界。
- 应删除或瘦身的 Python 逻辑：如适用，写清对象。
- 禁止采用的错误修复方向：如适用，写清不能采用的方向。
- 后续验证：写清可执行验证或测试缺口。

## 双事实来源清单

## Rust 主路径缺口

## Python 删除候选

## 测试缺口

## 交叉引用

## 已查无发现范围
```

## Task 1: Prepare Read-Only Baseline

**Files:**
- Create directory: `docs/records/reviews/rust-primary-refactor/`
- Create directory: `docs/records/reviews/rust-primary-refactor/batches/`
- Read: `docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md`

- [ ] **Step 1: Confirm workspace state**

Run:

```powershell
git status --short
```

Expected: command succeeds. Record existing modified or untracked files in the final report's read-only boundary statement. Do not revert, stage, clean, or commit them.

- [ ] **Step 2: Create review report directories**

Run:

```powershell
New-Item -ItemType Directory -Force -Path 'docs\records\reviews\rust-primary-refactor\batches' | Out-Null
```

Expected: command succeeds and creates only review report directories.

- [ ] **Step 3: Read the approved spec**

Run:

```powershell
Get-Content -Raw -LiteralPath 'docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md'
```

Expected: command succeeds. Confirm scope remains: 7 read-only tracks, no fixes, no source edits, no state-changing commands, final merged report.

- [ ] **Step 4: Capture repository inventory without private runtime directories**

Run:

```powershell
rg --files app rust tests skills docs scripts .github README.md CHANGELOG.md pyproject.toml setting.example.toml
```

Expected: command succeeds. Do not include `data/`, `logs/`, `outputs/`, `tmp/`, `dist/`, `target/`, `.venv/`, `.pytest_cache/`, or `__pycache__/`.

- [ ] **Step 5: Decide execution mode**

Use `superpowers:subagent-driven-development` if subagent tools are available. Dispatch one independent read-only worker per track. If subagent tools are unavailable, write this exact statement into the final report and execute tracks sequentially:

```text
未能使用子代理并发 review；原因：当前环境没有可用的子代理派发工具。已改为单会话分轨道审查。
```

Expected: execution mode is recorded. The review remains read-only in either mode.

## Task 2: Track 01 Fact Sources And Contracts

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-01-fact-sources-contract.md`
- Read: `app/`
- Read: `rust/src/`
- Read: `app/persistence/schema/current.sql`
- Read: `skills/att-mz-protocol/`
- Read: `skills/att-mz/`
- Read: `skills/att-mz-release/`
- Read: relevant `tests/`

- [ ] **Step 1: Scan fact-source vocabulary**

Run:

```powershell
rg -n 'candidate|selector|path_template|rule_hash|text_rules_hash|scope_hash|fact_id|location_path|metadata|schema_version|error_code|report|事实|候选|规则|范围|过期' app rust/src tests skills/att-mz-protocol skills/att-mz skills/att-mz-release
```

Expected: command returns candidate fact-source sites. Classify producers, consumers, final consumption paths, and duplicate fact construction risks.

- [ ] **Step 2: Inspect schema and report contracts**

Run:

```powershell
rg -n 'schema_version|CURRENT_SCHEMA_VERSION|TEXT_FACT_SCHEMA_VERSION|error_code|report|AgentReport|translation_items|text_facts|text_index|rule_hash|scope_hash' app rust/src tests app/persistence/schema/current.sql
```

Expected: command returns contract sites across Python, Rust, tests, and schema. Check whether JSON schema, SQLite schema, report fields, and error codes express one current contract.

- [ ] **Step 3: Inspect docs or Skill as reverse fact sources**

Run:

```powershell
rg -n 'candidate|selector|scope|hash|location_path|fact_id|schema|规则|候选|当前事实|事实源' README.md docs/superpowers skills/att-mz-protocol skills/att-mz skills/att-mz-release tests
```

Expected: command returns human docs, Skill, and tests that may describe fact sources. Findings only count when docs, Skill, or tests can override or mislead current runtime contracts.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-01-fact-sources-contract.md` using the shared template. Include:

- fact-source list;
- producer and consumer list;
- final consumption path;
- confirmed duplicate or drifting sources;
- recommended unique source;
- entries to delete, merge, or downgrade.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-01-fact-sources-contract.md' -Pattern $patterns
```

Expected: no output.

## Task 3: Track 02 Rust Primary Path

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-02-rust-primary-path.md`
- Read: `rust/src/native_core/`
- Read: `app/native_*.py`
- Read: `app/text_facts.py`
- Read: `app/agent_toolkit/`
- Read: `app/plugin_source_text/`
- Read: `app/nonstandard_data/`
- Read: `app/event_command_text/`
- Read: `app/note_tag_text/`
- Read: related `tests/test_native_*.py`

- [ ] **Step 1: Scan Python heavy-core responsibilities**

Run:

```powershell
rg -n 'scan|candidate|selector|AST|parse|hash|stale|quality|write.*protocol|write_back|TextScope|build\(|extract|validate|coverage|cache|fallback|native' app tests
```

Expected: command returns Python logic that may still perform CPU-heavy scanning, rule matching, AST parsing, stale checks, hash construction, quality checks, or write-back protocol decisions.

- [ ] **Step 2: Scan Rust primary capabilities**

Run:

```powershell
rg -n 'scan|candidate|selector|ast|parse|hash|stale|quality|write_back|scope_index|rule|plugin_source|nonstandard|event_command|note_tag|placeholder' rust/src
```

Expected: command returns Rust implementations and gaps. Compare with Python sites from Step 1 to identify Rust-owned paths and missing Rust entry points.

- [ ] **Step 3: Inspect Python native adapters**

Run:

```powershell
rg -n 'native|_native|adapter|fallback|return .*report|schema_version|json|validate|scan_rule_candidates|build_native' app/native_*.py app/agent_toolkit app/application tests/test_native_*.py
```

Expected: command returns adapter boundaries. Check whether adapters merely pass parameters and assemble reports, or reimplement business judgment.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-02-rust-primary-path.md` using the shared template. Include:

- Rust already-owned production paths;
- Rust capability gaps;
- Python deletion candidates;
- Python boundaries that should remain;
- Python locations that must stop growing.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-02-rust-primary-path.md' -Pattern $patterns
```

Expected: no output.

## Task 4: Track 03 Cross-Command Lifecycle

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-03-cross-command-lifecycle.md`
- Read: `app/cli_main.py`
- Read: `app/cli/`
- Read: `app/application/`
- Read: `app/agent_toolkit/services/`
- Read: `app/plugin_source_text/`
- Read: `app/nonstandard_data/`
- Read: `app/event_command_text/`
- Read: `app/note_tag_text/`
- Read: `rust/src/native_core/`
- Read: related CLI and agent toolkit tests

- [ ] **Step 1: Map command entry points**

Run:

```powershell
rg -n 'export-|validate-|import-|rebuild-text-index|translate|quality-report|audit-coverage|write-back|prepare-agent-workspace|validate-agent-workspace' app tests README.md skills/att-mz-protocol skills/att-mz skills/att-mz-release
```

Expected: command returns command definitions, service calls, docs, Skill references, and tests. Build the lifecycle sequence for each rule or candidate family.

- [ ] **Step 2: Trace plugin-source lifecycle sample**

Run:

```powershell
rg -n 'plugin-source|plugin_source|PluginSource|selector|excluded_selectors|source_file|ast|runtime_map|stale' app rust/src tests skills/att-mz-protocol skills/att-mz skills/att-mz-release
```

Expected: command returns plugin-source rule paths. Check whether export, validate, import, rebuild, translate, and write-back consume the same candidate fact.

- [ ] **Step 3: Trace other external rule chains**

Run:

```powershell
rg -n 'nonstandard|event_command|note_tag|mv_virtual_namebox|placeholder|structured_placeholder|terminology|rule_hash|scope_hash' app rust/src tests
```

Expected: command returns nonstandard data, event command, Note tag, MV namebox, placeholder, structured placeholder, and terminology lifecycles. Identify hidden state or repeated interpretation between commands.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-03-cross-command-lifecycle.md` using the shared template. Include:

- each lifecycle command sequence;
- fact source used at each step;
- confirmed cross-command contract breaks;
- boundaries that must be unified by Rust;
- plugin-source sample replay against the spec acceptance sample.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-03-cross-command-lifecycle.md' -Pattern $patterns
```

Expected: no output.

## Task 5: Track 04 Cache, Metadata, And Fast Path

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-04-cache-metadata-fast-path.md`
- Read: `app/text_index.py`
- Read: `app/text_facts.py`
- Read: `app/translation/cache.py`
- Read: `app/agent_toolkit/services/`
- Read: `app/persistence/`
- Read: `rust/src/native_core/scope_index/`
- Read: `rust/src/native_core/write_back_plan/`
- Read: relevant tests containing cache, metadata, workflow gate, or precheck behavior

- [ ] **Step 1: Scan fast path and cache sites**

Run:

```powershell
rg -n 'fast|cache|metadata|precheck|warm|summary|skip|shortcut|mtime|hash|source_hash|rule_hash|scope_hash|workflow_gate|gate|stale|current' app rust/src tests
```

Expected: command returns fast path and cache candidates. Identify skip conditions and whether they bypass current Rust fact validation.

- [ ] **Step 2: Inspect SQLite metadata and text index metadata**

Run:

```powershell
rg -n 'metadata|text_index|text_facts|scope|summary|schema_version|contract_version|rule_hash|source_hash|runtime_map' app/persistence app/text_index.py app/text_facts.py rust/src/native_core tests
```

Expected: command returns metadata producers and consumers. Check whether metadata records enough rule口径, text-rule口径, source snapshot, and Rust contract version to invalidate safely.

- [ ] **Step 3: Inspect workflow gate and quality fast paths**

Run:

```powershell
rg -n 'workflow|gate|quality|pending|translated|stale|precheck|skip|cache|summary|report' app/agent_toolkit app/translation app/native_quality.py rust/src/native_core/quality tests
```

Expected: command returns gate and quality paths. Check whether they compare only input text and database records while skipping current candidate membership.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-04-cache-metadata-fast-path.md` using the shared template. Include:

- fast path list;
- skip conditions for each fast path;
- whether each bypasses Rust primary path;
- stale-as-passed risks;
- entries to delete, tighten, or move to Rust validation.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-04-cache-metadata-fast-path.md' -Pattern $patterns
```

Expected: no output.

## Task 6: Track 05 Tests And Acceptance

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-05-tests-acceptance.md`
- Read: `tests/`
- Read: `rust/src/**/tests`
- Read: `rust/src/native_core/**`
- Read: `tests/test_scan_budget.py`
- Read: `tests/scan_budget_contract.py`
- Read: `tests/agent_toolkit_contract_fixtures.py`
- Read: `tests/_native_write_plan_helper.py`

- [ ] **Step 1: Inventory Python and Rust tests**

Run:

```powershell
rg -n 'plugin_source|plugin-source|nonstandard|event_command|note_tag|placeholder|structured_placeholder|text_fact|scope|fact_id|location_path|stale|same path|write_back|scan_budget|native|fallback|legacy' tests rust/src
```

Expected: command returns behavior tests, helper fixtures, scan-budget protections, and native tests. Classify coverage by business behavior, boundary conditions, failure paths, and implementation-detail locks.

- [ ] **Step 2: Inspect lifecycle and regression gaps**

Run:

```powershell
rg -n 'export.*import|import.*rebuild|rebuild.*stale|translate.*write|write.*fact_id|same.*path|excluded_selectors|quality_error|error_code|source_hash|rule_hash' tests rust/src
```

Expected: command returns tests that may cover command lifecycles and plugin-source acceptance samples. Identify missing tests, especially "导入通过后重建不能立刻 stale".

- [ ] **Step 3: Inspect test helper second-model risks**

Run:

```powershell
rg -n 'make_|fixture|helper|fake|stub|mock|legacy|fallback|old|location_path|fact_id|schema|current|native' tests
```

Expected: command returns helpers and fixtures. Check whether helpers encode a second business model or use Python integration tests to cover Rust internal logic.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-05-tests-acceptance.md` using the shared template. Include:

- current test coverage list;
- missing Rust tests;
- Python flow tests that should remain;
- Python large integration regions that should not expand;
- plugin-source acceptance-sample test gaps.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-05-tests-acceptance.md' -Pattern $patterns
```

Expected: no output.

## Task 7: Track 06 Migration And Deletion

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-06-migration-deletion.md`
- Read: `app/`
- Read: `rust/src/`
- Read: `tests/`
- Read: `docs/records/rust-scope-index/`
- Read: `docs/records/reviews/rust-migration/`
- Read: `docs/superpowers/plans/`
- Read: `docs/superpowers/specs/`

- [ ] **Step 1: Scan dual-track and deletion signals**

Run:

```powershell
rg -n 'legacy|fallback|deprecated|old|delete|remove|delet|slim|thin|adapter|migration|migrate|Python|Rust|native|旧|历史|兼容|迁移|废弃|回退|删除|瘦身' app rust/src tests docs/records/rust-scope-index docs/records/reviews/rust-migration docs/superpowers/plans docs/superpowers/specs
```

Expected: command returns migration notes, old helper references, planned deletion points, and dual-track risks. Classify current production code separately from historical records.

- [ ] **Step 2: Inspect direct old-path calls**

Run:

```powershell
rg -n 'TextScopeService\.build|PluginSourceTextExtraction|NoteTagTextExtraction|collect_.*candidates|scan_.*candidates|extract_all_text|old|legacy|fallback' app tests
```

Expected: command returns direct calls to old or heavy Python paths. Determine which are production paths, tests, wrappers, or historical protections.

- [ ] **Step 3: Inspect migration stage records**

Run:

```powershell
rg -n '下一批|剩余风险|删除|瘦身|旧路径|native|Rust|Python|主路径|事实来源' docs/records/rust-scope-index docs/records/reviews/rust-migration docs/superpowers/plans docs/superpowers/specs
```

Expected: command returns existing phase plans and records. Use these only as context; current runtime code remains the source of confirmed findings.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-06-migration-deletion.md` using the shared template. Include:

- deletion list;
- slimming list;
- migration phase suggestions;
- completion conditions for each phase;
- dual-track states that cannot remain as completion.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-06-migration-deletion.md' -Pattern $patterns
```

Expected: no output.

## Task 8: Track 07 Performance And Concurrency Evidence

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/batches/track-07-performance-concurrency.md`
- Read: `app/`
- Read: `rust/src/`
- Read: `tests/test_scan_budget.py`
- Read: `tests/scan_budget_contract.py`
- Read: `docs/records/reviews/rust-migration/large-game-performance-defect-report.md`
- Read: `docs/records/rust-scope-index/`

- [ ] **Step 1: Scan full-scan and repeated-scan sites**

Run:

```powershell
rg -n 'scan|full|all|walk|iter|collect|load_game_data|TextScopeService|build\(|for .* in|parallel|rayon|threads|ATT_MZ_RUST_THREADS|scan_budget|performance|timing|diagnostics' app rust/src tests docs/records/reviews/rust-migration docs/records/rust-scope-index
```

Expected: command returns scan, iteration, concurrency, and diagnostic sites. Identify commands that traverse all game text, plugin config, plugin source, AST, database translation rows, or write-back plans.

- [ ] **Step 2: Inspect Rust concurrency configuration**

Run:

```powershell
rg -n 'ATT_MZ_RUST_THREADS|rayon|ThreadPool|par_iter|join|spawn|threads|concurrency|parallel' rust/src app tests
```

Expected: command returns Rust and Python concurrency entry points. Check whether thread limits are configurable and actually participate in heavy scheduling.

- [ ] **Step 3: Inspect performance evidence records**

Run:

```powershell
rg -n 'elapsed|ms|seconds|profile|benchmark|scan_budget|真实|性能|耗时|瓶颈|N\+1|全量|重复扫描' docs/records/reviews/rust-migration docs/records/rust-scope-index tests app rust/src
```

Expected: command returns real or claimed performance evidence. Separate true CLI evidence from scan-budget or theoretical complexity checks.

- [ ] **Step 4: Write track report**

Create `docs/records/reviews/rust-primary-refactor/batches/track-07-performance-concurrency.md` using the shared template. Include:

- scan counts and scan ranges;
- Python serial heavy work;
- Rust concurrency entry points;
- true CLI performance evidence gaps;
- metrics that later refactors must capture.

- [ ] **Step 5: Self-check the track report**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Select-String -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches\track-07-performance-concurrency.md' -Pattern $patterns
```

Expected: no output.

## Task 9: Merge Track Reports Into Final Report

**Files:**
- Create: `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md`
- Read: all files under `docs/records/reviews/rust-primary-refactor/batches/`

- [ ] **Step 1: Verify all 7 track reports exist**

Run:

```powershell
Get-ChildItem -File -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches' | Sort-Object Name | Select-Object Name,Length
```

Expected: exactly these 7 files are present:

```text
track-01-fact-sources-contract.md
track-02-rust-primary-path.md
track-03-cross-command-lifecycle.md
track-04-cache-metadata-fast-path.md
track-05-tests-acceptance.md
track-06-migration-deletion.md
track-07-performance-concurrency.md
```

- [ ] **Step 2: Extract severity headings**

Run:

```powershell
rg -n '^### P[0-3]：' docs/records/reviews/rust-primary-refactor/batches
```

Expected: command returns confirmed findings, or exits with no matches if all tracks passed. Use this output as the first source for the highest-priority index.

- [ ] **Step 3: Extract cross-track lists**

Run:

```powershell
rg -n '^## 双事实来源清单|^## Rust 主路径缺口|^## Python 删除候选|^## 测试缺口|^## 交叉引用|^### P[0-3]：' docs/records/reviews/rust-primary-refactor/batches
```

Expected: command returns section anchors and confirmed findings. Use it to deduplicate same-root issues across tracks.

- [ ] **Step 4: Write final merged report**

Create `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md` with exactly these sections:

```markdown
# Rust 主路径收束专项 Review 总报告

## 执行摘要

## 最高优先级问题

## 横向矩阵

### 单一事实来源破坏

### Rust 主路径缺口

### Python 删除候选

### 跨命令生命周期断点

### fast path 和 cache 风险

### 性能与并发风险

### 测试验收缺口

## 插件源码规则样本复盘

## 后续重构建议批次

## 明确拒绝的错误方向

## 剩余不确定项

## 只读边界声明
```

Expected: final report states `PASS`, `FAIL`, or `BLOCKED`; lists P0/P1 blockers; merges same-root causes; identifies Python deletion or slimming candidates; identifies Rust prerequisite gaps; and declares no source or state-changing files were modified.

- [ ] **Step 5: Confirm final report references every track**

Run:

```powershell
rg -n 'track-01|track-02|track-03|track-04|track-05|track-06|track-07' docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md
```

Expected: all 7 track names or equivalent explicit references appear.

## Task 10: Review Artifact Self-Check

**Files:**
- Read: `docs/records/reviews/rust-primary-refactor/`

- [ ] **Step 1: Scan for unfinished markers**

Run:

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换')
Get-ChildItem -Recurse -File -LiteralPath 'docs\records\reviews\rust-primary-refactor' | Select-String -Pattern $patterns
```

Expected: no output.

- [ ] **Step 2: Scan for forbidden state-changing command recommendations**

Run:

```powershell
rg -n 'add-game|reset-game|translate|write-back|rebuild-active-runtime|import-|reset-translations|run-all|--write' docs/records/reviews/rust-primary-refactor
```

Expected: matches are allowed only when explicitly described as prohibited, as lifecycle names, or as commands to review conceptually. They must not appear as executed commands during this review.

- [ ] **Step 3: Confirm only review reports changed**

Run:

```powershell
git status --short
```

Expected: new or modified files from this execution are only under `docs/records/reviews/rust-primary-refactor/`. Pre-existing unrelated changes may still appear and must be listed as pre-existing in delivery.

- [ ] **Step 4: Run Markdown-sensitive diff check**

Run:

```powershell
git diff --check -- docs/records/reviews/rust-primary-refactor
```

Expected: no whitespace errors.

## Task 11: Delivery

**Files:**
- Read: `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md`
- Read: `docs/records/reviews/rust-primary-refactor/batches/`

- [ ] **Step 1: Summarize result to the user**

Final response must include:

- final report path;
- overall result: `PASS`, `FAIL`, or `BLOCKED`;
- counts of P0, P1, P2, and P3 findings;
- whether subagents were used;
- list of commands actually run;
- checks not run and why;
- confirmation that no source, database, game, log, output, temp, build, or private runtime data was modified or read.

- [ ] **Step 2: Ask before staging or committing reports**

Do not stage, commit, or push review reports unless the user explicitly asks. If the user asks to publish the reports, follow the repository git rules and keep the commit message in Chinese.

## Plan Self-Review

- Spec coverage: This plan covers the approved design's 7 review tracks, read-only scope, Rust-primary direction, single fact-source axis, fast path/cache risks, test and performance acceptance, subagent execution, per-track reports, final report, and prohibited state-changing commands.
- Placeholder scan: The plan contains no incomplete implementation markers. Dynamic review findings are produced during execution and must be filled with evidence in the track reports.
- Type and path consistency: All review artifact paths use `docs/records/reviews/rust-primary-refactor/`; all 7 track filenames are fixed and reused consistently in creation, merge, self-check, and delivery.
