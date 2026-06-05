# Rust Scope/Index Engine 批次 6BA 验收记录

## 本批范围

本批是结构化占位符扫描命令 native 薄适配接入。范围只覆盖 `scan-structured-placeholder-candidates` 对应的只读候选覆盖报告，让它复用 `build_native_structured_placeholder_candidates_payload` 与 `scan_rule_candidates(structured_placeholders)`。

本批触及以下文件：

- `app/native_structured_placeholder_scan.py`
- `app/agent_toolkit/services/common.py`
- `app/agent_toolkit/services/placeholder_rules.py`
- `tests/test_agent_toolkit_coverage.py`
- `tests/test_scan_budget.py`

本批不迁移 `validate-structured-placeholder-rules`、`import-structured-placeholder-rules`、`app/application/flow_gate.py::build_structured_placeholder_coverage_result`、workflow gate 或 workspace 的结构化占位符覆盖结果。

## 保护网

新增 `tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan`：

- monkeypatch `app.agent_toolkit.services.common._iter_structured_shell_candidate_matches` 为报错函数。
- 调用公开服务方法 `scan_structured_placeholder_candidates`。
- 断言报告仍返回 `ok`，`rule_count`、`candidate_count`、`covered_count` 和 `uncovered_count` 保持旧报告语义。
- 断言报告明细包含结构化 shell 候选，但不泄露候选外的完整正文尾部。

新增 `tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists`：

- 固定计划表链接本批记录。
- 固定新增 `app/native_structured_placeholder_scan.py`。
- 固定 helper 调用 `build_native_structured_placeholder_candidates_payload` 和 `scan_native_rule_candidates`。
- 固定 `_build_structured_placeholder_coverage_report_with_context` 消费 native helper，不再直接调用 `_collect_structured_placeholder_candidate_details` 或 `_iter_structured_shell_candidate_matches`。
- 固定 `import_structured_placeholder_rules` 仍使用 `build_structured_placeholder_coverage_result`，避免本批扩大到导入和 workflow gate 覆盖结果。

新增 `tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_record_exists_and_tracks_contract
```

结果：3 failed。失败点分别是扫描命令仍调用 Python 结构化候选扫描器、计划表缺少 `docs/records/rust-scope-index/batches/batch-084.md`，以及本批记录不存在。

## 实现说明

新增 `app/native_structured_placeholder_scan.py`：

- `collect_native_structured_placeholder_candidate_details` 调用 `build_native_structured_placeholder_candidates_payload` 与 `scan_native_rule_candidates`。
- 从 `scan_summary["structured_placeholders"]["candidates"]` 读取 native 候选明细。
- 将 native 明细收窄为旧报告同形字段：`location_path`、`line_number`、`candidate`、`covered` 和 `matching_rules`。
- `count_uncovered_structured_placeholder_candidate_details` 只统计 `covered=false` 的候选。

`app/agent_toolkit/services/common.py::_build_structured_placeholder_coverage_report_with_context` 改为使用该 native helper 构建 `RuleCoverageResult`。报告仍通过 `structured_placeholder_rule_scope_hash(candidate_details)` 对完整候选明细计算 hash，不使用抽样候选。

`app/agent_toolkit/services/placeholder_rules.py::scan_structured_placeholder_candidates` 继续负责加载设置、规则和当前正文上下文，并把已构造的 `TextRules` 传给 common 报告构建函数。Python 仍只做 I/O 编排、native JSON 明细收窄和报告组装。

## 旧路径收束

本批迁移的是 `scan-structured-placeholder-candidates` 的只读候选报告路径。旧 Python 结构化候选扫描函数仍保留：

- `app/agent_toolkit/services/common.py::_collect_structured_placeholder_candidate_details`
- `app/agent_toolkit/services/common.py::_iter_structured_shell_candidate_matches`
- `app/application/flow_gate.py::collect_structured_placeholder_candidate_details`

这些路径仍服务于后续尚未迁移的覆盖结果、导入确认 hash、workflow gate 和 workspace 校验。下一批迁移结构化占位符覆盖报告时，需要单独建立 RED/GREEN，不能把本批结论外推。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema 或 Rust 原生代码变化。

`scan-structured-placeholder-candidates` 的可观察报告字段保持：

- `summary.game`
- `summary.report_detail_mode`
- `summary.rule_count`
- `summary.candidate_count`
- `summary.covered_count`
- `summary.uncovered_count`
- `details.detail_mode`
- `details.candidates.count`
- `details.candidates.items[].location_path`
- `details.candidates.items[].line_number`
- `details.candidates.items[].candidate`
- `details.candidates.items[].covered`
- `details.candidates.items[].matching_rules`

## 性能证据

本批将 `scan-structured-placeholder-candidates` 的结构化 shell 候选扫描和规则覆盖判断切到 Rust `scan_rule_candidates(structured_placeholders)`。Python 不再在该扫描命令的报告构建路径里执行 `_iter_structured_shell_candidate_matches`。

由于本批尚未迁移 `build_structured_placeholder_coverage_result`，导入确认 hash、workflow gate 和 workspace 校验仍会通过旧 Python 覆盖结果扫描。该剩余风险已写入本批记录，下一批应继续收束覆盖结果事实来源。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_record_exists_and_tracks_contract`，3 failed。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_record_exists_and_tracks_contract`，3 passed。
- 相关结构化回归：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_import_empty_structured_placeholder_rules_uses_full_candidate_hash tests/test_agent_toolkit_rule_import.py::test_import_nonempty_structured_placeholder_rules_confirms_remaining_uncovered_candidates tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_candidate_review_rejects_legacy_sampled_hash tests/test_cli_json_output.py::test_structured_placeholder_rule_commands_accept_input_files tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_record_exists_and_tracks_contract`，7 passed。
- 历史审计保护修正：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_record_exists_and_tracks_contract`，3 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`，902 passed。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批修改生产 Python 代码，因此已按临时策略执行全量 `uv run pytest`。
- 本批未修改 Rust 原生代码。

## 审查处理

本批使用只读子代理复核普通占位符 batch 73/74 的 native 薄适配模式、结构化 scan 当前报告 schema、hash 边界，以及本批不应触碰的 validate/import/workspace/flow_gate 路径。子代理未修改文件，结论确认 batch 84 应复刻“native 明细 helper + 旧报告同形输出”模式，只迁 `scan-structured-placeholder-candidates`。

本地实现采纳该边界：新增结构化 native helper，common 报告消费 native 明细，validate/import/workspace/flow_gate 均不在本批迁移。

## 剩余风险

`validate-structured-placeholder-rules`、`import-structured-placeholder-rules`、`build_structured_placeholder_coverage_result`、workflow gate 和 workspace 校验仍保留旧 Python 结构化候选扫描事实来源。

本批只证明扫描命令报告路径不再调用旧 Python 结构化候选扫描器。导入确认 hash、doctor、workflow gate 和工作区 manifest 仍需后续批次单独迁移与验证。

## 下一批入口

建议下一批进入结构化占位符覆盖报告 native 化：把 `app/application/flow_gate.py::build_structured_placeholder_coverage_result` 与 `structured_placeholder_scope_hash` 依赖的候选明细切到 `collect_native_structured_placeholder_candidate_details`，同时保护完整候选 hash、导入确认和 workflow gate 行为不漂移。
