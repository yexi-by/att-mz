# Rust Scope/Index Engine 批次 50 记录

## 本批范围

- 批次：6S，旧 scanner 工作流/备份测试夹具第四组 Rust-derived 替换。
- 覆盖范围：`tests/test_plugin_source_text.py` 内 3 个只为准备 selector 而调用旧 scanner 的工作流/备份测试夹具。
- 成功状态：这 3 个测试改用 `build_native_plugin_source_scan` 准备候选事实，不再通过 `_build_legacy_plugin_source_scan` 别名获取 selector。
- 明确非范围：本批不迁移旧 scanner 统计、AST batch、cache 复用、语法错误统计、非 UTF-8 读取、控制符解码、high-risk gate 主扫描或 runtime strict scan 对照测试。

## 保护网

- 新增 `tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_seeds_use_native_scan`：
  - 读取 `tests/test_plugin_source_text.py` 中 3 段目标测试函数源码。
  - 用 Python AST 收集真实调用节点。
  - 断言这些测试函数调用 `build_native_plugin_source_scan`。
  - 断言这些测试函数不再调用 `build_plugin_source_scan`。
- 新增 `tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_record_exists_and_tracks_contract`：
  - 断言本记录被计划表链接。
  - 断言本批 native 入口、legacy 私有入口、目标测试名和保护测试名写入记录。
  - 断言记录不包含本机私有路径、用户名和未完成占位文案。
- 相邻行为测试覆盖：
  - `tests/test_plugin_source_text.py::test_plugin_source_write_back_requires_native_ast`
  - `tests/test_plugin_source_text.py::test_plugin_source_partial_backup_keeps_unmodified_files_visible`
  - `tests/test_plugin_source_text.py::test_plugin_source_stale_rule_hash_blocks_workflow`

## 实现说明

- 更新 `tests/test_plugin_source_text.py`：
  - 将 `test_plugin_source_write_back_requires_native_ast` 的前置候选扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_plugin_source_partial_backup_keeps_unmodified_files_visible` 的前置候选扫描改为 `build_native_plugin_source_scan`。
  - 将 `test_plugin_source_stale_rule_hash_blocks_workflow` 的初始规则候选扫描改为 `build_native_plugin_source_scan`。
  - 保持测试主体断言不变，继续验证缺少 Rust 原生扩展时写回停止、部分备份后未改动文件仍可见、当前运行变化不污染翻译源规则身份。
- 更新 `tests/test_scan_budget.py`：
  - 新增 6S 静态迁移保护和批次记录保护。
  - 复用 AST 调用节点检查辅助函数。
- 更新 `docs/plans/completed/rust-scope-index-engine.md`：
  - 追加 6S 批次进度行。

## 旧路径收束

- 已收束路径：
  - `test_plugin_source_write_back_requires_native_ast`
  - `test_plugin_source_partial_backup_keeps_unmodified_files_visible`
  - `test_plugin_source_stale_rule_hash_blocks_workflow`
  - 以上 3 段测试不再用旧 scanner 别名准备 selector。
- 保留路径：
  - `test_plugin_source_scan_only_counts_enabled_direct_plugin_files` 继续覆盖旧 scanner 的直接文件统计、风险计数和嵌套文件排除语义。
  - 旧 AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描、runtime strict scan 和 AgentToolkit 级高风险审查相关测试仍使用 legacy helper，等待后续分组判断。
  - `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍保留为私有兼容入口。

## 外部契约变化

- CLI 参数、Agent JSON 字段、SQLite schema、错误码、日志格式和目录结构不变。
- 本批只改变测试夹具事实来源，不改变生产运行路径。
- 工作流/备份测试中的 selector 来自 Rust-derived scan，更贴近当前生产默认候选事实。

## 性能证据

- 本批不新增生产扫描、I/O 或 Rust 调用。
- 测试夹具对旧 Python scanner 的依赖从 21 处降到 18 处，`build_native_plugin_source_scan` 夹具调用从 11 处增加到 14 处。
- 目标行为测试在 native selector 下仍通过，说明这些工作流/备份场景不依赖旧 scanner 生成 selector 的特殊行为。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_seeds_use_native_scan tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_record_exists_and_tracks_contract`
  - 结果：2 failed。
  - 失败原因：目标测试仍未调用 `build_native_plugin_source_scan`；`docs/records/rust-scope-index/batches/batch-050.md` 尚不存在。
- GREEN：`uv run pytest tests/test_plugin_source_text.py::test_plugin_source_write_back_requires_native_ast tests/test_plugin_source_text.py::test_plugin_source_partial_backup_keeps_unmodified_files_visible tests/test_plugin_source_text.py::test_plugin_source_stale_rule_hash_blocks_workflow tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_seeds_use_native_scan tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_record_exists_and_tracks_contract`
  - 结果：5 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors、0 warnings、0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：816 passed in 263.10s。
- 文档保护最终验证：`uv run pytest tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_seeds_use_native_scan tests/test_scan_budget.py::test_batch50_plugin_source_workflow_fixture_record_exists_and_tracks_contract`
  - 结果：2 passed。
- 敏感路径和占位文案搜索：
  - 结果：无匹配。
- Diff 空白检查：`git diff --check`
  - 结果：退出码 0；输出只有 Git 的 LF/CRLF 工作副本提示。
- 旧夹具调用统计：`rg -n "build_plugin_source_scan\\(" tests/test_plugin_source_text.py` 与 `rg -n "build_native_plugin_source_scan\\(" tests/test_plugin_source_text.py`
  - 结果：18 处 legacy 夹具调用、14 处 native 夹具调用。

## 审查处理

- 只读子代理审查未发现阻断问题。
- 只读子代理审查确认：6S 三个目标测试只看到 selector 准备从 legacy scan 换到 `build_native_plugin_source_scan`，未发现误迁移旧 scanner 语义测试。
- 只读子代理审查指出初版 GREEN 命令漏跑 `test_batch50_plugin_source_workflow_fixture_record_exists_and_tracks_contract`，且初版审查段仍写着“将进行只读子代理审查”；已补入组合 GREEN 命令，并在本段回填实际审查结论。
- 只读子代理审查提醒：batch50 静态保护只能覆盖当前 3 个目标函数内的直接调用；未来通过别名或 helper 间接重新引入旧 scanner 的风险仍需后续分组审计。

## 剩余风险

- `tests/test_plugin_source_text.py` 仍有 18 处 `build_plugin_source_scan` legacy 夹具调用。
- 部分剩余 legacy 调用可能只是 selector/file_hash 准备，但尚未逐一确认是否会削弱旧 scanner 对照覆盖。
- `_build_legacy_plugin_source_scan` 和 `_scan_legacy_plugin_source_files_text_strict` 仍存在，后续需要继续按分组收束。

## 下一批入口

- 建议下一批：旧 scanner 测试夹具第五组 Rust-derived 替换。
- 建议边界：优先审计 AgentToolkit 级只构造规则输入的测试；继续避开旧 AST batch、cache 复用、syntax error、非 UTF-8、控制符解码、high-risk gate 主扫描和 runtime strict scan 对照测试。
- 理由：6S 已证明这组工作流/备份 selector 夹具可直接使用 Rust-derived scan，下一批可以继续减少私有 legacy helper 的测试依赖。
