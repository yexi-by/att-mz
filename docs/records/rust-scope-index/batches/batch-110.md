# Rust Scope/Index Engine 批次 6CA 验收记录

## 本批范围

本批是 P1-B 事件指令 Rust 候选入口最小契约。本批修改生产代码，本批修改 Rust 原生代码。

本批承接 `docs/records/rust-scope-index/batches/batch-109.md` 的评估结论，只建立 `scan_rule_candidates(event_commands)` 的最小 Rust/Python JSON 契约，不把三个公开事件指令命令直接切到 native 事实来源。

本批覆盖的最小能力：

- `RuleCandidatesPayload` 新增 `event_command_data_files`、`event_command_codes` 和 `event_command_rules`。
- Python 侧新增 `build_native_event_command_candidates_payload`。
- Rust 侧新增事件指令候选扫描模块，支持 `401.parameters[0]` 这类直接字符串参数候选。
- Rust 侧支持 `event_command_rules` 的 `parameter_filters` 和 `path_templates`，本批测试覆盖 `$['parameters'][1]['message']` 命中 JSON 字符串容器内部叶子。
- `scan_summary["event_commands"]` 输出 `samples_by_code`、`hit_details`、`sample_count`、`matched_command_count` 和 `scanned_command_count`，可作为后续导出样本去重、规则路径命中明细和空规则确认范围 hash 输入快照的基础。

## RED/GREEN

RED 目标测试：

- `uv run pytest tests/test_native_scope_index.py::test_build_native_event_command_candidates_payload_includes_data_codes_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_tracks_entry_shape tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_record_exists`，4 failed。

失败点符合预期：

- Python 侧缺少 `build_native_event_command_candidates_payload`。
- 旧 Rust `scan_rule_candidates` 忽略事件指令 payload，候选汇总为空。
- `RuleCandidatesPayload` 尚无事件指令输入字段。
- `docs/records/rust-scope-index/batches/batch-110.md` 尚不存在。

GREEN 代码侧目标测试：

- `uv run maturin develop --manifest-path rust/Cargo.toml`，成功重建本地 Rust 扩展。
- `uv run pytest tests/test_native_scope_index.py::test_build_native_event_command_candidates_payload_includes_data_codes_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_tracks_entry_shape tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_record_exists`，3 passed，1 failed；剩余失败点为本记录尚未创建。
- 创建本记录后，同一目标测试命令通过，4 passed。

目标测试也可拆分为以下单测命令定位：

- `uv run pytest tests/test_native_scope_index.py::test_build_native_event_command_candidates_payload_includes_data_codes_and_rules`
- `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates`
- `uv run pytest tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_tracks_entry_shape`
- `uv run pytest tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_record_exists`

## 改动范围

- `rust/src/native_core/scope_index/event_commands.rs`：新增事件指令候选扫描模块，负责从 Map、CommonEvents、Troops 和通用 JSON 结构中枚举事件指令，生成候选、样本快照和规则命中明细。
- `rust/src/native_core/scope_index/mod.rs`：把 `event_command_data_files`、`event_command_codes`、`event_command_rules` 接入 `RuleCandidatesPayload` 和 `scan_summary["event_commands"]`。
- `app/native_scope_index.py`：新增 `build_native_event_command_candidates_payload`，按文件名和 command code 排序构造 native payload。
- `app/native_contract.py` 与 `rust/src/lib.rs`：把 `NATIVE_CONTRACT_VERSION = 8` 作为当前 Rust/Python JSON 契约版本，避免旧 native 扩展静默忽略新增字段。
- `tests/test_native_scope_index.py`：新增 Python payload builder 测试和 native 事件指令候选行为测试。
- `tests/test_scan_budget.py`：调整 6BZ 历史边界测试，新增 6CA 契约形状和验收记录保护。
- `docs/plans/completed/rust-scope-index-engine.md`：新增 6CA 进度行。
- `docs/records/rust-scope-index/batches/batch-110.md`：新增本验收记录。

## 旧路径收束

本批不删除旧路径，也不切换公开 CLI 生产事实来源。

仍保留为生产路径的旧入口：

- `app/event_command_text/exporter.py::export_event_commands_json_file`
- `app/event_command_text/extraction.py::EventCommandTextExtraction`
- `app/event_command_text/importer.py::build_event_command_rule_records_from_import`
- `app/text_scope/rule_hits.py::collect_event_command_rule_hits`

本批只为下一步薄适配提供 native 候选入口；`export-event-commands-json`、`validate-event-command-rules` 和 `import-event-command-rules` 仍应继续保留在待复核 P1-B 队列中，直到对应生产链路实际接入并通过保护测试。

