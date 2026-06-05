# Rust Scope/Index Engine 批次 72 验收记录

## 本批范围

本批是 6AO：普通占位符 Rust 候选入口最小契约。范围只建立 `scan_rule_candidates(placeholders)` 的 native 候选入口，不接入 `scan-placeholder-candidates`、`validate-placeholder-rules`、`build-placeholder-rules` 或 `import-placeholder-rules` 的服务层流程。

本批新增 Python bridge `build_native_placeholder_candidates_payload`，把当前 `TranslationData` 的正文原文行压成 `placeholder_texts`，并复用 `build_native_rule_candidate_text_rules_payload(text_rules)` 传入普通占位符规则。

## 保护网

新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_placeholder_candidates`，固定 native 入口必须等价产出普通占位符候选明细：

- 明细字段保持旧 Python 报告形状：`marker`、`count`、`sources`、`standard_covered`、`custom_covered`、`covered`。
- 标准 RMMZ 控制符完整覆盖时标记 `standard_covered=true`。
- 自定义规则重叠覆盖时标记 `custom_covered=true`。
- 未覆盖候选按来源行聚合，并保留 `location_path#line_index` 来源。
- 聚合明细放在 `scan_summary["placeholders"]["candidates"]`，不伪造成逐位置 `RuleCandidateOutput`。

新增 `tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists` 和 `tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_record_exists_and_tracks_contract`，固定 Python bridge、Rust `placeholders` 分支、低层 raw candidate 暴露、计划索引和本批记录。

## 实现说明

Python 侧新增 `app/native_scope_index.py::build_native_placeholder_candidates_payload`：

- 输入仍是 `translation_data_map` 与 `TextRules`。
- 输出字段是 `placeholder_texts` 和 `text_rules`。
- `placeholder_texts` 只包含 `source_name` 与 `text`，避免把正文条目的数据库、写回或文件内部细节带进 native 候选入口。

Rust 侧新增 `rust/src/native_core/scope_index/placeholders.rs`：

- 使用现有 `iter_raw_control_sequence_candidates` 扫描疑似控制符。
- 使用现有 `iter_control_sequence_spans` 判断标准、自定义和结构化保护片段。
- 聚合逻辑保持旧 Python `scan_placeholder_candidates` 语义：标准必须完整覆盖；非标准保护片段按重叠取 marker；只有 custom 覆盖计入 `custom_covered`，structured 不计入普通占位符 covered。
- 候选排序按 `(standard_covered, custom_covered, marker.lower())`，同 key 时保留首次出现顺序；`sources` 使用字符串升序。
- 使用 Rayon 对输入文本行并行扫描，再按输入顺序聚合，避免把大规模文本扫描留在 Python。

Rust `controls.rs` 只把既有 `iter_raw_control_sequence_candidates` 和 `RawControlSequenceCandidate` 改为 `pub(crate)`，没有复制正则或新增第二套 raw candidate 规则。

## 旧路径收束

本批不删除 `app/agent_toolkit/placeholder_scan.py`，也不改变普通占位符四个公开命令的服务层事实来源。旧 Python scanner 暂时保留为服务、覆盖报告、规则校验、规则草稿和工作区流程的当前入口。

本批收束的是 native 边界缺口：scan budget 指向的 `Rust scan_rule_candidates(placeholders)` 已有最小可测入口，下一批可以把扫描命令薄适配到该入口，再逐步迁移覆盖报告和规则导入链路。

## 外部契约变化

没有 CLI 参数、stdout JSON、数据库 schema、配置字段、README 或 Skill 契约变化。

新增内部 native JSON 契约：

- 输入：`placeholder_texts: [{"source_name": "...", "text": "..."}]`
- 输入：`text_rules` 沿用现有规则候选扫描 payload。
- 输出：`scan_summary["placeholders"]` 包含 `candidate_count`、`covered_count`、`uncovered_count`、`standard_covered_count`、`custom_covered_count`、`scanned_text_count` 和 `candidates`。
- 输出：`candidate_summary` 增加 `{"domain": "placeholders", "candidate_count": N}`。

## 性能证据

本批把普通占位符候选扫描的可迁移重活放入 Rust：raw candidate 扫描、控制符覆盖判断和候选聚合都在 native 分支内完成。Rust 扫描输入行使用 Rayon 并行处理，Python bridge 只做线性载荷组装。

目标测试覆盖两行正文输入、标准覆盖、自定义覆盖和未覆盖候选聚合。下一批接入命令时需要继续验证 warm text index 复用，避免服务层重复构建完整文本范围。

## 验证结果

- RED：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_placeholder_candidates tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_record_exists_and_tracks_contract`，1 error；失败点是 `app.native_scope_index` 缺少 `build_native_placeholder_candidates_payload`。
- GREEN 入口：`uv run maturin develop`，通过。
- GREEN 目标：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_placeholder_candidates tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists`，2 passed。
- GREEN 记录保护：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_placeholder_candidates tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_record_exists_and_tracks_contract`，3 passed。
- 6AN/6AO 静态回归：`uv run pytest tests/test_scan_budget.py::test_batch71_placeholder_entry_audit_classifies_current_python_scan_paths tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_placeholder_candidates tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_entry_contract_exists tests/test_scan_budget.py::test_batch72_placeholder_native_candidate_record_exists_and_tracks_contract`，4 passed。
- 类型检查：`uv run basedpyright`，0 errors，0 warnings，0 notes。
- Python 全量测试：首轮 `uv run pytest` 为 869 passed、1 failed；失败原因是 6AN 历史断言精确匹配了带反引号的旧记录文本。修正为 marker 组合后，第二轮 `uv run pytest` 为 870 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`，71 passed。
- 文档敏感路径/占位文案搜索：使用 `rg -n` 检查当前开发记录、superpowers 计划、README 和 skills 中的本机路径、用户名和未回填验收占位文案，无命中。
- 空白差异检查：`git diff --check`，通过；仅输出仓库既有 LF/CRLF 换行提示。

## 审查处理

本批使用只读子代理复核普通占位符 native schema。子代理指出普通占位符候选是按 `marker` 聚合的覆盖报告，不应伪造成逐位置 `RuleCandidateOutput`。最终实现采纳该建议：明细放入 `scan_summary["placeholders"]["candidates"]`，`candidate_summary` 只记录 domain 计数。

子代理还提醒 structured 覆盖不能算作普通占位符 covered，本批实现保持该语义。

## 剩余风险

本批只建立 native 最小入口，普通占位符公开命令尚未消费该入口。后续接入时仍需保护：

- `scan-placeholder-candidates` 的报告字段、warning 文案和候选 scope hash 稳定性。
- `validate-placeholder-rules` 与 `import-placeholder-rules` 的 empty-rule 审查、规则保存事务和确认哈希。
- `build-placeholder-rules` 的草稿预览与手动边界警告。
- 工作区和 workflow gate 的 warm text index 复用，避免重复全量扫描。

## 下一批入口

建议下一批进入普通占位符扫描命令薄适配接入：先让 `scan-placeholder-candidates` 的只读候选扫描复用 `build_native_placeholder_candidates_payload` 与 `scan_rule_candidates(placeholders)`，并用现有 `test_scan_placeholder_candidates_uses_warm_text_index_without_full_scope_build`、`test_scan_placeholder_candidates_marks_custom_rule_coverage` 和 native 等价测试共同保护外部报告不漂移。
