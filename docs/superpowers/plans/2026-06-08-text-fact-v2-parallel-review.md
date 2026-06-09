# Text Fact v2 Current-vs-6efa Parallel Review Task

本文档用于在新 Codex 会话中执行一次只读 review。它内化当前仓库相对 `6efa43e5c578a4e4572ffbfd792caa266273a6e8` 的审查目标、并发子代理分工、证据标准和闭环交付格式。

执行本 review 时，不修改源码、测试、配置、Skill、README 或业务文档。若用户要求落盘 review 结论，只允许新增一份 review 报告到 `docs/records/reviews/`；默认直接在最终回复中给出结论。

## 新会话启动指令

在新会话中直接发送：

```text
/goal 按 docs/superpowers/plans/2026-06-08-text-fact-v2-parallel-review.md 对当前 HEAD 相对 6efa43e5c578a4e4572ffbfd792caa266273a6e8 执行只读并发 review。允许并要求使用子代理并发审查；禁止代码改动；最终按文档要求输出闭环 review 结论。
```

## 核心目标

本次 review 只回答一个问题：

> 当前 HEAD 相对 `6efa43e5c578a4e4572ffbfd792caa266273a6e8` 的 Text Fact Contract v2 改动，是否真正形成了单一、清楚、可验证的当前文本事实契约，并且没有把旧 `location_path` 身份、旧 Python 全量文本范围、旧 runtime literal 误归类或旧写回路径留在迁移后主流程里？

review 必须同时覆盖正确性、业务表现、性能风险、测试护栏和文档契约。不要只看代码是否能通过测试，也不要只看文档是否说得通。

## 已知上下文

对比范围：

```powershell
git diff 6efa43e5c578a4e4572ffbfd792caa266273a6e8..HEAD
```

当前已知差异规模：

```text
89 files changed, 16903 insertions(+), 1340 deletions(-)
```

当前 v2 主线：

- `translation_items` 从以 `location_path` 为主键，改为以 `fact_id` 为主键。
- 已保存译文必须带 `source_fact_raw_hash` 和 `source_fact_translatable_hash`。
- 当前文本事实由 `text_facts_v2`、`text_fact_render_parts_v2`、`text_fact_domain_payloads_v2` 和 `text_fact_scope_v2` 表表达。
- `location_path` 只作为用户可见定位和二级过滤条件，不再作为已保存译文正确性身份。
- Rust 写回按 `fact_id + raw_hash + translatable_hash + render_parts` 读取和重建写回文本。
- placeholder 候选和 active runtime literal 诊断不属于当前 `text_facts_v2` 翻译事实域。
- 真实游戏性能尚未由本 review 文档宣称通过；只能审代码侧性能护栏和明显风险。

执行 review 前必须阅读这些当前文档：

- `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`
- `docs/superpowers/plans/2026-06-07-text-fact-contract-v2-implementation.md`
- `docs/superpowers/plans/2026-06-08-text-fact-v2-review-closure.md`
- `README.md` 中“当前文本事实契约”小节
- `CHANGELOG.md` 中“未发布 - Text Fact Contract v2 契约冻结”小节

阅读原则：

- `docs/` 是人类文档，不是 Agent 翻译流程运行契约。
- `skills/att-mz-protocol/` 是 Skill 协议源；`skills/att-mz/` 和 `skills/att-mz-release/` 是生成目标。
- 原实现计划中 runtime literal 进入 v2 fact 的内容已被 closure plan 接管；review 时以 closure plan 和当前 design 为准。

## 并发子代理要求

必须使用子代理并发 review，因为本任务不涉及代码改动，多个审查面之间没有共享写状态。主代理负责派发、汇总、去重、严重程度统一和最终结论。

如果当前环境没有可用子代理工具，主代理必须在最终报告中记录：

```text
未能使用子代理并发 review；原因：写明实际不可用原因。已改为单会话分批审查。
```

这时仍必须按本文档的分工逐批审查，不能合并成泛泛总结。

### 子代理 A：Schema 与持久化身份

重点文件：

