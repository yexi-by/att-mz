# Rust Scope/Index Engine 性能改造计划

状态：执行计划
日期：2026-06-03
范围：本计划限定 Rust Scope/Index Engine 性能改造，不包含完整 Rust CLI 重写。

## 结论

本计划目标是把当前性能缺陷相关的重型扫描、文本范围构建、候选筛选、质量统计和覆盖统计收口到 Rust + SQLite 快路径。Python 保留 CLI 编排、配置读取、模型调用、报告组装和数据库事务编排职责，不再承担大规模文本扫描和筛选职责。

性能验收以逐命令改造前后对比为准。P0/P1 命令必须显著降低耗时，并消除不合理复杂度、重复全量扫描、`limit` 后置和 O(N^2) Python 筛选。90% 降幅作为排查阈值：未达到时必须说明剩余耗时来自磁盘 I/O、报告输出、SQLite 写入、AST 解析或其他必要成本。

## 已确认的问题

在 `Summer Stolen v0.2` 上已经确认：

- `export-pending-translations --limit 20` 超过 600 秒仍未完成。
- `translation-status --refresh-scope` 在索引缺失后重建文本索引约 63 秒，其中构建文本范围约 52 秒。
- `doctor --game ... --no-check-llm` 约 66 秒。
- `audit-coverage` 约 59 秒。
- `text-scope` 约 63 秒，输出约 43MB。
- `quality-report` 约 13 秒。
- `scan-plugin-source-text` 约 4 秒。
- `scan-nonstandard-data` 约 3 秒。

已有验证表明，根因不是 SQLite 本身。直接从 text index 查询 pending 的耗时低于 0.1 秒，瓶颈在 Python 侧：

- `app/agent_toolkit/services/manual_translation.py` 构建完整 `TextScopeService` 后再筛选 pending，`limit` 在全量筛选后才应用。
- `app/text_scope/models.py` 的 `writable_paths` 每次访问都会重新遍历全部 entries，导致大样本下接近 O(N^2)。
- 多个 CLI 命令会重复加载 `GameData`、重复构建 `TextScopeService`、重复扫描插件源码或非标准 data。

## 非目标

- 不做完整 Rust CLI 重写。
- 不删除 Python CLI 外壳。
- 不迁移模型调用、OpenAI SDK 调用、prompt 组装和翻译 worker。
- 不重写发行版构建流程。
- 不为旧数据库做静默兼容转换；旧 schema 或旧索引不符合当前契约时显式失败或要求重建。
- 不为了追求 90% 数字牺牲外部契约、错误可解释性和测试可维护性。

## P0 / P1 范围

### P0

P0 是本次性能缺陷的直接修复对象。

- `export-pending-translations --limit N`

要求：

- `limit` 必须在 SQLite 或 Rust 层提前生效。
- 不能为了导出前 N 条 pending 构建完整 Python `TextScopeService`。
- 有效 text index 可用时目标返回时间小于 3 秒。
- text index 缺失或失效时允许触发一次 Rust 索引重建，但不能进入 O(N^2) Python 筛选。

### P1-A 核心慢链路

这些命令直接参与翻译、范围索引、质量报告、覆盖审计或写回，必须作为核心验收命令：

- `rebuild-text-index`
- `translation-status --refresh-scope`
- `text-scope`
- `audit-coverage`
- `quality-report`
- `export-quality-fix-template`
- `import-manual-translations`
- `reset-translations`
- `translate`
- `run-all`
- `write-back`
- `rebuild-active-runtime`
- `write-terminology`

要求：

- 对每个命令记录改造前和改造后耗时。
- 不允许重复构建文本范围，除非报告说明不可复用原因。
- `translate --max-items N` 的前置门禁不能再构建完整 Python scope 后才读取 indexed pending。
- 写回相关命令的前置检查、质量 gate 和可写路径过滤要复用同一个 Rust/SQLite 范围事实。

### P1-B 规则、候选和工作区命令

这些命令不一定全部实测慢，但静态调用链会触发全量扫描、AST 扫描、非标准 data 扫描、text index 或规则覆盖检查，必须纳入本次审计：

