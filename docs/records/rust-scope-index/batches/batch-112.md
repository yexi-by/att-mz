# Rust Scope/Index Engine 批次 6CC 验收记录

## 本批范围

本批是 P1-B `export-event-commands-json` native samples 薄适配。本批修改生产代码，本批未修改 Rust 原生代码。

批次名称：P1-B export-event-commands-json native samples 薄适配。

本批只处理事件指令导出 helper，不切换 `validate-event-command-rules` 和 `import-event-command-rules`。导出入口仍是 `export_event_commands_json_file`，公开 CLI 参数、Agent 工作区调用点和输出 JSON 形状保持不变。

本批目标：

- 从 `GameData.data` 取地图、公共事件和敌群 data 文件，构造 `build_native_event_command_candidates_payload`。
- 调用 `scan_native_rule_candidates`，读取 `scan_summary["event_commands"]` 下的 `samples_by_code` 和 `sample_count`。
- 用 Rust 返回的样本写回原来的 `{ "357": [[...]] }` JSON 结构，并保留每个请求编码的空数组。
- 把 `export-event-commands-json` 从 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 移出；`validate-event-command-rules` 和 `import-event-command-rules` 仍保留待复核状态。

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples`，1 failed。失败点是 `app.event_command_text.exporter` 尚未暴露并调用 `scan_native_rule_candidates`，证明当前导出仍未接入 native samples。
- `uv run pytest tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_record_exists`，1 passed，1 failed。失败点是本记录尚不存在，生产边界测试已能固定当前适配要求。

GREEN 目标测试：

- `uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples tests/test_event_command_text.py::test_event_command_json_export_uses_configured_command_codes tests/test_event_command_text.py::test_mv_event_command_json_export_uses_engine_default_356`，3 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_record_exists`，记录保护覆盖本批计划索引、生产边界和预算状态。

目标测试可拆分为以下单测命令定位：

- `uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples`
- `uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_configured_command_codes`
- `uv run pytest tests/test_event_command_text.py::test_mv_event_command_json_export_uses_engine_default_356`
- `uv run pytest tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_tracks_current_boundary`
- `uv run pytest tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_record_exists`

## 改动范围

生产代码：

- `app/event_command_text/exporter.py`

测试与契约：

- `tests/test_event_command_text.py`
- `tests/scan_budget_contract.py`
- `tests/test_scan_budget.py`

文档：

- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-112.md`

## 旧路径收束

`export_event_commands_json_file` 不再调用 Python `iter_all_commands` 来枚举全量事件指令、按参数 JSON 去重和聚合样本。

旧 Python 路径仍保留给事件指令规则校验、导入、正文提取和写回相关链路使用：

- `validate-event-command-rules` 仍通过 `EventCommandTextExtraction`、已保存译文前缀读取和写回协议预演完成规则校验。
- `import-event-command-rules` 仍通过 `build_event_command_rule_records_from_import`、`event_command_rule_scope_hash_for_command_codes` 和数据库替换链路完成导入。

## 外部契约变化

无公开 CLI 参数、Agent JSON 报告、SQLite schema、Rust API、native contract version、日志格式、目录结构、README、Skill 或发布流程变化。

输出文件契约不变：`export-event-commands-json` 仍写出按事件指令编码分组的 JSON 对象，值为参数数组样本列表；未命中的请求编码仍保留空数组。

测试契约变化：

- `export-event-commands-json` 的预算事实来源改为 `Rust scan_rule_candidates(event_commands) samples_by_code`。
- `export-event-commands-json` 从 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 移出。
- `validate-event-command-rules` 和 `import-event-command-rules` 仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中。

## 性能证据

本批把事件指令导出的生产事实来源切到 Rust `scan_rule_candidates(event_commands)`，Python 只负责构造 data 文件载荷、读取 `samples_by_code`、校验 `sample_count` 和写文件。

性能边界变化：

- 导出不再在 Python 中执行 `iter_all_commands` 全量枚举和样本去重。
- Rust 侧仍执行一次事件指令候选扫描，预算表保持 `candidate_scan_count = 1`、`plugin_source_ast_scan_count = 0`。
- `app/application/handler.py::export_event_commands_json` 和 `app/agent_toolkit/services/workspace.py::prepare_agent_workspace` 继续复用同一个导出 helper，因此 CLI 导出和工作区生成同时消费 native samples。

## 验证结果

- RED 目标测试：`uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples`，1 failed，失败点为 native 扫描入口尚未接入。
- RED 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_record_exists`，1 passed，1 failed，失败点为本记录尚不存在。
- GREEN 导出目标测试：`uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples tests/test_event_command_text.py::test_event_command_json_export_uses_configured_command_codes tests/test_event_command_text.py::test_mv_event_command_json_export_uses_engine_default_356`，3 passed。
- GREEN 相关 scan_budget 边界：`uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_tracks_current_boundaries tests/test_scan_budget.py::test_batch111_p1b_event_command_candidate_adapter_evaluation_tracks_first_adapter_boundary`，3 passed。
- 记录保护命令：`uv run pytest tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch112_p1b_event_command_export_native_samples_adapter_record_exists`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_event_command_text.py::test_event_command_json_export_uses_native_samples tests/test_event_command_text.py::test_event_command_json_export_uses_configured_command_codes tests/test_event_command_text.py::test_mv_event_command_json_export_uses_engine_default_356 tests/test_scan_budget.py -k "batch112 or batch111 or batch109 or batch108_p1b_budget_fact_source_review"`，8 passed，175 deselected；该组合命令因 `-k` 只选择了 scan_budget 测试，导出行为测试已用单独命令覆盖。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-112.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批未使用子代理。主代理完成生产链路审计、RED/GREEN 测试、预算契约更新、计划索引和验收记录。

本批审查结论是：导出 helper 已具备最小 native samples 适配条件；规则校验和导入链路仍需要 hit details、规则记录构造和写回协议预演的边界评估，不能在本批合并处理。

## 剩余风险

本批按临时例外未跑全量 `uv run pytest`，全仓非本批路径仍需在目标完成收尾、准备提交或用户明确要求时用全量测试确认。

本批修改了生产代码但未修改 Rust 原生代码，因此没有执行 Rust 格式检查、Rust 静态检查或 Rust 测试。剩余风险集中在：更大样本下 native `samples_by_code` 与旧 Python 去重顺序是否完全覆盖所有极端结构；本批目标测试已覆盖 MZ、MV 和禁止旧遍历路径，但未执行全量回归。

`validate-event-command-rules` 和 `import-event-command-rules` 仍是待复核预算目标，下一批需要继续评估是否能直接消费 native `hit_details` 或需要先补 Python 适配层。

## 下一批入口

下一批入口：P1-B validate-event-command-rules native hit details 适配评估。

建议下一批进入 P1-B `validate-event-command-rules` native hit details 适配评估：审计 `_validate_event_command_rule_records_with_context`、`EventCommandTextExtraction.extract_all_text_with_rule_items`、`_preview_event_command_write_back` 和已保存译文前缀读取，判断 native `hit_details` 是否足以替换规则命中统计，还是需要先补充 Rust 输出明细契约。
