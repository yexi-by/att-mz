# Rust Scope/Index Engine 批次 79 验收记录

## 本批范围

本批是 6AV：普通占位符 build-placeholder-rules 预览/手动边界 native 化评估。范围覆盖公开 `build-placeholder-rules` 命令中的 `uncovered_count_after_draft_preview`、`manual_boundary_candidate_count` 和 `manual_boundary_candidates`。

本批不删除公开 `scan-placeholder-candidates` 方法，也不改变 `placeholder-rules.json` 草稿文件形状。目标是让 `build-placeholder-rules` 命令内的草稿生成、草稿预览覆盖统计和手动边界警告全部复用 native 普通占位符候选明细。

## 保护网

新增 `tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_details_for_preview_and_boundary`：

- monkeypatch `collect_native_placeholder_candidate_details` 按调用顺序返回草稿前和草稿后的 native sentinel 明细。
- monkeypatch `scan_placeholder_candidates` 为报错函数。
- 调用公开 `build-placeholder-rules`。
- 断言 native helper 被调用两次。
- 断言 `placeholder-rules.json` 草稿来自 native sentinel。
- 断言 `candidate_count`、`uncovered_count_before_draft`、`uncovered_count_after_draft_preview`、`manual_boundary_candidate_count` 和 `manual_boundary_candidates` 都来自 native 明细。

新增 `tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_contract_exists` 和 `tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_record_exists_and_tracks_contract`：

- 固定新增 `_joined_text_boundary_markers_from_details`。
- 固定 `build_placeholder_rules` 至少两次调用 `collect_native_placeholder_candidate_details`。
- 固定 `build_placeholder_rules` 不再调用旧 `scan_placeholder_candidates`。
- 固定生产代码中直接调用旧 `scan_placeholder_candidates` 的路径为空。
- 固定本记录和计划表链接。

## 实现说明

`app/agent_toolkit/services/common.py` 新增 `_joined_text_boundary_markers_from_details`，按旧报告同形候选明细筛选必须人工确认边界的裸字母控制符候选：

- 校验 `marker`、`standard_covered`、`custom_covered` 字段类型。
- 跳过标准规则或自定义规则已覆盖候选。
- 复用 `_needs_manual_joined_text_boundary` 判定边界风险。
- 按大小写无关顺序返回去重后的 marker。

`app/agent_toolkit/services/placeholder_rules.py::build_placeholder_rules` 现在：

- 用第一次 `collect_native_placeholder_candidate_details` 生成草稿、草稿前未覆盖计数和手动边界 marker。
- 生成 draft text rules 后，用第二次 `collect_native_placeholder_candidate_details` 取代旧 `draft_preview_candidates`，并通过 `count_uncovered_placeholder_candidate_details` 计算草稿预览后的未覆盖计数。
- 不再导入或调用旧 `scan_placeholder_candidates`、`count_uncovered_candidates` 或 `_joined_text_boundary_markers`。

## 旧路径收束

本批删除了 `build-placeholder-rules` 内最后两处旧 scanner 直接调用。普通占位符旧 scanner 不再被生产服务直接调用；后续保留的公开 `scan-placeholder-candidates` 方法会通过 native 覆盖报告路径输出旧报告同形 JSON。

历史批次 71、76、77、78 中关于旧 scanner 的保护测试已调整为检查当批记录中的历史边界，不再要求当前生产代码保留旧调用。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

`placeholder-rules.json` 的 JSON 形状保持不变。`manual_boundary_candidate_count`、`manual_boundary_candidates` 和 `uncovered_count_after_draft_preview` 的含义保持不变，但事实来源切换为 native 候选明细。

## 性能证据

本批移除了公开 `build-placeholder-rules` 命令内两次旧 Python 候选扫描：

- 手动边界警告不再要求旧 `PlaceholderCandidate`。
- 草稿预览覆盖统计不再重新跑旧 scanner。
- `build-placeholder-rules` 内普通占位符候选事实统一来自 native 明细。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_details_for_preview_and_boundary tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_contract_exists tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_record_exists_and_tracks_contract`，3 failed；失败点分别是旧 scanner 被调用、计划缺少 `docs/records/rust-scope-index/batches/batch-079.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_details_for_preview_and_boundary tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_contract_exists tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_record_exists_and_tracks_contract`，3 passed。
- 相关普通占位符回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_details_for_preview_and_boundary`，3 passed。
- 相关 scan_budget 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_contract_exists tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_contract_exists tests/test_scan_budget.py::test_batch79_placeholder_build_rules_preview_boundary_native_record_exists_and_tracks_contract`，9 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径/占位文案搜索：无命中。
- Diff 空白检查：`git diff --check`，通过；只输出仓库既有 LF/CRLF 换行提示。
- 全量回归：本批按补充分批策略未跑全量 `uv run pytest`。剩余风险是全仓其它非普通占位符测试未在本批重复执行；本批用目标测试、相关普通占位符回归、scan_budget 记录保护和类型检查约束影响面。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未派发子代理执行改动。迁移点集中在 `build_placeholder_rules` 的预览统计和手动边界统计，主代理直接对照 RED/GREEN 和 scan_budget 保护收束。

## 剩余风险

本批未做普通占位符支线的阶段性总审计。下一批需要从公开命令、服务方法、历史记录保护和 scan budget 角度确认普通占位符支线是否已经没有旧 Python 候选扫描生产直接调用，并检查是否还有测试夹具或文档语义需要收束。

## 下一批入口

建议下一批进入普通占位符支线收束回归审计：先建立 RED，要求普通占位符生产链路没有旧 scanner 直接调用，并用记录明确公开 `scan-placeholder-candidates` 的 native 覆盖报告路径、`build-placeholder-rules` 的两次 native 明细调用和剩余风险。