- `prepare-agent-workspace`
- `validate-agent-workspace`
- `scan-plugin-source-text`
- `export-plugin-source-ast-map`
- `scan-nonstandard-data`
- `export-nonstandard-data-json`
- `validate-nonstandard-data-rules`
- `import-nonstandard-data-rules`
- `scan-placeholder-candidates`
- `validate-placeholder-rules`
- `build-placeholder-rules`
- `import-placeholder-rules`
- `validate-structured-placeholder-rules`
- `scan-structured-placeholder-candidates`
- `import-structured-placeholder-rules`
- `export-note-tag-candidates`
- `validate-note-tag-rules`
- `import-note-tag-rules`
- `export-event-commands-json`
- `validate-event-command-rules`
- `import-event-command-rules`
- `validate-plugin-rules`
- `import-plugin-rules`
- `validate-plugin-source-rules`
- `import-plugin-source-rules`
- `export-mv-virtual-namebox-candidates`
- `validate-mv-virtual-namebox-rules`
- `import-mv-virtual-namebox-rules`
- `validate-source-residual-rules`
- `import-source-residual-rules`

要求：

- 命令可以共享 Rust Scope/Index Engine、插件源码扫描、非标准 data 扫描或 SQLite 快路径。
- 不是每个命令都必须单独重写，但每个命令都必须被静态审计并标注处理结论。
- 如果命令仍保留 Python 路径，必须说明规模边界和不迁移原因。

### P1-C 静态审计但排序靠后

这些命令需要纳入审计表，但不作为第一批实现入口：

- `audit-active-runtime`
- `diagnose-active-runtime`
- `verify-feedback-text`
- `export-terminology`
- `import-terminology`
- `probe-source-language`
- `export-plugins-json`

要求：

- 它们是否受益于 Rust Scope/Index Engine 要明确记录。
- 如果瓶颈来自真实运行文件审计、术语上下文生成或输出文件大小，不得归因为 scope/index 问题。

### 暂不纳入 P1

这些命令不是本次 Scope/Index 性能缺陷主链路：

- `list`
- `add-game`
- `reset-game`
- `cleanup-agent-workspace`
- `restore-font`

## 目标架构

### 单一事实来源

建立一个 Rust Scope/Index Engine，统一负责：

- 扫描 RPG Maker 标准 data JSON。
- 扫描插件参数。
- 扫描事件指令参数。
- 扫描 Note 标签。
- 扫描 MV 虚拟名字框候选。
- 扫描插件源码 AST 候选。
- 扫描非标准 data 文件候选。
- 判断文本是否进入正文翻译。
- 判断文本是否可写回。
- 生成稳定 `location_path`。
- 生成 text index 写入记录。
- 生成候选覆盖和规则命中统计所需的中间索引。

Python 不再并行维护大规模文本范围事实。Python 可以把 Rust 结果转换成现有 JSON 报告，但不能重新全量扫描做重复验证。

### SQLite 快路径

`text_index_items` 是索引有效状态下的主要查询入口。以下查询必须从数据库或 Rust 层提前筛选：

- pending count
- pending list with limit
- translated count
- quality error count
- writable count
- unwritable count
- rule/domain coverage count
- requested paths validation
- reset/import path membership validation

除非命令的外部契约要求输出完整清单，否则禁止在 Python 中读取全量记录后再做大规模筛选。

本计划需要新增 summary 表，而不是只复用 `text_index_items`。最低限度新增：

- `text_index_scope_summary`：保存当前索引的总量、可翻译量、可写量、不可写量、规则过期量、扫描耗时摘要和 Rust 原生线程数。
- `text_index_domain_summary`：按 domain 保存 item 数、active 数、writable 数、unwritable 数、inactive rule hit 数。
- `text_index_rule_hit_summary`：按规则 domain 和稳定 rule key 保存 hit 数、extractable 数、writable 数、unwritable 数。

动态统计，例如 pending、translated、quality error，继续通过 `text_index_items` 与译文/错误表查询得出，不写进静态 summary，避免第二事实来源。

### Rust 线程配置

新增全局配置：

```toml
[runtime]
rust_threads = "auto"
```

语义：

- `"auto"`：Rust 使用自动线程数。
- 正整数：Rust 使用指定线程数。
- 不接受 `0`、负数、空字符串或无法解析的文本。

实现要求：

- `setting.toml` 是唯一入口。
- `setting.example.toml` 必须声明默认值。
- `app/config/schemas.py` 增加严格配置模型，完成 pydantic 校验。
- Python 调用 Rust 时必须显式传入线程配置。
- Rust 侧删除 `ATT_MZ_RUST_THREADS` 读取逻辑。
- 测试和 benchmark 脚本不得再设置或断言 `ATT_MZ_RUST_THREADS`。
- `native_thread_count` 的报告值要来自本次配置，而不是环境变量。

