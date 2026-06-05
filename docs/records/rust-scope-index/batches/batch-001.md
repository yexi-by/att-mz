# Rust Scope/Index Engine 批次 1 审计记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只建立保护网、结构审计和性能基线记录，不进入配置收口、Rust 原生入口实现、SQLite schema 迁移或 P0 快路径实现。

涉及文件：

- `docs/records/rust-scope-index/batches/batch-001.md`
- `docs/plans/completed/rust-scope-index-engine.md`
- `tests/scan_budget_contract.py`
- `tests/test_scan_budget.py`

## 主流程图

| 命令范围 | 主流程 | 权威事实来源 | 失败暴露位置 |
| --- | --- | --- | --- |
| P0 `export-pending-translations --limit` | CLI 参数校验 -> 检查 text index -> SQLite pending limit 查询 -> 渲染 Agent JSON | `text_index_items` pending 快路径；索引缺失时由 Rust `build_scope_index` 重建一次 | 索引失效且无法重建、路径归属异常、JSON 输出失败 |
| P1-A 索引和状态命令 | CLI 参数校验 -> 配置加载 -> Rust `build_scope_index` 或 SQLite summary -> 统计/清单输出 | Rust scope/index rows、scope summary、domain summary、rule hit summary | 旧 schema、规则错配、native contract 版本不匹配、索引不可用 |
| P1-A 翻译和质量命令 | CLI 参数校验 -> 配置加载 -> SQLite pending/translation 查询 -> Rust `evaluate_scope_gate`/quality -> 报告或模型调用 | SQLite text index、Rust gate summary、Rust quality result | 质量检查没通过、prompt 输入不合法、模型失败、索引不可用 |
| P1-A 写回命令 | CLI 参数校验 -> 配置加载 -> Rust gate summary -> Rust write plan -> 文件替换/审计 -> Agent JSON | Rust scope/index、Rust quality、Rust write plan | 可写范围不满足、质量 gate 失败、写回协议错误、文件替换失败 |
| P1-B 工作区和规则命令 | CLI 参数校验 -> 配置加载 -> Rust `scan_rule_candidates` 或复用已建 scope/index -> 工作区 JSON/规则事务 | Rust candidate result、workspace manifest、规则数据库 | 候选覆盖不足、规则输入非法、manifest 不匹配、数据库写入失败 |
| P1-C 审计命令 | CLI 参数校验 -> 读取真实运行文件/术语/反馈文本 -> 局部 Rust 热路径或数据库查询 -> Agent JSON | active runtime cache、terminology repository、source language probe、Rust quality | 真实 I/O 失败、缓存失效、反馈文本质量错误、输入文件非法 |

## 事实来源矩阵

| 业务结论 | 权威产出位置 | 消费位置 | 是否允许重复计算 | 旧来源处理 |
| --- | --- | --- | --- | --- |
| 当前可处理范围 | Rust `build_scope_index` / SQLite text index | CLI、质量报告、覆盖审计、工作区、写回 | 否 | 删除 Python 全量扫描或改为薄适配层 |
| 当前可写范围 | Rust `build_scope_index` / `evaluate_scope_gate` | pending 导出、写回、质量报告、覆盖审计 | 否 | 删除 Python 可写路径重复推导 |
| pending 列表 | SQLite `text_index_items` 快路径 | pending 导出、翻译批次准备 | 否 | 删除 Python 全量 pending 筛选 |
| 规则命中统计 | Rust scope summary / rule hit summary | 工作区、规则校验、覆盖审计 | 否 | 删除 Python 全量统计 |
| 插件源码候选 | Rust `scan_rule_candidates(plugin_source)` | 插件源码扫描、工作区、规则校验 | 否 | 删除 Python AST 扫描主路径 |
| 非标准 data 候选 | Rust `scan_rule_candidates(nonstandard_data)` | 非标准 data 扫描、工作区、规则校验 | 否 | 删除 Python 扫描主路径 |
| 质量门禁结果 | Rust `evaluate_scope_gate` / Rust quality | 质量报告、写回、翻译门禁 | 否 | 删除重复门禁 |
| Rust 线程数 | `[runtime].rust_threads` | 所有 Rust 并行入口、报告摘要 | 否 | 后续批次删除环境变量入口 |
| Rust API 契约版本 | `app/native_contract.py` 与 Rust native contract | 新旧 Rust 热路径 adapter | 否 | 禁止只检查函数存在 |

