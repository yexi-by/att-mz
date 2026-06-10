# 轨道 01：事实来源与契约

## 范围

本轨道只读审查以下事实与契约：候选集合、selector、path template、rule hash、text rules hash、scope hash、fact_id、location_path、metadata、schema_version、error_code、report 字段，以及 docs/Skill/测试 helper 是否反向定义当前事实源。

已覆盖仓库区域：`app/`、`rust/src/`、`tests/`、`app/persistence/schema/current.sql`、`README.md`、`docs/superpowers/`、`skills/att-mz-protocol/`、`skills/att-mz/`、`skills/att-mz-release/`。

## 只读命令

- `rg -n 'candidate|selector|path_template|rule_hash|text_rules_hash|scope_hash|fact_id|location_path|metadata|schema_version|error_code|report|事实|候选|规则|范围|过期' app rust/src tests skills/att-mz-protocol skills/att-mz skills/att-mz-release`
- `rg -n 'schema_version|CURRENT_SCHEMA_VERSION|TEXT_FACT_SCHEMA_VERSION|error_code|report|AgentReport|translation_items|text_facts|text_index|rule_hash|scope_hash' app rust/src tests app/persistence/schema/current.sql`
- `rg -n 'candidate|selector|scope|hash|location_path|fact_id|schema|规则|候选|当前事实|事实源' README.md docs/superpowers skills/att-mz-protocol skills/att-mz skills/att-mz-release tests`
- `Get-Content -LiteralPath 'docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md'`
- `Get-Content -LiteralPath 'docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md'`
- 窄范围 `rg` / `Get-Content`：`app/rule_review.py`、`app/application/flow_gate.py`、`app/text_index.py`、`app/native_scope_index.py`、`app/json_path_protocol/__init__.py`、`app/plugin_source_text/`、`app/application/handler.py`、`rust/src/native_core/scope_index/`、`rust/src/native_core/write_back_plan/plugin_source.rs`、相关 `tests/`。

## 结论

FAIL

## 关键发现

### P0：空规则确认范围哈希在 Python 冷路径与 Rust 持久索引路径双入口构造

- 证据：`app/rule_review.py:29`、`app/rule_review.py:34`、`app/rule_review.py:55`、`app/rule_review.py:60`、`app/rule_review.py:65`、`app/rule_review.py:70`
- 证据：`app/application/flow_gate.py:486`、`app/application/flow_gate.py:511`、`app/application/flow_gate.py:523`、`app/application/flow_gate.py:534`、`app/application/flow_gate.py:548`
- 证据：`rust/src/native_core/scope_index/rebuild.rs:568`、`rust/src/native_core/scope_index/rebuild.rs:595`、`rust/src/native_core/scope_index/rebuild.rs:614`、`rust/src/native_core/scope_index/rebuild.rs:637`、`rust/src/native_core/scope_index/rebuild.rs:660`、`rust/src/native_core/scope_index/rebuild.rs:676`、`rust/src/native_core/scope_index/rebuild.rs:703`、`rust/src/native_core/scope_index/rebuild.rs:727`
- 证据：`app/text_index.py:404`、`app/text_index.py:412`、`app/text_index.py:472`
- 业务事实：外部文本规则空结果确认、普通占位符候选覆盖、结构化占位符候选覆盖的当前 `scope_hash`。
- 违反原则：单一事实来源 | Rust 主路径 | 跨命令生命周期
- 影响：无持久索引时，workflow gate 用 Python 重新计算当前范围哈希；有持久索引时，workflow gate 用 Rust 重建时写入的 `workflow_gate_scope_hashes`。同一个“空规则确认是否仍适用于当前游戏”的事实由两套入口决定，后续任一 payload、排序或序列化规则漂移，都会导致冷路径和 warm index 路径对同一规则状态给出不同结果。
- Python/Rust 职责判断：`scope_hash` 属于候选集合和规则范围事实，应由 Rust 主路径统一生成和验证；Python 只应读取 Rust 输出、传参和组装报告。
- 建议 Rust 接管点：为插件规则、事件指令规则、Note 标签规则、MV 虚拟名字框、普通占位符和结构化占位符提供同一 Rust scope hash/evaluate 入口；`rebuild-text-index` metadata 与非索引 workflow gate 都调用该入口。
- 应删除或瘦身的 Python 逻辑：瘦身 `app/rule_review.py` 的哈希构造函数；瘦身 `app/application/flow_gate.py` 中直接传入 Python 计算 `current_scope_hash` 的分支；测试 helper 不应再把 Python hash helper 当当前事实源。
- 禁止采用的错误修复方向：不要再新增 Python hash 对齐代码、Python fallback、报告层文案修正，或用额外 metadata 字段掩盖双入口。
- 后续验证：新增冷路径 workflow gate 与 warm index workflow gate 的同输入一致性测试，并为 Rust scope hash payload 加 Rust 单测；覆盖 plugin/event/note/mv/placeholder/structured placeholder 六个域。

