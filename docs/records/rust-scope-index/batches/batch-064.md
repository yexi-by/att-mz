# Rust Scope/Index Engine 批次 6AG 验收记录

## 本批范围

本批是 P1-B 非标准 data 支线入口审计，只新增静态保护测试、计划索引和验收记录，不修改生产代码。

范围覆盖四个公开命令：

- `scan-nonstandard-data`
- `export-nonstandard-data-json`
- `validate-nonstandard-data-rules`
- `import-nonstandard-data-rules`

范围也覆盖这些生产入口：

- `app/nonstandard_data/scanner.py`
- `app/agent_toolkit/services/nonstandard_data.py`
- `app/agent_toolkit/services/workspace.py`
- `app/application/flow_gate.py`

## 保护网

新增 `tests/test_scan_budget.py::test_batch64_nonstandard_data_entry_audit_classifies_current_python_scan_paths`：

- 固定 scan budget 对四个非标准 data 命令的目标事实来源为 `Rust scan_rule_candidates(nonstandard_data)`。
- 固定当前 `app/nonstandard_data/scanner.py` 仍公开 `build_nonstandard_data_scan`、`build_nonstandard_data_candidates_payload`、`load_nonstandard_data_files` 和 `resolve_nonstandard_data_leaves`。
- 固定当前 scanner 仍由 Python 加载非标准 JSON、递归展开叶子和递归筛选候选，尚未接入 `scan_native_rule_candidates`。
- 固定 AgentToolkit 四个非标准 data 命令、工作区准备/验收和 workflow gate 当前都直接消费 `build_nonstandard_data_scan`。
- 固定现有 `tests/test_nonstandard_data.py` 行为覆盖：扫描、导出、工作区、规则校验、规则导入、workflow gate、text scope、write-back 和 active runtime 审计。

新增 `tests/test_scan_budget.py::test_batch64_nonstandard_data_entry_audit_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定本批必须记录当前 Python 主路径、scan budget 的 Rust 目标事实来源、目标行为测试和下一批边界。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch64_nonstandard_data_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch64_nonstandard_data_entry_audit_record_exists_and_tracks_contract
```

结果：入口矩阵保护通过，记录保护因 `docs/records/rust-scope-index/batches/batch-064.md` 尚未存在失败。

## 实现说明

本批没有改变 `app/` 生产实现。新增保护测试把计划中的目标状态和当前实现状态同时固定下来：

| 业务结论 | 目标事实来源 | 当前生产入口 | 本批处理 |
| --- | --- | --- | --- |
| 非标准 data 候选扫描 | `Rust scan_rule_candidates(nonstandard_data)` | `app/nonstandard_data/scanner.py::build_nonstandard_data_scan` | 记录差距，下一批建立 Rust 候选入口 |
| 非标准 data 工作区导出 | `Rust scan_rule_candidates(nonstandard_data)` | `app/agent_toolkit/services/nonstandard_data.py::export_nonstandard_data_json` 调用当前 scan | 记录差距，下一批复用候选入口 |
| 非标准 data 规则校验 | `Rust scan_rule_candidates(nonstandard_data)` | `app/agent_toolkit/services/nonstandard_data.py::validate_nonstandard_data_rules` 调用当前 scan | 记录差距，下一批复用候选入口 |
| 非标准 data 规则导入 | `Rust scan_rule_candidates(nonstandard_data)` | `app/agent_toolkit/services/nonstandard_data.py::import_nonstandard_data_rules` 调用当前 scan | 记录差距，下一批复用候选入口 |
| 工作区和 workflow gate | `Rust scan_rule_candidates(nonstandard_data)` | `workspace.py` 与 `flow_gate.py` 调用当前 scan | 记录差距，后续接入同一候选事实 |

现有行为保护测试：

