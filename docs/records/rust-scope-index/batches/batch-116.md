# Rust Scope/Index Engine 批次 6CG 验收记录

## 本批范围

本批是 P1-B import-event-command-rules native hit details 薄适配。本批修改生产代码，本批未修改 Rust 原生代码。

批次名称：P1-B import-event-command-rules native hit details 薄适配。

本批承接 `docs/records/rust-scope-index/batches/batch-115.md`，把事件指令导入链路从 Python 事件遍历和旧 prefix helper 切到 Rust `scan_rule_candidates(event_commands)` 的 `rule_summaries` 与 `hit_details`。本批不减少交付内容：导入前覆盖检查、旧译文范围、备份、删除和预算状态同批处理。

本批目标：

- `import-event-command-rules` 不再用 `build_event_command_rule_records_from_import` 执行 Python `iter_all_commands` 覆盖检查。
- 新增 `build_event_command_rule_records_from_import_shape`，只解析外部 JSON 形状、合并规则和标准化路径；当前游戏命中验证交给 native validation。
- 新增 `app/event_command_text/native_validation.py`，集中提供 `build_native_event_command_rule_validation_context`、`translation_prefixes_by_index`、严格新规则校验和宽松旧规则前缀读取。
- handler 导入清理旧译文时不再调用旧 `_event_command_rule_prefixes`，改用 `_event_command_rule_prefixes_by_key` 消费 native per-rule prefixes。
- `import-event-command-rules` 从 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 移出。

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup`，1 failed。失败点为 `build_event_command_rule_records_from_import` 调用 Python `iter_all_commands`，被测试中的 `forbidden_iter_all_commands` 捕获。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_record_exists`，1 passed，2 failed。失败点分别为旧 helper 字符串断言误伤新 helper 名称、本记录尚不存在。

GREEN 目标测试：

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup`，1 passed。

目标测试可拆分为以下单测命令定位：

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup`
- `uv run pytest tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_tracks_current_boundary`
- `uv run pytest tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_record_exists`

## 改动范围

生产代码：

- `app/event_command_text/importer.py`
- `app/event_command_text/__init__.py`
- `app/event_command_text/native_validation.py`
- `app/agent_toolkit/services/common.py`
- `app/agent_toolkit/services/rule_validation.py`
- `app/application/handler.py`

测试与契约：

- `tests/test_agent_toolkit_rule_import.py`
- `tests/scan_budget_contract.py`
- `tests/test_scan_budget.py`

文档：

- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-116.md`

## 旧路径收束

`import-event-command-rules` 不再通过 `build_event_command_rule_records_from_import` 触发 Python `iter_all_commands`、`resolve_event_command_leaves` 和 `expand_rule_to_leaf_paths` 作为当前游戏覆盖检查。

旧 `TranslationHandler._event_command_rule_prefixes` 已删除。导入路径使用 `build_native_event_command_rule_validation_context` 的 `translation_prefixes_by_index`，再由 `_event_command_rule_prefixes_by_key` 按规则稳定键整理旧译文清理范围。

`EventCommandTextExtraction` 仍保留给尚未下线的事件指令正文提取和历史测试，但不再作为 validate/import 两条规则命令的事实来源。

## 外部契约变化

无公开 CLI 参数、Agent JSON 字段、SQLite schema、Rust native contract version、日志格式、README、Skill 或发布流程变化。

测试契约变化：

- `import-event-command-rules` 的预算事实来源改为 `Rust scan_rule_candidates(event_commands) rule_summaries/hit_details`。
- `import-event-command-rules` 从 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 移出。
- 事件指令 P1-B 三条命令 `export-event-commands-json`、`validate-event-command-rules`、`import-event-command-rules` 均已不再是待复核预算目标。

## 性能证据

本批把事件指令导入的当前游戏命中验证和旧译文清理范围收口到 native：

- 新规则严格调用 native validation，要求 command 和 path 仍命中当前游戏。
- 旧规则清理调用同一 native validation，但使用 `require_command_hits=False` 与 `require_path_hits=False`，只读取仍可定位的 command prefixes；旧路径过期不会阻止导入新规则。
- Python 只负责外部 JSON 解析、规则键比较、数据库事务、备份和删除。

预算表保持 `candidate_scan_count = 1`、`plugin_source_ast_scan_count = 0`，不新增 Python 全量事件指令遍历。

## 验证结果

- RED 行为测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup`，1 failed。
- GREEN 行为测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup`，1 passed。
- RED 记录保护：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_record_exists`，1 passed，2 failed。
- GREEN 目标和记录保护：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_event_command_rules_uses_native_hit_details_for_stale_cleanup tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch116_p1b_import_event_command_rules_native_hit_details_adapter_record_exists`，3 passed。
- 事件指令 validate/import 相关行为测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count tests/test_agent_toolkit_rule_import.py::test_import_empty_event_command_rules_requires_explicit_empty_confirmation tests/test_agent_toolkit_rule_import.py::test_import_empty_event_command_rules_records_cli_code_scope`，4 passed。
- 事件指令导出/导入/旧提取边界测试：`uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples tests/test_event_command_text.py::test_event_command_json_export_uses_configured_command_codes tests/test_event_command_text.py::test_mv_event_command_json_export_uses_engine_default_356 tests/test_event_command_text.py::test_event_command_rule_import_extracts_and_writes_back tests/test_event_command_text.py::test_event_command_extraction_rejects_stale_command_match tests/test_event_command_text.py::test_event_command_extraction_rejects_stale_path_template tests/test_event_command_text.py::test_event_command_extraction_rejects_path_changed_to_non_string_leaf`，7 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch116 or batch115 or batch114 or batch113 or batch112 or batch111 or batch109 or batch108_p1b_budget_fact_source_review"`，16 passed，172 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-115.md`、`docs/records/rust-scope-index/batches/batch-116.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 按用户当前目标，本批禁止运行全量 `uv run pytest`，实际未运行全量 `uv run pytest`。

## 审查处理

本批未使用子代理。主代理完成导入链路审计、RED/GREEN 行为测试、native validation 模块抽取、handler 导入路径迁移、预算契约更新、计划索引和验收记录。

本批审查结论是：事件指令规则命令族已经完成 export、validate、import 三条 P1-B 命令的 native 候选事实迁移。下一批应进入插件参数规则 validate/import 命令族，不能继续在事件指令支线拆小批次。

## 剩余风险

按用户当前目标，本批禁止运行全量 `uv run pytest`。剩余风险是全仓非目标路径未在本批用全量回归覆盖；本批使用行为测试、scan_budget/记录保护、类型检查、文档敏感搜索和空白检查覆盖本批边界。

空事件指令规则的 scope hash 仍由现有 `event_command_rule_scope_hash_for_command_codes` 计算。该路径服务于空规则确认范围，不再参与非空导入规则命中统计；后续 P1-B 总收束时需要统一复核事件指令支线是否还存在应下线的旧范围哈希实现。

## 下一批入口

下一批入口：P1-B 插件参数规则 validate/import 迁移评估与最小契约。

建议下一批把 `validate-plugin-rules` 和 `import-plugin-rules` 作为同一命令族推进：审计 `PluginTextExtraction`、插件参数候选规则、导入清理旧译文和空规则确认范围，必要时补 Rust `plugin_config` 候选契约，并同批给出是否能直接薄适配的结论。
