# Rust Scope/Index Engine 批次 31 验收记录

## 本批范围

- 批次：5Y，写回计划可写路径直连 SQLite/Rust 评估。
- 覆盖入口：`write_back`、`rebuild_active_runtime`、`write_terminology` 的索引快路径写回计划输入，以及 Rust `build_write_back_plan` 缺省 `allowed_translation_paths` 时的读取行为。
- 成功状态：索引快路径不再由 Python 为 Rust 写回计划组装完整 `allowed_translation_paths` 列表；Rust 在缺省该字段时从当前游戏 SQLite 的 `text_index_items` 读取 `writable = 1` 的可写路径，并只读取这些路径对应的已保存译文。

## 保护网

- 调整 `tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build`：
  - 覆盖三类写回入口。
  - 禁止 warm index 写回计划 payload 继续包含完整 `allowed_translation_paths`。
  - 继续禁止旧 Python `TextScopeService`、workflow/quality fallback 和完整索引行读取。
- 调整 `tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：
  - 覆盖索引缺失、索引数量不一致和旧索引缺少源码支线 gate 预检元信息三种状态。
  - 禁止自动重建后的写回计划 payload 继续包含完整 `allowed_translation_paths`。
- 新增 `tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_saved_translation_outside_writable_text_index`：
  - 构造 warm index 后额外保存一条不在当前可写索引范围内的旧译文。
  - 禁止继续生成 Rust 写回计划，断言 handler 在 SQL stale gate 阶段阻断。
- 调整 `tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：
  - 固定 `count_translations_outside_writable_text_index()` 同时统计不可写索引路径和索引外译文。
  - 固定 `read_translated_items_for_writable_text_index()` 只返回当前可写索引范围内的译文。
- 新增 Rust 单测 `build_plan_reads_allowed_translation_paths_from_text_index_when_payload_omits_them`：
  - 删除 payload 中的 `allowed_translation_paths`。
  - 在测试 SQLite 中写入可写和不可写索引路径。
  - 断言 Rust 计划只按可写索引路径读取译文并生成写回计划。
- 新增 Rust 单测 `build_plan_rejects_unwritable_text_index_translation_when_payload_omits_allowed_paths`：
  - 删除 payload 中的 `allowed_translation_paths`。
  - 在不可写索引路径上保存译文。
  - 断言 Rust 计划把该译文识别为当前可写范围外的旧译文并阻断。
- 新增 `tests/test_scan_budget.py::test_batch31_write_plan_sqlite_allowed_paths_record_exists_and_is_linked_from_plan`：固定本批验收记录必须被计划表链接，且包含统一收尾章节。

## 改动范围

- `app/native_write_plan.py`
  - `build_native_write_back_setting_payload(...)` 允许 `writable_location_paths=None`。
  - 只有调用方显式传入列表时才写入 `allowed_translation_paths`。
- `app/application/handler.py`
  - 索引快路径 `PreparedWriteOperation` 的 `writable_location_paths` 改为 `None`，让 Rust 从 SQLite 读取可写路径。
  - 写回前质量检查用 SQL 统计已保存译文是否落在当前可写索引之外。
  - 可写译文读取改为 SQL join 当前可写文本索引。
- `app/persistence/sql.py` 与 `app/persistence/translation_records.py`
  - 新增 `COUNT_TRANSLATIONS_OUTSIDE_WRITABLE_TEXT_INDEX`。
  - 新增 `SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX`。
- `rust/src/native_core/write_back_plan/repository.rs`
  - 新增 `read_writable_text_index_location_paths(...)`，从 SQLite `text_index_items` 读取可写路径。
  - 当 payload 未提供可写路径且索引表不可读时显式报错，提示重新运行 `rebuild-text-index`。
- `rust/src/native_core/write_back_plan/mod.rs`
  - 构建写回计划时先打开数据库连接。
  - `allowed_translation_paths` 缺省时改为从 SQLite 读取。
- `rust/src/native_core/write_back_plan/test_support.rs`
  - 增加缺省 payload 字段时从 text index 读取可写路径的 Rust 回归测试。
- `tests/test_rmmz_write_plan.py`
  - 把索引快路径行为断言从“传完整可写路径列表”改为“不传完整列表，由 Rust/SQLite 决定”。
  - 增加 warm index stale translation 负例，固定 SQL stale gate 会阻断旧译文越界。
- `tests/test_persistence.py`
  - 增加当前可写索引译文读取和旧译文越界统计断言。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 批次进度追加 5Y，并给出下一批入口建议。

## 旧路径收束

- 索引快路径不再调用 Python `read_writable_text_index_location_paths()` 组装完整 `allowed_translation_paths`。
- 索引快路径不再把完整可写路径列表塞进 Rust 写回计划 payload。
- 写回前的“译文是否超出当前可写范围”检查不再读取所有译文路径后在 Python 集合里比对，改为 SQLite 侧 join 统计。
- 写回计划仍保留显式 `allowed_translation_paths` 入口，供非索引路径和 adapter 测试使用；索引快路径不再依赖该入口。

## 外部契约变化

