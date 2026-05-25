# A.T.T MZ

面向 Agent 的 RPG Maker MV/MZ 汉化闭环工具：规则扫描、术语整理、模型翻译、质量检查、把译文写进游戏文件和试玩反馈补漏。

A.T.T MZ 以 Agent 执行协议为核心。程序负责提取文本、保存译文、校验规则、生成质量报告和写进游戏文件；Codex、Claude Code 或其他 Agent 按项目 Skill 组织流程，审查术语、处理规则、修复失败译文，并根据试玩反馈继续补漏。发行包已经包含可执行文件、默认配置、字体、提示词和 Agent Skill；普通使用不需要安装 Python、Rust、uv，也不需要读取源码。

## 适合什么

- 把 RPG Maker MV/MZ 日文或英文游戏汉化成第一版可试玩结果。
- 让 Codex、Claude Code 或其他 Agent 按项目 Skill 扫描规则、整理术语、翻译正文、检查译文，并把译文写进游戏文件。
- 在写进游戏文件前检查没成功保存译文的文本、源语言残留、必须原样保留的游戏控制符风险和游戏窗口放不下的长行。
- 把试玩中发现的漏翻、误翻、显示异常和语气问题整理成反馈清单，再定位、修复、检查并重新写进游戏文件。

不适合直接修改图片文字、音频或视频。插件源码文本只在高风险确认并导入源码规则后处理；默认扫描只提示风险，不会自动改插件源码。

## 核心特点

- Agent 优先：项目提供可执行的 Skill 和命令契约，让 Agent 按阶段完成汉化流程。
- 闭环流程：从注册游戏、准备工作区、导入术语和规则，到模型翻译、质量检查、写进游戏文件和试玩反馈补漏，全部由 CLI 状态和报告串联。
- 硬检查优先：字段译名表、正文术语表、外部规则和占位符规则不完整时，命令会直接报错；质量报告有错误时不能继续写进游戏文件。
- 可恢复运行：译文记录、术语、规则、日志和质量结果保存在项目数据目录，失败后按报告修复再继续。

## 你需要准备

- A.T.T MZ Windows 发行包 ZIP。
- 一个可运行的 RPG Maker MV/MZ 游戏目录。
- 一个 OpenAI 兼容接口的模型服务地址、API Key 和模型名。
- 一个能执行任务的 Agent。建议把发行版目录作为 Agent 的工作目录。

## 第一次使用

1. 解压发行包到 `<发行版目录>`。
2. 打开 `<发行版目录>\setting.toml`，填写模型配置：

```toml
[llm]
base_url = "https://<模型服务地址>/v1"
api_key = "<API Key>"
model = "<模型名>"
timeout = 600
```

3. 在 PowerShell 中进入发行版目录：

```powershell
cd <发行版目录>
```

4. 运行自检：

```powershell
.\att-mz.exe --agent-mode doctor --no-check-llm --json
```

如果要同时检查模型连通性，去掉 `--no-check-llm`：

```powershell
.\att-mz.exe --agent-mode doctor --json
```

## 注册游戏

日文游戏：

```powershell
.\att-mz.exe --agent-mode add-game --path <游戏目录> --source-language ja --json
```

英文游戏：

```powershell
.\att-mz.exe --agent-mode add-game --path <游戏目录> --source-language en --json
```

`add-game` 首次注册只接受干净原始游戏目录；目录内不能已有 `data_origin`、`js/plugins_origin.js` 或 `js/plugins_source_origin`。注册成功后，后续命令使用报告里的 `<游戏标题>`。

## 交给 Agent

用 Agent 打开发行版目录，提交下面这段任务说明：

```text
请使用 <发行版目录>/skills/att-mz/SKILL.md 自动汉化这个 RPG Maker MV/MZ 游戏。

发行版目录：<发行版目录>
游戏目录：<游戏目录>
游戏原文语言：ja 或 en
目标：先完成规则扫描、术语表、正文翻译和质量检查；确认质量报告没有错误后，再把译文写进游戏文件。
要求：所有命令使用 .\att-mz.exe --agent-mode ...；命令契约写有 --json 的步骤必须保留 --json，只导出文件的步骤按 Skill 命令契约使用 --output；不要读取源码；不要直接修改数据库；不要跳过校验。
```

