# Rust Scope/Index Engine 批次 5S translate --max-items 数据库条目名称术语上下文索引化记录

## 本批范围

本批只处理 `translate --max-items` warm index 路径缺少数据库条目名称术语上下文的问题：重建 text index 时把标准数据库条目的名称类上下文写入索引定位元数据，读取 pending 小批时从 `locator_json` 还原到 `TranslationItem.terminology_owner_terms`，让 `Skills.json/<id>/description` 这类正文可以在不加载完整 `GameData` 的情况下按同一条目的 `name` 注入术语。

本批不处理 System 字段术语；`System.json` 的 `elements`、`skillTypes`、`weaponTypes`、`armorTypes`、`equipTypes` 等仍留给下一批单独索引化。

## 保护网

新增行为测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_database_entry_name_terminology`
- `tests/test_scan_budget.py::test_batch25_translate_max_items_database_entry_name_context_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_database_entry_name_terminology tests/test_scan_budget.py::test_batch25_translate_max_items_database_entry_name_context_record_exists_and_is_linked_from_plan`：2 failed。
- 行为测试失败原因：warm index 小批只还原正文、角色和地图名上下文，`火の術` 只存在于 `Skills.json/1/name` 时被裁剪到 0 条可注入术语。
- 记录测试失败原因：批次 5S 验收记录尚不存在。

## 改动范围

- `TranslationItem` 增加内部字段 `terminology_owner_terms`，该字段不参与默认序列化，只用于当前批次 prompt 术语选择。
- text index 构建 payload 的 `locator` 增加 `terminology_owner_terms`，Rust Scope/Index Engine 继续透传 `locator_json`，无需修改 Rust 结构。
- `build_text_index_items_from_scope()` 同步支持可选 `GameData` 写入 owner 术语，保持 Python helper 与 Rust 构建路径一致。
- `text_index_item_to_translation_item()` 从 `locator_json.terminology_owner_terms` 还原内部 owner 术语列表。
- `filter_glossary_for_translation_data()` 和 `TerminologyPromptIndex.select_for_batch()` 把 owner 术语纳入 warm index 术语预裁剪和 prompt 选择。
- `collect_text_index_rules_fingerprint()` 的 prompt context 版本更新为 `display_name_owner_terms_v2`，让旧索引显式过期并重建。

## 旧路径收束

- 删除 warm index 小批只能靠正文 substring、角色和地图名保留术语的旧限制。
- 保留旧索引缺失 `locator_json.terminology_owner_terms` 时的兼容读取；缺失字段只表示旧索引或非数据库条目来源没有 owner 术语。
- 不新增完整 `GameData` 加载兜底，不新增 SQLite 表，也不把术语上下文拆成第二事实来源。

## 外部契约变化

- 公开 CLI 参数、配置字段、环境变量、JSON 报告结构和数据库 schema 没有变化。
- text index 的 `locator_json` 新增内部字段 `terminology_owner_terms`，属于持久索引内部定位元数据；旧索引会通过 prompt context 版本变化触发重建。
- `TranslationItem.terminology_owner_terms` 是内部运行字段，默认不参与序列化。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和路径收束：

- 行为测试在 warm index 命中 `Skills.json/1/description` 小批时禁止 `_load_session_game_data()`，确认同数据库条目名称术语仍能进入 prompt。
- 数据库条目名称通过 text index `locator_json` 随索引项保存和读取，没有新增完整 `GameData` 加载，也没有新增 SQLite 全量扫描。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_database_entry_name_terminology`：GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_database_entry_name_terminology tests/test_terminology.py::test_translation_prompt_injects_warm_index_actor_nickname_owner_term tests/test_scan_budget.py::test_batch25_translate_max_items_database_entry_name_context_record_exists_and_is_linked_from_plan`：3 passed。

审查处理：

- 子代理只读审查未发现 P1/P2 阻塞问题。
- P3：Actor nickname 缺少 warm-index 行为测试；已补 `tests/test_terminology.py::test_translation_prompt_injects_warm_index_actor_nickname_owner_term`。
- P3：本记录收尾验证未回填；已补具体命令与结果。

收尾验证：

- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `uv run pytest`：745 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无命中，确认旧线程环境变量名没有残留。
- `git diff --check`：通过；输出中只有 Git 的 LF/CRLF 工作区提示，没有空白错误。

## 剩余风险

- System 字段术语仍未在 warm index 中补齐；下一批需要为 `System.json` 类型数组设计轻量元信息承载方式。
- 本批通过 text index 规则指纹版本强制旧索引重建，但没有单独增加“旧指纹必须失效”的窄测试；完整行为由现有失效检测路径覆盖。
- owner 术语存放在每个相关索引项的 `locator_json` 中，会有少量重复元数据；这是为避免扩表并保持本批范围可控做出的取舍。

## 下一批入口

批次 5T：建议推进 `translate --max-items` System 字段术语上下文索引化，重点覆盖 `System.json` 正文翻译通过 `elements`、`skillTypes` 等同文件类型数组命中术语的场景，同时继续避免完整 `GameData` 加载。
