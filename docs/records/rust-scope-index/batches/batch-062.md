# Rust Scope/Index Engine 批次 6AE 验收记录

## 本批范围

本批是插件源码支线收束回归审计，只新增保护测试和验收记录，不修改生产代码。

范围覆盖四类入口：

- `app/plugin_source_text/__init__.py` 的 package root 导出边界。
- `app/plugin_source_text/native_scan.py` 的 `build_native_plugin_source_scan`、`build_native_plugin_source_ast_map_payload`、`build_native_plugin_source_risk_report` 和 `native_plugin_source_risk_report_from_scan`。
- `app/plugin_source_text/runtime_audit.py` 的当前运行文件扫描入口。
- `app/text_scope/write_probe.py` 的写回探针插件源码 AST 检查入口。

## 保护网

新增 `tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_protections_cover_native_and_runtime_entries`，固定以下事实：

- package root 继续导出 `build_native_plugin_source_scan` 与 `scan_plugin_source_runtime_files_text_strict`。
- `native_scan.py` 的风险报告、AST 地图和扫描对象三条生产入口继续调用 `scan_native_rule_candidates`。
- `runtime_audit.py` 和 `write_probe.py` 继续使用 `scan_plugin_source_runtime_files_text_strict`。
- 关键回归测试继续覆盖 `test_scan_plugin_source_text_uses_native_candidate_scan`、`test_export_plugin_source_ast_map_uses_native_candidate_scan`、`test_validate_plugin_source_rules_uses_native_plugin_source_scan`、`test_import_plugin_source_rules_uses_native_plugin_source_scan`、`test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`、`test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`、`test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files` 和 `test_plugin_source_write_probe_uses_batch_preview`。

目标回归测试分布在 `tests/test_plugin_source_text.py`、`tests/test_agent_toolkit_workspace.py` 和 `tests/test_agent_toolkit_rule_import.py`。

新增 `tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_record_exists_and_tracks_contract`，固定本记录和计划表链接。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_protections_cover_native_and_runtime_entries tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_record_exists_and_tracks_contract
```

结果：入口保护通过，记录保护因 `docs/records/rust-scope-index/batches/batch-062.md` 尚未存在失败。

## 实现说明

本批没有改变 `app/` 生产实现。新增保护测试使用 AST 读取已有生产函数和目标回归测试，避免用自然语言文档作为唯一依据。

保护测试把 native 候选支线和 runtime 字面量支线分开固定：

- 翻译源候选、风险报告和 AST 地图仍以 `scan_native_rule_candidates` 为事实来源。
- 当前运行文件审计和写回探针 fallback 仍以 `scan_plugin_source_runtime_files_text_strict` 为事实来源。

## 旧路径收束

本批没有新增旧路径，也没有恢复旧 scanner 可执行入口。旧 scanner 历史名称仍只允许停留在历史记录和保护测试中。

## 外部契约变化

无外部 CLI、JSON schema、数据库 schema、日志格式或用户文案变化。

## 性能证据

本批只新增静态保护和记录，不引入新的扫描流程。性能相关证据来自保护测试锁定的入口：

- `build_native_plugin_source_scan`
- `build_native_plugin_source_ast_map_payload`
- `build_native_plugin_source_risk_report`
- `scan_native_rule_candidates`
- `scan_plugin_source_runtime_files_text_strict`

## 验证结果

本节记录本批收束时执行的目标验证命令。普通编号批次按临时例外不强制执行全量 `uv run pytest`；本批未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程。

本批按临时例外未跑全量 pytest。

已执行：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_protections_cover_native_and_runtime_entries tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_record_exists_and_tracks_contract
```

结果：2 passed。

```powershell
uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_uses_native_candidate_scan tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files
```

结果：8 passed。

```powershell
uv run pytest tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed tests/test_scan_budget.py::test_batch60_legacy_private_helper_deletion_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch61_legacy_scanner_names_are_confined_to_history_and_protections tests/test_scan_budget.py::test_batch61_legacy_history_residual_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_protections_cover_native_and_runtime_entries tests/test_scan_budget.py::test_batch62_plugin_source_branch_regression_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch41_translation_source_plugin_source_native_fallback_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch42_active_runtime_scan_cache_native_runtime_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract
```

结果：9 passed。

```powershell
uv run basedpyright
```

结果：0 errors, 0 warnings, 0 notes。

文档敏感路径和占位文案搜索：无命中。

旧入口边界搜索：无命中。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理辅助审计入口分布；最终实现以本地读取和测试结果为准。无代码审查意见需要处理。

## 剩余风险

本批是静态收束回归网，不能替代全量行为回归。剩余风险是未来若新增插件源码支线入口，仍需要在对应行为测试里补充动态验证，并在下一批或阶段收束时扩展本保护。

## 下一批入口

建议下一批进入 P1-B 插件源码阶段收束回顾：汇总 6B 到 6AE 的支线迁移事实、剩余风险和是否可以进入下一个 P1-B 热路径审计。
