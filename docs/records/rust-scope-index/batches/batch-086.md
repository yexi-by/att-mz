# Rust Scope/Index Engine 批次 6BC 验收记录

## 本批范围

本批是结构化占位符 workflow gate native 化审计。范围只做静态保护和验收记录，不修改生产代码、CLI 参数、数据库 schema、Rust 原生代码或发布流程。

审计对象覆盖结构化占位符候选覆盖结果的主线消费入口：

- `collect_workflow_gate_errors`
- `collect_indexed_workflow_gate_errors`
- `collect_placeholder_candidate_review_decisions`
- `collect_placeholder_candidate_review_warnings`
- `text_index.py::_placeholder_gate_metadata`
- `quality-report`
- `write-back`
- `doctor`
- `audit-coverage`
- `validate-agent-workspace`
- `import-structured-placeholder-rules`

本批不删除 `collect_structured_placeholder_candidate_details`、`_collect_structured_placeholder_candidate_details` 或 `_iter_structured_shell_candidate_matches`。旧 helper 的删除、私有化或测试夹具隔离留到下一批评估。

## 保护网

新增 `tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists`：

- 固定 workflow gate 冷路径通过 `collect_workflow_gate_errors` 调用 `collect_placeholder_candidate_review_decisions`。
- 固定 indexed workflow gate 在缺少外部传入占位符 gate 结果时仍调用 `collect_placeholder_candidate_review_decisions`。
- 固定统一审查决策通过 `build_structured_placeholder_coverage_result` 获取结构化占位符覆盖结果，不直接调用旧 `collect_structured_placeholder_candidate_details`。
- 固定 text index metadata 通过 `_placeholder_gate_metadata` 调用 `build_structured_placeholder_coverage_result`。
- 固定 `quality-report`、`doctor`、`audit-coverage` 和 `write-back` 前置路径经由统一 review / workflow gate 入口消费结构化占位符覆盖结果。
- 固定 `validate-agent-workspace` 和 `import-structured-placeholder-rules` 通过 `build_structured_placeholder_coverage_result` 生成覆盖明细。
- 固定生产代码没有直接调用 `collect_structured_placeholder_candidate_details` 或 `_collect_structured_placeholder_candidate_details`。
- 固定 `_iter_structured_shell_candidate_matches` 的生产调用只剩旧 helper 定义所在文件。

新增 `tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定审计覆盖命令、主线 native coverage builder、剩余旧路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-086.md` 链接，以及本批记录不存在。

## 实现说明

本批没有生产实现改动。静态审计确认：

| 链路 | 当前结构化占位符覆盖事实来源 | 本批结论 |
| --- | --- | --- |
| workflow gate 冷路径 | `collect_workflow_gate_errors` -> `collect_placeholder_candidate_review_decisions` -> `build_structured_placeholder_coverage_result` | 已复用 native 明细 |
| indexed workflow gate | `collect_indexed_workflow_gate_errors` 在未传入 `placeholder_gate_errors` 时调用 `collect_placeholder_candidate_review_decisions` | 已复用 native 明细 |
| text index gate metadata | `_placeholder_gate_metadata` -> `build_structured_placeholder_coverage_result` | 已复用 native 明细 |
| `quality-report` warm index | `_quality_report_from_text_index` -> `collect_placeholder_candidate_review_decisions` | 已复用 native 明细 |
| `quality-report` cold/full path | `quality_report` -> `collect_workflow_gate_errors` / `collect_placeholder_candidate_review_warnings` | 已复用 native 明细 |
| `doctor` | `doctor` -> `collect_placeholder_candidate_review_decisions` | 已复用 native 明细 |
| `audit-coverage` | `audit_coverage` -> `collect_placeholder_candidate_review_warnings` | 已复用 native 明细 |
| `write-back` warm index | `_prepare_write_operation_from_text_index` -> `collect_indexed_workflow_gate_errors` | 已复用 text index gate 元信息 |
| `write-back` cold path | `_prepare_write_operation` -> `assert_workflow_gate_passed` -> `collect_workflow_gate_errors` | 已复用 native 明细 |
| `validate-agent-workspace` | `validate_agent_workspace` -> `build_structured_placeholder_coverage_result` | 已复用 native 明细 |
| `import-structured-placeholder-rules` | `import_structured_placeholder_rules` -> `build_structured_placeholder_coverage_result` | 已复用 native 明细 |

## 旧路径收束

本批确认旧结构化候选 helper 没有生产调用：

- `app/application/flow_gate.py::collect_structured_placeholder_candidate_details`
- `app/agent_toolkit/services/common.py::_collect_structured_placeholder_candidate_details`

旧 shell 扫描函数 `_iter_structured_shell_candidate_matches` 仍只被上述旧 helper 使用。`app/application/flow_gate.py` 中的 `collect_structured_placeholder_candidate_details` 仍在 `__all__` 导出，属于下一批删除或隔离评估边界。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

本批只新增静态保护测试和验收记录。对外可见的结构化占位符候选报告、workflow gate 错误码、quality report 警告、doctor 警告、write-back 前置错误、workspace 校验报告和 import 风险确认行为均未改变。

## 性能证据

本批没有新增运行时扫描。性能证据来自静态入口审计：

- 结构化占位符 workflow gate、doctor、quality report、audit coverage、write-back 前置路径、workspace validate 和 import 风险确认都经由 `build_structured_placeholder_coverage_result`。
- 该 builder 已在 6BB 切到 `app/native_structured_placeholder_scan.py`，由 `scan_rule_candidates(structured_placeholders)` 产出候选明细。
- 旧 Python shell 候选扫描 helper 不再被生产主线调用。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_record_exists_and_tracks_contract`，2 failed。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_record_exists_and_tracks_contract`，2 passed。
- 相关 scan_budget 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch84_structured_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch86_structured_placeholder_workflow_gate_native_record_exists_and_tracks_contract`，6 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批按临时例外未跑全量 `uv run pytest`：本批未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程，也不是每 5 个编号批次后的全量节点。剩余风险是全仓其他测试未在本批重复执行；该风险由本批只新增静态保护测试、计划行和验收记录的低行为影响面约束。
- 本批未修改 Rust 原生代码。

## 审查处理

本批派发只读子代理审计结构化占位符 workflow gate、doctor、workspace validate、import 和旧 helper 残留。子代理结论与本地审计一致：主线 workflow gate 已经 native 化，生产代码未发现绕过 builder 直接调用旧 helper 的路径；并建议本批不改生产代码，只补审计记录和 scan_budget 保护。

主代理以本地静态测试、代码阅读和验证命令为最终依据。

## 剩余风险

旧结构化候选 helper 仍保留：

- `app/application/flow_gate.py::collect_structured_placeholder_candidate_details` 仍在 `__all__` 导出。
- `app/agent_toolkit/services/common.py::_collect_structured_placeholder_candidate_details` 仍作为私有旧 helper 存在。
- `_iter_structured_shell_candidate_matches` 仍服务上述旧 helper。

下一批需要决定这些旧 helper 是删除、私有化、只保留测试哨兵，还是作为临时兼容入口继续保留，并同步调整 scan_budget、历史记录预期和相关 monkeypatch 测试。

## 下一批入口

建议下一批进入结构化占位符旧 helper 删除或隔离评估：优先审计 `collect_structured_placeholder_candidate_details` 的导出边界、`common.py::_collect_structured_placeholder_candidate_details` 的剩余价值，以及相关测试是否可以改为只保护 native builder。
