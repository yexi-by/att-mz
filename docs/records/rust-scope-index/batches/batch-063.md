# Rust Scope/Index Engine 批次 6AF 验收记录

## 本批范围

本批是 P1-B 插件源码阶段收束回顾，只新增阶段保护测试、计划索引和验收记录，不修改生产代码。

范围覆盖 6B 到 6AE 的插件源码支线迁移链：

- Rust 候选入口和 `scan_native_rule_candidates`。
- `scan-plugin-source-text`、`export-plugin-source-ast-map`、工作区准备和验收、插件源码规则校验与导入。
- 当前运行文件审计、runtime scan cache、`diagnose-active-runtime` 和写回探针 fallback。
- package root 导出边界、旧 scanner 测试夹具迁移、旧 scanner 生产入口删除和历史残留边界。
- 6AE 的插件源码支线收束回归保护。

## 保护网

新增 `tests/test_scan_budget.py::test_batch63_plugin_source_stage_records_cover_native_runtime_and_legacy_closure`：

- 逐条确认 `docs/records/rust-scope-index/batches/batch-033.md` 到 `docs/records/rust-scope-index/batches/batch-062.md` 都存在，并且都被计划表链接。
- 固定 6B 到 6AE 的代表性测试名、入口名和记录主题。
- 确认 `app/plugin_source_text/__init__.py` 继续导出 `build_native_plugin_source_scan` 与 `scan_plugin_source_runtime_files_text_strict`。
- 确认 `app/` 生产代码没有旧 scanner 主扫描函数、旧翻译源 strict 函数或旧 helper 名称残留。

新增 `tests/test_scan_budget.py::test_batch63_plugin_source_stage_closure_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定阶段记录链、关键入口、关键目标测试、全量 `uv run pytest` 和 `uv run basedpyright` 验证要求。

RED 证据：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch63_plugin_source_stage_records_cover_native_runtime_and_legacy_closure tests/test_scan_budget.py::test_batch63_plugin_source_stage_closure_record_exists_and_tracks_contract
```

结果：阶段链保护通过，记录保护因 `docs/records/rust-scope-index/batches/batch-063.md` 尚未存在失败。

## 实现说明

本批只把已有迁移事实收束成阶段级可机读保护，不改变生产实现。

阶段记录链：

| 批次 | 主题 | 记录 |
| --- | --- | --- |
| 6B | 插件源码候选扫描 Rust 入口 | `docs/records/rust-scope-index/batches/batch-033.md` |
| 6C | scan-plugin-source-text 薄适配接入 | `docs/records/rust-scope-index/batches/batch-034.md` |
| 6D | export-plugin-source-ast-map Rust 候选接入 | `docs/records/rust-scope-index/batches/batch-035.md` |
| 6E | prepare-agent-workspace 插件源码风险报告接入 Rust 事实 | `docs/records/rust-scope-index/batches/batch-036.md` |
| 6F | validate-agent-workspace 插件源码支线候选事实接入 Rust | `docs/records/rust-scope-index/batches/batch-037.md` |
| 6G | validate-plugin-source-rules 插件源码候选事实接入 Rust | `docs/records/rust-scope-index/batches/batch-038.md` |
| 6H | import-plugin-source-rules 插件源码候选事实接入 Rust | `docs/records/rust-scope-index/batches/batch-039.md` |
| 6I | 插件源码运行审计和写回定位相关路径候选事实审计 | `docs/records/rust-scope-index/batches/batch-040.md` |
| 6J | 翻译源 PluginSourceScan 通用 fallback 接入 Rust-derived scan | `docs/records/rust-scope-index/batches/batch-041.md` |
| 6K | active runtime 插件源码扫描缓存 Rust-AST runtime 入口接入 | `docs/records/rust-scope-index/batches/batch-042.md` |
| 6L | diagnose-active-runtime 写回映射 source scan 接入 runtime 字面量扫描 | `docs/records/rust-scope-index/batches/batch-043.md` |
| 6M | 写回探针 fallback 接入 runtime 字面量扫描 | `docs/records/rust-scope-index/batches/batch-044.md` |
| 6N | 旧插件源码扫描公共导出收束 | `docs/records/rust-scope-index/batches/batch-045.md` |
| 6O | 旧 scanner 主扫描本体私有化 | `docs/records/rust-scope-index/batches/batch-046.md` |
| 6P | 旧 scanner 测试夹具首组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-047.md` |
| 6Q | 旧 scanner 写回测试夹具第二组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-048.md` |
| 6R | 旧 scanner 规则排除测试夹具第三组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-049.md` |
| 6S | 旧 scanner 工作流/备份测试夹具第四组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-050.md` |
| 6T | AgentToolkit 规则输入测试夹具第五组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-051.md` |
| 6U | AgentToolkit 导入/质量/TextScope 测试夹具第六组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-052.md` |
| 6V | 剩余旧 scanner 残留夹具第七组 Rust-derived 替换与边界保护 | `docs/records/rust-scope-index/batches/batch-053.md` |
| 6W | feedback runtime 夹具第八组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-054.md` |
| 6X | workspace/write-plan/rule-import 夹具第九组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-055.md` |
| 6Y | 旧 scanner repo-wide 残留入口审计 | `docs/records/rust-scope-index/batches/batch-056.md` |
| 6Z | 共享 fixture legacy 导出收束 | `docs/records/rust-scope-index/batches/batch-057.md` |
| 6AA | 旧 scanner 语义测试首组 Rust-derived 替换 | `docs/records/rust-scope-index/batches/batch-058.md` |
| 6AB | 旧 scanner batch/cache 对照测试保留边界审计 | `docs/records/rust-scope-index/batches/batch-059.md` |
| 6AC | 旧 scanner 私有 helper 删除评估 | `docs/records/rust-scope-index/batches/batch-060.md` |
| 6AD | 旧 scanner 历史记录残留收尾审计 | `docs/records/rust-scope-index/batches/batch-061.md` |
| 6AE | 插件源码支线收束回归审计 | `docs/records/rust-scope-index/batches/batch-062.md` |

