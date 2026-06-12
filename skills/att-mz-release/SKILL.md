---
name: att-mz-release
description: 仅在用户明确要求使用 A.T.T MZ 发行版执行或继续 RPG Maker MV/MZ 游戏翻译流程时使用，包括注册游戏、准备工作区、分析术语和文本规则、导入规则、调用模型翻译、检查译文、手动修复、写进游戏文件与试玩反馈补漏。
---

# A.T.T MZ 发行版 Skill

本 Skill 是翻译任务执行协议，不是项目说明书。主文件只做路由：触发边界、运行面、阶段索引和硬停止规则。阶段细节、JSON 结构、任务契约和失败恢复按需读取 `references/`。

## 核心原则

- 业务数据只通过 A.T.T MZ CLI、工作区 JSON、当前游戏目录和用户明确提供的信息流转。
- 任何会消耗模型额度、导入规则、保存译文或写进游戏文件的动作，都必须先满足当前阶段的通过标准。
- 主代理是总控与裁决者：用户确认、规则导入、译文保存、写回许可、字体覆盖和最终风险判断不能交给子代理。
- 默认自动推进：除写文件、危险回溯、完整重译、源码/Skill 修改、接受不可逆或用户风险、显著增加额度/时间成本等真实决策外，主代理应自行诊断、修规则、重跑校验、导入修复和收束报告，不把可由流程判断的问题改成中途选择题。
- 子代理分为工作席和审查席：工作子代理主动发现并产出候选，审查子代理反向检查漏选、误选、偷懒、原文残留、过拟合和规则风险；子代理输出只是证据和候选，主代理必须裁决。
- 第一次写进游戏文件只表示生成第一版可试玩汉化结果，稳定版本依赖用户试玩反馈继续补漏。
- 源码仓库中的 `docs/wiki/` 是维护者资料，不是发行版翻译流程执行契约；执行翻译时不要读取源码 wiki、数据库表或维护者文档来替代本 Skill、CLI JSON 输出和当前工作区文件。

## 运行面

- `<发行版目录>` 是 A.T.T MZ 发行包目录。默认命令是 `.\att-mz.exe <命令> ...`。
- 翻译流程内 `<发行版目录>` 默认只读。未经用户明确允许，严禁修改源码、测试、配置、提示词、Skill、文档、构建脚本、发行脚本或任何项目文件；不得把“顺手修复”“排障需要”“测试失败”“格式化一下”当作源码修改许可。
- `<游戏目录>` 是目标 RPG Maker MV/MZ 游戏目录。首次注册必须使用没有 `data_origin`、`js/plugins_origin.js` 和 `js/plugins_source_origin` 的干净原始目录；注册游戏时由 CLI 创建可信源快照。
- `<工作区>` 是任务临时工作目录。导出文件、规则草稿、任务包、临时脚本和手动填写译文表都放在这里，不能散落到 `<发行版目录>` 或游戏根目录。
- `reset-game` 是危险的时光回溯命令，只能在用户明确要求注销、重置游戏或恢复到注册前状态时使用。
- 模型地址、API Key、路径、业务参数和可调开关只从环境变量、本地配置或 CLI 参数读取，不写进任务文件、报告或提交。
- CLI stdout 只读取最终 JSON；长任务的 stderr 进度行是阶段进展，不是结果 JSON。

## 按需参考资料

