# MV 虚拟名字框规则

本参考只用于 RPG Maker MV。MZ 使用标准 `101.parameters[4]` 名字框，不使用本规则。

MV 没有官方名字框字段。很多游戏用插件或事件约定把说话人写在 `101` 后第一条非空 `401` 正文里，例如独立名牌行、正文前缀、控制符包裹名牌或动态角色名。本阶段采用发现型任务：工作子代理主动发现当前游戏的发言人/名牌模式，审查子代理反向检查过拟合、漏同类和误伤，主代理裁决后才允许导入。不要把任何样例当成当前游戏固定答案。

## 工作顺序

1. 准备工作区后，先读取 `mv-virtual-namebox-candidates.json`。
2. 按 `agent-review-workflow.md` 派发 `mv_namebox_discovery` 工作任务。工作子代理可以在 `<工作区>/agent-scratch/mv_virtual_namebox/mv_namebox_discovery/` 写一次性脚本，统计对白块开头短文本、重复前缀、包裹符号、控制符、插件名牌形态、覆盖样本和误伤样本。
3. 工作子代理只写 `<工作区>/mv-virtual-namebox-rules.json`、`agent-reports/mv_virtual_namebox/mv_namebox_discovery.json` 和审计材料；不得导入规则。
4. 运行 `validate-mv-virtual-namebox-rules --game <游戏标题> --input <工作区>/mv-virtual-namebox-rules.json --output <工作区>/mv-virtual-namebox-validate-report.json`。
5. 派发 `mv_namebox_review` 审查任务，读取规则草稿、validate 报告、工作报告和脚本产物，检查过拟合、漏掉同类高频模式、普通正文误伤、动态控制符误翻、speaker/body 分组不稳定和模板无法重建源文本。
6. 主代理读取工作报告、审查报告和校验报告，检查 `newly_matched_candidates`，确认每个新命中样本确实是说话人名字框；不是说话人的样本必须通过收紧规则排除。
7. 主代理写 `<工作区>/review-decisions/mv_virtual_namebox.json`。存在未关闭 `blocker` 时禁止导入。
8. 校验通过且裁决为 `approved` 后运行 `import-mv-virtual-namebox-rules --game <游戏标题> --input <工作区>/mv-virtual-namebox-rules.json`。
9. 如果发现和审查都确认当前 MV 游戏没有虚拟名字框规则，文件写成 `{"rules":[]}`，裁决记录空结果理由，导入时加 `--confirm-empty`。
10. 重新运行 `prepare-agent-workspace --game <游戏标题> --output-dir <工作区>`，再开始术语候选第一轮。

## JSON 结构

合法空结构：

```json
{"rules":[]}
```

非空结构：

```json
{
  "rules": [
    {
      "name": "standalone-colon",
      "pattern": "^(?<speaker>[^：\\\\r\\\\n]{1,40})：$",
      "speaker_group": "speaker",
      "speaker_policy": "translate",
      "render_template": "{speaker}："
    }
  ]
}
```

每条规则必填 `name`、`pattern`、`speaker_group`、`speaker_policy`、`render_template`。有同一行正文时填写 `body_group`，没有正文组表示独立名字行。

`pattern` 必须使用正则命名分组，并完整匹配 `101` 后第一条非空 `401` 的清理文本。`speaker_group` 指向说话人分组。`body_group` 指向同一行正文分组。`render_template` 只能引用正则命名分组，以及 `{speaker}`、`{body}`。

`pattern` 必须是 PCRE2 正则。命名分组统一使用 PCRE2 写法 `(?<name>...)`，`speaker_group` 和 `body_group` 必须对应这种写法；不要使用其它正则方言的命名分组。校验和导入阶段会提前预检，当前游戏已保存规则不满足当前契约时 `doctor`、`text-scope`、`audit-coverage` 和 `quality-report` 会返回 `mv_virtual_namebox_rules_invalid`。

`speaker_policy` 只能是：

