# A.T.T MZ 超重型破坏性重构前 ReviewPlan

生成日期：2026-06-03

本文档用于指导后续 AI 对 A.T.T MZ 做一次完整的项目级、超重型破坏性重构前代码审查。本文档是闭环计划，已经内化必要的准备信息；执行审查时只需要当前仓库和本文档，不需要再依赖本文档之外的准备材料。

本文档不是重构方案，不执行修复，不提供修复方案或重构方案。最终产出只有一个：把所有检查到的问题写入本文档的“问题记录区”。

## 1. 核心目的

本次 review 的核心目的，是确认当前系统是否仍有一个清楚、唯一、可验证的当前模型。

执行者必须始终围绕这个核心问题审查：

> 当前系统的主流程，是否表达了当前正确模型？

如果主流程里混着旧状态兼容、历史兜底、临时分支、重复检查和多处并行推导，问题就不是局部代码难看，而是当前模型已经被历史层遮住。本 review 要找出的正是这些遮住当前模型的结构性问题。

本次 review 重点发现：

- 主流程是否清楚、线性，并能表达当前正确模型。
- 新能力是否替代旧路径，旧路径是否还进入默认流程。
- 重要业务结论是否只有一个事实来源。
- 检查、质量门禁和安全门禁是否重复且口径漂移。
- 文件职责是否过密，导致多个业务概念挤在同一处。
- 重复业务概念是否需要收束，而不是继续补分支。
- 公共抽象层是否缺失、边界不清或变成万能工具。
- 文件树是否表达项目结构，而不是历史堆积。
- 测试是否保护当前业务行为，还是锁死旧结构。
- 文档、Skill、README、AGENTS.md 和外部契约是否描述当前实现。

本次 review 和普通 review 的区别：

- 普通 review 主要检查一组具体改动有没有 bug、回归、缺测试或局部风险。
- 本次 review 是重构前结构审计，检查整个项目的当前模型是否清楚，哪些旧路径、重复事实来源、重复门禁、测试和文档约束会阻碍后续破坏性重构。

## 2. 执行边界

本 review 的任务是发现问题、固定证据、分类风险，不是设计解决方案。

执行者必须遵守：

- 只做只读审查；除把问题写入本文档外，不修改源码、测试、配置、文档或 Skill。
- 不提出修复方案、不写重构步骤、不写“建议怎么改”。
- 每个问题必须有证据，优先使用文件路径、行号、命令输出、测试失败、契约冲突或代码路径交叉引用。
- 不能确认的问题也可以记录，但必须标记为“需复核”，并说明还缺哪类证据。
- 对同一根因引出的多处问题，可以分条记录并互相引用；不要为了凑完整性把不同问题糊成一个大条目。
- 不能把“文件太大”“代码重复”“测试很多”单独当成问题，必须说明它遮住了哪个业务模型、事实来源、外部契约、性能路径或审查边界。
- 不使用 `skills/att-mz/` 或 `skills/att-mz-release/` 执行翻译流程；本任务是源码 review，不是游戏翻译流程。
- `docs/` 是人类文档，不能被当作 Agent 翻译流程契约。Skill、README、CLI、测试和发行脚本之间的冲突要记录为问题。

禁止输出的内容：

- 修复方案。
- 重构设计。
- 新模块拆分方案。
- 代码片段补丁。
- “可以通过某某方式解决”的描述。
- 没有证据的主观风格判断。

允许输出的内容：

- 问题本身。
- 影响范围。
- 证据。
- 根因线索。
- 冲突的事实来源。
- 重复或旧路径对象。
- 应删除或合并的对象。
- 受影响的外部契约。
- 仍需复核的证据缺口。

“应删除或合并的对象”是问题证据，不是解决方案。它只用于指出哪个旧路径、重复判断、重复状态、重复扫描、重复报告构造或测试形态暴露了结构问题；禁止继续展开怎么删除、怎么合并、怎么重构。

## 3. 审查成功状态

完成本文档要求的 review 后，必须满足以下可检查条件：

- 批次 00 到批次 17 全部完成。
- 每个批次的“批次产出”都已写入本文档。
- 所有确认问题都进入“问题记录区”，并有编号、严重程度、证据和影响。
- P0/P1 问题必须说明它遮住了哪个当前模型、事实来源、旧路径、重复门禁或外部契约。
- 每个确认问题必须记录“重复或旧路径对象”；存在明确结构收束对象时，还必须记录“应删除或合并的对象”。
- 所有需复核问题都进入“需复核问题区”，并说明缺少哪类证据。
- 最终没有把解决方案、重构设计或补丁混入问题条目。
- 对 10 万行级项目的规模控制已经落实为分批审查，而不是一次性泛扫。

## 4. 当前项目模型

A.T.T MZ 是面向 RPG Maker MV/MZ 游戏汉化流程的 Python CLI 工具。核心业务链路是：

```text
干净游戏目录
-> 注册并创建可信源快照
-> 导出工作区候选和规则草稿
-> 导入并审查文本规则、占位符规则、术语规则
-> 构建当前可翻译文本范围
-> 调用模型翻译并保存已验证译文记录
-> 运行质量检查和写文件前检查
-> 从可信源快照、规则和已保存译文记录生成当前运行游戏文件
-> 根据试玩反馈继续补漏
```

最重要的系统边界：

| 边界 | 当前含义 | review 必查风险 |
| --- | --- | --- |
| 可信源快照 | 注册游戏时创建的 `data_origin`、`js/plugins_origin.js`、`js/plugins_source_origin` | 当前运行文件是否被错误当成源文事实来源 |
| 当前运行文件 | 游戏实际运行的 `data`、`js/plugins.js`、`js/plugins` | 是否被当作写入目标之外的事实来源；损坏时是否显式失败 |
| SQLite 游戏库 | 每个游戏一套数据库，保存元数据、规则、术语、译文、文本索引、运行记录和写回映射 | schema 是否精确校验；旧库是否被静默兼容 |
| 工作区 JSON | Agent/用户处理候选、规则、手动译文和修复表的临时文件 | 候选文件是否被误当成已导入规则或系统事实 |
| LLM 输出 | 模型返回的批量译文 JSON | 是否在保存前经过 ID、行数、结构、占位符和源文残留校验 |
| Rust 原生能力 | CPU 密集扫描、JS AST、写回协议和写回计划 | Python/Rust 是否形成双事实来源；路径边界是否在 Python 适配层校验 |
| Skill 契约 | 开发版和发行版 Agent 翻译流程 | Skill 是否只描述翻译流程；docs 是否倒置覆盖 Skill |
| 发行包 | GitHub Actions release 工作流构建的 Windows ZIP | 本机构建是否被当成正式发行验收；发行包是否包含不该包含的源码或测试 |

当前外部契约包括：

- CLI 子命令、参数、默认值、帮助文本。
- CLI stdout Agent JSON 报告字段、错误语义和退出码。
- 工作区 JSON 文件名、结构、编码和导入语义。
- SQLite schema、schema version、表组所有权和不兼容处理。
- 配置字段、环境变量和 `setting.example.toml`。
- Prompt 隐私边界，特别是不得泄露真实路径、内部字段、数据库表、`location_path`、`translated_text`。
- 文本定位协议，包括 `location_path`、插件源码 selector、事件路径、Note 路径。
- Rust native JSON payload、contract version、线程配置和返回路径边界。
- 开发版 Skill、发行版 Skill、README、发行包布局和 GitHub Actions release 流程。
- 日志语义：终端中文摘要和文件 traceback 分层。

## 5. 仓库规模与分批策略

本项目按 10 万行级别处理。当前读到的规模基线是：排除 `.venv`、`.git`、`target`、`dist`、`data`、`logs`、`outputs`、`tmp` 等目录后，约 313 个可审查文本/源码文件，约 83k 行；如果计入更多文档、锁文件、生成文件和未跟踪材料，可按 100k 行项目规划。

当前规模分布：

| 区域 | 文件数 | 行数级别 | 审查策略 |
| --- | ---: | ---: | --- |
| `app/` | 约 172 | 约 38k | 按业务链路和事实来源分批，不按目录机械扫完 |
| `tests/` | 约 30 | 约 25k | 按保护的业务行为分批，识别锁死旧结构的测试 |
| `rust/` | 约 36 | 约 11k | 先看 Python adapter 契约，再看 Rust 核心实现 |
| `docs/` | 约 24 | 约 3k | 只检查是否描述当前实现、是否倒置为 Agent 契约 |
| `skills/` | 约 36 | 约 3k | 对比开发版和发行版语义，不执行翻译流程 |
| `scripts/` | 约 5 | 约 2k | 重点检查发行、benchmark 和 release notes 契约 |

大文件优先进入批次审查：

| 文件 | 当前行数级别 | 必查原因 |
| --- | ---: | --- |
| `tests/test_agent_toolkit.py` | 约 7.8k | 可能混合多个业务行为，容易锁死坏结构 |
| `tests/test_rmmz_loader_extraction_writeback.py` | 约 3.6k | 覆盖注册、抽取、写回主流程，可能隐藏契约耦合 |
| `app/agent_toolkit/services/common.py` | 约 3.0k | 共享职责过宽风险高 |
| `app/agent_toolkit/services/quality.py` | 约 2.2k | 质量、状态、审计、修复模板职责可能混杂 |
| `app/application/handler.py` | 约 1.9k | `TranslationHandler` 是应用编排最大热点 |
| `rust/src/native_core/write_back_plan/test_support.rs` | 约 2.0k | Rust 写回测试支撑可能形成第二业务模型 |
| `app/persistence/sql.py` | 约 1.4k | schema 是破坏性重构前必须冻结的契约 |
| `app/cli/parser.py` | 约 650 | CLI 参数是外部契约入口 |

分批原则：

- 每批只审一个业务层或一组强相关边界。
- 每批优先从外部契约进入，再读主实现，再读测试。
- 每批限制在 2k 到 8k 行主读范围；超出时拆成子批。
- 每批结束必须写入“批次产出”，不能把发现留在脑内。
- 跨批发现用问题编号交叉引用，不在多个批次重复记录同一问题。
- 先做全局索引，再做深读；先确定事实来源，再判断重复路径。
- 每批主读文件超过 8 个或主读行数超过 8k 时，必须拆成 A/B/C 子批，并分别记录子批证据。
- 同一批内先读入口和外部契约，再读实现，再读测试；不要从测试大文件开始倒推系统模型。
- 每批只允许输出问题、证据和证据缺口；发现潜在修复方向时只记录对应问题，不记录修复方向。

任务派发策略：

- 建议采用“一个主控审查者 + 多个批次审查者”的方式推进。
- 主控审查者负责批次 00、批次 17、问题编号、去重、严重程度统一和最终覆盖声明。
- 批次 01 到批次 16 可以分派给独立审查者，但每个审查者只能写入自己批次的产出和问题条目。
- 批次审查者不得跨批修补问题；跨批线索写入“跨批线索”，由批次 17 统一确认。
- 如果只能单一 AI 执行，也必须按批次切换上下文，每批完成登记后再进入下一批。

## 6. 证据与严重程度

严重程度用于排序，不代表修复优先级，因为本文不写修复方案。

| 严重程度 | 含义 |
| --- | --- |
| P0 | 已确认会破坏外部契约、写回安全、数据一致性、Prompt 隐私、DB schema 兼容判断或发行边界的问题 |
| P1 | 会阻塞超重型破坏性重构的结构性问题，例如多事实来源、旧路径仍进默认流程、门禁重复且口径漂移 |
| P2 | 明显增加维护成本、性能风险、测试脆弱性或文档漂移的问题 |
| P3 | 局部清晰度、命名、边界说明、测试组织或文案问题；需要记录但不阻塞主审查 |

证据等级：

| 证据等级 | 要求 |
| --- | --- |
| E1 | 文件路径和行号直接证明问题 |
| E2 | 两处以上文件或测试之间的契约冲突 |
| E3 | 命令输出、测试失败、静态检查失败或性能证据 |
| E4 | 代码路径推导，暂未用命令验证；必须标记“需复核” |

问题条目不能只有 E4；如果暂时只有 E4，先放入“需复核问题区”。

## 7. 通用审查命令

执行 review 时先用这些命令建立只读索引。命令结果只作为证据，不触发修复。

```powershell
git status --short
rg --files
rg -n "legacy|compat|fallback|deprecated|兜底|兼容|旧|临时|TODO|FIXME" app tests rust docs skills scripts
rg -n "location_path|translated_text|prompt|write-back|write_back|schema_version|contract_version|ATT_MZ_RUST_THREADS" app tests rust docs skills scripts
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

如果某个命令无法执行，记录为审查证据缺口；不要把无法执行当作通过。

行数和大文件索引用于分批，不用于单独定罪：

```powershell
$exclude = '(^|[\\/])(\.git|\.venv|target|dist|__pycache__|\.pytest_cache|data|logs|outputs|tmp|__ci_no_setting__|\.idea|\.vscode)([\\/]|$)'
$files = rg --files | Where-Object { $_ -match '\.(py|rs|toml|md|yml|yaml|json)$' -and $_ -notmatch $exclude }
$stats = foreach ($file in $files) {
  $lineCount = (Get-Content -LiteralPath $file | Measure-Object -Line).Lines
  [pscustomobject]@{ Lines = $lineCount; Path = $file }
}
$stats | Sort-Object Lines -Descending | Select-Object -First 40
```

## 8. 批次总览

批次必须按顺序推进。每批完成后写入“批次状态表”和“问题记录区”。

| 批次 | 名称 | 主目标 | 主要路径 | 完成条件 |
| --- | --- | --- | --- | --- |
| 00 | 审查启动与索引 | 固定工作树、规模、命令可用性 | 全仓库 | 批次状态表有基线记录 |
| 01 | 长期指令与文档边界 | 检查 AGENTS、README、docs、Skill 边界 | `AGENTS.md`、`README.md`、`docs/`、`skills/` | 记录指令漂移和契约倒置问题 |
| 02 | CLI 入口与 JSON 报告 | 检查命令、参数、dispatch、stdout JSON | `main.py`、`app/cli/`、CLI 测试 | parser/dispatch/report 契约矩阵完成 |
| 03 | 配置、运行目录与日志 | 检查配置全链路、app home、日志语义 | `app/config/`、`app/runtime_paths.py`、`app/observability/` | 配置字段链路和私有路径风险记录完成 |
| 04 | 注册、可信源快照与 RMMZ 数据层 | 检查注册、reset、源快照、当前运行文件边界 | `app/application/handler.py`、`app/rmmz/`、相关测试 | 源文事实来源问题记录完成 |
| 05 | 工作区与规则导入 | 检查 workspace JSON、规则校验、导入审查状态 | `app/agent_toolkit/`、规则模块、Skill references | 候选与已导入事实边界审查完成 |
| 06 | 标准 data 与事件文本域 | 检查标准文本、事件指令、MV 名字框 | `app/rmmz/`、`app/event_command_text/` | 文本域四状态审查完成 |
| 07 | 插件参数与插件源码文本域 | 检查插件配置、JS AST selector、运行映射 | `app/plugin_text/`、`app/plugin_source_text/`、Rust AST | selector 生命周期和映射风险记录完成 |
| 08 | Note、非标准 data、占位符、源文保留与字体 | 检查高风险支线和质量例外边界 | `app/note_tag_text/`、`app/nonstandard_data/`、`app/source_residual/`、font | 例外是否掩盖漏翻等问题记录完成 |
| 09 | TextScope 与 warm index | 检查 active/writable/translated/cannot_process_reason 和索引失效 | `app/text_scope/`、`app/text_index.py`、`app/agent_toolkit/services/text_index.py` | 文本范围事实来源矩阵完成 |
| 10 | 翻译、LLM 与 Prompt 隐私 | 检查批次协议、模型输出验证、Prompt 信息隔离 | `app/translation/`、`app/llm/`、`prompts/` | Prompt 泄露和模型信任边界审查完成 |
| 11 | 质量、覆盖、状态、反馈与手动修复 | 检查质量硬门槛和报告/修复职责边界 | `app/agent_toolkit/services/quality.py`、manual/feedback/coverage | 质量事实来源和重复门禁审查完成 |
| 12 | 写入门槛、写回计划与文件安全 | 检查 write-back、rebuild、write-terminology、回滚和路径边界 | `app/application/write_back_gate.py`、`file_writer.py`、`app/native_write_plan.py` | 写回安全问题记录完成 |
| 13 | 持久化与 DB schema | 检查 schema、repository、records、旧库处理 | `app/persistence/`、DB 测试 | 表组所有权和 schema 精确契约审查完成 |
| 14 | Rust 原生核心与 Python adapter | 检查 native contract、线程、质量、写协议、写回核心 | `app/native_*.py`、`rust/src/` | Python/Rust 双事实来源和 contract 问题记录完成 |
| 15 | 发行、Skill 同步与打包 | 检查发行版 Skill 转换、GitHub Actions、发行包边界 | `scripts/build_release.py`、`.github/`、`skills/` | 发行边界和 Skill 漂移审查完成 |
| 16 | 测试保护行为能力 | 检查测试是否保护业务行为或锁死坏结构 | `tests/` | 行为契约测试和结构锁死测试分类完成 |
| 17 | 跨批收束与最终问题索引 | 去重、分类、补证据缺口 | 本文档所有批次产出 | 最终问题清单完成，无解决方案混入 |

批次交接格式：

```text
批次编号：
执行者：
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

## 9. 批次 00：审查启动与索引

目标：建立只读审查基线，避免在脏工作树和大仓库里误判用户改动。

必读输入：

- `git status --short`
- `rg --files`
- 行数统计命令输出
- `pyproject.toml`
- `Cargo.toml`

检查问题：

- 当前工作树是否已有大量用户改动，导致 review 需要区分“现状问题”和“未完成改动问题”。
- 是否存在未跟踪的大型文档、计划、报告或生成文件，可能影响后续 AI 对项目状态的判断。
- 是否存在生成目录、数据目录、日志目录、虚拟环境、target 目录被误纳入 review。
- 是否存在命令无法执行的环境缺口。

批次产出：

- 在“批次状态表”记录仓库规模、主要未提交改动类型、命令可用性。
- 如果环境缺口会影响后续审查，写入“需复核问题区”。

## 10. 批次 01：长期指令与文档边界

目标：检查长期指令是否会带偏后续 AI 编程，检查 docs、Skill、README 的事实来源边界。

主读路径：

- `AGENTS.md`
- `README.md`
- `docs/`
- `skills/att-mz/SKILL.md`
- `skills/att-mz-release/SKILL.md`
- `skills/*/references/`

检查问题：

- `AGENTS.md` 是否把临时修复经验固化成永久规则。
- `AGENTS.md` 是否把内部实现细节误写成外部契约。
- `AGENTS.md` 是否鼓励保留旧兼容、旧状态、旧字段或旧入口。
- README、docs、Skill 是否互相覆盖或矛盾。
- docs 是否要求 Agent 从 `docs/` 复制任务契约。
- 开发版 Skill 和发行版 Skill 是否语义漂移。
- 发行版 Skill 是否要求 Python、Rust、uv、maturin 或源码上下文。
- 文档示例是否包含真实本机路径、用户名、客户项目名或用户数据。
- 文档是否描述历史实现而不是当前实现。

批次产出：

- 指令/文档冲突问题。
- Skill 语义漂移问题。
- docs 倒置为 Agent 契约的问题。

## 11. 批次 02：CLI 入口与 JSON 报告

目标：确认 CLI 参数、dispatch、命令实现和 stdout Agent JSON 是否是单一清晰契约。

主读路径：

- `main.py`
- `pyproject.toml`
- `app/cli_main.py`
- `app/cli/parser.py`
- `app/cli/dispatch.py`
- `app/cli/commands/*.py`
- `app/cli/runtime.py`
- `app/cli/reports.py`
- `app/agent_toolkit/reports.py`
- `tests/test_cli_json_output.py`
- `tests/test_skill_protocol.py`

检查问题：

- parser 有命令但 dispatch 没有 handler。
- dispatch 有 handler 但 parser 没有公开命令。
- CLI 参数定义、解析、校验、应用、测试链路断裂。
- stdout JSON 和 stderr 进度/日志边界混淆。
- CLI 报告字段在多个模块重复拼装。
- 命令错误文案没有按“发生了什么、影响什么、下一步做什么”表达。
- Skill references、README、测试中的命令示例和 parser 不一致。
- 外部契约字段改名或语义变化没有测试固定。

批次产出：

- CLI 契约矩阵。
- parser/dispatch/report 漂移问题。
- JSON 报告多事实来源问题。

## 12. 批次 03：配置、运行目录与日志

目标：检查配置字段和环境变量是否全链路生效，运行目录是否不依赖源码私有路径，日志是否分层。

主读路径：

- `setting.example.toml`
- `app/config/`
- `app/runtime_paths.py`
- `app/utils/config_loader_utils.py`
- `app/observability/logging.py`
- `tests/test_config_overrides.py`
- `tests/test_runtime_paths.py`
- `tests/test_observability.py`

检查问题：

- 配置字段只定义未解析、只解析未应用、只应用未测试。
- 测试依赖开发机私有 `setting.toml` 或默认源码根目录。
- `ATT_MZ_HOME`、发行版目录、源码根目录的优先级不清。
- prompt 文件注入和语言 profile 应用存在隐藏默认。
- 环境变量 override 和 CLI override 口径不一致。
- 终端输出 traceback，或文件日志没有完整 traceback。
- 用户文案中出现内部术语且未解释。

批次产出：

- 配置链路断点问题。
- 日志分层和用户摘要问题。
- 私有路径依赖问题。

## 13. 批次 04：注册、可信源快照与 RMMZ 数据层

目标：确认可信源快照、当前运行文件、RMMZ 读取和 reset 边界不混淆。

主读路径：

- `app/application/handler.py`
- `app/game_reset.py`
- `app/rmmz/`
- `app/persistence/source_snapshot_records.py`
- `tests/test_game_reset.py`
- `tests/test_rmmz_loader_extraction_writeback.py`

检查问题：

- 当前运行文件被当作正文翻译源文。
- 已存在可信源快照的目录被当作新干净源继续覆盖。
- 源快照指纹记录和实际文件校验口径不一致。
- reset 边界不清，可能删除或保留错误事实。
- `GameFileView` 没有清楚区分可信源和当前运行视图。
- RMMZ 标准 data、plugins.js、插件源码读取职责混在应用编排里。
- 注册流程中 DB schema 不兼容时出现静默迁就。

批次产出：

- 源文事实来源问题。
- 注册/reset 破坏性边界问题。
- RMMZ 数据视图混用问题。

## 14. 批次 05：工作区与规则导入

目标：确认工作区 JSON 是协作载体而不是内部事实来源，规则必须导入后才生效。

主读路径：

