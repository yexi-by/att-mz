# Text Fact Contract v2 破坏性重构设计

## 背景

当前工具已经把大量重型扫描迁到 Rust，但文本事实的核心语义仍没有统一分层。不同模块会把同一段文本同时当作原始协议片段、玩家可见文本、模型翻译正文、写回模板字段、质量检查输入或 stale 判断身份。MV 虚拟名字框问题暴露了这个共同根因：`body` 既承载格式空白，又承载可翻译正文，导致校验、索引和写回之间出现契约漂移。

本设计取代“在现有字段上继续补丁”的路线，建立 `Text Fact Contract v2`。Rust 是唯一文本事实生产者，`rebuild-text-index` 直接写入 SQLite v2 事实表。Python 只读 v2 facts，负责 CLI 编排、配置校验、事务控制、报告渲染和用户文案。旧数据库、旧工作区、旧规则 scope 和旧 runtime map 不迁移，遇到 v1 事实契约直接显式失败并要求重建。

## 抽象根因

核心问题不是某个 `.trim()` 写错，而是缺少稳定的事实层边界：

- 原始文本和清洗后的语义文本混在同一字段里。
- 写回所需的格式壳和模型应翻译的正文混在同一字段里。
- 导出、校验、索引、写回和质量检查各自重新解释文本。
- Python 和 Rust 在同一领域保留并行判断，形成第二事实来源。
- 错误报告丢失 raw/rendered 对比，弱模型或弱 Agent 只能猜测原因。

`Text Fact Contract v2` 的目标是让每条文本事实都明确回答：它从哪里来、原始形态是什么、玩家可见文本是什么、真正送翻译的正文是什么、写回时哪些片段必须保留、哪些 hash 用于 stale 判断。

## 目标

- 新建 SQLite v2 fact 表，并由 Rust `rebuild-text-index` 直接写入。
- 统一 `raw_text`、`visible_text`、`translatable_text`、`render_parts`、hash 和 scope 语义。
- 让标准 data、MV 虚拟名字框、插件配置、事件指令、Note、非标准 data、插件源码、placeholder、structured placeholder 和 active runtime literal 都能接入同一事实契约。
- 所有生产命令改读 v2 facts；Python 不再构建完整文本范围来复现 Rust 事实。
- 旧数据库、旧工作区、旧规则 scope hash、旧 runtime map 遇到 v2 需求时显式失败。
- 重型扫描和事实分类向 Rust 收敛，Python 只做薄适配和报告。
- 性能不得回退：每批迁移必须证明没有新增 Python 全量扫描或重复全量扫描，最终给出真实 CLI 性能证据。
- 弱模型/弱 Agent 只需要理解稳定字段和错误提示，不需要用复杂正则保住格式空白。

## 非目标

- 不兼容旧数据库或旧工作区。
- 不自动迁移旧 `translation_items` 为 v2 facts。
- 不把 docs、Skill 或 Markdown 作为运行时事实源。
- 不为单个游戏样本写特判。
- 不用 Python 回退重扫来补 Rust fact 缺口。
- 不一次性重写模型调用、prompt 调度或外部 OpenAI 兼容接口。
- 不为了性能提前引入文本去重表；v2 表先直接存全文，后续只有在真实证据显示 SQLite 体积或 I/O 成为瓶颈时再设计去重。

## 事实分层

每条事实必须区分以下字段：

| 字段 | 含义 | 用途 |
| --- | --- | --- |
| `raw_text` | 文件、JSON、JS 字符串或事件指令中的原始片段 | selector、stale、原样格式保留、写回定位 |
| `visible_text` | 解码后玩家可见文本 | 候选判断、质量检查、报告展示 |
| `translatable_text` | 真正送模型翻译的正文 | prompt、译文保存、人工修复表 |
| `render_parts` | 写回需要保留或替换的结构片段 | 译文写回、术语写入、运行映射 |
| `raw_hash` | 基于 `raw_text` 的身份 | 原始片段 stale 判断 |
| `visible_hash` | 基于 `visible_text` 的身份 | 可见文本覆盖和 runtime map |
| `translatable_hash` | 基于 `translatable_text` 的身份 | 去重翻译、译文匹配 |
| `scope_hash` | 绑定源快照、规则、文本规则和 schema version | 工作区、规则、索引和写回门禁 |

字段规则：

- `raw_text` 不允许被 trim 后再存入。
- `visible_text` 可以经过解码和可见化，但不能丢失玩家可见字符。
- `translatable_text` 不包含格式壳、speaker、selector、协议键、分隔空白或只用于写回的包装符。
- `render_parts` 是写回协议，不是提示词素材。
- hash 字段必须说明输入来源，不允许不同模块对同名 hash 使用不同输入。

