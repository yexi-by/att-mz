# Rust Scope/Index Engine 批次 6BI 验收记录

## 本批范围

本批是 Note 标签扫描命令 native 薄适配接入。范围只覆盖 `export-note-tag-candidates` 对应的候选 JSON 导出，让它复用 `build_native_note_tag_candidates_payload` 与 `scan_rule_candidates(note_tags)`。

本批触及以下文件：

- `app/native_note_tag_scan.py`
- `app/note_tag_text/exporter.py`
- `tests/test_agent_toolkit_manual_import.py`
- `tests/test_scan_budget.py`

本批不迁移 `validate-note-tag-rules`、`import-note-tag-rules`、`app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules`、workspace、text-scope rule hit、数据库规则导入、空规则确认 hash 或写回协议路径。

## 保护网

新增 `tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan`：

- monkeypatch `app.note_tag_text.exporter.collect_note_tag_candidates` 为报错函数。
- 调用公开服务方法 `export_note_tag_candidates`。
- 断言报告仍返回 `ok`，输出 JSON 仍包含 `details.candidates`。
- 断言 `sample_values`、`sample_locations` 和 `translatable_hit_count` 保持旧报告语义。

新增 `tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_contract_exists`：

- 固定计划表链接本批记录。
- 固定新增 `app/native_note_tag_scan.py`。
- 固定 helper 调用 `build_native_note_tag_candidates_payload` 和 `scan_native_rule_candidates`。
- 固定 `export_note_tag_candidates_file` 消费 `collect_native_note_tag_candidate_details`，不再直接调用 `collect_note_tag_candidates`。
- 固定 `app/agent_toolkit/services/rule_validation.py` 仍通过 `export_note_tag_candidates_file` 暴露公开服务入口。
- 固定 `count_note_tag_rule_candidates` 仍保留 `collect_note_tag_candidates`，避免本批扩大到 workflow gate。

新增 `tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_record_exists_and_tracks_contract
```

结果：3 failed。失败点分别是 `export-note-tag-candidates` 仍调用 Python `collect_note_tag_candidates`，计划表缺少 `docs/records/rust-scope-index/batches/batch-092.md`，以及本批记录不存在。

## 实现说明

新增 `app/native_note_tag_scan.py`：

- `collect_native_note_tag_candidate_details` 调用 `build_native_note_tag_candidates_payload` 与 `scan_native_rule_candidates`。
- 从 `scan_summary["note_tags"]["candidates"]` 读取 native 候选明细。
- 将 native 明细收窄为旧报告同形字段：`file_name`、`tag_name`、`hit_count`、`value_hit_count`、`translatable_hit_count`、`matched_file_count`、`sample_locations` 和 `sample_values`。

`app/note_tag_text/exporter.py::export_note_tag_candidates_file` 改为消费 `collect_native_note_tag_candidate_details`。`NoteTagCandidateExport`、输出 JSON 的 `candidate_tag_count`、`candidate_value_count`、`translatable_value_count` 和 `details.candidates` 字段保持不变。

## 旧路径收束

本批迁移的是 `export-note-tag-candidates` 的只读候选导出路径。旧 `collect_note_tag_candidates` 仍保留：

- `app/application/flow_gate.py::count_note_tag_rule_candidates` 继续使用它统计空规则候选数量。
- `app/application/flow_gate.py::note_tag_rule_scope_hash_for_text_rules` 继续使用它计算当前 scope hash。
- `app/text_scope/rule_hits.py::collect_note_tag_rule_hits`、`app/note_tag_text/importer.py`、`app/note_tag_text/extraction.py` 和写回协议仍按当前路径运行。
- 测试夹具中的 `collect_note_tag_candidates` 保留为后续迁移前的兼容辅助。

`prepare-agent-workspace` 生成 Note 标签候选文件时复用 `export_note_tag_candidates_file`，因此会等价消费本批 native-backed exporter；本批没有迁移 workspace 校验、manifest 规则判断或缺失规则阻断逻辑。

