# 持久化层

## 职责

`app.persistence` 管理多游戏数据库路径、连接、schema、游戏注册和所有业务记录读写。`GameRegistry` 是游戏注册入口，`TargetGameSession` 是当前游戏数据库会话入口。会话能力按记录域拆分为译文、规则、术语、运行状态和字体记录。更多表级说明见 [数据库文档](../database.md)。

## 输入

- 游戏标题、游戏根目录、源语言和目标语言。
- 应用层传入的译文记录、规则记录、术语记录、运行记录和字体处理记录。
- SQLite 查询结果行。

## 输出

- 每个游戏独立的 SQLite 数据库。
- Pydantic 记录模型，例如游戏注册信息、译文记录、规则记录、术语记录和运行记录。
- 可供应用层继续处理的强类型记录列表。

## 失败策略

- 数据库路径解析失败、枚举值非法、缺少必要语言信息或记录损坏时直接报错。
- 行对象读取通过 `rows.py` 收窄类型，避免把未知值向业务层传递。
- 不在长期代码里加入一次性迁移逻辑；schema 调整需要单独处理和验收。

## 协作模块

- `app.application` 通过 `GameRegistry` 和 `TargetGameSession` 编排完整用例。
- `app.agent_toolkit` 读取规则、译文和运行状态生成报告。
- 文本领域模块只接收记录模型，不直接操作数据库连接。

## 主要入口

- `app.persistence.repository.GameRegistry`
- `app.persistence.repository.TargetGameSession`
- `app.persistence.paths`
- `app.persistence.sql`
- `app.persistence.translation_records`
- `app.persistence.rule_records`
- `app.persistence.terminology_records`
- `app.persistence.run_records`
- `app.persistence.font_records`

## 测试覆盖

- `tests/test_persistence.py` 覆盖注册、会话和记录读写。
- 规则、术语、翻译和 Agent 工具箱测试会通过业务入口间接覆盖数据库方法。
