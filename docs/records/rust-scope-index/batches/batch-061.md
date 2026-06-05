# Rust Scope/Index Engine 批次 61 记录

## 本批范围

- 批次：6AD，旧 scanner 历史记录残留收尾审计。
- 覆盖范围：`tests/test_scan_budget.py`、`tests/test_plugin_source_text.py`、`docs/records/rust-scope-index/batches/batch-046.md` 到 `docs/records/rust-scope-index/batches/batch-061.md`、计划表和本记录。
- 成功状态：`_build_legacy_plugin_source_scan`、`_scan_legacy_plugin_source_files_text_strict` 和 `build_plugin_source_scan(` 的剩余出现被固定为历史记录和保护测试；`app/`、共享 fixture、默认路径测试和公开契约不再出现这些旧入口。
- 明确非范围：本批不改生产代码、CLI、数据库 schema、Rust 原生代码或发布流程；历史批次记录保留旧名称作为迁移过程证据。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch61_legacy_scanner_names_are_confined_to_history_and_protections`：
  - 扫描 `app/`、`tests/` 和 `docs/` 中的 `.py`、`.md` 文件。
  - 断言旧名称只出现在 `tests/test_plugin_source_text.py`、`tests/test_scan_budget.py` 和 `docs/records/rust-scope-index/batches/batch-046.md` 到 `docs/records/rust-scope-index/batches/batch-061.md`。
  - 断言 `app/` 下没有旧名称残留。
  - 断言 `tests/test_plugin_source_text.py` 中旧名称只用于 `test_legacy_plugin_source_scan_helpers_are_removed_from_scanner` 保护测试。
- 新增 `tests/test_scan_budget.py::test_batch61_legacy_history_residual_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本记录覆盖历史记录、保护测试和旧名称边界。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `tests/test_scan_budget.py`：
  - 新增 `_paths_containing_any_text` 辅助函数，用于统一审计 `.py` 和 `.md` 文件中的旧名称分布。
  - 新增 batch61 历史残留保护和记录保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6AD 批次进度行。
- 新增 `docs/records/rust-scope-index/batches/batch-061.md`：
  - 记录旧名称剩余分布、验证结果、剩余风险和下一批入口。

## 旧路径收束

- 可执行旧入口已清零：
  - `app/` 中没有 `_build_legacy_plugin_source_scan`。
  - `app/` 中没有 `_scan_legacy_plugin_source_files_text_strict`。
  - `app/` 中没有 `build_plugin_source_scan(`。
- 测试侧旧入口已清零：
  - 普通测试不再导入或 monkeypatch `app.plugin_source_text.scanner._build_legacy_plugin_source_scan`。
  - 普通测试不再导入或 monkeypatch `app.plugin_source_text.scanner._scan_legacy_plugin_source_files_text_strict`。
  - `build_plugin_source_scan(` direct call 不再出现。
- 保留出现：
  - 历史记录保留旧名称，用于说明旧路径如何被分批私有化、迁移、删除和审计。
  - `tests/test_plugin_source_text.py` 保留旧名称字符串，用于确认旧 helper 已从 scanner 模块删除。
  - `tests/test_scan_budget.py` 保留旧名称字符串，用于静态保护和记录保护。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构、Rust API 和发布流程不变。
- 本批只新增历史残留审计测试和验收记录，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O、SQLite 查询或 Rust 调用。
- 旧名称残留审计是静态文件扫描，只运行在测试中。
- `tests/test_scan_budget.py::test_batch61_legacy_scanner_names_are_confined_to_history_and_protections` 防止旧 scanner 名称重新进入生产代码或普通测试。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch61_legacy_scanner_names_are_confined_to_history_and_protections tests/test_scan_budget.py::test_batch61_legacy_history_residual_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：静态分布缺少 `docs/records/rust-scope-index/batches/batch-061.md`；`docs/records/rust-scope-index/batches/batch-061.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch61_legacy_scanner_names_are_confined_to_history_and_protections tests/test_scan_budget.py::test_batch61_legacy_history_residual_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 相关 scan_budget 保护：`uv run pytest tests/test_scan_budget.py::test_batch60_legacy_plugin_source_private_helpers_are_removed tests/test_scan_budget.py::test_batch60_legacy_private_helper_deletion_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch61_legacy_scanner_names_are_confined_to_history_and_protections tests/test_scan_budget.py::test_batch61_legacy_history_residual_record_exists_and_tracks_contract`
  - 结果：4 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors, 0 warnings, 0 notes。
- 文档敏感路径和占位文案搜索：
  - 结果：无匹配。
- 旧入口边界搜索：`rg -n "app\\.plugin_source_text\\.scanner\\._build_legacy_plugin_source_scan|app\\.plugin_source_text\\.scanner\\._scan_legacy_plugin_source_files_text_strict|from app\\.plugin_source_text\\.scanner import _|build_plugin_source_scan\\(" app tests -g "*.py" -g "!tests/test_scan_budget.py"`
  - 结果：无匹配。
- 空白检查：`git diff --check`
  - 结果：退出码 0；仅提示工作区现有 LF/CRLF 转换警告。
- 全量测试：
  - 本批按 rust-scope-index-engine 临时验证策略未跑全量 `uv run pytest`。
  - 原因：本批是普通编号批次，只修改测试和开发记录，未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程；本批不属于每 5 个编号批次收束点。

## 审查处理

- 本批审查重点是旧名称是否还可能作为可执行入口被误用。
- 当前分布显示旧名称只用于历史记录和保护测试。
- 本批未修改生产运行路径，也未改变 CLI、数据库 schema、Rust 原生代码或发布流程。

## 剩余风险

- 历史批次记录中仍会保留旧名称；这是迁移审计证据，不是当前实现契约。
- 当前工作树混有前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：插件源码支线收束回归审计。
- 建议边界：围绕插件源码支线已迁到 `build_native_plugin_source_scan` 和 `scan_plugin_source_runtime_files_text_strict` 的事实，审计 scan_budget、记录和关键目标测试是否足以证明旧 Python scanner 主路径不再回流。
- 理由：旧 scanner 名称已经从可执行路径清零，下一步应从名称残留转向插件源码支线整体收束质量。
