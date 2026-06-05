# Rust Scope/Index Engine 批次 6BV 验收记录

## 本批范围

本批是 NoteTagTextExtraction native 明细薄适配，承接 `docs/records/rust-scope-index/batches/batch-104.md`，把 `NoteTagTextExtraction.extract_all_text` 的来源扫描和标签逐命中解析切到同一次 native 扫描返回的 `source_details` 与 `hit_details`。本批修改生产 Python 代码，本批未修改 Rust 原生代码。

本批不修改 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill 或发布流程。

## 保护网

新增和调整以下测试：

- `tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_uses_native_details_without_python_note_scan`：固定正文提取只调用一次 `collect_native_note_tag_extraction_details`，不再调用 Python `collect_note_tag_sources` 或 `iter_note_tag_matches`，并保持 `TranslationData` / `TranslationItem` 输出、规则标签顺序、不可翻译过滤和 Map 文件模式行为。
- `tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_native_details_keep_duplicate_error_before_filter`：固定重复标签错误先于不可翻译过滤，即使重复值都不可翻译也必须报出 `标签重复`。
- `tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_returns_sources_and_hits_once`：固定组合 helper 通过同一次 native 扫描返回 `source_details` 与 `hit_details`。
- `tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_requires_both_detail_lists`：固定旧 native 扩展或缺字段结果不能静默降级，缺少任一明细字段都必须显式要求重建 native 扩展。
- `tests/test_scan_budget.py::test_batch105_note_tag_extraction_native_detail_adapter_uses_combined_native_details` 和 `tests/test_scan_budget.py::test_batch105_note_tag_extraction_native_detail_adapter_record_exists_and_tracks_contract`：固定计划索引、验收记录、组合 helper、旧 Python 扫描收束和下一批入口。

## 实现说明

`app/native_note_tag_scan.py` 新增 `collect_native_note_tag_extraction_details`。该 helper 直接调用 `build_native_note_tag_candidates_payload` 与 `scan_native_rule_candidates`，从同一个 `scan_summary["note_tags"]` 中读取并规范化：

- `source_details`
- `hit_details`

缺少 `source_details` 或 `hit_details` 时，helper 会抛出 `RuntimeError`，提示重新构建 Rust 原生扩展，避免旧 native 契约把来源或命中事实静默降级为空。

`app/note_tag_text/extraction.py` 的 `NoteTagTextExtraction.extract_all_text` 改为：

- 用 `source_details` 还原来源顺序和文件模式级过期规则检查；
- 用 `hit_details` 按真实 `file_name`、`location_prefix` 和 `tag_name` 建立逐命中明细表；
- 继续按 `rule_records` 顺序、`matching_sources` 顺序和 `rule_record.tag_names` 顺序生成输出；
- 继续用 `tag_hit_counts` 在不可翻译过滤之前统计标签级命中；
- 继续用 `seen_location_paths` 保持跨规则定位去重；
- 继续构造 `TranslationData(display_name=None)` 与 `TranslationItem(item_type="short_text")`。

native `hit_details.original_text` 已经按本项目可见文本协议和 `TextRules.normalize_extraction_text` 规范化，native `hit_details.translatable` 已经完成 `should_translate_source_text` 判断，因此本批生产提取路径不再调用 Python `normalize_visible_text_for_extraction`。

## 旧路径收束

本批收束 `NoteTagTextExtraction.extract_all_text` 中的旧 Python Note 扫描路径。该函数不再调用：

- `collect_note_tag_sources`
- `iter_note_tag_matches`

保留的 Python 逻辑只负责规则顺序、来源筛选、重复标签错误、不可翻译过滤、过期规则检查和输出对象组装。

`collect_native_note_tag_source_details` 与 `collect_native_note_tag_hit_details` 继续作为已有单项 helper 保留，供候选、text-scope、审计测试和其他路径使用。本批生产提取路径使用新的组合 helper，避免分别调用这两个 helper 造成两次 native 扫描。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill 或发布流程变化。

native JSON 契约版本不变，仍沿用上一批提升后的 `NATIVE_CONTRACT_VERSION = 7`。本批只新增 Python 组合 helper 并改造生产提取路径，不修改 Rust 输出结构。

## 性能证据

本批把 `NoteTagTextExtraction.extract_all_text` 的来源存在扫描和标签逐命中解析收束为同一次 native Note 标签扫描：

