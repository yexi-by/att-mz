# CLI 命令契约

本文件是开发版翻译流程 Agent 的执行契约，只记录如何安全调用 A.T.T MZ CLI、如何判断阶段结果、失败后回到哪一步。源码维护者用的逐命令事实地图位于 `docs/wiki/cli.md`，但它不是 Agent 执行依据，不能替代本文件、CLI 实际 JSON 输出或当前工作区文件。

命令必须在 `<项目目录>` 执行，默认前缀是：

```powershell
uv run python main.py <命令> ...
```

## 通用调用规则

- stdout 只读取最终 JSON；stderr 的长任务进度行只表示阶段进展，不是结果 JSON。
- 需要完整明细或业务文件时使用 `--output <文件>`。如果 stdout 的 `summary.report_detail_mode=sampled`，其中的数组只含样本，不能据此计算 hash、确认覆盖范围或补规则；需要全量候选时读取 `--output` 写出的完整报告。
- 文件型规则一律使用 `--input <文件>`；不要把大 JSON 塞进命令行，也不要用 `--rules "$(cat ...)"` 传大文件。
- 用户可写正则会在 validate/import、工作区验收和读取当前游戏已保存规则时预检。普通占位符、结构化占位符、MV 虚拟名字框、源文残留结构规则和 `[text_rules]` 配置正则统一使用 PCRE2 当前契约；命名分组统一使用 `(?<name>...)`。Note 标签文件键是 `fnmatch` 通配模式，不是正则。
- 所有工作区 JSON、临时脚本、手动填写译文表、规则文件和报告都按 UTF-8 读写。Windows 终端乱码时先设置 UTF-8 后重跑命令，不要基于乱码修改规则或译文。

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 配置与性能

- 第一次执行某个阶段时，业务参数和可调开关默认使用 `setting.toml` 与本地配置；命令行只传必需定位参数，例如 `--game`、`--path`、`--input`、`--output`、`--workspace`、`--output-dir`，以及已满足前置条件的确认参数。
- 用户明确指定值、CLI 输出说明默认配置缺失或不适合当前阶段，或 CLI 契约要求显式传入时，才做最小范围覆盖。一次性差异用 CLI 参数，运行时性能差异用环境变量，长期稳定差异再调整本地配置。
- 模型地址和 API Key 使用 `ATT_MZ_LLM_BASE_URL`、`ATT_MZ_LLM_API_KEY`。
- Rust 热路径线程数由 `ATT_MZ_RUST_THREADS` 控制；不设置或设为 `0` 时使用默认线程池。不要把性能基线里的 `4` 当运行上限。
- 需要解释重建索引或翻译阶段耗时时，使用 `--debug --debug-timings`，读取 `summary.diagnostics` 或完整诊断 JSON 中的 `text_index.rebuild.*` 计时与 `runtime.native_thread_count` 计数。普通 summary 只作为业务结果。

## 当前文本索引

- `rebuild-text-index --game <游戏标题>` 会生成当前文本索引，后续翻译、质量检查、手动补译、覆盖审计、反馈定位和写进游戏文件都读取当前文本索引。
- 当前文本索引区分原始片段、玩家可见文本、模型翻译正文、写回结构片段和 hash；不要从工作区文件、当前运行文件或诊断输出反推当前文本范围。
- 索引缺失、范围不一致或不满足当前契约时，命令必须按错误提示回到 `rebuild-text-index --game <游戏标题>`。
- 工作区校验失败、manifest 不匹配、范围信息不可用或不满足当前契约时，重新运行 `prepare-agent-workspace --game <游戏标题> --output-dir <工作区>`；不要手补 manifest 或复用未列入 manifest 的候选文件。
- 当前运行文件审计或反馈定位缺少可用写回映射时，先运行 `rebuild-text-index --game <游戏标题>`，再按需要运行 `rebuild-active-runtime --game <游戏标题>` 重建当前运行文件；不要把当前运行文件当作翻译源。
- 不满足当前契约的输入只作为无效输入处理；按错误提示重新生成当前索引、当前工作区、当前运行文件或重新导入当前规则。