| 主要工作 | 必读参考资料 | 读取时机 |
| --- | --- | --- |
| 启动与注册 | `cli-command-contract.md`、`workspace-schema.md` | 运行或排查启动、注册、状态检查和危险回溯前 |
| 工作区与基础候选 | `cli-command-contract.md`、`workspace-schema.md`、`agent-review-workflow.md`、`subtask-package-mode.md` | 读取、填写、修复、审查、分发任务包或清理工作区 JSON 前 |
| MV 虚拟名字框 | `agent-review-workflow.md`、`mv-virtual-namebox-rules.md`、`rpg-maker-mv-mz-world-knowledge.md` | MV 游戏第零轮规则发现、审查、编写或修复前 |
| 术语工程 | `agent-review-workflow.md`、`terminology-workflow.md`、`translation-rule-examples.md`、`subagent-collaboration.md`、`subtask-package-mode.md` | 进入术语工程、派发术语候选、分发术语任务包、审查术语质量、合并字段译名表或制作正文术语表前 |
| 外部文本规则 | `agent-review-workflow.md`、`external-rules-workflow.md`、`plugin-rules-agent-task.md`、`event-command-rules-agent-task.md`、`note-tag-rules-agent-task.md`、`translation-rule-examples.md`、`subagent-collaboration.md`、`subtask-package-mode.md` | 处理、主动发现、分发任务包或审查插件、事件指令、Note 标签规则前 |
| 非标准 data 与插件源码支线 | `agent-review-workflow.md`、`nonstandard-data-agent-task.md`、`plugin-source-text-agent-task.md`、`workspace-schema.md`、`subagent-collaboration.md` | 风险报告提示高风险，或用户要求处理、主动发现、审查非标准 data / 插件源码文本前 |
| 占位符收束 | `agent-review-workflow.md`、`placeholder-rules.md`、`structured-placeholder-rules.md`、`translation-rule-examples.md`、`subagent-collaboration.md` | 编写、审查、覆盖扫描或修复普通/结构化占位符规则前 |
| 正文翻译与手动修复 | `cli-command-contract.md`、`failure-recovery.md`、`placeholder-rules.md`、`structured-placeholder-rules.md` | 启动正文翻译、解释失败、导出修复表、导入手动译文或重置译文前 |
| 写进游戏文件 | `cli-command-contract.md`、`failure-recovery.md`、`subagent-collaboration.md` | 写进游戏文件、重建当前运行文件、术语专用写入或当前运行审计前 |
| 试玩反馈 | `feedback-iteration.md`、`failure-recovery.md`、`subagent-collaboration.md` | 用户反馈漏翻、误翻、显示异常或插件界面残留源语言文本时 |

不要把参考资料全文复制进模型 prompt、交付报告或子代理任务单；只读取当前阶段需要的小节，并继续以 CLI 输出和当前工作区文件为准。

## 阶段索引

| 阶段 | 目标 | 命令 | 必读参考 |
| --- | --- | --- | --- |
| 启动与注册 | 确认工具入口、游戏结构、工作区、源语言和模型配置可用 | `doctor`、`probe-source-language`、`add-game`、`list`、`reset-game` | `cli-command-contract.md`、`workspace-schema.md` |
| 工作区与基础候选 | 建立 Agent 分析边界并导出候选、草稿规则和术语上下文 | `prepare-agent-workspace`、`validate-agent-workspace`、`cleanup-agent-workspace`、`export-plugins-json`、`export-event-commands-json` | `cli-command-contract.md`、`workspace-schema.md`、`agent-review-workflow.md`、`subtask-package-mode.md` |
| MV 虚拟名字框 | 为 MV 游戏确认首行虚拟名字框规则 | `export-mv-virtual-namebox-candidates`、`validate-mv-virtual-namebox-rules`、`import-mv-virtual-namebox-rules` | `agent-review-workflow.md`、`mv-virtual-namebox-rules.md`、`rpg-maker-mv-mz-world-knowledge.md` |
| 术语工程 | 统一字段译名和正文术语，避免字段写回表与提示词术语表混用 | `export-terminology`、`import-terminology` | `agent-review-workflow.md`、`terminology-workflow.md`、`translation-rule-examples.md`、`subagent-collaboration.md`、`subtask-package-mode.md` |
| 外部文本规则 | 判断插件参数、事件指令参数和 Note 标签中的玩家可见文本 | `validate-plugin-rules`、`import-plugin-rules`、`validate-event-command-rules`、`import-event-command-rules`、`export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules` | `agent-review-workflow.md`、`external-rules-workflow.md`、`plugin-rules-agent-task.md`、`event-command-rules-agent-task.md`、`note-tag-rules-agent-task.md`、`translation-rule-examples.md`、`subagent-collaboration.md`、`subtask-package-mode.md` |
| 非标准 data 与插件源码支线 | 处理少见的非标准 data 文本和 js/plugins 源码硬编码显示文本 | `scan-nonstandard-data`、`export-nonstandard-data-json`、`validate-nonstandard-data-rules`、`import-nonstandard-data-rules`、`scan-plugin-source-text`、`export-plugin-source-ast-map`、`validate-plugin-source-rules`、`import-plugin-source-rules` | `agent-review-workflow.md`、`nonstandard-data-agent-task.md`、`plugin-source-text-agent-task.md`、`workspace-schema.md`、`subagent-collaboration.md` |
| 占位符收束 | 保护必须原样保留的控制符和协议片段，同时不吞掉玩家可见文本 | `build-placeholder-rules`、`validate-placeholder-rules`、`scan-placeholder-candidates`、`import-placeholder-rules`、`validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates`、`import-structured-placeholder-rules` | `agent-review-workflow.md`、`placeholder-rules.md`、`structured-placeholder-rules.md`、`translation-rule-examples.md`、`subagent-collaboration.md` |
| 正文翻译与手动修复 | 用小批量发现严重风险，再靠全量多轮重试保存译文，最后小规模手动收尾 | `rebuild-text-index`、`translate`、`translation-status`、`text-scope`、`audit-coverage`、`quality-report`、`export-quality-fix-template`、`export-pending-translations`、`import-manual-translations`、`reset-translations`、`validate-source-residual-rules`、`import-source-residual-rules`、`run-all` | `cli-command-contract.md`、`failure-recovery.md`、`placeholder-rules.md`、`structured-placeholder-rules.md` |
| 写进游戏文件 | 生成可试玩汉化结果，并验收当前运行文件 | `write-back`、`rebuild-active-runtime`、`write-terminology`、`restore-font`、`audit-active-runtime`、`diagnose-active-runtime`、`run-all` | `cli-command-contract.md`、`failure-recovery.md`、`subagent-collaboration.md` |
| 试玩反馈 | 根据实际游玩反馈继续补规则、补译文或定位写入缺口 | `verify-feedback-text`、`quality-report`、`audit-active-runtime`、`diagnose-active-runtime`、`write-back` | `feedback-iteration.md`、`failure-recovery.md`、`subagent-collaboration.md` |

