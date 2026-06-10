# Rust 主路径总重构蓝图设计

## 背景与结论

本设计基于 `docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md`。该总报告结论为 `FAIL`，原始确认发现合计 21 条：P0 3 条、P1 9 条、P2 9 条、P3 0 条。

本设计不是第一期短修，也不是只修 P0 的补丁单。它覆盖总报告全部 P0、P1、P2，并把后续实现组织成总重构蓝图、分阶段执行。后续 plan 可以分批落地，但必须覆盖全部阶段、全部删除项和全部验收要求。

总报告揭示的同根问题是：当前候选事实、gate 事实、规则命中事实、metadata/cache 事实没有统一事实源。Python 与 Rust 在多个入口分别生产或修正同一业务事实，metadata 和 fast path 又可能把旧结论当成当前事实消费，导致跨命令生命周期漂移。

## 最终目标状态

Rust/native contract 是候选扫描、规则命中、gate 判断、stale 判断、scope hash、metadata/cache 版本校验的唯一事实源。Python 只负责 CLI 编排、配置校验、数据库事务编排、报告组装和错误映射，不再生产或修正这些事实。

完成后的系统必须满足：

- 同一候选集合只由 Rust/native 当前 contract 产出。
- 同一 selector、path template、rule hit、scope hash、stale 结论和 gate 结论只有一个当前事实源。
- `rebuild-text-index`、`translate`、`quality-report`、`write-back` 消费同一套 Rust facts，不消费 Python 临时判断，也不消费过期 metadata 假事实。
- text index metadata 和 runtime scan cache 必须携带 Rust/native/parser contract version；版本不匹配时显式失效。
- Rust 接管某条生产主路径后，同功能 Python 重型扫描、候选、校验、AST、规则命中或写回协议判断必须删除或降级为非生产编排。

## 问题归并

### Gate metadata 伪事实

`workflow_gate_prechecked:* = passed`、空 `gate_errors`、已存 metadata shortcut 都不能表达生成该结论时的 Rust 候选口径、规则口径、parser 口径和 scope hash。后续命令消费这些 shortcut 时，实际消费的是旧状态或空标记，不是当前候选 gate 事实。

### Python/Rust 双事实源

插件源码、Note 标签、非标准 data、path template、JSONPath、scope hash、selector、location_path、placeholder 等路径存在 Python 和 Rust 双实现。即使单命令当前能运行，导出、校验、导入、重建、翻译、质量报告、写回之间也可能消费不同事实。

### Cache contract 缺失

warm text index、runtime plugin source scan cache 和部分 fast path 只比较文件 hash、item count、rules fingerprint 或数据库旧规则，没有校验 Rust/native/parser contract version，也没有证明当前 AST、启用状态、selector 和审计口径仍然新鲜。

### 测试与性能验收倒挂

部分测试固定 shortcut 行为或异常文案，未固定错误码、事实状态和跨命令生命周期。scan budget 能防止复杂度失控，但不能替代当前 HEAD 的真实 CLI 性能证据。

## 目标架构

### Scope Facts Contract

Rust/native 提供统一的 Scope Facts Contract。它是跨命令共享的事实契约，不是单个扫描函数。它负责产出当前 scope 内所有可被后续命令消费的事实：

- source branch：标准 data、非标准 data、插件源码、Note 标签、事件指令、插件参数等来源类型。
- text identity：文本身份、source text、location_path、selector、文件身份、scope 归属。
- candidate state：候选是否可翻译、是否被过滤、过滤原因、是否可写回。
- source snapshot：文件 hash、插件启用状态、parser contract、native contract、规则 contract。
- scope hash：空规则确认、导入校验、重建和后续 gate 共用同一口径。

Python 只能消费 Scope Facts Contract 的输出，不再独立构造候选集合、selector、location_path 或 scope hash。

### Rule Facts Contract

Rust/native 负责产出规则命中和规则有效性事实：

- rule hit details。
- path template / JSONPath 展开结果。
- translation prefixes。
- selector 命中、filtered selector、excluded selector。
- 导入规则是否仍匹配当前事实。
- Note 标签、非标准 data、插件源码规则的稳定错误码。

Python 不再展开当前 rule hit，不再维护第二套 path template 语义，不再执行 Note 标签精确源匹配、tag 命中和可翻译统计判断。

