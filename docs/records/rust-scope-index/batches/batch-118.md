# Rust Scope/Index Engine 批次 118 验收记录

## 本批范围

- 批次编号：6CI。
- 范围：P1-B 插件参数规则 validate/import 薄适配与旧路径收束。
- 命令：`validate-plugin-rules`、`import-plugin-rules`。
- 目标：两条命令共用 `scan_rule_candidates(plugin_config)` 的 `rule_summaries` 与 `hit_details`，不再回到旧 Python 插件参数全量提取路径。

## RED/GREEN

- RED：新增 `tests/test_agent_toolkit_rule_import.py::test_validate_plugin_rules_uses_native_plugin_config_hit_details`，旧实现调用 `PluginTextExtraction` / `build_plugin_rule_records_from_import` 时失败。
- RED：新增 `tests/test_agent_toolkit_rule_import.py::test_import_plugin_rules_uses_native_plugin_config_context`，旧导入链路调用 `build_plugin_rule_records_from_import` 时失败。
- RED：新增 `tests/test_scan_budget.py::test_batch118_p1b_plugin_config_validate_import_adapter_tracks_current_boundary`，旧 common/handler 调用链仍引用旧路径时失败。
- GREEN：`validate-plugin-rules` 先构建 native context，再按 native 给出的 translation prefixes 读取已保存译文并渲染报告。
- GREEN：`import-plugin-rules` 使用同一 native context 构造 `PluginTextRuleRecord`，保留旧译文备份、删除、规则替换和空规则确认事务。

## 改动范围

- `app/agent_toolkit/services/rule_validation.py`：`validate_plugin_rules` 改为消费 `build_native_plugin_rule_validation_context_from_import`，删除 `_plugin_rule_prefixes` 和旧记录构建入口。
- `app/agent_toolkit/services/common.py`：`_validate_plugin_rules_with_context` 改为 native context；新增 `build_plugin_rule_validation_report_from_native_context`；删除死代码 `_validate_plugin_rule_records_with_context`。
- `app/application/handler.py`：`import_plugin_rules` 改为消费 native context 的 `records`，数据库事务和备份流程保持原契约。
- `tests/test_agent_toolkit_rule_import.py`：新增 validate/import 两条旧路径防回退测试。
- `tests/test_scan_budget.py`：新增 6CI 当前边界和记录保护测试。

## 旧路径收束

- `validate-plugin-rules` 不再构造旧 `PluginTextExtraction`。
- `validate-plugin-rules` 不再调用旧 `build_plugin_rule_records_from_import`。
- `import-plugin-rules` 不再调用旧 `build_plugin_rule_records_from_import`。
- 旧 `PluginTextExtraction` 仍保留给插件文本提取模块自身和未下线翻译源路径；本批只下线 validate/import 的旧事实来源。

## 外部契约变化

- 公开 CLI 命令、参数、退出码、JSON 报告字段和空规则确认行为保持不变。
- JSON 字符串容器误指向提示仍包含“解析后的内部字符串叶子”和候选 JSONPath。
- 英文协议噪音路径仍按当前配置拒绝或放行。

## 性能证据

- validate/import 共用 `build_native_plugin_rule_validation_context_from_import` 生成的 native 命中事实。
- 已保存译文计数只按 native context 提供的插件前缀调用 `read_translated_items_by_prefixes`。
- 预算表固定 `validate-plugin-rules` 与 `import-plugin-rules` 的权威来源为 `Rust scan_rule_candidates(plugin_config) rule_summaries/hit_details`。

## 验证结果

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_plugin_rules_uses_native_plugin_config_hit_details`：passed。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_plugin_rules_uses_native_plugin_config_context`：passed。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_plugin_rules_uses_native_plugin_config_hit_details tests/test_agent_toolkit_rule_import.py::test_import_plugin_rules_uses_native_plugin_config_context`：2 passed。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_plugin_rules_reports_json_string_leaf_candidates tests/test_agent_toolkit_rule_import.py::test_validate_plugin_rules_uses_prefix_read_for_translated_count tests/test_agent_toolkit_rule_import.py::test_validate_plugin_rules_rejects_english_protocol_value_paths tests/test_agent_toolkit_rule_import.py::test_import_empty_plugin_rules_requires_explicit_empty_confirmation tests/test_agent_toolkit_rule_import.py::test_import_plugin_rules_rejects_english_protocol_value_paths tests/test_agent_toolkit_rule_import.py::test_import_plugin_rules_uses_configured_text_rules`：6 passed。
- `uv run pytest tests/test_plugin_text.py::test_plugin_rule_import_validates_external_file tests/test_plugin_text.py::test_plugin_rule_import_rejects_paths_without_english_source_text tests/test_plugin_text.py::test_plugin_text_extracts_rule_matched_leaves tests/test_plugin_text.py::test_plugin_text_extraction_rejects_stale_rule_hash`：4 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch117_p1b_plugin_config_native_contract_tracks_current_boundary tests/test_scan_budget.py::test_batch118_p1b_plugin_config_validate_import_adapter_tracks_current_boundary`：3 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch118_p1b_plugin_config_validate_import_adapter_tracks_current_boundary`：passed。
- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_config_rule_hits tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`：2 passed。
- `uv run basedpyright`：0 errors, 0 warnings。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：73 passed。
- `git diff --check`：通过，仅输出 CRLF 换行提示。
- 文档敏感路径搜索：NO_MATCH。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

- 本批修改生产代码。
- 本批未再修改 Rust 原生代码；Rust 原生契约变更记录在 6CH。
- 本批没有修改 CLI 外部参数、数据库 schema 或发布流程。
- 文档敏感路径搜索结果为 NO_MATCH。

## 剩余风险

- 本批未跑全量 Python pytest，剩余风险是非目标 Agent 工作区流程存在间接回归；已用工作区共用 helper 的 scan_budget 静态保护和插件参数相关目标测试覆盖主要行为。
- MV 虚拟名字框命令族仍未迁移，下一批需要完整评估 `mv_virtual_namebox` 是否需要 Rust 候选契约。

## 下一批入口

- 进入 6CJ：MV 虚拟名字框 `export` / `validate` / `import` 迁移评估。