Agent 会按 Skill 流程准备工作区、分析插件和事件指令规则、检查插件源码风险、导入术语表和规则、翻译正文、生成质量报告，并在确认没有无法继续的问题后把译文写进游戏文件。第一次写进游戏文件得到的是第一版可试玩汉化结果；稳定版本需要根据实际游玩反馈继续查缺补漏。翻译和写入前会执行程序硬检查：字段译名表、正文术语表、外部规则和占位符规则不完整时，命令会直接报错；插件源码高风险且未确认处理，或已启动支线但仍有候选未归入翻译或排除时，正文翻译也会停止。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 检查发行版配置 | `.\att-mz.exe --agent-mode doctor --no-check-llm --json` |
| 列出已注册游戏 | `.\att-mz.exe --agent-mode list --json` |
| 注册日文游戏 | `.\att-mz.exe --agent-mode add-game --path <游戏目录> --source-language ja --json` |
| 注册英文游戏 | `.\att-mz.exe --agent-mode add-game --path <游戏目录> --source-language en --json` |
| 准备 Agent 工作区 | `.\att-mz.exe --agent-mode prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --json` |
| 校验 Agent 工作区 | `.\att-mz.exe --agent-mode validate-agent-workspace --game <游戏标题> --workspace <工作区> --output <完整报告> --json` |
| 小批量试翻 | `.\att-mz.exe --agent-mode translate --game <游戏标题> --max-batches 1 --json` |
| 查看翻译状态 | `.\att-mz.exe --agent-mode translation-status --game <游戏标题> --json` |
| 查看当前文本范围 | `.\att-mz.exe --agent-mode text-scope --game <游戏标题> --json` |
| 审计覆盖范围 | `.\att-mz.exe --agent-mode audit-coverage --game <游戏标题> --json` |
| 审计当前运行文件 | `.\att-mz.exe --agent-mode audit-active-runtime --game <游戏标题> --json` |
| 反推当前运行文件问题 | `.\att-mz.exe --agent-mode diagnose-active-runtime --game <游戏标题> --output <诊断文件> --json` |
| 查看质量报告 | `.\att-mz.exe --agent-mode quality-report --game <游戏标题> --json` |
| 把译文写进游戏文件 | `.\att-mz.exe --agent-mode write-back --game <游戏标题> --json` |
| 允许本次写入时覆盖字体引用 | `.\att-mz.exe --agent-mode write-back --game <游戏标题> --confirm-font-overwrite --json` |
| 从可信源快照重建当前运行文件 | `.\att-mz.exe --agent-mode rebuild-active-runtime --game <游戏标题> --json` |
| 按原始备份还原项目覆盖过的字体引用 | `.\att-mz.exe --agent-mode restore-font --game <游戏标题> --json` |
| 按试玩反馈反查原文 | `.\att-mz.exe --agent-mode verify-feedback-text --game <游戏标题> --input <反馈原文清单> --json` |
| 扫描插件源码文本风险 | `.\att-mz.exe --agent-mode scan-plugin-source-text --game <游戏标题> --output <风险报告文件> --json` |
| 导出插件源码 AST 地图 | `.\att-mz.exe --agent-mode export-plugin-source-ast-map --game <游戏标题> --output <AST地图文件> --json` |
| 校验插件源码规则 | `.\att-mz.exe --agent-mode validate-plugin-source-rules --game <游戏标题> --input <规则文件> --json` |
| 导入插件源码规则 | `.\att-mz.exe --agent-mode import-plugin-source-rules --game <游戏标题> --input <规则文件> --json` |

`translation-status` 默认读取数据库中的最近运行统计；需要重新扫描当前文本范围时加 `--refresh-scope`。`text-scope`、`audit-coverage`、`quality-report`、`export-pending-translations` 和 `export-quality-fix-template` 默认不执行写入可行性探针；需要在报告里查看写入可行性时加 `--include-write-probe`。实际写文件命令始终执行写文件前检查。

## 写进游戏文件前

写入前必须先运行：

```powershell
.\att-mz.exe --agent-mode audit-coverage --game <游戏标题> --json
.\att-mz.exe --agent-mode quality-report --game <游戏标题> --json
```

只有报告没有错误、当前规则范围内正文译文完整，并且用户允许写回时，才执行：

```powershell
.\att-mz.exe --agent-mode write-back --game <游戏标题> --json
```

如果报告提示还有没成功保存译文的文本、必须原样保留的游戏控制符风险、源语言残留或某一行太长，先按报告修复，再重新检查。

`quality-report` 只检查已保存译文记录、规则、控制符、源语言残留、行宽和可生成性；它不把当前运行文件当翻译源，也不靠当前运行文件决定是否可以生成。`write-back` 会从注册时保存的可信源快照和已保存译文记录生成文件，并在写入后验收当前运行文件。

如果当前运行文件已经损坏，需要从可信源快照和已保存译文记录重建，使用：

```powershell
.\att-mz.exe --agent-mode rebuild-active-runtime --game <游戏标题> --json
```

`rebuild-active-runtime` 也是写文件操作，必须通过与 `write-back` 相同的覆盖审计、质量报告、完整译文覆盖、可信源快照和字体覆盖确认检查。它用于恢复当前运行文件状态，不能绕过规则、译文质量或完整覆盖要求。

如果 `write-back` 或 `rebuild-active-runtime` 提示当前运行插件源码读取失败或 JS 语法错误，先修复当前运行文件状态后重新写入。`audit-active-runtime` 默认不把插件源码内部源语言字符串当作漏翻清单；只有插件源码支线已启动或已有写回映射时，才把已管理 selector 的源文残留和坏控制符纳入诊断。需要反推到已保存译文时，运行 `diagnose-active-runtime` 生成诊断文件。诊断只解释会阻止写入验收的问题，并使用写回映射反推到已保存译文记录；`mapped_excluded` 表示已审查但不翻译，没有映射时会明确报告无法反推，不会按当前 JS 文本猜测。修复必须回到规则和已保存译文记录，再重新写进游戏文件。

## 字体处理

普通写入不会改字体引用。只有明确传入 `--confirm-font-overwrite` 时，工具才会按 `setting.toml` 的候选字体配置替换游戏字体引用。

若需要撤回项目覆盖过的字体引用：

```powershell
.\att-mz.exe --agent-mode restore-font --game <游戏标题> --json
```

## 数据位置

- 已注册游戏和译文记录：`<发行版目录>\data\db`
- 日志：`<发行版目录>\logs`
- Agent 临时工作区：由 `prepare-agent-workspace --output-dir <工作区>` 指定
- 写入时修改的游戏文件：目标游戏目录内的 RPG Maker 数据文件和插件配置
- 注册游戏时创建的可信源快照：目标游戏目录内的 `data_origin`、`js/plugins_origin.js` 和 `js/plugins_source_origin`

## 出错时怎么做

- 命令返回 `status=error` 时，不要继续下一步，先按报告修复原因。
- 配置错误先运行 `doctor`。
- 规则文件错误先运行对应的 `validate-...` 命令。
- 翻译质量错误先导出质量修复表或手动译文表，修好后重新导入。
- 写入后试玩发现原文，先整理反馈原文清单，再运行 `verify-feedback-text` 反查位置。