### Gate Facts Contract

Rust/native 负责产出当前 gate 事实：

- translate gate。
- quality-report gate。
- write-back gate。
- audit/review coverage gate。
- gate 失败错误码、用户可行动原因和关联事实。

`rebuild-text-index` 写入的必须是真实 gate facts 和 contract version，不能写入 `passed` 字符串 shortcut。后续命令必须验证 contract version 后消费 gate facts；无法验证时重新计算或显式失败。

### Stale Facts Contract

Rust/native 负责产出 stale 判断：

- 规则 stale。
- selector stale。
- file hash stale。
- scope hash stale。
- parser/native contract stale。
- 启用状态 stale。
- 过滤口径变化。

错误码必须区分“AST 不存在”“selector 被当前过滤口径排除”“源码文件变化”“插件启用状态变化”“contract 变化”。Python 不再用文案、字符串匹配或二次扫描修正 stale 语义。

### Metadata/Cache Contract

text index metadata 和 runtime scan cache 必须记录并校验：

- Rust contract version。
- native schema version。
- parser contract version。
- source branch contract version。
- rules fingerprint。
- scope hash。
- source snapshot。

metadata/cache 命中必须证明它仍对应当前 contract。旧 contract metadata/cache 不允许被当作当前事实源；不能静默兼容或自动放行。

### Python 消费边界

Python 保留：

- CLI 参数解析和配置校验。
- 调用 Rust/native contract。
- SQLite 事务编排。
- JSON report 和用户报告组装。
- 错误码到中文用户文案的映射。
- 模型 SDK 调用和 prompt 组装。

Python 禁止：

- 生产或修正 scope hash、selector membership、stale 判断、rule hit 展开、path template 展开、插件源码 coverage/risk。
- 在 hot path 中新增 fallback、兼容分支、二次扫描或兜底判断。
- 把旧 scanner/extractor/oracle 留作公共 API，等待调用方自觉不用。

## 分阶段执行蓝图

### 阶段 1：Contract Foundation

建立统一 Rust facts schema 和错误码边界，定义后续阶段共享的结构。

需要完成：

- 定义 Scope Facts、Rule Facts、Gate Facts、Stale Facts、Metadata/Cache Contract 的 Rust 输出 schema。
- 定义 source branch、contract version、parser version、native schema version 的稳定字段。
- 定义跨 Python/Rust 的错误码集合和字段含义。
- 固定 Python adapter 只消费 contract 输出，不在 adapter 内补业务判断。
- 补 Rust contract 层单测和 Python adapter schema 测试。

完成条件：

- 后续阶段不能再各自发明 facts 字段。
- Python 和 Rust 对 contract 字段含义只有一个事实源。
- 所有新增字段都有测试覆盖。

### 阶段 2：Gate + Metadata Lifecycle

收束 `rebuild-text-index` 到后续命令的 gate 生命周期，解决 metadata shortcut 和 cache contract 问题。

需要完成：

- `rebuild-text-index` 写入真实 Rust gate facts，而不是 `workflow_gate_prechecked:* = passed`。
- `translate`、`quality-report`、`write-back` 消费当前 contract 匹配的 Rust gate facts。
- 空 `gate_errors` 不再代表“通过”；通过状态必须有明确 contract、scope 和 source branch 证据。
- warm text index 校验 Rust/native/parser contract version。
- runtime plugin source scan cache 校验 AST/parser/audit contract。
- 旧 contract metadata/cache 显式失效，必要时要求重建或重新扫描。

完成条件：

- 后续命令不能通过 metadata shortcut 绕过当前候选 gate。
- 旧 metadata/cache 不会被当作当前事实源。
- 覆盖公开导入、冷重建、后续 translate/quality-report/write-back 的生命周期测试。

### 阶段 3：Plugin Source Rust Primary Path

收束插件源码主路径，删除 Python selector、stale、coverage、risk 双判断。

需要完成：

- Rust 输出插件源码 validate/import/extract 需要的 selector 命中、excluded selector、filtered selector。
- Rust 输出 stale reason、review coverage、risk summary 和稳定错误码。
- Rust 输出插件源码 scope hash 和当前 source branch gate facts。
- Python 删除插件源码 selector membership、file hash、stale、coverage、risk 二次判断。
- only `excluded_selectors` 的 fast path 必须验证当前 AST、启用状态、selector 新鲜度和 text index contract。

