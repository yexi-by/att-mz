# 工作区 JSON 结构契约

本文件记录 `prepare-agent-workspace` 生成或回填的常见文件。工作区文件是外部分析和 CLI 校验的唯一交换边界；定位键、路径、ID 和报告字段只按契约原样保留，不从中猜项目内部实现。

## 常见文件

- `manifest.json`：本轮工作区的唯一交换边界，记录 `files`、`generated`、`layout` 和 `workflow`。目录里存在但未列入 `manifest.files` 的文件不属于本轮输入，`validate-agent-workspace` 不会据此启用插件源码或非标准 data 支线，`cleanup-agent-workspace` 也只清理 `manifest.files` 记录的文件并提示未列入文件不会参与本轮验收。
- `mv-virtual-namebox-candidates.json`：MV 专用候选摘要，列出 `101` 后首条非空 `401` 文本；MZ 工作区没有此文件。
- `mv-virtual-namebox-rules.json`：MV 专用虚拟名字框规则。合法空结构是 `{ "rules": [] }`。
- `placeholder-candidates.json`：初始候选控制符报告，只供主代理参考。
- `placeholder-rules.json`：普通占位符规则草稿。最终规则必须在术语和三类外部规则导入后重新确认。
- `structured-placeholder-rules.json`：结构化占位符规则。合法空结构是 `{ "paired_shell_rules": [] }`。
- `terminology/field-terms.json`：字段译名表，只填写 value；用于写回地图显示名、数据库名称、系统类型和 MZ 标准名字框等游戏字段。
- `terminology/glossary.json`：正文术语表，顶层固定为 `terms`，只用于正文翻译提示词命中。
- `terminology/contexts/speakers/*.json`：说话人对白样本。
- `terminology/contexts/database_terms.json`：技能、物品、装备、角色、敌人、状态等术语的只读语义上下文。
- `terminology/subtasks/sources/*.json`：按术语字段拆分的只读子代理输入。
- `terminology/subtasks/candidates/*.json`：术语候选子代理的唯一可写文件。
- `plugins.json`：插件原始 JSON。
- `plugin-json-string-leaf-candidates.json`：插件参数 JSON 字符串内部的字符串叶子候选，只辅助判断路径层级。
- `plugin-rules.json`：插件规则草稿。合法空结构是 `[]`。
- `plugin-source-risk-report.json`：插件源码风险报告、`source_view` 和候选数量摘要，只扫描 `js/plugins` 直接 `.js` 文件；不包含 AST selector、源码偏移、完整候选列表或源码内容。
- `plugin-source-rules.json`：插件源码文本规则草稿。只在插件源码高风险或支线已有规则时生成；合法空结构是 `[]`。
- `nonstandard-data-risk-report.json`：非标准 `data/*.json` 风险报告，只说明文件数、候选数和高低风险。
- `nonstandard-data/candidates.json`：非标准 `data/*.json` 的源语言自然文本候选；只作为非标准 data 支线输入。
- `nonstandard-data/source/*.json`：非标准 data 文件的翻译源视图只读副本，供外部 Agent 核对上下文。
- `nonstandard-data-rules.json`：非标准 data 文本规则草稿。只在存在高风险候选或支线已有规则时生成；合法空结构是 `[]`。
- `event-commands.json`：事件指令参数导出。
- `event-command-rules.json`：事件指令规则草稿。合法空结构是 `{}`。
- `note-tag-candidates.json`：标准 `data/*.json` 中全部 `note` 字段的标签候选报告。
- `note-tag-rules.json`：Note 标签规则草稿。合法空结构是 `{}`。
- `agent-scratch/`：Agent 一次性脚本、统计、抽样、覆盖和反例材料，只服务当前任务审计，不是 CLI 规则事实源。
- `agent-reports/`：工作子代理报告目录，记录读取输入、脚本、CLI 命令、主动发现、候选、证据和风险。
- `review-reports/`：审查子代理报告目录，记录 `blocker`、`warning`、`info` 分级 findings、覆盖检查、过拟合检查和质量检查。
- `review-decisions/`：主代理阶段裁决目录，记录 blocker 关闭方式、warning 确认、用户确认和允许的下一步命令。

`prepare-agent-workspace` 会优先把 CLI 已保存到当前游戏状态里的字段译名表、正文术语表、MV 虚拟名字框规则、插件规则、事件指令规则、Note 标签规则、非标准 data 规则、普通占位符规则和结构化占位符规则回填到工作区。插件源码规则和非标准 data 规则只在高风险或支线已启动时回填。

工作区目录本身不是事实来源；本轮 `manifest.files` 才是 Agent、CLI 校验和清理命令共同认可的输入集合。复用已有工作区时，`plugin-source-rules.json`、`nonstandard-data-rules.json` 或 `nonstandard-data/` 只有在当前 manifest 明确列出时才参与本轮验收。