- `app/agent_toolkit/service.py`
- `app/agent_toolkit/services/workspace.py`
- `app/agent_toolkit/services/rule_validation.py`
- `app/agent_toolkit/services/placeholder_rules.py`
- `app/agent_toolkit/services/common.py`
- `app/rule_review.py`
- `app/rule_review_decision.py`
- `skills/*/references/workspace-schema.md`
- `tests/test_agent_toolkit.py`
- `tests/test_skill_protocol.py`

检查问题：

- 工作区候选文件被误当成已导入规则。
- 空规则语义和未审查语义混淆。
- `rule_review_states` 的审查状态被多个模块重复推导。
- validate 和 import 使用不同的路径语法或候选命中逻辑。
- workspace manifest、清理清单、导入结果报告由多个模块重复组装。
- Agent 子任务包和外部输出缺少导入边界。
- 用户可见字段名与项目文案映射不一致。

批次产出：

- 候选/事实边界问题。
- 规则审查状态多事实来源问题。
- workspace schema 与实现漂移问题。

## 15. 批次 06：标准 data 与事件文本域

目标：检查标准 data、对话事件、事件指令参数和 MV 名字框的文本域语义。

主读路径：

- `app/rmmz/extraction.py`
- `app/rmmz/text_rules.py`
- `app/rmmz/text_protocol.py`
- `app/rmmz/commands.py`
- `app/rmmz/mv_namebox.py`
- `app/event_command_text/`
- `tests/test_text_rules.py`
- `tests/test_event_command_text.py`
- `tests/test_rmmz_loader_extraction_writeback.py`

检查问题：

- 标准事件文本、数据库字段、地图名之间语义混淆。
- MV 虚拟名字框和 MZ 标准名字框混淆。
- MV `356` 与 MZ `357` 结构被整块翻译或整块写回。
- 文本域没有同时表达发现候选、进入翻译、已审查排除、可写回四状态。
- `location_path` 生成逻辑在多个地方重复且不一致。
- 数据抽取规则和写回协议对同一字段理解不同。

批次产出：

- 标准 data 文本域问题。
- 事件指令协议问题。
- 文本定位协议漂移问题。

## 16. 批次 07：插件参数与插件源码文本域

目标：检查插件配置文本、插件源码 AST selector、运行写回映射和诊断边界。

主读路径：

- `app/plugin_text/`
- `app/plugin_source_text/`
- `app/native_javascript_ast.py`
- `rust/src/native_core/javascript_ast.rs`
- `app/persistence/plugin_source_runtime_records.py`
- `tests/test_plugin_text.py`
- `tests/test_plugin_source_text.py`

检查问题：

- 插件参数 JSON 叶子路径、资源名、脚本片段被误判为可翻译文本。
- 插件源码 selector 不是来自 Rust AST 或被手写偏移替代。
- 当前运行 JS 文件被当作 selector 来源。
- 没有 runtime write map 时仍按当前 JS 行号、上下文或 AST 顺序猜译文记录。
- 插件源码规则、运行映射、诊断缓存存在多个事实来源。
- 插件源码扫描和规则导入没有稳定 selector 生命周期。
- Python 与 Rust 对 JS 字符串 span 的理解不一致。

批次产出：

- 插件参数误翻风险问题。
- 插件源码 selector 生命周期问题。
- runtime map 缺失时的错误恢复问题。

## 17. 批次 08：Note、非标准 data、占位符、源文保留与字体

目标：检查高风险文本支线、质量例外、占位符保护和字体替换边界。

主读路径：

- `app/note_tag_text/`
- `app/nonstandard_data/`
- `app/source_residual/`
- `app/rmmz/placeholder_guard.py`
- `app/rmmz/placeholder_mapping.py`
- `app/config/custom_placeholder_rules.py`
- `app/config/structured_placeholder_rules.py`
- `app/application/font_replacement/`
- `rust/src/native_core/note_sources.rs`
- `rust/src/native_core/font_replacement.rs`
- `tests/test_nonstandard_data.py`
- `tests/test_translation_line_alignment.py`

检查问题：

- Note 标签名匹配不精确，导致脚本、公式、资源引用进入翻译。
- 非标准 data 候选没有归类，把看不懂结构当成无内容。
- 源文保留例外掩盖整句漏翻。
- 普通占位符和结构化占位符规则事实来源冲突。
- Prompt 中解释占位符恢复机制或写回机制。
- 字体替换记录、普通写回、`restore-font` 的边界不清。
- 高风险支线未审查时仍允许进入翻译或写回。

批次产出：

- 高风险文本支线问题。
- 占位符/源文保留质量边界问题。
- 字体替换边界问题。

## 18. 批次 09：TextScope 与 warm index

目标：固定当前可翻译范围、可保存、可写回、已翻译和不能处理原因的语义，检查 warm index 是否只是性能层。

主读路径：

- `app/text_scope/`
- `app/text_index.py`
- `app/agent_toolkit/services/text_index.py`
- `app/persistence/text_index_records.py`
- `tests/test_text_index.py`
- `tests/test_benchmark_small_tasks.py`
- `tests/test_benchmark_rebuild_active_runtime.py`
- `tests/test_benchmark_active_runtime_audit.py`

检查问题：

- `enters_translation`、`can_save_translation`、`can_write_back`、`translated` 被压成单一布尔状态。
- active 和 writable 被当成同义词。
- 用规则命中数代替当前可翻译范围。
- warm index 改变业务语义，而不是只减少重复扫描。
- 源文件、规则、占位符、术语审查状态变化没有让索引失效。
- 索引条目数量与当前范围不一致时仍继续信任旧索引。
- 同一命令内重复构建文本范围或重复扫描候选。

批次产出：

- TextScope 事实来源矩阵。
- warm index 失效和重复扫描问题。
- 性能回归证据缺口。

## 19. 批次 10：翻译、LLM 与 Prompt 隐私

目标：检查翻译批次协议、模型输出验证和最终 user prompt 的内部信息隔离。

主读路径：

- `app/translation/`
- `app/llm/`
- `app/llm_request_body_extra.py`
- `prompts/`
- `app/terminology/prompt.py`
- `tests/test_translation_cache_context.py`
- `tests/test_translation_line_alignment.py`
- `tests/test_llm_retry.py`

检查问题：

- Prompt 包含来源文件名、数据库表名、内部字段名、真实路径、`location_path`、`translated_text`。
- 术语表没有使用 `[[术语表]]` 或条目不符合 `原文 => 标准译名`。
- 模型输出在保存前没有经过 ID、行数、结构、占位符和源文残留校验。
- 临时 batch ID 和内部定位路径边界混淆。
- JSON repair 被当成信任模型输出的兜底。
- 模型失败和质量失败记录口径不一致。
- retry、cache、context 批次构造存在多事实来源。

批次产出：

- Prompt 隐私问题。
- 模型输出信任边界问题。
- 翻译批次协议问题。

## 20. 批次 11：质量、覆盖、状态、反馈与手动修复

目标：检查质量和覆盖是否是写回硬门槛，报告、主动诊断和手动修复是否混杂。

主读路径：

- `app/agent_toolkit/services/quality.py`
- `app/agent_toolkit/services/coverage.py`
- `app/agent_toolkit/services/manual_translation.py`
- `app/agent_toolkit/services/feedback.py`
- `app/application/flow_gate.py`
- `app/application/write_back_gate.py`
- `tests/test_agent_toolkit.py`
- `tests/test_translation_line_alignment.py`

检查问题：

- 质量报告只是展示，不影响写回硬门槛。
- 覆盖、质量、状态、写回 gate 各自重复扫描并得出口径不同结论。
- `quality_error`、还没成功保存译文的文本、源文残留例外语义混淆。
- 手动修复模板和导入使用不同的 `translation_lines` 规则。
- 运行文件中的残留、坏控制符或语法错误通过错误来源定位。
- 插件源码问题没有依靠写回映射精确反推。
- `services/quality.py` 同时承担展示报告、写回硬门槛、主动诊断和手动修复职责。

批次产出：

- 质量硬门槛问题。
- 报告/诊断/修复职责混杂问题。
- 手动译文导入契约问题。

## 21. 批次 12：写入门槛、写回计划与文件安全

目标：检查写进游戏文件、重建当前运行文件、写术语和文件替换安全。

主读路径：

- `app/application/write_back_gate.py`
- `app/application/file_writer.py`
- `app/application/handler.py`
- `app/native_write_plan.py`
- `rust/src/native_core/write_back_plan/`
- `tests/test_rmmz_loader_extraction_writeback.py`
- `tests/_native_write_plan_helper.py`

检查问题：

- `write-back` 没有用户授权或绕过写文件前检查。
- `rebuild-active-runtime` 被当成绕过质量门槛的通道。
- `write-terminology` 绕过术语、规则、可信源、写入目标或已保存译文质量检查。
- Rust 返回路径、sidecar 路径或目标文件未在 Python adapter 校验目录边界。
- `file_writer` 事务式替换和回滚边界不清。
- 写回计划读取当前运行文件作为源文事实。
- Python 重新实现 Rust write plan 的重型业务判断。

批次产出：

- 写回安全问题。
- 路径边界问题。
- 写回计划双事实来源问题。

## 22. 批次 13：持久化与 DB schema

目标：检查每游戏 SQLite schema、记录 mixin、repository 和旧库处理策略。

主读路径：

- `app/persistence/sql.py`
- `app/persistence/repository.py`
- `app/persistence/records.py`
- `app/persistence/*_records.py`
- `app/persistence/session_base.py`
- `app/persistence/session_utils.py`
- `tests/test_persistence.py`

检查问题：

- schema version、表、列、外键、索引不是精确检查。
- 旧 DB 被自动迁移、静默兼容或猜测新语义。
- 表组所有权不清，导致任意服务直接读写任意表。
- repository、records、session mixin 对同一业务事实重复封装。
- DB schema、Skill references、README、测试之间描述不一致。
- 破坏性 schema 变更缺少显式失败文案或重建边界。
- `translation_items`、`translation_runs`、`llm_failures`、`translation_quality_errors` 的写入语义漂移。

批次产出：

- DB schema 契约问题。
- 表组所有权问题。
- 旧库兼容边界问题。

## 23. 批次 14：Rust 原生核心与 Python adapter

目标：检查 Rust/Python contract、线程配置、质量扫描、写协议、JS AST 和写回计划边界。

主读路径：

- `app/native_contract.py`
- `app/native_quality.py`
- `app/native_javascript_ast.py`
- `app/native_write_plan.py`
- `rust/src/lib.rs`
- `rust/src/native_core.rs`
- `rust/src/native_core/`
- `tests/test_native_adapters.py`
- Rust tests

检查问题：

- Python 未拒绝不兼容 native contract version。
- Rust 线程数没有受 `ATT_MZ_RUST_THREADS` 或配置限制。
- CPU 密集扫描在 Python 侧重复实现。
- Rust quality、write protocol、JS AST、write plan 返回 payload 没有 schema 测试。
- Python adapter 只转发调用，不承担路径和版本边界校验。
- Rust test support 维护第二套业务模型。
- Rust/Python 对质量错误、写回协议或 selector 的字段语义不一致。

批次产出：

- native contract 问题。
- 线程和性能边界问题。
- Python/Rust 语义漂移问题。

## 24. 批次 15：发行、Skill 同步与打包

目标：检查发行版只由 GitHub Actions release 工作流构建，发行版 Skill 转换和发行包边界正确。

主读路径：

- `.github/workflows/`
- `scripts/build_release.py`
- `scripts/extract_release_notes.py`
- `docs/release-readme.md`
- `docs/development/release-and-tests.md`
- `skills/att-mz/`
- `skills/att-mz-release/`
- `tests/test_release_notes.py`
- `tests/test_skill_protocol.py`

检查问题：

- 正式发行包可以在本机构建并被当成验收结果。
- 发行包包含源码、测试、历史日志、源码数据库或 Rust/Python 工具链要求。
- `skills/att-mz-release/SKILL.md` 没有转换为发行包内 `skills/att-mz/SKILL.md`。
- 发行包内 frontmatter `name` 不是 `att-mz`。
- 发行版 references 没有随发行包复制。
- 开发版和发行版 Skill 业务语义漂移。
- Release notes、CHANGELOG、GitHub Release 正文可能只写空泛文案。

批次产出：

- 发行边界问题。
- Skill 转换问题。
- 发布说明契约问题。

## 25. 批次 16：测试保护行为能力

目标：检查测试是在保护业务行为，还是锁死坏结构；为破坏性重构标记测试风险。

主读路径：

- `tests/`
- `tests/conftest.py`
- 每个批次对应的测试文件

测试分批：

| 子批 | 主测对象 | 文件 |
| --- | --- | --- |
| 16A | CLI 与 Skill 契约 | `tests/test_cli_json_output.py`、`tests/test_skill_protocol.py` |
| 16B | AgentToolkit 工作区、规则、质量、手动修复 | `tests/test_agent_toolkit.py` |
| 16C | RMMZ、写回、文本规则 | `tests/test_rmmz_loader_extraction_writeback.py`、`tests/test_text_rules.py`、`tests/test_text_protocol.py` |
| 16D | 插件、事件、Note、非标准 data | `tests/test_plugin_text.py`、`tests/test_plugin_source_text.py`、`tests/test_event_command_text.py`、`tests/test_nonstandard_data.py` |
| 16E | 持久化、配置、运行目录、日志 | `tests/test_persistence.py`、`tests/test_config_overrides.py`、`tests/test_runtime_paths.py`、`tests/test_observability.py` |
| 16F | 翻译、术语、Prompt、LLM | `tests/test_translation_*`、`tests/test_terminology.py`、`tests/test_llm_retry.py` |
| 16G | Rust/native/性能 | `tests/test_native_adapters.py`、benchmark tests、Rust tests |

检查问题：

- 测试断言临时内部字段、旧函数名或中间步骤，而不是外部可见行为。
- 测试夹具复制业务模型，形成第二事实来源。
- 大测试文件混合多个领域，导致重构牵一发而动全身。
- 测试过度 mock，只证明 helper 自己没坏。
- 缺少注册、准备工作区、导入规则、翻译、质量、写回、反馈修复的金丝雀流程测试。
- prompt 组装缺少最终 user prompt 泄露断言。
- 写回安全、路径越界、sidecar 越界、回滚、质量硬门槛缺少测试。
- warm index 缺少不重复构建文本范围、规则变化失效、源文件变化失效测试。
- 测试依赖私有 `setting.toml` 或开发机默认配置路径。

批次产出：

- 必须保留的行为契约测试清单。
- 可能锁死坏结构的测试问题。
- 测试缺口问题。

## 26. 批次 17：跨批收束与最终问题索引

目标：合并批次发现，去重，补证据，确保最终只有问题清单，没有解决方案。

检查问题：

- 同一问题是否被多批重复记录。
- 是否有只有主观判断、没有证据的问题。
- 是否有解决方案混入问题条目。
- 是否有 P0/P1 问题缺少受影响外部契约。
- 是否有“需复核”问题长期停留但没有说明证据缺口。
- 是否遗漏系统禁区：可信源快照、Prompt 隐私、质量硬门槛、插件源码 runtime map、docs/Skill 边界、Rust/Python 双事实来源、TextScope 多状态。

批次产出：

- 最终问题索引。
- 需复核问题索引。
- 审查覆盖声明。

## 27. 事实来源矩阵模板

执行 review 时必须填写。发现多事实来源时，把问题写入“问题记录区”。

| 业务事实 | 预期权威来源 | 实际发现的产出位置 | 实际消费者 | 是否重复计算 | 是否存在旧来源 | 问题编号 |
| --- | --- | --- | --- | --- | --- | --- |
| app home | `app/runtime_paths.py` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| CLI 命令和参数 | `app/cli/parser.py` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 命令到 handler 映射 | `app/cli/dispatch.py` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| CLI stdout JSON | `app/cli/reports.py`、`app/agent_toolkit/reports.py` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 配置 schema | `app/config/schemas.py` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| LLM system prompt | `prompts/` 经配置加载注入 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 游戏注册记录 | `GameRegistry` 与每游戏 DB | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| DB schema | `app/persistence/sql.py`、`ensure_schema_compatible()` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 可信源快照 | 注册流程写入的源快照 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 当前运行文件 | `data`、`js/plugins.js`、`js/plugins` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 当前可翻译范围 | `TextScopeService.build()` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| warm text index | `app/text_index/` 相关记录 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 规则审查状态 | `rule_review_states` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 已保存译文 | `translation_items` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 翻译运行记录 | `translation_runs`、`llm_failures`、`translation_quality_errors` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 写入可行性 | Rust write protocol 与 TextScope write probe | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 写回计划 | Python adapter + Rust `build_write_back_plan` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 插件源码写回映射 | `plugin_source_runtime_write_map` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 字段译名表 | `terminology_field_terms` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 正文术语表 | `text_glossary_terms` 与 prompt index | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 发行版 Skill | `skills/att-mz-release/` 经发行脚本转换 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 开发版 Skill | `skills/att-mz/` | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |

## 28. 外部契约审查模板

| 契约 | 当前来源 | 消费者 | 是否测试固定 | 是否与文档/Skill 一致 | 问题编号 |
| --- | --- | --- | --- | --- | --- |
| CLI 子命令和参数 | `app/cli/parser.py` | 用户、Skill、发行包、测试 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| CLI stdout JSON | `app/cli/reports.py`、`app/agent_toolkit/reports.py` | Agent 自动流程 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 工作区文件结构 | Skill references 与 workspace 输出 | 用户、子代理、导入命令 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 数据库 schema | `app/persistence/sql.py` | 已注册游戏 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 配置字段和环境变量 | `setting.example.toml`、`app/config/schemas.py` | 开发版、发行版、CI | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| Prompt 隐私边界 | `prompts/`、`app/translation/context.py` | LLM 请求 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 文本定位路径 | 各文本域 `location_path` 生成 | 手动修复、质量报告、写回映射 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 插件源码 selector | Rust JS AST + plugin source rules | 插件源码规则、运行诊断 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| Rust native JSON payload | Python adapter + Rust serde structs | 质量、写回、AST、字体 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 发行包布局 | `scripts/build_release.py`、GitHub Actions | 用户、发行版 Skill | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |
| 日志语义 | `app/observability/logging.py` | 用户排障、CI 日志 | 执行 review 时填写 | 执行 review 时填写 | 执行 review 时填写 |

## 29. 问题条目格式

每个问题使用以下格式。不要增加“解决方案”字段。

```text
编号：
批次：
严重程度：
证据等级：
状态：已确认 / 需复核
问题：
证据：
影响：
根因线索：
冲突的事实来源：
重复或旧路径对象：
应删除或合并的对象：
受影响外部契约：
验证方式或证据缺口：
```

字段说明：

- “问题”只写现象和缺陷，不写怎么修。
- “证据”必须包含文件路径、行号、命令输出或跨文件冲突。
- “根因线索”只写导致问题的结构线索，不写重构方案。
- “重复或旧路径对象”必须列出具体文件、函数、流程、表、报告字段、测试形态或文档入口。
- “应删除或合并的对象”只记录对象名称和证据，不写删除步骤、合并设计或新结构。
- “受影响外部契约”没有时写“未发现外部契约影响”。
- “验证方式或证据缺口”用于说明该问题如何被确认，或为什么还只能标记需复核。

## 30. 批次状态表

执行 review 时维护此表。

| 批次 | 状态 | 主读范围是否完成 | 测试/命令证据是否收集 | 问题数量 | 需复核数量 | 备注 |
| --- | --- | --- | --- | ---: | ---: | --- |
| 00 审查启动与索引 | 已完成 | 是 | 是 | 0 | 0 | 工作树仅本文档已修改；可审查规模 311 文件、82384 行；全部质量门禁通过 |
| 01 长期指令与文档边界 | 已完成 | 是 | 是 | 2 | 0 | 发现 review 记录脱敏边界问题，以及反馈流程建议文档与 Skill/CLI 重复描述当前流程 |
| 02 CLI 入口与 JSON 报告 | 已完成 | 是 | 是 | 2 | 0 | parser/dispatch 57 个命令对齐，Skill/docs 110 个命令示例均能匹配 parser；发现 stdout JSON 错误 envelope 第二来源和缺失的 Skill 协议测试 |
| 03 配置、运行目录与日志 | 已完成 | 是 | 是 | 1 | 0 | 配置加载、ATT_MZ_HOME、日志分层有测试覆盖；发现模型服务环境变量仍使用旧项目前缀且公开文档未给出具体变量名 |
| 04 注册、可信源快照与 RMMZ 数据层 | 已完成 | 是 | 是 | 1 | 0 | 注册和会话加载会创建并校验可信源快照 manifest；发现兼容 loader 与测试辅助仍保留未注册首次写回生成快照模型 |
| 05 工作区与规则导入 | 已完成 | 是 | 是 | 1 | 0 | workspace 生成/验收与规则导入边界已审；发现旧版候选确认 hash 仍可在 workflow gate 中按 warning 放行 |
| 06 标准 data 与事件文本域 | 已完成 | 是 | 是 | 1 | 0 | 标准事件文本、MV 名字框和事件指令参数路径已审；发现事件指令 JSONPath 协议寄存在插件文本模块内 |
| 07 插件参数与插件源码文本域 | 已完成 | 是 | 是 | 1 | 0 | 插件参数规则、插件源码 AST selector、runtime map 与当前运行诊断已审；发现插件源码高风险 gate 依赖调用方预扫描 |
| 08 Note、非标准 data、占位符、源文保留与字体 | 已完成 | 是 | 是 | 1 | 0 | Note、非标准 data、占位符和源文保留边界未新增确认问题；发现字体覆盖副作用和写文件事务边界不一致 |
| 09 TextScope 与 warm index | 已完成 | 是 | 是 | 1 | 0 | TextScope active/writable/translated/cannot_process_reason 与 SQL pending 过滤已审；发现 Agent 质量报告自动重建 warm index 时丢失本次 setting_overrides |
| 10 翻译、LLM 与 Prompt 隐私 | 已完成 | 是 | 是 | 1 | 0 | Prompt 隐私、术语表格式、模型输出校验和失败记录已审；发现 stop-on-error-rate 不会提前停止已排队模型请求 |
| 11 质量、覆盖、状态、反馈与手动修复 | 已完成 | 是 | 是 | 2 | 0 | 质量报告、覆盖、手动修复和反馈定位已审；发现质量修复快路径范围事实分裂，以及 include-write-probe 报告细分计数与 Rust gate 摘要不一致 |
| 12 写入门槛、写回计划与文件安全 | 已完成 | 是 | 是 | 1 | 0 | write-back、rebuild-active-runtime、write-terminology、Python adapter 路径校验和 Rust 写回计划已审；发现写后审计失败时文件/运行映射已落地但命令失败，回滚边界不清 |
| 13 持久化与 DB schema | 已完成 | 是 | 是 | 1 | 0 | schema 完整签名、旧库显式失败和记录 mixin 已审；发现规则导入跨表清理译文/替换规则/审查状态不是一个 DB 事务 |
| 14 Rust 原生核心与 Python adapter | 已完成 | 是 | 是 | 1 | 0 | Rust 线程池、native contract、JSON payload 解析和 adapter 测试已审；发现 JavaScript AST adapter 未校验 native contract version |
| 15 发行、Skill 同步与打包 | 已完成 | 是 | 是 | 2 | 0 | release workflow、打包脚本、发布说明、发行/开发 Skill 差异已审；发现发布说明具体性门槛和发行包布局测试缺口 |
| 16 测试保护行为能力 | 已完成 | 是 | 是 | 2 | 0 | 测试文件、CLI/Agent 流程保护、Prompt 隐私、配置路径和结构锁定风险已审；发现完整 CLI/Agent 金丝雀流程缺口和超大混合测试文件组织问题 |
| 17 跨批收束与最终问题索引 | 已完成 | 是 | 是 | 0 | 0 | 问题编号 001-021 连续唯一，严重程度分组完成；无未处理需复核问题，无新增问题 |
| 18 补充漏检复查 | 已完成 | 是 | 是 | 1 | 0 | 按用户要求补查漏检面；源语言探测和报告输出未新增问题，发现工作区复用时旧可选文件可能重新参与当前验收 |