- CLI 参数、配置字段、JSON schema、成功摘要字段和写回输出文件结构不变。
- Rust 写回计划内部 payload 允许省略 `allowed_translation_paths`；省略时要求数据库里存在当前契约下的 `text_index_items`。
- 若索引表不可读，Rust 会显式提示“写回计划缺少 allowed_translation_paths，且数据库当前文本范围索引不可读，请重新运行 rebuild-text-index”。

## 性能证据

- 行为测试禁止索引快路径向 Rust payload 传完整 `allowed_translation_paths`，证明 Python 不再为写回计划执行可写路径全量列表组装。
- Python 写回前质量检查改为 SQL 统计和 SQL join 读取，避免在 Python 中遍历全部译文路径后做集合差集。
- Rust 单测证明写回计划能在缺省 payload 字段时从 SQLite 读取可写路径，并忽略不可写索引路径。
- 审查后补充的 Rust 负例证明：不可写索引路径若保存了译文，不会被缺省 payload 误当作可写路径，而是作为当前可写范围外的旧译文阻断。
- 审查后补充的 Python 负例证明：handler 的 warm index stale gate 不需要重建 Python 全量文本范围，也不会继续生成 Rust 写回计划。

## 验证结果

- RED：`uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：12 failed，失败点为旧 payload 仍包含 `allowed_translation_paths`。
- RED：`cargo test --manifest-path rust/Cargo.toml build_plan_reads_allowed_translation_paths_from_text_index_when_payload_omits_them`：1 failed，旧 Rust 写回计划缺少 `allowed_translation_paths` 时直接失败。
- RED：`uv run pytest tests/test_scan_budget.py::test_batch31_write_plan_sqlite_allowed_paths_record_exists_and_is_linked_from_plan`：1 failed，批次 31 验收记录尚不存在。
- `uv run pytest tests/test_rmmz_write_plan.py::test_write_related_commands_reuse_text_index_scope_gate_without_python_scope_build tests/test_rmmz_write_plan.py::test_write_related_commands_rebuild_missing_or_stale_text_index_before_fast_gate`：12 passed。
- `cargo test --manifest-path rust/Cargo.toml build_plan_reads_allowed_translation_paths_from_text_index_when_payload_omits_them`：1 passed。
- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `cargo test --manifest-path rust/Cargo.toml write_back_plan`：41 passed。
- `uv run pytest tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate`：1 passed。
- `uv run maturin develop --manifest-path rust/Cargo.toml`：成功重建本地 PyO3 扩展。
- `uv run pytest tests/test_rmmz_write_plan.py`：27 passed。
- 审查后补测：`uv run pytest tests/test_persistence.py::test_text_index_records_replace_read_subset_and_invalidate tests/test_rmmz_write_plan.py::test_write_back_warm_index_rejects_saved_translation_outside_writable_text_index`：2 passed。
- 审查后补测：`cargo test --manifest-path rust/Cargo.toml write_back_plan`：42 passed。
- 收尾门禁：`uv run basedpyright`：0 errors，0 warnings，0 notes。
- 收尾门禁：`cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- 收尾门禁：批次文档敏感路径和未完成占位符扫描：无命中。
- 收尾门禁：`uv run pytest`：772 passed。
- 收尾门禁：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- 收尾门禁：`cargo test --manifest-path rust/Cargo.toml`：71 passed。
- 收尾门禁：`git diff --check`：通过；仅输出 Git 换行规范提示。

## 审查处理

- 实现自查：索引快路径 payload 不再携带完整可写路径列表；Rust 缺省字段时只从 SQLite 可写索引路径读取译文；非索引路径仍可显式传入列表保持原有适配层测试能力。
- 子代理审查未发现 Critical 问题。
- 子代理审查发现 Important 覆盖缺口：Python warm index stale translation gate 缺少负例，且新增 SQL 入口缺少直接持久化测试。
- 已修复：补充 handler 行为测试和持久化层断言，固定不可写索引路径和索引外译文都会被计为当前可写范围外的旧译文，且写回不会继续生成 Rust 计划。
- 子代理审查发现 Important 覆盖缺口：Rust 缺省 payload 测试未证明 `WHERE writable = 1`。
- 已修复：Rust 测试加入不可写索引行，并新增不可写路径存在译文时的阻断负例。

## 剩余风险

- Rust 直接读取 `text_index_items` 依赖当前数据库索引契约；旧库或损坏库会显式失败，需要重新运行 `rebuild-text-index`。
- 本批只收束写回计划的可写路径列表传递；工作区、规则导入、候选扫描等 P1-B 命令仍需后续按计划迁移到 Rust/index 事实。
- 大样本性能收益来自删除 Python 可写路径列表组装和路径集合比对，本批用行为测试证明路径已删除，未新增真实大样本 benchmark。

## 下一批入口

- 建议下一批：P1-B 工作区和规则命令迁移审计。重点先梳理 `prepare-agent-workspace`、`validate-agent-workspace`、`scan-plugin-source-text`、`scan-nonstandard-data` 和规则导入命令当前是否仍触发 Python 全量扫描、插件源码 AST 扫描或非标准 data 扫描，并选一个最小可验证入口迁到 Rust/index 候选事实。
