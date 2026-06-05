# Rust Scope/Index Engine 批次 76 验收记录

## 本批范围

本批是 6AS：普通占位符 workspace manifest native 化。范围覆盖 `prepare-agent-workspace` 写出的 `placeholder-candidates.json`，让候选 manifest 复用 `collect_native_placeholder_candidate_details`。

本批不迁移 `placeholder-rules.json` 草稿生成，也不迁移 `build-placeholder-rules`。草稿仍由 `scan_placeholder_candidates` 和 `_build_custom_placeholder_rule_draft` 生成，避免一次性牵动手动边界提示、草稿预览覆盖统计和旧语义测试。

## 保护网

新增 `tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest`：

- monkeypatch `app.agent_toolkit.services.workspace.collect_native_placeholder_candidate_details` 返回 native sentinel 候选。
- monkeypatch `app.agent_toolkit.services.workspace.scan_placeholder_candidates` 返回 legacy sentinel 候选。
- 调用 `prepare-agent-workspace`。
- 断言 `placeholder-candidates.json` 只使用 native sentinel。
- 断言 `placeholder-rules.json` 草稿仍来自 legacy sentinel。

新增 `tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists` 和 `tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_record_exists_and_tracks_contract`：

- 固定 `prepare_agent_workspace` 调用 `collect_native_placeholder_candidate_details` 写候选 manifest。
- 固定 `prepare_agent_workspace` 仍调用 `scan_placeholder_candidates` 给 `_build_custom_placeholder_rule_draft` 生成草稿。
- 固定 `placeholder_candidates_to_details` 不再参与 workspace manifest。
- 固定本记录和计划表链接。

## 实现说明

`app/agent_toolkit/services/workspace.py::prepare_agent_workspace` 现在分成两条普通占位符路径：

- `placeholder-candidates.json`：调用 `collect_native_placeholder_candidate_details`，写出旧报告同形候选明细。
- `placeholder-rules.json`：继续调用 `scan_placeholder_candidates`，再交给 `_build_custom_placeholder_rule_draft` 生成草稿。

这保持 workspace manifest 与 scan/coverage/workflow gate 的 native 候选事实一致，同时不改变草稿安全逻辑。

## 旧路径收束

本批从 workspace manifest 中移除了 `placeholder_candidates_to_details(scan_placeholder_candidates(...))` 组合。

旧 scanner 仍保留在两条草稿路径：

- `app/agent_toolkit/services/workspace.py::prepare_agent_workspace`：仅用于 `placeholder-rules.json` 草稿生成。
- `app/agent_toolkit/services/placeholder_rules.py::build_placeholder_rules`：用于公开 `build-placeholder-rules` 草稿生成、草稿预览覆盖统计和手动边界提示。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

`placeholder-candidates.json` 的 JSON 形状保持不变：

- `status`
- `errors`
- `warnings`
- `summary`
- `details.candidates[].marker`
- `details.candidates[].count`
- `details.candidates[].sources`
- `details.candidates[].standard_covered`
- `details.candidates[].custom_covered`
- `details.candidates[].covered`

`placeholder-rules.json` 的草稿输出形状不变。

## 性能证据

本批把 `prepare-agent-workspace` 的候选 manifest 扫描事实切到 native 明细，避免该输出继续用 Python 旧 scanner 生成候选报告。

本批没有减少草稿生成所需的一次旧 scanner 调用；这是刻意保留的旧路径，因为草稿生成还依赖旧 `PlaceholderCandidate` 结构和手动边界逻辑。下一批应单独评估草稿生成 native 化。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_record_exists_and_tracks_contract`，3 failed；失败点分别是 `placeholder-candidates.json` 未调用 native helper、计划缺少 `docs/records/rust-scope-index/batches/batch-076.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_record_exists_and_tracks_contract`，3 passed。
- 相关 workspace / scan_budget 回归：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_includes_placeholder_rule_draft tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_warns_uncovered_placeholder_rules tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_record_exists_and_tracks_contract`，7 passed。
- 全量回归：`uv run pytest`，881 passed。
- 类型检查：`uv run basedpyright`，0 errors、0 warnings、0 notes。
- 文档敏感路径/占位文案搜索：无匹配。
- Diff 空白检查：`git diff --check`，退出码 0。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未派发子代理执行改动。6AR 的只读子代理审计已经确认 `prepare-agent-workspace` manifest 是普通占位符旧 scanner 的剩余路径，本批按该边界做最小迁移。

## 剩余风险

普通占位符草稿生成仍未 native 化：

- `prepare-agent-workspace` 的 `placeholder-rules.json` 草稿仍使用旧 scanner。
- `build-placeholder-rules` 仍使用旧 scanner 生成草稿、草稿预览覆盖统计和手动边界警告。
- 如果下一批迁移草稿生成，需要先证明 native 明细足以表达旧 `PlaceholderCandidate` 的草稿输入，或先建立专用 adapter。

## 下一批入口

建议下一批进入普通占位符 workspace 草稿生成 native 化评估：确认 `placeholder-rules.json` 草稿是否可以复用 native 明细，或是否需要先把 `_build_custom_placeholder_rule_draft` 输入从 `PlaceholderCandidate` 收窄到旧报告同形 JSON 明细。
