# Rust Scope/Index Engine 批次 119 验收记录

## 本批范围

- 批次编号：6CJ。
- 范围：P1-B MV 虚拟名字框 export/validate/import 迁移评估。
- 命令：`export-mv-virtual-namebox-candidates`、`validate-mv-virtual-namebox-rules`、`import-mv-virtual-namebox-rules`。
- 结论：三条命令需要 Rust `scan_rule_candidates(mv_virtual_namebox)` 候选契约；本批已建立 `candidate_details`、`rule_summaries`、`hit_details` 和 `errors` 的 native 输出边界。

## RED/GREEN

- RED：新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_mv_virtual_namebox_rule_hits`，旧 Rust payload 忽略 `mv_virtual_namebox_data_files` / `mv_virtual_namebox_rules`，候选摘要为空。
- RED：新增 `tests/test_scan_budget.py::test_batch119_p1b_mv_virtual_namebox_native_contract_tracks_current_boundary`，旧预算仍把三条 MV 命令留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。
- GREEN：新增 Rust `mv_virtual_namebox` 候选模块，`scan_rule_candidates(mv_virtual_namebox)` 返回候选明细、规则摘要、命中明细、错误明细和扫描计数。

## 改动范围

- `rust/src/native_core/scope_index/mv_virtual_namebox.rs`：新增 MV 事件命令分组扫描，收集 `101` 后首条非空 `401` 候选，并用 Rust fancy-regex 计算规则命中。
- `rust/src/native_core/scope_index/mod.rs`：新增 `mv_virtual_namebox_data_files`、`mv_virtual_namebox_actor_names`、`mv_virtual_namebox_rules` payload 字段，并接入 `mv_virtual_namebox::scan_mv_virtual_namebox_rule_candidates`。
- `app/native_scope_index.py`：新增 `build_native_mv_virtual_namebox_candidates_payload` 和 `mv_virtual_namebox_rule_records_to_native_rules`。
- `tests/test_native_scope_index.py`：新增 native contract 测试，固定 `candidate_details`、`rule_summaries`、`hit_details` 输出形状。
- `tests/scan_budget_contract.py`：三条 MV 命令权威来源改为 `Rust scan_rule_candidates(mv_virtual_namebox)`。

## 旧路径收束

- `RuleCandidatesPayload` 不再缺失 `mv_virtual_namebox` 输入字段。
- MV 虚拟名字框候选不再停留在待复核预算目标。
- `collect_mv_virtual_namebox_candidates` 仍保留给 MV 写回、诊断和旧 helper 边界；本批先下线三条命令族的默认候选事实来源。

## 外部契约变化

- 公开 CLI 命令、参数、退出码和 JSON 报告字段保持不变。
- Rust 原生 `scan_rule_candidates` payload 增加 `mv_virtual_namebox_data_files`、`mv_virtual_namebox_actor_names`、`mv_virtual_namebox_rules`。
- Rust 原生 `scan_summary.mv_virtual_namebox` 增加 `candidate_details`、`rule_summaries`、`hit_details`、`errors`、`candidate_count`、`matched_candidate_count`、`scanned_command_count`、`scanned_file_count`。

## 性能证据

- MV 虚拟名字框候选由一次 Rust `scan_rule_candidates(mv_virtual_namebox)` 给出。
- 规则命中摘要和命中明细来自同一 native 扫描结果，不再要求 Python 为三条命令重复遍历事件指令。
- 预算表固定三条 MV 命令 `candidate_scan_count=1`、`plugin_source_ast_scan_count=0`。

## 验证结果

- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_mv_virtual_namebox_rule_hits`：passed。
- `cargo test --manifest-path rust/Cargo.toml scan_rule_candidates_scans_mv_virtual_namebox_rule_hits`：passed。
- `uv run pytest tests/test_scan_budget.py::test_batch119_p1b_mv_virtual_namebox_native_contract_tracks_current_boundary`：passed。
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
- 本批修改 Rust 原生代码。
- 本批新增 native contract 测试、Rust 单元测试和 scan_budget 当前边界测试。
- 文档敏感路径搜索结果为 NO_MATCH。

## 剩余风险

- 本批未跑全量 Python pytest，剩余风险是非目标 MV 诊断、workflow gate 或 text index 辅助路径仍可能保留旧 helper；本批目标限定三条 MV export/validate/import 命令族。
- `collect_mv_virtual_namebox_candidates` 尚未全仓下线，后续 P1-B 总收束需要复核是否仍有必要保留。

## 下一批入口

- 进入 6CK：P1-B MV 虚拟名字框命令族 native 薄适配。
