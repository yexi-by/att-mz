# 半迁移与无迁移并发 Review 执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:dispatching-parallel-agents` to execute this review. This is a read-only review plan; do not modify source code, tests, schema, Skill, README, configuration, generated files, database files, logs, outputs, or game files.

**Goal:** 对当前 HEAD 相对 `origin/codex/native-fact-contract-refactor` 的 PCRE2 规则运行时相关改动执行只读并发 review，专门判断是否存在半迁移、无迁移、伪删除、空门面或假成功测试。

**Architecture:** 主代理建立只读基线、抽取迁移声明、并发派发 8 个 explorer 子代理。每个子代理只审一个独立面，返回证据化报告；主代理只做去重、严重程度统一、真实 owner 判定和最终裁决。

**Tech Stack:** Git, PowerShell, ripgrep, Python source review, Rust source review, SQLite schema review, Codex `multi_agent_v1` subagents when available.

---

## Source Spec

执行前必须阅读：

- `docs/superpowers/specs/2026-06-11-half-migration-parallel-review-design.md`
- `docs/superpowers/specs/2026-06-11-pcre2-rule-runtime-design.md`
- `docs/superpowers/plans/2026-06-11-pcre2-rule-runtime-implementation.md`
- `docs/superpowers/specs/2026-06-11-redundant-source-test-deletion-design.md`
- `AGENTS.md`

本 plan 只用于 review，不是修复计划。发现问题后不改代码，不写修复补丁，不做临时兜底。

## Review Baseline

默认对比范围：

```powershell
origin/codex/native-fact-contract-refactor...HEAD
```

如果 `origin/codex/native-fact-contract-refactor` 不存在，主代理必须停止并在最终结论中标记 `BLOCKED`，要求用户提供 base；不得改用未经说明的 base。

基线命令：

```powershell
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse --verify origin/codex/native-fact-contract-refactor
git log --oneline origin/codex/native-fact-contract-refactor..HEAD
git diff --shortstat origin/codex/native-fact-contract-refactor...HEAD
git diff --stat origin/codex/native-fact-contract-refactor...HEAD
git diff --name-status origin/codex/native-fact-contract-refactor...HEAD
```

如果工作树不干净，记录未提交文件；不要清理、还原、暂存或提交。

## Allowed Actions

允许：

- 读取仓库文件。
- 使用 `rg`、`rg --files`、`Get-Content`、`git diff`、`git log`、`git show`、`git grep` 等只读命令。
- 运行不会写数据库、不会写游戏目录、不会改源码或生成物的只读检查。
- 子代理返回 Markdown 文本报告。
- 如果用户明确要求落盘 review 结果，主代理只允许新增 `docs/records/reviews/half-migration-pcre2/final-report.md`；默认不落盘报告。

禁止：

- 修改源码、测试、schema、Skill、README、docs、脚本、配置和发行文件。
- 执行会写 `data/db/`、`logs/`、`outputs/`、游戏目录或发行目录的命令。
- 执行 `import-*`、`translate`、`write-back`、`rebuild-text-index`、`reset-*`、`run-all` 等状态变更命令。
- 为了证明问题可修而实施修复。
- 把 “增加 Python guard”“旧代码未调用”“native 返回 success” 写成通过结论。

## Main-Agent Local Checklist

- [ ] **Step 1: Read source spec and establish baseline**

Run the baseline commands in `Review Baseline`. Record:

```text
branch:
base:
shortstat:
dirty files:
```

Expected: base exists. If base is missing, final result is `BLOCKED`.

- [ ] **Step 2: Extract migration claims**

Run:

```powershell
rg -n "commit_rule_import|prepare_rule_import|scan_rule_domain|inspect_rule_store|build_rules_fingerprint|rule_runtime|PCRE2|统一规则|单一规则|已删除|接管|Rust 主路径|最终删除|fallback|legacy|old|compat|deprecated|allow\(dead_code\)|\?P<|\?<" docs README.md CHANGELOG.md skills app rust tests
```

