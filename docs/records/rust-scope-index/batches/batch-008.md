# Rust Scope/Index Engine 批次 5B text-scope 索引清单记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `text-scope` 的 warm index 默认路径：当持久 text index 有效且未启用 `--include-write-probe` 时，统一文本清单直接从 text index rows 还原 entries 与统计，不加载完整游戏数据，不构建完整 `TextScopeService`。

本批不改变 `text-scope --include-write-probe`，不处理索引缺失或失效后的自动 rebuild，不迁移插件源码 AST、非标准 data 扫描，也不改变完整写入探针语义。

涉及文件：

- `app/agent_toolkit/services/common.py`
- `app/agent_toolkit/services/coverage.py`
- `tests/test_agent_toolkit_coverage.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-008.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_coverage.py::test_text_scope_uses_warm_text_index_without_full_scope_load`
- `tests/test_scan_budget.py::test_batch08_text_scope_index_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_coverage.py::test_text_scope_uses_warm_text_index_without_full_scope_load`：失败，旧实现仍调用 `_load_translation_source_game_data()`，说明 warm index 默认 `text-scope` 仍走完整游戏数据加载。
- `uv run pytest tests/test_scan_budget.py::test_batch08_text_scope_index_record_exists_and_is_linked_from_plan`：失败，批次 5B 验收记录尚不存在。

## 改动范围

- 新增公共 helper `build_text_index_text_scope_report()`，从持久索引 rows 和已保存译文生成默认 `text-scope` 报告。
- `text_scope()` 在 warm index 且 `include_write_probe=False` 时：
  - 使用 `detect_text_index_invalidations()` 确认索引有效。
  - 读取 `read_text_index_items()`、`read_translated_items()` 和非标准 data 规则。
  - 复用 `text_index_records_to_scope()` 恢复占位符候选覆盖检查所需的最小 scope。
  - 返回 `text_index_status="used"` 与由索引 rows 还原的完整 entries 清单。

## 旧路径收束

- 本批删除 `text-scope` warm index 默认路径中的完整 `GameData` 加载和完整 `TextScopeService` 构建。
- `text-scope --include-write-probe` 仍保留原完整 scope 路径，因为写入探针需要真实写回协议检查。
- 索引缺失或失效时，本批暂时保留现有完整路径；后续批次再决定是否改为 cold/stale rebuild 后消费索引。

## 外部契约变化

- `text-scope` summary 新增 `text_index_status`，warm index 默认路径返回 `used`。
- warm index 默认路径的 `details.entries` 继续输出完整清单，但每条 entry 的 `rule_source` 统一为 `text_index`，表示该清单来自持久索引事实。
- CLI 参数、退出码和 `--include-write-probe` 行为本批不变。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- warm index 测试禁止完整游戏数据加载和 `TextScopeService.build()`，`text-scope` 仍能返回完整 entries 清单。
- 清单统计使用 text index rows 与已保存译文计算 entry、extractable、translated、writable 和 unwritable 数量。
- coverage 测试组继续通过，证明 `text-scope` 写入探针路径和 `audit-coverage` 相关契约未被本批破坏。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_coverage.py::test_text_scope_uses_warm_text_index_without_full_scope_load`：1 passed。
- `uv run pytest tests/test_agent_toolkit_coverage.py`：11 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch08_text_scope_index_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_agent_toolkit_coverage.py tests/test_scan_budget.py`：21 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：711 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- `text-scope --include-write-probe` 仍走完整 scope 路径。
- 索引缺失或失效时，`text-scope` 还没有改成先 rebuild 再消费索引。
- 持久索引当前不保存过期插件规则明细；warm index 路径只能从索引 rows 还原 entries，不能补充未持久化的 stale rule 详情。
- 大样本输出仍可能主要受 JSON 序列化和 stdout 写出成本影响，需要后续基准区分扫描耗时和输出耗时。

## 下一批入口

批次 5C：建议处理 `translation-status --refresh-scope` 或 `translate --max-items` 的索引消费路径，优先让状态统计和翻译前置限制复用有效 text index 与 SQLite 查询，不再构建完整 Python scope 后再取统计或批次。
