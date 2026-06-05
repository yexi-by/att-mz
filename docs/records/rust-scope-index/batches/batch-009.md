# Rust Scope/Index Engine 批次 5C translation-status 索引统计记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只收束 P1-A 中 `translation-status --refresh-scope` 的索引统计路径：当持久 text index 有效时，状态刷新直接读取 text index metadata、SQLite pending/translated/quality-error count，不加载完整游戏数据，不构建完整 `TextScopeService`，也不读取全量路径集合或全量错误明细。

本批不处理 `translate --max-items` 的 workflow gate 迁移。当前 Rust Scope/Index Engine 还没有完整 `evaluate_scope_gate` summary，若直接跳过完整门禁会漏掉插件源码、非标准 data 等高风险支线，因此该项保留到下一批。

涉及文件：

- `app/agent_toolkit/services/quality.py`
- `app/persistence/text_index_records.py`
- `tests/test_agent_toolkit_manual_import.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-009.md`

## 保护网

已有或本批补充的测试：

- `tests/test_agent_toolkit_manual_import.py::test_translation_status_uses_database_fast_path_by_default`
- `tests/test_agent_toolkit_manual_import.py::test_translation_status_refresh_scope_cold_rebuilds_missing_text_index`
- `tests/test_agent_toolkit_manual_import.py::test_translation_status_refresh_scope_uses_text_index_without_full_scope_load`
- `tests/test_scan_budget.py::test_batch09_translation_status_index_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_scan_budget.py::test_batch09_translation_status_index_record_exists_and_is_linked_from_plan`：失败，批次 5C 验收记录尚不存在。

当前源码状态说明：

- `translation-status --refresh-scope` 的 warm index 行为测试在本批开始前已存在，并且当前实现已使用 SQLite count 快路径。本批把这条已实现路径正式收束为独立验收批次，没有重复修改生产代码。

## 改动范围

- 新增批次 5C 验收记录与计划进度行。
- 新增批次记录保护测试，确保 `docs/records/rust-scope-index/batches/batch-009.md` 被总计划链接，并包含固定验收章节。
- 复核 `translation_status()` 的 warm index 路径：
  - `detect_text_index_invalidations()` 判定索引有效。
  - `read_text_index_metadata()` 读取可提取总数。
  - `count_pending_text_index_items()`、`count_text_index_translated_items()`、`count_pending_text_index_quality_errors()` 和 `count_pending_text_index_quality_errors_by_type()` 直接在 SQLite 层统计。

## 旧路径收束

- warm index 下 `translation-status --refresh-scope` 不再加载完整 `GameData`。
- warm index 下不构建完整 `TextScopeService`。
- warm index 下不读取完整 text index 路径集合、全部已保存译文路径或全部质量错误明细。
- 索引缺失或失效时仍允许触发一次 `rebuild-text-index`，这是当前计划允许的 cold/stale rebuild 路径。

## 外部契约变化

- 本批不改变 CLI 参数、退出码和主要错误文案。
- `translation-status --refresh-scope` 在 warm index 下继续返回 `scope_refreshed=true` 与 `text_index_status="used"`。
- 索引缺失时继续返回 `text_index_status="cold_rebuilt"`，并保留 `text_index_rebuild_summary`。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止完整游戏数据加载，`translation-status --refresh-scope` 仍能返回刷新后的 pending、translated 和 quality-error 统计。
- warm index 测试禁止完整索引路径集合、已保存译文路径集合和质量错误明细读取，证明统计来自 SQLite count 查询。
- 缺索引测试覆盖 cold rebuild 后再读取索引统计，证明索引缺失时不会继续使用旧运行记录假装刷新。

## 验证结果

局部验证：

- `uv run pytest tests/test_scan_budget.py::test_batch09_translation_status_index_record_exists_and_is_linked_from_plan`：RED 已确认，后续待补 GREEN。
- `uv run pytest tests/test_scan_budget.py::test_batch09_translation_status_index_record_exists_and_is_linked_from_plan tests/test_agent_toolkit_manual_import.py::test_translation_status_uses_database_fast_path_by_default tests/test_agent_toolkit_manual_import.py::test_translation_status_refresh_scope_cold_rebuilds_missing_text_index tests/test_agent_toolkit_manual_import.py::test_translation_status_refresh_scope_uses_text_index_without_full_scope_load`：4 passed。
- `uv run pytest tests/test_agent_toolkit_manual_import.py tests/test_scan_budget.py`：42 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：712 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- `translate --max-items` warm index 路径仍会加载完整游戏数据并构建完整 scope 做 workflow gate；这是下一批入口，不在本批内半截迁移。
- `translation-status --refresh-scope` 在索引缺失或失效时仍会触发完整索引重建，该耗时归因于 rebuild，不属于 warm index 统计快路径。
- 本批没有真实大样本耗时表；后续需要在 `Summer Stolen v0.2` 上补充改造前后耗时。

## 下一批入口

批次 5D：`translate --max-items` 前置索引消费。建议先实现或接入 Rust `evaluate_scope_gate` / index gate summary，覆盖外部规则、占位符候选、插件源码、非标准 data、术语和可写性后，再移除 warm index 下的完整 Python scope 构建。
