# 轨道 04：缓存、metadata 与 fast path

## 范围

本轨道只读审查以下对象：

- 持久文本范围索引 metadata、scope summary、domain summary、workflow gate 预检标记和失效判断。
- workflow gate、quality-report、translation-status、write-back 前置检查、validate/import plugin-source 的 fast path。
- 插件源码 AST 扫描缓存、当前运行插件源码扫描缓存、runtime write map。
- text facts 与 text index 的 contract/hash 字段，以及相关 Python/Rust 测试覆盖。

未审查运行数据目录、日志目录、输出目录、临时目录、构建目录、虚拟环境和缓存目录；本轮没有执行任何业务状态变更命令。

## 只读命令

- `Get-Content -LiteralPath 'docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md'`
- `Get-Content -LiteralPath 'docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md'`
- `rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'fast|cache|metadata|precheck|warm|summary|skip|shortcut|mtime|hash|source_hash|rule_hash|scope_hash|workflow_gate|gate|stale|current' app rust/src tests`
- `rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'metadata|text_index|text_facts|scope|summary|schema_version|contract_version|rule_hash|source_hash|runtime_map' app/persistence app/text_index.py app/text_facts.py rust/src/native_core tests`
- `rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'workflow|gate|quality|pending|translated|stale|precheck|skip|cache|summary|report' app/agent_toolkit app/translation app/native_quality.py rust/src/native_core/quality tests`
- `rg -n` 窄范围读取：`app/text_index.py`、`app/agent_toolkit/services/quality.py`、`app/agent_toolkit/services/rule_validation.py`、`app/application/handler.py`、`app/plugin_source_text/scanner.py`、`app/plugin_source_text/runtime_audit.py`、`app/persistence/schema/current.sql`、`app/persistence/text_index_records.py`、`app/persistence/plugin_source_runtime_records.py`、`app/native_contract.py`、`app/native_scope_index.py`、`app/native_javascript_ast.py`、`rust/src/native_core/scope_index/rebuild.rs`、`rust/src/native_core/scope_index/storage.rs`、`tests/test_text_index.py`、`tests/test_agent_toolkit_quality_report.py`、`tests/test_agent_toolkit_workflow_gate.py`、`tests/test_rmmz_write_plan.py`、`tests/test_plugin_source_text.py`。

## 结论

FAIL

fast path 清单：

| fast path | 跳过条件 | 是否绕过 Rust 主路径 | stale 报告为已审查风险 | 建议 |
| --- | --- | --- | --- | --- |
| `validate_plugin_source_rules` / `import_plugin_source_rules` 排除 selector 快路径 | 有 text index metadata、metadata 预检标记为 `passed`、导入文件与当前已保存排除 selector 相同 | 是。直接返回 Python 报告，不调用 `detect_text_index_invalidations`，也不重新走 Rust AST/候选事实 | 是。旧 metadata 仍可让排除规则显示为 `reviewed_selector_count` 且无错误 | P0，删除 Python 直返或改为 Rust 当前事实验证 |
| warm text index 复用 | metadata 的 source snapshot fingerprint、rules fingerprint、item_count 均匹配 | 部分绕过。有效索引直接消费 SQLite text_facts / summaries，不重建 Rust 索引 | 有 contract 升级风险。metadata 不记录 native/scope-index contract version | P1，metadata 增加 Rust contract/version 并纳入失效判断 |
| workflow gate 预检标记 | `workflow_gate_prechecked:plugin_source_text` 和 `workflow_gate_prechecked:nonstandard_data` 都等于 `passed` | 正常路径由 Rust rebuild 写入，但 Python 只校验固定字符串 | 与上一项同源；标记本身不表达生成它的 Rust 口径 | 与 metadata contract 合并收紧 |
| quality-report 大库 count 快路径 | `item_count > QUALITY_REPORT_FULL_RECHECK_LIMIT`、存在最新 run、无 source residual 规则、不含 write probe | 不读全量索引和全量译文，但先经过 text index invalidation，计数来自 current text facts | 未确认直接 stale 漏报；受 metadata contract 缺口影响 | 保留性能方向，补 contract 失效测试 |
| translation-status 默认数据库快路径 | 未传 `--refresh-scope` | 是，但该命令默认只是读取最近运行状态，不声明完成当前范围审查 | 未确认作为 gate 使用 | 保留，用户文案持续区分 run 统计与 current scope |
| plugin-source 进程内 AST cache | 同进程同 file hash 命中 | 跳过重复 Rust AST parse | 进程内缓存，重启清空；未确认跨版本持久风险 | 可接受，若 AST parser contract 热替换不可发生则不需持久版本 |
| plugin-source active runtime 持久 scan cache | DB cache 中 file_name 存在且 file_hash 与当前文件 hash 相同 | 是。命中时从 DB literals_json 还原，不调用 Rust AST parse | 是。parser/native 口径升级但文件不变时可复用旧 literal_kind / audit_default_severity | P1，cache key 增加 native/parser contract 与文本审计口径 |
| write-back 索引快路径 | text index 有效，写回前置 gate 使用 index metadata/current facts | 后续仍调用 Rust write plan；未确认直接绕过 | 受 metadata contract 缺口影响 | 保留 Rust write plan，收紧 metadata |