## 31. 批次产出记录区

执行 review 时，每批完成后先填本区，再把确认问题追加到“问题记录区”。本区记录审查覆盖和证据，不写解决方案。

### 批次 00 产出

```text
主读文件：pyproject.toml；rust/Cargo.toml；全仓库文件索引
辅助读取：git status --short；rg --files；关键词索引；行数统计前 40 大文件
运行命令：git status --short -> 仅 docs/超重型破坏性重构/reviewplan.md 已修改；rg --files -> 全仓库文件索引已收集；行数统计 -> 311 个可审查 py/rs/toml/md/yml/yaml/json 文件、82384 行；rg -n "legacy|compat|fallback|deprecated|兜底|兼容|旧|临时|TODO|FIXME" app tests rust docs skills scripts -> 当前输出集中在 benchmark 脚本的临时工作目录/兼容假服务语义，未形成批次 00 确认问题；rg -n "location_path|translated_text|prompt|write-back|write_back|schema_version|contract_version|ATT_MZ_RUST_THREADS" app tests rust docs skills scripts -> 已收集跨批关键词线索；uv run basedpyright -> 0 errors, 0 warnings, 0 notes；uv run pytest -> 656 passed in 157.34s；cargo fmt --manifest-path rust/Cargo.toml -- --check -> 通过；cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings -> 通过；cargo test --manifest-path rust/Cargo.toml -> 67 passed
确认问题编号：无
需复核问题编号：无
跨批线索：scripts/benchmark_small_tasks.py 中通过解析 user prompt 生成假译文，后续批次 10/16 复核是否只属于测试/benchmark 契约；scripts/benchmark_rebuild_active_runtime.py 设置 ATT_MZ_RUST_THREADS，后续批次 14 复核线程配置是否有单一事实来源
未覆盖范围：批次 00 只固定基线，不深读业务实现；所有业务边界留待批次 01-17
```

### 批次 01 产出

```text
主读文件：AGENTS.md；README.md；docs/development/README.md；docs/development/review-records/README.md；docs/feedback-iteration-repair-plan.md；docs/advanced-usage.md；skills/att-mz/SKILL.md；skills/att-mz-release/SKILL.md；skills/att-mz/references/feedback-iteration.md；skills/att-mz-release/references/feedback-iteration.md
辅助读取：skills/att-mz/references/subtask-package-mode.md；skills/att-mz-release/references/subtask-package-mode.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/references/cli-command-contract.md；docs/development/review-records/rust-migration-review-final-report.md；docs/development/review-records/rust-migration-review-findings-batch-01.md；docs/development/review-records/rust-migration-review-closure-matrix.md；docs/development/review-records/rust-migration-review-fix-progress.md
运行命令：rg -n "<文档契约关键词>|<私有路径关键词>|<用户名关键词>|<样本名关键词>" README.md docs skills；git diff --no-index --stat -- skills/att-mz skills/att-mz-release；git diff --no-index -- skills/att-mz/references/cli-command-contract.md skills/att-mz-release/references/cli-command-contract.md；rg -n "<文档覆盖关键词>|<入口差异关键词>" README.md docs skills AGENTS.md；rg -n -- "--json|--agent-mode" README.md docs skills app tests scripts
确认问题编号：ATT-MZ-REVIEW-001；ATT-MZ-REVIEW-002
需复核问题编号：无
跨批线索：开发版与发行版 Skill 主体和 references 的差异主要集中在命令入口、可访问目录和工具排障边界，批次 15 继续用发行脚本和协议测试复核打包转换；开发版 subtask-package-mode.md 同时列出发行版命令但标注为“发行版使用”，当前不单独定为漂移
未覆盖范围：批次 01 不验证 CLI 实现是否完全符合 Skill references，留给批次 02、05、10、15、16
```

### 批次 02 产出

```text
主读文件：main.py；pyproject.toml；app/cli_main.py；app/cli/parser.py；app/cli/dispatch.py；app/cli/runtime.py；app/cli/reports.py；app/agent_toolkit/reports.py；app/cli/commands/registry.py；app/cli/commands/rules.py；app/cli/commands/translation.py；app/cli/commands/write_back.py；app/cli/commands/workspace.py；app/cli/commands/terminology.py；tests/test_cli_json_output.py
辅助读取：skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/references/cli-command-contract.md；docs/development/agent-toolkit.md；docs/development/release-and-tests.md；tests/test_release_notes.py；当前 tests 文件列表
运行命令：rg -n "print\\(|write_report_outputs\\(|AgentReport\\.from_parts\\(|build_.*_summary_report|to_json_text\\(" app/cli app/agent_toolkit；rg -n "registered_command_names|parser_command_names|COMMAND_HANDLERS|_att_mz_command_names|write_back_summary|pre_write_check_ms|rust_plan_ms|report_detail_mode|business_error|argument_error|unexpected_error" tests app skills docs；rg --files tests；uv run python - <<命令示例对照脚本>> -> parser_commands=57 command_refs=110 unknown_refs=[]；uv run python -c "import pathlib; print(pathlib.Path('tests/test_skill_protocol.py').exists())" -> False；Select-String 检查 test_skill_protocol.py 文档引用
确认问题编号：ATT-MZ-REVIEW-003；ATT-MZ-REVIEW-004
需复核问题编号：无
跨批线索：命令示例名与 parser 当前对齐，但该对齐不是现有测试套件中的可重复断言；批次 15/16 继续复核发行 Skill 转换和测试保护能力
未覆盖范围：批次 02 不深审每个命令的业务实现和参数应用链路；配置覆盖细节留给批次 03，规则/文本/写回语义留给后续批次
```

### 批次 03 产出

```text
主读文件：setting.example.toml；app/config/schemas.py；app/config/environment.py；app/config/overrides.py；app/runtime_paths.py；app/utils/config_loader_utils.py；app/observability/logging.py；tests/test_config_overrides.py；tests/test_runtime_paths.py；tests/test_observability.py；tests/test_cli_json_output.py
辅助读取：scripts/benchmark_small_tasks.py；tests/test_benchmark_small_tasks.py；README.md；docs/advanced-usage.md；skills/att-mz/references/cli-command-contract.md
运行命令：Select-String -Path app/config/environment.py,tests/test_config_overrides.py,scripts/benchmark_small_tasks.py,tests/test_benchmark_small_tasks.py,docs/advanced-usage.md,skills/att-mz/references/cli-command-contract.md,README.md -Pattern "RPG_MAKER_TOOLS|环境变量|ATT_MZ_RUST_THREADS|setting.toml|LLM_BASE_URL_ENV_NAME|LLM_API_KEY_ENV_NAME"；uv run python -c "import tomllib; from pathlib import Path; from app.utils.config_loader_utils import load_setting; s=load_setting(Path('setting.example.toml')); print(s.llm.base_url, s.prompts.text_translation_ja_to_zh_system_file, s.language_profiles.active_profile)" -> setting.example.toml 可加载，输出 https://api.example.com/v1 prompts/text_translation_ja_to_zh_system.md japanese_strict
确认问题编号：ATT-MZ-REVIEW-005
需复核问题编号：无
跨批线索：load_setting() 当前会在配置加载时记录配置摘要和模型 base_url，批次 10/16 继续复核 prompt 隐私边界和测试是否约束敏感信息；ATT_MZ_RUST_THREADS 在 Skill、benchmark 和 Rust adapter 中多处出现，批次 14/15 继续复核线程配置是否有单一事实来源
未覆盖范围：批次 03 不深审每个业务配置字段是否真实参与翻译、质量和写回调度；这些字段随对应业务批次继续复核
```

### 批次 04 产出

```text
主读文件：app/application/handler.py；app/game_reset.py；app/rmmz/loader.py；app/rmmz/source_snapshot.py；app/rmmz/game_file_view.py；app/rmmz/schema.py；app/persistence/repository.py；app/persistence/source_snapshot_records.py；tests/test_game_reset.py；tests/test_rmmz_loader_extraction_writeback.py
辅助读取：tests/_native_write_plan_helper.py；tests/test_persistence.py；tests/test_cli_json_output.py；app/application/font_replacement/restore.py
运行命令：rg --files app/rmmz app/application app/persistence tests | rg "(rmmz|handler|game_reset|source_snapshot|test_game_reset|test_rmmz_loader_extraction_writeback)"；rg -n "register|reset|source_snapshot|data_origin|plugins_origin|plugins_source_origin|origin|current|GameFileView|schema|fingerprint|trusted|可信|快照|运行文件" app/application/handler.py app/game_reset.py app/rmmz app/persistence/source_snapshot_records.py tests/test_game_reset.py tests/test_rmmz_loader_extraction_writeback.py；rg -n "load_game_data\\(|load_game_data_for_view\\(|load_translation_source_game_data\\(|load_active_runtime_game_data\\(" app tests；Select-String -Path app/rmmz/loader.py,tests/test_rmmz_loader_extraction_writeback.py,tests/_native_write_plan_helper.py -Pattern "load_game_data\\(|require_origin_backups=False|兼容完整游戏数据|业务服务层必须使用显式视图入口|首次磁盘回写|_ensure_source_snapshot|create_source_snapshot_for_clean_game|write_game_files\\("
确认问题编号：ATT-MZ-REVIEW-006
需复核问题编号：无
跨批线索：reset-game 明确不做完整 schema 校验但仍校验 source snapshot manifest，批次 13 继续复核 DB schema 破坏性边界；GameDataManager.load_game_data 仍存在内存缓存入口但未见 CLI 主路径使用，批次 16 复核测试是否仍锁定旧入口
未覆盖范围：批次 04 不深审每类文本抽取规则、插件源码 selector、非标准 data 与写回计划；这些留给批次 06-08、12、14
```

### 批次 05 产出

```text
主读文件：app/agent_toolkit/service.py；app/agent_toolkit/services/workspace.py；app/agent_toolkit/services/rule_validation.py；app/agent_toolkit/services/placeholder_rules.py；app/agent_toolkit/services/common.py；app/agent_toolkit/services/core.py；app/rule_review.py；app/rule_review_decision.py；skills/att-mz/references/workspace-schema.md；tests/test_agent_toolkit.py
辅助读取：app/application/flow_gate.py；app/application/write_back_gate.py；app/text_scope/；skills/att-mz-release/references/workspace-schema.md
运行命令：rg -n "workspace|manifest|candidate|import|validate|rule_review|review_state|confirm_empty|pending|approved|rejected|placeholder|path|schema|write|cleanup|导入|候选|审查|规则|确认" app/agent_toolkit/service.py app/agent_toolkit/services/workspace.py app/agent_toolkit/services/rule_validation.py app/agent_toolkit/services/placeholder_rules.py app/agent_toolkit/services/common.py app/rule_review.py app/rule_review_decision.py skills/att-mz/references/workspace-schema.md tests/test_agent_toolkit.py；Select-String -Path app/rule_review_decision.py,app/application/flow_gate.py,app/agent_toolkit/services/rule_validation.py,app/agent_toolkit/services/placeholder_rules.py,app/agent_toolkit/services/quality.py,tests/test_agent_toolkit.py -Pattern "confirmed_legacy_hash|legacy_scope_hashes|legacy_hash|旧版截断|兼容规则放行|重新导入规则后会升级|read_confirmation_status|build_rule_review_decision|build_empty_rule_review_decision|replace_rule_review_state|reviewed_empty|RuleReviewState"
确认问题编号：ATT-MZ-REVIEW-007
需复核问题编号：无
跨批线索：prepare_agent_workspace() 会在生成 manifest 时记录 game_root/content_root/data_dir/plugins_path 等真实路径，批次 10/15/16 继续复核 prompt 隐私和发行/Skill 用户可见边界；workspace schema 的命令示例测试仍受 ATT-MZ-REVIEW-004 约束
未覆盖范围：批次 05 不深审插件规则、事件指令规则、Note 规则、非标准 data 规则和插件源码 selector 的各自命中语义，留给批次 06-08
```

### 批次 06 产出

```text
主读文件：app/rmmz/extraction.py；app/rmmz/commands.py；app/rmmz/text_protocol.py；app/rmmz/mv_namebox.py；app/event_command_text/extraction.py；app/event_command_text/importer.py；app/event_command_text/exporter.py；app/plugin_text/paths.py；tests/test_event_command_text.py；tests/test_rmmz_loader_extraction_writeback.py
辅助读取：skills/att-mz/references/workspace-schema.md；app/rmmz/text_rules.py；app/rmmz/loader.py
运行命令：rg --files app/rmmz app/event_command_text tests | rg "(rmmz[/\\](extraction|text_rules|text_protocol|commands|mv_namebox)|event_command_text|test_text_rules|test_event_command_text|test_rmmz_loader_extraction_writeback)"；rg -n "location_path|source_line_paths|parameters\\[4\\]|code 356|code 357|MV|MZ|namebox|speaker|displayName|gameTitle|message|extract|write|parameters|event_command|EventCommand|101|401|102|405|356|357|visible|role|long_text" app/rmmz app/event_command_text tests/test_event_command_text.py tests/test_rmmz_loader_extraction_writeback.py；rg -n "resolve_event_command_leaves|jsonpath_to_event_command_location_path|build_json_string_leaf_path_hint|walk_plugin_value|jsonpath_to_location_path|\\$\\['parameters'\\]" app/event_command_text app/plugin_text/paths.py skills/att-mz/references/workspace-schema.md tests/test_event_command_text.py
确认问题编号：ATT-MZ-REVIEW-008
需复核问题编号：无
跨批线索：标准 MZ 名字框使用 101.parameters[4]，MV 虚拟名字框由外部规则识别第一行 401；事件指令翻译路径会追加到命令 location_path/parameters/...，后续批次 12/14 继续复核写回计划和 Rust adapter 是否与该定位协议完全一致
未覆盖范围：批次 06 不深审插件参数、插件源码 selector、Note、非标准 data、占位符规则、字体替换和 TextScope 索引；这些留给批次 07-09、12、14
```

### 批次 07 产出

```text
主读文件：app/plugin_text/importer.py；app/plugin_text/extraction.py；app/plugin_text/exporter.py；app/plugin_text/common.py；app/plugin_text/paths.py；app/plugin_source_text/models.py；app/plugin_source_text/scanner.py；app/plugin_source_text/importer.py；app/plugin_source_text/extraction.py；app/plugin_source_text/rules.py；app/plugin_source_text/runtime_mapping.py；app/plugin_source_text/runtime_audit.py；app/native_javascript_ast.py；rust/src/native_core/javascript_ast.rs；app/persistence/plugin_source_runtime_records.py；tests/test_plugin_text.py；tests/test_plugin_source_text.py
辅助读取：app/application/handler.py；app/application/flow_gate.py；app/agent_toolkit/services/quality.py；app/agent_toolkit/services/workspace.py；app/agent_toolkit/services/text_index.py；app/text_scope/builder.py；skills/att-mz/references/plugin-source-text-agent-task.md；skills/att-mz/references/workspace-schema.md；skills/att-mz/references/cli-command-contract.md；docs/advanced-usage.md；docs/database-wiki.md；tests/test_agent_toolkit.py
运行命令：rg --files app tests skills/att-mz/references | rg "(plugin_text|plugin_source|plugin|test_plugin|workspace-schema|rules|selector)"；rg -n "plugin_text|plugin_source|selector|JSONPath|jsonpath|source_text|source_path|plugin_index|plugin_name|parameters|note|import_.*plugin|scan-plugin|rule|candidate|stale|location_path|write" app tests skills/att-mz/references；rg -n "runtime_write_map|plugin_source_runtime|write_maps|active_runtime|audit_active_runtime|diagnose_active_runtime|clear_plugin_source_runtime|replace_plugin_source_runtime|read_plugin_source_runtime|audit_text_issues|text_issue_scope_keys" app tests rust/src/native_core；rg -n "if scan is None and not records|scan = build_plugin_source_scan|plugin_source_text_high_risk|not scan\\.risk\\.high_risk|scan\\.risk\\.high_risk and not fresh_records" app/application/flow_gate.py；rg -n "高风险时.*translate|translate.*停止|高风险时暂停正文翻译|用户没有肯定回复时，停止正文翻译|正文翻译已暂停|plugin-source-risk-report" docs/advanced-usage.md skills/att-mz/references/cli-command-contract.md skills/att-mz/references/plugin-source-text-agent-task.md skills/att-mz/SKILL.md
确认问题编号：ATT-MZ-REVIEW-009
需复核问题编号：无
跨批线索：插件源码写后诊断坚持 runtime write map 精确反推，默认模式不按当前 JS 行号、上下文或 AST 顺序猜测；批次 12/14 继续复核 Rust write plan 是否只在实际源码写回时生成完整 runtime map，并复核 `plugin_source_runtime_map_count` 与写后审计条件
未覆盖范围：批次 07 不深审 Note、非标准 data、占位符、源文保留和字体替换；高风险支线共性留给批次 08，Rust 写回 selector 实际替换细节留给批次 14
```

### 批次 08 产出

```text
主读文件：app/note_tag_text/sources.py；app/note_tag_text/importer.py；app/note_tag_text/extraction.py；app/note_tag_text/parser.py；rust/src/native_core/note_sources.rs；app/nonstandard_data/scanner.py；app/nonstandard_data/rules.py；app/nonstandard_data/extraction.py；app/nonstandard_data/runtime_audit.py；app/source_residual/rules.py；app/rmmz/placeholder_guard.py；app/rmmz/placeholder_mapping.py；app/config/custom_placeholder_rules.py；app/config/structured_placeholder_rules.py；app/agent_toolkit/placeholder_scan.py；app/agent_toolkit/services/placeholder_rules.py；app/rmmz/control_codes.py；app/rmmz/text_rules.py；app/rmmz/schema.py；app/application/font_replacement/service.py；app/application/font_replacement/restore.py；app/application/font_replacement/references.py；app/application/font_replacement/css.py；app/application/font_replacement/files.py；app/application/font_replacement/models.py；rust/src/native_core/font_replacement.rs；rust/src/native_core/write_back_plan/font.rs；rust/src/native_core/write_back_plan/mod.rs
辅助读取：app/application/handler.py；app/application/file_writer.py；app/persistence/font_records.py；app/cli/reports.py；tests/test_nonstandard_data.py；tests/test_agent_toolkit.py；tests/test_translation_line_alignment.py；tests/test_rmmz_loader_extraction_writeback.py；tests/test_text_rules.py；prompts/text_translation_ja_to_zh_system.md；prompts/text_translation_en_to_zh_system.md；docs/advanced-usage.md；skills/att-mz/references/cli-command-contract.md
运行命令：rg -n "占位符|恢复|保护|写回|RMMZ_|CUSTOM_|placeholder|restore|font|restore-font|confirm-font" prompts app tests rust skills docs；rg -n "class TextRules|iter_control_sequence_spans|collect_placeholder_tokens|check_source_residual|structured|custom|PLACEHOLDER|RMMZ|CUSTOM|control" app/rmmz/text_rules.py app/rmmz/control_codes.py app/rmmz/schema.py；rg -n "font|restore-font|confirm-font|confirm_font|font_replacement|FontReplacement|replacement_font|restore_font|gamefont" app/application app/cli app/persistence tests rust/src/native_core skills/att-mz docs/advanced-usage.md README.md；rg -n "def write_planned_text_file_sources|rollback|replace_text_file|replace_json_file|replace_plugins_file" app/application/file_writer.py tests/test_rmmz_loader_extraction_writeback.py；rg -n "collect_native_note_tag_sources|file_pattern_matches\\(|wildcard_match\\(" app rust tests；rg -n "placeholder_rule_loses_translatable_text|structured_placeholder|source_residual|allowed_terms|whole|整句|漏翻|line_scoped|shell" app/source_residual app/rmmz tests/test_translation_line_alignment.py tests/test_agent_toolkit.py；rg -n "apply_font_replacement\\(" app tests scripts rust docs skills
确认问题编号：ATT-MZ-REVIEW-010
需复核问题编号：无
跨批线索：Prompt 搜索显示两个系统提示词只要求 `[RMMZ_...]`、`[CUSTOM_...]` 原样保留，未见占位符恢复机制或写回机制进入系统提示词；`app/application/font_replacement/service.py::apply_font_replacement` 已不被 app 业务入口调用，但仍由 tests/test_rmmz_loader_extraction_writeback.py 直接测试，批次 16 继续复核测试是否锁定旧字体覆盖入口
未覆盖范围：批次 08 不深审 TextScope/warm index 对各类支线的索引缓存事实来源，也不深审 Rust 写回计划对 Note、非标准 data 和字体记录的完整替换协议；这些留给批次 09、12、14
```

### 批次 09 产出

