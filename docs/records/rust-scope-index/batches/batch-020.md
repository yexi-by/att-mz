# Rust Scope/Index Engine 批次 5N translate --max-items no-pending 小批读取早退记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 已预检路径在 workflow gate 通过后的 no-pending 早退顺序：当 SQLite pending 总数为 0 时，直接返回“正文译文已全部存在”，不再读取 `read_pending_text_index_items(limit=N)` 小批 rows，也不进入术语加载、去重、批次构建或翻译运行记录写入。

本批不修改 pending SQL 语义，不改变 `--max-items` 对仍有 pending 文本时的小批读取，不改 source branch 未预检 fallback，也不迁移术语加载或模型调用路径。

涉及文件：

- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-020.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_pending_rows_when_sql_pending_zero`
- `tests/test_scan_budget.py::test_batch20_translate_max_items_no_pending_early_return_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_pending_rows_when_sql_pending_zero`：1 failed，旧实现仍在 `total_pending_count == 0` 时调用 `read_pending_text_index_items(limit=3)`。
- `uv run pytest tests/test_scan_budget.py::test_batch20_translate_max_items_no_pending_early_return_record_exists_and_is_linked_from_plan`：1 failed，批次 5N 验收记录尚不存在。

## 改动范围

- `_translate_text_from_warm_index()` 先判断 `metadata.item_count == 0`，避免无提取文本时继续做 pending 查询。
- 通过 `count_pending_text_index_items()` 得到总 pending 后，若总数为 0，直接返回 summary，并保留最终进度回调。
- 只有总 pending 大于 0 时，才读取 `read_pending_text_index_items(limit=run_limits.max_items)`，并继续转换为翻译数据、加载术语、去重、构建批次和进入翻译运行阶段。
- 新增行为测试先把 warm index 中所有 pending 文本保存为译文，再禁止 `read_pending_text_index_items()` 和 `_run_prepared_translation_batches()`，固定 no-pending 早退不会触发小批 rows 读取或运行记录创建。

## 旧路径收束

- 删除 no-pending 分支前的无效小批 pending rows 读取。
- 删除 no-pending 分支前的无效 `text_index_items_to_translation_data_map()` 和 `count_translation_items()` 调用。
- 删除 no-pending 分支进入后续翻译批次准备的可能性；测试同时断言不会创建 translation run。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要用户文案不变。
- `total_pending_count == 0` 时的 summary 仍返回 `pending_count=0`、`total_pending_count=0`、`batch_count=0`、`success_count=0`、`error_count=0`。
- `text_index_status` 和 `text_index_rebuild_summary` 保持原语义。
- 仍有 pending 文本时，`pending_count` 继续受 `--max-items` 限制。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试禁止 no-pending 场景调用 `read_pending_text_index_items()`，确认 pending 总数为 0 时不再执行小批 rows 查询。
- 行为测试禁止进入 `_run_prepared_translation_batches()`，并结合当前代码顺序确认 no-pending 场景不会加载术语、构建批次或写入翻译运行记录。
- 代码顺序从“总 pending 统计后立即读取小批 rows”改为“总 pending 为 0 时立即返回”，避免对已全部保存译文的项目做不必要 SQL rows 读取和 Python 翻译数据组装。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_pending_rows_when_sql_pending_zero`：RED 阶段 1 failed，原因是旧实现仍调用 `read_pending_text_index_items(limit=3)`；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch20_translate_max_items_no_pending_early_return_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5N 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch20_translate_max_items_no_pending_early_return_record_exists_and_is_linked_from_plan`：GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_pending_rows_when_sql_pending_zero tests/test_scan_budget.py::test_batch20_translate_max_items_no_pending_early_return_record_exists_and_is_linked_from_plan`：7 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：733 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- 本批没有迁移术语加载和批次构建本身，只确保 no-pending 场景不会进入这些路径。
- source branch 未预检 fallback 仍保留完整 rows 读取和 full workflow gate。
- 本批没有新增大样本 benchmark，性能收益以路径删除测试作为证据。

## 下一批入口

批次 5O：建议推进 `translate --max-items` 术语加载和批次构建前置继续收束，优先审计仍有 pending 文本时，术语索引加载、去重统计和批次构建是否可以更严格地只作用于 `--max-items` SQL 小批结果，并确认不会再次引入全量文本范围或候选扫描。
