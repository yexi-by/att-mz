# Rust 迁移 Review 修复进度

## 当前结论

`docs/development/rust-migration-review-final-report.md` 中记录的 28 个 finding 已按优先级分轮处理，当前闭环状态以 `docs/development/rust-migration-review-closure-matrix.md` 为准。

本记录只保留当前有效的修复摘要和验证结果，不保留已撤回的 workflow 证据治理流水账。

## 保留的必要修复

- P1 功能与契约阻断：恢复写入后当前运行文件审计，修正 `post_write_audit_ms` 语义，release workflow 增加 Rust fmt、clippy、test，Rust 写回计划缺少 `allowed_translation_paths` 时 fail-fast，`add-game --json` 可信源快照冲突归类为 `business_error`。
- 写入路径等价：清理旧 Python 写回路径，统一走 handler/native plan，补 `write-back`、`rebuild-active-runtime`、`run-all` 真实路径测试，插件源码 runtime map 保存前做最终 AST 验证。
- 文本协议与 fail-fast：结构化字段按插件配置、事件参数、Note 标签原字段语义检查；关键布局字段、事件排序路径、启用插件名称、译文行缺失或空白均显式报错。
- 性能与并发：批量 JS AST 扫描、Rayon 并发、只读文本范围默认不跑写回探针、状态查询快速路径、工作区验收上下文复用、当前运行审计缓存、JSON/deepcopy 减重、sidecar 大文件内容。
- 大样本验证：使用 `data/db/サキュバスアカデミア.db` 的临时副本和样本副本完成真实 `rebuild-active-runtime` 替换路径验证；原始样本未污染，临时目录已清理。
- Skill 线程策略：开发版和发行版 Skill 明确 `ATT_MZ_RUST_THREADS` 没有 4 线程上限，长任务优先按运行主机可用逻辑处理器数量配置。

## 已删除的过度产物

- 删除 `scripts/collect_workflow_evidence.py` 和对应测试，撤掉专门的 workflow run 证据校验脚本。
- 删除 `.github/workflows/performance-gate.yml`，不把私有样本性能验证塞进自托管 GitHub workflow。
- 删除 `tests/test_review_closure_matrix.py`，不再用报告元测试约束闭环矩阵。
- 发布文档保留 release workflow 的 Rust gate；大样本性能验证回到本地 benchmark 命令。

## 验证快照

- `uv run basedpyright`：通过，0 error，0 warning。
- `uv run pytest`：通过，523 passed，耗时 77.31s。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：通过，59 passed。
- `uv run python -m py_compile scripts/benchmark_rebuild_active_runtime.py scripts/benchmark_active_runtime_audit.py`：通过。
- `git diff --check`：通过；仅输出 LF/CRLF 换行转换警告，没有空白错误。

后续若继续修改代码，需要重新执行与改动范围对应的检查。