## 门禁链审计

| 门禁 | 职责 | 输入 | 输出 | 重复扫描约束 |
| --- | --- | --- | --- | --- |
| 输入校验 | 校验 CLI 参数、配置字段和输入 JSON | CLI args、`setting.toml`、输入文件 | 结构化 Python 对象 | 不读取全量游戏文本 |
| 规则校验 | 校验规则语法、覆盖和候选命中 | Rust candidate result、规则文件 | 规则错误和覆盖摘要 | 同一命令候选扫描不超过 1 次 |
| 工作流门禁 | 判断本命令是否可继续 | text index summary、规则状态、数据库状态 | Agent JSON summary/status | 不重建第二份 scope |
| 质量门禁 | 判断译文能否进入写回或报告 | 已保存译文、Rust quality payload、scope/index | quality issues、gate result | 同一命令 quality gate 不超过 1 次 |
| 写回前检查 | 判断可写路径、字体副作用和写回协议 | Rust gate summary、write plan payload | write plan、文件操作计划 | 复用同一 scope/index 和 quality result |
| 写后审计 | 检查实际运行文件 | active runtime cache、替换结果 | runtime audit summary | 不归入 scope/index 事实来源 |

## 旧路径删除清单

| 新能力 | 替代旧路径 | 本批处理结论 | 后续批次 |
| --- | --- | --- | --- |
| SQLite pending limit 快路径 | `manual_translation.py` 构建完整 `TextScopeService` 后筛选 pending | 已在预算契约中标为 P0 删除对象 | 批次 3 实现并补行为测试 |
| Rust `build_scope_index` | Python 全量 `TextScopeService` 扫描、规则命中统计、可写路径推导 | 已在事实来源矩阵和预算表中设为唯一完整扫描入口 | 批次 4 和 P1-A 接入 |
| Rust `scan_rule_candidates` | Python 插件源码 AST、非标准 data、占位符和规则候选扫描主路径 | 已在 P1-B 预算表中逐命令标注 | 批次 8 接入并删除旧主路径 |
| Rust `evaluate_scope_gate` | Python 工作流门禁、质量门禁和写回前重复检查 | 已在门禁链审计中收束为单一 gate summary | 批次 5 至 7 接入 |
| `[runtime].rust_threads` | `ATT_MZ_RUST_THREADS` 生产读取、benchmark 注入、Skill 文案 | 本批记录为外部契约冲突，不改生产入口 | 批次 2 配置收口，批次 8/文档同步清理 |

## 测试分类清单

| 测试类别 | 当前处理 | 后续调整 |
| --- | --- | --- |
| 外部 CLI/Agent JSON 契约 | 保留，后续批次补金丝雀链路 | 不绑定内部函数形态 |
| 扫描预算测试 | 本批扩展为 P0/P1 全覆盖表 | 后续批次补运行时计数或行为测试 |
| benchmark 脚本测试 | 本批不改线程入口，记录冲突 | 批次 2 改为临时 `setting.toml` |
| native adapter 测试 | 本批不新增 Rust API | 批次 4 起纳入三类入口族版本门槛 |
| 旧 Python 重型函数形态测试 | 不新增 | 后续改为外部行为和预算断言 |
| 文档/Skill 测试 | 本批只检查批次记录存在和无私有路径 | 后续检查 Skill/README 不再描述旧线程入口 |

## 文档和指令审计

| 文件范围 | 当前发现 | 本批处理 | 后续处理 |
| --- | --- | --- | --- |
| README / docs development | 仍有历史性能和 `ATT_MZ_RUST_THREADS` 说明 | 本批记录，不改当前公开入口 | 配置收口后同步更新 |
| `skills/att-mz*` | 仍说明长任务可设置 `ATT_MZ_RUST_THREADS` | 本批记录，不修改翻译流程 Skill | 配置收口后开发版/发行版 Skill 同步 |
| CLI 契约 reference | 仍把 Rust 线程数描述为环境变量 | 本批记录为外部契约待调整项 | 配置收口后更新并补测试 |
| AGENTS.md | 当前只给长期工程底线 | 不添加临时实现细节 | 后续仍避免固化临时路径 |
| 本计划文档 | 已包含批次约定和停止条件 | 本批添加进度索引 | 每批结束更新进度 |

## 外部契约矩阵

