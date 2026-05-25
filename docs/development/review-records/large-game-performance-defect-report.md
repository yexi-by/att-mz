# 大规模游戏性能缺陷报告

## 范围

本报告检查大规模 RPG Maker MV 游戏在当前实现中的 CPU 密集路径。样本规模如下：

| 指标 | 数量 |
| --- | ---: |
| 当前可提取正文 | 32141 条 |
| 已保存译文记录 | 32141 条 |
| 插件源码文件 | 176 个 |
| 插件源码候选 | 24769 个 |
| 插件源码规则 selector | 24233 个 |
| 当前运行插件源码字符串字面量 | 34019 个 |

采样使用 `uv run python -m cProfile` 对只读命令采集 profile；写文件命令只读取 CLI 日志中已经落盘的分段耗时。profile 会放大绝对时间，报告中的结论以热点占比、重复调用次数和命令间对照为准。

## 命令采样

| 命令 | profile 总耗时 | 关键热点 |
| --- | ---: | --- |
| `quality-report --json` | 94.276s | JS AST 解析 450 次；`TextScopeService.build` 59.588s；写回探针 18.929s；Rust 译文质检 2.881s |
| `audit-coverage --json` | 63.960s | JS AST 解析 274 次；`TextScopeService.build` 56.640s；写回探针 23.753s |
| `scan-plugin-source-text --json` | 30.235s | 单轮插件源码扫描 176 文件；JS AST 解析 176 次 |
| `export-plugin-source-ast-map --json` | 29.436s | 单轮插件源码扫描 176 文件；JSON 写出不是主耗时 |
| `audit-active-runtime --json` | 30.068s | 当前运行插件源码审计 24.747s；严格 JS AST 扫描 160 文件 |
| `diagnose-active-runtime --json` | 35.716s | 当前运行插件源码审计 24.115s；反推匹配本身约 0.011s |
| `export-pending-translations --json` | 143.443s | 即使 pending 为 0，仍构建完整文本范围并执行写回探针 |
| `translation-status --json` | 35.507s | 状态查询执行完整提取范围构建；JS AST 解析 176 次 |
| `prepare-agent-workspace --json` | 60.936s | 插件源码扫描 2 轮；Note 标签原生扫描 3 次 |
| `validate-agent-workspace --json` | 291.923s | 插件源码扫描 7 轮；JS AST 解析 1330 次；Note 标签原生扫描 14 次；普通/结构化占位符覆盖扫描重复执行 |
| `rebuild-active-runtime --json` | CLI 日志 97.96s | Rust 写回计划 19.090s；其余主要在 Python 写入前检查和重复扫描 |

`rebuild-active-runtime` 的 Rust 写回计划分段：

| 阶段 | 耗时 |
| --- | ---: |
| `load_inputs` | 746ms |
| `active_runtime_audit` | 3575ms |
| `quality_gate` | 3417ms |
| `apply_translations` | 9674ms |
| `diff_outputs` | 1637ms |
| `total` | 19090ms |

## 缺陷清单

### P0：插件源码 AST 解析重复执行且 Python 外层串行

发生了什么：插件源码扫描使用 Python 按文件循环调用 Rust 单文件 AST 入口。一次完整扫描需要解析 176 个 JS 文件；多个命令在同一流程内重复构建 `PluginSourceScan`。

影响什么：大规模插件源码游戏中，单轮扫描约 29 到 30 秒；一旦命令重复扫描，质量报告、覆盖审计、工作区准备、工作区验收和写入前检查都会被放大。

下一步做什么：新增 Rust 批量扫描入口，输入多个文件内容，使用 Rayon 并发解析并返回按文件分组的最小结果；在 Python 命令级上下文中复用扫描结果，避免同一命令内重复解析。

证据：

- `scan-plugin-source-text` 单轮扫描 176 文件，`parse_javascript_string_spans` 调用 176 次，profile 30.235s。
- `quality-report` 调用 450 次 JS AST 解析：插件源码扫描 2 轮，加写回探针 98 文件。
- `validate-agent-workspace` 调用 1330 次 JS AST 解析，`build_plugin_source_scan` 7 次，profile 291.923s。

