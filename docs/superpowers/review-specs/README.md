# 长期 Review Spec

本目录保存可反复调用的通用审查规格。它们不是一次性设计稿，也不是实现计划；用途是在任何模块、命令、PR 或重构完成后，用同一把尺子检查当前系统是否真实、清晰、可维护。

调用时可以直接说：

- 用当前契约 Review Spec 审查 `<范围>`。
- 用单一事实源 Review Spec 审查 `<范围>`。
- 用生产链路真实性 Review Spec 审查 `<范围>`。
- 用冗余源码与测试删除 Review Spec 审查 `<范围>`。

## 四个规格

| Spec | 主要问题 | 适用场景 |
| --- | --- | --- |
| [当前契约 Review Spec](current-contract-review.md) | 当前系统是否只表达当前契约 | schema、CLI、配置、文案、测试、README、Skill |
| [单一事实源 Review Spec](single-source-of-truth-review.md) | 同一业务事实是否有多个生产者 | Rust/Python 边界、SQLite/cache、报告统计、写回计划 |
| [生产链路真实性 Review Spec](production-path-truth-review.md) | 当前源码中的承诺是否真的落到生产副作用 | `commit`、`write`、`import`、`store`、`rebuild`、报告字段 |
| [冗余源码与测试删除 Review Spec](redundant-source-test-deletion-review.md) | 当前生产契约不需要的代码和测试是否应删除 | 旧 helper、fixture、mock、stub、fallback、re-export、scan budget |

## 通用输出

每次审查至少输出：

- 审查范围和入口。
- 当前事实源或生产链路证据。
- 发现列表，按 P0/P1/P2/P3 排序。
- 已检查但未发现问题的边界。
- 未验证范围和原因。
- 建议动作：删除、收束、补测试、补真实链路证据、或无需处理。

严重程度默认口径：

- P0：会导致数据破坏、错误写回、错误清理、错误成功或用户无法恢复。
- P1：破坏当前契约、事实源、生产链路或核心测试真实性，但尚未证明会直接破坏数据。
- P2：维护者容易误判当前系统，或测试/文档/辅助路径会诱导后续错误实现。
- P3：命名、组织、说明或审计材料可读性问题，不改变当前行为。
