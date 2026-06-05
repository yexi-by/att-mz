# Rust Scope/Index Engine 批次 37 记录

## 本批范围

- 批次：6F，`validate-agent-workspace` 插件源码支线候选事实接入 Rust。
- 覆盖入口：Agent/CLI 子服务 `validate_agent_workspace` 中插件源码支线的候选扫描、文本范围复用和工作区插件源码规则校验。
- 成功状态：工作区验收不再调用旧 Python `build_plugin_source_scan` 主扫描；改为通过 `scan_native_rule_candidates` 构造兼容旧规则链路的 `PluginSourceScan`，并把同一份扫描结果传给文本范围构建和插件源码规则校验。

## 保护网

- 新增 `tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`：
  - 构造带有效插件源码规则的工作区，使 `validate_agent_workspace` 必须进入插件源码支线。
  - monkeypatch `app.agent_toolkit.services.workspace.build_plugin_source_scan` 为失败函数，禁止工作区验收回到旧 Python 主扫描。
  - monkeypatch `app.text_scope.builder.build_plugin_source_scan` 为失败函数，证明文本范围构建消费了已经构造好的插件源码扫描结果，没有隐藏二次扫描。
  - monkeypatch `app.text_scope.write_probe.scan_plugin_source_files_text_strict` 为失败函数，证明写回探针消费同一份 `PluginSourceScan`，没有在规则校验阶段重新执行插件源码 AST 扫描。
  - monkeypatch 计数 `app.agent_toolkit.services.workspace.scan_native_rule_candidates`，断言本轮插件源码支线只调用一次 Rust 候选扫描。
  - 断言工作区验收不会产生插件源码支线错误，并保留 `plugin_source_rules` 明细。
- 扩展 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`：
  - 固定 Rust 插件源码候选里的 `raw_text`、`quote`、`line`、`start_index`、`end_index`、`content_start_index` 和 `content_end_index` 字段，避免 Rust-derived `PluginSourceScan` 转换链路丢失旧 selector 定位所需的字段。
- 新增 `tests/test_scan_budget.py::test_batch37_validate_workspace_plugin_source_native_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `validate_agent_workspace`、`scan_native_rule_candidates`、`PluginSourceScan`、`build_plugin_source_scan` 和本批命令级测试名。

## 改动范围

- `app/agent_toolkit/services/workspace.py`
  - 新增 `_build_native_plugin_source_scan`，从 Rust 插件源码候选结果构造旧规则链路使用的 `PluginSourceScan`。
  - 新增 Rust 候选到 `PluginSourceCandidate` 的转换函数，以及 Rust 语法错误数组到旧 `syntax_errors` 字典的转换函数。
  - `validate_agent_workspace` 在插件源码支线活跃时先构造 Rust-derived `PluginSourceScan`，再传给 `_extract_active_translation_data_map` 和 `_validate_workspace_plugin_source_rules`。
  - `validate_agent_workspace` 不再调用 `build_plugin_source_scan`。
- `app/text_scope/write_probe.py`
  - `collect_write_back_probe_reasons` 新增可选 `plugin_source_scan` 参数。
  - 有现成 `PluginSourceScan` 时，写回探针直接按文件、语法错误、selector 和原文校验写回可行性，不再调用 `scan_plugin_source_files_text_strict`。
- `app/text_scope/builder.py`
  - 文本范围构建时把已解析的 `plugin_source_scan` 传给写回探针。
- `app/agent_toolkit/services/common.py`
  - 插件源码规则校验把调用方传入的同一份 `PluginSourceScan` 继续传给写回探针，避免校验阶段二次扫描。
- `tests/test_agent_toolkit_workspace.py`
  - 新增 6F 命令级回归测试，固定 Rust 候选事实源和单次扫描预算。
- `tests/test_native_scope_index.py`
  - 补充插件源码候选定位字段断言，覆盖审查指出的字段保护缺口。
- `tests/test_scan_budget.py`
  - 新增批次 37 验收记录测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 新增 6F 批次进度行。

## 旧路径收束

- `validate_agent_workspace` 插件源码支线已停止消费旧 Python `build_plugin_source_scan` 主扫描。
- 旧 `PluginSourceScan` 数据结构仍保留，作为当前插件源码规则校验、文本范围提取和 selector/hash 覆盖逻辑的兼容输入。
- `validate-plugin-source-rules` 和 `import-plugin-source-rules` 仍直接使用旧扫描入口，后续批次迁移前不能删除旧扫描器。

## 外部契约变化