Do not treat this output as findings by itself. Use it to seed the subagent prompts and final owner matrix.

- [ ] **Step 3: Dispatch 8 subagents in parallel**

If `multi_agent_v1.spawn_agent` is available, spawn A through H with `agent_type: explorer`. Do not use workers because this review is read-only. Do not set a model override unless the user explicitly requests one.

If no subagent tool is available, execute the 8 tracks sequentially in the main session and state in final output:

```text
是否使用子代理并发 review：否
原因：当前环境没有可用子代理工具。
降级方式：主代理按 A-H 轨道逐项只读审查。
```

- [ ] **Step 4: While agents run, do one local high-risk trace**

Trace only this known high-risk path locally:

```text
Python import service -> app.native_rule_runtime.commit_rule_import -> Rust rule_runtime api -> Rust store -> SQLite rules/rule_sets/rule_domain_states
```

The local trace must not duplicate every subagent track. Its purpose is to keep the critical path moving and to prepare the final owner matrix.

- [ ] **Step 5: Collect reports and normalize findings**

For every reported issue, normalize into:

```text
[P0|P1|P2|P3] title
phenomenon: 半迁移 | 无迁移 | 伪删除 | 空门面 | 假成功测试
evidence:
claimed owner:
real owner:
real side effect:
impact:
```

Merge duplicate root causes. If evidence is weak, move the item to `需复核`, not `发现`.

- [ ] **Step 6: Produce final review**

Use the final output format in this plan. Do not include code patches or implementation steps.

## Shared Subagent Instructions

Every subagent receives this common instruction before its track-specific section:

```text
你是只读 review 子代理。目标不是修复代码，而是审查当前 HEAD 相对 origin/codex/native-fact-contract-refactor 是否存在半迁移、无迁移、伪删除、空门面或假成功测试。

必须阅读：
- docs/superpowers/specs/2026-06-11-half-migration-parallel-review-design.md
- docs/superpowers/specs/2026-06-11-pcre2-rule-runtime-design.md

只允许读取文件和运行只读命令，例如 rg、rg --files、Get-Content、git diff、git grep、git log、git show。禁止修改任何文件，禁止运行会写数据库、日志、输出、游戏目录或发行目录的命令。

对比范围固定为：
origin/codex/native-fact-contract-refactor...HEAD

输出必须使用以下结构：

# 轨道 <字母>：<标题>

## 范围

## 只读命令

## 结论
PASS | FAIL | NEEDS_REVIEW

## 关键发现

### [P0|P1|P2|P3] <标题>

- 现象分类：<半迁移 | 无迁移 | 伪删除 | 空门面 | 假成功测试>
- 证据：<文件:行号或命令输出摘要>
- 声明 owner：<谁被声明接管>
- 真实 owner：<谁实际完成副作用>
- 真实副作用：<写库 | 清理 | 扫描 | 报告 | 写回 | 其他>
- 影响：<用户可见或工程可见问题>

## 已覆盖但未发现问题的边界

## 证据缺口

严重程度：
- P0：错误写库、半提交、数据破坏、错误写回、备份缺失后清理、用户报告成功但真实状态失败。
- P1：声明迁移完成或 Rust/current owner 已接管，但真实生产副作用仍由旧侧、Python、空门面或旁路完成；或文档声称生效但生产完全未迁移。
- P2：旧代码、旧测试、旧 fixture、旧 dialect、旧 helper 或假成功测试未清理，当前暂未证明会进入生产主路径。
- P3：命名、文档、注释、测试组织或报告表述容易误导后续维护，但不改变当前真实行为。
```

## Subagent A: Migration Claims And Production Chains

### Spawn Prompt

