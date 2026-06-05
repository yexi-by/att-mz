# Rust Scope/Index Engine 批次 41 记录

## 本批范围

- 批次：6J，翻译源 `PluginSourceScan` 通用 fallback 接入 Rust-derived scan。
- 覆盖范围：`quality-report` 两个插件源码审查分支、`flow_gate` 插件源码规则 gate fallback、`TextScopeService.build` 调用方未传 scan 时的翻译源 fallback、`prepare-agent-workspace` 复用 scan 链路、`validate-plugin-source-rules` 和 `import-plugin-source-rules` 的共享 scan helper。
- 成功状态：上述默认翻译源路径不再直接调用旧 Python `build_plugin_source_scan` 主扫描；统一通过 `app/plugin_source_text/native_scan.py` 的 `build_native_plugin_source_scan` 构造 Rust-derived `PluginSourceScan`。
- 明确非范围：active runtime scan cache、写回后运行文件审计、`scan_plugin_source_files_text_strict_with_cache` 和运行文件诊断仍留到下一批。

## 保护网

- 扩展 `tests/test_plugin_source_text.py::test_quality_report_uses_native_plugin_source_scan_before_branch_started`：
  - monkeypatch 禁止旧 `build_plugin_source_scan`。
  - 覆盖 indexed `quality-report` 尚未开始分支前的插件源码风险 gate。
- 扩展 `tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope`：
  - monkeypatch 禁止旧扫描器 fallback。
  - 断言旧 scope 分支的插件源码审查统计来自 Rust-derived scan，并传给 TextScope/写回探针链路复用。
- 新增 `tests/test_plugin_source_text.py::test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan`：
  - 覆盖 `TextScopeService.build` 调用方没有传入 scan、但存在插件源码规则时的通用 fallback。
  - 断言插件源码路径进入 active scope，且没有写回探针错误。
- 新增 `tests/test_plugin_source_text.py::test_plugin_source_rule_filter_fallback_uses_native_plugin_source_scan`：
  - 覆盖 `filter_fresh_plugin_source_text_rules` 调用方未传 scan 时的公共 fallback。
  - monkeypatch 禁止旧扫描器，断言只调用一次 `scan_native_rule_candidates`。
- 新增 `tests/test_plugin_source_text.py::test_plugin_source_import_fallback_uses_native_plugin_source_scan`：
  - 覆盖 `build_plugin_source_rule_records_from_import` 调用方未传 scan 时的公共 fallback。
  - monkeypatch 禁止旧扫描器，断言规则记录仍按 Rust-derived scan 构造。
- 新增 `tests/test_plugin_source_text.py::test_plugin_source_extraction_fallback_uses_native_plugin_source_scan`：
  - 覆盖 `PluginSourceTextExtraction` 调用方未传 scan 时的提取 fallback。
  - monkeypatch 禁止旧扫描器，断言提取项仍进入插件源码 TranslationData。
- 新增 `tests/test_plugin_source_text.py::test_quality_report_write_probe_loads_plugin_source_for_high_risk_gate`：
  - 覆盖 `quality-report --include-write-probe` 尚未启动插件源码支线时的 workflow gate。
  - 断言写回级质量报告会加载插件源码并用 Rust-derived scan 报告 `plugin_source_text_high_risk`。
- 调整 `tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`：
  - 工作区准备阶段禁止旧扫描器。
  - 断言同一份 Rust-derived `PluginSourceScan` 进入 scope 构建和工作区规则链路。
