# 开发文档地图

本目录说明 A.T.T MZ 当前源码模块如何协作，供修功能、审查接口、定位测试和发布前验收使用。源码运行与命令教学见 [进阶教学与源码编译](../advanced-usage.md)，发行包用户入口见 [快速开始](../../README.md)，项目文案、规则、交付红线见 [项目局部规范](../../AGENTS.md)。

模块说明文档放在本目录根层级；阶段性 review、性能问题分析、修复进度和闭环矩阵统一放在 [Review 记录](review-records/README.md)，避免和模块介绍混在一起。

## 阅读路线

1. 先读 [运行入口与 CLI](runtime-and-cli.md)，理解命令如何解析、输出报告和装配配置。
2. 再读 [应用层与业务流程](application-and-workflows.md)，理解用户用例如何编排。
3. 涉及外部 Agent 协作时读 [Agent 工具箱](agent-toolkit.md)。
4. 涉及 RPG Maker 数据、规则或写入时读 [文本领域模块](text-domains.md)。
5. 涉及模型请求、翻译批次或术语表时读 [翻译、LLM 与术语](translation-llm-terminology.md)。
6. 涉及数据库时读 [持久化层](persistence.md)。
7. 涉及 Rust 加速能力时读 [原生核心](native-core.md)。
8. 提交、发布或补测试前读 [发布与测试](release-and-tests.md)。

## 模块导航

| 文档 | 覆盖模块 | 主要问题 |
| --- | --- | --- |
| [运行入口与 CLI](runtime-and-cli.md) | `app.cli_main`、`app.cli`、`app.config`、`app.runtime_paths`、`app.observability`、`app.utils` | 命令如何进入、参数如何生效、日志和 JSON 如何输出 |
| [应用层与业务流程](application-and-workflows.md) | `app.application` | 注册、翻译、写入、字体处理和运行摘要如何编排 |
| [Agent 工具箱](agent-toolkit.md) | `app.agent_toolkit` | 外部 Agent 如何拿报告、工作区、规则校验和质量修复表 |
| [文本领域模块](text-domains.md) | `app.rmmz`、`app.text_scope`、`app.plugin_text`、`app.event_command_text`、`app.note_tag_text`、`app.source_residual` | RPG Maker 文本如何提取、检查、定位和写入 |
| [翻译、LLM 与术语](translation-llm-terminology.md) | `app.translation`、`app.llm`、`app.llm_request_body_extra`、`app.language`、`app.language_profiles`、`app.terminology` | 模型请求、批次、质量校验、语言档案和术语如何协作 |
| [持久化层](persistence.md) | `app.persistence` | 多游戏数据库、会话和记录读写如何组织 |
| [原生核心](native-core.md) | `rust/`、`app.native_quality` | PyO3 入口和 Rust 质量检查如何提供加速能力 |
| [发布与测试](release-and-tests.md) | `.github`、`scripts`、`skills`、`prompts`、`tests` | 发行包如何构建、Skill 如何区分、测试如何验收 |

## Review 记录

| 文档 | 内容 |
| --- | --- |
| [Review 记录索引](review-records/README.md) | Rust 迁移 review、性能分析、修复进度和闭环矩阵 |

## 开发边界

- CLI 是外部协议入口，新增或改动参数必须从定义、解析、校验、应用到测试完整贯通。
- `TranslationHandler` 和 `AgentToolkitService` 是稳定门面，外部命令优先依赖门面，不直接跨层调用内部实现。
- 文本范围统一由 `app.text_scope` 构建，应用层和 Agent 层不得各自拼接可处理文本、已保存译文和写入可行性。
- 源文残留能力统一位于 `app.source_residual`，不要新增按单一语言命名的并行模块。
- 面向发行包用户的文档和 Skill 只使用抽象占位符，不暴露本机路径、测试夹具或内部数据库细节。