```text
主读文件：app/text_scope/models.py；app/text_scope/builder.py；app/text_scope/write_probe.py；app/text_index.py；app/agent_toolkit/services/text_index.py；app/persistence/text_index_records.py；app/persistence/sql.py；app/agent_toolkit/services/quality.py；app/agent_toolkit/services/manual_translation.py；app/agent_toolkit/services/workspace.py；app/agent_toolkit/services/placeholder_rules.py；tests/test_text_index.py
辅助读取：app/application/handler.py；app/application/flow_gate.py；app/config/overrides.py；app/rmmz/text_rules.py；app/rmmz/extraction.py；scripts/benchmark_small_tasks.py；tests/test_agent_toolkit.py；tests/test_benchmark_small_tasks.py；docs/advanced-usage.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/references/cli-command-contract.md
运行命令：rg -n "def _text_scope_blocking_errors|unwritable_entries|write_back_probe|blocking_errors|_text_scope_blocking_errors" app tests；rg -n "text_index|COUNT_PENDING|SELECT_PENDING|pending_text_index|CREATE TABLE.*text_index|writable" app/persistence tests/test_text_index.py scripts/benchmark_small_tasks.py tests/test_benchmark_small_tasks.py；rg -n "def _text_index_records_to_scope|def _build_text_index_coverage_report|stale_paths|unwritable|writable_paths|_quality_report_from_text_index|detect_text_index_invalidations" app/agent_toolkit/services/quality.py app/agent_toolkit/services/manual_translation.py app/agent_toolkit/services/workspace.py；rg -n "source_residual|terminology|term|text_index|rules_fingerprint|external_rule|workflow_gate_scope_hashes|plugin_source" app/text_index.py app/text_scope app/application/handler.py app/agent_toolkit/services/text_index.py app/agent_toolkit/services/placeholder_rules.py；rg -n "write_back_protocol|collect_.*write.*protocol|native_write_protocol|write_protocol|collect_agent_service_native_quality_details" app/agent_toolkit/services/quality.py app/agent_toolkit/services/common.py app/native_quality.py；rg -n "rebuild_text_index\\(|setting_overrides|SettingOverrides|quality_report\\(" app/agent_toolkit/services app/application app/cli tests/test_agent_toolkit.py tests/test_text_index.py；rg -n "source_text_required_pattern|line_width_count_pattern|long_text_line_width_limit|strip_wrapping_punctuation_pairs|preserve_wrapping_punctuation_pairs" app/config/overrides.py app/rmmz/text_rules.py app/rmmz/extraction.py app/text_index.py
确认问题编号：ATT-MZ-REVIEW-011
需复核问题编号：无
跨批线索：插件源码高风险在 warm index 重建和普通质量报告快路径中的缺口已由 ATT-MZ-REVIEW-009 覆盖，本批不重复立案；普通 quality-report 默认使用索引且不执行写入可行性探针，与 Skill/高级用法文档的普通报告契约一致，写回级检查仍由 include_write_probe 完整路径承担；scripts/benchmark_small_tasks.py 直接读取 text_index_items 生成小任务输入，批次 16 继续复核 benchmark 测试是否锁定了过窄的索引表形态
未覆盖范围：批次 09 不深审翻译 batch、Prompt、质量门禁完整语义、写回 gate 和 Rust native 索引/写回协议；这些留给批次 10-14
```

### 批次 10 产出

```text
主读文件：app/translation/context.py；app/translation/verify.py；app/translation/text_translation.py；app/translation/retry.py；app/translation/cache.py；app/translation/batch.py；app/llm/handler.py；app/llm_request_body_extra.py；app/utils/config_loader_utils.py；app/terminology/prompt.py；app/application/handler.py；app/application/use_cases/translation_run.py；prompts/text_translation_ja_to_zh_system.md；prompts/text_translation_en_to_zh_system.md
辅助读取：app/config/schemas.py；app/llm/errors.py；app/cli/runtime.py；app/cli/parser.py；tests/test_translation_cache_context.py；tests/test_translation_line_alignment.py；tests/test_config_overrides.py；tests/test_llm_retry.py；tests/test_terminology.py；tests/test_cli_json_output.py
运行命令：rg --files app\translation app\llm prompts tests | rg "(translation|llm|prompt|context|terminology|test_translation|test_llm|test_prompt|agent_toolkit)"；rg -n "final user prompt|prompt.*location_path|translated_text|位置:|source_line|source_file|database|db|术语表|\[\[术语表\]\]|original_lines|translation_lines|model_response|parse|retry|repair" app tests prompts skills docs；rg -n "include_source_lines|输出字段列表|原文对照规则|source_lines|system_prompt|selected_system_prompt_file|text_translation" app/config app/utils app/translation prompts tests；rg -n "request_body_extra|extra_body|stream|streaming|response_format|json_repair|repair_json" app tests；rg -n "write_llm_failure|quality_error_count|success_count|TranslationRunInterrupted|LLMRequestFailure|stop_on_error_rate|write_translation_quality_errors|write_translation_items" app tests；rg -n "stop_on_error_rate|检查没通过的译文比例|time_limit_seconds|max_batches|max_items|TranslationRunInterrupted|iter_error_items|iter_right_items" tests app
确认问题编号：ATT-MZ-REVIEW-012
需复核问题编号：无
跨批线索：正文翻译 prompt 主链路使用每批短 id，真实 location_path 只保留在 prompt_ids_by_location_path 映射中；术语提示词以 [[术语表]] 和 “原文 => 标准译名” 进入 user prompt，未见内部路径、文件名、DB 表或 translated_text 泄露；默认系统提示词不要求 source_lines，开启 include_source_lines 后也只作为模型原文对照字段，verify_translation_batch 只信任 id 与 translation_lines 并继续执行行数、结构、占位符和源文残留校验。JSON repair 只修复语法/外层包裹，修复后仍通过 TranslationResponse、短 id 映射和业务校验。tests/test_translation_cache_context.py、tests/test_config_overrides.py、tests/test_terminology.py、tests/test_translation_line_alignment.py 和 tests/test_llm_retry.py 对这些边界已有覆盖。
未覆盖范围：批次 10 不深审质量报告、写回前检查、持久化 schema 和 Rust native 的质量/写回协议；这些留给批次 11-14。模型额外请求体除拒绝 stream/stream_options 外允许透传其他 OpenAI 兼容参数，本批只确认其不会绕过当前非流式完整 JSON 响应边界。
```

### 批次 11 产出

```text
主读文件：app/agent_toolkit/services/quality.py；app/agent_toolkit/services/coverage.py；app/agent_toolkit/services/manual_translation.py；app/agent_toolkit/services/feedback.py；app/agent_toolkit/services/common.py；app/application/write_back_gate.py；app/application/flow_gate.py；app/text_scope/builder.py；app/text_scope/models.py；app/persistence/run_records.py；app/persistence/translation_records.py；app/persistence/text_index_records.py；app/persistence/sql.py；app/native_write_plan.py；rust/src/native_core/write_back_plan/quality_gate.rs；rust/src/native_core/write_back_plan/mod.rs；rust/src/native_core/write_back_plan/repository.rs
辅助读取：app/native_quality.py；app/source_residual/rules.py；tests/test_agent_toolkit.py；tests/test_rmmz_loader_extraction_writeback.py；tests/test_persistence.py；docs/advanced-usage.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz/references/failure-recovery.md；skills/att-mz/references/feedback-iteration.md；skills/att-mz/references/plugin-source-text-agent-task.md
运行命令：rg -n "quality|质量|fix|repair|manual|检查没通过|quality_error|source_residual|overwide|placeholder|write_back|writeback|include_write_probe|run_quality_error|quality_errors" app\agent_toolkit app\application app\cli app\persistence app\source_residual app\native_quality.py tests docs\advanced-usage.md skills\att-mz\references；rg -n "async def quality_report|async def translation_status|async def export_quality_fix_template|_quality_report_from_text_index|include_write_probe|collect_agent_service_native_quality_details|_collect_rust_write_back_gate|write_back_gate" app\agent_toolkit\services\quality.py；rg -n "async def audit_coverage|coverage|blocking|write_probe|text_scope|include_write_probe|unwritable|pending|quality" app\agent_toolkit\services\coverage.py app\application\write_back_gate.py app\application\flow_gate.py app\text_scope app\persistence\text_index_records.py；rg -n "async def import_manual_translations|manual|quality_fix|translation_lines|validate|text_index|write_translation_items|write_translation_quality_errors|pending|quality_error" app\agent_toolkit\services\manual_translation.py app\agent_toolkit\services\feedback.py tests\test_agent_toolkit.py；rg -n "include_write_probe|write_back_gate|source_residual_count|placeholder_risk_count|overwide_line_count|write_back_protocol_count|quality-report|quality_report" tests\test_agent_toolkit.py tests\test_rmmz_loader_extraction_writeback.py docs\advanced-usage.md skills\att-mz\references；rg -n "quality_gate|source_residual|placeholder_risk|overwide|write_back_protocol|mode.*quality|build_native_write_back_plan" rust app\native_write_plan.py rust\src；rg -n "delete_translation_quality_errors|quality_errors|translation_quality_errors|stale.*quality|manual.*quality|saved_quality_errors|scope_mode" app tests；rg -n "def _collect_feedback_text_occurrences|def _classify_feedback_occurrences|plugin_source_hardcoded|feedback|occurrence" app\agent_toolkit\services\common.py tests\test_agent_toolkit.py skills\att-mz\references\feedback-iteration.md docs\advanced-usage.md
确认问题编号：ATT-MZ-REVIEW-013、ATT-MZ-REVIEW-014
需复核问题编号：无
跨批线索：普通 quality-report 的 warm index 快路径和完整 scope 路径都会把 latest_run 的 quality_error 先计算 run_quality_error_count，再过滤到当前 pending_paths 作为本轮需要修复的 quality_error_count；写回硬门槛同样只在 require_complete_translation 且 pending_paths 存在时检查 latest_run 的 active_quality_errors，并用 Rust/Python native quality 阻断已保存译文本体问题。feedback 服务会扫描 active runtime 的 data、plugins.js 和 js/plugins/*.js 候选，插件源码反馈定位作为结构性硬编码分类，不与当前运行源码诊断缓存合并。
未覆盖范围：批次 11 不深审具体写回计划文件替换安全、Rust native 契约字段和发行版 Skill 文案；这些留给批次 12、14、15。插件源码 active runtime 诊断与 runtime write map 的精确反推已在批次 07 留线索，本批只确认质量/反馈入口的职责边界。
```

### 批次 12 产出

```text
主读文件：app/application/write_back_gate.py；app/application/file_writer.py；app/application/handler.py；app/native_write_plan.py；rust/src/native_core/write_back_plan/mod.rs；rust/src/native_core/write_back_plan/quality_gate.rs；rust/src/native_core/write_back_plan/models.rs；rust/src/native_core/write_back_plan/layout.rs；rust/src/native_core/write_back_plan/utils.rs；rust/src/native_core/write_back_plan/repository.rs；tests/test_rmmz_loader_extraction_writeback.py；tests/test_native_adapters.py；tests/_native_write_plan_helper.py
辅助读取：app/cli/commands/write_back.py；app/cli/parser.py；tests/test_cli_json_output.py；docs/advanced-usage.md；docs/database-wiki.md；skills/att-mz/SKILL.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/SKILL.md
运行命令：rg -n "async def write_back|async def rebuild_active_runtime|async def write_terminology|_write_game_files_from_plan|build_native_write_back_plan|assert_write_back_quality_passed|write_planned_text_file_sources|replace_font_replacement_records|copy_replacement_font|replace_gamefont_css_references|confirm_font_overwrite|confirm_font" app/application/handler.py app/cli/commands/write_back.py app/cli/parser.py app/cli/runtime.py tests/test_rmmz_loader_extraction_writeback.py tests/test_cli_json_output.py；Get-Content app/application/file_writer.py；Get-Content app/native_write_plan.py；rg -n "write_back\(|rebuild_active_runtime|write_terminology|confirm_font_overwrite|quality gate|active runtime|terminology|write-back|write-terminology" tests/test_rmmz_loader_extraction_writeback.py tests/test_cli_json_output.py tests/_native_write_plan_helper.py tests/test_benchmark_rebuild_active_runtime.py tests/test_benchmark_active_runtime_audit.py；rg -n "quality_gate|assert_saved_translation_quality_passed|mode|WriteBackMode|write_terminology|rebuild_active_runtime|trusted|snapshot|source|runtime|allowed_translation_paths|plan_content_output_dir|content_path|target_path|relative_path|current" rust/src/native_core/write_back_plan app/native_write_plan.py tests/_native_write_plan_helper.py；rg -n "post_write|写入后|active_runtime_audit|audit_active_runtime|runtime_write_map|replace_plugin_source_runtime_write_maps|nonstandard_data_audit|plugin_source_audit|写后" app tests rust docs skills；rg -n "validate_planned_file|content_path|target_path|relative_path|is_relative_to|native_write_back_plan" tests/test_native_adapters.py tests/test_rmmz_loader_extraction_writeback.py tests/_native_write_plan_helper.py app/native_write_plan.py
确认问题编号：ATT-MZ-REVIEW-015
需复核问题编号：无
跨批线索：普通 write-back 和 rebuild-active-runtime 都经 _prepare_write_operation(require_complete_translation=True) 进入同一 workflow gate、TextScope 和写回质量门槛；write-terminology 经同一入口但 require_complete_translation=False，允许正文 pending，同时 Rust plan 仍对 allowed_translation_paths 内的已保存译文执行 native 质量 gate。Python adapter 已校验 Rust 返回 target_path 必须位于 content_root 且与 relative_path 一致，content_path 必须位于本次临时输出目录内，相关 tests/test_native_adapters.py 用例已固定。
未覆盖范围：批次 12 不深审 DB schema 所有权、Rust native 线程配置和发行包打包映射；这些留给批次 13、14、15。字体覆盖副作用在批次 08 已记录为 ATT-MZ-REVIEW-010，本批不重复登记。
```

### 批次 13 产出

```text
主读文件：app/persistence/repository.py；app/persistence/sql.py；app/persistence/session_base.py；app/persistence/translation_records.py；app/persistence/run_records.py；app/persistence/rule_records.py；app/persistence/text_index_records.py；app/persistence/terminology_records.py；app/persistence/plugin_source_runtime_records.py；app/persistence/font_records.py；app/persistence/source_snapshot_records.py；app/persistence/records.py；app/persistence/rows.py；tests/test_persistence.py
辅助读取：app/application/handler.py；app/agent_toolkit/services/rule_validation.py；app/agent_toolkit/services/placeholder_rules.py；app/agent_toolkit/services/nonstandard_data.py；app/cli/commands/rules.py；docs/database-wiki.md；docs/advanced-usage.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/references/cli-command-contract.md
运行命令：rg -n "## 22\\. 批次 13|### 批次 13 产出|schema|schema_version|ensure_schema|migration|migrate|CREATE TABLE|ALTER TABLE|PRAGMA|translation_items|translation_runs|llm_failures|translation_quality_errors|compat|legacy|旧|自动迁移|INSERT OR REPLACE|commit\\(" app/persistence tests/test_persistence.py app/application app/agent_toolkit/services docs/database-wiki.md skills/att-mz/references/workspace-schema.md；rg --files app/persistence tests | rg "(persistence|records|repository|session|sql|database|db)"；Get-Content app/persistence/repository.py；Get-Content app/persistence/sql.py；Get-Content app/persistence/translation_records.py；Get-Content app/persistence/run_records.py；Get-Content app/persistence/rule_records.py；Get-Content app/persistence/text_index_records.py；rg -n "deleted_translation_items = await session\\.delete_translation_items|await session\\.replace_.*rules|await session\\.clear_plugin_source_runtime_write_maps|await session\\.delete_rule_review_state|await session\\.replace_rule_review_state|write_rule_import_translation_backup" app/application/handler.py app/agent_toolkit/services/rule_validation.py app/agent_toolkit/services/placeholder_rules.py app/agent_toolkit/services/nonstandard_data.py；rg -n "async def delete_translation_items_by_prefixes|async def delete_translation_items_by_paths|await self\\.connection\\.commit\\(\\)" app/persistence/translation_records.py app/persistence/rule_records.py app/persistence/plugin_source_runtime_records.py；rg -n "rollback|transaction|失败|delete_translation_items|deleted_translation|规则导入|清理失效译文|backup|备份" tests/test_persistence.py tests/test_agent_toolkit.py tests/test_rmmz_loader_extraction_writeback.py
确认问题编号：ATT-MZ-REVIEW-016
需复核问题编号：无
跨批线索：数据库 schema 当前通过 EXPECTED_STATIC_TABLE_NAMES、表结构签名、schema_version 和旧库测试实现显式失败；未发现运行时自动迁移或静默补表。start_translation_run 会清空上一轮 translation_quality_errors 但保留历史 translation_runs/llm_failures，通过 latest_run 口径读取；delete_translation_quality_errors_by_paths 按路径跨 run 删除质量错误，当前与“路径已修好”语义基本一致，留到批次 17 总收束时复核是否需要单独列为表语义问题。
未覆盖范围：批次 13 不深审 Rust 只读 repository 与 Python schema 之间的契约字段一致性、native contract version 和线程池；这些留给批次 14。文件系统副作用事务问题已在批次 08 和 12 登记，本批只审 DB 状态。
```

### 批次 14 产出

```text
主读文件：app/native_contract.py；app/native_quality.py；app/native_javascript_ast.py；app/native_write_plan.py；app/regex_contract.py；rust/src/lib.rs；rust/src/native_core.rs；rust/src/native_core/pool.rs；rust/src/native_core/javascript_ast.rs；rust/src/native_core/write_back_plan/mod.rs；rust/src/native_core/write_back_plan/test_support.rs；tests/test_native_adapters.py；tests/test_regex_contract.py
辅助读取：docs/development/review-records/rust-migration-review-findings-batch-01.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/references/cli-command-contract.md；tests/test_benchmark_small_tasks.py；tests/test_benchmark_rebuild_active_runtime.py；tests/test_benchmark_active_runtime_audit.py
运行命令：rg -n "## 23\\. 批次 14|native_contract|native_contract_version|NATIVE_CONTRACT_VERSION|ATT_MZ_RUST_THREADS|rust_threads|thread|rayon|ThreadPool|run_with_optional_pool|native_thread_count|collect_native|count_native|write_protocol|parse_javascript|build_write_back_plan|quality_gate|contract|ensure_native_contract_version" app rust tests docs skills scripts；rg --files app rust tests scripts | rg "(native|rust|write_protocol|write_back_plan|javascript_ast|quality|contract|benchmark|thread|pool)"；rg -n "stale_native_contract|native_contract|ensure_native_contract_version|parse_javascript_string_spans|_load_native_javascript_ast_module|MissingNative|OldNative|native_write_plan_rejects|native_quality_rejects|regex_contract" tests/test_native_adapters.py tests/test_regex_contract.py app/native_javascript_ast.py app/native_quality.py app/native_write_plan.py app/regex_contract.py；Get-Content rust/src/lib.rs；Get-Content rust/src/native_core.rs；Get-Content rust/src/native_core/pool.rs；Get-Content tests/test_native_adapters.py；rg -n "run_with_optional_pool|par_iter|into_par_iter|read_configured_thread_count|with_thread_count_override_for_test|ATT_MZ_RUST_THREADS|native_thread_count|thread_count" rust/src app tests docs skills
确认问题编号：ATT-MZ-REVIEW-017
需复核问题编号：无
跨批线索：Rust 绑定层统一暴露 native_contract_version=2；质量、写回和正则 adapter 在加载 app._native 后调用 ensure_native_contract_version()，对应测试覆盖缺少契约函数和旧契约版本；Rust pool 读取 ATT_MZ_RUST_THREADS，0 或未设置时使用 Rayon 默认线程池，非法值报错，JS AST 批量扫描、质量扫描、写回协议、字体扫描和写回计划热路径均通过 run_with_optional_pool 包裹，Rust tests 覆盖 JS AST 与写回计划线程配置生效。Python adapter 对 quality counts、write protocol counts、write plan target_path/content_path、AST result has_error/ast_context 等返回 payload 有字段级解析测试。
未覆盖范围：批次 14 不重新评估各业务命令何时调用 native 热路径，也不执行新的性能基准；发行版打包是否携带匹配的 native 扩展和 Skill 说明留给批次 15。write plan 数据一致性问题已在批次 12、13 登记，本批不重复记录。
```

### 批次 15 产出

```text
主读文件：.github/workflows/release.yml；scripts/build_release.py；scripts/extract_release_notes.py；docs/release-readme.md；docs/development/release-and-tests.md；CHANGELOG.md；skills/att-mz/SKILL.md；skills/att-mz-release/SKILL.md；tests/test_release_notes.py
辅助读取：README.md；skills/att-mz/references/；skills/att-mz-release/references/；docs/advanced-usage.md；docs/超重型破坏性重构/系统地图.md；tests 当前文件列表
运行命令：rg --files .github scripts skills docs tests | rg "(release|pack|package|dist|build|skill|SKILL|README|workflow|notes|changelog|CHANGELOG|test_release|test_skill|att-mz-release)"；rg -n "att-mz-release|att-mz.exe|release|Release|发行|打包|package|dist|zip|scie|PEX|skills/att-mz|skills\\\\att-mz|SKILL.md|frontmatter|name:|CHANGELOG|changelog|release notes|自动生成|例行更新|若干优化|docs 覆盖 Skill|Agent 契约|GitHub Actions|workflow_dispatch|正式发布" .github scripts skills docs tests pyproject.toml README.md；Get-Content .github/workflows/release.yml；Get-Content scripts/build_release.py；Get-Content scripts/extract_release_notes.py；Get-Content tests/test_release_notes.py；Get-Content docs/release-readme.md；Get-Content docs/development/release-and-tests.md；Get-Content CHANGELOG.md；git diff --no-index --stat -- skills/att-mz skills/att-mz-release；git diff --no-index -- skills/att-mz/SKILL.md skills/att-mz-release/SKILL.md；git diff --no-index --stat -- skills/att-mz/references skills/att-mz-release/references；git diff --no-index --name-status -- skills/att-mz/references skills/att-mz-release/references；uv run python -c "from scripts.extract_release_notes import extract_release_notes_section; print(repr(extract_release_notes_section(changelog_text='# 更新日志\\n\\n## v0.2.0 - 2026-06-02\\n\\n## v0.1.9 - 2026-05-31\\n\\n- old\\n', tag='v0.2.0')))"
确认问题编号：ATT-MZ-REVIEW-018、ATT-MZ-REVIEW-019
需复核问题编号：无
跨批线索：release workflow 当前会按顺序准备 release notes、uv sync、basedpyright、pytest、Rust fmt/clippy/test、build_release、上传 ZIP 并用 release-notes.md 发布 GitHub Release；scripts/build_release.py 当前只在 GITHUB_ACTIONS=true 时执行，会复制发行版 README、配置模板、提示词、字体、发行版 references，并把 skills/att-mz-release/SKILL.md 的 frontmatter name 改成 att-mz 后写入发行包 skills/att-mz/SKILL.md。开发版和发行版 Skill 主体差异集中在命令入口、目录名和发行版黑盒排障边界，未发现业务阶段矩阵本身明显漂移。docs/development/release-and-tests.md 仍引用不存在的 tests/test_skill_protocol.py，该测试缺口已在 ATT-MZ-REVIEW-004 记录，本批不重复登记。
未覆盖范围：批次 15 不实际触发 GitHub Actions release，不构建真实 Windows ZIP，也不解包检查 PEX 内部依赖；测试保护能力的全局收束留给批次 16。
```

### 批次 16 产出

