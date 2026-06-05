# Rust Scope/Index Engine 批次 77 验收记录

## 本批范围

本批是 6AT：普通占位符 workspace 草稿生成 native 化评估。范围覆盖 `prepare-agent-workspace` 写出的 `placeholder-rules.json` 草稿，让 workspace 的普通占位符候选 manifest 和草稿生成共用同一次 `collect_native_placeholder_candidate_details` 明细。

本批不迁移公开 `build-placeholder-rules` 命令。该命令仍保留旧 `scan_placeholder_candidates`、草稿预览覆盖统计和手动边界警告，后续单独评估。

## 保护网

调整 `tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest`：

- monkeypatch `collect_native_placeholder_candidate_details` 返回 native sentinel 候选。
- monkeypatch `app.agent_toolkit.services.workspace.scan_placeholder_candidates` 为报错函数，并允许该属性不存在。
- 调用 `prepare-agent-workspace`。
- 断言 `placeholder-candidates.json` 使用 native sentinel。
- 断言 `placeholder-rules.json` 草稿也来自同一个 native sentinel。
- 断言 native helper 只调用一次，避免 manifest 和草稿各扫一遍。

新增 `tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists` 和 `tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_record_exists_and_tracks_contract`：

- 固定新增 `_build_custom_placeholder_rule_draft_from_details`。
- 固定 `prepare_agent_workspace` 不再调用 `scan_placeholder_candidates`。
- 固定生产代码中直接调用旧 `scan_placeholder_candidates` 的路径只剩 `app/agent_toolkit/services/placeholder_rules.py`。
- 固定 `build-placeholder-rules` 仍保留旧 scanner 和 `_build_custom_placeholder_rule_draft`。
- 固定本记录和计划表链接。

## 实现说明

`app/agent_toolkit/services/common.py` 新增 `_build_custom_placeholder_rule_draft_from_details`：

- 输入为旧报告同形 `JsonArray` 候选明细。
- 校验 `marker`、`standard_covered`、`custom_covered` 字段类型。
- 跳过标准规则或自定义规则已覆盖候选。
- 复用 `_needs_manual_joined_text_boundary` 和 `_draft_custom_placeholder_rule`。

`app/agent_toolkit/services/workspace.py::prepare_agent_workspace` 现在：

- 调用一次 `collect_native_placeholder_candidate_details`。
- 用同一份明细写出 `placeholder-candidates.json`。
- 用同一份明细生成 `placeholder-rules.json` 草稿。

## 旧路径收束

本批从 `prepare-agent-workspace` 中删除了旧 `scan_placeholder_candidates` 调用。普通占位符旧 scanner 的生产直接调用范围收束为：

- `app/agent_toolkit/services/placeholder_rules.py::build_placeholder_rules`

该旧路径仍服务公开 `build-placeholder-rules` 命令的草稿生成、草稿预览覆盖统计和手动边界警告。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

`placeholder-candidates.json` 和 `placeholder-rules.json` 的 JSON 形状保持不变。若 native 明细缺少必要字段，workspace 现在会在草稿生成阶段显式报错，而不是回到旧 scanner 静默补算。

## 性能证据

本批减少 `prepare-agent-workspace` 普通占位符分支的一次旧 Python 全量扫描：manifest 和草稿复用同一份 native 候选明细。

公开 `build-placeholder-rules` 仍有旧 Python 扫描；这是本批刻意保留的剩余路径，下一批单独处理。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_record_exists_and_tracks_contract`，3 failed；失败点分别是 `prepare-agent-workspace` 草稿仍调用旧 Python scanner、计划缺少 `docs/records/rust-scope-index/batches/batch-077.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_record_exists_and_tracks_contract`，3 passed。
- 相关 workspace 回归：`uv run pytest tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_includes_placeholder_rule_draft tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_warns_uncovered_placeholder_rules`，4 passed。
- 相关 scan_budget 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_record_exists_and_tracks_contract`，6 passed。
- 全量回归初跑：`uv run pytest`，1 failed，882 passed；失败项是批次 71 历史审计测试仍把当时的 workspace 旧 scanner 残留当成当前事实。
- 历史记录保护修正：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_record_exists_and_tracks_contract`，3 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量回归复跑：`uv run pytest`，883 passed。
- 文档敏感路径/占位文案搜索：无命中。
- Diff 空白检查：`git diff --check`，通过；只输出仓库既有 LF/CRLF 换行提示。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未派发子代理执行改动。6AR 的只读子代理审计已指出 workspace 是旧 scanner 残留路径；本批基于该结论继续收束。

## 剩余风险

公开 `build-placeholder-rules` 仍未 native 化：

- 仍使用旧 scanner 生成草稿。
- 仍使用旧 scanner 做草稿预览覆盖统计。
- 仍依赖旧 `PlaceholderCandidate` 结构做手动边界警告。

下一批需要先固定这些行为，再判断是否复用 `_build_custom_placeholder_rule_draft_from_details` 或建立更完整的 native draft adapter。

## 下一批入口

建议下一批进入普通占位符 build-placeholder-rules 草稿生成 native 化评估：先建立 RED，要求公开 `build-placeholder-rules` 不再为草稿生成调用旧 scanner，同时确认草稿预览覆盖统计和手动边界警告的迁移边界。
