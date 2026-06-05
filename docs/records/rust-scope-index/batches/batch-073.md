# Rust Scope/Index Engine 批次 73 验收记录

## 本批范围

本批是 6AP：普通占位符扫描命令薄适配接入。范围只覆盖 `scan-placeholder-candidates` 的只读候选覆盖报告，让它复用 `build_native_placeholder_candidates_payload` 与 `scan_rule_candidates(placeholders)`。

本批不接入 `validate-placeholder-rules`、`import-placeholder-rules`、`build-placeholder-rules`、workflow gate 或 workspace 的普通占位符覆盖结果，不修改数据库 schema、CLI 参数、配置字段或 Rust 原生代码。

## 保护网

新增 `tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan`：

- monkeypatch `app.agent_toolkit.services.common.scan_placeholder_candidates` 为报错函数。
- 调用公开服务方法 `scan-placeholder-candidates` 对应的 `service.scan_placeholder_candidates`。
- 断言报告仍能返回 `ok`，候选数量不为空，`uncovered_count` 为 0，且报告明细仍包含自定义控制符 marker，但不泄露完整正文样本文本。

新增 `tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists` 和 `tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_record_exists_and_tracks_contract`：

- 固定 `_build_placeholder_coverage_report_with_context` 不再调用旧 Python scanner。
- 固定 common 层 helper 调用 `build_native_placeholder_candidates_payload` 和 `scan_native_rule_candidates`。
- 固定 `build_placeholder_rules`、workflow gate 等后续路径仍保留旧 Python scanner，避免本批扩大范围。

## 实现说明

`app/agent_toolkit/services/common.py::_build_placeholder_coverage_report_with_context` 改为调用共享 native helper `collect_native_placeholder_candidate_details`：

- 使用 `build_native_placeholder_candidates_payload` 组装 native 输入。
- 使用 `scan_native_rule_candidates` 执行普通占位符候选扫描。
- 从 `scan_summary["placeholders"]["candidates"]` 读取旧报告同形明细。
- 使用 `_normalize_native_placeholder_candidate_detail` 收窄 `marker`、`count`、`sources`、`standard_covered`、`custom_covered`、`covered` 字段类型。
- 使用 `count_uncovered_placeholder_candidate_details` 统计未覆盖候选。

报告仍通过 `RuleCoverageResult` 渲染，`summary` 与 `details.candidates.items` 的外部形状保持不变。

## 旧路径收束

本批迁移的是 `scan-placeholder-candidates` 的只读候选报告路径。旧 `app/agent_toolkit/placeholder_scan.py::scan_placeholder_candidates` 仍保留：

- `build-placeholder-rules` 继续用旧 scanner 生成草稿和手动边界提示。
- `app/application/flow_gate.py::build_normal_placeholder_coverage_result` 继续用旧 scanner 生成 workflow gate 覆盖结果。
- `validate-placeholder-rules` 与 `import-placeholder-rules` 仍通过现有覆盖结果和规则校验链路运行。

下一批再迁移普通占位符覆盖报告或 workflow gate 时，需要单独建立 RED/GREEN，不能把本批结论外推。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段或数据库 schema 变化。

`scan-placeholder-candidates` 的可观察报告字段保持：

- `summary.rule_count`
- `summary.candidate_count`
- `summary.covered_count`
- `summary.uncovered_count`
- `details.candidates.items[].marker`
- `details.candidates.items[].count`
- `details.candidates.items[].sources`
- `details.candidates.items[].standard_covered`
- `details.candidates.items[].custom_covered`
- `details.candidates.items[].covered`

## 性能证据

本批将 `scan-placeholder-candidates` 的候选扫描重活从 Python scanner 切到 Rust `scan_rule_candidates(placeholders)`。Python 只负责已加载正文上下文的载荷组装、native JSON 明细收窄、报告组装和 warning 渲染。

warm text index 复用仍由既有 `test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build` 保护；本批新增测试进一步证明只读扫描命令不再调用旧 Python 普通占位符扫描器。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_record_exists_and_tracks_contract`，3 failed；失败点分别是扫描命令仍调用旧 Python scanner、计划缺少 `docs/records/rust-scope-index/batches/batch-073.md`、本批记录不存在。
- GREEN 目标：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_record_exists_and_tracks_contract`，3 passed。
- 相关回归：`uv run pytest tests/test_agent_toolkit_coverage.py::test_read_only_placeholder_scan_does_not_run_write_probe tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_marks_custom_rule_coverage tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_record_exists_and_tracks_contract`，8 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- Python 全量测试：`uv run pytest`，873 passed。
- 文档敏感路径/占位文案搜索：使用 `rg -n` 检查当前开发记录、superpowers 计划、README 和 skills 中的本机路径、用户名和未回填验收占位文案，无命中。
- 空白差异检查：`git diff --check`，通过；仅输出仓库既有 LF/CRLF 换行提示。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未使用子代理执行改动。范围较窄且只触及 common 层报告适配，主代理本地完成 TDD、实现和验证。

## 剩余风险

普通占位符还有多条旧路径没有迁移：

- 覆盖报告内部统一模型仍有旧 scanner 消费点。
- workflow gate 仍用 `build_normal_placeholder_coverage_result`。
- `build-placeholder-rules` 仍用旧 scanner 生成草稿和手动边界提示。
- `validate-placeholder-rules` 与 `import-placeholder-rules` 的规则保存事务和 empty-rule 确认哈希仍需后续单独验证。

## 下一批入口

建议下一批进入普通占位符覆盖报告 native 化：把 `app/application/flow_gate.py::build_normal_placeholder_coverage_result` 或共享 coverage builder 迁到 native 明细，并保护 workflow gate、规则确认 scope hash 与现有报告字段不漂移。
