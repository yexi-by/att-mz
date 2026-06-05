# Rust Scope/Index Engine 批次 6BN 验收记录

## 本批范围

本批是 Note 标签 scope hash/text-scope native 化评估，只新增保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

本批承接 `docs/records/rust-scope-index/batches/batch-096.md` 的剩余边界，审计以下入口是否适合继续 native 化：

- `count_note_tag_rule_candidates`
- `note_tag_rule_scope_hash_for_text_rules`
- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`
- `collect_note_tag_candidates`
- `collect_note_tag_sources`
- `iter_note_tag_matches`

## 保护网

新增 `tests/test_scan_budget.py::test_batch97_note_tag_scope_hash_text_scope_native_evaluation_tracks_boundaries`，固定以下事实：

- 计划表链接 `docs/records/rust-scope-index/batches/batch-097.md`，且批次 96 记录已经把本批列为下一批入口。
- `count_note_tag_rule_candidates` 当前通过 `collect_note_tag_candidates` 汇总 `translatable_hit_count`。
- `note_tag_rule_scope_hash_for_text_rules` 当前通过 `collect_note_tag_candidates` 和 `note_tag_rule_scope_hash_for_candidates` 计算空规则确认范围哈希。
- `collect_note_tag_candidates` 当前仍使用 `collect_note_tag_sources`、`iter_note_tag_matches` 和 `candidate_file_pattern` 构建候选摘要。
- `collect_native_note_tag_candidate_details` 返回的 native 候选摘要包含 `file_name`、`tag_name`、`hit_count`、`value_hit_count`、`translatable_hit_count`、`sample_locations` 和 `sample_values`，当前 native 候选摘要不包含逐命中 original_text/location_path。
- native 候选摘要由 `build_native_note_tag_candidates_payload` 组装输入，并通过 Rust `scan_rule_candidates(note_tags)` 返回。
- `collect_note_tag_rule_hits` 当前仍使用 `collect_note_tag_sources` 和 `iter_note_tag_matches` 展开 `TextScopeRuleHit`，并负责去重、文件模式匹配和可见文本规范化。
- `NoteTagTextExtraction` 当前仍使用 `collect_note_tag_sources` 和 `iter_note_tag_matches` 生成 `TranslationItem`，并负责过期规则检查、重复标签错误和可翻译文本筛选。

新增 `tests/test_scan_budget.py::test_batch97_note_tag_scope_hash_text_scope_evaluation_record_exists_and_tracks_contract`，固定本记录、验证命令、临时验证例外、评估结论和下一批入口。

本批同时确认现有行为测试继续覆盖：

- `test_workflow_gate_blocks_external_rule_hits_outside_writable_scope`
- `test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates`
- `test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup`
- `test_import_note_tag_rules_replaces_stale_existing_rule`
- `test_note_tag_rules_extract_and_write_back_only_target_values`
- `test_note_tag_extraction_rejects_stale_rule_without_current_tag`
- `test_note_tag_multiline_value_keeps_line_break_structure_before_write_back`
- `test_map_event_note_tag_rules_extract_and_write_back`
- `test_direct_write_back_rejects_missing_workflow_rules`
- `test_direct_rebuild_active_runtime_rejects_missing_workflow_rules`

## 实现说明

本批没有改变 `app/` 或 `rust/` 生产实现。结论如下：

- scope hash/count 可先迁移到 native 候选摘要。它们只依赖候选对象的计数字段和稳定排序后的候选集合，现有 `collect_native_note_tag_candidate_details` 已经提供 `hit_count`、`value_hit_count`、`translatable_hit_count`、`sample_locations` 和 `sample_values`。
- text-scope/实际提取需要逐命中明细。`collect_note_tag_rule_hits` 和 `NoteTagTextExtraction` 需要完整 `original_text`、唯一 `location_path`、逐标签重复检测、过期规则错误、可翻译文本筛选和 `TranslationItem` 构建语义，不能直接用当前 native 候选摘要替换；其中重复标签错误必须继续保留“标签重复，无法生成唯一定位路径”语义。
- 当前 native 候选摘要不包含逐命中 original_text/location_path，所以本批不把 text-scope 或实际提取标记为可直接迁移。

## 旧路径收束

本批确认可以作为下一批迁移入口的旧 Python 扫描边界：

- `count_note_tag_rule_candidates`
- `note_tag_rule_scope_hash_for_text_rules`
- `collect_note_tag_candidates`

本批确认需要更强 native 明细契约后再评估的旧 Python 扫描边界：

- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`
- `collect_note_tag_sources`
- `iter_note_tag_matches`