完成条件：

- 插件源码导出、校验、导入、重建、翻译、质量报告、写回消费同一 Rust facts。
- selector 未变时，导入成功后冷重建不 stale。
- selector 仍在 AST 中但被过滤时，错误码说明过滤口径变化。
- 旧 Python 插件源码生产事实源被删除或降级为非生产胶水。

### 阶段 4：Nonstandard Data + Path Template + Note Tag

收束剩余双事实源：非标准 data、path template、JSONPath、Note 标签。

需要完成：

- Rust 统一 JSONPath/path template 解析和展开。
- Rust 输出非标准 data rule hit details、translation prefixes、stale reason。
- Rust 提供 Note 标签导入规则验证结果、错误码和可翻译统计事实。
- Python 删除 `NonstandardDataTextExtraction` 的当前 rule hit 展开职责。
- Python 删除 `collect_nonstandard_data_rule_hits` 的生产命中展开职责。
- Python 删除 Note 标签导入规则精确匹配、tag 命中、可翻译统计业务判断。

完成条件：

- 非标准 data 的 validate/import/rebuild/text scope 消费同一 Rust rule facts。
- Note 标签规则验证不再依赖 Python 业务判断。
- path template / JSONPath 不再存在 Python/Rust 两套当前语义。

### 阶段 5：Deletion + Test/Performance Evidence

全局删除旧事实源，补齐测试退场和真实性能证据。

需要完成：

- 移除公共 API 中旧 Python scanner/extractor/oracle。
- 迁移旧 Python oracle parity 测试到 Rust/native contract 测试。
- 瘦身 Python 大集成测试，只保留流程契约和外部可观察行为。
- 补插件源码、非标准 data、Note 标签的公开导入 -> 冷重建 -> 后续命令生命周期测试。
- 补真实 CLI 性能结果、内部阶段耗时、扫描次数和并发配置证据。
- 确认临时 benchmark、runner、manifest、夹具和生成数据没有作为交付文件留在仓库。

完成条件：

- scan budget、行为测试、真实 CLI timings 三者齐备。
- 旧 Python 事实源没有公共导出和生产调用方。
- 最终验证命令通过，或明确记录无法执行的原因、影响范围和剩余风险。

## 发现到阶段映射

