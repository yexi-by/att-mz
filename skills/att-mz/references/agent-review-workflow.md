# Agent 审查型工作流

本文件是分析与规则产出阶段的统一审查契约。它只约束 Agent 协作、工作区审计材料和主代理门禁；CLI 规则文件、当前游戏状态和导入命令仍是运行事实源。

## 适用范围

以下阶段必须使用“工作子代理 -> 审查子代理 -> 主代理裁决 -> validate -> import”链路：

- MV 虚拟名字框。
- 术语工程。
- 插件规则。
- 事件指令规则。
- Note 标签规则。
- 非标准 data 支线。
- 插件源码支线。
- 普通占位符收束。
- 结构化占位符收束。

正文翻译、写进游戏文件和试玩反馈继续按各自阶段契约执行，不因为本文件新增子代理写文件或导入权限。

## 新增工作区目录

新增目录只服务 Agent 审计和断点恢复，不替代现有规则文件位置：

```text
<工作区>/
  agent-scratch/
    <阶段ID>/<任务ID>/
      scripts/
      outputs/
      samples/
  agent-reports/
    <阶段ID>/<任务ID>.json
  review-reports/
    <阶段ID>/<任务ID>.json
  review-decisions/
    <阶段ID>.json
```

- `agent-scratch/`：一次性脚本、统计、抽样、覆盖和反例材料。
- `agent-reports/`：工作子代理报告。
- `review-reports/`：审查子代理报告。
- `review-decisions/`：主代理阶段裁决。

最终规则仍写入原契约位置，例如 `terminology/field-terms.json`、`plugin-rules.json`、`placeholder-rules.json`。子代理不得删除审查报告、裁决文件或主代理要求保留的脚本产物。

## 子代理权限

子代理可以在任务声明授权范围内：

- 读取工作区文件。
- 读取白名单游戏文件，例如当前任务需要的 `data/*.json` 或 `js/plugins/*.js` 直接文件。
- 写一次性辅助脚本到 `<工作区>/agent-scratch/<阶段ID>/<任务ID>/scripts/`。
- 使用 Python、PowerShell、Node.js 或当前环境已有且不引入新依赖的工具。
- 把统计、抽样、覆盖、反例和临时 JSON 写到 `outputs/` 或 `samples/`。
- 调用只读、导出、扫描、诊断和校验类 CLI 命令，例如 `export-*`、`scan-*`、`validate-*`、`text-scope`、`quality-report`、`audit-coverage`。

子代理禁止：

- 执行 `import-*`、`write-back`、`rebuild-active-runtime`、`write-terminology`、`restore-font`、`reset-game`、`reset-translations`、`run-all`。
- 写数据库或写游戏文件。
- 修改 <项目目录> 下源码、测试、配置、提示词、Skill、README、docs、构建脚本或发行脚本。
- 把临时脚本写到 `<项目目录>` 或游戏根目录。
- 绕过 CLI 直接操作持久状态。
- 读取未授权目录扩大任务范围。
- 把某个游戏样本总结成通用硬规则。

简言之：子代理禁止任何 import、写回、重建、重置、数据库写入或游戏文件写入；这些动作只能由主代理在审查闭环和 validate 通过后执行。

## 工作报告

工作子代理报告写入：

```text
<工作区>/agent-reports/<阶段ID>/<任务ID>.json
```

报告必须包含：

```json
{
  "task_id": "<任务ID>",
  "stage_id": "<阶段ID>",
  "agent_role": "worker",
  "status": "completed | needs_main_review | blocked",
  "inputs_read": [],
  "scripts_written": [],
  "cli_commands_run": [],
  "outputs_written": [],
  "summary": "",
  "selected": [],
  "excluded": [],
  "uncertain": [],
  "active_discoveries": [],
  "evidence": [],
  "risk": [],
  "recommended_next_action": ""
}
```

`active_discoveries` 专门记录程序候选之外，子代理通过脚本、统计、抽样或上下文主动发现的当前游戏模式。工作报告必须区分哪些发现来自 CLI 候选，哪些来自主动发现。

## 审查报告

审查子代理报告写入：

```text
<工作区>/review-reports/<阶段ID>/<任务ID>.json
```

报告必须包含：

```json
{
  "task_id": "<任务ID>",
  "stage_id": "<阶段ID>",
  "agent_role": "reviewer",
  "status": "passed | passed_with_warnings | failed",
  "inputs_reviewed": [],
  "scripts_rerun_or_written": [],
  "cli_commands_run": [],
  "findings": [
    {
      "severity": "blocker | warning | info",
      "title": "",
      "target": "",
      "evidence": [],
      "impact": "",
      "recommended_resolution": ""
    }
  ],
  "coverage_checks": [],
  "anti_overfit_checks": [],
  "quality_checks": [],
  "recommended_next_action": ""
}
```

