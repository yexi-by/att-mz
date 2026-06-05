# Rust Scope/Index Engine 批次 44 记录

## 本批范围

- 批次：6M，写回探针 fallback 接入 runtime 字面量扫描。
- 覆盖范围：`app/text_scope/write_probe.py::collect_write_back_probe_reasons` 在调用方没有传入 `PluginSourceScan` 时的插件源码 selector 检查 fallback。
- 成功状态：写回探针 fallback 不再调用翻译源 `scan_plugin_source_files_text_strict`；改用 `scan_plugin_source_runtime_files_text_strict` 批量扫描相关插件源码文件的全部字符串字面量，再按 selector、原文和译文行数检查写入可行性。
- 明确非范围：旧 `build_plugin_source_scan` 公共导出、翻译源 `scan_plugin_source_files_text_strict` 的保留边界、以及调用方显式传入 `PluginSourceScan` 时的复用分支仍留到后续审计。

## 保护网

- 调整 `tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview`：
  - 用 `scan_plugin_source_runtime_files_text_strict` 构造测试插件源码字面量和 location_path。
  - monkeypatch 禁止 `app.text_scope.write_probe.scan_plugin_source_files_text_strict`。
  - monkeypatch 禁止 `app.plugin_source_text.scanner.scan_plugin_source_files_text_strict`。
  - monkeypatch 计数 `app.text_scope.write_probe.scan_plugin_source_runtime_files_text_strict`，并调用真实 runtime 字面量扫描 helper。
  - 断言写回探针 fallback 只对 `HardcodedText.js` 和 `HardcodedTextExtra.js` 批量扫描一次，且不产生不可写原因。
- 新增 `tests/test_plugin_source_text.py::test_write_probe_fallback_does_not_reference_legacy_plugin_source_strict_scan`：
  - 静态断言 `app/text_scope/write_probe.py` 不再引用旧 `scan_plugin_source_files_text_strict` 名称。
  - 静态断言 fallback 源码仍引用 `scan_plugin_source_runtime_files_text_strict`。
- 新增 `tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 write probe 入口、runtime helper、旧 strict scan 边界和保护测试都写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `app/text_scope/write_probe.py`：
  - fallback 分支导入并调用 `scan_plugin_source_runtime_files_text_strict`。
  - 保留已有 selector、原文行、译文行数和语法错误处理逻辑。
  - 调用方显式传入 `PluginSourceScan` 时仍复用现有 scan 分支，不触发 fallback 扫描。

## 旧路径收束

- 已收束路径：
  - `collect_write_back_probe_reasons` 的插件源码 fallback 不再调用 `scan_plugin_source_files_text_strict`。
  - `TextScopeService.build(include_write_probe=True)` 在未传 `PluginSourceScan` 且需要探针时，插件源码 fallback 进入 runtime 字面量扫描。
- 保留路径：
  - `_collect_plugin_source_write_back_probe_reasons_from_scan` 仍使用调用方传入的 `PluginSourceScan` 候选事实。
  - `build_plugin_source_scan` 旧公共导出仍保留。
  - `scan_plugin_source_files_text_strict` 仍作为翻译源严格扫描入口存在，后续需要继续明确保留原因或改成薄适配。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 写回探针输出的不可写原因文案不变。
- 写回探针 fallback 仍按同一 selector、原文和短文本行数规则判断插件源码条目是否可写。

## 性能证据

- 写回探针 fallback 只扫描 `active_items` 中实际引用的插件源码文件。
- 多个插件源码条目跨多个文件时，仍通过一次 `scan_plugin_source_runtime_files_text_strict` 批量进入 Rust AST。
- fallback 不再构造翻译源候选索引和规则过滤结果，减少不必要对象构造。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview`
  - 结果：1 failed。
  - 失败原因：`write_probe.py` fallback 仍调用 `scan_plugin_source_files_text_strict`，被测试禁用后产生 AST 检查失败原因。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview`
  - 结果：1 passed。
- 文档保护 RED：`uv run pytest tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract`
  - 结果：1 failed。
  - 失败原因：`docs/records/rust-scope-index/batches/batch-044.md` 尚不存在。
- 文档保护 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract`
  - 初次结果：3 failed、2 passed，失败原因是相邻保护测试仍用 `raising=True` monkeypatch 已删除的旧 `write_probe.scan_plugin_source_files_text_strict` 符号。
  - 修复后结果：5 passed。
- 审查修复回归：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview tests/test_plugin_source_text.py::test_write_probe_fallback_does_not_reference_legacy_plugin_source_strict_scan tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract`
  - 结果：3 passed。
- 审查后相邻回归：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_probe_uses_batch_preview tests/test_plugin_source_text.py::test_write_probe_fallback_does_not_reference_legacy_plugin_source_strict_scan tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope tests/test_agent_toolkit_workspace.py::test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch tests/test_scan_budget.py::test_batch44_write_probe_plugin_source_runtime_scan_record_exists_and_tracks_contract`
  - 结果：6 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：802 passed。
- 最终复核：`uv run basedpyright` 与 `uv run pytest`
  - 结果：`basedpyright` 为 0 errors、0 warnings、0 notes；`pytest` 为 802 passed in 273.78s。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- Rust 门禁：本批未修改 Rust 源码或构建流程，因此未执行 `cargo fmt`、`cargo clippy` 和 `cargo test`；运行时 Rust AST adapter 相关行为由相邻 Python 测试覆盖。

## 审查处理

- 本批审计确认：写回探针 fallback 只需要全部字符串字面量和 selector，不需要翻译候选对象。
- 只读子代理审查指出：仅 monkeypatch `write_probe` 局部旧符号不够硬，无法抓住未来从 scanner 模块直接调用旧 strict scan 的回归。本批已补强动态测试，额外禁用 `app.plugin_source_text.scanner.scan_plugin_source_files_text_strict`。
- 只读子代理审查指出：应增加静态断言固定 `write_probe.py` 不再引用旧 strict scan 名称。本批已新增 `test_write_probe_fallback_does_not_reference_legacy_plugin_source_strict_scan`。
- 只读子代理确认：fallback 已切到 `scan_plugin_source_runtime_files_text_strict`，显式传入 `PluginSourceScan` 的复用分支仍保留，selector、原文和译文行数检查语义未变化。

## 剩余风险

- 旧 `build_plugin_source_scan` 公共导出仍保留，后续需要集中审计可删除范围和仍需保留的测试夹具。
- `scan_plugin_source_files_text_strict` 仍作为翻译源严格扫描入口存在，后续需要明确保留原因或改成薄适配。
- `_collect_plugin_source_write_back_probe_reasons_from_scan` 仍依赖候选 selector；这适用于调用方传入的翻译源 `PluginSourceScan`，不在本批改动。

## 下一批入口

- 建议下一批：旧 `build_plugin_source_scan` 公共导出与翻译源 strict scan 保留边界审计。
- 建议边界：优先审计 `app/plugin_source_text/scanner.py::build_plugin_source_scan`、`scan_plugin_source_files_text_strict` 的剩余生产调用方和测试夹具调用方，明确哪些入口可删除、哪些只能作为测试或内部薄适配保留。
- 理由：6M 已收束写回探针 fallback；剩余插件源码旧扫描主要来自公共导出和翻译源 strict scan 本体。