| 契约 | 本批处理方式 | 说明 |
| --- | --- | --- |
| CLI 子命令和参数 | 保持不变 | 本批不改 parser 和 dispatch |
| stdout Agent JSON | 保持不变 | 本批不改运行命令 |
| SQLite schema | 保持不变 | summary 表在后续 schema 批次实现 |
| `setting.toml` | 保持不变 | `[runtime].rust_threads` 在配置收口批次新增 |
| Rust native payload | 保持不变 | 三类 Rust API 入口后续新增 |
| 工作区 JSON | 保持不变 | P1-B 迁移时保持字段契约或显式记录破坏性调整 |
| README / Skill | 保持不变 | 本批只记录待同步项 |
| 日志摘要 | 保持不变 | 本批不改运行时日志 |
| benchmark 脚本 | 保持不变 | 当前源码未支持 `[runtime].rust_threads`，本批不提前破坏测试 |

## 性能基线记录

已确认大样本问题来自计划文件中的性能记录，本批不重新运行大样本 benchmark，因为当前仓库没有提供可公开复用的样本路径和数据库输入。记录方式如下：

| 命令 | 改造前耗时 | 当前归因 | 本批处理 |
| --- | --- | --- | --- |
| `export-pending-translations --limit 20` | 超过 600 秒仍未完成 | Python 构建完整文本范围后再筛选 pending，limit 后置 | P0 预算固定 SQLite limit 快路径 |
| `translation-status --refresh-scope` | 约 63 秒 | 索引缺失后构建文本范围约 52 秒 | P1-A 预算固定最多一次 Rust scope/index |
| `doctor --no-check-llm` | 约 66 秒 | 重复加载和范围/规则检查 | 计划未列入 P1 主实现，后续如纳入需补预算 |
| `audit-coverage` | 约 59 秒 | Python 覆盖统计和范围扫描 | P1-A 预算固定 summary 快路径 |
| `text-scope` | 约 63 秒，输出约 43MB | 扫描成本加大输出成本 | P1-A 预算区分扫描和输出 I/O |
| `quality-report` | 约 13 秒 | 已保存译文质量检查和范围筛选 | P1-A 预算固定一次 quality gate |
| `scan-plugin-source-text` | 约 4 秒 | 插件源码 AST 扫描 | P1-B 预算迁到 Rust candidate |
| `scan-nonstandard-data` | 约 3 秒 | 非标准 data 候选扫描 | P1-B 预算迁到 Rust candidate |

本批性能证据是静态保护网：`tests/scan_budget_contract.py` 逐命令固定允许扫描次数、权威事实来源和旧路径处理结论。动态大样本耗时对比将在实现 P0/P1-A 后补充改造后数据。

## 批次 1 验收记录

本批范围：

- 建立 P0/P1 命令扫描预算表。
- 建立结构审计、事实来源、门禁链、旧路径、测试分类、文档指令和外部契约记录。
- 在计划文档中加入批次进度入口。

先建立或调整的行为测试：

- `tests/test_scan_budget.py::test_rust_scope_index_scan_budget_table_covers_p0_p1_commands`
- `tests/test_scan_budget.py::test_batch01_audit_record_exists_and_is_linked_from_plan`

删除或收束的旧路径：

- 本批不删除生产旧路径。
- 已把 P0/P1 对应旧路径处理结论写入扫描预算和旧路径删除清单，作为后续实现停止条件。

运行命令和结果：

- `uv run pytest tests/test_scan_budget.py`：3 passed in 0.06s。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：688 passed in 177.73s。
- 本批未修改 Rust 代码、Cargo 配置或 Rust 原生扩展，未运行 Rust 门禁。

性能证据：

- 已记录计划确认的大样本改造前耗时。
- 已建立扫描预算测试契约；本批不具备公开样本路径，未运行大样本 benchmark。

外部契约变化：

- 无。

剩余风险：

- benchmark 脚本仍通过 `--rust-threads` 设置环境变量，需在配置收口批次处理。
- `doctor --no-check-llm` 已有慢数据但不在 P0/P1 主范围，本批只记录冲突，不扩大实现范围。
- 扫描预算当前是结构化测试契约，不是运行时计数器；后续实现批次需要补行为测试或计数证据。

下一批入口：

- 批次 2：配置收口，新增 `[runtime].rust_threads`，删除 `ATT_MZ_RUST_THREADS` 生产读取和 benchmark env 注入。
