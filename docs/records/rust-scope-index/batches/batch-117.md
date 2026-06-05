# Rust Scope/Index Engine 批次 117 验收记录

## 本批范围

- 批次编号：6CH。
- 范围：P1-B 插件参数规则 validate/import 迁移评估与最小契约。
- 命令：`validate-plugin-rules`、`import-plugin-rules`。
- 目标事实来源：`Rust scan_rule_candidates(plugin_config) rule_summaries/hit_details`。

## RED/GREEN

- RED：新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_config_rule_hits`，旧 Rust payload 忽略 `plugin_config_plugins` / `plugin_config_rules`，候选摘要为空。
- RED：新增 `tests/test_scan_budget.py::test_batch117_p1b_plugin_config_native_contract_tracks_current_boundary`，旧预算仍把插件参数规则标为 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。
- GREEN：新增 Rust `plugin_config` 候选模块，`scan_rule_candidates(plugin_config)` 返回 `rule_summaries`、`hit_details`、`plugin_hash`、`string_leaf_count` 和 `plugin_config` 候选摘要。

## 改动范围

- `rust/src/native_core/scope_index/plugin_config.rs`：新增插件参数配置扫描、JSON 字符串容器展开、JSONPath 匹配、插件哈希和命中明细输出。
- `rust/src/native_core/scope_index/mod.rs`：新增 `plugin_config_plugins`、`plugin_config_rules` payload 字段，并把 `plugin_config::scan_plugin_config_rule_candidates` 接入 `scan_rule_candidates`。
- `app/native_scope_index.py`：新增 `build_native_plugin_config_candidates_payload`，只组装当前 `plugins.js` 输入和文本规则，不做 Python 叶子扫描。
- `app/plugin_text/native_validation.py`：新增 `build_native_plugin_rule_validation_context_from_import` 等 native 上下文构建函数，供 6CI 薄适配复用。
- `tests/scan_budget_contract.py`：把 `validate-plugin-rules`、`import-plugin-rules` 从待迁移集合移出，权威来源改为 `Rust scan_rule_candidates(plugin_config) rule_summaries/hit_details`。

## 旧路径收束

- `RuleCandidatesPayload` 不再缺失 `plugin_config` 输入字段。
- 插件参数规则的规则摘要和命中明细不再由 Python `PluginTextExtraction` 作为 validate/import 的权威事实来源。
- 旧 `build_plugin_rule_records_from_import` 保留为插件文本模块的直接单元测试和旧提取器边界测试对象，但不再作为 `validate-plugin-rules` / `import-plugin-rules` 的生产入口。

## 外部契约变化

- CLI JSON schema、退出码和用户可见错误语义保持不变。
- Rust 原生 `scan_rule_candidates` payload 增加 `plugin_config_plugins` 和 `plugin_config_rules` 字段。
- Rust 原生 `scan_summary.plugin_config` 增加 `plugins`、`rule_summaries`、`hit_details`、`candidate_count`、`string_leaf_count`。

## 性能证据

- 插件参数规则命中现在由一次 Rust `scan_rule_candidates(plugin_config)` 给出。
- 每条规则路径的字符串命中数和可翻译命中数来自同一 native 扫描结果，validate/import 不需要各自展开 `plugins.js` 叶子。
- 预算表固定 `candidate_scan_count=1`、`plugin_source_ast_scan_count=0`。

## 验证结果

- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_config_rule_hits`：1 passed。
- `cargo test --manifest-path rust/Cargo.toml scan_rule_candidates_scans_plugin_config_rule_hits`：1 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：73 passed。
- `uv run basedpyright`：0 errors, 0 warnings。
- `git diff --check`：通过，仅输出 CRLF 换行提示。
- 文档敏感路径搜索：NO_MATCH。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

- 本批修改生产代码。
- 本批修改 Rust 原生代码。
- 本批新增 native contract 测试、scan_budget 当前边界测试和 Rust 单元测试。
- 文档敏感路径搜索结果为 NO_MATCH。

## 剩余风险

- 本批不处理 MV 虚拟名字框和源文残留命令族，它们仍在剩余路线中。
- 本批未跑全量 Python pytest，剩余风险是未覆盖的插件参数边缘测试可能存在回归；已用目标行为测试、类型检查和 Rust 全量测试降低风险。

## 下一批入口

- 进入 6CI：P1-B 插件参数规则 validate/import 薄适配与旧路径收束。