| 严重度 | 发现 | 阶段 | 验收证据 |
| --- | --- | --- | --- |
| P0 | workflow gate metadata 不是当前候选 gate 事实 | 阶段 2 | `rebuild-text-index` 写真实 gate facts；后续命令校验 contract 后消费；生命周期测试覆盖 |
| P0 | 插件源码排除 selector fast path 可绕过当前 AST / selector 新鲜度 | 阶段 2、阶段 3 | excluded-only fast path 校验当前 AST、启用状态、selector 和 text index contract |
| P0 | 空规则确认 scope hash 有 Python 冷路径与 Rust warm index 双事实源 | 阶段 1、阶段 3 | scope hash 只由 Rust contract 产出；Python helper 删除；Rust/Python contract 测试覆盖 |
| P1 | `path_template` / JSONPath 语法和 `location_path` 展开仍由 Python 与 Rust 分别维护 | 阶段 1、阶段 4 | Rust 统一展开；Python 当前展开逻辑删除；规则命中测试覆盖 |
| P1 | 插件源码候选、selector、stale 和风险判断仍在 Python 二次实现 | 阶段 3 | Rust 输出 selector/stale/risk；Python 二次判断删除；插件源码生命周期测试覆盖 |
| P1 | Note 标签规则验证仍由 Python 执行精确匹配和可翻译判断 | 阶段 4 | Rust 输出 Note 标签验证事实和错误码；Python 业务判断删除 |
| P1 | 插件源码 `excluded_selectors` fast path 只比对已存规则 | 阶段 2、阶段 3 | fast path 必须验证当前 facts；旧数据库规则不能单独证明通过 |
| P1 | text index metadata 没有持久记录 Rust/native contract version | 阶段 2 | metadata 写入并校验 contract version；旧 metadata 显式失效 |
| P1 | 当前运行插件源码持久 scan cache 只按文件 hash 命中 | 阶段 2、阶段 3 | scan cache 增加 AST/parser/audit contract；旧 cache 失效 |
| P1 | 缺少“规则导入成功后冷重建不能立刻 stale”的非空规则生命周期回归 | 阶段 2、阶段 3、阶段 5 | 公开导入 -> 冷重建 -> 后续命令测试覆盖插件源码和非空规则 |
| P1 | 插件源码规则已宣称 Rust 主路径，但 Python 仍承担 selector 校验、stale 判断和覆盖门禁 | 阶段 3 | 对应 Python 路径删除；Rust contract 测试和流程测试覆盖 |
| P1 | 非标准 data 文本范围仍通过 Python 提取器展开规则命中 | 阶段 4 | Rust 输出 rule hit details；Python 提取器生产职责删除 |
| P2 | schema/version 契约常量在 SQL、Python、Rust 和测试中重复硬编码 | 阶段 1、阶段 2 | contract/version 常量收束；测试只依赖单一事实源 |
| P2 | 插件源码 selector 与插件源码 `location_path` 身份算法仍存在 Python/Rust 双实现 | 阶段 3 | Rust 输出身份事实；Python 只消费；双实现删除 |
| P2 | 普通 placeholder 生产路径已转 native，但旧 Python 扫描器仍在 `app` 包导出 | 阶段 5 | 公共导出删除；调用方迁移；native contract 测试覆盖 |
| P2 | 测试把“不在 Python 热路径偷扫”固定成“后续命令不消费插件源码高风险” | 阶段 2、阶段 5 | 测试改为验证 Rust gate facts，而不是固定 shortcut 行为 |
| P2 | 写回验收 helper 在测试层手工构造 current text fact | 阶段 5 | 测试改走冷重建事实源；helper 不再绕过 Rust facts |
| P2 | 部分直接写入命令只断言异常文案，没有固定错误码与事实状态 | 阶段 1、阶段 5 | 错误码、事实状态和用户文案映射均被测试固定 |
| P2 | 旧 Python 提取器和 helper 仍作为包根公共 API 暴露 | 阶段 5 | 公共 API 删除或降级为非生产内部胶水；调用方扫描无生产依赖 |
| P2 | 测试仍把 Python 旧实现当 native 对照 oracle | 阶段 5 | parity 测试退场；Rust/native contract 测试成为 oracle |
| P2 | 性能验收仍缺当前 HEAD 的真实 CLI 计时闭环 | 阶段 5 | 提供真实 CLI 总耗时、阶段耗时、扫描次数、并发配置和瓶颈归因 |

## 删除清单

### 必须删除的生产事实源

以下路径不能继续生产候选、gate、stale、selector、rule hit 或 scope hash 等事实：

- `app/rule_review.py` 中生产 scope hash 的 Python helper。
- `app/plugin_source_text/native_scan.py` 中插件源码 Python 二次过滤、风险计算和源文判断。
- `app/plugin_source_text/importer.py` 中 selector membership、file hash、stale 校验。
- `app/plugin_source_text/rules.py` 中 stale 与 review coverage 判断。
- `app/plugin_source_text/extraction.py::PluginSourceTextExtraction` 的生产扫描职责。
- `app/nonstandard_data/extraction.py::NonstandardDataTextExtraction` 的当前 rule hit 展开职责。
- `app/text_scope/rule_hits.py::collect_nonstandard_data_rule_hits` 的生产命中展开职责。
- `app/native_note_tag_scan.py` 中 Note 标签导入规则精确匹配、tag 命中、可翻译统计判断。
- `app/agent_toolkit/placeholder_scan.py::scan_placeholder_candidates` 及其公共导出，如果它仍作为生产扫描事实源。

每个删除项必须在 plan 中绑定替代 Rust contract、调用方迁移、测试覆盖和删除验收。不能只标记“未来清理”。

### 必须废弃的 shortcut/cache 语义

以下语义不能再代表当前事实：

- `workflow_gate_prechecked:* = passed`。
- 空 `gate_errors` 代表“通过”。
- runtime plugin source scan cache 只靠 file hash 命中。
- warm text index 不比较 Rust/native/parser contract。
- excluded-only fast path 不验证当前 AST、启用状态和 selector 新鲜度。

