# CLI 维护事实地图

本页面面向源码维护者，用来定位 CLI 外部协议、分发入口、业务门面、输出形态和测试护栏。它不是翻译流程 Agent 的执行契约；Agent 执行翻译时只读取 `skills/att-mz/` 或 `skills/att-mz-release/` 中的 Skill 契约，并以 CLI 实际 JSON 输出和当前工作区文件为准。

## 边界

- `app/cli/parser.py` 是参数和子命令名称的事实源。
- `app/cli/dispatch.py` 是子命令到 handler 的事实源。
- `app/cli/commands/*.py` 是 CLI 适配层，只负责参数读取、调用应用门面、报告输出和退出码。
- `app/application/handler.py` 与 `app/agent_toolkit/service.py` 是主要业务门面；CLI 不应直接跨层拼接数据库结构或游戏文件协议。
- `app/cli/reports.py` 是 stdout JSON、`--output` 完整报告、sampled/full 明细和 diagnostics 注入的事实源。
- `docs/wiki/` 只描述当前实现给维护者阅读，不覆盖 README、Skill、CLI、发布脚本和测试事实。

## 改命令时的同步清单

1. 在 `app/cli/parser.py` 定义参数、互斥关系、默认值和 help 文案。
2. 在 `app/cli/dispatch.py` 注册 handler，保持 parser 命令集合和 `COMMAND_HANDLERS` 一致。
3. 在 `app/cli/commands/` 只做适配：读取参数、调用 `TranslationHandler` 或 `AgentToolkitService`、选择报告输出模式、返回退出码。
4. 如果新增或改变 summary/details、退出码、`--output` 行为、诊断字段或写文件行为，同步测试。
5. 如果用户执行方式改变，同步 README、开发版 Skill、发行版 Skill 和发行包映射；如果只是内部维护定位，不写进 Skill。
6. 如果命令影响发行包，检查 `.github/workflows/release.yml`、发行包布局测试和发行版 Skill。

## 全局参数与配置

| 能力 | 事实源 | 维护规则 |
| --- | --- | --- |
| Debug 开关 | `app/cli/parser.py`、`app/observability` | `--debug` 是总开关；`--debug-logging`、`--debug-timings`、`--debug-llm-messages` 可单独覆盖。普通模式不要把诊断字段写成成功前置。 |
| 目标游戏选择 | `add_optional_target_arguments`、`app/cli/runtime.py` | 需要目标游戏的命令使用 `--game` / `--game-path` 二选一；无需目标游戏的命令不要伪造默认目标。 |
| 配置覆盖 | `add_setting_override_arguments`、`build_setting_overrides` | 每个覆盖参数必须完成定义、读取、校验、应用和测试链路。 |
| 翻译运行限制 | `add_translation_limit_arguments`、`build_translation_run_limits` | `--max-items`、`--max-batches`、`--time-limit-seconds`、`--stop-on-error-rate` 只用于翻译运行命令。 |
| 模型环境变量 | `app/config` | 当前契约只使用 `ATT_MZ_LLM_BASE_URL` 和 `ATT_MZ_LLM_API_KEY`。 |
| Rust 线程 | Rust native / observability | `ATT_MZ_RUST_THREADS` 控制热路径线程数；线程数和阶段耗时通过 diagnostics 表达。 |

## 输出模式

| 模式 | 入口 | 行为 |
| --- | --- | --- |
| 普通 stdout JSON | `print_report` / `write_report_outputs` | stdout 只输出最终 JSON；stderr 进度行不是结果。 |
| 完整报告文件 | `--output <文件>` + `write_report_outputs` | 写入文件的报告通过 `build_full_output_report` 标记 `summary.report_detail_mode=full`。 |
| stdout 抽样报告 | `build_sampled_stdout_report` | 大数组 details 被裁剪为 `{count, samples, omitted_count}`，并标记 `summary.report_detail_mode=sampled`。 |
| 诊断摘要 | `inject_diagnostics_summary` | 仅在 debug diagnostics 有内容时向 `summary.diagnostics` 注入；不要把普通 summary 当诊断事实源。 |
| 文件型导出 | `write_output_file=False` | 命令本身写业务文件或目录，stdout 只给摘要，不再把 `--output` 当完整报告路径。 |

## 命令库存

当前 parser 注册 57 个子命令。下表按维护归属分组，记录 parser/handler、业务边界和外部表面；具体参数以 `app/cli/parser.py` 为准。

