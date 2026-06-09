# 契约失忆化专项 Review 设计

## 背景

A.T.T MZ 当前处于主动开发阶段，项目规则已经明确不以短期兼容历史形态为目标。近期围绕文本事实、索引、写回身份、工作区验收和旧路径删除的改动，暴露出一个更大的结构性审查需求：项目里可能仍有字段、表名、错误文案、测试 helper、文档契约或 adapter 命名，把历史形态带进了当前系统。

本设计用于组织一次只读的破坏性大扫除前 review。它不修改代码，而是通过多个子代理并发审查，找出所有违反“契约失忆化”的对象，并合并成一份可直接转入后续清理 backlog 的 review 结果文档。

## 核心目标

本次 review 的主轴是 **契约失忆化**：

项目只有“当前契约有效”和“输入无效”两种状态。当前运行时、数据库 schema、配置、CLI/JSON 契约、错误提示、用户文档、Skill 协议和测试模型，不应为了识别、拒绝、解释、迁就或展示历史形态而保留字段、表、分支、名称、文案或判断逻辑。

审查对象包括但不限于：

- Python 源码、Rust native 源码和 Python adapter。
- SQLite 当前 schema、持久化记录模型和跨层 schema 对齐。
- CLI 参数、JSON 报告、错误码、错误文案和用户可见输出。
- Skill canonical 协议、生成 Skill、README、docs/wiki、docs/guides。
- 测试、fixtures、helper 和测试专用数据模型。
- 构建、发行、发布脚本、CHANGELOG、历史记录和归档文档。

## 非目标

本次 review 不做以下事情：

- 不修改源码、测试、schema、Skill、README、docs、脚本、配置或发行文件。
- 不生成迁移实现，不设计兼容策略，不写修复补丁。
- 不运行会改变数据库、工作区、游戏目录、运行输出或发行产物的命令。
- 不读取本机私有运行数据、日志、输出、临时样本、真实游戏目录或已有数据库。
- 不把合法的软件生态版本当作问题。

合法的软件生态版本包括：

- 项目发布号、依赖版本、锁文件版本和 Git tag。
- CHANGELOG 的发行版本段。
- 外部 API 路径或协议版本，例如 OpenAI 兼容接口 `/v1`。
- RPG Maker 引擎版本识别。

如果上述对象被用来表达 A.T.T MZ 内部历史契约，则重新纳入审查。

## 当前事实源优先级

子代理判断“当前契约是什么”时，必须按以下优先级取证：

1. 项目级 `AGENTS.md` 和全局 `AGENTS.md`。
2. 当前源码主路径：`app/`、`rust/src/`。
3. SQLite 当前 schema：`app/persistence/schema/current.sql`。
4. 当前 CLI/parser/report/schema 测试。
5. `skills/att-mz-protocol/` canonical Skill 协议。
6. 生成物 `skills/att-mz/`、`skills/att-mz-release/` 只用于检查漂移。
7. README 和 docs 只描述当前实现，不能覆盖源码和 Skill canonical。

`docs/archive/` 和 `docs/records/` 作为历史记录目录纳入审查但降级处理。它们允许保存历史，但不能被当前流程引用为事实源，也不能含有会误导后续 Agent 的当前契约表述或未脱敏私有路径。

## 审查准则

### 运行时失忆化

当前执行路径不能通过字段、表、配置、分支、错误码或字符串识别历史形态。无效输入只能按当前契约失败，错误信息只说明当前要求、当前问题和修正方式。

### Schema 失忆化

SQLite 当前 schema 只能表达当前事实模型。表名、字段名、索引、metadata、scope、cache、runtime map 等不能为了保留历史契约而命名或分层。合法的当前完整性校验可以存在，但不能把历史内容建模成当前业务状态。

### 文案失忆化

README、Skill、CLI 输出、错误提示和报告字段说明不能让用户理解历史形态是什么。用户只需要知道当前需要什么、当前缺什么、下一步如何重新生成、重新导入或修正输入。

### 测试失忆化

测试可以构造无效输入，但不应维护一套历史模型 helper、历史输入转换器或“历史输入仍能被识别为历史输入”的断言。测试应固定当前契约的成功行为和无效输入失败行为。

### 文档分层