## 关键发现

### P0：插件源码排除 selector 快路径没有先验证 text index 仍是当前事实源

- 证据：`app/agent_toolkit/services/rule_validation.py:814`
- 证据：`app/agent_toolkit/services/rule_validation.py:817`
- 证据：`app/agent_toolkit/services/rule_validation.py:819`
- 证据：`app/agent_toolkit/services/rule_validation.py:824`
- 证据：`app/agent_toolkit/services/rule_validation.py:897`
- 证据：`app/agent_toolkit/services/rule_validation.py:901`
- 证据：`app/agent_toolkit/services/rule_validation.py:907`
- 证据：`app/agent_toolkit/services/rule_validation.py:235`
- 证据：`app/agent_toolkit/services/rule_validation.py:262`
- 证据：`app/agent_toolkit/services/rule_validation.py:266`
- 证据：`app/agent_toolkit/services/rule_validation.py:302`
- 证据：`app/agent_toolkit/services/rule_validation.py:303`
- 证据：`app/agent_toolkit/services/rule_validation.py:282`
- 证据：`app/text_index.py:184`
- 证据：`app/text_index.py:202`
- 证据：`app/text_index.py:211`
- 业务事实：`validate_plugin_source_rules` 和 `import_plugin_source_rules` 在读取 `TextIndexMetadata` 后，只要 `workflow_gate_prechecked:*` 标记通过，且导入 JSON 与当前数据库中“只有 excluded_selectors 的插件源码规则”一致，就直接返回 `_plugin_source_current_exclusions_report`。这个报告写出 `errors=[]`、`reviewed_selector_count=selector_count+excluded_selector_count`，但没有先调用 `detect_text_index_invalidations` 比对当前 source snapshot、规则 fingerprint 和 item_count，也没有重新进入 Rust 插件源码候选扫描。
- 违反原则：fast path | Rust 主路径 | 单一事实来源 | 跨命令生命周期
- 影响：如果 text index metadata 是旧索引，或插件源码候选口径已经变化，用户再次校验/导入同一份“只排除 selector”的规则时，命令仍可能返回 ok，并把这些 selector 报为已审查。这样会让 stale 规则以“已审查、无错误”的外观绕过当前 Rust 主路径。
- Python/Rust 职责判断：Python 只能编排导入文本解析和报告组装；“当前 selector 是否仍属于当前插件源码候选事实、是否只是已审查排除项”应由 Rust scope/index 或 Rust plugin-source candidate fact 消费同一当前事实源后判断。
- 建议 Rust 接管点：新增 Rust 侧 `validate_current_plugin_source_exclusion_review` 或把该分支并入现有 plugin-source rule validation，输入当前数据库规则、导入规则和当前 source/index metadata，输出结构化 hit/review 摘要与 stale 错误码。
- 应删除或瘦身的 Python 逻辑：删除 `rule_validation.py` 中直接基于 `_plugin_source_import_matches_current_exclusions` 返回 `_plugin_source_current_exclusions_report` 的生产快路径；最多保留“解析导入 JSON 后调用 Rust 验证”的薄适配。
- 禁止采用的错误修复方向：不要只在此分支前补一层 Python AST 扫描、Python selector 判断或字符串比较；也不要把 `errors=[]` 改成 warning 来掩盖事实来源不一致。
- 后续验证：补回归测试：构造已有 `workflow_gate_prechecked:* = passed` 的 text index，随后让 `detect_text_index_invalidations` 可返回 `source_snapshot_changed` 或 `rules_changed`，再调用 `validate_plugin_source_rules` / `import_plugin_source_rules` 的只排除 selector 输入，必须显式失败或触发 Rust 当前事实验证，不能返回 `_plugin_source_current_exclusions_report`。

