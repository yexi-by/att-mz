# 子代理协作模型

本文件说明 A.T.T MZ 翻译流程如何把子代理从“帮手”升级为工作席和审查席。它只描述协作协议；规则导入、译文保存和写进游戏文件仍只能由主代理通过 CLI 完成。报告 schema、工作区审计目录和主代理阶段裁决见 `agent-review-workflow.md`。

## 为什么使用子代理

子代理适合并行探索、隔离噪声、独立审查和摘要证据。插件候选、事件指令、Note 标签、术语上下文、占位符覆盖和质量报告都可能产生大量中间信息；这些信息不应长期挤占主代理上下文。

工作子代理负责读取声明输入，主动发现当前游戏数据里的文本约定，产出候选、证据、风险和建议动作。审查子代理负责反向检查漏选、误选、偷懒、原文残留、过拟合、空结果无证据和规则风险。主代理负责需求、决策、用户沟通、阶段裁决、导入和写回许可。子代理报告不是最终结论，主代理必须复核。

## 角色总览

| 子代理 | 使命 | 唯一输出 | 交叉审查 |
| --- | --- | --- | --- |
| `att_mz_term_curator` | 从术语子任务源文件、说话人上下文和数据库上下文中产出可靠术语候选。 | `terminology/subtasks/candidates/<术语分组>.json` | `att_mz_terminology_reviewer` |
| `att_mz_rule_analyst` | 把默认三类外部候选归入可翻译、排除或不确定，并给出可审查证据。 | `plugin-rules.json / event-command-rules.json / note-tag-rules.json` | `att_mz_external_rule_reviewer`、`att_mz_placeholder_sentinel` |
| `att_mz_branch_analyst` | 按主代理提供的开局支线策略，把非标准 data 或插件源码候选全量归类。 | `nonstandard-data-rules.json / plugin-source-rules.json` | `att_mz_branch_reviewer`、`att_mz_placeholder_sentinel` |
| `att_mz_placeholder_sentinel` | 独立审查外部规则和占位符规则是否漏保护协议片段或吞掉玩家可见文本。 | `结构化风险报告，不产出最终规则` | 主代理 |
| `att_mz_writeback_auditor` | 根据覆盖审计、质量报告、当前运行审计和用户许可，判断是否建议写回。 | `写回审计报告，不执行写回` | 主代理 |
| `att_mz_mv_namebox_discoverer` | 基于当前工作区候选和事件正文样本主动发现 MV 虚拟名字框规则草稿，并产出覆盖、误伤和不确定证据。 | `mv-virtual-namebox-rules.json` | `att_mz_mv_namebox_reviewer` |
| `att_mz_mv_namebox_reviewer` | 检查 MV 虚拟名字框规则是否过拟合、漏同类模式、误伤普通正文或无法稳定重建源文本。 | `review-reports/mv_virtual_namebox/mv_namebox_review.json` | 主代理 |
| `att_mz_terminology_reviewer` | 用统计、抽样和上下文反向检查术语是否滥竽充数、原文照抄、中英混杂、机械拼接或转换不到位。 | `review-reports/terminology/<术语任务ID>.json` | 主代理 |
| `att_mz_external_rule_reviewer` | 反向检查三类外部规则是否误选机器协议、漏选玩家可见文本、空结果无证据或路径来自猜测。 | `review-reports/external_rules/<规则任务ID>.json` | 主代理 |
| `att_mz_branch_reviewer` | 确认已启动支线的活跃候选或 selector 全量归类，且没有越权读取、猜路径或误选机器协议。 | `review-reports/branch_rules/<支线任务ID>.json` | 主代理 |
| `att_mz_feedback_locator` | 根据反馈原文清单、verify-feedback-text 和相关报告，定位试玩反馈修复路径。 | `试玩反馈定位报告，不直接修文件` | 主代理 |

## 工作子代理统一报告字段

工作子代理或外部任务包完成报告必须包含：