```text
执行轨道 A：迁移声明与生产链路。

你的目标：找出当前改动中所有声称 PCRE2 规则运行时、Rust rule_runtime、统一规则 store、旧路径删除或 Rust 主路径接管的声明，并追到真实生产调用链。

重点文件和命令线索：
- docs/superpowers/specs/2026-06-11-half-migration-parallel-review-design.md
- docs/superpowers/specs/2026-06-11-pcre2-rule-runtime-design.md
- docs/superpowers/plans/2026-06-11-pcre2-rule-runtime-implementation.md
- README.md
- CHANGELOG.md
- app/native_rule_runtime.py
- app/agent_toolkit/services/
- app/cli_main.py
- main.py
- rust/src/native_core/rule_runtime/
- tests/test_native_rule_runtime.py
- tests/test_agent_toolkit_rule_import.py

必须检查：
- 文档、计划、测试名、API 名称和提交差异是否声称迁移完成。
- CLI 或 Agent service 是否真的接到新 Rust/native owner。
- 新路径是否只在测试中使用。
- 声明 owner 和真实生产 owner 是否一致。

返回：迁移声明清单、每条声明的真实生产链路、已完成迁移/半迁移/无迁移分类、证据缺口。
```

## Subagent B: Commit Store And Transaction Ownership

### Spawn Prompt

```text
执行轨道 B：副作用归属与事务边界。

你的目标：专查 prepare/commit/store 是否真的完成数据库副作用，尤其是 commit_rule_import 是否真实打开 SQLite、调用 Rust store、在事务里替换规则并写 domain state。

重点文件：
- app/native_rule_runtime.py
- app/agent_toolkit/services/placeholder_rules.py
- app/agent_toolkit/services/rule_validation.py
- app/persistence/rule_records.py
- app/persistence/schema/current.sql
- rust/src/native_core/rule_runtime/api.rs
- rust/src/native_core/rule_runtime/store.rs
- rust/src/native_core/rule_runtime/model.rs
- tests/test_native_rule_runtime.py
- tests/test_rule_runtime_store.py

必须检查：
- commit_rule_import 的 db_path 是否真实使用。
- Rust store::replace_domain_rules 是否进入生产调用链。
- Python 是否先写库，Rust 后置返回 ok。
- prepare/commit 是否共享 plan_token 和同一生命周期。
- commit 失败是否可能留下半导入、半清理或误报成功。
- validate/import 是否存在 dry-run 和 write 行为混乱。

返回：副作用归属矩阵、事务边界、no-op commit 或空门面证据、半提交风险。
```

## Subagent C: Isolated New Code And No-Migration Risk

### Spawn Prompt

```text
执行轨道 C：无迁移与孤立新代码。

你的目标：找出新增 Rust/native/current model 代码是否只是孤立存在，没有进入生产主路径。

重点文件：
- rust/src/native_core/rule_runtime/
- rust/src/native_core/mod.rs
- rust/src/lib.rs
- app/native_rule_runtime.py
- app/agent_toolkit/services/
- app/persistence/
- app/rmmz/
- tests/

必须检查：
- 新 Rust 模块是否只有 Rust 单测调用。
- 新 PyO3 API 是否没有生产 service 调用。
- 新 schema 是否没有生产读写。
- 新 diagnostics/report 字段是否没有真实数据来源。
- 新错误码是否不会从真实 CLI 或 Agent service 触发。
- 文档或测试是否已经声称这些新能力生效。

返回：孤立新代码清单、未接入生产链路的位置、无迁移分类和严重程度。
```

## Subagent D: Half-Migration And Empty Facades

### Spawn Prompt

```text
执行轨道 D：半迁移与空门面。

你的目标：审查新 API 是否只做表面接入，核心行为仍在旧侧完成。

重点文件：
- app/native_rule_runtime.py
- app/agent_toolkit/services/placeholder_rules.py
- app/agent_toolkit/services/rule_validation.py
- app/persistence/rule_records.py
- app/rmmz/text_rules.py
- app/source_residual/
- rust/src/native_core/rule_runtime/api.rs
- rust/src/native_core/rule_runtime/store.rs
- rust/src/native_core/quality/
- tests/test_scan_budget.py

必须检查：
- 名为 commit/store/write/import/apply 的函数是否完成对应副作用。
- 是否存在 unused db_path、下划线参数、allow(dead_code)、只返回 report 的实现。
- Python 是否仍直接处理 capture、matcher、模板、规则命中、规则写库、规则影响分析或清理。
- Rust API 调用是否发生在旧侧真实副作用之后。
- TextRules 旧规则语义是否仍保留为可恢复实现。

返回：空门面清单、半迁移调用链、旧侧真实副作用证据、声明 owner 和真实 owner。
```