### P1：`path_template` / JSONPath 语法和 `location_path` 展开仍由 Python 与 Rust 分别维护

- 证据：`app/json_path_protocol/__init__.py:12`、`app/json_path_protocol/__init__.py:180`、`app/json_path_protocol/__init__.py:218`、`app/json_path_protocol/__init__.py:255`
- 证据：`app/plugin_text/importer.py:128`、`app/event_command_text/importer.py:145`、`app/nonstandard_data/rules.py:48`、`app/nonstandard_data/rules.py:50`
- 证据：`rust/src/native_core/scope_index/plugin_config.rs:471`、`rust/src/native_core/scope_index/plugin_config.rs:486`、`rust/src/native_core/scope_index/plugin_config.rs:523`
- 证据：`rust/src/native_core/scope_index/event_commands.rs:674`、`rust/src/native_core/scope_index/event_commands.rs:689`、`rust/src/native_core/scope_index/event_commands.rs:726`
- 证据：`rust/src/native_core/scope_index/nonstandard_data.rs:521`、`rust/src/native_core/scope_index/nonstandard_data.rs:554`、`rust/src/native_core/scope_index/nonstandard_data.rs:772`
- 证据：`app/application/handler.py:718`、`app/application/handler.py:730`、`app/application/handler.py:814`
- 业务事实：插件参数、事件指令和非标准 data 规则的 `path_template` 语法、路径匹配结果、最终 `location_path`。
- 违反原则：单一事实来源 | Rust 主路径 | 跨命令生命周期
- 影响：导入、校验、重建和写回会围绕同一 JSONPath 合法性和展开结果做判断，但 Python 与 Rust 各有 parser/matcher/location builder。当前 event import 会先在 Python 构造规则形状再交给 native validation，非标准 data 的 Pydantic 校验也先调用 Python JSONPath parser；Rust 重建和候选扫描再独立解析。任一边界漂移都会出现“导入通过但重建立刻过期”或“同一路径清理/写回身份不一致”。
- Python/Rust 职责判断：JSONPath 语法、模板匹配和 `location_path` 展开属于规则事实，应归入 Rust；Python 只保留外部 JSON 结构读取和错误映射。
- 建议 Rust 接管点：把 path template 解析、模板展开、location path 构造和命中统计统一暴露为 Rust rule contract；Python importer 只调用 Rust 返回的 normalized records。
- 应删除或瘦身的 Python 逻辑：删除或降级 `app/json_path_protocol` 中生产路径使用的 parser/matcher；瘦身 `app/plugin_text/importer.py`、`app/event_command_text/importer.py`、`app/nonstandard_data/rules.py` 的路径校验和展开职责。
- 禁止采用的错误修复方向：不要在 Python 继续复制 Rust parser 细节；不要靠测试中枚举更多路径样例来维持双实现。
- 后续验证：增加“validate/import 通过后 rebuild-text-index 不得因同一 path_template 立刻 stale”的生命周期测试；Rust 侧固定 JSONPath grammar、wildcard、转义键、location path 构造的单测。

### P2：schema/version 契约常量在 SQL、Python、Rust 和测试中重复硬编码

