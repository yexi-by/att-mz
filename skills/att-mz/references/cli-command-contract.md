# CLI 命令契约

本文件记录开发版 Skill 使用的命令入口、阶段用途、成功判断和失败处理。命令必须在 `<项目目录>` 执行，默认前缀是：

```powershell
uv run python main.py --agent-mode <命令> ...
```

需要机器读取结果时使用 `--json` 或 `--output <文件>`。长任务会在 stderr 输出无 ANSI 进度行，stdout 的最终 JSON 才是命令结果。

`validate-agent-workspace` 和 `validate-mv-virtual-namebox-rules` 的 `--json` stdout 是摘要报告；需要完整 `details` 明细时加 `--output <完整报告>`，stdout 仍只读摘要。

文件型规则一律用 `--input <文件>`，不要用 `--rules "$(cat ...)"`，不要把大 JSON 塞进命令行。

## 编码与 Windows 终端

- 所有工作区 JSON、临时脚本、手动填写译文表、规则文件和交付报告都必须按 UTF-8 读写，禁止依赖 Windows 默认编码、ANSI、GBK 或 Shift-JIS。
- 写 JSON 时保持中日英原文可读性；Python 使用 `json.dumps(..., ensure_ascii=False)` 并显式 `encoding="utf-8"`。
- 自写临时脚本必须显式声明编码：Python 使用 `Path.read_text/write_text(..., encoding="utf-8")` 或 `open(..., encoding="utf-8")`；Node.js 使用 `fs.readFile/writeFile(..., "utf8")`；PowerShell 写文件必须显式 `-Encoding utf8`。
- Windows 终端 stdout 出现乱码时，先在同一 shell 设置 UTF-8 后重跑命令，不要基于乱码内容修改 JSON、规则或译文。

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

- 控制符、括号和引号边界不能只看终端显示；遇到乱码、非 ASCII 引号、全角括号或 `\` 控制片段异常时，必须核验 Unicode code point 或原始字节，再决定规则和译文。
- 正文译文保存和写进游戏文件前会自动按源文槽位整理 `「」「『』` 包裹符号；这属于标点整理能力，不作为 `quality-report` 问题项。
- `--json` 命令的 stdout 只读取最终 JSON；stderr 进度行不能当作命令结果 JSON。

## 环境与注册

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `list --json` | 列出当前已注册游戏 | 游戏清单可读取 | 未注册时先执行 add-game |
| `doctor --no-check-llm --json` | 检查项目静态环境，不请求模型服务 | `status` 不是 `error` | 修环境后重跑，不启动翻译 |
| `add-game --path <游戏目录> --source-language ja --json` | 按日文源语言注册干净原始游戏目录 | `summary.game_title` 可用于后续 `--game` | 目录已有可信源快照时换用干净原始游戏目录 |
| `add-game --path <游戏目录> --source-language en --json` | 按英文源语言注册干净原始游戏目录 | `summary.game_title` 可用于后续 `--game` | 目录已有可信源快照时换用干净原始游戏目录 |
| `doctor --game <游戏标题> --no-check-llm --json` | 检查游戏绑定和规则状态 | `status` 不是 `error` | 缺规则时只允许继续准备工作区，不启动翻译或写回 |

注册游戏必须显式传 `--source-language ja` 或 `--source-language en`，不做语言自动检测。

## 工作区与规则导入

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --json` | 导出候选文件、规则草稿和已保存规则；需要覆盖事件指令默认编码时加 `--code CODE` | 工作区文件存在，`summary.workspace` 指向目标目录，`summary.event_command_codes` 可解释 | 删除不完整工作区后重跑 |
| `validate-agent-workspace --game <游戏标题> --workspace <工作区> --output <完整报告> --json` | 总体验收工作区和规则覆盖；stdout 摘要、完整明细写入报告文件 | 无 `errors` | 逐项修工作区 JSON 后重跑 |
| `cleanup-agent-workspace --workspace <工作区> --json` | 清理 CLI 生成的工作区文件 | 命令返回 0 | 缺 `manifest.json` 时先人工确认范围 |
| `export-plugins-json --game <游戏标题> --output <plugins.json>` | 单独导出当前插件配置 JSON | 输出文件存在 | 重新检查游戏注册和 `js/plugins.js` |
| `export-event-commands-json --game <游戏标题> --output <候选文件>` | 单独导出配置默认编码的事件指令候选 | 输出文件存在，候选数量可解释 | 需要覆盖默认编码时显式加 `--code CODE` 后重跑 |

