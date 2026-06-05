# Rust Scope/Index Engine 批次 5J translate --max-items 占位符 gate 元信息复用记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 P1-A 中 `translate --max-items` warm index 前置检查里的占位符候选审查：重建 text index 时，把普通占位符和结构化占位符的 coverage 摘要写入索引元信息；warm index 命中并且源码支线 gate 已预检时，翻译前置检查直接从 metadata 生成占位符 gate errors，不再扫描完整 `translation_data_map`。

本批不迁移占位符规则导入、候选导出、工作区校验和 `quality-report` 的占位符候选报告；这些入口仍需要完整候选明细或样本，后续按 P1-B 迁移到 Rust `scan_rule_candidates`。

涉及文件：

- `app/application/flow_gate.py`
- `app/application/handler.py`
- `app/text_index.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-016.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata`
- `tests/test_scan_budget.py::test_batch16_translate_max_items_placeholder_gate_metadata_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata`：1 failed，旧实现仍调用 `scan_placeholder_candidates()` 重扫普通占位符候选。
- `uv run pytest tests/test_scan_budget.py::test_batch16_translate_max_items_placeholder_gate_metadata_record_exists_and_is_linked_from_plan`：1 failed，批次 5J 验收记录尚不存在。

## 改动范围

- `build_text_index_workflow_gate_scope_hashes()` 增加当前 `TextScopeResult` 输入：
  - 计算普通占位符 coverage 摘要。
  - 计算结构化占位符 coverage 摘要。
  - 把 scope hash、rule count、candidate count、covered count 和 uncovered count 写入 `TextIndexMetadata.workflow_gate_scope_hashes`。
- 新增 `collect_text_index_placeholder_gate_errors()`：
  - 从 text index metadata 还原普通/结构化占位符 `RuleCoverageResult` 摘要。
  - 使用现有规则审查状态生成 workflow gate errors。
  - metadata 缺失或损坏时显式要求重新运行 `rebuild-text-index`。
- `collect_indexed_workflow_gate_errors()` 新增可选 `placeholder_gate_errors` 参数；未传入时保留旧扫描行为。
- `translate --max-items` warm index 预检路径传入 metadata 生成的占位符 gate errors。

## 旧路径收束

- 本批删除当前有效 warm index 下 `translate --max-items` 前置 gate 对普通/结构化占位符候选扫描的依赖。
- 普通 `collect_workflow_gate_errors()`、`quality-report`、占位符规则导入和候选报告仍保留完整扫描，因为它们需要候选明细、样本或用户可见报告。
- 旧索引如果缺少占位符 gate metadata，不静默回退到 Python 扫描，而是显式提示重建索引。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要错误文案不变。
- `translate --max-items` 在有效 warm index 下仍保持占位符规则审查语义：未确认的未覆盖候选继续阻断，已确认候选继续允许流程推进。
- 新增 text index metadata 内部键，属于当前索引契约；旧索引需要重建后才能走 5J 快路径。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和代码路径收束：

- 行为测试在 text index 已重建后禁止 `scan_placeholder_candidates()` 和 `collect_structured_placeholder_candidate_details()`，`translate --max-items` 仍能准备 3 条小批翻译。
- 相邻 warm index 测试继续覆盖源码支线预检、跳过完整 `GameData` 加载和 Rust `evaluate_scope_gate` pending summary 消费。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata`：RED 阶段 1 failed，原因是旧实现重扫普通占位符候选；GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_prechecked_source_branch_gates tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_game_data_load_after_gate_precheck tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_rust_scope_gate_pending_summary`：4 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch16_translate_max_items_placeholder_gate_metadata_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5J 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch16_translate_max_items_placeholder_gate_metadata_record_exists_and_is_linked_from_plan`：1 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_scan_budget.py::test_batch16_translate_max_items_placeholder_gate_metadata_record_exists_and_is_linked_from_plan`：2 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：727 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。

## 剩余风险

- 本批仍在重建 text index 时用 Python 计算占位符 coverage 摘要；最终 P1-B 仍需要把大规模占位符候选扫描迁到 Rust `scan_rule_candidates`。
- metadata 只保存摘要，不保存候选样本；需要明细的命令仍会扫描完整候选。
- `translate --max-items` 前置 gate 里 `_text_scope_gate_errors()` 仍消费从全部 index rows 还原的 `TextScopeResult`，下一批应继续收束 text-scope gate。

## 下一批入口

批次 5K：建议推进 `translate --max-items` text-scope gate 继续索引化，优先把不可写条目、过期规则和 rule hit 不可写统计从 metadata/Rust summary 直接生成 gate errors。