### 已决策实现选择

本节把关键设计点定案，执行时按这里的边界推进。

#### Rust API 入口

不采用单一大型 JSON 入口，也不为每个 CLI 单独开 Rust 原生 API。采用三个稳定入口族：

1. `build_scope_index`
   - 唯一允许做完整翻译源扫描的入口。
   - 输出 text index rows、scope summary、domain summary、rule hit summary、candidate summary、unwritable reasons、过期规则明细。
   - 用于 `rebuild-text-index`、索引缺失或失效后的 rebuild、`text-scope` 完整清单和 P1-A/P1-B 的共享范围事实。

2. `scan_rule_candidates`
   - 使用和 `build_scope_index` 相同的 Rust 扫描器，但只返回某些规则支线需要的候选报告。
   - 用于插件源码、非标准 data、占位符、结构化占位符、Note、事件、插件规则、MV 虚拟名字框等 P1-B 命令。
   - 命令内已有 `build_scope_index` 结果时必须复用该结果，不允许再扫一遍。

3. `evaluate_scope_gate`
   - 消费 scope/index rows、已保存译文和规则摘要，返回工作流门禁、质量门禁、可写路径和写回前置检查需要的 compact summary。
   - 用于 `translate --max-items`、`quality-report`、`write-back`、`rebuild-active-runtime`、`write-terminology`。

pending 查询不做 Rust API。有效 text index 下由 Python persistence 层直接执行 SQLite 查询，例如 `read_pending_text_index_items(limit=N)`。这是数据库快路径，不是 Python 全量扫描。

#### Schema 决策

schema 必须升级，计划按当前 schema 之后新增一版。实现时如果当前 schema 号已变化，使用“当前最新 + 1”，但迁移内容必须包含 scope summary、domain summary、rule hit summary 三类能力。

summary 表只保存由当前文本范围和规则决定的静态事实。译文状态、pending 状态、质量错误状态仍通过查询实时计算。

#### P1-B 策略

P1-B 不采用 Python 共享扫描缓存作为过渡方案。交付时，P1-B 涉及的大规模文本、候选、AST、非标准 data 扫描必须由 Rust 执行。

允许 Python 保留：

- CLI 参数解析。
- JSON 报告渲染。
- 工作区文件写出。
- 小规模输入文件解析。
- 数据库事务编排。

不允许 Python 保留：

- 全量文本范围扫描。
- 插件源码 AST 扫描。
- 非标准 data 文本候选扫描。
- 大规模占位符覆盖扫描。
- 规则命中全量统计。
- 为了校验而重复构建一份当前文本范围。

执行者可以按实际代码结构调整模块名、结构体名和局部拆分，但不能改变上述入口族、summary 表能力和 P1-B Rust 迁移边界。

## 主要改造步骤

### 1. 建立性能基线和扫描预算表

目标：固化 P0/P1 命令的重型扫描次数和实测耗时。

涉及文件：

- `tests/scan_budget_contract.py`
- `tests/test_scan_budget.py`
- `scripts/benchmark_small_tasks.py`
- `scripts/benchmark_rebuild_active_runtime.py`
- `scripts/benchmark_active_runtime_audit.py`
- 新增或更新一份性能基线记录文档。

任务：

- 把 P0/P1 命令全部纳入扫描预算表。
- 标注每个命令允许的 `GameData` 加载、scope 构建、候选扫描、AST 扫描、quality gate 和 write plan 次数。
- benchmark 脚本移除 `--rust-threads` 通过环境变量传递的设计，改为生成临时 `setting.toml`。
- 记录 `Summer Stolen v0.2` before 数据。

### 2. 配置收口

涉及文件：

- `setting.example.toml`
- `app/config/schemas.py`
- `app/config/overrides.py`
- `app/cli/runtime.py`
- `app/native_quality.py`
- `rust/src/native_core/pool.rs`
- `rust/src/lib.rs`
- `tests/test_config_overrides.py`
- `tests/test_native_adapters.py`
- benchmark 相关测试。

任务：

- 新增 `RuntimeSetting`，字段 `rust_threads: Literal["auto"] | PositiveInt` 或等价 pydantic 校验。
- 删除 `ATT_MZ_RUST_THREADS` 的生产读取。
- Rust 暴露统一线程配置入口，例如 `configure_runtime_threads` 或在每个重型 Rust 原生 API 入参中传递线程数。
- 所有 Rust 并行入口使用同一个池配置函数。
- 修改错误文案，不再出现 `ATT_MZ_RUST_THREADS`。

