# Rust Scope/Index Engine 批次 6AI 验收记录

## 本批范围

本批是非标准 data 规则校验覆盖统计 native 化。范围限定为把 `validate_nonstandard_data_rules` 中的路径模板命中、候选覆盖、排除重叠、跳过文件和未归类候选统计迁入统一 `scan_rule_candidates` native 入口。

本批涉及：

- `rust/src/native_core/scope_index/mod.rs`
- `rust/src/native_core/scope_index/nonstandard_data.rs`
- `app/nonstandard_data/rules.py`
- `tests/test_native_scope_index.py`
- `tests/test_nonstandard_data.py`
- `tests/test_scan_budget.py`

## 保护网

新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_evaluates_nonstandard_data_rule_coverage`：

- 固定 `scan_rule_candidates` 支持 `nonstandard_data_rule_coverage` 输入。
- 固定 native 覆盖统计输出 `rules`、`translated_candidates`、`excluded_candidates`、`skipped_files`、`unreviewed_candidates` 和 `reviewed_candidate_count`。
- 固定 wildcard 路径模板可匹配字符串叶子，并只统计命中的候选路径。

新增 `tests/test_nonstandard_data.py::test_nonstandard_data_rules_validate_uses_native_rule_coverage`：

- 固定 `validate_nonstandard_data_rules` 调用 `scan_native_rule_candidates`。
- 固定 native payload 包含 `nonstandard_data_rule_coverage`。
- 固定验证结果仍返回现有 `NonstandardDataRuleValidationResult` 和 Agent 报告详情字段。

新增 `tests/test_scan_budget.py::test_batch66_nonstandard_data_rule_coverage_uses_native_entry`：

- 固定 `app/nonstandard_data/rules.py` 依赖 `scan_native_rule_candidates` 和 `nonstandard_data_rule_coverage`。
- 固定规则层不再引用 `expand_rule_to_leaf_paths`。
- 固定 Rust 侧存在 `scan_nonstandard_data_rule_coverage`。

新增 `tests/test_scan_budget.py::test_batch66_nonstandard_data_rule_coverage_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定本批验证命令、外部契约结论、剩余风险和下一批入口。

RED 证据：

```powershell
uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_evaluates_nonstandard_data_rule_coverage tests/test_nonstandard_data.py::test_nonstandard_data_rules_validate_uses_native_rule_coverage tests/test_scan_budget.py::test_batch66_nonstandard_data_rule_coverage_uses_native_entry tests/test_scan_budget.py::test_batch66_nonstandard_data_rule_coverage_record_exists_and_tracks_contract
```

结果：4 failed。失败原因分别是 Rust `scan_summary` 尚未包含 `nonstandard_data_rule_coverage`、Python 规则层仍调用 Python 路径模板展开、规则层尚未接入 native 入口、batch66 记录尚不存在。

## 实现说明

Rust 侧在 `RuleCandidatesPayload` 中新增 `nonstandard_data_rule_coverage` 输入，并在 `scan_rule_candidates` 中调用 `scan_nonstandard_data_rule_coverage`。该分支消费上一批 native scan 已产出的 leaves/candidates 结构，不重新读取或扫描非标准 data 文件。

native 覆盖统计负责：

- 解析受限 JSONPath 模板。
- 展开字符串叶子路径。
- 统计 `paths` 和 `excluded_paths` 命中的候选。
- 检查翻译路径和排除路径重叠。
- 统计跳过文件和未归类候选。
- 输出与当前 Python 报告详情兼容的覆盖明细。

Python 侧 `validate_nonstandard_data_rules` 保留规则 JSON 解析、pydantic 校验、错误文案组装和 `NonstandardDataRuleValidationResult` 结构；覆盖统计本身改由 native 结果还原。`import_nonstandard_data_rules` 继续复用同一个验证结果生成数据库记录。

## 旧路径收束

本批从 `app/nonstandard_data/rules.py` 删除 Python `expand_rule_to_leaf_paths` 依赖和 `_collect_rule_hits` 旧覆盖统计路径，避免规则校验阶段形成第二套路径展开事实。

`resolve_nonstandard_data_leaves` 仍被已导入规则的文本提取、写回和运行时审计使用；这不属于本批范围。

## 外部契约变化

无 CLI 参数、Agent JSON、SQLite schema、日志格式、目录结构、README、Skill 或发布流程变化。

`validate-nonstandard-data-rules` 和 `import-nonstandard-data-rules` 的用户可见 summary/details 字段保持不变。Rust/Python 内部 native payload 新增 `nonstandard_data_rule_coverage` 字段，这是内部结构化契约变化。

## 性能证据

本批把规则覆盖统计中的路径模板展开和候选覆盖判断迁入 Rust native 入口。Python 规则层不再执行 `expand_rule_to_leaf_paths`，只组装 native 输入和解析 native 输出。

## 验证结果

本批修改生产代码、跨模块 native 契约和 Rust 原生代码，按临时验证策略执行全量 `uv run pytest` 与 Rust 门禁。

已执行：

```powershell
uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_evaluates_nonstandard_data_rule_coverage tests/test_nonstandard_data.py::test_nonstandard_data_rules_validate_uses_native_rule_coverage tests/test_scan_budget.py::test_batch66_nonstandard_data_rule_coverage_uses_native_entry tests/test_scan_budget.py::test_batch66_nonstandard_data_rule_coverage_record_exists_and_tracks_contract
```

结果：4 passed。

```powershell
uv run pytest tests/test_nonstandard_data.py
```

结果：19 passed。

```powershell
uv run pytest tests/test_native_scope_index.py
```

结果：9 passed。

```powershell
uv run pytest tests/test_scan_budget.py
```

结果：88 passed。

```powershell
uv run basedpyright
```

结果：0 errors, 0 warnings, 0 notes。

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
```

结果：通过。

```powershell
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

结果：通过。

```powershell
cargo test --manifest-path rust/Cargo.toml
```

结果：71 passed。

```powershell
uv run pytest
```

结果：852 passed in 248.67s。

文档敏感路径和占位文案搜索：无命中。

非标准 data coverage native 入口搜索：命中 `nonstandard_data_rule_coverage`、`scan_nonstandard_data_rule_coverage`、`scan_native_rule_candidates` 和本批保护测试；结果与本批实现边界一致。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批未使用写入型子代理；实现边界沿用上一批只读审计和 batch65 剩余风险：规则校验覆盖统计应复用 native candidates/leaves，不重新形成 Python 路径展开事实。

## 剩余风险

已导入非标准 data 规则进入统一文本清单、写回和运行时审计时，仍会按当前文件重新展开 leaves；这部分属于已确认规则的文本提取链路，不属于本批规则导入校验范围。下一批需要评估该链路是否能复用 native leaves 或迁入同一 native 入口。

## 下一批入口

建议下一批进入非标准 data 已导入规则提取链路 native leaves 复用：先为 text-scope、write-back 和 active runtime audit 建立 RED，证明这些路径不再单独调用 Python `resolve_nonstandard_data_leaves` 构建第二套叶子事实。
