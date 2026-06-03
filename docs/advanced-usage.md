# A.T.T MZ 进阶教学与源码编译

本文面向需要从源码运行、调试或参与开发的使用者。只想使用发行包时，先看仓库根目录的 [快速开始](../README.md)。开发约束、文案规范和交付红线见 [项目局部规范](../AGENTS.md)。模块结构导航见 [开发文档地图](development/README.md)。

## 环境准备

| 工具 | 用途 |
| --- | --- |
| Python 3.14 | 运行 CLI、测试和 Python 业务代码 |
| uv | 安装依赖、运行命令和测试 |
| Rust stable | 构建 PyO3 原生扩展 |
| VS Build Tools | Windows 上提供 MSVC 链接器，安装“使用 C++ 的桌面开发”组件 |

初始化源码环境：

```powershell
cd <项目目录>
uv sync --locked --dev
uv run maturin develop --release
uv run python main.py --help
```

如果原生扩展构建失败，先确认 Rust 工具链和 VS Build Tools 可用，再重新执行：

```powershell
uv run maturin develop --release
```

## 模型配置

复制或编辑 `<项目目录>\setting.toml`，填写 OpenAI 兼容接口配置：

```toml
[llm]
base_url = "https://<模型服务地址>/v1"
api_key = "<API Key>"
model = "<模型名>"
timeout = 600

[text_translation.system_prompt_files]
ja = "prompts/text_translation_ja_to_zh_system.md"
en = "prompts/text_translation_en_to_zh_system.md"
```

也可以用环境变量覆盖敏感配置。源码运行时所有命令都使用开发版入口；所有命令 stdout 默认输出机器可读报告；只导出文件的步骤按 `--output` 文件验收：

```powershell
uv run python main.py <命令> ...
```

CLI 的 stdout 固定输出机器可读 JSON，stderr 输出日志和简单文本进度。命令返回 `status=error` 时，本阶段不能继续。

## 环境与游戏注册

先检查配置：

```powershell
uv run python main.py doctor --no-check-llm
uv run python main.py doctor
```

`doctor --no-check-llm` 只检查静态配置；无 `--game` 时日志中的语言档案是默认配置，不代表当前游戏源语言。注册前的源语言判断必须以 `probe-source-language` 的玩家可见文本探测结果和用户确认为准。

注册游戏时必须显式声明原文语言。日文游戏：

```powershell
uv run python main.py add-game --path <游戏目录> --source-language ja
```

英文游戏：

```powershell
uv run python main.py add-game --path <游戏目录> --source-language en
```

查看已注册游戏：

```powershell
uv run python main.py list
```

## Agent 工作区

工作区用于让外部 Agent 在不读源码、不碰数据库的前提下分析术语、插件规则、事件指令规则、Note 标签规则、插件源码风险和占位符规则。

```powershell
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区>
```

如果需要覆盖事件指令编码：

```powershell
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --code <事件指令编码>
```

外部 Agent 填写完成后，先校验工作区：

```powershell
uv run python main.py validate-agent-workspace --game <游戏标题> --workspace <工作区> --output <完整报告>
```

该命令的 stdout 是摘要报告，完整 `details` 明细写入 `--output` 指定文件。规则候选和覆盖扫描报告会用 `summary.report_detail_mode` 标记 `sampled` 或 `full`：stdout 里的 `sampled` 只适合快速查看，不能用来计算候选确认范围；需要审查全部候选时必须读取 `--output` 的完整报告。

临时文件完成导入后可以清理：

```powershell
uv run python main.py cleanup-agent-workspace --workspace <工作区>
```

## 术语表流程

导出术语表工程：

```powershell
uv run python main.py export-terminology --game <游戏标题> --output-dir <术语表目录>
```

外部 Agent 填写字段译名表和正文术语表后导入：

```powershell
uv run python main.py import-terminology --game <游戏标题> --input <术语表目录>/field-terms.json --glossary-input <术语表目录>/glossary.json
```

在规则前置、术语表、可信源快照和已保存译文质量检查通过后，把稳定名词写进游戏文件：

```powershell
uv run python main.py write-terminology --game <游戏标题>
```