- 证据：`app/persistence/schema/current.sql:466`、`app/persistence/sql.py:49`、`rust/src/native_core/scope_index/storage.rs:20`
- 证据：`app/persistence/sql.py:50`、`rust/src/native_core/text_facts.rs:7`、`app/native_scope_index.py:549`、`app/native_scope_index.py:574`、`app/native_scope_index.py:576`、`rust/src/native_core/scope_index/storage.rs:237`
- 证据：`app/native_scope_index.py:31`、`rust/src/native_core/scope_index/mod.rs:26`、`rust/src/native_core/scope_index/mod.rs:833`
- 证据：`tests/test_persistence.py:229`、`tests/test_persistence.py:894`、`tests/test_persistence.py:895`、`rust/src/native_core/scope_index/storage.rs:1204`
- 业务事实：SQLite `schema_version`、current text fact contract version、native rule candidates JSON schema version。
- 违反原则：单一事实来源 | 测试验收
- 影响：当前数值一致，但事实源不是单点：SQL 写入 17，Python 常量写 17/2，Rust 常量写 17/2/1，测试又断言固定数字。版本升级时必须人工同步多处，否则会出现 Python 仓储、Rust storage、native adapter 或测试对当前契约的理解不一致。
- Python/Rust 职责判断：SQLite DDL 事实源应是 `app/persistence/schema/current.sql` 或由构建脚本生成的单一 contract；text fact/native JSON contract 应有一份机器可读 contract，再由 Python/Rust 消费。
- 建议 Rust 接管点：Rust 可以继续 include 当前 schema SQL，但 schema version、text fact contract version、rule candidate schema version 应来自共享生成物或 Rust 生成并暴露给 Python adapter。
- 应删除或瘦身的 Python 逻辑：避免 Python adapter 再维护独立 `_RULE_CANDIDATES_SCHEMA_VERSION`；`CURRENT_TEXT_FACT_CONTRACT_VERSION` 不应与 Rust 常量手写同步。
- 禁止采用的错误修复方向：不要只修改测试断言数字；不要只在 README/Skill 说明“记得同步”。
- 后续验证：增加 contract 生成物检查或跨语言常量一致性检查；升级 schema/version 时应有单一命令验证 SQL、Python、Rust 三侧读取的是同一事实。

### P2：插件源码 selector 与插件源码 `location_path` 身份算法仍存在 Python/Rust 双实现

- 证据：`app/plugin_source_text/scanner.py:76`、`app/plugin_source_text/scanner.py:269`
- 证据：`rust/src/native_core/write_back_plan/plugin_source.rs:435`、`rust/src/native_core/scope_index/plugin_source.rs:467`、`rust/src/native_core/scope_index/plugin_source.rs:468`
- 证据：`app/plugin_source_text/extraction.py:87`、`app/plugin_source_text/extraction.py:94`、`app/plugin_source_text/extraction.py:111`、`app/plugin_source_text/extraction.py:146`、`app/plugin_source_text/extraction.py:151`
- 业务事实：插件源码 AST 字符串 selector、插件源码文本的 `location_path`、后续 fact identity 和写回定位。
- 违反原则：单一事实来源 | Rust 主路径 | 迁移删减
- 影响：Rust 负责当前 scope index 与写回 selector 校验，但 Python 仍保留 selector 构造、单文件 candidate index fallback 和 `location_path` 构造/解析。当前主流程多处已经使用 native scan，双实现仍会让测试、工具或未来修复绕回 Python 事实源，增加 selector/fact_id 漂移风险。
- Python/Rust 职责判断：selector 和源码定位身份属于 Rust AST 主路径事实；Python 应只消费 Rust 返回的 selector/location_path。
- 建议 Rust 接管点：暴露 Rust selector/location_path parse/build contract，或让 Python 只透传 native scan 输出，不再自行构造。
- 应删除或瘦身的 Python 逻辑：删除或测试隔离 `candidate_selector_for_span`、`build_plugin_source_candidate_index` fallback、`plugin_source_location_path`/`parse_plugin_source_location_path` 的生产使用。
- 禁止采用的错误修复方向：不要通过增加 Python selector 兼容格式、宽松解析或二次匹配来处理写回失败。
- 后续验证：补 Rust selector contract 单测，并增加 Python 层断言插件源码导出、导入、重建、写回全程使用 Rust selector/location_path 输出。

## 双事实来源清单

