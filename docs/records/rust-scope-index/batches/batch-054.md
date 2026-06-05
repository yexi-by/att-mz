# Rust Scope/Index Engine 批次 54 记录

## 本批范围

- 批次：6W，feedback runtime 夹具第八组 Rust-derived 替换。
- 覆盖范围：`tests/test_agent_toolkit_feedback.py` 内 6 个 active runtime diagnosis/audit 测试夹具；这些测试只用前置插件源码扫描构造 runtime map、translation item 或排除规则输入。
- 成功状态：这 6 个测试改用 `build_native_plugin_source_scan` 准备 `PluginSourceScan` 事实；`tests/test_agent_toolkit_feedback.py` 不再直接调用 `build_plugin_source_scan`。
- 明确非范围：本批不处理 `tests/test_plugin_source_text.py` 内剩余旧 scanner 语义对照，不迁移 workspace/write-plan/rule-import 残留夹具，不删除 `_build_legacy_plugin_source_scan`，不改生产代码、CLI、数据库 schema、Rust 原生代码或外部契约。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch54_feedback_runtime_fixtures_seed_with_native_scan`：
  - 读取 `tests/test_agent_toolkit_feedback.py` 中 6 段目标测试函数源码。
  - 用 Python AST 收集真实调用节点。
  - 断言这些测试函数调用 `build_native_plugin_source_scan`。
  - 断言这些测试函数不再调用 `build_plugin_source_scan`。
  - 断言 `tests/agent_toolkit_contract_fixtures.py` 暴露 `build_native_plugin_source_scan`，让 `import *` 测试文件能使用 native helper。
- 新增 `tests/test_scan_budget.py::test_batch54_feedback_runtime_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批涉及文件、native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache`
  - `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans`
  - `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_default_mode_never_guesses_without_runtime_map`
  - `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_does_not_ignore_excluded_runtime_residual_without_map`
  - `tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_ignores_excluded_residual_with_exact_runtime_map`
  - `tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_reports_unmapped_residual_when_other_runtime_map_exists`

## 实现说明

- 更新 `tests/agent_toolkit_contract_fixtures.py`：
  - 从 `app.plugin_source_text` 导入 `build_native_plugin_source_scan`。
  - 将 `build_native_plugin_source_scan` 加入 `__all__`，供 `tests/test_agent_toolkit_feedback.py` 的星号导入使用。
- 更新 `tests/test_agent_toolkit_feedback.py`：
  - 将 6 处 `source_scan = build_plugin_source_scan(...)` 改为 `source_scan = build_native_plugin_source_scan(...)`。
  - 6W 本轮只替换这些测试内的 scanner helper；这些测试在 6W 开始前已经存在的 monkeypatch 和 active runtime 断言不纳入本批变更范围。
  - 继续验证 active runtime diagnosis/audit 的 runtime map、translation cache、排除 selector 和未映射残留行为。
- 更新 `tests/test_scan_budget.py`：
  - 新增 6W feedback runtime 夹具静态保护和批次记录保护。
  - 静态保护解析 `tests/agent_toolkit_contract_fixtures.py` 的 `__all__`，确认 native helper 已导出，同时保留 legacy helper 供其他旧测试使用。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6W 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache`
  - `test_diagnose_active_runtime_batches_translation_source_scans`
  - `test_diagnose_active_runtime_default_mode_never_guesses_without_runtime_map`
  - `test_diagnose_active_runtime_does_not_ignore_excluded_runtime_residual_without_map`
  - `test_active_runtime_audit_ignores_excluded_residual_with_exact_runtime_map`
  - `test_active_runtime_audit_reports_unmapped_residual_when_other_runtime_map_exists`
  - 以上 6 段测试不再用旧 scanner 别名准备 runtime map、translation item 或排除规则输入。
