# Rust Scope/Index Engine 批次 36 记录

## 本批范围

- 批次：6E，`prepare-agent-workspace` 插件源码风险报告接入 Rust 候选事实。
- 覆盖入口：Agent/CLI 子服务 `prepare_agent_workspace` 生成的 `plugin-source-risk-report.json`、manifest 中的插件源码风险摘要字段和工作区准备阶段的插件源码语法告警。
- 成功状态：工作区风险报告不再从旧 `PluginSourceScan.risk_report_json()` 渲染，而是调用 `scan_native_rule_candidates` 生成轻量风险事实；旧 `PluginSourceScan` 仍保留给插件源码规则覆盖、selector 新鲜度和文本范围复用链路。

## 保护网

- 加固 `tests/test_plugin_source_text.py::test_prepare_workspace_writes_plugin_source_risk_summary_without_ast_map`：
  - monkeypatch `PluginSourceScan.risk_report_json` 为失败函数，证明 `plugin-source-risk-report.json` 不再由旧扫描对象渲染。
  - monkeypatch 计数 `app.agent_toolkit.services.workspace.scan_native_rule_candidates`，断言工作区准备阶段只调用一次 Rust 候选扫描来生成风险报告。
  - 断言工作区风险报告保留 `risk`、`candidate_count`、`active_candidate_count`、`syntax_errors` 和 `source_view`，但不携带 `files` 或顶层 `candidates`。
  - 断言 manifest/report summary 中的 `plugin_source_candidate_count`、`plugin_source_high_risk` 和 `plugin_source_syntax_error_file_count` 与 Rust 风险报告一致。
- 新增 `tests/test_scan_budget.py::test_batch36_prepare_workspace_plugin_source_risk_native_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `prepare_agent_workspace`、`plugin-source-risk-report.json`、`scan_native_rule_candidates`、`PluginSourceScan` 和本批命令级测试名。

## 改动范围

- `app/agent_toolkit/services/workspace.py`
  - `prepare_agent_workspace` 在解析 `TextRules` 后调用 `_build_native_plugin_source_risk_report`，生成插件源码轻量风险报告。
  - `plugin-source-risk-report.json` 改为写出 Rust 风险事实，并继续只带轻量摘要，不写完整 AST map。
  - manifest/report summary 中插件源码候选数、高风险状态和语法错误文件数改为读取同一份 Rust 风险报告。
  - 插件源码语法错误告警改为读取 Rust 风险报告中的 `syntax_errors`。
- `tests/test_plugin_source_text.py`
  - 加固 6E 工作区风险报告测试，固定 Rust 事实源和大字段防漏契约。
- `tests/test_scan_budget.py`
  - 新增批次 36 验收记录测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 新增 6E 批次进度行。

## 旧路径收束

- `prepare_agent_workspace` 已停止使用 `PluginSourceScan.risk_report_json()` 生成工作区风险报告。
- `PluginSourceScan` 仍在 `prepare_agent_workspace` 中保留，服务于：
  - `_extract_active_translation_data_map` 的插件源码文本范围复用。
  - `collect_plugin_source_review_coverage` 的规则覆盖统计。
  - 已导入插件源码规则的 selector、排除 selector 和 stale rule 相关后续链路。
- 本批没有迁移 `validate-agent-workspace`、`validate-plugin-source-rules` 或 `import-plugin-source-rules`，这些命令仍需下一批继续处理。

## 外部契约变化

- `prepare-agent-workspace` 仍生成 `plugin-source-risk-report.json`。
- `plugin-source-risk-report.json` 继续保留：
  - `risk`
  - `enabled_plugin_files`
  - `candidate_count`
  - `active_candidate_count`
  - `syntax_errors`
  - `source_view`
- `plugin-source-risk-report.json` 继续不包含 `files` 或顶层 `candidates`。
- manifest/report summary 继续保留：
  - `plugin_source_candidate_count`
  - `plugin_source_high_risk`
  - `plugin_source_syntax_error_file_count`
- 插件源码规则文件 `plugin-source-rules.json` 的生成条件不变：Rust 风险报告判定高风险，或项目已有插件源码规则。

## 性能证据

- 命令级保护网证明 `prepare_agent_workspace` 的风险报告路径不再调用旧 `PluginSourceScan.risk_report_json()`。
- 命令级保护网断言 `prepare_agent_workspace` 为插件源码风险报告只调用一次 `scan_native_rule_candidates`。
- 旧 `PluginSourceScan` 仍会在本批保留一次，用于规则覆盖和文本范围复用；后续规则校验/导入批次完成前不能删除。
- 工作区风险报告不构造完整 `files[].candidates[]`，只写轻量风险摘要。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_prepare_workspace_writes_plugin_source_risk_summary_without_ast_map`
  - 结果：1 failed，失败原因为 `prepare_agent_workspace` 调用了被 monkeypatch 的 `PluginSourceScan.risk_report_json()`。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_prepare_workspace_writes_plugin_source_risk_summary_without_ast_map`
  - 结果：1 passed。
- 文档记录 RED：`uv run pytest tests/test_scan_budget.py::test_batch36_prepare_workspace_plugin_source_risk_native_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-036.md` 尚不存在。
- 文档记录 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch36_prepare_workspace_plugin_source_risk_native_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 定向回归：`uv run pytest tests/test_plugin_source_text.py::test_prepare_workspace_writes_plugin_source_risk_summary_without_ast_map tests/test_plugin_source_text.py::test_prepare_workspace_warns_and_skips_invalid_plugin_source tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope tests/test_scan_budget.py::test_batch36_prepare_workspace_plugin_source_risk_native_record_exists_and_tracks_contract`
  - 结果：4 passed。
- 工作区/插件源码/扫描预算回归：`uv run pytest tests/test_plugin_source_text.py tests/test_agent_toolkit_workspace.py tests/test_scan_budget.py`
  - 结果：105 passed。
- 相关文件类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py tests/test_plugin_source_text.py tests/test_agent_toolkit_workspace.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 全仓类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：785 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- 补丁格式检查：`git diff --check`
  - 结果：退出码 0；仅出现 Git 的 LF/CRLF 工作区换行提示，无 whitespace 错误。

## 审查处理

- 已派发只读代码审查，结论为无 Critical、无 Important。
- 审查确认 `prepare_agent_workspace` 的风险报告和 manifest/report summary 都来自同一份 Rust 风险报告，旧 `PluginSourceScan` 仍保留在覆盖、selector/hash、validate/import 后续链路。
- 审查指出记录缺少文档记录测试 GREEN；已补充对应验证结果。

## 剩余风险

- `validate-agent-workspace` 插件源码支线仍使用旧 `PluginSourceScan`，工作区验收阶段的候选覆盖和规则校验还未迁移。
- 插件源码规则导入、stale rule 校验和写回定位仍依赖旧 selector/hash 事实，后续迁移前不能删除 Python 扫描器。
- 本批没有减少 `prepare_agent_workspace` 中旧 `PluginSourceScan` 的存在，只把工作区风险报告和风险摘要切换到 Rust 事实源。

## 下一批入口

- 建议下一批：6F `validate-agent-workspace` 插件源码支线候选事实接入 Rust。目标是在工作区验收读取 manifest 和规则文件时，逐步复用 Rust 插件源码候选事实，同时继续保护插件源码规则导入和写回定位所需的旧契约。
