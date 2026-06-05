# Rust Scope/Index Engine 批次 38 记录

## 本批范围

- 批次：6G，`validate-plugin-source-rules` 插件源码候选事实接入 Rust。
- 覆盖入口：Agent/CLI 子服务 `validate_plugin_source_rules` 的插件源码规则解析、候选覆盖统计、命中统计、译文计数和写回探针。
- 成功状态：独立插件源码规则校验不再调用旧 Python `build_plugin_source_scan` 主扫描；改为复用 `validate-agent-workspace` 已验证的 Rust-derived `PluginSourceScan`，并把同一份扫描结果传入规则校验和写回探针。

## 保护网

- 新增 `tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan`：
  - 构造带有效插件源码规则的独立规则校验输入。
  - monkeypatch `app.agent_toolkit.services.rule_validation.build_plugin_source_scan` 为失败函数，禁止 `validate_plugin_source_rules` 回到旧 Python 主扫描。
  - monkeypatch `app.text_scope.write_probe.scan_plugin_source_files_text_strict` 为失败函数，证明写回探针消费同一份 `PluginSourceScan`，没有在规则校验阶段重新执行插件源码 AST 扫描。
  - monkeypatch 计数 `app.agent_toolkit.services.workspace.scan_native_rule_candidates`，断言本轮独立规则校验只调用一次 Rust 候选扫描。
  - 断言规则校验报告保持 `ok`，并保留 1 条命中。
- 新增 `tests/test_scan_budget.py::test_batch38_validate_plugin_source_rules_native_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `validate_plugin_source_rules`、`scan_native_rule_candidates`、`PluginSourceScan`、`build_plugin_source_scan` 和本批命令级测试名。

## 改动范围

- `app/agent_toolkit/services/rule_validation.py`
  - `validate_plugin_source_rules` 使用 `_build_native_plugin_source_scan` 构造 Rust-derived `PluginSourceScan`。
  - `import_plugin_source_rules` 仍保留旧 `build_plugin_source_scan` 路径，留到后续批次迁移。
- `tests/test_plugin_source_text.py`
  - 新增 6G 命令级回归测试，固定独立规则校验的 Rust 候选事实源和单次扫描预算。
- `tests/test_scan_budget.py`
  - 新增批次 38 验收记录测试。
- `docs/plans/completed/rust-scope-index-engine.md`
  - 新增 6G 批次进度行。

## 旧路径收束

- `validate_plugin_source_rules` 已停止消费旧 Python `build_plugin_source_scan` 主扫描。
- 旧 `PluginSourceScan` 数据结构仍保留，作为当前插件源码规则校验、文本提取、selector/hash 覆盖逻辑和写回探针的兼容输入。
- `import-plugin-source-rules` 仍直接使用旧扫描入口，后续迁移前不能删除旧扫描器。

## 外部契约变化

- `validate-plugin-source-rules` 的 CLI 参数、退出码语义和 Agent JSON 报告结构不变。
- `summary` 中的 `file_count`、`selector_count`、`excluded_selector_count`、`reviewed_selector_count`、`unreviewed_selector_count`、`hit_count`、`extractable_count`、`translated_count`、`writable_count` 和 `unwritable_count` 字段保持不变。
- `details.rules` 明细结构保持不变。
- 插件源码规则无效、审查未完成、空规则、无命中和不可写命中项的错误码保持不变。

## 性能证据

- 命令级保护网证明 `validate_plugin_source_rules` 不再调用旧 `build_plugin_source_scan`。
- 命令级保护网证明写回探针不再隐藏调用旧插件源码 AST 严格扫描。
- 命令级保护网断言独立插件源码规则校验只调用一次 `scan_native_rule_candidates`，并复用同一份 Rust-derived `PluginSourceScan`。

## 验证结果

- RED：`uv run pytest tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan`
  - 结果：1 failed，失败原因为 `validate_plugin_source_rules` 没有调用 Rust 候选扫描，仍由旧扫描异常包装成插件源码规则无效报告。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan`
  - 结果：1 passed。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/rule_validation.py tests/test_plugin_source_text.py`
  - 结果：0 errors，0 warnings，0 notes。
- 定向回归：`uv run pytest tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_plugin_source_text.py::test_plugin_source_rule_validation_rejects_invalid_js_directly tests/test_plugin_source_text.py::test_validate_plugin_source_rules_errors_when_review_is_incomplete tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_prefix_read_for_translated_count tests/test_plugin_source_text.py::test_import_plugin_source_rules_rejects_high_risk_empty_review`
  - 结果：5 passed。
- 文档记录 RED：`uv run pytest tests/test_scan_budget.py::test_batch38_validate_plugin_source_rules_native_record_exists_and_tracks_contract`
  - 结果：1 failed，失败原因为 `docs/records/rust-scope-index/batches/batch-038.md` 尚不存在。
- 文档记录 GREEN：`uv run pytest tests/test_scan_budget.py::test_batch38_validate_plugin_source_rules_native_record_exists_and_tracks_contract`
  - 结果：1 passed。
- 文档与命令保护组合：`uv run pytest tests/test_plugin_source_text.py::test_validate_plugin_source_rules_uses_native_plugin_source_scan tests/test_scan_budget.py::test_batch38_validate_plugin_source_rules_native_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 局部类型检查：`uv run basedpyright app/agent_toolkit/services/rule_validation.py tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：0 errors，0 warnings，0 notes。
- 相邻回归：`uv run pytest tests/test_plugin_source_text.py tests/test_scan_budget.py`
  - 结果：87 passed。
- 全量类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：789 passed。
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
- Important：审查指出新增测试只禁止了 `rule_validation.build_plugin_source_scan`，没有同时禁止 `workspace.build_plugin_source_scan`，如果共享 helper 未来回退到旧主扫描，测试可能抓不住。本批已补充同测例对 `app.agent_toolkit.services.workspace.build_plugin_source_scan` 的失败 monkeypatch。
- Minor：审查指出文档记录只有文档 RED、缺少 GREEN。本批已补充文档记录测试的 GREEN 结果。
- 审查确认：`validate_plugin_source_rules` 当前不再调用旧 `build_plugin_source_scan`；`import_plugin_source_rules` 仍保留旧扫描路径，未提前迁移；报告字段、错误码和 `translated_count` 前缀读取行为保持原契约。

## 剩余风险

- `import-plugin-source-rules` 仍使用旧 Python 主扫描，后续迁移前不能删除旧扫描器。
- Rust-derived `PluginSourceScan` 当前覆盖扫描、AST map、prepare、validate workspace 和独立 validate rules；导入命令和运行文件写回审计仍需逐批迁移。
- 插件源码写回定位和运行文件审计仍依赖旧 selector/hash 语义，后续迁移必须继续保持外部契约等价。

## 下一批入口

- 建议下一批：6H `import-plugin-source-rules` 插件源码候选事实接入 Rust。目标是让插件源码规则导入命令也消费 Rust-derived `PluginSourceScan`，并继续保持数据库事务、空规则确认、高风险审查和旧译文备份清理契约不变。