- `task_id`：任务 ID。
- `stage_id`：阶段 ID。
- `agent_role`：固定为 `worker`。
- `status`：`completed`、`needs_main_review` 或 `blocked`。
- `inputs_read`：读取过的文件或报告。
- `scripts_written`：写入 `<工作区>/agent-scratch/` 的一次性脚本。
- `cli_commands_run`：执行过的只读、导出、扫描、诊断或 validate 命令。
- `outputs_written`：写出的候选、统计、样本或报告。
- `selected`：建议选中或进入下一步的对象。
- `excluded`：已审查但建议排除的对象。
- `uncertain`：证据不足、需要主代理或用户确认的对象。
- `active_discoveries`：程序候选之外，通过脚本、统计、抽样或上下文主动发现的当前游戏模式。
- `evidence`：支撑判断的候选来源、字段名、上下文、样本或报告条目。
- `risk`：可能误选、漏选、误伤协议、增加成本或阻断写回的风险。
- `needs_main_review`：主代理必须复核的具体点。
- `recommended_next_action`：建议主代理执行的下一步 CLI 校验、用户确认或规则修正。

## 审查子代理统一报告字段

审查子代理报告必须包含：

- `task_id`：任务 ID。
- `stage_id`：阶段 ID。
- `agent_role`：固定为 `reviewer`。
- `status`：`passed`、`passed_with_warnings` 或 `failed`。
- `inputs_reviewed`：复核过的工作产物、规则文件、报告和样本。
- `scripts_rerun_or_written`：复跑或新写的一次性审查脚本。
- `cli_commands_run`：执行过的只读、扫描、诊断或 validate 命令。
- `findings`：分级问题列表，每条都有 `severity`、`title`、`target`、`evidence`、`impact` 和 `recommended_resolution`。
- `coverage_checks`：覆盖、未归类、漏选或空结果检查。
- `anti_overfit_checks`：过拟合、硬套样例和误伤检查。
- `quality_checks`：原文照抄、中英混杂、机械拼接、玩家可见性和协议风险检查。
- `recommended_next_action`：建议主代理修正、重做、确认 warning、执行下一步 CLI 或在真实用户决策点停止；不要把普通修复项包装成用户选择。

`findings[].severity` 只能是 `blocker`、`warning` 或 `info`。未关闭 `blocker` 时，主代理禁止导入规则或进入下一阶段。

## 主代理等待纪律

- 派发子代理后，主代理进入等待态；优先使用平台提供的等待、轮询或 `sleep`，避免连续自我推理、反复读取同一批未变化文件或用消息消耗上下文。
- 轮询只检查完成状态、报告文件、唯一输出、越权动作和明确失败信号；没有新状态时继续等待，不把“暂时没有输出”解释为失败。
- 等待期间可以处理与该子代理结果无依赖的任务；禁止基于半成品、缺失报告、未完成 `status` 或推测结论写阶段裁决、运行 validate/import、启动正文翻译或写回。
- 短任务默认至少间隔 30-60 秒轮询；长任务、大范围扫描或多子代理并行任务默认间隔 2-5 分钟轮询。只有平台明确返回完成、失败、阻塞或用户改变目标时，才缩短等待或中断。
- 超出合理等待时间时，主代理先做一次轻量状态核对：确认子代理是否仍在运行、是否已有报告或错误、是否越权。只有确认失败、阻塞、越权、任务契约缺失或用户要求改变方式时，才重派、改串行或导出任务包。
- 干预必须留下原因：等待了什么、看到什么完成/失败信号、为什么原任务不能继续，以及改用的新处理方式。不能因为不耐烦、额度焦虑或想尽快进入下一阶段而干预。

## 统一禁止动作