## 阶段命令

### 0. 启动、注册与危险回溯

| 场景 | 命令 | 判断与下一步 |
| --- | --- | --- |
| 静态环境检查 | `doctor --no-check-llm` | `status` 不是 `error`；无 `--game` 时只说明默认配置，不代表当前游戏源语言。 |
| 源语言探测 | `probe-source-language --path <游戏目录> --output <探测报告>` | 只按玩家可见文本判断；结果不确定或与用户认知冲突时，展示样本让用户确认。 |
| 注册日文游戏 | `add-game --path <游戏目录> --source-language ja` | `summary.game_title` 是后续 `--game` 值；目录已有可信源快照时换干净原始目录。 |
| 注册英文游戏 | `add-game --path <游戏目录> --source-language en` | 同上；`add-game` 不读取探测报告，也不会替用户决定源语言。 |
| 游戏状态和下一步裁决 | `doctor --game <游戏标题> --no-check-llm` | 当前游戏源语言只看 `summary.source_language`。读取 `summary.flow_decision`、`summary.flow_reason`、`summary.flow_next_command`；`flow_can_continue=false` 时先处理阻断项，不启动翻译或写回。doctor 会默认执行写回级只读检查。 |
| 查看注册列表 | `list` | 不符合当前 schema 的游戏进入 warning；需要继续使用被跳过游戏时，按 warning 重新注册或修复。 |
| 危险回溯预演 | `reset-game --game <游戏标题> --dry-run` | 只转述恢复和删除计划，不修改文件。 |
| 危险回溯执行 | `reset-game --game <游戏标题> --confirm-game-title <游戏标题>` | 只能在用户明确要求注销、重置或恢复注册前状态时使用；禁止手动删库绕过恢复。 |

### 1. 工作区与基础候选

| 场景 | 命令 | 判断与下一步 |
| --- | --- | --- |
| 准备规则分析工作区 | `prepare-agent-workspace --game <游戏标题> --output-dir <工作区>` | 工作区文件存在，`summary.workspace` 指向目标目录；需要覆盖事件指令默认编码时加 `--code CODE`，后续空规则导入保持同一组 code。 |
| 验收工作区 | `validate-agent-workspace --game <游戏标题> --workspace <工作区> --output <完整报告>` | 无 `errors` 才能进入正文翻译；stdout 是摘要，完整明细读输出文件。 |
| 清理工作区 | `cleanup-agent-workspace --workspace <工作区>` | 只清理 CLI manifest 记录的文件；缺 manifest 时先人工确认范围。 |
| 单独导出插件配置 | `export-plugins-json --game <游戏标题> --output <plugins.json>` | 输出文件存在；用于排查插件配置候选。 |
| 单独导出事件指令 | `export-event-commands-json --game <游戏标题> --output <候选文件>` | 输出文件存在，`summary.command_codes` 可解释；需要覆盖默认编码时加 `--code CODE`。 |

### 2. 规则导入

所有规则都遵循同一顺序：先导出或读取候选，再编辑规则文件，再运行对应 validate，最后 import。空规则只有在已审查当前候选并能说明空结果理由时才加 `--confirm-empty`。导入后读取 `summary.impact_requires_text_index_rebuild`、`summary.impact_requires_doctor`、`summary.impact_write_back_probe_affected` 和 `details.import_impact`；需要重建索引就先运行 `rebuild-text-index`，需要 doctor 就重新运行 doctor。若出现 `deleted_translations_backed_up` warning，表示已保存译文因规则变化被清理；确认导错时，先导入正确规则，再用备份文件运行 `import-manual-translations` 恢复。

