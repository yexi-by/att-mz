# Rust Scope/Index Engine 批次 6AK 验收记录

## 本批范围

本批推进非标准 data 已导入规则链路重复 native leaves 扫描收束审计。范围限定为 `TextScopeService.build` 一轮构建内的三段链路：freshness check、正文提取和规则命中诊断。目标是让同一批非标准 data 文件的 native leaves 事实只构建一次，并在这三段链路内共享。

## 保护网

- `tests/test_nonstandard_data.py::test_nonstandard_data_text_scope_reuses_native_leaves_within_build` 对 `TextScopeService.build` 计数，断言同一轮构建只调用一次 `resolve_nonstandard_data_file_leaves_native`。
- `tests/test_scan_budget.py::test_batch68_nonstandard_data_text_scope_reuses_native_leaves_context` 固定 `NonstandardDataTextExtractionContext`、`build_nonstandard_data_text_extraction_context` 和 `nonstandard_data_context` 传参边界。
- `tests/test_scan_budget.py::test_batch68_nonstandard_data_text_scope_reuse_record_exists_and_tracks_contract` 固定本批验收记录和计划索引。

## 实现说明

- `app/nonstandard_data/extraction.py` 新增 `NonstandardDataTextExtractionContext`，集中保存当前文件快照与 Rust native leaves 结果。
- `app/nonstandard_data/extraction.py` 新增 `build_nonstandard_data_text_extraction_context`，供一轮流程先读取文件并展开 native leaves。
- `NonstandardDataTextExtraction` 新增可选 `context` 参数；`extract_all_text` 与 `collect_rule_hits` 优先复用传入上下文。
- `app/text_scope/builder.py` 在读取非标准 data 规则后构建一次 `nonstandard_data_context`，并传给 freshness check、`build_translation_data_map` 和 `collect_nonstandard_data_rule_hits`。
- `app/text_scope/rule_hits.py` 的 `collect_nonstandard_data_rule_hits` 新增可选 `nonstandard_data_context` 参数，继续由 `NonstandardDataTextExtraction` 负责规则展开。

## 旧路径收束

`TextScopeService.build` 不再让 freshness check、正文提取和规则命中诊断分别触发 native leaves scan。旧 `resolve_nonstandard_data_leaves` 仍保留在 scanner 兼容边界；本批不处理旧 Python resolver 删除。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、导入规则 JSON 格式或用户可见报告字段变化。本批只调整内部 text-scope 构建时的非标准 data leaves 事实复用。

## 性能证据

RED 阶段计数证明当前 `TextScopeService.build` 对同一文件触发 3 次 native leaves scan。GREEN 阶段同一测试证明已收束为 1 次。该证据覆盖本批目标链路：freshness check、正文提取和规则命中诊断。

## 验证结果

- RED：`uv run pytest tests/test_nonstandard_data.py::test_nonstandard_data_text_scope_reuses_native_leaves_within_build tests/test_scan_budget.py::test_batch68_nonstandard_data_text_scope_reuses_native_leaves_context tests/test_scan_budget.py::test_batch68_nonstandard_data_text_scope_reuse_record_exists_and_tracks_contract`，3 failed；行为测试观测到 3 次 native leaves scan，静态测试缺少 context 入口，记录测试缺少本批记录。
- GREEN：`uv run pytest tests/test_nonstandard_data.py::test_nonstandard_data_text_scope_reuses_native_leaves_within_build tests/test_scan_budget.py::test_batch68_nonstandard_data_text_scope_reuses_native_leaves_context tests/test_scan_budget.py::test_batch68_nonstandard_data_text_scope_reuse_record_exists_and_tracks_contract`，3 passed。
- `uv run pytest tests/test_nonstandard_data.py tests/test_scan_budget.py`，115 passed。
- `uv run basedpyright`，0 errors，0 warnings，0 notes。
- `uv run pytest`，861 passed。
- `git diff --check`，通过；仅输出既有 LF/CRLF 工作区提示。

## 审查处理

本批未进入外部 PR 审查。实现范围保持在 Python text-scope 与非标准 data 提取上下文，未改 Rust 原生入口和公开 CLI 契约。

## 剩余风险

本批只收束 `TextScopeService.build` 内的重复 native leaves scan。非标准 data 支线仍保留旧 Python resolver 公共导出边界，且 active runtime audit、直接写回输入提取等命令各自有独立 leaves 事实构建；这些路径是否需要进一步合并，应在支线收束审计中统一判断。

## 下一批入口

建议下一批进入非标准 data 支线收束回归审计：梳理候选扫描、规则覆盖、已导入规则提取、text-scope 复用和 active runtime audit 的剩余旧路径边界，决定是否删除或隔离 `resolve_nonstandard_data_leaves` 等兼容入口。