`write-terminology` 是术语专用写入，允许正文仍有还没成功保存译文的文本；它只会写入稳定术语和已保存且可写的正文译文。三类外部规则、普通占位符规则、结构化占位符规则、术语表、可信源快照、写入目标或已保存译文质量未通过时，命令会停止。

若本次写入需要覆盖字体引用，必须显式确认：

```powershell
uv run python main.py write-terminology --game <游戏标题> --confirm-font-overwrite
```

## 外部文本规则

插件规则从 `js/plugins.js` 导出、分析、校验、导入：

```powershell
uv run python main.py export-plugins-json --game <游戏标题> --output <工作区>/plugins.json
uv run python main.py validate-plugin-rules --game <游戏标题> --input <工作区>/plugin-rules.json
uv run python main.py import-plugin-rules --game <游戏标题> --input <工作区>/plugin-rules.json
```

事件指令规则从 `data/*.json` 导出、分析、校验、导入：

```powershell
uv run python main.py export-event-commands-json --game <游戏标题> --output <工作区>/event-commands.json
uv run python main.py validate-event-command-rules --game <游戏标题> --input <工作区>/event-command-rules.json
uv run python main.py import-event-command-rules --game <游戏标题> --input <工作区>/event-command-rules.json
```

Note 标签规则从标准数据文件的 `note` 字段导出、分析、校验、导入：

```powershell
uv run python main.py export-note-tag-candidates --game <游戏标题> --output <工作区>/note-tag-candidates.json
uv run python main.py validate-note-tag-rules --game <游戏标题> --input <工作区>/note-tag-rules.json
uv run python main.py import-note-tag-rules --game <游戏标题> --input <工作区>/note-tag-rules.json
```

规则导入只保存通过校验的条目。插件、事件指令和 Note 标签规则都不得绕过对应的 `validate-...` 命令。

空规则不会默认保存。插件、事件指令和 Note 标签候选文件里可能包含资源、脚本、协议串或内部标识；人工审查确认没有玩家可见文本时，用对应空结构并在导入命令追加 `--confirm-empty` 保存“已确认没有规则”的状态。事件指令候选如果用 `--code` 导出，空规则导入也传同一组 `--code`，让后续检查按同一范围判断确认是否过期。

如果规则变化导致一部分已保存译文不再属于当前规则范围，导入命令会先把这些译文备份到 `outputs/rule-import-backups/<游戏标题>/...json`，再清理项目数据库里的已保存译文记录。JSON 报告会返回 `deleted_translations_backed_up` 告警，并在 `summary.deleted_translation_backup_path` 给出备份文件路径。若确认规则导错，先重新导入正确规则，再用 `import-manual-translations --game <游戏标题> --input <备份文件>` 恢复这些译文。

插件源码文本属于少见支线。工作区默认只生成 `plugin-source-risk-report.json`，风险报告只包含风险摘要和候选数量，不包含 AST selector 或完整候选列表；只有插件源码高风险或支线已有规则时，才生成 `plugin-source-rules.json`。扫描范围固定为 `<游戏目录>/js/plugins/*.js` 的直接文件；不会扫描 `js` 根目录、其他目录或子目录。插件源码命令默认使用 `--view translation-source`，读取用于规则抽取和写回定位的翻译源；需要检查玩家当前实际运行文件时，使用 `audit-active-runtime` 或显式 `--view active-runtime`。当前运行文件只做写入结果验收，不作为翻译源。低风险且没有启动支线时不用填写空规则，可继续准备占位符和正文翻译。高风险时，`translate`、`run-all` 等正文入口会停止并要求用户确认；用户肯定后再导出 AST 地图、整理源码规则并导入：

```powershell
uv run python main.py export-plugin-source-ast-map --game <游戏标题> --output <工作区>/plugin-source-ast-map.json
uv run python main.py validate-plugin-source-rules --game <游戏标题> --input <工作区>/plugin-source-rules.json
uv run python main.py import-plugin-source-rules --game <游戏标题> --input <工作区>/plugin-source-rules.json
```

