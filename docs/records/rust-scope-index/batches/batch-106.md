# Rust Scope/Index Engine 批次 6BW 验收记录

## 本批范围

本批是 P1-B Note 标签阶段收束回顾，只新增阶段保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

范围覆盖 6BG 到 6BV 的 Note 标签支线迁移链：

- P1-B Note 标签支线入口审计和三个公开命令的 scan budget。
- Note 标签 Rust 候选入口与 `Rust scan_rule_candidates(note_tags)`。
- `export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules` 的 native 候选事实接入。
- `note_tag_rule_scope_hash_for_text_rules` 与 `count_note_tag_rule_candidates` 的 native 候选摘要接入。
- `collect_note_tag_rule_hits` 的 native `hit_details` 明细接入。
- `NoteTagTextExtraction` 的 native `source_details` / `hit_details` 组合明细接入。
- 旧 Python `collect_note_tag_sources` 与 `iter_note_tag_matches` 的当前保留边界。

## 保护网

新增 `tests/test_scan_budget.py::test_batch106_note_tag_stage_records_cover_native_scan_and_closure`：

- 逐条确认 `docs/records/rust-scope-index/batches/batch-090.md` 到 `docs/records/rust-scope-index/batches/batch-105.md` 都存在，并且都被计划表链接。
- 固定 6BG 到 6BV 的代表性测试名、入口名和记录主题。
- 固定 `export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules` 的 P1-B scan budget 仍以 `Rust scan_rule_candidates(note_tags)` 为事实来源，且不触发插件源码 AST 扫描。
- 确认候选导出、规则校验、规则导入、scope hash/count、text-scope 和正文提取路径仍挂在 native 候选、native `hit_details`、native `source_details` 或组合 helper 上。
- 确认 `NoteTagTextExtraction.extract_all_text` 与 `collect_note_tag_rule_hits` 不再调用旧 Python `collect_note_tag_sources` 或 `iter_note_tag_matches`。
- 固定 `app/note_tag_text/importer.py::_validate_note_tag_rule_hit` 仍保留旧 Python 精确校验 helper 边界。

