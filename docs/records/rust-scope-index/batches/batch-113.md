# Rust Scope/Index Engine 批次 6CD 验收记录

## 本批范围

本批是 P1-B validate-event-command-rules native hit details 适配评估。本批未修改生产代码，本批未修改 Rust 原生代码。

本批承接 `docs/records/rust-scope-index/batches/batch-112.md`：`export-event-commands-json` 已消费 Rust `samples_by_code`，但 `validate-event-command-rules` 和 `import-event-command-rules` 仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中。本批只评估 `validate-event-command-rules` 能否直接切到 native `hit_details`，不切换生产链路。

审计对象：

- `RuleValidationAgentMixin.validate_event_command_rules`
- `_event_command_rule_prefixes`
- `_validate_event_command_rule_records_with_context`
- `EventCommandTextExtraction.extract_all_text_with_rule_items`
- `build_event_command_rule_records_from_import`
- Rust `scan_rule_candidates(event_commands)` 的 `hit_details`

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_tracks_current_boundaries tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_record_exists`，1 passed，1 failed。

失败点符合预期：`docs/records/rust-scope-index/batches/batch-113.md` 尚不存在；边界测试已证明当前源码仍满足本批评估前提。

目标测试可拆分为以下单测命令定位：

- `uv run pytest tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_tracks_current_boundaries`
- `uv run pytest tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_record_exists`

## 评估结论

结论：`validate-event-command-rules` 暂不应在本批直接切换到 native `hit_details`，下一批应先补 P1-B validate-event-command-rules native hit details 最小契约。

原因：

- Rust `scan_rule_candidates(event_commands)` 已输出 `hit_details`，能表达规则路径命中的 `location_path`、`original_text`、`path_template` 和 `rule_index`。
- 当前 `validate_event_command_rules` 仍先通过 `build_event_command_rule_records_from_import` 校验外部 JSON 规则，并且该构造链路仍使用 Python `iter_all_commands`、`resolve_event_command_leaves` 和 `expand_rule_to_leaf_paths` 来确认 command 命中与路径命中。
- 当前 `validate_event_command_rules` 还通过 `_event_command_rule_prefixes` 和 `read_translated_items_by_prefixes` 读取已保存译文，前缀计算仍使用 Python `iter_all_commands` 和 `command_matches_filters`。
- 当前 `_validate_event_command_rule_records_with_context` 依赖 `EventCommandTextExtraction.extract_all_text_with_rule_items` 生成规则组命中项，随后执行 `_collect_write_protocol_unwritable_items` 和 `_preview_event_command_write_back`。
- Python 提取链路在生成命中项时还会应用 `TextRules.should_translate_source_text`；native `hit_details` 当前可以提供原文命中，但尚未固定一组校验专用契约来替代 Python 的规则记录构造、规则级 path 命中计数、文本规则过滤后的 extractable 统计和译文前缀读取。

因此，本批只固定边界：`validate-event-command-rules` 仍是待复核预算目标，不能因为已有 `hit_details` 就记录为已迁移事实。

## 旧路径收束

本批不删除旧路径，也不切换公开 CLI 或 Agent 工具箱生产事实来源。

当前仍保留的旧路径：

- `build_event_command_rule_records_from_import` 仍用 Python `iter_all_commands` 校验外部规则。
- `_event_command_rule_prefixes` 仍用 Python `iter_all_commands` 计算已保存译文路径前缀。
- `EventCommandTextExtraction.extract_all_text_with_rule_items` 仍用 Python `iter_all_commands`、`command_matches_filters`、`resolve_event_command_leaves`、`expand_rule_to_leaf_paths` 和 `jsonpath_to_event_command_location_path` 展开命中项。
- `_preview_event_command_write_back` 仍保留，用于写回协议预演。

## 外部契约变化

无公开 CLI 参数、Agent JSON 报告、SQLite schema、Rust API、native contract version、日志格式、目录结构、README、Skill 或发布流程变化。

测试契约变化：新增 6CD 评估保护测试和记录保护，防止后续把 Rust `hit_details` 能力误读成 `validate-event-command-rules` 已迁移完成。

预算契约保持不变：

- `export-event-commands-json` 已移出 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。
- `validate-event-command-rules` 仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。
- `import-event-command-rules` 仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。

## 性能证据

本批未新增运行时扫描，性能证据来自静态链路审计：

- `validate-event-command-rules` 当前至少在规则记录构造、译文前缀读取和规则命中提取三个位置可见 Python 事件指令遍历。
- Rust `hit_details` 已覆盖命中明细的基础字段，但未固定校验链路需要的最小契约，因此不能把 `validate-event-command-rules` 的 `authoritative_source` 改为已迁移事实。
- 下一批补强 native 校验契约后，才能用行为测试证明校验报告的 `hit_count`、`translated_count`、`writable_count`、`unwritable_count` 和规则级 details 可以脱离旧 Python 全量遍历。

## 验证结果

- RED 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_tracks_current_boundaries tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_record_exists`，1 passed，1 failed，失败点为本记录尚不存在。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_tracks_current_boundaries tests/test_scan_budget.py::test_batch113_p1b_validate_event_command_rules_native_hit_details_evaluation_record_exists`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch113 or batch112 or batch111 or batch109 or batch108_p1b_budget_fact_source_review"`，10 passed，172 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-113.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批未使用子代理。主代理完成当前源码链路审计、RED 测试、预算边界保护、计划索引和验收记录。

本批审查结论是：native `hit_details` 已经是校验迁移的基础，但生产校验链路还缺一层稳定的校验专用 native/Python 适配契约，不能直接用现有 `hit_details` 替换整个 `validate-event-command-rules`。

## 剩余风险

本批按临时例外未跑全量 `uv run pytest`，全仓非本批路径仍需在目标完成收尾、准备提交或用户明确要求时用全量测试确认。

`validate-event-command-rules` 和 `import-event-command-rules` 仍是待复核预算目标，事件指令规则校验和导入仍可触发 Python 事件指令遍历。下一批需要用 RED/GREEN 先固定 native 最小契约，再考虑生产薄适配。

## 下一批入口

下一批入口：P1-B validate-event-command-rules native hit details 最小契约补强。

建议下一批补强 Rust event_commands scan summary 或 Python native adapter，使校验链路可以稳定获得规则级 command 命中、path 命中、命中项明细和可用于译文前缀读取的 location prefixes；随后再推进 `validate-event-command-rules` 薄适配。