## MV 虚拟名字框

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `export-mv-virtual-namebox-candidates --game <游戏标题> --output <候选文件> --json` | 单独导出 MV 候选 | 输出文件存在；MZ 调用返回 error | 候选为空时可确认空规则 |
| `validate-mv-virtual-namebox-rules --game <游戏标题> --input <规则文件> --output <完整报告> --json` | 校验正则、模板和新增命中；stdout 摘要、完整明细写入报告文件 | `status` 不是 `error`，且新增命中样本已确认 | 修规则文件后重跑 |
| `import-mv-virtual-namebox-rules --game <游戏标题> --input <规则文件> --json` | 保存当前 MV 游戏规则 | `status` 为 `ok`；空规则需 `--confirm-empty` | 导入后重新准备工作区 |

## 术语与外部文本规则

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `export-terminology --game <游戏标题> --output-dir <术语工作目录>` | 导出术语表工程 JSON 和只读上下文 | 输出目录包含字段译名表、正文术语表和子任务文件 | 删除不完整目录后重跑 |
| `import-terminology --game <游戏标题> --input <字段译名表> --glossary-input <正文术语表> --json` | 保存字段译名表和正文术语表 | `status` 为 `ok` | 修结构、空值或冲突后重跑 |
| `validate-plugin-rules --game <游戏标题> --input <规则文件> --json` | 校验插件规则路径、字符串叶子命中和当前插件配置哈希 | `status` 为 `ok` | 修 `plugin-rules.json` 后重跑；如果提示插件哈希或当前配置不一致，重新准备工作区，不猜路径 |
| `import-plugin-rules --game <游戏标题> --input <规则文件> --json` | 保存插件文本规则 | `status` 为 `ok`；空规则需 `--confirm-empty`；或备份 warning 已记录 | 导错时先导入正确规则，再用备份恢复译文 |
| `export-plugin-source-ast-map --game <游戏标题> --output <AST地图文件> --json` | 用户确认高风险后导出插件源码 AST 地图；默认 `--view translation-source` | 输出文件存在，风险摘要、候选数量和 `summary.source_view` 可解释 | 只处理 `js/plugins` 直接 `.js` 文件；需要审计当前运行文件时显式传 `--view active-runtime` |
| `validate-plugin-source-rules --game <游戏标题> --input <规则文件> --json` | 校验插件源码 selector、排除 selector 和当前源码哈希 | `status` 为 `ok`，且高风险或已启动支线时未审查 selector 数为 0 | 修 `plugin-source-rules.json` 后重跑；selector 失效时重新导出 AST 地图 |
| `import-plugin-source-rules --game <游戏标题> --input <规则文件> --json` | 保存插件源码文本规则 | `status` 为 `ok`，且高风险或已启动支线时未审查 selector 数为 0 | 导入后重新扫描占位符候选，再进入正文翻译 |
| `validate-event-command-rules --game <游戏标题> --input <规则文件> --json` | 校验事件指令编码、match 和路径 | 无 `errors` | 修 `event-command-rules.json` 后重跑 |
| `import-event-command-rules --game <游戏标题> --input <规则文件> --json` | 保存事件指令文本规则 | `status` 为 `ok`；空规则需 `--confirm-empty`；若候选用 `--code` 导出，空规则导入也传同一组 `--code CODE`；或备份 warning 已记录 | 导错时先导入正确规则，再用备份恢复译文 |
| `export-note-tag-candidates --game <游戏标题> --output <文件> --json` | 单独导出 Note 标签候选 | 输出文件存在，候选数量可解释 | 异常时检查游戏注册和文件结构 |
| `validate-note-tag-rules --game <游戏标题> --input <规则文件> --json` | 校验 Note 标签规则 | 无 `errors` | 修 `note-tag-rules.json` 后重跑 |
| `import-note-tag-rules --game <游戏标题> --input <规则文件> --json` | 保存 Note 标签文本规则 | `status` 为 `ok`；空规则需 `--confirm-empty` | 导错时先导入正确规则，再用备份恢复译文 |