分级含义：

- `blocker`：未关闭前禁止导入、禁止进入下一阶段。
- `warning`：不自动阻断，但主代理必须逐项确认并写入裁决文件；只有需要用户接受风险、跳过候选、写文件或显著增加成本的 warning 才询问用户。
- `info`：记录证据和背景，不要求动作。

审查报告不能只写“有风险”，必须给出对象、证据、影响和建议处理方式。

## 主代理裁决

主代理裁决写入：

```text
<工作区>/review-decisions/<阶段ID>.json
```

裁决文件必须包含：

```json
{
  "stage_id": "<阶段ID>",
  "decision": "approved | needs_revision | skipped_by_user | blocked",
  "worker_reports": [],
  "review_reports": [],
  "blockers": [
    {
      "source_report": "",
      "title": "",
      "resolution": "fixed | accepted_by_user | deferred | rejected",
      "evidence": ""
    }
  ],
  "warnings": [
    {
      "source_report": "",
      "title": "",
      "main_agent_confirmation": "",
      "follow_up": ""
    }
  ],
  "allowed_next_commands": [],
  "user_confirmations": [],
  "notes": ""
}
```

硬规则：

- 存在未关闭 `blocker` 时，`decision` 不能是 `approved`。
- `warning` 可以放行，但必须写主代理确认理由。
- `approved` 后才允许运行对应 validate 和 import。
- validate 失败时，裁决退回 `needs_revision`。
- 用户确认跳过支线时，裁决使用 `skipped_by_user`，并记录后续 warning。
- 不要把 `needs_revision`、普通 `warning` 或可由 CLI/报告判断的修复项转成用户选择题；主代理应先修规则、补证据、重跑校验或写明反证。

## 主代理门禁

每个适用阶段的门禁顺序：

1. 准备基础候选和上下文。
2. 派发工作子代理。
3. 进入等待态，按 `subagent-collaboration.md` 的主代理等待纪律轮询工作报告和产物。
4. 派发审查子代理。
5. 进入等待态，按同一等待纪律轮询审查报告。
6. 主代理读取最终候选、工作报告、审查报告、脚本统计和样本。
7. 关闭 `blocker`。
8. 确认 `warning`。
9. 写 `review-decisions/<阶段ID>.json`。
10. 运行 validate。
11. validate 通过后执行 import。
12. import 后按需重新准备工作区或重新扫描候选。

进入 validate 或 import 前，主代理必须确认：

- 本阶段必需工作报告存在。
- 本阶段必需审查报告存在。
- 所有 `blocker` 都已关闭。
- 所有 `warning` 都有确认理由。
- 全部等待中的工作和审查任务已完成，没有用半成品或短时间无输出替代结果。
- 子代理没有越权动作。
- 最终规则文件在正确位置。
- 辅助脚本和统计产物路径已记录。
- 空结果有审查证据。
- 需要用户承担风险或成本的确认项已记录；普通审查 warning 用主代理确认理由闭环。
- 裁决文件为 `approved` 或 `skipped_by_user`。

`blocker` 只能用以下方式关闭：

- `fixed`：规则、术语或候选已修改，并重新审查或补充验证。
- `rejected`：主代理认为审查子代理误判，必须写明反证。
- `accepted_by_user`：只有用户可接受风险时使用，必须记录用户确认。
- `deferred`：只允许非当前阶段阻断项，且必须写明后续阶段处理位置。当前阶段必需项不能 deferred 后继续导入。

用户确认只用于真实用户决策：写进游戏文件、字体覆盖、危险回溯、完整重译、跳过高风险支线、接受未修复风险、修改项目源码/Skill、或显著增加模型额度/运行时间。路径判断、规则修正、空结果证据、普通 warning、质量错误修复和重复翻译失败诊断都由主代理在当前流程内自动处理。

## 阶段任务 ID

推荐任务 ID：

- `mv_namebox_discovery`、`mv_namebox_review`
- `speaker_and_actor_terms`、`map_and_system_terms`、`skill_and_state_terms`、`item_terms`、`equipment_terms`
- `terminology_glossary_proposal`、`terminology_group_review`、`terminology_bundle_review`
- `plugin_rules_discovery`、`event_command_rules_discovery`、`note_tag_rules_discovery`
- `plugin_rules_review`、`event_command_rules_review`、`note_tag_rules_review`、`external_rules_review`
- `nonstandard_data_classification`、`nonstandard_data_review`
- `plugin_source_text_classification`、`plugin_source_text_review`
- `placeholder_rule_review`、`structured_placeholder_rule_review`
