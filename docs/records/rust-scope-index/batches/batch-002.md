# Rust Scope/Index Engine 批次 2 配置收口记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 Rust 线程数配置入口收口，不进入 Scope/Index Engine 新 API、SQLite schema 迁移、P0 pending 快路径或 P1 命令迁移。

涉及文件：

- `setting.example.toml`
- `app/config/schemas.py`
- `app/config/__init__.py`
- `app/utils/config_loader_utils.py`
- `app/native_contract.py`
- `app/native_quality.py`
- `rust/src/native_core/pool.rs`
- `rust/src/native_core.rs`
- `rust/src/lib.rs`
- `scripts/benchmark_rebuild_active_runtime.py`
- `scripts/benchmark_active_runtime_audit.py`
- `tests/test_config_overrides.py`
- `tests/test_native_adapters.py`
- `tests/test_benchmark_rebuild_active_runtime.py`
- `tests/test_benchmark_active_runtime_audit.py`
- `tests/test_benchmark_small_tasks.py`
- `tests/test_scan_budget.py`

## 保护网

先建立或调整的测试：

- `tests/test_config_overrides.py` 覆盖 `[runtime].rust_threads` 读取、默认值、非法值和加载配置时调用 Rust 配置入口。
- `tests/test_native_adapters.py` 覆盖 Python adapter 把 `auto` 映射为 Rust `None`，正整数原样传入。
- benchmark 测试覆盖 `--rust-threads` 写入临时 `setting.toml`，子进程环境只验证必要的 `ATT_MZ_HOME`。
- Rust pool 单测覆盖显式配置 `auto`、正整数和非法 `0`。

RED 结果：

- `uv run pytest tests/test_config_overrides.py tests/test_native_adapters.py tests/test_benchmark_rebuild_active_runtime.py tests/test_benchmark_active_runtime_audit.py tests/test_benchmark_small_tasks.py`：12 failed, 74 passed。
- `cargo test --manifest-path rust/Cargo.toml native_core::pool::tests::runtime_thread_config_accepts_auto_or_positive_count`：编译失败，`configure_runtime_threads` 尚不存在。

## 改动范围

- 新增 `RuntimeSetting`，`runtime.rust_threads` 只接受 `"auto"` 或严格正整数；`setting.example.toml` 默认写入 `[runtime] rust_threads = "auto"`。
- `load_setting()` 在配置校验后调用 `configure_native_runtime_threads()`，日志摘要显示当前 Rust 原生线程配置。
- Python native adapter 新增 `configure_native_runtime_threads()`，把 `"auto"` 转为 Rust `None`。
- Rust pool 删除生产环境变量读取，改为进程内显式配置；PyO3 暴露 `configure_runtime_threads`。
- Python/Rust 两侧 native contract version 提升到 3，旧扩展会在加载时显式报错。
- benchmark 脚本保留 `--rust-threads` 参数用于性能记录和临时配置写入，不再通过子进程环境传递线程数。

## 旧路径收束

- 生产 Rust 代码不再读取旧线程环境变量。
- `app/`、`rust/src/`、`scripts/`、`tests/` 中已静态确认旧线程环境变量名不存在。
- 测试不再把旧线程环境变量作为断言对象。

## 外部契约变化

- `setting.toml` 新增 `[runtime].rust_threads`。
- 有效值为 `"auto"` 或正整数；`0`、负数、空字符串和字符串整数会显式失败。
- Rust 线程数报告来自当前配置；默认 `"auto"` 使用 Rayon 默认线程数。
- benchmark 的 `--rust-threads` 仍保留为脚本参数，但只写入临时 `setting.toml`。
- 原生扩展契约版本提升到 3；旧扩展需要重新构建或使用匹配发行包。

## 性能证据

本批没有引入 Scope/Index Engine 热路径，不运行大样本性能对比。可验证性能边界是配置入口真实参与调度：

- Rust pool 单测证明显式正整数会进入局部线程池配置读取。
- native adapter 测试证明 Python 配置会传到 Rust。
- benchmark 测试证明性能脚本生成的临时配置包含本次线程数。

## 验证结果

- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配。
- `cargo test --manifest-path rust/Cargo.toml native_core::pool::tests::runtime_thread_config_accepts_auto_or_positive_count`：1 passed。
- `uv run maturin develop --manifest-path rust/Cargo.toml`：成功重建本地 PyO3 扩展。
- `uv run pytest tests/test_config_overrides.py tests/test_native_adapters.py tests/test_benchmark_rebuild_active_runtime.py tests/test_benchmark_active_runtime_audit.py tests/test_benchmark_small_tasks.py tests/test_scan_budget.py`：90 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `uv run pytest`：696 passed。
- `cargo test --manifest-path rust/Cargo.toml`：67 passed。

## 剩余风险

- README、Skill 和其他说明文档里的旧线程入口说明尚未在本批统一清理；计划中仍留到后续文档同步批次处理。
- Scope/Index Engine 入口尚未实现，P0/P1 慢链路还没有性能改善。
- 本批没有大样本 benchmark 数据，因为改动对象是配置传递入口而不是扫描实现。

## 下一批入口

批次 3：Rust Scope/Index Engine 核心。建议先为 `build_scope_index`、`scan_rule_candidates`、`evaluate_scope_gate` 建立 native contract 测试和 payload 模型，再实现 Rust 模块骨架与 Python adapter。
