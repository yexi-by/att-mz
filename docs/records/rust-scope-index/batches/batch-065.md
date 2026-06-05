# Rust Scope/Index Engine 批次 6AH 验收记录

## 本批范围

本批是非标准 data Rust 候选入口最小契约。范围限定为把非标准 data 候选筛选和叶子展开接入统一 `scan_rule_candidates` native 入口，并保持 `build_nonstandard_data_scan`、`NonstandardDataScan` 和 `nonstandard-data/candidates.json` 的现有外部字段不变。

本批涉及：

- `rust/src/native_core/scope_index/mod.rs`
- `rust/src/native_core/scope_index/nonstandard_data.rs`
- `app/native_scope_index.py`
- `app/nonstandard_data/scanner.py`
- `tests/test_native_scope_index.py`
- `tests/test_nonstandard_data.py`
- `tests/test_scan_budget.py`

## 保护网

新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_nonstandard_data_files`：

- 固定 `scan_rule_candidates` 支持 `nonstandard_data_files` 结构化输入。
- 固定 Rust 返回 `domain == "nonstandard_data"`、`json_path`、`source_text`、`raw_text`、`field_name`、`sibling_field_names` 和 `parent_object_keys`。
- 固定 `candidate_summary` 和 `scan_summary["nonstandard_data"]` 的最小摘要字段。
- 固定 Rust 会展开 leaves，供 Python 规则校验继续使用。

新增 `tests/test_nonstandard_data.py::test_nonstandard_data_scan_uses_native_candidate_scan`：

- 固定 `build_nonstandard_data_scan` 只读取文件和组装公开对象，候选筛选通过 `scan_native_rule_candidates`。
- 固定 native payload 包含 `nonstandard_data_files` 和 `text_rules`。
- 固定返回候选、文件摘要和 leaves 与现有公开结构一致。

新增 `tests/test_scan_budget.py::test_batch65_nonstandard_data_native_candidate_entry_is_wired`：

- 固定 Python bridge 暴露 `build_native_nonstandard_data_candidates_payload`。
- 固定 scanner 主流程调用 `scan_native_rule_candidates`。
- 固定 Rust 入口存在 `nonstandard_data_files` 和 `scan_nonstandard_data_rule_candidates`。
- 固定本批目标测试存在。

新增 `tests/test_scan_budget.py::test_batch65_nonstandard_data_native_candidate_record_exists_and_tracks_contract`：

- 固定本记录和计划表链接。
- 固定本批验证命令、外部契约结论、剩余风险和下一批入口。

RED 证据：

```powershell
uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_nonstandard_data_files tests/test_nonstandard_data.py::test_nonstandard_data_scan_uses_native_candidate_scan tests/test_scan_budget.py::test_batch65_nonstandard_data_native_candidate_entry_is_wired tests/test_scan_budget.py::test_batch65_nonstandard_data_native_candidate_record_exists_and_tracks_contract
```

结果：4 failed。失败原因分别是 Rust 入口尚未识别 `nonstandard_data_files`、Python scanner 尚未调用 native 入口、Python bridge 尚未暴露非标准 data payload builder、batch65 记录尚不存在。

## 实现说明

Rust 侧在统一 `RuleCandidatesPayload` 中新增 `nonstandard_data_files` 输入，并新增 `scan_nonstandard_data_rule_candidates` 分支。该分支负责：

- 按文件名稳定排序。
- 递归展开 JSON leaves。
- 按字段名、布尔/null/数字字符串、资源路径和资源扩展名排除结构噪声。
- 复用现有候选文本规则编译、可见文本规范化、控制符剥离和源文识别。
- 返回候选列表、按 domain 汇总和 `scan_summary["nonstandard_data"]`。

Python 侧新增 `build_native_nonstandard_data_candidates_payload`，避免 `app/native_scope_index.py` 依赖 `app/nonstandard_data`。`build_nonstandard_data_scan` 保留文件 I/O 和公开 dataclass 组装，但候选和 leaves 均从 Rust/native 结果还原。

## 旧路径收束

本批删除 `build_nonstandard_data_scan` 主流程中的 Python 候选递归筛选调用；旧 `_iter_candidates_from_file`、`_walk_candidates` 和 Python 结构噪声判断已移除。

`resolve_nonstandard_data_leaves` 作为公开兼容入口暂时保留；当前生产扫描主流程不再调用它。下一批应评估规则校验覆盖统计是否仍需要 Python leaves 入口，并把覆盖统计进一步收敛到 native 结果。

## 外部契约变化

无 CLI 参数、Agent JSON、SQLite schema、日志格式、目录结构、README、Skill 或发布流程变化。

`nonstandard-data/candidates.json` 的外部字段保持为 `source_type`、`summary`、`files` 和 `candidates`；单个候选仍输出 `file`、`json_path`、`source_text`、`field_name`、`occurrence_count`、`samples_for_same_path`、`sibling_field_names` 和 `parent_object_keys`。

Rust/Python 内部 native payload 新增 `nonstandard_data_files` 字段，这是内部结构化契约变化。

## 性能证据

本批把非标准 data 候选筛选和 leaves 展开迁入 Rust native 入口，Python 不再递归筛选候选。由于本批修改生产代码和 Rust 原生代码，收尾执行全量 Python 测试和 Rust 门禁。

## 验证结果

本批修改生产代码、跨模块 native 契约和 Rust 原生代码，按临时验证策略执行全量 `uv run pytest` 与 Rust 门禁。

已执行：

```powershell
uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_nonstandard_data_files tests/test_nonstandard_data.py::test_nonstandard_data_scan_uses_native_candidate_scan tests/test_scan_budget.py::test_batch65_nonstandard_data_native_candidate_entry_is_wired tests/test_scan_budget.py::test_batch65_nonstandard_data_native_candidate_record_exists_and_tracks_contract
```

结果：4 passed。

```powershell
uv run pytest tests/test_nonstandard_data.py
```

结果：18 passed。

```powershell
uv run pytest tests/test_native_scope_index.py
```

结果：8 passed。

```powershell
uv run pytest tests/test_scan_budget.py
```

结果：86 passed。

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

结果：848 passed in 244.63s。

文档敏感路径和占位文案搜索：无命中。

非标准 data native 入口搜索：命中 `build_native_nonstandard_data_candidates_payload`、`scan_native_rule_candidates`、`nonstandard_data_files`、`scan_nonstandard_data_rule_candidates` 和本批保护测试；结果与本批实现边界一致。

```powershell
git diff --check
```

结果：通过；只输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理复核最小实现边界。子代理结论与本批实现一致：复用现有 `scan_rule_candidates` 入口，新增 `nonstandard_data_files` 输入分支；Python 保持公开返回结构和 `candidates.json` 外部字段不变。

## 剩余风险

非标准 data 规则校验覆盖统计仍由 Python 校验层消费 leaves 和规则文件完成；本批只把候选筛选与 leaves 展开迁入 native 入口。下一批需要评估并收束规则校验覆盖统计，避免校验阶段继续形成重型 Python 事实来源。

## 下一批入口

建议下一批进入非标准 data 规则校验覆盖统计 native 化：先为 `validate-nonstandard-data-rules` 和 `import-nonstandard-data-rules` 建立 RED，证明覆盖统计复用本批 native leaves/candidates 结果，不重新构建第二套 Python 扫描事实。
