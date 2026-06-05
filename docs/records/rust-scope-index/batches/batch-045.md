# Rust Scope/Index Engine 批次 45 记录

## 本批范围

- 批次：6N，旧插件源码扫描公共导出与 strict scan 保留边界审计。
- 覆盖范围：`app/plugin_source_text/__init__.py` 的包根导出、`app/plugin_source_text/scanner.py` 的星号导出列表，以及测试夹具对旧扫描器的引用路径。
- 成功状态：旧 `build_plugin_source_scan` 和旧翻译源 `scan_plugin_source_files_text_strict` 不再从 `app.plugin_source_text` 包根公开导出，也不再出现在 `scanner.py::__all__`；确需造旧 `PluginSourceScan` 测试夹具时，必须显式从 `app.plugin_source_text.scanner` 导入。
- 明确非范围：本批不删除 `scanner.py::build_plugin_source_scan` 和 `scanner.py::scan_plugin_source_files_text_strict` 函数本体；它们暂作为内部兼容入口和测试夹具构造入口保留。

## 保护网

- 新增 `tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_public_exports`：
  - 断言 `app.plugin_source_text.__all__` 不包含 `build_plugin_source_scan` 和 `scan_plugin_source_files_text_strict`。
  - 断言包根对象没有这两个旧扫描属性。
  - 断言 `app.plugin_source_text.scanner.__all__` 不再星号导出这两个旧扫描名称。
  - 同时断言 scanner 模块仍显式保留这两个函数，避免本批误删内部兼容入口。
- 新增 `tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_imported_from_package_root`：
  - 用 Python AST 遍历 `app/` 和 `tests/` 下所有 `.py` 文件。
  - 断言没有任何单行或多行 `from app.plugin_source_text import (...)` 继续导入旧扫描器。
- 新增 `tests/test_scan_budget.py::test_batch45_legacy_plugin_source_scan_export_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批导出边界、旧扫描名称、runtime 字面量扫描名称和保护测试写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `app/plugin_source_text/__init__.py`：
  - 移除包根导入和 `__all__` 中的 `build_plugin_source_scan`。
  - 移除包根导入和 `__all__` 中的 `scan_plugin_source_files_text_strict`。
  - 保留 `build_native_plugin_source_scan` 和 `scan_plugin_source_runtime_files_text_strict` 等当前生产默认路径需要的入口。
- 更新 `app/plugin_source_text/scanner.py`：
  - 从 `__all__` 移除 `build_plugin_source_scan` 和 `scan_plugin_source_files_text_strict`。
  - 保留两个函数本体，供显式内部引用和测试夹具继续使用。
- 更新测试夹具导入：
  - `tests/test_plugin_source_text.py`
  - `tests/agent_toolkit_contract_fixtures.py`
  - `tests/rmmz_writeback_contract_fixtures.py`
  - `tests/test_rule_import_transactions.py`
  - 上述文件如需旧扫描器，改为显式从 `app.plugin_source_text.scanner` 导入。

## 旧路径收束

- 已收束路径：
  - `from app.plugin_source_text import build_plugin_source_scan` 不再是可用公共入口。
  - `from app.plugin_source_text import scan_plugin_source_files_text_strict` 不再是可用公共入口。
  - `from app.plugin_source_text.scanner import *` 不再带出这两个旧扫描名称。
- 保留路径：
  - `app/plugin_source_text/scanner.py::build_plugin_source_scan` 仍保留，作为旧 `PluginSourceScan` 构造兼容入口。
  - `app/plugin_source_text/scanner.py::scan_plugin_source_files_text_strict` 仍保留，作为旧翻译源严格扫描内部 helper。
  - `scan_plugin_source_runtime_files_text_strict` 仍公开导出，供运行期字面量扫描、写回探针 fallback 和缓存重扫路径使用。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 包根 `app.plugin_source_text` 属于内部 Python 模块边界；本批收束其旧扫描器导出，不改变用户可见命令行为。
- 测试夹具继续能显式构造旧 `PluginSourceScan`，但不能通过包根导入制造第二个公共事实来源。

## 性能证据

- 生产 app 代码中没有包根旧 `build_plugin_source_scan` 或包根旧 `scan_plugin_source_files_text_strict` 调用方。
- 移除公共导出后，默认生产路径更难回退到旧 Python 翻译源扫描；新增测试固定这一边界。
- 本批不新增扫描或 I/O；运行成本变化来自导入边界收束，性能收益是防止后续误用旧扫描器。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_public_exports`
  - 结果：1 failed。
  - 失败原因：`app.plugin_source_text.__all__` 仍包含 `build_plugin_source_scan` 和 `scan_plugin_source_files_text_strict`。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_public_exports`
  - 结果：1 passed。
- 文档保护 RED：`uv run pytest tests/test_scan_budget.py::test_batch45_legacy_plugin_source_scan_export_record_exists_and_tracks_contract`
  - 结果：1 failed。
  - 失败原因：`docs/records/rust-scope-index/batches/batch-045.md` 尚不存在。
- 文档保护 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch45_legacy_plugin_source_scan_export_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 静态导入审计：`rg -n "from app\\.plugin_source_text import .*build_plugin_source_scan|from app\\.plugin_source_text import .*scan_plugin_source_files_text_strict" app tests -g "*.py"`
  - 结果：退出码 1，无匹配，表示 app 和 tests 中没有继续从包根导入旧扫描入口。
- 审查硬化：`uv run pytest tests/test_plugin_source_text.py::test_legacy_plugin_source_scan_helpers_are_not_imported_from_package_root`
  - 结果：1 passed。
  - 覆盖原因：补足普通 `rg` 对多行 import 块证明力不足的问题。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py tests/test_rule_import_transactions.py`
  - 结果：56 passed。
- 相邻夹具回归：`uv run pytest tests/test_agent_toolkit_workspace.py tests/test_agent_toolkit_feedback.py tests/test_rmmz_write_plan.py`
  - 结果：64 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：805 passed in 267.74s。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- Rust 门禁：本批未修改 Rust 源码或构建流程，因此未执行 `cargo fmt`、`cargo clippy` 和 `cargo test`。

## 审查处理

- 只读子代理审查确认：包根和 `scanner.__all__` 已不再暴露旧扫描入口，生产 `app` 代码未发现从包根导入旧名，测试夹具已显式从 `app.plugin_source_text.scanner` 导入旧扫描器。
- 只读子代理指出：记录里的普通 `rg` 静态审计对多行 import 块证明力不足。本批已新增 AST 级测试 `test_legacy_plugin_source_scan_helpers_are_not_imported_from_package_root`，固定单行和多行导入边界。

## 剩余风险

- `scanner.py::build_plugin_source_scan` 和 `scanner.py::scan_plugin_source_files_text_strict` 函数本体仍存在；它们还没有被重命名为私有函数，也没有完全替换为 Rust-derived 测试夹具。
- 多个测试仍用旧扫描器构造候选 selector，用于对比旧规则链路和写回语义；后续若删除本体，需要先迁移这些夹具。
- 本批没有改变 runtime cache、active runtime audit、diagnose-active-runtime 或 write probe 的行为。

## 下一批入口

- 建议下一批：旧 scanner 主扫描本体私有化或测试夹具替换评估。
- 建议边界：审计 `tests/` 中显式从 `app.plugin_source_text.scanner` 导入旧扫描器的用例，区分必须验证旧兼容语义的测试和可以改用 `build_native_plugin_source_scan` 的测试；先迁移一组可验证夹具，再决定是否把旧函数重命名为私有入口。
- 理由：6N 已去掉公共导出；剩余旧路径主要是函数本体和测试夹具引用。
