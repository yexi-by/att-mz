# Rust Scope/Index Engine 批次 6CF 验收记录

## 本批范围

本批是 P1-B validate-event-command-rules native hit details 薄适配。本批修改生产代码，本批未修改 Rust 原生代码。

批次名称：P1-B validate-event-command-rules native hit details 薄适配。

本批承接 `docs/records/rust-scope-index/batches/batch-114.md` 的 native 契约补强，把 `validate-event-command-rules` 的报告命中统计和已保存译文前缀读取切到 Rust `scan_rule_candidates(event_commands)` 返回的 `rule_summaries` 与 `hit_details`。

本批目标：

- `validate-event-command-rules` 不再通过 `EventCommandTextExtraction.extract_all_text_with_rule_items` 构造规则命中报告。
- 已保存译文读取前缀不再通过 Python `_event_command_rule_prefixes` 遍历事件指令获得，而是消费 native `matched_command_location_paths`。
- 校验报告仍保留 `TextRules.should_translate_source_text`、写回协议预演和规则级 `hit_count`、`translated_count`、`writable_count`、`unwritable_count`。
- `export-event-commands-json` 与 `validate-event-command-rules` 都从 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 移出；`import-event-command-rules` 仍保留待复核状态。

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count`，2 failed。失败点分别是旧 `EventCommandTextExtraction.extract_all_text_with_rule_items` 和旧 `_event_command_rule_prefixes` 仍会被 `validate-event-command-rules` 调用。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_record_exists`，3 passed，1 failed。失败点为本记录尚不存在。

GREEN 目标测试：

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count`，2 passed。

目标测试可拆分为以下单测命令定位：

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule`
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count`
- `uv run pytest tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_tracks_current_boundary`
- `uv run pytest tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_record_exists`

## 改动范围

生产代码：

- `app/agent_toolkit/services/common.py`
- `app/agent_toolkit/services/rule_validation.py`
- `app/native_scope_index.py`
- `app/event_command_text/exporter.py`

新增或改造的核心 helper：

- `_build_native_event_command_rule_validation_context`
- `_event_command_rule_records_to_native_rules`
- `_ensure_native_event_command_rules_have_current_hits`
- `_event_command_translation_prefixes_from_native_rule_summaries`
- `build_native_event_command_data_files`

测试与契约：

- `tests/test_agent_toolkit_rule_import.py`
- `tests/scan_budget_contract.py`
- `tests/test_scan_budget.py`

文档：

- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-115.md`

## 旧路径收束

`validate-event-command-rules` 的报告命中统计不再调用 `EventCommandTextExtraction.extract_all_text_with_rule_items`。该旧提取类仍保留给尚未迁移的事件指令导入、正文提取和其他历史链路，但不再是规则校验报告的事实来源。

`app.agent_toolkit.services.rule_validation` 中的 `_event_command_rule_prefixes` 已删除。事件指令规则校验读取已保存译文时，前缀来自 native `rule_summaries[].matched_command_location_paths`。

`app/native_scope_index.py` 新增 `build_native_event_command_data_files`，供事件指令导出和规则校验共享标准 data 文件筛选逻辑，避免 `export-event-commands-json` 私有 helper 与 validate adapter 各自维护一套 data 文件事实。

## 外部契约变化

无公开 CLI 参数、Agent JSON 报告字段、SQLite schema、Rust native contract version、日志格式、README、Skill 或发布流程变化。

测试契约变化：

- `validate-event-command-rules` 的预算事实来源改为 `Rust scan_rule_candidates(event_commands) rule_summaries/hit_details`。
- `validate-event-command-rules` 从 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 移出。
- `import-event-command-rules` 仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中，下一批继续评估导入前覆盖检查和旧译文清理链路。

## 性能证据

本批把 `validate-event-command-rules` 的规则命中统计和前缀读取事实来源切到一次 Rust `scan_rule_candidates(event_commands)`：

- Rust `rule_summaries` 提供每组规则的 `matched_command_count`、`matched_command_location_paths` 和 `path_hit_counts`。
- Rust `hit_details` 提供逐叶子命中，用于构造报告中的 `TranslationItem` 和规则级命中统计。
- Python 只负责 JSON 载荷组装、类型收窄、`TextRules.should_translate_source_text` 过滤、写回协议预演和报告组装。

预算表保持 `candidate_scan_count = 1`、`plugin_source_ast_scan_count = 0`。本批不新增 Rust 扫描次数，也不引入 Python 全量事件指令遍历作为校验事实来源。

## 验证结果

- RED 行为测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count`，2 failed。
- GREEN 行为测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count`，2 passed。
- RED 记录保护：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_record_exists`，3 passed，1 failed，失败点为本记录尚不存在。
- GREEN 目标和记录保护：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_reports_hits_per_rule tests/test_agent_toolkit_rule_import.py::test_validate_event_command_rules_uses_prefix_read_for_translated_count tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch115_p1b_validate_event_command_rules_native_hit_details_adapter_record_exists`，4 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch115 or batch114 or batch113 or batch112 or batch111 or batch109 or batch108_p1b_budget_fact_source_review"`，14 passed，172 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-115.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 按用户最新目标，本批禁止运行全量 `uv run pytest`，实际未运行全量 `uv run pytest`。

## 审查处理

本批未使用子代理。主代理完成生产链路审计、RED/GREEN 行为测试、预算契约更新、计划索引和验收记录。

本批审查结论是：`validate-event-command-rules` 已具备独立 native hit details 薄适配，下一步应把事件指令导入前覆盖检查、旧译文范围计算和删除备份链路纳入同一命令族评估，避免导入路径继续维护第二事实来源。

## 剩余风险

按用户最新目标，本批禁止运行全量 `uv run pytest`。剩余风险是全仓非目标路径未在本批用全量回归覆盖；本批用行为测试、scan_budget 保护、类型检查、文档敏感搜索和空白检查降低回退风险。

`import-event-command-rules` 仍保留 Python 事件指令规则导入前覆盖检查和旧译文清理路径，下一批必须继续处理。`EventCommandTextExtraction` 仍保留在仓库内，不能被误判为事件指令规则校验仍依赖旧事实来源。

## 下一批入口

下一批入口：P1-B import-event-command-rules native hit details 适配评估。

建议下一批直接把 `import-event-command-rules` 作为完整命令族处理：审计导入前覆盖检查、规则替换事务、旧译文范围计算、备份和删除路径，判断是否能复用本批 `_build_native_event_command_rule_validation_context` 或需要新增导入专用 native adapter。
