# Rust Scope/Index Engine 批次 124 验收记录

## 本批范围

- 批次编号：7A。
- 范围：P1-C 运行审计命令组。
- 覆盖命令：`audit-active-runtime`、`diagnose-active-runtime`、`verify-feedback-text`。
- 目标：把运行审计相关命令的预算事实、旧路径边界和可验证行为收束到当前实现；真实 active runtime I/O 保留为命令成本，不再伪装成 scope/index 成本。

## 保护网

- `tests/test_agent_toolkit_feedback.py::test_verify_feedback_text_uses_warm_text_index_without_full_scope_build`：禁止 `verify-feedback-text` 在 warm index 下临时构建完整 `TextScopeService`。
- `tests/test_agent_toolkit_feedback.py::test_verify_feedback_text_uses_runtime_literal_scan_for_plugin_source`：禁止反馈源码残留定位回到旧 `_collect_plugin_source_text_candidates` regex 扫描。
- `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_skips_translation_source_scan_when_source_hash_matches`：固定 `diagnose-active-runtime` 在 source file hash 未变时不再扫描翻译源插件源码 AST。
- `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans`：固定 source file hash 已变时只批量扫描涉及的翻译源插件源码。
- `tests/test_scan_budget.py::test_batch124_p1c_runtime_audit_group_tracks_current_boundaries`：固定 7A 三条命令的 P1-C 预算事实、静态旧路径边界和当前事实来源。
- `tests/test_scan_budget.py::test_batch124_p1c_runtime_audit_group_record_exists`：固定本验收记录、验证命令、敏感路径边界和下一批入口。

## RED/GREEN

- RED：`test_verify_feedback_text_uses_warm_text_index_without_full_scope_build` 初次运行失败，命中 `TextScopeService.build`，证明反馈反查仍会临时构建完整文本范围。
- RED：`test_verify_feedback_text_uses_runtime_literal_scan_for_plugin_source` 初次运行失败，命中旧 `_collect_plugin_source_text_candidates`，证明反馈反查仍会通过 Python regex 扫描插件源码。
- RED：`test_diagnose_active_runtime_skips_translation_source_scan_when_source_hash_matches` 初次运行失败，命中翻译源插件源码 runtime literal scan，证明 source hash 未变时仍有额外 AST 扫描。
- RED：`test_batch124_p1c_runtime_audit_group_tracks_current_boundaries` 和 `test_batch124_p1c_runtime_audit_group_record_exists` 在计划进度和验收记录缺失时失败。
- GREEN：`verify-feedback-text` 改为读取 active runtime 残留，并使用 `SQLite text_index_items` 还原缺口分类范围。
- GREEN：反馈插件源码残留定位改用 `Rust plugin source runtime scan`，旧 regex helper 和导出残留已删除。
- GREEN：`diagnose-active-runtime` 在写回映射 `source_file_hash` 未变时直接信任源文件和源文本 hash；只在 hash 已变时批量扫描涉及的翻译源插件源码。

## 实现说明

- `app/agent_toolkit/services/feedback.py`：移除 `_load_translation_source_game_data` 和 `TextScopeService.build` 生产路径；命令内检测持久文本索引是否缺失或过期，必要时用 `rebuild_text_index(..., include_write_probe=False)` 重建，再通过 `text_index_items_to_scope` 和 `read_translation_location_paths` 完成缺口分类。
- `app/agent_toolkit/services/common.py`：`_collect_feedback_text_occurrences` 的插件源码分支改为消费 `scan_plugin_source_runtime_files_text_strict`，从 active runtime 插件源码字面量中定位反馈原文残留。
- `app/agent_toolkit/services/quality.py`：`_build_plugin_source_write_map_source_scan_cache` 只收集 `source_file_hash` 已变化的翻译源文件；`_plugin_source_write_map_source_matches` 在文件 hash 未变时不再读取源 AST scan cache。
- `tests/scan_budget_contract.py`：修正 P1-C 预算事实，明确 `audit-active-runtime` 为 1 次 active runtime GameData、`diagnose-active-runtime` 为 active runtime 加 translation source 两次 GameData、`verify-feedback-text` 为 1 次 active runtime GameData。

## 旧路径收束

