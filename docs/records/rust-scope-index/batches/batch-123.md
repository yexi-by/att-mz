# Rust Scope/Index Engine 批次 123 验收记录

## 本批范围

- 批次编号：6CN。
- 范围：P1-B 工作区和规则命令总收束。
- 目标：覆盖 30 个 P1-B 命令，确认预算表、事实来源、旧路径边界和验收记录都已经收束到当前实现。
- 本批新增生产收束：把 `prepare-agent-workspace` 的 MV 虚拟名字框候选输出切到 native payload，并让 `prepare-agent-workspace` / `validate-agent-workspace` 默认通过持久文本索引读取正文范围。

## RED/GREEN

- RED：`tests/test_scan_budget.py::test_batch123_p1b_total_closure_record_exists` 在 `docs/records/rust-scope-index/batches/batch-123.md` 缺失时失败。
- RED：`tests/test_scan_budget.py::test_batch123_p1b_total_closure_static_old_path_boundary` 初版把 `import-plugin-rules` 入口定位到错误模块，暴露出总收束检查必须按真实服务入口绑定。
- RED：子代理只读审计指出 `prepare-agent-workspace` 的 MV 候选输出仍调用旧 Python payload，`validate-agent-workspace` 默认仍会通过 `_extract_active_translation_data_map` 构建完整文本范围。
- RED：新增 `tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_warm_text_index_without_full_scope_build` 和 `tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_mv_namebox_uses_native_payload` 固定两个 workspace 漏点。
- GREEN：`tests/test_scan_budget.py::test_batch123_p1b_total_closure_tracks_all_budget_facts` 固定 P1-B 命令数量、预算分类、事实来源和 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 清空状态。
- GREEN：静态边界检查改为按 `validate-plugin-rules` 的 service 入口和 `import-plugin-rules` 的 handler 入口分别审计。
- GREEN：`workspace.py` 使用 `_read_workspace_translation_data_map_from_text_index` 统一处理 workspace 正文范围读取；warm index 直接读 SQLite，cold/stale index 先用底层持久索引重建再读 SQLite。
- GREEN：底层 `app/text_index.py::rebuild_text_index` 接收已有 `PluginSourceScan`，避免 workspace cold rebuild 时重复扫描插件源码。

## 改动范围

- `app/agent_toolkit/services/workspace.py`：新增 workspace text index 读取 helper；`prepare-agent-workspace` 和 `validate-agent-workspace` 改为复用持久文本索引；MV 候选输出改用 `native_mv_virtual_namebox_candidates_payload`。
- `app/text_index.py`：`rebuild_text_index` 新增可选 `plugin_source_scan` 入参，供 workspace cold/stale 重建时复用已有插件源码扫描结果。
- `tests/test_agent_toolkit_workspace.py`：新增 workspace warm index 验收和 MV native payload 行为保护，并复跑既有插件源码扫描复用与 MV 默认工作区回归。
- `tests/test_scan_budget.py`：新增 P1-B 总收束预算事实、静态旧路径边界和 batch-123 记录保护测试。
- `docs/plans/completed/rust-scope-index-engine.md`：新增 6CN 已完成记录，并把剩余批次数从 5 批推进到 4 批。
- `docs/records/rust-scope-index/batches/batch-123.md`：新增本批验收记录。

## 旧路径收束

- P1-B 预算表中 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 为空，表示 30 个 P1-B 命令都已经有当前事实来源。
- 工作区和插件源码命令事实来源覆盖 `Rust build_scope_index / scan_rule_candidates` 与 `Rust scan_rule_candidates(plugin_source)`。
- 非标准 data 命令事实来源覆盖 `Rust scan_rule_candidates(nonstandard_data)`。
- 普通占位符命令事实来源覆盖 `Rust scan_rule_candidates(placeholders)`。
- 结构化占位符命令事实来源覆盖 `Rust scan_rule_candidates(structured_placeholders)`。
- Note 标签命令事实来源覆盖 `Rust scan_rule_candidates(note_tags)`。
- 事件指令命令事实来源覆盖 `Rust scan_rule_candidates(event_commands)`。
- 插件参数规则命令事实来源覆盖 `Rust scan_rule_candidates(plugin_config)`。
- MV 虚拟名字框命令事实来源覆盖 `Rust scan_rule_candidates(mv_virtual_namebox)`。
- 源文残留 validate/import 命令事实来源覆盖 `SQLite text_index_items`。
- `prepare-agent-workspace` 的 MV 候选输出不再调用旧 `mv_virtual_namebox_candidates_payload` 和 `collect_mv_virtual_namebox_candidates` 生产路径。
- `prepare-agent-workspace` / `validate-agent-workspace` 不再默认调用 `_extract_active_translation_data_map` 构建正文范围；正文范围由 `read_text_index_items` 还原。