### 环境、注册与回溯

| 命令 | CLI handler | 业务边界 | 外部表面 |
| --- | --- | --- | --- |
| `list` | `registry.run_list_command` | `GameRegistry.list_games_with_issues` | stdout 列出可读游戏，坏库进入 warning。 |
| `doctor` | `registry.run_doctor_command` | `AgentToolkitService.doctor` | 可用 `--no-check-llm` 跳过模型连接；无 `--game` 不代表当前游戏语言。 |
| `probe-source-language` | `registry.run_probe_source_language_command` | `build_source_language_probe_report` | 注册前源语言探测；不注册、不写库、不创建源快照。 |
| `add-game` | `registry.run_add_game_command` | `TranslationHandler.add_game` | 注册干净原始游戏目录并创建可信源快照。 |
| `reset-game` | `registry.run_reset_game_command` | `reset_registered_game` | 危险回溯；`--dry-run` 预演，真正执行要求 `--confirm-game-title`。 |

### 工作区与基础候选导出

| 命令 | CLI handler | 业务边界 | 外部表面 |
| --- | --- | --- | --- |
| `prepare-agent-workspace` | `workspace.run_prepare_agent_workspace_command` | `AgentToolkitService.prepare_agent_workspace` | 导出 Agent 工作区、候选文件、规则草稿和 manifest。 |
| `validate-agent-workspace` | `workspace.run_validate_agent_workspace_command` | `AgentToolkitService.validate_agent_workspace` | stdout 抽样，`--output` 写完整报告。 |
| `cleanup-agent-workspace` | `workspace.run_cleanup_agent_workspace_command` | `AgentToolkitService.cleanup_agent_workspace` | 按 manifest 清理 CLI 生成的工作区文件。 |
| `export-plugins-json` | `rules.run_export_plugins_json_command` | `TranslationHandler.export_plugins_json` | 写出当前 `js/plugins.js` 的 JSON 视图。 |
| `export-event-commands-json` | `rules.run_export_event_commands_json_command` | `TranslationHandler.export_event_commands_json` | 写出事件指令候选；`--code` 覆盖配置默认编码。 |

### 术语、规则与支线候选

