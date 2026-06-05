# Rust Scope/Index Engine 批次 6BK 验收记录

## 本批范围

本批是 Note 标签规则导入 native 候选接入。范围只覆盖公开 `import-note-tag-rules` 命令对应的 `AgentToolkitService.import_note_tag_rules` 导入前规则命中检查，让它复用 `app/native_note_tag_scan.py::build_note_tag_rule_records_from_native_candidates` 与 Rust `scan_rule_candidates(note_tags)`。

本批触及以下文件：

- `app/agent_toolkit/services/rule_validation.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-094.md`

本批不迁移 `TranslationHandler.import_note_tag_rules`、`app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context`、`app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules`、workspace manifest 校验、text-scope rule hit、数据库 schema、空规则确认 hash 或写回协议路径。

## 保护网

新增 `tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan`：

- monkeypatch `app.agent_toolkit.services.rule_validation.build_note_tag_rule_records_from_import` 为报错函数。
- 调用公开服务方法 `import_note_tag_rules`。
- 断言报告仍返回 `ok`。
- 断言 `file_count`、`tag_count` 和数据库保存的 `NoteTagTextRuleRecord` 保持旧导入语义。

新增 `tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_contract_exists`：

- 固定计划表链接本批记录。
- 固定 `import_note_tag_rules` 调用 `build_note_tag_rule_records_from_native_candidates`，不再直接调用 `build_note_tag_rule_records_from_import`。
- 固定 `import_note_tag_rules` 仍保留 `ensure_empty_rule_confirmed`、旧译文前缀读取、`_translation_paths_matching_note_rules`、`NoteTagTextExtraction`、`RuleImportUnitOfWork`、`replace_note_tag_text_rules`、规则审查状态更新和 `note_tag_rule_scope_hash_for_text_rules`。
- 固定 `TranslationHandler.import_note_tag_rules` 和 common workspace helper 仍保留 `build_note_tag_rule_records_from_import`，避免本批扩大到旧 handler 与 workspace 已加载上下文校验。

新增 `tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_contract_exists tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_record_exists_and_tracks_contract
```

结果：3 failed。失败点分别是 `import-note-tag-rules` 仍调用旧 Python `build_note_tag_rule_records_from_import`，计划表缺少 `docs/records/rust-scope-index/batches/batch-094.md`，以及本批记录不存在。

## 实现说明

`app/agent_toolkit/services/rule_validation.py::import_note_tag_rules` 改为调用 `build_note_tag_rule_records_from_native_candidates`：

- 规则文件解析仍由 `parse_note_tag_rule_import_text` 完成。
- 规则文件名、标签名、机器协议标签和精确地图规则语义继续由 `app/native_note_tag_scan.py` 统一校验。
- native helper 内部继续调用 `collect_native_note_tag_candidate_details` 读取 Rust `scan_rule_candidates(note_tags)` 候选明细。
- 导入前命中检查使用 native 候选摘要中的 `value_hit_count` 和 `translatable_hit_count`。
- 构造出的 `NoteTagTextRuleRecord` 继续交给后续旧译文清理、事务替换和审查状态逻辑。

## 旧路径收束

本批只迁移 `AgentToolkitService.import_note_tag_rules` 的导入前规则命中检查。以下路径继续保留：

- `NoteTagTextExtraction` 继续负责导入后新规则实际命中路径计算，用于清理旧译文。
- `_translation_paths_matching_note_rules` 继续按旧规则定位已保存译文。
- `RuleImportUnitOfWork`、`replace_note_tag_text_rules`、`delete_rule_review_state` 和 `replace_rule_review_state` 继续保持导入事务边界。
- `ensure_empty_rule_confirmed` 和 `note_tag_rule_scope_hash_for_text_rules` 继续保持空规则确认与空规则 hash 语义。
- `TranslationHandler.import_note_tag_rules` 和 `app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context` 仍使用 `build_note_tag_rule_records_from_import`。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema 或 Rust 原生代码变化。

`import-note-tag-rules` 的可观察报告字段保持：

- `summary.file_count`
- `summary.tag_count`
- `summary.deleted_translation_items`
- `summary.deleted_translation_backup_path`
- `details.rules[].file_name`
- `details.rules[].tag_names`

## 性能证据

本批把 `import-note-tag-rules` 的导入前规则命中检查从 Python `build_note_tag_rule_records_from_import` 切到 native Note 标签候选摘要。该路径不再在规则构建阶段重复调用 Python `collect_note_tag_sources` + `iter_note_tag_matches` 做每条标签的命中检查。

服务级保护测试通过 monkeypatch 旧 Python 记录构建函数为报错函数，证明公开导入命令不再调用旧前置扫描函数。

后续 `NoteTagTextExtraction` 仍会执行一次实际提取，用于计算新规则命中路径并清理旧译文；这是导入事务语义所需的事实来源，不属于本批要删除的前置候选扫描。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_contract_exists tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_record_exists_and_tracks_contract`，3 failed。
- 目标测试和记录保护命令：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_contract_exists tests/test_scan_budget.py::test_batch94_note_tag_import_native_candidate_record_exists_and_tracks_contract`，结果 3 passed。
- 相关 Note 标签回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_note_tag_rule_validation_import_and_pending_export tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_replaces_stale_existing_rule tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_keeps_precise_map_file_scope tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back tests/test_scan_budget.py -k "note_tag"`，结果 17 passed，134 deselected。
- 类型检查：`uv run basedpyright`，结果 0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`。
- Diff 空白检查：`git diff --check`。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标测试、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批派发只读子代理复核 `import-note-tag-rules` 调用链、native helper 复用方式、必须保持不变的导入事务和不应触碰的旧路径。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

本地实现采纳本批最小边界：只迁公开导入命令的前置候选命中检查，不迁旧 handler、workspace helper、flow gate、text-scope rule hit、数据库或写回路径。

## 剩余风险

`TranslationHandler.import_note_tag_rules`、common workspace helper、scope hash、text-scope rule hit、workflow gate、workspace 校验和写回协议仍未消费新 native 前置校验函数。下一批需要评估旧 handler/common 是否继续作为兼容边界保留，或进入独立迁移批次。

Note 标签 native 分支使用真实 `source_text_required_pattern` 计算 `translatable_hit_count`。如果用户配置使用 Rust regex 不支持但 Python re 支持的高级语法，规则导入会显式失败；这是本批延续 batch 91/92/93 的显式错误边界。

## 下一批入口

建议下一批进入 Note 标签导入后旧 handler/common 收束评估：审计 `TranslationHandler.import_note_tag_rules` 和 `_validate_note_tag_rules_with_context` 是否需要迁移到 native 候选 helper，或明确保留为旧兼容/已加载上下文边界。
