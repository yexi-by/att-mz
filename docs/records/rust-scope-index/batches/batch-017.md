# Rust Scope/Index Engine 批次 5K translate --max-items text-scope gate 元信息复用记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 已预检分支里的 text-scope gate：当前文本范围的过期插件规则数量、不可写条目数量和规则命中文本未进入可写范围数量，改为从持久索引的 scope/domain summary 生成 workflow gate errors。

本批不迁移普通 cold/full workflow gate，不改变写回探针逻辑，不删除 `text_index_items_to_scope()` 的 warm index 全量还原；这些仍保留到下一批继续收束。

涉及文件：

- `app/application/flow_gate.py`
- `app/application/handler.py`
- `app/text_index.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-017.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata`
- `tests/test_scan_budget.py::test_batch17_translate_max_items_text_scope_gate_metadata_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata`：1 failed，旧实现仍调用 `_text_scope_gate_errors()`。
- `uv run pytest tests/test_scan_budget.py::test_batch17_translate_max_items_text_scope_gate_metadata_record_exists_and_is_linked_from_plan`：1 failed，批次 5K 验收记录尚不存在。

## 改动范围

- `collect_indexed_workflow_gate_errors()` 新增可选 `text_scope_gate_errors` 参数；未传入时保留旧完整 scope gate 行为。
- 新增 `collect_text_index_scope_gate_errors()`：
  - 从 `text_index_scope_summary` 读取 `stale_rule_count` 和 `unwritable_count`。
  - 从 `text_index_domain_summary` 汇总 `inactive_rule_hit_count`。
  - 用现有 `stale_plugin_rules`、`coverage_unwritable`、`rule_hits_unwritable` code 和用户文案生成 workflow gate errors。
  - scope summary 缺失时显式要求重新运行 `rebuild-text-index`。
- `translate --max-items` warm index 已预检分支传入索引摘要生成的 text-scope gate errors。

## 旧路径收束

- 本批删除当前有效 warm index 已预检分支对 `_text_scope_gate_errors()` 的依赖。
- cold/full workflow gate 仍使用 `_text_scope_gate_errors()`，因为该路径仍需要完整 `TextScopeResult`。
- `translate --max-items` warm index 路径仍会先读取全部 index rows 并还原最小 `TextScopeResult`；本批只是让 text-scope gate 不再消费它，下一批继续收束这段全量还原。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- `translate --max-items` 在有效 warm index 下仍保持 text-scope gate 阻断语义：过期插件规则、当前不可写条目和规则命中文本未进入可写范围都会继续阻断。
- 旧索引如果缺少 scope summary，不静默回退到 Python gate，而是显式提示重新运行 `rebuild-text-index`。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试在 text index 已重建后禁止 `_text_scope_gate_errors()`，`translate --max-items` 仍能准备 3 条小批翻译。
- text-scope gate 的计数来源改为 SQLite summary，不再遍历还原后的完整 `TextScopeResult.entries`。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata`：RED 阶段 1 failed，原因是旧实现仍调用 `_text_scope_gate_errors()`；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch17_translate_max_items_text_scope_gate_metadata_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5K 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch17_translate_max_items_text_scope_gate_metadata_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_text_scope_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary tests/test_scan_budget.py::test_batch17_translate_max_items_text_scope_gate_metadata_record_exists_and_is_linked_from_plan`：6 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：729 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- `text_index_domain_summary.inactive_rule_hit_count` 当前来自 Rust summary 的规则命中统计；如果同一文本位置被多条外部规则命中，计数可能按命中项而不是唯一位置计数。后续批次应把 Rust summary 的这个字段收敛为唯一 location 语义或补充更精确字段。
- warm index 路径仍会在 gate 前读取全部 index rows 并还原 `TextScopeResult`，下一批应继续移除这段已经不再被 indexed gate 需要的还原。
- 写回探针错误仍只存在完整 scope 路径；当前 `translate --max-items` 的 index rebuild 默认不启用写回探针，本批未改变该行为。

## 下一批入口

批次 5L：建议推进 `translate --max-items` warm index 前置完整 scope 还原收束，优先把已预检路径改为只读 metadata、summary 和必要 pending rows，把全部 index rows 读取延后或限定在 Rust gate 需要的最小输入内。
