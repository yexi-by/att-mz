# Rust Scope/Index Engine 批次 6AM 验收记录

## 本批范围

本批是 P1-B 非标准 data 阶段收束回顾，只新增阶段保护测试、计划索引和验收记录，不修改生产代码。

范围覆盖 6AG 到 6AL 的非标准 data 支线迁移链：

- P1-B 非标准 data 支线入口审计和四个公开命令的 scan budget。
- 非标准 data 候选扫描 Rust 入口和 `build_native_nonstandard_data_candidates_payload`。
- 规则校验覆盖统计 native 化和 `nonstandard_data_rule_coverage`。
- 已导入规则提取、写回提取、active runtime audit 的 native leaves 复用。
- text-scope 一轮构建内的 `NonstandardDataTextExtractionContext` 复用。
- 旧 Python `resolve_nonstandard_data_leaves`、`_walk_json_value` 和候选 walker 的生产残留删除。

## 保护网

新增 `tests/test_scan_budget.py::test_batch70_nonstandard_data_stage_records_cover_native_scan_and_closure`：

- 逐条确认 `docs/records/rust-scope-index/batches/batch-064.md` 到 `docs/records/rust-scope-index/batches/batch-069.md` 都存在，并且都被计划表链接。
- 固定 6AG 到 6AL 的代表性测试名、入口名和记录主题。
- 固定 `scan-nonstandard-data`、`export-nonstandard-data-json`、`validate-nonstandard-data-rules`、`import-nonstandard-data-rules` 的 P1-B scan budget 仍以 `Rust scan_rule_candidates(nonstandard_data)` 为事实来源，且不触发插件源码 AST 扫描。
- 确认 `app/` 生产代码没有 `resolve_nonstandard_data_leaves`、`_walk_json_value`、`_walk_candidates`、`_iter_candidates_from_file`、`_is_structural_nonstandard_string` 或 `STRUCTURAL_FIELD_NAMES` 残留。
- 确认 scanner、rules、extraction、runtime audit、text-scope 和 Rust nonstandard_data 分支仍挂在 native 候选、native coverage、native leaves 和 context 复用入口上。

新增 `tests/test_scan_budget.py::test_batch70_nonstandard_data_stage_closure_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定阶段记录链、四个公开命令、关键 native 入口、关键目标测试、全量 `uv run pytest` 和 `uv run basedpyright` 验证要求。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch70_nonstandard_data_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch70_nonstandard_data_stage_closure_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-070.md` 链接，以及 `docs/records/rust-scope-index/batches/batch-070.md` 尚不存在。

## 实现说明

本批只把已有迁移事实收束成阶段级可机读保护，不改变生产实现。

阶段记录链：

| 批次 | 主题 | 记录 |
| --- | --- | --- |
| 6AG | P1-B 非标准 data 支线入口审计 | `docs/records/rust-scope-index/batches/batch-064.md` |
| 6AH | 非标准 data Rust 候选入口最小契约 | `docs/records/rust-scope-index/batches/batch-065.md` |
| 6AI | 非标准 data 规则校验覆盖统计 native 化 | `docs/records/rust-scope-index/batches/batch-066.md` |
| 6AJ | 非标准 data 已导入规则提取链路 native leaves 复用 | `docs/records/rust-scope-index/batches/batch-067.md` |
| 6AK | 非标准 data 已导入规则链路重复 native leaves 扫描收束审计 | `docs/records/rust-scope-index/batches/batch-068.md` |
| 6AL | 非标准 data 支线收束回归审计 | `docs/records/rust-scope-index/batches/batch-069.md` |

本阶段固定的公开命令：

- `scan-nonstandard-data`
- `export-nonstandard-data-json`
- `validate-nonstandard-data-rules`
- `import-nonstandard-data-rules`

本阶段固定的关键入口：

- `build_native_nonstandard_data_candidates_payload`
- `build_native_nonstandard_data_leaves_payload`
- `nonstandard_data_rule_coverage`
- `scan_nonstandard_data_rule_candidates`
- `scan_nonstandard_data_rule_coverage`
- `scan_nonstandard_data_file_leaves`
- `NonstandardDataTextExtractionContext`
- `resolve_nonstandard_data_file_leaves_native`

