# 子代理协作模型

本文件说明 A.T.T MZ 翻译流程如何把子代理从“帮手”升级为专业审查席。它只描述协作协议；规则导入、译文保存和写进游戏文件仍只能由主代理通过 CLI 完成。

## 为什么使用子代理

子代理适合并行探索、隔离噪声、独立审查和摘要证据。插件候选、事件指令、Note 标签、术语上下文、占位符覆盖和质量报告都可能产生大量中间信息；这些信息不应长期挤占主代理上下文。

主代理负责需求、决策、用户沟通、导入和写回许可。子代理负责读取声明输入，产出候选、证据、风险和建议动作。子代理报告不是最终结论，主代理必须复核。

## 角色总览

| 子代理 | 使命 | 唯一输出 | 交叉审查 |
| --- | --- | --- | --- |
| `att_mz_term_curator` | 从术语子任务源文件、说话人上下文和数据库上下文中产出可靠术语候选。 | `terminology/subtasks/candidates/<术语分组>.json` | 主代理 |
| `att_mz_rule_analyst` | 把默认三类外部候选归入可翻译、排除或不确定，并给出可审查证据。 | `plugin-rules.json / event-command-rules.json / note-tag-rules.json` | `att_mz_placeholder_sentinel` |
| `att_mz_branch_analyst` | 在用户确认支线后，把非标准 data 或插件源码候选全量归类。 | `nonstandard-data-rules.json / plugin-source-rules.json` | `att_mz_placeholder_sentinel` |
| `att_mz_placeholder_sentinel` | 独立审查外部规则和占位符规则是否漏保护协议片段或吞掉玩家可见文本。 | `结构化风险报告，不产出最终规则` | 主代理 |
| `att_mz_writeback_auditor` | 根据覆盖审计、质量报告、当前运行审计和用户许可，判断是否建议写回。 | `写回审计报告，不执行写回` | 主代理 |
| `att_mz_feedback_locator` | 根据反馈原文清单、verify-feedback-text 和相关报告，定位试玩反馈修复路径。 | `试玩反馈定位报告，不直接修文件` | 主代理 |

## 统一报告字段

每个子代理或外部任务包完成报告必须包含：

- `selected`：建议选中或进入下一步的对象。
- `excluded`：已审查但建议排除的对象。
- `uncertain`：证据不足、需要主代理或用户确认的对象。
- `evidence`：支撑判断的候选来源、字段名、上下文、样本或报告条目。
- `risk`：可能误选、漏选、误伤协议、增加成本或阻断写回的风险。
- `needs_main_review`：主代理必须复核的具体点。
- `recommended_next_action`：建议主代理执行的下一步 CLI 校验、用户确认或规则修正。

## 统一禁止动作

- 禁止子代理执行任何 `import-*`、`write-back`、`rebuild-active-runtime`、`reset-game` 或 `reset-translations` 命令。
- 禁止子代理写数据库、写进游戏文件、修改项目源码、修改 Skill、修改 README 或修改发布脚本。
- 禁止子代理把当前运行 JS 行号、AST 顺序、数据库表名或源码对象当作外部契约。
- 子代理只能读取任务声明的输入；只有任务明确给出唯一可写文件时，才能写那个文件。
- 占位符哨兵、写回审计和试玩反馈定位代理只产出报告，不产出最终规则，不执行修复。

## 角色详情

## `att_mz_term_curator`

使命：从术语子任务源文件、说话人上下文和数据库上下文中产出可靠术语候选。

输入：
- terminology/subtasks/sources/*.json
- terminology/contexts/speakers/*.json
- terminology/contexts/database_terms.json

唯一输出：`terminology/subtasks/candidates/<术语分组>.json`

报告字段：
- `selected`
- `excluded`
- `uncertain`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止改 terminology/field-terms.json 最终表
- 禁止改 terminology/glossary.json 最终表
- 禁止执行导入命令
- 禁止写数据库或游戏文件

交叉审查：由主代理审查。

## `att_mz_rule_analyst`

使命：把默认三类外部候选归入可翻译、排除或不确定，并给出可审查证据。

输入：
- plugins.json
- plugin-json-string-leaf-candidates.json
- event-commands.json
- note-tag-candidates.json
- 对应任务契约

唯一输出：`plugin-rules.json / event-command-rules.json / note-tag-rules.json`

报告字段：
- `selected`
- `excluded`
- `uncertain`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止编造 JSONPath
- 禁止选择资源、脚本、机器协议或内部标识
- 禁止执行导入命令
- 禁止写数据库或游戏文件

交叉审查：`att_mz_placeholder_sentinel`。

## `att_mz_branch_analyst`

使命：在用户确认支线后，把非标准 data 或插件源码候选全量归类。

输入：
- nonstandard-data/candidates.json
- nonstandard-data/source/*.json
- plugin-source-risk-report.json
- plugin-source-ast-map.json
- 对应任务契约

唯一输出：`nonstandard-data-rules.json / plugin-source-rules.json`

报告字段：
- `selected`
- `excluded`
- `uncertain`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止处理未获用户确认的高风险支线
- 禁止手写或改写 AST selector
- 禁止扫描 js/plugins 外目录
- 禁止执行导入命令

交叉审查：`att_mz_placeholder_sentinel`。

## `att_mz_placeholder_sentinel`

使命：独立审查外部规则和占位符规则是否漏保护协议片段或吞掉玩家可见文本。

输入：
- placeholder-candidates.json
- placeholder-rules.json
- structured-placeholder-rules.json
- 外部规则草稿
- 覆盖扫描报告

唯一输出：`结构化风险报告，不产出最终规则`

报告字段：
- `selected`
- `excluded`
- `uncertain`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止直接生成最终占位符规则
- 禁止导入规则
- 禁止放行坏控制符
- 禁止写数据库或游戏文件

交叉审查：由主代理审查。

## `att_mz_writeback_auditor`

使命：根据覆盖审计、质量报告、当前运行审计和用户许可，判断是否建议写回。

输入：
- audit-coverage 报告
- quality-report 报告
- audit-active-runtime 报告
- 写回许可上下文

唯一输出：`写回审计报告，不执行写回`

报告字段：
- `selected`
- `excluded`
- `uncertain`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止执行 write-back
- 禁止执行 rebuild-active-runtime
- 禁止确认字体覆盖
- 禁止写数据库或游戏文件

交叉审查：由主代理审查。

## `att_mz_feedback_locator`

使命：根据反馈原文清单、verify-feedback-text 和相关报告，定位试玩反馈修复路径。

输入：
- 反馈原文清单
- verify-feedback-text 报告
- quality-report 报告
- audit-active-runtime 或 diagnose-active-runtime 报告

唯一输出：`试玩反馈定位报告，不直接修文件`

报告字段：
- `selected`
- `excluded`
- `uncertain`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止直接全量重译
- 禁止手改游戏 data 文件
- 禁止猜测 location_path
- 禁止写数据库或游戏文件

交叉审查：由主代理审查。

## 主代理复核清单

- 候选文件必须真实存在，并且只改了任务允许的唯一输出。
- 空结果必须有检查范围和空结果理由。
- 选中项、排除项和不确定项必须有证据；证据不足时不要导入。
- 子代理报告里的风险必须逐项关闭、转为用户确认或明确写入后续计划。
- 导入前必须运行对应 validate 命令；validate 失败时只修任务文件后重跑，不绕过 CLI。
- 写回前必须由主代理亲自确认用户许可、质量报告、覆盖审计和当前运行文件验收。
