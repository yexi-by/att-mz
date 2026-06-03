# CLI 命令契约

本文件记录开发版 Skill 使用的命令入口、阶段用途、成功判断和失败处理。命令必须在 `<项目目录>` 执行，默认前缀是：

```powershell
uv run python main.py <命令> ...
```

所有命令 stdout 默认输出机器可读 JSON；需要完整明细或业务文件时使用 `--output <文件>`。长任务会在 stderr 输出无 ANSI 进度行，stdout 的最终 JSON 才是命令结果。

`validate-agent-workspace` 和 `validate-mv-virtual-namebox-rules` 的 stdout 是摘要报告；需要完整 `details` 明细时加 `--output <完整报告>`，stdout 仍只读摘要。

规则候选、覆盖扫描和大数组报告会在 `summary.report_detail_mode` 标明明细模式：`sampled` 表示 stdout 只含 `{count, samples, omitted_count}` 样本，不能据此计算 hash、确认范围或补规则；`full` 表示报告含完整 `{count, items}` 或等价完整字段。需要审查全部候选、排查覆盖计数或派发外部 Agent 时，必须使用 `--output <完整报告>` 读取 full 明细。

文件型规则一律用 `--input <文件>`，不要用 `--rules "$(cat ...)"`，不要把大 JSON 塞进命令行。

用户可写正则会在 validate/import、工作区验收和读取当前游戏已保存规则时提前预检。普通占位符、结构化占位符和 MV 虚拟名字框规则必须同时兼容 Python `re` 与 Rust `fancy-regex`；源文残留结构规则和会进入 Rust 的 `[text_rules]` 正则必须同时兼容 Python `re` 与 Rust `regex`。命名分组统一使用 `(?P<name>...)`。Note 标签文件键是 `fnmatch` 通配模式，不是正则。

## 配置与参数选择

- 第一次执行某个阶段时，业务参数和可调开关默认使用 `setting.toml` 与本地配置；命令行只传当前命令必需的定位参数，例如 `--game`、`--path`、`--input`、`--output`、`--workspace`、`--output-dir`，以及已满足前置条件的确认参数。
- 用户明确指定值、CLI 契约要求显式传入，或 CLI 输出说明默认配置缺失、冲突、不适合当前游戏或当前阶段时，立即改用最小范围覆盖：一次性差异用 CLI 参数，运行时性能差异用环境变量，长期稳定差异再调整本地配置。
- 模型地址和 API Key 的当前环境变量只使用 `ATT_MZ_LLM_BASE_URL`、`ATT_MZ_LLM_API_KEY`；旧项目前缀的模型环境变量不再作为成功配置入口，出现时按 CLI JSON 错误处理。
- 不要反复用同一套失败配置重试。确认是配置问题后，先根据 CLI 摘要、工作区文件和用户已给信息自行选择合理覆盖；只有涉及模型密钥、费用风险、写文件许可或多种业务结果都合理时，才停下来问用户。
- 使用覆盖参数后，后续关联命令必须保持同一语义。例如工作区用显式 `--code` 导出事件指令候选时，导入空事件指令规则也要传同一组 `--code CODE`。

## 性能与 Rust 线程

- Rust 热路径线程数由环境变量 `ATT_MZ_RUST_THREADS` 控制；该值没有 `4` 的上限，必须是非负整数。
- `ATT_MZ_RUST_THREADS=0` 或不设置时使用 Rayon 默认线程池；默认先沿用 `setting.toml` 与当前环境，不为了性能基线一开始固定传线程数。
- 默认线程配置导致吞吐明显不足、CLI 输出提示线程配置不合适、用户要求性能优先，或当前机器是专用运行机器时，再显式设置为合适的逻辑处理器数量。Windows PowerShell 可用 `(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors` 获取逻辑处理器数量。
- 如果用户指定线程数，以用户指定为准。不要把性能门禁里的 `4` 当运行上限，`4` 只是可重复基线和阈值比较用配置。

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
- CLI stdout 只读取最终 JSON；stderr 进度行不能当作命令结果 JSON。

