# Rust Scope/Index Engine 批次 6BB 验收记录

## 本批范围

本批是结构化占位符覆盖报告 native 化。范围覆盖 `app/application/flow_gate.py::build_structured_placeholder_coverage_result`、`structured_placeholder_scope_hash` 和 `count_uncovered_structured_placeholder_candidates` 依赖的结构化候选明细。

本批触及以下文件：

- `app/application/flow_gate.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`

本批不删除 flow_gate 中旧 `collect_structured_placeholder_candidate_details` 导出，不迁移 workspace manifest 和 workspace validate 的额外结构化规则校验，不修改 CLI 参数、数据库 schema、配置字段或 Rust 原生代码。

## 保护网

新增 `tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan`：

- monkeypatch `app.application.flow_gate._iter_structured_shell_candidate_matches` 为报错函数。
- 直接调用 `build_structured_placeholder_coverage_result`。
- 断言覆盖结果仍产出候选数量、覆盖数量、完整候选 hash 和旧报告同形明细。

新增 `tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists`：

- 固定计划表链接本批记录。
- 固定 `build_structured_placeholder_coverage_result` 使用 `collect_native_structured_placeholder_candidate_details` 与 `count_uncovered_structured_placeholder_candidate_details`。
- 固定 `count_uncovered_structured_placeholder_candidates` 使用同一 native 明细 helper。
- 固定旧 `collect_structured_placeholder_candidate_details` 仍作为导出存在，避免本批扩大到删除旧入口。

新增 `tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_record_exists_and_tracks_contract
```

结果：3 failed。失败点分别是 `build_structured_placeholder_coverage_result` 仍调用 Python 结构化候选扫描器、计划表缺少 `docs/records/rust-scope-index/batches/batch-085.md`，以及本批记录不存在。

## 实现说明

`app/application/flow_gate.py` 现在复用 `app/native_structured_placeholder_scan.py`：

- `build_structured_placeholder_coverage_result` 使用 `collect_native_structured_placeholder_candidate_details` 获取旧报告同形候选明细。
- `count_uncovered_structured_placeholder_candidates` 使用 `count_uncovered_structured_placeholder_candidate_details` 统计未覆盖候选。
- `structured_placeholder_scope_hash` 继续通过 `build_structured_placeholder_coverage_result` 计算完整候选 hash。

由于 flow_gate 的结构化 coverage builder 只有 `structured_rules` 参数，本批新增 `_structured_placeholder_candidate_text_rules` 构造结构化候选扫描所需的最小 `TextRules` 上下文。该上下文只承载结构化规则，保持与旧 Python 覆盖扫描相同的输入边界。

## 旧路径收束

本批迁移结构化覆盖报告事实来源，但保留旧 Python helper：

- `app/application/flow_gate.py::collect_structured_placeholder_candidate_details`
- `app/application/flow_gate.py::_iter_structured_shell_candidate_matches`
- `app/agent_toolkit/services/common.py::_collect_structured_placeholder_candidate_details`

旧 helper 仍用于后续删除/隔离评估和兼容边界审计。本批不做删除，避免同时改变 workspace、旧导出和测试夹具语义。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema 或 Rust 原生代码变化。

`RuleCoverageResult` 的可观察字段保持：

- `rule_domain`
- `scope_hash`
- `rule_count`
- `candidate_count`
- `covered_count`
- `uncovered_count`
- `candidates[].location_path`
- `candidates[].line_number`
- `candidates[].candidate`
- `candidates[].covered`
- `candidates[].matching_rules`

## 性能证据

本批把 `build_structured_placeholder_coverage_result` 和 `structured_placeholder_scope_hash` 依赖的结构化候选明细切到 Rust `scan_rule_candidates(structured_placeholders)`。因此 `import-structured-placeholder-rules` 的导入确认 hash、workflow gate 和 workspace 中复用该 coverage builder 的路径不再通过 flow_gate 旧 Python shell 候选扫描器。

Python 仍负责 native JSON 明细收窄、hash 计算和 `RuleCoverageResult` 组装。旧 Python helper 本批保留，但不再是 coverage builder 的事实来源。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，3 failed。
- GREEN 目标测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，3 passed。
- 相关结构化回归：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_import_empty_structured_placeholder_rules_confirms_uncovered_candidates tests/test_agent_toolkit_rule_import.py::test_import_empty_structured_placeholder_rules_uses_full_candidate_hash tests/test_agent_toolkit_rule_import.py::test_import_nonempty_structured_placeholder_rules_confirms_remaining_uncovered_candidates tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_candidate_review_rejects_legacy_sampled_hash tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_reuses_structured_placeholder_context tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，8 passed。
- 历史审计保护修正：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_agent_toolkit_rule_import.py::test_structured_placeholder_coverage_result_uses_native_candidate_scan tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_contract_exists tests/test_scan_budget.py::test_batch85_structured_placeholder_coverage_builder_native_record_exists_and_tracks_contract`，4 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`，905 passed。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批修改生产 Python 代码，因此已按临时策略执行全量 `uv run pytest`。
- 本批未修改 Rust 原生代码。

## 审查处理

本批未使用子代理执行改动。边界来自 batch 84 下一批入口和普通占位符 batch 74 的既有迁移模式：coverage builder 与 scope hash 复用 native 明细，旧 helper 删除留到单独审计批次。

## 剩余风险

flow_gate 和 common 中的旧结构化候选 helper 仍保留。它们已经不再服务本批迁移的 coverage builder，但是否可以删除、私有化或仅保留为测试夹具，需要下一批审计。

workspace 中 `validate-agent-workspace` 仍有结构化规则校验与 coverage 展示路径；虽然 coverage builder 已 native 化，workspace 支线还需要单独确认是否存在绕过路径或重复扫描。

## 下一批入口

建议下一批进入结构化占位符 workflow gate native 化审计：确认 workflow gate、doctor、workspace validate 和 import 后风险确认是否都经由 native coverage builder，并列出旧结构化候选 helper 的删除或隔离边界。
