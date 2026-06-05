# Rust Scope/Index Engine 批次 5D translate --max-items 索引前置记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` 的 warm index 前置检查局部收束：当持久 text index 有效时，正文翻译前置检查不再调用 `TextScopeService.build()` 重新构建完整 Python scope，而是从 text index rows 还原 workflow gate 可消费的最小 `TextScopeResult`。

本批不删除 workflow gate 本身，不跳过插件源码、非标准 data、外部规则、术语、占位符和可写性检查；仍保留必要的 `GameData` 加载给尚未迁移到 Rust/index summary 的高风险支线使用。

涉及文件：

- `app/application/handler.py`
- `app/text_index.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-010.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_does_not_build_full_scope_before_sql_limit`
- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_text_index_keeps_external_rule_workflow_gate`
- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_uses_text_index_after_full_workflow_gate`
- `tests/test_agent_toolkit_translation_limits.py::test_translate_max_items_cold_rebuilds_missing_text_index`
- `tests/test_scan_budget.py::test_batch10_translate_max_items_index_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_does_not_build_full_scope_before_sql_limit`：失败，旧实现仍在 warm index 前置检查阶段调用 `TextScopeService.build()`。
- `uv run pytest tests/test_scan_budget.py::test_batch10_translate_max_items_index_record_exists_and_is_linked_from_plan`：失败，批次 5D 验收记录尚不存在。

## 改动范围

- 新增 `text_index_items_to_scope()`，把持久 text index rows 还原为 workflow gate 可消费的最小 `TextScopeResult`。
- `translate --max-items` warm index 路径在读取 metadata 后：
  - 读取 `read_text_index_items()`。
  - 用 `text_index_items_to_scope()` 构造最小 scope。
  - 继续调用 `collect_workflow_gate_errors()`，但显式传入索引恢复的 scope，避免内部重建完整 Python scope。
  - 继续使用 `count_pending_text_index_items()` 和 `read_pending_text_index_items(limit=N)` 在 SQLite 层应用 `max_items`。

## 旧路径收束

- 本批删除 `translate --max-items` warm index 前置检查中的完整 `TextScopeService.build()` 调用。
- 索引缺失或失效时仍允许通过 `_rebuild_text_index_for_translation()` 执行一次索引重建。
- 插件源码、非标准 data 和外部规则等尚未迁移完成的 workflow gate 支线仍可使用完整 `GameData`；本批只收束重复 Python scope 构建。

## 外部契约变化

- CLI 参数、退出码和主要错误文案不变。
- `translate --max-items` warm index 成功路径继续返回 `text_index_status="used"`。
- 外部规则未确认时仍返回阻断摘要，不进入模型批次。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止 `TextScopeService.build()`，`translate --max-items` 仍能通过已满足的 workflow gate 并按 SQL limit 准备 3 条。
- 相邻 workflow gate 测试继续证明外部规则未确认时不会进入模型批次。
- translation limit 测试继续证明缺索引时可以 cold rebuild，并在 SQLite 层应用 `max_items`。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_does_not_build_full_scope_before_sql_limit`：1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_translation_limits.py`：7 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch10_translate_max_items_index_record_exists_and_is_linked_from_plan tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_translation_limits.py`：8 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：714 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- `translate --max-items` warm index 前置检查仍会加载完整 `GameData`，因为插件源码、非标准 data、外部规则和其它 workflow gate 支线尚未全部具备 Rust/index summary。
- `text_index_items_to_scope()` 只能还原进入 text index 的 active entries；未进入索引的 inactive rule hit 仍需要后续 Rust rule hit summary / evaluate_scope_gate 接管。
- 本批没有真实大样本耗时表；后续需要在 `Summer Stolen v0.2` 上区分 scope 构建、GameData 加载和输出/模型前置成本。

## 下一批入口

批次 5E：继续推进 `translate --max-items` 的完整 index gate，建议优先实现或接入 Rust `evaluate_scope_gate` / rule hit summary，覆盖插件源码、非标准 data、inactive rule hit、占位符候选、术语和可写性后，再移除 warm index 下的完整 `GameData` 加载。
