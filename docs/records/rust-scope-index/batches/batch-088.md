# Rust Scope/Index Engine 批次 6BE 验收记录

## 本批范围

本批是结构化占位符支线收束回归审计，只新增保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

范围覆盖结构化占位符支线 6AY 到 6BD 的迁移结果：

- `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates` 和 `import-structured-placeholder-rules` 三个公开命令的 scan_budget 分类和事实来源。
- Rust `scan_rule_candidates(structured_placeholders)` 候选入口。
- `build_native_structured_placeholder_candidates_payload` 和 `app/native_structured_placeholder_scan.py` native helper。
- `app/agent_toolkit/services/common.py::_build_structured_placeholder_coverage_report_with_context`。
- `app/application/flow_gate.py::build_structured_placeholder_coverage_result`。
- workflow gate、`app/text_index.py::_placeholder_gate_metadata`、`validate-agent-workspace`、规则导入和结构化占位符扫描命令。
- 旧 Python helper `collect_structured_placeholder_candidate_details`、`_collect_structured_placeholder_candidate_details`、`_iter_structured_shell_candidate_matches` 和 `STRUCTURED_SHELL_CANDIDATE_PATTERNS` 的当前代码边界。

本批复核以下记录链：

- `docs/records/rust-scope-index/batches/batch-082.md`
- `docs/records/rust-scope-index/batches/batch-083.md`
- `docs/records/rust-scope-index/batches/batch-084.md`
- `docs/records/rust-scope-index/batches/batch-085.md`
- `docs/records/rust-scope-index/batches/batch-086.md`
- `docs/records/rust-scope-index/batches/batch-087.md`

## 保护网

新增 `tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_covers_native_entries`，固定以下事实：

- 计划表链接批次 82 到 88 的结构化占位符记录。
- 批次 82 到 87 的记录链覆盖入口审计、Rust 候选入口、扫描命令 native 薄适配、覆盖报告 native 化、workflow gate native 审计和旧 helper 删除。
- `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates` 和 `import-structured-placeholder-rules` 都属于 P1-B，每个命令只保留一次候选扫描预算，插件源码 AST 扫描预算为 0，权威来源是 Rust `scan_rule_candidates(structured_placeholders)`。
- `app/` 当前 Python 代码中没有旧候选 helper 标记。
- `collect_native_structured_placeholder_candidate_details` 继续通过 `build_native_structured_placeholder_candidates_payload` 消费 native scan payload。
- `_build_structured_placeholder_coverage_report_with_context` 和 `build_structured_placeholder_coverage_result` 都通过 `collect_native_structured_placeholder_candidate_details` 与 `count_uncovered_structured_placeholder_candidate_details` 统计覆盖结果。
- `_placeholder_gate_metadata`、`validate-agent-workspace`、`scan-structured-placeholder-candidates` 和 `import-structured-placeholder-rules` 继续通过统一 coverage builder 或 native coverage report 路径消费结构化候选事实。
- 结构化占位符行为测试继续覆盖 native payload、native scan、扫描命令、覆盖报告、workflow gate metadata 和 workspace validate。

新增 `tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_record_exists_and_tracks_contract`，固定本记录、计划表链接、验证命令、临时验证例外和下一批入口。

关联保护测试包括：

- `tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules`
- `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates`
- `tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan`
- `tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan`
- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata`
- `tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_reuses_structured_placeholder_context`

## 实现说明

本批没有改变 `app/` 或 `rust/` 生产实现。新增保护测试通过 AST 和文本记录审计当前事实来源：

- 结构化占位符候选明细由 `collect_native_structured_placeholder_candidate_details` 生成。
- native helper 通过 `build_native_structured_placeholder_candidates_payload` 组装 payload，并消费 Rust `scan_rule_candidates(structured_placeholders)` 的 scan summary。
- 覆盖统计由 `count_uncovered_structured_placeholder_candidate_details` 和统一 coverage builder 完成。
- `scan-structured-placeholder-candidates` 通过 `_build_structured_placeholder_coverage_report_with_context` 进入 native helper。
- `import-structured-placeholder-rules`、workflow gate、text index metadata 和 workspace validate 通过 `build_structured_placeholder_coverage_result` 复用同一候选事实来源。

## 旧路径收束

本批确认当前 `app/` Python 代码中不再存在旧结构化候选事实来源：

- `collect_structured_placeholder_candidate_details`
- `_collect_structured_placeholder_candidate_details`
- `_iter_structured_shell_candidate_matches`
- `STRUCTURED_SHELL_CANDIDATE_PATTERNS`

这些旧名称只允许继续出现在历史记录和 scan_budget 保护测试里，用于证明迁移边界。Rust 原生模块中的 `STRUCTURED_SHELL_CANDIDATE_PATTERNS` 是 native 当前事实来源的一部分，不属于旧 Python helper。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

本批只补齐结构化占位符支线收束审计记录和计划索引，不改变用户可见命令行为。

## 性能证据

本批只新增静态保护和记录，不引入新的运行时扫描流程。

性能相关证据来自保护测试：

- 三个结构化占位符命令的 scan_budget 固定为每个命令一次候选扫描。
- 三个结构化占位符命令的插件源码 AST 扫描预算固定为 0。
- 三个结构化占位符命令的权威来源固定为 Rust `scan_rule_candidates(structured_placeholders)`。
- 当前生产入口通过 `collect_native_structured_placeholder_candidate_details` 或 `build_structured_placeholder_coverage_result` 消费同一 native 候选事实来源。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_covers_native_entries tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_record_exists_and_tracks_contract`，2 failed。失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-088.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_covers_native_entries tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_record_exists_and_tracks_contract`，2 passed。
- 相关结构化占位符行为回归：`uv run pytest tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_reuses_structured_placeholder_context`，6 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "structured_placeholder"`，14 passed，118 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非结构化占位符测试未在本批重复执行；本批用目标测试、相关结构化占位符行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批使用只读子代理辅助审计结构化占位符生产链路，主代理负责最终判断、记录和验证。

子代理结论与主代理 RED/GREEN 结果一致：当前代码状态支持结构化占位符支线收束，`app/` 下未发现旧 Python 结构化候选事实来源或调用路径，主要生产入口已经通过 `collect_native_structured_placeholder_candidate_details` 或统一的 `build_structured_placeholder_coverage_result` 消费 Rust `scan_rule_candidates(structured_placeholders)`。

子代理额外提醒：当前缺口集中在记录层，不在生产迁移层；补齐本记录和计划索引后，下一批不建议继续迁移结构化占位符生产入口，而应进入阶段总回顾。

## 剩余风险

本批是结构化占位符支线收束回归审计，不是 P1-B 结构化占位符阶段总回顾。下一批仍需汇总 6AY 到 6BE 的记录、测试、剩余风险和计划索引，判断结构化占位符支线是否可以整体关闭，并决定后续进入哪个 P1-B 或 P2 支线。

本批未跑全量 `uv run pytest`，全仓其它非结构化占位符测试没有在本批重复验证。

## 下一批入口

建议下一批进入 P1-B 结构化占位符阶段收束回顾：汇总 6AY 到 6BE 的支线迁移事实、剩余风险和是否可以进入下一个 P1-B 热路径审计。
