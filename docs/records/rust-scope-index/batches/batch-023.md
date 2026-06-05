# Rust Scope/Index Engine 批次 5Q translate --max-items 非空术语 prompt 索引预裁剪记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 路径中的非空正文术语表加载边界：当本轮已经通过 SQLite 读取到 `--max-items` 限制后的 pending 小批时，构建 `TerminologyPromptIndex` 前先把正文术语表裁剪到本轮 pending 文本可能命中的术语。

裁剪依据只复用现有 warm index prompt 注入语义：已存在的地图显示名精确命中、说话人角色精确命中、正文原文子串命中。本批不补齐 warm index 当前缺少的 `GameData` 派生术语上下文；完整 scope 翻译路径仍使用 `GameData` 构建同条目名称术语和系统字段术语索引。

涉及文件：

- `app/terminology/prompt.py`
- `app/terminology/__init__.py`
- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-023.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prunes_unmatched_terminology_before_prompt_index`
- `tests/test_scan_budget.py::test_batch23_translate_max_items_nonempty_terminology_prune_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prunes_unmatched_terminology_before_prompt_index`：1 failed，旧实现把本轮正文命中的 `火の術` 和无关的 `海の術` 一起传给 prompt 索引。
- `uv run pytest tests/test_scan_budget.py::test_batch23_translate_max_items_nonempty_terminology_prune_record_exists_and_is_linked_from_plan`：1 failed，批次 5Q 验收记录尚不存在。

## 改动范围

- 新增 `filter_glossary_for_translation_data()`，按当前 `TranslationData` 已携带的地图名、角色名和原文行筛出现有 warm index prompt 语义下可能注入的术语。
- `_translate_text_from_warm_index()` 在读取 SQL pending 小批后，把小批 `TranslationData` 传给 `_load_terminology_prompt_index()`。
- `_load_terminology_prompt_index()` 仅在 `game_data is None` 且传入小批数据时裁剪 glossary；完整 scope 翻译路径不传小批数据，保持原完整索引语义。
- 当裁剪后没有任何本轮可注入术语时，沿用批次 5P 的 `None` 索引路径，不生成 `[[术语表]]` 段落。

## 旧路径收束

- 删除 warm index 小批在非空正文术语表下无条件为完整 glossary 构建 prompt 索引的旧路径。
- 保留术语包读取和一致性校验，避免把术语包缺失或字段译名表未填写误判为可裁剪状态。
- 保留完整 scope 的完整 glossary 索引路径，避免裁剪掉只能通过 `GameData` 所属对象或系统字段发现的术语。

## 外部契约变化

- CLI 参数、stdout JSON 字段和退出码不变。
- 相对当前 warm index 的无 `GameData` prompt 语义，模型 prompt 的术语注入结果不变；未命中本轮 pending 文本、角色或已携带地图名的术语本来也不会进入该批 prompt。
- 日志中的“可注入译名”数量在 warm index 小批下改为本轮小批可注入候选数，可能小于完整正文术语表条目数。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和路径收束：

- 行为测试构造非空正文术语表，其中只有 `火の術` 命中本轮 pending 文本，确认传给 `TerminologyPromptIndex.from_glossary()` 的 glossary 已不包含无关的 `海の術`。
- 代码路径从“完整 glossary 全量构建 prompt 索引”改为“SQL pending 小批相关 glossary 构建 prompt 索引”，减少小批翻译中无关术语的对象创建和批次匹配工作。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prunes_unmatched_terminology_before_prompt_index`：RED 阶段 1 failed，原因是旧实现仍把无关术语传入 prompt 索引；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch23_translate_max_items_nonempty_terminology_prune_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5Q 验收记录尚不存在。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_prunes_unmatched_terminology_before_prompt_index tests/test_scan_budget.py::test_batch23_translate_max_items_nonempty_terminology_prune_record_exists_and_is_linked_from_plan`：2 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：740 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- 本批的裁剪粒度是 `--max-items` 后的 SQL pending 小批，不是 `--max-batches` 后实际会发送的批次；如果 `max_batches` 进一步丢弃后续批次，仍可能保留只属于未发送批次的术语。
- warm index 还原的文本数据当前缺少完整 scope 路径可用的 `GameData` 派生上下文，例如部分地图显示名、同数据库条目名称和系统字段术语；本批没有补齐这类术语元信息，只保证不进一步改变现有 warm index prompt 语义。
- 本批仍需要扫描当前 glossary 的 key 来判定是否命中小批文本；它减少索引构建和后续批次匹配工作，但不是术语表读取本身的 SQLite 快路径。
- `TerminologyPromptIndex.from_glossary()` 内部仍存在重复 `_build_indexes()` 调用，可作为独立小批清理。

## 下一批入口

批次 5R：建议审计 `translate --max-items` warm index 如何补齐 `GameData` 派生术语元信息，重点确认能否通过 text index 或轻量 SQLite 元数据保留地图显示名、同数据库条目名称和系统字段术语，避免回到完整 `GameData` 加载。