```text
主读文件：tests/；tests/conftest.py；tests/test_agent_toolkit.py；tests/test_rmmz_loader_extraction_writeback.py；tests/test_plugin_source_text.py；tests/test_cli_json_output.py；tests/test_translation_cache_context.py；tests/test_terminology.py；tests/test_config_overrides.py；tests/test_translation_line_alignment.py；tests/test_llm_retry.py；tests/test_release_notes.py
辅助读取：app/cli/commands/write_back.py；app/application/handler.py；app/agent_toolkit/services/quality.py；app/agent_toolkit/services/manual_translation.py；tests/test_benchmark_small_tasks.py；docs/development/release-and-tests.md
运行命令：rg --files tests | Sort-Object | Measure-Object -> 29 个测试文件；rg -n 'main\(\["(add-game|prepare-agent-workspace|import-plugin-rules|translate|quality-report|write-back|run-all|import-manual-translations|rebuild-text-index)' tests -> 只命中 tests/test_cli_json_output.py 中 translate、write-back、run-all、run-all --skip-write-back 4 个局部 CLI 调用；Get-Item tests/test_agent_toolkit.py,tests/test_rmmz_loader_extraction_writeback.py,tests/test_plugin_source_text.py,tests/test_cli_json_output.py | Select-Object Name,Length -> 最大 4 个测试文件分别约 386036、177841、88833、55924 字节；Get-Content 行数统计 -> test_agent_toolkit.py 8718 行，test_rmmz_loader_extraction_writeback.py 4035 行，test_plugin_source_text.py 2037 行，test_cli_json_output.py 1538 行；rg -n '^(async )?def test_.*(rule|workspace|quality|write|manual|feedback|placeholder|translate|terminology|coverage|font|source_snapshot|mv_namebox|note|nonstandard|plugin|runtime|run_all|run-all|CLI|json)' tests/test_agent_toolkit.py tests/test_rmmz_loader_extraction_writeback.py -> 两个大文件覆盖多领域测试入口；读取 tests/test_cli_json_output.py 第 260-350、520-670 行和 tests/test_agent_toolkit.py 第 6610-6778 行确认 run-all/translate 关键路径使用 FakeHandlerSession、fake_translate_text_for_handler、fake_run_text_translation_batches；rg -n "Map001\.json|location_path|位置:|translated_text|\[\[术语表\]\]|source_lines|user_prompt|system prompt|prompt" tests/test_translation_cache_context.py tests/test_terminology.py tests/test_config_overrides.py tests/test_translation_line_alignment.py tests/test_llm_retry.py -> 已有最终 user prompt/system prompt 隐私断言；rg -n "<私有路径关键词>|<用户名关键词>|<样本名关键词>|setting\.toml|setting\.example\.toml|load_setting\(|ATT_MZ_HOME|tmp_path.*setting" tests app scripts docs -> 未发现测试直接依赖开发机私有 setting.toml 的新缺口
确认问题编号：ATT-MZ-REVIEW-020、ATT-MZ-REVIEW-021
需复核问题编号：无
跨批线索：Prompt 隐私边界已有 tests/test_translation_cache_context.py、tests/test_terminology.py、tests/test_config_overrides.py 直接断言最终 user prompt/system prompt 不出现 Map001.json、location_path、translated_text、位置: 等内部上下文，本批不新增问题；ATT-MZ-REVIEW-007、ATT-MZ-REVIEW-013、ATT-MZ-REVIEW-014、ATT-MZ-REVIEW-015 已覆盖测试锁定旧结构或坏结构的具体路径，本批不重复登记；release/Skill 协议测试缺口已由 ATT-MZ-REVIEW-004 和 ATT-MZ-REVIEW-019 覆盖。
未覆盖范围：批次 16 不新增运行 pytest 或门禁命令，不执行真实端到端翻译流程；本批只检查测试保护能力、测试组织和已存在断言边界，最终去重和问题索引留给批次 17。
```

### 批次 17 产出

```text
主读文件：docs/超重型破坏性重构/reviewplan.md
辅助读取：git status --short
运行命令：rg -n '^编号：ATT-MZ-REVIEW-|^严重程度：|^### P[0-3] 问题|^确认问题编号：|^需复核问题编号：' docs/超重型破坏性重构/reviewplan.md -> 确认批次产出和问题记录均有编号/严重程度；PowerShell 统计 '^编号：ATT-MZ-REVIEW-[0-9]{3}' -> count=21、unique=21，编号 ATT-MZ-REVIEW-001 到 ATT-MZ-REVIEW-021 连续；PowerShell 按问题块统计严重程度 -> P0=1、P1=8、P2=10、P3=2；git status --short -> 仅 docs/超重型破坏性重构/reviewplan.md 已修改
确认问题编号：无新增；最终确认问题为 ATT-MZ-REVIEW-001 至 ATT-MZ-REVIEW-021
需复核问题编号：无
跨批线索：ATT-MZ-REVIEW-007、ATT-MZ-REVIEW-013、ATT-MZ-REVIEW-014、ATT-MZ-REVIEW-015 已覆盖测试锁定旧结构或坏结构的具体路径，批次 16 只新增全链路金丝雀缺口和测试组织问题；ATT-MZ-REVIEW-004 与 ATT-MZ-REVIEW-019 分别覆盖 Skill/CLI 协议测试缺口和发行包布局测试缺口，批次 15/16 不重复登记；字体副作用事务问题由 ATT-MZ-REVIEW-010 记录，写后审计失败事务边界由 ATT-MZ-REVIEW-015 记录，规则导入 DB 事务边界由 ATT-MZ-REVIEW-016 记录，三者保持分开。
未覆盖范围：批次 17 不重新审查源码、不执行修复、不新增测试、不重复运行批次 00 的质量门禁；GitHub Actions release、真实 Windows ZIP 解包和完整端到端翻译流程仍按对应批次未覆盖范围记录。
```

### 补充批次 18 产出

```text
主读文件：docs/超重型破坏性重构/reviewplan.md；app/cli/parser.py；app/cli/runtime.py；app/cli/commands/translation.py；app/cli/commands/write_back.py；app/cli/commands/registry.py；app/cli/reports.py；app/source_language_probe.py；app/agent_toolkit/services/workspace.py；tests/test_agent_toolkit.py；tests/test_cli_json_output.py；tests/test_source_language_probe.py；skills/att-mz/SKILL.md；skills/att-mz-release/SKILL.md；skills/att-mz/references/cli-command-contract.md；skills/att-mz-release/references/cli-command-contract.md；skills/att-mz/references/workspace-schema.md；docs/advanced-usage.md
辅助读取：python-engineering-standards；rust-engineering-standards；superpowers:using-superpowers；git status --short；当前问题编号索引
运行命令：git status --short -> 仅 docs/超重型破坏性重构/reviewplan.md 已修改；rg -n '^## 30|^## 31|^### 批次 1[5-7]|^## 32|^### P[0-3]|^## 33|^## 34|^编号：ATT-MZ-REVIEW-|^已完成批次：|^已确认问题数量：|^P[0-3] 数量' docs/超重型破坏性重构/reviewplan.md -> 当前问题区和最终覆盖声明定位完成；PowerShell 统计 '^编号：ATT-MZ-REVIEW-[0-9]{3}' -> count=21、unique=21；rg -n "add_argument|--[a-z0-9-]+|dest=|default=|concurrency|max_|timeout|stop_on|stop-on|setting_overrides|report_detail|skip|confirm|force|threads|workers" app/cli app/application app/agent_toolkit -> 参数链路补查，stop-on-error-rate 和 setting_overrides 问题已由 ATT-MZ-REVIEW-012、ATT-MZ-REVIEW-011 覆盖；rg -n "except Exception|except BaseException|contextlib\.suppress|pass\s*$|return None|raise RuntimeError|TODO|FIXME|fallback|兼容|legacy|deprecated|旧|临时|mock|假装|忽略|跳过|silent|silently" app tests scripts rust docs skills -> 宽泛异常主要集中在 benchmark 结构化失败结果，未新增主流程问题；rg -n "probe-source-language|source_language_probe|recommended_source_language|source_language|low_confidence|uncertain|source-language" app tests skills docs README.md -> 源语言探测入口、Skill 和基础测试已定位，未新增独立问题；rg -n "prepare_agent_workspace|cleanup_agent_workspace|validate_agent_workspace|plugin-source-rules|nonstandard-data-rules|stale|reuse|existing|output_dir|manifest.files|工作区.*旧|工作区.*复用|清理" tests/test_agent_toolkit.py tests/test_cli_json_output.py app/agent_toolkit/services/workspace.py skills/att-mz/references/workspace-schema.md docs/advanced-usage.md docs/development/agent-toolkit.md -> 定位工作区复用和旧可选文件漏检；读取 app/agent_toolkit/services/workspace.py 第 200-330、441-499、517-548、929-973 行确认 prepare、manifest、validate、cleanup 的路径事实来源
确认问题编号：ATT-MZ-REVIEW-022
需复核问题编号：无
跨批线索：源语言探测只生成注册前报告，add-game 仍要求显式 --source-language，现有 tests/test_source_language_probe.py 覆盖日英两个基本夹具；缺少完整 CLI/Agent 金丝雀已由 ATT-MZ-REVIEW-020 覆盖，本批不重复登记。write_report_outputs 对“导出数据文件不被报告覆盖”的边界已有 tests/test_cli_json_output.py 覆盖，本批不新增报告输出问题。工作区复用问题与 ATT-MZ-REVIEW-004 的 Skill 协议测试缺口、ATT-MZ-REVIEW-020 的端到端金丝雀缺口相关，但根因是 manifest 与固定文件存在性两套工作区事实来源，单独登记。
未覆盖范围：本补充批不重跑全量 pyright/pytest/Rust 门禁，不构造真实 stale workspace 复现，只做漏检高风险面静态审查并把新增确认问题写回。
```

## 32. 问题记录区

执行 review 时从 `ATT-MZ-REVIEW-001` 开始编号。此区初始为空；只追加问题，不追加解决方案。

### P0 问题

此处记录已确认会破坏外部契约、写回安全、数据一致性、Prompt 隐私、DB schema 兼容判断或发行边界的问题。

```text
编号：ATT-MZ-REVIEW-010
批次：08 Note、非标准 data、占位符、源文保留与字体
严重程度：P0
证据等级：E2
状态：已确认
问题：普通写回确认字体覆盖后，替换字体复制、gamefont.css 改写和 font_replacement_records 保存发生在计划文件事务之前；如果后续写文件事务失败，这些字体副作用和数据库记录不随事务回滚，导致“写入失败不改变当前运行文件、字体记录只描述成功写入状态”的写回安全模型不成立。
证据：app/application/handler.py 第 1428-1446 行先生成 Rust 写回计划，第 1449-1461 行在写计划文件前复制替换字体、改写 gamefont.css 并调用 session.replace_font_replacement_records(font_records)，第 1465-1471 行才调用 write_planned_text_file_sources() 写入 data、plugins.js 和插件源码文件；app/application/file_writer.py 第 64-103 行的事务回滚只覆盖传入的 _WriteOperation 列表，未包含前置字体复制、gamefont.css 替换或数据库记录；app/application/font_replacement/css.py 第 63-68 行独立备份并替换 gamefont.css；app/persistence/font_records.py 第 15-36 行 replace_font_replacement_records() 先删除旧记录再插入本次记录并 commit。app/application/handler.py 第 1684-1715 行 restore-font 读取字体记录和配置候选字体名后执行还原，并在 records 存在时清空记录；app/application/font_replacement/restore.py 第 49-54、108-125 行基于原件备份对比还原 CSS，但该还原路径不是写回失败事务的一部分。tests/test_rmmz_loader_extraction_writeback.py 第 1897-2038 行只覆盖 Rust 计划阶段失败时不会产生字体副作用；第 420-430、578-579、732-733 行 monkeypatch 的 write_planned_text_file_sources 用例都是成功路径或非字体路径，当前未见覆盖“CSS/记录已写入后计划文件事务失败”的测试。
影响：write-back、write-terminology、rebuild-active-runtime 和 run-all 的最终写入阶段在失败路径上可能留下已改写的字体样式表、已复制字体文件和已经保存的字体覆盖记录，而 data/plugins 计划文件没有完成写入；后续 restore-font 又会把这些记录当作最近一次字体覆盖事实读取，遮住“写文件阶段失败恢复和数据库记录一致”的当前模型。
根因线索：字体覆盖同时属于写文件计划、CSS 运行文件修改、字体文件复制和数据库可还原记录；当前主流程把其中一部分放在 Rust 计划文件事务之外，并且记录保存早于计划文件落盘。
冲突的事实来源：app/application/handler.py 中前置字体副作用和记录保存；app/application/file_writer.py 的计划文件事务；app/persistence/font_records.py 的最近一次字体覆盖记录；restore-font 对记录和原件备份的读取语义。
重复或旧路径对象：handler 内字体复制/CSS 替换/记录保存路径；write_planned_text_file_sources() 文件事务；font_replacement_records 最近一次覆盖记录；app/application/font_replacement/service.py::apply_font_replacement 仍作为单独 Python 字体覆盖入口被测试直接使用。
应删除或合并的对象：写文件事务外独立存在的字体运行文件副作用；早于计划文件落盘提交的 font_replacement_records；测试直接锁定的旧 Python 字体覆盖入口。
受影响外部契约：`write-back --confirm-font-overwrite`、`write-terminology --confirm-font-overwrite`、`rebuild-active-runtime --confirm-font-overwrite`、`run-all --confirm-font-overwrite`、`restore-font`、字体覆盖记录表和写入失败恢复语义。
验证方式或证据缺口：`rg -n "confirm_font_overwrite|copy_replacement_font|replace_gamefont_css_references|replace_font_replacement_records|write_planned_text_file_sources|clear_font_replacement_records" app/application/handler.py app/application/file_writer.py app/application/font_replacement/css.py app/persistence/font_records.py tests/test_rmmz_loader_extraction_writeback.py` 可定位；当前证据为静态路径与现有测试覆盖缺口，未执行会故意制造写文件失败的破坏性复现。
```

### P1 问题

此处记录会阻塞超重型破坏性重构的结构性问题。

```text
编号：ATT-MZ-REVIEW-003
批次：02 CLI 入口与 JSON 报告
严重程度：P1
证据等级：E1
状态：已确认
问题：CLI stdout JSON 的外层报告结构存在两个构造来源：正常命令报告使用 AgentReport 模型，参数错误、业务错误、未知异常等顶层错误路径由 cli_main 手写 payload，外部 Agent JSON envelope 的当前模型没有唯一事实来源。
证据：app/agent_toolkit/reports.py 第 22-61 行定义 AgentReport、from_parts() 和 to_json_text()，作为“供终端和外部 Agent 使用的统一报告结构”；app/cli_main.py 第 109-128 行的 print_json_error() 直接手写 `status/errors/warnings/summary/details` payload 并 print，不经过 AgentReport；tests/test_cli_json_output.py 第 201-225、229-283、675-689 行分别测试 unexpected_error、business_error、argument_error 输出可解析 JSON，证明顶层错误路径是外部可观察契约。
影响：后续破坏性重构若调整 AgentReport 字段、状态集合、错误去重或序列化规则，正常命令报告和顶层错误报告需要分别维护；外部 Agent 依赖的 stdout JSON envelope 由两个路径并行表达，遮住“CLI stdout JSON 是单一 AgentReport 契约”的当前模型。
根因线索：CLI 启动层为了在解析失败和异常时保持 stdout JSON，自行复制了 AgentReport 外层结构。
冲突的事实来源：app/agent_toolkit/reports.py 的 AgentReport 模型；app/cli_main.py 的 print_json_error() 手写 payload；tests/test_cli_json_output.py 对两类路径分别断言。
重复或旧路径对象：app/cli_main.py::print_json_error；app/agent_toolkit/reports.py::AgentReport；tests/test_cli_json_output.py 中顶层错误 JSON 断言。
应删除或合并的对象：print_json_error() 中复制 AgentReport envelope 的手写 payload。
受影响外部契约：CLI stdout Agent JSON 报告字段、错误语义和退出码。
验证方式或证据缺口：`Select-String -Path app/cli_main.py,app/agent_toolkit/reports.py,tests/test_cli_json_output.py -Pattern "def print_json_error|payload = \\{|class AgentReport|def from_parts|def to_json_text|test_json_command_reports_unexpected_error|test_json_import_command_reports_business_error|test_unknown_command_reports_json_argument_error"` 直接定位；本问题不主张当前输出已经错误，而是确认报告外层结构存在重复事实来源。
```

```text
编号：ATT-MZ-REVIEW-007
批次：05 工作区与规则导入
严重程度：P1
证据等级：E2
状态：已确认
问题：规则候选确认状态同时接受当前完整候选 hash 和旧版截断候选 hash；旧版 hash 命中时 workflow gate 按 warning 放行，导致“当前候选已审查”不是唯一当前事实，旧确认状态仍进入默认翻译/写入前置判断。
证据：app/rule_review_decision.py 第 28 行把 `confirmed_legacy_hash` 列为确认状态，第 143-148 行在 build_rule_review_decision() 中把 `confirmed` 和 `confirmed_legacy_hash` 都作为已审查状态处理，旧 hash 只改 warning code/message，第 199-205 行对空规则确认同样按 `confirmed_legacy_hash` 放行，第 249-264 行 read_confirmation_status() 明确在 state.scope_hash 命中 legacy_scope_hashes 时返回 `confirmed_legacy_hash`；app/application/flow_gate.py 第 697-706 行在普通/结构化占位符候选前置检查中传入 _legacy_placeholder_scope_hashes()，第 754 行的空规则前置检查也复用 build_empty_rule_review_decision()；tests/test_agent_toolkit.py 第 3666-3692 行手工写入旧版普通占位符前 100 候选 hash，并断言 confirmation_status 为 `confirmed_legacy_hash`、severity 为 warning、workflow gate errors 中没有 `placeholder_uncovered`；第 3727-3757 行对结构化占位符旧版 hash 做同样放行断言。
影响：后续破坏性重构需要同时维护“完整候选 hash 当前确认”和“旧版截断候选 hash 兼容确认”两套规则审查事实；当候选数量超过 sample_limit 时，旧确认只覆盖前 100 个候选却能让流程继续，遮住“规则导入后保存的当前候选范围 hash 是唯一确认依据”的当前模型。
根因线索：候选报告曾经用采样明细计算确认 hash，引入完整明细 hash 后保留了旧 hash 兼容判断，并把兼容状态接入 workflow gate。
冲突的事实来源：app/rule_review_decision.py 的当前/旧版确认状态并存；app/application/flow_gate.py 的 legacy_scope_hashes；app/agent_toolkit/services/placeholder_rules.py 导入时保存完整 coverage.scope_hash；tests/test_agent_toolkit.py 对旧版 hash workflow gate 放行的断言。
重复或旧路径对象：`confirmed_legacy_hash`；`_legacy_placeholder_scope_hashes()`；tests/test_agent_toolkit.py::test_placeholder_candidate_review_accepts_legacy_sampled_hash；tests/test_agent_toolkit.py::test_structured_placeholder_candidate_review_accepts_legacy_sampled_hash。
应删除或合并的对象：旧版截断候选确认 hash；workflow gate 中接受 legacy_scope_hashes 的分支；测试中手工写入旧版前 100 候选 hash 并断言放行的用例。
受影响外部契约：规则导入确认状态；普通占位符和结构化占位符候选风险确认；workflow gate 对翻译、手动导入、质量报告和写回前置条件的统一口径。
验证方式或证据缺口：`Select-String -Path app/rule_review_decision.py,app/application/flow_gate.py,app/agent_toolkit/services/rule_validation.py,app/agent_toolkit/services/placeholder_rules.py,app/agent_toolkit/services/quality.py,tests/test_agent_toolkit.py -Pattern "confirmed_legacy_hash|legacy_scope_hashes|legacy_hash|旧版截断|兼容规则放行|重新导入规则后会升级|read_confirmation_status|build_rule_review_decision|build_empty_rule_review_decision|replace_rule_review_state|reviewed_empty|RuleReviewState"` 直接定位；本问题不判断当前旧库升级策略是否必要，只确认旧确认状态仍是默认门禁事实来源。
```

```text
编号：ATT-MZ-REVIEW-009
批次：07 插件参数与插件源码文本域
严重程度：P1
证据等级：E2
状态：已确认
问题：插件源码高风险门禁依赖调用方预先传入 plugin_source_scan；没有已导入插件源码规则时，正文翻译和文本索引重建路径不会加载插件源码，也不会扫描高风险源码候选，导致“高风险插件源码会暂停正文入口”的外部契约不是核心 workflow gate 自身的稳定事实。
证据：app/application/flow_gate.py 第 487-492 行的 _plugin_source_rule_gate_errors() 写着“高风险插件源码文本必须先确认并导入源码规则”，但当 scan is None 且 records 为空时直接返回 []；同函数第 506-514 行只有在已有 scan 后才根据 scan.risk.high_risk 产生 plugin_source_text_high_risk。app/application/handler.py 第 1100-1139 行的直接正文翻译分支调用 _load_session_game_data(session) 和 TextScopeService().build(...)，随后 assert_workflow_gate_passed(...) 未传 plugin_source_scan；app/application/handler.py 第 389-404 行的 translate --max-items 自动重建索引路径只有在已有 plugin_source_records 时才 include_plugin_source_files=bool(plugin_source_records)，构建 scope 也未传 plugin_source_scan；app/agent_toolkit/services/text_index.py 第 67-82 行的 rebuild-text-index 同样只在已有 plugin_source_records 时加载插件源码；app/text_scope/builder.py 第 63-70 行只有存在 plugin_source_rule_records 时才保留或构建 plugin_source_scan。tests/test_plugin_source_text.py 第 1248-1254 行验证高风险暂停时手动把 plugin_source_scan 传给 collect_workflow_gate_errors()，当前未看到直接 translate 或 rebuild-text-index 在无规则高风险源码下会触发 plugin_source_text_high_risk 的测试。docs/advanced-usage.md 第 170 行写“高风险时，translate、run-all 等正文入口会停止并要求用户确认”；skills/att-mz/references/plugin-source-text-agent-task.md 第 8 行写用户未确认时停止正文翻译；skills/att-mz/references/cli-command-contract.md 第 161 行写 scan-plugin-source-text 高风险时暂停正文翻译。
影响：同一插件源码高风险事实有两套入口：prepare/scan 场景下由显式 scan 发现并阻断，直接正文/索引入口在无规则时跳过扫描并继续；后续重构如果相信 workflow gate 已统一覆盖高风险插件源码，会漏掉未处理源码文本支线，造成玩家可见插件源码文本未进入翻译或排除审查。
根因线索：插件源码扫描是重型支线，当前为了避免默认读取源码，把扫描责任放到工作区准备或显式扫描命令；但外部契约同时要求正文入口在高风险时停止，核心门禁没有保存或计算该风险状态。
冲突的事实来源：app/application/flow_gate.py 的可选 plugin_source_scan；app/application/handler.py 的直接 translate 和 warm index 重建路径；app/agent_toolkit/services/text_index.py 的索引重建路径；Skill/docs 对高风险暂停正文入口的说明；tests/test_plugin_source_text.py 只覆盖显式传入 scan 的 gate 场景。
重复或旧路径对象：collect_workflow_gate_errors(plugin_source_scan=...) 调用方责任；_plugin_source_rule_gate_errors() 的 scan None 空返回；直接正文翻译未加载插件源码路径；rebuild-text-index 和 translate --max-items 无规则时不加载插件源码路径。
应删除或合并的对象：插件源码高风险状态只由调用方预扫描携带的临时事实；正文入口和索引入口各自决定是否加载插件源码的分散判断。
受影响外部契约：`translate`、`run-all`、`rebuild-text-index`、`translate --max-items` 的高风险插件源码前置检查；`plugin-source-risk-report.json` 与插件源码支线启动条件；Skill 对“高风险未处理时停止正文翻译”的流程约束。
验证方式或证据缺口：`rg -n "if scan is None and not records|plugin_source_text_high_risk|include_plugin_source_files=bool\\(plugin_source_records\\)|def _translate_text_in_session|plugin_source_scan=plugin_source_scan" app/application/flow_gate.py app/application/handler.py app/agent_toolkit/services/text_index.py app/text_scope/builder.py tests/test_plugin_source_text.py` 可定位；当前证据来自静态路径和测试覆盖形态，未另写新测试执行完整 CLI 复现。
```

