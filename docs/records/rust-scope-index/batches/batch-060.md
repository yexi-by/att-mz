# Rust Scope/Index Engine 批次 60 记录

## 本批范围

- 批次：6AC，旧 scanner 私有 helper 删除评估。
- 覆盖范围：`app/plugin_source_text/scanner.py`、`tests/test_plugin_source_text.py`、`tests/test_agent_toolkit_workspace.py`、`tests/test_agent_toolkit_rule_import.py`、`tests/agent_toolkit_contract_fixtures.py`、`tests/test_scan_budget.py`、计划表和本记录。
- 成功状态：`_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 从生产模块删除；测试侧不再导入、调用或 monkeypatch 这两个私有 helper。
- 明确非范围：本批不改 CLI 参数、Agent JSON 字段、SQLite schema、Rust 原生代码或发布流程；历史批次记录中的旧名称只作为历史事实保留。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed`：
  - 断言 `app/` 中不再包含 `_build_legacy_plugin_source_scan` 或 `_scan_legacy_plugin_source_files_text_strict`。
  - 断言 `app/plugin_source_text/scanner.py` 不再定义两个旧 helper 或 `_LEGACY_PLUGIN_SOURCE_SCAN_HELPERS`。
  - 断言测试侧不再从 `app.plugin_source_text.scanner` 导入这两个私有 helper。
  - 断言测试侧不再直接调用 `build_plugin_source_scan(`，也不再 monkeypatch 旧 dotted path。
  - 断言两个 batch/cache 对照测试改用 `scan_plugin_source_runtime_files_text_strict`。
- 新增 `tests/test_scan_budget.py::test_batch60_legacy_private_helper_deletion_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本记录覆盖生产模块、测试文件、旧 helper 名称、公开 runtime strict scan 和 batch60 保护测试。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 同步更新 batch53、batch56、batch57、batch58、batch59 的当前残留保护：
  - 历史记录测试仍检查旧批次记录。
  - 当前工作区残留断言改为 direct legacy 调用清零、私有 helper 导入清零、dotted monkeypatch 清零。

## 实现说明

- 更新 `app/plugin_source_text/scanner.py`：
  - 删除 `_build_legacy_plugin_source_scan`。
  - 删除 `_scan_legacy_plugin_source_files_text_strict`。
  - 删除 `_LEGACY_PLUGIN_SOURCE_SCAN_HELPERS`。
  - 删除只服务旧 wrapper 的 `_build_risk` 和相关导入。
- 更新 `tests/test_plugin_source_text.py`：
  - `test_legacy_plugin_source_scan_helpers_are_private_in_scanner` 收束为 `test_legacy_plugin_source_scan_helpers_are_removed_from_scanner`。
  - `test_plugin_source_scan_batches_native_ast_parse_for_source_files` 改用 `scan_plugin_source_runtime_files_text_strict` 验证批量 AST 入口。
  - `test_plugin_source_scan_reuses_native_ast_by_file_hash` 改用 `scan_plugin_source_runtime_files_text_strict` 验证文件 hash 缓存复用。
  - 删除多个测试中对已删除 helper 的 monkeypatch。
- 更新 `tests/agent_toolkit_contract_fixtures.py`：
  - 删除 `real_scan_plugin_source_files_text_strict` 旧 helper 导入和 `__all__` 导出。
- 更新 `tests/test_agent_toolkit_workspace.py` 和 `tests/test_agent_toolkit_rule_import.py`：
  - 删除对已删除 helper 的禁止回退 monkeypatch。
- 更新 `tests/test_scan_budget.py`：
  - 新增 batch60 保护。
  - 更新旧 residual 保护到当前清零事实。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6AC 批次进度行。

## 旧路径收束

- 已删除生产私有 helper：
  - `_build_legacy_plugin_source_scan`
  - `_scan_legacy_plugin_source_files_text_strict`
- 已清理测试侧入口：
  - `tests/test_plugin_source_text.py` 不再导入 `_build_legacy_plugin_source_scan as build_plugin_source_scan`。
  - `tests/agent_toolkit_contract_fixtures.py` 不再导出 `real_scan_plugin_source_files_text_strict`。
  - 默认路径防回退测试不再 monkeypatch 已删除 helper。
- 保留行为：
  - 批量 AST 入口和文件 hash 缓存仍通过公开 `scan_plugin_source_runtime_files_text_strict` 覆盖。
  - `build_native_plugin_source_scan` 继续作为翻译源候选事实入口。

## 外部契约变化

- 公开包根 `app.plugin_source_text`、CLI 参数、Agent JSON 字段、SQLite schema、日志格式、目录结构、Rust API 和发布流程不变。
- 删除对象均为此前已私有化且未导出的内部 helper。
- 测试侧不再把旧私有 helper 当作兼容入口。

## 性能证据

- 本批删除旧 wrapper，没有新增生产扫描、I/O、SQLite 查询或 Rust 调用。
- 两个 batch/cache 对照测试继续覆盖公开 runtime strict scan 的批量 AST 入口和源码 hash cache。
- `tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed` 固定 direct legacy 调用和旧 private helper 引用清零。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed tests/test_scan_budget.py::test_batch60_legacy_private_helper_deletion_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：`app/plugin_source_text/scanner.py` 仍存在旧 helper；`docs/records/rust-scope-index/batches/batch-060.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_removed_from_scanner tests/test_plugin_source_text.py::test_plugin_source_scan_batches_native_ast_parse_for_source_files tests/test_plugin_source_text.py::test_plugin_source_scan_reuses_native_ast_by_file_hash tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_skips_inactive_heavy_branch_scans tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch57_shared_fixtures_do_not_export_legacy_plugin_source_scan tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_first_group_uses_native_scan tests/test_scan_budget.py::test_batch59_legacy_batch_cache_tests_are_only_remaining_legacy_scan_users tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed`
  - 结果：13 passed。
- 目标 GREEN 与记录保护：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_removed_from_scanner tests/test_plugin_source_text.py::test_plugin_source_scan_batches_native_ast_parse_for_source_files tests/test_plugin_source_text.py::test_plugin_source_scan_reuses_native_ast_by_file_hash tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_skips_inactive_heavy_branch_scans tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch57_shared_fixtures_do_not_export_legacy_plugin_source_scan tests/test_scan_budget.py::test_batch58_legacy_semantic_fixture_first_group_uses_native_scan tests/test_scan_budget.py::test_batch59_legacy_batch_cache_tests_are_only_remaining_legacy_scan_users tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed tests/test_scan_budget.py::test_batch60_legacy_private_helper_deletion_record_exists_and_tracks_contract`
  - 结果：14 passed。