## Subagent E: Physical Deletion Of Old Code And Tests

### Spawn Prompt

```text
执行轨道 E：伪删除与旧代码旧测试残留。

你的目标：审查被替换对象是否物理删除，而不是只禁用、raise、allow(dead_code)、未调用或由 scan budget 禁止。

重点文件和搜索范围：
- app/
- rust/
- tests/
- pyproject.toml
- rust/Cargo.toml
- README.md
- CHANGELOG.md
- skills/
- docs/superpowers/specs/2026-06-11-pcre2-rule-runtime-design.md

必须检查：
- app/regex_contract.py、rust/src/native_core/regex_contract.rs、fancy-regex 是否完全删除。
- 旧 domain 规则表读写 API 是否物理删除，而不是换成旧 owner 写新表。
- TextRules 中旧 source residual/config regex 规则语义是否物理删除。
- tests、fixtures、stubs、mocks、scan budget、canary 是否仍保护旧实现。
- 当前源码、测试、README、Skill 或配置模板是否仍出现旧 dialect、旧字段、旧表、legacy/old/fallback/compat/deprecated。
- docs/records 或历史 plan 中的历史表述只作为线索，不作为问题本身。

返回：物理删除矩阵、仍保留对象是否属于当前生产契约、应删除或改写的旧测试和 fixture。
```

## Subagent F: Test Truthfulness And False-Success Guards

### Spawn Prompt

```text
执行轨道 F：测试真实性与防假成功。

你的目标：审查测试是否验证真实迁移，而不是只验证新门面能返回 success。

重点文件：
- tests/test_native_rule_runtime.py
- tests/test_rule_runtime_store.py
- tests/test_agent_toolkit_rule_import.py
- tests/test_scan_budget.py
- tests/test_text_rules.py
- tests/test_rmmz_mv_namebox.py
- tests/test_native_scope_index.py
- tests/agent_toolkit_contract_fixtures.py
- tests/rmmz_writeback_contract_fixtures.py
- rust/src/native_core/rule_runtime/

必须检查：
- native commit 测试是否验证 SQLite rules、rule_sets、rule_domain_states 真实变化。
- import 命令测试是否验证规则 store、domain state、备份和清理。
- validate dry-run 测试是否验证不写库。
- 是否只断言 ok/success/report 而不检查真实副作用。
- 当前测试示例是否仍使用旧正则写法 `(?P<name>...)`，而不是 PCRE2 推荐写法 `(?<name>...)`。
- 是否有 no-fallback 测试覆盖旧侧函数不能被生产调用。

返回：假成功测试清单、缺失的真实副作用断言、旧契约测试残留、需要改写的测试类型。
```

## Subagent G: Docs Skill And User Contract

### Spawn Prompt

```text
执行轨道 G：文档、Skill 与用户契约。

你的目标：审查用户可见契约是否与真实生产行为一致，且只描述当前 PCRE2 和统一规则模型契约。

重点文件：
- README.md
- CHANGELOG.md
- setting.example.toml
- docs/superpowers/specs/2026-06-10-pcre2-rule-runtime-requirements.md
- docs/superpowers/specs/2026-06-11-pcre2-rule-runtime-design.md
- docs/superpowers/specs/2026-06-11-half-migration-parallel-review-design.md
- skills/att-mz-protocol/
- skills/att-mz/
- skills/att-mz-release/
- tests/test_skill_protocol.py
- tests/test_release_notes.py

必须检查：
- README、Skill、配置示例和错误文案是否声称迁移完成。
- 当前示例是否仍保留 Python/Rust regex 交集写法或 `(?P<name>...)`。
- 用户可见报告是否可能把半迁移报告成完成。
- docs 是否倒置覆盖 Skill 或当前实现。
- 破坏性变化是否只描述当前要求，不解释旧路径。
- 文档示例是否脱敏。

返回：文档声明和真实行为对照、旧契约表述残留、用户可能被误导的位置、Skill canonical 源与生成目标一致性风险。
```

