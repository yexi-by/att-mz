# Rust Scope/Index Engine 批次 3A 三入口契约记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只建立 Rust Scope/Index Engine 的三个原生入口族、Python adapter 和最小可验证核心输出，不接入现有 P0/P1 CLI 调用链，不新增 SQLite summary 表，不替换现有 Python `TextScopeService` 默认生产路径。

涉及文件：

- `app/native_contract.py`
- `app/native_scope_index.py`
- `rust/src/lib.rs`
- `rust/src/native_core.rs`
- `rust/src/native_core/scope_index/mod.rs`
- `tests/test_native_scope_index.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-003.md`

## 保护网

先建立或调整的测试：

- `tests/test_native_scope_index.py::test_build_native_scope_index_returns_rows_and_summaries`
- `tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_candidate_summary`
- `tests/test_native_scope_index.py::test_evaluate_native_scope_gate_returns_compact_gate_summary`
- `tests/test_scan_budget.py::test_batch03_scope_index_contract_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_native_scope_index.py`：collection 失败，`app.native_scope_index` 尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch03_scope_index_contract_record_exists_and_is_linked_from_plan`：失败，批次 3 验收记录尚不存在。

## 改动范围

- 新增 `app/native_scope_index.py`，提供 `build_native_scope_index()`、`scan_native_rule_candidates()` 和 `evaluate_native_scope_gate()` 三个 Python adapter。
- Rust 新增 `native_core::scope_index` 模块，实现三入口最小核心：
  - `build_scope_index` 产出 text index rows、scope summary、domain summary、rule hit summary、candidate summary、unwritable reasons、stale rule details 和 writable path list。
  - `scan_rule_candidates` 产出候选清单和按 domain 汇总的 candidate summary。
  - `evaluate_scope_gate` 产出 workflow gate、quality gate、pending count、translated count、quality error count 和 writable path list。
- PyO3 暴露 `build_scope_index`、`scan_rule_candidates`、`evaluate_scope_gate`。
- native contract version 提升到 4，确保旧扩展不会悄悄缺入口。

## 旧路径收束

- 本批不删除现有 Python `TextScopeService`、插件源码扫描、非标准 data 扫描或 text index 写入路径。
- 新增入口已经通过 adapter 与 contract 固定为后续唯一 Rust 边界；下一批接入真实扫描和 SQLite summary 时，旧 Python 重型路径才能开始改为薄适配层或删除。

## 外部契约变化

- 原生扩展契约版本提升到 4。
- 新增 Rust/Python JSON 边界入口：
  - `build_scope_index(payload_json: str) -> str`
  - `scan_rule_candidates(payload_json: str) -> str`
  - `evaluate_scope_gate(payload_json: str) -> str`
- CLI 参数、stdout Agent JSON、SQLite schema、工作区 JSON 和 README/Skill 本批不变。

## 性能证据

本批没有接入实际大规模扫描和 CLI 热路径，不运行大样本耗时对比。性能相关证据限定为：

- 三个 Rust 入口均经过统一线程池配置函数执行。
- `build_scope_index` 在 Rust 侧一次性生成 rows 与 summaries，避免 Python adapter 二次汇总。
- 后续批次可以把 P0/P1 命令接入同一 Rust 边界，而不是继续新增分散入口。

## 验证结果

- `cargo test --manifest-path rust/Cargo.toml native_core::scope_index::tests::build_scope_index_outputs_text_rows_and_summaries`：1 passed。
- `uv run maturin develop --manifest-path rust/Cargo.toml`：成功重建本地 PyO3 扩展。
- `uv run pytest tests/test_native_scope_index.py`：3 passed。
- `uv run pytest tests/test_native_scope_index.py tests/test_scan_budget.py`：8 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `uv run pytest`：701 passed。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：68 passed。

## 剩余风险

- Scope/Index Engine 当前输入仍由结构化条目驱动，尚未接管 RPG Maker 标准 data、插件参数、事件、Note、插件源码 AST 和非标准 data 的真实扫描。
- SQLite summary schema 尚未新增，现有持久 text index 仍未写入 scope/domain/rule hit summary。
- P0 `export-pending-translations --limit` 和 P1 命令尚未接入本批新增 Rust 入口。
- `TextScopeService.writable_paths` 的重复构建问题尚未在本批修复。

## 下一批入口

批次 3B：SQLite summary schema 与真实扫描接入。建议先新增 summary 表迁移和 persistence 读写测试，再让 `rebuild-text-index` 能消费 `build_scope_index` 结果写入 rows 与 summaries。