### 3. Rust Scope/Index Engine 核心

建议新增 Rust 模块：

- `rust/src/native_core/scope_index/mod.rs`
- `rust/src/native_core/scope_index/models.rs`
- `rust/src/native_core/scope_index/data_scan.rs`
- `rust/src/native_core/scope_index/plugin_config.rs`
- `rust/src/native_core/scope_index/plugin_source.rs`
- `rust/src/native_core/scope_index/nonstandard_data.rs`
- `rust/src/native_core/scope_index/placeholders.rs`

Python 桥接：

- `app/native_scope_index.py`
- `app/text_index.py`
- `app/text_scope/builder.py`
- `app/text_scope/models.py`

任务：

- Rust 输入使用结构化 payload，不做路径硬编码。
- Rust 输出包含 text index rows、domain summary、rule hit summary、unwritable reasons、过期规则明细和可写路径集合。
- Rust API 按 `build_scope_index`、`scan_rule_candidates`、`evaluate_scope_gate` 三个入口族实现。
- SQLite schema 增加 scope/domain/rule hit summary 能力，迁移版本使用“当前最新 + 1”。
- Python `TextScopeService` 逐步收敛为薄适配层，优先消费 Rust 结果。
- 修掉 `writable_paths` 重复构建问题，即使过渡期保留 Python model，也必须缓存或直接使用 Rust 输出集合。

### 4. P0 快路径

涉及文件：

- `app/agent_toolkit/services/manual_translation.py`
- `app/persistence/text_index_records.py`
- `app/persistence/repository.py`
- `tests/test_agent_toolkit_manual_import.py`
- `tests/test_manual_translation_scope.py`

任务：

- `export-pending-translations --limit N` 先检查 text index。
- 有效 index 可用时直接 `read_pending_text_index_items(limit=N)`。
- text index 缺失或失效时触发一次 Rust rebuild，再走数据库 limit 查询。
- `include-write-probe` 如需要完整写回探针，必须由 Rust scope/index 或 write plan 一次性给出，不允许 Python 全量二次筛选。
- 增加测试证明 `limit` 不会构建全量 pending list。

### 5. P1-A 核心命令迁移

涉及文件：

- `app/agent_toolkit/services/text_index.py`
- `app/agent_toolkit/services/coverage.py`
- `app/agent_toolkit/services/quality.py`
- `app/agent_toolkit/services/manual_translation.py`
- `app/application/handler.py`
- `app/application/write_back_gate.py`
- `app/text_index.py`
- `app/text_scope/*`
- `tests/test_text_index.py`
- `tests/test_agent_toolkit_coverage.py`
- `tests/test_agent_toolkit_quality_report.py`
- `tests/test_agent_toolkit_translation_limits.py`
- `tests/test_write_back_transactions.py`

任务：

- `rebuild-text-index` 改为 Rust 构建 scope/index rows。
- `translation-status --refresh-scope` 只在索引缺失或失效时重建，统计走 SQLite。
- `text-scope` 输出完整清单时可以读取全量，但清单来源必须是 Rust/index，不重新 Python 扫。
- `audit-coverage` 使用 index/domain summary。
- `quality-report` 在索引有效时避免读取全量 index 后再由 Python 大规模筛选；质量明细需要 Rust 原生质量检查时，按当前已保存译文子集处理。
- `translate --max-items` 前置 gate 改用 index metadata 和 Rust gate summary，不构建完整 Python scope。
- `write-back`、`rebuild-active-runtime`、`write-terminology` 的可写路径和质量 gate 复用 Rust 范围事实。

### 6. P1-B 工作区和规则命令迁移

涉及文件：

- `app/agent_toolkit/services/workspace.py`
- `app/agent_toolkit/services/rule_validation.py`
- `app/agent_toolkit/services/placeholder_rules.py`
- `app/agent_toolkit/services/nonstandard_data.py`
- `app/plugin_source_text/*`
- `app/nonstandard_data/*`
- `app/event_command_text/*`
- `app/note_tag_text/*`
- `tests/test_agent_toolkit_workspace.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_agent_toolkit_diagnostics.py`
- `tests/test_nonstandard_data.py`
- `tests/test_plugin_source_text.py`

任务：

