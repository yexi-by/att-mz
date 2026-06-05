# Rust Scope/Index Engine 批次 6BP 验收记录

## 本批范围

本批是 Note 标签 text-scope 逐命中 native 明细评估，承接 `docs/records/rust-scope-index/batches/batch-098.md`，新增 `collect_note_tag_rule_hits` 行为保护、计划索引和验收记录。

本批同时修复 6BO 后暴露的 `app/application/flow_gate.py` 顶层导入循环：`flow_gate` 保留可测试的 `collect_native_note_tag_candidate_details` 包装入口，但把真正的 `app.native_note_tag_scan` 导入改为函数内延迟导入。本批修改生产 Python 代码，本批未修改 Rust 原生代码。

本批评估以下入口：

- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`
- `collect_note_tag_sources`
- `iter_note_tag_matches`
- Rust `NoteTagCandidateOutput`

## 保护网

新增 `tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text`，固定以下逐命中行为：

- `collect_note_tag_rule_hits` 必须输出完整 `location_path`。
- `collect_note_tag_rule_hits` 必须输出规范化后的 `original_text`。
- 输出必须保留 `source_type="note_tag"` 和 `rule_source="Note 标签规则"`。
- 多条规则命中同一 `location_path` 时必须通过 `seen_paths` 去重。
- 文件模式不匹配的规则不能产生命中。

新增 `tests/test_scan_budget.py::test_batch99_note_tag_text_scope_hit_detail_evaluation_tracks_boundaries`，固定以下边界：

- 当前 Rust `NoteTagCandidateOutput` 仍是候选摘要，只包含 `sample_locations` 和 `sample_values`，不包含完整逐命中 `location_path` 和 `original_text`。
- 当前 native 候选摘要不能直接替代 text-scope 逐命中明细。
- `collect_note_tag_rule_hits` 仍负责 `TextScopeRuleHit`、`location_path`、`original_text`、`seen_paths` 和可见文本规范化。
- `NoteTagTextExtraction` 仍负责 `TranslationItem` 构建、过期规则检查、重复标签错误和可翻译文本筛选。

新增 `tests/test_scan_budget.py::test_batch99_note_tag_text_scope_hit_detail_evaluation_record_exists_and_tracks_contract`，固定本记录、计划表链接、验证命令、临时验证例外和下一批入口。

## 实现说明

本批没有把 text-scope 或实际提取改成 native。评估结论如下：

- 当前 Rust `NoteTagCandidateOutput` 仍是候选摘要，按 `(file_pattern, tag_name)` 聚合，并只保留最多 5 个 `sample_locations` 和 `sample_values`。
- 当前 Rust NoteTagCandidateOutput 仍是候选摘要，当前 native 候选摘要不能直接替代 text-scope 逐命中明细。
- `sample_locations` 与 `sample_values` 只是样例，不是完整逐命中明细，也不是 `location_path` 与 `original_text` 的一一绑定列表。
- `collect_note_tag_rule_hits` 需要完整逐命中 `location_path` 和规范化后的 `original_text`，还要保留按规则文件模式筛选、按定位去重和 `TextScopeRuleHit` 构建语义。
- `NoteTagTextExtraction` 还需要 `TranslationItem` 构建、过期规则错误、重复标签错误和 `should_translate_source_text` 过滤，不能直接消费当前 native 候选摘要。

本批对 `flow_gate` 的延迟导入修复只解决模块加载顺序问题，不改变 `count_note_tag_rule_candidates` 与 `note_tag_rule_scope_hash_for_text_rules` 已迁移到 native 候选摘要的行为。

## 旧路径收束

本批继续保留以下 Python 逐命中路径：

- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`
- `collect_note_tag_sources`
- `iter_note_tag_matches`

本批确认以下 native/Rust 输出仍不是逐命中明细：

- `collect_native_note_tag_candidate_details`
- Rust `NoteTagCandidateOutput`
- Rust `scan_rule_candidates(note_tags)`

这些路径不是本批删除对象。下一批若进入 native 逐命中明细，必须先定义完整 `location_path`、`original_text`、真实 `file_name`、真实 `tag_name` 和重复标签语义。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

用户可见行为保持不变；变化只在测试保护和 `flow_gate` 内部导入时机。

## 性能证据

本批没有新增 runtime 快路径，也没有减少 text-scope 的 Python 逐命中扫描。性能相关结论如下：

- 当前 Rust/native Note 标签路径只能提供聚合候选摘要。
- text-scope/实际提取仍需要 Python 逐命中路径，直到 Rust 提供完整逐命中明细。
- 新增行为测试固定逐命中完整性，避免后续为了性能误用候选摘要替代完整 text-scope 明细。

## 验证结果

- RED：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text` 首次运行出现 import error，暴露 6BO 后 `flow_gate` 顶层导入 `native_note_tag_scan` 引发的 Note 标签包初始化循环。
- RED：`uv run pytest tests/test_scan_budget.py::test_batch99_note_tag_text_scope_hit_detail_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch99_note_tag_text_scope_hit_detail_evaluation_record_exists_and_tracks_contract`，2 failed。失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-099.md`、本批记录不存在。
- GREEN 目标行为测试：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text`，1 passed。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch99_note_tag_text_scope_hit_detail_evaluation_tracks_boundaries tests/test_scan_budget.py::test_batch99_note_tag_text_scope_hit_detail_evaluation_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rule_hits_expand_full_locations_and_normalized_text tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_extraction_rejects_stale_rule_without_current_tag tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back tests/test_agent_toolkit_rule_import.py::test_note_tag_scope_hash_and_count_use_native_candidate_scan`，5 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，20 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批修改生产 Python 代码。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标行为测试、目标记录保护、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批使用只读子代理辅助审计 Rust/native Note 标签输出和 Python text-scope 语义，主代理负责最终判断、记录和验证。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

只读子代理结论与本地结论一致：当前 Rust `NoteTagCandidateOutput` 仍是候选摘要，不包含完整逐命中 `location_path` 与 `original_text`；`sample_locations` 和 `sample_values` 只是最多 5 个样例，不能替代 `collect_note_tag_rule_hits` 或 `NoteTagTextExtraction`。

## 剩余风险

本批没有建立 Rust 逐命中明细输出，也没有迁移 `collect_note_tag_rule_hits` 或 `NoteTagTextExtraction`。后续实现 native 逐命中明细时，还需要补充超过 5 个同标签命中、精确 `Map001.json` 规则、重复标签错误和不可翻译值过滤等行为测试。

本批未跑全量 `uv run pytest`，全仓其它非 Note 标签测试没有在本批重复验证。

## 下一批入口

建议下一批进入 Note 标签逐命中 Rust 明细最小契约：定义并实现完整逐命中输出，至少包含 `location_path`、规范化后的 `original_text`、真实 `file_name`、真实 `tag_name` 和重复标签语义，再评估替换 Python text-scope 路径。
