# Rust Scope/Index Engine 批次 75 验收记录

## 本批范围

本批是 6AR：普通占位符 workflow gate native 化审计。范围只做静态保护和验收记录，不修改生产代码、CLI 参数、数据库 schema、Rust 原生代码或发布流程。

审计对象覆盖普通占位符候选覆盖结果的主线消费入口：

- `collect_workflow_gate_errors`
- `collect_indexed_workflow_gate_errors`
- `collect_placeholder_candidate_review_decisions`
- `collect_placeholder_candidate_review_warnings`
- `text_index.py::_placeholder_gate_metadata`
- `quality-report`
- `write-back`
- `doctor`
- `audit-coverage`
- `prepare-agent-workspace`
- `validate-agent-workspace`

本批不迁移 `build-placeholder-rules` 草稿生成，也不迁移 `prepare-agent-workspace` 输出 `placeholder-candidates.json` 和 `placeholder-rules.json` 草稿时的旧 scanner。

## 保护网

新增 `tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists`：

- 固定 workflow gate 冷路径通过 `collect_workflow_gate_errors` 调用 `collect_placeholder_candidate_review_decisions`。
- 固定 indexed workflow gate 在缺少外部传入占位符 gate 结果时仍调用 `collect_placeholder_candidate_review_decisions`。
- 固定 `collect_placeholder_candidate_review_decisions` 通过 `build_normal_placeholder_coverage_result` 获取普通占位符覆盖结果，不直接调用旧 scanner。
- 固定 text index metadata 通过 `_placeholder_gate_metadata` 调用 `build_normal_placeholder_coverage_result`。
- 固定 `quality-report`、`doctor`、`audit-coverage` 和 `write-back` 前置路径经由统一 review / workflow gate 入口消费普通占位符覆盖结果。
- 固定当前生产代码里直接调用 `scan_placeholder_candidates` 的路径只剩 `app/agent_toolkit/services/placeholder_rules.py` 和 `app/agent_toolkit/services/workspace.py`。
- 固定旧 scanner 函数级调用只允许出现在 `build_placeholder_rules` 和 `prepare_agent_workspace`，避免同文件内其他 workflow gate 或 workspace validate 路径回退。
- 固定 `validate-agent-workspace` 通过 `build_normal_placeholder_coverage_result` 生成覆盖明细，同时 `prepare-agent-workspace` 仍保留旧 scanner 生成 manifest 和草稿。

