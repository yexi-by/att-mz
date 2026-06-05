# Rust Scope/Index Engine 批次 6BM 验收记录

## 本批范围

本批是 Note 标签支线收束回归审计，只新增保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

范围覆盖 Note 标签支线 6BG 到 6BL 的迁移结果：

- `export-note-tag-candidates`、`validate-note-tag-rules` 和 `import-note-tag-rules` 三个公开命令的 scan_budget 分类和事实来源。
- Rust `scan_rule_candidates(note_tags)` 候选入口。
- `build_native_note_tag_candidates_payload` 和 `app/native_note_tag_scan.py` native helper。
- `app/note_tag_text/exporter.py::export_note_tag_candidates_file`。
- `AgentToolkitService.validate_note_tag_rules` 与 `AgentToolkitService.import_note_tag_rules`。
- 旧 `TranslationHandler.import_note_tag_rules` 和 common/workspace helper 保留边界。
- `count_note_tag_rule_candidates`、`note_tag_rule_scope_hash_for_text_rules`、`collect_note_tag_rule_hits` 和 `NoteTagTextExtraction` 的剩余 Python 扫描边界。

本批复核以下记录链：

- `docs/records/rust-scope-index/batches/batch-090.md`
- `docs/records/rust-scope-index/batches/batch-091.md`
- `docs/records/rust-scope-index/batches/batch-092.md`
- `docs/records/rust-scope-index/batches/batch-093.md`
- `docs/records/rust-scope-index/batches/batch-094.md`
- `docs/records/rust-scope-index/batches/batch-095.md`

## 保护网

新增 `tests/test_scan_budget.py::test_batch96_note_tag_branch_closure_covers_native_entries_and_remaining_boundaries`，固定以下事实：

- 计划表链接批次 90 到 96 的 Note 标签记录。
- 批次 90 到 95 的记录链覆盖入口审计、Rust 候选入口、扫描命令 native 薄适配、公开校验 native 接入、公开导入 native 接入和旧 handler/common 保留边界。
- `export-note-tag-candidates`、`validate-note-tag-rules` 和 `import-note-tag-rules` 都属于 P1-B，每个命令只保留一次候选扫描预算，插件源码 AST 扫描预算为 0，权威来源是 Rust `scan_rule_candidates(note_tags)`。
- `app/native_scope_index.py` 与 Rust scope index 已提供 `note_tags` 候选 payload 和 scan summary。
- `app/native_note_tag_scan.py` 通过 `collect_native_note_tag_candidate_details` 消费 `build_native_note_tag_candidates_payload` 和 `scan_native_rule_candidates`，并保留精确地图规则的 Python 来源校验边界。
- `export_note_tag_candidates_file`、`validate_note_tag_rules` 和 `import_note_tag_rules` 已进入 native helper。
- `TranslationHandler.import_note_tag_rules` 与 `_validate_note_tag_rules_with_context` 仍保留旧 `build_note_tag_rule_records_from_import`。
- `count_note_tag_rule_candidates`、`note_tag_rule_scope_hash_for_text_rules`、`collect_note_tag_rule_hits` 和 `NoteTagTextExtraction` 仍保留 `collect_note_tag_candidates`、`collect_note_tag_sources` 或 `iter_note_tag_matches`。
- Note 标签行为测试继续覆盖候选导出、公开校验、公开导入、精确地图规则、旧 handler 清理、空规则确认、workspace 缺规则、JSON 字符串协议和地图事件 Note 标签规则。

新增 `tests/test_scan_budget.py::test_batch96_note_tag_branch_closure_record_exists_and_tracks_contract`，固定本记录、计划表链接、验证命令、临时验证例外和下一批入口。

## 实现说明

本批没有改变 `app/` 或 `rust/` 生产实现。新增保护测试通过 AST 和文本记录审计当前事实来源：