- `prepare-agent-workspace` 一次加载和扫描，所有输出复用同一 Rust scope/index/candidate result。
- `validate-agent-workspace` 消费 manifest，并复用一次候选扫描结果。
- 插件源码 AST 扫描迁到 Rust 统一入口，Python 只渲染风险报告和规则文件。
- 非标准 data 扫描迁到 Rust 统一入口，Python 只渲染风险报告、导出工作区和执行数据库事务。
- 占位符、结构化占位符、Note、事件、插件规则校验全部优先消费 Rust/index 结果。

### 7. P1-C 审计命令处理

涉及文件：

- `app/agent_toolkit/services/quality.py`
- `app/agent_toolkit/services/feedback.py`
- `app/application/handler.py`
- `app/source_language_probe.py`
- `app/terminology/*`

任务：

- 标注每个命令是否受 Rust Scope/Index Engine 影响。
- 对真实 active runtime 审计、术语上下文生成、源语言探测等命令，区分真实 I/O/输出成本和 scope/index 成本。
- 仅迁移共享热点；不为边缘命令新增独立复杂抽象。

### 8. 删除环境变量契约

涉及文件：

- `rust/src/native_core/pool.rs`
- `rust/src/native_core/javascript_ast.rs`
- `rust/src/native_core/write_back_plan/test_support.rs`
- `tests/test_benchmark_small_tasks.py`
- `tests/test_benchmark_active_runtime_audit.py`
- `tests/test_benchmark_rebuild_active_runtime.py`
- `docs/development/native-core.md`
- `README.md`
- `skills/att-mz*/references/cli-command-contract.md` 中涉及相关文案的部分。

任务：

- 删除 `ATT_MZ_RUST_THREADS` 文案、测试、benchmark env 注入和 Rust 读取。
- 测试改为 `setting.toml` 或直接 Rust 原生 API 参数。
- 文档只描述 `[runtime].rust_threads`。

## 验收标准

### 行为标准

- P0/P1 命令外部 JSON schema、退出码和主要错误文案保持当前契约，除非计划中明确记录破坏性变更。
- 旧索引、错配规则和无法重建的状态必须显式报错。
- `limit`、`--max-items` 等限制参数必须在数据库或 Rust 层真实参与调度。
- 不允许吞异常、伪造成功或静默降级到旧 Python 全量慢路径。

### 性能标准

- 每个 P0/P1-A 命令必须提供改造前和改造后耗时表。
- P0 必须从超时或长时间无可用结果改为 3 秒内可用。
- P1-A 必须大幅下降；未达到 90% 时要给出剩余耗时归因。
- P1-B 完成静态审计，并把大规模文本、候选、AST、非标准 data 扫描迁到 Rust；有实测条件的命令补充改造前后耗时对比。

### 测试标准

必须执行：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

新增或更新测试：

- 配置链路：`[runtime].rust_threads` 定义、解析、校验、应用、报告。
- 环境变量删除：`ATT_MZ_RUST_THREADS` 不再影响线程数。
- P0：`export-pending-translations --limit N` 不构建全量 pending list。
- 扫描预算：P0/P1 命令不会重复构建 scope 或重复扫描候选。
- Rust scope/index：大样本索引构建、路径稳定性、可写路径、规则命中和错误路径。
- SQLite 快路径：pending count/list、path membership、coverage summary。
- schema 迁移：scope summary、domain summary、rule hit summary 写入和读取。
- 工作区命令：prepare/validate 复用一次候选扫描。

## 风险

- Rust Scope/Index Engine 输出结构会成为新的核心契约，必须用测试固定 path 稳定性。
- `text-scope` 这类完整报告命令仍可能受 43MB 输出成本限制，不能把输出 I/O 误判成扫描性能退化。
- 插件源码 AST 和非标准 data 扫描迁移到 Rust 后，需要保持现有风险分类和报告字段。
- 当前工作区存在大量未提交变更，正式实现前必须确认变更归属，避免误改无关文件。

## 实施顺序

1. 完成配置收口并删除 `ATT_MZ_RUST_THREADS`，因为这是所有 Rust 并行路径的共同入口。
2. 完成 P0 pending 导出快路径，修复 P0 性能缺陷。
3. 实现 Rust Scope/Index Engine 最小闭环：标准 data、插件参数、事件、Note、可写路径、text index rows。
4. 接入 `rebuild-text-index`、`translation-status --refresh-scope`、`translate --max-items`。
5. 接入 `quality-report`、`audit-coverage`、`text-scope`。
6. 接入写回前置检查和 write plan 复用。
7. 接入工作区和规则命令。
8. 执行完整验证，并生成 `Summer Stolen v0.2` 改造前后性能表。
