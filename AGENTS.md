# att-mz 项目局部规范

本文件只放 att-mz 源码开发长期稳定的硬边界。翻译执行流程、外部 JSON schema、代理任务契约和候选处理细节放在 `skills/att-mz/`、`skills/att-mz-release/` 或对应 CLI 契约中；普通源码开发不得把翻译流程 Skill 当工程规范使用。若与更高优先级运行时指令冲突，以更高优先级指令为准。

## 1. 项目边界与技术栈

- 主体是 Python 3.14+ 命令行应用，依赖和任务运行使用 `uv`；源码入口是 `main.py`，安装后入口是 `att-mz = app.cli_main:main`。
- 配置和外部输入校验使用 `pydantic` v2；运行配置以 `setting.toml` / `setting.example.toml` 为模板，业务参数不得散落硬编码。
- 模型调用使用 OpenAI 兼容接口和 `openai` Python SDK；系统提示词文件放在 `prompts/`。
- 运行数据使用 SQLite，按游戏分库存储在 `data/db/`；持久 schema DDL 以 `app/persistence/schema/current.sql` 为事实源，业务代码不得复制 schema 结构判断。
- 性能敏感和结构化写回能力由 Rust 2024 原生扩展提供，通过 `PyO3` + `maturin` 构建为 `app._native`；Rust 侧重型并行使用 `rayon` 等可控线程池。
- 大规模重构应以逐步减少 Python 职责、强化 Rust 主路径为长期方向。除 CLI 编排、配置校验、模型 SDK 接入等当前确需 Python 承担的边界外，不再主动扩展 Python 技术栈；新增核心逻辑和基础能力优先放到 Rust。
- 正式 Windows 发行包只允许由 GitHub Actions `release` 工作流生成；本机只提供源码改动、提交和工作流触发。

## 2. 结构性修复边界

- 本项目处于主动开发阶段，源码改动以长期正确、清晰可维护为目标；禁止为了短期兼容保留错误或含混的内部契约。
- 缺陷修复必须追到根因；同一根因引出的契约缺口、测试缺口和文档缺口，应在同一变更中收束。
- 当局部补丁会制造多事实来源、隐藏状态同步、旁路开关或长期维护成本时，必须做结构性修复；允许删除废弃入口、调整内部边界或进行破坏性重构。
- 旧数据库、旧规则或旧 metadata 不符合当前契约时必须显式失败，并提示重新导入、重建或按当前契约修正；禁止自动迁就、静默兜底或继续按旧语义运行。
- 禁止用堆叠 `if/else`、字符串识别、吞异常、mock 成功、隐式回退或双事实来源掩盖问题。
- Rust 接管某条生产主路径后，旧 Python 重型扫描、候选、校验、AST 或写回同功能回退路径必须删除；Python 只保留编排、配置校验、报告组装和小规模胶水逻辑。

## 3. 性能、并发与诊断

- 性能退化、重复全量扫描、CPU 密集任务串行执行和“参数存在但没有真实参与调度”都按功能缺陷处理。
- 会遍历全游戏文本、插件配置、插件源码、AST、数据库译文记录或写回计划的命令，必须先梳理本命令内全量扫描次数；无真实顺序依赖的阶段必须复用已加载范围、候选扫描结果、中间索引或 SQLite metadata。
- CPU 密集型的大规模文本扫描、占位符识别、AST 解析、质量检查、写回协议检查、哈希/索引构建和批量规则匹配，默认放到 Rust 原生扩展实现。
- 无真实顺序依赖的 I/O 与 CPU 任务必须使用真实并发；Rust 并发数量通过 `ATT_MZ_RUST_THREADS` 或配置入口限制，禁止无上限榨干 CPU，也禁止可并行重活保持单线程。
- 修改性能敏感路径时，必须给出真实 CLI 性能证据；`scan_budget` 只能做复杂度保护，不能替代真实命令耗时。
- 临时 benchmark、runner、manifest、测试夹具和生成数据只允许作为执行期资产，交付前必须删除。
- 诊断计时应集中到专门模块；普通模式只保留命令/阶段级摘要，debug 模式可输出 `diagnostics.timings`。禁止 per-row、per-text、per-candidate 打点，避免诊断工具本身制造性能问题。

## 4. Rust / Python 职责与测试分层

- Rust 测核心逻辑：规则匹配、selector、hash、stale 判断、候选扫描、占位符覆盖、SQLite 写入、native schema 和错误码。
- Python 测流程契约：CLI 参数链路、配置覆盖、JSON 报告、用户文案、错误映射、数据库读写结果和跨模块集成。
- 跨层契约单独固定：native 输入输出 schema、错误码、report 字段、SQLite schema version、thread 配置和 CLI JSON 兼容面。
- 不得长期用 Python 大集成测试兜 Rust 内部逻辑；Rust 接管后应补 Rust 单测，同时瘦身 Python 测试，只保留关键流程步骤。
- 新增或修改测试不得依赖开发机私有 `setting.toml` 或默认配置路径；涉及配置加载、应用目录或 CLI 的测试必须显式传入 `setting.example.toml`、测试专用临时配置，或通过 `ATT_MZ_HOME` 创建临时应用目录。
- 测试应覆盖业务行为、边界条件和失败路径，避免约束 `.md` 自然语言正文、段落顺序、具体措辞或排版格式。

