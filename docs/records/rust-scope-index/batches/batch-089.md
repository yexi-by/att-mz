# Rust Scope/Index Engine 批次 6BF 验收记录

## 本批范围

本批是 P1-B 结构化占位符阶段收束回顾，只新增阶段保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

范围覆盖 6AY 到 6BE 的结构化占位符支线迁移链：

- P1-B 结构化占位符支线入口审计和三个公开命令的 scan budget。
- 结构化占位符 Rust 候选入口与 `scan_rule_candidates(structured_placeholders)`。
- `scan-structured-placeholder-candidates` 公开报告路径 native helper 化。
- `validate-structured-placeholder-rules` 和 `import-structured-placeholder-rules` 的规则校验与覆盖统计事实来源。
- `build_native_structured_placeholder_candidates_payload`、`collect_native_structured_placeholder_candidate_details` 和 `count_uncovered_structured_placeholder_candidate_details`。
- `_build_structured_placeholder_coverage_report_with_context` 与 `build_structured_placeholder_coverage_result`。
- workflow gate、text index metadata、workspace validate、doctor、quality-report、audit-coverage 和 write-back 前置检查消费统一结构化覆盖事实。
- 旧 Python `collect_structured_placeholder_candidate_details`、`_collect_structured_placeholder_candidate_details`、`_iter_structured_shell_candidate_matches` 和 Python 侧 `STRUCTURED_SHELL_CANDIDATE_PATTERNS` 的当前生产边界。

本阶段记录链：

| 批次 | 主题 | 记录 |
| --- | --- | --- |
| 6AY | P1-B 结构化占位符支线入口审计 | `docs/records/rust-scope-index/batches/batch-082.md` |
| 6AZ | 结构化占位符 Rust 候选入口最小契约 | `docs/records/rust-scope-index/batches/batch-083.md` |
| 6BA | 结构化占位符扫描命令 native 薄适配接入 | `docs/records/rust-scope-index/batches/batch-084.md` |
| 6BB | 结构化占位符覆盖报告 native 化 | `docs/records/rust-scope-index/batches/batch-085.md` |
| 6BC | 结构化占位符 workflow gate native 化审计 | `docs/records/rust-scope-index/batches/batch-086.md` |
| 6BD | 结构化占位符旧 helper 删除或隔离评估 | `docs/records/rust-scope-index/batches/batch-087.md` |
| 6BE | 结构化占位符支线收束回归审计 | `docs/records/rust-scope-index/batches/batch-088.md` |

## 保护网

新增 `tests/test_scan_budget.py::test_batch89_structured_placeholder_stage_records_cover_native_scan_and_closure`：

- 逐条确认 `docs/records/rust-scope-index/batches/batch-082.md` 到 `docs/records/rust-scope-index/batches/batch-088.md` 都存在，并且都被计划表链接。
- 固定 6AY 到 6BE 的代表性测试名、入口名和记录主题。
- 固定 `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates`、`import-structured-placeholder-rules` 的 P1-B scan budget 仍以 Rust `scan_rule_candidates(structured_placeholders)` 为事实来源，且不触发插件源码 AST 扫描。
- 确认 `app/` 当前 Python 代码没有旧结构化候选 helper 标记。
- 确认 native adapter、Rust structured_placeholders 分支、覆盖报告、扫描命令、工作区、text index metadata 和 workflow gate 仍挂在 native 明细入口或统一 coverage builder 上。

