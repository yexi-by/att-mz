# Rust Scope/Index Engine 批次 46 记录

## 本批范围

- 批次：6O，旧 scanner 主扫描本体私有化。
- 覆盖范围：`app/plugin_source_text/scanner.py` 中旧 `PluginSourceScan` 构造入口和旧翻译源 strict scan helper，以及测试夹具对这两个旧入口的显式引用。
- 成功状态：`scanner.py` 不再存在无下划线的 `build_plugin_source_scan` 和 `scan_plugin_source_files_text_strict` 函数本体；旧兼容入口改为 `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict`。
- 明确非范围：本批不把全部测试夹具迁到 `build_native_plugin_source_scan`，也不删除旧兼容实现；后续批次继续评估哪些夹具可替换为 Rust-derived scan。

## 保护网

- 新增 `tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_private_in_scanner`：
  - 断言 scanner 模块没有 `build_plugin_source_scan` 和 `scan_plugin_source_files_text_strict` 属性。
  - 断言 scanner 模块保留 `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 属性。
- 新增 `tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_imported_by_public_scanner_names`：
  - 用 Python AST 遍历 `app/` 和 `tests/` 下所有 `.py` 文件。
  - 断言没有任何单行或多行 `from app.plugin_source_text.scanner import (...)` 继续导入无下划线旧扫描器名称。
- 调整 `tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_public_exports`：
  - 保留包根公共导出边界。
  - 同步断言 scanner 模块也不再暴露无下划线旧函数属性。
- 新增 `tests/test_scan_budget.py::test_batch46_legacy_plugin_source_scanner_private_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批私有函数名、旧函数名、保护测试和保留边界写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `app/plugin_source_text/scanner.py`：
  - `build_plugin_source_scan` 改名为 `_build_legacy_plugin_source_scan`。
  - `scan_plugin_source_files_text_strict` 改名为 `_scan_legacy_plugin_source_files_text_strict`。
  - `_build_legacy_plugin_source_scan` 内部调用私有 strict helper。
- 更新测试夹具和保护测试：
  - `tests/test_plugin_source_text.py`
  - `tests/agent_toolkit_contract_fixtures.py`
  - `tests/rmmz_writeback_contract_fixtures.py`
  - `tests/test_rule_import_transactions.py`
  - 需要旧扫描器造候选 selector 的测试继续用本地别名 `build_plugin_source_scan`，但导入来源改为私有兼容函数。
- 更新旧路径禁止类 monkeypatch：
  - 原先指向 `app.plugin_source_text.scanner.build_plugin_source_scan` 的禁止钩子改为指向 `_build_legacy_plugin_source_scan`。
  - 写回探针 fallback 的旧 strict scan 禁止钩子改为指向 `_scan_legacy_plugin_source_files_text_strict`。

## 旧路径收束

- 已收束路径：
  - `app.plugin_source_text.scanner.build_plugin_source_scan` 不再存在。
  - `app.plugin_source_text.scanner.scan_plugin_source_files_text_strict` 不再存在。
  - `app/` 和 `tests/` 不再从 scanner 模块导入无下划线旧扫描器名称。
- 保留路径：
  - `_build_legacy_plugin_source_scan` 仍保留，用于少量测试夹具构造旧 `PluginSourceScan` 对象。
  - `_scan_legacy_plugin_source_files_text_strict` 仍保留，用于旧兼容扫描对象构造和对照测试。
  - `scan_plugin_source_runtime_files_text_strict` 仍是运行期字面量扫描的公开入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- `app.plugin_source_text.scanner` 是内部模块边界；本批私有化旧函数本体，不改变用户可见命令行为。
- 测试夹具继续可以构造旧 `PluginSourceScan`，但名称明确标记为 legacy/private，避免被生产默认路径当作可用公共入口。

## 性能证据

