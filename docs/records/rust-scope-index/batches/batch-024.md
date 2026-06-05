# Rust Scope/Index Engine 批次 5R translate --max-items 地图显示名术语上下文索引化记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 路径缺少地图显示名上下文的问题：重建 text index 时把 `TranslationData.display_name` 写入索引定位元数据，读取 pending 小批时从 `locator_json` 还原到 `TranslationData.display_name`，让场景 prompt 和地图名术语注入可以在不加载完整 `GameData` 的情况下工作。

本批不处理数据库条目名称术语和 System 字段术语；这两类仍需要后续设计轻量元信息来源，避免回到完整 `GameData` 加载。

涉及文件：

- `app/text_index.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-024.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_map_display_name_terminology`
- `tests/test_scan_budget.py::test_batch24_translate_max_items_map_display_name_context_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_map_display_name_terminology`：1 failed，旧实现还原出的 warm index 小批 prompt 里地图为空，且 `始まりの町 => 起始之镇` 没有注入。
- `uv run pytest tests/test_scan_budget.py::test_batch24_translate_max_items_map_display_name_context_record_exists_and_is_linked_from_plan`：1 failed，批次 5R 验收记录尚不存在。

## 改动范围

- text index 构建 payload 的 `locator` 增加 `display_name`，Rust Scope/Index Engine 继续透传 `locator_json`，无需修改 Rust 结构。
- `build_text_index_items_from_scope()` 同步写入 `display_name`，保持 Python 侧构建 helper 与 Rust 构建路径一致。
- `text_index_items_to_translation_data_map()` 从 `locator_json.display_name` 还原 `TranslationData.display_name`，并对同一来源文件内不一致的地图名显式报错。
- `collect_text_index_rules_fingerprint()` 增加 `prompt_context_version=display_name_v1`，让旧索引在新版本下显式过期并重建。

## 旧路径收束

- 删除 warm index 小批还原时固定 `display_name=None` 的旧行为。
- 保留旧索引缺失 `locator_json.display_name` 时的兼容读取；缺失字段只表示旧索引或非地图来源没有地图名。
- 不新增完整 `GameData` 回退路径；测试明确禁止 warm index 为地图名术语加载完整游戏数据。

## 外部契约变化

- CLI 参数、stdout JSON 字段和退出码不变。
- `translate --max-items` 对 Map 文件的小批 prompt 现在会恢复“地图：<地图显示名>”场景文本，并可注入命中的地图名术语。
- text index 规则指纹加入 prompt 上下文版本，已有旧索引会在下次命令中被判定为规则变化并自动重建。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和路径收束：

- 行为测试在 warm index 命中 Map001 pending 小批时禁止 `_load_session_game_data()`，确认地图名场景和地图名术语仍能进入 prompt。
- 地图名通过 text index `locator_json` 随索引项保存和读取，没有新增完整 `GameData` 加载，也没有新增 SQLite 全量扫描。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_restores_map_display_name_terminology`：RED 阶段 1 failed，原因是旧实现 prompt 地图为空且没有地图名术语；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch24_translate_max_items_map_display_name_context_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5R 验收记录尚不存在。

收尾验证：

- `uv run basedpyright`：0 errors，0 warnings，0 notes。
- `uv run pytest`：742 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无命中，确认旧线程环境变量名没有残留。
- `git diff --check`：通过；输出中只有 Git 的 LF/CRLF 工作区提示，没有空白错误。

## 剩余风险

- 数据库条目名称术语和 System 字段术语仍未在 warm index 中补齐；下一批需要设计 text index 或轻量 SQLite 元数据承载这些上下文。
- 本批通过 text index 规则指纹版本强制旧索引重建，但没有单独增加“旧指纹必须失效”的窄测试；完整行为由现有失效检测路径覆盖。
- 地图名存放在每个索引项的 `locator_json` 中，会有少量重复元数据；这是为避免扩表和保持本批范围可控做出的取舍。

## 下一批入口

批次 5S：建议推进 `translate --max-items` 数据库条目名称术语上下文索引化，重点覆盖 `Skills.json/<id>/description` 这类正文通过同一数据库对象名称命中术语的场景，同时避免完整 `GameData` 加载。
