# Rust Scope/Index Engine 批次 34 记录

## 本批范围

- 批次：6C，`scan-plugin-source-text` 薄适配接入。
- 覆盖入口：Agent/CLI 子服务 `scan_plugin_source_text`、Python `scan_native_rule_candidates` 适配层和 Rust `scan_rule_candidates(plugin_source)` 摘要。
- 成功状态：`scan-plugin-source-text` 不再调用 Python `build_plugin_source_scan` 主扫描；Python 只负责读取游戏文件、构造 Rust payload、渲染原有轻量风险报告和写出 Agent JSON。

## 保护网

- 新增 `tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan`：
  - monkeypatch `app.agent_toolkit.services.workspace.build_plugin_source_scan` 为失败函数。
  - 断言 `scan_plugin_source_text` 仍能输出风险报告，证明该命令已经消费 Rust 候选入口。
  - 断言 `candidate_count`、`active_candidate_count`、`source_view`、`risk_score` 和 strong context 计数保持外部 JSON 语义。
- 新增 `tests/test_plugin_source_text.py::test_scan_plugin_source_text_handles_empty_plugin_source_files`：
  - 删除夹具中的直接插件源码文件，构造 `plugin_source_files` 为空的命令路径。
  - 断言命令不因 Rust `scan_summary.plugin_source` 缺失而崩溃，并保留旧的空风险报告和 `plugin_source_text_empty` 告警。
- 新增 `tests/test_plugin_source_text.py::test_scan_plugin_source_text_keeps_python_only_source_pattern_contract`：
  - 使用 Python `re` 支持但 Rust `regex` 不支持的 lookbehind 源文识别规则。
  - 断言 `scan_plugin_source_text` 仍能输出报告，证明命令没有把用户配置升级成 Rust regex 约束。
- 调整 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`：
  - 断言 `scan_summary.plugin_source.syntax_errors` 返回非法 JS 文件明细。
  - 语法错误明细保持 `file`、`active` 和 `syntax_error` 字段，供风险报告告警复用。
- 调整 `tests/test_native_adapters.py::test_native_rule_candidates_requires_scan_summary`：
  - 断言 native contract 6 的规则候选输出仍必须包含 `scan_summary`。
- 新增 `tests/test_scan_budget.py::test_batch34_scan_plugin_source_text_native_adapter_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `scan_plugin_source_text`、`scan_native_rule_candidates`、`build_plugin_source_scan` 和本批命令级测试名。

## 改动范围

- `app/agent_toolkit/services/workspace.py`
  - `scan_plugin_source_text` 改为调用 `scan_native_rule_candidates`。
  - 新增 `_build_native_plugin_source_risk_report`，把 Rust 候选 JSON 还原为旧轻量风险报告结构。
  - 新增 `_empty_native_plugin_source_risk_report`，在没有可读插件源码文件时直接输出旧语义空风险报告。
  - 新增 Rust 候选 JSON 字段读取校验，候选数和启用候选数与 `scan_summary.plugin_source` 不一致时显式失败。
  - 新增 `_plugin_source_native_scan_warnings`，从 Rust `syntax_errors` 渲染原有插件源码语法错误告警。
- `app/native_scope_index.py`
  - 新增 `build_native_rule_candidate_text_rules_payload` 和 `build_native_plugin_source_candidates_payload`。
  - Python 侧统一把提取规则和插件源码文件压成 Rust 候选扫描 payload。
  - Rust payload 只使用宽松源文预筛正则，避免把 Python-only `source_text_required_pattern` 交给 Rust regex 编译。
- `rust/src/native_core/scope_index/mod.rs`
  - `scan_summary.plugin_source` 新增 `syntax_errors` 数组。
  - 插件源码候选文件扫描结果保留 `file_name`，用于生成稳定语法错误明细。
- `app/native_contract.py` 与 `rust/src/lib.rs`
  - `NATIVE_CONTRACT_VERSION = 6`，避免旧扩展缺少 `scan_summary.plugin_source.syntax_errors` 时继续通过版本检查。
- `tests/test_plugin_source_text.py`
  - 新增命令级薄适配回归测试。
- `tests/test_native_scope_index.py`
  - 补齐 Rust 插件源码候选摘要的语法错误明细断言。
- `tests/test_scan_budget.py`
  - 新增批次 34 验收记录测试。

## 旧路径收束

- `scan_plugin_source_text` 已停止消费 `PluginSourceScan`，不再执行 Python 插件源码 AST 主扫描。
- `build_plugin_source_scan` 仍保留在 `workspace.py`，仅供本批未迁移的命令使用：
  - `export_plugin_source_ast_map`
  - `prepare_agent_workspace`
  - `validate-agent-workspace`
  - `validate-plugin-source-rules`
  - `import-plugin-source-rules`
- 本批没有删除旧扫描器，因为完整 AST map、规则导入校验和写回 selector 定位仍需要后续批次逐步迁移。

## 外部契约变化

- `scan-plugin-source-text` 输出文件继续保留：
  - `risk`
  - `enabled_plugin_files`
  - `candidate_count`
  - `active_candidate_count`
  - `syntax_errors`
  - `source_view`