## 新游戏主流程

1. 在 `<发行版目录>` 运行静态检查，确认 CLI 可启动；注册游戏前必须运行 `probe-source-language --path <游戏目录>`，只按玩家可见文本确认源语言。
2. 运行游戏检查，准备 `<工作区>`，读取 `manifest.json` 判断引擎类型。
3. MV 游戏执行第零轮虚拟名字框发现与审查；MZ 游戏跳过。工作子代理发现当前游戏发言人/名牌模式，审查子代理反向检查过拟合、漏同类和误伤，主代理写裁决后才 validate/import。
4. 开局确定候选分析方式和高风险支线策略；用户没有特别要求时，默认当前会话自动完成并自动处理高风险支线，不把后续可判断的支线处理变成中途选择题。
5. 第一轮处理术语候选；工作子代理产出分组候选和证据，术语审查子代理检查原文照抄、中英混杂、机械拼接和转换风险，主代理合并字段译名表和正文术语表并写裁决后再导入。
6. 第二轮处理插件规则、事件指令规则和 Note 标签规则；每类规则可以为空，但必须有工作报告、审查报告、空结果理由和主代理裁决，再通过对应导入流程保存。
7. 非标准 data 文本和插件源码文本只在高风险或用户明确要求时进入支线；默认按开局策略自动处理。只有缺少策略且会显著增加成本/风险、审查 blocker 未关闭或仍有未归类候选时停止正文翻译。
8. 三类外部规则和必要支线规则全部导入后，主代理收束普通占位符规则；存在协议外壳包住显示文本时，再处理结构化占位符规则。两类占位符都必须经过审查子代理检查吞文本、漏保护、过宽、过窄和结构化需求。
9. 运行工作区总体验收。任一规则未完成、校验失败、审查 blocker 未关闭、主代理裁决缺失或占位符覆盖不清楚时，不启动正文翻译。
10. 大型游戏先运行 `rebuild-text-index`，再执行小批量翻译、查看翻译进度、文本范围、覆盖审计和质量报告；小批量只用于观察模型、规则和控制符风险，不以 0 失败作为指标。
11. 小批量出现还没成功保存译文或检查没通过译文是正常现象；禁止为了让小批量样本完美而导出手动修复表、手填译文或重置译文。
12. 进入全量续跑后，只要剩余数量明显下降且没有规则性事故，就继续翻译；主要依靠多轮重试收敛。
13. 全量多轮后剩余量已经很小、适合人工收尾，或连续多轮同类失败不下降时，先自动诊断主要错误类型并尝试修规则、换提示上下文允许的模型策略、导出质量修复表或待补译表、精确重置坏译文；只有需要用户承担额外成本、接受风险或选择完整重译时才询问用户。
14. 确认确需保留源语言片段时，使用源文保留例外规则；禁止全局关闭源文残留检测。
15. 写进游戏文件前，必须通过覆盖审计和质量检查，并取得用户写回许可；字体覆盖必须单独确认。写入后必须验收当前运行文件。
16. 写回后要求用户试玩，反馈漏翻、误翻、显示异常、插件界面残留源语言文本和图片文字等问题。

