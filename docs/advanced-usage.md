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
```

也可以用环境变量覆盖敏感配置。源码运行时所有命令都使用开发版入口；命令契约写有 `--json` 的步骤输出机器可读报告，只导出文件的步骤按 `--output` 文件验收：

```powershell
uv run python main.py --agent-mode <命令> ...
```

`--agent-mode` 会输出适合外部 Agent 读取的简洁日志；支持 `--json` 的命令会输出机器可读报告。命令返回 `status=error` 时，本阶段不能继续。

## 环境与游戏注册

先检查配置：

```powershell
uv run python main.py --agent-mode doctor --no-check-llm --json
uv run python main.py --agent-mode doctor --json
```

注册游戏时必须显式声明原文语言。日文游戏：

```powershell
uv run python main.py --agent-mode add-game --path <游戏目录> --source-language ja --json
```

英文游戏：

```powershell
uv run python main.py --agent-mode add-game --path <游戏目录> --source-language en --json
```

查看已注册游戏：

```powershell
uv run python main.py --agent-mode list --json
```

## Agent 工作区

工作区用于让外部 Agent 在不读源码、不碰数据库的前提下分析术语、插件规则、事件指令规则、Note 标签规则、插件源码风险和占位符规则。

```powershell
uv run python main.py --agent-mode prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --json
```

如果需要覆盖事件指令编码：

```powershell
uv run python main.py --agent-mode prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --code <事件指令编码> --json
```

外部 Agent 填写完成后，先校验工作区：

```powershell
uv run python main.py --agent-mode validate-agent-workspace --game <游戏标题> --workspace <工作区> --output <完整报告> --json
```

该命令的 stdout 是摘要报告，完整 `details` 明细写入 `--output` 指定文件。

临时文件完成导入后可以清理：

```powershell
uv run python main.py --agent-mode cleanup-agent-workspace --workspace <工作区> --json
```

## 术语表流程

导出术语表工程：

```powershell
uv run python main.py --agent-mode export-terminology --game <游戏标题> --output-dir <术语表目录>
```

外部 Agent 填写字段译名表和正文术语表后导入：

```powershell
uv run python main.py --agent-mode import-terminology --game <游戏标题> --input <术语表目录>/field-terms.json --glossary-input <术语表目录>/glossary.json --json
```

在规则前置和质量检查通过后，把稳定名词写进游戏文件：

```powershell
uv run python main.py --agent-mode write-terminology --game <游戏标题>
```

`write-terminology` 会执行写回前流程检查。三类外部规则、普通占位符规则、结构化占位符规则、术语表和已保存译文质量未通过时，命令会停止，不会绕过正文翻译流程直接写入。

命令当前不支持 `--json`，执行时以终端日志和文件日志确认结果。

若本次写入需要覆盖字体引用，必须显式确认：

```powershell
uv run python main.py --agent-mode write-terminology --game <游戏标题> --confirm-font-overwrite
```

## 外部文本规则

插件规则从 `js/plugins.js` 导出、分析、校验、导入：

```powershell
uv run python main.py --agent-mode export-plugins-json --game <游戏标题> --output <工作区>/plugins.json
uv run python main.py --agent-mode validate-plugin-rules --game <游戏标题> --input <工作区>/plugin-rules.json --json
uv run python main.py --agent-mode import-plugin-rules --game <游戏标题> --input <工作区>/plugin-rules.json --json
```

事件指令规则从 `data/*.json` 导出、分析、校验、导入：

```powershell
uv run python main.py --agent-mode export-event-commands-json --game <游戏标题> --output <工作区>/event-commands.json
uv run python main.py --agent-mode validate-event-command-rules --game <游戏标题> --input <工作区>/event-command-rules.json --json
uv run python main.py --agent-mode import-event-command-rules --game <游戏标题> --input <工作区>/event-command-rules.json --json
```

Note 标签规则从标准数据文件的 `note` 字段导出、分析、校验、导入：

```powershell
uv run python main.py --agent-mode export-note-tag-candidates --game <游戏标题> --output <工作区>/note-tag-candidates.json --json
uv run python main.py --agent-mode validate-note-tag-rules --game <游戏标题> --input <工作区>/note-tag-rules.json --json
uv run python main.py --agent-mode import-note-tag-rules --game <游戏标题> --input <工作区>/note-tag-rules.json --json
```

规则导入只保存通过校验的条目。插件、事件指令和 Note 标签规则都不得绕过对应的 `validate-...` 命令。

空规则不会默认保存。插件、事件指令和 Note 标签候选文件里可能包含资源、脚本、协议串或内部标识；人工审查确认没有玩家可见文本时，用对应空结构并在导入命令追加 `--confirm-empty` 保存“已确认没有规则”的状态。事件指令候选如果用 `--code` 导出，空规则导入也传同一组 `--code`，让后续检查按同一范围判断确认是否过期。

如果规则变化导致一部分已保存译文不再属于当前规则范围，导入命令会先把这些译文备份到 `outputs/rule-import-backups/<游戏标题>/...json`，再清理项目数据库里的已保存译文记录。JSON 报告会返回 `deleted_translations_backed_up` 告警，并在 `summary.deleted_translation_backup_path` 给出备份文件路径。若确认规则导错，先重新导入正确规则，再用 `import-manual-translations --game <游戏标题> --input <备份文件> --json` 恢复这些译文。

插件源码文本属于少见支线。工作区会生成 `plugin-source-risk-report.json` 和 `plugin-source-rules.json`，风险报告只包含风险摘要和候选数量，不包含 AST selector 或完整候选列表。扫描范围固定为 `<游戏目录>/js/plugins/*.js` 的直接文件；不会扫描 `js` 根目录、其他目录或子目录。插件源码命令默认使用 `--view translation-source`，读取用于规则抽取和写回定位的翻译源；需要检查玩家当前实际运行文件时，使用 `audit-active-runtime` 或显式 `--view active-runtime`。当前运行文件只做产物验收，不作为翻译源。低风险且没有启动支线时保持空规则即可继续准备占位符和正文翻译。高风险时，`translate`、`run-all` 等正文入口会停止并要求用户确认；用户肯定后再导出 AST 地图、整理源码规则并导入：

```powershell
uv run python main.py --agent-mode export-plugin-source-ast-map --game <游戏标题> --output <工作区>/plugin-source-ast-map.json --json
uv run python main.py --agent-mode validate-plugin-source-rules --game <游戏标题> --input <工作区>/plugin-source-rules.json --json
uv run python main.py --agent-mode import-plugin-source-rules --game <游戏标题> --input <工作区>/plugin-source-rules.json --json
```

AST 地图默认导出所有包含源语言字符的 JS 字符串。源码规则使用 `selectors` 表示进入正文翻译和写回的 selector，使用 `excluded_selectors` 表示已经审查但判定不翻译的 selector。高风险项目或已经启动支线的项目，必须把活跃候选全部归入这两类之一；没有用户确认或仍有未审查 selector 时，不继续制作自定义占位符规则，也不启动正文翻译。

## 游戏控制符规则

在真实游戏翻译前，必须先确认自定义控制符和特殊文本协议。先生成可编辑草稿：

```powershell
uv run python main.py --agent-mode build-placeholder-rules --game <游戏标题> --output <工作区>/placeholder-rules.json --json
```

校验规则和样本文本：

```powershell
uv run python main.py --agent-mode validate-placeholder-rules --game <游戏标题> --input <工作区>/placeholder-rules.json --json
```

扫描仍未覆盖的疑似控制符：

```powershell
uv run python main.py --agent-mode scan-placeholder-candidates --game <游戏标题> --input <工作区>/placeholder-rules.json --json
```

确认后导入当前游戏数据库：

```powershell
uv run python main.py --agent-mode import-placeholder-rules --game <游戏标题> --input <工作区>/placeholder-rules.json --json
```

普通占位符规则和结构化占位符规则都遵循同一条硬闸：空规则必须加 `--confirm-empty`，并且当前候选扫描必须确实为空；有未覆盖候选时不能继续翻译或写进游戏文件。

规则 JSON 顶层是对象，键为正则表达式字符串，值为占位符模板字符串。模板应生成形如 `[CUSTOM_NAME_1]` 的方括号占位符，建议使用 `{index}` 区分同一规则的多次命中。

## 正文翻译

小批量试跑：

```powershell
uv run python main.py --agent-mode translate --game <游戏标题> --max-batches 1 --json
```

查看状态和范围：

```powershell
uv run python main.py --agent-mode translation-status --game <游戏标题> --json
uv run python main.py --agent-mode text-scope --game <游戏标题> --json
uv run python main.py --agent-mode audit-coverage --game <游戏标题> --json
uv run python main.py --agent-mode quality-report --game <游戏标题> --json
uv run python main.py --agent-mode audit-active-runtime --game <游戏标题> --json
```

继续全量翻译：

```powershell
uv run python main.py --agent-mode translate --game <游戏标题> --json
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
uv run python main.py --agent-mode export-pending-translations --game <游戏标题> --output <工作区>/pending-translations.json --json
```

导入填写后的译文表：

```powershell
uv run python main.py --agent-mode import-manual-translations --game <游戏标题> --input <工作区>/pending-translations.json --json
```

导出“模型翻了，但项目检查没通过的译文”修复表：

```powershell
uv run python main.py --agent-mode export-quality-fix-template --game <游戏标题> --output <工作区>/quality-fix-template.json --json
```

修复后同样用 `import-manual-translations` 导入。

按清单重置指定文本：

```powershell
uv run python main.py --agent-mode reset-translations --game <游戏标题> --input <工作区>/reset-translations.json --json
```

完整重译前必须确认成本，再执行：

```powershell
uv run python main.py --agent-mode reset-translations --game <游戏标题> --all --json
```

## 源文残留例外

如果质量报告提示译文里仍有源语言文本，先判断是否漏翻。只有名单、作品名、品牌名、专有名词等确实应保留源文时，才写入例外规则。

```powershell
uv run python main.py --agent-mode validate-source-residual-rules --game <游戏标题> --input <工作区>/source-residual-rules.json --json
uv run python main.py --agent-mode import-source-residual-rules --game <游戏标题> --input <工作区>/source-residual-rules.json --json
```

当前源码模块名是 `source_residual`，负责源文残留例外规则解析、校验和检查协作。不要把源文残留检查理解成只服务日文；英文游戏也会按语言档案检查英文残留。

## 写进游戏文件

写入前必须确认覆盖范围和质量报告：

```powershell
uv run python main.py --agent-mode audit-coverage --game <游戏标题> --json
uv run python main.py --agent-mode quality-report --game <游戏标题> --json
uv run python main.py --agent-mode audit-active-runtime --game <游戏标题> --json
```

报告没有错误后，把译文写进游戏文件：

```powershell
uv run python main.py --agent-mode write-back --game <游戏标题> --json
```

首次写进游戏文件前，工具会在游戏目录内生成完整原始 `data` 备份 `data_origin`。后续读取源文时使用该备份，当前激活 `data` 目录仍必须保持 RPG Maker 标准文件完整。

如果本次写入包含插件源码文本，工具会先在游戏 `js` 目录下创建 `plugins_source_origin`，只备份将要修改的 `js/plugins` 直接插件文件。源码文本写入使用已导入规则中的 selector 定位；文件哈希、原文或 selector 不匹配时会停止写入并报告原因。写入成功后会保存当前运行字符串到翻译源 `location_path` 的确定性映射。写入前后都会审计当前运行插件源码，发现漏翻、坏控制符或 JS 语法错误时命令会报错。

当前运行审计报错后，用诊断命令反推到已保存译文记录：

```powershell
uv run python main.py --agent-mode diagnose-active-runtime --game <游戏标题> --output <工作区>/active-runtime-diagnosis.json --json
```

诊断只使用写回映射精确匹配当前运行 `runtime_selector`，不会按文本相似度、行号、上下文或 AST 顺序猜测。`mapped` 表示已反推到已保存译文记录；`mapped_cache_changed` 表示已保存译文记录已变化；`mapped_source_changed` 表示翻译源 selector 或原文已变化；`unmapped` 表示没有确定性映射，不能反推。修复路径是补规则、重置或手修已保存译文记录后重新写入，再运行 `audit-active-runtime` 验收。JS 语法错误和文件读取失败没有字符串 selector，只会报告无法反推，需要先恢复或修复当前运行文件。

如需让配置字体覆盖游戏字体引用：

```powershell
uv run python main.py --agent-mode write-back --game <游戏标题> --confirm-font-overwrite --json
```

按原始备份还原项目覆盖过的字体引用：

```powershell
uv run python main.py --agent-mode restore-font --game <游戏标题> --json
```

`run-all` 会按固定顺序执行正文翻译和写入；使用前仍应先完成规则、术语和占位符准备：

```powershell
uv run python main.py --agent-mode run-all --game <游戏标题>
```

只运行翻译、不写入：

```powershell
uv run python main.py --agent-mode run-all --game <游戏标题> --skip-write-back
```

## 试玩反馈

写入后如果试玩发现原文，把反馈原文整理为字符串数组或 `{"texts": [...]}`，再反查真实文件：

```powershell
uv run python main.py --agent-mode verify-feedback-text --game <游戏标题> --input <工作区>/feedback-texts.json --json
```

若怀疑原文来自插件源码硬编码文本，先扫描风险：

```powershell
uv run python main.py --agent-mode scan-plugin-source-text --game <游戏标题> --output <工作区>/plugin-source-risk-report.json --json
uv run python main.py --agent-mode audit-active-runtime --game <游戏标题> --json
uv run python main.py --agent-mode diagnose-active-runtime --game <游戏标题> --output <工作区>/active-runtime-diagnosis.json --json
```

插件源码风险报告只说明翻译源是否需要启动支线；当前运行文件审计直接检查玩家实际运行的 JS；当前运行诊断只用写回映射反推已保存译文记录。需要让这些文本进入正文翻译时，按插件源码支线导出 AST 地图、导入规则，再执行质量检查和写进游戏文件。

## 开发检查

提交或交付前执行：

```powershell
uv run basedpyright
uv run pytest
```

改到 Rust 原生扩展、构建配置或发布流程时再执行：

```powershell
cargo fmt -- --check
cargo clippy --all-targets -- -D warnings
cargo test
```

发行版只能由 GitHub Actions 的 `release` 工作流构建。本机负责源码修改、测试和提交，不负责生成正式发行包。