新增的 `agent-scratch/`、`agent-reports/`、`review-reports/` 和 `review-decisions/` 是 Agent 审计材料。它们可以证明工作过程、审查结论和主代理裁决，但不能单独让文本进入翻译范围，也不能替代规则文件、validate/import 命令或当前游戏已保存状态。

## 报告明细模式

工作区校验和候选扫描报告会用 `summary.report_detail_mode` 标记明细模式。`full` 表示候选数组是完整 `{count, items}`；`sampled` 表示 stdout 只保留 `{count, samples, omitted_count}`。外部 Agent 可以用 `sampled` 快速判断风险，但不能用样本计算确认范围、删除候选或补规则；需要审查全部候选时必须读取 `--output <完整报告>` 写出的 full 明细。

## 规则匹配语法

普通占位符、结构化占位符和 MV 虚拟名字框的 `pattern` 是正则，必须同时通过 Python `re` 和 Rust `fancy-regex` 预检；命名分组统一使用 Python 风格 `(?P<name>...)`。

`source-residual-rules.json` 的 `structural_rules[].pattern` 是正则，必须同时通过 Python `re` 和 Rust `regex` 预检，`check_group` 必须在两边都能识别。`setting.toml` 中 `line_width_count_pattern`、`source_residual_segment_pattern` 和 `residual_escape_sequence_pattern` 也必须同时兼容 Python `re` 和 Rust `regex`；`source_text_required_pattern` 当前只承诺 Python `re`。

Note 标签规则的文件键是 `fnmatch` 风格文件通配模式，例如 `Map*.json`；不是正则。Note 标签名是精确匹配，不支持正则。

## 规则文件结构

### MV 虚拟名字框规则

`mv-virtual-namebox-rules.json` 顶层必须是对象：

```json
{
  "rules": []
}
```

每条规则必须声明 `name`、`pattern`、`speaker_group`、`speaker_policy` 和 `render_template`；有同一行正文时再声明 `body_group`。`pattern` 必须使用 Python 风格正则命名分组并完整匹配候选清理文本。`speaker_policy` 只能是 `translate`、`preserve` 或 `actor_name`。

### 普通占位符规则

`placeholder-rules.json` 顶层必须是 `{正则表达式: 占位符模板}`。占位符模板必须生成形如 `[CUSTOM_NAME_1]` 的方括号占位符，推荐使用 `{index}`。禁止写成 `{占位符名: 正则表达式}`，禁止把 RPG Maker 标准控制符当自定义规则硬写。

工作区验收会报告普通占位符空规则和未覆盖候选 warning，但不要求当前游戏状态里已经存在确认状态。空规则确认和未覆盖候选风险确认由 `import-placeholder-rules` 保存到当前游戏状态；已保存确认只在当前候选范围一致时有效，候选范围变化时重新审查并导入当前规则；不要为了消除工作区 warning 编造规则。

### 结构化占位符规则

`structured-placeholder-rules.json` 顶层必须是对象：

```json
{
  "paired_shell_rules": []
}
```

每条规则必须声明 `name`、`pattern`、`translatable_group` 和 `protected_groups`。`pattern` 必须使用 Python 风格命名分组，`translatable_group` 指向继续交给模型翻译的分组，`protected_groups` 只保护固定协议外壳。

工作区验收会报告结构化占位符空规则和未覆盖候选 warning，但不要求当前游戏状态里已经存在确认状态。空规则确认和未覆盖候选风险确认由 `import-structured-placeholder-rules` 保存到当前游戏状态；已保存确认只在当前候选范围一致时有效，候选范围变化时重新审查并导入当前规则；不要为了消除工作区 warning 编造结构化规则。

### 字段译名表

`terminology/field-terms.json` 顶层固定为术语类别对象，包括 `speaker_names`、`map_display_names`、角色、职业、技能、物品、装备、敌人、状态和系统类型术语。只填写已有 key 对应的 value；不改 key，不新增字段，不写说明字段，不把样本文件路径写入 value。

MV 的 `speaker_names` 是虚拟名字框说话人术语，由已导入 MV 虚拟名字框规则从每个对话块首条非空 `401` 正文识别。它用于译名统一、正文翻译提示词命中，并在写进游戏文件时重建对应 `401` 说话人行或名字标签，不写回 `101.parameters[4]`。

### 正文术语表

`terminology/glossary.json` 顶层必须是：

```json
{
  "terms": {}
}
```

`terms` 的 key 是主代理从字段译名表和上下文中规范化后的原文术语，value 是标准中文译名。正文术语表不是字段译名表副本，不要求字段译名表的每个原文都原样进入 `terms`。字段包装形式、整句、一次性枚举、调试项、数值状态标签、定位信息和说明字段不写入正文术语表；与字段译名表同名的条目必须保持译名一致。`source == translated` 是合法术语，不能因为人名中日同形或用户希望固定不变就过滤掉。