- `app/persistence/schema/current.sql`
- `app/persistence/sql.py`
- `app/persistence/records.py`
- `app/persistence/text_fact_records.py`
- `app/persistence/translation_records.py`
- `app/persistence/run_records.py`
- `app/rmmz/schema.py`
- `tests/test_persistence.py`

必须检查：

- schema version 是否和 Python/Rust 侧一致。
- `translation_items` 是否真正以 `fact_id` 为主键。
- 已保存译文是否强制要求 `fact_id`、`source_fact_raw_hash`、`source_fact_translatable_hash`。
- 质量错误是否携带并使用 `fact_id`，而不是只靠 `location_path`。
- path-based helper 是否只作为用户命令和清理辅助，不是当前成功事实源。
- 是否存在旧库、旧 schema、旧 scope 静默兼容或吞异常。

### 子代理 B：Python v2 adapter 与 Agent 服务

重点文件：

- `app/text_facts.py`
- `app/application/handler.py`
- `app/application/use_cases/translation_run.py`
- `app/translation/cache.py`
- `app/translation/verify.py`
- `app/agent_toolkit/services/coverage.py`
- `app/agent_toolkit/services/quality.py`
- `app/agent_toolkit/services/manual_translation.py`
- `app/agent_toolkit/services/workspace.py`
- `app/agent_toolkit/services/common.py`
- `app/agent_toolkit/services/rule_validation.py`

必须检查：

- pending、translated、stale、quality_error 是否按当前 v2 fact 身份判断。
- `location_path` 是否只用于显示、排序、用户路径输入或样本输出。
- dedupe、缓存扩展、手动补译导入导出是否保留 fact identity。
- prompt 和用户可见自然语言是否没有泄露内部字段、真实路径、`location_path`、`translated_text` 或 `位置:`。
- migrated flows 是否没有调用 `TextScopeService.build()` 或旧 Python full-scope rebuild 才能成功。
- plugin-source 和 note-tag 规则验证是否没有生产路径回退到旧 extractor。

### 子代理 C：Rust v2 facts、索引重建与写回

重点文件：

- `rust/src/native_core/text_facts.rs`
- `rust/src/native_core/scope_index/rebuild.rs`
- `rust/src/native_core/scope_index/storage.rs`
- `rust/src/native_core/scope_index/mv_virtual_namebox.rs`
- `rust/src/native_core/scope_index/event_commands.rs`
- `rust/src/native_core/scope_index/plugin_source.rs`
- `rust/src/native_core/write_back_plan/repository.rs`
- `rust/src/native_core/write_back_plan/models.rs`
- `rust/src/native_core/write_back_plan/command_writer.rs`
- `rust/src/native_core/write_back_plan/plugin_source.rs`
- `rust/src/native_core/write_back_plan/terminology.rs`

必须检查：

- fact id、raw hash、visible hash、translatable hash 的输入是否稳定。
- supported domains 是否只包含当前翻译事实域。
- render parts 是否能重建写回需要的原始结构，特别是 MV 虚拟名字框。
- storage 是否在一个事务中重写 v2 facts、render parts、payload 和旧 warm index summary。
- write-back repository 是否用 `fact_id + raw_hash + translatable_hash` join 已保存译文和当前 facts。
- allowed path 是否只是二级过滤，不是正确性身份。
- Rust 并行和 SQLite 查询是否没有明显 N+1 或无界扫描。

### 子代理 D：测试、扫描预算和防回退护栏

重点文件：

- `tests/test_scan_budget.py`
- `tests/scan_budget_contract.py`
- `tests/test_agent_toolkit_quality_report.py`
- `tests/test_agent_toolkit_manual_import.py`
- `tests/test_agent_toolkit_workspace.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_native_scope_index.py`
- `tests/test_rmmz_write_plan.py`
- `tests/test_translation_cache_context.py`
- `tests/_native_write_plan_helper.py`
- `tests/agent_toolkit_contract_fixtures.py`
- `rust/src/native_core/write_back_plan/test_support.rs`

必须检查：

- 测试是否固定业务行为，而不是固定自然语言段落或历史实现细节。
- scan budget 是否能防止 migrated flows 回到 Python full-scope rebuild、旧 extractor、旧 `location_path` join。
- 是否存在大量测试夹具形成第二业务模型，和生产 schema、Rust test support 或 Python adapter 漂移。
- 测试是否覆盖旧库失败、旧 workspace 失败、stale translation、same path different fact、same fact current translation 等关键边界。
- 是否存在只在测试里允许的旧路径，但生产代码也能误用。

