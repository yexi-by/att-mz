# Rust Scope/Index Engine 批次 6BJ 验收记录

## 本批范围

本批是 Note 标签规则校验 native 候选接入。范围只覆盖 `validate-note-tag-rules` 的规则文件前置命中检查，让它复用 `collect_native_note_tag_candidate_details` 与 Rust `scan_rule_candidates(note_tags)`。

本批触及以下文件：

- `app/native_note_tag_scan.py`
- `app/agent_toolkit/services/rule_validation.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_scan_budget.py`

本批不迁移 `import-note-tag-rules`、`app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context`、`app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules`、workspace manifest 校验、text-scope rule hit、数据库导入事务、空规则确认 hash 或写回协议路径。

## 保护网

新增 `tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan`：

- monkeypatch `app.agent_toolkit.services.rule_validation.build_note_tag_rule_records_from_import` 为报错函数。
- 调用公开服务方法 `validate_note_tag_rules`。
- 断言报告仍返回 `ok`。
- 断言 `file_count`、`tag_count`、`hit_count` 和 `details.rules` 保持旧报告语义。

新增 `tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_keeps_precise_map_file_scope`：

- 构造 `Map001.json` 精确地图规则和 `Map002.json` 同标签可翻译命中。
- 断言 `Map001.json` 精确规则不会被 native `Map*.json` 聚合候选误放行。
- 固定错误仍指向 `Map001.json/namePop` 没有命中玩家可见可翻译文本。

新增 `tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_contract_exists`：

- 固定计划表链接本批记录。
- 固定 `app/native_note_tag_scan.py` 导出 `build_note_tag_rule_records_from_native_candidates`。
- 固定 native helper 使用 `collect_native_note_tag_candidate_details`、`value_hit_count` 和 `translatable_hit_count` 完成前置命中检查。
- 固定 native helper 对精确地图规则保留 `collect_note_tag_sources` 精确来源校验，避免 `Map*.json` 聚合候选覆盖单图规则。
- 固定 `validate_note_tag_rules` 调用 `build_note_tag_rule_records_from_native_candidates`，不再直接调用 `build_note_tag_rule_records_from_import`。
- 固定 `import_note_tag_rules` 和 common workspace helper 仍保留 `build_note_tag_rule_records_from_import`，避免本批扩大到导入和 workspace。

新增 `tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_contract_exists tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_record_exists_and_tracks_contract
```

结果：3 failed。失败点分别是 `validate-note-tag-rules` 仍调用旧 Python `build_note_tag_rule_records_from_import`，计划表缺少 `docs/records/rust-scope-index/batches/batch-093.md`，以及本批记录不存在。

## 实现说明

`app/native_note_tag_scan.py` 新增 `build_note_tag_rule_records_from_native_candidates`：

- 调用 `collect_native_note_tag_candidate_details` 获取 native Note 标签候选摘要。
- 继续复用 `normalize_tag_names`，因此空标签、重复标签、包含 `/` 的标签和机器协议标签仍按旧规则拒绝。
- 继续通过 `matched_note_file_names` 校验规则文件模式是否指向当前 data JSON 文件。
- 对每个规则标签，用 native 候选的 `value_hit_count` 判断是否命中带值 Note 标签，用 `translatable_hit_count` 判断是否命中玩家可见可翻译文本。
- 对 `Map001.json`、`Map00?.json` 这类精确或子集地图规则，保留精确来源校验；因为 Rust 候选摘要当前按 `Map*.json` 聚合地图文件，不能用聚合命中替代单图规则事实。
- 构造旧路径同形的 `NoteTagTextRuleRecord`，交给后续报告与写回预览流程。

`app/agent_toolkit/services/rule_validation.py::validate_note_tag_rules` 改为调用 `build_note_tag_rule_records_from_native_candidates`。后续 `_validate_note_tag_rule_records_with_context` 仍用 `NoteTagTextExtraction` 生成实际命中项、已保存译文统计、可写性和写回预览。

## 旧路径收束

本批迁移的是 `validate-note-tag-rules` 的规则文件前置命中检查。旧 `build_note_tag_rule_records_from_import` 仍保留：

