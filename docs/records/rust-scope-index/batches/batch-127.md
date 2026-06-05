# Rust Scope/Index Engine 批次 127 验收记录

## 本批范围

- 批次编号：7D。
- 范围：全计划收束验收。
- 覆盖阶段：P0、P1-A、P1-B、P1-C。
- 目标：把 `docs/plans/completed/rust-scope-index-engine.md` 从活跃推进态下线，确认所有计划批次都有验收记录，预算表覆盖全部 P0/P1 命令，并把未运行全量回归的风险边界写清楚。

## 保护网

- `tests/test_scan_budget.py::test_rust_scope_index_scan_budget_table_covers_p0_p1_commands`：固定 P0/P1 命令预算表覆盖要求。
- `tests/test_scan_budget.py::test_batch127_final_plan_closure_marks_plan_downlined_and_budgets_complete`：固定计划状态、7D 已完成行、剩余批次清零、四类预算集合和 P1-C 记录闭环。
- `tests/test_scan_budget.py::test_batch127_final_plan_closure_record_exists_and_limits_claims`：固定本验收记录，并禁止把按用户当前目标未运行全量 `uv run pytest` 误写成全仓回归已验证。

## 预算复核

- P0 命令数：1。
- P1-A 命令数：13。
- P1-B 命令数：30。
- P1-C 命令数：7。
- 合计：1 + 13 + 30 + 7 = 51。
- `P1_B_PENDING_FACT_SOURCE_COMMANDS` 为空，表示 P1-B 不再保留待复核事实来源集合。
- `scan_budgets_by_command()` 与 `required_scan_budget_commands_by_category()` 的四类命令集合完全一致。
- 预算字段中不允许继续保留待复核或旧目标占位文案。

## 旧路径收束

- P0 pending 导出已通过批次 4 和后续 P1-A/P1-B/P1-C 预算复核记录收束。
- P1-A 核心命令已按批次 5A 到 5Y 进入 Rust/SQLite scope/index、warm index、质量 gate 和写回计划复用边界。
- P1-B 工作区和规则命令已按批次 6A 到 6CN 分支收束，插件源码、非标准 data、普通占位符、结构化占位符、Note 标签、事件指令、插件参数、MV 虚拟名字框和源文残留命令均有对应验收记录。
- P1-C 运行审计、术语/语言探测、插件配置导出和文档契约已按批次 7A 到 7C 收束。
- 本批不新增生产迁移，不删除额外生产入口；作用是把计划文档下线并固定最终验收边界。

## 外部契约变化

- 无 CLI 参数变化。
- stdout Agent JSON 字段名不变。
- 无数据库 schema 变化。
- 无 Rust 原生扩展 API 变化。
- 计划文档状态从 `执行计划` 改为 `状态：已完成（已下线）`，并声明无剩余批次。

## 性能证据

- scan_budget 表已经覆盖 P0/P1-A/P1-B/P1-C 的 51 个命令，并为每个命令固定 GameData load、TextScope build、候选扫描、插件源码 AST scan、质量 gate 和写回计划预算。
- P1-B 待复核事实来源集合为空，防止旧 Python 重型路径继续以待办形式留在计划尾部。
- 7A、7B、7C 三份记录分别覆盖 P1-C 的 7 个命令：运行审计三命令、术语/语言探测三命令和 `export-plugins-json`。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch127_final_plan_closure_marks_plan_downlined_and_budgets_complete tests/test_scan_budget.py::test_batch127_final_plan_closure_record_exists_and_limits_claims`：2 failed，失败点分别是计划仍为执行计划状态和本批记录不存在。
- 调整总预算保护后复跑：`uv run pytest tests/test_scan_budget.py::test_rust_scope_index_scan_budget_table_covers_p0_p1_commands tests/test_scan_budget.py::test_batch127_final_plan_closure_marks_plan_downlined_and_budgets_complete tests/test_scan_budget.py::test_batch127_final_plan_closure_record_exists_and_limits_claims`：3 passed。中途该命令曾因旧总预算测试不允许 `diagnose-active-runtime` 的 2 次真实 GameData I/O 失败，已收窄为仅该命令允许 2 次，其它命令仍最多 1 次。
- 本轮最终目标组合验证：`uv run pytest tests/test_plugin_text.py::test_plugin_json_export_writes_raw_plugins_array tests/test_skill_protocol.py::test_removed_agent_mode_flags_are_absent_from_public_protocol_docs tests/test_skill_protocol.py::test_skill_and_readme_command_examples_exist_in_parser tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_tracks_current_boundaries tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_record_exists tests/test_scan_budget.py::test_rust_scope_index_scan_budget_table_covers_p0_p1_commands tests/test_scan_budget.py::test_batch127_final_plan_closure_marks_plan_downlined_and_budgets_complete tests/test_scan_budget.py::test_batch127_final_plan_closure_record_exists_and_limits_claims`：8 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- 文档敏感路径搜索：`文档敏感路径` 检查覆盖本记录、7C 记录和计划文档，NO_MATCH。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 本批按用户当前目标未运行全量 `uv run pytest`。

## 最终风险

- 本批按用户当前目标未运行全量 `uv run pytest`。
- 因用户当前 goal 明确禁止全量回归，本批不能声明全仓 Python 测试已验证，只能声明本批目标测试、相关 scan_budget/记录保护、类型检查、文档敏感路径搜索和 diff 空白检查通过后的结果。
- 工作区存在大量前序批次改动；本批未回滚、不整理、不合并这些改动。

## 计划下线结论

- `docs/plans/completed/rust-scope-index-engine.md` 已标记为 `状态：已完成（已下线）`。
- 剩余批次数为 0 批，无剩余批次。
- `docs/records/rust-scope-index/batches/batch-127.md` 是本计划最后一份验收记录。
