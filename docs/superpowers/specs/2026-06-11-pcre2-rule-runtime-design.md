# PCRE2 统一规则运行时设计

## 背景

当前问题不是单个规则的正则方言差异，而是外部规则在导入、校验、存储、扫描、capture 解释、报告和写回协作中存在多处事实源。项目需要一次破坏性收束：所有用户或 Agent 可写规则进入统一规则生命周期，所有用户或 Agent 可写正则统一由 Rust PCRE2 规则运行时负责。

本设计承接 `docs/superpowers/specs/2026-06-10-pcre2-rule-runtime-requirements.md`，描述正式实现前的目标状态和边界。它不是实现计划，不规定具体批次顺序。

## 目标

- 用户或 Agent 可写的正则字段统一使用 PCRE2。
- 用户或 Agent 可写的非正则规则字段进入统一规则模型，但按自身 matcher 语义处理。
- Rust `rule_runtime` 成为规则规范化、语义校验、扫描、capture 解释、规则存储和报告事实的唯一主路径。
- SQLite 规则存储统一成单一规则模型，不再保留多个 domain 规则表作为运行事实源。
- Python 只保留入口、文件读取、基础形状校验、备份文件写入和报告渲染。
- 当前源码、schema、测试、Skill、README、错误文案和 JSON 报告只描述当前契约。
- 被替换的 Python 正则解释、旧规则表读写、旧 regex contract 和旧测试在最终状态中删除。

## 范围

纳入 PCRE2 的外部可写正则字段包括：

- 配置正则：`source_text_required_pattern`、`source_residual_segment_pattern`、`line_width_count_pattern`、`residual_escape_sequence_pattern`。
- 普通占位符规则的 `pattern`。
- 结构化占位符规则的 `pattern`。
- 源文残留结构规则的 `pattern`。
- MV 虚拟名字框规则的 `pattern`。
- 未来新增的用户或 Agent 可写正则字段。

进入统一规则生命周期但不交给 PCRE2 的字段包括：

- 插件规则、事件指令规则、非标准 data 规则中的 JSONPath 或 path template。
- 插件源码规则中的 AST selector。
- Note 标签名、插件名、事件参数 literal match。
- 源文残留 position 规则。

这些字段不是正则，不能用 PCRE2 解释。它们应使用各自 matcher kind，例如 `json_path_template`、`ast_selector`、`literal` 或 `domain_payload`。

不主动纳入本设计的内容：

- 内部固定正则，例如文件名识别、RPG Maker 内置控制符识别、AST 风险启发式。它们不是外部规则契约，可以继续使用 Rust `regex` 或其他合适实现。
- 一次性重写所有非规则字符串处理逻辑。
- 为旧规则表或旧规则文件形态提供迁移兼容。

## 外部文件契约

外部规则文件继续保留 domain 专用格式。命令上下文决定规则类型，例如 MV 虚拟名字框导入命令读取 MV 名字框规则格式，普通占位符导入命令读取普通占位符规则格式。

用户和 Agent 不需要手写统一规则表格式，也不需要在文件内部声明旧引擎、旧规则形态或运行模式。

公开 PCRE2 写法只描述当前契约：

- 命名 capture 使用 `(?<name>...)`。
- flags 使用内联写法，例如 `(?i)`、`(?s)`、`(?m)`。
- 不新增规则级 `flags` 字段。
- 配置示例改成当前 PCRE2 推荐写法，不保留 Python/Rust regex 交集写法。

## Rust Rule Runtime 架构

新增独立 Rust `rule_runtime` 模块，不继续把规则能力塞进 `scope_index::scan_rule_candidates`。模块边界按职责划分：

- `engine`：PCRE2 wrapper，负责 UTF/UCP、内联 flags、命名 capture、资源限制、JIT、编译和匹配错误。
- `model`：统一规则模型、matcher kind、domain state、错误结构、contract version。
- `store`：SQLite 统一规则存储、domain 替换、fingerprint、schema version。
- `adapters`：各 domain adapter，负责把 matcher 结果转成当前业务对象。
- `api`：PyO3 JSON API，供 Python 调用。

依赖方向：

- `rule_runtime` 是底层模块，不依赖 `scope_index`、`quality`、`write_back` 或 Python。
- `scope_index`、`quality`、`write_back` 消费 `rule_runtime` 的公共输出。
- `scope_index` 不再解释外部规则，只使用规则命中和 domain 输出构建 text facts/index。
- adapter 不反向调用 Python。

建议的 native API 形态：

- `prepare_rule_import(payload_json) -> report`
- `commit_rule_import(payload_json) -> report`
- `scan_rule_domain(payload_json) -> report`
- `inspect_rule_store(payload_json) -> diagnostics`
- `build_rules_fingerprint(payload_json) -> fingerprint`

