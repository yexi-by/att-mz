# Rust Scope/Index Engine 批次 6BX 验收记录

## 本批范围

本批是 P1-B 工作区和规则命令阶段总收束回顾，只新增阶段保护测试、计划索引和验收记录，本批未修改生产代码，本批未修改 Rust 原生代码。

范围覆盖 P1-B 已迁移并阶段收束的主要支线：

- 插件源码：`docs/records/rust-scope-index/batches/batch-063.md`。
- 非标准 data：`docs/records/rust-scope-index/batches/batch-070.md`。
- 普通占位符：`docs/records/rust-scope-index/batches/batch-081.md`。
- 结构化占位符：`docs/records/rust-scope-index/batches/batch-089.md`。
- Note 标签：`docs/records/rust-scope-index/batches/batch-106.md`。

本批不把 P1-B 宣告为无风险完成；重点是把已完成支线、scan budget 总账、仍保留的旧 helper 边界和下一批预算目标 vs 当前实现事实来源复核入口固定下来。

## 保护网

新增 `tests/test_scan_budget.py::test_batch107_p1b_workspace_rule_stage_records_cover_branch_closures_and_reuse_risks`：

- 固定五条 P1-B 支线阶段记录都存在并被计划表链接。
- 固定每条支线记录包含代表性 native 入口或剩余风险标记。
- 固定 `prepare-agent-workspace`、`validate-agent-workspace`、插件源码、非标准 data、普通占位符、结构化占位符和 Note 标签公开命令都属于 `P1_B_COMMANDS`。
- 固定这些命令的 scan budget 分类为 P1-B，候选扫描预算为一次，插件源码 AST 扫描预算不超过一次。
- 固定 `TextScopeService` 当前生产事实：插件源码和非标准 data 已有上下文复用入口；Note 标签正文提取、规则命中、workflow gate 和 text index 仍是下一批跨消费者 native 结果复用评估的证据入口。

新增 `tests/test_scan_budget.py::test_batch107_p1b_workspace_rule_stage_closure_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定五条支线名称、代表性公开命令、`P1_B_COMMANDS`、旧 helper、空规则、跨消费者 native 结果复用、预算目标 vs 当前实现事实来源、临时验证例外和下一批入口。

## 实现说明

本批只把已有迁移事实收束成阶段级可机读保护，不改变生产实现。

阶段记录链：

| 支线 | 阶段记录 | 代表性事实 |
| --- | --- | --- |
| 插件源码 | `docs/records/rust-scope-index/batches/batch-063.md` | `build_native_plugin_source_scan` 和插件源码 AST scan budget |
| 非标准 data | `docs/records/rust-scope-index/batches/batch-070.md` | `NonstandardDataTextExtractionContext` |
| 普通占位符 | `docs/records/rust-scope-index/batches/batch-081.md` | `collect_native_placeholder_candidate_details` |
| 结构化占位符 | `docs/records/rust-scope-index/batches/batch-089.md` | `collect_native_structured_placeholder_candidate_details` |
| Note 标签 | `docs/records/rust-scope-index/batches/batch-106.md` | `collect_native_note_tag_extraction_details` 和跨消费者 native 结果复用风险 |

本批固定的已成链主支线公开命令类别：

- 工作区命令：`prepare-agent-workspace`、`validate-agent-workspace`。
- 插件源码命令：`scan-plugin-source-text`、`export-plugin-source-ast-map`、`validate-plugin-source-rules`、`import-plugin-source-rules`。
- 非标准 data 命令：`scan-nonstandard-data`、`export-nonstandard-data-json`、`validate-nonstandard-data-rules`、`import-nonstandard-data-rules`。
- 普通占位符命令：`scan-placeholder-candidates`、`validate-placeholder-rules`、`build-placeholder-rules`、`import-placeholder-rules`。
- 结构化占位符命令：`validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates`、`import-structured-placeholder-rules`。
- Note 标签命令：`export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules`。

测试还确认 `required_scan_budget_commands_by_category()["P1-B"]` 与 `P1_B_COMMANDS` 保持一致，避免 P1-B 总账和命令集合漂移。

注意：`P1_B_COMMANDS` 还包含事件指令、插件参数、MV 虚拟名字框和源文残留等预算登记类别。本批不声称这些类别已经拥有和五条主支线同等的独立迁移链；下一批需要复核预算目标 vs 当前实现事实来源，确认这些类别是否仍停留在预算登记或 Python 领域路径。

## 旧路径收束

P1-B 五条主迁移支线已经从 Python 大规模候选扫描迁移到 Rust `scan_rule_candidates(...)` 或 `build_scope_index / scan_rule_candidates` 事实来源。Python 仍保留 CLI/service 外壳、JSON 报告组装、规则导入事务、规则顺序筛选、错误文案、manifest 校验和输出对象组装。

仍需下一批审计的旧 helper 或重复消费边界：

- `TextScopeService.build` 目前会读取规则、构建 active translation data、收集 inactive rule hits；其中 Note 标签正文提取和 `collect_note_tag_rule_hits` 仍可能分别消费 native 明细。
- workflow gate 和 text index 会通过 `note_tag_rule_scope_hash_for_text_rules` 消费 Note 标签 native 候选摘要。
- 空规则缺少更早短路时，部分支线可能在没有外部规则时仍进入 native 候选或明细扫描。
- 旧 helper 已经不是这些公开命令的默认候选事实来源，但仍需要按模块确认是否还有生产路径把旧 helper 当成第二数据源。
- 事件指令、插件参数、MV 虚拟名字框和源文残留等 `P1_B_COMMANDS` 预算登记类别，需要确认预算目标与当前实现事实来源是否一致。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自阶段保护固定的 scan budget 和生产入口事实：

- `P1_B_COMMANDS` 仍由 `required_scan_budget_commands_by_category()["P1-B"]` 统一声明。
- 工作区、插件源码、非标准 data、普通占位符、结构化占位符和 Note 标签代表性命令的候选扫描预算固定为一次。
- 插件源码相关命令的插件源码 AST 扫描预算固定为一次，其余被本批覆盖的支线命令固定为不触发插件源码 AST 扫描。
- 插件源码在 `TextScopeService.build` 中可通过 `plugin_source_scan` 入参复用；非标准 data 在 `TextScopeService.build` 和 `build_translation_data_map` 中复用 `NonstandardDataTextExtractionContext`。
- 事件指令、插件参数、MV 虚拟名字框和源文残留等预算登记类别尚未完成事实来源复核；Note 标签跨消费者 native 结果复用尚未完成结构性证明，因此本批把它们明确留给后续批次。

## 验证结果

- RED 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch107_p1b_workspace_rule_stage_records_cover_branch_closures_and_reuse_risks tests/test_scan_budget.py::test_batch107_p1b_workspace_rule_stage_closure_record_exists_and_tracks_contract`，1 passed，1 failed；失败点为 `docs/records/rust-scope-index/batches/batch-107.md` 尚不存在。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch107_p1b_workspace_rule_stage_records_cover_branch_closures_and_reuse_risks tests/test_scan_budget.py::test_batch107_p1b_workspace_rule_stage_closure_record_exists_and_tracks_contract`，2 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch107 or batch106"`，4 passed，166 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