## 子代理协作

- 子代理的优势是并行探索、隔离噪声、独立审查和压缩证据；它们不是“替主代理拍板”的执行者。
- 分析与规则产出阶段采用审查型工作流：工作子代理产出候选和证据，审查子代理用 `blocker`、`warning`、`info` 分级反向审查，主代理写 `review-decisions/<阶段ID>.json` 后才允许 validate/import。
- 子代理可以在任务授权范围内把一次性 Python、PowerShell、Node.js 或其他本机可用脚本写到 `<工作区>/agent-scratch/<阶段ID>/<任务ID>/scripts/`，也可以运行只读、导出、扫描、诊断和 validate 类 CLI 命令；禁止任何 import、写回、重建、重置、数据库写入或游戏文件写入。
- 外部协作任务包只用于术语候选、插件规则、事件指令规则和 Note 标签规则的工作候选；生成、回收和验收任务包前必须读取 `references/subtask-package-mode.md`，任务包不能替代审查子代理或主代理裁决。
- 当前平台支持子代理时，当前会话完成模式必须并行处理无依赖候选；不支持子代理时，按同一任务契约串行执行或使用外部协作任务包。
- 用户未明确选择外部任务包时，默认使用当前会话完成模式；只有用户表示额度/时间有限、希望带走任务包，或当前会话无法承载候选分析时，才中断询问任务包方案。
- 每个子代理或任务包都必须有明确输入、逻辑、唯一输出、空结果条件、校验命令和完成报告。
- 派发子代理时不能只概括任务，必须复制对应任务契约并填入 `<发行版目录>`、`<工作区>`、`<游戏标题>`、必要时的 `<游戏目录>`、输入文件、唯一可写文件和校验命令。
- 工作子代理必须返回 `selected`、`excluded`、`uncertain`、`active_discoveries`、`evidence`、`risk`、`needs_main_review`、`recommended_next_action`，并列出读取文件、脚本、统计产物和 CLI 命令。
- 审查子代理必须返回 `findings`，每条 finding 都有 `severity`、`target`、`evidence`、`impact` 和 `recommended_resolution`；未关闭 `blocker` 时主代理禁止导入。
- 主代理必须等待工作和审查全部完成，逐项读取结果并写阶段裁决；用户或外部代理返回内容一律只是候选答案。
- 主代理等待子代理时必须使用平台等待、轮询或 `sleep` 控制节奏；不得因短时间无输出就催促、打断、改用半成品裁决或反复读取未变化产物消耗上下文。
- 详细角色、权限、报告结构和交叉审查关系见 `references/agent-review-workflow.md` 与 `references/subagent-collaboration.md`。

## 写进游戏文件前硬门槛

- 用户明确允许写回
- audit-coverage 没有 error
- quality-report 没有 error
- 可信源快照有效
- 当前规则范围内正文译文完整
- 普通 warning 已由主代理逐项确认；只有接受风险类 warning 需要用户确认
- 字体覆盖已单独确认
- 写入后当前运行文件验收通过

## 工具排障边界

- 正常翻译任务保持黑盒，不靠源码、数据库表结构或 Python 对象猜外部规则格式。
- 工具排障只处理翻译流程内的合法输入反复失败或 Skill/CLI 契约冲突。普通源码开发、代码审查、测试修复、重构和发布维护按项目开发规范处理，不作为本 Skill 的触发条件。
- 需要阅读或修改 A.T.T MZ 项目源码时，必须切换到源码仓库和发行版 Skill。发行版同一合法工作区文件反复触发无法解释的 CLI 错误时，停止翻译流程并报告需要源码级排障；不要在发行版目录内尝试修工具。
- 用户同意源码修改后，源码修复必须作为独立源码排障任务执行，遵守项目开发规范；修复后继续翻译时，必须回到公开 CLI 和工作区 JSON 流程重新校验。

## 硬停止规则

