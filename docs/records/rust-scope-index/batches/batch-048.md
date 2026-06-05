# Rust Scope/Index Engine 批次 48 记录

## 本批范围

- 批次：6Q，旧 scanner 写回测试夹具第二组 Rust-derived 替换。
- 覆盖范围：`tests/test_plugin_source_text.py` 内 3 个插件源码写回相关测试夹具；这些测试只用前置扫描准备 selector、file_hash 和规则记录，实际断言对象是写回结果与 runtime write map。
- 成功状态：这 3 个写回测试改用 `build_native_plugin_source_scan` 准备候选事实，不再通过 `_build_legacy_plugin_source_scan` 别名获取 selector/hash。
- 明确非范围：本批不迁移旧 scanner 统计、AST batch、cache 复用、非 UTF-8 读取、语法错误统计、runtime strict scan 或 AgentToolkit 高风险审查对照测试。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixtures_seed_with_native_scan`：
  - 读取 `tests/test_plugin_source_text.py` 中 3 段写回测试函数源码。
  - 用 Python AST 收集真实调用节点。
  - 断言这些测试函数调用 `build_native_plugin_source_scan`。
  - 断言这些测试函数不再调用 `build_plugin_source_scan`。
- 新增 `tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_plugin_source_text.py::test_plugin_source_write_back_returns_runtime_write_maps_after_length_changes`
  - `tests/test_plugin_source_text.py::test_plugin_source_write_back_treats_runtime_map_as_optional`
  - `tests/test_plugin_source_text.py::test_plugin_source_write_back_scans_changed_file_for_runtime_write_maps`

## 实现说明

- 更新 `tests/test_plugin_source_text.py`：
  - 将 3 个写回测试里的前置 `scan = build_plugin_source_scan(...)` 改为 `scan = build_native_plugin_source_scan(...)`。
  - 保持测试主体断言不变，继续验证 runtime write map、写回后源码内容和只扫描实际写入文件。
- 更新 `tests/test_scan_budget.py`：
  - 新增 6Q 静态迁移保护和批次记录保护。
  - 复用批次 47 已引入的 AST 调用节点检查辅助函数。
- 更新 `docs/records/rust-scope-index/batches/batch-047.md`：
  - 修正剩余风险中已过时的“只保护三段 fallback”描述，改为当前 5 段已迁移测试保护状态。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6Q 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_plugin_source_write_back_returns_runtime_write_maps_after_length_changes`
  - `test_plugin_source_write_back_treats_runtime_map_as_optional`
  - `test_plugin_source_write_back_scans_changed_file_for_runtime_write_maps`
  - 以上 3 段测试不再用旧 scanner 别名准备 selector/hash。
- 保留路径：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 继续覆盖旧 scanner 的直接文件统计、风险计数和嵌套文件排除语义。
  - 旧 AST batch、cache 复用、syntax error、非 UTF-8、runtime strict scan 和 AgentToolkit 级高风险审查相关测试仍使用 legacy helper，等待后续分组判断。
  - `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍保留为私有兼容入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。
- 写回测试中的 selector、file_hash 来自 Rust-derived scan，更贴近当前生产默认候选事实。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- 测试夹具对旧 Python scanner 的依赖从 27 处降到 24 处，`build_native_plugin_source_scan` 夹具调用从 5 处增加到 8 处。
- 写回行为测试在 native selector/hash 下仍通过，说明写回路径不依赖旧 scanner 生成 selector 的特殊行为。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixture_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：目标写回测试仍未调用 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-048.md` 尚不存在。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_back_returns_runtime_write_maps_after_length_changes tests/test_plugin_source_text.py::test_plugin_source_write_back_treats_runtime_map_as_optional tests/test_plugin_source_text.py::test_plugin_source_write_back_scans_changed_file_for_runtime_write_maps tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixture_record_exists_and_tracks_contract`
  - 结果：5 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：812 passed in 251.97s。
- 文档保护最终验证：`uv run pytest tests/test_scan_budget.py::test_batch47_plugin_source_fixture_migration_record_exists_and_tracks_contract tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixtures_seed_with_native_scan tests/test_scan_budget.py::test_batch48_plugin_source_write_back_fixture_record_exists_and_tracks_contract`
  - 结果：3 passed。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- 旧夹具调用统计：`rg -n "build_plugin_source_scan\\(" tests/test_plugin_source_text.py` 与 `rg -n "build_native_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：24 处 legacy 夹具调用、8 处 native 夹具调用。

## 审查处理

- 只读子代理审查未发现写回测试迁移误删旧 scanner 语义覆盖，也未发现批次 47 文档修正或 6Q 静态保护存在阻断问题。
- 只读子代理审查指出初版 GREEN 命令漏跑 `test_batch48_plugin_source_write_back_fixture_record_exists_and_tracks_contract`，存在文档验收口径不完整风险；已补入组合 GREEN 命令，并用 5 passed 结果验证。

## 剩余风险

- `tests/test_plugin_source_text.py` 仍有 24 处 `build_plugin_source_scan` legacy 夹具调用。
- 部分剩余 legacy 调用可能只是 selector/file_hash 准备，但尚未逐一确认是否会削弱旧 scanner 对照覆盖。
- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在，后续需要继续按分组收束。

## 下一批入口

- 建议下一批：旧 scanner 测试夹具第三组 Rust-derived 替换。
- 建议边界：优先审计插件源码规则排除、只读规则导出或 AgentToolkit 级只构造规则输入的测试；继续避开旧 batch AST、cache 复用、syntax error、非 UTF-8 和 runtime strict scan 对照测试。
- 理由：6Q 已证明写回类 selector/hash 夹具可直接使用 Rust-derived scan，下一批可以继续减少私有 legacy helper 的测试依赖。
