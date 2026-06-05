# Rust Scope/Index Engine 批次 32 验收记录

## 本批范围

- 批次：6A，P1-B 工作区和规则命令静态审计矩阵。
- 覆盖入口：计划中列出的全部 P1-B 工作区、规则、候选扫描和规则导入命令。
- 成功状态：每个 P1-B 命令都有当前事实来源、旧路径状态、处理结论和下一步入口；后续迁移不能跳过未审计命令，也不能把目标预算误当成当前实现完成状态。

## P1-B 命令审计矩阵

| 命令 | 当前事实来源 | 旧路径状态 | 处理结论 | 下一步入口 |
| --- | --- | --- | --- | --- |
| `prepare-agent-workspace` | `app/agent_toolkit/services/workspace.py`；可用 text index 时读取索引行，插件源码和非标准 data 候选仍由 Python 扫描 | 部分收束 | 保留工作区渲染；候选扫描迁到 Rust 后复用同一结果 | 先接入插件源码候选 |
| `validate-agent-workspace` | workspace manifest；启用的规则支线仍调用对应 Python 校验/扫描 | 部分收束 | 继续消费 manifest；活动支线改为复用 Rust 候选结果 | 接 `prepare-agent-workspace` 同源候选 |
| `scan-plugin-source-text` | `build_plugin_source_scan` Python AST 扫描 | 待迁移 | CLI 报告保留；候选主路径迁到 Rust `scan_rule_candidates(plugin_source)` | 下一批首选 |
| `export-plugin-source-ast-map` | `build_plugin_source_scan` Python AST 扫描 | 待迁移 | AST map 输出保留；扫描结果改由 Rust 生成 | 跟随插件源码候选迁移 |
| `scan-nonstandard-data` | `build_nonstandard_data_scan` Python 非标准 data 扫描 | 待迁移 | 报告渲染保留；候选主路径迁到 Rust `scan_rule_candidates(nonstandard_data)` | 插件源码后迁移 |
| `export-nonstandard-data-json` | Python 非标准 data 扫描和工作区导出 | 待迁移 | 导出事务保留；候选和风险摘要改为 Rust 来源 | 跟随非标准 data 候选迁移 |
| `validate-nonstandard-data-rules` | Python 非标准 data 规则校验 | 待迁移 | 校验外壳保留；覆盖统计改用 Rust 候选 | 跟随非标准 data 候选迁移 |
| `import-nonstandard-data-rules` | Python 非标准 data 规则解析、覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；导入前覆盖检查改用 Rust 候选 | 跟随非标准 data 候选迁移 |
| `scan-placeholder-candidates` | Python 普通占位符候选扫描 | 待迁移 | 输出协议保留；候选扫描改由 Rust/index 事实提供 | 规则候选第二阶段 |
| `validate-placeholder-rules` | Python 普通占位符规则校验和覆盖检查 | 待迁移 | 校验外壳保留；覆盖统计改用 Rust 候选 | 跟随占位符候选迁移 |
| `build-placeholder-rules` | Python 普通占位符规则生成 | 待迁移 | 生成协议保留；候选输入改用 Rust 候选 | 跟随占位符候选迁移 |
| `import-placeholder-rules` | Python 普通占位符导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随占位符候选迁移 |
| `validate-structured-placeholder-rules` | Python 结构化占位符校验和覆盖检查 | 待迁移 | 校验协议保留；覆盖统计改用 Rust 候选 | 规则候选第二阶段 |
| `scan-structured-placeholder-candidates` | Python 结构化占位符候选扫描 | 待迁移 | 输出协议保留；候选扫描改由 Rust/index 事实提供 | 规则候选第二阶段 |
| `import-structured-placeholder-rules` | Python 结构化占位符导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随结构化占位符候选迁移 |
| `export-note-tag-candidates` | Python Note 标签候选扫描 | 待迁移 | 输出协议保留；候选扫描改为 Rust 来源 | 规则候选第二阶段 |
| `validate-note-tag-rules` | Python Note 标签规则校验 | 待迁移 | 校验协议保留；覆盖统计改用 Rust 候选 | 跟随 Note 标签候选迁移 |
| `import-note-tag-rules` | Python Note 标签导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随 Note 标签候选迁移 |
| `export-event-commands-json` | Python 事件指令候选导出 | 待迁移 | 导出协议保留；候选来源改用 Rust/index 事实 | 规则候选第二阶段 |
| `validate-event-command-rules` | Python 事件指令规则校验 | 待迁移 | 校验协议保留；覆盖统计改用 Rust 候选 | 跟随事件指令候选迁移 |
| `import-event-command-rules` | Python 事件指令导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随事件指令候选迁移 |
| `validate-plugin-rules` | Python 插件参数规则校验 | 待迁移 | 校验协议保留；覆盖统计改用 Rust 插件配置候选 | 规则候选第二阶段 |
| `import-plugin-rules` | Python 插件参数导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随插件参数候选迁移 |
| `validate-plugin-source-rules` | `build_plugin_source_scan` Python AST 扫描和规则校验 | 待迁移 | 校验协议保留；覆盖统计改用 Rust 插件源码候选 | 跟随插件源码候选迁移 |
| `import-plugin-source-rules` | `build_plugin_source_scan` Python AST 扫描、覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 插件源码候选 | 跟随插件源码候选迁移 |
| `export-mv-virtual-namebox-candidates` | Python MV 虚拟名字框候选扫描 | 待迁移 | 输出协议保留；候选来源改用 Rust/index 事实 | 规则候选第二阶段 |
| `validate-mv-virtual-namebox-rules` | Python MV 虚拟名字框规则校验 | 待迁移 | 校验协议保留；覆盖统计改用 Rust 候选 | 跟随 MV 虚拟名字框候选迁移 |
| `import-mv-virtual-namebox-rules` | Python MV 虚拟名字框导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随 MV 虚拟名字框候选迁移 |
| `validate-source-residual-rules` | Python 源文残留规则校验 | 待迁移 | 校验协议保留；候选覆盖改用 Rust 质量/候选事实 | 规则候选第二阶段 |
| `import-source-residual-rules` | Python 源文残留导入前覆盖检查和数据库事务 | 待迁移 | 数据库事务保留；覆盖检查改用 Rust 候选 | 跟随源文残留候选迁移 |

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch32_p1b_static_audit_record_exists_and_covers_all_commands`：
  - 从 `tests.scan_budget_contract.P1_B_COMMANDS` 读取 P1-B 命令集合。
  - 解析本记录的审计矩阵，断言每个 P1-B 命令恰好进入审计集合。
  - 固定本记录必须被总计划链接，并包含统一收尾章节。

## 改动范围

- `tests/test_scan_budget.py`
  - 增加批次 32 P1-B 审计矩阵保护测试。
- `docs/records/rust-scope-index/batches/batch-032.md`
  - 新增 P1-B 全命令静态审计矩阵。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 批次进度追加 6A，并给出下一批入口建议。

## 旧路径收束

- 本批不删除生产代码旧路径；它先把旧路径逐项显式化，避免后续只迁移少数命令而漏掉同类入口。
- 当前确认插件源码、非标准 data、占位符、Note、事件、插件参数、MV 虚拟名字框和源文残留候选/覆盖检查仍有 Python 路径，需要后续分批收束。
- `prepare-agent-workspace` 和 `validate-agent-workspace` 已有部分 warm index/manifest 防重扫保护，但候选支线仍需迁移。

## 外部契约变化

- CLI 参数、配置字段、JSON schema、输出文件名和报告字段不变。
- 本批只新增开发验收记录和测试保护，不改变用户可见行为。

## 性能证据

- 审计矩阵把每个 P1-B 命令的当前候选扫描来源显式列出，证明下一批迁移从仍使用 Python 重型路径的入口开始。
- 保护测试防止 P1-B 命令列表扩展后没有同步审计记录。
- 本批没有运行大样本 benchmark；性能收益将在后续具体迁移批次用行为测试或 benchmark 固定。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch32_p1b_static_audit_record_exists_and_covers_all_commands`：1 failed，批次 32 验收记录尚不存在。
- GREEN：`uv run pytest tests/test_scan_budget.py::test_batch32_p1b_static_audit_record_exists_and_covers_all_commands`：1 passed。
- `uv run pytest tests/test_scan_budget.py::test_rust_scope_index_scan_budget_table_covers_p0_p1_commands tests/test_scan_budget.py::test_batch32_p1b_static_audit_record_exists_and_covers_all_commands`：2 passed。
- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- 批次文档敏感路径和未完成占位符扫描：无命中。
- `git diff --check`：通过；仅输出 Git 换行规范提示。

