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

也可以用环境变量覆盖敏感配置。源码运行时所有命令都使用：

```powershell
uv run python main.py --agent-mode <命令> ... --json
```

`--agent-mode` 会输出适合外部 Agent 读取的简洁日志；`--json` 会输出机器可读报告。命令返回 `status=error` 时，本阶段不能继续。

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

工作区用于让外部 Agent 在不读源码、不碰数据库的前提下分析术语、插件规则、事件指令规则、Note 标签规则和占位符规则。

```powershell
uv run python main.py --agent-mode prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --json
```

如果需要覆盖事件指令编码：

```powershell
uv run python main.py --agent-mode prepare-agent-workspace --game <游戏标题> --output-dir <工作区> --code <事件指令编码> --json
```

外部 Agent 填写完成后，先校验工作区：

```powershell
uv run python main.py --agent-mode validate-agent-workspace --game <游戏标题> --workspace <工作区> --json
```

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

把稳定名词直接写进游戏文件：

```powershell
uv run python main.py --agent-mode write-terminology --game <游戏标题>
```

`write-terminology` 当前不支持 `--json`，执行时以终端日志和文件日志确认结果。

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
| `--stop-on-rate-limit-count <次数>` | 模型限流次数达到阈值时停止 |

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
```

报告没有错误后，把译文写进游戏文件：

```powershell
uv run python main.py --agent-mode write-back --game <游戏标题> --json
```

如需让配置字体覆盖游戏字体引用：

```powershell
uv run python main.py --agent-mode write-back --game <游戏标题> --confirm-font-overwrite --json
```

还原项目覆盖过的字体引用：

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

若怀疑原文来自插件源码硬编码文本，扫描候选：

```powershell
uv run python main.py --agent-mode scan-plugin-source-text --game <游戏标题> --output <工作区>/plugin-source-candidates.json --json
```

插件源码候选只说明“可能出现过这段文本”，不自动判断玩家是否可见，也不会修改插件源码。

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