- 禁止子代理执行任何 `import-*`、`write-back`、`rebuild-active-runtime`、`write-terminology`、`restore-font`、`reset-game`、`reset-translations` 或 `run-all` 命令。
- 禁止子代理写数据库、写进游戏文件、修改项目源码、修改 Skill、修改 README 或修改发布脚本。
- 禁止子代理把当前运行 JS 行号、AST 顺序、数据库表名或源码对象当作外部契约。
- 子代理只能读取任务声明的输入和授权白名单文件；工作子代理只有任务明确给出唯一可写最终文件时，才能写那个文件。
- 子代理可以把一次性辅助脚本、统计、样本和反例写到 `<工作区>/agent-scratch/<阶段ID>/<任务ID>/`，但禁止写到 <项目目录> 或游戏目录。
- 子代理可以运行只读、导出、扫描、诊断和 validate 类命令；运行过的命令必须写进报告。
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
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_read`
- `scripts_written`
- `cli_commands_run`
- `outputs_written`
- `selected`
- `excluded`
- `uncertain`
- `active_discoveries`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止改 terminology/field-terms.json 最终表
- 禁止改 terminology/glossary.json 最终表
- 禁止执行导入命令
- 禁止写数据库或游戏文件

交叉审查：`att_mz_terminology_reviewer`。

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
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_read`
- `scripts_written`
- `cli_commands_run`
- `outputs_written`
- `selected`
- `excluded`
- `uncertain`
- `active_discoveries`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止编造 JSONPath
- 禁止选择资源、脚本、机器协议或内部标识
- 禁止执行导入命令
- 禁止写数据库或游戏文件

交叉审查：`att_mz_external_rule_reviewer`、`att_mz_placeholder_sentinel`。

## `att_mz_branch_analyst`

使命：按主代理提供的开局支线策略，把非标准 data 或插件源码候选全量归类。

