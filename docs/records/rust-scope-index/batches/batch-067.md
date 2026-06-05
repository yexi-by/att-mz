# Rust Scope/Index Engine 批次 6AJ 验收记录

## 本批范围

本批推进非标准 data 已导入规则提取链路 native leaves 复用。范围限定为 `text-scope`、写回输入提取和当前运行审计三条已导入规则链路，把 JSON 叶子枚举事实切到 Rust `scan_rule_candidates(nonstandard_data_leaves)` 分支。旧 `resolve_nonstandard_data_leaves` 作为 scanner 内部兼容能力保留，不在本批删除。

## 保护网

- `tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_nonstandard_data_leaves` 固定 leaves-only native 契约：不需要 `text_rules`，不产出候选，只返回每个非标准 data 文件的 leaves 摘要。
- `tests/test_nonstandard_data.py::test_nonstandard_data_text_scope_uses_native_leaves_for_imported_rules` 禁用提取模块旧 Python leaf resolver 后，统一文本清单仍能包含已导入规则命中的非标准 data 文本。
- `tests/test_nonstandard_data.py::test_nonstandard_data_write_back_extraction_uses_native_leaves` 禁用提取模块旧 Python leaf resolver 后，写回输入仍能定位已管理 JSON 字符串叶子。
- `tests/test_nonstandard_data.py::test_active_runtime_audit_uses_native_nonstandard_data_leaves` 禁用当前运行审计模块旧 Python leaf resolver 后，active runtime audit 仍能统计已管理路径。
- `tests/test_scan_budget.py::test_batch67_nonstandard_data_imported_rule_leaves_use_native_entry` 和 `tests/test_scan_budget.py::test_batch67_nonstandard_data_imported_rule_leaves_record_exists_and_tracks_contract` 固定入口、旧路径收束和验收记录边界。

## 实现说明

- Rust `RuleCandidatesPayload` 新增 `nonstandard_data_leaves` 输入字段，`scan_rule_candidates` 在 `scan_summary["nonstandard_data_leaves"]` 返回文件级 leaves 摘要。
- Rust `nonstandard_data.rs` 新增 `scan_nonstandard_data_file_leaves`，复用同一 JSON walk 逻辑；候选扫描分支继续传入编译后的 `text_rules`，leaves-only 分支不要求 `text_rules`。
- Python `app/native_scope_index.py` 新增 `build_native_nonstandard_data_leaves_payload`。
- Python `app/nonstandard_data/scanner.py` 新增 `resolve_nonstandard_data_file_leaves_native`，把 native leaves 摘要还原为 `ResolvedLeaf`。
- `app/nonstandard_data/extraction.py` 的 `collect_rule_hits` 与 `extract_all_text` 改为按文件批量读取 native leaves。
- `app/nonstandard_data/runtime_audit.py` 的当前运行审计改为先批量展开 active 文件 native leaves，再按规则模板匹配已管理字符串叶子。

## 旧路径收束

`app/nonstandard_data/extraction.py` 和 `app/nonstandard_data/runtime_audit.py` 不再导入或调用 `resolve_nonstandard_data_leaves`。旧函数仍保留在 `app/nonstandard_data/scanner.py`，用于当前未迁移的兼容边界和后续删除评估。

## 外部契约变化

无 CLI 参数、配置字段、数据库 schema、JSON 规则导入格式或用户可见报告字段变化。本批新增的是 Rust/Python 内部 native scan payload 分支；公开非标准 data 规则导入、文本清单、写回和 active runtime audit 输出保持等价。

## 性能证据

已导入非标准 data 规则链路不再由 Python 递归枚举 JSON leaves，改为 Rust 原生入口统一展开。单个 `NonstandardDataTextExtraction` 实例内会按当前已加载文件批量调用 native leaves；当前文本清单构建中的 freshness check、正文提取和规则命中诊断仍可能分别实例化提取器，这是下一批需要继续收束的重复 native leaves scan 风险。

## 验证结果

- RED：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_nonstandard_data_leaves tests/test_nonstandard_data.py::test_nonstandard_data_text_scope_uses_native_leaves_for_imported_rules tests/test_nonstandard_data.py::test_nonstandard_data_write_back_extraction_uses_native_leaves tests/test_nonstandard_data.py::test_active_runtime_audit_uses_native_nonstandard_data_leaves tests/test_scan_budget.py::test_batch67_nonstandard_data_imported_rule_leaves_use_native_entry tests/test_scan_budget.py::test_batch67_nonstandard_data_imported_rule_leaves_record_exists_and_tracks_contract`，6 failed，失败点分别是缺少 `nonstandard_data_leaves`、已导入规则链路仍调用 Python resolver、批次记录缺失。
- GREEN：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_returns_nonstandard_data_leaves tests/test_nonstandard_data.py::test_nonstandard_data_text_scope_uses_native_leaves_for_imported_rules tests/test_nonstandard_data.py::test_nonstandard_data_write_back_extraction_uses_native_leaves tests/test_nonstandard_data.py::test_active_runtime_audit_uses_native_nonstandard_data_leaves tests/test_scan_budget.py::test_batch67_nonstandard_data_imported_rule_leaves_use_native_entry tests/test_scan_budget.py::test_batch67_nonstandard_data_imported_rule_leaves_record_exists_and_tracks_contract`，6 passed。
- `uv run maturin develop`，Rust 原生扩展构建并安装成功。
- `uv run pytest tests/test_nonstandard_data.py tests/test_native_scope_index.py`，32 passed。
- `uv run pytest tests/test_scan_budget.py`，90 passed。
- `uv run basedpyright`，0 errors，0 warnings，0 notes。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`，通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`，通过。
- `cargo test --manifest-path rust/Cargo.toml`，71 passed。
- `uv run pytest`，858 passed。

## 审查处理

本批未进入外部 PR 审查。实现中处理了 Rust clippy 提示的嵌套 `if let`，折叠为 let-chain，不改变行为。

## 剩余风险

已导入规则链路的 JSON leaves 枚举已从 Python 切到 Rust，但文本清单构建中 freshness check、正文提取和规则命中诊断仍可能各自触发 native leaves scan。该重复扫描已低于旧 Python 递归扫描风险，但仍属于可继续收束的性能边界。

## 下一批入口

建议下一批进入非标准 data 已导入规则链路重复 native leaves 扫描收束审计：先固定 `TextScopeService.build` 内 freshness check、正文提取和规则命中诊断不会为同一批非标准 data 文件重复展开 leaves，再决定是否引入单次构建级 leaves 事实复用。