## 环境与注册

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `list` | 列出当前可读取的已注册游戏；旧库、坏库或外部 SQLite 会进入 warning 并跳过 | 命令返回 0，`summary.game_count` 和 `summary.skipped_database_count` 可解释 | 需要继续使用被跳过游戏时，按 warning 说明重新注册或修复对应库 |
| `doctor --no-check-llm` | 检查项目静态环境，不请求模型服务；无 `--game` 时日志里的语言档案只是默认配置，不是当前游戏源语言 | `status` 不是 `error`，`summary.llm_connection_status` 为 `skipped` | 修环境后重跑，不启动翻译，不把默认语言档案当作注册依据 |
| `probe-source-language --path <游戏目录> --output <探测报告>` | 注册前只按玩家可见文本探测源语言，排除资源名、公式、ID、脚本和协议值 | `summary.recommended_source_language` 为 `ja`、`en` 或 `uncertain`；命令不注册游戏、不写数据库、不创建可信源快照 | 不确定或与用户认知冲突时展示样本让用户确认，禁止用 grep 假名或英文字符代替 |
| `add-game --path <游戏目录> --source-language ja` | 按日文源语言注册干净原始游戏目录 | `summary.game_title` 可用于后续 `--game` | 目录已有可信源快照时换用干净原始游戏目录 |
| `add-game --path <游戏目录> --source-language en` | 按英文源语言注册干净原始游戏目录 | `summary.game_title` 可用于后续 `--game` | 目录已有可信源快照时换用干净原始游戏目录 |
| `doctor --game <游戏标题> --no-check-llm` | 检查游戏绑定和规则状态；当前游戏源语言只看 `summary.source_language` | `status` 不是 `error`，`summary.llm_connection_status` 为 `skipped` | 缺规则时只允许继续准备工作区，不启动翻译或写回 |
| `reset-game --game <游戏标题> --dry-run` | 危险回溯预演：只列出将恢复的运行文件和将删除的注册痕迹 | `summary.changed` 为 `false`，`details.restore` 和 `details.delete.paths` 可解释 | 真正执行前把计划转述给用户确认 |
| `reset-game --game <游戏标题> --confirm-game-title <游戏标题>` | 用户明确要求时，把当前运行文件恢复到可信源快照，再删除 `data_origin`、`plugins_origin.js`、`plugins_source_origin`、`gamefont_origin.css` 和游戏数据库 | `summary.changed` 为 `true`；后续该游戏不再注册，需要重新 `add-game` | 确认标题不匹配、可信源快照缺失或校验失败时停止；禁止手动删库绕过恢复 |

注册游戏必须先运行 `probe-source-language --path <游戏目录>`，再显式传 `--source-language ja` 或 `--source-language en`。探测命令只提供分析报告，`add-game` 不读取探测报告，也不会自动替用户决定或阻止源语言选择。

`reset-game` 只能在用户明确要求注销、重置或恢复到注册前状态时使用。执行顺序固定为先恢复当前运行文件，再删除注册痕迹；如果报告提示字体文件清单没有注册快照，只能说明该边界，不能自行删除无法证明由本项目创建的字体文件。

## 工作区与规则导入

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `prepare-agent-workspace --game <游戏标题> --output-dir <工作区>` | 导出候选文件、规则草稿和已保存规则；需要覆盖事件指令默认编码时加 `--code CODE` | 工作区文件存在，`summary.workspace` 指向目标目录，`summary.event_command_codes` 可解释 | 删除不完整工作区后重跑 |
| `validate-agent-workspace --game <游戏标题> --workspace <工作区> --output <完整报告>` | 总体验收工作区和规则覆盖；stdout 摘要、完整明细写入报告文件 | 无 `errors` | 逐项修工作区 JSON 后重跑 |
| `cleanup-agent-workspace --workspace <工作区>` | 清理 CLI 生成的工作区文件 | 命令返回 0 | 缺 `manifest.json` 时先人工确认范围 |
| `export-plugins-json --game <游戏标题> --output <plugins.json>` | 单独导出当前插件配置 JSON | 输出文件存在 | 重新检查游戏注册和 `js/plugins.js` |
| `export-event-commands-json --game <游戏标题> --output <候选文件>` | 单独导出配置默认编码的事件指令候选 | 输出文件存在，`summary.command_codes` 和候选数量可解释 | 需要覆盖默认编码时显式加 `--code CODE` 后重跑 |

