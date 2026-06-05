# Rust Scope/Index Engine 批次 4 P0 pending 导出记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P0 `export-pending-translations --limit N`：有效 text index 可用时直接读取 SQLite pending 快路径，并在 SQL 层应用 `limit`；索引缺失或失效时先重建一次 text index，再读取受 `limit` 限制的 pending 条目。

本批不迁移插件参数、Note、插件源码 AST、非标准 data 扫描，不改写 `quality-report`、`audit-coverage`、`text-scope` 的主流程，也不修改 CLI 参数或 pending 文件 JSON 格式。

涉及文件：

- `app/agent_toolkit/services/manual_translation.py`
- `app/agent_toolkit/services/text_index.py`
- `app/agent_toolkit/services/common.py`
- `tests/test_agent_toolkit_manual_import.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-006.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_manual_import.py::test_export_pending_translations_warm_index_uses_sql_limit_without_full_scope_load`
- `tests/test_agent_toolkit_manual_import.py::test_export_pending_translations_cold_rebuilds_missing_text_index_then_uses_limit`
- `tests/test_agent_toolkit_coverage.py::test_read_only_scope_reports_skip_write_probe_by_default`
- `tests/test_scan_budget.py::test_batch06_p0_pending_export_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_pending_translations_warm_index_uses_sql_limit_without_full_scope_load`：失败，旧实现仍调用 `_load_translation_source_game_data()`，说明 warm index 下仍走完整游戏数据加载和 Python scope 构建。
- `uv run pytest tests/test_scan_budget.py::test_batch06_p0_pending_export_record_exists_and_is_linked_from_plan`：失败，批次 4 验收记录尚不存在。

## 改动范围

- `export_pending_translations()` 改为先通过 `detect_text_index_invalidations()` 检查持久索引。
- warm index 路径直接调用 `count_pending_text_index_items()` 与 `read_pending_text_index_items(limit=N)`，不加载完整 `GameData`，不构建 `TextScopeService`。
- cold/stale index 路径先调用一次 `rebuild_text_index()`，失败时显式返回 rebuild 错误和索引失效明细。
- `limit <= 0` 保留旧行为：导出空 JSON，不把非正数传给 SQL limit 查询。
- `rebuild_text_index()` 增加内部 `include_write_probe` 参数，默认保持 `True`；pending 导出冷重建时按命令自身 `include_write_probe` 传递，避免默认导出触发写入探针。
- pending 导出 summary 新增 `text_index_status`、`pending_total_count` 和可选 `text_index_rebuild_summary`。

## 旧路径收束

- 删除 `export_pending_translations()` 默认流程中的 Python 全量 pending 筛选。
- 删除该命令中为了导出前 N 条 pending 而加载完整 `GameData`、读取全部已保存译文和构建完整 `TextScopeService` 的路径。
- 保留 text index 缺失或失效时的一次 rebuild；这是索引事实来源刷新，不是 pending 导出的隐藏慢路径回退。
- `include_write_probe=True` 仍依赖索引重建或已有索引的 writable 事实；本批没有新增第二套写回探针筛选。

## 外部契约变化

- pending 文件 JSON 格式不变。
- CLI 参数和退出码不变。
- summary 保留原有 `pending_exported_count`、`output`、`write_back_probe_enabled` 字段，并新增索引状态字段。
- 默认 `include_write_probe=False` 的导出仍不执行写入探针。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止完整游戏数据加载和 `TextScopeService.build()`，`export-pending-translations --limit 1` 仍成功导出 1 条。
- cold index 测试证明缺索引时先重建一次，然后导出数量受 `limit=1` 限制。
- persistence 层既有 `read_pending_text_index_items(limit=N)` 继续在 SQL `LIMIT ?` 中应用上限。

## 验证结果

本批目标测试已先转绿：

- `uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_pending_translations_warm_index_uses_sql_limit_without_full_scope_load`：1 passed。
- `uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_pending_translations_warm_index_uses_sql_limit_without_full_scope_load tests/test_agent_toolkit_manual_import.py::test_export_pending_translations_cold_rebuilds_missing_text_index_then_uses_limit`：2 passed。
- `uv run pytest tests/test_agent_toolkit_coverage.py::test_read_only_scope_reports_skip_write_probe_by_default`：1 passed。
- `uv run pytest tests/test_agent_toolkit_manual_import.py`：31 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch06_p0_pending_export_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_agent_toolkit_manual_import.py tests/test_agent_toolkit_coverage.py::test_read_only_scope_reports_skip_write_probe_by_default tests/test_scan_budget.py`：40 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：707 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无命中。

## 剩余风险

- `include_write_probe=True` 的 warm index 是否来自带探针的索引，目前没有 metadata 标记；本批只保证不在导出函数里二次全量扫描。
- 真实大样本 `<样本游戏>` 耗时尚未复测，本批用小夹具和静态路径证明 `limit` 已前移到 SQLite。
- P1-A 的 `quality-report`、`audit-coverage`、`text-scope`、`translate --max-items` 仍需继续审计和接入 summary/index 快路径。
- Rust 真实扫描器仍只覆盖上一批的最小 data 扫描点。

## 下一批入口

批次 5：P1-A 核心命令索引消费。建议优先审计并收束 `quality-report`、`audit-coverage`、`text-scope` 对 text index scope/domain/rule summary 的消费路径，避免在索引有效时重新构建完整 Python scope 或二次统计 coverage。