- `verify-feedback-text` 不再构建完整 `TextScopeService`。
- `verify-feedback-text` 不再加载 translation source `GameData` 作为缺口分类事实来源。
- `_collect_plugin_source_text_candidates`、`PLUGIN_SOURCE_TEXT_PATTERN` 和 `_unescape_js_candidate_text` 已从生产公共服务中删除。
- `diagnose-active-runtime` 不再在 source hash 未变时为写回映射额外扫描翻译源插件源码 AST。
- `audit-active-runtime` 和 `diagnose-active-runtime` 保留 `audit_active_runtime_plugin_source_with_scan_cache`，真实运行态审计成本归入 active runtime I/O 与 Rust runtime scan cache，不归入文本范围重复构建。

## 外部契约变化

- 无 CLI 参数变化。
- stdout Agent JSON 字段名保留；`verify-feedback-text` summary 新增 `text_index_status` 和 `text_index_rebuild_summary`，用于说明缺口分类读取的是 warm index 还是已重建后的 index。
- 无数据库 schema 变化。
- 无 Rust 原生扩展 API 变化。
- 本批只更新计划进度和 P1-C 预算事实，不改变项目长期 AGENTS.md 基线。

## 性能证据

- `verify-feedback-text` warm index 下不再构建完整文本范围，缺口分类直接消费 `SQLite text_index_items`。
- `verify-feedback-text` 插件源码残留定位不再对 `js/plugins/*.js` 执行 Python regex 扫描，改为复用 `Rust plugin source runtime scan`。
- `diagnose-active-runtime` 保留 active runtime 扫描缓存；翻译源 AST 扫描只在写回映射记录的 `source_file_hash` 已变化时触发。
- `audit-active-runtime` 只做 active runtime 完整性和运行态源码审计，不构建文本范围、不生成写回计划、不执行质量 gate。

## 验证结果

- `uv run pytest tests/test_agent_toolkit_feedback.py::test_verify_feedback_text_uses_warm_text_index_without_full_scope_build tests/test_agent_toolkit_feedback.py::test_verify_feedback_text_uses_runtime_literal_scan_for_plugin_source tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_skips_translation_source_scan_when_source_hash_matches tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans`：4 passed。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `uv run pytest tests/test_agent_toolkit_feedback.py::test_feedback_verification_and_plugin_source_scan_are_structural_only tests/test_agent_toolkit_feedback.py::test_feedback_verification_reads_active_files_not_origin_backups tests/test_agent_toolkit_feedback.py::test_default_active_runtime_audit_skips_plugin_source_text_branch tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_default_mode_never_guesses_without_runtime_map tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_ignores_excluded_residual_with_exact_runtime_map tests/test_agent_toolkit_feedback.py::test_active_runtime_audit_reports_unmapped_residual_when_other_runtime_map_exists`：6 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch124_p1c_runtime_audit_group_tracks_current_boundaries tests/test_scan_budget.py::test_batch124_p1c_runtime_audit_group_record_exists`：2 passed。
- `uv run pytest tests/test_scan_budget.py::test_batch42_active_runtime_scan_cache_native_runtime_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch43_diagnose_active_runtime_write_map_source_scan_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch54_feedback_runtime_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch54_feedback_runtime_fixture_record_exists_and_tracks_contract`：4 passed。
- 文档敏感路径搜索：`文档敏感路径` 检查覆盖本记录和计划文档，NO_MATCH。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 本批按临时例外未跑全量 `uv run pytest`。

## 剩余风险

- 本批按临时例外未跑全量 `uv run pytest`。
- 本批修改生产 Python 代码；按用户当前 goal 禁止全量 `uv run pytest`，剩余风险是未覆盖测试文件中的远端组合回归要等阶段收束或用户解除禁令后验证。
- `verify-feedback-text` 在 text index 缺失或过期时仍需要重建一次持久索引；本批目标是重建后不再另起完整 scope 分类路径。
- `diagnose-active-runtime` 仍需要加载 active runtime 和 translation source `GameData`，这是当前运行诊断和写回映射反推的真实 I/O 成本，不属于本批删除范围。

## 下一批入口

- 进入 7B：P1-C 术语和语言探测命令组。
- 覆盖 `export-terminology`、`import-terminology`、`probe-source-language`。
