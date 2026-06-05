# Rust Scope/Index Engine 批次 6BU 验收记录

## 本批范围

本批是 NoteTagTextExtraction native 来源存在契约补强，承接 `docs/records/rust-scope-index/batches/batch-103.md`，为 native Note 标签扫描补充独立 `source_details` 摘要。本批修改 Rust 原生代码，本批修改生产 Python 代码。

本批不替换 extract_all_text。`NoteTagTextExtraction.extract_all_text` 仍保留当前 `collect_note_tag_sources`、`iter_note_tag_matches`、重复标签错误、不可翻译过滤、过期规则检查和 `TranslationData` / `TranslationItem` 组装语义。

## 保护网

新增和调整以下测试：

- `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates`：固定 `scan_summary["note_tags"]["source_details"]` 存在，且每项只包含 `file_name` 和 `location_prefix`。
- `tests/test_native_scope_index.py::test_collect_native_note_tag_source_details_returns_native_note_sources`：固定 Python helper `collect_native_note_tag_source_details` 返回 native 来源存在摘要，不暴露 `note_text`，也不混入 `tag_name`、`original_text`、`translatable` 等命中字段。
- `tests/test_native_adapters.py::test_collect_native_note_tag_source_details_returns_source_summary`：用伪 native 模块固定 Python helper 的正常收窄行为。
- `tests/test_native_adapters.py::test_collect_native_note_tag_source_details_requires_source_details`：固定旧 Rust 扩展或缺字段结果不能静默当作空来源，必须报出 `source_details 缺失`。
- `tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_source_details_prove_matching_sources_without_value_hits`：固定没有带值标签命中的 marker-only note 也会进入 `source_details`，包括 `MarkerOnly` 和 `MapMarkerOnly`，证明它不是从 `hit_details` 反推。
- `tests/test_scan_budget.py::test_batch104_note_tag_extraction_native_source_contract_exists` 和 `tests/test_scan_budget.py::test_batch104_note_tag_extraction_native_source_record_exists_and_tracks_contract`：固定计划索引、验收记录、Rust 输出字段、Python helper、契约版本和下一批入口。

## 实现说明

Rust 侧在 `rust/src/native_core/scope_index/note_tags.rs` 新增 `NoteTagSourceDetailOutput`，并在 `NoteTagRuleCandidateScan` 中新增 `source_details`。该字段直接从 Rust 扫描阶段已收集的 `sources` 向量映射而来，每项只包含：

- `file_name`
- `location_prefix`

Rust 侧在 `rust/src/native_core/scope_index/mod.rs` 把 `"source_details": note_tag_scan.source_details` 写入 `scan_summary["note_tags"]`。该摘要与 `hit_details` 分离：`source_details` 表示“当前游戏存在这个非空 note 字段”，不表示命中任何标签；`hit_details` 继续表示带值标签逐命中，并保留 `tag_name`、`location_path`、`original_text`、`translatable`。

Python 侧在 `app/native_note_tag_scan.py` 新增：

- `collect_native_note_tag_source_details`
- `_normalize_native_note_tag_source_detail`

`collect_native_note_tag_source_details` 调用既有 `build_native_note_tag_candidates_payload` 和 `scan_native_rule_candidates`，从 `scan_summary["note_tags"]["source_details"]` 读取来源摘要。缺少 `source_details` 时显式抛出 `RuntimeError`，避免旧 Rust 扩展把来源事实静默降级为空列表。

本批同步将 Python 与 Rust 原生契约版本提升到 `NATIVE_CONTRACT_VERSION = 7`。

## 旧路径收束

本批只补 native 来源存在契约，不收束 `NoteTagTextExtraction.extract_all_text` 旧路径。

当前生产提取路径仍调用：

- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `_ensure_note_tag_rule_has_current_hits`

后续薄适配时应同时消费 `source_details` 和 `hit_details`，其中 `source_details` 负责复刻 `matching_sources` 文件模式级过期规则检查，`hit_details` 负责复刻标签命中、重复标签错误、不可翻译过滤和输出组装。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、stdout JSON、README、Skill 或发布流程变化。

Rust/Python 原生 JSON 契约发生内部版本变化：`scan_summary["note_tags"]` 新增 `source_details`，原生契约版本升为 `NATIVE_CONTRACT_VERSION = 7`。旧原生扩展必须重新构建；本地验证执行了 `uv run maturin develop`。