- 全量测试：`uv run pytest`
  - 结果：836 passed in 300.97s。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors, 0 warnings, 0 notes。
- 文档敏感路径和占位文案搜索：
  - 结果：无匹配。
- 空白检查：`git diff --check`
  - 结果：退出码 0；仅提示工作区现有 LF/CRLF 转换警告。
- 旧入口静态搜索：`rg -n "app\\.plugin_source_text\\.scanner\\._build_legacy_plugin_source_scan|app\\.plugin_source_text\\.scanner\\._scan_legacy_plugin_source_files_text_strict|from app\\.plugin_source_text\\.scanner import _|build_plugin_source_scan\\(" app tests -g "*.py" -g "!tests/test_scan_budget.py"`
  - 结果：无匹配。
- 生产代码旧名称搜索：`rg -n "_build_legacy_plugin_source_scan|_scan_legacy_plugin_source_files_text_strict|build_plugin_source_scan\\(" app -g "*.py"`
  - 结果：无匹配。
- 记录补写后复验：`uv run pytest tests/test_scan_budget.py::test_batch60_legacy_private_helper_deletion_record_exists_and_tracks_contract`
  - 结果：1 passed。

## 审查处理

- 本批使用只读子代理做旁路审计，确认生产路径不再真实依赖两个旧 helper，剩余引用集中在测试保护、fixture 和历史记录。
- 本地实现按子代理建议收束：保留生产删除，清理测试导入和 monkeypatch，同步 scan_budget 保护。
- 本批触及生产 Python 代码，因此按临时验证策略执行全量 `uv run pytest`。

## 剩余风险

- 历史批次记录仍包含旧 helper 名称，用于说明旧路径如何被逐步收束；下一批可做历史记录残留收尾审计，确认这些出现只存在于历史记录和保护测试文本中。
- 当前工作树混有前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：旧 scanner 历史记录残留收尾审计。
- 建议边界：确认 `_build_legacy_plugin_source_scan`、`_scan_legacy_plugin_source_files_text_strict` 和 `build_plugin_source_scan` 的剩余出现只属于历史批次记录、scan_budget 记录保护或用户可理解的迁移说明，不再出现在生产代码、共享 fixture、默认路径测试和公开契约中。
- 理由：生产私有 helper 已删除，剩余工作应转为历史记录与文档边界审计，避免旧名称再次变成可执行入口。