## MV 虚拟名字框

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `export-mv-virtual-namebox-candidates --game <游戏标题> --output <候选文件>` | 单独导出 MV 候选 | 输出文件存在；MZ 调用返回 error | 候选为空时可确认空规则 |
| `validate-mv-virtual-namebox-rules --game <游戏标题> --input <规则文件> --output <完整报告>` | 校验正则、模板和新增命中；stdout 摘要、完整明细写入报告文件 | `status` 不是 `error`，且新增命中样本已确认 | 修规则文件后重跑 |
| `import-mv-virtual-namebox-rules --game <游戏标题> --input <规则文件>` | 保存当前 MV 游戏规则 | `status` 为 `ok`；空规则需 `--confirm-empty` | 导入后重新准备工作区 |

## 术语与外部文本规则

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `export-terminology --game <游戏标题> --output-dir <术语工作目录>` | 导出术语表工程 JSON 和只读上下文 | 输出目录包含字段译名表、正文术语表和子任务文件 | 删除不完整目录后重跑 |
| `import-terminology --game <游戏标题> --input <字段译名表> --glossary-input <正文术语表>` | 保存字段译名表和正文术语表 | `status` 为 `ok` | 修结构、空值或冲突后重跑 |
| `validate-plugin-rules --game <游戏标题> --input <规则文件>` | 校验插件规则路径、字符串叶子命中和当前插件配置哈希 | `status` 为 `ok` | 修 `plugin-rules.json` 后重跑；如果提示插件哈希或当前配置不一致，重新准备工作区，不猜路径 |
| `import-plugin-rules --game <游戏标题> --input <规则文件>` | 保存插件文本规则 | `status` 为 `ok`；空规则需 `--confirm-empty`；或备份 warning 已记录 | 导错时先导入正确规则，再用备份恢复译文 |
| `export-plugin-source-ast-map --game <游戏标题> --output <AST地图文件>` | 用户确认高风险后导出插件源码 AST 地图；默认 `--view translation-source` | 输出文件存在，风险摘要、候选数量和 `summary.source_view` 可解释 | 只处理 `js/plugins` 直接 `.js` 文件；需要审计当前运行文件时显式传 `--view active-runtime` |
| `validate-plugin-source-rules --game <游戏标题> --input <规则文件>` | 校验插件源码 selector、排除 selector 和当前源码哈希 | `status` 为 `ok`，且高风险或已启动支线时未审查 selector 数为 0 | 修 `plugin-source-rules.json` 后重跑；selector 失效时重新导出 AST 地图 |
| `import-plugin-source-rules --game <游戏标题> --input <规则文件>` | 保存插件源码文本规则 | `status` 为 `ok`，且高风险或已启动支线时未审查 selector 数为 0 | 导入后重新扫描占位符候选，再进入正文翻译 |
| `scan-nonstandard-data --game <游戏标题> --output <风险报告文件>` | 扫描非标准 data 文件文本风险摘要 | 输出文件存在；高风险时返回 warning 并给出候选数量 | 高风险时导出候选并填写规则，或按文件确认跳过 |
| `export-nonstandard-data-json --game <游戏标题> --output-dir <工作区>/nonstandard-data` | 导出非标准 data 文件候选报告和原始 JSON 副本 | 输出目录包含 `candidates.json` 和 `source/*.json` | 删除不完整目录后重跑，不读源码猜路径 |
| `validate-nonstandard-data-rules --game <游戏标题> --input <规则文件>` | 校验非标准 data 文件文本规则、路径命中和候选全量归类 | 无 `errors`；跳过文件只允许出现 warning | 修 `nonstandard-data-rules.json` 后重跑；路径失效时重新导出候选 |
| `import-nonstandard-data-rules --game <游戏标题> --input <规则文件>` | 保存非标准 data 文件文本规则 | `status` 为 `ok`；跳过文件只允许出现 warning | 导入后重新扫描占位符候选，再进入正文翻译 |
| `validate-event-command-rules --game <游戏标题> --input <规则文件>` | 校验事件指令编码、match 和路径 | 无 `errors` | 修 `event-command-rules.json` 后重跑 |
| `import-event-command-rules --game <游戏标题> --input <规则文件>` | 保存事件指令文本规则 | `status` 为 `ok`；空规则需 `--confirm-empty`；若候选用 `--code` 导出，空规则导入也传同一组 `--code CODE`；或备份 warning 已记录 | 导错时先导入正确规则，再用备份恢复译文 |
| `export-note-tag-candidates --game <游戏标题> --output <文件>` | 单独导出 Note 标签候选 | 输出文件存在，候选数量可解释 | 异常时检查游戏注册和文件结构 |
| `validate-note-tag-rules --game <游戏标题> --input <规则文件>` | 校验 Note 标签规则 | 无 `errors` | 修 `note-tag-rules.json` 后重跑 |
| `import-note-tag-rules --game <游戏标题> --input <规则文件>` | 保存 Note 标签文本规则 | `status` 为 `ok`；空规则需 `--confirm-empty` | 导错时先导入正确规则，再用备份恢复译文 |