本批使用只读子代理辅助审计 P1-B 总收束边界，主代理负责最终判断、测试保护、记录和验证。子代理不修改文件。

审计重点包括五条阶段收束记录、`P1_B_COMMANDS` 覆盖面、`TextScopeService`、workflow gate、text index、旧 helper、预算目标 vs 当前实现事实来源和跨消费者 native 结果复用风险。

子代理审计结论被纳入本记录的剩余风险和下一批入口：P1-B 主迁移线已经接近收尾，但不能把所有 `P1_B_COMMANDS` 都说成已有独立迁移链；事件指令、插件参数、MV 虚拟名字框和源文残留等预算登记类别需要先做事实来源复核，同时不应把跨消费者 native 结果复用、空规则短路和旧 helper 第二数据源风险从总账中抹掉。

## 剩余风险

本批按临时例外未跑全量 `uv run pytest`，全仓非 P1-B 路径仍需在阶段收束、准备提交或用户明确要求时用全量测试确认。

预算目标 vs 当前实现事实来源是下一批优先风险：`P1_B_COMMANDS` 覆盖 30 个公开命令，其中五条主迁移支线已有阶段记录；事件指令、插件参数、MV 虚拟名字框和源文残留等类别还需要确认当前实现是否真正以 Rust 候选事实为主，而不只是预算表中的目标登记。

跨消费者 native 结果复用仍是主要剩余风险：同一轮工作区构建、`TextScopeService`、workflow gate、text index 和规则命令之间是否能共享同一份 native 候选或明细上下文，目前只有局部支线级证据，没有总线级复用设计。

空规则短路仍需单独确认：当外部规则为空时，相关支线是否能在进入 native 重扫描前停止，需要从工作区命令和 `TextScopeService` 两个入口一起审计。

旧 helper 风险仍需收束到可证明边界：当前记录确认公开命令的候选事实来源已迁到 Rust，但下一批仍应检查是否存在隐藏生产路径把旧 helper 当成第二数据源。

## 下一批入口

建议下一批进入 P1-B 预算事实来源复核：以 `P1_B_COMMANDS` 中未形成独立阶段链的事件指令、插件参数、MV 虚拟名字框和源文残留为重点，对比 scan budget 目标、Rust `RuleCandidatesPayload` 能力和当前 Python 生产路径；复核后再决定进入跨消费者 native 结果复用评估，或先补空规则短路保护测试来防止无规则场景重复扫描。
