# Rust Scope/Index Engine 批次 6AN 验收记录

## 本批范围

本批是 P1-B 普通占位符支线入口审计，只新增静态保护测试、计划索引和验收记录，不修改生产代码。

范围覆盖四个普通占位符公开命令：

- `scan-placeholder-candidates`
- `validate-placeholder-rules`
- `build-placeholder-rules`
- `import-placeholder-rules`

目标是固定当前事实：scan budget 已要求这些命令以 `Rust scan_rule_candidates(placeholders)` 为目标事实来源，但当前生产链路仍由 Python `scan_placeholder_candidates`、`build_normal_placeholder_coverage_result`、`_build_placeholder_coverage_report_with_context` 和 `_validate_placeholder_rules_with_context` 承担候选扫描、覆盖统计、规则校验和草稿生成。当前 `rust/src/native_core/scope_index/placeholders.rs` 尚不存在，`scan_rule_candidates` 也没有普通占位符候选分支。

## 保护网

新增 `tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths`：

- 固定四个普通占位符命令都在 P1-B scan budget 中，并且目标事实来源是 `Rust scan_rule_candidates(placeholders)`。
- 固定 `app/agent_toolkit/placeholder_scan.py` 当前仍导出 `scan_placeholder_candidates`、`placeholder_candidates_to_details` 和 `count_uncovered_candidates`。
- 固定当前扫描函数仍调用 `iter_raw_control_sequence_candidates`、`TextRules.iter_control_sequence_spans`、`_iter_scan_texts` 和 `_find_covering_span`。
- 固定 `app/agent_toolkit/services/placeholder_rules.py` 四个公开方法当前分别消费 `_build_placeholder_coverage_report_with_context`、`_validate_placeholder_rules_with_context`、`build_normal_placeholder_coverage_result`、`scan_placeholder_candidates` 和 `_build_custom_placeholder_rule_draft`。
- 固定 `app/agent_toolkit/services/common.py`、`app/application/flow_gate.py` 和 `app/agent_toolkit/services/workspace.py` 仍以 Python placeholder coverage 为默认事实来源。
- 固定当前还没有 `rust/src/native_core/scope_index/placeholders.rs`、`scan_placeholder_rule_candidates` 或 native placeholder 行为测试。
- 固定既有行为测试覆盖候选扫描、规则校验、规则导入、规则草稿、工作区和 warm index gate。

新增 `tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定四个公开命令、当前 Python 事实来源、Rust 目标事实来源、Rust gap、既有行为测试和验证命令。

## 实现说明

本批不改生产代码，仅补充 6AN 入口审计保护。当前普通占位符事实来源矩阵如下：

| 链路 | scan budget 目标 | 当前生产入口 | 本批结论 |
| --- | --- | --- | --- |
| 候选扫描 | `Rust scan_rule_candidates(placeholders)` | `app/agent_toolkit/placeholder_scan.py::scan_placeholder_candidates` | 记录差距，下一批建立 Rust 候选入口 |
| 覆盖报告 | `Rust scan_rule_candidates(placeholders)` | `app/agent_toolkit/services/common.py::_build_placeholder_coverage_report_with_context` | 记录差距，下一批复用 Rust 候选 |
| 规则校验 | `Rust scan_rule_candidates(placeholders)` | `app/agent_toolkit/services/placeholder_rules.py::validate_placeholder_rules` 与 `_validate_placeholder_rules_with_context` | 记录差距，下一批评估样本预览和覆盖统计拆分 |
| 规则导入 | `Rust scan_rule_candidates(placeholders)` | `app/agent_toolkit/services/placeholder_rules.py::import_placeholder_rules` 调用 `build_normal_placeholder_coverage_result` | 记录差距，下一批复用 Rust 候选 |
| 规则草稿 | `Rust scan_rule_candidates(placeholders)` | `app/agent_toolkit/services/placeholder_rules.py::build_placeholder_rules` 调用 `scan_placeholder_candidates` 与 `_build_custom_placeholder_rule_draft` | 记录差距，下一批复用 Rust 候选 |
| 工作区 | `Rust scan_rule_candidates(placeholders)` | `app/agent_toolkit/services/workspace.py` 生成候选和校验覆盖 | 记录差距，后续与候选入口同批或后续批次接入 |
| workflow gate | `Rust scan_rule_candidates(placeholders)` | `app/application/flow_gate.py::build_normal_placeholder_coverage_result` | 记录差距，后续与候选入口同批或后续批次接入 |

## 旧路径收束

本批结论：普通占位符支线仍存在 Python 候选扫描和覆盖统计主路径。按照计划和 scan budget，下一步应先新增普通占位符 Rust/native 候选入口，再逐步让扫描、覆盖报告、规则校验、规则导入、规则草稿、工作区和 workflow gate 复用该候选事实。Python 后续应保留 CLI 编排、规则 JSON 解析、样本预览、草稿渲染和数据库事务。

## 外部契约变化

无 CLI 参数、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。本批只记录当前实现和下一批迁移边界。

## 性能证据

本批没有新增运行时扫描或数据库读取。性能证据来自静态入口审计：

- scan budget 已要求四个普通占位符命令以 `Rust scan_rule_candidates(placeholders)` 为事实来源。
- 当前生产链路仍由 Python 遍历 `translation_data_map` 原文行、识别控制符候选并计算覆盖统计。
- 当前 Rust `scan_rule_candidates` 没有普通占位符分支；下一批需要建立最小 native 候选契约。

本批固定的既有行为测试包括 `test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build`、`test_validate_placeholder_rules_blocks_translatable_text_loss`、`test_import_placeholder_rules_runs_validation_before_save`、`test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text` 和 `test_prepare_agent_workspace_includes_placeholder_rule_draft`。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_record_exists_and_tracks_contract`，2 failed；失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-071.md` 链接，以及本批记录不存在。
- GREEN：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_record_exists_and_tracks_contract`，2 passed。
- `uv run pytest tests/test_scan_budget.py`，98 passed。
- `uv run basedpyright`，0 errors，0 warnings，0 notes。
- 本批按临时例外未跑全量 `uv run pytest`：本批未修改生产代码、Rust 原生代码、跨模块契约、数据库 schema、CLI 外部契约或发布流程，也不是阶段收束。剩余风险是全仓其他测试未在本批重复执行；该风险由本批只新增静态保护和验收记录的低行为影响面约束。
- 文档敏感路径/占位文案搜索，无命中。
- `git diff --check`，通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批曾尝试派发只读子代理复核普通占位符入口，但收尾等待返回 `not_found`，未取得可用审计结果。最终收束只以本地静态审计、目标测试和验证命令输出为准。

## 剩余风险

本批是入口审计，不迁移生产逻辑。普通占位符扫描需要保留当前外部报告字段、规则安全预览、手动边界警告、empty-rule 审查哈希和工作区候选输出；下一批新增 Rust 候选入口时必须先用行为测试固定与当前 Python 候选扫描等价，再接入薄适配。

## 下一批入口

建议下一批进入普通占位符 Rust 候选入口最小契约：先为 `scan_rule_candidates(placeholders)` 建立 RED，要求 Rust/native 输入能基于当前 text index 或 translation_data_map 等价产出普通占位符候选明细，再让 Python bridge 暴露最小 payload builder。