### P0：工作区验收重复调用全量校验器

发生了什么：`validate-agent-workspace` 自身先加载游戏数据、构建文本范围和插件源码扫描，随后又调用多个独立校验入口。每个入口重新加载数据或重新构建提取范围，导致插件源码、Note 标签、占位符候选反复扫描。

影响什么：工作区验收成为当前最慢的只读命令，profile 291.923s。该命令属于 Agent 流程关键检查，长时间无进度会让外部代理误判为卡死。

下一步做什么：把工作区验收改成单次构建命令上下文：`GameData`、`TextRules`、`translation_data_map`、`PluginSourceScan`、Note 标签来源、事件命中、占位符候选在同一上下文内共享；校验器提供接收上下文的内部接口，CLI 入口仍保留独立使用能力。

证据：

- `validate-agent-workspace` 中 `build_plugin_source_scan` 7 次，`parse_javascript_string_spans` 1330 次。
- `collect_note_tag_sources` 14 次，Rust `collect_note_tag_sources` 自身耗时 32.680s。
- `scan_placeholder_candidates` 和 `scan_structured_placeholder_candidates` 在覆盖检查中重复执行，合计约 77s 累计耗时。

### P1：文本范围构建默认执行写回探针

发生了什么：`TextScopeService.build()` 默认 `include_write_probe=True`。覆盖审计、手动修复表导出、质量报告等读操作在构建文本范围时会执行写回可行性探针；插件源码文本会再次按文件做严格 AST 扫描。

影响什么：读操作承担写文件前的成本。`audit-coverage` 写回探针 23.753s；`export-pending-translations` 即使没有还没成功保存译文，也执行完整文本范围和写回探针，profile 143.443s。

下一步做什么：拆分文本范围模式：普通提取、覆盖审计、写入前检查分别声明是否需要写回探针。只在需要报告 `can_write_back` 或真正写文件前启用探针；其余命令使用轻量模式。

证据：

- `audit-coverage` 写回探针 23.753s，其中插件源码严格扫描 98 文件。
- `export-pending-translations` 输出 `pending_exported_count=0`，仍执行 JS AST 解析 274 次。

### P1：写文件命令存在 Python 与 Rust 双重质量门禁

发生了什么：`rebuild-active-runtime` 先在 Python `_prepare_write_operation()` 中加载数据、构建文本范围、执行流程 gate 和写入前质量检查；随后 Rust 写回计划再次读取输入、执行当前运行文件审计、译文质量 gate、写回计划生成和差异比较。

影响什么：原生命令本身已经较快，Rust 计划总计 19.090s；CLI 总耗时 97.96s，说明大量时间落在 Python 前置重复检查上。进度条在计划生成前一直显示“准备开始”，用户无法判断真实阶段。

下一步做什么：将写文件前 gate 统一到 Rust dry-run/计划入口，Python 只负责解析参数、展示错误和落盘事务；必须保留的外部契约检查以 Rust 计划结果为准，避免 Python 再构建完整文本范围和重复质检。

证据：

- CLI 日志记录 `rebuild-active-runtime` 总耗时 97.96s。
- 同一次日志中 Rust 写回计划 `total 19090ms`，其中 `quality_gate 3417ms`、`apply_translations 9674ms`。
- 进度条在 `build_native_write_back_plan()` 返回后才设置为 `0/32141`。

### P1：状态查询不是轻量查询

发生了什么：`translation-status` 为了计算当前还没成功保存译文数量，调用 `_extract_active_translation_data_map()`，间接构建文本范围并扫描插件源码。

影响什么：一个状态查询命令在大样本上 profile 35.507s，并执行 176 次 JS AST 解析。状态查询本应优先使用数据库中最近运行统计和已保存译文记录。

下一步做什么：默认状态查询走数据库快速路径，直接返回最近运行记录、已保存译文数量和最新错误统计；需要重新扫描当前规则范围时增加显式刷新参数。

证据：

- `translation-status` 中 `build_plugin_source_scan` 1 次，`parse_javascript_string_spans` 176 次。
- 输出显示当前 pending 为 0，但仍执行完整提取范围构建。