导入命令返回 `deleted_translations_backed_up` warning 时，表示规则变化清理了不再属于当前规则范围的已保存译文。备份文件路径在 `summary.deleted_translation_backup_path` 或 `details.deleted_translation_backup.path`。确认导错时，先导入正确规则，再用备份文件通过 `import-manual-translations` 恢复。

## 占位符规则

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `build-placeholder-rules --game <游戏标题> --output <规则文件>` | 基于当前正文集合生成普通占位符草稿 | 输出文件存在 | 查看 `errors`，不要手写替代导出 |
| `validate-placeholder-rules --game <游戏标题> --input <规则文件>` | 校验正则、模板和样本文本往返 | `status` 为 `ok` 或只有可接受 warning | 修规则后重跑 |
| `scan-placeholder-candidates --game <游戏标题> --input <规则文件>` | 扫描普通占位符候选覆盖 | 规则命中可解释，未覆盖候选已修规则或确认风险 | 未覆盖且无法确认时修规则，再 validate 和 scan |
| `import-placeholder-rules --game <游戏标题> --input <规则文件>` | 保存普通占位符规则 | `status` 为 `ok` 或可接受 warning；空规则需 `--confirm-empty`；未覆盖候选会保存已确认风险 | 导入失败时回到 validate/scan 修规则，不编造规则 |
| `validate-structured-placeholder-rules --game <游戏标题> --input <规则文件>` | 校验结构化规则 | `status` 不是 `error` | 修规则后重跑 |
| `scan-structured-placeholder-candidates --game <游戏标题> --input <规则文件>` | 扫描结构化候选覆盖 | 规则命中可解释，覆盖风险已处理或已确认 | 未覆盖且无法确认时修规则，再 validate 和 scan |
| `import-structured-placeholder-rules --game <游戏标题> --input <规则文件>` | 保存结构化规则 | `status` 为 `ok` 或可接受 warning；空规则需 `--confirm-empty`；未覆盖候选会保存已确认风险 | 导入失败时回到 validate/scan 修规则，不编造规则 |

普通占位符未确认风险时使用 `placeholder_uncovered` error，确认风险后在 `doctor`、`text-scope`、`audit-coverage` 和 `quality-report` 中使用 `placeholder_uncovered_reviewed` warning。结构化占位符对应 `structured_placeholder_uncovered` error 和 `structured_placeholder_uncovered_reviewed` warning。旧版样本确认不再作为当前确认依据；如果候选范围变化或旧确认过期，必须重新导出、审查并导入当前规则。warning 只表示流程可继续，不表示译文可以改坏协议片段；坏控制符仍会在保存或写文件前成为质量 error。

