# A.T.T MZ 超重型破坏性重构前 ReviewPlan

生成日期：2026-06-03

本文档用于指导后续 AI 对 A.T.T MZ 做一次完整的项目级、超重型破坏性重构前代码审查。本文档是闭环计划，已经内化准备材料的必要内容；执行审查时只需要当前仓库和本文档，不需要再依赖其他两份准备文档。

本文档不是重构方案，不执行修复，不给解决答案。最终产出只有一个：把所有检查到的问题写入本文档的“问题记录区”。

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

完成本文档要求的 review 后，执行者应该能够回答：

> 只靠这个计划文档和当前仓库，能不能让 AI 完整完成项目级、超重型破坏性重构前代码审查？

合格答案必须是：

> 可以

达成“可以”的最低条件：

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
| 00 审查启动与索引 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 01 长期指令与文档边界 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 02 CLI 入口与 JSON 报告 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 03 配置、运行目录与日志 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 04 注册、可信源快照与 RMMZ 数据层 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 05 工作区与规则导入 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 06 标准 data 与事件文本域 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 07 插件参数与插件源码文本域 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 08 Note、非标准 data、占位符、源文保留与字体 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 09 TextScope 与 warm index | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 10 翻译、LLM 与 Prompt 隐私 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 11 质量、覆盖、状态、反馈与手动修复 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 12 写入门槛、写回计划与文件安全 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 13 持久化与 DB schema | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 14 Rust 原生核心与 Python adapter | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 15 发行、Skill 同步与打包 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 16 测试保护行为能力 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |
| 17 跨批收束与最终问题索引 | 未执行 | 否 | 否 | 0 | 0 | 初始状态 |

## 31. 批次产出记录区

执行 review 时，每批完成后先填本区，再把确认问题追加到“问题记录区”。本区记录审查覆盖和证据，不写解决方案。

### 批次 00 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 01 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 02 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 03 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 04 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 05 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 06 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 07 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 08 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 09 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 10 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 11 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 12 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 13 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 14 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 15 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 16 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

### 批次 17 产出

```text
主读文件：
辅助读取：
运行命令：
确认问题编号：
需复核问题编号：
跨批线索：
未覆盖范围：
```

## 32. 问题记录区

执行 review 时从 `ATT-MZ-REVIEW-001` 开始编号。此区初始为空；只追加问题，不追加解决方案。

### P0 问题

此处记录已确认会破坏外部契约、写回安全、数据一致性、Prompt 隐私、DB schema 兼容判断或发行边界的问题。

### P1 问题

此处记录会阻塞超重型破坏性重构的结构性问题。

### P2 问题

此处记录明显增加维护成本、性能风险、测试脆弱性或文档漂移的问题。

### P3 问题

此处记录局部清晰度、命名、边界说明、测试组织或文案问题。

## 33. 需复核问题区

此区只放证据暂不足的问题。补到 E1、E2 或 E3 后，移动到“问题记录区”。

## 34. 最终审查覆盖声明

执行批次 17 时填写。

```text
已完成批次：
未完成批次：
无法执行的命令：
已确认问题数量：
需复核问题数量：
P0 数量：
P1 数量：
P2 数量：
P3 数量：
是否包含解决方案：否
是否仍依赖其他两份准备文档：否
是否可以只靠本文档和当前仓库完成完整项目级 review：可以
```
