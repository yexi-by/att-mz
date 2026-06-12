# 单一事实源 Review Spec

## 目标

审查同一个业务事实是否只有一个生产者、一个明确契约和一组受控消费者。

本 spec 适用于任何事实：文本身份、scope hash、规则命中、selector、stale 判断、gate 状态、metadata/cache 版本、报告统计、写回计划、schema version、配置默认值、prompt 输入边界等。

## 核心原则

- 每个业务事实必须有唯一 owner。
- 消费者只能消费 owner 输出，不能二次推导同一事实。
- cache、metadata、fast path 只能缓存带版本的当前事实，不能把旧结论、空标记或 shortcut 当事实。
- 测试 helper 不能成为第二事实源。
- Python/Rust 跨层时，重型扫描、规则语义、候选、写回协议和核心状态判断优先由 Rust/native contract 产出；Python 只做编排、配置、事务、报告和错误映射。

## 审查步骤

1. 列出本次范围内的业务事实。
2. 为每个事实标出 owner、生产入口、持久化位置和消费者。
3. 搜索是否有同目的实现、helper、adapter、测试构造器、cache shortcut 或报告层重算。
4. 检查跨命令生命周期：重建、导入、翻译、质量检查、写回是否消费同一事实。
5. 检查版本和失效：schema、parser、native contract、规则 contract、scope hash 不匹配时是否显式失败或重算。

## 审查问题

- 这个事实的唯一 owner 是谁？
- 是否存在 Python/Rust 双实现、SQL/Python 常量重复、报告层重算、测试 helper 手工构造？
- 下游命令消费的是当前事实，还是 `passed`、空错误列表、旧 metadata、旧 cache、scan budget 结论？
- cache 命中是否校验足够的 contract version、输入 hash 和 scope？
- 错误码是否表达事实状态，而不是靠字符串匹配或文案推断？
- 删除一个非 owner 实现后，生产链路是否仍能通过 owner 输出完成？

## 输出格式

```text
范围：<模块、命令或 PR>
结论：PASS | FAIL | BLOCKED

事实矩阵：
| 事实 | owner | 生产入口 | 持久化/传递 | 消费者 | 结论 |
| --- | --- | --- | --- | --- | --- |

发现：
- <P0/P1/P2/P3> <标题>
  事实：<业务事实>
  证据：<文件:行号>
  问题：<多事实源、假事实、旧 cache 或二次判断>
  建议：<收束到 owner、删除重复实现、补版本失效、补测试>

已查无发现：
- <边界>

未验证：
- <边界和原因>
```

## 通过标准

- 每个关键事实都有唯一 owner。
- 同目的旧实现、二次判断和测试 oracle 已删除或降级为非生产辅助。
- cache 和 metadata 带当前 contract 证据，不以空标记或旧结论代表通过。
- Rust/Python 边界清晰，Python 不重建 Rust 已产出的核心事实。
- 测试覆盖 owner 输出、消费者行为、版本失效和跨命令生命周期。
