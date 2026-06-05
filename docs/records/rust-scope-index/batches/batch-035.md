# Rust Scope/Index Engine 批次 35 记录

## 本批范围

- 批次：6D，`export-plugin-source-ast-map` Rust 候选/AST map 接入。
- 覆盖入口：Agent/CLI 子服务 `export_plugin_source_ast_map`、共享的 Rust 插件源码候选扫描适配层和 AST map JSON 渲染。
- 成功状态：`export-plugin-source-ast-map` 不再调用 Python `build_plugin_source_scan` 主扫描；输出文件继续保留完整 AST map，AgentReport 的 summary/details 继续只返回轻量摘要。

## 保护网

- 新增 `tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_uses_native_candidate_scan`：
  - monkeypatch `app.agent_toolkit.services.workspace.build_plugin_source_scan` 为失败函数。
  - monkeypatch 计数 `app.agent_toolkit.services.workspace.scan_native_rule_candidates`，断言命令只调用一次 Rust 候选扫描。
  - 断言 `export_plugin_source_ast_map` 仍能输出完整 AST map，证明该命令已经消费 Rust 候选入口。
  - 断言输出文件保留 `files[].candidates[]`，AgentReport summary/details 不携带完整大图。
  - 精确断言候选只保留旧公开字段 `file`、`line`、`selector`、`text`、`context`、`api`、`key`、`ast_context`、`active`、`confidence`、`structural_flags`，不泄漏 Rust 原始字段。
- 复跑 6C 相关回归：
  - `test_scan_plugin_source_text_uses_native_candidate_scan`
  - `test_scan_plugin_source_text_keeps_python_only_source_pattern_contract`
  - `test_scan_plugin_source_text_handles_empty_plugin_source_files`
- 加固 `test_scan_plugin_source_text_uses_native_candidate_scan`：
  - 断言 `scan_plugin_source_text` 只调用一次 `scan_native_rule_candidates`。
  - 断言风险报告输出、AgentReport summary 和 AgentReport details 都不包含 `files` 或顶层 `candidates`。
- 新增 `tests/test_scan_budget.py::test_batch35_export_plugin_source_ast_map_native_adapter_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `export_plugin_source_ast_map`、`scan_native_rule_candidates`、`build_plugin_source_scan` 和本批命令级测试名。

## 改动范围

- `app/agent_toolkit/services/workspace.py`
  - 新增 `_build_native_plugin_source_ast_map_payload`，从 Rust 候选输出构造旧 AST map JSON。
  - `scan_plugin_source_text` 继续使用轻量风险报告构造，避免为了风险扫描在内存里渲染完整 AST map。
  - `export_plugin_source_ast_map` 改为调用 `_build_native_plugin_source_ast_map_payload`，并继续把完整 `files` 仅写入输出文件。
  - 新增 Rust 候选到旧 AST map 候选 JSON 的字段压缩函数，保持旧输出不新增顶层 `candidates` 或 `active_candidate_count`。
- `tests/test_plugin_source_text.py`
  - 新增 6D 命令级薄适配回归测试。
- `tests/test_scan_budget.py`
  - 新增批次 35 验收记录测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 新增 6D 批次进度行。

## 旧路径收束

- `export_plugin_source_ast_map` 已停止消费 `PluginSourceScan`，不再执行 Python 插件源码 AST 主扫描。
- `build_plugin_source_scan` 仍保留在 `workspace.py`，仅供本批未迁移的命令使用：
  - `prepare_agent_workspace`
  - `validate-agent-workspace`
  - `validate-plugin-source-rules`
  - `import-plugin-source-rules`
- 本批没有删除旧扫描器，因为规则导入校验、selector 排除、stale rule 校验和写回定位仍依赖完整 `PluginSourceScan` 对象。

## 外部契约变化

- `export-plugin-source-ast-map` 输出文件继续保留：
  - `risk`
  - `enabled_plugin_files`
  - `candidate_count`
  - `syntax_errors`
  - `files`
  - `source_view`
- `files[]` 继续保留：
  - `file`
  - `file_hash`
  - `active`
  - `strong_context_text_count`
  - `medium_confidence_text_count`
  - `file_score`
  - `candidates`
- `files[].candidates[]` 继续保留旧公开字段：
  - `file`
  - `line`
  - `selector`
  - `text`
  - `context`
  - `api`
  - `key`
  - `ast_context`
  - `active`
  - `confidence`
  - `structural_flags`
- AgentReport summary 继续只包含 `source_view`、`output`、`candidate_count` 和摊平后的 `risk` 字段。
- AgentReport details 继续只包含轻量风险报告、`source_view` 和 `output`；不得包含 `files` 或顶层 `candidates`。

## 性能证据

- 命令级保护网用 monkeypatch 证明 `export_plugin_source_ast_map` 不再调用 Python `build_plugin_source_scan`。
- `export_plugin_source_ast_map` 和 `scan_plugin_source_text` 的命令级测试都断言单次执行只调用一次 `scan_native_rule_candidates`。
- 插件源码 AST 字符串扫描由 Rust `tree-sitter-javascript` 执行，多文件扫描继续使用 `rayon` 并行。
- Python 侧只遍历 Rust 候选一次来渲染旧 AST map JSON 和轻量风险报告，不再构造 `PluginSourceCandidateIndex` 或 `PluginSourceFileScan`。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_uses_native_candidate_scan`
  - 结果：1 failed，失败原因为 `export_plugin_source_ast_map` 调用了被 monkeypatch 的 Python `build_plugin_source_scan`。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_uses_native_candidate_scan`
  - 结果：1 passed。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py`
  - 结果：0 errors，0 warnings，0 notes。
