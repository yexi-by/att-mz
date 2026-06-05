# Rust Scope/Index Engine 批次 6BD 验收记录

## 本批范围

本批是结构化占位符旧 helper 删除或隔离评估。结论是删除旧 Python 候选 helper，保留已经 native 化的结构化占位符候选事实来源。

本批触及以下文件：

- `app/application/flow_gate.py`
- `app/agent_toolkit/services/common.py`
- `tests/test_agent_toolkit_coverage.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`

本批不修改 CLI 参数、stdout JSON 字段、数据库 schema、配置字段、Rust 原生代码或发布流程。

## 保护网

新增 `tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_contract_exists`：

- 固定 `app/application/flow_gate.py` 不再导出或定义 `collect_structured_placeholder_candidate_details`。
- 固定 `app/application/flow_gate.py` 不再保留 `_iter_structured_shell_candidate_matches`、`_structured_rule_covered_ranges` 和 `STRUCTURED_SHELL_CANDIDATE_PATTERNS`。
- 固定 `app/agent_toolkit/services/common.py` 不再导出或定义 `_collect_structured_placeholder_candidate_details`。
- 固定 `app/agent_toolkit/services/common.py` 不再保留结构化 shell 候选旧扫描器。
- 固定 `_collect_structured_placeholder_preview_samples` 和 `_line_matches_structured_rules` 继续存在，避免误删结构化规则样本预览能力。
- 固定行为测试改为使用 `collect_native_structured_placeholder_candidate_details` 作为 native 入口哨兵。

新增 `tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定删除范围、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

同步调整既有保护：

- `tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths` 不再要求当前代码保留旧 helper。
- `tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists` 不再允许旧 shell scanner 调用残留。
- `tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan` 使用 native helper sentinel 证明扫描命令消费 native 入口。
- `tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan` 使用 native helper sentinel 证明 coverage builder 消费 native 入口。
- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata` 禁止 warm index 路径重新调用 native 结构化候选扫描。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_record_exists_and_tracks_contract
```

结果：3 failed。失败点分别是 `common.py::_collect_structured_placeholder_candidate_details` 仍存在、计划缺少 `docs/records/rust-scope-index/batches/batch-087.md`，以及本批记录不存在。

## 实现说明

`app/application/flow_gate.py` 删除以下旧路径：

- `collect_structured_placeholder_candidate_details`
- `_iter_structured_shell_candidate_matches`
- `_structured_rule_covered_ranges`
- `STRUCTURED_SHELL_CANDIDATE_PATTERNS`
- `collect_structured_placeholder_candidate_details` 的 `__all__` 导出

`app/agent_toolkit/services/common.py` 删除以下旧路径：

- `_collect_structured_placeholder_candidate_details`
- `_iter_structured_shell_candidate_matches`
- `_structured_rule_covered_ranges`
- `STRUCTURED_SHELL_CANDIDATE_PATTERNS`
- `_collect_structured_placeholder_candidate_details` 的 `__all__` 导出

`common.py::_collect_structured_placeholder_preview_samples` 仍保留，并继续通过 `_line_matches_structured_rules` 判断结构化规则样本文本。该路径用于规则预览，不再承担候选覆盖扫描。

## 旧路径收束

本批删除结构化占位符旧 Python shell 候选扫描事实来源。结构化候选覆盖、扫描命令、workflow gate、workspace validate、doctor、quality-report、audit-coverage、write-back 和 import 风险确认继续通过 native helper 产出候选明细。

旧记录中提到的历史 helper 只作为历史说明存在，不再是当前代码导出、生产调用或测试夹具依赖。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

`app/application/flow_gate.py::collect_structured_placeholder_candidate_details` 曾作为内部导出保留，但没有生产调用。本批删除该导出，属于源码内部旧 helper 收束；对公开 CLI JSON、用户文案和规则导入协议没有影响。

## 性能证据

本批减少旧 Python 候选扫描入口，避免后续代码误用 `_iter_structured_shell_candidate_matches` 形成第二事实来源。

当前结构化占位符候选事实来源保持为 `collect_native_structured_placeholder_candidate_details`，底层由 Rust `scan_rule_candidates(structured_placeholders)` 生成旧报告同形候选明细。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_record_exists_and_tracks_contract`，3 failed。
- GREEN 代码契约：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_contract_exists`，3 passed。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_record_exists_and_tracks_contract`，4 passed。
- 相关行为回归：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata`，3 passed。
- 相关 scan_budget 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_contract_exists tests/test_scan_budget.py::test_batch87_structured_placeholder_legacy_helpers_removed_record_exists_and_tracks_contract`，7 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`，909 passed。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批修改生产 Python 代码，因此已执行全量 `uv run pytest`。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未派发子代理执行改动。上一批只读审计已确认旧 helper 没有生产调用；本批通过 RED/GREEN 静态测试和行为哨兵完成删除。

## 剩余风险

旧结构化 helper 已从当前代码删除。剩余风险是历史验收记录仍描述旧 helper 曾经存在，后续阅读时需要按批次时间线理解，不应把早期记录当作当前实现。

后续仍需做结构化占位符支线收束回归审计，确认 scan budget、行为测试、记录索引和 native 入口覆盖已经足够，不再需要额外结构化占位符支线迁移批次。

## 下一批入口

建议下一批进入结构化占位符支线收束回归审计：汇总 6AY 到 6BD 的结构化占位符支线迁移结果，确认当前没有旧 Python 候选事实来源、没有重复扫描入口，并给出是否进入 P1-B 结构化占位符阶段收束回顾的判断。
