# Rust 主路径收束专项 Review 总报告

## 执行摘要

结论：FAIL。

本轮按 `docs/superpowers/plans/2026-06-10-rust-primary-refactor-review-execution.md` 执行了只读 review。轨道 01 到 06 使用子代理并发审查，轨道 07 因子代理并发上限由主会话执行；共生成 7 份轨道报告：

- `track-01-fact-sources-contract.md`
- `track-02-rust-primary-path.md`
- `track-03-cross-command-lifecycle.md`
- `track-04-cache-metadata-fast-path.md`
- `track-05-tests-acceptance.md`
- `track-06-migration-deletion.md`
- `track-07-performance-concurrency.md`

原始确认发现合计 21 条：P0 3 条、P1 9 条、P2 9 条、P3 0 条。P0/P1 已形成阻断，不能把本轮结论写成 PASS。

同根问题主要有三类：

1. workflow gate / text index metadata 把“已预检”当作当前候选事实消费，插件源码和非标准 data 的后续命令可能绕过当前 Rust gate。
2. 插件源码、Note 标签、非标准 data、path template、scope hash 等关键事实仍存在 Python/Rust 双实现或 Python 二次判断。
3. 测试和性能验收仍有倒挂：部分测试固定 shortcut 行为，scan budget 不能替代真实 CLI 性能证据。

## 最高优先级问题

### P0：workflow gate metadata 不是当前候选 gate 事实

- 证据：`track-03-cross-command-lifecycle.md:34`。
- 证据：`rust/src/native_core/scope_index/rebuild.rs:576`、`rust/src/native_core/scope_index/rebuild.rs:578`、`rust/src/native_core/scope_index/rebuild.rs:582`、`rust/src/native_core/scope_index/rebuild.rs:583`。
- 证据：`app/application/handler.py:995`、`app/application/handler.py:1000`、`app/application/handler.py:1422`、`app/application/handler.py:1427`。
- 影响：`rebuild-text-index` 写入插件源码/非标准 data 已预检标记，`translate`、`quality-report`、`write-back` 后续信任 metadata shortcut，而不是消费当前候选 gate。高风险或 stale 状态可能显示为已审查。
- 同根项：轨道 04 的插件源码排除 selector fast path P0、轨道 04 的 text index metadata contract P1、轨道 01 的 scope hash 双入口 P0。

### P0：插件源码排除 selector fast path 可绕过当前 AST / selector 新鲜度

- 证据：`track-04-cache-metadata-fast-path.md:42`。
- 证据：`app/agent_toolkit/services/rule_validation.py:814`、`app/agent_toolkit/services/rule_validation.py:817`、`app/agent_toolkit/services/rule_validation.py:897`、`app/agent_toolkit/services/rule_validation.py:901`。
- 影响：只包含 `excluded_selectors` 的规则在 metadata 标记和已存规则匹配时可直接报告通过，不重新验证当前 text index、AST、启用状态、selector 是否仍新鲜。用户会看到 validate/import 成功，但后续重建或写回才暴露 stale。
- 同根项：轨道 03 的 excluded selector lifecycle P1、轨道 02/06 的插件源码 Python selector/stale 判断 P1。

### P0：空规则确认 scope hash 有 Python 冷路径与 Rust warm index 双事实源

- 证据：`track-01-fact-sources-contract.md:24`。
- 证据：`app/rule_review.py:29`、`app/application/flow_gate.py:486`、`rust/src/native_core/scope_index/rebuild.rs:568`、`app/text_index.py:404`。
- 影响：无持久索引时由 Python 计算当前 scope hash；有持久索引时读取 Rust 重建写入的 `workflow_gate_scope_hashes`。同一“空规则确认是否仍适用当前范围”的事实有两个入口，序列化、排序或 payload 口径漂移时会给出不同结论。

## 横向矩阵

### 单一事实来源破坏

- 空规则 scope hash：Python 冷路径与 Rust metadata 双入口，见 `track-01-fact-sources-contract.md:24`。
- path template / JSONPath：Python importer、`app/json_path_protocol` 与 Rust `plugin_config.rs`、`event_commands.rs`、`nonstandard_data.rs` 分别解析和展开，见 `track-01-fact-sources-contract.md:39`。
- 插件源码 selector/location_path：Python `scanner.py`、`extraction.py` 与 Rust scope/write-back 分别构造，见 `track-01-fact-sources-contract.md:71`。
- 插件源码候选/stale/coverage：Rust 已有候选扫描和 rebuild 检查，但 Python 仍二次过滤、校验和覆盖统计，见 `track-02-rust-primary-path.md:49`、`track-06-migration-deletion.md:28`。
- 非标准 data rule hit：候选扫描声明 Rust 主路径，但 text scope 命中仍由 Python 提取器展开，见 `track-06-migration-deletion.md:40`。

