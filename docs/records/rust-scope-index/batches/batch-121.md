# Rust Scope/Index Engine 批次 121 验收记录

## 本批范围

- 批次编号：6CL。
- 范围：P1-B 源文残留 validate/import 迁移评估与契约补强。
- 命令：`validate-source-residual-rules`、`import-source-residual-rules`。
- 目标：明确源文残留例外规则导入校验是否需要新增 Rust `source_residual` 候选域，并把扫描预算从待复核状态改为当前唯一事实来源。

## RED/GREEN

- RED：`tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_record_exists` 在记录缺失时失败。
- RED：`tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_tracks_current_state` 要求 `source_residual` 不进入 `RuleCandidatesPayload`，并要求两条命令移出 `P1_B_PENDING_FACT_SOURCE_COMMANDS`。
- GREEN：扫描预算确认两条命令不新增 `scan_rule_candidates(source_residual)`，改用 `SQLite text_index_items` 精确路径事实、Python source_residual 规则解析、Rust regex contract 和 Rust quality。

## 改动范围

- `tests/scan_budget_contract.py`：`P1_B_PENDING_FACT_SOURCE_COMMANDS` 变为空集合；两条源文残留规则命令的 `candidate_scan_count` 改为 0。
- `tests/test_scan_budget.py`：新增 6CL 当前边界测试和记录保护测试。
- `docs/plans/completed/rust-scope-index-engine.md`：新增 batch-121 记录链接。

## 旧路径收束

- 本批结论是不新增 `scan_rule_candidates(source_residual)`。
- 原因：源文残留 validate/import 校验的是输入规则里的 `position_rules` 是否命中当前文本范围，以及 `allowed_terms` 是否出现在当前原文或已保存译文中；这不是可从全量候选扫描获得更强事实的命令。
- Rust 已有 `Rust regex contract`、`Rust quality` 和写回质量 gate 能力；缺口不在源文残留检测，而在规则导入前的范围归属查询。
- 旧的命令内完整文本范围构建留给 6CM 薄适配收束。

## 外部契约变化

- CLI 参数、stdout Agent JSON 字段、退出码和错误码保持不变。
- 内部扫描预算变化：`validate-source-residual-rules`、`import-source-residual-rules` 的权威事实来源改为 `SQLite text_index_items` 精确路径查询，不再记录为 Rust candidate 域待迁移。
- `P1_B_PENDING_FACT_SOURCE_COMMANDS` 当前为空，表示 P1-B 工作区和规则命令的事实来源复核已清到总收束入口。

## 性能证据

- 新预算固定 `candidate_scan_count=0`、`plugin_source_ast_scan_count=0`。
- 允许的 `text_scope_build_count=1` 只表示 cold 或 stale index 时最多触发一次文本索引重建；warm index 下不应构建完整文本范围。
- 6CM 将用行为测试固定 warm index 下只调用 `read_text_index_items_by_paths` 和 `read_translated_items_by_paths`。

## 验证结果

- `uv run pytest tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_tracks_current_state`：通过，已包含在本批 10 项目标验证中。
- `uv run pytest tests/test_scan_budget.py::test_batch121_p1b_source_residual_sqlite_boundary_record_exists`：通过，已包含在本批 10 项目标验证中。
- `uv run basedpyright`：0 errors, 0 warnings, 0 notes。
- `git diff --check`：通过；仅输出当前工作区 CRLF warning。
- 文档敏感路径搜索：NO_MATCH。
- 本批按临时例外未跑全量 `uv run pytest`。

## 审查处理

- 子代理只读审计确认：当前旧路径会加载 `GameData`、调用 `TextScopeService.build()`，并全量读取已保存译文。
- 子代理建议与本批结论一致：不硬迁到 `scan_rule_candidates(source_residual)`，应走 SQLite text index 快路径。
- 本批没有修改 Rust 原生代码、数据库 schema、CLI 参数或发布流程。

## 剩余风险

- 本批未跑全量 Python pytest。
- 6CM 仍需把服务层旧路径从完整 scope 构建改为索引精确查询，并补行为测试禁止回退。

## 下一批入口

- 进入 6CM：源文残留 validate/import 薄适配与旧路径收束。
