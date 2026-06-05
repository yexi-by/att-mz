# Rust Scope/Index Engine 批次 52 记录

## 本批范围

- 批次：6U，AgentToolkit 导入/质量/TextScope 测试夹具第六组 Rust-derived 替换。
- 覆盖范围：`tests/test_plugin_source_text.py` 内 4 个只用前置插件源码扫描准备 selector、file_hash 或规则记录输入的测试。
- 成功状态：这 4 个测试改用 `build_native_plugin_source_scan` 准备候选事实，不再通过 `_build_legacy_plugin_source_scan` 别名获取规则输入。
- 明确非范围：本批不迁移旧 scanner 统计、AST batch、cache 复用、语法错误统计、非 UTF-8 读取、控制符解码、high-risk gate 主扫描或 runtime strict scan 对照测试。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixtures_seed_with_native_scan`：
  - 读取 `tests/test_plugin_source_text.py` 中 4 段目标测试函数源码。
  - 用 Python AST 收集真实调用节点。
  - 断言这些测试函数调用 `build_native_plugin_source_scan`。
  - 断言这些测试函数不再调用 `build_plugin_source_scan`。
- 新增 `tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan`
  - `tests/test_plugin_source_text.py::test_import_plugin_source_rules_replaces_stale_existing_rule`
  - `tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope`
  - `tests/test_plugin_source_text.py::test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan`

## 实现说明

- 更新 `tests/test_plugin_source_text.py`：
  - 将 `test_import_plugin_source_rules_uses_native_plugin_source_scan` 的前置候选扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_import_plugin_source_rules_replaces_stale_existing_rule` 的前置候选扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_quality_report_write_probe_reuses_plugin_source_scan_for_scope` 的前置规则记录构造扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan` 的前置规则记录构造扫描改为 `build_native_plugin_source_scan`。
  - 保持测试主体断言不变，继续验证规则导入走 native 候选事实、过期规则替换清理旧译文、quality-report 写回探针不二次扫描 AST、TextScope fallback 不回旧 Python 主扫描。
- 更新 `tests/test_scan_budget.py`：
  - 新增 6U 静态迁移保护和批次记录保护。
  - 复用 AST 调用节点检查辅助函数。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6U 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_import_plugin_source_rules_uses_native_plugin_source_scan`
  - `test_import_plugin_source_rules_replaces_stale_existing_rule`
  - `test_quality_report_write_probe_reuses_plugin_source_scan_for_scope`
  - `test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan`
  - 以上 4 段测试不再用旧 scanner 别名准备 selector、file_hash 或规则记录输入。
- 保留路径：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 继续覆盖旧 scanner 的直接文件统计、风险计数和嵌套文件排除语义。
  - 旧 AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描、runtime strict scan 和源码提取扫描次数对照测试仍使用 legacy helper，等待后续分组判断。
  - `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍保留为私有兼容入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。
- AgentToolkit 导入/质量/TextScope 测试中的 selector、file_hash 和 `PluginSourceScan` 来自 Rust-derived scan，更贴近当前生产默认候选事实。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- 测试夹具对旧 Python scanner 的依赖从 14 处降到 10 处，`build_native_plugin_source_scan` 夹具调用从 18 处增加到 22 处。
- 目标行为测试在 native selector 和 file_hash 下仍通过，说明这些 AgentToolkit 导入/质量/TextScope 场景不依赖旧 scanner 生成规则输入的特殊行为。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixture_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：目标测试仍未调用 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-052.md` 尚不存在。
- 目标 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_import_plugin_source_rules_replaces_stale_existing_rule tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope tests/test_plugin_source_text.py::test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixtures_seed_with_native_scan`
  - 结果：5 passed。
- 组合 GREEN：`uv run pytest tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_import_plugin_source_rules_replaces_stale_existing_rule tests/test_plugin_source_text.py::test_quality_report_write_probe_reuses_plugin_source_scan_for_scope tests/test_plugin_source_text.py::test_text_scope_build_uses_native_plugin_source_scan_when_caller_omits_scan tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch52_agent_toolkit_import_scope_fixture_record_exists_and_tracks_contract`
  - 结果：6 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：820 passed。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- 旧夹具调用统计：`rg -n "build_plugin_source_scan\\(" tests/test_plugin_source_text.py` 与 `rg -n "build_native_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：10 处 legacy 夹具调用、22 处 native 夹具调用。

## 审查处理

- 只读子代理审查未发现 Critical 问题。
- 只读子代理审查确认 4 个目标测试已直接使用 `build_native_plugin_source_scan`，不再直接调用 `build_plugin_source_scan`。
- 只读子代理审查确认剩余 legacy direct 调用计数为 10，native 调用计数为 22；旧 scanner 语义测试仍保留 legacy。
- 只读子代理审查指出初版记录含占位式验证文案，且 batch52 forbidden markers 未覆盖这类表述；已删除占位文案，并在 `test_batch52_agent_toolkit_import_scope_fixture_record_exists_and_tracks_contract` 中加入对应的占位补全类拦截词。
- 只读子代理审查指出 batch52 静态保护只检查调用名，不额外校验 `build_native_plugin_source_scan` 的导入绑定来源；当前导入来自 `app.plugin_source_text`，本批不把该 Minor 项作为阻断，后续如继续增强静态保护可补充导入来源检查。

## 剩余风险

- `tests/test_plugin_source_text.py` 仍有 10 处 `build_plugin_source_scan` legacy 夹具调用。
- 剩余 legacy 调用里包含旧 scanner 主体统计、AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描和 runtime strict scan 对照场景，后续批次需要先判断是否属于旧语义保护再迁移。
- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在，后续需要继续按分组收束。

## 下一批入口

- 建议下一批：旧 scanner 测试夹具第七组 Rust-derived 替换。
- 建议边界：优先审计剩余 legacy 调用中只构造规则输入或 selector 的测试；继续避开旧 scanner 主体统计、AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描和 runtime strict scan 对照测试。
- 理由：6U 已证明 AgentToolkit 导入/质量/TextScope 规则输入夹具可直接使用 Rust-derived scan，下一批可以继续减少私有 legacy helper 的测试依赖。