- `validate-agent-workspace` 的外部 JSON 报告结构不变。
- `details.plugin_source_rules` 继续沿用既有规则校验明细。
- 插件源码规则缺失、空规则、高风险未审查、已启动支线未审查等错误码保持不变。
- 工作区 manifest、`plugin-source-rules.json` 和 `plugin-source-risk-report.json` 的文件契约不变。

## 性能证据

- 命令级保护网证明 `validate_agent_workspace` 插件源码支线不再调用旧 `build_plugin_source_scan`。
- 命令级保护网证明文本范围构建不再隐藏调用旧插件源码主扫描。
- 命令级保护网证明写回探针不再隐藏调用旧插件源码 AST 严格扫描。
- 命令级保护网断言插件源码支线只调用一次 `scan_native_rule_candidates`，并复用同一份 Rust-derived `PluginSourceScan`。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
  - 结果：1 failed，失败原因为文本范围构建调用了被 monkeypatch 的旧 Python `build_plugin_source_scan`。
- GREEN：`uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
  - 结果：1 passed。
- 审查修复 RED：`uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
  - 结果：1 failed，失败原因为写回探针调用了被 monkeypatch 的旧 `scan_plugin_source_files_text_strict`，最终表现为插件源码支线错误。
- 审查修复 GREEN：`uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
  - 结果：1 passed。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py tests/test_agent_toolkit_workspace.py`
  - 结果：0 errors，0 warnings，0 notes。
- 审查修复局部类型检查：`uv run basedpyright app/agent_toolkit/services/workspace.py app/agent_toolkit/services/common.py app/text_scope/write_probe.py app/text_scope/builder.py tests/test_agent_toolkit_workspace.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 定向回归：`uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_rejects_high_risk_empty_plugin_source_review tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_skips_inactive_heavy_branch_scans tests/test_plugin_source_text.py::test_prepare_workspace_warns_and_skips_invalid_plugin_source`
  - 结果：4 passed。
- 审查修复定向回归：`uv run pytest tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_rejects_high_risk_empty_plugin_source_review tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_skips_inactive_heavy_branch_scans tests/test_plugin_source_text.py::test_prepare_workspace_warns_and_skips_invalid_plugin_source tests/test_scan_budget.py::test_batch37_validate_workspace_plugin_source_native_record_exists_and_tracks_contract`
  - 结果：5 passed。
- 字段保护 RED：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`
  - 结果：1 failed，失败原因为测试把当前契约中的 `raw_text` 误判为带引号源码片段；确认当前契约是字面量内容本身。
- 字段保护 GREEN：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`
  - 结果：1 passed。
- 字段保护类型检查：`uv run basedpyright tests/test_native_scope_index.py app/text_scope/write_probe.py app/text_scope/builder.py app/agent_toolkit/services/common.py`
  - 结果：0 errors，0 warnings，0 notes。
- 文档记录 RED：`uv run pytest tests/test_scan_budget.py::test_batch37_validate_workspace_plugin_source_native_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-037.md` 尚不存在。
- 文档记录 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch37_validate_workspace_plugin_source_native_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 相邻回归：`uv run pytest tests/test_agent_toolkit_workspace.py tests/test_plugin_source_text.py tests/test_scan_budget.py tests/test_native_scope_index.py`
  - 结果：114 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：787 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。

## 审查处理

- 已按 Superpowers 流程完成只读代码审查。
- Critical：无。
- Important：审查指出 `_validate_plugin_source_rules_with_context` 会经由写回探针调用 `scan_plugin_source_files_text_strict`，导致插件源码规则校验阶段仍存在二次 AST 扫描。本批已补 RED 保护网，并让 `collect_write_back_probe_reasons` 接收现成 `PluginSourceScan` 后复用 selector、语法错误和原文事实。
- Minor：审查指出 Rust 候选字段保护不够直接。本批已补充原生候选字段断言；文档记录也补上了 GREEN 结果。

## 剩余风险

- `validate-plugin-source-rules` 和 `import-plugin-source-rules` 仍使用旧 Python 主扫描，后续迁移前不能删除旧扫描器。
- Rust-derived `PluginSourceScan` 目前只接入 `validate_agent_workspace`；其他命令仍需逐批迁移。
- 插件源码写回定位和运行文件审计仍依赖旧 selector/hash 语义，后续迁移必须继续保持外部契约等价。

## 下一批入口

- 建议下一批：6G `validate-plugin-source-rules` 插件源码候选事实接入 Rust。目标是让独立插件源码规则校验命令也消费 Rust-derived `PluginSourceScan`，并继续保留导入和写回定位所需的旧字段契约。
