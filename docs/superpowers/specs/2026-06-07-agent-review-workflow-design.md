# A.T.T MZ Agent 审查型工作流设计

## 背景

当前 A.T.T MZ 翻译流程在规则和术语阶段主要依赖 CLI 导出的候选、子代理填表和主代理导入。这个模式能保证 JSON 结构和导入命令可运行，但不足以保证语义质量。程序没有发现的当前游戏文本约定，子代理往往也不会主动发掘；子代理交付格式正确的候选后，主代理容易进入形式审核和导入流程。

本设计的目标不是为某个具体游戏补特判，而是重构分析与规则产出阶段的协作方式，让流程具备主动发现、独立审查和主代理裁决能力。

## 目标

- 将分析与规则产出阶段升级为“工作子代理产出、审查子代理反向审查、主代理裁决”的审查型流程。
- 保留现有 CLI 规则文件位置和导入契约，只新增 Agent 审计材料目录。
- 允许子代理在工作区内写一次性辅助脚本，并调用只读、导出、扫描、诊断和校验类 CLI 命令，以便主动发现程序候选外的问题。
- 用结构化工作报告、审查报告和主代理裁决文件记录证据、风险和门禁结果。
- 通过 `blocker`、`warning`、`info` 分级阻断机制，避免格式正确但质量失败的规则或术语被导入。

## 非目标

- 第一版不重构正文翻译、写进游戏文件和试玩反馈主流程。
- 第一版不重排现有工作区主结构。
- 第一版不让新增 Agent 审计目录成为 CLI 规则事实源。
- 第一版不允许子代理执行任何状态变更命令。
- 第一版不把某个游戏的文本形态固化为通用规则。

## 总体架构

第一版采用“可审计工作区增强”。现有规则文件仍放在原路径，CLI 仍以现有规则文件和当前游戏状态为事实源。新增目录只服务 Agent 协作和人工审计。

```text
CLI/工作区基础候选
-> 工作子代理主动分析
-> 工作产物 + 证据报告 + 辅助脚本/统计
-> 审查子代理反向审查
-> blocker/warning/info 分级报告
-> 主代理裁决文件
-> validate
-> import 或退回修正
```

新增目录：

```text
<工作区>/
  agent-scratch/
  agent-reports/
  review-reports/
  review-decisions/
```

职责边界：

- CLI 负责基础导出、结构校验、规则导入和状态变更。
- 工作子代理负责主动发现、产出候选、写辅助脚本、生成证据。
- 审查子代理负责反向找漏选、误选、偷懒、原文残留、过拟合和规则风险。
- 主代理负责读取双方结果、关闭 blocker、确认 warning、写阶段裁决，并执行 validate/import。

## 覆盖阶段

第一版覆盖所有分析与规则产出阶段：

- MV 虚拟名字框。
- 术语工程。
- 插件规则。
- 事件指令规则。
- Note 标签规则。
- 非标准 data 支线。
- 插件源码支线。
- 普通占位符收束。
- 结构化占位符收束。

正文翻译、写进游戏文件和试玩反馈阶段沿用现有主流程。

## 子代理权限

允许子代理：

- 读取任务声明授权的工作区文件。
- 读取任务声明授权的游戏目录白名单文件，例如当前任务需要的 `data/*.json` 或 `js/plugins/*.js` 直接文件。
- 在 `<工作区>/agent-scratch/<阶段ID>/<任务ID>/scripts/` 写一次性辅助脚本。
- 使用 Python、PowerShell、Node.js 或其他当前环境已有且不引入新依赖的工具。
- 将统计、抽样、覆盖、反例和临时 JSON 写入 `outputs/` 或 `samples/`。
- 调用只读、导出、扫描、诊断和校验类 CLI 命令，例如 `export-*`、`scan-*`、`validate-*`、`text-scope`、`quality-report`、`audit-coverage`。

禁止子代理：

- 执行 `import-*`、`write-back`、`rebuild-active-runtime`、`write-terminology`、`restore-font`、`reset-game`、`reset-translations`、`run-all`。
- 写数据库。
- 写游戏文件。
- 修改项目源码、测试、配置、提示词、Skill、README、docs、构建脚本或发行脚本。
- 把临时脚本写到 `<项目目录>`。
- 绕过 CLI 直接操作持久状态。
- 读取未授权目录来扩大任务范围。
- 把某个游戏样本总结成通用硬规则。

子代理报告必须声明读取了哪些文件、写了哪些脚本、生成了哪些统计或样本、运行了哪些 CLI 命令，以及哪些发现来自程序候选、哪些来自主动发现。

## 工作区结构

`agent-scratch/` 放一次性脚本和中间证据：

```text
agent-scratch/
  <阶段ID>/
    <任务ID>/
      scripts/
      outputs/
      samples/
```

`agent-reports/` 放工作子代理报告：

```text
agent-reports/
  <阶段ID>/
    <任务ID>.json
```