- 新增 `tests/test_scan_budget.py::test_batch41_translation_source_plugin_source_native_fallback_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含本批迁移入口、核心 helper、保护测试和下一批边界。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 新增 `app/plugin_source_text/native_scan.py`：
  - `build_native_plugin_source_scan` 调用 `scan_native_rule_candidates`，把 Rust 插件源码候选事实转换为现有规则链路使用的 `PluginSourceScan`。
  - `build_native_plugin_source_risk_report` 保留给轻量风险摘要入口。
  - `build_native_plugin_source_ast_map_payload` 保留给完整 AST map 导出入口。
  - `native_plugin_source_risk_report_from_scan` 从已构造的 Rust-derived scan 派生轻量风险报告，避免 `prepare-agent-workspace` 为风险摘要和 scope 复用重复扫描。
- 更新 `app/plugin_source_text/__init__.py`，导出 `build_native_plugin_source_scan`，让服务层可以走统一 adapter。
- 更新 `app/agent_toolkit/services/quality.py`：
  - `_collect_text_index_plugin_source_review` 改用 `build_native_plugin_source_scan`。
  - `quality_report` 写回级 scope 分支始终加载翻译源插件源码并构造 Rust-derived scan，保证未导入插件源码规则时也能由 workflow gate 识别高风险源码。
  - 有插件源码规则时继续把同一份 scan 传给 `filter_fresh_plugin_source_text_rules`、`collect_plugin_source_review_coverage` 和 TextScope。
- 更新 `app/application/flow_gate.py`：
  - `_plugin_source_rule_gate_errors` 在调用方未传入 scan 时改用 Rust-derived scan。
- 更新 `app/text_scope/builder.py`：
  - `TextScopeService.build` 的插件源码规则 fallback 改用 Rust-derived scan。
- 更新 `app/agent_toolkit/services/workspace.py`：
  - `prepare-agent-workspace` 先构造一次 Rust-derived scan，再用 `native_plugin_source_risk_report_from_scan` 派生 `plugin-source-risk-report.json`，并把同一份 scan 继续传入 scope 构建。
  - 共享 native helper 从工作区服务内迁出，减少命令服务之间复制同一事实构造逻辑。
- 更新 `app/agent_toolkit/services/rule_validation.py`：
  - `validate-plugin-source-rules` 和 `import-plugin-source-rules` 直接引用公共 `build_native_plugin_source_scan`。
- 更新 `app/plugin_source_text/rules.py`、`app/plugin_source_text/importer.py` 和 `app/plugin_source_text/extraction.py`：
  - 公共 `scan=None` fallback 改用 `build_native_plugin_source_scan`。
  - 已迁移命令仍优先显式传入 scan，公共 fallback 只作为调用方漏传时的同一事实来源兜底。

## 旧路径收束

- 已收束的直接消费者：
  - `quality-report` indexed review。
  - `quality-report` 旧 scope 分支。
  - `flow_gate` 插件源码规则 gate fallback。
  - `TextScopeService.build` 翻译源插件源码 fallback。
  - `prepare-agent-workspace` scope fallback。
  - `validate-plugin-source-rules`。
  - `import-plugin-source-rules`。
  - `filter_fresh_plugin_source_text_rules` 公共 fallback。
  - `build_plugin_source_rule_records_from_import` 公共 fallback。
  - `PluginSourceTextExtraction` 公共 fallback。
- 仍保留旧 `build_plugin_source_scan` 的生产位置：
  - `app/plugin_source_text/scanner.py` 是旧扫描器定义和导出。
  - `app/plugin_source_text/__init__.py` 保留旧导出，避免当前公共 API 断裂。
- 不在本批迁移的路径：
  - active runtime 审计扫描当前运行文件，不等同于翻译源 scan。
  - 写回后运行文件审计和诊断依赖 runtime selector/hash、写回映射和当前文件内容，需要独立批次处理。
  - `app/text_scope/write_probe.py` 在调用方没有传入 `PluginSourceScan` 时仍保留严格 AST fallback；已迁移质量报告、规则校验和 TextScope 路径用测试固定会传入 scan。

## 外部契约变化

- CLI 参数、Agent JSON 字段、错误码、SQLite schema、日志格式和公开目录结构不变。
- `plugin-source-risk-report.json` 继续输出 `risk`、`enabled_plugin_files`、`candidate_count`、`active_candidate_count` 和 `syntax_errors`。
- `syntax_errors` 条目继续保留 `file`、`active` 和 `syntax_error`，由 Rust-derived scan 派生时按启用插件文件集合补齐 active 状态。

## 性能证据

- 质量报告、workflow gate、TextScope fallback、公共规则/导入/提取 fallback 和工作区准备默认翻译源路径已停止直接调用旧 Python `build_plugin_source_scan` 主扫描。
- `prepare-agent-workspace` 原先本批改动中会为风险报告和 scope 复用触发两次 `scan_native_rule_candidates`；已改为一次 Rust-derived scan 后派生风险报告。
- 相邻测试用 monkeypatch 禁止旧扫描器，证明这些默认路径无法回退到旧 Python 主扫描。
- `quality-report --include-write-probe` 在没有插件源码规则时也会加载翻译源插件源码并构造 Rust-derived scan，避免 workflow gate 基于空源码误判为低风险。
- 本批没有迁移 active runtime scan cache，因此写回后运行文件审计的 Python AST 扫描耗时仍是剩余风险。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_quality_report_uses_native_plugin_source_scan_before_branch_started tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope tests/test_plugin_source_text.py::test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`
  - 结果：4 failed，失败原因分别是质量报告、TextScope fallback 和工作区准备仍调用旧 `build_plugin_source_scan`。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_quality_report_uses_native_plugin_source_scan_before_branch_started tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope tests/test_plugin_source_text.py::test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`
  - 结果：4 passed。
- 重复扫描回归：`uv run pytest tests/test_plugin_source_text.py::test_prepare_workspace_writes_plugin_source_risk_summary_without_ast_map`
  - 初次结果：1 failed，失败原因为 `prepare-agent-workspace` 同时构造风险报告和 scan，导致准备阶段调用两次 `scan_native_rule_candidates`。
  - 修复后结果：1 passed。
- 语法错误字段回归：`uv run pytest tests/test_plugin_source_text.py::test_prepare_workspace_warns_and_skips_invalid_plugin_source`
  - 初次结果：1 failed，失败原因为从 scan 派生的 `syntax_errors` 缺少 `active` 字段。
  - 修复后结果：1 passed。
- 文档保护 RED：`uv run pytest tests/test_scan_budget.py::test_batch41_translation_source_plugin_source_native_fallback_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-041.md` 尚不存在。
- 文档保护 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch41_translation_source_plugin_source_native_fallback_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 审查回归 RED：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_rule_filter_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_import_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_extraction_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_quality_report_write_probe_loads_plugin_source_for_high_risk_gate tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope`
  - 结果：4 failed、1 passed。
  - 失败原因：规则过滤、导入和提取公共 fallback 仍调用旧扫描器；写回级质量报告没有加载插件源码，导致 `scan_native_rule_candidates` 未被调用。
