# 更新日志

## v0.1.10 - 2026-06-01

### 功能变化

- 正文翻译提示词不再向模型暴露游戏内部定位路径，改用批次内临时短 ID 绑定模型输出和本地文本。
- 翻译返回解析改为严格 JSON；模型返回可修复但不合法的 JSON 时记录为“模型返回不可解析”，避免保存非协议输出。
- 插件规则、插件源码规则、事件指令规则和 Note 标签规则增加当前游戏漂移检查；规则不再命中当前结构时显式提示重新导出并导入。
- 规则导入时会清理不再属于当前规则范围的已保存译文，并先写入可恢复备份。
- 当前运行插件源码审计恢复路径更精确，只对写回映射覆盖的运行时 selector 做译文质量反查。

### 协议与文档

- 项目级 `AGENTS.md` 同步当前 CLI 入口：开发版使用 `uv run python main.py <命令> ...`，发行版使用 `.\att-mz.exe <命令> ...`，不再要求 `--agent-mode` 或 `--json`。
- 自定义正文提示词保留旧用法：缺少输出协议模板占位符时自动追加本轮输出协议；只写了部分模板占位符时显式报错。
- `--system-prompt` 帮助文案和配置模板补充了输出协议模板说明。
- README 和开发文档补充 RGSS 系列引擎后续适配范围说明。
- 发布工作流改为从 `CHANGELOG.md` 提取当前 tag 的版本段落作为 GitHub Release 正文，避免空泛自动发布说明。

### 依赖变化

- 移除 `json-repair` 运行依赖。

### 验证

- `uv run basedpyright`
- `uv run pytest`
- Rust 原生扩展和发行包冒烟测试由 GitHub Actions `release` 工作流执行。

### 发行包

- 正式发行包由 GitHub Actions `release` 工作流生成 `att-mz-windows-x86_64.zip`，并附在 GitHub Release 下载区。

## v0.1.9 - 2026-05-31

### CLI 协议

- CLI 统一为 Agent JSON 协议：命令 stdout 固定输出最终 JSON 报告，stderr 承载日志和已有长任务的简单文本进度。
- 删除 `--json` 和 `--agent-mode` 参数；传入这些参数会返回 `argument_error` JSON。
- `list`、`add-game`、`translate`、`write-back`、`run-all`、规则导入导出和术语相关命令默认输出 AgentReport 风格 JSON。
- `export-plugins-json`、`export-event-commands-json` 和 `export-terminology` 增加最小 JSON 摘要，包含输出路径和关键计数。

### 日志与进度

- 保留简单文本进度行，删除 Rich 动态进度条和 Rich 表格报告。
- stderr 日志固定为无 ANSI 单行文本，启动日志、结束日志、错误摘要和长任务进度不会污染 stdout。
- `--debug` 保留为排障日志级别开关，不影响 stdout JSON 协议。

### Agent 契约与文档

- 开发版 Skill、发行版 Skill、CLI 契约文档、README、进阶文档和性能脚本命令示例同步移除 `--json` / `--agent-mode`。
- 运行依赖移除 `rich`，发行包命令示例统一使用固定 Agent 协议。

### 验证

- `uv run basedpyright`
- `uv run pytest`