## 明确禁止的修复方向

- 不在 Python 新增 selector fallback、stale 二次判断、风险阈值补丁或 path template 兼容分支。
- 不让 Python 和 Rust 长期保留同一候选事实的双实现。
- 不用 `workflow_gate_prechecked:* = passed` 继续代表当前 gate 已审查。
- 不把旧 Python scanner/extractor 保留在包根公共 API 中等待调用方自觉不用。
- 不用更宽松的中文文案正则替代错误码和事实状态断言。
- 不把 scan budget 或旧性能报告写成当前 HEAD 真实 CLI 性能通过。
- 不为了兼容旧数据库、旧规则或旧 metadata 默默放行；旧 contract 必须显式失效。

## 测试、性能与门禁

### Rust contract 测试

Rust 测核心事实：

- scope hash 生成。
- selector、excluded selector、filtered selector。
- plugin source stale reason、coverage、risk summary。
- nonstandard data rule hit details、path template 展开、translation prefixes。
- Note 标签规则验证、错误码。
- metadata/cache contract version 比较和失效。
- gate facts 生成与错误码。

### Python 流程契约测试

Python 只测外部可观察流程：

- CLI 参数到 Rust contract 调用的链路。
- 错误码映射到中文用户文案。
- JSON report 字段和退出码。
- SQLite 事务结果。
- translate、quality-report、write-back 是否拒绝旧 contract metadata。
- 公开导入 -> 冷重建 -> 后续命令不会 stale 误判或 gate 漏判。

### 生命周期回归测试

必须覆盖：

- 公开导入插件源码规则。
- 不依赖当前内存扫描事实，冷重建 text index。
- 再执行 translate、quality-report、write-back。
- 验证后续命令消费的是 Rust gate facts，不是 shortcut。
- 插件源码、非标准 data、Note 标签至少各一个关键路径。

### 性能与并发证据

scan budget 只保留为复杂度保护，不能当性能证明。实现计划必须采集当前 HEAD 的真实 CLI 证据：

- 至少包含一个大规模项目或项目内约定 fixture。
- 记录命令总耗时、Rust 阶段耗时、Python 编排耗时、扫描次数。
- 记录 `ATT_MZ_RUST_THREADS` 或配置并发数是否真实参与调度。
- 对比重构前后，说明瓶颈归因和剩余风险。
- 临时 benchmark、runner、manifest、测试夹具和生成数据不得作为交付文件留在仓库。

### 最终验证命令

涉及 Python/Rust 源码、测试、schema、构建流程、发行流程或可执行契约的阶段，交付前必须执行：

```powershell
uv run basedpyright
uv run pytest
```

修改 Rust 原生扩展、构建流程或发行流程时，还必须在 Rust crate 对应工作目录执行：

```powershell
cargo fmt -- --check
cargo clippy --all-targets -- -D warnings
cargo test
```

涉及 Skill 协议、生成 Skill、README 映射或发布脚本时，必须按项目规则执行：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

无法执行应跑验证时，交付说明必须说明具体原因、影响范围和剩余风险。

## 后续 Plan 生成要求

后续 implementation plan 必须覆盖五个阶段，不能只写第一阶段。每个任务应明确适用项：

- 新增或收束 Rust contract。
- 迁移 Python 消费路径。
- 删除旧 Python 事实源。
- 补 Rust contract 测试。
- 补 Python 流程测试。
- 补生命周期回归。
- 补性能和并发证据。
- 执行验证命令。

plan 可以按阶段拆成多批执行，但必须保留全局依赖和最终完成定义。任何临时迁移路径必须写明删除条件、删除触发点和验收方式。

## 成功状态

本总重构蓝图完成后，应达到：

- Rust/native contract 成为当前候选事实、规则命中事实、gate 事实、stale 事实、scope hash 和 metadata/cache contract 的唯一事实源。
- Python 只保留 CLI 编排、配置校验、事务编排、报告组装、错误映射、模型接口等边界职责。
- 总报告全部 P0/P1/P2 均有对应阶段、代码边界和验收证据。
- 旧 Python 生产事实源和 shortcut/cache 假事实被删除或显式失效。
- Rust contract 测试、Python 流程测试、生命周期测试和真实 CLI 性能证据共同证明重构完成。