```text
编号：ATT-MZ-REVIEW-012
批次：10 翻译、LLM 与 Prompt 隐私
严重程度：P1
证据等级：E2
状态：已确认
问题：正文翻译的 `--stop-on-error-rate` 外部契约写明“检查没通过的译文比例达到该值时停止本轮”，但当前调度只在错误消费者中抛出 TranslationRunInterrupted；外层 gather 使用 return_exceptions=True 并继续等待成功消费者和后台翻译 runner 结束，导致达到阈值后不会立即停止模型请求和剩余批次，停止参数没有真实参与调度中止。
证据：app/cli/parser.py 第 596 行把 `--stop-on-error-rate` 描述为“检查没通过的译文比例达到该值时停止本轮”，app/cli/runtime.py 第 137-148 行把该参数解析到 TranslationRunLimits.stop_on_error_rate。app/application/handler.py 第 1856-1878 行同时启动成功消费者和错误消费者，第 1881 行使用 `asyncio.gather(success_task, error_task, return_exceptions=True)`，第 1882-1885 行等待 gather 完成后才进入第 1892-1897 行 finally 停止后台翻译。第 1963-1989 行的 _consume_error_items() 在比例达到阈值时抛出 TranslationRunInterrupted，但该异常只作为 gather 的一个结果返回；第 1899-1914 行直到两个消费者都结束后才检查 runner_error。app/translation/text_translation.py 第 120-156 行的后台 runner 会继续 TaskGroup 和 worker，只有 runner 自身结束时才给 right_queue/error_queue 放入 None；错误消费者提前抛出后，成功消费者仍会等到 right_queue 收到 None 才结束。`rg -n "stop_on_error_rate|检查没通过的译文比例" tests app` 只找到 CLI/runtime/handler 相关实现，未看到覆盖达到阈值后后台模型请求提前停止的测试。
影响：大批量翻译中，如果模型持续产生质量错误，用户设置的停止阈值可能只在全部已排队批次执行结束后才反映到运行记录；这会增加模型调用成本、耗时和质量错误写入量，也遮住“运行限制参数必须定义、解析、校验、应用并真实参与调度”的当前模型。后续重构若相信 TranslationRunLimits 已经统一表达运行中止条件，会误判翻译调度和消费者队列的真实边界。
根因线索：运行限制状态由错误消费者判断，但后台翻译 runner、成功消费者和外层 gather 没有共享“达到阈值后停止本轮”的中止事实；return_exceptions=True 把中断异常延后成结果处理。
冲突的事实来源：CLI 帮助文本和 TranslationRunLimits.stop_on_error_rate 的“停止本轮”契约；_consume_error_items() 的局部比例判断；_run_text_translation_batches() 的 gather 等待语义；TextTranslation._run_translation() 的后台 worker 完成后才发送队列结束标记。
重复或旧路径对象：错误消费者内的 stop_on_error_rate 判断；外层 gather(return_exceptions=True) 的延后错误处理；后台 TextTranslation runner 独立完成全部任务后再结束队列的调度事实。
应删除或合并的对象：只存在于错误消费者局部的停止阈值事实；运行限制和后台翻译 runner 之间分离的中止状态。
受影响外部契约：`translate --stop-on-error-rate`、`run-all --stop-on-error-rate`、Agent JSON 报告中的 blocked_reason/success_count/quality_error_count/llm_failure_count、翻译运行记录的 stopped/blocked 语义和大规模翻译运行成本控制。
验证方式或证据缺口：`rg -n "stop_on_error_rate|检查没通过的译文比例|TranslationRunInterrupted|return_exceptions=True|iter_error_items|iter_right_items|await text_translation.stop" app/application/handler.py app/translation/text_translation.py app/cli/parser.py app/cli/runtime.py tests` 可定位；当前证据为静态调度路径审查和测试覆盖缺口，未执行带假 LLM 的完整早停复现。
```

```text
编号：ATT-MZ-REVIEW-013
批次：11 质量、覆盖、状态、反馈与手动修复
严重程度：P1
证据等级：E2
状态：已确认
问题：import-manual-translations 的质量修复快路径把最新运行的 translation_quality_errors 记录当作当前可导入文本范围；当输入路径全部命中最新 quality_error 时，它不重建或读取 text index，也不加载当前游戏数据确认该路径仍在当前可写范围，导致“当前 TextScope/text_index 是手动译文保存范围事实来源”的模型被质量错误历史记录分裂。
证据：app/agent_toolkit/services/manual_translation.py 第 149-152 行默认 scope_mode 为 `saved_quality_errors`，第 183-195 行只按输入 payload_paths 读取最新运行的 quality_error 记录，第 196-202 行在 payload_paths 全部属于 latest_quality_error_paths 时启用快路径；第 203-217 行把 translated_items 或 latest_quality_errors_by_path 构造成 active_items，第 219-259 行的 text_index 重建与 read_text_index_items_by_paths 只在不能使用快路径时执行；第 281-287 行随后只按该 active_items 执行译文校验，第 321-323 行直接 write_translation_items 并按路径删除质量错误。app/persistence/translation_records.py 第 30-48 行和 app/persistence/sql.py 第 450-455 行显示写译文表是按 location_path INSERT OR REPLACE，不要求当前 text_index 命中；rust/src/native_core/write_back_plan/repository.rs 第 82-120 行只会在写回阶段报“已保存译文不在当前可写文本范围内”。tests/test_agent_toolkit.py 第 5991-6102 行的 test_manual_quality_fix_import_uses_saved_item_fast_path 明确要求质量修复快路径不加载完整游戏数据、不读取全部质量错误，并断言 scope_mode 为 saved_quality_errors；同一测试第 6046-6055 行还写入 `Map999.json/ghost` 这类不在当前 fixture 范围内的 quality_error 记录，说明质量错误表本身不保证当前范围有效。
影响：旧修复表、手工构造输入或规则/源文件变化后的 quality_error 记录可以把不属于当前范围的 location_path 写入主译文表；后续 quality-report 或 Rust 写回 gate 可能再以 stale_saved_translations 拦住写回，但数据库已经保存了当前 TextScope 之外的译文记录。后续重构若把手动导入、质量修复、文本索引和写回 gate 视作同一当前范围模型，会被 saved_quality_errors 快路径和 text_index 路径两套事实来源遮住。
根因线索：为了让小规模质量修复不加载完整游戏数据，质量错误表被复用为当前条目的来源；该表保存的是某次翻译运行的失败结果，而不是当前文本范围索引或当前可写范围。
冲突的事实来源：manual_translation.py 的 saved_quality_errors 快路径；manual_translation.py 的 text_index 路径；translation_quality_errors 表的历史运行记录；text_index_items/current TextScope 的当前范围事实；Rust 写回计划的 allowed_translation_paths 检查。
重复或旧路径对象：scope_mode=`saved_quality_errors`；latest_quality_errors_by_path 构造 active_items；scope_mode=`text_index` 的 detect_text_index_invalidations/read_text_index_items_by_paths；tests/test_agent_toolkit.py::test_manual_quality_fix_import_uses_saved_item_fast_path。
应删除或合并的对象：质量错误历史记录作为手动译文保存范围事实的快路径；手动导入中 saved_quality_errors 和 text_index 并列决定 active_items 的双事实来源。
受影响外部契约：`import-manual-translations`、质量修复表导入、translation_quality_errors 表语义、手动译文保存范围、write-back 前 stale_saved_translations 门禁。
验证方式或证据缺口：`rg -n "saved_quality_errors|latest_quality_errors_by_path|detect_text_index_invalidations|read_text_index_items_by_paths|write_translation_items|delete_translation_quality_errors_by_paths|test_manual_quality_fix_import_uses_saved_item_fast_path" app/agent_toolkit/services/manual_translation.py tests/test_agent_toolkit.py app/persistence/translation_records.py app/persistence/sql.py rust/src/native_core/write_back_plan/repository.rs` 可定位；当前证据为静态路径和测试约束，未执行手工输入 ghost quality_error 的完整复现。
```

```text
编号：ATT-MZ-REVIEW-015
批次：12 写入门槛、写回计划与文件安全
严重程度：P1
证据等级：E2
状态：已确认
问题：写后当前运行文件审计失败时，data/plugins 计划文件已经完成替换，插件源码运行映射也已经保存到数据库，但命令随后以 WriteBackGateError 失败；文件替换事务只覆盖替换循环内部失败，不覆盖写后审计失败，导致“命令失败”和“游戏目录及诊断映射已经改变”同时成立。
证据：app/application/handler.py 第 1465 行先调用 write_planned_text_file_sources() 替换 Rust 计划文件，第 1474-1475 行进入“保存写入诊断映射”并调用 session.replace_plugin_source_runtime_write_maps()，第 1480 行才开始“审计写入后的当前运行文件”，第 1574 行和第 1591 行在插件源码或非标准 data 审计失败时抛出“写入后当前运行文件审计未通过”。app/application/file_writer.py 第 64-103 行 replace_write_operations_transactionally() 的 rollback 只保存并恢复 replaced_targets，finally 清理 rollback_dir，不覆盖 handler 后续的诊断映射保存或写后审计失败。tests/test_rmmz_loader_extraction_writeback.py 第 619 行的 test_native_write_back_helper_saves_runtime_map_before_post_write_audit 明确覆盖该顺序，第 676-681 行记录文件替换已经发生，第 742 行期望写后审计失败抛错，第 766 行断言事件顺序是 write、load、audit，第 768 行和第 770 行断言 runtime_map 与 scan_cache 已保存。skills/att-mz/SKILL.md 第 65、85 行把“写入后当前运行文件验收通过”写成写进游戏文件阶段成功条件，skills/att-mz/references/cli-command-contract.md 第 149 行描述 write-back/rebuild 成功前提，docs/advanced-usage.md 第 313、329 行要求质量和覆盖通过后再写回、rebuild 不能绕过相同检查。
影响：用户或 Agent 看到命令失败时，可能按“写文件阶段未成功”理解并继续修复，但游戏目录已经写入一批新文件，运行映射和扫描缓存也可能已经更新；后续 audit-active-runtime、verify-feedback-text 或诊断流程会基于失败写入后的当前运行文件工作。若失败原因来自写后审计发现 JS 语法错误、坏控制符或非标准 data 残留，当前实现没有把文件恢复到写前状态，也没有在外部契约中说明这是有意保留的失败后状态。
根因线索：写文件事务、诊断映射保存和写后审计处于三个相邻阶段，但事务边界只在 file_writer.replace_write_operations_transactionally() 内部；写后审计被建模为成功前的硬门槛，同时又在测试中要求审计失败前保留诊断映射以便反推。
冲突的事实来源：file_writer 的“任一失败时恢复已替换文件”事务语义；handler 的写后审计硬门槛；plugin_source_runtime_write_map 和 runtime scan cache 的失败前诊断语义；Skill/CLI 文档对写入成功需要写后验收通过的描述。
重复或旧路径对象：app/application/file_writer.py::replace_write_operations_transactionally；app/application/handler.py::write_runtime_files_with_native_plan；plugin_source_runtime_write_map 表；plugin_source_runtime_scan_cache 表；tests/test_rmmz_loader_extraction_writeback.py::test_native_write_back_helper_saves_runtime_map_before_post_write_audit。
应删除或合并的对象：写文件替换事务、写后审计失败处理、运行映射保存时机三处对失败后状态的分散定义。
受影响外部契约：`write-back`、`rebuild-active-runtime`、`write-terminology`、`run-all` 最终写回阶段；写后 active runtime 审计；plugin_source_runtime_write_map 诊断映射；失败后游戏目录状态。
验证方式或证据缺口：`rg -n "write_planned_text_file_sources|保存写入诊断映射|replace_plugin_source_runtime_write_maps|审计写入后的当前运行文件|写入后当前运行文件审计未通过|replace_write_operations_transactionally|test_native_write_back_helper_saves_runtime_map_before_post_write_audit|events.append|assert events ==" app/application/handler.py app/application/file_writer.py tests/test_rmmz_loader_extraction_writeback.py` 可定位；当前证据为静态顺序和测试断言，未执行真实游戏目录上构造写后审计失败后的文件 diff。
```

```text
编号：ATT-MZ-REVIEW-016
批次：13 持久化与 DB schema
严重程度：P1
证据等级：E2
状态：已确认
问题：规则导入中“备份并清理不再属于当前规则范围的已保存译文、替换规则、清理插件源码运行映射、更新规则审查状态”不是一个数据库事务；多个 persistence 方法内部各自 commit，导致后续规则替换或审查状态写入失败时，前面已经提交的译文删除无法随命令失败回滚。
证据：app/application/handler.py 第 491-501 行插件规则导入先生成备份并 delete_translation_items_by_prefixes()，第 501-508 行才 replace_plugin_text_rules() 并更新 PLUGIN_TEXT_RULE_DOMAIN 审查状态；第 659-675 行事件指令规则导入同样先删译文再 replace_event_command_text_rules() 和更新审查状态；第 746-758 行 Note 标签规则导入先 delete_translation_items_by_paths()，再 replace_note_tag_text_rules() 和更新审查状态。app/agent_toolkit/services/rule_validation.py 第 390-395 行 Agent Note 规则导入同样先删除译文再替换规则/审查状态，第 730-736 行插件源码规则导入先删除译文，再 replace_plugin_source_text_rules()、clear_plugin_source_runtime_write_maps() 和更新审查状态。app/persistence/translation_records.py 第 106-116、139-159 行删除译文方法内部 commit；app/persistence/rule_records.py 第 108、165、272、334、513、518 行各规则替换/审查状态方法内部 commit；app/persistence/plugin_source_runtime_records.py 第 88 行 clear_plugin_source_runtime_write_maps() 也独立 commit。app/cli/commands/rules.py 第 59-62 行和第 130-133 行导入异常报告只返回 game/input，不包含已清理译文或备份路径；app/agent_toolkit/services/rule_validation.py 第 405-411、743-752 行异常分支把 deleted_translation_items 和 deleted_translation_backup_path 固定返回 0/空字符串。
影响：如果规则导入在已提交删除译文后因为 SQLite 写入失败、唯一约束、连接异常或后续审查状态写入失败而中断，命令会以导入失败形式结束，但数据库里的部分已保存译文已经消失，规则和审查状态可能仍是旧值或半更新状态；CLI/Agent 失败报告又可能不提示本次已经清理过译文和备份位置。后续重构若把“规则导入成功后才清理失效译文”作为单一事实，会被这些已提交局部副作用遮住。
根因线索：persistence mixin 把每个表组操作做成自提交方法，业务层再串联多个方法表达一次规则导入；没有命令级 DB 事务包住跨表状态变化，也没有失败报告携带已发生的局部提交状态。
冲突的事实来源：规则导入业务流程的成功/失败报告；translation_items 表中已提交的清理结果；plugin/event/note/plugin-source 规则表；rule_review_states；plugin_source_runtime_write_map；备份文件路径和报告 warning。
重复或旧路径对象：app/application/handler.py::import_plugin_rules；app/application/handler.py::import_event_command_rules；app/application/handler.py::import_note_tag_rules；app/agent_toolkit/services/rule_validation.py::import_note_tag_rules；app/agent_toolkit/services/rule_validation.py::import_plugin_source_rules；TranslationRecordSessionMixin 删除方法内部 commit；RuleRecordSessionMixin 替换/审查状态方法内部 commit；PluginSourceRuntimeRecordSessionMixin.clear_plugin_source_runtime_write_maps。
应删除或合并的对象：规则导入跨表状态变化由多个自提交 persistence 方法分散定义的事务边界；失败报告中“没有删除译文”和数据库已经删除译文之间的状态分裂。
受影响外部契约：`import-plugin-rules`、`import-event-command-rules`、`import-note-tag-rules`、`import-plugin-source-rules`；规则导入 JSON 报告的 deleted_translation_items/deleted_translation_backup_path；备份恢复流程；规则审查状态和已保存译文表的一致性。
验证方式或证据缺口：`rg -n "deleted_translation_items = await session\\.delete_translation_items|replace_.*rules|clear_plugin_source_runtime_write_maps|delete_rule_review_state|replace_rule_review_state|await self\\.connection\\.commit\\(\\)|deleted_translation_items\\\": 0|deleted_translation_backup_path\\\": \\\"\\\"" app/application/handler.py app/agent_toolkit/services/rule_validation.py app/persistence app/cli/commands/rules.py tests` 可定位；当前证据为静态事务边界和测试覆盖缺口，未用 monkeypatch 注入“删除后规则替换失败”的完整复现。
```

```text
编号：ATT-MZ-REVIEW-017
批次：14 Rust 原生核心与 Python adapter
严重程度：P1
证据等级：E2
状态：已确认
问题：JavaScript AST native adapter 没有校验 app._native 的 native contract version；质量、写回和正则 adapter 都会拒绝缺少契约函数或契约版本过旧的 Rust 扩展，但 AST adapter 只检查 parse_javascript_string_spans 是否存在，导致同一个 Rust/Python 原生契约在 AST 热路径上不是统一硬门槛。
证据：app/native_javascript_ast.py 第 14-23 行的 NativeJavaScriptAstModule Protocol 只声明 parse_javascript_string_spans 和 parse_javascript_string_spans_batch，不声明 native_contract_version；第 134-139 行 _load_native_javascript_ast_module() 直接 import app._native，只在缺少 parse_javascript_string_spans 时报错，未调用 ensure_native_contract_version()。对比 app/native_quality.py 第 243-250 行、app/native_write_plan.py 第 169-175 行和 app/regex_contract.py 第 265-271 行，三个 adapter 都在加载 app._native 后调用 ensure_native_contract_version()。tests/test_native_adapters.py 第 105-114 行定义缺少契约函数和旧契约版本的 fake module，第 138-146 行覆盖 native_quality 拒绝旧扩展，第 149-168 行覆盖 native_write_plan 拒绝旧扩展；tests/test_regex_contract.py 第 54-62 行覆盖 regex contract 拒绝旧扩展；tests/test_native_adapters.py 第 49-66 行的 _FakeJavaScriptAstModule 不提供 native_contract_version，第 400、428 行之后的 AST adapter 测试通过 monkeypatch _load_native_javascript_ast_module() 只覆盖返回 payload 字段解析，未覆盖旧 native contract 拒绝。rust/src/lib.rs 第 9-13 行定义并暴露 NATIVE_CONTRACT_VERSION=2/native_contract_version()，第 75-91 行暴露 parse_javascript_string_spans 和 parse_javascript_string_spans_batch。
影响：如果本地或发行环境残留旧版 app._native，只要旧扩展已经包含 JS AST 解析入口，插件源码扫描和写回计划中依赖 AST span/context 的路径可能继续运行，而不会像质量、写回和正则入口一样显式报“Rust 原生扩展版本过旧”；后续破坏性重构若调整 AST payload、ast_context 字段或 parser 语义，会被一个未纳入契约版本硬门槛的 native 热路径遮住。
根因线索：native contract version 已集中在 app/native_contract.py 与 Rust lib.rs，但 JavaScript AST adapter 是独立加载函数，历史上只按入口函数存在性判断扩展是否可用，没有同步接入统一契约校验和 stale native 测试。
冲突的事实来源：app/native_contract.py 的统一 native contract version；app/native_quality.py、app/native_write_plan.py、app/regex_contract.py 的加载校验；app/native_javascript_ast.py 的入口存在性校验；tests/test_native_adapters.py 对 quality/write_plan 旧扩展拒绝和 AST payload 解析的分离覆盖。
重复或旧路径对象：app/native_javascript_ast.py::_load_native_javascript_ast_module；NativeJavaScriptAstModule Protocol 中缺失 native_contract_version；tests/test_native_adapters.py::_FakeJavaScriptAstModule；AST adapter 测试未覆盖 stale native contract。
应删除或合并的对象：AST adapter 独立于 native_contract.py 的入口存在性契约；native adapter stale contract 测试只覆盖 quality/write_plan/regex 而遗漏 AST 的测试边界。
受影响外部契约：插件源码扫描、插件源码规则导入、文本范围构建中依赖 Rust JS AST 的路径；发行包 app._native 与 Python adapter 的版本一致性；native contract version 对所有 Rust 热路径的统一硬门槛。
验证方式或证据缺口：`rg -n "stale_native_contract|native_contract|ensure_native_contract_version|parse_javascript_string_spans|_load_native_javascript_ast_module|MissingNative|OldNative|native_write_plan_rejects|native_quality_rejects|regex_contract" tests/test_native_adapters.py tests/test_regex_contract.py app/native_javascript_ast.py app/native_quality.py app/native_write_plan.py app/regex_contract.py` 可定位；当前证据为静态 adapter 对比和测试覆盖缺口，未构造旧 app._native 二进制执行完整插件源码扫描复现。
```