### P1：text index metadata 没有持久记录 Rust/native contract version，warm index 可跨 Rust 口径变化复用

- 证据：`app/persistence/schema/current.sql:312`
- 证据：`app/persistence/schema/current.sql:314`
- 证据：`app/persistence/schema/current.sql:315`
- 证据：`app/persistence/schema/current.sql:316`
- 证据：`app/persistence/schema/current.sql:317`
- 证据：`app/text_index.py:184`
- 证据：`app/text_index.py:202`
- 证据：`app/text_index.py:211`
- 证据：`app/text_index.py:223`
- 证据：`app/native_contract.py:5`
- 证据：`app/native_scope_index.py:500`
- 证据：`rust/src/native_core/scope_index/rebuild.rs:448`
- 证据：`rust/src/native_core/scope_index/rebuild.rs:461`
- 证据：`rust/src/native_core/scope_index/storage.rs:984`
- 证据：`rust/src/native_core/scope_index/storage.rs:985`
- 证据：`tests/test_text_index.py:202`
- 证据：`tests/test_text_index.py:224`
- 业务事实：`text_index_meta` 只持久保存 `source_snapshot_fingerprint`、`rules_fingerprint`、`item_count`、`workflow_gate_scope_hashes` 和 `created_at`。`detect_text_index_invalidations` 也只比较 source snapshot、rules fingerprint、item_count。当前代码有全局 `NATIVE_CONTRACT_VERSION = 12`，加载 native 模块时会检查当前 Python/Rust 扩展契约，但这个版本没有写入 text index metadata，也没有参与 warm index 失效。测试覆盖了 prompt context version 变化会导致 `rules_changed`，但没有覆盖 native/scope-index contract version 变化。
- 违反原则：fast path | Rust 主路径 | 单一事实来源 | 测试验收
- 影响：Rust scope/index 的候选过滤、workflow gate metadata 生成、文本事实构建或 locator 语义如果升级，而输入文件和规则 fingerprint 没变，已有 warm index 仍可能被 `quality-report`、`translate --max-items`、`write-back` 前置检查、coverage 等入口当作当前事实源继续使用。用户可见表现是旧 Rust 口径生成的索引显示为 `used`，而不是显式要求重建。
- Python/Rust 职责判断：Rust 应定义 scope/index storage contract version 或 native contract fingerprint；Python 只负责读取 metadata 并比较当前要求，不应靠 Python 常量和局部 prompt version 兜住 Rust 语义升级。
- 建议 Rust 接管点：由 Rust rebuild 输出并写入 `text_index_meta` 的 `native_contract_version` 或 `scope_index_contract_hash`；Rust storage 写入与 Python `detect_text_index_invalidations` 都消费同一个字段。
- 应删除或瘦身的 Python 逻辑：不要继续增加零散 Python 常量来代表局部口径；`TEXT_INDEX_PROMPT_CONTEXT_VERSION` 可以保留为 prompt 输入版本，但不能替代 Rust scope/index contract。
- 禁止采用的错误修复方向：不要只在 README 或报告文案中提醒用户手动重建；不要把数据库 schema version 当作 Rust 候选事实 contract version，schema 只说明表结构，不说明当前 Rust 过滤语义。
- 后续验证：补 Python 流程测试，模拟旧 metadata 缺少或携带旧 `scope_index_contract_hash` 时，所有 warm index fast path 都返回 `text_index_contract_changed` 一类失效原因并停止或重建；补 Rust storage 测试确认重建写入该字段。

### P1：当前运行插件源码持久 scan cache 只按文件 hash 命中，缺少 AST/parser contract 与文本审计口径

