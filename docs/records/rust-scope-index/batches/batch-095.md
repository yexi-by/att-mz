# Rust Scope/Index Engine 批次 6BL 验收记录

## 本批范围

本批是 Note 标签导入后旧 handler/common 收束评估。范围只覆盖旧 `TranslationHandler.import_note_tag_rules` 与 `app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context` 的边界审计和保护记录，本批未修改生产代码，本批未修改 Rust 原生代码。

本批触及以下文件：

- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-095.md`

本批不迁移 `TranslationHandler.import_note_tag_rules`、`_validate_note_tag_rules_with_context`、workspace manifest 校验、`app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules`、text-scope rule hit、数据库 schema、空规则确认 hash 或写回协议路径。

## 保护网

新增 `tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_boundary_is_audited`：

- 固定公开 `import-note-tag-rules` CLI 仍走 `AgentToolkitService.import_note_tag_rules`，不走 `TranslationHandler`。
- 固定 `AgentToolkitService.import_note_tag_rules` 已消费 `build_note_tag_rule_records_from_native_candidates`，不再调用 `build_note_tag_rule_records_from_import`。
- 固定 `TranslationHandler.import_note_tag_rules` 仍使用 `load_note_tag_rule_import_file` 和 `build_note_tag_rule_records_from_import`，并保留 `ensure_empty_rule_confirmed`、`_translation_paths_matching_note_rules`、`NoteTagTextExtraction`、`RuleImportUnitOfWork`、`replace_note_tag_text_rules` 与 `note_tag_rule_scope_hash_for_text_rules`。
- 固定 `_validate_note_tag_rules_with_context` 仍使用 `build_note_tag_rule_records_from_import` 并继续进入 `_validate_note_tag_rule_records_with_context`。
- 固定 `_validate_workspace_note_tag_rules` 继续复用 `_validate_note_tag_rules_with_context`。
- 固定旧 handler 旧译文清理测试 `test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup` 与 workspace Note 规则缺失测试 `test_validate_agent_workspace_blocks_missing_note_tag_rules` 仍存在。

新增 `tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_boundary_is_audited tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-095.md`，以及本批记录不存在。

## 审计结论

公开 `import-note-tag-rules` 命令已经通过 `app/cli/commands/rules.py::run_import_note_tag_rules_command` 调用 `AgentToolkitService.import_note_tag_rules`。该服务入口已在批次 6BK 接入 `build_note_tag_rule_records_from_native_candidates`，因此公开 CLI 的导入前规则命中检查已经消费 native 候选摘要。

`TranslationHandler.import_note_tag_rules` 当前不是公开 `import-note-tag-rules` CLI 的必经入口；它是旧应用服务和测试夹具路径，输入形态仍是 `input_path: Path`，并且保留比 AgentToolkit service 更细的 `changed_rule_count` / `removed_rule_count` 旧译文清理条件。本批不把它并入 native helper，避免把旧应用服务语义和当前公开 Agent JSON 导入语义混在同一批。

`_validate_note_tag_rules_with_context` 是工作区已加载上下文校验 helper。它的直接调用方是 `app/agent_toolkit/services/workspace.py::_validate_workspace_note_tag_rules`，用于复用工作区已经加载的 `GameData`、`TextRules` 和已保存译文定位集合。本批不迁它，避免在工作区校验批次外引入新的 native 候选扫描和报告事实来源变化。

## 旧路径收束

本批明确保留以下旧路径：

- `TranslationHandler.import_note_tag_rules`
- `app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context`
- `app/agent_toolkit/services/workspace.py::_validate_workspace_note_tag_rules`
- `build_note_tag_rule_records_from_import`

这些路径继续服务旧应用服务、测试夹具和工作区已加载上下文校验。后续如要迁移，必须拆成独立批次，分别证明旧 handler 的文件输入/清理条件不漂移，以及 workspace 校验不会引入重复全量扫描或报告字段变化。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust 原生代码、发布流程或用户可见文案变化。

本批只新增静态保护和验收记录，不改变运行时行为。

## 性能证据

本批未新增运行时扫描。性能证据来自静态保护：

- 公开 `import-note-tag-rules` 服务入口已固定为 native 候选 helper。
- 旧 handler/common 路径被明确记录为未迁移边界，避免后续误把它们当作已完成的 native 迁移路径。
- workspace common helper 的保留原因是复用已加载上下文；若下一批迁移，需要单独证明不会增加无意义重复扫描。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_boundary_is_audited tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_record_exists_and_tracks_contract`，2 failed。
- 目标测试和记录保护命令：`uv run pytest tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_boundary_is_audited tests/test_scan_budget.py::test_batch95_note_tag_legacy_handler_common_record_exists_and_tracks_contract`，结果 2 passed。
- 相关 Note 标签记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，结果 12 passed，134 deselected。
- 相关行为边界验证：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_blocks_missing_note_tag_rules`，结果 3 passed。
- 类型检查：`uv run basedpyright`，结果 0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，结果退出码 0；Git 仅提示若干已有工作区文件下次写入时会从 LF 转为 CRLF。
- 本批未修改生产代码。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标测试、相关 scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批派发只读子代理复核旧 `TranslationHandler.import_note_tag_rules`、common helper 和 workspace 调用边界。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

本地结论是：当前批次不迁移旧 handler/common。公开 CLI/service 路径已在 6BJ/6BK 迁移；旧 handler/common 需要分别进入更小的后续批次或在支线收束审计中明确保留退出条件。

## 剩余风险

旧 handler/common、scope hash、text-scope rule hit、workflow gate、workspace 校验和写回协议仍未消费新 native 前置校验函数。它们是否继续迁移需要后续批次逐项评估，不能用本批审计结论替代行为迁移。

## 下一批入口

建议下一批进入 Note 标签支线收束回归审计：汇总 Note 标签导出、公开校验、公开导入、旧 handler/common、flow gate、text-scope、workspace 和写回路径的剩余 Python 扫描边界，决定下一阶段是继续迁移 scope hash/text-scope，还是进入 P1-B Note 标签阶段收束。
