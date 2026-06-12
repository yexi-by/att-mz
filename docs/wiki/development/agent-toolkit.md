# Agent 工具箱

## 职责

`app.agent_toolkit` 为外部 Agent 提供可读、可校验、可恢复的协作接口。`AgentToolkitService` 是稳定门面，子服务位于 `app.agent_toolkit.services`：环境诊断、占位符规则、当前文本索引、范围审计、质量报告、人工译文表、工作区、规则导入和反馈原文反查分别由独立 mixin 承担。`reports.py` 定义统一报告模型；疑似自定义控制符候选扫描由 Rust Rule Runtime 和 Scope/Index 相关适配入口提供事实。

## 输入

- 当前游戏标题或已注册游戏路径。
- 外部 Agent 填写的 JSON 规则、术语表、手动译文表、质量修复表和反馈原文清单。
- 当前数据库统一规则、当前文本索引、当前文本事实、已保存译文记录和游戏文件。

## 输出

- `AgentReport`，包含 errors、warnings、summary 和 details。
- Agent 工作区文件，例如插件配置 JSON、事件指令候选、Note 标签候选、术语表工程和 manifest。
- 可填写的手动译文表和质量修复表。

## 失败策略

- 规则导入前必须通过统一规则运行时校验；校验失败只返回报告，不直接写库。
- 工作区校验失败时不继续导入；外部 Agent 必须修复对应文件后重新校验。
- 质量报告发现错误时，写入游戏文件前必须先修复译文或规则。

## 协作模块

- 通过 `app.text_index`、`app.text_fact_*` 和 `app.native_scope_index` 获取当前文本范围与当前文本事实。
- 通过 `app.source_residual` 校验允许保留源文片段的例外规则。
- 通过 `app.native_rule_runtime` 调用 Rust 统一规则运行时。
- 通过 `app.native_quality` 调用 Rust 原生质量检查和写入协议扫描。
- 通过 `app.persistence` 读取当前游戏规则、译文和运行状态。

## 主要入口

- `app.agent_toolkit.service.AgentToolkitService`
- `app.agent_toolkit.services.doctor`
- `app.agent_toolkit.services.placeholder_rules`
- `app.agent_toolkit.services.coverage`
- `app.agent_toolkit.services.quality`
- `app.agent_toolkit.services.manual_translation`
- `app.agent_toolkit.services.workspace`
- `app.agent_toolkit.services.text_index`
- `app.agent_toolkit.services.rule_import_runtime`
- `app.agent_toolkit.services.rule_validation`
- `app.agent_toolkit.services.feedback`

## 测试覆盖

- `tests/test_cli_public_contract.py` 覆盖工作区公开 CLI 主链路：注册游戏、准备工作区、校验工作区和按 manifest 清理工作区。
- 规则匹配、范围覆盖、流程检查、质量检查和翻译停止条件不再由 Agent 工具箱 Python 大集成 pytest 固定；核心规则归 Rust/native owner 测试，Python 只保留公开入口和可观察报告契约。
- Skill 与 CLI 协议一致性通过 canonical 协议生成检查和人工审查确认，不再由 pytest 固定。
