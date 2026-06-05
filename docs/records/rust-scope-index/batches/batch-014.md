# Rust Scope/Index Engine 批次 5H translate --max-items Rust evaluate_scope_gate 最小接入记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 路径的 Rust `evaluate_scope_gate` 最小接入：持久 text index 有效时，翻译前置流程把索引项、已保存译文路径和最新质量错误路径组装成 Rust gate payload，并用 Rust 返回的 `pending_count` 作为本次报告里的总 pending 摘要。

本批不把 Rust `workflow_gate`、`quality_gate` 或 `writable_location_paths` 结果提升为阻断条件。现有 Python indexed workflow gate 仍负责术语、占位符和文本范围错误检查；SQLite `read_pending_text_index_items(limit=N)` 仍负责按 `max_items` 读取实际翻译批次列表。

涉及文件：

- `app/text_index.py`
- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-014.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary`
- `tests/test_scan_budget.py::test_batch14_translate_max_items_rust_scope_gate_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary`：1 failed，旧实现没有调用 `app.text_index.evaluate_native_scope_gate`，测试中的 fake gate 计数不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch14_translate_max_items_rust_scope_gate_record_exists_and_is_linked_from_plan`：1 failed，批次 5H 验收记录尚不存在。

## 改动范围

- 新增 `evaluate_text_index_scope_gate()`：
  - 读取主翻译表中的已保存译文路径。
  - 读取最新翻译运行中的质量错误路径。
  - 把 `TextIndexItemRecord` 转换为 Rust `evaluate_scope_gate` 所需的 entries payload。
  - 返回 `NativeScopeGateResult`，作为后续 gate 继续收束的薄适配层。
- `translate --max-items` warm index 路径调整为：
  - 继续用 indexed workflow gate 做前置阻断。
  - 通过 `evaluate_text_index_scope_gate()` 取得 Rust compact summary。
  - 使用 Rust `pending_count` 填充 `TextTranslationSummary.total_pending_count`。
  - 继续通过 SQLite `read_pending_text_index_items(limit=max_items)` 准备实际小批翻译输入。

## 旧路径收束

- 本批删除 `translate --max-items` warm index 总 pending 摘要对 `session.count_pending_text_index_items()` 的直接依赖。
- SQLite pending list 快路径保留，这是计划中明确的权威入口，不属于要删除的旧 Python 全量扫描路径。
- 其它命令中的 pending count、质量报告统计和写回 gate 尚未迁移，仍按各自已有路径运行。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- `total_pending_count` 的含义不变，来源从 SQLite count 查询收束到 Rust `evaluate_scope_gate` compact summary。
- `pending_count` 仍表示本次按 `max_items` 准备发送给模型的条目数，不受 Rust fake summary 或总量摘要影响。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试用 fake Rust gate 返回特殊 `pending_count=12345`，`translate --max-items` 最终报告采纳该值，同时实际批次仍被 SQL limit 限制为 3 条。
- 相邻 warm index 测试继续证明当前路径不构建完整 Python scope、不加载完整 `GameData`，并保留源码支线预检和 SQL limit 行为。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary`：RED 阶段 1 failed，原因是旧实现没有调用 Rust gate；GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_uses_text_index_after_full_workflow_gate tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_does_not_build_full_scope_before_sql_limit tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary`：5 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch14_translate_max_items_rust_scope_gate_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5H 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch14_translate_max_items_rust_scope_gate_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary tests/test_scan_budget.py::test_batch14_translate_max_items_rust_scope_gate_record_exists_and_is_linked_from_plan`：2 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：723 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- Rust `workflow_gate`、`quality_gate` 和 `writable_location_paths` 当前只通过返回结果暴露，尚未替代 Python indexed workflow gate 和写回前置检查。
- `evaluate_text_index_scope_gate()` 当前需要读取全部 text index rows 和已保存译文路径，仍不是大样本下的最终形态；下一步应把占位符、质量 gate 和可写范围继续向 Rust/index summary 收束，减少 Python 侧大集合组装。
- 质量错误路径只取最新翻译运行，符合当前写回 gate 语义；如果后续质量报告需要跨运行视角，应单独定义契约，不能混入本批。

## 下一批入口

批次 5I：建议继续推进 `translate --max-items` 的占位符审查和 quality gate 索引化，优先消费 Rust `workflow_gate` / `quality_gate` / `writable_location_paths`，减少 Python indexed workflow gate 中的大规模文本扫描。
