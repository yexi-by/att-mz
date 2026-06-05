# Rust Scope/Index Engine 批次 6AZ 验收记录

## 本批范围

本批建立结构化占位符 Rust 候选入口最小契约，范围限于 Python native payload、Rust `scan_rule_candidates` 分支、目标测试、scan budget 记录保护和计划索引。

本批触及以下生产代码：

- `app/native_scope_index.py`
- `rust/src/native_core/scope_index/mod.rs`
- `rust/src/native_core/scope_index/structured_placeholders.rs`

本批不迁移 `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates`、`import-structured-placeholder-rules` 的 service、workflow gate 或 workspace 消费路径。

## 保护网

新增 `tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules`：

- 固定 `build_native_structured_placeholder_candidates_payload` 会从 `translation_data_map` 输出 `structured_placeholder_texts`。
- 固定每条文本携带 `location_path`、`line_number` 和 `text`。
- 固定 payload 复用 `build_native_rule_candidate_text_rules_payload`，并携带 `structured_placeholder_rules`。

新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates`：

- 固定 `scan_native_rule_candidates` 接受 `structured_placeholder_texts`。
- 固定 `scan_summary["structured_placeholders"]` 返回 `candidate_count`、`candidates`、`covered_count`、`uncovered_count` 和 `scanned_text_count`。
- 固定候选项字段为 `location_path`、`line_number`、`candidate`、`covered` 和 `matching_rules`。
- 固定 `candidate_summary` domain 为 `structured_placeholders`。

新增 `tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists`：

- 固定计划表链接本批记录。
- 固定 batch 82 下一批入口指向本批。
- 固定 `app/native_scope_index.py` 导出 `build_native_structured_placeholder_candidates_payload`。
- 固定 Rust 结构化候选模块存在，并接入 `scope_index/mod.rs`。

新增 `tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_record_exists_and_tracks_contract`：

- 固定本记录章节、关键路径、验证命令和下一批入口。
- 固定文档不写入本机路径、私有用户名和未完成占位文案。

RED 证据：

```powershell
uv run pytest tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates
```

结果：2 failed。失败点分别是 `app.native_scope_index` 缺少 `build_native_structured_placeholder_candidates_payload`，以及 Rust scan summary 缺少 `structured_placeholders`。

```powershell
uv run pytest tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_record_exists_and_tracks_contract
```

结果：2 failed。失败点分别是计划表缺少 `docs/records/rust-scope-index/batches/batch-083.md`，以及本批记录不存在。

## 实现说明

`app/native_scope_index.py` 新增 `build_native_structured_placeholder_candidates_payload`。该函数只负责把当前已加载的 `TranslationData` 文本行转换为 Rust 输入，不主动加载游戏数据，也不执行候选扫描。

Rust 新增 `rust/src/native_core/scope_index/structured_placeholders.rs`，提供 `scan_structured_placeholder_rule_candidates`。该分支复用结构化规则编译与 `iter_structured_placeholder_spans` 的冲突校验能力，再按 `STRUCTURED_SHELL_CANDIDATE_PATTERNS` 扫描 shell 候选，并输出结构化候选明细。

`rust/src/native_core/scope_index/mod.rs` 新增可选输入 `structured_placeholder_texts`。调用方传入该字段时，Rust 会写入 `scan_summary["structured_placeholders"]`，并把候选数量计入 `candidate_summary`。

本批只建立 native 契约入口。`validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates` 和 `import-structured-placeholder-rules` 仍由下一批再接入 native 薄适配。

## 旧路径收束

本批没有删除 Python service、workflow gate 或 workspace 的结构化候选扫描路径。当前仍保留以下生产事实来源，等待下一批迁移：

- `app/agent_toolkit/services/common.py` 的结构化候选覆盖报告。
- `app/application/flow_gate.py` 的结构化候选覆盖结果。
- `app/agent_toolkit/services/workspace.py` 的工作区结构化规则校验。

本批新增 Rust 入口后，旧路径已经具备可迁移目标；但旧路径删除必须等待对应命令和工作区路径先切到 native 输出。

## 外部契约变化

Rust 原生 JSON 输入契约新增可选字段 `structured_placeholder_texts`。Rust 原生 JSON 输出契约新增可选 summary domain `structured_placeholders`。

本批不改变 CLI 参数、stdout JSON、数据库 schema、配置字段、README、Skill 或发布流程。

## 性能证据

本批把结构化占位符候选扫描的候选提取和规则覆盖判断移入 Rust native 分支。Rust 侧返回 `scanned_text_count`，用于固定实际扫描文本行数量；候选数量进入 `candidate_summary`，用于后续命令层复用和预算保护。

由于本批尚未迁移 service/CLI 消费路径，公开命令仍会走 Python 候选扫描。下一批接入 native 薄适配后，才会把公开命令的结构化候选事实来源切换到 `scan_rule_candidates(structured_placeholders)`。

## 验证结果

- RED native 目标测试：`uv run pytest tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates`，2 failed。
- RED scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_record_exists_and_tracks_contract`，2 failed。
- 本地扩展重建：`uv run maturin develop --release`，通过。
- GREEN native 目标测试：`uv run pytest tests/test_native_scope_index.py::test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_structured_placeholder_candidates`，2 passed。
- GREEN scan_budget/记录保护：`uv run pytest tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_record_exists_and_tracks_contract`，2 passed。
- 历史审计保护修正：`uv run pytest tests/test_scan_budget.py::test_batch82_structured_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch83_structured_placeholder_native_candidate_record_exists_and_tracks_contract`，3 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- Rust 自测：`cargo test --manifest-path rust/Cargo.toml`，71 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`，899 passed。
- 文档敏感路径/占位文案搜索：对 `docs/wiki/development`、`docs/plans`、`README.md` 和 `skills` 执行本机路径与未完成占位文案搜索，结果 `NO_MATCH`。
- Diff 空白检查：`git diff --check`，exit 0；Git 仅提示工作树多文件行尾转换 warning，未报告空白错误。
- 本批修改生产 Python 和 Rust 原生代码，因此已按临时策略执行全量 `uv run pytest`。

## 审查处理

本批使用只读子代理复核结构化候选 Python schema、Rust 普通 placeholder 分支模式、最小契约字段和不应触碰的路径。子代理未修改文件，结论确认本批应只新增 `build_native_structured_placeholder_candidates_payload`、`structured_placeholder_texts`、`scan_structured_placeholder_rule_candidates` 和目标测试，不提前迁移 service、workflow gate、workspace 或 CLI。

本地实现采纳该边界：结构化候选输出保持 `location_path`、`line_number`、`candidate`、`covered`、`matching_rules` 明细形状；`covered` 语义为结构化规则完整匹配范围覆盖 shell 候选范围。

## 剩余风险

当前 `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates` 和 `import-structured-placeholder-rules` 仍未消费新 native 分支。公开命令层仍存在 Python 结构化候选扫描事实来源，下一批需要用 native 薄适配收束。

结构化占位符 native 入口不能外推到 Note 标签、事件指令、插件参数、MV 虚拟名字框和源文残留规则链；这些 P1-B 支线仍需要独立批次审计与迁移。

## 下一批入口

建议下一批进入结构化占位符扫描命令 native 薄适配接入：让 `scan-structured-placeholder-candidates` 和相关覆盖报告优先消费 `scan_native_rule_candidates` 的 `structured_placeholders` 明细，同时继续保护 `validate-structured-placeholder-rules` 与 `import-structured-placeholder-rules` 的候选 hash 语义。
