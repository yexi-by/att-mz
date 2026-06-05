# Rust Scope/Index Engine 批次 6BS 验收记录

## 本批范围

本批是 Note 标签 text-scope native 明细薄适配，承接 `docs/records/rust-scope-index/batches/batch-101.md`，把 `collect_note_tag_rule_hits` 的扫描来源从 Python Note 来源扫描切到 `collect_native_note_tag_hit_details`。本批修改生产 Python 代码，本批未修改 Rust 原生代码。

本批只替换 text-scope 规则命中路径，不替换 `NoteTagTextExtraction` 的实际文本提取路径。

## 保护网

新增 `tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_use_native_details_without_python_note_scan`，固定以下行为：

- `collect_note_tag_rule_hits` 不再调用 Python `collect_note_tag_sources`。
- `collect_note_tag_rule_hits` 不再调用 Python `iter_note_tag_matches`。
- 规则文件模式仍通过 `note_file_pattern_matches` 匹配，覆盖 `Items*.json`、精确 `Map001.json` 和通配 `Map*.json`。
- 同一 `location_path` 的重复 native 明细仍按旧 `seen_paths` 语义只输出第一条。
- `PrivateProtocol` 这类 `translatable=false` 的明细仍进入 text-scope 规则命中，`translatable` 不作为过滤条件。
- 输出仍构造 `TextScopeRuleHit`，并保留 `source_type="note_tag"`、`rule_source="Note 标签规则"` 和 native 已规范化的 `original_text`。

新增 `tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_uses_native_details` 和 `tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_record_exists_and_tracks_contract`，固定计划索引、验收记录、生产路径调用 native helper、旧 Python scanner 不再参与 `collect_note_tag_rule_hits`、以及下一批入口。

## 实现说明

`app/text_scope/rule_hits.py` 新增延迟导入 wrapper：

- `collect_native_note_tag_hit_details`

该 wrapper 在函数内部导入 `app.native_note_tag_scan.collect_native_note_tag_hit_details`，避免 Note 标签包初始化循环。

`collect_note_tag_rule_hits` 当前流程为：

- 调用 `collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules)` 获取 native 逐命中明细。
- 对每条明细通过 `ensure_json_object` 和 `_read_note_tag_hit_string` 收窄 `file_name`、`tag_name`、`location_path`、`original_text`。
- 按每条 `NoteTagTextRuleRecord` 的 `tag_names` 和 `note_file_pattern_matches` 做规则筛选。
- 用 `seen_paths` 保留旧的全局 `location_path` 去重语义。
- 构造 `TextScopeRuleHit`，固定 `source_type="note_tag"` 和 `rule_source="Note 标签规则"`。

本批刻意不读取 `translatable` 字段，因为 text-scope 规则命中不是可翻译文本项过滤。

## 旧路径收束

本批从 `collect_note_tag_rule_hits` 收束以下旧扫描入口：

- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `normalize_visible_text_for_extraction` 的 Note 标签值规范化调用

这些入口仍可能被 `NoteTagTextExtraction`、规则导入校验或其它旧路径使用，本批不删除对应模块能力。

`NoteTagTextExtraction` 仍保留 Python 逐命中扫描、重复标签错误、不可翻译值过滤、过期规则检查和 `TranslationItem` 构造。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill、Rust API 或发布流程变化。

用户可见行为应保持不变；变化是 text-scope 内部扫描来源从 Python Note 扫描改为 native 明细。

## 性能证据

本批让 text-scope 的 Note 标签规则命中复用 Rust/native `hit_details`，避免在 text-scope 构建时再次通过 Python 路径遍历 Note 来源并正则解析标签值。

性能收益主要体现在包含 Note 标签规则的 text-scope 构建命令；本批通过 monkeypatch 保护确认 `collect_note_tag_rule_hits` 不再调用旧 Python Note scanner。

## 验证结果

- RED 目标行为测试：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_use_native_details_without_python_note_scan`，1 failed。失败点是旧实现仍调用 `collect_note_tag_sources`。
- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_uses_native_details tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_record_exists_and_tracks_contract`，2 failed。失败点是计划缺少 `docs/records/rust-scope-index/batches/batch-102.md`，本批记录不存在。
- GREEN 目标行为测试：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_use_native_details_without_python_note_scan tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text`，3 passed。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_uses_native_details tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_use_native_details_without_python_note_scan tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_rejects_stale_rule_without_current_tag tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back`，6 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，26 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量测试：`uv run pytest`，952 passed。
- 最终记录保护：`uv run pytest tests/test_scan_budget.py::test_batch102_note_tag_text_scope_native_detail_adapter_record_exists_and_tracks_contract`，1 passed。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。

## 审查处理

本批使用只读子代理辅助审计 thin adapter 的风险点，主代理负责最终实现、验证和记录。子代理不修改文件。

审计重点是：导入循环风险、旧规则顺序、文件模式匹配、`location_path` 去重、不按 `translatable` 过滤、以及不能误替换 `NoteTagTextExtraction`。

## 剩余风险

本批没有替换 `NoteTagTextExtraction`，因此实际 Note 标签文本提取仍会使用 Python 逐命中路径。后续需要单独评估 `NoteTagTextExtraction` 是否能消费 native 明细，同时保留重复标签错误、不可翻译过滤、过期规则检查和 `TranslationItem` 构造语义。

## 下一批入口

建议下一批进入 NoteTagTextExtraction native 明细替换评估：先对比 `NoteTagTextExtraction` 与 native 明细的语义差异，尤其是重复标签错误、过期规则、不可翻译过滤和 `TranslationData` 组装，再决定是否进入薄适配。
