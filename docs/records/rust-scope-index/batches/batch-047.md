# Rust Scope/Index Engine 批次 47 记录

## 本批范围

- 批次：6P，旧 scanner 测试夹具首组 Rust-derived 替换。
- 覆盖范围：`tests/test_plugin_source_text.py` 内一组只为准备 selector、file_hash 或规则输入而调用旧 scanner 的测试夹具。
- 成功状态：首组选定用例改用 `build_native_plugin_source_scan` 准备候选事实；这些测试不再通过 `_build_legacy_plugin_source_scan` 别名获取 selector/hash。
- 明确非范围：本批不删除 `_build_legacy_plugin_source_scan` 或 `_scan_legacy_plugin_source_files_text_strict`，不迁移仍在验证旧扫描缓存、旧 strict scan 或旧 AST 语义的对照测试。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch47_plugin_source_text_fixtures_seed_with_native_scan`：
  - 读取 `tests/test_plugin_source_text.py` 中 5 段已迁移测试函数源码。
  - 用 Python AST 收集真实调用节点，避免注释或 docstring 里的同名文本造成误判。
  - 断言这些测试函数调用 `build_native_plugin_source_scan`。
  - 断言这些测试函数不再调用 `build_plugin_source_scan`。
- 新增 `tests/test_scan_budget.py::test_batch47_plugin_source_fixture_migration_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_plugin_source_text.py::test_plugin_source_rules_extract_and_write_back_ast_string`
  - `tests/test_plugin_source_text.py::test_plugin_source_extraction_rejects_stale_rule_hash`
  - `tests/test_plugin_source_text.py::test_plugin_source_rule_filter_fallback_uses_native_plugin_source_scan`
  - `tests/test_plugin_source_text.py::test_plugin_source_import_fallback_uses_native_plugin_source_scan`
  - `tests/test_plugin_source_text.py::test_plugin_source_extraction_fallback_uses_native_plugin_source_scan`

## 实现说明

- 更新 `tests/test_plugin_source_text.py`：
  - 从 `app.plugin_source_text` 导入 `build_native_plugin_source_scan`。
  - 将首组 5 个只需要 selector/hash 的前置扫描改为 `build_native_plugin_source_scan`。
  - 这 5 个用例由批次保护测试固定，避免后续重新退回旧 `build_plugin_source_scan` 别名。
- 更新 `tests/test_scan_budget.py`：
  - 增加 `_source_for_test_function` 辅助函数，用 AST 定位指定测试函数源码。
  - 增加本批静态夹具迁移保护和批次记录保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6P 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_plugin_source_rules_extract_and_write_back_ast_string`
  - `test_plugin_source_extraction_rejects_stale_rule_hash`
  - `test_plugin_source_rule_filter_fallback_uses_native_plugin_source_scan`
  - `test_plugin_source_import_fallback_uses_native_plugin_source_scan`
  - `test_plugin_source_extraction_fallback_uses_native_plugin_source_scan`
  - 以上 5 段测试不再用旧 scanner 别名准备 selector/hash。
- 本批保留的旧语义测试：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 继续使用旧 scanner，保留直接文件统计、风险计数和嵌套文件排除的 legacy 语义覆盖。
- 保留路径：
  - `_build_legacy_plugin_source_scan` 仍保留给旧扫描缓存、旧 AST batch 调用和旧规则行为对照测试。
  - `_scan_legacy_plugin_source_files_text_strict` 仍保留给 legacy strict scan 对照和 runtime write probe 相关禁止钩子。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。
- 迁移后测试中使用的 selector、file_hash 来自 Rust-derived scan，更贴近当前生产默认路径。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- 测试夹具前置候选事实改用 `build_native_plugin_source_scan`，减少对旧 Python scanner 的测试依赖。
- fallback 类测试仍通过 monkeypatch 统计 `scan_native_rule_candidates`，确认被测公共 fallback 只触发 1 次 native 候选扫描。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch47_plugin_source_text_fallback_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch47_plugin_source_fixture_migration_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：目标 fallback 测试仍未调用 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-047.md` 尚不存在。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_rules_extract_and_write_back_ast_string tests/test_plugin_source_text.py::test_plugin_source_extraction_rejects_stale_rule_hash tests/test_plugin_source_text.py::test_plugin_source_rule_filter_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_import_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_extraction_fallback_uses_native_plugin_source_scan tests/test_scan_budget.py::test_batch47_plugin_source_text_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch47_plugin_source_fixture_migration_record_exists_and_tracks_contract`
  - 结果：7 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：810 passed in 265.08s。
- 文档保护最终验证：`uv run pytest tests/test_scan_budget.py::test_batch47_plugin_source_text_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch47_plugin_source_fixture_migration_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- 旧夹具剩余调用统计：`rg -n "build_native_plugin_source_scan\\(|build_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：`tests/test_plugin_source_text.py` 中本批保留 5 处 `build_native_plugin_source_scan` 调用和 27 处 `build_plugin_source_scan` legacy 夹具调用。
- Rust 门禁：本批未修改 Rust 源码或构建流程，因此未执行 `cargo fmt`、`cargo clippy` 和 `cargo test`。

## 审查处理

- 只读子代理审查发现 `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 初版改动误迁移了旧 scanner 统计语义测试；已恢复为旧 scanner 调用，并在本记录中把它列为本批保留路径。
- 只读子代理审查发现初版静态保护只覆盖 3 个 fallback 用例，无法固定另外 2 个 selector/hash 用例；已扩展到 5 个迁移用例。
- 只读子代理审查发现初版静态保护用字符串包含判断，可能被注释或 docstring 误导；已改为 AST 调用节点检查。
- 只读子代理审查发现初版 GREEN 命令未包含记录保护测试；已修正验证命令，明确同时运行迁移保护和记录保护。

## 剩余风险

- `tests/test_plugin_source_text.py` 仍有多处旧 scanner 私有兼容入口调用；这些调用尚未逐一判断是否可迁移。
- 本批静态保护覆盖 5 段已迁移测试，防止它们退回旧 scanner；其他 legacy 夹具仍需后续按语义分组审计。
- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在，后续需要继续按分组收束。

## 下一批入口

- 建议下一批：旧 scanner 测试夹具第二组 Rust-derived 替换。
- 建议边界：优先迁移仍只用 selector/file_hash 构造规则、且已经在生产路径有 native fallback 覆盖的 AgentToolkit 级测试；暂不触碰旧 batch AST、cache 复用、runtime strict scan 和写回探针对照测试。
- 理由：6P 已证明首组 selector/hash 夹具可直接使用 Rust-derived scan，下一批可以继续减少私有 legacy helper 的测试依赖。