- `source_details` 负责文件模式级 `matching_sources` 判断；
- `hit_details` 负责标签值命中、重复标签错误、不可翻译过滤和输出组装；
- 不再在正文提取路径重复执行 Python `collect_note_tag_sources` 与 `iter_note_tag_matches`。

目标行为测试通过 `native_call_count == 1` 固定组合 helper 只被调用一次。适配层测试通过 fake native 模块固定 `collect_native_note_tag_extraction_details` 只触发一次 `scan_rule_candidates(note_tags)`。

## 验证结果

- RED 正文提取行为：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_uses_native_details_without_python_note_scan tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_native_details_keep_duplicate_error_before_filter`，2 failed。失败点是旧实现仍调用 Python `collect_note_tag_sources`。
- RED 组合 helper 行为：`uv run pytest tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_returns_sources_and_hits_once tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_requires_both_detail_lists`，2 failed。失败点是 `collect_native_note_tag_extraction_details` 尚不存在。
- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch105_note_tag_extraction_native_detail_adapter_uses_combined_native_details tests/test_scan_budget.py::test_batch105_note_tag_extraction_native_detail_adapter_record_exists_and_tracks_contract`，2 failed。失败点是计划缺少 `docs/records/rust-scope-index/batches/batch-105.md`，本批记录不存在。
- GREEN 正文提取行为：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_uses_native_details_without_python_note_scan tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_native_details_keep_duplicate_error_before_filter`，2 passed。
- GREEN 组合 helper 行为：`uv run pytest tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_returns_sources_and_hits_once tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_requires_both_detail_lists`，2 passed。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch105_note_tag_extraction_native_detail_adapter_uses_combined_native_details tests/test_scan_budget.py::test_batch105_note_tag_extraction_native_detail_adapter_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_rejects_stale_rule_without_current_tag tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_successful_note_tag_extraction tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_expose_duplicate_locations_for_extraction_error tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_source_details_prove_matching_sources_without_value_hits tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_uses_native_details_without_python_note_scan tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_native_details_keep_duplicate_error_before_filter tests/test_rmmz_note_nonstandard_data.py::test_note_tag_multiline_value_keeps_line_break_structure_before_write_back tests/test_rmmz_note_nonstandard_data.py::test_note_tag_json_string_leaf_uses_visible_text_protocol tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back`，10 passed。
- 相关 native helper / scope 回归：`uv run pytest tests/test_native_adapters.py::test_collect_native_note_tag_source_details_returns_source_summary tests/test_native_adapters.py::test_collect_native_note_tag_source_details_requires_source_details tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_returns_sources_and_hits_once tests/test_native_adapters.py::test_collect_native_note_tag_extraction_details_requires_both_detail_lists tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_full_note_tag_hit_details tests/test_native_scope_index.py::test_collect_native_note_tag_hit_details_returns_full_native_note_hits tests/test_native_scope_index.py::test_collect_native_note_tag_source_details_returns_native_note_sources`，8 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，32 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计旧 `NoteTagTextExtraction.extract_all_text` 语义，主代理负责最终实现、验证和记录。子代理不修改文件。

审计结论与本批实现一致：文件模式级过期规则必须由 `source_details` 证明；标签级过期、重复标签错误、不可翻译过滤和输出组装必须由 `hit_details` 证明；重复标签错误必须先于不可翻译过滤；输出顺序必须保持 `rule_records` -> `matching_sources` -> `tag_names`。

## 剩余风险

本批只收束 `NoteTagTextExtraction.extract_all_text` 的正文提取扫描路径。`collect_native_note_tag_source_details` 与 `collect_native_note_tag_hit_details` 仍作为单项 helper 存在，其他路径如果分别调用它们，仍可能各自触发 native 扫描；这些路径不是本批生产提取链路。

本批按临时例外未跑全量 `uv run pytest`，全仓非 Note 标签路径仍需在阶段收束或最终提交前用全量测试确认。

## 下一批入口

建议下一批进入 P1-B Note 标签阶段收束回顾：审计 Note 标签支线从候选导出、规则校验、规则导入、text-scope、scope hash/count 到 `NoteTagTextExtraction` 的 native 消费边界，确认是否还存在不必要的 Python Note 扫描、重复 native 扫描或未记录的过期规则语义风险。