导入命令返回 `deleted_translations_backed_up` warning 时，表示规则变化清理了不再属于当前规则范围的已保存译文。备份文件路径在 `summary.deleted_translation_backup_path` 或 `details.deleted_translation_backup.path`。确认导错时，先导入正确规则，再用备份文件通过 `import-manual-translations` 恢复。

## 占位符规则

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `build-placeholder-rules --game <游戏标题> --output <规则文件> --json` | 基于当前正文集合生成普通占位符草稿 | 输出文件存在 | 查看 `errors`，不要手写替代导出 |
| `validate-placeholder-rules --game <游戏标题> --input <规则文件> --json` | 校验正则、模板和样本文本往返 | `status` 为 `ok` 或只有可接受 warning | 修规则后重跑 |
| `scan-placeholder-candidates --game <游戏标题> --input <规则文件> --json` | 扫描普通占位符候选覆盖 | `summary.uncovered_count == 0` | 未覆盖时修规则，再 validate 和 scan |
| `import-placeholder-rules --game <游戏标题> --input <规则文件> --json` | 保存普通占位符规则 | `status` 为 `ok`；空规则需 `--confirm-empty` | 回到 validate/scan 修规则 |
| `validate-structured-placeholder-rules --game <游戏标题> --input <规则文件> --json` | 校验结构化规则 | `status` 不是 `error` | 修规则后重跑 |
| `scan-structured-placeholder-candidates --game <游戏标题> --input <规则文件> --json` | 扫描结构化候选覆盖 | 覆盖风险已确认 | 未覆盖时修规则，再 validate 和 scan |
| `import-structured-placeholder-rules --game <游戏标题> --input <规则文件> --json` | 保存结构化规则 | `status` 为 `ok`；空规则需确认 | 回到 validate/scan 修规则 |

## 翻译、检查和手动修复

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `translate --game <游戏标题> --max-batches 1 --json` | 小批量试跑正文翻译 | 命令正常结束，质量报告无新增规则性事故 | 看状态和质量报告，不盲目全量 |
| `translate --game <游戏标题> --json` | 继续翻译还没成功保存译文的文本 | 剩余量下降且质量风险可解释 | 连续多轮不下降时转修规则、换模型或手动处理 |
| `run-all --game <游戏标题> --skip-write-back` | 按固定顺序翻译正文但不写进游戏文件 | 翻译状态可解释，质量检查可继续 | 规则或质量错误未清前不写回 |
| `run-all --game <游戏标题> --confirm-font-overwrite` | 翻译后执行最终写回并允许字体覆盖 | 用户已单独确认字体覆盖，命令正常结束 | 未确认字体覆盖时不使用 |
| `translation-status --game <游戏标题> --json` | 查看已保存、剩余和模型失败数量 | 数量能解释 | 数量下降时继续翻译，停滞时分析失败类型 |
| `text-scope --game <游戏标题> --json` | 查看统一文本范围和规则来源 | `status` 为 `ok` | 发现规则命中但不可翻译时先修规则 |
| `audit-coverage --game <游戏标题> --json` | 对比规则命中、译文和可写范围 | `status` 为 `ok` | 补规则、补译文或精确重置 |
| `audit-active-runtime --game <游戏标题> --json` | 直接审计当前游戏运行文件里的插件源码漏翻、坏控制符和 JS 语法错误 | `status` 为 `ok`，`summary.source_view` 为 `active-runtime` | 有 error 时运行 `diagnose-active-runtime` 反推已保存译文记录 |
| `diagnose-active-runtime --game <游戏标题> --output <诊断文件> --json` | 用写回映射诊断当前运行插件源码阻塞问题 | 输出文件存在，`summary.diagnosis_issue_count` 与 error 数量可解释 | 映射缺失或文件变化时重新执行 `rebuild-active-runtime`；已映射问题回到规则、重置或手动译文 |
| `quality-report --game <游戏标题> --json` | 判断已保存译文记录、规则、控制符、源文残留、行宽和可生成性是否允许写回 | `status` 不是 `error` | 按明细修译文或规则；有 error 禁止写回 |
| `export-quality-fix-template --game <游戏标题> --output <文件> --json` | 导出检查没通过译文的修复表 | 输出文件存在，数量可解释 | 只改中文译文行后导入 |
| `export-pending-translations --game <游戏标题> --output <文件> --json` | 导出还没成功保存译文的文本表 | 输出文件存在；可加 `--limit N` | 抽样显示仍适合模型时回到翻译 |
| `import-manual-translations --game <游戏标题> --input <文件> --json` | 检查并保存手动填写译文 | `status` 为 `ok` | 修中文译文行后重跑 |
| `reset-translations --game <游戏标题> --input <文件> --json` | 精确删除坏译文，让模型重译 | `summary.mode=input` 且数量可解释 | 非法路径整体失败；修输入文件 |
| `reset-translations --game <游戏标题> --all --json` | 用户明确选择完整重译时删除当前提取范围译文 | `summary.mode=all` 且数量可解释 | 数量异常时先解释，不手工拼全集 |
| `validate-source-residual-rules --game <游戏标题> --input <规则文件> --json` | 校验源文保留例外 | `status` 为 `ok` | 修例外规则，不关闭全局检测 |
| `import-source-residual-rules --game <游戏标题> --input <规则文件> --json` | 保存源文保留例外 | `status` 为 `ok` | 回到 validate 修规则 |

