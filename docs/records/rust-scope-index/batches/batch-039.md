# Rust Scope/Index Engine 批次 39 记录

## 本批范围

- 批次：6H，`import-plugin-source-rules` 插件源码候选事实接入 Rust。
- 覆盖入口：Agent/CLI 子服务 `import_plugin_source_rules` 的规则解析、候选覆盖检查、高风险审查、数据库事务、旧译文清理备份和规则写入。
- 成功状态：插件源码规则导入不再调用旧 Python `build_plugin_source_scan` 主扫描；改为复用 `validate-plugin-source-rules` 已验证的 Rust-derived `PluginSourceScan`，并保持导入事务和外部报告契约不变。

## 保护网

- 新增 `tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan`：
  - 构造带有效插件源码规则的导入输入。
  - monkeypatch `app.agent_toolkit.services.rule_validation.build_plugin_source_scan` 和 `app.agent_toolkit.services.workspace.build_plugin_source_scan` 为失败函数，禁止导入命令回到旧 Python 主扫描。
  - monkeypatch 计数 `app.agent_toolkit.services.workspace.scan_native_rule_candidates`，断言本轮导入只调用一次 Rust 候选扫描。
  - 断言导入报告保持 `ok`，`selector_count` 为 1，且没有清理旧译文。
  - 打开数据库会话读取已保存插件源码规则，断言规则被真实写入当前游戏数据库。
- 保留并定向回归：
  - `test_import_plugin_source_rules_rejects_high_risk_empty_review`
  - `test_import_plugin_source_rules_replaces_stale_existing_rule`
  - `test_validate_plugin_source_rules_uses_native_plugin_source_scan`
  - `test_validate_plugin_source_rules_uses_prefix_read_for_translated_count`
- 新增 `tests/test_scan_budget.py::test_batch39_import_plugin_source_rules_native_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `import_plugin_source_rules`、`scan_native_rule_candidates`、`PluginSourceScan`、`build_plugin_source_scan` 和本批命令级测试名。

## 改动范围

- `app/agent_toolkit/services/rule_validation.py`
  - `import_plugin_source_rules` 使用 `_build_native_plugin_source_scan` 构造 Rust-derived `PluginSourceScan`。
  - 移除 `rule_validation.py` 中已不再使用的 `build_plugin_source_scan` 导入。
- `tests/test_plugin_source_text.py`
  - 新增 6H 命令级回归测试，固定导入命令的 Rust 候选事实源、单次扫描预算和数据库写入结果。
- `tests/test_scan_budget.py`
  - 新增批次 39 验收记录测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 新增 6H 批次进度行。

## 旧路径收束

- `import_plugin_source_rules` 已停止消费旧 Python `build_plugin_source_scan` 主扫描。
- `rule_validation.py` 中的旧扫描导入已移除。
- 旧 `build_plugin_source_scan` 仍保留给尚未迁移的插件源码运行审计、写回定位和其他非本批路径；本批不能删除旧扫描器。

## 外部契约变化

- `import-plugin-source-rules` 的 CLI 参数、退出码语义和 Agent JSON 报告结构不变。
- 空规则确认、高风险空审查拦截、未审查候选错误、旧译文备份清理、规则替换事务和运行写回映射清理行为保持不变。
- `summary` 中的 `file_count`、`selector_count`、`excluded_selector_count`、`reviewed_selector_count`、`unreviewed_selector_count`、`deleted_translation_items` 和 `deleted_translation_backup_path` 字段保持不变。
- `details.rules` 明细结构保持不变。

## 性能证据

- 命令级保护网证明 `import_plugin_source_rules` 不再调用旧 `build_plugin_source_scan`。
- 命令级保护网断言插件源码规则导入只调用一次 `scan_native_rule_candidates`，并复用同一份 Rust-derived `PluginSourceScan` 完成规则记录构建、审查覆盖统计和文本提取。
- 定向回归保留旧规则替换和旧译文清理场景，证明性能路径切换没有绕过导入事务。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan`
  - 结果：1 failed，失败原因为 `import_plugin_source_rules` 没有调用 Rust 候选扫描，仍由旧扫描异常包装成插件源码规则导入失败报告。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan`
  - 结果：1 passed。
- 局部类型检查第一次：`uv run basedpyright app/agent_toolkit/services/rule_validation.py tests/test_plugin_source_text.py`
  - 结果：0 errors，1 warning，失败原因为 `build_plugin_source_scan` 导入已未使用。
- 局部类型检查 GREEN：`uv run basedpyright app/agent_toolkit/services/rule_validation.py tests/test_plugin_source_text.py`
  - 结果：0 errors，0 warnings，0 notes。
- 定向回归：`uv run pytest tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_import_plugin_source_rules_rejects_high_risk_empty_review tests/test_plugin_source_text.py::test_import_plugin_source_rules_replaces_stale_existing_rule tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_prefix_read_for_translated_count`
  - 结果：5 passed。
- 文档记录 RED：`uv run pytest tests/test_scan_budget.py::test_batch39_import_plugin_source_rules_native_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-039.md` 尚不存在。
- 文档记录 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch39_import_plugin_source_rules_native_record_exists_and_tracks_contract tests/test_plugin_source_text.py::test_import_plugin_source_rules_uses_native_plugin_source_scan`
  - 结果：2 passed。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/rule_validation.py tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：89 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：791 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。

## 审查处理

- 已按 Superpowers 流程完成只读代码审查。
- Critical：无。
- Important：无。
- Minor：审查指出文档记录只有文档 RED、缺少 GREEN。本批已补充文档记录测试通过结果。
- 审查确认：`import_plugin_source_rules` 已改为调用 `_build_native_plugin_source_scan`，没有再直接调用旧 `build_plugin_source_scan`；`validate_plugin_source_rules` 的 6G 路径保持 Rust-derived `PluginSourceScan`；导入事务、旧译文备份删除、空规则确认、高风险审查、运行写回映射清理都仍在原事务区和原报告结构里。

## 剩余风险

- 旧插件源码扫描器仍被其他运行审计和写回定位路径使用，后续迁移前不能删除。
- Rust-derived `PluginSourceScan` 当前覆盖扫描、AST map、prepare、validate workspace、validate rules 和 import rules；运行文件写回审计仍需逐批迁移。
- 插件源码写回定位和运行文件审计仍依赖旧 selector/hash 语义，后续迁移必须继续保持外部契约等价。

## 下一批入口

- 建议下一批：6I 插件源码运行审计和写回定位相关路径的候选事实审计。目标是先静态梳理仍使用旧插件源码扫描器的运行文件审计、写回映射和质量路径，再决定下一条可安全迁移的命令或服务边界。
