# Rust Scope/Index Engine 批次 5P translate --max-items 空术语 prompt 索引跳过记录

状态：已完成
日期：2026-06-04
对应计划：`docs/plans/completed/rust-scope-index-engine.md`

## 本批范围

本批只处理 `translate --max-items` warm index 路径中的空正文术语表边界：当当前游戏已经导入合法术语包，但正文术语表 `terms` 为空时，翻译批次构建不再创建无可注入内容的 `TerminologyPromptIndex`。

本批仍会读取字段译名表和正文术语表，并继续执行术语包一致性校验；字段译名表已有条目但正文术语表为空时仍会阻断。非空正文术语表的匹配、提示词注入、同条目名称术语和系统字段术语语义不变。

涉及文件：

- `app/application/handler.py`
- `tests/test_agent_toolkit_workflow_gate.py`
- `tests/test_scan_budget.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- `docs/records/rust-scope-index/batches/batch-022.md`

## 保护网

先建立或调整的测试：

- `tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_empty_terminology_prompt_index`
- `tests/test_scan_budget.py::test_batch22_translate_max_items_empty_terminology_skip_record_exists_and_is_linked_from_plan`

RED 结果：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_empty_terminology_prompt_index`：1 failed，旧实现会在空正文术语表下调用 `TerminologyPromptIndex.from_glossary()`。
- `uv run pytest tests/test_scan_budget.py::test_batch22_translate_max_items_empty_terminology_skip_record_exists_and_is_linked_from_plan`：1 failed，批次 5P 验收记录尚不存在。

## 改动范围

- `_load_terminology_prompt_index()` 在读取并校验术语包后，若 `glossary.term_count() == 0`，记录可注入译名为 0 并直接返回 `None`。
- `translate --max-items` warm index 批次构造继续通过现有 `terminology_prompt_index is None` 分支生成正文 prompt，不包含 `[[术语表]]` 段落。
- 共享 helper 的空术语表行为同步适用于普通完整 scope 翻译路径；非空术语表仍按原流程构建索引。

## 旧路径收束

- 删除“空正文术语表也创建空 prompt 索引对象”的旧路径。
- 保留术语包读取和校验路径，避免把未导入术语表、字段译名表未填写或术语包不一致误判为可跳过状态。
- 保留非空正文术语表的完整索引构建路径，避免在本批引入可能漏掉同条目名称术语或系统字段术语的裁剪风险。

## 外部契约变化

- CLI 参数、stdout JSON 字段、退出码和主要用户文案不变。
- 空正文术语表下的模型用户 prompt 仍不包含术语表段落；本批只减少无效索引构建。
- 术语包缺失、字段译名表缺失、字段译名表已填写但正文术语表为空等失败语义不变。

## 性能证据

本批没有运行真实大样本耗时对比；性能证据来自行为测试和路径收束：

- 行为测试在 warm index 小批中把 `TerminologyPromptIndex.from_glossary()` 替换为失败函数，确认空正文术语表时不再构建 prompt 索引。
- 空正文术语表是默认最小前置状态和无术语项目的常见状态，跳过索引构建可避免一次无收益对象创建和匹配索引初始化。

## 验证结果

局部验证：

- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_empty_terminology_prompt_index`：RED 阶段 1 failed，原因是旧实现仍构建空 prompt 索引；GREEN 阶段 1 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch22_translate_max_items_empty_terminology_skip_record_exists_and_is_linked_from_plan`：RED 阶段 1 failed，原因是批次 5P 验收记录尚不存在。
- `uv run pytest tests/test_scan_budget.py::test_batch22_translate_max_items_empty_terminology_skip_record_exists_and_is_linked_from_plan`：GREEN 阶段 1 passed。
- `uv run pytest tests/test_agent_toolkit_workflow_gate.py::test_translate_max_items_warm_index_skips_empty_terminology_prompt_index tests/test_scan_budget.py::test_batch22_translate_max_items_empty_terminology_skip_record_exists_and_is_linked_from_plan`：2 passed。

完整门禁：

- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest`：738 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：69 passed。
- `rg -n "ATT_MZ_RUST_THREADS" app rust/src scripts tests`：无匹配，确认本批未引回旧环境变量入口。
- `git diff --check`：退出码 0；仅有仓库当前 LF/CRLF 转换提示。

## 剩余风险

- 非空正文术语表仍会为本轮 pending 小批构建完整 prompt 索引；这是为保持同条目名称术语、系统字段术语和正文子串命中语义而保留的安全边界。
- 本批没有新增大样本 benchmark，收益以路径删除测试作为证据。
- `TerminologyPromptIndex.from_glossary()` 内部仍存在可独立审计的重复索引构建机会，但不在本批范围内。

## 下一批入口

批次 5Q：建议推进 `translate --max-items` 非空术语索引裁剪审计，重点确认是否能基于本轮 pending 文本、角色、地图名和 `location_path` 所属对象提前缩小 glossary，同时不改变同条目名称术语和系统字段术语注入语义。
