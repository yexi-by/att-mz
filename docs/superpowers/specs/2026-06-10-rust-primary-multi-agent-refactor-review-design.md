# Rust 主路径收束多子代理 Review 设计

## 背景

插件源码规则校验与文本索引重建的候选口径问题，暴露出的核心风险不是单个 selector 失效，而是同一个业务事实被拆成多个独立判断入口：导出、校验、导入、重建、翻译和写回可能分别消费不同的 Python 或 Rust 判断结果。只要这些入口没有被强制收束到同一套契约和同一个最终消费路径，就会出现一边认为规则合法、另一边认为规则过期的矛盾。

本设计用于组织一次大规模重构前的只读 review。review 的重点不是立即修复当前 bug，而是让多个子代理并发审查当前系统里是否存在双事实来源、跨语言契约漂移、Python 核心逻辑膨胀、Rust 主路径缺口、缓存或 fast path 掩盖真实状态等结构问题。

长期方向是逐步减少 Python 职责，强化 Rust 主路径。除 CLI 编排、配置加载和校验、模型 SDK 接入、报告组装等当前确需 Python 承担的边界外，不再主动扩展 Python 技术栈。新增核心逻辑、基础能力和性能敏感路径优先进入 Rust；Rust 接管后，对应 Python 核心逻辑应进入删除或瘦身清单。

## 核心目标

- 为大规模重构前建立一份可并发执行、可汇总、可验收的 review 任务书。
- 固定长期架构 review 标准，防止后续审查偏向 Python 补丁、Python 兜底或双语言长期共存。
- 找出同一业务事实被多个入口独立判断的问题，并判断哪个事实源应收束到 Rust。
- 审查现有 Python/Rust 边界是否清晰，哪些 Python 逻辑应删除、降级为编排，或被 Rust 主路径替代。
- 以插件源码规则问题作为必审样本，但不把本次 review 限定为单 bug 复盘。

## 非目标

- 本轮不修复问题。
- 本轮不修改源码、测试、schema、Skill、README、docs、脚本、配置或发行文件。
- 本轮不提交补丁、不做临时迁移、不重构模块、不改错误码。
- 本轮不运行会改变数据库、工作区、游戏目录或发行产物的命令。
- 本轮不把某个 Python 补丁方案设计成后续重构方向。
- 本轮不以当前插件源码问题的局部症状替代系统性审查。

## 硬约束

### 只读边界

本轮多子代理只执行 review，不修复、不改代码、不提交补丁、不做临时迁移。子代理可以读取仓库文件、查调用链、运行只读命令、运行不会改变项目状态的验证命令，并输出审查报告。任何修复建议只能写成后续重构候选，不能在本轮实施。

### Rust 主路径优先

长期方案必须减少 Python 核心逻辑。以下方向默认不合格，除非明确证明它只是短期迁移脚手架，并写出删除条件、删除触发点和验收方式：

- 在 Python 增加新的核心候选判断。
- 在 Python 增加核心规则匹配、扫描、过滤、stale 判断或写回协议判断。
- 让 Python 和 Rust 长期保留同一业务事实的双实现。
- 通过 Python fallback、silent fallback、mock 成功或兼容旧路径绕过 Rust 主路径。
- 只在报告层修正文案，而不收束事实来源。

Rust 接管某条生产主路径后，旧 Python 重型扫描、候选、校验、AST、质量判断或写回同功能路径必须列入删除或瘦身计划。Python 只保留编排、配置校验、模型接入、报告组装和小规模胶水逻辑。

### 单一事实来源

同一个业务事实必须有唯一当前事实源。review 必须识别以下风险：

- 同一候选集合由多个函数或语言分别构造。
- 同一 selector、path、rule、scope、hash 或 metadata 有多个判断入口。
- 导出、校验、导入、重建、翻译、写回消费不同的候选口径。
- 错误码和错误文案把过滤变化、AST 消失、文件变化、启用状态变化混成一个 stale 语义。
- cache、metadata 或 fast path 能绕过当前事实源。

