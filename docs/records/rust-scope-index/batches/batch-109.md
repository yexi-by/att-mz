# Rust Scope/Index Engine 批次 6BZ 验收记录

## 本批范围

本批是 P1-B 事件指令候选 Rust 入口评估，只新增评估保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

本批承接 `docs/records/rust-scope-index/batches/batch-108.md` 的事实来源复核结论，聚焦三个事件指令 P1-B 命令：

- `export-event-commands-json`
- `validate-event-command-rules`
- `import-event-command-rules`

本批目标不是实现 `scan_rule_candidates(event_commands)`，而是固定当前边界：事件指令仍在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中，Rust `ScopeIndexDataFileInput` 已有标准 data 事件指令文本扫描能力，但 `RuleCandidatesPayload` 尚未提供 `event_commands` 候选输入字段。

## 保护网

新增 `tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_tracks_current_boundaries`：

- 固定三个事件指令命令仍属于 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。
- 固定三个事件指令命令的 scan budget 仍是 P1-B、候选扫描预算一次、插件源码 AST 扫描预算 0，并且 `authoritative_source` 仍标记为 `待复核:` 与目标 `Rust scan_rule_candidates(event_commands)`。
- 固定 Rust `RuleCandidatesPayload` 当前没有 `event_commands` 或 `data_files` 规则候选输入字段。
- 固定 Rust `ScopeIndexDataFileInput` 路径已经存在 `scan_event_command_data_file`、`append_event_command_entry`、`code 401`、`parameters_index = 0`、`event_command.default` 和 `command_parameter_location_path` 等标准 data 事件正文扫描能力。
- 固定当前 Python 生产事实来源：`app/event_command_text/exporter.py::export_event_commands_json_file` 使用 `iter_all_commands`；`EventCommandTextExtraction._extract_all_text` 使用 `iter_all_commands`、`command_matches_filters`、`expand_rule_to_leaf_paths`、`resolve_event_command_leaves` 和 `jsonpath_to_event_command_location_path`；`build_event_command_rule_records_from_import` 使用 `iter_all_commands`；`collect_event_command_rule_hits` 使用同一套 Python 事件指令解析路径。

新增 `tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_record_exists`：

- 固定本记录和计划表链接。
- 固定事件指令三个公开命令、当前 Python 事实来源、Rust scope index 已有能力、`RuleCandidatesPayload` 缺口、验证命令、临时验证例外和下一批入口。

## 实现说明

本批没有修改生产实现，只把事件指令候选 Rust 入口评估固定成可机读测试和记录。

评估结论：

- 当前 `export-event-commands-json` 的默认生产事实来源仍是 `app/event_command_text/exporter.py` 的 `iter_all_commands`。
- 当前 `validate-event-command-rules` 与 `import-event-command-rules` 仍依赖 `build_event_command_rule_records_from_import`、`EventCommandTextExtraction`、`resolve_event_command_leaves` 和 `jsonpath_to_event_command_location_path`。
- 当前 `app/text_scope/rule_hits.py::collect_event_command_rule_hits` 仍使用 Python `iter_all_commands` 枚举事件指令规则命中。
- Rust `scope_index` 已有 `ScopeIndexDataFileInput`、`scan_event_command_data_file` 和 `append_event_command_entry`，能为 `code 401` 的 `parameters[0]` 标准 data 事件正文生成 `source_type = event_command` 与 `rule_source = event_command.default` 的 scope entry。
- Rust `RuleCandidatesPayload` 当前没有 `event_commands` 输入字段；因此下一批需要先定义事件指令候选输入/输出最小契约，而不是直接把 Python 适配层指向不存在的 Rust payload。
- 事件指令规则校验已有 `collect_native_write_protocol_details` 的写回协议检查能力；下一批不应把候选扫描和写回协议预演混成同一个新入口。

## 旧路径收束

本批不删除旧路径。阶段结论是：事件指令候选导出、规则校验、规则导入和 text-scope rule hits 仍可见 Python 生产事实来源，不能记录为已迁移到 Rust 候选事实。

本批固定的旧路径边界：

- `export_event_commands_json_file`
- `EventCommandTextExtraction`
- `build_event_command_rule_records_from_import`
- `collect_event_command_rule_hits`
- `iter_all_commands`
- `resolve_event_command_leaves`
- `jsonpath_to_event_command_location_path`

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

测试契约变化：新增 6BZ 事件指令评估保护测试，防止后续把 Rust scope index 已有标准 data 扫描能力误读成 `scan_rule_candidates(event_commands)` 已经落地。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自静态保护：

- 三个事件指令 P1-B 命令仍在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中。
- 三个事件指令 P1-B 命令的 scan budget 仍限制为候选扫描预算一次、插件源码 AST 扫描预算 0。
- Rust `RuleCandidatesPayload` 当前没有事件指令候选输入字段，避免虚构 Rust 候选迁移事实。
- Rust scope index 已有 `scan_event_command_data_file` 和 `append_event_command_entry`，下一批可在同一标准 data 事件指令扫描语义上定义候选入口，但不能直接复用现有仅覆盖 `code 401` / `parameters[0]` 的正文索引语义。

## 验证结果

- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_tracks_current_boundaries tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_record_exists`，1 passed，1 failed；失败点为 `docs/records/rust-scope-index/batches/batch-109.md` 尚不存在。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_tracks_current_boundaries tests/test_scan_budget.py::test_batch109_p1b_event_command_candidate_rust_entry_evaluation_record_exists`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch109 or batch108 or rust_scope_index_scan_budget_table"`，5 passed，169 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计事件指令候选 Rust 入口边界，主代理负责最终判断、测试保护、记录和验证。子代理不修改文件。

审计重点包括事件指令导出、规则导入构造、规则校验、text-scope rule hits、Rust `ScopeIndexDataFileInput` 标准 data 扫描、Rust `RuleCandidatesPayload` 和下一批最小契约入口。

子代理只读审计补充确认：事件指令导出、校验、导入、工作区生成/校验、空规则确认范围 hash 仍可见 Python `iter_all_commands` 或事件指令规则路径；Rust 侧已有标准 data 事件正文扫描和写回协议检查能力，但不是 `scan_rule_candidates(event_commands)` 候选入口。

本批审计结论：事件指令已有可借用的 Rust 标准 data 扫描语义，但 P1-B 规则候选入口尚未定义；下一批应先补 Rust 事件指令候选输入/输出最小契约。

## 剩余风险

本批按临时例外未跑全量 `uv run pytest`，全仓非本批路径仍需在阶段收束、准备提交或用户明确要求时用全量测试确认。

事件指令候选迁移仍未实现：`export-event-commands-json`、`validate-event-command-rules` 和 `import-event-command-rules` 仍在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中，当前生产路径仍由 Python 事件指令模块提供事实来源。

事件指令 Rust 候选入口还需要设计输入字段、输出 candidate schema、命令编码过滤、参数过滤、JSON leaf path 展开、JSON 字符串容器递归解析、错误文案、空规则确认范围 hash 输入快照和 Python 薄适配边界。

## 下一批入口

建议下一批进入 P1-B 事件指令 Rust 候选入口最小契约：在 Rust `RuleCandidatesPayload` 中新增 `event_command_data_files`、`command_codes` 和可选 rules 输入字段，建立最小输出结构测试；最小输出需要能支撑导出样本去重、规则路径命中明细和空规则确认范围 hash 输入快照，先覆盖 `401.parameters[0]` 这类当前 scope index 已支持的事件正文候选，再逐步扩展到公开命令需要的任意事件指令参数叶子。