## 审查处理

- 实现自查：本批没有生产代码改动；审计矩阵以当前代码调用链为依据，并把 P1-B 未迁移路径标为后续工作。
- 子代理审查未发现 Critical 问题。
- 子代理审查发现 Important：验证结果只记录 RED，没有写入 GREEN 和收尾验证。
- 已修复：补充 GREEN、扫描预算关联测试、类型检查、文档扫描和 diff 检查结果。
- 子代理审查确认矩阵覆盖 `P1_B_COMMANDS` 30/30，未把仍由 Python 扫描的路径写成已完成迁移；残余风险是若未来新增 CLI 命令但未同步 `P1_B_COMMANDS`，本批测试不会发现。

## 剩余风险

- 本批是 P1-B 的静态审计和保护网，不代表 P1-B 命令已经完成 Rust 候选扫描迁移。
- `scan_rule_candidates` 当前仍是 Rust 汇总边界，不是完整插件源码或非标准 data 原生扫描器；下一批需要先扩展该入口的真实输入能力。
- 工作区命令涉及多种规则文件和 manifest，后续迁移时必须保持现有输出文件和 JSON 字段契约不变。

## 下一批入口

- 建议下一批：6B 插件源码候选扫描 Rust 入口。先让 `scan_rule_candidates(plugin_source)` 接收插件源码输入并生成与 `scan-plugin-source-text` 所需报告等价的候选摘要，再把 CLI/Agent 报告渲染保留在 Python 薄适配层。