新增 `tests/test_scan_budget.py::test_batch89_structured_placeholder_stage_closure_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定阶段记录链、三个公开命令、关键 native 入口、旧入口边界、验证命令、临时验证例外和下一批入口。

本阶段固定的关键目标测试：

- `test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules`
- `test_scan_native_rule_candidates_scans_structured_placeholder_candidates`
- `test_scan_structured_placeholder_candidates_uses_native_candidate_scan`
- `test_structured_placeholder_coverage_result_uses_native_candidate_scan`
- `test_translate_max_items_warm_index_uses_placeholder_gate_metadata`
- `test_validate_agent_workspace_reuses_structured_placeholder_context`
- `test_batch88_structured_placeholder_branch_closure_covers_native_entries`
- `test_batch88_structured_placeholder_branch_closure_record_exists_and_tracks_contract`
- `test_batch89_structured_placeholder_stage_records_cover_native_scan_and_closure`
- `test_batch89_structured_placeholder_stage_closure_record_exists_and_tracks_contract`

## 实现说明

本批只把已有迁移事实收束成阶段级可机读保护，不改变生产实现。

本阶段固定的公开命令：

- `validate-structured-placeholder-rules`
- `scan-structured-placeholder-candidates`
- `import-structured-placeholder-rules`

本阶段固定的关键入口：

- `build_native_structured_placeholder_candidates_payload`
- `collect_native_structured_placeholder_candidate_details`
- `count_uncovered_structured_placeholder_candidate_details`
- `_build_structured_placeholder_coverage_report_with_context`
- `build_structured_placeholder_coverage_result`
- `scan_rule_candidates(structured_placeholders)`

## 旧路径收束

本阶段结论：结构化占位符默认生产支线已经收束到 Rust `scan_rule_candidates(structured_placeholders)` 候选入口、native helper 和统一 coverage builder。Python 保留公开 CLI/service 外壳、报告组装、规则导入事务、样本预览和工作区 JSON 编排，不再把旧 Python 结构化 shell 候选扫描作为生产事实来源。

旧入口边界搜索纳入本批验证。当前 `app/` Python 代码中不应出现以下旧候选事实来源标记：

- `collect_structured_placeholder_candidate_details`
- `_collect_structured_placeholder_candidate_details`
- `_iter_structured_shell_candidate_matches`
- `STRUCTURED_SHELL_CANDIDATE_PATTERNS`

Rust 原生模块中的 `STRUCTURED_SHELL_CANDIDATE_PATTERNS` 属于当前 native structured_placeholders 分支，不是旧 Python helper。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自阶段保护固定的事实来源：

- 三个结构化占位符命令的 scan_budget 固定为每个命令一次候选扫描。
- 三个结构化占位符命令的插件源码 AST 扫描预算固定为 0。
- 三个结构化占位符命令的权威来源固定为 Rust `scan_rule_candidates(structured_placeholders)`。
- 结构化候选明细使用 `collect_native_structured_placeholder_candidate_details`。
- 覆盖统计使用 `count_uncovered_structured_placeholder_candidate_details`。
- 扫描报告使用 `_build_structured_placeholder_coverage_report_with_context`。
- 导入、workflow gate、text index metadata 和 workspace validate 使用 `build_structured_placeholder_coverage_result`。
- 阶段保护确认旧 Python 结构化候选 helper 不再留在 `app/` 生产代码中。

## 验证结果

RED：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch89_structured_placeholder_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch89_structured_placeholder_stage_closure_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-089.md` 链接，以及 `docs/records/rust-scope-index/batches/batch-089.md` 尚不存在。

本批目标测试：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch89_structured_placeholder_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch89_structured_placeholder_stage_closure_record_exists_and_tracks_contract
```

结果：2 passed。

相关结构化占位符行为回归：

```powershell
uv run pytest tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates tests/test_agent_toolkit_coverage.py::test_scan_structured_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_reuses_structured_placeholder_context
```

结果：6 passed。

相关 scan_budget/记录保护：

```powershell
uv run pytest tests/test_scan_budget.py -k "structured_placeholder"
```

结果：16 passed，118 deselected。

类型检查：

```powershell
uv run basedpyright
```

结果：0 errors，0 warnings，0 notes。

文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果 `NO_MATCH`。

```powershell
git diff --check
```

结果：exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。

本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非结构化占位符测试未在本批重复执行；本批用目标测试、相关结构化占位符行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批派发只读子代理辅助复核 6AY 到 6BE 的记录链、关键入口、旧 Python 事实来源残留和下一批建议。子代理不修改文件、不运行全量 pytest；最终收束以本地测试和验证命令输出为准。

子代理结论：6BF 可以成立，当前不建议继续迁移结构化占位符生产入口；生产入口已经收束到 native helper 和统一 coverage builder。子代理确认 `app/` 下未命中旧 Python 结构化候选事实来源标记，native payload builder、native helper、common coverage report、flow gate coverage builder 和 Rust structured_placeholders 分支仍是当前事实来源。下一批建议进入 `P1-B Note 标签支线入口审计`。

## 剩余风险

本批是阶段收束保护，不新增生产功能。剩余 P1-B 命令仍包括 Note 标签、事件指令、插件参数、MV 虚拟名字框和源文残留规则链；这些支线不能复用结构化占位符阶段结论作为完成证据，后续仍需逐支线建立入口审计、目标测试和旧路径收束记录。

## 下一批入口

建议下一批进入 P1-B Note 标签支线入口审计：先梳理 `export-note-tag-candidates`、`validate-note-tag-rules` 和 `import-note-tag-rules` 的现有事实来源、scan budget 和旧 Python 候选路径，再决定是否需要 Rust 候选入口或只做静态边界收束。
