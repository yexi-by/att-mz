# Rust Scope/Index Engine 批次 6CB 验收记录

## 本批范围

本批是 P1-B 事件指令候选薄适配接入评估。本批未修改生产代码，本批未修改 Rust 原生代码。

本批承接 `docs/records/rust-scope-index/batches/batch-110.md` 的最小契约：Rust `scan_rule_candidates(event_commands)` 已能输出 `scan_summary["event_commands"]`，其中包含 `samples_by_code`、`sample_count` 和规则 `hit_details`。本批目标是固定三条公开命令的薄适配先后顺序，而不是直接改生产链路。

本批审计的公开命令：

- `export-event-commands-json`
- `validate-event-command-rules`
- `import-event-command-rules`

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_tracks_first_adapter_boundary tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_record_exists`，1 passed，1 failed。

失败点符合预期：`docs/records/rust-scope-index/batches/batch-111.md` 尚不存在；静态评估边界测试已经证明当前源码仍满足本批评估前提。

目标测试可拆分为以下单测命令定位：

- `uv run pytest tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_tracks_first_adapter_boundary`
- `uv run pytest tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_record_exists`

## 评估结论

结论：下一批应按“导出优先”推进，先做 P1-B `export-event-commands-json` native samples 薄适配。

原因：

- `export_event_commands_json_file` 当前只依赖 Python `iter_all_commands` 枚举事件指令、按 command code 过滤、按参数 JSON 去重并写出样本；6CA 的 `scan_summary["event_commands"]["samples_by_code"]` 和 `sample_count` 已覆盖这段核心事实。
- `app/application/handler.py::export_event_commands_json` 和 `app/agent_toolkit/services/workspace.py::prepare_agent_workspace` 都调用 `export_event_commands_json_file`，因此先替换导出 helper 可以同时服务 CLI 导出和工作区生成。
- `validate-event-command-rules` 当前不仅要构造规则，还要读取已保存译文前缀、运行 `EventCommandTextExtraction`、统计每条规则命中、调用 `_preview_event_command_write_back` 做写回协议预演；它需要更多 native 明细和 Python 适配，不适合作为第一刀。
- `import-event-command-rules` 当前还要处理 `build_event_command_rule_records_from_import`、旧规则 stale prefix 清理、`event_command_rule_scope_hash_for_command_codes` 空规则确认和数据库事务；它依赖校验链路，适合在导出与校验适配稳定后推进。

本批固定的当前事实来源：

- `export_event_commands_json_file` 仍使用 Python `iter_all_commands`。
- `_validate_event_command_rule_records_with_context` 仍使用 `EventCommandTextExtraction`、`_collect_write_protocol_unwritable_items` 和 `_preview_event_command_write_back`。
- `AgentToolkitService.validate_event_command_rules` 仍使用 `build_event_command_rule_records_from_import` 和 `read_translated_items_by_prefixes`。
- `ApplicationHandler.import_event_command_rules` 仍使用 `build_event_command_rule_records_from_import`、`event_command_rule_scope_hash_for_command_codes` 和 `replace_event_command_text_rules`。

## 旧路径收束

本批不删除旧路径，也不切换公开 CLI 或 Agent 工作区生产事实来源。

三个事件指令公开命令仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中，`authoritative_source` 仍应以 `待复核:` 开头，并指向目标 `Rust scan_rule_candidates(event_commands)`。

## 外部契约变化

无公开 CLI 参数、Agent JSON 报告、SQLite schema、Rust API、native contract version、日志格式、目录结构、README、Skill 或发布流程变化。

测试契约变化：新增 6CB 评估保护测试和记录保护，防止后续把 `samples_by_code` 能力误读成三条事件指令公开命令都已迁移完成。

## 性能证据

本批未新增运行时扫描，性能证据来自静态链路审计：

- 导出 helper 的待替换重活是一次 `iter_all_commands` 全量事件指令枚举和样本去重。
- 6CA native 输出已提供 `samples_by_code` 和 `sample_count`，下一批可以把导出 helper 的样本生成收口到 Rust。
- 校验与导入还会触发规则记录构造、命中提取、写回协议预演、翻译前缀读取和数据库事务，直接切换风险较高，应拆到后续批次。

## 验证结果

- RED 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_tracks_first_adapter_boundary tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_record_exists`，1 passed，1 failed，失败点为本记录尚不存在。
- GREEN 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_tracks_first_adapter_boundary tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_record_exists`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch111 or batch110 or batch108_p1b_budget_fact_source_review"`，6 passed，172 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-111.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批启动过只读子代理并行审计事件指令三条公开命令的薄适配风险，但子代理未在收尾前返回最终报告，已关闭，未作为本批完成依据。主代理负责本地源码核对、测试保护、计划索引、验收记录和最终判断。

主代理本地审计结论是：先接 `export-event-commands-json` 的 native samples 薄适配，暂不直接切 `validate-event-command-rules` 和 `import-event-command-rules`。

## 剩余风险

本批按临时例外未跑全量 `uv run pytest`，全仓非本批路径仍需在目标完成收尾、准备提交或用户明确要求时用全量测试确认。

事件指令公开命令仍未切换到 native 候选事实来源；下一批需要用行为测试证明 `export_event_commands_json_file` 的输出 JSON、样本去重和 command count 与旧 Python 行为等价。

校验和导入链路仍有 Python `EventCommandTextExtraction`、`build_event_command_rule_records_from_import` 和 `event_command_rule_scope_hash_for_command_codes` 残留，后续需要继续拆分。

## 下一批入口

建议下一批进入 P1-B export-event-commands-json native samples 薄适配：新增 helper 从 `GameData.data` 构造 `build_native_event_command_candidates_payload`，调用 `scan_native_rule_candidates`，用 `samples_by_code` 写出原有 JSON 格式，并用测试固定命令输出、去重数量和工作区生成复用路径。