- `risk` 内阈值和计分规则保持不变：
  - 仅统计启用插件候选。
  - `risk_score = strong_context_text_count * 3 + medium_confidence_text_count`。
  - 高风险阈值继续使用 strong 总数、总分、多文件分数和单文件 strong 数组合判断。
- Rust `scan_summary.plugin_source` 新增 `syntax_errors`，用于命令报告渲染；该字段属于 native contract 6 的摘要输出扩展。
- `export-plugin-source-ast-map` 的完整 AST map JSON 在本批不变。

## 性能证据

- 命令级保护网用 monkeypatch 证明 `scan_plugin_source_text` 不再调用 Python `build_plugin_source_scan`。
- 插件源码 AST 字符串扫描由 Rust `tree-sitter-javascript` 执行，多文件扫描继续使用 `rayon` 并行。
- Python 侧只遍历 Rust 返回候选一次，用于还原轻量风险摘要；不再构造 `PluginSourceCandidateIndex`、`PluginSourceFileScan` 或完整 AST map。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan`
  - 结果：1 failed，失败原因为 `scan_plugin_source_text` 调用了被 monkeypatch 的 Python `build_plugin_source_scan`。
- RED：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`
  - 结果：1 failed，失败原因为 Rust `scan_summary.plugin_source` 缺少 `syntax_errors`。
- 文档记录 RED：`uv run pytest tests/test_scan_budget.py::test_batch34_scan_plugin_source_text_native_adapter_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-034.md` 尚不存在。
- Rust 格式化：`cargo fmt --manifest-path rust/Cargo.toml`
  - 结果：通过。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py app/native_scope_index.py`
  - 结果：0 errors，0 warnings，0 notes。
- 构建：`uv run maturin develop --manifest-path rust/Cargo.toml`
  - 结果：通过，已安装当前 Rust 原生扩展。
- GREEN：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`
  - 结果：1 passed。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan`
  - 结果：1 passed。
- 审查回归 RED：`uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_keeps_python_only_source_pattern_contract`
  - 结果：1 failed，失败原因为 Rust regex 不支持 Python lookbehind。
- 审查回归 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_keeps_python_only_source_pattern_contract`
  - 结果：1 passed。
- 边界 RED：`uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_handles_empty_plugin_source_files`
  - 结果：1 failed，失败原因为 `scan_summary.plugin_source` 缺失导致 `KeyError`。
- 边界 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_scan_plugin_source_text_handles_empty_plugin_source_files`
  - 结果：1 passed。
- 本批定向回归：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan tests/test_scan_budget.py::test_batch34_scan_plugin_source_text_native_adapter_record_exists_and_tracks_contract`
  - 结果：3 passed。
- 审查后定向回归：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files tests/test_plugin_source_text.py::test_scan_plugin_source_text_uses_native_candidate_scan tests/test_plugin_source_text.py::test_scan_plugin_source_text_keeps_python_only_source_pattern_contract tests/test_plugin_source_text.py::test_scan_plugin_source_text_handles_empty_plugin_source_files tests/test_native_adapters.py::test_native_rule_candidates_requires_scan_summary tests/test_scan_budget.py::test_batch34_scan_plugin_source_text_native_adapter_record_exists_and_tracks_contract`
  - 结果：6 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：782 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- diff 空白检查：`git diff --check`
  - 结果：通过；仅输出 Windows 换行提示。

## 审查处理

- 已派发只读子代理审查 `scan-plugin-source-text` 的既有风险报告契约、6C 不可触碰边界和潜在实现风险。
- 子代理指出启用插件源码文件名应与旧扫描器保持 `.strip()` 和跳过空名语义；已按旧实现对齐。
- 自审发现没有可读插件源码文件时 Rust 不返回 `scan_summary.plugin_source`；已补边界测试和空风险报告分支。
- 子代理指出新增 `scan_summary.plugin_source.syntax_errors` 需要 native contract 防旧扩展；已升级到 `NATIVE_CONTRACT_VERSION = 6`。
- 子代理指出 `source_text_required_pattern` 只承诺 Python `re`；已改为 Rust 宽松预筛，Python 薄报告层用 `TextRules.should_translate_source_text` 执行最终过滤。
- 当前实现显式保留旧风险字段和计分阈值，并通过命令级测试固定不再调用 Python AST 主扫描。

## 剩余风险

- `export_plugin_source_ast_map` 仍然需要完整 AST map，尚未消费 Rust 候选入口。
- `prepare_agent_workspace`、工作区验收和插件源码规则导入仍使用旧 `PluginSourceScan`，后续迁移前不能删除 Python 扫描器。
- 本批只迁移轻量风险报告；规则 selector 覆盖、排除规则和写回定位仍需要下一批继续验证。

## 下一批入口

- 建议下一批：6D `export-plugin-source-ast-map` 接入 Rust 候选/AST map 输出。目标是让完整 AST map 报告消费 Rust 插件源码扫描事实，同时继续保留 selector、raw_text、AST 上下文和风险摘要的外部 JSON 结构。
