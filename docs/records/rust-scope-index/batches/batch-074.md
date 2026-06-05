# Rust Scope/Index Engine 批次 74 验收记录

## 本批范围

本批是 6AQ：普通占位符覆盖报告 native 化。范围覆盖 `app/application/flow_gate.py::build_normal_placeholder_coverage_result`、`normal_placeholder_scope_hash` 和 `collect_placeholder_candidate_review_decisions` 共享的普通占位符覆盖结果。

本批不迁移 `build-placeholder-rules` 的规则草稿生成，也不修改 `validate-placeholder-rules`、`import-placeholder-rules` 的数据库事务、CLI 参数、配置字段、数据库 schema 或 Rust 原生代码。

## 保护网

新增 `tests/test_agent_toolkit_rule_import.py::test_normal_placeholder_coverage_result_uses_native_candidate_scan`：

- monkeypatch `app.application.flow_gate.scan_placeholder_candidates` 为报错函数。
- 直接调用 `build_normal_placeholder_coverage_result`。
- 断言覆盖结果仍能产出候选、覆盖计数和旧报告同形明细。

新增 `tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_contract_exists` 和 `tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_record_exists_and_tracks_contract`：

- 固定新增共享模块 `app/native_placeholder_scan.py`。
- 固定 `flow_gate.py::build_normal_placeholder_coverage_result` 不再调用旧 Python scanner。
- 固定 `common.py::_build_placeholder_coverage_report_with_context` 与 `flow_gate.py` 共用同一套 native 明细 helper。
- 固定 `build-placeholder-rules` 仍保留旧 Python scanner，避免本批扩大到草稿生成。

## 实现说明

新增 `app/native_placeholder_scan.py`：

- `collect_native_placeholder_candidate_details` 调用 `build_native_placeholder_candidates_payload` 与 `scan_native_rule_candidates`。
- `count_uncovered_placeholder_candidate_details` 统计 native 明细里的 `covered=false` 候选。
- `_normalize_native_placeholder_candidate_detail` 在单一模块内收窄 native JSON 字段，避免 common 和 flow gate 各自复制弱类型解析。

`app/agent_toolkit/services/common.py::_build_placeholder_coverage_report_with_context` 改为使用共享 helper。上一批 6AP 的扫描命令 native 适配仍成立，但不再保留 common 私有 native helper。

`app/application/flow_gate.py::build_normal_placeholder_coverage_result` 改为使用共享 helper 构建 `RuleCoverageResult`。因此 `normal_placeholder_scope_hash`、`collect_placeholder_candidate_review_decisions`、workflow gate 和空规则确认 hash 都复用 native 普通占位符候选明细。

## 旧路径收束

本批迁移覆盖结果事实来源，但不删除旧 `app/agent_toolkit/placeholder_scan.py::scan_placeholder_candidates`：

- `build-placeholder-rules` 仍用旧 scanner 生成规则草稿和手动边界警告。
- 旧 scanner 仍有独立行为测试保护，例如长候选必须完整覆盖、自定义规则可包住内部标准形态候选。
- 后续迁移草稿生成时必须单独建立 RED/GREEN。

6AP 记录中的 common 私有 helper 已被共享 helper 替代；当前事实来源以本批记录为准。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段或数据库 schema 变化。

`RuleCoverageResult` 的可观察字段保持不变：

- `rule_domain`
- `scope_hash`
- `rule_count`
- `candidate_count`
- `covered_count`
- `uncovered_count`
- `candidates[].marker`
- `candidates[].count`
- `candidates[].sources`
- `candidates[].standard_covered`
- `candidates[].custom_covered`
- `candidates[].covered`

## 性能证据

本批把普通占位符 workflow gate 和规则确认 hash 依赖的覆盖结果切到 Rust native 候选明细。Python 只负责明细收窄、hash 计算和 `RuleCoverageResult` 组装。

6AP 已迁移 `scan-placeholder-candidates` 报告路径，本批复用同一个 helper，避免扫描命令与 workflow gate 出现两套 native JSON 解析事实源。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_normal_placeholder_coverage_result_uses_native_candidate_scan tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，3 failed；失败点分别是 `build_normal_placeholder_coverage_result` 仍调用旧 Python scanner、计划缺少 `docs/records/rust-scope-index/batches/batch-074.md`、本批记录不存在。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_normal_placeholder_coverage_result_uses_native_candidate_scan tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，3 passed。
- 相关回归与记录保护：`uv run pytest tests/test_agent_toolkit_coverage.py::test_scan_placeholder_candidates_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_normal_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_uses_placeholder_gate_metadata tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch73_placeholder_scan_command_native_adapter_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch74_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，7 passed。
- 全量回归：`uv run pytest`，退出码 0，收集 876 项。
- 类型检查：`uv run basedpyright`，0 errors、0 warnings、0 notes。
- 文档敏感路径/占位文案搜索：无匹配。
- Diff 空白检查：`git diff --check`，退出码 0。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未使用子代理执行改动。实现边界清晰，主代理本地完成 TDD、代码调整和验证。

## 剩余风险

普通占位符支线仍有旧路径：

- `build-placeholder-rules` 仍依赖旧 Python scanner 生成草稿。
- 规则校验和导入事务本身仍有独立路径，需要后续继续确认是否复用 native coverage。
- 工作区 manifest 和 validate 中的普通占位符候选提示仍需后续审计是否已经间接复用本批 coverage builder。

## 下一批入口

建议下一批进入普通占位符 workflow gate native 化审计：确认 workflow gate、quality report、write-back 前置检查、doctor 和工作区校验是否都已经经由 `build_normal_placeholder_coverage_result` 复用 native 明细；若发现绕过路径，再单独迁移。
