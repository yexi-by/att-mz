# Rust Scope/Index Engine 批次 5T translate --max-items System 字段术语上下文索引化记录

## 本批范围

本批只处理 `translate --max-items` warm index 路径缺少 System 类型数组术语上下文的问题：重建 text index 时把 `System.json` 的 `elements`、`skillTypes`、`weaponTypes`、`armorTypes`、`equipTypes` 非空值写入索引定位元数据，读取 pending 小批时从 `locator_json` 还原到 `TranslationItem.terminology_owner_terms`，让 `System.json` 正文翻译可以在不加载完整 `GameData` 的情况下注入这些系统类型术语。

本批不处理术语之外的 prompt 构建成本、批次排序策略和真实大样本耗时对比；这些留给后续 `translate --max-items` 收尾审计。

## 保护网

新增行为测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_system_field_terminology`
- `tests/test_scan_budget.py::test_batch26_translate_max_items_system_field_context_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_system_field_terminology tests/test_scan_budget.py::test_batch26_translate_max_items_system_field_context_record_exists_and_is_linked_from_plan`：2 failed。
- 行为测试失败原因：warm index 小批只还原正文、角色、地图名和数据库 owner 名称上下文，`魔法` 只存在于 `System.json.skillTypes` 时被裁剪到 0 条可注入术语。
- 记录测试失败原因：批次 5T 验收记录尚不存在。

## 改动范围

- text index 构建 payload 的 `locator.terminology_owner_terms` 增加 System 类型数组术语。
- `build_text_index_items_from_scope()` 同步支持 System 类型数组术语，保持 Python helper 与 Rust 构建路径一致。
- `collect_text_index_rules_fingerprint()` 的 prompt context 版本更新为 `display_name_owner_system_terms_v3`，让旧索引显式过期并重建。
- `TranslationItem.terminology_owner_terms`、`filter_glossary_for_translation_data()` 和 `TerminologyPromptIndex.select_for_batch()` 沿用批次 5S 已建立的 owner 术语通道。

## 旧路径收束

- 删除 warm index 小批只能靠完整 `GameData` 的 `_system_entries` 注入 System 类型术语的限制。
- 保留旧索引缺失 `locator_json.terminology_owner_terms` 时的兼容读取；缺失字段只表示旧索引或当前来源没有 owner 术语。
- 不新增完整 `GameData` 加载兜底，不新增 SQLite 表，也不把 System 术语上下文拆成第二事实来源。

## 外部契约变化

- 公开 CLI 参数、配置字段、环境变量、JSON 报告结构和数据库 schema 没有变化。
- text index 的 `locator_json.terminology_owner_terms` 现在也可能包含 System 类型数组术语；该字段属于持久索引内部定位元数据。
- 旧索引会通过 prompt context 版本变化触发重建。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和路径收束：

- 行为测试在 warm index 命中 `System.json/gameTitle` 小批时禁止 `_load_session_game_data()`，确认 System 类型数组术语仍能进入 prompt。
- System 类型数组术语通过 text index `locator_json` 随索引项保存和读取，没有新增完整 `GameData` 加载，也没有新增 SQLite 全量扫描。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_system_field_terminology`：GREEN 阶段 1 passed。

审查后补充验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_system_field_terminology tests/test_scan_budget.py::test_batch26_translate_max_items_system_field_context_record_exists_and_is_linked_from_plan`：2 passed。

完整门禁：

- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `uv run pytest`：747 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批没有新增 Rust 线程池配置入口。

## 审查处理

请求代码审查后未发现 P1/P2 问题。已处理两项 P3 建议：

- System 字段术语测试改为逐批断言，确认 `魔法 => 魔法系` 只出现在包含 `System.json/gameTitle` 的批次 prompt 中。
- 批次记录测试新增未回填收尾验证占位语句检查，防止记录里残留未完成文案。

## 剩余风险

- 本批通过 text index 规则指纹版本强制旧索引重建，但没有单独增加“旧指纹必须失效”的窄测试；完整行为由现有失效检测路径覆盖。
- System 类型数组术语存放在每个 `System.json` 索引项的 `locator_json` 中，会有少量重复元数据；这是为避免扩表并保持本批范围可控做出的取舍。
- 本批只证明 System 类型术语注入不回到完整 `GameData`，不代表 `translate --max-items` 的 prompt 构建阶段已经完成最终性能收尾。

## 下一批入口

批次 5U：建议推进 `translate --max-items` prompt context 索引元信息收尾审计，复核地图名、数据库条目名称和 System 类型术语三类 GameData 派生上下文是否已经全部由 text index 承载，并用测试固定不会重新引入完整 `GameData` 加载或无意义重复扫描。
