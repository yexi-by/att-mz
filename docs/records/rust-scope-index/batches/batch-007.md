# Rust Scope/Index Engine 批次 5A audit-coverage 索引消费记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `audit-coverage` 的 warm index 默认路径：当持久 text index 有效且未启用 `--include-write-probe` 时，覆盖审计直接消费 text index rows、已保存译文和索引恢复的最小 scope，不加载完整游戏数据，不构建完整 `TextScopeService`。

本批不改变 `audit-coverage --include-write-probe`，不迁移 `text-scope` 完整清单，不迁移插件源码 AST、非标准 data 扫描，也不处理 `quality-report` 之外的质量 gate 链路。

涉及文件：

- `app/agent_toolkit/services/common.py`
- `app/agent_toolkit/services/coverage.py`
- `app/agent_toolkit/services/quality.py`
- `tests/test_agent_toolkit_coverage.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-007.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_coverage.py::test_audit_coverage_uses_warm_text_index_without_full_scope_load`
- `tests/test_agent_toolkit_quality_report.py::test_quality_report_uses_text_index_without_full_scope_load`
- `tests/test_scan_budget.py::test_batch07_audit_coverage_index_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_coverage.py::test_audit_coverage_uses_warm_text_index_without_full_scope_load`：失败，旧实现仍调用 `_load_translation_source_game_data()`，说明 warm index 覆盖审计仍走完整游戏数据加载。
- `uv run pytest tests/test_scan_budget.py::test_batch07_audit_coverage_index_record_exists_and_is_linked_from_plan`：失败，批次 5A 验收记录尚不存在。

## 改动范围

- 新增公共 helper `text_index_records_to_scope()`，从持久索引恢复占位符覆盖检查所需的最小 `TextScopeResult`。
- 新增公共 helper `build_text_index_coverage_report()`，用 text index rows 与已保存译文生成 sampled 覆盖审计结果。
- `quality-report` 改为复用公共 helper，避免 quality 和 coverage 维护两套索引覆盖统计逻辑。
- `audit_coverage()` 在 warm index 且 `include_write_probe=False` 时：
  - 使用 `detect_text_index_invalidations()` 确认索引有效。
  - 读取 `read_text_index_items()` 与 `read_translated_items()`。
  - 从索引恢复最小 scope 继续执行占位符候选覆盖提醒。
  - 返回 `text_index_status="used"` 与 sampled coverage details。

## 旧路径收束

- 本批删除 `audit-coverage` warm index 默认路径中的完整 `GameData` 加载和完整 `TextScopeService` 构建。
- `audit-coverage --include-write-probe` 仍保留原完整 scope 路径，因为写入探针语义需要单独批次处理。
- 索引缺失或失效时，本批暂时保留现有完整路径；后续批次再决定是否改为 cold/stale rebuild 后消费索引。

## 外部契约变化

- `audit-coverage` summary 新增 `text_index_status`，warm index 默认路径返回 `used`。
- warm index 默认路径的 details 使用 sampled 结构，避免大样本输出完整 pending/stale 列表。
- CLI 参数、退出码和 `--include-write-probe` 行为本批不变。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止完整游戏数据加载和 `TextScopeService.build()`，`audit-coverage` 仍能返回覆盖摘要。
- 覆盖报告使用 text index rows 与已保存译文计算 pending、stale、writable、translated 等计数。
- quality-report 的 warm index 测试继续通过，证明公共 helper 没有破坏已有索引质量报告路径。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_coverage.py::test_audit_coverage_uses_warm_text_index_without_full_scope_load`：1 passed。
- `uv run pytest tests/test_agent_toolkit_quality_report.py::test_quality_report_uses_text_index_without_full_scope_load`：1 passed。
- `uv run pytest tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py::test_quality_report_uses_text_index_without_full_scope_load`：11 passed。
- `uv run pytest tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py::test_quality_report_uses_text_index_without_full_scope_load tests/test_scan_budget.py`：20 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：709 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- `audit-coverage --include-write-probe` 仍走完整 scope 路径。
- 索引缺失或失效时，`audit-coverage` 还没有改成先 rebuild 再消费索引。
- `text-scope` 完整清单仍未改为从 index rows 输出。
- sampled details 是为了大样本性能收束；若后续 CLI 契约要求完整清单，需要增加显式选项或专门命令路径。

## 下一批入口

批次 5B：`text-scope` 索引清单输出。建议优先让 warm index 默认 `text-scope` 从 text index rows 和 summary 生成清单与统计；需要完整 entries 时由索引 rows 还原，而不是重新构建 Python scope。