## 性能证据

本批没有新增额外扫描。Rust Note 标签扫描本来已经在同一次 `scan_rule_candidates(note_tags)` 中收集 `sources`，本批只把已有来源事实映射成 `source_details` 输出。

这为下一批 `NoteTagTextExtraction` native 明细薄适配提供完整输入：后续可在一次 native Note 标签扫描中同时获得 `source_details` 和 `hit_details`，避免 Python 再调用 `collect_note_tag_sources` 与 `iter_note_tag_matches` 重复遍历和解析 Note。

## 验证结果

- RED native scope / helper 行为：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_native_scope_index.py::test_collect_native_note_tag_source_details_returns_native_note_sources`，2 failed。失败点是 `source_details` 缺失和 `collect_native_note_tag_source_details` 尚不存在。
- RED adapter helper 行为：`uv run pytest tests/test_native_adapters.py::test_collect_native_note_tag_source_details_returns_source_summary tests/test_native_adapters.py::test_collect_native_note_tag_source_details_requires_source_details`，2 failed。失败点是 Python helper 尚不存在。
- RED marker-only 行为：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_source_details_prove_matching_sources_without_value_hits`，collection error。失败点是测试导入的 `collect_native_note_tag_source_details` 尚不存在。
- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch104_note_tag_extraction_native_source_contract_exists tests/test_scan_budget.py::test_batch104_note_tag_extraction_native_source_record_exists_and_tracks_contract`，2 failed。失败点是计划缺少 `docs/records/rust-scope-index/batches/batch-104.md`，本批记录不存在。
- Rust/Python native 重建：`uv run maturin develop`，成功。
- GREEN native scope / helper 行为：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_native_scope_index.py::test_collect_native_note_tag_source_details_returns_native_note_sources`，2 passed。
- GREEN adapter helper 行为：`uv run pytest tests/test_native_adapters.py::test_collect_native_note_tag_source_details_returns_source_summary tests/test_native_adapters.py::test_collect_native_note_tag_source_details_requires_source_details`，2 passed。
- GREEN marker-only 行为：`uv run pytest tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_source_details_prove_matching_sources_without_value_hits`，1 passed。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch104_note_tag_extraction_native_source_contract_exists tests/test_scan_budget.py::test_batch104_note_tag_extraction_native_source_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_full_note_tag_hit_details tests/test_native_scope_index.py::test_collect_native_note_tag_hit_details_returns_full_native_note_hits tests/test_native_scope_index.py::test_collect_native_note_tag_source_details_returns_native_note_sources tests/test_native_adapters.py::test_collect_native_note_tag_source_details_returns_source_summary tests/test_native_adapters.py::test_collect_native_note_tag_source_details_requires_source_details tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_source_details_prove_matching_sources_without_value_hits tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_can_shadow_successful_note_tag_extraction tests/test_rmmz_note_nonstandard_data.py::test_native_note_tag_hit_details_expose_duplicate_locations_for_extraction_error`，9 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，30 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`，通过。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计 `source_details` 最小字段和边界，主代理负责最终实现、验证和记录。子代理不修改文件。

审计结论与本批实现一致：最小来源存在契约只需要 `file_name` 和 `location_prefix`；不应暴露 `note_text`，也不应从 `hit_details` 反推来源。`source_details` 只证明 `matching_sources` 的来源存在事实，不代表任何标签值命中。

## 剩余风险

本批尚未替换 `NoteTagTextExtraction.extract_all_text`，因此实际提取路径仍会走 Python Note 来源扫描和正则解析。

下一批薄适配需要同时消费 `source_details` 与 `hit_details`，并保持旧语义：文件模式级过期规则检查、标签级过期规则检查、重复标签错误先于不可翻译过滤、不可翻译值不进入 `TranslationItem`、输出顺序按规则和来源顺序重建。

## 下一批入口

建议下一批进入 NoteTagTextExtraction native 明细薄适配：让 `extract_all_text` 消费同一次 native 扫描得到的 `source_details` 与 `hit_details`，收束 `collect_note_tag_sources` 和 `iter_note_tag_matches` 在该路径上的重复扫描，同时保持本批固定的过期规则、重复标签、不可翻译过滤和输出组装语义。