### Rust 主路径缺口

- 插件源码：Rust 需要直接输出 import/validate/extract 所需的 selector 命中、filtered selectors、excluded selector、新鲜度、review coverage、risk summary 和错误码。
- Note 标签：Rust 当前提供 scan facts，但缺少“给定导入规则是否合法”的 native rule validation schema，见 `track-02-rust-primary-path.md:63`。
- 非标准 data：Rust 需要输出 rule hit details、translation prefixes、stale reason，供 text scope / rebuild / validate / import 共用。
- metadata/cache：text index metadata 和 runtime plugin source scan cache 缺少 Rust/native/parser contract version，见 `track-04-cache-metadata-fast-path.md:69`、`track-04-cache-metadata-fast-path.md:97`。

### Python 删除候选

- `app/plugin_source_text/native_scan.py` 中插件源码 Python 二次过滤、风险计算和源文判断。
- `app/plugin_source_text/importer.py` 中 selector membership、file_hash、stale 校验。
- `app/plugin_source_text/rules.py` 中 stale 与 review coverage。
- `app/plugin_source_text/extraction.py::PluginSourceTextExtraction`。
- `app/nonstandard_data/extraction.py::NonstandardDataTextExtraction` 的 path template 展开。
- `app/text_scope/rule_hits.py::collect_nonstandard_data_rule_hits` 的 Python hit 展开。
- `app/native_note_tag_scan.py` 中 Note 标签导入规则精确匹配与可翻译判断。
- `app/agent_toolkit/placeholder_scan.py::scan_placeholder_candidates` 及公共导出。
- `app/rule_review.py` 中生产 scope hash 的 Python helper。

### 跨命令生命周期断点

- 插件源码样本链路中，导出/完整导入读取当前 AST，重建写 metadata shortcut，翻译/质量/写回消费 shortcut，不是同一候选事实。
- 非标准 data 单命令 validate/import 能读取当前扫描事实，但 indexed lifecycle 中 gate errors 被空列表替代。
- 缺少公开 import 后冷重建不 stale 的非空规则生命周期测试，见 `track-05-tests-acceptance.md:51`。

### fast path 和 cache 风险

- `workflow_gate_prechecked:* = passed` 只有字符串标记，不能表达生成该结论的 Rust 候选口径。
- `validate_plugin_source_rules` / `import_plugin_source_rules` 的 excluded-only fast path 可不经当前 AST 验证。
- warm text index 只比较 source snapshot、rules fingerprint、item_count，未比较 scope/index contract。
- runtime plugin source scan cache 只按 file hash 命中，未记录 AST/parser/audit contract。

### 性能与并发风险

- 未发现当前 Rust 热路径完全缺少线程池包装：scope index、JS AST 批量解析、质量检查、写入协议检查均有 `run_with_optional_pool` 或 `par_iter` 证据，见 `track-07-performance-concurrency.md:60`。
- 性能验收仍缺当前 HEAD 真实 CLI 计时闭环，见 `track-07-performance-concurrency.md:40`。`scan_budget` 能防止旧重型路径回归，但不能证明用户实际等待时间下降。

### 测试验收缺口

- 缺插件源码/Note/事件/非标准 data “公开导入 -> 冷重建 -> 后续报告/写回 gate” 生命周期测试。
- 写回 helper 在测试中手工构造 current text facts，容易绕开 Rust 冷重建事实源，见 `track-05-tests-acceptance.md:63`。
- 部分写入命令只断言异常文案，没有固定错误码与事实状态，见 `track-05-tests-acceptance.md:75`。
- 旧 Python oracle 仍用于 native parity 测试，缺少退场条件，见 `track-06-migration-deletion.md:64`。

## 插件源码规则样本复盘

设计要求插件源码规则链路必须覆盖：

- `export-plugin-source-ast-map`
- `validate-plugin-source-rules`
- `import-plugin-source-rules`
- `rebuild-text-index`
- `translate`
- `write-back`

本轮审查结论：当前链路没有证明消费同一候选事实。

确认断点：

