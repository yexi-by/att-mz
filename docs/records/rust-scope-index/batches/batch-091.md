# Rust Scope/Index Engine 批次 6BH 验收记录

## 本批范围

本批建立 Note 标签 Rust 候选入口最小契约。范围限于 Python native payload、Rust `scan_rule_candidates(note_tags)` 分支、目标测试、scan budget 记录保护和计划索引。

本批触及以下生产代码：

- `app/native_scope_index.py`
- `rust/src/native_core/scope_index/mod.rs`
- `rust/src/native_core/scope_index/note_tags.rs`

本批不迁移 `export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules` 的 service、CLI、workflow gate、workspace、text-scope rule hit、数据库规则导入或写回路径。

## 保护网

新增 `tests/test_native_scope_index.py::test_build_native_note_tag_candidates_payload_includes_data_and_text_rules`：

- 固定 `build_native_note_tag_candidates_payload` 会把当前已加载的标准 data JSON 压入 `note_tag_data_files`。
- 固定 payload 跳过 `plugins.js`。
- 固定 Note 标签分支携带真实 `source_text_required_pattern`，用于 Rust 侧计算 `translatable_hit_count`。
- 固定 payload 复用 `build_native_rule_candidate_text_rules_payload` 的占位符规则、包裹标点和排除 profile 结构。

新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates`：

- 固定 `scan_rule_candidates(note_tags)` 输出 `scan_summary["note_tags"]`。
- 固定候选按 `file_name` 与 `tag_name` 聚合，地图文件聚合为 `Map*.json`。
- 固定候选项字段为 `candidate_count`、`hit_count`、`value_hit_count`、`translatable_hit_count`、`matched_file_count`、`sample_locations` 和 `sample_values`。
- 固定 JSON 字符串外壳样本会解成可见文本。
- 固定无值标签保留 `hit_count`，但不增加 `value_hit_count` 和样本。
- 固定 `candidate_summary` domain 为 `note_tags`。

新增 `tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_entry_contract_exists`：

- 固定计划表链接本批记录。
- 固定 batch 90 下一批入口指向本批。
- 固定 `app/native_scope_index.py` 导出 `build_native_note_tag_candidates_payload`。
- 固定 Rust Note 标签候选模块存在，并接入 `scope_index/mod.rs`。

新增 `tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_native_scope_index.py::test_build_native_note_tag_candidates_payload_includes_data_and_text_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_record_exists_and_tracks_contract
```

结果：4 failed。失败点分别是 `app.native_scope_index` 缺少 `build_native_note_tag_candidates_payload`、Rust scan summary 缺少 `note_tags`、计划表缺少 `docs/records/rust-scope-index/batches/batch-091.md`，以及本批记录不存在。

## 实现说明

`app/native_scope_index.py` 新增 `build_native_note_tag_candidates_payload`。该函数只负责把当前已加载的 `GameData` 标准 data JSON 转换为 Rust 输入，不主动加载游戏数据，也不解析 Note 标签。

Rust 新增 `rust/src/native_core/scope_index/note_tags.rs`，提供 `scan_note_tag_rule_candidates`。该分支复用现有 `collect_note_tag_sources_in_value` 和 `NOTE_TAG_RE`，把每个非空 `note` 字段中的标签按 `(file_pattern, tag_name)` 聚合为候选摘要。

`rust/src/native_core/scope_index/mod.rs` 新增可选输入 `note_tag_data_files`。调用方传入该字段时，Rust 会写入 `scan_summary["note_tags"]`，并把候选数量计入 `candidate_summary`。

Note 标签分支没有复用插件源码的宽松预筛正则。`build_native_note_tag_candidates_payload` 会把 `TextRulesSetting.source_text_required_pattern` 写回 payload，使 Rust 侧能直接计算 `translatable_hit_count`。如果配置使用 Rust regex 不支持的源文识别正则，本分支会显式报错，不静默改成宽松匹配。

## 旧路径收束

本批没有删除 Python service、CLI、workflow gate、workspace 或写回相关路径。当前仍保留以下生产事实来源，等待下一批迁移：

- `app/note_tag_text/exporter.py::collect_note_tag_candidates`
- `app/note_tag_text/sources.py::collect_note_tag_sources`
- `app/note_tag_text/parser.py::iter_note_tag_matches`
- `app/note_tag_text/importer.py::build_note_tag_rule_records_from_import`
- `app/note_tag_text/extraction.py::NoteTagTextExtraction`
- `app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules`
- `app/text_scope/rule_hits.py::collect_note_tag_rule_hits`

本批新增 Rust 入口后，旧路径已经具备可迁移目标；但公开命令、规则导入、scope hash、text-scope rule hit 和写回协议必须等待后续批次单独 RED/GREEN 后再切换。

## 外部契约变化

Rust 原生 JSON 输入契约新增可选字段 `note_tag_data_files`。Rust 原生 JSON 输出契约新增可选 summary domain `note_tags`。

`scan_summary["note_tags"]` 包含：

- `candidate_count`
- `candidate_value_count`
- `value_hit_count`
- `translatable_value_count`
- `scanned_source_count`
- `candidates`

每个 candidate 包含：

- `file_name`
- `tag_name`
- `hit_count`
- `value_hit_count`
- `translatable_hit_count`
- `matched_file_count`
- `sample_locations`
- `sample_values`

本批不改变 CLI 参数、stdout JSON、SQLite schema、配置字段、README、Skill 或发布流程。

## 性能证据

本批把 Note 标签候选解析和聚合能力放入 Rust `scan_rule_candidates(note_tags)` 分支。Rust 侧复用已有 `collect_note_tag_sources_in_value` 递归来源枚举，不在 Python 侧重复解析标签，也不新增第二套 data 遍历事实来源。

`scanned_source_count` 固定实际扫描到的非空 `note` 来源数量；`candidate_summary` 固定 Rust 聚合出的 Note 标签候选数量，为后续 `export-note-tag-candidates` native 薄适配提供可复用事实来源。

由于本批尚未迁移公开命令，实际 CLI 仍会走当前 Python `collect_note_tag_candidates`。下一批接入 native 薄适配后，才会把公开命令的 Note 标签候选事实来源切换到 `scan_rule_candidates(note_tags)`。

## 验证结果

- RED 目标测试：`uv run pytest tests/test_native_scope_index.py::test_build_native_note_tag_candidates_payload_includes_data_and_text_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_record_exists_and_tracks_contract`，4 failed。
- 本地扩展重建：`uv run maturin develop --release`，通过。
- GREEN native 目标测试：`uv run pytest tests/test_native_scope_index.py::test_build_native_note_tag_candidates_payload_includes_data_and_text_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_note_tag_rule_validation_import_and_pending_export tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_prefix_read_for_translated_count tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_replaces_stale_existing_rule tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_blocks_missing_note_tag_rules tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_json_string_leaf_uses_visible_text_protocol tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back`，9 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- Rust 自测：`cargo test --manifest-path rust/Cargo.toml`，71 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`，919 passed。
- 相关 scan_budget/记录保护命令：`uv run pytest tests/test_native_scope_index.py::test_build_native_note_tag_candidates_payload_includes_data_and_text_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_note_tag_candidates tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch91_note_tag_native_candidate_record_exists_and_tracks_contract`，5 passed。
- note_tag 记录保护命令：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，4 passed，134 deselected。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批修改生产 Python 和 Rust 原生代码，因此已执行全量 `uv run pytest`。剩余风险是公开 Note 标签命令尚未消费新 native 分支；本批用目标测试、相关 Note 标签行为测试、scan_budget 记录保护、Rust 门禁、类型检查、全量 Python 测试、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批派发只读子代理复核 Note 标签 native 最小契约、当前 Python 导出器字段、Rust source collector 复用边界和不应提前触碰的路径。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