- 审查回归 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_rule_filter_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_import_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_extraction_fallback_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_quality_report_write_probe_loads_plugin_source_for_high_risk_gate tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope`
  - 结果：5 passed。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py tests/test_agent_toolkit_workspace.py tests/test_agent_toolkit_workflow_gate.py tests/test_workflow_gate.py tests/test_stage0_canaries.py`
  - 结果：101 passed。
- 记录测试：`uv run pytest tests/test_scan_budget.py`
  - 结果：43 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：798 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。

## 审查处理

- 已按 Superpowers 流程完成只读子代理审查。
- 审查指出：`rules.py`、`importer.py` 和 `extraction.py` 的公共 `scan=None` fallback 仍会回旧扫描器。本批已补充三个 RED 测试，并改为调用公共 `build_native_plugin_source_scan`。
- 审查指出：`quality_report(include_write_probe=True)` 没有插件源码规则时会用未加载源码的 `GameData` 进入 workflow gate，导致高风险插件源码被空扫描掩盖。本批已补充 RED 测试，并让写回级质量报告始终加载翻译源插件源码和构造 Rust-derived scan。
- 审查指出：质量报告写回探针复用测试没有禁止 `scan_plugin_source_files_text_strict` fallback。本批已补充 monkeypatch，固定质量报告写回探针消费同一份 scan。
- 审查确认：active runtime scan cache 没有被误称已迁移，仍保留为下一批边界。

## 剩余风险

- active runtime scan cache、写回后审计和诊断尚未迁移，仍可能在大插件源码项目上承担 Python AST 扫描成本。
- `app/text_scope/write_probe.py` 的严格 AST fallback 仍保留给未迁移调用方；已迁移路径用测试禁止触发，但删除该 fallback 需要等 active runtime scan cache 批次。
- `app/agent_toolkit/services/quality.py::_build_plugin_source_write_map_source_scan_cache` 仍用严格 AST 扫描翻译源文件来诊断 runtime write map；它依赖写回映射、source selector 和 runtime hash，留到 active runtime/诊断批次处理。
- 旧 `build_plugin_source_scan` 还不能删除；删除需要先处理 active runtime、写回探针、诊断和公共 API 导出。

## 下一批入口

- 建议下一批：6K active runtime 插件源码扫描缓存 Rust 化审计和接入。
- 建议边界：优先审计 `audit_active_runtime_plugin_source_with_scan_cache`、`scan_plugin_source_files_text_strict_with_cache`、写回后审计和诊断命令，明确当前运行文件 scan 与翻译源 scan 的差异，再决定 Rust active-runtime scan cache payload 和复用边界。
- 理由：6J 已收束翻译源 `PluginSourceScan` 默认 fallback；剩余重扫描主要来自当前运行文件审计，必须保留 runtime selector/hash 和写回映射语义。
