# Rust Scope/Index Engine 批次 5I translate --max-items quality gate 路径快路径记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 路径的 Rust quality gate 输入快路径：`evaluate_text_index_scope_gate()` 不再读取最新翻译运行的完整质量错误对象，而是从 SQLite 直接读取当前 text index 范围内的质量错误路径，再交给 Rust `evaluate_scope_gate` 生成 compact quality gate summary。

本批不改变 `translate` 遇到历史质量错误时是否继续翻译的用户可见行为。质量错误仍不会让本次 `translate --max-items` 自动阻断；本批只收束 Rust gate 的输入来源，避免为 compact summary 构造加载完整错误明细。

涉及文件：

- `app/persistence/sql.py`
- `app/persistence/text_index_records.py`
- `app/text_index.py`
- `tests/test_text_index.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-015.md`

## 保护网

先建立或调整的测试：

- `tests/test_text_index.py::test_evaluate_text_index_scope_gate_reads_quality_error_paths_from_index_fast_path`
- `tests/test_scan_budget.py::test_batch15_translate_max_items_quality_gate_fast_path_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_text_index.py::test_evaluate_text_index_scope_gate_reads_quality_error_paths_from_index_fast_path`：1 failed，旧实现调用 `read_translation_quality_errors()` 加载完整质量错误对象。
- `uv run pytest tests/test_scan_budget.py::test_batch15_translate_max_items_quality_gate_fast_path_record_exists_and_is_linked_from_plan`：1 failed，批次 5I 验收记录尚不存在。

## 改动范围

- 新增 `SELECT_TEXT_INDEX_QUALITY_ERROR_PATHS`：
  - 用 `translation_quality_errors` 与 `text_index_items` 按 `location_path` join。
  - 只返回指定运行中仍属于当前 text index 范围的质量错误定位路径。
- 新增 `TargetGameSession.read_text_index_quality_error_paths(run_id)`。
- `evaluate_text_index_scope_gate()` 改为读取最新 run 后调用 text index 质量错误路径快路径，不再加载完整 `TranslationErrorItem` 列表。

## 旧路径收束

- 本批删除 Rust scope gate 摘要输入对 `read_translation_quality_errors()` 的依赖。
- 完整质量错误对象读取仍保留给 `quality-report`、修复表导出、人工导入修复和用户可见明细报告。
- 本批没有改写 `write-back` quality gate；它仍使用自己的写回前置检查路径。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- `translate --max-items` 继续允许后续翻译运行处理 pending 文本；历史质量错误不会在本批变成新的翻译阻断条件。
- Rust `quality_gate.quality_error_count` 的输入范围更精确：只计入当前 text index 范围内的最新质量错误路径。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试禁止 `read_translation_quality_errors()`，`evaluate_text_index_scope_gate()` 仍可得到 Rust `quality_gate` 错误状态。
- 同一测试写入一个索引内错误和一个索引外错误，Rust `quality_error_count` 只计入索引内路径，证明 quality gate 输入不再读取或处理完整错误明细。

## 验证结果

局部验证：

- `uv run pytest tests/test_text_index.py::test_evaluate_text_index_scope_gate_reads_quality_error_paths_from_index_fast_path`：RED 阶段 1 failed，原因是旧实现读取完整质量错误对象；GREEN 阶段 1 passed。
- `uv run pytest tests/test_text_index.py`：5 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch15_translate_max_items_quality_gate_fast_path_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5I 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch15_translate_max_items_quality_gate_fast_path_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_text_index.py::test_evaluate_text_index_scope_gate_reads_quality_error_paths_from_index_fast_path tests/test_scan_budget.py::test_batch15_translate_max_items_quality_gate_fast_path_record_exists_and_is_linked_from_plan`：2 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：725 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- Rust `quality_gate` 当前仍只是 compact summary 的数据来源，尚未接管 `quality-report`、`write-back` 和 `rebuild-active-runtime` 的完整质量阻断链。
- `evaluate_text_index_scope_gate()` 仍需要读取全部 text index rows 和已保存译文路径；这不是最终大样本形态，后续应继续向 SQLite summary 或 Rust compact 输入收束。
- 占位符候选审查仍在 Python 中扫描从 index 还原的文本范围，下一批应优先迁移这一处大规模文本扫描。

## 下一批入口

批次 5J：建议推进 `translate --max-items` 占位符 gate 索引化，优先避免 `collect_indexed_workflow_gate_errors()` 为占位符候选审查扫描完整 `translation_data_map`。