| 命令 | CLI handler | 业务边界 | 外部表面 |
| --- | --- | --- | --- |
| `export-terminology` | `terminology.run_export_terminology_command` | `TranslationHandler.export_terminology` | 导出字段译名表、正文术语表和只读上下文。 |
| `import-terminology` | `terminology.run_import_terminology_command` | `TranslationHandler.import_terminology` | 导入字段译名表和正文术语表。 |
| `export-mv-virtual-namebox-candidates` | `rules.run_export_mv_virtual_namebox_candidates_command` | `AgentToolkitService.export_mv_virtual_namebox_candidates` | 仅 MV 第零轮使用；MZ 不应进入。 |
| `validate-mv-virtual-namebox-rules` | `rules.run_validate_mv_virtual_namebox_rules_command` | `AgentToolkitService.validate_mv_virtual_namebox_rules` | stdout 抽样，`--output` 写完整报告。 |
| `import-mv-virtual-namebox-rules` | `rules.run_import_mv_virtual_namebox_rules_command` | `AgentToolkitService.import_mv_virtual_namebox_rules` | 空规则需 `--confirm-empty`。 |
| `validate-plugin-rules` | `rules.run_validate_plugin_rules_command` | `AgentToolkitService.validate_plugin_rules` | 校验插件配置规则；支持 `--rules` 或 `--input`。 |
| `import-plugin-rules` | `rules.run_import_plugin_rules_command` | `TranslationHandler.import_plugin_rules` | 空规则需 `--confirm-empty`；规则变化可能备份被清理译文。 |
| `validate-event-command-rules` | `rules.run_validate_event_command_rules_command` | `AgentToolkitService.validate_event_command_rules` | 校验事件指令规则；支持 `--rules` 或 `--input`。 |
| `import-event-command-rules` | `rules.run_import_event_command_rules_command` | `TranslationHandler.import_event_command_rules` | 空规则需 `--confirm-empty`；空规则导入要保持同一组 `--code`。 |
| `export-note-tag-candidates` | `rules.run_export_note_tag_candidates_command` | `AgentToolkitService.export_note_tag_candidates` | 写出 Note 标签候选。 |
| `validate-note-tag-rules` | `rules.run_validate_note_tag_rules_command` | `AgentToolkitService.validate_note_tag_rules` | 校验 Note 标签规则文件。 |
| `import-note-tag-rules` | `rules.run_import_note_tag_rules_command` | `AgentToolkitService.import_note_tag_rules` | 空规则需 `--confirm-empty`。 |
| `scan-nonstandard-data` | `rules.run_scan_nonstandard_data_command` | `AgentToolkitService.scan_nonstandard_data` | 风险摘要；高风险时进入非标准 data 支线。 |
| `export-nonstandard-data-json` | `rules.run_export_nonstandard_data_json_command` | `AgentToolkitService.export_nonstandard_data_json` | 写候选清单和 `source/*.json` 副本。 |
| `validate-nonstandard-data-rules` | `rules.run_validate_nonstandard_data_rules_command` | `AgentToolkitService.validate_nonstandard_data_rules` | stdout 可抽样，`--output` 写完整报告。 |
| `import-nonstandard-data-rules` | `rules.run_import_nonstandard_data_rules_command` | `AgentToolkitService.import_nonstandard_data_rules` | 保存非标准 data 规则；跳过文件只能是 warning。 |
| `scan-plugin-source-text` | `translation.run_scan_plugin_source_text_command` | `AgentToolkitService.scan_plugin_source_text` | 风险摘要；默认 `--view translation-source`。 |
| `export-plugin-source-ast-map` | `translation.run_export_plugin_source_ast_map_command` | `AgentToolkitService.export_plugin_source_ast_map` | 写 AST 地图和候选；默认 `--view translation-source`。 |
| `validate-plugin-source-rules` | `rules.run_validate_plugin_source_rules_command` | `AgentToolkitService.validate_plugin_source_rules` | 校验 selector、排除 selector 和源码哈希。 |
| `import-plugin-source-rules` | `rules.run_import_plugin_source_rules_command` | `AgentToolkitService.import_plugin_source_rules` | 低风险空规则需 `--confirm-empty`。 |
| `build-placeholder-rules` | `rules.run_build_placeholder_rules_command` | `AgentToolkitService.build_placeholder_rules` | 从当前正文范围生成普通占位符草稿。 |
| `validate-placeholder-rules` | `rules.run_validate_placeholder_rules_command` | `AgentToolkitService.validate_placeholder_rules` | 可无游戏目标，仅校验规则和 sample；支持 `--rules`、`--input`。 |
| `scan-placeholder-candidates` | `rules.run_scan_placeholder_candidates_command` | `AgentToolkitService.scan_placeholder_candidates` | 扫描普通占位符覆盖；支持 `--input`。 |
| `import-placeholder-rules` | `rules.run_import_placeholder_rules_command` | `AgentToolkitService.import_placeholder_rules` | 空规则需 `--confirm-empty`；未覆盖候选会保存确认风险。 |
| `validate-structured-placeholder-rules` | `rules.run_validate_structured_placeholder_rules_command` | `AgentToolkitService.validate_structured_placeholder_rules` | 校验结构化占位符规则和 sample。 |
| `scan-structured-placeholder-candidates` | `rules.run_scan_structured_placeholder_candidates_command` | `AgentToolkitService.scan_structured_placeholder_candidates` | 扫描结构化规则覆盖。 |
| `import-structured-placeholder-rules` | `rules.run_import_structured_placeholder_rules_command` | `AgentToolkitService.import_structured_placeholder_rules` | 空规则需 `--confirm-empty`；未覆盖候选会保存确认风险。 |
| `validate-source-residual-rules` | `rules.run_validate_source_residual_rules_command` | `AgentToolkitService.validate_source_residual_rules` | 校验源文保留例外；支持 `--rules` 或 `--input`。 |
| `import-source-residual-rules` | `rules.run_import_source_residual_rules_command` | `AgentToolkitService.import_source_residual_rules` | 保存源文保留例外。 |

### 翻译、检查与修复