- 启动与注册：游戏结构无效
- 启动与注册：源语言探测不确定且用户未确认
- 启动与注册：模型配置缺失且本轮需要翻译
- 启动与注册：工作区不可写
- 工作区与基础候选：manifest 缺失或工作区不可写
- 工作区与基础候选：validate-agent-workspace 有 error
- 工作区与基础候选：stdout sampled 明细被当成完整候选使用
- MV 虚拟名字框：MZ 游戏误跑本阶段
- MV 虚拟名字框：MV 发现或审查报告缺失
- MV 虚拟名字框：审查 blocker 未关闭
- MV 虚拟名字框：MV 新命中未审查
- MV 虚拟名字框：空规则未确认
- 术语工程：子代理直接改最终表
- 术语工程：术语工作或审查报告缺失
- 术语工程：审查 blocker 未关闭
- 术语工程：正文术语表是字段译名表副本
- 术语工程：把字段包装形式、整句或定位信息写进正文术语表
- 术语工程：同一术语冲突
- 外部文本规则：猜测路径
- 外部文本规则：审查 blocker 未关闭
- 外部文本规则：选中资源、脚本或机器协议
- 外部文本规则：空结果未说明理由
- 外部文本规则：插件配置变化后未重新准备当前工作区
- 非标准 data 与插件源码支线：高风险支线策略缺失且当前候选处理会显著增加成本或风险
- 非标准 data 与插件源码支线：高风险未处理也未按已确认策略跳过
- 非标准 data 与插件源码支线：审查 blocker 未关闭
- 非标准 data 与插件源码支线：候选未归类
- 非标准 data 与插件源码支线：路径或 selector 失效
- 非标准 data 与插件源码支线：试图扫描 plugins 外目录
- 占位符收束：审查 blocker 未关闭
- 占位符收束：未覆盖候选未修复也未确认风险
- 占位符收束：规则吞掉玩家可见文本
- 占位符收束：候选范围变化后未重新审查并导入当前规则
- 占位符收束：外部规则变化后未重新扫描
- 正文翻译与手动修复：规则性事故
- 正文翻译与手动修复：控制符风险扩大
- 正文翻译与手动修复：小批量阶段手动修复或追求 0 失败
- 正文翻译与手动修复：全量同类失败多轮不下降且已完成自动诊断后仍需要用户承担成本、风险或策略取舍
- 正文翻译与手动修复：用源文保留例外掩盖整句漏翻
- 写进游戏文件：未获写回许可
- 写进游戏文件：质量 error
- 写进游戏文件：还没成功保存译文的文本未清
- 写进游戏文件：当前运行文件存在未解决的阻断级审计问题
- 写进游戏文件：字体覆盖未单独确认
- 试玩反馈：凭空猜测
- 试玩反馈：无证据扩大规则
- 试玩反馈：补外部规则后跳过占位符收束
- 试玩反馈：直接全量重译
- 试玩反馈：直接手改游戏 data 文件
- 试玩反馈：反馈无法定位且未向用户补充上下文

## 禁止做法

- 在 `<发行版目录>` 写翻译临时脚本、中间 JSON、抽样报告或手动译文表。
- 运行发行版 Python 入口、安装开发依赖、读取源码，或修改发行包外的项目文件。
- 用临时脚本直接 `import app...` 操作数据库或游戏数据。
- 把看不懂的结构当成没有内容，或为了让规则非空而编造规则。
- 子代理未完成、规则未导入、占位符未覆盖就启动正文翻译。
- 主代理用未完成报告、半成品文件或短时间无输出作为失败结论，提前进入 validate/import、翻译或写回。
- 分析与规则产出阶段缺少工作报告、审查报告或主代理裁决就 validate/import。
- 审查报告仍有未关闭 `blocker` 时 validate/import。
- 子代理执行 `import-*`、`write-back`、`rebuild-active-runtime`、`reset-game`、`reset-translations`、`run-all` 或直接写数据库/游戏文件。
- 质量检查有 error 仍写进游戏文件。
- 绕过 CLI 手改数据库、手动改游戏 `data/*.json`，或用空译文伪造重置。
- 用源文保留例外掩盖整句漏翻，或关闭源文残留检测。
- 把模型密钥写进命令、任务文件、报告、日志摘要或提交。
- 把第一版可试玩汉化结果包装成百分百完成。