- 导出和完整导入会读取当前插件源码、`plugins.js` 和 native scan。
- `rebuild-text-index` 能把插件源码 managed texts 写入 current facts，但同时写入 source branch gate precheck metadata。
- `translate`、`quality-report`、`write-back` 的 indexed gate 可消费 metadata shortcut，而不是当前插件源码 gate 结论。
- `excluded_selectors` only 的 validate/import fast path 可只比较导入文件和已存规则，不验证当前 AST、启用状态和 selector 新鲜度。

后续验收样本必须至少包含：

- selector 未变时：导入成功后冷重建不 stale，后续质量报告和写回 gate 消费同一 Rust 事实。
- selector 仍在 AST 中但被当前候选过滤口径排除时：错误码必须说明过滤口径变化，不能伪装成 AST 缺失。
- only `excluded_selectors` 时：重复导入要验证当前 selector 事实，而不是只比较数据库旧规则。
- fast path 命中时：必须证明 current text index 和 Rust/native contract 仍当前。

## 后续重构建议批次

1. **Gate metadata 收束批次**
   - 目标：让 `rebuild-text-index` 写入真实 source branch gate 结论，而不是 `passed` shortcut。
   - 完成条件：`translate`、`quality-report`、`write-back` 消费 Rust gate 结果；不在 Python hot path 重新全量扫描。

2. **插件源码规则 Rust contract 批次**
   - 目标：Rust 输出 validate/import/extract 需要的 selector、excluded selector、filtered selector、stale reason、review coverage、risk summary。
   - 完成条件：删除 Python selector/stale/coverage 二次判断；插件源码生命周期测试通过。

3. **path template 与非标准 data rule hit 批次**
   - 目标：Rust 统一 JSONPath/path template 解析、命中展开、translation prefixes 和 stale reason。
   - 完成条件：Python 不再用 `NonstandardDataTextExtraction` 展开当前 rule hit。

4. **Note 标签规则验证批次**
   - 目标：Rust 提供 Note 标签导入规则验证结果和错误码。
   - 完成条件：Python 不再执行 Map 精确源、tag 命中、可翻译统计的业务判断。

5. **metadata/cache contract 批次**
   - 目标：text index metadata、runtime scan cache 写入并校验 Rust/native/parser contract。
   - 完成条件：旧 contract metadata/cache 不会被当作当前事实源。

6. **测试退场与性能证据批次**
   - 目标：迁移旧 Python oracle 到 Rust/native contract 测试，补真实 CLI 性能证据。
   - 完成条件：scan budget、行为测试、真实 CLI timings 三者齐备。

## 明确拒绝的错误方向

- 不在 Python 新增 selector fallback、stale 二次判断、风险阈值补丁或 path template 兼容分支。
- 不让 Python 和 Rust 长期保留同一候选事实的双实现。
- 不用 `workflow_gate_prechecked:* = passed` 继续代表当前 gate 已审查。
- 不把旧 Python scanner/extractor 保留在包根公共 API 中等待调用方自觉不用。
- 不用更宽松的中文文案正则替代错误码和事实状态断言。
- 不把 scan budget 或旧性能报告写成当前 HEAD 真实 CLI 性能通过。

## 剩余不确定项

- 本轮未运行 `uv run basedpyright`、`uv run pytest`、Rust fmt、clippy 或 Rust tests；原因是本任务是只读 review 报告生成，且计划不要求全量测试。
- 本轮未执行真实 CLI benchmark；性能结论只说明代码侧线程/预算护栏和证据缺口。
- 事件指令、MV 虚拟名字框、结构化占位符未确认存在同等级生命周期 P0，但它们仍应纳入后续 Rust contract 统一验收。
- 子代理并发上限导致轨道 07 由主会话执行；其余轨道 01 到 06 已由独立 worker 并发完成。

## 只读边界声明

本轮执行的命令类型限于只读检索、文件读取、报告目录创建、报告写入、自检、`git status --short` 和 `git diff --check`。未执行 `import-*`、`translate`、`write-back`、`rebuild-active-runtime`、`reset-game`、`reset-translations`、`run-all` 等状态变更命令。

本轮新增/修改范围仅限：

- `docs/superpowers/plans/2026-06-10-rust-primary-refactor-review-execution.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-01-fact-sources-contract.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-02-rust-primary-path.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-03-cross-command-lifecycle.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-04-cache-metadata-fast-path.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-05-tests-acceptance.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-06-migration-deletion.md`
- `docs/records/reviews/rust-primary-refactor/batches/track-07-performance-concurrency.md`
- `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md`

未修改源码、测试、schema、Skill、README、配置、脚本、数据库、游戏目录、日志、输出、临时目录或构建产物。未读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。