- `translate`：说话人进入 `speaker_names`，写回时用字段译名表译名渲染。
- `preserve`：说话人不进入 `speaker_names`，写回时保留源文本，适合必须保留的动态控制符。
- `actor_name`：说话人分组是 `\N[n]` 这类角色名控制符，术语 key 使用数据库角色名，写回时用字段译名表译名渲染。

## 收紧原则

- 动态角色名、游戏控制符和必须原样保留的协议标记优先写成单独规则，并使用 `preserve` 或 `actor_name`。
- 普通尖括号、方括号、书名号名字框必须按当前候选确认出的说话人白名单收紧，例如把候选里真实存在的角色名写成正则候选组；不要使用能吞掉全部尖括号内容的通配规则。
- 遇到 `<角色A><角色B>`、`角色A・角色B：`、`角色A＆角色B` 这类组合名字框时，按当前游戏候选和显示规则审查是否应该作为一个组合 key、拆成两个说话人，或保留源格式；不要默认把组合 key 当成通用工具缺陷。
- 校验报告中的 `newly_matched_candidates` 表示相对已保存规则多命中的候选。主代理必须逐条看 `text`、`matching_rules` 和 `matches`，确认这些样本是否应该进入虚拟名字框。
- 如果同一候选命中动态规则和普通规则，普通规则必须继续收紧。依靠规则顺序遮住宽规则不是合格结果。

## 可用样例

独立名字行：

```json
{
  "name": "standalone-colon",
  "pattern": "^(?<speaker>[^：\\\\r\\\\n]{1,40})：$",
  "speaker_group": "speaker",
  "speaker_policy": "translate",
  "render_template": "{speaker}："
}
```

内联正文：

```json
{
  "name": "quote-inline",
  "pattern": "^(?<speaker>[^「\\\\r\\\\n]{1,40})「(?<body>.*)$",
  "speaker_group": "speaker",
  "body_group": "body",
  "speaker_policy": "translate",
  "render_template": "{speaker}「{body}"
}
```

控制符包裹名牌：

```json
{
  "name": "control-angle-inline",
  "pattern": "^(?<command>\\\\[Nn])<(?<speaker>[^>\\\\r\\\\n]{1,80})>(?<body>.*)$",
  "speaker_group": "speaker",
  "body_group": "body",
  "speaker_policy": "translate",
  "render_template": "{command}<{speaker}>{body}"
}
```

动态角色名原样保留：

```json
{
  "name": "dynamic-angle",
  "pattern": "^<(?<speaker>\\\\[Nn]\\\\[\\\\d+\\\\])>$",
  "speaker_group": "speaker",
  "speaker_policy": "preserve",
  "render_template": "<{speaker}>"
}
```

角色名控制符转数据库角色名：

```json
{
  "name": "actor-inline",
  "pattern": "^(?<speaker>\\\\[Nn]\\\\[(?<actor_id>\\\\d+)\\\\])(?<separator>[:：])(?<body>.*)$",
  "speaker_group": "speaker",
  "body_group": "body",
  "speaker_policy": "actor_name",
  "render_template": "{speaker}{separator}{body}"
}
```

## 反例

- 把所有 `^<.*>$` 都当名字框：会误吞成对标签、脚本片段和普通正文。
- 使用 `^<(?<speaker>[^>]+)>$` 这类普通尖括号宽规则：会误吞动态角色名控制符、系统标签和制作名单标签；应当改成动态控制符专用规则加当前游戏说话人白名单规则。
- 把任何冒号前短文本都当说话人：会误判说明句、选择提示和 UI 文案。
- 规则命中 `\N[999]` 这类不存在角色 ID，却使用 `actor_name`：校验或提取会失败。
- 模板不能重建源文本：例如源文本使用半角冒号，模板固定全角冒号。
- 在规则 JSON 中加入游戏标题、本地目录、说明字段或版本号：主流程不读取这些字段，导入会拒绝。