子代理结论：本批可以成立，最小范围应是 `app/native_scope_index.py` 新增 Note payload builder，`rust/src/native_core/scope_index/` 新增 `note_tags.rs` 并接入 `scan_rule_candidates`，`tests/test_native_scope_index.py` 增加 native 契约测试；不要提前接 service、CLI、workflow、text_scope 或写回路径。

本地实现采纳该范围，并补充保持当前 `collect_note_tag_candidates` 的聚合语义：无值标签保留 `hit_count`，JSON 字符串外壳样本解成可见文本，样本最多 5 个并去重。

## 剩余风险

`export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules`、scope hash、text-scope rule hit、workflow gate、workspace 校验和写回协议仍未消费新 native 分支。公开命令层仍存在 Python Note 标签候选扫描事实来源，下一批需要用 native 薄适配收束。

Note 标签分支现在使用真实 `source_text_required_pattern` 计算 `translatable_hit_count`。如果用户配置使用 Rust regex 不支持但 Python re 支持的高级语法，本分支会显式失败；后续接入公开命令时需要在用户可见错误文案里说明该边界。

## 下一批入口

建议下一批进入 Note 标签扫描命令 native 薄适配接入：让 `export-note-tag-candidates` 优先消费 `build_native_note_tag_candidates_payload` 与 `scan_rule_candidates(note_tags)` 的候选摘要，同时保护现有 Agent JSON 报告字段、空规则确认和候选 hash 不漂移。
