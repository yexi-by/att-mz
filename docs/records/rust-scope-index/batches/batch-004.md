# Rust Scope/Index Engine 批次 3B SQLite summary 记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只新增持久文本范围索引的 summary schema、读写记录和 `rebuild-text-index` 写入链路。不接入 P0 pending 导出快路径，不删除 Python `TextScopeService` 主扫描路径，也不实现 RPG Maker 标准 data、插件源码或非标准 data 的 Rust 真实扫描器。

涉及文件：

- `app/persistence/records.py`
- `app/persistence/sql.py`
- `app/persistence/repository.py`
- `app/persistence/text_index_records.py`
- `app/text_index.py`
- `tests/test_persistence.py`
- `tests/test_text_index.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-004.md`

## 保护网

先建立或调整的测试：

- `tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`
- `tests/test_text_index.py::test_rebuild_text_index_persists_current_text_scope`
- `tests/test_text_index.py::test_agent_service_rebuild_text_index_writes_database_index`
- `tests/test_scan_budget.py::test_batch04_summary_schema_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：collection 失败，summary dataclass 尚不存在。
- `uv run pytest tests/test_text_index.py::test_rebuild_text_index_persists_current_text_scope`：失败，session 尚无 `read_text_index_scope_summary()`。
- `uv run pytest tests/test_scan_budget.py::test_batch04_summary_schema_record_exists_and_is_linked_from_plan`：失败，批次 3B 验收记录尚不存在。

## 改动范围

- schema version 从 14 升到 15。
- 新增三张静态 summary 表：
  - `text_index_scope_summary`
  - `text_index_domain_summary`
  - `text_index_rule_hit_summary`
- 新增持久化记录：
  - `TextIndexScopeSummaryRecord`
  - `TextIndexDomainSummaryRecord`
  - `TextIndexRuleHitSummaryRecord`
- `replace_text_index()` 支持与 metadata/items 同事务替换 summary；`clear_text_index()` 同时清空 summary。
- 新增 summary 读取接口。
- `rebuild_text_index()` 通过 `build_native_scope_index()` 生成 text index rows 与 summary，再写入 SQLite。

## 旧路径收束

- 本批没有删除旧 Python 扫描路径。
- `rebuild_text_index()` 的 rows 与 summary 已开始消费 Rust Scope/Index Engine 输出，避免 Python 在写库前另建 summary 事实。
- 当前 Python scope 仍作为过渡输入传给 Rust；真实扫描器接入后，这一过渡 payload 需要被 Rust 内部扫描结果替代。

## 外部契约变化

- SQLite schema 升级到 15；旧数据库会按当前项目策略显式失败并要求重建或重新注册。
- 新增 summary 表属于数据库内部契约；CLI stdout、命令参数、工作区 JSON、README 和 Skill 本批不变。

## 性能证据

本批未运行大样本性能对比，因为仍未接入真实 Rust 扫描器和 P0/P1 命令快路径。可验证的性能相关变化是：

- 静态 summary 写入数据库，后续 `audit-coverage`、`quality-report`、`text-scope` 等命令可从 SQLite summary 读取范围事实。
- `rebuild_text_index()` 不再由 Python 单独推导 summary，而是消费 Rust `build_scope_index` 输出。

## 验证结果

本批目标测试已先转绿：

- `uv run pytest tests/test_persistence.py::test_register_game_creates_declared_static_table_set tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：2 passed。
- `uv run pytest tests/test_text_index.py::test_rebuild_text_index_persists_current_text_scope tests/test_text_index.py::test_agent_service_rebuild_text_index_writes_database_index`：2 passed。
- `uv run pytest tests/test_persistence.py::test_register_game_creates_declared_static_table_set tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate tests/test_text_index.py::test_rebuild_text_index_persists_current_text_scope tests/test_text_index.py::test_agent_service_rebuild_text_index_writes_database_index tests/test_scan_budget.py`：10 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `uv run pytest`：702 passed。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：68 passed。

## 剩余风险

- 真实 Rust 扫描器尚未接入，`TextScopeService` 仍负责构建过渡 scope。
- P0 `export-pending-translations --limit` 尚未改变。
- P1-A/P1-B 命令尚未读取新 summary 表。
- 新 summary 当前主要由 rebuild 写入，还没有覆盖覆盖审计、质量报告、工作区命令的消费路径。

## 下一批入口

批次 3C：真实 Rust 扫描接入。建议优先从标准 data / event command 的最小扫描器开始，让 `build_scope_index` 能直接从结构化 GameData payload 产生 rows 与 summary，再逐步接插件参数、Note、插件源码和非标准 data。
