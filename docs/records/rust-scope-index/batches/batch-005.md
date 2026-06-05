# Rust Scope/Index Engine 批次 3C data 扫描记录

状态：已完成
日期：2026-06-03
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只接入 `build_scope_index` 的最小真实 Rust data 扫描能力：从结构化 `data_files` payload 扫描 `System.json/gameTitle` 和事件指令 `code=401` 的 `parameters[0]`，并直接产出 text index rows、scope summary、domain summary 和 writable paths。

本批不接入插件参数、Note 标签、插件源码 AST、非标准 data 扫描，不改变 CLI 参数、stdout Agent JSON、SQLite schema，也不推进 P0 pending 导出快路径。

涉及文件：

- `rust/src/native_core/scope_index/mod.rs`
- `tests/test_native_scope_index.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-005.md`

## 保护网

先建立或调整的测试：

- `tests/test_native_scope_index.py::test_build_native_scope_index_scans_standard_data_and_event_commands`
- `tests/test_scan_budget.py::test_batch05_data_scan_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_native_scope_index.py::test_build_native_scope_index_scans_standard_data_and_event_commands`：失败，Rust 输入 JSON 解析提示缺少 `entries`，说明当前入口尚不能扫描 `data_files`。
- `uv run pytest tests/test_scan_budget.py::test_batch05_data_scan_record_exists_and_is_linked_from_plan`：失败，批次 3C 验收记录尚不存在。

## 改动范围

- `BuildScopeIndexPayload.entries` 改为默认空列表，保留上一批结构化条目输入兼容。
- 新增 `BuildScopeIndexPayload.data_files`，允许调用方传入结构化 RPG Maker data JSON。
- 新增 Rust 扫描器最小闭环：
  - `System.json/gameTitle` 生成 `standard_data` / `short_text` 索引行。
  - JSON 树中 `code=401` 且 `parameters[0]` 为字符串的事件指令生成 `event_command` / `long_text` 索引行。
- 扫描生成的条目与既有 `entries` 合并后统一进入 Rust rows 与 summary 生成流程。
- 新增 Rust 单元测试覆盖最小 data 扫描输出顺序和路径稳定性。

## 旧路径收束

- 本批开始替代 Python 侧“先构造 entries 再交给 Rust”的过渡输入形态，但只覆盖标准标题和事件 401 文本两个最小扫描点。
- 现有 `rebuild_text_index()` 仍使用 Python scope 作为过渡来源，本批没有删除 `TextScopeService` 主扫描路径。
- 真实接管范围扩大到插件参数、Note、插件源码和非标准 data 后，再按计划删除或改造成薄适配层；当前不新增隐藏回退路径。

## 外部契约变化

- Rust/Python JSON 边界新增可选字段 `data_files`。
- `entries` 保持兼容，但不再是 `build_scope_index` 的必填字段。
- CLI 参数、stdout Agent JSON、SQLite schema、工作区 JSON、README 和 Skill 本批不变。

## 性能证据

本批没有运行大样本命令耗时对比，因为只完成最小扫描器，不接入 CLI 热路径。

可验证的性能相关变化：

- `build_scope_index` 已能在 Rust 内部直接从结构化 data JSON 生成索引条目，后续 `rebuild-text-index` 可以逐步减少 Python 全量 scope 构建。
- rows、domain summary、scope summary 仍由同一个 Rust 构建流程一次产出，没有在 Python adapter 中二次汇总。

## 验证结果

本批目标测试已先转绿：

- `cargo test --manifest-path rust/Cargo.toml native_core::scope_index`：2 passed。
- `uv run maturin develop --manifest-path rust/Cargo.toml`：成功重建本地 PyO3 扩展。
- `uv run pytest tests/test_native_scope_index.py::test_build_native_scope_index_scans_standard_data_and_event_commands`：1 passed。
- `uv run pytest tests/test_native_scope_index.py`：4 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch05_data_scan_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run pytest tests/test_native_scope_index.py tests/test_scan_budget.py`：11 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `uv run pytest`：704 passed。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无命中。

## 剩余风险

- `rebuild_text_index()` 尚未直接传入 `data_files`，真实生产链路仍通过 Python scope 过渡。
- 标准 data 只覆盖 `System.json/gameTitle`，事件指令只覆盖 `code=401` 的第一参数。
- 插件参数、Note 标签、MV 虚拟名字框、插件源码 AST、非标准 data 和规则候选扫描仍未迁到 Rust。
- P0 `export-pending-translations --limit` 尚未接入 SQLite/Rust 快路径重建流程。

## 下一批入口

批次 4：P0 pending 导出快路径。建议优先让 `export-pending-translations --limit N` 在有效 text index 可用时直接走 SQLite `limit` 查询；索引缺失或失效时触发一次 Rust rebuild，再读取受 `limit` 限制的 pending 列表。
