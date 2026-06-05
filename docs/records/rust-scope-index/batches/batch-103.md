# Rust Scope/Index Engine 批次 6BT 验收记录

## 本批范围

本批是 NoteTagTextExtraction native 明细替换评估，承接 `docs/records/rust-scope-index/batches/batch-102.md`，只新增评估测试、计划索引和验收记录。本批未修改生产代码，本批未修改 Rust 原生代码。

本批评估 `NoteTagTextExtraction.extract_all_text` 是否可以直接消费 `collect_native_note_tag_hit_details` 做薄适配。评估对象包含成功提取输出、重复标签错误、不可翻译过滤、过期规则检查和 `TranslationData` / `TranslationItem` 组装。

## 保护网

新增 `tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_successful_note_tag_extraction`，固定以下评估事实：

- `collect_native_note_tag_hit_details` 的 `file_name`、`tag_name`、`location_path`、`original_text` 和 `translatable` 字段足够复刻成功路径的 `TranslationData` / `TranslationItem` 输出。
- native 明细保留真实 `Map001.json` 文件名，因此成功路径可继续按 `Map*.json` 规则筛选。
- native 明细的 `original_text` 已完成可见文本规范化，可直接映射到 `TranslationItem.original_lines`。
- `PrivateProtocol` 和 `BlankValue` 这类 `translatable=false` 的命中仍会出现在 native 明细中，但成功提取输出必须按 `NoteTagTextExtraction` 旧语义过滤掉不可翻译值。
- 评估 helper 按规则标签顺序、来源顺序和 `location_path` 去重模拟旧提取流程，避免直接按 native 命中顺序改变输出顺序。

新增 `tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_expose_duplicate_locations_for_extraction_error`，固定 native 明细保留同一 `location_path` 的重复命中，后续 adapter 可以在不可翻译过滤前复刻重复标签错误。

新增 `tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_tracks_boundaries` 和 `tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_record_exists_and_tracks_contract`，固定计划索引、验收记录、当前生产路径仍未替换、评估测试名称和下一批入口。

## 评估结论

`collect_native_note_tag_hit_details` 已经覆盖成功提取路径所需的核心字段：

- `file_name` 支撑具体文件和 `Map*.json` 这类规则文件模式筛选。
- `tag_name` 支撑规则标签筛选和按 `rule_record.tag_names` 顺序重建输出。
- `location_path` 支撑 `seen_location_paths` 去重，也能识别重复标签错误。
- `original_text` 支撑 `TranslationItem.original_lines`。
- `translatable` 支撑 `NoteTagTextExtraction` 的不可翻译过滤。

但是，`hit_details` 不能单独证明规则文件模式仍命中当前游戏 note 字段。当前 `NoteTagTextExtraction.extract_all_text` 会先构造 `matching_sources`，如果规则文件模式没有命中任何当前 note 字段，会报出文件模式级过期规则错误；而 native `hit_details` 只包含带值标签命中，不包含“存在 note 字段但没有目标标签”或“存在 note 字段但没有带值标签”的来源存在事实。换句话说，hit_details 不能单独证明规则文件模式仍命中当前游戏 note 字段。

因此，本批不建议立刻把 `NoteTagTextExtraction` 切到只消费 `hit_details` 的薄适配。后续如果要替换，应先补 native 来源存在契约，或在 adapter 中显式引入等价的来源存在事实，并保持以下旧语义：

- `matching_sources` 文件模式级过期规则检查。
- 每个标签的过期规则检查 `_ensure_note_tag_rule_has_current_hits`。
- 重复标签错误必须在不可翻译过滤之前触发。
- 不可翻译过滤只影响 `TranslationItem` 输出，不影响过期规则命中计数。
- 输出顺序必须按规则顺序、来源顺序和 `rule_record.tag_names` 顺序重建，不能直接使用 native 命中顺序。

## 旧路径收束

本批不收束生产旧路径。当前 `app/note_tag_text/extraction.py` 的 `NoteTagTextExtraction.extract_all_text` 仍调用：

- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `_ensure_note_tag_rule_has_current_hits`
- `TranslationData`
- `TranslationItem`

这些路径仍是实际提取的事实来源。本批新增的 native 明细 shadow helper 只存在于测试侧，用于评估后续替换边界。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill、Rust API 或发布流程变化。

本批只新增测试和文档记录，不改变用户可见行为。

## 性能证据

本批没有新增 runtime 快路径。评估结果说明：成功提取输出、不可翻译过滤和重复标签错误具备迁移到 native 明细的基础，但完整替换还缺少来源存在事实。

因此实际运行性能不会变化；`NoteTagTextExtraction` 仍会保留当前 Python 标签解析路径。下一批若补齐 native 来源存在契约，才适合继续推进实际 thin adapter。

## 验证结果

- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_record_exists_and_tracks_contract`，2 failed。失败点是计划缺少 `docs/records/rust-scope-index/batches/batch-103.md`，本批记录不存在。
- 目标行为评估测试：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_successful_note_tag_extraction tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_expose_duplicate_locations_for_extraction_error`，2 passed。
- GREEN 初次记录保护：`uv run pytest tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_record_exists_and_tracks_contract`，2 failed。失败点是记录保护测试对评估测试 marker 和验收记录表述约束过窄；已修正为检查 `original_lines` 和明确的 `hit_details` 缺口结论。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch103_note_tag_extraction_native_detail_evaluation_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_successful_note_tag_extraction tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_expose_duplicate_locations_for_extraction_error tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_rejects_stale_rule_without_current_tag tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back`，5 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，28 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计 `NoteTagTextExtraction` 与 native 明细的语义差异，主代理负责最终测试、记录和验证。子代理不修改文件。

审计重点是：成功输出字段是否足够、重复标签错误能否保留、不可翻译过滤是否可复刻、`matching_sources` 文件模式级过期规则检查是否可由 `hit_details` 单独证明，以及是否可以直接进入 thin adapter。

## 剩余风险

本批没有替换生产实现，因此实际 `NoteTagTextExtraction` 仍会使用旧提取路径。

后续真正切换前仍需补齐来源存在事实，否则仅靠 `hit_details` 可能把“规则文件模式没有命中任何当前 note 字段”和“命中了 note 字段但没有目标标签值”折叠成同一种过期规则判断，改变现有错误边界。

## 下一批入口

建议下一批进入 NoteTagTextExtraction native 来源存在契约补强：为 native Note 标签扫描补充可证明 `matching_sources` 语义的来源存在摘要或等价事实，再评估是否可以进入 `NoteTagTextExtraction` native 明细薄适配。