`review-reports/` 放审查子代理报告：

```text
review-reports/
  <阶段ID>/
    <任务ID>.json
```

`review-decisions/` 放主代理阶段裁决：

```text
review-decisions/
  <阶段ID>.json
```

现有最终规则文件路径不变，例如：

```text
mv-virtual-namebox-rules.json
terminology/field-terms.json
terminology/glossary.json
plugin-rules.json
event-command-rules.json
note-tag-rules.json
nonstandard-data-rules.json
plugin-source-rules.json
placeholder-rules.json
structured-placeholder-rules.json
```

新增目录默认保留到本轮翻译结束，便于审计。子代理不得删除审查报告和裁决文件。

## 工作报告 Schema

路径：

```text
<工作区>/agent-reports/<阶段ID>/<任务ID>.json
```

建议结构：

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

`active_discoveries` 用于记录程序候选之外，子代理通过脚本、统计、抽样或上下文主动发现的模式。

## 审查报告 Schema

路径：

```text
<工作区>/review-reports/<阶段ID>/<任务ID>.json
```

建议结构：

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
- `warning`：不自动阻断，但主代理必须逐项确认并写入裁决文件。
- `info`：记录证据和背景，不要求动作。

审查报告不能只写“有风险”，必须给出对象、证据、影响和建议处理方式。

## 主代理裁决文件

路径：

```text
<工作区>/review-decisions/<阶段ID>.json
```

建议结构：

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

- 未关闭 `blocker` 时，裁决不能是 `approved`。
- `warning` 可以放行，但必须写主代理确认理由。
- `approved` 后才允许运行对应 validate 和 import。
- validate 失败会把阶段裁决退回 `needs_revision`。
- 用户确认跳过支线时，裁决必须是 `skipped_by_user`，并记录后续 warning。

## 主代理门禁

每个阶段固定门禁：

```text
1. 准备基础候选和上下文
2. 派发工作子代理
3. 等待工作报告和产物
4. 派发审查子代理
5. 等待审查报告
6. 主代理读取最终候选、工作报告、审查报告、脚本统计和样本
7. 关闭 blocker
8. 确认 warning
9. 写 review-decisions/<阶段ID>.json
10. 运行 validate
11. validate 通过后执行 import
12. import 后按需重新 prepare 或重新 scan
```

进入 validate/import 前，主代理必须确认：

- 本阶段必需工作报告存在。
- 本阶段必需审查报告存在。
- 所有 `blocker` 都已关闭。
- 所有 `warning` 都有确认理由。
- 子代理没有越权动作。
- 最终规则文件在正确位置。
- 辅助脚本和统计产物路径已记录。
- 空结果有审查证据。
- 用户确认项已记录。
- 裁决文件为 `approved` 或 `skipped_by_user`。

`blocker` 关闭方式：

- `fixed`：规则、术语或候选已修改，并重新审查或补充验证。
- `rejected`：主代理认为审查子代理误判，必须写明反证。
- `accepted_by_user`：只有用户可接受风险时使用，必须记录用户确认。
- `deferred`：只允许非当前阶段阻断项，且必须写明后续阶段处理位置。当前阶段必需项不能 deferred 后继续导入。

## 阶段任务设计

### MV 虚拟名字框

工作任务：`mv_namebox_discovery`

- 主动发现当前 MV 游戏如何表达发言人、名牌和正文边界。
- 可写脚本统计对白块开头短文本、重复前缀、包裹符号、控制符、插件名牌形态。
- 输出规则草稿、覆盖样本、误伤样本、未覆盖疑似样本、不确定模式。

审查任务：`mv_namebox_review`

- 检查是否过拟合某个写法。
- 检查是否漏掉同类变体。
- 检查是否把普通正文误判成名字框。
- 检查动态控制符、speaker/body 分组和 render_template 是否稳定。

明显过宽、明显漏掉同类高频模式、无法重建文本或误伤普通正文时，必须给 `blocker`。

### 术语工程

工作任务：

- `speaker_and_actor_terms`
- `map_and_system_terms`
- `skill_and_state_terms`
- `item_terms`
- `equipment_terms`
- `terminology_glossary_proposal`

审查任务：

- `terminology_group_review`
- `terminology_bundle_review`

分组工作子代理必须产出候选译名 JSON、工作报告、疑难项清单、保留源文清单及理由。规模较大时必须提供脚本或统计结果。

术语审查重点：

- `source == translation` 数量和比例。
- 空值。
- 中英混杂。
- 源文残留。
- 机械拼接。
- 重复源文不同译名。
- 字段译名表和正文术语表同名一致性。
- 正文术语表过小或过大。
- 字段包装、整句、一次性枚举、调试项是否误入正文术语表。
- 原文保留是否有理由。

如果某分组原文照抄比例异常高，审查报告必须给 `blocker`，除非工作报告明确证明这些条目确实应该保留源文。