## 审查范围

本次 review 以插件源码规则链路为必审样本，但审查范围应覆盖所有可能存在同类结构问题的模块：

- 插件源码规则、AST 地图、selector、runtime map 和写回计划。
- 非标准 data 候选、规则导入、路径模板和索引消费。
- 插件参数、事件指令、Note 标签、MV 虚拟名字框等外部规则链路。
- 普通占位符和结构化占位符候选。
- text index、text facts、scope、workflow gate、quality gate。
- Rust native adapter、JSON contract、错误码和 schema 版本。
- CLI、Agent toolkit、报告、metadata、cache 和 precheck fast path。

## 多子代理 Review 轨道

### 轨道 01：事实来源与契约

目标：审查业务事实是否唯一。

重点：

- 候选集合、selector、path template、rule hash、text rules hash、scope hash 是否有多个构造入口。
- Python 和 Rust 是否分别维护同一事实的判断。
- JSON schema、数据库 schema、report 字段和错误码是否表达同一契约。
- 当前事实源是否被 docs、Skill、测试 helper 或 metadata 反向覆盖。

必须输出：

- 发现的事实源列表。
- 每个事实源的生产者、消费者和最终消费路径。
- 双事实来源或潜在漂移点。
- 建议保留的唯一事实源。
- 应删除、合并或降级的入口。

### 轨道 02：Rust 主路径

目标：审查哪些核心逻辑应迁入 Rust，哪些 Python 逻辑应删除或瘦身。

重点：

- CPU 密集扫描、规则匹配、AST 解析、stale 判断、hash、索引构建、质量判断、写回协议是否仍由 Python 承担。
- Rust 侧是否已有能力但 Python 仍保留旧重型路径。
- Python adapter 是否只是传参和报告，还是又实现了一套业务判断。
- Rust 输出 schema 和错误码是否足以支持 Python 删除逻辑。

必须输出：

- Rust 已接管路径。
- Rust 缺口。
- Python 删除候选。
- Python 只应保留的边界职责。
- 不应继续扩展 Python 的位置。

### 轨道 03：跨命令生命周期

目标：审查同一规则或候选从导出到写回的生命周期是否一致。

重点：

- `export-*`、`validate-*`、`import-*`、`rebuild-text-index`、`translate`、`quality-report`、`audit-coverage`、`write-back` 是否消费同一事实。
- 导入时有效的 selector、path 或 rule，在源码、启用状态和配置未变时，后续重建是否可能立即 stale。
- 当前命令的报告是否能被下一命令真实消费，而不是只在报告层通过。
- 命令之间是否存在 hidden state、metadata shortcut 或二次解释。

必须输出：

- 每条生命周期的命令序列。
- 每步使用的事实源。
- 跨命令契约断点。
- 需要 Rust 统一消费的边界。

### 轨道 04：缓存、metadata 与 fast path

目标：审查所有快速路径是否会掩盖真实状态。

重点：

- text index metadata、workflow gate precheck、scan cache、runtime map、rule hash 是否可能绕过当前 Rust 主路径。
- fast path 是否只比较输入文本和数据库记录，而不重新验证候选仍在当前事实源里。
- cache 是否记录了足够的规则口径、文本规则口径、源码快照和 Rust contract version。
- 快速路径失效时，是否显式失败并要求重建，而不是继续报告 ok。

必须输出：

- fast path 清单。
- 每个 fast path 的跳过条件。
- 是否绕过 Rust 主路径。
- 是否可能把 stale 规则报告为已审查。
- 应删除、收紧或改为 Rust 验证的路径。

### 轨道 05：测试与验收

目标：审查测试是否固定跨语言、跨命令业务契约。

重点：

