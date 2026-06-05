# Rust Scope/Index Engine 批次 6BR 验收记录

## 本批范围

本批是 Note 标签 text-scope native 明细替换评估，承接 `docs/records/rust-scope-index/batches/batch-100.md`，只新增评估测试、计划索引和验收记录。本批未修改生产代码，本批未修改 Rust 原生代码。

本批评估 `collect_native_note_tag_hit_details` 是否能在规则筛选和定位去重后复刻 `collect_note_tag_rule_hits` 的 `TextScopeRuleHit` 输出语义。结论是：native 明细已经足够支撑 text-scope 规则命中薄适配，但本批不替换生产路径。

## 保护网

新增 `tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits`，固定以下评估事实：

- `collect_native_note_tag_hit_details` 输出可以按保存的 `NoteTagTextRuleRecord` 做 `note_file_pattern_matches` 文件模式筛选。
- native 明细保留真实 `Map001.json` 文件名，因此可同时支持精确 `Map001.json` 和通配 `Map*.json` 规则。
- native 明细保留真实 `Items.json` 文件名，因此 `Items*.json` 这类普通通配规则也应沿用旧 `fnmatchcase` 文件模式语义。
- native 明细保留同一 `location_path` 的重复标签事实；text-scope 替换时仍必须按旧 `seen_paths` 语义去重。
- `PrivateProtocol` 这类 `translatable=false` 的 Note 标签值仍必须进入 text-scope 规则命中评估；`translatable` 不能作为 `collect_note_tag_rule_hits` 的过滤条件。
- native 明细经规则筛选、去重和 `TextScopeRuleHit` 字段映射后，输出必须与当前 Python `collect_note_tag_rule_hits` 完全一致。

新增 `tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_evaluation_tracks_boundaries` 和 `tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_record_exists_and_tracks_contract`，固定计划索引、验收记录、旧生产路径仍未替换、评估测试和下一批入口。

## 实现说明

本批没有修改 `app/text_scope/rule_hits.py`。当前 `collect_note_tag_rule_hits` 仍直接调用：

- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `note_file_pattern_matches`
- `normalize_visible_text_for_extraction`

评估测试在测试侧模拟后续薄适配逻辑：读取 `collect_native_note_tag_hit_details` 的 `file_name`、`tag_name`、`location_path`、`original_text` 和 `translatable`，再按规则文件模式、规则标签名和 `seen_paths` 做筛选与去重。该模拟输出与当前 `collect_note_tag_rule_hits` 的 `(location_path, source_type, rule_source, original_text)` 一致。

本批确认 text-scope 替换时不能用 `translatable` 过滤。`translatable` 可用于后续实际提取或质量边界判断，但 `collect_note_tag_rule_hits` 当前是“规则命中的文本范围”展开，不等同于“进入翻译的文本项”过滤。

## 旧路径收束

本批继续保留以下旧路径：

- `collect_note_tag_rule_hits`
- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `TextScopeRuleHit`

本批也继续保留 `NoteTagTextExtraction`。它还负责已保存规则的实际提取、不可翻译值过滤、重复标签错误和过期规则检查，不属于本批替换对象。

下一批若进入 Note 标签 text-scope native 明细薄适配，应只替换 `collect_note_tag_rule_hits` 的扫描来源，并保持以下旧语义不变：

- 规则文件模式匹配。
- 规则标签名筛选。
- 按 `location_path` 去重。
- `source_type="note_tag"`。
- `rule_source="Note 标签规则"`。
- 不用 `translatable` 过滤 text-scope 命中。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill、Rust API 或发布流程变化。

本批只新增测试和文档记录，不改变用户可见行为。

## 性能证据

本批没有新增 runtime 快路径。评估结果说明：后续 thin adapter 可复用一次 Rust Note 标签扫描产生的 `hit_details`，避免 `collect_note_tag_rule_hits` 再通过 Python 路径遍历所有 Note 标签来源和正则解析标签值。

由于本批不切换生产路径，实际运行性能不会变化。

## 验证结果

- 评估目标行为测试：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits`，1 passed。
- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_record_exists_and_tracks_contract`，2 failed。失败点是计划缺少 `docs/records/rust-scope-index/batches/batch-101.md`，本批记录不存在。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_record_exists_and_tracks_contract`，2 passed。
- 补强后目标行为测试：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits`，1 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_rejects_stale_rule_without_current_tag tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back`，5 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，24 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 最终记录保护：`uv run pytest tests/test_scan_budget.py::test_batch101_note_tag_text_scope_native_detail_replacement_record_exists_and_tracks_contract`，1 passed。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计 native 明细替换 text-scope 的风险点，主代理负责最终测试、记录和验证。子代理不修改文件。

审计重点是文件模式匹配、`location_path` 去重、同一 Note 内重复标签、`translatable` 是否参与 text-scope 过滤、精确 `Map001.json` 与通配 `Map*.json` 语义，以及 `NoteTagTextExtraction` 仍需保留的实际提取边界。

只读子代理结论与本批测试一致：`collect_native_note_tag_hit_details` 信息量足够支撑 `collect_note_tag_rule_hits`，但必须通过薄适配层复刻旧规则顺序、文件模式筛选、`location_path` 去重和 `TextScopeRuleHit` 构造；它不能直接替代 `NoteTagTextExtraction`。

## 剩余风险

本批没有替换 `collect_note_tag_rule_hits` 的生产实现，因此 text-scope 仍会保留 Python Note 标签来源扫描。后续薄适配时仍需用 monkeypatch 或等价保护固定：`collect_note_tag_rule_hits` 不再调用 `collect_note_tag_sources` 和 `iter_note_tag_matches`，而是消费 `collect_native_note_tag_hit_details`。

`NoteTagTextExtraction` 仍未 native 化；它的重复标签错误、不可翻译过滤、过期规则检查和 `TranslationItem` 构造需要后续单独处理。

## 下一批入口

建议下一批进入 Note 标签 text-scope native 明细薄适配：把 `collect_note_tag_rule_hits` 的来源切到 `collect_native_note_tag_hit_details`，保留本批固定的规则筛选、去重、`TextScopeRuleHit` 字段和不按 `translatable` 过滤的旧语义。
