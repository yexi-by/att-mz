# 更新日志

## 未发布 - 阶段 9 契约冻结

### 破坏性变更

- 缺少可信源快照、旧规则短哈希、旧 `RPG_MAKER_TOOLS_*` 环境变量和旧工作区可选文件都不再作为成功入口；用户需要重新注册游戏、重新导出规则或改用当前 `ATT_MZ_*` 配置入口。
- 写入游戏文件、规则导入、字体替换和质量修复不再保留历史兼容分支；无法满足当前契约时显式失败，避免旧数据被当作当前输入继续运行。
- 内部测试文件已按业务域拆分，旧的聚合测试文件名不再作为开发文档中的事实来源。

### 协议变化

- CLI stdout 统一经 Agent JSON 报告封装输出，错误、摘要和详情来自单一报告模型。
- 工作区 manifest、文本范围快照、质量检查结果、写回计划和原生扩展版本检查成为当前公开流程的强制边界。
- JSONPath 事件指令协议、插件源码扫描、规则导入事务和写后审计由各自领域模块集中维护，不再由调用方传入第二事实来源。

### 性能变化

- 大型游戏会建立文本范围索引，质量报告、手动补译、当前运行重建和写入审计复用已加载范围，避免同一命令内重复全量扫描。
- 翻译停止阈值、Rust 线程数和写回计划扫描都通过当前配置真实参与调度；阶段 0 与阶段 7 的基准测试用于防止小样本和当前运行重建路径回退。

### 验证命令

- `uv run basedpyright`
- `uv run pytest`
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml`

### 发行包下载信息占位规则

- 正式发布时，当前版本段落必须写明 GitHub Release 下载 `att-mz-windows-x86_64.zip`，并列出本版实际功能变化、协议变化、修复点、依赖变化和验证命令。
- Windows ZIP 只能由 GitHub Actions `release` 工作流生成并上传；本机不得手工构建后上传正式发行包。

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