- `import-note-tag-rules` 继续用它进入导入事务、旧译文清理和空规则确认。
- `app/agent_toolkit/services/common.py::_validate_note_tag_rules_with_context` 继续用它服务 workspace 已加载上下文校验。
- `NoteTagTextExtraction` 继续负责 validate 报告的实际命中项、重复标签检查、可写预览和写回协议边界。
- `flow_gate`、workspace manifest、text-scope rule hit 和写回路径不在本批迁移。

下一批迁移导入前覆盖检查时，需要单独建立 RED/GREEN，不能把本批结论外推到导入事务或空规则确认 hash。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema 或 Rust 原生代码变化。

`validate-note-tag-rules` 的可观察报告字段保持：

- `summary.file_count`
- `summary.tag_count`
- `summary.hit_count`
- `summary.extractable_count`
- `summary.translated_count`
- `summary.writable_count`
- `summary.unwritable_count`
- `details.rules[].file_name`
- `details.rules[].tag_count`
- `details.rules[].tag_names`

## 性能证据

本批把 `validate-note-tag-rules` 的规则文件前置命中检查从 Python `build_note_tag_rule_records_from_import` 切到 native Note 标签候选摘要。该路径不再在规则构建阶段重复调用 Python `collect_note_tag_sources` + `iter_note_tag_matches` 做每条标签的命中检查。

服务级保护测试通过 monkeypatch 旧 Python 记录构建函数为报错函数，证明公开 validate 命令不再调用旧前置扫描函数。

精确地图规则是本批唯一保留的精确来源校验分支：native 候选摘要把地图归并为 `Map*.json`，所以 `Map001.json` 这类规则不能直接消费聚合命中。该分支只在规则匹配到地图文件且规则模式不是 `Map*.json` 时触发，避免牺牲旧的单图外部契约。

后续 `NoteTagTextExtraction` 仍会执行一次实际提取，用于生成报告明细、写回预览和错误检查；这属于本批保留的报告事实来源，下一批不应把它误判为前置候选扫描残留。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_contract_exists tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_record_exists_and_tracks_contract`，3 failed。
- GREEN 服务级目标测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan`，1 passed。
- GREEN 精确地图保护测试：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_keeps_precise_map_file_scope`，1 passed。
- 目标测试和记录保护命令：`uv run pytest tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_keeps_precise_map_file_scope tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_contract_exists tests/test_scan_budget.py::test_batch93_note_tag_validate_native_candidate_record_exists_and_tracks_contract`，结果 4 passed。
- 相关 Note 标签回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_note_tag_rule_validation_import_and_pending_export tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_prefix_read_for_translated_count tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_uses_native_candidate_scan tests/test_agent_toolkit_rule_import.py::test_validate_note_tag_rules_keeps_precise_map_file_scope tests/test_rmmz_note_nonstandard_data.py::test_note_tag_json_string_leaf_uses_visible_text_protocol tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back tests/test_scan_budget.py -k "note_tag"`，结果 14 passed，134 deselected。
- 类型检查：`uv run basedpyright`，结果 0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，结果退出码 0；Git 仅提示若干已有工作区文件下次写入时会从 LF 转为 CRLF。
- 全量测试：因本批修改生产代码，按临时验证策略执行 `uv run pytest`，结果 926 passed，用时 252.84s。
- 本批未修改 Rust 原生代码。

## 审查处理

本批派发只读子代理复核 validate 调用链、native helper 复用方式、应新增的保护测试和不应触碰的路径。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

本地实现采纳本批最小边界：只迁 `validate-note-tag-rules` 的前置候选命中检查，不迁导入事务、workspace helper、flow gate、text-scope rule hit、数据库或写回路径。

## 剩余风险

`import-note-tag-rules`、scope hash、text-scope rule hit、workflow gate、workspace 校验和写回协议仍未消费新 native 前置校验函数。公开命令层还剩 Note 标签规则导入命令保留 Python 候选事实来源，下一批需要继续收束。

Note 标签 native 分支使用真实 `source_text_required_pattern` 计算 `translatable_hit_count`。如果用户配置使用 Rust regex 不支持但 Python re 支持的高级语法，规则校验会显式失败；这是本批延续 batch 91/92 的显式错误边界。

## 下一批入口

建议下一批进入 Note 标签规则导入 native 候选接入：让 `import-note-tag-rules` 的导入前规则命中检查消费同一份 native 候选摘要，同时保护旧译文清理、空规则确认、scope hash 和数据库事务行为不漂移。