- 旧报告形状和 6C 回归：`uv run pytest tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_report_keeps_full_map_only_in_output_file tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan tests/test_plugin_source_text.py::test_scan_plugin_source_text_keeps_python_only_source_pattern_contract tests/test_plugin_source_text.py::test_scan_plugin_source_text_handles_empty_plugin_source_files`
  - 结果：4 passed。
- 文档记录 RED：`uv run pytest tests/test_scan_budget.py::test_batch35_export_plugin_source_ast_map_native_adapter_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-035.md` 尚不存在。
- 审查后定向回归：`uv run pytest tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_uses_native_candidate_scan tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_report_keeps_full_map_only_in_output_file tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan tests/test_plugin_source_text.py::test_scan_plugin_source_text_keeps_python_only_source_pattern_contract tests/test_plugin_source_text.py::test_scan_plugin_source_text_handles_empty_plugin_source_files tests/test_scan_budget.py::test_batch35_export_plugin_source_ast_map_native_adapter_record_exists_and_tracks_contract`
  - 结果：6 passed。
- 审查后局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 代码审查反馈加固回归：`uv run pytest tests/test_plugin_source_text.py::test_export_plugin_source_ast_map_uses_native_candidate_scan tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan`
  - 结果：2 passed。
- 加固后局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 加固后局部回归：`uv run pytest tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：83 passed。
- 全仓类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：784 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- 补丁格式检查：`git diff --check`
  - 结果：退出码 0；仅出现 Git 的 LF/CRLF 工作区换行提示，无 whitespace 错误。

## 审查处理

- 已派发只读子代理核对 `export-plugin-source-ast-map` 的输出 JSON/AgentReport 契约、6D 不可触碰边界和实现风险。
- 当前实现保持完整 AST map 只写入输出文件，summary/details 继续使用轻量风险报告。
- 当前实现保留 Python-only `source_text_required_pattern` 的最终过滤语义，沿用 6C 对 Rust 宽松预筛的处理。
- 子代理指出 `scan-plugin-source-text` 不应因为共享 helper 在内部构造完整 AST map；已拆回轻量风险构造，`export-plugin-source-ast-map` 才渲染完整 `files[]`。
- 最终只读代码审查指出三类测试缺口：候选字段白名单不够精确、AgentReport 大字段防漏覆盖不完整、未固定单命令 Rust 扫描次数。已补充对应断言，未扩大 6D 生产实现范围。

## 剩余风险

- `prepare_agent_workspace`、工作区验收和插件源码规则导入仍使用旧 `PluginSourceScan`，后续迁移前不能删除 Python 扫描器。
- 规则 selector 覆盖、排除规则、stale rule 校验和写回定位仍需下一批继续迁移或审计。
- 本批只迁移 AST map 导出命令；工作区生成的 `plugin-source-risk-report.json` 尚未消费共享 Rust AST map payload。

## 下一批入口

- 建议下一批：6E `prepare-agent-workspace` 插件源码风险报告接入 Rust AST map 事实。目标是让工作区生成的 `plugin-source-risk-report.json` 复用 Rust 插件源码扫描事实，同时继续保留插件源码规则审查覆盖所需的旧路径，直到规则校验/导入批次完成。
