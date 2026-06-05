# Rust Scope/Index Engine 批次 6AY 验收记录

## 本批范围

本批是 P1-B 结构化占位符支线入口审计，只新增入口审计保护测试、计划索引和验收记录，本批未修改生产代码。

范围覆盖结构化占位符相关公开命令与当前事实来源：

- `validate-structured-placeholder-rules`
- `scan-structured-placeholder-candidates`
- `import-structured-placeholder-rules`
- `app/agent_toolkit/services/placeholder_rules.py` 的结构化占位符 service 方法。
- `app/agent_toolkit/services/common.py` 的结构化候选覆盖报告。
- `app/application/flow_gate.py` 的 workflow gate 结构化占位符覆盖结果。
- `app/agent_toolkit/services/workspace.py` 的工作区结构化占位符导出和校验路径。
- `app/native_scope_index.py`、`rust/src/native_core/scope_index/mod.rs` 和 `rust/src/native_core/controls.rs` 中当前 Rust 结构化占位符能力边界。

## 保护网

新增 `tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths`：

- 固定三个结构化占位符命令属于 P1-B，scan budget 的权威事实来源写为 `Rust scan_rule_candidates(structured_placeholders)`。
- 固定 CLI 命令仍通过 service 方法进入 `validate_structured_placeholder_rules`、`scan_structured_placeholder_candidates` 和 `import_structured_placeholder_rules`。
- 固定 service 方法当前仍会加载游戏正文、构建 `translation_data_map`，并调用 `_validate_structured_placeholder_rules_with_context`、`_build_structured_placeholder_coverage_report_with_context` 或 `build_structured_placeholder_coverage_result`。
- 固定 `app/agent_toolkit/services/common.py` 与 `app/application/flow_gate.py` 当前各自保留 `_iter_structured_shell_candidate_matches`、`_iter_translation_items_from_map` 和结构化候选收集逻辑。
- 固定 `prepare-agent-workspace` 会导出 `STRUCTURED_PLACEHOLDER_RULES_FILE_NAME`，`validate-agent-workspace` 会用 `_validate_workspace_structured_placeholder_rules` 和 `build_structured_placeholder_coverage_result` 复核工作区结构化规则。
- 固定 Rust 侧目前只在 `build_native_rule_candidate_text_rules_payload` 和 `controls.rs::iter_structured_placeholder_spans` 中承载结构化规则；尚没有 `build_native_structured_placeholder_candidates_payload` 或 `scan_structured_placeholder_rule_candidates`。
- 固定当前结构化占位符相关行为测试仍存在。
- 固定既有行为保护包括 `test_validate_structured_placeholder_rules_rejects_rust_incompatible_regex`、`test_import_structured_placeholder_rules_loads_translation_source_once` 和 `test_validate_agent_workspace_reuses_structured_placeholder_context`。

新增 `tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定入口审计范围、关键文件、当前缺口、验证命令和下一批入口。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-082.md` 链接，以及 `docs/records/rust-scope-index/batches/batch-082.md` 尚不存在。

## 实现说明

本批没有改变 `app/` 或 `rust/` 生产实现。入口审计结论如下：

| 事项 | 当前状态 | 批次判断 |
| --- | --- | --- |
| `validate-structured-placeholder-rules` | service 加载规则、必要时加载当前正文并用 Python 上下文校验样本 | 仍未消费 Rust structured 候选入口 |
| `scan-structured-placeholder-candidates` | service 加载当前正文后调用 `_build_structured_placeholder_coverage_report_with_context` | 覆盖扫描仍是 Python 候选事实来源 |
| `import-structured-placeholder-rules` | service 校验后调用 `build_structured_placeholder_coverage_result` 做导入前覆盖检查 | 导入前覆盖检查仍是 Python 候选事实来源 |
| `app/agent_toolkit/services/common.py` | `_collect_structured_placeholder_candidate_details` 遍历 `translation_data_map` 并用 `_iter_structured_shell_candidate_matches` 扫描 shell 候选 | 与 workflow gate 存在重复候选逻辑 |
| `app/application/flow_gate.py` | `collect_structured_placeholder_candidate_details` 也遍历 `translation_data_map` 并维护同名 shell 候选正则 | 与 service common 存在第二事实来源 |
| `app/agent_toolkit/services/workspace.py` | `prepare-agent-workspace` 导出结构化规则；`validate-agent-workspace` 复用 `_validate_workspace_structured_placeholder_rules` 和 `build_structured_placeholder_coverage_result` | 工作区校验仍依赖 Python 结构化候选扫描 |
| `app/native_scope_index.py` | 已把 `structured_placeholder_rules` 写进通用 rule candidate text rules payload | 只有规则输入序列化，没有 structured 候选 payload |
| `rust/src/native_core/controls.rs` | 已有 `iter_structured_placeholder_spans` 支持结构化规则匹配/冲突校验 | 可复用能力存在，但不是候选扫描分支 |
| `rust/src/native_core/scope_index/mod.rs` | 只携带 `structured_placeholder_rules`，没有 `structured_placeholders` scan summary | 下一批需要补最小 Rust 候选入口 |

