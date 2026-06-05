# Rust Scope/Index Engine 批次 42 记录

## 本批范围

- 批次：6K，active runtime 插件源码扫描缓存接入专用 Rust-AST runtime 入口。
- 覆盖范围：`audit_active_runtime_plugin_source`、`audit_active_runtime_plugin_source_with_scan_cache`、`scan_plugin_source_files_text_strict_with_cache` 的当前运行插件源码扫描路径。
- 成功状态：active runtime 审计和扫描缓存 miss/stale 重扫不再调用翻译源 `scan_plugin_source_files_text_strict` 入口；改由 `scan_plugin_source_runtime_files_text_strict` 进入 `parse_native_javascript_string_spans_batch`，只构造当前运行字符串字面量和语法错误。
- 关键边界：Rust `scan_rule_candidates` 是可翻译候选入口，会按源文规则过滤字符串，不能作为 active runtime 的全部字符串字面量事实源。本批保留“Rust AST 批量解析 + Python 薄转换”的运行时语义，避免漏掉控制符、协议片段或低置信字面量。
- 明确非范围：`app/agent_toolkit/services/quality.py::_build_plugin_source_write_map_source_scan_cache`、`app/text_scope/write_probe.py` 和旧 `build_plugin_source_scan` 公共导出仍留到后续批次。

## 保护网

- 调整 `tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files`：
  - 首次审计写入 runtime scan cache。
  - 第二次审计命中缓存，断言 `active_runtime_scan_cache_rescan_file_count == 0` 且不调用 runtime 扫描入口。
  - 修改一个插件源码文件后，第三次审计只重扫 stale 文件，断言 `active_runtime_scan_cache_rescan_file_count == 1`。
  - monkeypatch 禁止 `runtime_audit.scan_plugin_source_files_text_strict` 和 `scanner.scan_plugin_source_files_text_strict`。
  - 计数 wrapper 调用真实 `scan_plugin_source_runtime_files_text_strict`，用于固定 runtime helper 自身不会委托回旧 strict scan。
- 保留 `tests/test_plugin_source_text.py::test_active_runtime_audit_batches_native_ast_scan`：
  - 断言 active runtime 审计使用 `parse_native_javascript_string_spans_batch` 批扫。
  - 禁止逐文件 `parse_native_javascript_string_spans` 入口，避免跨 Python/Rust 边界逐文件调用。
- 新增 `tests/test_scan_budget.py::test_batch42_active_runtime_scan_cache_native_runtime_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 runtime helper、缓存入口、审计入口、摘要字段和保护测试都写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `app/plugin_source_text/scanner.py`：
  - 新增 `scan_plugin_source_runtime_files_text_strict`，专门服务 active runtime 审计和缓存重扫。
  - 抽出 `_scan_plugin_source_files_text_from_native_spans`，让翻译源 strict scan 和 runtime scan 共用同一个 Rust AST 批量解析薄转换。
  - runtime scan 固定 `text_rules=None`，只保留 `PluginSourceStringLiteral` 和语法错误，不构造翻译候选索引。
- 更新 `app/plugin_source_text/runtime_audit.py`：
  - `audit_active_runtime_plugin_source` 默认扫描路径改用 `scan_plugin_source_runtime_files_text_strict`。
  - `scan_plugin_source_files_text_strict_with_cache` 的 miss/stale 重扫改用 `scan_plugin_source_runtime_files_text_strict`。
  - 缓存命中恢复逻辑和 `active_runtime_scan_cache_*` 摘要字段保持不变。
- 更新 `app/plugin_source_text/__init__.py`：
  - 导出 `scan_plugin_source_runtime_files_text_strict`，让后续诊断和写回映射审计可以复用明确入口。

## 旧路径收束

- 已收束路径：
  - active runtime 无缓存审计不再调用翻译源 strict scan。
  - active runtime scan cache miss/stale 重扫不再调用翻译源 strict scan。
  - active runtime scan cache 命中路径继续从 SQLite 缓存记录恢复字面量，不触发 AST 扫描。
- 保留路径：
  - `scan_plugin_source_files_text_strict` 仍作为翻译源和公共旧 API 的严格扫描入口。
  - `build_plugin_source_scan` 旧导出仍保留，删除需要等写回探针、诊断和公共 API 收束。
  - `_build_plugin_source_write_map_source_scan_cache` 仍需独立审计，它服务 runtime write map 诊断，不等同于 active runtime scan cache。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- `active_runtime_scan_cache_rescan_file_count`、`active_runtime_scan_cache_hit_file_count`、`active_runtime_literal_count` 等摘要字段语义不变。
- 新增的 `scan_plugin_source_runtime_files_text_strict` 是内部源码 API 导出，不改变公开命令协议。

## 性能证据

- active runtime 缓存命中时不进入 Rust AST 扫描。
- active runtime 缓存 stale 时只把 hash 变化的文件传给 `scan_plugin_source_runtime_files_text_strict`。
- runtime scan 入口复用 `parse_native_javascript_string_spans_batch`，不会逐文件跨 Python/Rust 边界调用。
- runtime scan 不构造翻译源 `PluginSourceCandidate`，减少运行时审计缓存路径的候选对象构造和规则过滤成本。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files`
  - 结果：1 failed。
  - 失败原因：`runtime_audit` 尚无 `scan_plugin_source_runtime_files_text_strict`，缓存重扫仍绑定旧 strict scan 入口。
