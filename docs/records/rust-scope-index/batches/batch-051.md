# Rust Scope/Index Engine 批次 51 记录

## 本批范围

- 批次：6T，AgentToolkit 规则输入测试夹具第五组 Rust-derived 替换。
- 覆盖范围：`tests/test_plugin_source_text.py` 内 4 个 AgentToolkit 级规则输入测试夹具；这些测试只用前置扫描准备 selector、file_hash 或规则 JSON 输入。
- 成功状态：这 4 个测试改用 `build_native_plugin_source_scan` 准备候选事实，不再通过 `_build_legacy_plugin_source_scan` 别名获取 selector 或 `PluginSourceScan`。
- 明确非范围：本批不迁移旧 scanner 统计、AST batch、cache 复用、语法错误统计、非 UTF-8 读取、控制符解码、high-risk gate 主扫描、import-rule 规则导入或 runtime strict scan 对照测试。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixtures_seed_with_native_scan`：
  - 读取 `tests/test_plugin_source_text.py` 中 4 段目标测试函数源码。
  - 用 Python AST 收集真实调用节点。
  - 断言这些测试函数调用 `build_native_plugin_source_scan`。
  - 断言这些测试函数不再调用 `build_plugin_source_scan`。
- 新增 `tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_plugin_source_text.py::test_quality_report_errors_when_high_risk_plugin_source_review_is_incomplete`
  - `tests/test_plugin_source_text.py::test_validate_plugin_source_rules_errors_when_review_is_incomplete`
  - `tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_prefix_read_for_translated_count`
  - `tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan`

## 实现说明

- 更新 `tests/test_plugin_source_text.py`：
  - 将 `test_quality_report_errors_when_high_risk_plugin_source_review_is_incomplete` 的前置候选扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_validate_plugin_source_rules_errors_when_review_is_incomplete` 的前置候选扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_validate_plugin_source_rules_uses_prefix_read_for_translated_count` 的前置扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_validate_plugin_source_rules_uses_native_plugin_source_scan` 的前置扫描改为 `build_native_plugin_source_scan`；该测试的生产路径 native 断言属于旧批次成果，本批只迁移它的规则夹具事实来源。
  - 保持测试主体断言不变，继续验证质量报告提示源码审查未完成、规则校验提示未覆盖候选、规则校验只读取插件源码前缀译文、validate-plugin-source-rules 不回旧 Python 主扫描。
- 更新 `tests/test_scan_budget.py`：
  - 新增 6T 静态迁移保护和批次记录保护。
  - 复用 AST 调用节点检查辅助函数。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6T 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_quality_report_errors_when_high_risk_plugin_source_review_is_incomplete`
  - `test_validate_plugin_source_rules_errors_when_review_is_incomplete`
  - `test_validate_plugin_source_rules_uses_prefix_read_for_translated_count`
  - `test_validate_plugin_source_rules_uses_native_plugin_source_scan`
  - 以上 4 段测试不再用旧 scanner 别名准备 selector 或规则输入。
- 保留路径：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 继续覆盖旧 scanner 的直接文件统计、风险计数和嵌套文件排除语义。
  - 旧 AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描、import-rule 规则导入、runtime strict scan 和 AgentToolkit 级高风险导入相关测试仍使用 legacy helper，等待后续分组判断。
  - `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍保留为私有兼容入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。
- AgentToolkit 规则输入测试中的 selector、file_hash 和 `PluginSourceScan` 来自 Rust-derived scan，更贴近当前生产默认候选事实。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- 测试夹具对旧 Python scanner 的依赖从 18 处降到 14 处，`build_native_plugin_source_scan` 夹具调用从 14 处增加到 18 处。
- 目标行为测试在 native selector 下仍通过，说明这些 AgentToolkit 规则输入场景不依赖旧 scanner 生成 selector 的特殊行为。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixture_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：目标测试仍未调用 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-051.md` 尚不存在。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_quality_report_errors_when_high_risk_plugin_source_review_is_incomplete tests/test_plugin_source_text.py::test_validate_plugin_source_rules_errors_when_review_is_incomplete tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_prefix_read_for_translated_count tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixture_record_exists_and_tracks_contract`
  - 结果：6 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：818 passed in 272.12s。
- 文档保护最终验证：`uv run pytest tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch51_agent_toolkit_rule_fixture_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- 旧夹具调用统计：`rg -n "build_plugin_source_scan\\(" tests/test_plugin_source_text.py` 与 `rg -n "build_native_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：14 处 legacy 夹具调用、18 处 native 夹具调用。

## 审查处理

- 只读子代理审查未发现阻断问题。
- 只读子代理审查确认 `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 仍走 legacy scanner，未误迁移旧 scanner 统计语义测试。
- 只读子代理审查指出初版 GREEN 命令漏跑 `test_batch51_agent_toolkit_rule_fixture_record_exists_and_tracks_contract`；已补入组合 GREEN 命令，并用 6 passed 结果验证。
- 只读子代理审查提醒 `test_validate_plugin_source_rules_uses_native_plugin_source_scan` 来自旧批次 native 路径验证；本记录已澄清本批只迁移该测试的前置规则夹具事实来源。

## 剩余风险

- `tests/test_plugin_source_text.py` 仍有 14 处 `build_plugin_source_scan` legacy 夹具调用。
- 部分剩余 legacy 调用可能只是 selector/file_hash 准备，但尚未逐一确认是否会削弱旧 scanner 对照覆盖。
- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在，后续需要继续按分组收束。

## 下一批入口

- 建议下一批：旧 scanner 测试夹具第六组 Rust-derived 替换。
- 建议边界：优先审计 import-plugin-source-rules、quality-report 复用扫描或 TextScope 级只构造规则输入的测试；继续避开旧 AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描和 runtime strict scan 对照测试。
- 理由：6T 已证明这组 AgentToolkit 规则输入夹具可直接使用 Rust-derived scan，下一批可以继续减少私有 legacy helper 的测试依赖。