## 外部契约变化

无公开 CLI 参数、Agent JSON 报告、SQLite schema、日志格式、目录结构、README、Skill 或发布流程变化。

内部 Rust/Python native JSON 契约发生变化：

- 输入新增 `event_command_data_files`、`event_command_codes`、`event_command_rules`。
- 输出新增 `scan_summary["event_commands"]`，包含 `samples_by_code`、`hit_details`、`sample_count`、`matched_command_count`、`scanned_command_count` 和 `command_codes`。
- 当前原生契约版本升为 `NATIVE_CONTRACT_VERSION = 8`。旧 `app._native` 必须重新执行 `uv run maturin develop --manifest-path rust/Cargo.toml` 或使用同版本发行构建。

## 性能证据

本批将事件指令候选枚举放到 Rust 原生模块中执行，Python 只负责 payload 组装和结果解析。

扫描行为边界：

- 每个输入 data 文件在 native 入口内枚举一次事件指令。
- `samples_by_code` 使用稳定 JSON 文本和 `BTreeSet` 去重，相同 command code 下相同参数样本只保留一份；候选命中仍按真实 `location_path` 保留。
- `event_command_codes` 与 `event_command_rules.command_code` 取并集后过滤命令，避免无关事件指令参与候选生成。
- JSON 字符串容器递归解析在 Rust 内完成，规则路径命中不需要 Python 再展开一次。

本批尚未接入公开命令薄适配，因此没有声明公开命令吞吐量改善。

## 验证结果

- RED 目标测试：`uv run pytest tests/test_native_scope_index.py::test_build_native_event_command_candidates_payload_includes_data_codes_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_tracks_entry_shape tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_record_exists`，4 failed，失败点符合预期。
- 本地扩展重建：`uv run maturin develop --manifest-path rust/Cargo.toml`，成功。
- GREEN 目标测试：`uv run pytest tests/test_native_scope_index.py::test_build_native_event_command_candidates_payload_includes_data_codes_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_event_command_candidates tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_tracks_entry_shape tests/test_scan_budget.py::test_batch110_p1b_event_command_candidate_rust_contract_record_exists`，4 passed。
- Rust 目标测试：`cargo test --manifest-path rust/Cargo.toml native_core::scope_index::tests::scan_rule_candidates_scans_event_command_candidates`，1 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "batch110 or batch109 or batch104_note_tag_extraction_native_source_contract"`，5 passed，171 deselected。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`，72 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量测试：第一次 `uv run pytest` 为 979 passed、1 failed，失败点是 6BY 历史保护仍禁止 `event_commands` payload 字段；修正该保护后，第二次 `uv run pytest` 为 980 passed。
- 文档敏感路径和占位文案搜索：覆盖 `docs/records/rust-scope-index/batches/batch-110.md`、计划索引、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。

## 审查处理

本批未使用子代理。主代理完成事件指令候选入口审计、RED/GREEN 测试、Rust/Python 实现、契约版本处理、计划索引和验收记录。

审查重点：

- 新增 native payload 不能被旧 `app._native` 静默忽略，因此同步提升 `NATIVE_CONTRACT_VERSION = 8`。
- 本批不应把 Rust `build_scope_index` 的 `event_command.default` 正文扫描能力等同于 `scan_rule_candidates(event_commands)` 的规则候选入口。
- 本批不切公开 CLI 生产路径，避免尚未验证的候选入口影响事件指令导出、校验和导入行为。

## 剩余风险

本批已按生产代码和 Rust 原生代码变更要求执行全量 `uv run pytest`，最终 980 passed。

事件指令公开命令尚未切换到 native 候选事实来源；下一批仍需评估或实现 `export-event-commands-json`、`validate-event-command-rules` 和 `import-event-command-rules` 的薄适配。

本批最小契约覆盖 Map、CommonEvents、Troops 的当前路径协议，并保留通用 JSON fallback；后续薄适配需要继续用命令级测试确认 `location_path` 与实际写回路径完全一致。

插件参数、MV 虚拟名字框和源文残留仍属于 6BY 标出的待复核 P1-B 尾部类别，本批未处理。

## 下一批入口

建议下一批进入 P1-B 事件指令候选薄适配接入评估：先审计三个公开命令是否可以复用 `build_native_event_command_candidates_payload` 和 `scan_summary["event_commands"]`，再决定先接 `export-event-commands-json` 的样本导出，还是先接规则校验/导入的路径命中明细。
