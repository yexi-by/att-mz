# Rust Scope/Index Engine 批次 6BG 验收记录

## 本批范围

本批是 P1-B Note 标签支线入口审计，只新增入口审计保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

范围覆盖 Note 标签三条公开命令和当前候选事实来源：

- `export-note-tag-candidates`
- `validate-note-tag-rules`
- `import-note-tag-rules`
- 当前 scan_budget 表中的 Rust `scan_rule_candidates(note_tags)` 目标。
- 当前 `app/note_tag_text/` 下的 Python 候选、规则命中和文本提取路径。
- 当前 `app/native_quality.py` 与 `rust/src/native_core/note_sources.rs` 的 native Note 来源枚举路径。
- 当前 `app/native_scope_index.py` 与 `rust/src/native_core/scope_index/mod.rs` 尚未提供 Note 标签候选 payload 与 `note_tags` scan summary 的差距。

## 保护网

新增 `tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_classifies_current_python_scan_paths`：

- 固定 `export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules` 都属于 P1-B，scan budget 目标是 Rust `scan_rule_candidates(note_tags)`，插件源码 AST 扫描预算为 0。
- 固定 CLI 三个命令继续调用 service 公开入口。
- 固定 service 当前通过 `export_note_tag_candidates_file`、`build_note_tag_rule_records_from_import`、`NoteTagTextExtraction` 和 `note_tag_rule_scope_hash_for_text_rules` 完成导出、校验和导入。
- 固定当前候选导出仍由 `collect_note_tag_candidates` 调用 `collect_note_tag_sources` 与 `iter_note_tag_matches` 组合完成。
- 固定当前 `collect_note_tag_sources` 消费 `collect_native_note_tag_sources`，也就是 native Note source collector。
- 固定当前规则导入校验、文本提取、flow gate hash 和 text-scope rule hits 仍复用 `collect_note_tag_sources`、`iter_note_tag_matches` 或 `collect_note_tag_candidates`。
- 固定 `app/native_scope_index.py` 尚没有 `build_native_note_tag_candidates_payload`，`rust/src/native_core/scope_index/mod.rs` 尚没有 `note_tags` scan summary。
- 固定既有行为测试仍覆盖 Note 标签导出、校验、导入、工作区缺失提示、文本提取、JSON 字符串协议和地图事件 Note 标签规则。

新增 `tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定三条公开命令、当前 Python 候选路径、native source collector、缺失的 scope_index note_tags 候选入口、验证命令、临时验证例外和下一批入口。

## 实现说明

本批只审计并记录现状，不改变生产实现。

当前入口事实如下：

- `app/cli/commands/rules.py` 的三个 Note 标签命令调用 AgentToolkit service。
- `app/agent_toolkit/services/rule_validation.py::export_note_tag_candidates` 读取配置和游戏数据后调用 `export_note_tag_candidates_file`。
- `app/note_tag_text/exporter.py::collect_note_tag_candidates` 枚举 `collect_note_tag_sources`，再用 `iter_note_tag_matches` 统计候选。
- `app/note_tag_text/sources.py::collect_note_tag_sources` 已经消费 `collect_native_note_tag_sources`。
- `collect_native_note_tag_sources` 底层对应 `rust/src/native_core/note_sources.rs`，它负责扫描标准 data JSON 中的 `note` 字段来源。
- `validate-note-tag-rules` 和 `import-note-tag-rules` 当前通过 `build_note_tag_rule_records_from_import`、`NoteTagTextExtraction`、`note_tag_rule_scope_hash_for_text_rules` 和 `_validate_note_tag_rule_records_with_context` 完成规则命中、可写性和空规则确认。
- `app/text_scope/rule_hits.py::collect_note_tag_rule_hits` 当前仍用 `collect_note_tag_sources` 与 `iter_note_tag_matches` 展开规则命中。

本批确认：native Note source collector 不等同于 Rust Scope/Index Engine 的 `scan_rule_candidates(note_tags)` 候选事实来源。当前 `app/native_scope_index.py` 尚未提供 `build_native_note_tag_candidates_payload`，`rust/src/native_core/scope_index/mod.rs` 尚未输出 `note_tags` scan summary。

## 旧路径收束

本批不删除旧路径。当前需要保留并记录的旧 Python 事实路径包括：

- `collect_note_tag_candidates`
- `collect_note_tag_sources`
- `iter_note_tag_matches`
- `NoteTagTextExtraction`
- `note_tag_rule_scope_hash_for_text_rules`
- `collect_note_tag_rule_hits`

这些路径目前仍承担 Note 标签候选统计、规则校验、导入清理、空规则确认、text-scope rule hit 和写回前置检查相关职责。下一批应建立 Rust 候选入口最小契约，再决定哪些 Python 路径改成薄适配，哪些只保留为文本提取或写回协议辅助。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取。性能相关证据来自入口审计保护：

- scan_budget 表已经要求三条 Note 标签命令消费 Rust `scan_rule_candidates(note_tags)`，每个命令只允许一次候选扫描，插件源码 AST 扫描预算为 0。
- 机器可观察标记：Rust scan_rule_candidates(note_tags)。
- 当前实现只有 `collect_native_note_tag_sources` / `rust/src/native_core/note_sources.rs` 这条 native Note 来源枚举路径。
- 当前实现尚未提供 `build_native_note_tag_candidates_payload` 和 `note_tags` scan summary，因此 scan_budget 目标与当前生产实现之间存在明确差距。
- 该差距应在下一批 Note 标签 Rust 候选入口最小契约中收束。

## 验证结果

RED：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-090.md` 链接，以及 `docs/records/rust-scope-index/batches/batch-090.md` 尚不存在。