```text
编号：ATT-MZ-REVIEW-022
批次：18 补充漏检复查
严重程度：P1
证据等级：E2
状态：已确认
问题：prepare-agent-workspace 复用已有输出目录时不会清空旧工作区文件，但 validate-agent-workspace 会按固定路径是否存在来决定是否启用插件源码和非标准 data 支线，而不是只信任本轮 manifest；旧的 plugin-source-rules.json、nonstandard-data-rules.json 或 nonstandard-data 目录可能在下一次低风险工作区中重新参与当前验收。
证据：app/agent_toolkit/services/workspace.py 第 208-209 行把 output_dir resolve 后直接 mkdir(parents=True, exist_ok=True)，未删除已有目录内容；第 302-308 行只在 plugin_source_extension_active 时写入 plugin-source-rules.json，第 309-330 行只在 nonstandard_data_extension_active 时导出 nonstandard-data 目录和 nonstandard-data-rules.json；第 441-468 行本轮 manifest.files 只追加本轮实际生成的可选文件。validate_agent_workspace 第 517-528 行固定拼出 plugin-source-rules.json、nonstandard-data-rules.json、nonstandard-data-risk-report.json 等路径并读取 manifest；第 540-548 行用 `plugin_source_rules_path.exists()`、`nonstandard_data_rules_path.exists()`、已保存规则或 manifest 高风险标记决定是否执行重扫描；第 673-723 行只要 plugin-source-rules.json 存在就校验插件源码规则，第 735-764 行只要 nonstandard_data_scan 存在且 nonstandard-data-rules.json 存在就解析非标准 data 规则。cleanup_agent_workspace 第 945-964 行只按 manifest.files 删除本轮清单里的路径，第 953-958 行还会跳过非字符串或工作区外路径，意味着新 manifest 未列出的旧可选文件不会被自动清理。skills/att-mz/references/workspace-schema.md 第 23 行和第 27 行说明 plugin-source-rules.json、nonstandard-data-rules.json 只在高风险或支线已有规则时生成；skills/att-mz/references/cli-command-contract.md 第 71 行把 prepare-agent-workspace 描述为导出候选文件、规则草稿和已保存规则，第 72 行把 validate-agent-workspace 描述为总体验收工作区和规则覆盖；tests/test_agent_toolkit.py 第 4276-4311 行只断言低风险新工作区中可选规则文件不存在、验收跳过重支线扫描，没有覆盖同一 output_dir 先高风险后低风险复用时旧文件残留。
影响：外部 Agent 或用户复用同一个 `<工作区>` 目录重新执行 prepare-agent-workspace 时，旧可选规则文件可以让 validate-agent-workspace 把“本轮没有生成、manifest 也未列出”的支线文件当作当前输入。轻则低风险项目被旧插件源码/非标准 data 规则误阻塞，重则旧规则与当前游戏状态混合进入验收报告，让工作区 JSON 从“本轮生成的交换边界”变成“目录里碰巧存在的文件集合”。
根因线索：prepare 阶段的事实来源是本轮生成清单和 manifest，validate 阶段的事实来源是固定文件存在性加 manifest.generated 高风险标记，cleanup 阶段又只按 manifest.files 清理；三者对“哪些工作区文件属于当前任务”的定义不一致。
冲突的事实来源：prepare_agent_workspace 生成的 manifest.files；validate_agent_workspace 的固定路径 exists() 分支；cleanup_agent_workspace 的 manifest.files 清理清单；Skill/workspace-schema 对可选支线文件只在高风险或已启动时生成的描述；tests 对全新低风险工作区的断言。
重复或旧路径对象：旧 workspace/plugin-source-rules.json；旧 workspace/nonstandard-data-rules.json；旧 workspace/nonstandard-data/；validate_agent_workspace 中 plugin_source_rules_path.exists() 与 nonstandard_data_rules_path.exists()；cleanup_agent_workspace 只删除 manifest.files 的清理模型。
应删除或合并的对象：本轮 manifest 与目录固定文件存在性并行决定工作区当前输入的双事实来源；复用工作区时不会退出当前任务的旧可选支线文件。
受影响外部契约：prepare-agent-workspace、validate-agent-workspace、cleanup-agent-workspace；工作区 JSON 作为外部协作交换边界；插件源码和非标准 data 支线只在高风险或支线已启动时参与的流程契约。
验证方式或证据缺口：`rg -n "prepare_agent_workspace|cleanup_agent_workspace|validate_agent_workspace|plugin-source-rules|nonstandard-data-rules|stale|reuse|existing|output_dir|manifest.files|工作区.*旧|工作区.*复用|清理" tests/test_agent_toolkit.py tests/test_cli_json_output.py app/agent_toolkit/services/workspace.py skills/att-mz/references/workspace-schema.md docs/advanced-usage.md docs/development/agent-toolkit.md` 可定位；当前证据为静态路径和测试覆盖缺口，未构造先高风险后低风险复用同一工作区的完整复现。
```

### P2 问题

此处记录明显增加维护成本、性能风险、测试脆弱性或文档漂移的问题。

```text
编号：ATT-MZ-REVIEW-001
批次：01 长期指令与文档边界
严重程度：P2
证据等级：E1
状态：已确认
问题：docs/development/review-records 下的历史 review 文档仍保留真实本机路径、用户名、临时工作目录和具体样本游戏名，违反文档示例脱敏边界，也会让后续审查把私有样本和本机目录误读为当前项目可用事实。
证据：AGENTS.md 第 63 行要求涉及 Skill、README、docs 或发布说明的测试只校验机器可观察边界并禁止敏感实现细节，AGENTS.md 第 62 行要求测试不依赖开发机私有 setting.toml 或默认配置路径，docs/development/README.md 第 47 行要求发行包用户文档和 Skill 只使用抽象占位符、不暴露本机路径、测试夹具或内部数据库细节；docs/development/review-records/rust-migration-review-final-report.md 记录 `<样本根目录>` 与 `<样本游戏目录>`；docs/development/review-records/rust-migration-review-findings-batch-01.md 记录 `<样本游戏目录>` 与 `<系统临时工作目录>`；docs/development/review-records/rust-migration-review-closure-matrix.md 记录 `<样本游戏>` 与 `data/db/<样本游戏>.db`。
影响：文档脱敏规则和历史 review 记录之间形成冲突；后续 AI 或维护者读取 docs 时可能把私有样本路径、临时工作目录、具体样本数据库名当成可复用验证入口或当前发行/测试契约，增加重构前证据收束成本。
根因线索：阶段性 review 记录作为 docs/development 导航的一部分保留，但没有和当前公开文档的脱敏边界隔离。
冲突的事实来源：AGENTS.md 的示例脱敏与文档边界要求；docs/development/README.md 的抽象占位符要求；docs/development/review-records 的真实路径和样本记录。
重复或旧路径对象：docs/development/review-records/rust-migration-review-final-report.md；docs/development/review-records/rust-migration-review-findings-batch-01.md；docs/development/review-records/rust-migration-review-closure-matrix.md；docs/development/review-records/rust-migration-review-fix-progress.md。
应删除或合并的对象：上述 review 记录中的真实本机绝对路径、用户名、临时工作目录、具体样本游戏名和具体样本数据库名片段。
受影响外部契约：文档脱敏边界；发行包用户文档和 Skill 的抽象占位符边界；后续 review 使用 docs 作为证据时的可信输入边界。
验证方式或证据缺口：`rg -n "<私有路径关键词>|<用户名关键词>|<样本名关键词>" README.md docs skills` 直接命中上述文件；本问题不涉及运行时代码验证。
```

```text
编号：ATT-MZ-REVIEW-002
批次：01 长期指令与文档边界
严重程度：P2
证据等级：E2
状态：已确认
问题：docs/feedback-iteration-repair-plan.md 以“修复建议”文档形式继续保留 P0/P1/P2、推荐实现顺序、测试建议和当前约束，同时其中的反馈反查和 Skill 更新内容已经在 Skill references 与 CLI 契约中落地，形成 docs 与 Skill/CLI 对同一反馈流程的重复事实来源。
证据：docs/feedback-iteration-repair-plan.md 第 78、101、119、130、142、167、177、199、221 行以 P0/P1/P2 标题描述流程能力和后续要求，第 221-226 行写 `skills/att-mz/SKILL.md` 和发行版 Skill 都应更新试玩反馈流程，第 230-236 行给出推荐实现顺序，第 239 行进入测试建议，第 298 行写修复完成后的验收标准，第 307 行写当前约束；但 skills/att-mz/references/feedback-iteration.md 第 30-47 行已经要求 `verify-feedback-text` 反查和闭环，skills/att-mz-release/references/feedback-iteration.md 第 30-47 行也有对应发行版命令；skills/att-mz/references/cli-command-contract.md 第 160-161 行和 skills/att-mz-release/references/cli-command-contract.md 第 160-161 行已经记录 `verify-feedback-text` 与 `scan-plugin-source-text` 的命令契约；app/cli/parser.py 第 251-259 行注册了两个命令。
影响：同一反馈迭代流程同时由 docs 修复计划、开发版 Skill、发行版 Skill、CLI 契约和 CLI parser 描述；重构前审查必须额外判断哪个文档是当前事实，哪个只是历史计划，增加文档漂移和外部 Agent 契约误读风险。
根因线索：已落地的流程计划没有从当前 docs 入口中退出，计划文档继续使用“当前约束”和“应更新 Skill”等措辞。
冲突的事实来源：docs/feedback-iteration-repair-plan.md；skills/att-mz/references/feedback-iteration.md；skills/att-mz-release/references/feedback-iteration.md；skills/*/references/cli-command-contract.md；app/cli/parser.py。
重复或旧路径对象：docs/feedback-iteration-repair-plan.md 中的反馈反查、插件源码扫描、Skill 更新、推荐实现顺序、测试建议和当前约束段落。
应删除或合并的对象：docs/feedback-iteration-repair-plan.md 中已经由 Skill references、CLI 契约和 parser 承担的反馈流程事实描述。
受影响外部契约：试玩反馈流程 Skill 契约；CLI `verify-feedback-text` 和 `scan-plugin-source-text` 命令说明；docs 不能覆盖 Skill 的文档边界。
验证方式或证据缺口：通过 `rg -n "verify-feedback-text|scan-plugin-source-text|feedback-iteration|反馈原文清单|真实文件反查" skills docs README.md tests app` 交叉确认 docs、Skill、CLI parser 同时描述该流程；本问题不判断实现正确性，后续批次 11/15/16 继续验证质量、Skill 同步和测试覆盖。
```

```text
编号：ATT-MZ-REVIEW-004
批次：02 CLI 入口与 JSON 报告
严重程度：P2
证据等级：E2
状态：历史发现，阶段 1 已收束
问题：阶段 1 前，开发文档、发布文档和 reviewplan 都把 `tests/test_skill_protocol.py` 当成 Skill/CLI 协议一致性的测试入口，但当时 tests 目录没有该文件；Skill references 与 parser 的命令示例对齐只能靠 review 临时脚本证明，不是项目测试套件里的稳定保护。
证据：阶段 1 前，docs/development/agent-toolkit.md 第 47 行写 `tests/test_skill_protocol.py` 覆盖 Skill 与 CLI 协议关键一致性；docs/development/release-and-tests.md 第 90 行要求改到 Skill、README、提示词或工作区协议时同步检查 `tests/test_skill_protocol.py`；docs/超重型破坏性重构/reviewplan.md 第 339-340、433-434、746-747、779 行把 `tests/test_skill_protocol.py` 列为批次主读文件或测试子批；当时 `rg --files tests` 未列出该文件；临时命令示例对照脚本输出 `parser_commands=57 command_refs=110 unknown_refs=[]`，但该检查不在测试套件中。
影响：该缺口已由阶段 1 的协议测试收束；本段仅作为历史发现保留，不再描述当前测试入口状态。
根因线索：文档中保留了已删除或未迁移的测试入口名称，现有测试套件只覆盖 CLI parser/dispatch 和部分 JSON 字段，不覆盖 Skill markdown 命令示例到 parser 的完整关系。
冲突的事实来源：docs/development/agent-toolkit.md；docs/development/release-and-tests.md；docs/超重型破坏性重构/reviewplan.md；当前 tests 文件列表；临时命令示例对照脚本结果。
重复或旧路径对象：文档中的 `tests/test_skill_protocol.py` 测试入口；本批临时命令示例对照脚本。
应删除或合并的对象：指向不存在 `tests/test_skill_protocol.py` 的测试入口描述；Skill/CLI 命令示例一致性检查的临时脚本形态。
受影响外部契约：开发版 Skill、发行版 Skill、README/docs 命令示例与 CLI parser 的一致性测试边界。
验证方式或证据缺口：`rg --files tests` 与 `Path('tests/test_skill_protocol.py').exists()` 直接确认文件缺失；临时脚本只证明当前没有未知命令示例，不证明未来变更会被测试阻止。
```

```text
编号：ATT-MZ-REVIEW-005
批次：03 配置、运行目录与日志
严重程度：P2
证据等级：E2
状态：历史发现，阶段 1 已收束
问题：阶段 1 前，模型服务配置的环境变量外部契约仍使用旧项目前缀，测试和 benchmark 已固定旧名字，但 README、Skill 和高级用法文档只泛称“环境变量”或只具体说明 `ATT_MZ_RUST_THREADS`，导致当时项目配置契约没有统一公开事实来源。
证据：阶段 1 前，app/config/environment.py、tests/test_config_overrides.py、scripts/benchmark_small_tasks.py 和 tests/test_benchmark_small_tasks.py 共同固定旧项目前缀的模型服务环境变量；docs/advanced-usage.md 只写“也可以用环境变量覆盖敏感配置”，README.md 只要求编辑 `setting.toml`，skills/att-mz/references/cli-command-contract.md 只具体说明 `ATT_MZ_RUST_THREADS`。
影响：该缺口已由阶段 1 的当前命名、旧前缀拒绝测试和公开说明收束；本段仅作为历史发现保留，不再描述当前配置契约。
根因线索：模型环境变量沿用了旧项目命名，代码常量集中但公开契约没有同步给出具体变量名。
冲突的事实来源：阶段 1 前的环境变量常量、测试断言、benchmark 子进程环境注入和公开配置说明。
重复或旧路径对象：旧项目前缀的模型服务环境变量契约；docs/advanced-usage.md 中未列名的“环境变量覆盖敏感配置”说明；tests/test_benchmark_small_tasks.py 中对旧前缀字符串的直接断言。
应删除或合并的对象：旧项目前缀的模型服务环境变量契约；公开文档中未列出具体变量名的环境变量说明；测试中绕过配置常量的旧前缀字符串断言。
受影响外部契约：配置字段、环境变量和 `setting.example.toml`；benchmark 子进程模型连接覆盖；开发版 Skill 的配置补救说明。
验证方式或证据缺口：`Select-String -Path app/config/environment.py,tests/test_config_overrides.py,scripts/benchmark_small_tasks.py,tests/test_benchmark_small_tasks.py,docs/advanced-usage.md,skills/att-mz/references/cli-command-contract.md,README.md -Pattern "RPG_MAKER_TOOLS|环境变量|ATT_MZ_RUST_THREADS|setting.toml|LLM_BASE_URL_ENV_NAME|LLM_API_KEY_ENV_NAME"` 直接确认代码、测试、脚本和公开说明之间的口径差异；本问题不判断当前环境变量覆盖功能失效。
```

```text
编号：ATT-MZ-REVIEW-006
批次：04 注册、可信源快照与 RMMZ 数据层
严重程度：P2
证据等级：E2
状态：已确认
问题：当前注册模型要求 add-game 从干净游戏目录创建可信源快照和数据库 manifest，但兼容 loader 与测试写文件辅助仍保留“未注册游戏首次磁盘写回时自动生成 data_origin/plugins_origin 快照”的旧模型，测试层继续把当前运行文件作为缺快照时的源文入口。
证据：app/persistence/repository.py 第 554-634 行的 register_game() 在新库路径调用 create_source_snapshot_for_clean_game()、写入 source_snapshot_files，并在既有库路径读取和 validate_source_snapshot_manifest()，app/application/handler.py 第 324-344 行的 _load_session_game_data() 固定 source_view=GameFileView.TRANSLATION_SOURCE 并要求 session.read_source_snapshot_records() 非空；但 app/rmmz/loader.py 第 55-67 行的 load_game_data() 标注“兼容完整游戏数据”，以 use_origin_backups=True 且 require_origin_backups=False 调用底层加载，缺少 data_origin 时会回退激活 data；tests/_native_write_plan_helper.py 第 114-124、156、364-381 行的测试专用写文件入口每次调用 _ensure_source_snapshot()，缺少快照时直接从当前运行 data、plugins.js、js/plugins 复制生成；tests/test_rmmz_loader_extraction_writeback.py 第 3571-3595 行的 test_first_write_back_archives_complete_original_data_snapshot 明确断言“首次磁盘回写会准备完整可信源快照”，第 3613-3671 行继续用 load_game_data()/write_game_files() 验证后续写回不修改该测试生成的快照。
影响：重构前的当前模型是“注册创建可信源快照，业务会话只读翻译源视图并校验 manifest”；测试和兼容 loader 仍维护“写回时可从当前运行文件补建可信源”的旧路径，会让 RMMZ 数据层、写回测试和 Rust 计划测试对源文事实来源形成两套入口，增加删除旧写回路径和调整测试夹具时的判断成本。
根因线索：历史写回测试辅助在引入注册快照 manifest 后继续承担直接磁盘写回和快照补建职责，load_game_data() 作为兼容入口保留了缺快照回退激活文件的语义。
冲突的事实来源：app/persistence/repository.py 的 add-game 快照创建与 manifest 记录；app/application/handler.py 的会话加载 manifest 校验；app/rmmz/loader.py 的兼容 load_game_data()；tests/_native_write_plan_helper.py 的 _ensure_source_snapshot()；tests/test_rmmz_loader_extraction_writeback.py 的首次写回快照测试。
重复或旧路径对象：app/rmmz/loader.py::load_game_data；tests/_native_write_plan_helper.py::write_game_files；tests/_native_write_plan_helper.py::_ensure_source_snapshot；tests/test_rmmz_loader_extraction_writeback.py::test_first_write_back_archives_complete_original_data_snapshot；tests/test_rmmz_loader_extraction_writeback.py::test_written_game_reads_complete_origin_without_mutating_snapshot。
应删除或合并的对象：缺少可信源快照时回退当前运行文件的兼容加载入口；测试辅助中从当前运行文件自动补建可信源快照的路径；首次磁盘写回创建快照的旧测试模型。
受影响外部契约：可信源快照事实来源边界；RMMZ 游戏数据加载视图；写回测试对未注册游戏目录的隐含入口。
验证方式或证据缺口：`Select-String -Path app/rmmz/loader.py,tests/test_rmmz_loader_extraction_writeback.py,tests/_native_write_plan_helper.py -Pattern "load_game_data\\(|require_origin_backups=False|兼容完整游戏数据|业务服务层必须使用显式视图入口|首次磁盘回写|_ensure_source_snapshot|create_source_snapshot_for_clean_game|write_game_files\\("` 直接定位旧模型；`rg -n "load_game_data\\(" app tests` 显示该兼容入口主要由测试调用，当前未确认 CLI 主路径直接使用。
```

```text
编号：ATT-MZ-REVIEW-011
批次：09 TextScope 与 warm index
严重程度：P2
证据等级：E2
状态：已确认
问题：Agent 质量报告的 warm index 自动重建会用本次 setting_overrides 判断索引过期，却调用不接收覆盖参数的 rebuild_text_index() 写回索引；重建后的索引元信息仍来自基础配置，随后报告直接使用该索引，不再复核它是否匹配本次覆盖后的文本规则。
证据：app/agent_toolkit/services/quality.py 第 1414-1431 行的 quality_report() 接收 setting_overrides，并用 load_setting(..., overrides=setting_overrides) 构造本次 setting；第 1455-1458 行用覆盖后的 text_rules 调用 detect_text_index_invalidations()；第 1481-1484 行自动重建时调用 self.rebuild_text_index(game_title=game_title, callbacks=...)，没有传递 setting_overrides；第 1506-1514 行随即调用 _quality_report_from_text_index() 并把 text_index_status 标为 cold_rebuilt 或 stale_rebuilt。app/agent_toolkit/services/text_index.py 第 28-36 行的 rebuild_text_index() 签名只有 game_title 和 callbacks，第 56 行 load_setting(self.setting_path, source_language=session.source_language) 不接收覆盖参数，第 62-66 行据此生成 text_rules。app/text_index.py 第 63-83 行把传入 text_rules 的 rules_fingerprint 和 workflow_gate_scope_hashes 保存为索引元信息，第 87-124 行的 detect_text_index_invalidations() 又用当前 text_rules 与元信息比对。app/config/overrides.py 第 25-32、130-158 行显示覆盖参数可以改 strip/preserve 标点、long_text_line_width_limit、line_width_count_pattern、source_text_required_pattern 等 text_rules 字段；app/rmmz/text_rules.py 第 155 行和 app/rmmz/extraction.py 第 371 行用 source_text_required_pattern 判断文本是否进入提取/翻译范围。tests/test_agent_toolkit.py 第 7197-7245 行只覆盖 source_residual_allowed_chars 对质量结果生效，未断言自动重建后的 text_index_status、rules_fingerprint 或提取范围是否与覆盖参数一致。
影响：当调用者通过 Agent 服务 API 传入会影响 text_rules 的覆盖参数时，quality_report 可以先判定旧索引过期，再写入仍基于基础配置的索引，最后用该索引生成本次报告；这会让当前文本范围、索引元信息和报告质量规则三者分裂，也会导致相同覆盖参数下持续出现 rules_changed/stale_rebuilt 类重复全量扫描风险，遮住“warm index 只是当前 TextScope 的性能缓存”的模型。
根因线索：Agent 命令入口级 rebuild_text_index() 作为独立命令没有配置覆盖入口，却被 quality_report() 的当前运行覆盖参数路径复用为自动重建事实来源。
冲突的事实来源：quality_report() 中覆盖后的 setting/text_rules；TextIndexAgentMixin.rebuild_text_index() 中基础配置构造的 setting/text_rules；text_index metadata 中保存的 rules_fingerprint；测试中只验证覆盖参数影响质量判断但不验证索引元信息。
重复或旧路径对象：app/agent_toolkit/services/quality.py 的当前运行覆盖参数；app/agent_toolkit/services/text_index.py 的基础配置索引重建入口；app/text_index.py 的 rules_fingerprint 元信息；tests/test_agent_toolkit.py::test_quality_report_uses_command_setting_overrides。
应删除或合并的对象：质量报告自动重建时脱离本次覆盖参数的索引构建事实；同一 Agent 质量报告运行中“覆盖后的 text_rules”和“基础配置 text_rules”并存的索引事实。
受影响外部契约：AgentToolkitService.quality_report(setting_overrides=...)；普通 quality-report 的 text_index_status、rules_fingerprint 和 extractable_count 语义；配置覆盖参数对文本范围和质量报告的全链路生效契约。
验证方式或证据缺口：`rg -n "def quality_report|setting_overrides|detect_text_index_invalidations|rebuild_text_index\\(|_quality_report_from_text_index|load_setting\\(" app/agent_toolkit/services/quality.py app/agent_toolkit/services/text_index.py tests/test_agent_toolkit.py` 与 `rg -n "source_text_required_pattern|line_width_count_pattern|long_text_line_width_limit|strip_wrapping_punctuation_pairs|preserve_wrapping_punctuation_pairs" app/config/overrides.py app/rmmz/text_rules.py app/rmmz/extraction.py app/text_index.py` 可定位；当前证据为静态路径冲突，未执行专门复现用例。
```