- `test_nonstandard_data_scan_reports_high_risk_candidates`
- `test_nonstandard_data_agent_exports_candidates_and_sources`
- `test_prepare_agent_workspace_exports_nonstandard_data_branch`
- `test_validate_agent_workspace_blocks_empty_nonstandard_data_review`
- `test_nonstandard_data_rules_validate_full_classification`
- `test_nonstandard_data_rules_import_persists_records`
- `test_nonstandard_data_workflow_gate_blocks_until_rules_imported`
- `test_nonstandard_data_rules_enter_unified_text_scope`
- `test_nonstandard_data_write_back_updates_managed_json_leaf`
- `test_active_runtime_audit_reports_nonstandard_data_source_residual`
- `test_batch64_nonstandard_data_entry_audit_classifies_current_python_scan_paths`
- `test_batch64_nonstandard_data_entry_audit_record_exists_and_tracks_contract`

## 旧路径收束

本批结论：非标准 data 支线仍存在 Python 主扫描路径，且该路径会遍历非标准 JSON 文件、展开叶子并筛选候选。按照计划和 scan budget，下一步应把候选扫描迁入 Rust 统一入口，Python 只保留报告渲染、工作区导出和数据库事务编排。

本批没有删除旧路径；删除或薄适配应在 Rust 候选入口具备行为保护后推进。

## 外部契约变化

无外部 CLI 参数、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取。性能证据是静态审计：

- scan budget 已要求四个非标准 data 命令以 `Rust scan_rule_candidates(nonstandard_data)` 为权威事实来源。
- 当前生产实现仍通过 `build_nonstandard_data_scan` 在 Python 中读取、解析和递归扫描非标准 JSON。
- 下一批需要用动态行为测试证明 Rust 候选入口保持现有候选、报告字段和规则覆盖语义。

## 验证结果

本批属于普通编号批次，未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程；按临时验证策略不强制执行全量 `uv run pytest`。

本批按临时例外未跑全量 pytest。

已执行：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch64_nonstandard_data_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch64_nonstandard_data_entry_audit_record_exists_and_tracks_contract
```

结果：2 passed。

```powershell
uv run pytest tests/test_nonstandard_data.py::test_nonstandard_data_scan_reports_high_risk_candidates tests/test_nonstandard_data.py::test_nonstandard_data_agent_exports_candidates_and_sources tests/test_nonstandard_data.py::test_prepare_agent_workspace_exports_nonstandard_data_branch tests/test_nonstandard_data.py::test_validate_agent_workspace_blocks_empty_nonstandard_data_review tests/test_nonstandard_data.py::test_nonstandard_data_rules_validate_full_classification tests/test_nonstandard_data.py::test_nonstandard_data_rules_import_persists_records tests/test_nonstandard_data.py::test_nonstandard_data_workflow_gate_blocks_until_rules_imported tests/test_nonstandard_data.py::test_nonstandard_data_rules_enter_unified_text_scope tests/test_nonstandard_data.py::test_nonstandard_data_write_back_updates_managed_json_leaf tests/test_nonstandard_data.py::test_active_runtime_audit_reports_nonstandard_data_source_residual
```

结果：10 passed。

```powershell
uv run pytest tests/test_scan_budget.py
```

结果：84 passed。

```powershell
uv run basedpyright
```

结果：0 errors, 0 warnings, 0 notes。

文档敏感路径和占位文案搜索：无命中。

非标准 data 入口搜索：命中当前 `build_nonstandard_data_scan` 生产调用点、四个非标准 data CLI 命令、scan budget 的 Rust 目标事实来源和本批保护测试；结果与本批审计矩阵一致。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理辅助复核非标准 data 生产入口、测试分布和下一批建议；最终收束以本地测试和验证命令输出为准。子代理复核结论与本批保护网一致：当前默认事实来源仍是 `build_nonstandard_data_scan`，`scan_native_rule_candidates` 尚未接入非标准 data 输入，下一批应先建立 Rust/native 候选入口的等价行为保护。

## 剩余风险

非标准 data 候选扫描尚未迁入 Rust；当前 `build_nonstandard_data_scan` 仍是公开命令、工作区和 workflow gate 的默认事实来源。下一批修改生产代码后，需要执行全量 pytest，并按 Rust 改动要求补充 Rust 门禁。

## 下一批入口

建议下一批进入非标准 data Rust 候选入口最小契约：先为 `scan-nonstandard-data` 建立 RED，要求新 Rust/native 候选入口输出与当前 Python 候选扫描等价，再接入薄适配。
