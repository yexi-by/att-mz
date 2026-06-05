# Rust Scope/Index Engine 批次 6AL 验收记录

## 本批范围

本批推进非标准 data 支线收束回归审计。范围限定为候选扫描、规则覆盖统计、已导入规则提取、text-scope 复用和 active runtime audit 的旧叶子解析边界，目标是删除 `app/nonstandard_data/scanner.py` 中保留的旧 Python `resolve_nonstandard_data_leaves` 事实来源，让生产代码只通过 Rust native leaves 入口展开非标准 data JSON 叶子。

## 保护网

- `tests/test_scan_budget.py::test_batch69_nonstandard_data_stage_closure_removes_legacy_python_leaf_resolver` 固定生产代码中不得再出现 `resolve_nonstandard_data_leaves`、`_walk_json_value` 和 scanner 内的 `quote_jsonpath_key` 旧递归实现，同时确认 `resolve_nonstandard_data_file_leaves_native` 仍是导出入口。
- `tests/test_scan_budget.py::test_batch69_nonstandard_data_stage_closure_record_exists_and_tracks_contract` 固定本批验收记录、计划索引和验证命令。
- 既有 `tests/test_nonstandard_data.py` 行为测试继续覆盖候选扫描、规则导入、text-scope 提取、写回提取和 active runtime audit 的非标准 data 主流程。

## 实现说明

- `app/nonstandard_data/scanner.py` 删除旧 Python `resolve_nonstandard_data_leaves` 和私有 `_walk_json_value`。
- `app/nonstandard_data/scanner.py` 移除只服务旧递归实现的 `quote_jsonpath_key` 导入。
- `app/nonstandard_data/scanner.py` 的 `__all__` 不再导出 `resolve_nonstandard_data_leaves`，保留 `resolve_nonstandard_data_file_leaves_native` 作为多文件 native leaves 入口。
- `tests/test_scan_budget.py` 更新 6AG 当前入口审计断言，避免继续把旧 resolver 当成 scanner 必备导出。

## 旧路径收束

候选扫描继续由 `build_nonstandard_data_scan` 调用 `scan_native_rule_candidates` 和 `build_native_nonstandard_data_candidates_payload`。规则覆盖统计继续由 `app/nonstandard_data/rules.py` 调用 Rust 候选结果。已导入规则提取和 active runtime audit 继续使用 `resolve_nonstandard_data_file_leaves_native`。text-scope 一轮构建继续复用 `NonstandardDataTextExtractionContext` 和 `nonstandard_data_context`。

本批后，`app/` 生产代码不再包含 `resolve_nonstandard_data_leaves` 或 `_walk_json_value`。旧 Python leaf resolver 不再作为并行事实来源存在。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、导入规则 JSON 格式、退出码或用户可见报告字段变化。本批删除的是内部 Python 模块兼容导出；项目仍处于主动开发阶段，不保留错误或含混的内部契约。

## 性能证据

RED 阶段静态测试证明旧 Python resolver 仍留在 scanner 生产代码中。GREEN 阶段同一测试证明生产代码已经没有旧 resolver 残留，非标准 data 叶子展开只剩 Rust native 入口，避免后续链路重新引入 Python 递归全量扫描事实来源。

## 验证结果

- RED：`uv run pytest tests/test_scan_budget.py::test_batch69_nonstandard_data_stage_closure_removes_legacy_python_leaf_resolver tests/test_scan_budget.py::test_batch69_nonstandard_data_stage_closure_record_exists_and_tracks_contract`，2 failed；失败点分别是 scanner 仍含 `resolve_nonstandard_data_leaves` 和本批记录不存在。
- GREEN：`uv run pytest tests/test_scan_budget.py::test_batch69_nonstandard_data_stage_closure_removes_legacy_python_leaf_resolver tests/test_scan_budget.py::test_batch69_nonstandard_data_stage_closure_record_exists_and_tracks_contract`，2 passed。
- `uv run pytest tests/test_nonstandard_data.py tests/test_scan_budget.py`，117 passed。
- `uv run basedpyright`，0 errors，0 warnings，0 notes。
- `uv run pytest`，863 passed。
- 文档敏感路径/占位文案搜索，通过，无命中。
- `git diff --check`，通过；仅输出既有 LF/CRLF 工作区提示。

## 审查处理

本批未进入外部 PR 审查。删除范围集中在非标准 data scanner 旧兼容入口和对应 scan_budget 记录保护，未改 Rust 原生代码、CLI 外部契约或数据库 schema。

## 剩余风险

本批收束了非标准 data 支线旧 Python leaf resolver，但没有合并 active runtime audit、写回提取和 text-scope 之间的跨命令 leaves 事实缓存。它们属于不同命令或不同运行阶段，暂不共享内存事实；若后续出现同一命令内重复构建，应按 scan_budget 继续单独固定。

## 下一批入口

建议下一批进入 P1-B 非标准 data 阶段收束回顾：复核 6AG 到 6AL 的记录、测试和计划索引，确认非标准 data 支线是否可以整体关闭，并决定后续进入哪个 P1/P2 支线。
