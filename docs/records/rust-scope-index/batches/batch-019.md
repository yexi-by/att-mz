# Rust Scope/Index Engine 批次 5M translate --max-items SQL pending 总数收束记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 已预检路径在 workflow gate 通过后的总 pending 统计：`total_pending_count` 改为直接使用 SQLite `count_pending_text_index_items()`，不再为了一个 pending 总数读取全部 text index rows，也不再调用 Rust `evaluate_scope_gate`。

本批不修改 `evaluate_text_index_scope_gate()` 本身，不迁移其他命令，不改变 `read_pending_text_index_items(limit=N)` 小批读取，也不改变 source branch 未预检 fallback 的完整 scope 路径。

涉及文件：

- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-019.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows`
- `tests/test_scan_budget.py::test_batch19_translate_max_items_sql_pending_count_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows`：1 failed，旧实现仍在 workflow gate 通过后调用 `session.read_text_index_items()`。
- `uv run pytest tests/test_scan_budget.py::test_batch19_translate_max_items_sql_pending_count_record_exists_and_is_linked_from_plan`：1 failed，批次 5M 验收记录尚不存在。

子代理只读审计：

- 子代理确认旧实现中当前 handler 只消费 `evaluate_text_index_scope_gate()` 的 `pending_count` 字段；本批已删除该 handler 对这个函数的直接依赖。
- SQLite `count_pending_text_index_items()` 与 Rust pending 统计在当前语义下等价：都统计当前 text index 范围内 writable 且没有已保存译文的条目。
- 最新质量错误路径只影响 Rust 返回的 quality gate 字段，不参与 pending 计数；当前 handler 没有消费这些字段。

## 改动范围

- `_translate_text_from_warm_index()` 中 workflow gate 通过后的总 pending 统计改为 `await session.count_pending_text_index_items()`。
- 删除该 handler 对 `evaluate_text_index_scope_gate()` 的直接依赖。
- 删除该 handler 为 pending 总数读取全部 text index rows 的路径。
- 保留 `read_pending_text_index_items(limit=run_limits.max_items)`，继续由 SQL 层应用 `--max-items`。

## 旧路径收束

- 本批删除 warm index 已预检翻译路径中“读取全部 index rows -> 构造 Rust scope gate payload -> 只取 pending_count”的旧路径。
- `evaluate_text_index_scope_gate()` 保留给其他单元契约和后续可能需要完整 gate 结果的路径。
- source branch 未预检 fallback 仍在 full workflow gate 中读取 rows 并还原 scope。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- `total_pending_count` 语义不变：当前索引范围内未保存译文且可写的总数，不受 `--max-items` 限制。
- `pending_count` 仍来自 `read_pending_text_index_items(limit=N)` 后的小批数量。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试先保存 1 条译文，再禁止 `TargetGameSession.read_text_index_items()` 和 `app.text_index.evaluate_native_scope_gate()`，`translate --max-items` 仍能得到扣除已保存译文后的 `total_pending_count` 并准备 3 条小批翻译。
- workflow gate 通过后的总 pending 统计改为单条 SQLite COUNT 查询，避免全量 rows 读取和 Rust payload 构造。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows`：RED 阶段 1 failed，原因是旧实现仍调用 `session.read_text_index_items()`；GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows`：增强已保存译文场景后 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch19_translate_max_items_sql_pending_count_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5M 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch19_translate_max_items_sql_pending_count_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows tests/test_scan_budget.py::test_batch19_translate_max_items_sql_pending_count_record_exists_and_is_linked_from_plan`：6 passed。

完整门禁：

- `uv run basedpyright`：首次 1 error，原因是测试中直接对 `JsonValue` 做减法；补充 `isinstance(indexed_count, int)` 收窄后，复跑 0 errors, 0 warnings, 0 notes。
- `uv run pytest`：731 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- 本批没有删除 `evaluate_text_index_scope_gate()`，因为它仍有单元测试和潜在复用价值；后续如确认无生产入口，可单独批次处理。
- source branch 未预检 fallback 仍保留完整 rows 读取和 full workflow gate。
- 本批没有新增大样本 benchmark，性能收益以路径删除测试作为证据。

## 下一批入口

批次 5N：建议推进 `translate --max-items` 启动运行记录前置统计继续收束，优先审计 `_translate_text_from_warm_index()` 中 workflow gate 通过后、正式写入 run 记录前是否还有不必要的全量统计、重复查询或可延后的读取。