具体函数名可在实现计划中细化，但规则 runtime 必须有独立 API 边界。

## PCRE2 引擎要求

PCRE2 引擎必须提供统一封装，不允许各 domain 直接使用 crate API。

要求：

- 默认启用 UTF 和 UCP 语义。
- 支持内联 flags，不支持独立 `flags` 字段。
- 统一读取命名 capture，并只把 `(?<name>...)` 写入文档、Skill 和测试。
- 支持全局配置级 match limit、match depth 或等价资源限制。
- 资源超限返回结构化错误，不当作未命中，不静默跳过。
- 默认尝试 JIT；JIT 不可用时退回解释执行，并在 diagnostics 中记录。
- 编译错误、匹配错误、资源限制错误必须包含稳定错误码和当前字段信息。
- 同一输入在不同线程数下输出、fingerprint 和写库结果必须稳定。

当前资料显示，`pcre2` crate 0.2.11 是 PCRE2 高层绑定，提供 UTF/UCP、JIT 和 `jit_if_available` 等 builder 能力；`pcre2-sys` 0.2.10 会优先使用系统库，否则静态编译 PCRE2，并说明当前构建脚本应可在 Windows、Linux 和 macOS 工作。高层 `pcre2` 文档未显示 match limit API，因此实现计划必须验证资源限制是否需要下探到 `pcre2-sys` 或在 runtime wrapper 中补充低层调用。

PCRE2 资料依据：

