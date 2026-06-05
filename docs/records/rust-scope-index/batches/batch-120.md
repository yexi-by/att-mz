# Rust Scope/Index Engine 批次 120 验收记录

## 本批范围

- 批次编号：6CK。
- 范围：P1-B MV 虚拟名字框命令族 native 薄适配。
- 命令：`export-mv-virtual-namebox-candidates`、`validate-mv-virtual-namebox-rules`、`import-mv-virtual-namebox-rules`。
- 目标：三条命令消费 6CJ 建立的 `scan_rule_candidates(mv_virtual_namebox)` 事实，不再调用旧 Python 候选扫描作为默认生产路径。

## RED/GREEN

- RED：新增 `tests/test_agent_toolkit_rule_import.py::test_mv_virtual_namebox_rule_commands_use_native_candidate_context`，旧 export 调用 `mv_virtual_namebox_candidates_payload` 时触发禁止旧候选扫描断言。
- RED：新增 `tests/test_scan_budget.py::test_batch120_p1b_mv_virtual_namebox_adapter_tracks_current_boundary`，旧服务层仍引用 `validate_mv_virtual_namebox_rules_against_game` 或 `mv_virtual_namebox_candidate_details` 时失败。
- GREEN：`export-mv-virtual-namebox-candidates` 改为写出 `native_mv_virtual_namebox_candidates_payload`。
- GREEN：`validate-mv-virtual-namebox-rules` 改为使用 `scan_native_mv_virtual_namebox` 的 rule errors、hit details 和 candidate details；旧规则新增命中对比只复用已加载 native 候选。
- GREEN：`import-mv-virtual-namebox-rules` 改为使用 native 命中明细做导入前覆盖检查和空规则 scope hash。

## 改动范围

- `app/rmmz/mv_namebox.py`：新增 `validate_mv_virtual_namebox_rules_against_candidates`，允许复用已收集候选校验旧规则，不触发候选扫描。
- `app/rmmz/mv_namebox_native.py`：新增 native 扫描适配、候选导出 payload 和 native 候选转旧 helper 候选对象。
- `app/agent_toolkit/services/rule_validation.py`：MV export/import 入口改为消费 native payload 和 native scan。
- `app/agent_toolkit/services/common.py`：`_validate_mv_virtual_namebox_rules_with_context` 改为 native scan，并复用 native candidate details 做新旧规则命中差异。
- `tests/test_agent_toolkit_rule_import.py`：新增旧路径防回退测试。
- `tests/test_scan_budget.py`：新增 6CK 静态边界和记录保护测试。

## 旧路径收束

- `export-mv-virtual-namebox-candidates` 不再调用 `mv_virtual_namebox_candidates_payload`。
- `validate-mv-virtual-namebox-rules` 不再调用 `validate_mv_virtual_namebox_rules_against_game`。
- `import-mv-virtual-namebox-rules` 不再调用 `validate_mv_virtual_namebox_rules_against_game` 或 `mv_virtual_namebox_candidate_details`。
- `collect_mv_virtual_namebox_candidates` 和 `validate_mv_virtual_namebox_rules_against_game` 仍作为非本批路径和兼容 helper 保留；命令族默认事实来源已迁到 native。

## 外部契约变化

- CLI 参数、退出码、JSON 字段和用户可见错误语义保持不变。
- `matched_candidates`、`newly_matched_candidates`、`candidate_count`、空规则确认和 MZ 禁用行为保持原契约。
- 新增内部 native 适配函数 `native_mv_virtual_namebox_candidates_payload`、`scan_native_mv_virtual_namebox`、`validate_mv_virtual_namebox_rules_against_candidates`。

## 性能证据

- export 只执行一次 `scan_rule_candidates(mv_virtual_namebox)`。
- validate/import 的候选和规则命中来自 native；validate 对旧规则的新增命中对比复用 native candidate details，不重新遍历游戏事件指令。
- 已执行旧路径防回退测试，禁止三条命令回到旧 Python 候选扫描和旧 Python 规则命中扫描。

## 验证结果

- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_mv_virtual_namebox_rule_commands_use_native_candidate_context`：passed。
- `uv run pytest tests/test_agent_toolkit_rule_import.py::test_mv_virtual_namebox_rule_commands_validate_import_and_reject_mz tests/test_agent_toolkit_rule_import.py::test_mv_virtual_namebox_rule_commands_use_native_candidate_context tests/test_agent_toolkit_rule_import.py::test_mv_namebox_rule_validation_skips_plugin_source_file_loading tests/test_agent_toolkit_quality_report.py::test_mv_virtual_namebox_validation_reports_overwide_angle_rule_hits tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_mv_event_command_default`：5 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch120_p1b_mv_virtual_namebox_adapter_tracks_current_boundary`：passed。
- `uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch119_p1b_mv_virtual_namebox_native_contract_tracks_current_boundary tests/test_scan_budget.py::test_batch120_p1b_mv_virtual_namebox_adapter_tracks_current_boundary`：3 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch119_p1b_mv_virtual_namebox_native_contract_tracks_current_boundary tests/test_scan_budget.py::test_batch119_p1b_mv_virtual_namebox_native_contract_record_exists tests/test_scan_budget.py::test_batch120_p1b_mv_virtual_namebox_adapter_tracks_current_boundary tests/test_scan_budget.py::test_batch120_p1b_mv_virtual_namebox_adapter_record_exists`：5 passed。
- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_mv_virtual_namebox_rule_hits tests/test_agent_toolkit_rule_import.py::test_mv_virtual_namebox_rule_commands_validate_import_and_reject_mz tests/test_agent_toolkit_rule_import.py::test_mv_virtual_namebox_rule_commands_use_native_candidate_context tests/test_agent_toolkit_rule_import.py::test_mv_namebox_rule_validation_skips_plugin_source_file_loading tests/test_agent_toolkit_quality_report.py::test_mv_virtual_namebox_validation_reports_overwide_angle_rule_hits tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_uses_mv_event_command_default tests/test_scan_budget.py::test_batch108_p1b_budget_fact_source_review_marks_unmigrated_budget_targets tests/test_scan_budget.py::test_batch119_p1b_mv_virtual_namebox_native_contract_tracks_current_boundary tests/test_scan_budget.py::test_batch120_p1b_mv_virtual_namebox_adapter_tracks_current_boundary`：9 passed。
- `uv run basedpyright`：0 errors, 0 warnings。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：74 passed。
- `git diff --check`：通过。
- 文档敏感路径搜索：NO_MATCH。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

- 本批修改生产代码。
- 本批修改 Rust 原生代码，原因是 6CJ/6CK 在同一轮完成。
- 本批没有修改 CLI 外部参数、数据库 schema 或发布流程。
- 文档敏感路径搜索结果为 NO_MATCH。

## 剩余风险

- 本批未跑全量 Python pytest，剩余风险是非目标辅助路径仍可能间接使用旧 MV helper；已用目标命令、工作区、质量报告和 scan_budget 保护降低主要风险。
- 源文残留 validate/import 仍在 `P1_B_PENDING_FACT_SOURCE_COMMANDS`，下一批需要继续迁移评估。

## 下一批入口

- 进入 6CL：源文残留 `validate` / `import` 迁移评估与契约补强。
