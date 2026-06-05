# Rust Scope/Index Engine 批次 126 验收记录

## 本批范围

- 批次编号：7C。
- 范围：P1-C 插件导出和文档契约收束。
- 覆盖命令：`export-plugins-json`。
- 覆盖文档：README、Skill、docs 当前公开说明。
- 目标：固定插件配置导出的真实成本和公开文档边界，确认该命令只导出 `plugins.js` 配置 JSON，不构建 `TextScopeService`、不扫描候选、不进入质量 gate 或写回计划；同时确认 docs 只作为人类文档，不倒置覆盖 Skill 和 CLI 当前契约。

## 保护网

- `tests/test_plugin_text.py::test_plugin_json_export_writes_raw_plugins_array`：固定 `export-plugins-json` 写出的顶层结构是原始插件配置数组。
- `tests/test_skill_protocol.py::test_removed_agent_mode_flags_are_absent_from_public_protocol_docs`：固定公开协议文档不再要求旧 Agent JSON 开关。
- `tests/test_skill_protocol.py::test_skill_and_readme_command_examples_exist_in_parser`：固定 README、Skill 和 references 中的入口命令示例能被 parser 识别。
- `tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_tracks_current_boundaries`：固定 `export-plugins-json` 的 P1-C 预算事实、handler/exporter/CLI 静态旧路径边界和 README/Skill/docs 当前公开契约。
- `tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_record_exists`：固定本验收记录、验证命令、敏感路径边界和下一批入口。

## RED/GREEN

- RED：`test_batch126_p1c_plugin_export_docs_contract_tracks_current_boundaries` 和 `test_batch126_p1c_plugin_export_docs_contract_record_exists` 在计划进度和验收记录缺失时失败。
- GREEN：计划表新增 `docs/records/rust-scope-index/batches/batch-126.md` 并把 7C 标记为已完成，下一批入口改为全计划收束验收。
- GREEN：本批记录写明 `export-plugins-json`、README、Skill 和 docs 当前边界，并把 `plugins.js parser / plugin config reader` 作为该命令的扫描预算事实来源。

## 实现说明

- 本批不修改生产 Python/Rust 入口。
- `app/application/handler.py::export_plugins_json` 当前只加载一次当前游戏 `GameData`，调用 `export_plugins_json_file` 写出插件配置数组，并返回 Agent JSON summary 所需的输出路径和插件数量。
- `app/plugin_text/exporter.py::export_plugins_json_file` 只序列化 `game_data.plugins_js`，不构建文本范围，不触发插件源码 AST scan，不读取 SQLite text index。
- `app/cli/commands/rules.py::run_export_plugins_json_command` 保持 stdout Agent JSON 报告输出，通过 `write_report_outputs` 统一写出。
- README、Skill 和 docs 当前公开说明不把 docs 写成 Agent 任务契约；docs/README.md 明确 docs 只供人类阅读，当前翻译流程以 Skill 为准，且不覆盖 Skill。

## 旧路径收束

- `export-plugins-json` 保留 1 次 `GameData` 加载，这是读取 `js/plugins.js` 当前插件配置的真实 I/O 成本。
- `export-plugins-json` 不构建 `TextScopeService`。
- `export-plugins-json` 不调用插件源码 runtime scan、native AST scan 或 text index invalidation 检查。
- README/Skill/docs 边界由 `test_removed_agent_mode_flags_are_absent_from_public_protocol_docs` 和 batch-126 静态保护共同固定，避免公开协议文档重新引入旧 Agent JSON 开关或把 docs 倒置成 Skill 的覆盖来源。

## 外部契约变化

- 无 CLI 参数变化。
- stdout Agent JSON 字段名不变。
- 无数据库 schema 变化。
- 无 Rust 原生扩展 API 变化。
- 本批只更新计划进度和 P1-C 文档/预算保护，不改变项目长期 AGENTS.md 基线。

## 性能证据

- `export-plugins-json` 的 scan budget 为 `game_data_load_count=1`、`text_scope_build_count=0`、`candidate_scan_count=0`、`plugin_source_ast_scan_count=0`、`quality_gate_count=0`、`write_plan_count=0`。
- 事实来源为 `plugins.js parser / plugin config reader`，本批静态测试固定 handler、exporter 和 CLI 中没有 `TextScopeService`、插件源码扫描、text index invalidation 或写回计划相关调用。
- `export_plugins_json_file` 直接写出 `game_data.plugins_js`，该成本与插件配置 JSON 导出目标一致，不属于 Rust Scope/Index Engine 的大规模文本扫描迁移对象。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_tracks_current_boundaries tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_record_exists`：2 failed，失败点分别是计划表缺少 7C 已完成记录和本批记录不存在。
- `uv run pytest tests/test_plugin_text.py::test_plugin_json_export_writes_raw_plugins_array tests/test_skill_protocol.py::test_removed_agent_mode_flags_are_absent_from_public_protocol_docs tests/test_skill_protocol.py::test_skill_and_readme_command_examples_exist_in_parser tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_tracks_current_boundaries tests/test_scan_budget.py::test_batch126_p1c_plugin_export_docs_contract_record_exists`：5 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- 文档敏感路径搜索：`文档敏感路径` 检查覆盖本记录和计划文档，NO_MATCH。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 本批按临时例外未跑全量 `uv run pytest`。

## 剩余风险

- 本批按临时例外未跑全量 `uv run pytest`。
- 本批不修改生产代码，剩余风险主要是全仓其它文档/Skill/CLI 组合测试未在本批重复执行；本批用目标行为测试、公开协议测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。
- `export-plugins-json` 仍需加载当前 GameData 读取插件配置，这是该命令的真实输出成本，不是本计划要删除的重复 scope/index 成本。

## 下一批入口

- 进入 7D：全计划收束验收。
- 复核 P0、P1-A、P1-B、P1-C 目标架构、预算表和最终风险清单；按用户当前目标禁止全量 `uv run pytest`。