## SQLite v2 Schema 草案

核心表直接存全文：

```sql
CREATE TABLE text_facts_v2 (
    fact_id            TEXT PRIMARY KEY,
    schema_version     INTEGER NOT NULL,
    domain             TEXT NOT NULL,
    location_path      TEXT NOT NULL,
    source_file        TEXT NOT NULL,
    source_type        TEXT NOT NULL,
    item_type          TEXT NOT NULL,
    role               TEXT NOT NULL,
    selector           TEXT NOT NULL,
    raw_text           TEXT NOT NULL,
    visible_text       TEXT NOT NULL,
    translatable_text  TEXT NOT NULL,
    raw_hash           TEXT NOT NULL,
    visible_hash       TEXT NOT NULL,
    translatable_hash  TEXT NOT NULL,
    scope_key          TEXT NOT NULL
);

CREATE TABLE text_fact_render_parts_v2 (
    fact_id       TEXT NOT NULL,
    part_order    INTEGER NOT NULL,
    part_kind     TEXT NOT NULL,
    raw_text      TEXT NOT NULL,
    semantic_text TEXT NOT NULL,
    template_key  TEXT NOT NULL,
    PRIMARY KEY (fact_id, part_order),
    FOREIGN KEY (fact_id) REFERENCES text_facts_v2(fact_id) ON DELETE CASCADE
);

CREATE TABLE text_fact_domain_payloads_v2 (
    fact_id      TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (fact_id) REFERENCES text_facts_v2(fact_id) ON DELETE CASCADE
);

CREATE TABLE text_fact_scope_v2 (
    scope_key            TEXT PRIMARY KEY,
    schema_version       INTEGER NOT NULL,
    scope_hash           TEXT NOT NULL,
    source_snapshot_hash TEXT NOT NULL,
    rule_hash            TEXT NOT NULL,
    text_rules_hash      TEXT NOT NULL,
    created_at           TEXT NOT NULL
);
```

建议索引：

```sql
CREATE INDEX idx_text_facts_v2_domain_location ON text_facts_v2(domain, location_path);
CREATE INDEX idx_text_facts_v2_domain_source_file ON text_facts_v2(domain, source_file);
CREATE INDEX idx_text_facts_v2_selector ON text_facts_v2(selector);
CREATE INDEX idx_text_facts_v2_visible_hash ON text_facts_v2(visible_hash);
CREATE INDEX idx_text_facts_v2_translatable_hash ON text_facts_v2(translatable_hash);
CREATE INDEX idx_text_facts_v2_scope_key ON text_facts_v2(scope_key);
```

`payload_json` 只允许存 domain-specific 小扩展，例如 MV speaker policy、JS span、event command code、note tag name。核心字段不得塞进 JSON 逃避 schema。

## 支持的 Domain

v2 schema 从第一版开始面向所有文本域：

- `standard_data`
- `mv_virtual_namebox`
- `plugin_config`
- `event_command`
- `note_tag`
- `nonstandard_data`
- `plugin_source`
- `placeholder_candidate`
- `structured_placeholder_candidate`
- `active_runtime_literal`

实施时分批接入，不要求第一批写满所有 domain。未接入 domain 在生产命令中不得回退到 Python 全量扫描；命令应明确返回“该 domain 尚未写入 v2 facts，请先运行对应重建/导出流程”或停留在未迁移批次之外。

## MV 虚拟名字框模型

示例源文本：

```text
\n<Dan:> Hello
```

v2 fact：

```text
raw_text            = "\n<Dan:> Hello"
visible_text        = "\n<Dan:> Hello"
translatable_text   = "Hello"
role                = "Dan"
domain              = "mv_virtual_namebox"
```

render parts：

```text
0 literal          raw="\n<" semantic="\n<" template_key="prefix"
1 speaker          raw="Dan" semantic="Dan" template_key="speaker"
2 literal          raw=":> " semantic=":> " template_key="separator"
3 translated_body  raw=" Hello" semantic="Hello" template_key="body"
```

写回时，Rust 根据 render parts 重建：

```text
\n<丹:> 你好
```

设计要求：

- Agent 可以写朴素规则，规则指出 speaker/body 即可。
- 原始 `body` 中的前后格式空白由 render parts 保留。
- 送模型的是 `translatable_text`，不带分隔空白。
- 校验源文本重建使用 raw parts。
- speaker 术语需求、workspace 校验和 write-back 使用同一 v2 fact。
- 异常 speaker（例如只有空白或不可见格式字符）必须显式失败，不能被宽规则吞掉。

## Rust / Python 职责

Rust 负责：

