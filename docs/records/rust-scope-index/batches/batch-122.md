# Rust Scope/Index Engine 批次 122 验收记录

## 本批范围

- 批次编号：6CM。
- 范围：P1-B 源文残留 validate/import 薄适配与旧路径收束。
- 命令：`validate-source-residual-rules`、`import-source-residual-rules`。
- 目标：两条命令保留 Python 输入解析、报告渲染和数据库事务，但不再为了校验源文残留例外规则而构建完整当前文本范围或全量读取所有已保存译文。

## RED/GREEN

- RED：新增 `tests/test_agent_toolkit_rule_import.py::test_source_residual_rule_commands_use_warm_text_index_without_full_scope_build`，旧实现命中 warm index 后仍调用 `TextScopeService` 或 `read_translated_items` 时失败。
- RED：`tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_record_exists` 在记录缺失时失败。
- GREEN：`_build_source_residual_rule_records` 解析规则后，只在存在 position rules 时检查 text index；warm index 下按规则路径读取 `read_text_index_items_by_paths` 和 `read_translated_items_by_paths`。
- GREEN：allowed_terms 只存在于目标路径已保存译文中的场景也能通过，证明没有漏读目标译文。

## 改动范围

- `app/agent_toolkit/services/core.py`：`_build_source_residual_rule_records` 改为索引薄适配；使用 `detect_text_index_invalidations` 检查索引状态；删除命令内 `_load_translation_source_game_data`、`_extract_active_translation_data_map` 和全量 `read_translated_items` 路径。
- `tests/test_agent_toolkit_rule_import.py`：新增源文残留规则命令旧路径防回退测试。
- `tests/test_scan_budget.py`：新增 6CM 静态边界和记录保护测试。
- `docs/plans/completed/rust-scope-index-engine.md`：新增 batch-122 记录链接，并把下一批入口推进到 6CN。

## 旧路径收束

- warm index 下不再调用 `TextScopeService.build()`。
- warm index 下不再调用 `read_translated_items` 全量读取所有已保存译文。
- position rule 校验只按规则里出现的定位路径查询 `read_text_index_items_by_paths` 和 `read_translated_items_by_paths`。
- structural rule 保持现有输入校验和 Rust regex contract 预检，不触发文本范围构建。

## 外部契约变化

- CLI 参数、stdout Agent JSON 字段、错误码和用户可见语义保持不变。
- cold 或 stale index 时可以触发一次 `rebuild_text_index(include_write_probe=False)`；重建失败会显式返回源文残留例外规则不可导入错误。
- 规则数据库事务仍由 `import-source-residual-rules` 原服务入口执行。

## 性能证据

- warm index 路径由目标行为测试固定：禁止 `TextScopeService` 和全量 `read_translated_items`。
- 两条命令在常规 validate 后 import 的使用方式下，不再重复完整 `GameData` 加载和完整 scope 构建。
- 大规模输入时，position rule 的校验成本随规则路径数量增长，不再随当前游戏全部文本数量增长。

## 验证结果

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_source_residual_rule_commands_use_warm_text_index_without_full_scope_build`：1 passed。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_source_residual_rule_commands_use_warm_text_index_without_full_scope_build tests/test_agent_toolkit_quality_report.py::test_validate_source_residual_rules_rejects_rust_incompatible_structural_regex tests/test_agent_toolkit_quality_report.py::test_quality_report_structural_source_residual_rule_is_line_scoped tests/test_agent_toolkit_quality_report.py::test_quality_report_errors_on_corrupt_source_residual_rule tests/test_agent_toolkit_manual_import.py::test_manual_translation_uses_source_residual_exception_rules tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_current_budget_targets tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_tracks_current_state tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_record_exists tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_record_exists`：10 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_tracks_current_boundary`：通过，已包含在本批 10 项目标验证中。
- `uv run pytest tests/test_scan_budget.py::test_batch122_p1b_source_residual_adapter_record_exists`：通过，已包含在本批 10 项目标验证中。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 文档敏感路径搜索：NO_MATCH。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

- 本批修改生产 Python 代码。
- 本批没有修改 Rust 原生代码、数据库 schema、CLI 参数或发布流程。
- 子代理审计建议的 SQLite text index 快路径已落实到服务层。

## 剩余风险

- 本批未跑全量 Python pytest。
- cold index 分支依赖现有 `rebuild_text_index` 能力；本批目标测试重点固定 warm index 快路径。
- 下一批仍需做 P1-B 工作区和规则命令总收束，统一复核 30 个 P1-B 命令预算、旧路径、记录和剩余风险。

## 下一批入口

- 进入 6CN：P1-B 工作区和规则命令总收束。