AST 地图默认导出所有包含源语言字符的 JS 字符串。源码规则使用 `selectors` 表示进入正文翻译和写回的 selector，使用 `excluded_selectors` 表示已经审查但判定不翻译的 selector。高风险项目或已经启动支线的项目，必须把活跃候选全部归入这两类之一；没有用户确认或仍有未审查 selector 时，不继续制作自定义占位符规则，也不启动正文翻译。

## 游戏控制符规则

在真实游戏翻译前，必须先确认自定义控制符和特殊文本协议。先生成可编辑草稿：

```powershell
uv run python main.py build-placeholder-rules --game <游戏标题> --output <工作区>/placeholder-rules.json
```

校验规则和样本文本：

```powershell
uv run python main.py validate-placeholder-rules --game <游戏标题> --input <工作区>/placeholder-rules.json
```

扫描仍未覆盖的疑似控制符：

```powershell
uv run python main.py scan-placeholder-candidates --game <游戏标题> --input <工作区>/placeholder-rules.json
```

确认后导入当前游戏数据库：

```powershell
uv run python main.py import-placeholder-rules --game <游戏标题> --input <工作区>/placeholder-rules.json
```

普通占位符规则和结构化占位符规则的候选扫描是风险提示和校验输入，不等同于所有候选都必须写规则。空规则仍必须加 `--confirm-empty`；如果扫描仍有未覆盖候选，导入命令会把本次“已审查但不写规则”或“仍有未覆盖候选但已确认风险”的状态保存到当前游戏数据库，并在后续 `doctor`、`text-scope`、`audit-coverage` 和 `quality-report` 中持续提示 warning。

翻译和写进游戏文件前仍会重新扫描当前文本。未覆盖候选为 0 时直接通过；未覆盖候选存在且数据库里有同一候选范围的当前确认状态时可以继续，并保留 warning；候选范围变化或旧确认过期时会重新停止。旧版样本确认不再作为当前确认依据，必须重新导出、审查并导入当前规则。不要为了消除计数编造错误规则，需要放行误报或特殊候选时，走对应 `import-* --confirm-empty` 或非空规则导入的持久化确认路径。确认风险不表示允许译文改坏协议片段；如果模型或人工译文删除、改写未覆盖疑似控制符，保存前校验、质量检查或写文件前检查仍会报 error。

规则 JSON 顶层是对象，键为正则表达式字符串，值为占位符模板字符串。模板应生成形如 `[CUSTOM_NAME_1]` 的方括号占位符，建议使用 `{index}` 区分同一规则的多次命中。

## 正文翻译