新增 `tests/test_scan_budget.py::test_batch106_note_tag_stage_closure_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定阶段记录链、三个公开命令、关键 native 入口、旧 helper 保留边界、验证命令、临时验证例外和下一批入口。

## 实现说明

本批只把已有迁移事实收束成阶段级可机读保护，不改变生产实现。

阶段记录链：

| 批次 | 主题 | 记录 |
| --- | --- | --- |
| 6BG | P1-B Note 标签支线入口审计 | `docs/records/rust-scope-index/batches/batch-090.md` |
| 6BH | Note 标签 Rust 候选入口最小契约 | `docs/records/rust-scope-index/batches/batch-091.md` |
| 6BI | Note 标签扫描命令 native 薄适配接入 | `docs/records/rust-scope-index/batches/batch-092.md` |
| 6BJ | Note 标签规则校验 native 候选接入 | `docs/records/rust-scope-index/batches/batch-093.md` |
| 6BK | Note 标签规则导入 native 候选接入 | `docs/records/rust-scope-index/batches/batch-094.md` |
| 6BL | Note 标签导入后旧 handler/common 收束评估 | `docs/records/rust-scope-index/batches/batch-095.md` |
| 6BM | Note 标签支线收束回归审计 | `docs/records/rust-scope-index/batches/batch-096.md` |
| 6BN | Note 标签 scope hash/text-scope native 化评估 | `docs/records/rust-scope-index/batches/batch-097.md` |
| 6BO | Note 标签 scope hash/count native 薄适配 | `docs/records/rust-scope-index/batches/batch-098.md` |
| 6BP | Note 标签 text-scope 逐命中 native 明细评估 | `docs/records/rust-scope-index/batches/batch-099.md` |
| 6BQ | Note 标签逐命中 Rust 明细最小契约 | `docs/records/rust-scope-index/batches/batch-100.md` |
| 6BR | Note 标签 text-scope native 明细替换评估 | `docs/records/rust-scope-index/batches/batch-101.md` |
| 6BS | Note 标签 text-scope native 明细薄适配 | `docs/records/rust-scope-index/batches/batch-102.md` |
| 6BT | NoteTagTextExtraction native 明细替换评估 | `docs/records/rust-scope-index/batches/batch-103.md` |
| 6BU | NoteTagTextExtraction native 来源存在契约补强 | `docs/records/rust-scope-index/batches/batch-104.md` |
| 6BV | NoteTagTextExtraction native 明细薄适配 | `docs/records/rust-scope-index/batches/batch-105.md` |

本阶段固定的公开命令：

- `export-note-tag-candidates`
- `validate-note-tag-rules`
- `import-note-tag-rules`

本阶段固定的关键入口：

- `build_native_note_tag_candidates_payload`
- `collect_native_note_tag_candidate_details`
- `build_note_tag_rule_records_from_native_candidates`
- `note_tag_rule_scope_hash_for_text_rules`
- `count_note_tag_rule_candidates`
- `collect_native_note_tag_hit_details`
- `collect_native_note_tag_source_details`
- `collect_native_note_tag_extraction_details`
- `collect_note_tag_rule_hits`
- `TextScopeRuleHit`
- `TextScopeService`
- `NoteTagTextExtraction`

本阶段固定的关键目标测试：

- `test_export_note_tag_candidates_uses_native_candidate_scan`
- `test_validate_note_tag_rules_uses_native_candidate_scan`
- `test_import_note_tag_rules_uses_native_candidate_scan`
- `test_note_tag_scope_hash_and_count_use_native_candidate_scan`
- `test_note_tag_rule_hits_use_native_details_without_python_note_scan`
- `test_note_tag_extraction_uses_native_details_without_python_note_scan`
- `test_note_tag_extraction_native_details_keep_duplicate_error_before_filter`
- `test_collect_native_note_tag_extraction_details_returns_sources_and_hits_once`
- `test_batch105_note_tag_extraction_native_detail_adapter_uses_combined_native_details`
- `test_batch106_note_tag_stage_records_cover_native_scan_and_closure`
- `test_batch106_note_tag_stage_closure_record_exists_and_tracks_contract`

## 旧路径收束

本阶段结论：Note 标签默认生产支线已经收束到 Rust `scan_rule_candidates(note_tags)` 候选入口和 native 明细适配。Python 保留公开 CLI/service 外壳、JSON 报告组装、规则导入事务、规则顺序筛选、错误文案和输出对象组装，不再把旧 Python Note 全量扫描作为候选导出、规则校验、规则导入、scope hash/count、text-scope 或正文提取的生产事实来源。

仍保留的旧 helper 边界：

- `app/note_tag_text/sources.py::collect_note_tag_sources`：保留为公共来源枚举 helper，内部已经通过 `collect_native_note_tag_sources` 获取来源摘要。
- `app/note_tag_text/parser.py::iter_note_tag_matches`：保留为 Note 标签 parser 和写回替换 helper 的基础工具。
- `app/note_tag_text/exporter.py::collect_note_tag_candidates`：保留为旧报告同形候选构造 helper，但公开导出路径 `export_note_tag_candidates_file` 已消费 `collect_native_note_tag_candidate_details`。
- `app/note_tag_text/importer.py::_validate_note_tag_rule_hit`：仍用于旧导入构造入口的精确 Python 校验边界；AgentToolkit 的规则校验和导入路径已经改用 `build_note_tag_rule_records_from_native_candidates`。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自阶段保护固定的事实来源：

- 三个 Note 标签公开规则命令的 scan budget 固定为每个命令一次候选扫描。
- 三个 Note 标签公开规则命令的插件源码 AST 扫描预算固定为 0。
- 三个 Note 标签公开规则命令的权威来源固定为 `Rust scan_rule_candidates(note_tags)`。
- text-scope 规则命中使用 `collect_native_note_tag_hit_details`，不再重复 Python `collect_note_tag_sources` 与 `iter_note_tag_matches`。
- `NoteTagTextExtraction.extract_all_text` 使用 `collect_native_note_tag_extraction_details` 一次取得 `source_details` 和 `hit_details`，不再分别触发两个 native helper 或重复 Python Note 扫描。

注意：当前 scan budget 固定的是公开命令的候选扫描预算，不等同于证明整条 `TextScopeService` 或工作区构建链路只有一次 Note native 扫描。跨消费者 native 结果复用仍属于下一批总收束审计范围。

## 验证结果

- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch106_note_tag_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch106_note_tag_stage_closure_record_exists_and_tracks_contract`，2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-106.md` 链接，以及 `docs/records/rust-scope-index/batches/batch-106.md` 尚不存在。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch106_note_tag_stage_records_cover_native_scan_and_closure tests/test_scan_budget.py::test_batch106_note_tag_stage_closure_record_exists_and_tracks_contract`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，34 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计 Note 标签阶段残留扫描边界，主代理负责最终判断、测试保护、记录和验证。子代理不修改文件。

审计重点包括候选导出、规则校验、规则导入、scope hash/count、text-scope、正文提取、旧 helper 导出和可能的重复 native 扫描。

子代理只读审计补充确认：`TextScopeService.build` 中正文提取与 `collect_note_tag_rule_hits` 可能分别触发 Note native 明细扫描；workflow gate / text index 还会额外消费 native 候选摘要。该发现已纳入剩余风险和下一批入口。

## 剩余风险

`collect_native_note_tag_candidate_details`、`collect_native_note_tag_hit_details`、`collect_native_note_tag_source_details` 与 `collect_native_note_tag_extraction_details` 仍是按使用场景拆分的 Python helper。当前已确认 `NoteTagTextExtraction` 使用组合 helper 避免两次 native 扫描；其他路径如 text-scope、workflow gate、text index 和候选导出各自触发 native 扫描，是否需要在更大一轮 `TextScopeService` 或工作区构建内复用同一个 Note 标签 native 结果，应放到后续 P1-B 总收束阶段评估。

空规则缺少更早短路也是剩余风险之一：如果调用链在没有 Note 标签规则时仍进入 native Note 扫描，可能产生不必要成本。该问题需要在 P1-B 总收束中和其他外部规则支线一起审计。

本批按临时例外未跑全量 `uv run pytest`，全仓非 Note 标签路径仍需在阶段总收束或最终提交前用全量测试确认。

## 下一批入口

建议下一批进入 P1-B 工作区和规则命令阶段总收束回顾：汇总插件源码、非标准 data、普通占位符、结构化占位符和 Note 标签各支线阶段结论，审计 P1-B 命令整体是否仍存在重复扫描、空规则未短路、旧 helper 生产事实来源或未记录的跨支线复用风险，重点评估跨消费者 native 结果复用。