### 三类外部规则

工作任务：

- `plugin_rules_discovery`
- `event_command_rules_discovery`
- `note_tag_rules_discovery`

审查任务可按三类独立审查，也可在低风险项目里聚合为 `external_rules_review`。

工作子代理可以写脚本做字符串叶子统计、字段名和值形态聚类、高频自然语言字段发现、排除项统计、JSON 字符串内部叶子展开分析、空结果证据表和混合协议文本样本清单。

审查重点：

- 是否误选资源、脚本、机器协议或内部标识。
- 是否因为字段复杂就排除玩家可见文本。
- JSONPath 是否来自真实候选。
- 空结果是否有证据。
- 混合协议文本是否提醒后续占位符保护。
- 是否过拟合某个插件、编码或样例。
- 是否在插件配置变化后继续使用旧工作区。

误选会破坏运行协议、路径不存在、空结果无证据或候选范围不完整时，必须给 `blocker`。

### 非标准 data 支线

触发条件：

- 高风险报告提示。
- 用户明确要求。
- 试玩反馈或审计指向非标准 data 文本缺口。

工作任务：`nonstandard_data_classification`

审查任务：`nonstandard_data_review`

启动后，活跃候选必须全量归类为 `paths`、`excluded_paths`，或经用户确认后按文件 `skipped`。高风险支线不能用空规则绕过审查。

### 插件源码支线

触发条件：

- 高风险报告提示。
- 用户明确要求。
- 试玩反馈指向插件源码硬编码文本。

工作任务：`plugin_source_text_classification`

审查任务：`plugin_source_text_review`

启动后，活跃 selector 必须全量归类为 `selectors` 或 `excluded_selectors`。selector 必须原样来自 AST 地图。不得扫描 `js/plugins` 以外目录，不得把当前运行审计结果当作规则 selector 来源。

### 普通占位符

主代理仍负责最终规则，但必须新增审查任务：`placeholder_rule_review`。

审查重点：

- 是否有未覆盖疑似控制符。
- 是否规则吞掉玩家可见文本。
- 是否规则过宽或过窄。
- 是否外部规则变化后未重新扫描。
- sampled 报告是否被错误当成完整候选。
- `validate --sample` 预览里，去掉占位符后是否仍能看到应该翻译的文本。

规则吞掉玩家可见文本、明显漏保护高风险协议片段、普通规则与结构化需求混淆时，必须给 `blocker`。

### 结构化占位符

主代理仍负责最终规则，但必须新增审查任务：`structured_placeholder_rule_review`。

审查重点：

- 是否有成对外壳被错误拆成普通占位符。
- `translatable_group` 是否真的是玩家可见文本。
- `protected_groups` 是否只保护固定外壳。
- 普通占位符与结构化规则是否重叠。
- 两条结构化规则是否抢同一段文本。
- 是否为通过扫描而编造规则。
- 空结构是否确实已审查。

## 质量和验收

### 协议生成验收

涉及 Skill 协议时必须运行：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

验收点：

- canonical 源和生成目标一致。
- 开发版 Skill 和发行版 Skill 语义一致。
- 新增审查流程只出现在 Skill/协议中，不让 `docs/` 覆盖 Skill。

### 报告 Schema 验收

应固定以下机器可观察边界：

- 工作报告包含 `task_id`、`stage_id`、`agent_role`、`status`、`inputs_read`、`outputs_written`、`selected`、`excluded`、`uncertain`、`active_discoveries`、`evidence`、`risk`。
- 审查报告 findings 的 `severity` 只能是 `blocker | warning | info`。
- 主代理裁决的 `decision` 只能是 `approved | needs_revision | skipped_by_user | blocked`。
- 示例 JSON 不含真实路径、用户名或项目私有数据。

### 流程门禁验收

协议必须明确：

- 存在未关闭 `blocker` 时禁止 validate/import。
- `warning` 放行必须写入主代理裁决。
- 子代理禁止执行状态变更命令。
- 子代理允许只读、导出、扫描、诊断和校验类命令。
- 子代理脚本只能写在 `<工作区>/agent-scratch/`。

### 术语质量验收

术语审查必须覆盖：

- `source == translated` 统计。
- 中英混杂。
- 源文残留。
- 机械拼接。
- 正文术语表过小或过大。
- 字段译名表和正文术语表同名一致。
- 原文保留理由。

### 名字框和占位符验收

协议必须明确：

- MV 名字框工作代理是发现型任务，不得硬套样例。
- 审查必须检查过拟合、漏同类模式、误伤普通正文和无法重建源文本。
- 占位符审查必须检查吞文本、漏保护、规则过宽或过窄、普通/结构化规则混用。
- 世界知识是探索方向，不是固定答案。

### 项目验证

交付前运行：

```powershell
uv run basedpyright
uv run pytest
```

涉及 Skill 协议时额外运行：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```