## 旧路径收束

本批确认结构化占位符支线尚未进入旧路径收束阶段。当前旧路径不是历史残留，而是仍在生产使用的 Python 候选事实来源：

- `app/agent_toolkit/services/common.py::_collect_structured_placeholder_candidate_details`
- `app/agent_toolkit/services/common.py::_iter_structured_shell_candidate_matches`
- `app/application/flow_gate.py::collect_structured_placeholder_candidate_details`
- `app/application/flow_gate.py::_iter_structured_shell_candidate_matches`
- `app/agent_toolkit/services/workspace.py::validate_agent_workspace` 内的 `build_structured_placeholder_coverage_result`

本批不删除这些路径。下一批应先建立 Rust `scan_rule_candidates(structured_placeholders)` 最小契约，再逐步迁移 service 覆盖报告、workflow gate、workspace 和导入前覆盖检查。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

## 性能证据

本批只新增静态入口审计和记录，不引入新的运行时扫描流程。性能相关证据来自保护测试：

- scan budget 已要求 `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates` 和 `import-structured-placeholder-rules` 消费 `Rust scan_rule_candidates(structured_placeholders)`。
- 当前生产代码仍需要在 service 和 workflow gate 中用 Python 遍历 `translation_data_map` 扫描结构化 shell 候选。
- 工作区校验路径仍通过 Python `build_structured_placeholder_coverage_result` 扫描结构化候选。
- 当前 `app/native_scope_index.py` 和 Rust `scope_index` 尚未提供结构化占位符候选 payload 与 scan summary。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_record_exists_and_tracks_contract`，2 failed；失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-082.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_record_exists_and_tracks_contract`，2 passed。
- 相关结构化占位符行为回归：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_structured_placeholder_rules_rejects_rust_incompatible_regex tests/test_agent_toolkit_rule_import.py::test_import_structured_placeholder_rules_loads_translation_source_once tests/test_agent_toolkit_rule_import.py::test_import_empty_structured_placeholder_rules_confirms_uncovered_candidates tests/test_agent_toolkit_rule_import.py::test_import_empty_structured_placeholder_rules_uses_full_candidate_hash tests/test_agent_toolkit_rule_import.py::test_import_nonempty_structured_placeholder_rules_confirms_remaining_uncovered_candidates tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_candidate_review_rejects_legacy_sampled_hash tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_reuses_structured_placeholder_context tests/test_cli_json_output.py::test_structured_placeholder_rule_commands_accept_input_files tests/test_text_rules.py::test_structured_placeholder_rules_reject_python_only_regex_before_native_use tests/test_text_rules.py::test_structured_placeholder_rule_keeps_shell_and_translates_inner_text`，10 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "structured_placeholder"`，2 passed，118 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，最终无匹配。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批按补充分批策略未跑全量 `uv run pytest`。剩余风险是全仓其它非结构化占位符测试未在本批重复执行；本批只做入口审计和静态保护，没有修改生产代码。
- 本批未修改生产代码。

## 审查处理

本批使用只读子代理辅助复核结构化占位符公开命令、scan budget、当前事实来源和下一批建议。子代理未修改文件、未运行长时间全量测试；其静态审计结论确认 batch 81 的下一批入口已经指向本批，三条结构化占位符命令的预算权威来源均写为 `Rust scan_rule_candidates(structured_placeholders)`，但当前 `app/` 和 `rust/` 实现仍缺少结构化候选扫描分支，service、workflow gate 和 workspace 仍依赖 Python 候选扫描。最终收束以本地测试和验证命令输出为准。

## 剩余风险

当前结构化占位符预算目标和生产实现仍不一致：预算要求 `Rust scan_rule_candidates(structured_placeholders)`，生产实现仍在 Python service 和 workflow gate 中扫描候选。这个风险已经由本批记录和保护测试固定，下一批应进入 Rust 最小契约，不应直接跳到 service 迁移。

结构化占位符结论不能外推到 Note 标签、事件指令、插件参数、MV 虚拟名字框和源文残留规则链；这些 P1-B 支线仍需要各自的入口审计和目标测试。

## 下一批入口

建议下一批进入结构化占位符 Rust 候选入口最小契约：新增 `build_native_structured_placeholder_candidates_payload`、Rust `scan_structured_placeholder_rule_candidates` 或等价分支，并用最小行为测试固定 `scan_rule_candidates(structured_placeholders)` 能返回候选明细与覆盖统计。