```text
编号：ATT-MZ-REVIEW-014
批次：11 质量、覆盖、状态、反馈与手动修复
严重程度：P2
证据等级：E2
状态：已确认
问题：quality-report --include-write-probe 进入写回级分支后，硬门槛改由 Rust quality_gate 返回单个 write_back_gate 错误，但报告 summary/details 仍保留 source_residual_count、placeholder_risk_count、overwide_line_count、write_back_protocol_count 和对应明细数组，并在该分支固定填 0/空数组；当 Rust gate 因源文残留、坏控制符、结构或行宽报错时，Agent JSON 会同时出现 write_back_gate.message 说明质量失败、细分质量计数却为 0 的重复事实来源。
证据：app/agent_toolkit/services/quality.py 第 1711-1738 行在 include_write_probe 路径计算 protocol_probe_count 后调用 _collect_rust_write_back_gate()，第 1739-1743 行把 residual_items、text_structure_items、placeholder_risk_items、overwide_line_items、write_back_protocol_items 全部初始化为空数组，第 1763-1780 行只根据 write_back_gate_error 和这些空数组追加 errors，第 1818-1825 行把 source_residual_count、text_structure_count、placeholder_risk_count、overwide_line_count、write_back_protocol_count 写为这些空数组长度并附带 write_back_gate 摘要，第 1830-1835 行 details 也返回空明细。rust/src/native_core/write_back_plan/quality_gate.rs 第 9-58 行的 assert_saved_translation_quality_passed() 会检查 placeholder_risk、source_residual、text_structure、overwide_line，并把首条明细拼进错误消息；rust/src/native_core/write_back_plan/mod.rs 第 140-150 行在 quality_gate 阶段调用该检查。tests/test_agent_toolkit.py 第 1364-1438 行明确断言 include-write-probe 质量报告不再重复执行 Python native gate 且 summary.write_back_gate.status 为 ok；第 1441-1535 行只断言坏译文时 report.errors 包含 write_back_gate、summary.write_back_gate.message 与 write-back 错误一致，未断言细分计数与 message 一致。docs/advanced-usage.md 第 232-236 行把 quality-report 与 --include-write-probe 描述为在报告里查看写入可行性，不说明开启后细分质量计数会被置零。
影响：用户和 Agent 读取同一份质量报告时，可能看到 `write_back_gate.message` 提示“发现 1 条译文存在源文残留风险”或“发现 1 条译文里的游戏控制符可能被改坏”，但 summary 中 source_residual_count/placeholder_risk_count 仍是 0，details 中对应数组为空；这会降低质量修复定位和自动判断可靠性，也让“质量报告字段描述当前质量事实”的外部 JSON 契约被 Rust gate 摘要和 Python 细分字段两套事实来源分裂。
根因线索：写回级报告为了避免重复 Python native gate，把质量硬门槛收束到 Rust quality_gate，但保留了普通质量报告的细分 summary/details 字段，并用空值占位。
冲突的事实来源：summary.write_back_gate.message；summary 中 source_residual_count/text_structure_count/placeholder_risk_count/overwide_line_count/write_back_protocol_count；details 中各类质量明细数组；tests/test_agent_toolkit.py 对“不重复 Python native gate”的结构锁定。
重复或旧路径对象：include_write_probe 分支中的空 residual_items/text_structure_items/placeholder_risk_items/overwide_line_items/write_back_protocol_items；Rust quality_gate 错误消息；普通 quality-report 细分质量字段。
应删除或合并的对象：写回级质量报告中与 Rust quality_gate message 并存但固定为空的细分质量事实；普通报告细分字段和写回级 gate 摘要之间的双事实来源。
受影响外部契约：`quality-report --include-write-probe` 的 Agent JSON summary/details；`write_back_gate` 摘要；质量修复定位和自动判断对 source_residual_count、placeholder_risk_count、overwide_line_count、write_back_protocol_count 的使用。
验证方式或证据缺口：`rg -n "include_write_probe|write_back_gate|source_residual_count|placeholder_risk_count|overwide_line_count|write_back_protocol_count|collect_agent_service_native_quality_details|quality_gate" app/agent_toolkit/services/quality.py tests/test_agent_toolkit.py rust/src/native_core/write_back_plan/quality_gate.rs rust/src/native_core/write_back_plan/mod.rs docs/advanced-usage.md` 可定位；当前证据为静态路径和测试覆盖缺口，未执行构造源文残留后读取 include-write-probe summary 的复现。
```

```text
编号：ATT-MZ-REVIEW-018
批次：15 发行、Skill 同步与打包
严重程度：P2
证据等级：E2
状态：已确认
问题：GitHub Release 正文虽然改为从 CHANGELOG 提取指定 tag 段落，但提取脚本只检查匹配段落字符串非空；只有版本标题、没有任何实际更新条目的 CHANGELOG 段落也会通过，导致“正式发布必须提供具体更新说明”的发行门槛仍可能被空段落绕过。
证据：docs/development/release-and-tests.md 第 25 行要求发布工作流必须先从 CHANGELOG.md 提取当前 tag 的具体更新说明，找不到对应版本段落时停止发布，不能只使用 GitHub 自动生成的 Release notes；.github/workflows/release.yml 第 65-67 行用 scripts/extract_release_notes.py 写出 dist/release-notes.md，第 104-111 行把该文件作为 GitHub Release body_path。scripts/extract_release_notes.py 第 48-58 行按 `## v...` 标题截取版本段落，第 59-61 行只在 notes 为空字符串时报错；由于 notes 包含版本标题本身，`uv run python -c "from scripts.extract_release_notes import extract_release_notes_section; print(repr(extract_release_notes_section(changelog_text='# 更新日志\\n\\n## v0.2.0 - 2026-06-02\\n\\n## v0.1.9 - 2026-05-31\\n\\n- old\\n', tag='v0.2.0')))"` 输出 `'## v0.2.0 - 2026-06-02\\n'`。tests/test_release_notes.py 第 14-36 行只覆盖正常提取，第 39-45 行只覆盖找不到 tag，第 48-65 行只覆盖写文件，不覆盖标题-only、空 bullet、空泛文案或必须列出验证命令/发行包下载信息。
影响：后续正式发布时，只要 CHANGELOG 有对应 `## vX` 标题，release workflow 就可以继续构建并发布 GitHub Release，即使正文没有功能变化、协议变化、修复点、依赖变化、验证命令或发行包下载信息；这会让发布说明外部契约由“必须具体”退化为“有标题即可”，增加发行边界和用户升级判断风险。
根因线索：发布说明提取脚本把版本标题纳入正文并用整体 strip 判空，没有把版本标题之外的实际说明内容建模为发布门槛；测试也只验证 tag 存在性和截取范围。
冲突的事实来源：docs/development/release-and-tests.md 的具体更新说明要求；scripts/extract_release_notes.py 的标题段落提取逻辑；tests/test_release_notes.py 的最低覆盖；GitHub Release body_path 对 release-notes.md 的直接信任。
重复或旧路径对象：extract_release_notes_section() 的非空判断；CHANGELOG 标题本身作为正文；tests/test_release_notes.py::test_extract_release_notes_section_requires_changelog_entry 只检查缺 tag。
应删除或合并的对象：发布说明“有版本标题即有正文”的判定；只验证 tag 存在而不验证实际内容的发布说明测试边界。
受影响外部契约：GitHub Release 正文、CHANGELOG 版本段落、正式发布说明必须列出具体变化/协议变化/修复点/依赖变化/验证命令/发行包下载信息的交付要求。
验证方式或证据缺口：`rg -n "extract_release_notes|CHANGELOG|Release 正文|发布说明|具体更新说明|body_path" scripts/extract_release_notes.py tests/test_release_notes.py docs/development/release-and-tests.md .github/workflows/release.yml CHANGELOG.md` 可定位；已用临时 Python 命令确认标题-only 段落会被返回为 release notes，未实际创建 GitHub Release。
```

```text
编号：ATT-MZ-REVIEW-019
批次：15 发行、Skill 同步与打包
严重程度：P2
证据等级：E2
状态：已确认
问题：发行包布局、发行版 Skill 转换和禁止复制源码/测试/日志/数据库的边界只由 scripts/build_release.py 和 release workflow 冒烟阶段隐式执行，当前测试套件没有稳定测试固定 `skills/att-mz-release/SKILL.md` 到发行包内 `skills/att-mz/SKILL.md` 的 frontmatter 改写、references 复制、资源清单和排除清单。
证据：scripts/build_release.py 第 130-136 行用字符串替换把 `name: att-mz-release` 改为 `name: att-mz` 并写到目标 Skill，第 139-161 行复制 README、LICENSE、setting.example.toml、setting.toml、custom_placeholder_rules.json、prompts、字体、发行版 references，并创建 data/db、logs、outputs 空目录，第 230-232 行复制资源、冒烟测试并压缩 ZIP；.github/workflows/release.yml 第 93-95 行只在 release workflow 中执行 build_release.py。`rg -n "build_release|copy_packaged_release_skill|copy_release_resources|ensure_github_actions_environment|run_smoke_tests|create_release_zip|release package|发行包|frontmatter|name: att-mz|att-mz-release" tests scripts docs .github` 只在 scripts/docs/workflow 中命中 build_release 相关对象，未在 tests 下命中发行包布局或 Skill 转换测试；tests/test_release_notes.py 只覆盖发布说明提取。docs/development/release-and-tests.md 第 16 行把发行包内 README、setting.toml、skills/att-mz/SKILL.md、Skill references、字体、提示词和空数据目录列为输出，第 70-71 行说明发行版 Skill 发布时改写为发行包内 skills/att-mz/SKILL.md，第 90 行要求改到 Skill/README/提示词/工作区协议时同步检查 tests/test_skill_protocol.py，但该文件不存在且已作为 ATT-MZ-REVIEW-004 记录。
影响：如果后续重构打包脚本、Skill frontmatter、references 布局或发行资源清单，常规 `uv run pytest` 不会在 release workflow 前发现发行包内 Skill 名称错误、复制了开发版 Skill、漏复制 references、漏创建空目录，或把源码/测试/日志/数据库误放进 ZIP；发布边界只能等真实 release 构建和人工检查发现，削弱“发行包只包含允许资源且 release Skill 映射正确”的外部契约。
根因线索：打包脚本把发行布局和 Skill 转换集中在命令式文件复制里，但测试套件没有构造临时 release_dir 对这些机器可观察边界做断言；现有发布测试只覆盖 CHANGELOG 到 release notes。
冲突的事实来源：scripts/build_release.py 的复制/改写逻辑；docs/development/release-and-tests.md 的发行包输出清单；release workflow 的真实发包执行；当前 tests 目录缺少 build_release 布局断言。
重复或旧路径对象：copy_packaged_release_skill() 的字符串替换；copy_release_resources() 的资源清单；release workflow 中才执行的 run_smoke_tests/create_release_zip；不存在的 tests/test_skill_protocol.py 发布协议测试入口。
应删除或合并的对象：只在真实 release workflow 中验证的发行包布局事实；没有单元/集成测试固定的 Skill frontmatter 改写与 references 复制边界。
受影响外部契约：正式 Windows ZIP 包内容；发行包内 `skills/att-mz/SKILL.md` frontmatter `name: att-mz`；发行版 references 随包分发；发行包不得包含源码、测试、历史日志、源码数据库或开发工具链要求的边界。
验证方式或证据缺口：`rg -n "build_release|copy_packaged_release_skill|copy_release_resources|ensure_github_actions_environment|run_smoke_tests|create_release_zip|release package|发行包|frontmatter|name: att-mz|att-mz-release" tests scripts docs .github` 可定位；当前证据为测试覆盖缺口和脚本静态路径，未实际构建发行 ZIP 解包验证。
```

```text
编号：ATT-MZ-REVIEW-020
批次：16 测试保护行为能力
严重程度：P2
证据等级：E2
状态：已确认
问题：测试套件缺少覆盖公开 CLI/Agent 翻译主链路的完整金丝雀流程；当前测试分别验证 CLI JSON、Agent 服务、翻译批次、质量和写回切片，但没有用临时 ATT_MZ_HOME、临时游戏夹具和假模型服务串起 add-game、prepare-agent-workspace、导入规则、translate、quality-report、write-back、反馈修复等外部可观察阶段。
证据：`rg -n 'main\(\["(add-game|prepare-agent-workspace|import-plugin-rules|translate|quality-report|write-back|run-all|import-manual-translations|rebuild-text-index)' tests` 只命中 tests/test_cli_json_output.py 第 274 行 translate、第 402 行 write-back、第 595 行 run-all、第 660 行 run-all --skip-write-back，未命中 add-game、prepare-agent-workspace、import-plugin-rules、quality-report、import-manual-translations 或 rebuild-text-index 的 CLI 直接调用。tests/test_cli_json_output.py 第 290-348 行的 run-all 测试用 FakeHandlerSession、fake_resolve_target_game_title 和 fake_translate_text_for_handler，只断言调用顺序与错误传播；第 536-670 行的 run-all JSON 摘要同样替换 HandlerSession 和 translate_text_for_handler。tests/test_agent_toolkit.py 第 6618-6778 行的 translate --max-items 测试使用 GameRegistry 临时库和最小规则前置条件，但把 TranslationHandler._run_text_translation_batches 替换为 fake_run_text_translation_batches，并在注释中说明“截断到模型前，不消耗真实模型额度”。tests/test_llm_retry.py 只覆盖 LLMHandler 重试，tests/test_benchmark_small_tasks.py 的假 LLM 只服务 benchmark 子进程，不形成 CLI/Agent 主链路保护。
影响：后续破坏性重构 CLI dispatch、运行目录、数据库注册、workspace 文件、规则导入、模型调用、质量报告和写回阶段时，常规测试可以分别通过，但跨命令外部契约仍可能断裂；尤其是 stdout JSON 报告、临时应用目录、假模型响应、TextScope/warm index、质量错误保存、写回门槛和反馈修复之间的串联关系缺少一个稳定的业务级回归入口。
根因线索：测试套件按模块和命令切片组织，并大量用 FakeHandlerSession、fake_translate_text_for_handler、fake_run_text_translation_batches 断开真实流程；已有集成测试多在 AgentToolkitService 或 Handler 内部层验证局部行为，没有把公开 CLI 命令作为同一用户流程连续执行。
冲突的事实来源：Skill/CLI references 描述的完整翻译流程阶段；tests/test_cli_json_output.py 中的局部 CLI fake；tests/test_agent_toolkit.py 中的服务级 warm index 与 translate 切片；tests/test_llm_retry.py 的独立模型重试测试；tests/test_benchmark_small_tasks.py 的 benchmark 专用假模型。
重复或旧路径对象：FakeHandlerSession；fake_translate_text_for_handler；fake_run_text_translation_batches；只在 benchmark 中存在的假模型服务；把 run-all 摘要测试当作完整主链路保护的测试边界。
应删除或合并的对象：用多个 mocked 命令切片替代完整 CLI/Agent 用户流程保护的测试事实；公开流程阶段之间缺少统一金丝雀入口的测试边界。
受影响外部契约：add-game、prepare-agent-workspace、import-plugin-rules、translate、quality-report、write-back、import-manual-translations、verify-feedback-text 和 run-all 的跨命令业务流程；CLI stdout JSON；ATT_MZ_HOME 临时运行目录；假模型响应到质量/写回的可观察结果。
验证方式或证据缺口：已用 rg 定位 tests 下公开 CLI 调用，并读取 tests/test_cli_json_output.py 与 tests/test_agent_toolkit.py 关键 fake 路径；当前证据为测试覆盖缺口，未执行新端到端复现流程。
```

### P3 问题

此处记录局部清晰度、命名、边界说明、测试组织或文案问题。

```text
编号：ATT-MZ-REVIEW-008
批次：06 标准 data 与事件文本域
严重程度：P3
证据等级：E2
状态：已确认
问题：事件指令 JSONPath 展开、命中和 location_path 转换的协议函数放在 app/plugin_text/paths.py 中，事件指令域通过插件文本模块取得 `resolve_event_command_leaves`、`expand_rule_to_leaf_paths` 和 `jsonpath_to_event_command_location_path`，导致插件参数规则与事件指令参数规则共享协议事实但没有中性模块边界。
证据：app/event_command_text/importer.py 第 11-13 行从 app.plugin_text.paths 导入 build_json_string_leaf_path_hint、expand_rule_to_leaf_paths 和 resolve_event_command_leaves，第 124-132 行用这些函数解析事件指令参数和提示路径；app/event_command_text/extraction.py 第 6-7 行从同一模块导入 jsonpath_to_event_command_location_path 和 resolve_event_command_leaves，第 85-98 行把事件指令规则命中转成正文 location_path；app/plugin_text/paths.py 第 1 行模块标题为“JSON 参数树展开与受限 JSONPath 工具”，但第 29 行是 resolve_plugin_leaves，第 61 行是 walk_plugin_value，第 274 行是插件级 jsonpath_to_location_path，第 285 行才是事件指令 jsonpath_to_event_command_location_path，第 359-367 行 __all__ 同时导出插件与事件指令函数；skills/att-mz/references/workspace-schema.md 第 113 行描述插件参数 JSONPath，第 165 行描述事件指令 JSONPath，二者是两个外部规则入口；tests/test_event_command_text.py 第 216-217、234-235、283、544、583 行固定事件指令 `$['parameters']` 路径语义。
影响：后续破坏性重构插件参数规则、事件指令规则或 location_path 协议时，需要在 plugin_text 模块里同时维护两个领域；事件指令规则的外部契约会被隐藏在插件文本命名下，增加模块边界误读和跨域修改风险。
根因线索：插件参数和事件指令参数都使用受限 JSONPath 与 JSON 字符串叶子展开，历史实现把共享逻辑集中到 plugin_text/paths.py，但没有把共享协议抽成中性事实来源。
冲突的事实来源：app/plugin_text/paths.py 的插件域模块名和插件函数命名；app/event_command_text/importer.py 与 app/event_command_text/extraction.py 对事件指令路径协议的实际依赖；skills/att-mz/references/workspace-schema.md 对插件规则和事件指令规则的分开描述。
重复或旧路径对象：app/plugin_text/paths.py::walk_plugin_value；app/plugin_text/paths.py::jsonpath_to_location_path；app/plugin_text/paths.py::jsonpath_to_event_command_location_path；app/event_command_text/importer.py 的 plugin_text.paths 导入；app/event_command_text/extraction.py 的 plugin_text.paths 导入。
应删除或合并的对象：事件指令域依赖插件文本模块名承载 JSONPath 协议的边界；插件专有命名下承载通用 JSON 参数树遍历的函数名。
受影响外部契约：workspace 中 event-commands.json 的 `$['parameters']` 路径规则；事件指令文本抽取 location_path；插件参数规则与事件指令规则的模块边界。
验证方式或证据缺口：`rg -n "resolve_event_command_leaves|jsonpath_to_event_command_location_path|build_json_string_leaf_path_hint|walk_plugin_value|jsonpath_to_location_path|\\$\\['parameters'\\]" app/event_command_text app/plugin_text/paths.py skills/att-mz/references/workspace-schema.md tests/test_event_command_text.py` 直接定位依赖；本问题不判断事件指令抽取或写回当前结果错误，仅确认协议事实来源的模块边界不清。
```

```text
编号：ATT-MZ-REVIEW-021
批次：16 测试保护行为能力
严重程度：P3
证据等级：E2
状态：已确认
问题：测试套件把多个业务领域集中在少数超大文件中，尤其是 tests/test_agent_toolkit.py 和 tests/test_rmmz_loader_extraction_writeback.py 同时覆盖规则导入、工作区、质量报告、手动修复、反馈、placeholder、TextScope、写回、字体、可信源快照、MV 名字框、Note 和非标准 data，导致破坏性重构前难以从文件边界判断失败归属和重构影响面。
证据：Get-Content 行数统计显示 tests/test_agent_toolkit.py 8718 行、tests/test_rmmz_loader_extraction_writeback.py 4035 行、tests/test_plugin_source_text.py 2037 行、tests/test_cli_json_output.py 1538 行；Get-Item 显示这四个文件分别约 386036、177841、88833、55924 字节。`rg -n '^(async )?def test_.*(rule|workspace|quality|write|manual|feedback|placeholder|translate|terminology|coverage|font|source_snapshot|mv_namebox|note|nonstandard|plugin|runtime|run_all|run-all|CLI|json)' tests/test_agent_toolkit.py tests/test_rmmz_loader_extraction_writeback.py` 显示 tests/test_agent_toolkit.py 从第 557 行规则导入一路覆盖到第 8698 行 native quality，期间混合 workflow gate、feedback、active runtime audit、placeholder、workspace、manual import、translate max_items、quality-report、event command validation 等领域；tests/test_rmmz_loader_extraction_writeback.py 从第 259 行 native write plan 到第 3954 行 restore font，混合写回、可信源快照、MV 名字框、Note/data 写回和字体覆盖。
影响：重构一个领域时，维护者需要在超大混合测试文件里定位相关 fixture、helper 和断言，容易把跨域 helper 改动误当成业务行为变化；测试失败时也难以快速判断是规则、索引、质量、写回、字体还是数据层受影响，增加 review 前的证据收束和后续破坏性拆分成本。
根因线索：测试文件以 AgentToolkit 或 RMMZ loader/writeback 的历史入口聚合，而不是按外部业务契约或领域边界拆分；一些 helper 被多个领域复用后，文件名已经不能准确表达当前测试范围。
冲突的事实来源：tests/test_agent_toolkit.py 的文件名和实际跨领域覆盖范围；tests/test_rmmz_loader_extraction_writeback.py 的文件名和实际写回/快照/字体/Note/MV 覆盖范围；批次 16 要求区分行为契约测试和结构锁死测试。
重复或旧路径对象：tests/test_agent_toolkit.py 中混合的规则、workspace、quality、feedback、manual、translation、placeholder、event command、native quality 测试段；tests/test_rmmz_loader_extraction_writeback.py 中混合的 native write plan、source snapshot、MV namebox、note/nonstandard data、font replacement 测试段。
应删除或合并的对象：按历史服务入口聚合的大文件测试边界；需要跨多个领域共享的测试 helper 与领域断言混放在同一文件的组织方式。
受影响外部契约：后续重构时测试失败定位、领域职责边界、行为契约测试与结构锁死测试的分类能力。
验证方式或证据缺口：已用文件行数/字节统计和测试函数名 rg 输出确认混合领域；本问题不判断具体业务断言错误，只记录测试组织对重构前审查和后续拆分的维护成本。
```

## 33. 需复核问题区

此区只放证据暂不足的问题。补到 E1、E2 或 E3 后，移动到“问题记录区”。

## 34. 最终审查覆盖声明

```text
已完成批次：00-17；补充批次 18
未完成批次：无
无法执行的命令：无；批次 15 未实际触发 GitHub Actions release、未构建/解包真实 Windows ZIP，批次 16 未执行完整端到端翻译流程，补充批次 18 未构造 stale workspace 动态复现，均已作为审查范围限制记录，不是命令执行失败
已确认问题数量：22
需复核问题数量：0
P0 数量：1
P1 数量：9
P2 数量：10
P3 数量：2
是否包含解决方案：否
是否存在未填写批次产出：否
是否存在只有主观判断、没有证据的问题：否
是否存在未处理的需复核问题：否
是否仍依赖本文档之外的准备材料：否
```