- 本批不新增扫描、I/O 或 Rust 调用。
- 私有化旧入口后，未来生产代码若误用旧 Python 翻译源扫描，需要显式引用带 `_legacy` 的私有函数；新增 AST 测试会阻止重新通过无下划线旧名导入。
- 相邻回归验证显示插件源码文本、规则导入和工作区复用路径在私有化后仍可运行。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_private_in_scanner`
  - 结果：1 failed。
  - 失败原因：`app.plugin_source_text.scanner` 仍存在 `build_plugin_source_scan` 属性。
- RED：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_imported_by_public_scanner_names`
  - 结果：1 failed。
  - 失败原因：测试夹具仍从 `app.plugin_source_text.scanner` 导入无下划线旧扫描器名称。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_private_in_scanner tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_imported_by_public_scanner_names tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_public_exports`
  - 结果：3 passed。
- 相邻回归初次验证：`uv run pytest tests/test_plugin_source_text.py tests/test_rule_import_transactions.py tests/test_agent_toolkit_workspace.py::test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`
  - 初次结果：1 failed、59 passed。
  - 失败原因：`test_plugin_source_write_probe_uses_batch_preview` 的 monkeypatch 仍指向已私有化的 `scan_plugin_source_files_text_strict` 旧属性。
  - 修复后结果：60 passed。
- 文档保护 RED：`uv run pytest tests/test_scan_budget.py::test_batch46_legacy_plugin_source_scanner_private_record_exists_and_tracks_contract`
  - 结果：1 failed。
  - 失败原因：`docs/records/rust-scope-index/batches/batch-046.md` 尚不存在。
- 文档保护 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch46_legacy_plugin_source_scanner_private_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 类型检查初次验证：`uv run basedpyright`
  - 初次结果：0 errors、6 warnings、0 notes。
  - 失败原因：测试夹具显式导入私有 legacy helper 触发 `reportPrivateUsage`，scanner 内私有 legacy helper 触发 `reportUnusedFunction`。
  - 修复方式：在相关测试夹具中显式声明 `# pyright: reportPrivateUsage=false`，并在 scanner 内用 `_LEGACY_PLUGIN_SOURCE_SCAN_HELPERS` 标记 legacy helper 是有意保留的兼容入口。
  - 修复后结果：0 errors、0 warnings、0 notes。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py tests/test_rule_import_transactions.py tests/test_agent_toolkit_workspace.py tests/test_stage0_canaries.py tests/test_scan_budget.py::test_batch46_legacy_plugin_source_scanner_private_record_exists_and_tracks_contract`
  - 结果：84 passed。
- 全量 Python 测试初次验证：`uv run pytest`
  - 初次结果：1 failed、807 passed。
  - 失败原因：`tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files` 的 monkeypatch 仍指向已私有化的 `scan_plugin_source_files_text_strict` 旧属性。
  - 修复后相邻结果：`uv run pytest tests/test_plugin_source_text.py tests/test_rule_import_transactions.py tests/test_agent_toolkit_workspace.py tests/test_stage0_canaries.py tests/test_agent_toolkit_rule_import.py::test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files tests/test_scan_budget.py::test_batch46_legacy_plugin_source_scanner_private_record_exists_and_tracks_contract` 为 85 passed。
- 精确旧名搜索：`rg -n "def build_plugin_source_scan\\(|def scan_plugin_source_files_text_strict\\(|app\\.plugin_source_text\\.scanner\\.build_plugin_source_scan|app\\.plugin_source_text\\.scanner\\.scan_plugin_source_files_text_strict|from app\\.plugin_source_text\\.scanner import build_plugin_source_scan|from app\\.plugin_source_text\\.scanner import scan_plugin_source_files_text_strict" app tests -g "*.py"`
  - 结果：退出码 1，无匹配。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 全量 Python 测试最终验证：`uv run pytest`
  - 结果：808 passed in 262.52s。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- Rust 门禁：本批未修改 Rust 源码或构建流程，因此未执行 `cargo fmt`、`cargo clippy` 和 `cargo test`。

## 审查处理

- 只读子代理审查确认：旧本体已私有化为 `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict`，旧无下划线名未出现在 `scanner.__all__`，生产 `app/` 目录未检索到旧名。
- 只读子代理审查确认：`_LEGACY_PLUGIN_SOURCE_SCAN_HELPERS` 只是私有 tuple 标记，未公共导出；`reportPrivateUsage=false` 只出现在测试夹具边界，没有掩盖生产 private usage。
- 子代理未发现阻断问题。

## 剩余风险

- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在；它们只是私有化，尚未删除。
- 多个测试仍通过私有兼容入口构造旧 selector 和 `PluginSourceScan`，下一批需要继续筛出可迁移到 `build_native_plugin_source_scan` 的夹具。
- 本批没有改变 active runtime cache、diagnose-active-runtime、write probe runtime 字面量扫描或 Rust native adapter。

## 下一批入口

- 建议下一批：旧 scanner 测试夹具 Rust-derived 替换评估。
- 建议边界：优先审计 `tests/test_plugin_source_text.py` 内只为获得 selector 或 file_hash 而调用 `_build_legacy_plugin_source_scan` 的用例，选择一组替换为 `build_native_plugin_source_scan`，并用测试固定替换后仍不影响规则导入、写回和 stale rule 行为。
- 理由：6O 已完成旧 scanner 本体私有化；剩余旧路径集中在测试夹具使用私有兼容入口。