这些路径不是本批删除对象。下一批如果迁移 scope hash/count，必须保持 `note_tag_rule_scope_hash_for_candidates` 的哈希语义和空规则确认行为不漂移。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

本批只补齐 Note 标签 scope hash/text-scope native 化评估记录和计划索引，不改变用户可见命令行为。

## 性能证据

本批只新增静态保护和记录，不引入新的运行时扫描流程。性能相关结论如下：

- `count_note_tag_rule_candidates` 和 `note_tag_rule_scope_hash_for_text_rules` 当前仍会通过 `collect_note_tag_candidates` 展开 Note 标签来源并解析匹配。
- 这两个入口的输出只依赖候选摘要，适合作为 Note 标签 scope hash/count native 薄适配 的下一批入口。
- `collect_note_tag_rule_hits` 和 `NoteTagTextExtraction` 需要逐命中原文和唯一定位，当前 native 候选摘要不足以证明可替换。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch97_note_tag_scope_hash_text_scope_native_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch97_note_tag_scope_hash_text_scope_evaluation_record_exists_and_tracks_contract`，2 failed。失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-097.md`、本批记录不存在。
- GREEN 目标测试和记录保护命令：`uv run pytest tests/test_scan_budget.py::test_batch97_note_tag_scope_hash_text_scope_native_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch97_note_tag_scope_hash_text_scope_evaluation_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_workflow_gate_blocks_external_rule_hits_outside_writable_scope tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_replaces_stale_existing_rule tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_rejects_stale_rule_without_current_tag tests/test_rmmz_note_nonstandard_data.py::test_note_tag_multiline_value_keeps_line_break_structure_before_write_back tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back tests/test_rmmz_write_plan.py::test_direct_write_back_rejects_missing_workflow_rules tests/test_rmmz_write_plan.py::test_direct_rebuild_active_runtime_rejects_missing_workflow_rules`，10 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，16 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批未修改生产代码。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标测试、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批使用只读子代理辅助审计 Note 标签 scope hash 和 text-scope 边界，主代理负责最终判断、记录和验证。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

本地结论是：`count_note_tag_rule_candidates` 与 `note_tag_rule_scope_hash_for_text_rules` 可以进入 native 候选摘要薄适配评估；`collect_note_tag_rule_hits` 与 `NoteTagTextExtraction` 需要逐命中明细契约，不能直接消费当前 native 候选摘要。

只读子代理审计结论与本地结论一致，并补充确认：当前没有专门断言 `collect_note_tag_rule_hits` 输出内容的行为测试，因此下一次涉及 text-scope 迁移时必须先补逐命中行为测试，不能只依赖 scan_budget 结构保护。

## 剩余风险

本批是评估批次，不是 Note 标签 scope hash/count 的实现批次。下一批如果实际改造 `count_note_tag_rule_candidates` 和 `note_tag_rule_scope_hash_for_text_rules`，还需要补充行为测试，证明 native 候选摘要生成的候选集合与 `collect_note_tag_candidates` 的哈希输入等价。

本批未跑全量 `uv run pytest`，全仓其它非 Note 标签测试没有在本批重复验证。

## 下一批入口

建议下一批进入 Note 标签 scope hash/count native 薄适配：让 `count_note_tag_rule_candidates` 与 `note_tag_rule_scope_hash_for_text_rules` 消费 `collect_native_note_tag_candidate_details`，同时固定 `note_tag_rule_scope_hash_for_candidates` 的输入等价性和空规则确认行为。