新增 `tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定审计覆盖命令、主线 native coverage builder、剩余旧路径、验证命令和下一批入口。

## 实现说明

本批没有生产实现改动。静态审计确认：

| 链路 | 当前普通占位符覆盖事实来源 | 本批结论 |
| --- | --- | --- |
| workflow gate 冷路径 | `collect_workflow_gate_errors` -> `collect_placeholder_candidate_review_decisions` -> `build_normal_placeholder_coverage_result` | 已复用 native 明细 |
| indexed workflow gate | `collect_indexed_workflow_gate_errors` 在未传入 `placeholder_gate_errors` 时调用 `collect_placeholder_candidate_review_decisions` | 已复用 native 明细 |
| text index gate metadata | `_placeholder_gate_metadata` -> `build_normal_placeholder_coverage_result` | 已复用 native 明细 |
| `quality-report` warm index | `_quality_report_from_text_index` -> `collect_placeholder_candidate_review_decisions` | 已复用 native 明细 |
| `quality-report` cold/full path | `quality_report` -> `collect_workflow_gate_errors` / `collect_placeholder_candidate_review_warnings` | 已复用 native 明细 |
| `doctor` | `doctor` -> `collect_placeholder_candidate_review_decisions` | 已复用 native 明细 |
| `audit-coverage` | `audit_coverage` -> `collect_placeholder_candidate_review_warnings` | 已复用 native 明细 |
| `write-back` warm index | `_prepare_write_operation_from_text_index` -> `collect_indexed_workflow_gate_errors` | 已复用 text index gate 元信息 |
| `write-back` cold path | `_prepare_write_operation` -> `assert_workflow_gate_passed` -> `collect_workflow_gate_errors` | 已复用 native 明细 |
| `validate-agent-workspace` | `validate_agent_workspace` -> `build_normal_placeholder_coverage_result` | 已复用 native 明细 |
| `prepare-agent-workspace` manifest/草稿 | `prepare_agent_workspace` -> `scan_placeholder_candidates` | 仍是旧 scanner，下一批迁移 |
| `build-placeholder-rules` 草稿生成 | `build_placeholder_rules` -> `scan_placeholder_candidates` | 仍是旧 scanner，单独后续迁移 |

## 旧路径收束

本批将旧 scanner 直接调用范围固定为两处：

- `app/agent_toolkit/services/placeholder_rules.py::build_placeholder_rules`：用于生成普通占位符草稿、草稿预览覆盖统计和手动边界提示。
- `app/agent_toolkit/services/workspace.py::prepare_agent_workspace`：用于导出 `placeholder-candidates.json` 和生成 `placeholder-rules.json` 草稿。

这些路径仍需要保留旧语义测试保护，不能由本批的 workflow gate 审计结论外推为已迁移。下一批应优先迁移 workspace manifest，因为它可以复用上一批的 native 明细而不碰 `build-placeholder-rules` 的草稿安全逻辑。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

本批只新增静态保护测试和验收记录。对外可见的普通占位符候选报告、workflow gate 错误码、quality report 警告、doctor 警告、write-back 前置错误和 workspace JSON 文件形状均未改变。

## 性能证据

本批没有新增运行时扫描。性能证据来自静态入口审计：

- 普通占位符 workflow gate、doctor、quality report、audit coverage 和 write-back 前置路径不再直接调用旧 Python scanner。
- 这些主线路径复用 `build_normal_placeholder_coverage_result`，而该 builder 已在 6AQ 切到 `app/native_placeholder_scan.py`。
- 直接调用旧 scanner 的生产路径只剩草稿/manifest 输出，不再覆盖 workflow gate 主线。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_record_exists_and_tracks_contract`，2 failed；失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-075.md` 链接，以及本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_record_exists_and_tracks_contract`，2 passed。
- 相关 scan_budget 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_contract_exists tests/test_scan_budget.py::test_batch75_placeholder_workflow_gate_native_audit_record_exists_and_tracks_contract`，10 passed。
- 类型检查：`uv run basedpyright`，0 errors、0 warnings、0 notes。
- 文档敏感路径/占位文案搜索：无匹配。
- Diff 空白检查：`git diff --check`，退出码 0。
- 本批按临时例外未跑全量 `uv run pytest`：本批未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程，也不是每 5 个编号批次后的全量节点。剩余风险是全仓其他测试未在本批重复执行；该风险由本批只新增静态保护测试、计划行和验收记录的低行为影响面约束。
- 本批未修改 Rust 原生代码。

## 审查处理

本批派发只读子代理审计普通占位符 workflow gate、quality report、write-back、doctor 和 workspace 相关入口。子代理结论与本地审计一致：主线 workflow gate 已经 native 化，`prepare-agent-workspace` 仍有旧 scanner manifest/草稿残留；并建议把保护从文件级收窄到函数级。本批已采纳该建议，主代理以本地静态测试、代码阅读和验证命令为最终依据。

## 剩余风险

本批只证明普通占位符 workflow gate 主线路径已经复用 native coverage builder，不迁移剩余旧 scanner：

- `prepare-agent-workspace` 仍用旧 scanner 生成候选 manifest 和普通占位符草稿。
- `build-placeholder-rules` 仍用旧 scanner 生成草稿、草稿预览覆盖统计和手动边界警告。
- workspace manifest 迁移后仍需要单独确认输出 JSON 形状、草稿输入和既有工作区校验行为不漂移。

## 下一批入口

建议下一批进入普通占位符 workspace manifest native 化：优先把 `prepare-agent-workspace` 的 `placeholder-candidates.json` 输出切到 `collect_native_placeholder_candidate_details`，并保留 `placeholder-rules.json` 草稿生成的旧 scanner 边界，避免一次性牵动 `build-placeholder-rules`。