- 全量扫描和多线程调度。
- 生成 v2 facts、render parts、hash、scope。
- 写入 SQLite v2 表。
- 规则匹配、selector、placeholder coverage、runtime literal classification。
- 写回计划消费 v2 facts 和 render parts。
- Rust 单测固定事实语义、hash、scope 和写回重建。

Python 负责：

- CLI 参数解析、配置校验、命令编排。
- 调用 Rust native 入口。
- 读取 v2 facts 的 typed adapter。
- 报告采样、错误文案、JSON 输出和事务控制。
- Python 测试固定 CLI 观察行为和 contract adapter。

禁止：

- Python 构建完整文本范围作为 v2 facts 的生产替代。
- Python 用字符串片段判断正则、packer、eval、控制符拆分或特殊名字框。
- 导出、校验、写回各自计算同一 scope hash。
- 保留旧 `translation_items` 作为生产事实源。

## 破坏性迁移策略

不提供旧库自动迁移。任何命令需要 v2 facts 时：

- v2 表不存在：失败，提示运行 `rebuild-text-index`。
- `schema_version` 不支持：失败，提示升级工具并重建。
- `scope_hash` 不匹配：失败，提示重新准备工作区或重新导入规则。
- 旧 workspace 候选缺少 v2 scope：失败，提示重新运行 `prepare-agent-workspace`。
- 旧 runtime map 缺少 v2 hash：失败，提示重新写回或重建当前运行文件。

错误文案必须说明：

1. 发生了什么。
2. 影响什么命令或阶段。
3. 下一步执行什么命令。

不允许静默读取旧表继续运行。

## 性能策略

性能是功能验收的一部分。

- `rebuild-text-index` 是唯一全量重型入口。
- Rust 扫描必须使用真实并发，线程数受 `ATT_MZ_RUST_THREADS` 或配置限制。
- 一次扫描写完整 v2 facts、render parts、hash 和 scope。
- 后续命令优先读 warm SQLite v2 facts。
- 规则校验、workspace 校验、质量报告、覆盖审计、反馈定位不得重新全量扫描游戏文本。
- 不为了报告字段补齐新增全量扫描。
- 每批迁移必须记录至少一个真实 CLI 耗时或阶段耗时。
- 如果命令本来会 cold rebuild，报告必须区分 `used`、`cold_rebuilt`、`stale_rebuilt`。

