# Rust Scope/Index Engine 批次 6BO 验收记录

## 本批范围

本批是 Note 标签 scope hash/count native 薄适配，修改生产 Python 代码，让 `count_note_tag_rule_candidates` 与 `note_tag_rule_scope_hash_for_text_rules` 消费 `collect_native_note_tag_candidate_details`。

本批未修改 Rust 原生代码；继续复用既有 Rust `scan_rule_candidates(note_tags)` 候选摘要。

本批承接 `docs/records/rust-scope-index/batches/batch-097.md`，只迁移适合消费候选摘要的入口：

- `count_note_tag_rule_candidates`
- `note_tag_rule_scope_hash_for_text_rules`

本批不迁移需要逐命中明细的入口：

- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`

## 保护网

新增 `tests/test_agent_toolkit_rule_import.py::test_note_tag_scope_hash_and_count_use_native_candidate_scan`，固定以下行为：

- `count_note_tag_rule_candidates` 不再调用 Python `collect_note_tag_candidates`。
- `note_tag_rule_scope_hash_for_text_rules` 不再调用 Python `collect_note_tag_candidates`。
- 两个入口都通过 `collect_native_note_tag_candidate_details` 消费 native 候选摘要。
- `count_note_tag_rule_candidates` 继续累加 `translatable_hit_count`。
- `note_tag_rule_scope_hash_for_text_rules` 继续把候选摘要交给 `note_tag_rule_scope_hash_for_candidates`，保持空规则确认 hash 的事实来源形状。

新增 `tests/test_agent_toolkit_rule_import.py::test_native_note_tag_candidates_match_python_scope_hash_input`，固定真实最小游戏数据上 native 候选摘要与旧 Python 候选摘要等价，避免 scope hash 输入漂移。

新增 `tests/test_scan_budget.py::test_batch98_note_tag_scope_hash_count_native_adapter_contract_exists`，固定 `app/application/flow_gate.py` 的调用关系和导入边界。

新增 `tests/test_scan_budget.py::test_batch98_note_tag_scope_hash_count_native_adapter_record_exists_and_tracks_contract`，固定本记录、计划表链接、验证命令、临时验证例外和下一批入口。

## 实现说明

`app/application/flow_gate.py` 现在提供延迟导入包装入口 `collect_native_note_tag_candidate_details`，并在以下入口使用：

- `count_note_tag_rule_candidates`
- `note_tag_rule_scope_hash_for_text_rules`

旧 `collect_note_tag_candidates` 仍保留在 `app/note_tag_text/exporter.py`，用于历史等价测试、旧边界记录和后续 text-scope/逐命中迁移评估；但本批迁移后的 scope hash/count 不再调用它。

`note_tag_rule_scope_hash_for_candidates` 没有变化，hash 输入仍是候选摘要列表。真实数据等价测试覆盖 `collect_native_note_tag_candidate_details` 与 `collect_note_tag_candidates` 的摘要输出一致性。

## 旧路径收束

本批已收束以下旧 Python 候选扫描入口：

- `count_note_tag_rule_candidates`
- `note_tag_rule_scope_hash_for_text_rules`

本批仍保留以下旧 Python 扫描边界：

- `collect_note_tag_candidates`
- `collect_note_tag_rule_hits`
- `NoteTagTextExtraction`
- `collect_note_tag_sources`
- `iter_note_tag_matches`

这些剩余路径不是本批删除对象。下一批涉及 text-scope 时，必须先补专门断言 `TextScopeRuleHit` 输出内容的行为测试。

## 外部契约变化

无 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema、Rust API 或发布流程变化。

用户可见行为保持不变；变化只在空 Note 标签规则确认 hash/count 的内部候选扫描事实来源。

## 性能证据

本批把 `count_note_tag_rule_candidates` 与 `note_tag_rule_scope_hash_for_text_rules` 从 Python `collect_note_tag_candidates` 切到 native `collect_native_note_tag_candidate_details`。

相关性能保护：

- 行为测试禁止两个入口调用 Python `collect_note_tag_candidates`。
- scan_budget/记录保护要求 `app/application/flow_gate.py` 通过延迟导入包装入口调用 `collect_native_note_tag_candidate_details`，且两个入口不再调用 `collect_note_tag_candidates`。
- 等价测试固定 native 候选摘要与旧 Python 候选摘要同形，避免为了性能牺牲空规则确认 hash 语义。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_note_tag_scope_hash_and_count_use_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_native_note_tag_candidates_match_python_scope_hash_input`，1 failed，1 passed。失败点是 `count_note_tag_rule_candidates` 仍调用 Python `collect_note_tag_candidates`。
- RED：`uv run pytest tests/test_scan_budget.py::test_batch98_note_tag_scope_hash_count_native_adapter_contract_exists tests/test_scan_budget.py::test_batch98_note_tag_scope_hash_count_native_adapter_record_exists_and_tracks_contract`，2 failed。失败点分别是计划缺少 `docs/records/rust-scope-index/batches/batch-098.md`、本批记录不存在。
- GREEN 目标行为测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_note_tag_scope_hash_and_count_use_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_native_note_tag_candidates_match_python_scope_hash_input`，2 passed。
- GREEN 目标记录保护：`uv run pytest tests/test_scan_budget.py::test_batch98_note_tag_scope_hash_count_native_adapter_contract_exists tests/test_scan_budget.py::test_batch98_note_tag_scope_hash_count_native_adapter_record_exists_and_tracks_contract`，2 passed。
- 相关 Note 标签行为回归：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates tests/test_agent_toolkit_rule_import.py::test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup tests/test_agent_toolkit_rule_import.py::test_import_note_tag_rules_replaces_stale_existing_rule tests/test_agent_toolkit_workflow_gate.py::test_workflow_gate_blocks_external_rule_hits_outside_writable_scope`，4 passed。
- 相关 scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py -k "note_tag"`，18 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果为 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，退出码 0；命令只输出工作区既有 CRLF 转换提示。
- 本批修改生产 Python 代码。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标行为测试、目标记录保护、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批改动范围很窄，没有再派发子代理写代码。6BN 的只读子代理审计已经指出：`note_tag_rule_scope_hash_for_text_rules` 与 `count_note_tag_rule_candidates` 只依赖候选摘要，适合作为本批薄适配对象；`collect_note_tag_rule_hits` 与 `NoteTagTextExtraction` 需要逐命中明细，继续留到后续批次。

本地判断是：本批只改变 scope hash/count 的内部事实来源，不改变规则审查状态、空规则确认、旧译文清理或 text-scope 构建语义。

## 剩余风险

本批没有建立 text-scope 逐命中 native 明细契约，也没有删除旧 `collect_note_tag_candidates`。后续迁移 `collect_note_tag_rule_hits` 前，必须先补专门行为测试，固定 `location_path`、`original_text`、去重和可见文本规范化。

本批未跑全量 `uv run pytest`，全仓其它非 Note 标签测试没有在本批重复验证。

## 下一批入口

建议下一批进入 Note 标签 text-scope 逐命中 native 明细评估：先补 `collect_note_tag_rule_hits` 输出内容测试，再判断 Rust 是否需要输出完整逐命中 `location_path` 与 `original_text`，而不是复用当前最多 5 个样例的候选摘要。