| 领域 | 命令组 | 关键判断 |
| --- | --- | --- |
| MV 虚拟名字框 | `export-mv-virtual-namebox-candidates`、`validate-mv-virtual-namebox-rules`、`import-mv-virtual-namebox-rules` | 仅 MV 游戏运行；MZ 游戏跳过。新增命中样本必须经主代理确认。 |
| 术语 | `export-terminology`、`import-terminology` | 字段译名表和正文术语表是不同文件；主代理亲自审查后导入。术语导入不要求重建文本索引，但要求重新 doctor 和写回级检查。 |
| 插件参数 | `validate-plugin-rules`、`import-plugin-rules` | 插件哈希或当前配置不一致时重新准备工作区，不猜路径。 |
| 事件指令 | `validate-event-command-rules`、`import-event-command-rules` | 事件编码覆盖要从导出、validate 到 import 保持一致。 |
| Note 标签 | `export-note-tag-candidates`、`validate-note-tag-rules`、`import-note-tag-rules` | 文件键是 `fnmatch`；空规则必须说明理由。 |
| 非标准 data 支线 | `scan-nonstandard-data`、`export-nonstandard-data-json`、`validate-nonstandard-data-rules`、`import-nonstandard-data-rules` | 高风险或用户要求时才进入；候选必须归入翻译、排除或用户确认跳过。 |
| 插件源码支线 | `scan-plugin-source-text`、`export-plugin-source-ast-map`、`validate-plugin-source-rules`、`import-plugin-source-rules` | 高风险或反馈指向源码时按开局支线策略处理；默认自动处理并使用 `--view translation-source`，审计当前运行文件才用 `--view active-runtime`。 |
| 普通占位符 | `build-placeholder-rules`、`validate-placeholder-rules`、`scan-placeholder-candidates`、`import-placeholder-rules` | 未覆盖候选必须修规则或确认风险；warning 不表示译文可以改坏协议片段。 |
| 结构化占位符 | `validate-structured-placeholder-rules`、`scan-structured-placeholder-candidates`、`import-structured-placeholder-rules` | 处理固定协议外壳包住可翻译显示文本的情况。 |
| 源文保留例外 | `validate-source-residual-rules`、`import-source-residual-rules` | 只用于确实不应翻译且被报告的片段；禁止用来掩盖整句漏翻或关闭全局检测。 |

### 3. 翻译、检查与手动修复

| 场景 | 命令 | 判断与下一步 |
| --- | --- | --- |
| 建立 warm index | `rebuild-text-index --game <游戏标题>` | `summary.index_status=rebuilt`，索引数量可解释；大型游戏规则导入、源文件变化或规则变化后先运行。 |
| 小批量试跑 | `translate --game <游戏标题> --max-items 3` | 只用于观察模型、规则和控制符风险；不以 0 失败作为指标。正常结束，`summary.pending_count` 是本轮数量，`summary.total_pending_count` 是总剩余，`summary.text_index_status` 可解释索引来源。小批量阶段禁止导出修复表、手填译文或重置译文。 |
| 持续正文翻译 | `translate --game <游戏标题>` | 每轮后运行 doctor 读取 `flow_decision`。`ready_to_translate` 继续，`should_stop_retrying` 先按质量错误补规则或导出修复表，`ready_for_manual_fix` 进入精确修复，`ready_to_write_back` 才进入写回确认。 |
| 查看进度 | `translation-status --game <游戏标题>` | 数量能解释；需按当前范围刷新时加 `--refresh-scope`。 |
| 查看文本范围 | `text-scope --game <游戏标题>` | `status` 为 `ok`；加 `--include-write-probe` 只标记索引可写状态，不执行写回级检查。 |
| 覆盖审计 | `audit-coverage --game <游戏标题>` | `status` 为 `ok`；发现规则命中、译文或范围缺口时先补规则、补译文或精确重置。 |
| 普通质量报告 | `quality-report --game <游戏标题>` | `status` 不是 `error`；有 error 禁止写回。需要 Rust 写回级只读检查时加 `--include-write-probe`；doctor 已默认执行这项检查。 |
| 导出质量修复表 | `export-quality-fix-template --game <游戏标题> --output <文件>` | 只改中文译文行后导入；`--include-write-probe` 只标记请求和索引可写状态。 |
| 导出待补译表 | `export-pending-translations --game <游戏标题> --output <文件>` | 可加 `--limit N`；抽样仍适合模型时回到 `translate`。 |
| 保存前校验手动译文 | `import-manual-translations --game <游戏标题> --input <文件> --check-only` | 只验证整包译文，不保存；通过后再去掉 `--check-only` 正式导入。 |
| 导入手动译文 | `import-manual-translations --game <游戏标题> --input <文件>` | `status` 为 `ok`；质量错误时只修中文译文行后先跑 `--check-only`。 |
| 精确重置 | `reset-translations --game <游戏标题> --input <文件>` | `summary.mode=input` 且数量可解释；输入路径不属于当前范围时整体失败，不部分删除。 |
| 完整重译 | `reset-translations --game <游戏标题> --all` | 只能在用户明确选择完整重译时使用。 |
| 跳过写回流水线 | `run-all --game <游戏标题> --skip-write-back` | 规则或质量错误未清前不写回。 |
| 最终流水线 | `run-all --game <游戏标题> --confirm-font-overwrite` | 只有用户单独确认字体覆盖时使用。 |