当前 README、docs、Skill 只描述当前实现。历史对比、迁移背景和阶段性记录只能留在 `CHANGELOG.md`、迁移指南、发布说明、`docs/archive/` 或 `docs/records/`，且不能反向污染当前事实源。

## 严重程度

### P0

运行时代码、数据库 schema、CLI/JSON 契约会识别、拒绝、迁就、展示或分支处理历史形态。历史记忆已经进入当前执行路径。

### P1

Skill、README、正式 docs、错误文案或用户输出把历史形态当成当前用户需要理解的概念。

### P2

测试、helper、内部命名、注释、adapter 层仍保留历史模型，虽然未必直接影响用户，但会带偏后续开发。

### P3

归档记录、历史 review、开发记录里有可能污染当前判断的表述、引用或未脱敏内容。

## 并发审查批次

### 批次 01：CLI、配置与运行目录

范围：

- `app/cli_main.py`
- `app/cli/`
- `app/config/`
- `app/runtime_paths.py`
- `setting.example.toml`
- CLI JSON 输出和错误映射相关测试

重点：

- CLI 参数、配置字段、环境变量是否保留历史契约记忆。
- 错误文案是否解释历史形态，而不是说明当前要求。
- 运行目录、缓存目录和临时目录是否形成第二事实来源。

### 批次 02：SQLite schema 与 persistence

范围：

- `app/persistence/`
- `app/persistence/schema/current.sql`
- Rust 中直接读写 SQLite schema 的代码

重点：

- 当前 schema 是否只表达当前事实模型。
- schema 常量、校验、错误文案是否把历史内容建模为业务状态。
- Python/Rust 是否存在 schema 判断的双事实来源。

### 批次 03：Text Fact、索引与 scope

范围：

- `app/text_*`
- `app/text_scope/`
- `app/text_fact_*`
- `rust/src/native_core/scope_index/`

重点：

- 文本事实、scope、stale、warm index、identity 命名和错误是否保留历史契约。
- 当前事实身份是否唯一，是否仍有路径身份、旧同形报告或旧索引模型残留。
- 索引重建、失效判断和范围校验是否表达当前无效状态，而不是历史状态。

### 批次 04：工作区、规则与 Agent toolkit

范围：

- `app/agent_toolkit/`
- 工作区 manifest、规则导入导出、plugin/event/note/nonstandard/placeholder/source residual 相关模块

重点：

- 工作区目录是否只承认当前 manifest。
- 规则导入、审查状态和候选确认是否保留历史样本、历史确认或旧文件参与当前验收。
- Agent 报告和用户文案是否只表达当前任务输入。

### 批次 05：翻译、LLM、Prompt 与质量

范围：

- `app/translation/`
- `app/llm/`
- `app/llm_request_body_extra.py`
- `prompts/`
- 质量检查、pending、quality_error、manual import、reset 相关报告

重点：

- prompt 组装是否泄露内部字段或历史上下文。
- 质量错误、失败恢复和手动导入是否只描述当前失败原因。
- pending、quality_error、source residual 等用户文案是否保留历史模型。

### 批次 06：写回、RMMZ 与文件安全

范围：

- `app/application/`
- `app/rmmz/`
- `app/native_write_plan.py`
- `rust/src/native_core/write_back_plan/`
- 字体替换、可信源快照、写回 gate

重点：

- 写回前置条件是否只承认当前可信源和当前文本事实。
- 是否存在从当前运行文件补建可信源、回退读取、兼容加载或旧写回路径。
- Rust 写回计划和 Python 编排是否有同一契约的第二实现。

### 批次 07：Rust native 与 Python adapter 边界

范围：

- `rust/src/`
- `app/native_*.py`
- `app/native_contract.py`

重点：

- native 输出 schema、错误码、adapter 字段和 Python 包装层是否仍保留旧同形报告。
- Python 是否只保留编排、配置校验、报告组装和小规模胶水。
- Rust 接管的生产主路径是否还有 Python 重型同功能回退路径。

### 批次 08：Skill 协议、README 与当前文档

范围：

- `skills/att-mz-protocol/`
- `skills/att-mz/`
- `skills/att-mz-release/`
- `README.md`
- `docs/wiki/`
- `docs/guides/`

重点：

- canonical Skill 与生成 Skill 是否语义一致。
- 当前用户文档是否描述当前实现，而不是解释历史形态。
- docs 是否覆盖或改写 Skill 契约。
- 文档示例是否脱敏。