| 命令 | CLI handler | 业务边界 | 外部表面 |
| --- | --- | --- | --- |
| `rebuild-text-index` | `translation.run_rebuild_text_index_command` | `AgentToolkitService.rebuild_text_index` | 重建持久文本范围索引；性能事实在 debug diagnostics。 |
| `translate` | `translation.run_translate_command` | `TranslationHandler.translate_text` 适配 | 正文翻译；支持翻译运行限制和配置覆盖。 |
| `run-all` | `write_back.run_all_command` | `TranslationHandler.translate_text` + `write_back` | 固定流水线；可 `--skip-write-back`。 |
| `translation-status` | `translation.run_translation_status_command` | `AgentToolkitService.translation_status` | 查看剩余数量和最近运行；`--refresh-scope` 触发范围刷新。 |
| `text-scope` | `translation.run_text_scope_command` | `AgentToolkitService.text_scope` | stdout 抽样；`--include-write-probe` 只标记索引可写状态。 |
| `audit-coverage` | `translation.run_audit_coverage_command` | `AgentToolkitService.audit_coverage` | 对比规则、译文和文本范围；可输出完整报告。 |
| `audit-active-runtime` | `translation.run_audit_active_runtime_command` | `AgentToolkitService.audit_active_runtime` | 审计当前运行文件，默认只阻断读取失败和 JS 语法错误。 |
| `diagnose-active-runtime` | `translation.run_diagnose_active_runtime_command` | `AgentToolkitService.diagnose_active_runtime` | 用写回映射反推当前运行插件源码问题，`--output` 必填。 |
| `quality-report` | `translation.run_quality_report_command` | `AgentToolkitService.quality_report` | 普通质量报告；`--include-write-probe` 才执行 Rust 写回级检查。 |
| `export-quality-fix-template` | `translation.run_export_quality_fix_template_command` | `AgentToolkitService.export_quality_fix_template` | 写质量修复表；导出本身不执行额外写回级检查。 |
| `export-pending-translations` | `translation.run_export_pending_translations_command` | `AgentToolkitService.export_pending_translations` | 写待补译表；可 `--limit`。 |
| `import-manual-translations` | `translation.run_import_manual_translations_command` | `AgentToolkitService.import_manual_translations` | 导入手动译文并做质量校验。 |
| `reset-translations` | `translation.run_reset_translations_command` | `AgentToolkitService.reset_translations` | `--input` 精确重置或 `--all` 完整重译。 |
| `verify-feedback-text` | `translation.run_verify_feedback_text_command` | `AgentToolkitService.verify_feedback_text` | 写回后按反馈原文清单反查真实文件。 |

### 写入、重建与字体

| 命令 | CLI handler | 业务边界 | 外部表面 |
| --- | --- | --- | --- |
| `write-back` | `write_back.run_write_back_command` | `TranslationHandler.write_back` | 把译文写进游戏文件；字体覆盖需 `--confirm-font-overwrite`。 |
| `rebuild-active-runtime` | `write_back.run_rebuild_active_runtime_command` | `TranslationHandler.rebuild_active_runtime` | 从可信源快照和已保存译文重建当前运行文件。 |
| `write-terminology` | `write_back.run_write_terminology_command` | `TranslationHandler.write_terminology` | 术语专用写入，允许正文仍有 pending。 |
| `restore-font` | `write_back.run_restore_font_command` | `TranslationHandler.restore_font_replacement` | 按原始备份还原字体引用。 |

## Skill 同步原则

- Skill 只写 Agent 运行翻译流程所需的黑盒命令契约，不写 handler、源码模块、数据库表或维护者排障路线。
- 开发版 Skill 使用 `uv run python main.py <命令> ...`；发行版 Skill 使用 `.\att-mz.exe <命令> ...`。
- 两份 Skill 的业务语义、JSON 判断、停止条件和用户文案必须一致；差异只允许来自命令入口、可访问资源、停止条件和打包环境。
- CLI wiki 可以帮助维护者审查 Skill 是否过时，但不能被 Skill 引用成执行依据。

## 测试护栏

| 领域 | 测试入口 |
| --- | --- |
| parser/dispatch 命令集合 | `tests/test_cli_json_output.py` |
| 配置覆盖链路 | `tests/test_config_overrides.py` |
| 输出与 diagnostics | `tests/test_cli_json_output.py`、`tests/test_observability.py` |
| 工作区与规则导入 | `tests/test_agent_toolkit_workspace.py`、`tests/test_agent_toolkit_rule_import.py` |
| 文本索引当前契约 | `tests/test_text_index.py` |
| 写回、字体和当前运行审计 | `tests/test_write_back_transactions.py`、`tests/test_font_replacement_transactions.py`、`tests/test_agent_toolkit_feedback.py` |
| 发行包布局、Skill 映射与发布说明 | 通过生成检查、脚本检查和人工审查确认，不再由 pytest 固定 |
