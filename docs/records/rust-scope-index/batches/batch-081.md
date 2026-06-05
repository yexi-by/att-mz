# Rust Scope/Index Engine 批次 6AX 验收记录

## 本批范围

本批是 P1-B 普通占位符阶段收束回顾，只新增阶段保护测试、计划索引和验收记录，不修改生产代码。

范围覆盖 6AN 到 6AW 的普通占位符支线迁移链：

- P1-B 普通占位符支线入口审计和四个公开命令的 scan budget。
- 普通占位符 Rust 候选入口与 `scan_placeholder_rule_candidates`。
- `scan-placeholder-candidates` 公开报告路径 native 明细化。
- `validate-placeholder-rules`、`build-placeholder-rules` 和 `import-placeholder-rules` 的普通占位符覆盖统计事实来源。
- `prepare-agent-workspace` 候选 manifest 与 `placeholder-rules.json` 草稿。
- workflow gate 普通占位符覆盖报告。
- 旧 Python `scan_placeholder_candidates`、`_build_custom_placeholder_rule_draft`、`_joined_text_boundary_markers` 的生产调用边界。

## 保护网

新增 `tests/test_scan_budget.py::test_batch81_placeholder_stage_records_cover_native_scan_and_closure`：

- 逐条确认 `docs/records/rust-scope-index/batches/batch-071.md` 到 `docs/records/rust-scope-index/batches/batch-080.md` 都存在，并且都被计划表链接。
- 固定 6AN 到 6AW 的代表性测试名、入口名和记录主题。
- 固定 `scan-placeholder-candidates`、`validate-placeholder-rules`、`build-placeholder-rules`、`import-placeholder-rules` 的 P1-B scan budget 仍以 `Rust scan_rule_candidates(placeholders)` 为事实来源，且不触发插件源码 AST 扫描。
- 确认 `app/` 生产代码没有旧 Python `scan_placeholder_candidates`、`_build_custom_placeholder_rule_draft` 和 `_joined_text_boundary_markers` 的直接调用。
- 确认属性调用只有 `app/cli/commands/rules.py` 通过 service 公开入口调用 `scan_placeholder_candidates`；旧 helper 属性调用路径为空。
- 确认 native adapter、Rust placeholders 分支、覆盖报告、扫描命令、工作区和 workflow gate 仍挂在 native 明细入口上。

新增 `tests/test_scan_budget.py::test_batch81_placeholder_stage_closure_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定阶段记录链、四个公开命令、关键 native 入口、旧入口边界搜索、全量 `uv run pytest` 和 `uv run basedpyright` 验证要求。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch81_placeholder_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch81_placeholder_stage_closure_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-081.md` 链接，以及 `docs/records/rust-scope-index/batches/batch-081.md` 尚不存在。

## 实现说明

本批只把已有迁移事实收束成阶段级可机读保护，不改变生产实现。

阶段记录链：

| 批次 | 主题 | 记录 |
| --- | --- | --- |
| 6AN | P1-B 普通占位符支线入口审计 | `docs/records/rust-scope-index/batches/batch-071.md` |
| 6AO | 普通占位符 Rust 候选入口最小契约 | `docs/records/rust-scope-index/batches/batch-072.md` |
| 6AP | 普通占位符扫描命令薄适配接入 | `docs/records/rust-scope-index/batches/batch-073.md` |
| 6AQ | 普通占位符覆盖报告 native 化 | `docs/records/rust-scope-index/batches/batch-074.md` |
| 6AR | 普通占位符 workflow gate native 化审计 | `docs/records/rust-scope-index/batches/batch-075.md` |
| 6AS | 普通占位符 workspace manifest native 化 | `docs/records/rust-scope-index/batches/batch-076.md` |
| 6AT | 普通占位符 workspace 草稿生成 native 化评估 | `docs/records/rust-scope-index/batches/batch-077.md` |
| 6AU | 普通占位符 build-placeholder-rules 草稿生成 native 化评估 | `docs/records/rust-scope-index/batches/batch-078.md` |
| 6AV | 普通占位符 build-placeholder-rules 预览/手动边界 native 化评估 | `docs/records/rust-scope-index/batches/batch-079.md` |
| 6AW | 普通占位符支线收束回归审计 | `docs/records/rust-scope-index/batches/batch-080.md` |

本阶段固定的公开命令：

- `scan-placeholder-candidates`
- `validate-placeholder-rules`
- `build-placeholder-rules`
- `import-placeholder-rules`

本阶段固定的关键入口：

- `build_native_placeholder_candidates_payload`
- `collect_native_placeholder_candidate_details`
- `count_uncovered_placeholder_candidate_details`
- `_build_custom_placeholder_rule_draft_from_details`
- `_joined_text_boundary_markers_from_details`
- `scan_placeholder_rule_candidates`

本阶段固定的关键目标测试：

