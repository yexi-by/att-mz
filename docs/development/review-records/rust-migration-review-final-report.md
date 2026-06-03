# Rust 迁移分支渐进式 Review 最终报告

## 结论

本报告汇总对当前工作区相对 `main` 的 Python 到 Rust 迁移重构 review 结果。Review 分为静态 review、性能与并发 review、测试工具链 review 和动态样本验证；过程中未修改业务代码。

总体判断：当前分支本机工具链检查通过，但仍不建议直接合入。主要阻断来自写入后当前运行文件审计退化、发布 CI 未纳入 Rust 交付红线、Rust native 边界 fail-fast 不完整、外部 JSON 错误分类不稳定，以及大规模游戏性能路径仍存在重复扫描和串行瓶颈。

## Review 范围

- 对照基线：`main` 分支。
- 当前分支状态：迁移内容主要位于未提交工作区差异。
- 静态范围：CLI、应用编排、Rust native core、PyO3 适配、写回/重建、文本协议、质量检查、测试和文档。
- 动态范围：`<样本根目录>` 下 MV/MZ 候选样本，只操作副本和临时 `ATT_MZ_HOME`。
- 性能补充来源：`large-game-performance-defect-report.md`。本报告对其中与本次 review 重复的结论做合并，对未重复结论单列补充。

## 合入判断

当前分支存在 P1 阻断项，不建议合入。建议至少先处理以下问题：

1. 恢复或重建写入后的当前运行文件审计，保证 `write-back`、`rebuild-active-runtime` 和报告字段语义一致。
2. 发布 CI 加入 Rust `fmt`、`clippy`、`test` 交付红线。
3. Rust native plan 对缺失 `allowed_translation_paths`、规则载荷和写入范围执行 fail-fast。
4. 修正 `add-game` 已有可信源快照时的 CLI JSON 错误分类。
5. 对大规模重复扫描、工作区验收和状态查询路径设定明确的性能修复方案和回归验证。

## P1 阻断项

### P1-1 写入后当前运行文件审计退化

当前实现中，`write-back`、`rebuild-active-runtime` 写入 planned files 后没有像 `main` 一样重新加载当前运行文件并执行 active runtime 审计。`post_write_audit_ms` 仍出现在 CLI JSON 摘要中，但值来自 Rust 计划阶段的 `active_runtime_audit`，实际是写入前检查，不是写入后验收。

影响：

- 功能退化：`main` 写入后会审计当前运行文件，新实现缺少同等验证。
- 外部契约误导：Agent 看到 `post_write_audit_ms` 会误以为写后验收完成。
- 诊断链风险：当前运行文件中的 JS 语法错误、坏控制符或漏翻可能在写入后不被即时拦截。

证据：

- 当前：`app/application/handler.py` 把 `plan.timings_ms["active_runtime_audit"]` 写入 `post_write_audit_ms`。
- 当前：`app/cli/reports.py` 输出 `post_write_audit_ms`。
- 当前：`rust/src/native_core/write_back_plan/mod.rs` 在生成计划前执行 `active_runtime_audit`。
- `main`：写入后执行 `load_active_runtime_game_data()` 和 `_assert_active_plugin_source_runtime_audit_passed()`。

### P1-2 Release CI 未执行 Rust 交付红线

当前 `.github/workflows/release.yml` 只执行 `uv run basedpyright` 和 `uv run pytest`，没有执行：