### 4. 写进游戏文件、重建与反馈

`write-back`、`rebuild-active-runtime` 和不跳过写入的 `run-all` 都是写文件操作。执行前必须满足：用户允许写回、`audit-coverage` 无 error、`quality-report` 无 error、可信源快照有效、当前规则范围内正文译文完整、普通 warning 已由主代理确认、接受风险类 warning 已获用户确认、字体覆盖已单独确认。

| 场景 | 命令 | 判断与下一步 |
| --- | --- | --- |
| 写进游戏文件 | `write-back --game <游戏标题>` | 写文件前检查无 error，命令返回 0 且摘要可读；失败时按错误修质量、规则或已保存译文记录。 |
| 字体覆盖写回 | `write-back --game <游戏标题> --confirm-font-overwrite` | 只有用户单独确认字体覆盖时使用。 |
| 重建当前运行文件 | `rebuild-active-runtime --game <游戏标题>` | 当前运行文件损坏或需要从可信源快照重建时使用；写入后再验收当前运行文件。 |
| 字体覆盖重建 | `rebuild-active-runtime --game <游戏标题> --confirm-font-overwrite` | 只有用户单独确认字体覆盖时使用。 |
| 术语专用写入 | `write-terminology --game <游戏标题>` | 允许正文仍有 pending，但术语表、规则前置、可信源快照、写入目标和已保存译文质量仍必须通过检查。 |
| 字体还原 | `restore-font --game <游戏标题>` | 缺原始备份或替换字体信息时停止说明。 |
| 当前运行文件审计 | `audit-active-runtime --game <游戏标题>` | 只把报告中的 error 当作阻断级问题；原游戏自带且未被 ATT-MZ 管理的非法 JS 只作为 warning 记录。插件源码支线已启动或已有写回映射时，才把已管理 selector 的残留、坏控制符或写回后的 JS 语法错误作为阻断问题。 |
| 阻塞诊断 | `diagnose-active-runtime --game <游戏标题> --output <诊断文件>` | 有 active runtime error 时运行；`mapped_excluded` 不进入重置清单，映射缺失时只报告无法反推。 |
| 试玩反馈反查 | `verify-feedback-text --game <游戏标题> --input <反馈原文清单>` | 按规则缺口、译文缺口、写入缺口或插件源码硬编码分类处理；禁止凭空猜测或直接全量重译。 |

## 停止条件

- 源语言探测不确定且用户未确认。
- 规则未导入、工作区验收有 error、占位符覆盖风险未处理也未确认。
- 非标准 data 或插件源码高风险已触发，但缺少开局支线策略、处理会显著增加成本或风险，或候选未归类。
- 翻译质量报告有 error，或写文件前检查失败。
- 当前运行文件审计有 error 且无法通过规则、译文、重置或重建解释。
- 用户未允许写回、未单独确认字体覆盖，或要求执行危险回溯但没有完整确认标题。