- `test_scan_native_rule_candidates_scans_placeholder_control_codes`
- `test_scan_placeholder_candidates_uses_native_candidate_scan`
- `test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build`
- `test_scan_placeholder_candidates_marks_custom_rule_coverage`
- `test_normal_placeholder_coverage_result_uses_native_candidate_scan`
- `test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest`
- `test_build_placeholder_rules_uses_native_candidate_details_for_draft`
- `test_build_placeholder_rules_uses_native_details_for_preview_and_boundary`
- `test_batch80_placeholder_branch_closure_covers_native_entries`
- `test_batch80_placeholder_branch_closure_record_exists_and_tracks_contract`
- `test_batch81_placeholder_stage_records_cover_native_scan_and_closure`
- `test_batch81_placeholder_stage_closure_record_exists_and_tracks_contract`

## 旧路径收束

本阶段结论：普通占位符默认生产支线已经收束到 Rust `scan_rule_candidates(placeholders)` 候选入口和 native 明细适配。Python 保留公开 CLI/service 外壳、报告组装、规则导入事务、工作区 JSON 生成和 workflow gate 编排，不再把旧 Python `PlaceholderCandidate` scanner 作为生产事实来源。

旧入口边界搜索纳入本批验证。旧 `app/agent_toolkit/placeholder_scan.py`、`PlaceholderCandidate`、`count_uncovered_candidates`、`_build_custom_placeholder_rule_draft` 和 `_joined_text_boundary_markers` 仍作为历史名称、导出边界或旧测试语义存在；它们不是本阶段生产事实来源，后续是否删除应在单独批次评估。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自阶段保护固定的事实来源：

- 普通占位符候选扫描使用 `scan_native_rule_candidates` 与 `build_native_placeholder_candidates_payload`。
- 覆盖报告、扫描命令、workflow gate、工作区候选 manifest 和规则草稿使用 `collect_native_placeholder_candidate_details`。
- 覆盖统计使用 `count_uncovered_placeholder_candidate_details`。
- 草稿和手动边界统计使用 `_build_custom_placeholder_rule_draft_from_details` 与 `_joined_text_boundary_markers_from_details`。
- 阶段保护确认旧 Python scanner 和旧 helper 不再作为 `app/` 生产代码直接调用路径。

## 验证结果

本批属于 P1-B 普通占位符阶段收束，按临时验证策略执行全量 `uv run pytest`。

已执行：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch81_placeholder_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch81_placeholder_stage_closure_record_exists_and_tracks_contract
```

结果：2 passed。

```powershell
uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_marks_custom_rule_coverage tests/test_agent_toolkit_rule_import.py::test_normal_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_writes_native_placeholder_candidate_manifest tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_candidate_details_for_draft tests/test_agent_toolkit_manual_import.py::test_build_placeholder_rules_uses_native_details_for_preview_and_boundary
```

结果：8 passed。

```powershell
uv run pytest tests/test_scan_budget.py
```

结果：118 passed。

```powershell
uv run basedpyright
```

结果：0 errors，0 warnings，0 notes。

```powershell
uv run pytest
```

结果：893 passed in 255.50s。

文档敏感路径和占位文案搜索：无命中。

旧入口边界搜索：`service.scan_placeholder_candidates(` 只命中 `app/cli/commands/rules.py` 的公开 service 调用；`scan_placeholder_candidates(` 命中旧 scanner 定义、service 公开方法、common mixin 方法和 CLI service 调用；`._build_custom_placeholder_rule_draft(` 与 `._joined_text_boundary_markers(` 无命中。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理辅助复核 6AN 到 6AW 的记录链、关键入口、生产残留和下一批建议。子代理未修改文件、未运行长时间全量测试；其静态审计结论确认 batch 71 到 80 链路完整，公开入口保留但事实来源已经进入 native 明细和覆盖报告路径，batch-81 已补上阶段闭环以及 batch-80 只覆盖 71 到 79 记录正文的窄口。最终收束以本地测试和验证命令输出为准。

## 剩余风险

本批是阶段收束保护，不新增生产功能。旧普通占位符 scanner 模块和旧 helper 定义仍存在，部分测试仍直接绑定旧 scanner 语义；这些保留边界已经记录为历史名称和测试事实，不应被当成生产事实来源。后续若要删除旧导出或旧语义测试，需要单独批次建立 RED/GREEN 保护。

剩余 P1-B 命令仍包括结构化占位符、Note 标签、事件指令、插件参数、MV 虚拟名字框和源文残留规则链；这些支线不能复用普通占位符阶段结论作为完成证据，后续仍需逐支线建立入口审计、目标测试和旧路径收束记录。

## 下一批入口

建议下一批进入 P1-B 结构化占位符支线入口审计：先梳理 `validate-structured-placeholder-rules`、`import-structured-placeholder-rules` 和相关报告/工作区路径的现有事实来源、scan budget 和旧 Python 候选路径，再决定是否需要 Rust 候选入口或只做静态边界收束。
