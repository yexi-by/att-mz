# Rust Scope/Index Engine 批次 55 记录

## 本批范围

- 批次：6X，workspace/write-plan/rule-import 夹具第九组 Rust-derived 替换。
- 覆盖范围：`tests/test_agent_toolkit_workspace.py`、`tests/test_rmmz_write_plan.py` 和 `tests/test_rule_import_transactions.py` 内 4 个只用前置插件源码扫描准备规则输入、写回计划输入或事务回滚输入的测试夹具。
- 成功状态：这 4 个测试改用 `build_native_plugin_source_scan`；上述三个测试文件与 `tests/test_agent_toolkit_feedback.py` 不再直接调用 `build_plugin_source_scan`。
- 明确非范围：本批不处理 `tests/test_plugin_source_text.py` 内剩余旧 scanner 语义对照，不删除 `_build_legacy_plugin_source_scan`，不改生产代码、CLI、数据库 schema、Rust 原生代码或外部契约。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_fixtures_seed_with_native_scan`：
  - 读取 3 个目标测试文件的目标测试函数源码。
  - 用 Python AST 收集真实调用节点。
  - 断言目标测试函数调用 `build_native_plugin_source_scan`。
  - 断言目标测试函数不再调用 `build_plugin_source_scan`。
  - 解析 `tests/agent_toolkit_contract_fixtures.py` 和 `tests/rmmz_writeback_contract_fixtures.py` 的 `__all__`，确认 native helper 已导出，同时 legacy helper 仍保留给旧测试使用。
- 新增 `tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批涉及文件、native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`
  - `tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
  - `tests/test_rmmz_write_plan.py::test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit`
  - `tests/test_rule_import_transactions.py::test_plugin_source_rule_import_rolls_back_when_tail_step_fails`

## 实现说明

- 更新 `tests/rmmz_writeback_contract_fixtures.py`：
  - 从 `app.plugin_source_text` 导入 `build_native_plugin_source_scan`。
  - 将 `build_native_plugin_source_scan` 加入 `__all__`，供 `tests/test_rmmz_write_plan.py` 的星号导入使用。
  - 保留 `build_plugin_source_scan` 导出，避免切断尚未迁移的旧测试。
- 更新 `tests/test_agent_toolkit_workspace.py`：
  - 将 2 处 `scan = build_plugin_source_scan(...)` 改为 `scan = build_native_plugin_source_scan(...)`。
  - 保持测试主体断言不变，继续验证 prepare/validate workspace 复用扫描结果、不回旧主扫描和写回探针不二次扫 AST。
- 更新 `tests/test_rmmz_write_plan.py`：
  - 将 excluded plugin source selector 的候选预扫描改为 `build_native_plugin_source_scan`。
- 更新 `tests/test_rule_import_transactions.py`：
  - 从 `app.plugin_source_text` 导入 `build_native_plugin_source_scan`。
  - 将事务回滚测试里的旧/新 selector 预扫描改为 `build_native_plugin_source_scan`。
- 更新 `tests/test_scan_budget.py`：
  - 新增 6X workspace/write-plan/rule-import 夹具静态保护和批次记录保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6X 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`
  - `test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
  - `test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit`
  - `test_plugin_source_rule_import_rolls_back_when_tail_step_fails`
  - 以上 4 段测试不再用旧 scanner 别名准备规则输入、写回计划输入或事务回滚输入。
- 保留路径：
  - `tests/test_plugin_source_text.py` 内旧 scanner 语义对照仍按 batch53 清单保留。
  - `tests/agent_toolkit_contract_fixtures.py` 和 `tests/rmmz_writeback_contract_fixtures.py` 仍导出 `build_plugin_source_scan`，因为仍有旧语义测试和共享 fixture 边界未完全收束。
  - `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍保留为私有兼容入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构和 Rust API 不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- `tests/test_agent_toolkit_workspace.py`、`tests/test_rmmz_write_plan.py`、`tests/test_rule_import_transactions.py` 和 `tests/test_agent_toolkit_feedback.py` 中 `build_plugin_source_scan(` 直接调用为 0。
- 本批 3 个目标测试文件中 `build_native_plugin_source_scan(` 调用为 4 处。
- 目标行为测试在 native selector 和 file_hash 下仍通过，说明这些 workspace/write-plan/rule-import 场景不依赖旧 scanner 生成规则输入的特殊行为。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：`tests/rmmz_writeback_contract_fixtures.py` 尚未导出 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-055.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_rmmz_write_plan.py::test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit tests/test_rule_import_transactions.py::test_plugin_source_rule_import_rolls_back_when_tail_step_fails tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_fixtures_seed_with_native_scan`
  - 结果：5 passed。
- 目标行为和记录 GREEN：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_rmmz_write_plan.py::test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit tests/test_rule_import_transactions.py::test_plugin_source_rule_import_rolls_back_when_tail_step_fails tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch55_workspace_write_plan_rule_import_record_exists_and_tracks_contract`
  - 结果：6 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors, 0 warnings, 0 notes。
- 全量测试：`uv run pytest`
  - 结果：826 passed in 247.54s。
  - 说明：本批为 batch55，按 rust-scope-index-engine 临时验证策略触发每 5 个编号批次一次的全量 pytest。
- 文档敏感路径和占位文案搜索：
  - 结果：无匹配。
- 空白检查：`git diff --check`
  - 结果：退出码 0；仅提示工作区现有 LF/CRLF 转换警告。
- 旧入口残留计数：
  - `tests/test_agent_toolkit_workspace.py`、`tests/test_rmmz_write_plan.py`、`tests/test_rule_import_transactions.py` 和 `tests/test_agent_toolkit_feedback.py` 中 `build_plugin_source_scan(` 直接调用为 0。
  - `tests/test_agent_toolkit_workspace.py`、`tests/test_rmmz_write_plan.py` 和 `tests/test_rule_import_transactions.py` 中 `build_native_plugin_source_scan(` 调用为 4。

## 审查处理

- 只读审查聚焦 4 个目标测试是否只迁移测试夹具事实来源、是否遗漏直接 legacy 调用、记录是否含占位文案。
- 只读审查未发现 4 个目标测试、共享 fixture 导出、batch55 保护测试和批次记录存在阻塞问题。
- 只读审查指出当前工作树混有前序未提交的生产、Rust、脚本和配置改动，不能仅用全局 `git status` 证明第 55 批的变更归因。本批记录按实际编辑范围限定为测试夹具和验收记录，不处理这些前序未提交改动。

## 剩余风险

- `tests/test_plugin_source_text.py` 内旧 scanner 语义对照仍直接依赖私有 helper。
- repo-wide 仍需继续审计 `_build_legacy_plugin_source_scan` 导入、monkeypatch 和共享 fixture 导出是否还能进一步收束。
- `test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit` 用 native scan 准备 selector，但后续规则记录构造仍依赖现有 helper 默认路径；这不违反本批“目标函数体不直接调用旧 scanner”的边界，下一批 repo-wide 审计时继续确认。
- 当前工作树存在前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：旧 scanner repo-wide 残留入口审计。
- 建议边界：用静态测试区分剩余 `_build_legacy_plugin_source_scan` 出现位置：生产私有定义、旧 scanner 语义测试、禁止回退 monkeypatch、共享 fixture 导出和历史文档引用。
- 理由：workspace/write-plan/rule-import 普通夹具已迁移，下一步应从 repo-wide 残留视角判断私有 legacy helper 何时可以删除或进一步隔离。