## 5. Prompt、用户文案与内部信息隔离

- 面向用户的回复、报告、README、Skill 主流程、默认日志摘要和故障说明，必须先说明“发生了什么、影响什么、下一步做什么”。
- 内部字段、数据库表、类名或函数名只允许在 JSON 格式说明或排障定位中出现，且第一次出现必须紧跟中文解释。
- 常见用户文案默认使用：`pending`=还没成功保存译文的文本，`quality_error`=模型翻了但项目检查没通过的译文，`placeholder`=必须原样保留的游戏控制符，`write-back`=把译文写进游戏文件，`location_path`=文本在游戏里的内部位置。
- 禁止把“入库、缓存、门禁、阻断、产物、收尾、跑批、兜底、兼容旧逻辑”当作默认用户文案；改成用户能行动的中文说明。
- 给 LLM 的 prompt 只能包含当前任务必需的可见输入、输出格式、质量要求和原样保留约束；禁止加入来源文件名、数据库表名、内部字段名、真实路径、`location_path`、`translated_text` 等模型无法使用的内部实现细节。
- 修改 prompt 组装逻辑后，必须用测试覆盖最终 user prompt 文本，并断言不会出现内部文件名、内部字段名和 `位置:` 这类无效上下文。

## 6. docs、Skill 与发行边界

- `docs/` 只放给人类阅读的 README、使用指南、开发说明、设计说明、排障说明和发布说明；不得让 `docs/` 成为翻译流程运行依赖。
- 会被 Agent 复制、派发、执行、校验或作为黑盒流程依据的内容，必须放在 `skills/<技能名>/SKILL.md` 或 `skills/<技能名>/references/`。
- `skills/att-mz-protocol/` 是开发版和发行版翻译流程 Skill 的单一事实来源；`workflow.toml`、`subagents.toml`、`profiles/*.toml` 和 `templates/` 共同生成公开 Skill。
- `skills/att-mz/` 和 `skills/att-mz-release/` 是生成结果；修改 Skill 协议时优先修改 `skills/att-mz-protocol/`，再运行 `uv run python scripts/generate_skill_protocol.py --write`。
- 交付任何 Skill 协议相关改动前必须运行 `uv run python scripts/generate_skill_protocol.py --check`，确认生成物没有漂移；不得只手写一边 Skill 或只改生成物。
- `skills/att-mz/` 和 `skills/att-mz-release/` 只描述翻译流程，不作为普通源码开发、代码审查、测试修复、重构、发布维护和工具实现排障依据。
- 开发版 Skill 使用源码入口，发行版 Skill 使用发行包 exe 入口；两者业务语义、JSON schema、子代理任务契约和用户可见文案必须一致，差异只允许来自命令入口、可访问资源、停止条件和打包要求。
- 源码运行用户只需要知道开发版 Skill 和源码入口 `uv run python main.py <命令> ...`；只有维护者或贡献者修改 Skill 协议时，才需要理解生成流程。
- 修改开发版或发行版 Skill 时，必须同步审查 canonical 源和生成目标，避免任务协议语义漂移；涉及 Skill、README、docs 或发布脚本的改动，必须检查是否出现“Agent 契约放在 docs 里”或“docs 覆盖 Skill”的倒置关系。
- 发行包只包含可执行文件、配置模板、README、许可证、字体、提示词、发行版 Skill、必要参考资料和空的数据/日志/输出目录；不得包含源码数据库、历史日志、测试目录、Python 源码目录或 Rust 源码目录。
- 每次正式发布必须提供具体更新说明，并同步写入仓库更新日志和 GitHub Release 正文；禁止只写“例行更新”“若干优化”或依赖自动生成空泛说明。

## 7. 验证与交付

- 涉及 Python/Rust 源码、测试、schema、构建流程、发行流程或可执行契约的项目交付前，必须执行 `uv run basedpyright` 和 `uv run pytest`，保持 0 warning、0 error；修改 Rust 原生扩展、构建流程或发行流程时，还必须执行 Rust 格式检查、clippy 和 Rust 测试。
- 本机全量 `pytest` 比较笨重；不涉及源码、测试、schema、构建流程、发行流程或可执行契约的纯文档、Skill 文案、README 或发布说明改动，原则上不在本机运行 `uv run pytest`，只执行与改动直接相关的生成物检查、静态检查或针对性验证；若确需全量运行，必须说明触发原因。
- 触及 CLI 参数、配置字段、环境变量、JSON schema、SQLite schema、外部规则、写回逻辑、prompt 组装或发行脚本时，必须补充对应测试。
- 修改性能敏感路径时，交付说明必须列出真实 CLI 性能结果、内部阶段耗时、瓶颈归因和剩余风险。
- 涉及 docs、Skill、README 或发布说明的改动，只允许用测试固定机器可观察边界，例如文件存在、入口指向、打包映射和禁止出现的敏感实现细节。
- 文档示例必须脱敏，使用 `<项目目录>`、`<输入文件>`、`<输出目录>` 等占位符，禁止写真实本机路径、用户名、客户项目名或用户数据。
- 无法执行应跑验证时，必须说明具体原因、影响范围和剩余风险；不得把未验证内容写成已通过。