## Subagent H: Performance Concurrency And Diagnostics Ownership

### Spawn Prompt

```text
执行轨道 H：性能与并发真实路径。

你的目标：审查性能敏感逻辑是否真的迁移到 Rust/current owner，而不是只新增 Rust 包装或报告字段。

重点文件：
- app/agent_toolkit/services/placeholder_rules.py
- app/agent_toolkit/services/rule_validation.py
- app/persistence/rule_records.py
- app/rmmz/text_rules.py
- app/source_residual/
- rust/src/native_core/rule_runtime/
- rust/src/native_core/quality/
- rust/src/native_core/scope_index/
- tests/test_scan_budget.py
- docs/records/performance/
- docs/records/reviews/

必须检查：
- 大规模规则扫描、匹配、hash、stale 判断、质量检查、写回协议是否仍由 Python 串行完成。
- Rust 线程配置是否真实参与 rule runtime 或相关生产调度。
- diagnostics 中 rule_runtime 阶段耗时、thread_count、JIT 状态是否来自真实 Rust 阶段。
- scan budget 是否掩盖真实性能证据缺失。
- 是否存在重复全量扫描或 Python/Rust 双跑。

返回：性能敏感副作用归属、Python 串行重活残留、Rust 并发入口是否生产可达、真实 CLI 性能证据缺口。
```

## Main-Agent Consolidation Matrix

主代理汇总时必须建立以下矩阵。最终回复可以摘要，不必逐项贴满，但每个 P0/P1 必须能追到矩阵证据。

```text
Claim:
Claim source:
Claimed owner:
Real production path:
Real owner:
Real side effect:
Classification:
Severity:
Evidence:
```

分类只能使用：

- 已完成迁移
- 半迁移
- 无迁移
- 伪删除
- 空门面
- 假成功测试
- 需复核

## Final Output Format

最终回复必须按以下顺序输出：

```text
结论：PASS | FAIL | BLOCKED

是否使用子代理并发 review：是 | 否

使用的 base：

发现：
1. [P0/P1/P2/P3] 标题
   现象分类：
   证据：
   声明 owner：
   真实 owner：
   真实副作用：
   影响：

已确认没有问题的边界：

证据缺口：

未运行验证：

后续建议：
只允许写 review 后的处理方向，例如“需要修复后再复审”，不得写代码补丁。
```

结论规则：

- `PASS`：未发现 P0/P1；P2/P3 不影响迁移真实性。
- `FAIL`：发现 P0/P1，或发现关键迁移声明无法追到真实生产副作用。
- `BLOCKED`：base、关键文件、diff 或生产链路不可读，无法可靠判断。

## Optional Verification

本 review 默认不运行全量 `uv run pytest`。如主代理需要增强证据，只能选择不改变业务状态的命令：

```powershell
uv run basedpyright
uv run python scripts/generate_skill_protocol.py --check
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
uv run pytest tests/test_native_rule_runtime.py tests/test_rule_runtime_store.py -q
git diff --check
```

未运行的验证必须在最终输出中写明，不能写成通过。

## Success Criteria

本 review 完成时必须满足：

- A-H 八个轨道均已完成，或明确记录无法并发执行的原因。
- 每个 P0/P1 都写清声明 owner、真实 owner 和真实副作用。
- 半迁移、无迁移、伪删除、空门面和假成功测试没有被混成“旧代码残留”泛泛描述。
- PCRE2 规则运行时的 prepare/commit/store/report/fingerprint 真实状态被查清。
- 旧代码和旧测试是否物理删除有明确结论。
- 最终结论是 `PASS`、`FAIL` 或 `BLOCKED` 三选一。
- 没有修改仓库文件，除非用户事先明确要求落盘最终 review 报告。
