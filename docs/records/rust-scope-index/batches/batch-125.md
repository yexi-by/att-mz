# Rust Scope/Index Engine 批次 125 验收记录

## 本批范围

- 批次编号：7B。
- 范围：P1-C 术语和语言探测命令组。
- 覆盖命令：`export-terminology`、`import-terminology`、`probe-source-language`。
- 目标：区分术语上下文生成、术语导入形状校验、源语言探测的真实 I/O/输出成本和 scope/index 成本；只收束共享热点，不为边缘命令新增独立复杂抽象。

## 保护网

- `tests/test_terminology.py::test_import_terminology_validates_shape_without_export_context_generation`：禁止 `import-terminology` 为字段形状校验生成导出用 speaker/database contexts。
- `tests/test_scan_budget.py::test_batch125_p1c_terminology_language_group_tracks_current_boundaries`：固定 7B 三条命令的 P1-C 预算事实、静态旧路径边界和当前事实来源。
- `tests/test_scan_budget.py::test_batch125_p1c_terminology_language_group_record_exists`：固定本验收记录、验证命令、敏感路径边界和下一批入口。

## RED/GREEN

- RED：`test_import_terminology_validates_shape_without_export_context_generation` 初次运行失败，命中 `TerminologyExtraction.extract_registry_and_contexts`，证明导入阶段仍生成导出上下文。
- RED：`test_batch125_p1c_terminology_language_group_tracks_current_boundaries` 和 `test_batch125_p1c_terminology_language_group_record_exists` 在计划进度和验收记录缺失时失败。
- GREEN：`TerminologyExtraction` 新增 `extract_registry`，只返回 current terminology registry shape，不构造 speaker/database context 输出对象。
- GREEN：`import-terminology` 使用 `extract_registry` 校验外部字段译名表形状，仍保留当前 GameData 加载，避免导入过期字段表。
- GREEN：`probe-source-language` 预算事实明确为 `raw JSON visible-text sampler`，不归入 GameData、scope/index 或候选扫描成本。

## 实现说明

- `app/terminology/extraction.py`：新增 `extract_registry`；`_collect_database_terms` 增加 `include_contexts` 参数，导入校验时跳过导出上下文构造。
- `app/application/handler.py`：`import_terminology` 切换到 `TerminologyExtraction.extract_registry`。
- `tests/scan_budget_contract.py`：修正 `import-terminology` 为 1 次 current GameData shape 校验，修正 `probe-source-language` 为 0 次 GameData load、事实来源为 raw JSON visible-text sampler。
- `export-terminology` 保持 `export_terminology_artifacts` 和 `extract_registry_and_contexts`，因为它必须写出字段译名表、正文术语表和只读上下文目录。

## 旧路径收束

- `import-terminology` 不再调用 `extract_registry_and_contexts`，不再为导入校验生成导出上下文对象。
- `import-terminology` 保留 current GameData 形状校验，这是防止导入过期字段译名表的真实 I/O 成本。
- `export-terminology` 的 `extract_registry_and_contexts` 保留为真实输出成本，不归入 scope/index 迁移对象。
- `probe-source-language` 只读取标准 data JSON 并采样玩家可见文本，不构建 `GameData`、不构建 `TextScopeService`、不消费 `SQLite text_index_items`。

## 外部契约变化

- 无 CLI 参数变化。
- stdout Agent JSON 字段名不变。
- 无数据库 schema 变化。
- 无 Rust 原生扩展 API 变化。
- 计划文档只更新进度和下一批入口，不改变项目长期验证基线。

## 性能证据

- `import-terminology` 不再生成导出用 speaker/database context 输出对象；导入只读取输入 JSON、加载当前 GameData 生成字段表形状，并执行数据库事务。
- `export-terminology` 明确保留 1 次 GameData 加载和上下文输出，这是术语工程文件的真实交付成本。
- `probe-source-language` 明确保留 raw JSON visible-text sampler，不构建 GameData 或文本范围。
- 7B 三条命令的 `text_scope_build_count`、`candidate_scan_count`、`plugin_source_ast_scan_count`、`quality_gate_count`、`write_plan_count` 都为 0。

## 验证结果

- `uv run pytest tests/test_terminology.py::test_import_terminology_validates_shape_without_export_context_generation tests/test_terminology.py::test_export_terminology_writes_terms_and_contexts tests/test_terminology.py::test_import_terminology_rejects_field_terms_without_glossary tests/test_terminology.py::test_import_terminology_accepts_cleaned_glossary_from_wrapped_field_terms`：4 passed。
- `uv run pytest tests/test_source_language_probe.py::test_source_language_probe_recommends_japanese_visible_text tests/test_source_language_probe.py::test_source_language_probe_recommends_english_visible_text`：2 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch125_p1c_terminology_language_group_tracks_current_boundaries tests/test_scan_budget.py::test_batch125_p1c_terminology_language_group_record_exists`：2 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- 文档敏感路径搜索：`文档敏感路径` 检查覆盖本记录和计划文档，NO_MATCH。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 本批按临时例外未跑全量 `uv run pytest`。

## 剩余风险

- 本批按临时例外未跑全量 `uv run pytest`。
- 本批修改生产 Python 代码；按用户当前 goal 禁止全量回归，剩余风险是未覆盖测试文件中的远端组合回归要等阶段收束或用户解除禁令后验证。
- `export-terminology` 仍会为术语工程输出加载完整当前 GameData 并写上下文目录，这是当前外部契约要求的真实输出成本。
- `import-terminology` 仍会加载当前 GameData 校验字段译名表形状，这是防止旧字段表静默导入的必要成本。

## 下一批入口

- 进入 7C：P1-C 插件导出和文档契约收束。
- 覆盖 `export-plugins-json`、README/Skill/docs 审计。
