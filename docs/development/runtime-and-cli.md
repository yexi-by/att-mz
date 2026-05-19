# 运行入口与 CLI

## 职责

`app.cli_main` 是命令行启动入口，负责初始化日志、构建解析器并进入异步分发。`app.cli` 定义所有外部命令、参数读取、报告渲染、错误转换和进度展示。`app.config` 负责配置模型、环境变量覆盖和 CLI 覆盖参数。`app.runtime_paths` 负责解析运行目录，`app.observability` 负责终端日志、文件日志和进度条协作，`app.utils` 放置配置加载等小型共享工具。

## 输入

- 用户命令行参数，例如 `--agent-mode`、`--json`、`--game`、`--game-path` 和各子命令参数。
- `setting.toml` 和环境变量。
- 当前工作目录、应用目录、日志目录和数据目录。

## 输出

- 普通终端日志或适合 Agent 读取的简洁日志。
- JSON 报告，字段由命令报告层统一输出。
- 文件日志，记录运行开始、关键事件、错误摘要和排障上下文。

## 失败策略

- 参数解析失败由 `app.cli.errors` 转为清晰错误，不进入业务流程。
- 业务异常由命令实现捕获并输出中文原因；未知异常只在终端显示摘要，完整异常链写入文件日志。
- 配置加载、参数类型和不可用功能必须尽早报错，不静默忽略。

## 协作模块

- CLI 命令只做输入输出适配，业务逻辑交给 `app.application.TranslationHandler` 或 `app.agent_toolkit.AgentToolkitService`。
- 配置覆盖通过 `SettingOverrides` 进入应用层，不能只停留在参数解析层。
- 进度展示和日志共享同一控制台对象，避免长任务输出互相覆盖。

## 主要入口

- `app.cli.parser.build_parser`
- `app.cli.dispatch.dispatch_command`
- `app.cli.runtime`
- `app.cli.commands.*`
- `app.config.load_setting`
- `app.observability.logging`

## 测试覆盖

- `tests/test_cli_json_output.py` 覆盖命令参数、JSON 输出、写入前检查错误和配置覆盖。
- `tests/test_config_overrides.py` 覆盖配置文件与 CLI 覆盖链路。
- `tests/test_observability.py` 覆盖日志表现层。
- `tests/test_runtime_paths.py` 覆盖运行目录解析。
