# Rust Scope/Index Engine 批次 5L translate --max-items warm index 前置完整 scope 还原收束记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 已预检分支的前置 gate 阶段：在 indexed workflow gate 已经能够消费外部规则、占位符和 text-scope metadata/summary 后，前置阶段不再读取全部 text index rows，也不再把 rows 还原成 `TextScopeResult`。

本批不迁移 Rust `evaluate_scope_gate` 的输入构造，不删除 `read_text_index_items()`，也不改变 pending 小批读取；当前 rows 读取仍保留在 workflow gate 通过之后，用于 Rust pending/quality gate 统计。

涉及文件：

- `app/application/flow_gate.py`
- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-018.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata`
- `tests/test_scan_budget.py::test_batch18_translate_max_items_skips_warm_index_scope_restore_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata`：1 failed，旧实现仍在 warm index 前置阶段调用 `text_index_items_to_scope()` 还原完整 `TextScopeResult`。
- `uv run pytest tests/test_scan_budget.py::test_batch18_translate_max_items_skips_warm_index_scope_restore_record_exists_and_is_linked_from_plan`：1 failed，批次 5L 验收记录尚不存在。

## 改动范围

- `collect_indexed_workflow_gate_errors()` 的 `scope` 参数改为可选：
  - 调用方传入 `placeholder_gate_errors` 和 `text_scope_gate_errors` 时，不再要求完整 `TextScopeResult`。
  - 缺少占位符或 text-scope 预生成 gate errors 且没有 `scope` 时，显式抛出错误，避免静默绕过 gate。
- `translate --max-items` warm index 已预检分支：
  - 前置 gate 阶段只读取 metadata、外部规则确认状态、占位符 metadata 和 text-scope summary。
  - 不再提前调用 `session.read_text_index_items()`。
  - 不再调用 `text_index_items_to_scope()`。
  - workflow gate 通过后，才读取全部 index rows 供 Rust `evaluate_scope_gate` 使用。

## 旧路径收束

- 本批删除当前有效 warm index 已预检前置 gate 对完整 `TextScopeResult` 还原的依赖。
- source branch 未预检的 fallback 路径仍会读取全部 index rows 并还原 scope，因为它仍需要完整 `collect_workflow_gate_errors()`。
- Rust `evaluate_scope_gate` 当前仍需要 index rows 输入；下一批继续收束这个读取点。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- warm index 已预检路径的阻断语义不变；只改变内部事实来源和读取时机。
- 如果调用 indexed workflow gate 时缺少必要的预生成 gate errors 且没有完整 scope，会显式抛出内部错误，不静默放行。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试在 warm index 已预检路径中禁止 `text_index_items_to_scope()`，`translate --max-items` 仍能准备 3 条小批翻译。
- 前置 gate 失败时不再需要为了判断 workflow gate 而先构造完整 `TextScopeResult`。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata`：RED 阶段 1 failed，原因是旧实现调用 `text_index_items_to_scope()`；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch18_translate_max_items_skips_warm_index_scope_restore_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5L 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch18_translate_max_items_skips_warm_index_scope_restore_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary tests/test_scan_budget.py::test_batch18_translate_max_items_skips_warm_index_scope_restore_record_exists_and_is_linked_from_plan`：6 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：730 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- workflow gate 通过后，`translate --max-items` 仍会读取全部 index rows 以构造 Rust `evaluate_scope_gate` 输入；下一批应继续把这个输入收束到 SQLite summary 或更小的 Rust gate payload。
- source branch 未预检 fallback 仍保留完整 scope 还原，符合当前安全边界；后续只有在等价 metadata 可证明时再迁移。
- 本批未补真实大样本 benchmark，性能收益以路径删除测试作为证据。

## 下一批入口

批次 5M：建议推进 `translate --max-items` Rust gate 输入行读取继续收束，优先评估 `evaluate_text_index_scope_gate()` 是否能从 SQLite summary、translation path 集合和 pending 统计直接生成结果，减少 workflow gate 通过后的全部 index rows 读取。