### 子代理 E：文档、Skill 与用户契约

重点文件：

- `README.md`
- `CHANGELOG.md`
- `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md`
- `docs/superpowers/plans/2026-06-07-text-fact-contract-v2-implementation.md`
- `docs/superpowers/plans/2026-06-08-text-fact-v2-review-closure.md`
- `skills/att-mz-protocol/templates/references/cli-command-contract.md.in`
- `skills/att-mz/references/cli-command-contract.md`
- `skills/att-mz-release/references/cli-command-contract.md`
- `tests/test_skill_protocol.py`
- `tests/test_release_notes.py`

必须检查：

- README 是否用用户能行动的中文说明发生了什么、影响什么、下一步做什么。
- CHANGELOG 是否具体说明破坏性变化、协议变化、性能边界和验证命令。
- docs 是否只描述当前实现，不倒置覆盖 Skill 契约。
- Skill canonical 源和生成目标是否语义一致。
- 开发版入口和发行版入口是否只在命令入口层不同，业务语义一致。
- 文档示例是否没有真实本机路径、用户名、客户项目名或用户数据。

### 子代理 F：性能风险与代码膨胀结构

重点文件：

- `app/text_facts.py`
- `app/agent_toolkit/services/coverage.py`
- `app/agent_toolkit/services/quality.py`
- `app/persistence/sql.py`
- `rust/src/native_core/scope_index/rebuild.rs`
- `rust/src/native_core/scope_index/storage.rs`
- `rust/src/native_core/write_back_plan/repository.rs`
- `tests/test_scan_budget.py`
- `docs/plans/completed/non-network-cli-performance-closure.md`
- `docs/records/reviews/rust-migration/large-game-performance-defect-report.md`

必须检查：

- 新增 SQL count/report 是否重复读取 scope、重复 join 或形成可合并的统计往返。
- write-back 前置校验是否会扫描大量译文表；若会，是否有索引和合理边界。
- `rebuild-text-index` 的全量重活是否集中在 Rust，不回到 Python。
- 新增大文件是否只是测试/契约护栏，还是生产职责已经过密。
- 是否有真实性能证据缺口；不能把 scan budget 说成真实游戏性能通过。
- 是否需要记录“代码膨胀原因”和“后续可审查的瘦身对象”，但不要写修复方案。

## 主代理执行步骤

### 1. 建立只读基线

运行：

```powershell
git status --short
git log --oneline 6efa43e5c578a4e4572ffbfd792caa266273a6e8..HEAD
git diff --shortstat 6efa43e5c578a4e4572ffbfd792caa266273a6e8..HEAD
git diff --stat 6efa43e5c578a4e4572ffbfd792caa266273a6e8..HEAD
git diff --name-status 6efa43e5c578a4e4572ffbfd792caa266273a6e8..HEAD
```

如果工作树不干净，记录未提交文件；不要清理、还原或提交。

### 2. 派发并发子代理

同时派发 A 到 F 六个子代理。每个子代理只读审查，不修改文件。每个子代理必须返回：

```text
子代理编号：
审查范围：
已读关键文件：
已运行命令：
发现的问题：
无问题但已覆盖的检查：
证据缺口：
```

问题条目必须使用统一格式：

```text
[P0|P1|P2|P3] 标题
证据：文件路径和行号，或命令输出摘要。
影响：业务层影响，用大白话说明。
根因线索：旧路径、多事实来源、契约缺口、测试缺口或性能边界。
是否需要复核：是/否
```

严重程度：

- P0：会导致错误译文写回、数据一致性破坏、旧库静默成功、Prompt 隐私泄露、发行/Skill 契约错误。
- P1：会导致 v2 单一事实来源失败、旧路径仍进主流程、关键命令错误统计或明显性能回退。
- P2：测试护栏不足、报告文案误导、代码职责过密、性能风险未证实但结构可疑。
- P3：局部清晰度、文档表述、命名或组织问题。

