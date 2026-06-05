# Rust Scope/Index Engine 批次 6CE 验收记录

## 本批范围

本批是 P1-B validate-event-command-rules native hit details 最小契约补强。本批修改生产代码，本批修改 Rust 原生代码。

批次名称：P1-B validate-event-command-rules native hit details 最小契约补强。

本批承接 `docs/records/rust-scope-index/batches/batch-113.md` 的评估结论：现有 `hit_details` 已能表达规则路径命中，但还缺少 `validate-event-command-rules` 后续薄适配所需的规则级 command 命中、命中前缀和 path 计数。本批只补 native 契约，不切换 `validate-event-command-rules` 生产链路。

本批补强内容：

- `hit_details` 新增 `command_location_path`，用于后续从叶子命中定位到事件指令前缀。
- `scan_summary["event_commands"]` 新增 `rule_summaries`，由 Rust `EventCommandRuleSummaryOutput` 输出。
- `rule_summaries` 每条记录包含 `rule_index`、`command_code`、`matched_command_count`、`matched_command_location_paths` 和 `path_hit_counts`。
- `path_hit_counts` 由 Rust `EventCommandPathHitCountOutput` 输出。
- native contract version 从 8 提升到 9。

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`，1 failed。失败点是 `hit_details` 缺少 `command_location_path`，并且尚无 `rule_summaries`。
- `uv run pytest tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_tracks_rule_summary_shape tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_record_exists`，1 passed，1 failed。失败点是本记录尚不存在。

GREEN 目标测试：

- `uv run maturin develop --manifest-path rust/Cargo.toml`，重建当前 uv 环境中的 `app._native`。
- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`，1 passed。
- `cargo test --manifest-path rust/Cargo.toml scan_rule_candidates_scans_event_command_candidates`，1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_tracks_rule_summary_shape tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_record_exists`，记录保护覆盖本批计划索引、native contract version 和规则摘要契约。

目标测试可拆分为以下单测命令定位：

- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`
- `cargo test --manifest-path rust/Cargo.toml scan_rule_candidates_scans_event_command_candidates`
- `uv run pytest tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_tracks_rule_summary_shape`
- `uv run pytest tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_record_exists`

## 改动范围

生产代码：

- `app/native_contract.py`
- `rust/src/lib.rs`
- `rust/src/native_core/scope_index/event_commands.rs`
- `rust/src/native_core/scope_index/mod.rs`

测试与契约：

- `tests/test_native_scope_index.py`
- `tests/test_scan_budget.py`

文档：

- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-114.md`

## 旧路径收束

本批不删除旧 Python 校验路径，也不切换 `validate-event-command-rules` 生产事实来源。

`validate-event-command-rules` 和 `import-event-command-rules` 仍保留在 `P1_B_PENDING_FACT_SOURCE_COMMANDS` 中。下一批需要用这些新 native 字段构建薄适配，才能考虑把 `validate-event-command-rules` 从待复核预算目标中移出。

## 外部契约变化

native JSON 契约版本提升到 `NATIVE_CONTRACT_VERSION = 9`，Rust `native_contract_version()` 同步返回 9。

新增的 Rust `scan_rule_candidates(event_commands)` 输出字段：

- `hit_details[].command_location_path`
- `scan_summary["event_commands"].rule_summaries`
- `rule_summaries[].matched_command_count`
- `rule_summaries[].matched_command_location_paths`
- `rule_summaries[].path_hit_counts`

无公开 CLI 参数、Agent JSON 报告、SQLite schema、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有增加额外扫描入口。`rule_summaries` 在原有一次 `scan_rule_candidates(event_commands)` 遍历中同步累计：

- command 命中时记录 `matched_command_count` 和 `matched_command_location_paths`。
- 每个 path template 展开后记录 `path_hit_counts`。
- `hit_details` 仍在同一次规则路径命中过程中生成。

因此预算仍是 `candidate_scan_count = 1`、`plugin_source_ast_scan_count = 0`；本批只是让一次 native 扫描返回后续 validate 薄适配所需的更多事实。

## 验证结果

- RED 目标测试：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`，1 failed，失败点为 native 输出缺少 `command_location_path` 和 `rule_summaries`。
- RED 记录保护：`uv run pytest tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_tracks_rule_summary_shape tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_record_exists`，1 passed，1 failed，失败点为本记录尚不存在。
- native 重建：`uv run maturin develop --manifest-path rust/Cargo.toml`，成功安装当前 `app._native`。
- GREEN native 目标测试：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`，1 passed。
- GREEN Rust 目标测试：`cargo test --manifest-path rust/Cargo.toml scan_rule_candidates_scans_event_command_candidates`，1 passed。
- GREEN scan_budget 目标测试：`uv run pytest tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_tracks_rule_summary_shape tests/test_scan_budget.py::test_batch114_p1b_validate_event_command_rules_native_hit_details_contract_record_exists`，2 passed。
- 相关 scan_budget 保护：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates tests/test_scan_budget.py -k "batch114 or batch113 or batch112 or batch110 or batch104"`，10 passed，175 deselected；该组合命令因 `-k` 只选择了 scan_budget 测试，native 目标测试已用单独命令覆盖。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，退出码 0。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，退出码 0。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`，72 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`，989 passed。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-114.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。

## 审查处理

本批未使用子代理。主代理完成 native 契约设计、RED/GREEN、Rust/Python 契约同步、计划索引和验收记录。

本批审查结论是：`validate-event-command-rules` 后续薄适配已经具备 native 最小事实入口；下一批仍需在 Python 侧构造适配层，复用 `rule_summaries`、`hit_details` 和写回协议预演，并用行为测试证明报告统计不回退。

## 剩余风险

本批修改 Rust 原生代码和 native contract version，因此按临时验证策略需要执行全量 `uv run pytest`，不能使用普通批次例外跳过。

剩余风险集中在下一批：`rule_summaries` 已提供 command/path 级事实，但 `validate-event-command-rules` 生产链路仍未消费它；Python 旧遍历仍会在规则校验和导入链路出现。

## 下一批入口

下一批入口：P1-B validate-event-command-rules native hit details 薄适配。

建议下一批在 Python 侧新增 validate 专用 native adapter：从 `build_native_event_command_candidates_payload` 和 `scan_native_rule_candidates` 读取 `rule_summaries` 与 `hit_details`，保留 `TextRules.should_translate_source_text` 和写回协议预演，先替换 `EventCommandTextExtraction.extract_all_text_with_rule_items` 在校验报告中的命中统计路径。