- `cargo fmt --manifest-path rust/Cargo.toml -- --check`
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml`

影响：

- 本机 Rust 检查通过不能成为发布门禁。
- Rust/PyO3 迁移后的 lint、格式和 native 单测可能绕过 release workflow。
- 与开发文档中 Rust/PyO3 改动必须执行 Rust 检查的要求不一致。

证据：

- `.github/workflows/release.yml`
- `docs/development/release-and-tests.md`

### P1-3 Rust native 写入范围边界不够 fail-fast

Rust native plan 支持按 `allowed_translation_paths` 限制可写译文范围；handler 当前会传入该字段，但 native 边界本身在缺失时会退到全部数据库译文。对于 PyO3/native 边界，这属于关键安全条件没有在底层自证。

影响：

- 一旦未来新增调用方漏传限制字段，native plan 可能把数据库中全部译文纳入写入范围。
- 迁移后底层边界没有完全做到 fail-fast。

建议：

- `write_back` / `rebuild_active_runtime` / `write_terminology` 等写文件模式中，native plan 必须要求显式写入范围。
- 对缺失、空值、非法路径分别给出业务错误。

### P1-4 `add-game` 已有可信源快照时 JSON 分类错误

动态样本 `<样本游戏>` 副本包含 `data_origin`，`add-game` 正确拒绝了非干净目录，但 JSON 输出 code 是 `unexpected_error`，而不是可恢复的业务错误。

影响：

- 外部 Agent 无法稳定区分“用户应换干净目录”的业务失败和未知异常。
- 与“有问题直接报错”不冲突，但错误分类不利于恢复路径。

证据：

- `app/rmmz/source_snapshot.py` 抛出 `FileExistsError`。
- `app/cli_main.py` 只把 `CliBusinessError` 和 `ApplicationBusinessError` 归类为 `business_error`。
- 动态验证中 `add-game` 返回 `unexpected_error`。

## P2 主要问题

### P2-1 旧 CLI 写入 gate 残留且测试仍依赖旧接口

`ensure_write_back_gate()` 和 `collect_write_back_gate_errors()` 仍在 `app/cli/runtime.py` 中保留，测试仍导入并断言旧 gate 逻辑；但真实 `write-back`、`rebuild-active-runtime`、`write-terminology` 命令已走 handler 内部 gate。

影响：

- 旧代码删除不到位。
- 测试给出旧 CLI gate 仍参与真实命令的错觉。
- 未来维护者可能修旧 gate 而真实路径不受影响。

证据：

- `app/cli/runtime.py`
- `app/cli/commands/write_back.py`
- `tests/test_cli_json_output.py`

### P2-2 `run-all` 写入 gate 测试是弱证明

`run-all` 写入阶段测试通过 monkeypatch `write_back_for_handler` 直接抛错，只证明 `run-all` 会调用该函数，不证明真实 handler gate、真实 quality gate 或 native plan 会阻断写入。

影响：

- 测试覆盖了调用形状，没有覆盖真实业务路径。
- CLI 外部契约仍有回归空间。

### P2-3 Rust plan 对结构化字段二次质检有覆盖风险

Rust 写回计划中的质量 gate 会把插件配置、事件指令参数、Note 标签等结构化字段折叠为 `structured_field` 参与扫描。该做法可能跳过 Python 侧按单字段规则执行的结构检查和字面量换行计数检查。

影响：

- 插件 JSON 字符串容器、事件参数、Note 标签外壳可能出现结构破坏但未被同等拦截。
- 对 `main` 的文本协议等价性不足。

### P2-4 插件源码 runtime 映射缺少最终 AST 验证

`main` 在保存插件源码 runtime mapping 前，会检查 selector 能在最终 AST 中找到，并且最终 raw text 与写入文本一致。当前 Rust plan 生成 runtime map 后，Python 侧直接保存计划返回的映射。

影响：

- 诊断映射可能记录未真实落在当前运行 AST 的 selector。
- 后续 `diagnose-active-runtime` 可能基于不可靠映射反推。

### P2-5 写入差异生成仍有全集读写成本

Rust plan 会生成输出并与当前文件比较，写回/术语写回路径仍可能序列化大对象、读取当前文件并比较全集内容。插件源码 origin 集合也会参与输出 diff，即使本轮没有插件源码译文。

影响：

- 大项目写回路径存在不必要 I/O 和内存成本。
- 未完全兑现 Rust 迁移应减少热路径重复动作的目标。

### P2-6 Python 与 Rust 双重质量门禁

写文件命令先在 Python `_prepare_write_operation()` 中构建文本范围、执行流程 gate 和写入前质量检查，随后 Rust plan 再读取输入、执行当前运行审计和质量 gate。

影响：

- 大样本 `rebuild-active-runtime` CLI 日志显示总耗时 97.96s，其中 Rust plan 19.090s，其余主要消耗在 Python 前置重复检查。
- 进度条在 Rust plan 返回前缺少真实阶段。

去重说明：

- 本问题与 `large-game-performance-defect-report.md` 的“写文件命令存在 Python 与 Rust 双重质量门禁”重复，已合并为本 finding。

### P2-7 测试缺少真实 CLI/handler/native 闭环

Rust 单测覆盖了 native plan 的多类输入输出，Python 测试覆盖了 handler 对伪 plan 的应用，但缺少“真实 CLI 或 handler 调用真实 Rust plan，再事务写入，再输出 JSON”的闭环测试。

影响：

- 适配层、真实 native 输出、写文件事务和 JSON 报告之间仍可能出现集成偏差。

### P2-8 `write-back` JSON 摘要缺少测试

`build_write_back_summary_report()` 没有专门测试断言字段语义，尤其是 `post_write_audit_ms`。测试没有固定写后审计字段应来自哪个阶段。

影响：

- 第 P1-1 类契约误导不容易被测试发现。

### P2-9 性能与并发缺少自动验收

当前 Rust 有 `ATT_MZ_RUST_THREADS` 解析测试和非法值测试，但缺少真实热路径线程配置生效、批处理粒度、重复扫描次数或耗时阈值的自动验收。

影响：

- Rust 多线程是否贯穿热路径只能靠人工 review 和 profile。
- 后续性能回归没有稳定门禁。

### P2-10 大规模插件源码 AST 重复解析且 Python 外层串行

`large-game-performance-defect-report.md` 显示，插件源码扫描使用 Python 按文件循环调用 Rust 单文件 AST 入口。大样本单轮扫描 176 个 JS 文件约 29 到 30 秒；`quality-report` 调用 450 次 JS AST 解析；`validate-agent-workspace` 调用 1330 次。

影响：

- 迁移到 Rust 后，AST 解析能力存在，但批量并发没有贯彻到 Python 外层调度。
- 质量报告、覆盖审计、工作区准备、工作区验收、写入前检查都会被重复扫描放大。

建议：

- 新增 Rust 批量 JS AST 扫描入口。
- 用 Rayon 对多个插件源码文件并发解析。
- 命令级上下文复用同一轮扫描结果。

去重说明：

- 本问题与本次 review 的“插件源码扫描不复用”和“多线程未贯彻到底”重复，性能报告提供了更强的 profile 数据，因此在此升级为主要性能 finding。

### P2-11 工作区验收重复调用全量校验器

性能报告显示，`validate-agent-workspace` 自身先加载游戏数据、构建文本范围和插件源码扫描，随后又调用多个独立校验入口，导致插件源码、Note 标签、占位符候选反复扫描。该命令 profile 总耗时 291.923s。

影响：

- Agent 关键验收命令可能长时间无反馈。
- 重复调用独立校验器违背“无关性能损耗应避免”的 review 要求。

建议：

- 增加命令级上下文对象，统一携带 `GameData`、`TextRules`、`translation_data_map`、`PluginSourceScan`、Note 标签来源、事件命中和占位符候选。
- 校验器保留独立 CLI 能力，同时支持复用已构建上下文。

### P2-12 文本范围构建默认执行写回探针

性能报告显示，`TextScopeService.build()` 默认 `include_write_probe=True`。覆盖审计、手动修复表导出、质量报告等只读命令会执行写回可行性探针，并触发插件源码严格 AST 扫描。

影响：

- 只读命令承担写文件前成本。
- `audit-coverage` 写回探针 23.753s。
- `export-pending-translations` 即使 pending 为 0，仍执行完整文本范围和写回探针，profile 143.443s。

建议：

- 拆分文本范围模式。
- 只有需要 `can_write_back` 或真正写文件前才启用写回探针。

### P2-13 状态查询不是轻量查询

性能报告显示，`translation-status` 为计算 pending 数量会构建完整文本范围并扫描插件源码。大样本 profile 35.507s，执行 176 次 JS AST 解析。

影响：

- 状态查询变成重型扫描命令。
- 外部 Agent 频繁查询状态时会放大性能问题。

建议：

- 默认走数据库快速路径。
- 需要刷新当前规则范围时提供显式参数。

### P2-14 当前运行审计缺少可复用扫描结果

性能报告显示，`audit-active-runtime` 与 `diagnose-active-runtime` 都完整扫描当前运行插件源码；诊断反推本身约 0.011s，但仍要承担约 24s 的当前运行审计成本。

影响：

- 当前运行审计和诊断重复消耗。
- 试玩反馈循环中会放大等待时间。

建议：

- 按文件哈希复用当前运行插件源码审计结果。
- 诊断命令复用审计结果和运行映射索引。

### P2-15 原生 Note 标签扫描重复执行

性能报告显示，`prepare-agent-workspace` 中 Note 标签扫描 3 次，约 7.070s；`validate-agent-workspace` 中 14 次，约 32.680s。

影响：

- Rust 原生扫描本身已存在，但调用入口重复。
- 工作区流程性能被重复调用放大。

### P2-16 Python JSON 边界和深拷贝成本被放大

性能报告显示，Rust 结果通过 JSON 文本返回 Python 后，Python 执行 `coerce_json_value`、结构收窄和 `deepcopy`。在 `validate-agent-workspace` 中，`coerce_json_value` 约 11.673s，`deepcopy` 约 27.349s。

影响：

- 跨语言 JSON 大对象传输次数过多。
- 大型扫描结果和规则校验对象被重复复制。

建议：

- 对只需要摘要的命令返回轻量结构。
- 减少完整扫描对象跨语言往返。
- 避免对完整 `GameData` 或大型扫描结果做无意义深拷贝。

### P2-17 长任务进度缺少真实阶段

性能报告显示，`rebuild-active-runtime` 在长时间处理时没有准确说明正在执行写入前检查还是 Rust 写回计划；`validate-agent-workspace` 也存在长时间无阶段进度。

影响：

- 用户和外部 Agent 无法区分 CPU 密集处理、文件 I/O、数据库等待或卡死。
- 性能回归难以定位。

建议：

- 为写文件、工作区验收、手动修复表导出、状态查询等命令增加阶段状态和分段计时。

## P3 次要问题

### P3-1 `TextPlanRules` 对缺失布局字段使用默认值

部分文本布局字段缺失时会被默认化。迁移后的 fail-fast 边界不够强，可能隐藏配置缺失。

### P3-2 事件命令排序解析失败默认为 0

事件指令排序解析中非法值会落到 0，而 `main` 的 `int()` 行为会失败。该行为可能改变异常暴露方式。

### P3-3 启用插件缺失名称时生成 `unnamed_plugin_{index}.js`

启用插件缺失名称时使用 fallback 文件名，可能掩盖插件配置异常。

### P3-4 缺失译文行仍存在空字符串兜底

写入协议预检对缺失 translation lines 有空字符串兜底痕迹，属于继承问题，不应继续扩大。

### P3-5 `rebuild-active-runtime` 部分测试只验证 helper

现有测试证明入口调用了 helper，但对完整 rebuild 语义和 native mode 差异证明不足。

### P3-6 文档/注释仍有历史叙事残留

`app/plugin_source_text/models.py` 中 `candidates_json()` docstring 写有“兼容旧扫描命令”。该问题继承自 `main`，不是迁移新增退化，但不符合当前文档规范。

### P3-7 性能脚本包含本机样本路径默认值

`scripts/benchmark_rebuild_active_runtime.py` 默认样本路径写死 `<样本根目录>\...`。这不适合作为长期仓库脚本默认值，也和示例脱敏、配置分离要求冲突。

## 正向证据

### 工具链命令

以下命令已在本机执行并通过：

| 命令 | 结果 |
| --- | --- |
| `uv run basedpyright` | 0 errors, 0 warnings |
| `uv run pytest` | 462 passed |
| `cargo fmt --manifest-path rust/Cargo.toml -- --check` | 通过 |
| `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` | 通过 |
| `cargo test --manifest-path rust/Cargo.toml` | 38 passed |

### 动态样本验证

动态验证只操作副本和临时 `ATT_MZ_HOME`，未调用模型。

#### 样本筛选

- `<样本根目录>` 顶层目录本身不是游戏根。
- `<未筛选样本目录>` 一层扫描未发现标准 MV/MZ 根目录。
- `<候选样本目录>` 中发现多个 MV/MZ 候选。

#### `<样本游戏>`

- 副本规模：1032 文件，438.87 MB。
- `add-game` 被已有 `data_origin` 阻断。
- 阻断正确，但 JSON code 为 `unexpected_error`，形成 P1-4。
- 原始样本 `js/plugins.js` SHA-256 前后不变。
- 临时工作目录已删除。

#### `<样本游戏>`

- 副本规模：829 文件，501.47 MB。
- `add-game` 成功，游戏标题 `<样本游戏>`。
- `ATT_MZ_RUST_THREADS=4`。
- 动态命令结果：

| 命令 | 退出码 | 结果 | 耗时 |
| --- | ---: | --- | ---: |
| `translation-status` | 0 | warning `translation_run_missing` | 1241ms |
| `scan-placeholder-candidates` | 0 | 55 candidates，1 uncovered | 5654ms |
| `scan-plugin-source-text` | 0 | 94 candidates，扫描 55 文件，忽略 35 文件，high_risk=false | 4024ms |
| `text-scope` | 0 | 12577 条，全部 writable | 7110ms |
| `audit-coverage` | 1 | `coverage_missing_translation`，pending 12577 | 5470ms |
| `quality-report` | 1 | 缺译文、术语、插件/事件/Note 规则、占位符规则 fail-fast | 9063ms |
| `write-back` | 1 | `business_error`，规则缺失阻断 | 9206ms |
| `rebuild-active-runtime` | 1 | `business_error`，规则缺失阻断 | 9242ms |

副本 `plugins.js` 和 `System.json` 在写入命令前后哈希不变。原始样本 `js/plugins.js` SHA-256 前后不变。临时工作目录已删除。

## 未验证范围

- 未执行真实模型翻译，避免消耗模型额度。
- 未在规则齐备、译文齐备的外部样本上验证成功写入后的完整审计链。
- 未对大规模样本执行可重复性能基准并设置阈值。
- 未以 Skill 文件正文作为开发 review 依据；普通源码 review 按项目开发规范，不读取 Skill 作为实现说明。
- 未验证 GitHub Actions 实际发布工作流运行结果，只审查当前 workflow 文件。

## 去重后的性能补充

`large-game-performance-defect-report.md` 中以下内容已经和本次 review 结论合并：

- 写文件命令 Python 与 Rust 双重质量门禁。
- 插件源码 AST 重复扫描和未批量并发。
- 长任务缺少真实阶段进度。

以下内容是本次最终报告中新补入的非重复性能结论：

- `validate-agent-workspace` 重复调用全量校验器，profile 291.923s。
- `TextScopeService.build()` 默认执行写回探针，导致只读命令承担写入前成本。
- `translation-status` 不是轻量查询，状态查询会构建完整文本范围。
- `audit-active-runtime` 与 `diagnose-active-runtime` 缺少当前运行扫描结果复用。
- Note 标签原生扫描在工作区准备和验收中重复执行。
- Python JSON 边界和 `deepcopy` 成本在大对象校验中被放大。

## 建议修复顺序

1. 修复写入后当前运行文件审计和 `post_write_audit_ms` 契约。
2. 把 Rust `fmt`、`clippy`、`test` 加入 release workflow。
3. 让 Rust write plan 对写入范围、规则载荷和关键配置缺失 fail-fast。
4. 清理旧 CLI gate 或重命名为测试专用/内部 helper，并补真实 CLI gate 测试。
5. 修复 `add-game` 已有可信源快照的 JSON 错误分类。
6. 建立命令级上下文，复用 `GameData`、文本范围、插件源码扫描、Note 来源和占位符候选。
7. 新增 Rust 批量 JS AST 扫描入口，并用 Rayon 并发处理插件源码文件。
8. 拆分 `TextScopeService.build()` 模式，默认只读路径不执行写回探针。
9. 为状态查询、工作区验收、写文件命令增加轻量路径、阶段进度和性能回归指标。
10. 补真实 CLI/handler/native plan 闭环测试和写回 JSON 摘要契约测试。
