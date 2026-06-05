# Rust Scope/Index Engine 批次 56 记录

## 本批范围

- 批次：6Y，旧 scanner repo-wide 残留入口审计。
- 覆盖范围：`app/plugin_source_text/scanner.py`、`tests/test_plugin_source_text.py`、`tests/test_agent_toolkit_workspace.py`、`tests/agent_toolkit_contract_fixtures.py`、`tests/rmmz_writeback_contract_fixtures.py`、`tests/test_scan_budget.py` 和历史批次记录。
- 成功状态：repo-wide 剩余 `_build_legacy_plugin_source_scan`、`_scan_legacy_plugin_source_files_text_strict`、`build_plugin_source_scan` 别名和旧 scanner 禁止钩子被分成生产私有定义、旧 scanner 语义测试、禁止回退 monkeypatch、共享 fixture 导出和历史批次记录五类。
- 明确非范围：本批不删除 `_build_legacy_plugin_source_scan` 或 `_scan_legacy_plugin_source_files_text_strict`，不迁移 `tests/test_plugin_source_text.py` 内剩余旧语义测试，不删除共享 fixture 的 legacy 导出，不改生产代码、CLI、数据库 schema、Rust 原生代码或发布流程。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified`：
  - 断言生产 `app/` 目录内 legacy 私有 helper 只出现在 `app/plugin_source_text/scanner.py`。
  - 断言 `scanner.py` 保留 `_build_legacy_plugin_source_scan`、`_scan_legacy_plugin_source_files_text_strict` 和 `_LEGACY_PLUGIN_SOURCE_SCAN_HELPERS` 私有边界。
  - 断言 `_build_legacy_plugin_source_scan as build_plugin_source_scan` 只由 `tests/test_plugin_source_text.py`、`tests/agent_toolkit_contract_fixtures.py` 和 `tests/rmmz_writeback_contract_fixtures.py` 导入。
  - 断言 `_scan_legacy_plugin_source_files_text_strict as real_scan_plugin_source_files_text_strict` 只由 `tests/agent_toolkit_contract_fixtures.py` 导入。
  - 断言测试代码中直接调用 `build_plugin_source_scan(` 的路径仅剩 `tests/test_plugin_source_text.py`，且函数级调用清单保持 batch53 旧语义边界。
  - 断言 `_build_legacy_plugin_source_scan` 的 dotted monkeypatch 路径仅剩 `tests/test_plugin_source_text.py` 和 `tests/test_agent_toolkit_workspace.py`。
- 新增 `tests/test_scan_budget.py::test_batch56_legacy_scanner_repo_wide_residual_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本记录覆盖生产私有定义、旧 scanner 语义测试、禁止回退 monkeypatch、共享 fixture 导出和历史批次记录五类。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。

## 实现说明

- 更新 `tests/test_scan_budget.py`：
  - 新增基于 AST 的 import alias 查询辅助函数。
  - 新增基于 AST 的命名调用路径查询辅助函数。
  - 新增文本包含路径查询辅助函数。
  - 新增 batch56 repo-wide 残留分类保护和记录保护。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6Y 批次进度行。
- 新增本记录：
  - 固定旧 scanner 残留分类、验证结果、剩余风险和下一批入口。

## 旧路径收束

| 分类 | 当前路径 | 处理结论 |
| --- | --- | --- |
| 生产私有定义 | `app/plugin_source_text/scanner.py` | 仅保留私有 helper 定义、私有 strict helper 和 `_LEGACY_PLUGIN_SOURCE_SCAN_HELPERS` 内部元组；生产 `app/` 目录其他 Python 文件不得引用这两个 legacy 私有名。 |
| 旧 scanner 语义测试 | `tests/test_plugin_source_text.py` | 只保留 batch53 固定的 8 个旧语义测试直接调用 `build_plugin_source_scan(`，用于对照旧扫描行为、缓存和历史 AST 语义。 |
| 禁止回退 monkeypatch | `tests/test_plugin_source_text.py`、`tests/test_agent_toolkit_workspace.py` | 仅作为“不得回到旧 scanner”的动态保护钩子保留。 |
| 共享 fixture 导出 | `tests/agent_toolkit_contract_fixtures.py`、`tests/rmmz_writeback_contract_fixtures.py` | 暂时保留 `build_plugin_source_scan` 导出，避免切断尚未完全隔离的旧语义测试和共享夹具边界。 |
| 历史批次记录 | `docs/records/rust-scope-index/batches/batch-045.md` 至 `docs/records/rust-scope-index/batches/batch-056.md` 等记录 | 作为历史验收证据保留，不作为当前翻译流程 Agent 契约或生产入口。 |

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构、Rust API 和发布流程不变。
- 本批只新增测试保护和验收记录，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O、SQLite 查询或 Rust 调用。
- 生产 `app/` 目录内 legacy 私有 helper 引用只在 `app/plugin_source_text/scanner.py`。
- 除 `tests/test_scan_budget.py` 自身保护文本外，测试代码中直接调用 `build_plugin_source_scan(` 的路径仅剩 `tests/test_plugin_source_text.py`。
- 旧 scanner 残留被分类后，后续批次可以优先处理共享 fixture legacy 导出，不需要重新全仓猜测残留语义。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch56_legacy_scanner_repo_wide_residual_record_exists_and_tracks_contract`
  - 结果：1 failed、1 passed。
  - 失败原因：`docs/records/rust-scope-index/batches/batch-056.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch56_legacy_plugin_source_scan_residuals_are_classified tests/test_scan_budget.py::test_batch56_legacy_scanner_repo_wide_residual_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors, 0 warnings, 0 notes。
- 文档敏感路径和占位文案搜索：
  - 结果：无匹配。
- 空白检查：`git diff --check`
  - 结果：退出码 0；仅提示工作区现有 LF/CRLF 转换警告。
- 全量测试：
  - 本批按 rust-scope-index-engine 临时验证策略未跑全量 `uv run pytest`。
  - 原因：本批是普通编号批次，未修改生产代码、跨模块契约、数据库 schema、CLI 外部契约、Rust 原生代码或发布流程；上一批 batch55 已执行全量 pytest，本批不属于每 5 个编号批次收束点。

## 审查处理

- 本批审查重点是静态分类是否遗漏 repo-wide 残留入口、记录是否误把历史文档当作当前生产入口、是否引入生产代码改动。
- 本批目标保护测试覆盖了 repo-wide 分类边界：生产私有定义、旧 scanner 语义测试、禁止回退 monkeypatch、共享 fixture 导出和历史批次记录。
- 本批未新增生产运行路径，也未改变 CLI、数据库 schema、Rust 原生代码或发布流程。

## 剩余风险

- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在于 `app/plugin_source_text/scanner.py`。
- `tests/test_plugin_source_text.py` 仍有 8 个旧 scanner 语义测试直接调用 `build_plugin_source_scan(`。
- `tests/agent_toolkit_contract_fixtures.py` 和 `tests/rmmz_writeback_contract_fixtures.py` 仍导出 `build_plugin_source_scan`。
- 当前工作树混有前序未提交改动，本批不回滚、不归并、不重新解释这些改动；准备提交或合并前仍需建立清晰提交边界。

## 下一批入口

- 建议下一批：共享 fixture legacy 导出删除或隔离评估。
- 建议边界：先审计 `tests/agent_toolkit_contract_fixtures.py` 与 `tests/rmmz_writeback_contract_fixtures.py` 中 `build_plugin_source_scan` 导出的实际消费者，再决定删除导出、改成显式私有旧语义 fixture，或把剩余消费者继续迁移到 `build_native_plugin_source_scan`。
- 理由：repo-wide 分类已固定，下一步应先减少共享 fixture 暴露面，再处理 `tests/test_plugin_source_text.py` 内真正需要保留的旧语义对照。