## 翻译、检查和手动修复

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `rebuild-text-index --game <游戏标题>` | 重建当前翻译源视图的持久文本范围索引；大型游戏规则导入、源文件变化或规则变化后先运行 | `summary.index_status=rebuilt`，索引数量可解释，`summary.elapsed_ms`、`summary.stage_timings` 和 `summary.native_thread_count` 能解释 cold rebuild 耗时；cold rebuild 是首次全量扫描 | 报错时先修规则、可信源快照或文本范围问题，不让小任务静默回退全量扫描 |
| `translate --game <游戏标题> --max-items 3` | 使用文本范围索引做小批量正文翻译试跑；索引缺失或过期时自动重建，然后 SQL 层只取本轮数量 | 命令正常结束，`summary.pending_count` 是本轮数量，`summary.total_pending_count` 是当前总剩余数量，`summary.text_index_status` 可解释索引来源 | 索引重建失败时先修规则、可信源快照或文本范围问题；质量报告有规则性事故时先修规则 |
| `translate --game <游戏标题>` | 继续翻译还没成功保存译文的文本 | 剩余量下降且质量风险可解释 | 连续多轮不下降时转修规则、换模型或手动处理 |
| `run-all --game <游戏标题> --skip-write-back` | 按固定顺序翻译正文但不写进游戏文件 | `status` 为 `ok`，摘要说明写文件阶段已跳过 | 规则或质量错误未清前不写回 |
| `run-all --game <游戏标题> --confirm-font-overwrite` | 翻译后执行最终写回并允许字体覆盖 | 用户已单独确认字体覆盖，摘要包含翻译和写文件结果 | 未确认字体覆盖时不使用 |
| `translation-status --game <游戏标题>` | 快速查看最近运行、已保存译文和模型失败数量 | 数量能解释；需按当前范围刷新时加 `--refresh-scope`，warm index 下优先用索引，索引缺失或过期时自动重建并在 `summary.text_index_status` 标明原因 | 数量下降时继续翻译，停滞时分析失败类型 |
| `text-scope --game <游戏标题>` | 查看统一文本范围和规则来源 | `status` 为 `ok`；需检查写入可行性时加 `--include-write-probe` | 发现规则命中但不可翻译时先修规则 |
| `audit-coverage --game <游戏标题>` | 对比规则命中、译文和当前文本范围 | `status` 为 `ok`；需检查写入可行性时加 `--include-write-probe` | 补规则、补译文或精确重置 |
| `audit-active-runtime --game <游戏标题>` | 审计当前运行插件源码完整性；默认只阻断读取失败和 JS 语法错误，插件源码支线已启动或已有写回映射时才审计已管理 selector 的文本残留和坏控制符 | `status` 为 `ok`，`summary.source_view` 为 `active-runtime`；普通流程不要把源语言字符串告警当漏翻清单 | 有 error 时运行 `diagnose-active-runtime` 反推已保存译文记录或确认映射缺失 |
| `diagnose-active-runtime --game <游戏标题> --output <诊断文件>` | 用写回映射诊断当前运行插件源码阻塞问题 | 输出文件存在，`summary.diagnosis_issue_count` 与 error 数量可解释；`mapped_excluded` 不进入重置清单 | 映射缺失时报告无法反推；已映射翻译问题回到规则、重置或手动译文 |
| `quality-report --game <游戏标题>` | 使用索引和已保存译文做普通质量报告；默认不执行写入可行性探针；索引缺失或过期时会先自动重建并在 `summary.text_index_status` 标明 `cold_rebuilt` 或 `stale_rebuilt` | `status` 不是 `error`；需要写回级检查时加 `--include-write-probe` | 按明细修译文或规则；有 error 禁止写回 |
| `export-quality-fix-template --game <游戏标题> --output <文件>` | 导出检查没通过译文的修复表 | 输出文件存在，数量可解释；需检查写入可行性时加 `--include-write-probe` | 只改中文译文行后导入 |
| `export-pending-translations --game <游戏标题> --output <文件>` | 导出还没成功保存译文的文本表 | 输出文件存在；可加 `--limit N`；需检查写入可行性时加 `--include-write-probe` | 抽样显示仍适合模型时回到翻译 |
| `import-manual-translations --game <游戏标题> --input <文件>` | 按输入路径检查并保存手动填写译文；普通待补译导入依赖文本范围索引，索引缺失或过期时自动重建并在 `summary.text_index_status` 标明原因 | `status` 为 `ok` | 质量错误时只修中文译文行后重跑；索引重建失败时先修规则、可信源快照或文本范围问题 |
| `reset-translations --game <游戏标题> --input <文件>` | 按输入路径精确删除坏译文，让模型重译；索引缺失或过期时自动重建，输入路径必须全部属于当前文本范围 | `summary.mode=input` 且数量可解释；未保存路径会作为 warning 报告 | 路径不属于当前范围时整体失败且不部分删除；数量异常时先核对输入文件，不手工拼全集 |
| `reset-translations --game <游戏标题> --all` | 用户明确选择完整重译时删除当前提取范围译文 | `summary.mode=all` 且数量可解释 | 数量异常时先解释，不手工拼全集 |
| `validate-source-residual-rules --game <游戏标题> --input <规则文件>` | 校验源文保留例外 | `status` 为 `ok` | 修例外规则，不关闭全局检测 |
| `import-source-residual-rules --game <游戏标题> --input <规则文件>` | 保存源文保留例外 | `status` 为 `ok` | 回到 validate 修规则 |