大型游戏在规则导入、源文件变化或规则变化后，先重建文本范围索引。第一次 cold rebuild 需要扫描当前翻译源；索引 warm 后，手动导入、精确重置、`translate --max-items`、普通 `quality-report` 和 `translation-status --refresh-scope` 会优先使用索引，避免每次小任务都全量扫描。这些小任务发现索引缺失或过期时会先自动重建，并在报告里标明 `cold_rebuilt` 或 `stale_rebuilt`。

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```

小批量试跑：

```powershell
uv run python main.py translate --game <游戏标题> --max-items 3
```

查看状态和范围：

```powershell
uv run python main.py translation-status --game <游戏标题>
uv run python main.py text-scope --game <游戏标题>
uv run python main.py audit-coverage --game <游戏标题>
uv run python main.py quality-report --game <游戏标题>
uv run python main.py audit-active-runtime --game <游戏标题>
```

`translation-status` 默认读取数据库中的最近运行统计；需要按当前范围刷新数量时加 `--refresh-scope`，warm index 下会优先使用索引，索引缺失或过期时会自动重建并在报告里说明。只读范围和普通质量报告默认不执行写入可行性探针；需要在报告里查看写入可行性时给 `text-scope`、`audit-coverage`、`quality-report`、`export-pending-translations` 或 `export-quality-fix-template` 加 `--include-write-probe`。

继续全量翻译：

```powershell
uv run python main.py translate --game <游戏标题>
```

常用运行控制参数：

| 参数 | 作用 |
| --- | --- |
| `--max-items <数量>` | 本轮最多处理的还没成功保存译文的文本数量 |
| `--max-batches <数量>` | 本轮最多发送给模型的批次数 |
| `--time-limit-seconds <秒数>` | 本轮最长运行时长 |
| `--stop-on-error-rate <比例>` | 项目检查没通过的译文比例达到阈值时停止 |
| `--include-source-lines` | 本轮要求模型额外输出原文对照，方便排障 |
| `--no-source-lines` | 本轮要求模型不要输出原文对照，减少输出 token |

## 手动填写和质量修复

导出还没成功保存译文的文本：

```powershell
uv run python main.py export-pending-translations --game <游戏标题> --output <工作区>/pending-translations.json
```

导入填写后的译文表：

```powershell
uv run python main.py import-manual-translations --game <游戏标题> --input <工作区>/pending-translations.json
```

普通待补译导入依赖有效文本范围索引；索引缺失或过期时会先自动重建并在报告里说明，随后仍只按输入路径检查和保存译文。质量修复表中的已保存问题项仍会优先走小范围修复路径。

导出“模型翻了，但项目检查没通过的译文”修复表：

```powershell
uv run python main.py export-quality-fix-template --game <游戏标题> --output <工作区>/quality-fix-template.json
```

修复后同样用 `import-manual-translations` 导入。

按清单重置指定文本：

```powershell
uv run python main.py reset-translations --game <游戏标题> --input <工作区>/reset-translations.json
```

按清单重置会先确认输入路径都属于当前文本范围；索引缺失或过期时会自动重建。路径不属于当前范围时整体失败且不会部分删除；路径已经没有已保存译文时会作为 warning 报告，便于解释数量差异。

完整重译前必须确认成本，再执行：

```powershell
uv run python main.py reset-translations --game <游戏标题> --all
```

## 源文残留例外

如果质量报告提示译文里仍有源语言文本，先判断是否漏翻。只有名单、作品名、品牌名、专有名词等确实应保留源文时，才写入例外规则。

```powershell
uv run python main.py validate-source-residual-rules --game <游戏标题> --input <工作区>/source-residual-rules.json
uv run python main.py import-source-residual-rules --game <游戏标题> --input <工作区>/source-residual-rules.json
```

当前源码模块名是 `source_residual`，负责源文残留例外规则解析、校验和检查协作。不要把源文残留检查理解成只服务日文；英文游戏会按语言档案检查当前原文的大段复制残留，不把单字母、单个词或短缩写直接当作漏翻。

## 写进游戏文件

写入前必须确认覆盖范围和质量报告：

```powershell
uv run python main.py audit-coverage --game <游戏标题>
uv run python main.py quality-report --game <游戏标题>
```

报告没有错误、当前规则范围内正文译文完整，并且用户允许写回后，把译文写进游戏文件：

```powershell
uv run python main.py write-back --game <游戏标题>
```

首次注册游戏时，工具只接受干净原始游戏目录，并在游戏目录内生成可信源快照：完整原始 `data` 备份 `data_origin`、插件配置备份 `js/plugins_origin.js` 和直接插件源码备份 `js/plugins_source_origin`。后续翻译源读取只使用这组快照；缺失、损坏或与数据库 manifest 不一致时，命令会停止并要求用干净游戏目录重新注册。

写进游戏文件时，工具只从可信源快照、已导入规则、术语和已保存译文记录生成待替换文件，不把当前运行文件当作翻译源。文件哈希、原文、selector 或已保存译文质量不匹配时会停止写入并报告原因。插件源码写入成功后会为已翻译 selector 和已审查排除 selector 保存可选诊断映射。当前运行审计默认只检查玩家实际运行 JS 文件的读取失败和语法错误；只有插件源码支线已启动或已有写回映射时，才把已管理 selector 的源文残留和坏控制符纳入支线诊断。

如果当前运行文件已经损坏，需要从可信源快照和已保存译文记录重建，使用：

```powershell
uv run python main.py rebuild-active-runtime --game <游戏标题>
```

`rebuild-active-runtime` 也是写文件操作，必须通过与 `write-back` 相同的覆盖审计、质量报告、完整译文覆盖、可信源快照和字体覆盖确认检查。它用于恢复当前运行文件状态，不能绕过规则、译文质量或完整覆盖要求。

当前运行审计报错后，用诊断命令反推到已保存译文记录：

```powershell
uv run python main.py diagnose-active-runtime --game <游戏标题> --output <工作区>/active-runtime-diagnosis.json
```

诊断只解释会阻止写入验收的问题，并使用写回映射精确匹配当前运行 `runtime_selector`，不会按文本相似度、行号、上下文或 AST 顺序猜测。`mapped_translate` 表示已反推到已保存译文记录；`mapped_excluded` 表示该字符串已审查但不翻译，不能加入重置清单；`runtime_mapping_missing` 表示当前运行字符串没有可用写回映射，诊断无法反推到已保存译文。修复路径是补规则、重置或手修已保存译文记录后重新写入，再运行 `audit-active-runtime` 验收。JS 语法错误和文件读取失败没有字符串 selector，需要先恢复或修复当前运行文件。

如需让配置字体覆盖游戏字体引用：

```powershell
uv run python main.py write-back --game <游戏标题> --confirm-font-overwrite
```

按原始备份还原项目覆盖过的字体引用：

```powershell
uv run python main.py restore-font --game <游戏标题>
```

`run-all` 会按固定顺序执行正文翻译和写入；最终写入阶段使用同一套写文件前检查。使用前仍应先完成规则、术语和占位符准备：

```powershell
uv run python main.py run-all --game <游戏标题>
```

只运行翻译、不写入：

```powershell
uv run python main.py run-all --game <游戏标题> --skip-write-back
```

## 试玩反馈

写入后如果试玩发现原文，把反馈原文整理为字符串数组或 `{"texts": [...]}`，再反查真实文件：

```powershell
uv run python main.py verify-feedback-text --game <游戏标题> --input <工作区>/feedback-texts.json
```

若怀疑原文来自插件源码硬编码文本，先扫描风险：

```powershell
uv run python main.py scan-plugin-source-text --game <游戏标题> --output <工作区>/plugin-source-risk-report.json
uv run python main.py audit-active-runtime --game <游戏标题>
uv run python main.py diagnose-active-runtime --game <游戏标题> --output <工作区>/active-runtime-diagnosis.json
```

插件源码风险报告只说明翻译源是否需要启动支线；普通流程不要把当前运行审计里的源语言字符串告警当漏翻清单。当前运行诊断只用写回映射反推已保存译文记录或确认已审查排除项。需要让这些文本进入正文翻译时，按插件源码支线导出 AST 地图、导入规则，再执行质量检查和写进游戏文件。

## 开发检查

提交或交付前执行：

```powershell
uv run basedpyright
uv run pytest
```

改到 Rust 原生扩展、构建配置或发布流程时再执行：

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

发行版只能由 GitHub Actions 的 `release` 工作流构建。本机负责源码修改、测试和提交，不负责生成正式发行包。

## 性能基准

大型游戏性能改动不能只看功能测试。改到文本范围索引、手动导入、精确重置、小批翻译或普通质量报告时，使用小任务 benchmark 验证 warm index 后的小输入链路：

```powershell
uv run python scripts/benchmark_small_tasks.py `
  --sample <样本游戏目录> `
  --game <游戏标题> `
  --db <数据库路径> `
  --runs 1 `
  --manual-item-count 100 `
  --max-items 3 `
  --max-quality-report-ms 10000 `
  --max-translate-ms 5000 `
  --max-import-ms 2000 `
  --max-reset-ms 1000
```

脚本会复制样本和数据库到临时工作目录，先执行 `rebuild-text-index`，再计时普通 `quality-report`、`translate --max-items`、`import-manual-translations` 和 `reset-translations --input`。默认会启动本地假 OpenAI 兼容服务并通过环境变量覆盖临时配置，不消耗真实模型额度；只有显式传入 `--allow-real-llm` 时才使用当前模型配置。结果里的 `threshold_failures`、`command_failures` 和 `command_warnings` 都应为空；每个 task 都会记录 `elapsed_ms`、`return_code`、`report_status`、索引状态、阶段耗时和 Rust 线程数。样本路径、游戏标题和数据库路径必须通过参数传入，不要把本机私有路径写进脚本或文档。