本阶段固定的关键入口：

- `build_native_plugin_source_scan`
- `build_native_plugin_source_ast_map_payload`
- `build_native_plugin_source_risk_report`
- `scan_native_rule_candidates`
- `scan_plugin_source_runtime_files_text_strict`

本阶段固定的关键目标测试：

- `test_scan_plugin_source_text_uses_native_candidate_scan`
- `test_export_plugin_source_ast_map_uses_native_candidate_scan`
- `test_validate_plugin_source_rules_uses_native_plugin_source_scan`
- `test_import_plugin_source_rules_uses_native_plugin_source_scan`
- `test_prepare_agent_workspace_reuses_plugin_source_scan_for_scope`
- `test_validate_agent_workspace_uses_native_plugin_source_scan_for_branch`
- `test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files`
- `test_plugin_source_write_probe_uses_batch_preview`
- `test_batch63_plugin_source_stage_records_cover_native_runtime_and_legacy_closure`
- `test_batch63_plugin_source_stage_closure_record_exists_and_tracks_contract`

## 旧路径收束

本阶段结论：插件源码默认生产支线已经收束到 Rust-derived 翻译源候选入口和 runtime 字面量入口；旧 scanner 生产主入口不再留在 `app/` 生产代码中。旧 scanner 历史名称只允许停留在历史记录和保护测试。

旧入口边界搜索纳入本批验证。

## 外部契约变化

无外部 CLI、Agent JSON、SQLite schema、Rust API、日志格式、目录结构、README、Skill 或发布流程变化。

## 性能证据

本批没有新增运行时扫描或数据库读取；性能证据来自阶段保护固定的事实来源：

- 翻译源插件源码候选、风险报告、AST 地图和规则链路使用 `scan_native_rule_candidates`。
- 当前运行插件源码审计、runtime scan cache 和写回探针 fallback 使用 `scan_plugin_source_runtime_files_text_strict`。
- 阶段保护确认这些入口仍被既有目标行为测试覆盖。

## 验证结果

本批属于 P1-B 插件源码阶段收束，按临时验证策略执行全量 `uv run pytest`。

已执行：

```powershell
uv run pytest tests/test_scan_budget.py::test_batch63_plugin_source_stage_records_cover_native_runtime_and_legacy_closure tests/test_scan_budget.py::test_batch63_plugin_source_stage_closure_record_exists_and_tracks_contract
```

结果：2 passed。

```powershell
uv run pytest tests/test_scan_budget.py
```

结果：82 passed。

```powershell
uv run pytest
```

结果：842 passed in 366.22s。

```powershell
uv run basedpyright
```

结果：0 errors, 0 warnings, 0 notes。

文档敏感路径和占位文案搜索：无命中。

生产代码旧入口精确搜索：覆盖旧无下划线主扫描、旧翻译源 strict 入口以及旧 helper 名称，结果无命中。

repo 旧名称搜索仍命中历史记录和保护测试；这些命中由 batch61 和本批保护固定为允许范围。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理辅助复核 6B 到 6AE 的记录链、关键入口和下一阶段建议。子代理未修改文件、未运行 pytest；其结论确认 batch-33 到 batch-62 记录连续存在，`app/` 下没有旧插件源码扫描生产入口残留。最终收束以本地测试和验证命令输出为准。

## 剩余风险

本批是阶段收束保护，不新增生产功能。剩余风险是下一阶段进入非标准 data 或其他 P1-B 热路径后，需要重新建立该支线自己的入口矩阵和动态行为回归，不能复用插件源码阶段结论作为其他支线的完成证据。

## 下一批入口

建议下一批进入 P1-B 非标准 data 支线入口审计：先梳理非标准 data 候选扫描、规则校验、工作区和质量报告的现有事实来源，再确定是否需要 Rust 候选入口、记录保护和目标行为回归。
