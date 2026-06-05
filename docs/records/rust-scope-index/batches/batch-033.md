# Rust Scope/Index Engine 批次 33 记录

## 本批范围

- 批次：6B，插件源码候选扫描 Rust 入口。
- 覆盖入口：Rust `scan_rule_candidates` 原生入口、Python `scan_native_rule_candidates` 适配层和 native contract 版本。
- 成功状态：`scan_rule_candidates` 可以接收 `plugin_source_files` 与提取用 `text_rules`，直接从插件源码生成 `plugin_source` 候选、候选摘要和 `scan_summary.plugin_source`；旧的传入候选汇总行为保持可用。

## 保护网

- 新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`：
  - 输入启用、禁用和 JS 语法错误的插件源码文件。
  - 断言 Rust 入口返回 `plugin_source` 候选、`selector`、`location_path`、`active`、`confidence` 和候选摘要。
  - 断言 `scan_summary.plugin_source` 包含 `candidate_count`、`active_candidate_count`、`scanned_file_count`、`ignored_file_count` 和 `syntax_error_file_count`。
- 新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_decodes_plugin_source_unicode_escapes`：
  - 断言插件源码中的 `\uXXXX` 和 `\u{...}` JS Unicode 转义会还原成可翻译文本候选。
- 新增 `tests/test_native_scope_index.py::test_scan_native_rule_candidates_requires_plugin_source_active_flag`：
  - 断言 `plugin_source_files[].active` 缺失时显式报错，避免启用状态被静默当成禁用。
- 新增 `tests/test_native_adapters.py::test_native_rule_candidates_requires_scan_summary`：
  - 断言 native contract 5 的 `scan_summary` 缺失时 Python 适配层必须报错。
- 新增 `tests/test_scan_budget.py::test_batch33_plugin_source_native_candidate_record_exists_and_tracks_contract`：
  - 断言本记录被计划文件链接。
  - 断言记录包含 `plugin_source_files`、`scan_summary`、`NATIVE_CONTRACT_VERSION = 5` 和新增测试名。

## 改动范围

- `rust/src/native_core/scope_index/mod.rs`
  - `RuleCandidatesPayload` 新增可选 `plugin_source_files` 和 `text_rules`。
  - Rust AST 扫描器从插件源码字符串节点生成 `plugin_source` 候选。
  - 候选保留 `selector`、`text`、`raw_text`、`line`、AST 上下文、启用状态、置信度和源码 hash。
  - 返回 `scan_summary.plugin_source`，为后续 Python 薄报告层提供候选计数和文件状态摘要。
- `rust/src/native_core/write_back_plan/mod.rs`
  - 重导出插件源码 selector、JS 文本解码和可见文本规范化辅助函数，避免 Scope/Index 与写回使用两套定位规则。
- `rust/src/native_core/write_back_plan/plugin_source.rs`
  - 将 `candidate_selector_for_span`、`unescape_js_text`、`normalize_visible_text_for_extraction` 提升为 `native_core` 内部可复用函数。
  - `unescape_js_text` 补齐 `\xHH`、`\uXXXX` 和 `\u{...}` 解码，保持与旧 Python 插件源码扫描器一致。
- `app/native_scope_index.py`
  - `NativeRuleCandidatesResult` 新增并强制读取 `scan_summary`。
- `app/native_contract.py` 与 `rust/src/lib.rs`
  - `NATIVE_CONTRACT_VERSION = 5`，旧扩展不会静默吞掉新输入。

## 旧路径收束

- 本批没有切换 `scan-plugin-source-text`、`export-plugin-source-ast-map`、`validate-plugin-source-rules` 或 `import-plugin-source-rules` 的 Python 报告/事务入口。
- Python `build_plugin_source_scan` 仍是这些命令的主路径；本批只建立可复用的 Rust 候选事实入口。
- 下一批应把 `scan-plugin-source-text` 的候选来源改成 `scan_rule_candidates(plugin_source)`，Python 只保留报告渲染和 CLI 输出。

## 外部契约变化

- `scan_rule_candidates` 继续支持旧 payload：
  - `candidates`: 已构造候选数组。
- `scan_rule_candidates` 新增可选 payload：
  - `plugin_source_files`: `{file_name, source, active}` 数组；`active` 必填。
  - `text_rules`: 插件源码提取判断所需规则，包括 `source_text_required_pattern`、`source_text_exclusion_profile`、`strip_wrapping_punctuation_pairs`、`custom_placeholder_rules` 和 `structured_placeholder_rules`。