- 证据：`app/persistence/schema/current.sql:109`
- 证据：`app/persistence/schema/current.sql:110`
- 证据：`app/persistence/schema/current.sql:111`
- 证据：`app/persistence/schema/current.sql:112`
- 证据：`app/persistence/schema/current.sql:113`
- 证据：`app/rmmz/schema.py:420`
- 证据：`app/rmmz/schema.py:423`
- 证据：`app/rmmz/schema.py:424`
- 证据：`app/plugin_source_text/runtime_audit.py:351`
- 证据：`app/plugin_source_text/runtime_audit.py:355`
- 证据：`app/plugin_source_text/runtime_audit.py:373`
- 证据：`app/plugin_source_text/runtime_audit.py:377`
- 证据：`app/plugin_source_text/runtime_audit.py:382`
- 证据：`app/plugin_source_text/runtime_audit.py:448`
- 证据：`app/plugin_source_text/runtime_audit.py:475`
- 证据：`app/plugin_source_text/runtime_audit.py:507`
- 证据：`app/plugin_source_text/runtime_audit.py:528`
- 证据：`app/agent_toolkit/services/quality.py:876`
- 证据：`app/agent_toolkit/services/quality.py:885`
- 证据：`app/application/handler.py:1623`
- 证据：`app/application/handler.py:1647`
- 证据：`app/application/write_plan_applier.py:80`
- 证据：`app/application/write_plan_applier.py:82`
- 业务事实：`plugin_source_runtime_scan_cache` 的持久表和 Pydantic record 只保存 file_name、file_hash、syntax_error、literals_json、created_at。命中逻辑按 file_name 找记录，再比较当前文件 hash；hash 相同时直接从 DB 还原 literals，不重新调用 Rust AST parse。该缓存被 `audit_active_runtime`、`diagnose_active_runtime` 和写回后的当前运行审计使用，并会在写回成功路径保存回数据库。缓存中的 literal 还包含 `literal_kind` 与 `audit_default_severity`，这些字段来自旧扫描口径，随后再参与 Rust literal issue fact 和阻断分类。
- 违反原则：fast path | Rust 主路径 | 单一事实来源 | 跨命令生命周期
- 影响：如果 Rust JS AST parser、literal 分类、默认阻断级别或 runtime literal issue 输入契约升级，而插件源码文件内容未变，持久 scan cache 仍可命中并绕过当前 Rust parser。写后审计、当前运行审计或诊断可能使用旧 literal 事实判断安全性，严重时把应阻断的当前运行问题报告为通过或反向误报。
- Python/Rust 职责判断：持久 runtime scan cache 可以作为性能缓存，但缓存 key 和失效口径应由 Rust AST/parser contract 或 native contract 控制；Python 不应只用 file hash 决定当前 AST 事实是否可复用。
- 建议 Rust 接管点：由 Rust AST scan 输出 `parser_contract_hash`、`literal_contract_version` 或统一 `native_contract_version`，持久 cache 写入并在读取时强校验；命中失败时显式重新扫描，扫描失败时继续按当前错误码阻断。
- 应删除或瘦身的 Python 逻辑：瘦身 `scan_plugin_source_files_text_strict_with_cache` 中的 Python 命中判断，让它只传入现有 cache 和当前 contract，最终由 Rust 或统一 adapter 决定哪些记录可复用；删除只看 file_hash 的长期事实判断。
- 禁止采用的错误修复方向：不要只清空一次缓存或在异常时静默丢弃缓存继续报告 ok；不要新增手写 Python 版本号散落在 runtime_audit 与 persistence 两侧。
- 后续验证：补测试：写入旧 contract 的 runtime scan cache 且文件 hash 不变时，`audit_active_runtime` 与写后审计必须重新扫描或显式失败；补 Rust/Python adapter 测试确认缓存记录缺少 contract 字段时不会被当成当前事实。

## 双事实来源清单

- 插件源码排除 selector 当前性：Python `_plugin_source_import_matches_current_exclusions` 使用导入 JSON 与数据库规则快照判断；Rust plugin-source scan / scope-index 才是当前候选事实来源。
- text index 当前性：Python `detect_text_index_invalidations` 用 metadata 快速判断；Rust `rebuild_scope_index_storage` 生成 workflow gate metadata、text facts 和 summaries。当前 metadata 未携带 Rust contract，导致“当前性”缺少统一口径。
- 当前运行插件源码 AST 事实：Python 持久 scan cache 通过 file hash 恢复 literals；Rust JS AST parser 生成当前 parser 事实。cache key 未记录 parser/native contract。

## Rust 主路径缺口

