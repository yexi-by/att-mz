# Rust Scope/Index Engine 批次 40 记录

## 本批范围

- 批次：6I，插件源码运行审计和写回定位相关路径候选事实审计。
- 覆盖范围：6F、6G、6H 已迁移后的剩余插件源码候选事实消费者，重点是 `quality-report`、`write-back`、`audit-active-runtime`、`diagnose-active-runtime`、workflow gate、TextScope fallback、写回探针和运行文件扫描缓存。
- 成功状态：本批只做静态审计和保护网，不迁移生产逻辑；输出剩余旧路径矩阵、明确下一批最小迁移入口，并用测试固定记录不能漏掉当前生产代码中的旧扫描消费者。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch40_plugin_source_runtime_audit_record_exists_and_covers_remaining_scan_paths`：
  - 断言本记录被计划文件链接。
  - 自动搜索 `app/**/*.py` 中仍直接提到 `build_plugin_source_scan` 的生产文件，排除扫描器定义和包导出文件后，要求每个剩余消费者都写入本记录。
  - 断言记录覆盖 `audit_active_runtime_plugin_source_with_scan_cache`、`scan_plugin_source_files_text_strict_with_cache`、`scan_plugin_source_files_text_strict`、`plugin_source_runtime_write_maps`、`collect_write_back_probe_reasons`、`_plugin_source_rule_gate_errors`、`_collect_text_index_plugin_source_review`、`quality-report`、`write-back`、`audit-active-runtime` 和 `diagnose-active-runtime`。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 剩余旧路径审计矩阵

| 路径 | 入口或函数 | 当前事实来源 | 处理结论 |
| --- | --- | --- | --- |
| `app/agent_toolkit/services/quality.py` | `_collect_text_index_plugin_source_review` | 直接调用 `build_plugin_source_scan`，为 indexed `quality-report` 补插件源码审查 gate | 下一批优先迁移。可改为复用 Rust-derived `PluginSourceScan`，并同步更新 `quality-report` 扫描预算测试。 |
| `app/agent_toolkit/services/quality.py` | `quality_report` 旧 scope 分支 | 有插件源码规则时直接调用 `build_plugin_source_scan`，后续传给 `filter_fresh_plugin_source_text_rules`、`collect_plugin_source_review_coverage` 和 TextScope | 下一批优先迁移。该路径和 indexed review 同属质量报告插件源码审查事实。 |
| `app/application/flow_gate.py` | `_plugin_source_rule_gate_errors` | 未传入 scan 时直接调用 `build_plugin_source_scan` | 下一批优先迁移。调用方可传入 Rust-derived scan，保留函数参数作为薄适配边界。 |
| `app/agent_toolkit/services/workspace.py` | `prepare_agent_workspace` scope fallback | 风险报告已用 Rust 候选事实，但后续 TextScope fallback 仍构造旧 `PluginSourceScan` | 保留为剩余工作区 fallback。后续批次应把 prepare 的同一份 Rust-derived scan 传入 `_extract_active_translation_data_map`。 |
| `app/text_scope/builder.py` | `TextScopeService.build` | 有插件源码规则且调用方未传 scan 时直接调用 `build_plugin_source_scan` | 保留为通用 fallback，不应成为已迁移命令默认路径。后续迁移命令必须显式传 scan 并用测试禁止 fallback。 |
| `app/plugin_source_text/extraction.py` | `PluginSourceTextExtraction._scan_for_validation` | 提取器未传 scan 时延迟调用 `build_plugin_source_scan` | 保留为内部兜底，后续只能由小规模或测试夹具触发；默认命令应传入 Rust-derived scan。 |
| `app/plugin_source_text/importer.py` | `build_plugin_source_rule_records_from_import` | 调用方未传 scan 时直接调用 `build_plugin_source_scan` | 6H 的 `import-plugin-source-rules` 已传 Rust-derived scan；此处保留为公共函数 fallback。 |
| `app/plugin_source_text/rules.py` | `filter_fresh_plugin_source_text_rules` | 调用方未传 scan 时直接调用 `build_plugin_source_scan` | 已迁移入口应传 scan；该 fallback 后续随调用点逐步清理。 |
| `app/plugin_source_text/runtime_audit.py` | `audit_active_runtime_plugin_source_with_scan_cache` | 使用 `scan_plugin_source_files_text_strict_with_cache`，缓存 miss 时回到 `scan_plugin_source_files_text_strict` | 暂不在本批迁移。它扫描当前运行文件，和翻译源候选扫描不是同一输入；后续需要 Rust active-runtime 扫描缓存边界。 |
| `app/application/handler.py` | `write_back` 写入后审计 | 写回计划的 `plugin_source_runtime_write_maps` 已来自 Rust native write plan，但写入后 active runtime 审计仍调用 Python scan cache | 后续单独迁移。该路径必须保持写回后真实运行文件审计，不可直接复用写回前翻译源 scan。 |
| `app/agent_toolkit/services/quality.py` | `audit_active_runtime`、`diagnose_active_runtime` | 读取 `plugin_source_runtime_write_maps` 和运行扫描缓存，调用 `audit_active_runtime_plugin_source_with_scan_cache` | 后续单独迁移。诊断还会把 runtime selector/hash 反推到翻译源记录，迁移时要保留错误解释和建议文案。 |
| `app/agent_toolkit/services/quality.py` | `_plugin_source_write_map_source_matches` | 用运行写回映射的 source selector 在翻译源 scan cache 中查找候选，并比对 `plugin_source_runtime_hash_text` | 暂不独立迁移。它依赖写回映射和翻译源文件 hash，适合跟 active-runtime Rust scan cache 一起处理。 |
| `app/text_scope/write_probe.py` | `collect_write_back_probe_reasons` | 调用方未传 `PluginSourceScan` 时用 `scan_plugin_source_files_text_strict` 做写回探针 | 保留为 fallback。已迁移命令应传入 scan 或使用 Rust write plan gate，不让探针重复扫描全部插件源码。 |
| `app/plugin_source_text/scanner.py` | `find_candidate_by_selector` | 旧扫描器中的 selector 查询辅助函数 | 当前未发现生产调用者；保留为旧扫描器内部 API，删除时需和扫描器清理批次一起处理。 |

## 旧路径收束

- 已迁移入口：
  - `scan-plugin-source-text` 使用 Rust native candidate scan 薄适配。
  - `export-plugin-source-ast-map` 使用 Rust native AST map 事实。
  - `prepare-agent-workspace` 的插件源码风险报告使用 Rust candidate 事实。
  - `validate-agent-workspace` 插件源码支线使用 Rust-derived `PluginSourceScan`。
  - `validate-plugin-source-rules` 使用 Rust-derived `PluginSourceScan`。
  - `import-plugin-source-rules` 使用 Rust-derived `PluginSourceScan`。
- 尚未收束的旧路径分三类：
  - 质量报告和 workflow gate 仍直接消费旧翻译源 `build_plugin_source_scan`。
  - TextScope、提取器、规则解析和导入公共函数仍保留 fallback；这些 fallback 不应被已迁移 CLI 默认路径触发。
  - active runtime 审计、写入后审计、诊断和写回探针仍使用严格文本扫描或扫描缓存；这些路径扫描的是当前运行文件，不能简单复用翻译源候选 scan。

## 外部契约变化

- 本批不修改生产代码、CLI 参数、Agent JSON 报告、SQLite schema、Rust native payload、日志格式或错误文案。
- 本批新增一条批次记录测试，属于开发期静态保护网，不改变公开用户契约。
- 计划文件新增 6I 进度行，用于后续会话定位下一批入口。

## 性能证据

- 静态搜索确认除扫描器定义和包导出外，当前仍有 7 个生产文件直接提到 `build_plugin_source_scan`：
  - `app/agent_toolkit/services/quality.py`
  - `app/agent_toolkit/services/workspace.py`
  - `app/application/flow_gate.py`
  - `app/plugin_source_text/rules.py`
  - `app/plugin_source_text/importer.py`
  - `app/plugin_source_text/extraction.py`
  - `app/text_scope/builder.py`
- 运行审计相关路径不直接使用 `build_plugin_source_scan`，但仍通过 `scan_plugin_source_files_text_strict_with_cache` 和 `scan_plugin_source_files_text_strict` 做 active runtime AST 扫描。
- 写回计划里的 `plugin_source_runtime_write_maps` 已由 Rust native write plan 生成；写入后审计和诊断仍需要对当前运行文件重新扫描，这是独立于翻译源候选 scan 的剩余性能风险。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch40_plugin_source_runtime_audit_record_exists_and_covers_remaining_scan_paths`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-040.md` 尚不存在。
- GREEN：`uv run pytest tests/test_scan_budget.py::test_batch40_plugin_source_runtime_audit_record_exists_and_covers_remaining_scan_paths`
  - 结果：1 passed。
- 局部类型检查：`uv run basedpyright tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 相邻回归：`uv run pytest tests/test_scan_budget.py`
  - 结果：42 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：792 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- 最终记录复验：`uv run pytest tests/test_scan_budget.py::test_batch40_plugin_source_runtime_audit_record_exists_and_covers_remaining_scan_paths`
  - 结果：1 passed。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。