- 输出新增：
  - `scan_summary`: 当前包含 `plugin_source` 摘要。
- native contract 版本从 4 提升到 5。

## 性能证据

- 插件源码候选扫描在 Rust 内部复用 `tree-sitter-javascript` 字符串节点扫描。
- 多文件扫描按文件名稳定排序后使用 `rayon` 并行执行，并受项目既有 Rust 线程配置入口约束。
- 本批尚未切换 CLI 命令，因此不记录 `scan-plugin-source-text` 改造前后耗时；命令级耗时应在下一批接入 Python 薄报告层后补充。

## 验证结果

- RED：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`
  - 结果：1 failed，失败原因为候选集合为空，证明旧 Rust 入口不会扫描 `plugin_source_files`。
- RED 校正后复跑同一命令：
  - 结果：1 failed，仍失败于候选集合为空。
- 构建：`uv run maturin develop --manifest-path rust/Cargo.toml`
  - 结果：通过，已安装 native contract 5 的本地扩展。
- GREEN：`uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_scans_plugin_source_files`
  - 结果：1 passed。
- 局部回归：`uv run pytest tests/test_native_scope_index.py`
  - 结果：5 passed。
- 审查回归 RED：
  - `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_decodes_plugin_source_unicode_escapes`：1 failed，失败原因为 Unicode 转义文本没有进入候选。
  - `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_requires_plugin_source_active_flag`：1 failed，失败原因为缺失 `active` 没有报错。
  - `uv run pytest tests/test_native_adapters.py::test_native_rule_candidates_requires_scan_summary`：1 failed，失败原因为缺失 `scan_summary` 被 Python 兜底成空对象。
- 审查回归 GREEN：
  - `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_decodes_plugin_source_unicode_escapes`：1 passed。
  - `uv run pytest tests/test_native_scope_index.py::test_scan_native_rule_candidates_requires_plugin_source_active_flag`：1 passed。
  - `uv run pytest tests/test_native_adapters.py::test_native_rule_candidates_requires_scan_summary`：1 passed。
- 本批相关契约组：`uv run pytest tests/test_native_scope_index.py tests/test_native_adapters.py::test_native_rule_candidates_requires_scan_summary tests/test_scan_budget.py::test_batch33_plugin_source_native_candidate_record_exists_and_tracks_contract`
  - 结果：9 passed。
- 类型检查：`uv run basedpyright`
  - 结果：0 errors，0 warnings，0 notes。
- 全量 Python 测试：`uv run pytest`
  - 结果：778 passed。
- Rust 格式检查：`cargo fmt --manifest-path rust/Cargo.toml -- --check`
  - 结果：通过。
- Rust 静态检查：`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
  - 结果：通过。
- Rust 测试：`cargo test --manifest-path rust/Cargo.toml`
  - 结果：71 passed。
- diff 空白检查：`git diff --check`
  - 结果：通过；仅输出 Windows 换行提示。
- 文档敏感路径扫描：使用保护测试中的敏感路径和未完成占位文案模式扫描本批记录与计划文件。
  - 结果：无匹配。

## 审查处理

- 已请求只读代码审查，审查未发现 Critical 问题。
- Important 1：Rust 候选扫描未解码 `\uXXXX`、`\u{...}` 等 JS Unicode 转义，可能漏掉旧 Python 扫描器能识别的候选。已补测试并修复 `unescape_js_text`。
- Important 2：Python 适配层对 `scan_summary` 使用空对象兜底，可能吞掉 contract 5 输出缺失。已补测试并改为强制读取。
- Important 3：`plugin_source_files[].active` 缺失时默认 `false`，可能把启用插件静默当成禁用。已补测试并改为必填字段。
- Minor：本节原先写着等待审查。已更新为真实审查处理结果。

## 剩余风险

- `scan-plugin-source-text` 等 CLI/Agent 命令仍未消费新 Rust 候选入口，旧 Python 扫描主路径还没有删除。
- Rust 入口已经返回候选和摘要，但完整 AST map 文件、风险报告对象和规则导入覆盖统计仍需下一批逐步迁移。
- 英文源语言项目的 `source_text_exclusion_profile = english_protocol_noise` 已按现有 Python 规则迁入核心判断，但命令级回归需要在接入报告层时继续覆盖。

## 下一批入口

- 建议下一批：6C `scan-plugin-source-text` 薄适配接入。把 CLI/Agent 的候选来源改为 `scan_rule_candidates(plugin_source)`，Python 仅负责读取游戏文件、传入 `plugin_source_files`、渲染风险报告和输出 Agent JSON。
