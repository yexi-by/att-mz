# Rust Scope/Index Engine 批次 28 验收记录

## 本批范围

- 批次：5V，写回相关命令可写范围与质量 gate 复用索引事实审计。
- 覆盖入口：`write_back`、`rebuild_active_runtime`、`write_terminology`。
- 成功状态：当前游戏已有有效 warm index，且索引元信息记录插件源码和非标准 data 支线 gate 已预检时，写入前检查不再重建 Python `TextScopeService` 全量范围；可写路径、pending 数量和最新质量错误数量来自持久文本范围索引与 Rust `evaluate_scope_gate`。

## 保护网

- 新增 `tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build`：三类写回入口在 warm index 下禁止调用 `TextScopeService.build`，并断言 Rust 写回计划收到非空且有序的 `allowed_translation_paths`。
- 新增 `tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_quality_errors_without_python_scope_build`：warm index 下最新翻译运行存在质量错误时，写回必须在生成 Rust 写回计划前失败；测试禁止读取完整质量错误对象和重建 Python 全量文本范围。
- 新增 `tests/test_scan_budget.py::test_batch28_write_related_index_gate_record_exists_and_is_linked_from_plan`：固定本批验收记录必须被计划表链接，且包含统一收尾章节。

## 改动范围

- `app/application/handler.py`
  - `_prepare_write_operation` 先加载配置和规则，再尝试索引快路径。
  - 新增 `_prepare_write_operation_from_text_index`，在索引有效且源码支线 gate 已预检时，复用 `collect_text_index_*_gate_errors`、`collect_indexed_workflow_gate_errors` 和 `evaluate_text_index_scope_gate` 完成写入前检查。
  - `PreparedWriteOperation.game_data` 与 `PreparedWriteOperation.scope` 改为慢路径上下文，可为空；后续 Rust 写回计划只消费 setting、text rules 和可写路径。
- `app/persistence/sql.py`
  - `SELECT_TEXT_INDEX_QUALITY_ERROR_PATHS` 改为只返回当前可写且尚未保存译文的质量错误路径，保持与旧写回 quality gate 的 pending 路径语义一致。
- `tests/test_rmmz_write_plan.py`
  - 增加写回三入口 warm index 复用测试。
  - 增加 warm index 质量错误快路径测试。
  - 增加“最新质量错误已被后续保存译文修复后不阻断写回”的回归测试。
- `tests/test_scan_budget.py`
  - 增加批次 28 验收记录存在性测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 批次进度追加 5V，并给出下一批入口建议。

## 旧路径收束

- warm index 有效且源码支线 gate 预检通过时，`write_back`、`rebuild_active_runtime`、`write_terminology` 不再走旧的 Python `TextScopeService().build(...)` 写入前范围构建。
- warm index 快路径不再通过 `read_translation_quality_errors_by_paths(...)` 读取完整质量错误对象；质量错误数量由 text index 质量错误路径快路径提供，并限定为 pending 且可写的路径。
- 索引缺失、索引过期或索引未记录源码支线 gate 预检时，仍保留旧慢路径，避免改变未建立索引项目的写回入口行为。

## 外部契约变化

- CLI 参数、配置字段、JSON schema、输出摘要字段和写回成功路径不变。
- 业务错误文案沿用现有写回前检查语义：未完成译文、最新运行质量错误、模型运行故障和旧译文路径仍以“写进游戏文件前检查没通过”开头。
- 已有 warm index 的项目会更早复用索引事实完成写入前检查；没有有效索引的项目仍可按旧路径执行。

## 性能证据

- 新增行为测试在 monkeypatch 层禁止 warm index 写回入口调用 `TextScopeService.build`，证明本批消除了这三类入口的重复 Python 全量范围构建。
- 新增质量 gate 测试禁止读取完整质量错误对象，证明质量错误拦截使用 text index 路径级快路径。
- 本批仍会读取全部 text index rows 作为 Rust `evaluate_scope_gate` 输入；下一批建议继续把写回快路径的索引行读取收束为 SQL 摘要或更小载荷，并审计 fallback 自动重建策略。

## 验证结果

- `uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build`：3 passed。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_quality_errors_without_python_scope_build`：1 passed。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_quality_errors_without_python_scope_build tests/test_rmmz_write_plan.py::test_write_back_warm_index_ignores_quality_error_after_translation_saved`：2 passed。
- `uv run pytest tests/test_rmmz_write_plan.py::test_direct_write_back_rejects_latest_quality_errors tests/test_rmmz_write_plan.py::test_write_terminology_allows_pending_body_translation_run`：2 passed。
- `uv run pytest tests/test_rmmz_write_plan.py`：15 passed。
- `uv run pytest tests/test_text_index.py::test_evaluate_text_index_scope_gate_reads_quality_error_paths_from_index_fast_path tests/test_native_scope_index.py::test_evaluate_native_scope_gate_returns_compact_gate_summary`：2 passed。
- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `uv run pytest`：756 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。

## 审查处理

- 已完成自查：索引快路径只在 `detect_text_index_invalidations(...)` 无失效且 `text_index_source_branch_gates_prechecked(...)` 为真时启用；否则保留旧慢路径。
- 子代理审查发现 P1：原 `SELECT_TEXT_INDEX_QUALITY_ERROR_PATHS` 会把已经通过手动保存译文修复的最新质量错误继续计入 warm index quality gate，和旧写回 gate 只检查 pending 路径的语义不一致。
- 已修复：质量错误路径 SQL 增加 `index_items.writable = 1` 与 translation 表空匹配条件，并新增回归测试覆盖“质量错误已被后续保存译文修复后允许写回”。

## 剩余风险

- 写回快路径仍读取全部 text index rows 传给 Rust `evaluate_scope_gate`，没有进一步降到纯 SQL 汇总。
- 无有效索引时仍走旧慢路径，本批没有实现写回入口自动重建索引。
- Rust 写回计划自身仍会读取游戏文件和数据库生成计划；本批只收束写入前 Python 文本范围与质量 gate。

## 下一批入口

- 建议下一批：写回快路径索引行读取与 fallback 自动重建继续收束。优先评估能否用 text index summary、SQL pending/stale 计数和质量错误路径计数替代全量 `read_text_index_items()`，并明确索引缺失时是否由写回入口自动重建。
