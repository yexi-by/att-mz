# Rust Scope/Index Engine 批次 58 记录

## 本批范围

- 批次：6AA，旧 scanner 语义测试首组 Rust-derived 替换。
- 覆盖范围：`tests/test_plugin_source_text.py` 中 6 个不需要保留 legacy batch/cache 内部语义的测试、`tests/test_scan_budget.py`、计划表和本记录。
- 成功状态：这 6 个测试改用 `build_native_plugin_source_scan`；`build_plugin_source_scan(` 直接调用只剩 2 个明确验证旧 batch/cache 机制的对照测试。
- 明确非范围：本批不删除 `app/plugin_source_text/scanner.py` 内 `_build_legacy_plugin_source_scan` 或 `_scan_legacy_plugin_source_files_text_strict`，不迁移 `test_plugin_source_scan_batches_native_ast_parse_for_source_files` 和 `test_plugin_source_scan_reuses_native_ast_by_file_hash`，不改生产代码、CLI、数据库 schema、Rust 原生代码或发布流程。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_first_group_uses_native_scan`：
  - 断言 6 个目标测试函数体内调用 `build_native_plugin_source_scan`。
  - 断言这 6 个目标测试函数体内不再调用 `build_plugin_source_scan`。
  - 断言当前 `tests/test_plugin_source_text.py` 中直接调用 `build_plugin_source_scan(` 的函数只剩：
    - `test_plugin_source_scan_batches_native_ast_parse_for_source_files`
    - `test_plugin_source_scan_reuses_native_ast_by_file_hash`
- 新增 `tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本记录覆盖 6 个迁移测试、2 个保留 legacy 对照测试和 batch58 保护测试。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 同步调整旧保护：
  - batch53 当前剩余 legacy 计数收窄为 2 个 batch/cache 对照测试。
  - batch56 repo-wide 残留分类里的 direct call 计数同步收窄为这 2 个对照测试。

## 实现说明

- 更新 `tests/test_plugin_source_text.py`：
  - 将 `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 改用 `build_native_plugin_source_scan`。
  - 将 `test_plugin_source_ast_map_exports_short_source_text_with_ast_context` 改用 `build_native_plugin_source_scan`。
  - 将 `test_non_utf8_plugin_source_does_not_break_default_game_loading` 改用 `build_native_plugin_source_scan`。
  - 将 `test_plugin_source_scan_decodes_doubled_control_literal_without_real_line_break` 改用 `build_native_plugin_source_scan`。
  - 将 `test_plugin_source_high_risk_pauses_workflow_until_rules_are_confirmed` 改用 `build_native_plugin_source_scan`。
  - 将 `test_plugin_source_rule_validation_rejects_invalid_js_directly` 改用 `build_native_plugin_source_scan`。
- 更新 `tests/test_scan_budget.py`：
  - 新增 batch58 首组迁移保护和记录保护。
  - 更新 batch53、batch56 的当前 legacy call count 保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6AA 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files`
  - `test_plugin_source_ast_map_exports_short_source_text_with_ast_context`
  - `test_non_utf8_plugin_source_does_not_break_default_game_loading`
  - `test_plugin_source_scan_decodes_doubled_control_literal_without_real_line_break`
  - `test_plugin_source_high_risk_pauses_workflow_until_rules_are_confirmed`
  - `test_plugin_source_rule_validation_rejects_invalid_js_directly`
- 保留路径：
  - `test_plugin_source_scan_batches_native_ast_parse_for_source_files` 仍验证旧 scanner 批量 AST 入口，不在本批迁移。
  - `test_plugin_source_scan_reuses_native_ast_by_file_hash` 仍验证旧 scanner 文件 hash 缓存机制，不在本批迁移。
  - `tests/test_plugin_source_text.py` 仍显式导入 `_build_legacy_plugin_source_scan as build_plugin_source_scan`，因为上述 2 个对照测试仍直接需要它。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构、Rust API 和发布流程不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O、SQLite 查询或 Rust 调用。
- `tests/test_plugin_source_text.py` 中 `build_plugin_source_scan(` 直接调用从 9 处降到 3 处，调用函数从 8 个降到 2 个。
- 剩余 2 个 legacy 测试只覆盖旧 scanner batch/cache 对照语义，不再承担普通业务行为事实准备。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_first_group_uses_native_scan tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：目标测试仍调用 `build_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-058.md` 尚不存在。
- 目标行为测试：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_scan_only_counts_enabled_direct_plugin_files tests/test_plugin_source_text.py::test_plugin_source_ast_map_exports_short_source_text_with_ast_context tests/test_plugin_source_text.py::test_non_utf8_plugin_source_does_not_break_default_game_loading tests/test_plugin_source_text.py::test_plugin_source_scan_decodes_doubled_control_literal_without_real_line_break tests/test_plugin_source_text.py::test_plugin_source_high_risk_pauses_workflow_until_rules_are_confirmed tests/test_plugin_source_text.py::test_plugin_source_rule_validation_rejects_invalid_js_directly`
  - 结果：6 passed。
- 目标 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_scan_only_counts_enabled_direct_plugin_files tests/test_plugin_source_text.py::test_plugin_source_ast_map_exports_short_source_text_with_ast_context tests/test_plugin_source_text.py::test_non_utf8_plugin_source_does_not_break_default_game_loading tests/test_plugin_source_text.py::test_plugin_source_scan_decodes_doubled_control_literal_without_real_line_break tests/test_plugin_source_text.py::test_plugin_source_high_risk_pauses_workflow_until_rules_are_confirmed tests/test_plugin_source_text.py::test_plugin_source_rule_validation_rejects_invalid_js_directly tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_first_group_uses_native_scan tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_record_exists_and_tracks_contract`
  - 结果：10 passed。
- 记录补写后复验：`uv run pytest tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_record_exists_and_tracks_contract`
  - 结果：1 passed。
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

- 本批审查重点是确认迁移测试不验证旧 scanner batch/cache 内部机制，且两个真正 legacy 对照测试仍保留。
- 目标测试和 scan_budget 保护确认 6 个业务语义测试已改用 native scan，剩余 direct legacy 调用只在 2 个 batch/cache 对照测试里。
- 本批未新增生产运行路径，也未改变 CLI、数据库 schema、Rust 原生代码或发布流程。

## 剩余风险

- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在于 `app/plugin_source_text/scanner.py`。
- `tests/test_plugin_source_text.py` 仍有 2 个旧 scanner batch/cache 对照测试直接调用 `build_plugin_source_scan(`。
- 当前工作树混有前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：旧 scanner batch/cache 对照测试保留边界审计。
- 建议边界：确认 `test_plugin_source_scan_batches_native_ast_parse_for_source_files` 和 `test_plugin_source_scan_reuses_native_ast_by_file_hash` 是否仍有价值；如果只验证已不再生产默认的旧内部机制，应改成历史记录或删除对应 legacy helper 依赖。
- 理由：普通业务行为测试已经迁到 native scan，剩余直接调用集中在旧 scanner batch/cache 内部机制本身。
