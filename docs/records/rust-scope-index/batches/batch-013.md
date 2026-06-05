# Rust Scope/Index Engine 批次 5G translate --max-items indexed workflow gate 去除 GameData 加载记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 前置检查的完整 `GameData` 加载：当持久 text index 有效，并且索引元信息包含 5F 写入的插件源码 / 非标准 data gate 预检标记时，翻译前置检查直接走 indexed-only workflow gate，不再加载完整翻译源 `GameData`。

本批不删除旧索引兜底路径。缺少预检标记的旧索引仍会加载 `GameData` 并执行完整插件源码、非标准 data 和外部规则支线，避免把历史索引误判为已完成高风险预检。

涉及文件：

- `app/application/flow_gate.py`
- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-013.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck`
- `tests/test_scan_budget.py::test_batch13_translate_max_items_indexed_gate_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck`：1 failed，旧实现仍在 warm index 前置检查阶段调用 `_load_session_game_data()`。
- `uv run pytest tests/test_scan_budget.py::test_batch13_translate_max_items_indexed_gate_record_exists_and_is_linked_from_plan`：1 failed，批次 5G 验收记录尚不存在。

## 改动范围

- 新增 `collect_indexed_workflow_gate_errors()`：
  - 消费已由调用方提供的插件源码 gate、非标准 data gate 和外部规则 gate 结果。
  - 继续检查术语表一致性、普通/结构化占位符审查状态和 text-scope 错误。
  - 不接收 `GameData`，用于已由 text index 和预检标记覆盖 GameData 支线的 warm index 路径。
- `translate --max-items` warm index 路径调整为：
  - 先读取 text index rows 并还原最小 `TextScopeResult`。
  - 先读取 text index metadata 中的外部规则 gate 结果和源码支线预检标记。
  - 有预检标记时走 `collect_indexed_workflow_gate_errors()`，不加载完整 `GameData`。
  - 缺少预检标记时保留完整 `GameData` 兜底路径。

## 旧路径收束

- 本批删除当前有效预检 warm index 下的完整 `_load_session_game_data(..., include_plugin_source_files=True)` 调用。
- 旧索引、测试直写索引或缺少源码支线预检标记的索引仍保留完整 `GameData` 加载和旧 gate 路径。
- 本批没有删除 `collect_workflow_gate_errors()`；普通 CLI、质量报告、旧索引兜底和其它需要完整游戏上下文的入口仍使用它。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- `translate --max-items` warm index 命中且预检标记有效时仍报告 `text_index_status="used"`，并继续在 SQLite 层应用 `max_items`。
- 缺少预检标记的旧索引仍按旧行为做完整前置检查，不静默降级为通过。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止 `_load_session_game_data()`，小批翻译仍能按 SQL limit 准备 3 条，证明预检索引路径不再加载完整 `GameData`。
- 相邻测试继续覆盖外部规则 metadata、源码支线预检、scope 从索引恢复和 text index 失效检测。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck`：1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py tests/test_workflow_gate.py tests/test_text_index.py`：16 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_scan_budget.py::test_batch13_translate_max_items_indexed_gate_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5G 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch13_translate_max_items_indexed_gate_record_exists_and_is_linked_from_plan`：1 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：721 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- 本批只移除已预检 warm index 下的完整 `GameData` 加载；`translate --max-items` 仍未接入 Rust `evaluate_scope_gate` 的完整 compact summary。
- 占位符审查仍在 Python 中基于索引还原的文本扫描；后续需要纳入 Rust/index summary，避免大样本下 Python 扫描成为新热点。
- 质量 gate、写回前置检查和其它命令入口仍需继续向同一个 Rust/index 事实来源收束。

## 下一批入口

批次 5H：建议接入 Rust `evaluate_scope_gate` 的最小 workflow gate summary，优先覆盖 `translate --max-items` 的占位符审查、可写路径和质量 gate compact 结果，继续减少 Python 大规模扫描。