- 空规则确认 `scope_hash`：Python producer 为 `app/rule_review.py` 与 `app/application/flow_gate.py`，Rust producer 为 `rust/src/native_core/scope_index/rebuild.rs`，consumer 为 `app/text_index.py` 和 workflow gate；建议唯一事实源为 Rust scope hash/evaluate 入口。
- `path_template` / JSONPath：Python producer/parser 为 `app/json_path_protocol/__init__.py` 及各 importer，Rust producer/parser 为 `plugin_config.rs`、`event_commands.rs`、`nonstandard_data.rs`；建议唯一事实源为 Rust rule path contract。
- schema/version：SQL、Python、Rust、测试均保存字面量；建议唯一事实源为共享 contract 生成物或 schema 资源派生值。
- 插件源码 selector/location_path：Python `scanner.py`/`extraction.py` 与 Rust `write_back_plan/plugin_source.rs`、`scope_index/plugin_source.rs` 都能构造；建议唯一事实源为 Rust AST selector contract。
- text fact `scope_hash` / `fact_id`：当前生产主路径主要在 Rust `text_facts.rs` 和 `scope_index/rebuild.rs`，Python 多为读取和校验；本轨道未确认 Python 生产路径直接生成当前 text fact `fact_id`，但测试 helper 中存在手工构造 hash/identity 的噪音，应由轨道 05 继续收束。

## Rust 主路径缺口

- Rust 已接管 text index rebuild、text fact scope/fact 构造、plugin source selector 校验和多类 native candidate scan，但空规则确认 hash 的冷路径仍由 Python 构造。
- Rust 已有 JSONPath/parser/matcher 生产逻辑，但 Python importer 和 nonstandard data 校验仍保留同类语法判断入口。
- Rust 已写入 workflow gate metadata，Python warm path 读取 metadata；缺口在于非索引 gate 没有调用同一 Rust evaluator。

## Python 删除候选

- `app/rule_review.py` 中用于生产当前 `scope_hash` 的函数，后续应改为 Rust adapter 或仅保留 domain 名称解析。
- `app/json_path_protocol/__init__.py` 中生产路径使用的 parser/matcher/location builder；如仍需 CLI 输入预检，应改为调用 Rust。
- `app/plugin_text/importer.py`、`app/event_command_text/importer.py`、`app/nonstandard_data/rules.py` 中 path template 语法和命中判断。
- `app/plugin_source_text/scanner.py` 的 Python selector 构造与 candidate index fallback。
- `app/plugin_source_text/extraction.py` 的插件源码 `location_path` 构造/解析生产使用。

## 测试缺口

- 缺少覆盖所有 rule domain 的冷路径 workflow gate 与 warm index metadata gate 同事实测试。
- 缺少 validate/import/rebuild 生命周期测试，证明同一 `path_template` 不会因 Python/Rust JSONPath 解析差异而在导入后立刻 stale。
- 缺少跨语言版本契约的单一来源检查；现有测试断言固定数字，不能防止新增硬编码事实源。
- 插件源码 selector 需要 Rust contract 单测与 Python adapter 透传测试，避免 Python helper 再成为事实源。

## 交叉引用

- 轨道 02：应继续评估 Python JSONPath、插件源码 selector、nonstandard data 规则覆盖是否应迁入 Rust 主路径。
- 轨道 03：应重点检查 `import-*`、`rebuild-text-index`、`quality-report`、`write-back` 对同一 path/selector/scope 的生命周期是否一致。
- 轨道 04：应继续检查 `workflow_gate_scope_hashes` metadata 是否成为 fast path，是否会绕过当前 Rust evaluator。
- 轨道 05：应审查测试 helper 直接写 rule review state、手工构造 fact identity/hash 的位置。
- 轨道 06：应把本报告列出的 Python 删除候选转为迁移删减清单。

## 已查无发现范围

- 未确认 docs 或 Skill 文件直接作为运行时依赖覆盖 schema、selector、scope hash 或 report 字段；目前看到的 Skill 内容主要描述翻译流程和 CLI 协作边界。
- 未确认 Rust 直接生成 `AgentReport` envelope；`AgentReport` 仍主要是 Python CLI/Agent toolkit 报告边界。
- 未确认当前生产主路径由 Python 直接生成 current text fact `fact_id`；确认的生产构造集中在 Rust `text_facts.rs` / `scope_index/rebuild.rs`。
