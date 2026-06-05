# Rust Scope/Index Engine 批次 5F translate --max-items 源码支线 gate 预检索引化记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 前置检查的插件源码和非标准 data 支线 gate。当前持久索引还没有保存足以完整重放这两支候选覆盖检查的明细，因此本批不伪造纯 metadata 判断，而是建立更安全的预检索引契约：

- `rebuild-text-index` 和 `translate --max-items` 自动重建索引在写入 text index 前，必须同时通过插件源码 gate 和非标准 data gate。
- 写入索引时记录“插件源码 gate / 非标准 data gate 已预检通过”标记。
- warm index 命中时，只有索引元信息带有该预检标记，才把这两支 gate 的预计算结果作为空错误注入 workflow gate，避免重新扫描插件源码 AST 和非标准 data 文件。
- 旧索引、低层测试直接写出的索引或缺少标记的索引不被当成已预检通过，仍会走完整 gate。

本批不删除完整 `GameData` 加载，也不接管术语、占位符、text-scope 错误、可写性和完整 Rust `evaluate_scope_gate`；这些仍留给下一批继续收束。

涉及文件：

- `app/application/flow_gate.py`
- `app/application/handler.py`
- `app/agent_toolkit/services/text_index.py`
- `app/text_index.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-012.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates`
- `tests/test_workflow_gate.py::test_rebuild_text_index_blocks_unreviewed_high_risk_nonstandard_data`
- `tests/test_scan_budget.py::test_batch12_translate_max_items_source_branch_gate_index_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_workflow_gate.py::test_rebuild_text_index_blocks_unreviewed_high_risk_nonstandard_data`：2 failed。warm index 仍调用插件源码 gate；高风险非标准 data 未归类时 `rebuild-text-index` 仍返回 ok。
- `uv run pytest tests/test_scan_budget.py::test_batch12_translate_max_items_source_branch_gate_index_record_exists_and_is_linked_from_plan`：1 failed，批次 5F 验收记录尚不存在。

## 改动范围

- `collect_workflow_gate_errors()` 新增可选参数：
  - `plugin_source_rule_gate_errors`
  - `nonstandard_data_rule_gate_errors`
- 调用方传入预计算结果时，workflow gate 直接复用该结果；未传入时保持原行为，继续运行完整插件源码和非标准 data gate。
- 新增 `collect_nonstandard_data_workflow_gate_errors()`，让重建索引入口可显式复用同源非标准 data gate。
- `rebuild-text-index` Agent 服务和 `translate --max-items` 自动重建索引在写入持久 text index 前，同时执行插件源码 gate 与非标准 data gate；通过后写入预检标记。
- `translate --max-items` warm index 路径通过 `text_index_source_branch_gates_prechecked()` 判断索引是否有预检标记；有标记时跳过两支旧扫描 gate。

## 旧路径收束

- 本批收束正常 Agent 重建索引后，`translate --max-items` warm index 前置检查中插件源码 gate 与非标准 data gate 的重复扫描。
- 缺少预检标记的旧索引不跳过旧 gate，避免把历史索引误认为已完成源码支线预检。
- 本批新增了非标准 data gate 写索引前阻断，防止未归类高风险非标准 data 被保存成可直接 warm 使用的索引。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要成功路径不变。
- `rebuild-text-index` 在发现未归类高风险非标准 data 时会返回 error，错误码为 `nonstandard_data_high_risk`；这是把原先 translate 前置硬闸提前到索引写入前。
- `translate --max-items` warm index 命中且预检标记有效时仍报告 `text_index_status="used"`，并继续在 SQLite 层应用 `max_items`。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和路径收束：

- warm index 测试禁止 `_plugin_source_rule_gate_errors()` 和 `_nonstandard_data_rule_gate_errors()`，小批翻译仍能按 SQL limit 准备 3 条，证明两支重复 gate 扫描已被预检标记替代。
- 非标准 data 高风险测试证明索引写入前会阻断未归类风险，避免 warm index 后续跳过 gate 时丢失风险。
- 相邻 workflow/text-index 测试覆盖外部规则、scope 恢复和索引失效行为。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_workflow_gate.py::test_rebuild_text_index_blocks_unreviewed_high_risk_nonstandard_data`：2 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py tests/test_workflow_gate.py tests/test_text_index.py`：15 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_scan_budget.py::test_batch12_translate_max_items_source_branch_gate_index_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5F 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch12_translate_max_items_source_branch_gate_index_record_exists_and_is_linked_from_plan`：1 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：719 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- warm index 前置检查仍会加载完整 `GameData`，因为术语、占位符、text-scope 错误、可写性和后续质量 gate 尚未全部接入 Rust `evaluate_scope_gate`。
- 本批的预检标记是过渡契约，不等同于 Rust 已保存插件源码/非标准 data 的完整候选明细；后续仍需要由 Rust/index summary 或 `evaluate_scope_gate` 输出可解释的 gate 结果。
- 本批没有真实大样本耗时表；后续需要在实际游戏上区分 `GameData` 加载、剩余占位符扫描和模型批次准备成本。

## 下一批入口

批次 5G：建议推进 `translate --max-items` 的术语、占位符和可写性 gate 向 Rust `evaluate_scope_gate` / index summary 收束，优先减少 warm index 下仍需要完整 `GameData` 的前置检查支线。