日文和英文游戏都使用通用源文残留命令。英文残留检查偏高精度，主要报告译文连续复制当前原文的大段英文；源文保留例外只用于确实不应翻译且被报告的片段，不能掩盖整句漏翻。

## 写进游戏文件与反馈定位

`write-back` 和 `rebuild-active-runtime` 都是写文件操作，成功前提相同：覆盖审计和质量报告没有 error、可信源快照有效、当前规则范围内正文译文完整、字体覆盖已单独确认。`write-terminology` 是术语专用写入，允许正文仍有还没成功保存译文的文本，但不能跳过术语表、规则前置、可信源快照、写入目标和已保存译文质量检查。

| 命令 | 用途 | 成功判断 | 失败处理 |
| --- | --- | --- | --- |
| `write-back --game <游戏标题>` | 把译文写进游戏文件 | 写文件前检查无 error，命令返回 0 且摘要可读 | 停止交付，按错误修质量、规则或已保存译文记录 |
| `write-back --game <游戏标题> --confirm-font-overwrite` | 写回并覆盖字体引用 | 用户已单独确认字体覆盖，摘要可解释 | 未确认字体覆盖时不使用 |
| `rebuild-active-runtime --game <游戏标题>` | 从可信源快照和已保存译文重建当前运行文件 | 写文件前检查无 error，命令返回 0，随后 `audit-active-runtime` 无 error；未启动插件源码支线时不要求处理插件源码内部源语言字符串 | 质量问题未清时先修规则、手动译文或精确重置 |
| `rebuild-active-runtime --game <游戏标题> --confirm-font-overwrite` | 重建运行文件并允许字体覆盖 | 用户已单独确认字体覆盖，摘要可解释 | 未确认字体覆盖时不使用 |
| `write-terminology --game <游戏标题>` | 术语专用写入，并保留已保存且可写的正文译文 | `status` 为 `ok`，摘要包含术语写入和保留正文译文数量 | 术语表、规则前置、可信源快照或已保存译文质量未通过时停止 |
| `write-terminology --game <游戏标题> --confirm-font-overwrite` | 写入稳定名词并允许字体覆盖 | 用户已单独确认字体覆盖，且写回前流程检查通过，摘要可解释 | 未确认字体覆盖时不使用 |
| `restore-font --game <游戏标题>` | 按原件还原项目覆盖过的字体引用 | 摘要可解释 | 缺原始备份或替换字体信息时停止说明 |
| `verify-feedback-text --game <游戏标题> --input <反馈原文清单>` | 在真实游戏文件中反查反馈原文 | `status` 为 `ok`，分类可解释 | 按规则缺口、译文缺口、写入缺口或插件源码硬编码分类处理 |
| `scan-plugin-source-text --game <游戏标题> --output <风险报告文件>` | 扫描插件源码文本风险摘要；默认 `--view translation-source` | 输出文件存在，且不包含 AST selector 或完整候选列表，`summary.source_view` 可解释 | 高风险时暂停正文翻译；需要看当前运行文件时显式传 `--view active-runtime` |
