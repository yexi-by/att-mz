# Rust Scope/Index Engine 批次 53 记录

## 本批范围

- 批次：6V，剩余旧 scanner 残留夹具第七组 Rust-derived 替换与边界保护。
- 覆盖范围：`tests/test_plugin_source_text.py` 内剩余直接调用 `build_plugin_source_scan` 的测试函数。
- 成功状态：将 `test_plugin_source_extraction_scans_each_file_once` 的 selector/file_hash 预扫描改为 `build_native_plugin_source_scan`；用扫描预算测试固定剩余 8 个测试函数和 9 次 legacy 调用。
- 明确非范围：本批不迁移这些测试，不删除 `_build_legacy_plugin_source_scan`，不改生产代码，不修改 CLI、数据库 schema、Rust 原生代码或外部契约。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional`：
  - 读取 `tests/test_plugin_source_text.py`。
  - 用 Python AST 统计每个测试函数内对 `build_plugin_source_scan` 的真实调用次数。
  - 断言剩余 legacy 调用精确等于本批列出的 8 个测试函数和 9 次调用。
- 新增 `tests/test_scan_budget.py::test_batch53_remaining_legacy_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 native 入口、legacy 私有入口、剩余 legacy 测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 同步补强 batch52 记录保护：
  - `test_batch52_agent_toolkit_import_scope_fixture_record_exists_and_tracks_contract` 增加占位补全类拦截词，防止记录再次出现执行后未替换的临时说明。

## 实现说明

- 更新 `tests/test_scan_budget.py`：
  - 新增 `_test_function_call_counts_for_name`，用于按测试函数统计指定调用名出现次数。
  - 新增 6V 剩余 legacy 边界保护和批次记录保护。
  - 补强 6U/batch52 记录保护的占位文案拦截。
  - 记录边界同时引用 `build_native_plugin_source_scan`，用于说明这些剩余调用不同于此前已迁移的 Rust-derived 测试夹具。
- 更新 `tests/test_plugin_source_text.py`：
  - 将 `test_plugin_source_extraction_scans_each_file_once` 的预扫描改为 `build_native_plugin_source_scan`。
  - 保持该测试的核心断言不变，继续验证源码提取阶段调用 native candidate scan 一次且不回旧 AST 扫描。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6V 批次进度行。
- 新增 `docs/records/rust-scope-index/batches/batch-053.md`：
  - 记录剩余 legacy 调用的分类边界、验证结果和下一批入口。

## 旧路径收束

- 本批减少 1 处 legacy 调用：
  - `test_plugin_source_extraction_scans_each_file_once` 只需要 selector 和 file_hash 作为提取规则输入，已改用 `build_native_plugin_source_scan`。
- 本批把剩余调用收束为可审计清单：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files`：旧 scanner 的启用文件、禁用文件、嵌套文件和风险计数语义。
  - `test_plugin_source_scan_batches_native_ast_parse_for_source_files`：旧 scanner 主扫描批量 AST 入口语义。
  - `test_plugin_source_scan_reuses_native_ast_by_file_hash`：旧 scanner 主扫描 AST cache 复用语义，两次调用。
  - `test_plugin_source_ast_map_exports_short_source_text_with_ast_context`：旧 scanner AST 上下文候选事实语义。
  - `test_non_utf8_plugin_source_does_not_break_default_game_loading`：非 UTF-8 读取错误和低成本加载边界。
  - `test_plugin_source_scan_decodes_doubled_control_literal_without_real_line_break`：双反斜杠控制符解码边界。
  - `test_plugin_source_high_risk_pauses_workflow_until_rules_are_confirmed`：显式传入旧 scanner 风险结果的 workflow gate 对照。
  - `test_plugin_source_rule_validation_rejects_invalid_js_directly`：JS AST 语法错误报告和规则校验失败路径。
- 后续任何减少这些 legacy 调用的批次，都必须先证明对应语义已有 native 行为测试或已不再需要旧 scanner 对照。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式、目录结构和 Rust API 不变。
- 本批只新增测试边界和开发记录，不改变生产运行路径。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- 当前 `tests/test_plugin_source_text.py` 中 legacy helper 调用从 10 处降到 9 处，native helper 调用从 22 处增加到 23 处。
- 性能收益来自后续批次可以基于精确清单处理剩余旧路径，避免误迁移或重复审计。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch53_remaining_legacy_fixture_record_exists_and_tracks_contract`
  - 结果：1 passed、1 failed。
  - 失败原因：剩余 legacy 边界静态测试已通过；`docs/records/rust-scope-index/batches/batch-053.md` 尚不存在。
- review fix RED：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_extraction_scans_each_file_once tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional`
  - 结果：1 passed、1 failed。
  - 失败原因：`test_plugin_source_extraction_scans_each_file_once` 改用 native 预扫描后行为通过；batch53 剩余 legacy 清单仍包含该测试。
- GREEN：`uv run pytest tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch53_remaining_legacy_fixture_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 相关记录保护：`uv run pytest tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixture_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch53_remaining_legacy_plugin_source_scan_fixtures_are_intentional tests/test_scan_budget.py::test_batch53_remaining_legacy_fixture_record_exists_and_tracks_contract`
  - 结果：3 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- 旧夹具调用统计：`rg -n "build_plugin_source_scan\\(" tests/test_plugin_source_text.py` 与 `rg -n "build_native_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：9 处 legacy 夹具调用、23 处 native 夹具调用。
- 全量 Python 测试：
  - 本批按 rust-scope-index-engine 临时验证策略未执行 `uv run pytest` 全量测试。

## 审查处理

- 只读子代理审查未发现 Critical 问题。
- 只读子代理审查指出 `test_plugin_source_extraction_scans_each_file_once` 是普通 selector/file_hash 夹具残留，不应固定为剩余 legacy 语义边界；已改用 `build_native_plugin_source_scan`，并从剩余 legacy 清单移除。
- 只读子代理审查指出当前工作区相对 `HEAD` 有大量前序生产代码改动，不能把当前工作区 diff 等同于 6V diff；本记录的“本批不改生产代码”仅指 6V 本轮新增/修改范围，不评价前序批次遗留变更。
- 只读子代理审查确认 batch53 文档未发现本机私有路径、用户名或未完成占位文案。

## 剩余风险

- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在。
- 剩余 9 处 legacy 调用仍在测试中直接依赖旧 scanner 私有兼容入口。
- 本批按临时验证策略不跑全量 Python 测试；风险集中在扫描预算静态保护没有覆盖的无关测试模块。

## 下一批入口

- 建议下一批：旧 scanner 私有兼容入口删除或替代评估。
- 建议边界：从 6V 固定的 9 个测试函数中逐项判断哪些语义应迁到 native 行为测试，哪些应保留到旧 scanner 删除前作为对照；不要再按“看见 legacy 调用就替换”的方式推进。
- 理由：剩余 legacy 调用已不再是普通规则输入夹具，下一步需要处理旧 scanner 私有入口本身的存废边界。
