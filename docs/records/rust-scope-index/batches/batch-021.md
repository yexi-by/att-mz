# Rust Scope/Index Engine 批次 5O translate --max-items max-batches 批次构建收束记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 路径在仍有 pending 文本时的批次构建边界：`--max-batches` 不再等到所有 pending 小批都构建完成后才切片，而是在 `build_translation_batches()` 构建过程中达到上限即停止，避免为后续会被丢弃的来源文件继续组装 prompt 批次。

本批不改变 SQL pending 读取语义，不改变 `--max-items` 的小批 rows 限制，不修改术语表加载和术语匹配规则，不迁移模型调用，也不改变已构建批次的发送、保存、质量检查和运行记录语义。

涉及文件：

- `app/application/use_cases/translation_run.py`
- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-021.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_applies_max_batches_while_building_batches`
- `tests/test_scan_budget.py::test_batch21_translate_max_items_max_batches_build_limit_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_applies_max_batches_while_building_batches`：1 failed，旧实现为第二个来源文件继续调用批次生成器，说明 `max_batches=1` 仍是构建后切片。
- `uv run pytest tests/test_scan_budget.py::test_batch21_translate_max_items_max_batches_build_limit_record_exists_and_is_linked_from_plan`：1 failed，批次 5O 验收记录尚不存在。

## 改动范围

- `build_translation_batches()` 新增 `max_batches` 参数，并在批次生成循环内达到上限后直接返回。
- `_translate_text_from_warm_index()` 调用 `build_translation_batches()` 时传入 `run_limits.max_batches`，删除构建完成后的切片。
- 普通完整 scope 翻译路径同步使用同一个批次构建入口传入 `run_limits.max_batches`，保持共享 helper 语义一致。
- 新增行为测试在 warm index 小批中确认存在多个 `source_file`，再把批次生成器替换成“第二次调用即失败”的测试替身，固定 `max_batches=1` 不会继续构建被丢弃来源文件的批次。

## 旧路径收束

- 删除 warm index 路径中“构建所有 pending 批次 -> 再按 `max_batches` 切片”的旧路径。
- 删除完整 scope 路径中同样的构建后切片路径。
- 保留 `pending_count` 和 `total_pending_count` 原语义；它们仍描述本轮 SQL 小批 pending 数和索引总 pending 数，不被 `max_batches` 覆盖。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要用户文案不变。
- `--max-batches N` 的可观察结果不变：最多发送 N 个模型批次。
- `deduplicated_count` 继续按实际将要发送的批次条目数计算。
- `--max-batches` 在 CLI 入口仍要求正整数；内部 helper 同步拒绝非正上限，避免把非法内部值静默变成“没有可送入模型的批次”。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试构造多个来源文件的 warm index 小批，并禁止 `max_batches=1` 后继续调用第二个来源文件的批次生成器。
- 代码路径从“全部构建后切片”改为“达到上限即停止构建”，避免为后续会被丢弃的 pending 来源文件继续组装 prompt。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_applies_max_batches_while_building_batches`：RED 阶段 1 failed，原因是旧实现仍进入第二个来源文件批次构建；GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_rejects_non_positive_internal_max_batches`：RED 阶段 1 failed，原因是内部 `max_batches=0` 被静默转成空批次；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch21_translate_max_items_max_batches_build_limit_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5O 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch21_translate_max_items_max_batches_build_limit_record_exists_and_is_linked_from_plan`：GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_applies_max_batches_while_building_batches tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_sql_pending_count_without_full_rows tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_pending_rows_when_sql_pending_zero tests/test_agent_toolkit_translation_limits.py::test_translate_max_items_cold_rebuilds_missing_text_index tests/test_scan_budget.py::test_batch21_translate_max_items_max_batches_build_limit_record_exists_and_is_linked_from_plan`：5 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：736 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- 本批没有改变术语表加载本身，仍会为本轮 pending 小批加载术语索引；下一批可继续审计术语加载边界。
- 本批没有新增大样本 benchmark，性能收益以路径删除测试作为证据。
- 如果单个来源文件本身生成大量批次，本批会在达到 `max_batches` 后停止该来源文件的剩余批次构建；这符合 `--max-batches` 上限语义。

## 下一批入口

批次 5P：建议推进 `translate --max-items` 术语加载边界继续收束，优先审计 warm index 小批是否仍需无条件加载完整术语索引，以及能否在不改变提示词注入语义的前提下减少无关术语处理。