本阶段固定的关键目标测试：

- `test_scan_native_rule_candidates_scans_nonstandard_data_files`
- `test_nonstandard_data_scan_uses_native_candidate_scan`
- `test_scan_native_rule_candidates_evaluates_nonstandard_data_rule_coverage`
- `test_nonstandard_data_rules_validate_uses_native_rule_coverage`
- `test_scan_native_rule_candidates_returns_nonstandard_data_leaves`
- `test_nonstandard_data_text_scope_uses_native_leaves_for_imported_rules`
- `test_nonstandard_data_write_back_extraction_uses_native_leaves`
- `test_active_runtime_audit_uses_native_nonstandard_data_leaves`
- `test_nonstandard_data_text_scope_reuses_native_leaves_within_build`
- `test_batch70_nonstandard_data_stage_records_cover_native_scan_and_closure`
- `test_batch70_nonstandard_data_stage_closure_record_exists_and_tracks_contract`

## 旧路径收束

本阶段结论：非标准 data 默认生产支线已经收束到 Rust `scan_rule_candidates(nonstandard_data)` 候选入口、Rust `nonstandard_data_rule_coverage` 覆盖统计入口和 Rust `nonstandard_data_leaves` 叶子展开入口。Python 保留文件 I/O、公开 dataclass/JSON 报告组装、规则导入事务和 text-scope 编排，不再承担非标准 data 大规模候选筛选或叶子递归枚举事实来源。

旧入口边界搜索纳入本批验证。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自阶段保护固定的事实来源：

- 非标准 data 候选扫描和工作区 JSON 导出使用 `scan_native_rule_candidates` 与 `build_native_nonstandard_data_candidates_payload`。
- 非标准 data 规则校验和导入前覆盖检查使用 `nonstandard_data_rule_coverage`。
- 已导入规则提取、写回提取和 active runtime audit 使用 `resolve_nonstandard_data_file_leaves_native`。
- text-scope 一轮构建内复用 `NonstandardDataTextExtractionContext`，避免同一轮 freshness check、正文提取和规则命中诊断重复展开 leaves。
- 阶段保护确认旧 Python leaf resolver 和旧候选 walker 不再留在 `app/` 生产代码中。

## 验证结果

本批属于 P1-B 非标准 data 阶段收束，按临时验证策略执行全量 `uv run pytest`。

已执行：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch70_nonstandard_data_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch70_nonstandard_data_stage_closure_record_exists_and_tracks_contract
```

结果：2 passed。

```powershell
uv run pytest tests/test_nonstandard_data.py tests/test_scan_budget.py
```

结果：119 passed。

```powershell
uv run basedpyright
```

结果：0 errors, 0 warnings, 0 notes。

```powershell
uv run pytest
```

结果：865 passed。

文档敏感路径和占位文案搜索：无命中。

旧入口边界搜索：覆盖 `resolve_nonstandard_data_leaves`、`_walk_json_value`、`_walk_candidates`、`_iter_candidates_from_file`、`_is_structural_nonstandard_string` 和 `STRUCTURAL_FIELD_NAMES`，生产目录无命中。repo 旧名称搜索仍命中历史记录和保护测试；这些命中属于允许的历史和测试保护范围。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理辅助复核 6AG 到 6AL 的记录链、关键入口、生产残留和下一批建议。子代理未修改文件；最终收束以本地测试和验证命令输出为准。

## 剩余风险

本批是阶段收束保护，不新增生产功能。剩余 P1-B 命令仍包括普通占位符、结构化占位符、Note 标签、事件指令、插件参数、MV 虚拟名字框和源文残留规则链；这些支线不能复用非标准 data 阶段结论作为完成证据，后续仍需逐支线建立入口审计、目标测试和旧路径收束记录。

## 下一批入口

建议下一批进入 P1-B 普通占位符支线入口审计：先梳理 `scan-placeholder-candidates`、`validate-placeholder-rules`、`build-placeholder-rules` 和 `import-placeholder-rules` 的现有事实来源、scan budget 和旧 Python 候选路径，再决定是否需要 Rust 候选入口或只做静态边界收束。