### 3. 主代理汇总裁决

主代理必须：

- 去重同一根因的问题。
- 把跨子代理证据合并成一个问题。
- 将只有推测、没有证据的问题放入“需复核”。
- 不写修复方案，不写补丁，不改代码。
- 对“无问题”区域也说明审过哪些关键边界。
- 明确说明是否使用了子代理并发 review。

### 4. 可选验证命令

review 默认是只读审查，不要求为了 review 重跑全量测试。若时间允许，主代理可运行：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
uv run python scripts/generate_skill_protocol.py --check
git diff --check
```

运行结果只能作为证据。未运行时必须写清“未运行”和剩余风险，不能写成通过。

## 必查问题清单

review 至少要回答以下问题：

- 是否还有 migrated production path 用 `translations.location_path = facts.location_path` 判定已翻译成功？
- 是否还有 migrated production path 必须构建完整 Python text scope 才能成功？
- 是否还有 `PluginSourceTextExtraction` 或 `NoteTagTextExtraction` 作为生产规则验证 fallback？
- 手动补译、模型翻译保存、质量错误清理是否都保留并消费 `fact_id`？
- Rust 写回是否会把同一路径下不同 fact 混成一条译文？
- runtime literal 和 placeholder 候选是否被错误写入当前翻译事实域？
- v2 facts、render parts、payload 和 scope 的 schema 是否形成单一事实来源？
- old database、old workspace、old runtime map 是否显式失败并给出下一步命令？
- prompt 是否没有暴露内部路径、字段、selector、`location_path` 或 `位置:`？
- 测试是否覆盖 same path different fact、stale translation、old scope、old workspace 和 no fallback？
- 新增大文件是否有职责过载，还是可接受的契约/测试护栏膨胀？
- 文档和 Skill 是否没有“docs 覆盖 Skill”的倒置关系？
- 性能结论是否只声明代码侧护栏，不冒充真实游戏 benchmark 通过？

## 最终输出格式

最终回复必须按以下顺序输出：

```text
结论：
- PASS：未发现 P0/P1；仅有 P2/P3 或证据缺口。
- FAIL：发现 P0/P1，需要先处理。
- BLOCKED：关键证据无法读取或子代理/命令无法完成，不能给出可靠结论。

并发说明：
- 是否使用子代理。
- 子代理数量和分工。
- 未使用时的具体原因。

主要发现：
按严重程度排序，先 P0，再 P1，再 P2，再 P3。

业务层影响：
用大白话说明每个重要问题会让用户看到什么、错在哪里、为什么危险。

代码膨胀判断：
区分契约/测试护栏膨胀、Rust/Python 双层边界膨胀、真实生产职责过载。

已覆盖但未发现问题的区域：
列出关键边界，不要只写“已检查”。

验证命令：
列出实际运行的命令和结果；未运行的命令也列出原因。

需复核问题：
只放证据不足的问题，说明还缺什么证据。

剩余风险：
尤其说明真实游戏性能是否未验收。
```

如果发现 0 个问题，也必须说明：

- 哪些子代理审查范围没有发现问题。
- 哪些验证未运行。
- 真实游戏性能是否仍需目标样本 benchmark。

## 禁止事项

- 禁止修改源码、测试、配置、Skill、README 或业务文档。
- 禁止提交 commit。
- 禁止把 review 变成修复计划。
- 禁止提出代码补丁。
- 禁止只用 diff 行数判断好坏。
- 禁止把“代码很多”单独当成问题；必须说明它遮住了哪个业务模型、事实来源、性能路径或审查边界。
- 禁止把 docs 当作 Agent 翻译流程契约。
- 禁止宣称真实游戏性能已通过，除非本次 review 实际运行了目标样本 benchmark 并记录结果。

## 闭环标准

本 review 完成时必须满足：

- A 到 F 六个审查面都已完成，或明确记录无法并发执行的原因。
- 每个确认问题都有证据、影响和严重程度。
- P0/P1 问题有清楚的业务影响说明。
- 没有把修复方案混进问题条目。
- 最终结论是 `PASS`、`FAIL` 或 `BLOCKED` 三选一。
- 对真实游戏性能只给出已验证事实，不夸大结论。
