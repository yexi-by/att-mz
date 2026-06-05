# Rust Scope/Index Engine 批次 6BQ 验收记录

## 本批范围

本批是 Note 标签逐命中 Rust 明细最小契约，承接 `docs/records/rust-scope-index/batches/batch-099.md` 的评估结论，在 Rust `scan_rule_candidates(note_tags)` 输出中新增完整逐命中 `hit_details`，并在 Python 适配层新增 `collect_native_note_tag_hit_details`。

本批修改生产 Python 和 Rust 原生代码。Python 改动包含 `app/native_note_tag_scan.py` 新 helper，以及 `app/note_tag_text/exporter.py` 的延迟导入修复；Rust 改动包含 `rust/src/native_core/scope_index/note_tags.rs` 和 `rust/src/native_core/scope_index/mod.rs` 的逐命中输出。

本批不替换 `collect_note_tag_rule_hits` 或 `NoteTagTextExtraction`，只提供后续替换评估可消费的最小 native 明细契约。

## 保护网

新增或更新以下行为测试：

- `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates`
- `tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_full_note_tag_hit_details`
- `tests/test_native_scope_index.py::test_collect_native_note_tag_hit_details_returns_full_native_note_hits`

这些测试固定以下行为：

- Rust `hit_details` 必须输出完整逐命中列表，而不是 `sample_locations` 和 `sample_values` 的最多 5 个摘要样例。
- 每条 `NoteTagHitOutput` 必须包含真实 `file_name`、真实 `tag_name`、完整 `location_path`、规范化后的 `original_text` 和可翻译判断 `translatable`。
- `Map001.json` 这类实际文件在逐命中明细里必须保留真实文件名，不能使用候选摘要里的 `Map*.json` 聚合模式。
- `<empty>` 这种无 value 标签不能进入 `hit_details`；`<blank:>` 这种空 value 标签必须进入 `hit_details`，并带 `original_text=""` 和 `translatable=false`。
- Python `collect_native_note_tag_hit_details` 必须只暴露逐命中字段，不把 `sample_locations` 或 `sample_values` 泄漏成明细。
- Python helper 遇到旧 native 扩展缺少 `hit_details` 时必须显式失败，提示重新构建 Rust 原生扩展，不能静默返回空明细。
- 冷启动直接导入 `app.native_note_tag_scan` 不能再被 `app.note_tag_text.exporter` 反向导入卡住。

新增 `tests/test_scan_budget.py::test_batch100_note_tag_native_hit_detail_contract_exists` 和 `tests/test_scan_budget.py::test_batch100_note_tag_native_hit_detail_record_exists_and_tracks_contract`，固定计划索引、验收记录、Rust/Python helper 契约、旧 text-scope 路径保留边界和验证命令。

## 实现说明

Rust 新增 `NoteTagHitOutput`，字段为：

- `file_name`
- `tag_name`
- `location_path`
- `original_text`
- `translatable`

`scan_note_tag_rule_candidates` 仍按 `(file_pattern, tag_name)` 构造 `NoteTagCandidateOutput` 候选摘要，保留 `sample_locations`、`sample_values`、`hit_count`、`value_hit_count` 和 `translatable_hit_count` 等旧字段；同时在每个带 value 的 Note 标签命中上追加一条 `hit_details` 明细。`original_text` 复用 Rust 现有 `normalize_visible_text_for_extraction` 与 `normalize_extraction_text` 链路，和候选摘要样例值保持同一规范化口径。

`translatable` 在 Rust 同一处通过 `should_translate_plugin_source_text` 计算，`translatable_value_count` 继续与所有逐命中里的 `translatable=true` 数量一致。`rust/src/native_core/scope_index/mod.rs` 在 `scan_summary["note_tags"]` 中新增 `"hit_details": note_tag_scan.hit_details`。这是 native 内部扫描摘要字段，不是 CLI 外部 stdout 新契约。

Python 新增 `collect_native_note_tag_hit_details` 和 `_normalize_native_note_tag_hit_detail`，负责把 native JSON 收窄为强约束 `JsonObject` 列表。`app/note_tag_text/exporter.py` 把 `collect_native_note_tag_candidate_details` 改为函数内延迟导入，避免直接导入 `app.native_note_tag_scan` 时触发 Note 标签包初始化循环。

## 旧路径收束

本批继续保留以下 Python 逐命中路径：

- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`
- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `TextScopeRuleHit`

`collect_note_tag_rule_hits` 仍负责按保存的 Note 标签规则筛选、按 `location_path` 去重并构造 `TextScopeRuleHit`。`NoteTagTextExtraction` 仍负责已保存规则的实际提取、不可翻译文本过滤、过期规则检查和重复标签错误。Rust `hit_details` 只是后续迁移的输入基础，本批不改变这些运行路径。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill 或发布流程变化。

本批新增的是 native 内部扫描摘要字段 `scan_summary["note_tags"]["hit_details"]` 和 Python 内部 helper `collect_native_note_tag_hit_details`。现有 `collect_native_note_tag_candidate_details`、候选摘要文件、规则校验、规则导入、scope hash/count 行为保持不变。

## 性能证据

本批让 Rust 在一次 Note 标签扫描中同时生成候选摘要和逐命中明细，避免未来 text-scope 替换时为了 `location_path` 与 `original_text` 再触发第二次 Python 全量 Note 标签扫描。

逐命中明细会随 value 命中数量线性增长，内存占用也随命中数线性增长。这个成本是后续替换 Python text-scope 路径所需的真实数据成本；本批通过超过 5 个同标签命中的测试确认它不再受摘要样例上限影响。

## 验证结果

- RED 目标行为测试：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_full_note_tag_hit_details tests/test_native_scope_index.py::test_collect_native_note_tag_hit_details_returns_full_native_note_hits`，3 failed。失败点是缺少 `hit_details`、缺少 `collect_native_note_tag_hit_details`，以及直接导入 `app.native_note_tag_scan` 时触发 Note 标签包初始化循环。
- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch100_note_tag_native_hit_detail_contract_exists tests/test_scan_budget.py::test_batch100_note_tag_native_hit_detail_record_exists_and_tracks_contract`，2 failed。失败点是计划缺少 `docs/records/rust-scope-index/batches/batch-100.md`，本批记录不存在。
- 构建：`uv run maturin develop --manifest-path rust/Cargo.toml`，已重新安装本地 Rust 扩展。
- GREEN 目标行为测试：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_full_note_tag_hit_details tests/test_native_scope_index.py::test_collect_native_note_tag_hit_details_returns_full_native_note_hits`，3 passed。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch100_note_tag_native_hit_detail_contract_exists tests/test_scan_budget.py::test_batch100_note_tag_native_hit_detail_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签 native/导入回归：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_native_note_tag_candidates_match_python_scope_hash_input tests/test_agent_toolkit_rule_import.py::test_note_tag_scope_hash_and_count_use_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan`，4 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，22 passed，134 deselected。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`，71 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量测试首轮：`uv run pytest`，944 passed，2 failed。失败点是先前普通占位符/结构化占位符旧记录保护测试与旧记录事实不一致，测试要求“本批修改生产 Python 代码”，但记录写明“本批未修改生产代码”。
- 旧记录保护修正验证：`uv run pytest tests/test_scan_budget.py::test_batch80_placeholder_branch_closure_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch88_structured_placeholder_branch_closure_record_exists_and_tracks_contract`，2 passed。修正方式是让测试匹配旧记录事实，没有修改旧验收记录。
- 全量测试复跑：`uv run pytest`，946 passed。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。

## 审查处理

本批使用只读子代理辅助审计 native Note 标签输出边界和测试落点，主代理负责最终实现、验证和记录。子代理不修改文件。

审计重点与实现保持一致：当前 `sample_locations` 和 `sample_values` 只能作为候选摘要样例，不能替代完整逐命中明细；新 `hit_details` 必须保留真实文件名、完整定位和规范化文本。

## 剩余风险

本批仍未把 `collect_note_tag_rule_hits` 或 `NoteTagTextExtraction` 改为消费 native 明细，因此 text-scope 和实际提取仍保留 Python 逐命中扫描。后续替换时还要验证按保存规则筛选、按定位去重、重复标签错误、不可翻译值过滤和精确地图文件规则语义。

## 下一批入口

建议下一批进入 Note 标签 text-scope native 明细替换评估：以 `collect_native_note_tag_hit_details` 为输入，对比 `collect_note_tag_rule_hits` 的筛选、去重和 `TextScopeRuleHit` 构造语义，先做评估和保护网，再决定是否替换 Python 逐命中扫描。
