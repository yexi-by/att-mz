# Rust Scope/Index Engine 批次 30 验收记录

## 本批范围

- 批次：5X，写回入口索引缺失/过期自动重建审计。
- 覆盖入口：`write_back`、`rebuild_active_runtime`、`write_terminology` 的写入前检查。
- 成功状态：写回相关入口发现持久文本范围索引缺失、索引项数量与元信息不一致，或旧索引缺少源码支线 gate 预检元信息时，不再落回旧 Python 全量写回前置路径；命令先重建一次持久索引，重建成功后继续走 SQL/index 快路径，重建失败时显式报错。

## 保护网

- 新增 `tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：
  - 覆盖 `write_back`、`rebuild_active_runtime`、`write_terminology`。
  - 覆盖 `missing`、`count_mismatch` 和 `precheck_missing` 三种索引不可复用状态。
  - 禁止自动重建后调用旧 Python `assert_workflow_gate_passed`、`assert_write_back_quality_passed` 和 `_filter_writable_translation_items` fallback。
  - 禁止自动重建后的快路径读取全部 `text_index_items` 行或调用 `evaluate_text_index_scope_gate`。
- 新增 `tests/test_rmmz_write_plan.py::test_write_related_commands_stop_when_text_index_rebuild_fails_without_fallback`：
  - 覆盖三类写回入口自动重建失败分支。
  - 模拟索引重建返回阻断原因，断言命令抛出 `WriteBackGateError`。
  - 禁止失败后继续调用旧 Python workflow/quality/filter fallback 或生成 Rust 写回计划。
- 新增 `tests/test_scan_budget.py::test_batch30_write_related_index_rebuild_record_exists_and_is_linked_from_plan`：固定本批验收记录必须被计划表链接，且包含统一收尾章节。

## 改动范围

- `app/application/handler.py`
  - `_prepare_write_operation(...)` 透传写文件进度回调，便于自动重建阶段更新状态。
  - `_prepare_write_operation_from_text_index(...)` 在索引缺失、过期或缺少源码支线 gate 预检元信息时调用自动重建。
  - 新增 `_rebuild_text_index_for_write_operation(...)`，复用现有索引重建流程；重建失败时抛出 `WriteBackGateError`，不再继续旧慢路径。
- `tests/test_rmmz_write_plan.py`
  - 增加三入口三状态矩阵测试。
  - 增加三入口自动重建失败停止测试。
- `tests/test_scan_budget.py`
  - 增加批次 30 验收记录存在性测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 批次进度追加 5X，并给出下一批入口建议。

## 旧路径收束

- 写回相关入口在索引缺失时不再直接构建旧 Python `TextScopeService` 写入前范围并继续旧 workflow/quality/filter 路径。
- 写回相关入口在索引过期时不再直接落回旧慢路径，而是先重建一次持久索引。
- 旧索引缺少源码支线 gate 预检元信息时不再作为 warm index 不兼容理由进入旧慢路径，而是重建为当前契约下可复用的索引。
- 自动重建后继续复用上一批收束出的 SQL/index 快路径；仍禁止读取全部索引行和 Rust scope gate 输入还原。

## 外部契约变化

- CLI 参数、配置字段、JSON schema 和成功摘要字段不变。
- 写回相关入口在索引不可用时会多执行一次索引重建；若重建失败，错误会说明“当前游戏持久文本范围索引自动重建失败”并带出具体阻断原因。
- 原本无索引或旧索引状态下仍可能完成写回的项目，现在会先刷新索引事实，避免旧慢路径产生第二事实来源。

## 性能证据

- 行为测试禁止索引不可用后的旧 Python workflow/quality/filter fallback，证明自动重建成功后不会再重复执行旧全量写回前置检查。
- 行为测试继续禁止 `read_text_index_items()` 与 `evaluate_text_index_scope_gate()`，证明自动重建后的写回前检查仍保持批次 29 的 SQL 摘要路径。
- 本批仍会在索引不可用时执行一次完整索引重建；这是刷新单一事实来源的必要成本，不是继续执行旧写回前置 fallback。

## 验证结果

- RED：`uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：6 failed，失败点为旧 Python workflow gate fallback 被调用。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：9 passed。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_stop_when_text_index_rebuild_fails_without_fallback tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：12 passed。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_quality_errors_without_python_scope_build tests/test_rmmz_write_plan.py::test_write_back_warm_index_ignores_quality_error_after_translation_saved`：11 passed。
- `uv run pytest tests/test_rmmz_write_plan.py tests/test_scan_budget.py::test_batch30_write_related_index_rebuild_record_exists_and_is_linked_from_plan`：25 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch30_write_related_index_rebuild_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest`：770 passed。
- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。

## 审查处理

- 已完成自查：自动重建只在索引不可复用时触发；重建成功后读取新的 metadata 并继续 SQL/index 快路径。
- 子代理审查发现 P2：自动重建失败分支缺少测试，未固定失败后不能继续旧 workflow/quality/filter fallback 或生成 Rust 写回计划。
- 已修复：新增 `test_write_related_commands_stop_when_text_index_rebuild_fails_without_fallback`，模拟重建失败并禁止旧 fallback 与写回计划继续执行。

## 剩余风险

- 自动重建本身仍依赖当前统一文本范围构建流程；本批目标是删除写回前置旧 fallback，不是把索引重建流程完全 Rust-only 化。
- 写回计划仍需要完整 `allowed_translation_paths` 列表作为 Rust 写回计划输入；本批没有把 Rust 写回计划改为直接从 SQLite 读取可写范围。
- 自动重建的耗时仍取决于当前游戏规模；本批用行为保护网证明不会在重建后再重复走旧写回前置路径。

## 下一批入口

- 建议下一批：写回计划可写路径直连 SQLite/Rust 评估。重点确认 `allowed_translation_paths` 是否还能继续缩小为 SQLite/Rust 内部读取，避免 Python 为 Rust 写回计划组装完整可写路径列表。