### P1：当前运行文件审计缺少可复用扫描结果

发生了什么：`audit-active-runtime` 和 `diagnose-active-runtime` 都扫描当前运行插件源码。诊断命令的确定性反推本身很快，但仍要完整审计当前运行文件。

影响什么：当前运行审计单次约 30s；诊断命令 profile 35.716s，其中反推匹配约 0.011s，主要成本仍是源码审计。

下一步做什么：为当前运行插件源码审计建立命令级复用结果，按文件哈希跳过未变化文件；诊断命令复用审计结果和运行映射索引。

证据：

- `audit-active-runtime` 当前运行审计 24.747s，严格扫描 160 文件。
- `diagnose-active-runtime` 当前运行审计 24.115s，`_build_active_runtime_diagnosis_items` 约 0.011s。

### P2：原生 Note 标签扫描重复执行

发生了什么：工作区准备和验收流程多次调用 Note 标签来源扫描。该扫描已经在 Rust 原生侧执行，但调用入口重复。

影响什么：`prepare-agent-workspace` 中 Note 标签扫描 3 次，约 7.070s；`validate-agent-workspace` 中 14 次，约 32.680s。

下一步做什么：在命令上下文中共享 Note 标签来源和规则命中结果；规则校验入口支持接收已经计算好的来源集合。

### P2：Python JSON 边界和深拷贝成本在超大校验中放大

发生了什么：Rust 结果通过 JSON 文本返回 Python，随后 Python 对大对象执行 `coerce_json_value`、结构收窄和 `deepcopy`。单轮命令成本不是第一热点，但在工作区验收中被重复调用放大。

影响什么：`validate-agent-workspace` 中 `coerce_json_value` 约 11.673s，`deepcopy` 约 27.349s；插件源码扫描对象和规则校验对象越大，放大越明显。

下一步做什么：减少跨语言 JSON 大对象传输次数；对只需要摘要的命令返回轻量结构；避免对完整 `GameData` 或大型扫描结果做不必要深拷贝。

### P2：长任务进度缺少真实阶段

发生了什么：多个命令没有阶段状态回调，长时间只显示“准备开始”或完全没有进度。`rebuild-active-runtime` 在 96 秒内没有说明正在执行写入前检查或 Rust 写回计划；`validate-agent-workspace` 长时间无阶段进度。

影响什么：用户和外部代理无法判断是 CPU 密集处理、文件 I/O、数据库等待还是卡死，也无法定位性能问题。

下一步做什么：为写文件、工作区验收、手动修复表导出、状态查询等命令增加阶段状态和分段计时；报告文本使用用户可理解阶段名。

## 优先修复路径

1. 新增命令级上下文对象，统一携带 `GameData`、`TextRules`、`translation_data_map`、`PluginSourceScan`、Note 标签来源、事件规则命中和已保存译文索引。
2. 新增 Rust 批量 JS AST 扫描入口，用 Rayon 并发处理插件源码文件，并按调用场景返回轻量摘要、候选索引或 selector 验证结果。
3. 将 `TextScopeService.build()` 默认模式改为轻量提取；写回探针必须由调用方显式开启。
4. 写文件命令以 Rust 写回计划作为唯一重型 gate，Python 避免重复构建完整文本范围和重复质检。
5. `translation-status`、`export-pending-translations` 增加快速路径；需要刷新当前规则范围时显式启用。
6. 工作区验收改为一次加载、多校验复用，避免调用独立 CLI 校验器造成多轮扫描。
7. 补齐长任务阶段进度和分段耗时日志，让性能回归可以直接定位阶段。

## 未验证范围

- 未对真实模型翻译调用做 profile，避免消耗模型额度；翻译命令中的本地准备阶段与文本范围构建路径相关，预计受同类问题影响。
- 未对原始游戏目录执行新的写文件命令；写文件性能结论来自当前 CLI 文件日志中已经记录的 `rebuild-active-runtime` 分段。
- profile 运行会增加绝对耗时；本报告用于定位热点和重复调用，不把 profile 秒数当作发布基准。