输入：
- nonstandard-data/candidates.json
- nonstandard-data/source/*.json
- plugin-source-risk-report.json
- plugin-source-ast-map.json
- 对应任务契约

唯一输出：`nonstandard-data-rules.json / plugin-source-rules.json`

报告字段：
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_read`
- `scripts_written`
- `cli_commands_run`
- `outputs_written`
- `selected`
- `excluded`
- `uncertain`
- `active_discoveries`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止处理主代理未授权的高风险支线
- 禁止手写或改写 AST selector
- 禁止扫描 js/plugins 外目录
- 禁止执行导入命令

交叉审查：`att_mz_branch_reviewer`、`att_mz_placeholder_sentinel`。

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
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_reviewed`
- `scripts_rerun_or_written`
- `cli_commands_run`
- `findings`
- `coverage_checks`
- `anti_overfit_checks`
- `quality_checks`
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

## `att_mz_mv_namebox_discoverer`

使命：基于当前工作区候选和事件正文样本主动发现 MV 虚拟名字框规则草稿，并产出覆盖、误伤和不确定证据。

输入：
- mv-virtual-namebox-candidates.json
- mv-virtual-namebox-rules.json
- terminology/contexts/speakers/*.json
- 当前任务授权的事件正文样本

唯一输出：`mv-virtual-namebox-rules.json`

报告字段：
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_read`
- `scripts_written`
- `cli_commands_run`
- `outputs_written`
- `selected`
- `excluded`
- `uncertain`
- `active_discoveries`
- `evidence`
- `risk`
- `needs_main_review`
- `recommended_next_action`

禁止动作：
- 禁止执行 import-mv-virtual-namebox-rules
- 禁止把某个样本形态固化为通用规则
- 禁止写数据库或游戏文件
- 禁止修改项目源码

交叉审查：`att_mz_mv_namebox_reviewer`。

## `att_mz_mv_namebox_reviewer`

使命：检查 MV 虚拟名字框规则是否过拟合、漏同类模式、误伤普通正文或无法稳定重建源文本。

输入：
- mv-virtual-namebox-rules.json
- mv-virtual-namebox-validate-report.json
- agent-reports/mv_virtual_namebox/mv_namebox_discovery.json
- agent-scratch/mv_virtual_namebox/mv_namebox_discovery/**

唯一输出：`review-reports/mv_virtual_namebox/mv_namebox_review.json`

报告字段：
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_reviewed`
- `scripts_rerun_or_written`
- `cli_commands_run`
- `findings`
- `coverage_checks`
- `anti_overfit_checks`
- `quality_checks`
- `recommended_next_action`

禁止动作：
- 禁止执行 import-mv-virtual-namebox-rules
- 禁止直接放行宽规则
- 禁止写数据库或游戏文件
- 禁止修改项目源码

交叉审查：由主代理审查。

## `att_mz_terminology_reviewer`

使命：用统计、抽样和上下文反向检查术语是否滥竽充数、原文照抄、中英混杂、机械拼接或转换不到位。

输入：
- terminology/subtasks/candidates/*.json
- terminology/field-terms.json
- terminology/glossary.json
- terminology/contexts/*.json
- agent-reports/terminology/*.json

唯一输出：`review-reports/terminology/<术语任务ID>.json`

报告字段：
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_reviewed`
- `scripts_rerun_or_written`
- `cli_commands_run`
- `findings`
- `coverage_checks`
- `anti_overfit_checks`
- `quality_checks`
- `recommended_next_action`

禁止动作：
- 禁止改 terminology/field-terms.json
- 禁止改 terminology/glossary.json
- 禁止执行 import-terminology
- 禁止写数据库或游戏文件

交叉审查：由主代理审查。

## `att_mz_external_rule_reviewer`

使命：反向检查三类外部规则是否误选机器协议、漏选玩家可见文本、空结果无证据或路径来自猜测。

输入：
- plugin-rules.json
- event-command-rules.json
- note-tag-rules.json
- plugins.json
- event-commands.json
- note-tag-candidates.json
- agent-reports/external_rules/*.json

唯一输出：`review-reports/external_rules/<规则任务ID>.json`

报告字段：
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_reviewed`
- `scripts_rerun_or_written`
- `cli_commands_run`
- `findings`
- `coverage_checks`
- `anti_overfit_checks`
- `quality_checks`
- `recommended_next_action`

禁止动作：
- 禁止执行 import-plugin-rules/import-event-command-rules/import-note-tag-rules
- 禁止替工作代理生成最终规则
- 禁止写数据库或游戏文件
- 禁止修改项目源码

交叉审查：由主代理审查。

## `att_mz_branch_reviewer`

使命：确认已启动支线的活跃候选或 selector 全量归类，且没有越权读取、猜路径或误选机器协议。

输入：
- nonstandard-data-rules.json
- plugin-source-rules.json
- nonstandard-data/candidates.json
- plugin-source-ast-map.json
- agent-reports/branch_rules/*.json

唯一输出：`review-reports/branch_rules/<支线任务ID>.json`

报告字段：
- `task_id`
- `stage_id`
- `agent_role`
- `status`
- `inputs_reviewed`
- `scripts_rerun_or_written`
- `cli_commands_run`
- `findings`
- `coverage_checks`
- `anti_overfit_checks`
- `quality_checks`
- `recommended_next_action`

禁止动作：
- 禁止执行 import-nonstandard-data-rules/import-plugin-source-rules
- 禁止手写或改写 AST selector
- 禁止扫描 js/plugins 外目录
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
- 子代理报告里的风险必须逐项关闭；普通 warning 由主代理写确认理由，只有接受风险、跳过候选、写回许可、字体覆盖或显著增加成本时才转为用户确认。
- 等待记录必须能说明所有工作和审查任务已完成；不得用未完成产物、缺失报告或短时间无输出替代完成信号。
- 导入前必须读取工作报告、审查报告和 `review-decisions/<阶段ID>.json`；存在未关闭 `blocker` 时禁止 validate/import。
- 导入前必须运行对应 validate 命令；validate 失败时退回 `needs_revision`，只修任务文件后重跑，不绕过 CLI。
- 写回前必须由主代理亲自确认用户许可、质量报告、覆盖审计和当前运行文件验收；普通 warning 由主代理写确认理由，只有接受跳过、高风险放行、字体覆盖和写文件许可需要用户确认。
