# Rust Scope/Index Engine 批次 43 记录

## 本批范围

- 批次：6L，`diagnose-active-runtime` 写回映射 source scan 接入 runtime 字面量扫描。
- 覆盖范围：`app/agent_toolkit/services/quality.py::_build_plugin_source_write_map_source_scan_cache`、`_plugin_source_write_map_source_matches` 和 `diagnose-active-runtime` 反推当前运行问题到翻译源插件源码 selector 的路径。
- 成功状态：诊断反推 source selector 时不再调用翻译源 `scan_plugin_source_files_text_strict`；改用 `scan_plugin_source_runtime_files_text_strict` 批量扫描相关翻译源插件文件的全部字符串字面量，并用 selector 对应 literal 文本核对 `source_text_hash`。
- 明确非范围：`app/text_scope/write_probe.py` 的写回探针 fallback、旧 `build_plugin_source_scan` 公共导出、翻译源 `PluginSourceScan` 候选事实入口仍留到后续批次。

## 保护网

- 调整 `tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans`：
  - 构造两个插件源码运行问题和对应 `PluginSourceRuntimeWriteMapRecord`。
  - monkeypatch 禁止 `app.agent_toolkit.services.quality.scan_plugin_source_files_text_strict`。
  - monkeypatch 计数 `scan_plugin_source_runtime_files_text_strict`，并调用真实 runtime 字面量扫描 helper。
  - 断言 `diagnose-active-runtime` 只批量扫描 `BadSourceA.js` 和 `BadSourceB.js` 一次，并仍输出 2 条 `mapped_translate` 诊断。
- 新增 `tests/test_scan_budget.py::test_batch43_diagnose_active_runtime_write_map_source_scan_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批旧路径、runtime helper、诊断命令、保护测试和新增 source 文本匹配 helper 都写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `app/agent_toolkit/services/quality.py`：
  - `_build_plugin_source_write_map_source_scan_cache` 改用 `scan_plugin_source_runtime_files_text_strict`。
  - `_build_active_runtime_diagnosis_items` 不再把 `TextRules` 传给 source scan cache，因为诊断只需要 selector 对应的字面量文本，不需要翻译候选过滤。
  - `_plugin_source_write_map_source_matches` 改为通过 `_plugin_source_write_map_source_text` 读取 selector 对应文本。
  - `_plugin_source_write_map_source_text` 先兼容已有候选索引，再从 `PluginSourceFileTextScan.literals` 查找 selector；这样旧候选 scan 和新 runtime literal scan 都能复用同一匹配逻辑。

## 旧路径收束

- 已收束路径：
  - `diagnose-active-runtime` 反推 write map source selector 时不再调用翻译源 `scan_plugin_source_files_text_strict`。
  - `_build_plugin_source_write_map_source_scan_cache` 不再构造翻译候选索引，只扫描诊断需要的源文件字面量。
  - source text hash 校验仍保留 selector 和 source file hash 双重约束。
- 保留路径：
  - `app/text_scope/write_probe.py` 仍有 `scan_plugin_source_files_text_strict` fallback。
  - 旧 `build_plugin_source_scan` 公共导出仍保留。
  - 翻译源候选事实仍由 6J 的 Rust-derived `build_native_plugin_source_scan` 负责，不由本批 runtime literal scan 取代。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- `diagnose-active-runtime` 输出的 `source_hash_matches`、`source_file_hash_matches`、`mapped_translate_count` 和 `mapped_excluded_count` 语义不变。
- 新增 `_plugin_source_write_map_source_text` 是内部 helper，不改变公开命令协议。

## 性能证据

- 诊断只扫描本次问题实际引用的 source file names。
- 多个 write map 记录引用多个源文件时，仍通过一次 `scan_plugin_source_runtime_files_text_strict` 批量进入 Rust AST。
- 诊断 source scan 不再构造 `PluginSourceCandidate` 和最终翻译源规则过滤结果，减少不必要对象构造。

## 验证结果

- RED：`uv run pytest tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans`
  - 结果：1 failed。
  - 失败原因：`_build_plugin_source_write_map_source_scan_cache` 仍调用 `scan_plugin_source_files_text_strict`。
- GREEN：`uv run pytest tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans`
  - 结果：1 passed。
- 文档保护 RED：`uv run pytest tests/test_scan_budget.py::test_batch43_diagnose_active_runtime_write_map_source_scan_record_exists_and_tracks_contract`
  - 结果：1 failed。
  - 失败原因：`docs/records/rust-scope-index/batches/batch-043.md` 尚不存在。
- 文档保护 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch43_diagnose_active_runtime_write_map_source_scan_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 相邻回归：`uv run pytest tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache tests/test_agent_toolkit_feedback.py::test_diagnose_active_runtime_batches_translation_source_scans tests/test_scan_budget.py::test_batch43_diagnose_active_runtime_write_map_source_scan_record_exists_and_tracks_contract`
  - 结果：3 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：800 passed。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- Rust 门禁：本批未修改 Rust 源码或构建流程，因此未执行 `cargo fmt`、`cargo clippy` 和 `cargo test`；运行时 Rust AST adapter 相关行为已由相邻 Python 测试覆盖。

## 审查处理

- 本批审计确认：write map source hash 校验不需要翻译源候选对象，只需要 selector 对应的可见文本。
- `_plugin_source_write_map_source_text` 保留候选索引兼容分支，避免未来调用方传入候选 scan 时行为变化。
- 只读子代理审查指出：原测试只断言 `mapped_translate_count`，没有断言 `source_hash_matches` 和 `source_file_hash_matches`。本批已补强 `test_diagnose_active_runtime_batches_translation_source_scans`，直接检查两条 mapped 诊断的 source hash 和 source file hash 均匹配。
- 只读子代理审查指出：记录缺少文档保护 GREEN 和最终通过结果。本批已补充验证记录，并在审查修复后重新执行关键测试和最终门禁。

## 剩余风险

- `app/text_scope/write_probe.py` 的严格 AST fallback 仍保留，后续需要迁移或删除。
- 旧 `build_plugin_source_scan` 公共导出仍保留；删除需要等写回探针 fallback 和公共 API 调用方全部收束。
- `scan_plugin_source_files_text_strict` 仍作为翻译源严格扫描入口存在，后续需要继续明确保留原因或改成薄适配。

## 下一批入口

- 建议下一批：写回探针 fallback 与旧 `build_plugin_source_scan` 公共导出审计。
- 建议边界：优先处理 `app/text_scope/write_probe.py`、`collect_write_back_probe_reasons` 调用方，以及 `app/plugin_source_text/scanner.py::build_plugin_source_scan` 的剩余公共导出。
- 理由：6L 已收束 `diagnose-active-runtime` 的 write map source scan；剩余插件源码旧扫描主要来自写回探针 fallback 和公共 API 旧入口。
