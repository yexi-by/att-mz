# Rust Scope/Index Engine 批次 59 记录

## 本批范围

- 批次：6AB，旧 scanner batch/cache 对照测试保留边界审计。
- 覆盖范围：`tests/test_plugin_source_text.py` 中剩余 2 个直接调用 `build_plugin_source_scan` 的 batch/cache 对照测试、`tests/test_scan_budget.py`、计划表和本记录。
- 成功状态：剩余 `build_plugin_source_scan(` 直接调用被固定为 3 处，且只属于 2 个旧 scanner 内部机制对照测试。
- 明确非范围：本批不删除 `app/plugin_source_text/scanner.py` 内 `_build_legacy_plugin_source_scan` 或 `_scan_legacy_plugin_source_files_text_strict`，不改生产代码、CLI、数据库 schema、Rust 原生代码或发布流程。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch59_legacy_batch_cache_tests_are_only_remaining_legacy_scan_users`：
  - 断言 `tests/test_plugin_source_text.py` 中直接调用 `build_plugin_source_scan` 的测试只剩：
    - `test_plugin_source_scan_batches_native_ast_parse_for_source_files`
    - `test_plugin_source_scan_reuses_native_ast_by_file_hash`
  - 断言 `_build_legacy_plugin_source_scan as build_plugin_source_scan` 的测试导入只存在于 `tests/test_plugin_source_text.py`。
  - 断言批量 AST 对照测试仍包含 `parse_native_javascript_string_spans_batch`、`parse_native_javascript_string_spans` 和 `batch_calls`。
  - 断言文件 hash 缓存对照测试仍包含 `clear_plugin_source_native_scan_cache`、`batch_calls`、`HashCacheA.js` 和 `HashCacheB.js`。
- 新增 `tests/test_scan_budget.py::test_batch59_legacy_batch_cache_boundary_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本记录覆盖 2 个保留 legacy 对照测试、旧 helper 名称和 batch59 保护测试。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `tests/test_scan_budget.py`：
  - 新增 batch59 剩余 legacy batch/cache 对照测试边界保护。
  - 新增 batch59 记录保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6AB 批次进度行。
- 新增 `docs/records/rust-scope-index/batches/batch-059.md`：
  - 记录本批审计结论、验证结果、剩余风险和下一批入口。

## 旧路径收束

- 当前剩余旧路径集中在 `tests/test_plugin_source_text.py`：
  - `test_plugin_source_scan_batches_native_ast_parse_for_source_files` 直接调用 `build_plugin_source_scan` 1 次，用于验证旧 scanner 通过 `parse_native_javascript_string_spans_batch` 批量解析插件源码。
  - `test_plugin_source_scan_reuses_native_ast_by_file_hash` 直接调用 `build_plugin_source_scan` 2 次，用于验证旧 scanner 的文件 hash 缓存复用。
- 当前保留生产私有 helper：
  - `_build_legacy_plugin_source_scan`
  - `_scan_legacy_plugin_source_files_text_strict`
- 本批结论：这些 direct legacy 调用已经不再承载普通业务语义，只剩旧 scanner batch/cache 内部机制对照用途；是否继续保留 helper，应进入下一批删除评估。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构、Rust API 和发布流程不变。
- 本批只新增测试保护和记录，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O、SQLite 查询或 Rust 调用。
- `build_plugin_source_scan(` 直接调用保持为 3 处，集中在 2 个 batch/cache 对照测试里。
- 新增 scan_budget 保护会阻止普通业务测试重新用旧 scanner 准备事实。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch59_legacy_batch_cache_tests_are_only_remaining_legacy_scan_users tests/test_scan_budget.py::test_batch59_legacy_batch_cache_boundary_record_exists_and_tracks_contract`
  - 结果：1 passed, 1 failed。
  - 失败原因：边界事实测试通过；`docs/records/rust-scope-index/batches/batch-059.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_scan_batches_native_ast_parse_for_source_files tests/test_plugin_source_text.py::test_plugin_source_scan_reuses_native_ast_by_file_hash tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_first_group_uses_native_scan tests/test_scan_budget.py::test_batch59_legacy_batch_cache_tests_are_only_remaining_legacy_scan_users tests/test_scan_budget.py::test_batch59_legacy_batch_cache_boundary_record_exists_and_tracks_contract`
  - 结果：7 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors, 0 warnings, 0 notes。
- 文档敏感路径和占位文案搜索：
  - 结果：无匹配。
- 空白检查：`git diff --check`
  - 结果：退出码 0；仅提示工作区现有 LF/CRLF 转换警告。
- 旧入口静态搜索：`rg -n "build_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：剩余 3 处，集中在 2 个保留 batch/cache 对照测试里。
- 全量测试：
  - 本批按 rust-scope-index-engine 临时验证策略未跑全量 `uv run pytest`。
  - 原因：本批是普通编号批次，未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程；本批不属于每 5 个编号批次收束点。

## 审查处理

- 本批审查重点是确认剩余 direct legacy 调用是否仍是普通业务行为事实准备。
- 审计结果：剩余 2 个测试只验证旧 scanner 批量 AST 和文件 hash 缓存内部机制，不再代表默认生产扫描路径。
- 本批未删除旧 helper，避免在审计批次中扩大到生产代码修改。

## 剩余风险

- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在于 `app/plugin_source_text/scanner.py`。
- `tests/test_plugin_source_text.py` 仍有 2 个旧 scanner batch/cache 对照测试直接调用 `build_plugin_source_scan(`。
- 当前工作树混有前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：旧 scanner 私有 helper 删除评估。
- 建议边界：确认 2 个 batch/cache 对照测试是否仍需要保留为旧内部机制测试；如果这些机制已经不是默认生产路径，应评估删除测试、删除 `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict`，或将其收敛为更明确的历史兼容边界。
- 理由：普通业务语义和共享 fixture 已迁到 native scan，剩余 legacy 依赖只验证旧 scanner 自身。
