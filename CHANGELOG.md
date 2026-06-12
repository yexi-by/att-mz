# 更新日志

## v0.1.11 - 2026-06-12

### 更新重点

- 复杂 MV/MZ 游戏处理能力明显提升：针对插件多、结构复杂、数据不规范的项目，在术语表和规则审查到位时，完整流程更接近一轮跑通。
- 新增当前文本索引主流程：通过 `rebuild-text-index` 统一建立翻译、质量检查、手动补译、覆盖审计和写进游戏文件所需的文本范围，减少大型项目重复扫描。
- 引入 Text Fact Contract v2：`fact_id` 成为翻译、质量检查、手动补译和写进游戏文件的核心身份，减少同路径多文本、旧路径和过期译文造成的误修。
- Rust 原生索引与统一规则运行时升级：文本范围构建、规则命中、候选扫描、索引写入和范围检查等重型路径继续向 Rust 收束。
- 规则系统统一处理插件规则、事件指令规则、Note 标签规则、普通占位符、结构化占位符、MV 虚拟名字框和源文残留检查。
- Agent 编排升级：工作区以 `manifest.json` 为交换边界，Skill 协议由 canonical 模板生成，并强化子代理发现、审查与主代理最终裁决流程。
- 写进游戏文件前置检查更严格：覆盖审计、质量报告、可信源快照、当前规则范围、用户许可和必要 warning 确认会共同决定是否允许继续。
- Debug 能力补强：新增统一 `--debug`、`--debug-timings`、`--debug-llm-messages`，便于查看阶段耗时、Rust 线程数和模型请求消息。

### 实际体验

- 对非常复杂且不规范的 MV/MZ 游戏，当前流程在术语准确、规则充分审查的前提下，已经能显著降低返工概率。
- 复杂项目的处理时间可能增加。原因是能力更依赖子代理隔离上下文、候选交叉审查和主代理最终确认，这是为了正确性、术语一致性和写回安全付出的成本。

### 升级提醒

- 升级后建议重新运行 `rebuild-text-index --game <游戏标题>`；必要时重新运行 `prepare-agent-workspace --game <游戏标题> --output-dir <工作区>`。
- 旧规则表不自动迁移；遇到规则校验失败时，请按当前命令重新导出并导入规则。
- 旧工作区、旧索引、旧 schema、旧规则哈希不再作为成功入口；当前命令会明确提示需要重建、重新准备或重新导入。
- 自定义正则需要检查 PCRE2 语法，命名分组请使用 `(?<name>...)`。

### 已知风险与反馈

- 项目近期迭代速度较快，复杂能力已经提前落地，但仍可能存在隐藏 bug、边界样本遗漏或个别游戏适配不足。遇到问题欢迎提交 Issue，并尽量附上命令、日志、游戏结构特征和可复现步骤。

### 后续计划

- 性能极致优化：继续减少重复扫描，优化 Rust 热路径、索引复用、并发调度和大型项目耗时。
- 流程编排能力优化：继续收束 Agent 工作区、规则审查、补译、质量修复和写进游戏文件之间的协作边界。
- MV/MZ 主流程稳定后，转向更久远的 RPG Maker 引擎支持。

### 验证命令

- `uv run basedpyright`
- `uv run pytest`
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml`

### 发行包

- GitHub Release 下载 `att-mz-windows-x86_64.zip`。
- 正式 Windows ZIP 由 GitHub Actions `release` 工作流生成。

## v0.1.10 - 2026-06-01

### 功能变化

- 正文翻译提示词不再向模型暴露游戏内部定位路径，改用批次内临时短 ID 绑定模型输出和本地文本。
- 翻译返回解析改为严格 JSON；模型返回可修复但不合法的 JSON 时记录为“模型返回不可解析”，避免保存非协议输出。
- 插件规则、插件源码规则、事件指令规则和 Note 标签规则增加当前游戏漂移检查；规则不再命中当前结构时显式提示重新导出并导入。
- 规则导入时会清理不再属于当前规则范围的已保存译文，并先写入可恢复备份。
- 当前运行插件源码审计恢复路径更精确，只对写回映射覆盖的运行时 selector 做译文质量反查。

### 协议与文档

- 项目级 `AGENTS.md` 同步当前 CLI 入口：开发版使用 `uv run python main.py <命令> ...`，发行版使用 `.\att-mz.exe <命令> ...`，不再要求 `--agent-mode` 或 `--json`。
- 自定义正文提示词允许不写输出协议模板占位符：缺少时自动追加本轮输出协议；只写了部分模板占位符时显式报错。
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
