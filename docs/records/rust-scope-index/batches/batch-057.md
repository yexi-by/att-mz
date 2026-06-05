# Rust Scope/Index Engine 批次 57 记录

## 本批范围

- 批次：6Z，共享 fixture legacy 导出收束。
- 覆盖范围：`tests/agent_toolkit_contract_fixtures.py`、`tests/rmmz_writeback_contract_fixtures.py`、`tests/test_scan_budget.py`、`docs/plans/completed/rust-scope-index-engine.md` 和本记录。
- 成功状态：两个共享 fixture 继续导出 `build_native_plugin_source_scan`，但不再通过星号导入暴露 `build_plugin_source_scan`；`_build_legacy_plugin_source_scan as build_plugin_source_scan` 仅剩 `tests/test_plugin_source_text.py` 直接导入，用于旧 scanner 语义测试。
- 明确非范围：本批不删除 `app/plugin_source_text/scanner.py` 内 `_build_legacy_plugin_source_scan` 或 `_scan_legacy_plugin_source_files_text_strict`，不迁移 `tests/test_plugin_source_text.py` 内剩余旧语义测试，不改生产代码、CLI、数据库 schema、Rust 原生代码或发布流程。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch57_shared_fixtures_do_not_export_legacy_plugin_source_scan`：
  - 断言 `tests/agent_toolkit_contract_fixtures.py` 和 `tests/rmmz_writeback_contract_fixtures.py` 继续导出 `build_native_plugin_source_scan`。
  - 断言这两个共享 fixture 的 `__all__` 不再包含 `build_plugin_source_scan`。
  - 断言 `_build_legacy_plugin_source_scan as build_plugin_source_scan` 只剩 `tests/test_plugin_source_text.py` 导入。
  - 断言除 `tests/test_scan_budget.py` 自身保护文本外，测试代码中直接调用 `build_plugin_source_scan(` 的路径仍仅为 `tests/test_plugin_source_text.py`。
- 新增 `tests/test_scan_budget.py::test_batch57_shared_fixture_legacy_export_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本记录覆盖共享 fixture、旧 scanner 私有入口、星号导入暴露面和 batch57 保护测试。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 同步调整旧保护：
  - batch54、batch55 的 fixture 导出断言从“同时导出 native 和 legacy”改为“导出 native，不导出 legacy”。
  - batch56 的 repo-wide 残留分类断言收窄为 `_build_legacy_plugin_source_scan as build_plugin_source_scan` 只剩 `tests/test_plugin_source_text.py`。

## 实现说明

- 更新 `tests/agent_toolkit_contract_fixtures.py`：
  - 删除 `_build_legacy_plugin_source_scan as build_plugin_source_scan` 导入。
  - 从 `__all__` 删除 `build_plugin_source_scan`。
  - 保留 `real_scan_plugin_source_files_text_strict`，供旧 strict scan 对照和 runtime 禁止钩子使用。
- 更新 `tests/rmmz_writeback_contract_fixtures.py`：
  - 删除 `_build_legacy_plugin_source_scan as build_plugin_source_scan` 导入。
  - 从 `__all__` 删除 `build_plugin_source_scan`。
- 更新 `tests/test_scan_budget.py`：
  - 新增 `__all__` 解析辅助函数。
  - 新增 batch57 共享 fixture legacy 导出收束保护和记录保护。
  - 同步 batch54、batch55、batch56 的当前状态保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6Z 批次进度行。

## 旧路径收束

- 已收束路径：
  - `tests/agent_toolkit_contract_fixtures.py` 不再导入或导出 `build_plugin_source_scan`。
  - `tests/rmmz_writeback_contract_fixtures.py` 不再导入或导出 `build_plugin_source_scan`。
  - 通过这些共享 fixture 星号导入的 AgentToolkit 和 RMMZ 测试文件不再能隐式获得旧 scanner 别名。
- 保留路径：
  - `tests/test_plugin_source_text.py` 仍显式导入 `_build_legacy_plugin_source_scan as build_plugin_source_scan`，用于 8 个旧 scanner 语义测试。
  - `tests/agent_toolkit_contract_fixtures.py` 仍导出 `real_scan_plugin_source_files_text_strict`，用于旧 strict scan 对照和 runtime 保护。
  - `app/plugin_source_text/scanner.py` 内两个 legacy 私有 helper 仍保留。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构、Rust API 和发布流程不变。
- 本批只改变测试共享 fixture 的导出面，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O、SQLite 查询或 Rust 调用。
- 两个共享 fixture 不再向星号导入消费者暴露 `build_plugin_source_scan`，减少后续测试夹具误用旧 scanner 的入口。
- 除 `tests/test_scan_budget.py` 自身保护文本外，测试代码中直接调用 `build_plugin_source_scan(` 的路径仍仅剩 `tests/test_plugin_source_text.py`。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch57_shared_fixtures_do_not_export_legacy_plugin_source_scan tests/test_scan_budget.py::test_batch57_shared_fixture_legacy_export_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：两个共享 fixture 仍导出 `build_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-057.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch54_feedback_runtime_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch57_shared_fixtures_do_not_export_legacy_plugin_source_scan tests/test_scan_budget.py::test_batch57_shared_fixture_legacy_export_record_exists_and_tracks_contract`
  - 结果：5 passed。
- 代表性行为测试：`uv run pytest tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_rmmz_write_plan.py::test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit`
  - 结果：3 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors, 0 warnings, 0 notes。
- 文档敏感路径和占位文案搜索：
  - 结果：无匹配。
- 空白检查：`git diff --check`
  - 结果：退出码 0；仅提示工作区现有 LF/CRLF 转换警告。
- 全量测试：
  - 本批按 rust-scope-index-engine 临时验证策略未跑全量 `uv run pytest`。
  - 原因：本批是普通编号批次，未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程；本批不属于每 5 个编号批次收束点。

## 审查处理

- 本批审查重点是确认共享 fixture 只收束 legacy 导出，不切断 native helper、旧 strict scan 对照 helper或星号导入使用方。
- 目标保护测试确认两个共享 fixture 仍导出 `build_native_plugin_source_scan`，且不再导出 `build_plugin_source_scan`。
- 代表性行为测试覆盖了 AgentToolkit feedback、AgentToolkit workspace 和 RMMZ write-plan 三类星号导入消费者。
- 本批未新增生产运行路径，也未改变 CLI、数据库 schema、Rust 原生代码或发布流程。

## 剩余风险

- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在于 `app/plugin_source_text/scanner.py`。
- `tests/test_plugin_source_text.py` 仍有 8 个旧 scanner 语义测试直接调用 `build_plugin_source_scan(`。
- 当前工作树混有前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：旧 scanner 语义测试收束评估。
- 建议边界：按 batch53 固定的 8 个 `tests/test_plugin_source_text.py` 旧语义测试分组判断哪些还能替换为 `build_native_plugin_source_scan`，哪些必须继续作为 legacy 对照保留。
- 理由：共享 fixture 已不再暴露旧 scanner，剩余直接调用集中在单一测试文件，可以开始逐组处理真正的旧语义对照。