日文和英文游戏都使用通用源文残留命令。源文保留例外只用于确实不应翻译的片段，不能掩盖整句漏翻。

## 写进游戏文件与反馈定位

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `write-back --game <游戏标题> --json` | 把译文写进游戏文件 | 命令返回 0 且摘要可读 | 停止交付，按错误修质量或规则 |
| `write-back --game <游戏标题> --confirm-font-overwrite --json` | 写回并覆盖字体引用 | 用户已单独确认字体覆盖，摘要可解释 | 未确认字体覆盖时不使用 |
| `rebuild-active-runtime --game <游戏标题> --json` | 从可信源快照和已保存译文重建当前运行文件 | 命令返回 0，随后 `audit-active-runtime` 无 error | 质量问题未清时先修缓存、规则或重置译文 |
| `rebuild-active-runtime --game <游戏标题> --confirm-font-overwrite --json` | 重建运行文件并允许字体覆盖 | 用户已单独确认字体覆盖，摘要可解释 | 未确认字体覆盖时不使用 |
| `write-terminology --game <游戏标题>` | 在写回前流程检查通过后写入稳定名词，并保留已保存且可写的正文译文 | 命令返回 0，写入范围可解释 | 术语表、规则前置或质量风险未通过时停止 |
| `write-terminology --game <游戏标题> --confirm-font-overwrite` | 写入稳定名词并允许字体覆盖 | 用户已单独确认字体覆盖，且写回前流程检查通过 | 未确认字体覆盖时不使用 |
| `restore-font --game <游戏标题> --json` | 按原件还原项目覆盖过的字体引用 | 摘要可解释 | 缺原始备份或替换字体信息时停止说明 |
| `verify-feedback-text --game <游戏标题> --input <反馈原文清单> --json` | 在真实游戏文件中反查反馈原文 | `status` 为 `ok`，分类可解释 | 按规则缺口、译文缺口、写入缺口或插件源码硬编码分类处理 |
| `scan-plugin-source-text --game <游戏标题> --output <风险报告文件> --json` | 扫描插件源码文本风险摘要；默认 `--view translation-source` | 输出文件存在，且不包含 AST selector 或完整候选列表，`summary.source_view` 可解释 | 高风险时暂停正文翻译；需要看当前运行文件时显式传 `--view active-runtime` |
