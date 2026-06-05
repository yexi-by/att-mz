# Rust Scope/Index Engine 批次 29 验收记录

## 本批范围

- 批次：5W，写回快路径 SQL gate 摘要收束。
- 覆盖入口：`write_back`、`rebuild_active_runtime`、`write_terminology` 的 warm index 写入前检查。
- 成功状态：当前游戏已有有效 warm index 且源码支线 gate 已预检时，写入前检查不再读取全部 `text_index_items` 行，也不再调用 Rust `evaluate_scope_gate` 重建 gate 输入；pending 数量、最新质量错误数量和可写路径列表改由 SQL 摘要/路径接口提供。

## 保护网

- 扩展 `tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build`：在三类写回入口 warm index 测试中同时禁止 `TextScopeService.build`、`read_text_index_items` 和 `evaluate_text_index_scope_gate`。
- 扩展 `tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：固定 `read_writable_text_index_location_paths()` 只返回可写路径，且按路径顺序稳定输出。
- 新增 `tests/test_scan_budget.py::test_batch29_write_related_sql_gate_summary_record_exists_and_is_linked_from_plan`：固定本批验收记录必须被计划表链接，且包含统一收尾章节。

## 改动范围

- `app/application/handler.py`
  - `_prepare_write_operation_from_text_index` 改用 `read_writable_text_index_location_paths()`、`count_pending_text_index_items()` 和 `count_pending_text_index_quality_errors(...)`。
  - 删除写回快路径对 `read_text_index_items()` 与 `evaluate_text_index_scope_gate(...)` 的依赖。
- `app/persistence/sql.py`
  - 新增 `SELECT_WRITABLE_TEXT_INDEX_LOCATION_PATHS`，只读取 `writable = 1` 的定位路径并按路径排序。
- `app/persistence/text_index_records.py`
  - 新增 `read_writable_text_index_location_paths()` 会话方法。
- `tests/test_rmmz_write_plan.py`
  - 扩展三入口 warm index 性能保护网。
- `tests/test_persistence.py`
  - 增加可写路径接口断言。
- `tests/test_scan_budget.py`
  - 增加批次 29 验收记录存在性测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 批次进度追加 5W，并给出下一批入口建议。

## 旧路径收束

- warm index 写回快路径不再通过 `read_text_index_items()` 读取完整索引行。
- warm index 写回快路径不再为了计算 pending、quality error 和 writable paths 调用 `evaluate_text_index_scope_gate(...)`。
- 索引缺失、索引过期或索引未记录源码支线 gate 预检时，仍保留旧慢路径；本批不改变 fallback 行为。

## 外部契约变化

- CLI 参数、配置字段、JSON schema、输出摘要字段和用户可见错误文案不变。
- 写回计划收到的 `allowed_translation_paths` 仍为当前可写定位路径列表，顺序保持按定位路径排序。
- 已有有效 warm index 的项目会减少写入前检查的 Python 行对象读取和 Rust gate 输入重建。

## 性能证据

- 行为测试禁止三类写回入口调用 `read_text_index_items()`，证明 warm index 写入前检查不再读取全部 text index rows。
- 行为测试禁止调用 `evaluate_text_index_scope_gate()`，证明本批不再把索引行还原为 Rust gate 输入。
- 仍需要读取全部可写定位路径字符串传入 Rust 写回计划；这是写回计划 `allowed_translation_paths` 的外部输入需求，本批没有消除这一步。

## 验证结果

- `uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build`：3 passed。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_quality_errors_without_python_scope_build tests/test_rmmz_write_plan.py::test_write_back_warm_index_ignores_quality_error_after_translation_saved tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：3 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch29_write_related_sql_gate_summary_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_rmmz_write_plan.py tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：16 passed。
- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `uv run pytest`：757 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。

## 审查处理

- 子代理审查未发现 P0-P2 阻塞问题。
- 子代理审查发现 P3：本记录的审查处理仍为占位状态，且没有记录完整 `uv run pytest` 结果。
- 已处理：回填审查结论，并补充完整 Python/Rust 门禁结果。
- 残余风险经审查确认：本批没有覆盖索引缺失/过期 fallback；“Rust 写回计划收到的 allowed paths 一定排除某个已知不可写路径”主要由持久层可写路径接口测试和 SQL 条件证明。

## 剩余风险

- 无有效索引时仍走旧慢路径，本批没有实现写回入口自动重建索引。
- 写回计划仍需要完整可写定位路径列表作为 `allowed_translation_paths`，本批没有把 Rust 写回计划改为直接从 SQLite 读取可写范围。
- fallback 自动重建的用户体验和失败文案尚未审计。

## 下一批入口

- 建议下一批：写回入口索引缺失/过期自动重建审计。重点确认 `write_back`、`rebuild_active_runtime`、`write_terminology` 在索引缺失或过期时是否应自动重建 warm index，若自动重建失败，错误文案和旧慢路径 fallback 如何保持可解释且不重复全量扫描。
