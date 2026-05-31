# 更新日志

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
