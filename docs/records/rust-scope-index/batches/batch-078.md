# Rust Scope/Index Engine 批次 78 验收记录

## 本批范围

本批是 6AU：普通占位符 build-placeholder-rules 草稿生成 native 化评估。范围覆盖公开 `build-placeholder-rules` 命令写出的 `placeholder-rules.json` 草稿生成。

本批只迁移草稿生成的候选事实来源：`candidate_count`、`uncovered_count_before_draft` 和 `draft_rules` 复用 `collect_native_placeholder_candidate_details` 明细。`draft_preview_candidates` 和 `_joined_text_boundary_markers` 仍暂时使用旧 `scan_placeholder_candidates`，作为下一批单独评估的残留路径。

## 保护网

新增 `tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft`：

- monkeypatch `collect_native_placeholder_candidate_details` 返回只存在于 native sentinel 的候选。
- monkeypatch `scan_placeholder_candidates` 返回空候选，隔离旧 scanner 草稿来源。
- 调用公开 `build-placeholder-rules`。
- 断言 `placeholder-rules.json` 草稿来自 native sentinel。
- 断言 `candidate_count` 和 `uncovered_count_before_draft` 来自 native 明细。

新增 `tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_contract_exists` 和 `tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_record_exists_and_tracks_contract`：

- 固定 `build_placeholder_rules` 调用 `collect_native_placeholder_candidate_details`。
- 固定 `build_placeholder_rules` 调用 `count_uncovered_placeholder_candidate_details`。
- 固定 `build_placeholder_rules` 调用 `_build_custom_placeholder_rule_draft_from_details`。
- 固定 `build_placeholder_rules` 不再调用 `_build_custom_placeholder_rule_draft`。
- 固定旧 `scan_placeholder_candidates` 仍只在 `app/agent_toolkit/services/placeholder_rules.py` 直接调用。
- 固定本记录和计划表链接。

## 实现说明

`app/agent_toolkit/services/placeholder_rules.py::build_placeholder_rules` 现在先从 native 普通占位符候选明细生成草稿：

- `collect_native_placeholder_candidate_details` 读取旧报告同形候选明细。
- `count_uncovered_placeholder_candidate_details` 统计草稿生成前未覆盖候选数。
- `_build_custom_placeholder_rule_draft_from_details` 把未覆盖候选折叠成 Agent 可编辑规则草稿。

旧 `scan_placeholder_candidates` 仍在同一命令内保留两类职责：

- 给 `_joined_text_boundary_markers` 提供手动边界候选。
- 给 `draft_preview_candidates` 提供草稿预览后的覆盖统计。

## 旧路径收束

本批从 `build-placeholder-rules` 的草稿生成主路径中删除旧 `PlaceholderCandidate` 草稿 helper：`_build_custom_placeholder_rule_draft` 不再由 `build_placeholder_rules` 调用。

普通占位符旧 scanner 仍有生产直接调用，但范围收束为公开 `build-placeholder-rules` 内的预览统计和手动边界警告。下一批需要决定这两类职责是否共用 native 明细，或是否需要补充 native 手动边界分类字段。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

`placeholder-rules.json` 的 JSON 形状保持不变。若 native 明细缺少必要字段，草稿生成会沿用明细 helper 的显式类型错误，不回退到旧 scanner 静默补算。

## 性能证据

本批减少公开 `build-placeholder-rules` 草稿生成的一次旧 Python 候选折叠依赖：草稿候选、草稿前未覆盖计数和规则草稿共用 native 明细。

旧 Python 扫描尚未完全移除，因为草稿预览覆盖统计和手动边界警告仍需要候选对象。该残留会在下一批单独验证，避免一次性改变 warnings 与 preview summary 语义。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_contract_exists tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_record_exists_and_tracks_contract`，3 failed；失败点分别是 native helper 未被调用、计划缺少 `docs/records/rust-scope-index/batches/batch-078.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_contract_exists tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_record_exists_and_tracks_contract`，3 passed。
- 相关普通占位符回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_contract_exists tests/test_scan_budget.py::test_batch76_placeholder_workspace_manifest_native_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_contract_exists tests/test_scan_budget.py::test_batch77_placeholder_workspace_draft_native_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_contract_exists tests/test_scan_budget.py::test_batch78_placeholder_build_rules_draft_native_record_exists_and_tracks_contract`，8 passed。
- 全量回归初跑：`uv run pytest`，1 failed，885 passed；失败项是批次 71 历史审计测试仍把当时的旧草稿 helper 当成当前事实。
- 历史记录保护修正：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths`，1 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量回归复跑：`uv run pytest`，886 passed。
- 文档敏感路径/占位文案搜索：无命中。
- Diff 空白检查：`git diff --check`，通过；只输出仓库既有 LF/CRLF 换行提示。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未派发子代理执行改动。迁移点集中在 `build_placeholder_rules` 单一命令，主代理直接对照 RED/GREEN 和 scan_budget 保护收束。

## 剩余风险

公开 `build-placeholder-rules` 仍未完全 native 化：

- 草稿预览覆盖统计仍使用旧 scanner。
- 手动边界警告仍使用旧 `PlaceholderCandidate` 分类。
- `manual_boundary_candidate_count` 和 `uncovered_count_after_draft_preview` 的计算仍来自旧候选对象。

下一批需要先固定这些残留行为，再评估是否把手动边界分类迁到 native 明细，或新增更窄的 native preview adapter。

## 下一批入口

建议下一批进入普通占位符 build-placeholder-rules 预览/手动边界 native 化评估：先建立 RED，要求 `draft_preview_candidates` 和 `_joined_text_boundary_markers` 不再依赖旧 scanner，同时保持 warnings 与 summary 字段语义不变。