- Note 标签候选明细由 `collect_native_note_tag_candidate_details` 生成。
- native helper 通过 `build_native_note_tag_candidates_payload` 组装 payload，并消费 Rust `scan_rule_candidates(note_tags)` 的 scan summary。
- `export-note-tag-candidates` 公开命令通过 `export_note_tag_candidates_file` 消费 native 候选明细。
- `validate-note-tag-rules` 和 `import-note-tag-rules` 公开命令通过 `build_note_tag_rule_records_from_native_candidates` 完成前置规则命中检查。
- 旧 handler/common、scope hash、text-scope rule hit 和实际提取路径仍按旧 Python 来源扫描保留。

## 旧路径收束

本批确认当前 Note 标签支线已迁 native 的公开入口包括：

- `export-note-tag-candidates`
- `validate-note-tag-rules`
- `import-note-tag-rules`

本批确认仍保留的旧 Python 扫描边界包括：

- `TranslationHandler.import_note_tag_rules`
- `app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context`
- `app/application/flow_gate.py::count_note_tag_rule_candidates`
- `app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules`
- `app/text_scope/rule_hits.py::collect_note_tag_rule_hits`
- `app/note_tag_text/extraction.py::NoteTagTextExtraction`
- `app/native_note_tag_scan.py` 中精确地图规则的 `_validate_note_tag_precise_source_hit`

这些路径不是本批删除对象。后续迁移必须分别证明空规则 hash、text-scope、工作区报告、写回预览、旧译文清理和精确地图规则语义不漂移。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

本批只补齐 Note 标签支线收束审计记录和计划索引，不改变用户可见命令行为。

## 性能证据

本批只新增静态保护和记录，不引入新的运行时扫描流程。性能相关证据来自保护测试：

- 三个公开 Note 标签命令的 scan_budget 固定为每个命令一次候选扫描。
- 三个公开 Note 标签命令的插件源码 AST 扫描预算固定为 0。
- 三个公开 Note 标签命令的权威来源固定为 Rust `scan_rule_candidates(note_tags)`。
- 当前公开导出、公开校验和公开导入入口通过 `collect_native_note_tag_candidate_details` 或 `build_note_tag_rule_records_from_native_candidates` 消费 native 候选事实来源。
- 剩余 Python 扫描边界被明确记录为后续迁移对象，而不是误记为已完成 native 迁移。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch96_note_tag_branch_closure_covers_native_entries_and_remaining_boundaries tests/test_scan_budget.py::test_batch96_note_tag_branch_closure_record_exists_and_tracks_contract`，2 failed。失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-096.md`、本批记录不存在。
- GREEN 目标测试和记录保护命令：`uv run pytest tests/test_scan_budget.py::test_batch96_note_tag_branch_closure_covers_native_entries_and_remaining_boundaries tests/test_scan_budget.py::test_batch96_note_tag_branch_closure_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_keeps_precise_map_file_scope tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_blocks_missing_note_tag_rules tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back`，7 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，14 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批未修改生产代码。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标测试、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批使用只读子代理辅助审计 Note 标签支线生产链路，主代理负责最终判断、记录和验证。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

本地结论是：Note 标签三条公开命令的前置候选事实来源已经进入 Rust `scan_rule_candidates(note_tags)`，但 scope hash、text-scope、workspace/common、旧 handler 和实际提取仍保留 Python 来源扫描。当前支线不能声明全部 Note 标签路径都已 native 化，只能声明公开导出/校验/导入入口已完成 native 接入。

## 剩余风险

本批是 Note 标签支线收束回归审计，不是 P1-B Note 标签阶段总回顾。下一批仍需决定是否继续迁移 `note_tag_rule_scope_hash_for_text_rules` 与 `collect_note_tag_rule_hits`，或把它们作为需要实际提取语义的长期保留边界。

本批未跑全量 `uv run pytest`，全仓其它非 Note 标签测试没有在本批重复验证。

## 下一批入口

建议下一批进入 Note 标签 scope hash/text-scope native 化评估：审计 `note_tag_rule_scope_hash_for_text_rules`、`count_note_tag_rule_candidates` 和 `collect_note_tag_rule_hits` 是否可以消费 native 候选或 SQLite 索引事实，并分别保护空规则确认 hash、text-scope rule hit 和实际提取语义不漂移。