## 审查处理

- 已按 Superpowers 流程完成只读子代理审计。
- 审查确认：`quality-report` 的 indexed review 和旧 scope 分支仍直接构造旧 `build_plugin_source_scan`；`flow_gate._plugin_source_rule_gate_errors` 仍保留 `scan is None` 旧 fallback；`TextScopeService.build`、`PluginSourceTextExtraction`、`filter_fresh_plugin_source_text_rules`、`build_plugin_source_rule_records_from_import` 和 `collect_write_back_probe_reasons` 仍保留通用 fallback。
- 审查确认：`validate-agent-workspace`、`validate-plugin-source-rules` 和 `import-plugin-source-rules` 已经传入 Rust-derived `PluginSourceScan`，但它们复用的公共函数仍允许调用方不传 scan 时回到旧路径。
- 审查确认：`find_candidate_by_selector` 当前没有生产调用者，只是旧扫描器定义和导出；真实 selector 定位分散在提取器、规则过滤、写回探针和 Rust write plan 里。
- 审查建议：下一批先迁移翻译源 `PluginSourceScan` 通用 fallback，把 active runtime 的 `scan_plugin_source_files_text_strict_with_cache` 留到后续批次；本记录已按该建议调整下一批入口。

## 剩余风险

- 本批只做审计，不降低运行时耗时。
- `quality-report` 和 workflow gate 仍可能在默认流程里触发旧翻译源扫描。
- active runtime 审计扫描当前运行文件，后续迁移需要新增或复用 Rust active-runtime scan cache 边界，不能把翻译源 scan 当作等价事实来源。
- 写回诊断依赖 runtime selector、source selector、runtime hash、source hash 和已保存译文 hash；迁移时必须保持定位和建议文案等价。

## 下一批入口

- 建议下一批：6J 翻译源 `PluginSourceScan` 通用 fallback 接入 Rust-derived scan。
- 建议边界：把 `_build_native_plugin_source_scan` 从工作区服务中移到可复用生产模块，替换 `quality-report` 两个插件源码 review 分支、`flow_gate._plugin_source_rule_gate_errors`、`TextScopeService.build` 和 `prepare-agent-workspace` 中的直接旧 scan 构造；暂不迁移 active runtime scan cache。
- 理由：该边界全部扫描翻译源插件源码，能复用 6F、6G、6H 已验证的 Rust-derived `PluginSourceScan` 契约，并可用 monkeypatch 禁止 `build_plugin_source_scan` 来验证默认命令不回旧路径；active runtime 审计需要当前运行文件、runtime scan cache 和 runtime map 语义，独立放到后一批风险更低。