- 是否只有 Python 单元测试，而缺 Rust 核心逻辑测试。
- 是否只有单命令测试，而缺导出、导入、重建、翻译、写回的生命周期测试。
- 是否测试了错误文案却没有测试错误码和事实状态。
- 是否用 Python 大集成测试兜 Rust 内部逻辑。
- 是否缺少“导入通过后重建不能立刻 stale”的回归测试。

必须输出：

- 当前测试覆盖清单。
- 测试缺口。
- 应新增 Rust 测试。
- 应保留的 Python 流程测试。
- 不应继续扩大 Python 大集成测试的区域。

### 轨道 06：迁移与删减

目标：审查后续重构是否能逐步删除 Python 核心逻辑，而不是新增双轨。

重点：

- 每个建议是否包含删除对象。
- 临时迁移路径是否有删除条件。
- 是否存在“先复制到 Rust，再长期保留 Python”的风险。
- 是否有旧入口、旧 helper、旧 adapter、旧报告字段继续表达当前事实。
- 重构是否能按小步提交，同时保持外部契约清晰。

必须输出：

- 删除清单。
- 瘦身清单。
- 迁移阶段建议。
- 每阶段完成条件。
- 不能作为完成状态保留的双轨路径。

### 轨道 07：性能与并发证据

目标：审查性能和并发是否作为功能被纳入重构验收。

重点：

- 哪些命令会全量扫描游戏文本、插件配置、插件源码、AST、数据库译文记录或写回计划。
- 是否存在重复全量扫描。
- 是否存在 CPU 密集任务仍在 Python 串行执行。
- Rust 线程配置是否真实参与调度。
- 性能证据是否来自真实 CLI，而不是只用 scan budget 或理论复杂度说明。

必须输出：

- 扫描次数和扫描范围。
- Python 串行重活。
- Rust 并发入口。
- 真实 CLI 性能证据缺口。
- 后续重构必须采集的性能指标。

## 子代理权限

允许：

- 读取仓库内授权范围文件。
- 使用 `rg`、`rg --files`、`Get-Content`、`git show`、`git log` 等只读命令。
- 运行不会写数据库、不会写游戏目录、不会改源码或生成物的只读验证命令。
- 输出本轨道 Markdown review 报告。

禁止：

- 修改源码、测试、schema、Skill、README、docs、脚本、配置和发行文件。
- 执行 `import-*`、`translate`、`write-back`、`rebuild-active-runtime`、`reset-game`、`reset-translations`、`run-all` 等状态变更命令。
- 写数据库、写游戏目录、写 `data/db/`、`logs/`、`outputs/`、发行目录或真实样本目录。
- 为了证明修复可行而实施修复。
- 把 Python 补丁写成长期推荐方案。

如需运行测试或静态检查，子代理必须说明命令是否会写缓存或生成文件。本轮 review 默认不要求全量测试，除非用户另行批准。

## 子代理报告格式

每个轨道输出一份 Markdown 报告：

```text
docs/records/reviews/rust-primary-refactor/batches/track-<NN>-<topic>.md
```

报告必须包含：

```markdown
# 轨道 <NN>：<标题>

## 范围

## 只读命令

## 结论

PASS | FAIL | NEEDS_REVIEW

## 关键发现

### <严重程度>：<标题>

- 证据：<文件:行号>
- 业务事实：<候选、规则、selector、scope、hash、cache、写回协议等>
- 违反原则：<单一事实来源 | Rust 主路径 | 跨命令生命周期 | fast path | 测试验收 | 迁移删减 | 性能并发>
- 影响：<会导致什么用户可见或工程可见问题>
- Python/Rust 职责判断：<应由哪一侧承担>
- 建议 Rust 接管点：<如适用>
- 应删除或瘦身的 Python 逻辑：<如适用>
- 禁止采用的错误修复方向：<如适用>
- 后续验证：<可执行验证或测试缺口>

## 双事实来源清单

## Rust 主路径缺口

## Python 删除候选

## 测试缺口

## 已查无发现范围
```

