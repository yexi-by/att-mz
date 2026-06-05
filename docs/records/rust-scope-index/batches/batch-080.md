# Rust Scope/Index Engine 批次 80 验收记录

## 本批范围

本批是 6AW：普通占位符支线收束回归审计，只新增保护测试、计划索引和验收记录，本批未修改生产代码。

范围覆盖普通占位符支线 6AN 到 6AV 的迁移结果：

- `scan-placeholder-candidates` 公开方法。
- `build-placeholder-rules` 草稿生成、草稿预览和手动边界统计。
- `prepare-agent-workspace` 候选 manifest 与 `placeholder-rules.json` 草稿。
- workflow gate、`app/application/flow_gate.py` 与普通占位符覆盖报告。
- 历史旧 scanner 模块 `app/agent_toolkit/placeholder_scan.py`。

## 保护网

新增 `tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_covers_native_entries`，固定以下事实：

- 计划表链接批次 71 到 80 的普通占位符记录。
- 生产代码中直接调用旧 `scan_placeholder_candidates` 的路径为空。
- 生产代码中直接调用旧 `_build_custom_placeholder_rule_draft` 的路径为空。
- 生产代码中直接调用旧 `_joined_text_boundary_markers` 的路径为空。
- 生产代码中的属性调用审计只允许 `app/cli/commands/rules.py` 通过 service 公开入口调用 `scan_placeholder_candidates`，旧 helper 属性调用路径为空。
- `scan-placeholder-candidates` 公开方法仍存在，但通过 `_build_placeholder_coverage_report_with_context` 进入 native 覆盖报告路径。
- `_build_placeholder_coverage_report_with_context` 使用 `collect_native_placeholder_candidate_details` 和 `count_uncovered_placeholder_candidate_details`。
- `build-placeholder-rules` 至少两次调用 `collect_native_placeholder_candidate_details`，并使用 `_build_custom_placeholder_rule_draft_from_details` 与 `_joined_text_boundary_markers_from_details`。
- `prepare-agent-workspace` 继续使用 native 明细写候选 manifest 和草稿。
- workflow gate 的 `build_normal_placeholder_coverage_result` 继续使用 native 明细。
- 批次 71 到 79 的记录链覆盖入口审计、Rust 候选入口、扫描命令薄适配、覆盖报告、workflow gate、workspace、build-placeholder-rules 草稿和预览/手动边界迁移。

新增 `tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_record_exists_and_tracks_contract`，固定本记录、计划表链接、验证命令和下一批入口。

## 实现说明

本批没有改变 `app/` 生产实现。新增保护测试通过 AST 和文本记录审计当前事实来源：

- 旧 scanner 名称仍存在于 `app/agent_toolkit/placeholder_scan.py` 和历史记录中。
- 普通占位符生产链路不再直接调用旧 scanner。
- 当前生产事实来源集中在 `app/agent_toolkit/services/common.py`、`app/agent_toolkit/services/placeholder_rules.py` 和 `app/agent_toolkit/services/workspace.py` 内消费的 `collect_native_placeholder_candidate_details`、`count_uncovered_placeholder_candidate_details`、`_build_custom_placeholder_rule_draft_from_details` 和 `_joined_text_boundary_markers_from_details`。

## 旧路径收束

本批确认旧 Python `scan_placeholder_candidates`、`_build_custom_placeholder_rule_draft` 和 `_joined_text_boundary_markers` 不再作为普通占位符生产事实来源被直接调用。

属性调用审计确认 `app/` 下只有 `app/cli/commands/rules.py` 通过 service 公开入口调用 `scan_placeholder_candidates`；旧草稿 helper 和旧边界 helper 没有属性调用路径。

保留的旧名称边界：

- `app/agent_toolkit/placeholder_scan.py` 仍保留旧 scanner 定义和 `PlaceholderCandidate` 导出。
- 历史记录和 scan_budget 保护测试仍会引用旧名称，用于证明迁移边界。
- 公开 `scan-placeholder-candidates` 方法的用户可见报告路径仍存在，但事实来源已经是 native 覆盖报告。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

## 性能证据

本批只新增静态保护和记录，不引入新的运行时扫描流程。性能相关证据来自保护测试：

- `scan-placeholder-candidates` 公开方法走 native 覆盖报告路径。
- `build-placeholder-rules` 的草稿、预览和手动边界统计统一走 native 明细。
- `prepare-agent-workspace` 的候选 manifest 和草稿统一走 native 明细。
- workflow gate 普通占位符覆盖统计走 native 明细。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_covers_native_entries tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_record_exists_and_tracks_contract`，2 failed；失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-080.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_covers_native_entries tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_record_exists_and_tracks_contract`，2 passed。
- 相关普通占位符回归：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_marks_custom_rule_coverage tests/test_agent_toolkit_rule_import.py::test_normal_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_details_for_preview_and_boundary`，8 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "placeholder"`，21 passed，95 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，最终无匹配。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批按补充分批策略未跑全量 `uv run pytest`。剩余风险是全仓其它非普通占位符测试未在本批重复执行；本批用目标测试、相关普通占位符保护、scan_budget 记录保护和类型检查约束影响面。
- 本批未修改生产代码。

## 审查处理

本批使用只读子代理辅助审计普通占位符生产链路，主代理负责最终判断、记录和验证。子代理结论与主代理验证一致：旧 `scan_placeholder_candidates`、`_build_custom_placeholder_rule_draft`、`_joined_text_boundary_markers` 在生产代码中的直接调用集合为空；公开 `scan-placeholder-candidates` CLI 和 service 方法仍保留，事实来源已经进入 native 明细和覆盖报告路径。

子代理额外提醒：`app/agent_toolkit/services/common.py` 和 `app/agent_toolkit/__init__.py` 仍导出旧 API，旧 helper 定义仍存在，部分测试 fixture 和旧语义测试仍直接绑定旧 scanner。这些不是生产调用，但属于下一批阶段回顾需要判断是否继续保留的旧事实边界。

## 剩余风险

本批是普通占位符支线收束回归审计，不是阶段总回顾。下一批需要复核 6AN 到 6AW 的记录、测试、剩余风险和计划索引，判断普通占位符支线是否可以整体关闭，并决定后续进入哪个 P1-B 或 P2 支线。

## 下一批入口

建议下一批进入 P1-B 普通占位符阶段收束回顾：汇总 6AN 到 6AW 的支线迁移事实、剩余风险和是否可以进入下一个 P1-B 热路径审计。
