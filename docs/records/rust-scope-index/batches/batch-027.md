# Rust Scope/Index Engine 批次 5U translate --max-items prompt context 索引元信息收尾审计记录

## 本批范围

本批只做 `translate --max-items` warm index prompt context 的收尾审计：复核地图显示名、数据库条目名称和 System 类型数组术语三类 `GameData` 派生上下文是否已经全部由 text index `locator_json` 承载，并固定旧 prompt context 版本必须让索引显式失效。

本批不继续新增 prompt context 类型，不调整批次排序策略，不运行真实大样本耗时对比，也不处理写回相关命令的可写路径和质量 gate 复用问题。

## 保护网

新增行为和审计测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prompt_context_uses_index_metadata_only`
- `tests/test_text_index.py::test_prompt_context_version_change_invalidates_text_index`
- `tests/test_scan_budget.py::test_batch27_translate_max_items_prompt_context_audit_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prompt_context_uses_index_metadata_only tests/test_text_index.py::test_prompt_context_version_change_invalidates_text_index tests/test_scan_budget.py::test_batch27_translate_max_items_prompt_context_audit_record_exists_and_is_linked_from_plan`：1 failed，2 passed。
- 行为测试已证明当前 warm index 小批能在同一次运行中从索引还原地图名、数据库 owner 术语和 System owner 术语，并且 `TerminologyPromptIndex.from_glossary()` 收到的 `game_data` 为 `None`。
- 版本失效测试已证明 prompt context 版本进入 rules fingerprint；旧 prompt context 版本会触发 `rules_changed`。
- 记录测试失败原因：批次 5U 验收记录尚不存在。

## 改动范围

- 新增组合行为测试，覆盖同一 `translate --max-items` warm index 小批中的三类 prompt context。
- 新增 prompt context 版本失效测试，固定 `TEXT_INDEX_PROMPT_CONTEXT_VERSION` 变化必须让旧索引过期。
- 新增批次 5U 验收记录测试，防止本批记录缺失或残留未回填验证占位文案。
- 本批没有修改生产逻辑；现有 `app/text_index.py` 已由批次 5R、5S、5T 分别完成地图显示名、数据库条目名称和 System 类型数组术语的索引承载。

## 旧路径收束

- 确认 warm index prompt context 不通过 `_load_session_game_data()` 回到完整 `GameData` 加载。
- 确认 prompt context 术语预裁剪消费 `text_index_items_to_translation_data_map()` 还原出的 `TranslationData.display_name` 和 `TranslationItem.terminology_owner_terms`。
- 确认旧 prompt context 版本不会被继续视为有效索引。

## 外部契约变化

- 公开 CLI 参数、stdout JSON 字段、退出码、配置字段、环境变量和 SQLite schema 没有变化。
- text index 内部 prompt context 版本仍为 `display_name_owner_system_terms_v3`。
- `locator_json.display_name` 和 `locator_json.terminology_owner_terms` 继续作为持久索引内部定位元数据，不新增外部 Agent 契约字段。

## 性能证据

- 组合行为测试在 warm index prompt context 阶段禁止 `_load_session_game_data()`，确认三类上下文可以同时进入 prompt 且不加载完整 `GameData`。
- pending 小批仍通过 `read_pending_text_index_items(limit=N)` 在 SQL 层应用上限；本批没有新增全量索引读取、完整 scope 还原或候选扫描。
- prompt context 版本失效测试证明旧索引会被 `rules_changed` 拦截并重建，避免缺少新元信息的旧索引继续参与小批 prompt 构建。

## 验证结果

局部 RED 验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prompt_context_uses_index_metadata_only tests/test_text_index.py::test_prompt_context_version_change_invalidates_text_index tests/test_scan_budget.py::test_batch27_translate_max_items_prompt_context_audit_record_exists_and_is_linked_from_plan`：1 failed，2 passed。

局部 GREEN 验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prompt_context_uses_index_metadata_only tests/test_text_index.py::test_prompt_context_version_change_invalidates_text_index tests/test_scan_budget.py::test_batch27_translate_max_items_prompt_context_audit_record_exists_and_is_linked_from_plan`：3 passed。

完整门禁：

- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `uv run pytest`：750 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批没有重新引入旧线程环境变量入口。
- `git diff --check`：通过；输出中只有 Git 的 LF/CRLF 工作区提示，没有空白错误。

## 审查处理

请求子代理审查后未发现 P1 问题。已处理审查反馈：

- P2：组合测试原先使用 `火の術` 作为数据库 owner 术语，而夹具中 `Skills.json/1/message1` 也包含该词，存在原文自然命中导致假阳性的风险。测试已改为把 `Skills.json/1/name` 设为不出现在所选原文中的 `秘奥義`，并断言所选原文不含该词，再验证 `秘奥義 => 秘奥义` 只能通过 owner 元信息进入 prompt。
- P3：审查处理段落曾保留未来式占位文案；已改为具体审查结论，并让批次记录测试拦截同类未收尾表述。

## 剩余风险

- 本批没有做真实大样本耗时对比；性能结论限于路径收束和单元行为证据。
- `locator_json` 中的 prompt context 元信息仍按索引项重复存储，避免扩表但会带来少量重复元数据。
- 本批只收束 `translate --max-items` prompt context；写回相关命令是否完全复用索引事实仍需后续批次审计。

## 下一批入口

批次 5V：建议推进写回相关命令可写范围与质量 gate 复用索引事实审计，优先检查 `write-back`、`rebuild-active-runtime`、`write-terminology` 是否仍存在重复构建完整 Python scope 或重复运行质量 gate 的路径。