要求：

- 每条发现必须有文件和行号证据。
- 发现必须按 P0、P1、P2、P3 排序。
- 不允许只写“可能有问题”。
- 无发现范围必须明确写出。
- 涉及其他轨道的发现必须写交叉引用。
- 建议必须服务于 Rust 主路径收束和 Python 职责减少。

## 严重程度

### P0

当前运行路径存在双事实来源、跨命令事实漂移、Python/Rust 核心判断冲突，或 fast path 会把无效状态报告为通过。

### P1

核心逻辑仍由 Python 承担，或 Rust 已接管后 Python 同功能路径仍存在，导致性能、维护和契约同步风险。

### P2

测试、报告、adapter、metadata 或文档暗示双事实来源，虽然未必直接阻断当前命令，但会带偏后续重构。

### P3

命名、注释、旧 helper、局部文案或开发记录存在方向性噪音，需要后续清理但不阻断重构设计。

## 总报告合并方式

主代理合并所有轨道报告，输出：

```text
docs/records/reviews/rust-primary-refactor/rust-primary-refactor-review-final-report.md
```

总报告结构：

```markdown
# Rust 主路径收束专项 Review 总报告

## 执行摘要

## 最高优先级问题

## 横向矩阵

### 单一事实来源破坏
### Rust 主路径缺口
### Python 删除候选
### 跨命令生命周期断点
### fast path 和 cache 风险
### 性能与并发风险
### 测试验收缺口

## 插件源码规则样本复盘

## 后续重构建议批次

## 明确拒绝的错误方向

## 剩余不确定项

## 只读边界声明
```

总报告必须给出：

- 本次 review 是否 PASS。
- 是否存在 P0/P1 阻断。
- 哪些问题属于同一根因。
- 哪些 Python 逻辑应删除、瘦身或停止扩展。
- 哪些 Rust 能力是重构前置缺口。
- 后续重构批次建议。
- 本轮未修改源码、未执行状态变更命令的声明。

## 插件源码规则问题的验收样本

后续如果进入重构，插件源码规则问题必须作为验收样本覆盖，但不能只用局部补丁关闭。

必须覆盖：

- `export-plugin-source-ast-map`、`validate-plugin-source-rules`、`import-plugin-source-rules`、`rebuild-text-index`、`translate`、`write-back` 消费同一候选事实。
- selector 在导入时有效，且插件源码文件内容、启用状态、规则相关配置未变化时，`rebuild-text-index` 不能立刻报告 stale。
- selector 仍在 AST 中但被当前候选过滤规则排除时，错误码和错误文案必须指出过滤口径变化，不能伪装成“无法命中当前 AST 地图”。
- 只包含 `excluded_selectors` 的规则，导入后能稳定通过重建。
- fast path 不能让已过期或口径不一致的规则显示为完全通过。
- Python 不应通过新增核心过滤、selector 兜底或二次 stale 判断来长期修复该问题。
- Rust 应成为插件源码候选事实和重建消费事实的同一主路径。

## 成功状态

本 spec 执行完成后，应得到：

- 7 份轨道审查报告。
- 1 份总报告。
- P0-P3 问题索引。
- 双事实来源清单。
- Rust 主路径缺口清单。
- Python 删除和瘦身候选清单。
- fast path/cache 风险清单。
- 性能与并发证据缺口。
- 可转入后续重构计划的批次建议。

本次 review 的成功不等于完成重构。成功只表示已经用只读、可审计、方向不偏的方式识别问题，并为后续 Rust 主路径收束和 Python 职责减少提供证据。

## 后续验证建议

本 spec 是文档和 review 流程设计，不要求本机运行全量测试。正式执行 review 或进入后续重构计划前，建议至少完成：

```powershell
uv run basedpyright
uv run pytest
```

如果后续 review 或重构触及 Skill 协议，还必须执行：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```