最终性能验收至少覆盖：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区>
uv run python main.py validate-agent-workspace --game <游戏标题> --workspace <工作区>
uv run python main.py quality-report --game <游戏标题>
uv run python main.py audit-coverage --game <游戏标题>
```

交付说明必须列出候选数、事实数、扫描文件数、命令耗时、是否 cold/stale rebuild，以及是否有新增全量扫描。

## 实施批次

### 批次 1：v2 schema 与 Rust writer

目标：

- 新建 v2 SQLite schema。
- Rust `rebuild-text-index` 直接写 v2 facts。
- 覆盖 `standard_data`、`mv_virtual_namebox` 和当前 warm index 主路径所需事实。
- Python adapter 只校验并读取 v2 facts，不实现旧表迁移。

测试：

- Rust 单测覆盖 raw/visible/translatable/render/hash。
- Rust 单测覆盖 MV `\n<Name:> Body` 的事实拆分。
- Python contract 测试覆盖 schema version、缺表、scope mismatch。
- 扫描预算测试确认 warm index 命令不构建 Python 完整文本范围。

性能：

- 记录当前样本 `rebuild-text-index` CLI 耗时和 fact 数量。

### 批次 2：核心正文命令迁移

迁移命令：

- `translate`
- `translation-status`
- `text-scope`
- `audit-coverage`
- `quality-report`

目标：

- 以上命令生产读取 v2 facts。
- 旧 `translation_items` 不再作为这些命令的事实源。
- prompt 组装只使用 `translatable_text`，不得暴露 raw selector、location_path 或内部字段。

测试：

- Python CLI 测试固定 JSON 报告。
- prompt 测试确认 user prompt 不含内部路径、内部字段名和无效上下文。
- 质量检查测试确认 raw 格式空白不进入正文质量判断。

性能：

- warm index 下命令只读 SQLite v2 facts。

### 批次 3：workspace 与规则命令迁移

迁移范围：

- `prepare-agent-workspace`
- `validate-agent-workspace`
- MV namebox validate/import
- placeholder scan/validate/import
- structured placeholder scan/validate/import
- event command rules
- plugin rules
- note tag rules
- nonstandard data rules
- plugin source rules

目标：

- workspace 文件带 v2 scope。
- 规则校验消费 v2 facts 和 Rust rule hit facts。
- Python 不再重扫游戏 data 或插件源码补候选。
- 错误报告保留 raw/rendered 短对比。

测试：

- 弱规则样本：`<Name:> Body` 能正确拆分，不要求 Agent 写 separator。
- 异常 speaker 样本必须失败。
- structured placeholder coverage 覆盖 standard/custom/structured 三类。
- scan budget 覆盖所有迁移命令。

性能：

- workspace warm index 不触发完整 scope build。

### 批次 4：扩展 domain 接入

接入：

- `plugin_config`
- `event_command`
- `note_tag`
- `nonstandard_data`
- `plugin_source`
- `active_runtime_literal`

目标：

- 插件源码继续保留 raw JS span 和 visible text 双通道。
- active runtime literal classification 由 Rust fact 输出。
- Python 不再用字符串特征判断 regex、packer、eval。
- 非标准 data 和插件配置使用同一 raw/visible/translatable/hash 语义。

测试：

- Rust 测试覆盖 JS span、JSON string、event command path、note tag、active runtime literal。
- Python 报告测试覆盖 blocking/warning/ignore 计数。

性能：

- 插件源码和 active runtime 扫描复用 Rust native 结果，不重复扫描。

### 批次 5：写回、反馈与手动导入迁移

迁移范围：

- write-back plan
- rebuild-active-runtime
- write-terminology
- audit-active-runtime
- diagnose-active-runtime
- verify-feedback-text
- manual translation import

目标：

- 写回只消费 v2 facts 和 render parts。
- runtime map 使用 v2 hash。
- feedback 缺口定位读 v2 facts。
- manual import 使用 v2 fact identity；默认原子导入，显式模式可保存有效项并报告无效项。

测试：

- MV `:> ` 空格写回保留。
- 插件源码 raw selector stale 仍能阻断。
- feedback warm index 不构建 Python 完整 scope。
- manual import 原子模式和显式部分导入模式。

性能：

- 写回计划不新增全量源扫描；必须说明读取当前运行文件的必要范围。

### 批次 6：旧路径删除与最终验收

目标：

- 删除或隔离旧生产读取路径。
- 旧 `translation_items` 不再作为生产事实源。
- Python 重型 scanner 不再参与已迁移命令。
- 更新 Skill/README/排障说明中涉及事实契约的内容。

测试：

- scan budget 全量通过。
- Python/Rust contract 全量通过。
- schema fingerprint 或等价测试固定 v2 schema。

最终验证：

```powershell
uv run basedpyright
uv run pytest
```

Rust：

```powershell
cd rust
cargo fmt -- --check
cargo clippy --all-targets -- -D warnings
cargo test
```

如果修改 Skill 协议：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

## 新会话执行协议

新会话可以直接从本 spec 进入 implementation plan。执行时必须遵守：

- 先写分批 implementation plan，再改代码。
- 每批必须有 RED/GREEN 测试或等价 contract 测试。
- 每批完成后运行该批直接相关验证。
- 触及性能路径必须记录真实 CLI 或阶段耗时。
- 不允许保留生产双事实来源。
- 不允许为了通过测试降低错误级别、吞异常或读取旧表继续运行。
- 如果发现需要新增第 7 批，必须停止并向用户说明原因、已完成内容、未完成内容、性能风险和下一步最小计划。

## 硬停止条件

出现以下任一情况必须停止实施并回到设计讨论：

- v2 表无法覆盖某个已迁移命令的生产事实，只能依赖 Python 全量扫描。
- 性能证据显示核心命令明显回退，且无法通过减少重复扫描或 Rust 并发修复。
- 需要长期同时维护 v1/v2 生产读取路径。
- 写回无法从 render parts 重建源文本或保留必要格式。
- schema 需要变成大量 JSON blob 才能继续推进。
- 新增兼容旧库逻辑成为主要工作量。

## 验收标准

最终交付必须满足：

- Rust `rebuild-text-index` 直接写 v2 SQLite facts。
- 所有迁移命令只读 v2 facts，不读旧事实源。
- MV 虚拟名字框 raw/semantic/render 语义统一，弱 Agent 朴素规则也能正确处理 `:> ` 空格。
- 旧数据库、旧工作区、旧规则 scope、旧 runtime map 显式失败。
- Python 不再保留已迁移领域的重型事实回退。
- 全量 Python 和 Rust 验证通过，或未执行项有明确原因和风险。
- 性能证据没有新增全量扫描或明显回退。

## 风险

- v2 schema 是跨层契约，字段命名和 hash 语义必须一次性定清楚。
- 直接新建 v2 表会触发大量测试更新，必须区分行为契约和实现细节。
- 旧路径删除会暴露隐藏依赖，不能用兼容分支掩盖。
- active runtime literal 分类必须保守，不能把真实用户可见残留误降级。
- 性能验证需要真实样本；不能只用单元测试证明没有回退。
