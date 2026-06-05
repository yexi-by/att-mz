# Rust Scope/Index Engine 批次 5E translate --max-items 外部规则 gate 索引化记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 前置检查的外部规则 gate 支线：当持久 text index 有效，并且 metadata 已保存当前索引的外部规则 scope hash 时，翻译前置检查直接消费索引元信息生成插件规则、事件指令规则、Note 标签规则和 MV 虚拟名字框规则的阻断结果，不再重新从完整 `GameData` 扫描这些外部规则范围。

本批不删除完整 `GameData` 加载，也不接管插件源码、非标准 data、术语、占位符、text-scope 错误和可写性等其它 workflow gate 支线；这些仍留给后续 Rust/index summary 或 `evaluate_scope_gate` 批次继续收束。

涉及文件：

- `app/application/flow_gate.py`
- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-011.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_metadata_external_rule_gate`
- `tests/test_scan_budget.py::test_batch11_translate_max_items_external_gate_index_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_metadata_external_rule_gate`：失败，旧实现仍会调用完整 `_external_rule_gate_errors()`，说明 warm index 外部规则 gate 没有消费索引元信息。
- `uv run pytest tests/test_scan_budget.py::test_batch11_translate_max_items_external_gate_index_record_exists_and_is_linked_from_plan`：失败，批次 5E 验收记录尚不存在。

## 改动范围

- `collect_workflow_gate_errors()` 新增可选参数 `external_rule_gate_errors`：
  - 未传入时保持原行为，继续运行完整外部规则 gate。
  - 传入时直接复用调用方给出的外部规则 gate 结果，避免在 warm index 路径重复扫描外部规则范围。
- `translate --max-items` warm index 路径读取有效 text index 后：
  - 继续用 `text_index_items_to_scope()` 从索引行恢复最小 `TextScopeResult`。
  - 调用 `collect_text_index_external_rule_gate_errors()`，从 text index metadata 生成外部规则缺失阻断。
  - 把预计算的外部规则 gate 结果传入 `collect_workflow_gate_errors()`。

## 旧路径收束

- 本批收束 `translate --max-items` warm index 前置检查中的外部规则范围重复扫描。
- 索引缺失、索引失效或其它非 warm index 路径仍保留完整外部规则 gate。
- 插件源码、非标准 data、术语、占位符、text-scope 错误和可写性 gate 尚未迁移；因此本批不声称 `translate --max-items` 已经完全移除 `GameData` 依赖。

## 外部契约变化

- CLI 参数、退出码、stdout JSON 字段和主要错误文案不变。
- 外部规则未确认时仍会阻断翻译，并返回包含“插件规则”“事件指令规则”“Note 标签规则”等中文摘要的 `blocked_reason`。
- warm index 命中时仍报告 `text_index_status="used"`，且不会进入模型批次。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止完整 `_external_rule_gate_errors()` 被调用，仍能从索引元信息产生外部规则缺失阻断。
- 相邻测试继续禁止 `TextScopeService.build()`，证明 `translate --max-items` warm index 前置检查的 scope 构建和外部规则 gate 都已转向索引事实。
- SQL 层 `max_items` 读取路径没有变化，继续由上一批测试固定。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_metadata_external_rule_gate`：1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_translation_limits.py`：8 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_scan_budget.py::test_batch11_translate_max_items_external_gate_index_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5E 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch11_translate_max_items_external_gate_index_record_exists_and_is_linked_from_plan`：1 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：716 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- `translate --max-items` warm index 前置检查仍会加载完整 `GameData`，因为插件源码、非标准 data、术语、占位符、text-scope 错误和可写性 gate 还没有全部迁移到 Rust/index summary。
- `collect_workflow_gate_errors()` 现在允许调用方传入预计算的外部规则 gate 结果；后续新增调用点必须确保只在可信索引元信息有效时使用。
- 本批没有真实大样本耗时表；后续需要在实际游戏上区分 `GameData` 加载、插件源码扫描、非标准 data 扫描和模型批次准备成本。

## 下一批入口

批次 5F：继续推进 `translate --max-items` 的插件源码和非标准 data gate 索引化，建议优先把插件源码 residual 检查与非标准 data 规则缺失检查接入 Rust/index summary 或 `evaluate_scope_gate`，进一步移除 warm index 下的完整 `GameData` gate 依赖。