下一批迁移规则校验或导入前覆盖检查时，需要单独建立 RED/GREEN，不能把本批结论外推。

## 外部契约变化

没有 CLI 参数、stdout JSON 字段、README、Skill、配置字段、数据库 schema 或 Rust 原生代码变化。

`export-note-tag-candidates` 的可观察报告字段保持：

- `summary.candidate_tag_count`
- `summary.candidate_value_count`
- `summary.translatable_value_count`
- `details.candidates.items[].file_name`
- `details.candidates.items[].tag_name`
- `details.candidates.items[].hit_count`
- `details.candidates.items[].value_hit_count`
- `details.candidates.items[].translatable_hit_count`
- `details.candidates.items[].matched_file_count`
- `details.candidates.items[].sample_locations`
- `details.candidates.items[].sample_values`

## 性能证据

本批将 `export-note-tag-candidates` 的 Note 标签候选解析和聚合重活从 Python `collect_note_tag_candidates` 切到 Rust `scan_rule_candidates(note_tags)`。Python 只负责已加载 `GameData` 的 native payload 组装、native JSON 明细收窄、报告组装和文件写入。

服务级保护测试通过 monkeypatch 旧 Python 候选统计函数为报错函数，证明导出命令路径不再调用旧 Python 聚合函数。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_record_exists_and_tracks_contract`，3 failed。
- GREEN 服务级目标测试：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan`，1 passed。
- 目标测试和记录保护命令：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_contract_exists tests/test_scan_budget.py::test_batch92_note_tag_scan_command_native_adapter_record_exists_and_tracks_contract`，3 passed。
- 相关 Note 标签回归：`uv run pytest tests/test_agent_toolkit_manual_import.py::test_note_tag_rule_validation_import_and_pending_export tests/test_agent_toolkit_manual_import.py::test_export_note_tag_candidates_uses_native_candidate_scan tests/test_rmmz_note_nonstandard_data.py::test_note_tag_json_string_leaf_uses_visible_text_protocol tests/test_rmmz_note_nonstandard_data.py::test_map_event_note_tag_rules_extract_and_write_back tests/test_scan_budget.py -k "note_tag"`，10 passed，134 deselected。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 文档敏感路径和占位文案搜索：覆盖 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills`，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批未修改 Rust 原生代码。
- 本批按临时例外未跑全量 `uv run pytest`。剩余风险是全仓其它非 Note 标签测试未在本批重复执行；本批用目标测试、相关 Note 标签行为测试、scan_budget 记录保护、类型检查、文档敏感路径搜索和 diff 空白检查约束影响面。

## 审查处理

本批派发只读子代理复核 Note 标签导出路径、native helper 边界、应新增的保护测试和不应触碰的路径。子代理不修改文件；最终收束以本地测试和验证命令输出为准。

本地实现采纳本批最小边界：只迁 `export-note-tag-candidates` 的候选导出路径，不迁规则校验、导入、workflow gate、workspace、text-scope rule hit、数据库或写回路径。

## 剩余风险

`validate-note-tag-rules`、`import-note-tag-rules`、scope hash、text-scope rule hit、workflow gate、workspace 校验和写回协议仍未消费新 native helper。公开命令层仍有两条 Note 标签规则命令保留 Python 候选事实来源，下一批需要继续收束。

Note 标签 native 分支使用真实 `source_text_required_pattern` 计算 `translatable_hit_count`。如果用户配置使用 Rust regex 不支持但 Python re 支持的高级语法，导出命令会显式失败；后续接入规则校验时需要继续保留这个显式错误边界。

## 下一批入口

建议下一批进入 Note 标签规则校验 native 候选接入：让 `validate-note-tag-rules` 消费同一份 `collect_native_note_tag_candidate_details` 候选摘要，同时保护现有命中统计、机器协议拒绝、已保存译文读取范围和错误文案不漂移。