- [pcre2 crate 文档](https://docs.rs/pcre2/latest/pcre2/)
- [pcre2 RegexBuilder 文档](https://docs.rs/pcre2/latest/pcre2/bytes/struct.RegexBuilder.html)
- [pcre2-sys build.rs](https://docs.rs/crate/pcre2-sys/0.2.10/source/build.rs)
- [PCRE2 JIT 官方文档](https://www.pcre.org/current/doc/html/pcre2jit.html)

crate 选择优先级：

1. Windows 发行包稳定。
2. PCRE2 能力完整。
3. 维护成本低。

## 统一规则存储

统一规则存储至少包含三类逻辑数据：

- `rule_sets`：记录某个 domain 的当前导入批次、规则数量、来源、scope/context hash、导入时间、runtime contract version 和 store schema version。
- `rules`：记录规则条目，包括 `rule_id`、domain、`rule_order`、`matcher_kind`、matcher 主值、`payload_json`、enabled、hash、source_kind。
- `rule_domain_states`：记录 confirmed_empty、风险确认、scope hash、确认时间等没有真实规则但影响流程的 domain 状态。

domain 专用字段放入 `payload_json`，不拆成宽表列。Rust domain adapter 对 `payload_json` 做 schema 和语义校验。Python 不读取 payload 内部语义。

配置正则不写入 `rules` 表，因为它们来自 `setting.toml`。它们必须进入 runtime 编译、行为计算和 `rules_fingerprint`。

规则顺序是契约：

- 外部文件顺序进入 normalized `rule_order`。
- `rule_order` 参与运行、存储和 fingerprint。
- 数据库读取按 `(domain, rule_order, rule_id)` 稳定排序。

`rule_id` 由 Rust 规范化生成，不要求外部文件手写。生成必须稳定：同一 normalized 规则重复导入应得到同一 `rule_id`。

重导入只替换当前 domain，不影响其他 domain。第一版不暴露单条规则启停或删除；可以预留 enabled 字段，但当前契约不描述单条管理能力。

## Domain Adapter 原则

每个 adapter 明确声明：

- 输入上下文。
- 允许的 matcher kind。
- 必需 capture。
- 可选 capture。
- capture 到业务字段的映射。
- capture 空值策略。
- 模板校验和渲染规则。
- 多规则冲突策略。
- 无命中是 error 还是 warning。
- 输出结构。

默认原则：

- 无命中默认是 error，只有 adapter 明确说明业务理由时才可降级为 warning。
- 语义要求唯一解释的 domain，多个规则命中同一对象时返回 error。
- 允许叠加或覆盖的 domain 必须声明排序和优先级。
- 模板校验、模板字段引用、模板渲染、非法占位符检查都属于 adapter 语义，不能留在 Python。

domain 建模：

- 普通占位符和结构化占位符继续作为两个 domain。
- 源文残留保留一个 `source_residual` domain，内部区分 position 和 structural；只有 structural 走 PCRE2。
- 插件参数、事件指令、Note、非标准 data、插件源码等非正则规则也进入统一 store，按各自 matcher 校验。

## 导入与校验流程

保留 `validate-*` 和 `import-*` 的当前语义，但两者必须共用同一个 Rust runtime 路径。

`validate-*` 是 dry-run：

- 只执行 prepare。
- 不写 SQLite。
- 不写备份文件。
- 返回如果导入会发生的影响，例如将备份并清理多少条已保存译文。

`import-*` 执行两阶段导入：

1. Python 读取规则文件、解析 JSON/TOML、做基础形状校验，并加载当前命令所需最小游戏上下文。
2. Python 调 Rust `prepare_rule_import`。
3. Rust 完成规则规范化、PCRE2 编译、非正则 matcher 校验、domain adapter 校验、命中扫描、影响分析、备份/清理计划和 `plan_token` 生成。
4. 如需清理已保存译文，Python 先写备份文件并校验可读。
5. Python 将备份路径和 `plan_token` 传给 Rust `commit_rule_import`。
6. Rust 校验 `plan_token` 仍匹配当前数据库状态，在一个 SQLite 事务里替换当前 domain 规则、写 domain state、清理无效译文并记录备份路径。

备份策略：

- 如果规则变化导致已保存译文脱离当前文本事实，自动备份后清理无效译文。
- 备份文件由 Python 写。
- Rust prepare 返回待备份记录和清理计划。
- 备份失败时不能修改数据库。
- commit 失败时不能留下半导入规则。
- 导入报告必须说明备份路径、清理数量和影响范围。

`plan_token` 至少覆盖：

- domain
- normalized rules hash
- game context hash
- 当前 DB rules hash
- cleanup plan hash
- rule runtime contract version

commit 时发现 token 不匹配，必须失败并要求重新运行 import。

空规则确认也走同一套 prepare/commit：

- `confirm_empty=true` 时 prepare 校验当前候选范围和确认语义。
- commit 写入 `rule_domain_states`，规则条目数为 0。
- 需要确认的 domain 没有 `confirm_empty` 时默认 error。

## Python 边界

Python 保留：

- CLI 参数和命令编排。
- 规则文件读取。
- JSON/TOML 语法解析。
- Pydantic 基础形状校验。
- 加载命令所需文件上下文。
- 调用 Rust native API。
- 写备份文件。
- 渲染中文摘要和 JSON 报告。

Python 不保留：

- 用户、Agent 或配置正则的 `re.compile`。
- capture 分组检查。
- capture 到业务对象的解释。
- 规则命中判断。
- 模板字段语义校验。
- 与 Rust 同目的的扫描、覆盖和质量判断。
- 直接写统一规则表或旧 domain 规则表。

Pydantic 只能校验形状和基础类型，例如字段存在、数组类型、字符串非空。PCRE2 编译、capture、路径命中、selector 命中、模板语义和 domain 解释都必须进入 Rust。

最终删除：

- Python `regex_contract.py`。
- Rust `regex_contract.rs`。
- `fancy-regex` 依赖。
- Python `TextRules` 中承载的规则语义。`TextRules` 要么删除，要么瘦身为配置 DTO 或展示辅助。

Rust `regex` 可以继续用于内部固定正则，但不能解释外部可写正则。

## 旧数据与旧路径处理

不做旧规则迁移，不做兼容识别。

最终状态：

- `current.sql` 不再创建旧 domain 规则表。
- Python `rule_records.py` 不再提供旧规则表读写 API。
- Rust 不再读取旧规则表。
- 旧 SQL 常量、旧 schema 字段、旧测试夹具和旧报告字段删除。
- 旧库缺少当前统一规则 schema 或当前规则模型时，依赖规则的命令显式失败，提示重新导入当前规则或重建当前数据库。

运行时错误只说明当前要求和当前问题，不解释旧表结构或旧规则形态。破坏性变化写入 `CHANGELOG.md` 或发布说明。

## Fingerprint 与版本

统一 `rules_fingerprint` 必须包含：

- 所有当前 domain 的规则条目。
- domain state，例如 confirmed_empty 或风险确认。
- 配置正则。
- 规则顺序、matcher、payload、enabled 状态。
- `rule_runtime_contract_version`。
- `rule_store_schema_version`。

版本维度：

- `rule_runtime_contract_version`：Rust/Python JSON API、错误结构和 runtime 语义版本。
- `rule_store_schema_version`：SQLite 统一规则表 schema 版本。

版本必须进入 diagnostics 和 fingerprint。schema 不匹配时显式失败，不做隐式升级或旧表迁移。

## 报告与错误

不为旧 JSON 报告字段做兼容。所有 validate/import/scan/export/report 输出只描述当前统一规则模型和当前 runtime 结果。旧字段、旧错误码、旧 warning 口径如果不适合当前契约，直接删除或重命名。

结构化错误至少包含：

- `code`
- `domain`
- `rule_id` 或 `rule_key`
- `field`
- `message`
- `details`
- `location`，仅扫描具体文本时出现

用户可见文案必须说明：

- 发生了什么。
- 影响什么。
- 下一步怎么修。

用户可见文案不得暴露旧表、旧引擎、Python re、fancy-regex 或旧规则形态。stdout 摘要显示短 pattern 摘要和可读 rule name；JSON details 可以包含完整 pattern。真实本机路径必须脱敏，超长 pattern 截断展示。

## Diagnostics 与性能

diagnostics 只记录阶段级和 domain 级信息，不做 per-row 打点。

至少记录：

- `rule_runtime.compile_ms`
- `rule_runtime.scan_ms`
- `rule_runtime.store_ms`
- `rule_runtime.domain_timings`
- `rule_runtime.jit_enabled`
- `rule_runtime.thread_count`
- `rule_runtime.rule_count_by_domain`
- `rule_runtime.error_count_by_code`

扫描可并发，但输出必须稳定排序。同样输入在不同线程数下，输出 JSON、fingerprint 和写库结果必须一致。线程数走现有 runtime 配置，不从规则文件配置。

最终交付必须提供真实 CLI 性能证据，至少覆盖规则导入、重建索引或质量报告中的关键路径，并展示 diagnostics 中 rule runtime 阶段耗时、线程数和 JIT 状态。

## 文档、Skill 与 Prompt 边界

README、Skill、示例和错误文案只描述当前契约。

要求：

- Agent 规则任务明确使用 PCRE2 和 `(?<name>...)`。
- `setting.example.toml` 改成当前 PCRE2 推荐写法。
- docs 只做人类说明，不作为 Agent 黑盒执行契约。
- 修改 Skill 协议时优先修改 `skills/att-mz-protocol/`，再运行 `uv run python scripts/generate_skill_protocol.py --write`。
- 交付前运行 `uv run python scripts/generate_skill_protocol.py --check`。
- 破坏性变化写入 `CHANGELOG.md` 或发布说明。

内部统一规则模型不得泄露进翻译 prompt：

- `rule_id`、`payload_json`、数据库表名和内部规则 store 字段不进入翻译 prompt。
- Agent 规则编写任务可以看到 domain 专用候选和规则格式，但不看到统一规则表内部结构。
- 修改 prompt 组装逻辑时必须测试不会出现内部字段、内部文件名或无效上下文。

## 测试策略

Rust 测核心语义：

- PCRE2 编译成功和失败。
- 内联 flags。
- UTF/UCP 行为。
- 命名 capture 提取。
- 必需 capture 缺失。
- capture 空值策略。
- 资源限制生效。
- JIT fallback 可观测。
- domain adapter 输出结构。
- 多规则冲突。
- 统一 rule store 写入。
- prepare/commit 和 `plan_token`。
- rules fingerprint 稳定。
- 并发扫描结果稳定。

Python 测流程契约：

- CLI 参数链路。
- `validate-*` dry-run 不写库。
- `import-*` 写统一规则表。
- 备份文件写入和失败处理。
- 中文摘要和 JSON 报告。
- 旧库失败。
- Python 不再解释外部或配置正则。
- Skill 生成物检查。
- prompt 不泄露内部规则模型。

删除或改写旧测试：

- 不保留绑定旧规则表、旧字段、旧错误码、旧 Python 正则解释或旧报告口径的测试。

验证策略：

- 中间批次运行针对性 Python 测试和相关 Rust 测试。
- 触及 Rust 原生扩展的批次运行 Rust 格式检查、clippy 和相关 Rust 测试。
- `uv run basedpyright` 在关键 Python 边界变更后运行。
- 全量 `uv run pytest` 只在最终收尾门禁运行。
- 最终完成前必须运行 `uv run basedpyright`、`uv run pytest`、Rust fmt/clippy/test。

## 验收标准

完成后必须满足：

- 所有用户或 Agent 可写正则统一由 PCRE2 处理。
- 非正则规则字段进入统一规则模型，但不被 PCRE2 解释。
- Rust `rule_runtime` 是规则语义、规则存储和规则报告事实的唯一主路径。
- SQLite 当前 schema 只描述统一规则模型。
- 旧 domain 规则表和旧读写路径已删除。
- Python 不编译、不匹配、不解释用户、Agent 或配置正则。
- Python 不解释 capture、不校验模板语义、不写规则表。
- `scope_index`、`quality`、`write_back` 不再各自解释外部规则。
- `validate-*` 和 `import-*` 共用 Rust prepare 路径。
- `import-*` 使用备份加 commit 的两阶段导入。
- scan/export/report 类规则事实来自 Rust runtime。
- 当前 README、Skill、示例、错误文案和测试只描述当前契约。
- `regex_contract.py`、Rust `regex_contract.rs`、`fancy-regex` 和旧测试已删除。
- 真实 CLI 性能证据已记录。
- `uv run basedpyright`、`uv run pytest`、Rust fmt/clippy/test 通过。