本批目标测试：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch90_note_tag_entry_audit_record_exists_and_tracks_contract
```

结果：2 passed。

相关 Note 标签行为回归：

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_note_tag_rule_validation_import_and_pending_export tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_prefix_read_for_translated_count tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_replaces_stale_existing_rule tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_blocks_missing_note_tag_rules tests/test_rmmz_note_nonstandard_data.py::test_note_tag_rules_extract_and_write_back_only_target_values tests/test_rmmz_note_nonstandard_data.py::test_note_tag_json_string_leaf_uses_visible_text_protocol tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back
```

结果：9 passed。

相关 scan_budget/记录保护：

```powershell
uv run pytest tests/test_scan_budget.py -k "note_tag"
```

结果：2 passed，134 deselected。

类型检查：

```powershell
uv run basedpyright
```

结果：0 errors，0 warnings，0 notes。

文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果 `NO_MATCH`。

```powershell
git diff --check
```

结果：exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。

本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标测试、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批派发只读子代理辅助复核 Note 标签三条公开命令、scan budget、native Note source collector、scope_index note_tags 缺口和下一批建议。子代理不修改文件、不运行全量 pytest；最终收束以本地测试和验证命令输出为准。

子代理结论：三条 Note 标签命令的 scan budget 已声明 Rust `scan_rule_candidates(note_tags)`，但当前生产实现还没有 Rust scope_index Note 标签候选入口；现有 Rust `note_sources.rs` 只是 note source collector，不等同于 rule candidate。后续候选聚合、规则命中、scope hash、text-scope rule hit 仍在 Python 路径中完成。下一批应进入 Note 标签 Rust 候选入口最小契约，避免把 note source collector 误当成 scope_index 候选事实来源。

## 剩余风险

当前 Note 标签支线仍没有 Rust Scope/Index Engine 的 `note_tags` 候选入口。虽然 Note 来源枚举已经使用 native `collect_native_note_tag_sources`，但候选统计、规则覆盖、scope hash、导入清理和 text-scope rule hit 仍由 Python 组合完成。

下一批需要建立 `build_native_note_tag_candidates_payload` 与 Rust `scan_rule_candidates(note_tags)` 最小契约，并用行为测试证明它能表达当前导出候选所需的文件模式、标签名、命中数、可翻译命中数、样本位置和样本文本。

## 下一批入口

建议下一批进入 Note 标签 Rust 候选入口最小契约：建立 native payload 与 Rust scan summary 的最小结构，使 `scan_rule_candidates(note_tags)` 能覆盖当前 `collect_note_tag_candidates` 的候选统计事实。