- 保留路径：
  - `tests/test_plugin_source_text.py` 内旧 scanner 语义对照仍按 batch53 清单保留。
  - `tests/test_agent_toolkit_workspace.py`、`tests/test_rmmz_write_plan.py`、`tests/test_rule_import_transactions.py` 和共享 fixture 内仍有旧 scanner 残留，留到后续批次逐项迁移或分类。
  - `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍保留为私有兼容入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构和 Rust API 不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- `tests/test_agent_toolkit_feedback.py` 中 `build_plugin_source_scan(` 直接调用从 6 处降到 0 处，`build_native_plugin_source_scan(` 调用从 0 处增加到 6 处。
- 目标行为测试在 native selector 和 file_hash 下仍通过，说明这些 feedback runtime 场景不依赖旧 scanner 生成 runtime map 输入的特殊行为。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch54_feedback_runtime_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch54_feedback_runtime_fixture_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：公共测试夹具尚未暴露 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-054.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_default_mode_never_guesses_without_runtime_map tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_does_not_ignore_excluded_runtime_residual_without_map tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_ignores_excluded_residual_with_exact_runtime_map tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_reports_unmapped_residual_when_other_runtime_map_exists tests/test_scan_budget.py::test_batch54_feedback_runtime_fixtures_seed_with_native_scan`
  - 结果：7 passed。
- 组合 GREEN：`uv run pytest tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_default_mode_never_guesses_without_runtime_map tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_does_not_ignore_excluded_runtime_residual_without_map tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_ignores_excluded_residual_with_exact_runtime_map tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_reports_unmapped_residual_when_other_runtime_map_exists tests/test_scan_budget.py::test_batch54_feedback_runtime_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch54_feedback_runtime_fixture_record_exists_and_tracks_contract`
  - 结果：8 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- feedback 夹具调用统计：`rg -n "build_plugin_source_scan\\(" tests/test_agent_toolkit_feedback.py` 与 `rg -n "build_native_plugin_source_scan\\(" tests/test_agent_toolkit_feedback.py`
  - 结果：0 处 legacy 调用、6 处 native 调用。
- 全量 Python 测试：
  - 本批按 rust-scope-index-engine 临时验证策略未执行 `uv run pytest` 全量测试。

## 审查处理

- 只读子代理审查未发现 Critical 问题。
- 只读子代理审查确认 6 个目标测试均各调用 1 次 `build_native_plugin_source_scan`，0 次 `build_plugin_source_scan`；`tests/test_agent_toolkit_feedback.py` 全文件没有遗漏的直接 legacy 调用。
- 只读子代理审查指出 `test_diagnose_active_runtime_batches_translation_source_scans` 相对 `HEAD` 还有 monkeypatch 和 active runtime hash 断言变化，若按当前工作区对 `HEAD` 的总 diff 审查，会与“只替换 scanner helper”的表述冲突；本记录已明确 6W 的基线是 6V 后当前工作区，本轮只替换 scanner helper，前序批次留下的同文件变更不纳入 6W 范围。
- 只读子代理审查指出 batch54 静态保护只做文本包含检查，不精确校验 `__all__`；已改为解析 `tests/agent_toolkit_contract_fixtures.py` 的 `__all__`，同时断言 native helper 已导出、legacy helper 仍保留。
- 只读子代理审查确认 batch54 文档和计划行存在，未发现本机私有路径、用户名或未完成占位文案，记录已说明本批未跑全量 `uv run pytest`。

## 剩余风险

- 其他测试文件仍有 `build_plugin_source_scan` 私有 helper 残留，本批没有处理。
- 本批按 rust-scope-index-engine 临时验证策略未执行 `uv run pytest` 全量测试；风险集中在未运行的无关模块测试。

## 下一批入口

- 建议下一批：workspace/write-plan/rule-import 残留夹具替换评估。
- 建议边界：优先审计 `tests/test_agent_toolkit_workspace.py`、`tests/test_rmmz_write_plan.py` 和 `tests/test_rule_import_transactions.py` 中的直接 legacy 调用，判断哪些只是规则输入夹具，哪些属于旧 scanner 对照。
- 理由：feedback runtime 夹具已迁移完毕，下一批应继续减少共享测试 fixture 对 `_build_legacy_plugin_source_scan` 的依赖。