- GREEN：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files`
  - 结果：1 passed。
- 文档保护 RED：`uv run pytest tests/test_scan_budget.py::test_batch42_active_runtime_scan_cache_native_runtime_record_exists_and_tracks_contract`
  - 结果：1 failed。
  - 失败原因：`docs/records/rust-scope-index/batches/batch-042.md` 尚不存在。
- 文档保护 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch42_active_runtime_scan_cache_native_runtime_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py::test_active_runtime_audit_batches_native_ast_scan tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files tests/test_scan_budget.py::test_batch42_active_runtime_scan_cache_native_runtime_record_exists_and_tracks_contract`
  - 结果：3 passed。
- 审查修复回归：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files`
  - 结果：1 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：799 passed。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- Rust 门禁：本批未修改 Rust 源码或构建流程，因此未执行 `cargo fmt`、`cargo clippy` 和 `cargo test`；运行时 Rust AST adapter 相关行为已由相邻 Python 测试和全量 pytest 覆盖。

## 审查处理

- 本批实现前已审计 Rust `scan_rule_candidates` 的插件源码路径，确认其会调用 `should_translate_plugin_source_text` 并按源文规则过滤字符串。
- 因 active runtime 审计必须保留全部普通字符串字面量，本批没有把候选入口误用成 runtime scan cache 的事实源。
- 只读子代理审查指出：原缓存测试把 runtime helper 替换为计数 wrapper，但 wrapper 内部调用旧 `real_scan_plugin_source_files_text_strict`，不能证明 runtime helper 自身不会委托旧入口。本批已把 wrapper 改为调用真实 `real_scan_plugin_source_runtime_files_text_strict`，同时继续在 scanner 模块禁用旧 strict scan。
- 后续审查重点：`_build_plugin_source_write_map_source_scan_cache` 是否能复用 runtime helper 或 Rust-derived source scan，避免诊断路径继续承担旧 strict fallback。

## 剩余风险

- `_build_plugin_source_write_map_source_scan_cache` 仍用严格 AST 扫描构造 source selector 映射，后续需要结合 runtime write map 诊断单独迁移。
- `app/text_scope/write_probe.py` 的严格 AST fallback 仍保留给未迁移调用方。
- 旧 `build_plugin_source_scan` 公共导出仍保留；删除需要等 active runtime 诊断、写回探针和公共 API 调用方全部收束。

## 下一批入口

- 建议下一批：写回诊断源码扫描缓存与 write map source scan 审计。
- 建议边界：优先处理 `app/agent_toolkit/services/quality.py::_build_plugin_source_write_map_source_scan_cache`、`diagnose-active-runtime` 和写回后诊断输出，确认 source selector 映射能否复用 `scan_plugin_source_runtime_files_text_strict` 或 6J 的 Rust-derived 翻译源 scan。
- 理由：6K 已收束 active runtime scan cache；剩余插件源码旧扫描主要来自诊断和写回探针 fallback。