### 插件规则

`plugin-rules.json` 顶层必须是数组：

```json
[
  {
    "plugin_index": 0,
    "plugin_name": "<插件名>",
    "paths": ["$['parameters']['<玩家可见文本字段>']"]
  }
]
```

`plugin_index` 必须是 `plugins.json` 数组下标；`plugin_name` 必须与该下标插件的 `name` 完全一致；JSONPath 必须使用括号路径语法并从 `$['parameters']` 开始。插件参数值如果是 JSON 字符串，规则必须写到解析后的内部字符串叶子。

### 插件源码规则

`plugin-source-rules.json` 顶层必须是数组：

```json
[
  {
    "file": "<插件源码文件名>.js",
    "selectors": ["ast:string:<start>:<end>:<hash>"],
    "excluded_selectors": ["ast:string:<start>:<end>:<hash>"]
  }
]
```

`file` 只能是 `js/plugins` 直接 `.js` 文件名，不能包含目录分隔符。`selectors` 和 `excluded_selectors` 都必须来自 `plugin-source-ast-map.json`，禁止手写或改写，同一个 selector 不能同时出现在两个数组中。低风险且本支线未启动时不需要此文件；高风险或已开始插件源码支线时，活跃源语言候选必须全部归入翻译 selector 或排除 selector。

`plugin-source-ast-map.json` 的候选按 `files[].candidates` 分组读取；顶层只保留风险摘要、启用插件文件名、候选总数和文件数组，不提供重复的全量 `candidates`。候选中的 `ast_context` 是 AST 事实上下文，不是工具对玩家可见性的判断结论。

### 非标准 data 规则

`nonstandard-data-rules.json` 顶层必须是数组：

```json
[
  {
    "file": "<data 第一层 JSON 文件名>",
    "paths": ["$[*]['name']"],
    "excluded_paths": ["$[*]['id']"],
    "skipped": false
  }
]
```

`file` 只能是 `data` 第一层非标准 JSON 文件名，不能包含目录分隔符。`paths` 表示进入正文翻译并允许后续写回的字符串叶子；`excluded_paths` 表示已审查但判定不翻译的候选路径；两者都必须使用括号 JSONPath，并命中 `nonstandard-data/candidates.json` 里的候选。高风险项目必须把每个候选归入 `paths`、`excluded_paths`，或按用户已确认的开局跳过策略按文件写 `skipped: true`。`skipped: true` 时 `paths` 和 `excluded_paths` 必须为空；导入后流程会放行，但 `text-scope`、`audit-coverage`、`quality-report` 和当前运行审计仍会持续 warning。

### 事件指令规则

`event-command-rules.json` 顶层必须是对象：

```json
{
  "<指令编码>": [
    {
      "match": {},
      "paths": ["$['parameters'][0]"]
    }
  ]
}
```

`match` 是参数索引字符串到期望字符串值的对象；没有过滤条件时写 `{}`。`paths` 必须从 `$['parameters']` 开始并命中字符串叶子。

### Note 标签规则

`note-tag-rules.json` 顶层必须是 `{data文件名或fnmatch文件通配模式: [note标签名, ...]}`。文件键可写 `Map*.json` 这类通配模式，但不是正则；只写候选里真实存在的精确标签名，不支持标签正则。禁止选择脚本、公式、资源名、ID、布尔/枚举、数值列表、资源引用、内部关联字段和纯系统标签。

## 手动处理文件

- `pending-translations.json`：还没成功保存译文的文本表。顶层是 `{location_path: 条目对象}`，导入前只填写 `translation_lines` 字符串数组。
- `quality-fix-template.json`：检查没通过译文的修复表。只改 `translation_lines`；其他字段只读原样保留。
- `reset-translations.json`：顶层必须是 `{"location_paths": ["<定位路径>"]}`，只用于显式重置坏译文。
- `source-residual-rules.json`：允许保留源文的例外表，顶层是 `{position_rules, structural_rules}`。`position_rules` 按文本内部位置放行，格式为 `{"<定位路径>": {"allowed_terms": ["<源文片段>"], "reason": "<原因>"}}`；定位键必须来自导出文件或质量检查报告，不允许自造。`allowed_terms` 是允许原样保留的源语言片段字符串数组。英文游戏不靠单字母、单个词、短缩写或专名形态判断漏翻，只在质量报告提示当前原文的大段英文复制残留且确认确实不应翻译时写入例外。`structural_rules` 是结构性例外数组，每项包含 `pattern`、`allowed_terms`、`check_group` 和 `reason`；`structural_rules` 只能遮蔽协议词，显示文本仍会继续做分组源文残留检查。只在确认片段确实不应翻译时使用，禁止在 `pending-translations.json` 内新增例外字段。

填写译文表时只能使用 `original_lines` 里的游戏原始控制符，禁止把 `text_for_model_lines` 中的程序占位符复制进 `translation_lines`。