- 缺少 Rust 侧“当前插件源码排除规则已审查”验证入口，导致 Python 可以直接把 DB 规则快照渲染为 ok 报告。
- 缺少 text index metadata 的 Rust scope/index contract 字段，warm index 无法判断旧 Rust 口径生成物是否仍可用。
- 缺少 plugin-source runtime scan cache 的 parser/native contract 字段和统一失效策略。
- workflow gate 预检标记只有 `passed` 字符串，不能独立说明生成该标记的 Rust 候选口径。

## Python 删除候选

- 删除或改造 `app/agent_toolkit/services/rule_validation.py` 中 `_plugin_source_import_matches_current_exclusions` 驱动的生产 fast path。
- `_plugin_source_current_exclusions_report` 可降级为 Rust 验证结果的报告渲染函数，不能再作为事实判断入口。
- `app/plugin_source_text/runtime_audit.py` 中只按 file hash 命中的持久 cache 判断应瘦身为 adapter，不再直接决定当前 AST 事实可复用。
- 不再扩展 `text_index_source_branch_gates_prechecked` 的 Python 语义；它只能读取 Rust 写入并带 contract 的 metadata。

## 测试缺口

- 缺 `validate_plugin_source_rules` / `import_plugin_source_rules` 在旧 metadata 或 text index invalidation 存在时禁用排除 selector fast path 的回归测试。
- 缺 text index native/scope-index contract version 变化触发 warm index 失效的测试。现有测试只覆盖 prompt context version、规则和 source snapshot 变化：`tests/test_text_index.py:151`、`tests/test_text_index.py:202`。
- 缺 runtime scan cache contract mismatch 测试。现有测试覆盖缓存会读写和 hash stale 统计，但未覆盖 parser/native contract 变化：`tests/test_agent_toolkit_rule_import.py:1433`、`tests/test_agent_toolkit_rule_import.py:1441`。
- 现有性能测试固定大库 quality-report count fast path 不读全量索引和译文：`tests/test_agent_toolkit_quality_report.py:704`、`tests/test_agent_toolkit_quality_report.py:749`、`tests/test_agent_toolkit_quality_report.py:760`。需要补相邻测试确保 contract mismatch 时不走 count-only 报告。
- 现有写回测试固定自动重建后写回快路径不调用 `evaluate_text_index_scope_gate`：`tests/test_rmmz_write_plan.py:515`、`tests/test_rmmz_write_plan.py:516`。需要补相邻测试确保 metadata contract mismatch 先重建或失败。

## 交叉引用

- 轨道 01：事实来源与契约应合并本报告的 text index metadata contract 和 plugin-source exclusion 双事实来源。
- 轨道 02：Rust 主路径应接收 plugin-source exclusion validation、runtime scan cache contract、scope-index metadata version 三个 Rust 接管点。
- 轨道 03：跨命令生命周期应关注 validate/import plugin-source、rebuild-text-index、quality-report、write-back 之间对 workflow gate metadata 的消费一致性。
- 轨道 05：测试与验收应补 fast path stale/contract mismatch 回归测试。
- 轨道 07：性能与并发可保留 count fast path 和 scan cache 的性能目标，但必须把 contract 失效纳入验收。

## 已查无发现范围

- `app/translation/cache.py` 是单轮内存去重缓存，按 `translation_dedupe_key` 或原文行、类型、角色去重；测试确认展开时保留 fact_id 与 source fact hash。未发现它会绕过当前 text fact membership。
- `quality-report` warm index 主入口先调用 `detect_text_index_invalidations`，缺失或过期时会自动重建，重建失败或重建后仍不匹配会停止。除本报告指出的 metadata contract 缺口外，未确认它直接把已知过期索引当作 ok。
- `evaluate_text_index_scope_gate` 会读取 current text facts、当前匹配译文 fact_id 和最新质量错误 fact_id，并在索引记录缺少 current text fact 时显式要求重新生成索引。未发现该函数本身只比较输入文本和数据库译文而跳过 current fact membership。
- `write-back` / `rebuild-active-runtime` 前置检查会先处理 text index invalidation、workflow gate、stale saved translations、pending 和最新质量错误，并继续进入 Rust write plan。除 metadata contract 缺口外，未确认直接跳过 Rust 写回主路径。
- 进程内插件源码 AST LRU cache 只存在于当前 Python 进程内，按 file hash 复用；本轮未确认它会跨进程保留旧 Rust parser 事实。
