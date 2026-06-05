# Rust Scope/Index Engine 批次 6BY 验收记录

## 本批范围

本批是 P1-B 预算事实来源复核，只调整测试契约、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

本批承接 `docs/records/rust-scope-index/batches/batch-107.md` 的结论，确认 `P1_B_COMMANDS` 覆盖 30 个公开命令，并把其中未形成独立迁移链的命令从“完成事实”改为“预算目标 vs 当前实现事实来源待复核”。范围包括：

- 事件指令：`export-event-commands-json`、`validate-event-command-rules`、`import-event-command-rules`。
- 插件参数：`validate-plugin-rules`、`import-plugin-rules`。
- MV 虚拟名字框：`export-mv-virtual-namebox-candidates`、`validate-mv-virtual-namebox-rules`、`import-mv-virtual-namebox-rules`。
- 源文残留：`validate-source-residual-rules`、`import-source-residual-rules`。

## 保护网

新增 `tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets`：

- 固定 `tests.scan_budget_contract.P1_B_PENDING_FACT_SOURCE_COMMANDS` 覆盖上述 10 个命令，并确认 `P1_B_COMMANDS` 覆盖 30 个公开命令。
- 固定这些命令仍属于 `P1_B_COMMANDS`，scan budget 仍是 P1-B，但 `authoritative_source` 必须以 `待复核:` 开头。
- 固定这些命令的 `authoritative_source` 只能写成目标 `Rust scan_rule_candidates(event_commands)`、`Rust scan_rule_candidates(plugin_config)`、`Rust scan_rule_candidates(mv_virtual_namebox)` 或 `Rust scan_rule_candidates(source_residual)`，不能写成完成事实。
- 固定当前 Rust `RuleCandidatesPayload` 只包含已经成链的 `plugin_source_files`、`nonstandard_data_files`、`placeholder_texts`、`structured_placeholder_texts`、`note_tag_data_files` 等输入，不包含 `event_commands`、`plugin_config`、`mv_virtual_namebox` 或 `source_residual` 输入字段。
- 固定当前 Python 生产事实来源：`app/event_command_text/exporter.py` 仍用 `iter_all_commands`；插件参数规则校验仍用 `PluginTextExtraction`；事件指令规则校验仍用 `EventCommandTextExtraction`；MV 虚拟名字框仍用 `collect_mv_virtual_namebox_candidates`；源文残留规则仍经过 `build_source_residual_rule_records_from_import` / `TextRules` 残留检查。

新增 `tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定本批关键命令、`P1_B_PENDING_FACT_SOURCE_COMMANDS`、`RuleCandidatesPayload`、当前 Python 事实来源、临时验证例外和下一批入口。

## 实现说明

本批没有把未迁移类别实现为 Rust 候选扫描，只修正测试预算契约的表达：

- 新增 `P1_B_PENDING_FACT_SOURCE_COMMANDS`，显式列出仍需事实来源复核的 P1-B 命令。
- 新增 `_pending_fact_source_budget(...)`，让这些命令的 `authoritative_source` 以 `待复核:` 开头，并同时记录当前 Python 生产路径与目标 Rust domain。
- 保持这些命令的预算分类、候选扫描次数和插件源码 AST 扫描次数不变，因为这些仍是 P1-B 目标预算；本批只避免把目标预算写成已经完成的生产事实。

代表性事实来源：

| 类别 | 当前实现事实 | 目标预算 |
| --- | --- | --- |
| 事件指令 | `app/event_command_text/exporter.py` / `EventCommandTextExtraction` | `Rust scan_rule_candidates(event_commands)` |
| 插件参数 | `PluginTextExtraction` | `Rust scan_rule_candidates(plugin_config)` |
| MV 虚拟名字框 | `collect_mv_virtual_namebox_candidates` | `Rust scan_rule_candidates(mv_virtual_namebox)` |
| 源文残留 | `build_source_residual_rule_records_from_import` / `TextRules` 残留检查 | `Rust scan_rule_candidates(source_residual)` |

## 旧路径收束

本批没有删除旧路径。阶段结论是：上述 10 个命令仍可见 Python 生产事实来源，不能在 scan budget 契约或验收记录中写成已经迁移到 Rust 候选事实。

已成链主支线继续保持 6BX 结论：插件源码、非标准 data、普通占位符、结构化占位符和 Note 标签已有阶段记录和 native/Rust 候选事实保护。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

测试契约变化：`tests/scan_budget_contract.py` 新增 `P1_B_PENDING_FACT_SOURCE_COMMANDS`，并把 10 个未成链命令的 `authoritative_source` 从“完成事实”修正为“待复核目标”。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自静态保护：

- `RuleCandidatesPayload` 当前没有 `event_commands`、`plugin_config`、`mv_virtual_namebox` 或 `source_residual` 输入字段。
- 事件指令、插件参数、MV 虚拟名字框和源文残留仍可在 Python 领域模块中找到生产事实来源。
- scan budget 仍限制这些命令为 P1-B、候选扫描预算一次、插件源码 AST 扫描预算 0，但现在明确这只是预算目标而非完成事实。

## 验证结果

- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_record_exists_and_tracks_contract`，2 failed。失败点分别是 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 尚不存在，以及 `docs/records/rust-scope-index/batches/batch-108.md` 尚不存在。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_record_exists_and_tracks_contract`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch108 or batch107 or rust_scope_index_scan_budget_table"`，5 passed，167 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计未成链 P1-B 类别，主代理负责最终判断、测试保护、记录和验证。子代理不修改文件。

审计重点包括 `P1_B_COMMANDS` 预算声明、Rust `RuleCandidatesPayload` 当前能力、事件指令、插件参数、MV 虚拟名字框、源文残留和工作区 prepare/validate 对这些类别的消费边界。

本批审计结论：这些命令应保留在 P1-B scan budget 总账中，但必须标记为待复核目标，不能继续被描述为已完成 Rust 候选事实迁移。

## 剩余风险

本批按临时例外未跑全量 `uv run pytest`，全仓非本批路径仍需在阶段收束、准备提交或用户明确要求时用全量测试确认。

未成链类别仍需要继续分批迁移或复核：事件指令、插件参数、MV 虚拟名字框和源文残留当前仍有 Python 生产事实来源。后续批次应按类别逐条建立 Rust 候选入口、薄适配、覆盖校验和导入保护，或明确从 P1-B 迁移范围中移出并修正计划。

跨消费者 native 结果复用和空规则短路仍是后续总线级风险，当前不应和本批事实来源复核混在一起处理。

## 下一批入口

建议下一批进入 P1-B 事件指令候选 Rust 入口评估：先为 `export-event-commands-json`、`validate-event-command-rules`、`import-event-command-rules` 建立事件指令候选的 Rust 输入/输出最小契约，再判断是否按插件源码、非标准 data、占位符、Note 标签相同模式推进薄适配。