### 批次 09：测试、fixtures 与 helper

范围：

- `tests/`
- 测试专用 helper 和 fixtures

重点：

- 是否存在历史模型 helper、历史输入转换器或旧行为断言。
- 测试文件边界是否按历史入口聚合，导致当前契约不清。
- 测试是否固定业务行为，而不是固定历史实现细节。

### 批次 10：发行、构建与历史记录降级

范围：

- `.github/`
- `scripts/`
- `CHANGELOG.md`
- `docs/archive/`
- `docs/records/`
- 发行包清单和发布说明提取

重点：

- 发行包是否只包含当前需要的文件。
- 发行说明是否有具体更新内容。
- 历史记录是否被当前 docs、Skill 或流程引用为事实源。
- 历史记录是否包含真实本机路径、私有样本名或会误导后续 Agent 的当前契约表述。

## 子代理权限

允许：

- 读取仓库内授权范围文件。
- 运行只读命令，例如 `rg`、`rg --files`、`Get-Content`、`Select-String`、`git log`、`git show`、文件统计。
- 把本批次审查报告写入指定 review 输出目录。

禁止：

- 修改源码、测试、schema、Skill、README、docs、脚本、配置和发行文件。
- 写数据库、写游戏目录、写 `data/db/`、`logs/`、`outputs/`、`tmp/` 或真实样本目录。
- 读取本机私有运行数据，包括 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。
- 运行会改变项目状态、数据库、工作区或游戏文件的命令，例如 `add-game`、`reset-game`、`translate`、`write-back`、`rebuild-active-runtime`、`import-*`、`reset-translations`、`run-all`。

如需运行测试或静态检查，必须先判断是否会写缓存或改状态。本次 review 默认不要求运行全量测试，除非用户单独批准。

## 子代理报告格式

每个批次输出一份 Markdown 报告：

```text
docs/records/reviews/contract-amnesia/batches/batch-<NN>-<topic>.md
```

报告必须包含：

```markdown
# 批次 <NN>：<标题>

## 范围

## 事实源

## 只读命令

## 结论

PASS | FAIL | NEEDS_REVIEW

## 发现

### <严重程度>：<标题>

- 证据：<文件:行号>
- 违反准则：<运行时失忆化 | schema 失忆化 | 文案失忆化 | 测试失忆化 | 文档分层>
- 影响范围：<当前执行路径、用户文案、测试模型、文档事实源等>
- 建议收束：<删除、改名、合并、改文案、改测试模型等>
- 后续验证：<可执行的验证命令或检查方式>

## 交叉引用

## 已查无发现范围
```

要求：

- 发现必须按 P0、P1、P2、P3 排序。
- 每条发现都必须有文件和行号证据。
- 不允许只写“可能有旧逻辑”或“看起来不干净”。
- 无发现范围必须明确写出，避免无法区分“已查无问题”和“未审查”。
- 疑似影响其他批次的对象必须写入交叉引用。

## 总报告合并方式

主代理合并所有子代理报告，输出：

```text
docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md
```

总报告不直接照抄子代理全文，而是做判断和归并。结构：

```markdown
# 契约失忆化专项 Review 总报告

## 执行摘要

## 最高优先级问题索引

## 横向矩阵

### 运行时历史记忆
### Schema 历史记忆
### 文案历史记忆
### 测试历史模型
### 文档与 Skill 当前契约漂移
### 归档记录污染风险

## 跨批重复与同根问题

## 建议清理批次

## 剩余不确定项

## 只读边界声明
```

总报告必须给出：

- 本次 review 是否 PASS。
- 是否存在 P0/P1 阻断。
- 同一根因下源码、schema、测试、文档问题的合并主题。
- 后续破坏性清理顺序建议。
- 证据不足或需要用户裁决的问题。
- 本次未修改源码、未读取私有运行数据、未执行状态变更命令的声明。

## 成功状态

本 spec 执行完成后，应得到：

- 10 份批次审查报告。
- 1 份总报告。
- P0-P3 问题索引。
- 按问题类型归并的横向矩阵。
- 可转入后续破坏性清理的 backlog 主题。
- 明确的只读边界和未验证范围。

本次 review 的成功不等于项目已经完成失忆化清理。成功只表示已用可审计方式识别问题、合并证据并形成后续清理入口。