## 外部契约变化

- 无 CLI 参数变化。
- stdout Agent JSON 字段名不变。
- `prepare-agent-workspace` 在 text index 缺失或过期时会先重建持久索引，再以 `translation_scope_mode="text_index"` 输出 workspace；`text_index_status` 使用 `cold_rebuilt` 或 `stale_rebuilt` 表示已重建后读取。
- 无数据库 schema 变化。
- 无 Rust 原生扩展 API 变化。
- 计划文档只更新进度和下一批入口，不改变项目长期验证基线。

## 性能证据

- `test_batch123_p1b_total_closure_tracks_all_budget_facts` 要求 30 个 P1-B 命令的 `quality_gate_count` 和 `write_plan_count` 都为 0。
- 该测试要求除源文残留 validate/import 外，其余 P1-B 命令的候选扫描预算为单次；源文残留命令不再计入候选全量扫描。
- 插件源码 AST 相关命令只允许声明一次 plugin source AST scan，避免重复 AST 扫描重新进入默认路径。
- `test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope` 证明 workspace cold/stale 索引重建复用已有 `PluginSourceScan`，不在 TextScope 构建中重复扫描插件源码。
- `test_validate_agent_workspace_uses_warm_text_index_without_full_scope_build` 证明 warm index 下 validate 不调用 `TextScopeService.build`。
- `test_prepare_agent_workspace_mv_namebox_uses_native_payload` 证明 MV workspace 候选输出不调用旧 Python 候选扫描器。

## 验证结果

- `uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_mv_namebox_uses_native_payload`：4 passed。
- `uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_skips_inactive_heavy_branch_scans tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_mv_event_command_default`：2 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch123_p1b_total_closure_tracks_all_budget_facts tests/test_scan_budget.py::test_batch123_p1b_total_closure_static_old_path_boundary tests/test_scan_budget.py::test_batch123_p1b_total_closure_record_exists`：3 passed。
- `uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_mv_namebox_uses_native_payload tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_skips_inactive_heavy_branch_scans tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_mv_event_command_default`：6 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_current_budget_targets tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_tracks_current_state tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_record_exists tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_record_exists tests/test_scan_budget.py::test_batch123_p1b_total_closure_tracks_all_budget_facts tests/test_scan_budget.py::test_batch123_p1b_total_closure_static_old_path_boundary tests/test_scan_budget.py::test_batch123_p1b_total_closure_record_exists`：8 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- 文档敏感路径搜索：NO_MATCH。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

- 本批修改生产 Python 代码。
- 本批没有修改 Rust 原生代码、数据库 schema、CLI 外部契约或发布流程。
- 子代理只读审计指出 workspace 两个漏点；主线已按行为测试和静态保护落实修复。

## 剩余风险

- 本批按临时例外未跑全量 `uv run pytest`。
- 静态旧路径边界能防止 P1-B 关键入口回退到旧重型扫描，但不能替代对所有 30 个命令逐一运行大样本性能测试。
- cold/stale text index 下仍需要执行一次索引重建；本批目标是保证 workspace 默认正文范围读取和重建后的消费不再另起旧范围路径。
- P1-C 尚未收束，运行审计、术语、插件导出和最终计划验收仍在剩余 4 批中完成。

## 下一批入口

- 进入 7A：P1-C 运行审计命令组。
