# 非标准 data 文件文本支线设计

日期：2026-06-01

## 背景

部分 RPG Maker MV/MZ 游戏会在 `data/` 第一层放置插件自定义 JSON 文件，例如配方、制作分类、任务或图鉴数据。这些文件不属于 RPG Maker 标准 data 文件，也不是 `MapXXX.json`，现有标准 data 提取流程不会把它们纳入正文翻译范围。

本设计新增一条“非标准 data 文件文本”支线。它对齐现有插件源码文本支线：普通流程只做风险扫描；只有发现高风险、已有规则，或用户明确要求处理时，才进入 Agent/LLM 分析与规则导入流程。

## 目标

- 在准备工作区阶段发现非标准 `data/*.json` 中可能存在的玩家可见源语言文本。
- 高风险时阻止正文翻译直接继续，除非用户按文件确认跳过或已导入规则。
- 支持 Agent 按工作区文件分析非标准 JSON 字段语义，输出可校验、可导入的规则。
- 规则导入后，非标准 JSON 文本进入统一文本清单，复用现有正文翻译、质量检查和写进游戏文件流程。
- 写进游戏文件后能在当前运行视图审计这些非标准 JSON 的写回结果。
- 第一版只处理 `data/*.json` 第一层文件，但内部边界为后续其他文件类型预留扩展点。

## 非目标

- 第一版不处理 `data/*.txt`、`data/*.csv`、二进制数据、子目录 JSON 或插件源码外的其他脚本文件。
- 程序内部不直接调用模型生成规则；LLM/Agent 只通过工作区支线契约分析候选文件。
- 第一版不承诺保留非标准 JSON 原始缩进、换行或格式，只保证 JSON 合法、结构和值正确。

## 命名与范围

用户文案统一使用“非标准 data 文件文本”。

第一版扫描范围：

```text
data/*.json
```

排除：

```text
RPG Maker 标准 data 文件
MapXXX.json
data 子目录中的文件
非 JSON 文件
```

内部来源类型建议命名为 `nonstandard-data`。第一版 provider 可以命名为 `nonstandard-data-json`，后续新增文件类型时挂到同一支线框架下。

## 风险扫描

准备工作区和独立扫描命令都读取翻译源视图。非标准 JSON 也必须纳入注册游戏时的原始备份和可信源快照，避免规则分析回退到当前运行文件。

风险定义：

```text
高风险 = 存在非标准 data/*.json，且其中存在符合当前 source_language 的疑似自然文本字符串
低风险 = 没有非标准 data/*.json，或只有资源名、公式、ID、布尔、数字、协议值等非源语言自然文本
```

源语言检测必须跟随游戏注册时的 `source_language`。英文游戏检测英文自然文本，日文游戏检测日文自然文本；不能因为日文游戏里有英文协议值就误报高风险。

非标准 JSON 文件读取失败或 JSON 解析失败时返回 error，阻止继续。工具不能在无法判断文件内容时假装没有漏翻风险。

## 工作区产物

准备工作区时始终生成：

```text
<工作区>/nonstandard-data-risk-report.json
```

高风险或当前游戏已有规则时，额外生成：

```text
<工作区>/nonstandard-data-rules.json
```

支线导出命令生成：

```text
<工作区>/nonstandard-data/
  candidates.json
  source/
    <非标准 data 文件>.json
```

`candidates.json` 只提供事实信息，不提供机器初判类别或翻译建议。建议字段：

```text
file
json_path
source_text
field_name
occurrence_count
samples_for_same_path
sibling_field_names
parent_object_keys
```

不写入：

```text
natural_text_candidate
resource_like
formula_like
enum_or_protocol_like
建议翻译
建议排除
```

## CLI 命令

新增命令按规则流程拆分：

```text
scan-nonstandard-data
export-nonstandard-data-json
validate-nonstandard-data-rules
import-nonstandard-data-rules
```

职责：

- `scan-nonstandard-data`：生成风险报告。
- `export-nonstandard-data-json`：生成候选报告和原始 JSON 副本。
- `validate-nonstandard-data-rules`：校验规则结构、路径模板、覆盖状态和当前文件命中。
- `import-nonstandard-data-rules`：导入规则和按文件跳过状态。

命令默认使用翻译源视图做规则分析。当前运行视图用于写进游戏文件后审计与诊断。

## 规则文件

`nonstandard-data-rules.json` 放在工作区根目录，顶层为数组。每个非标准 JSON 文件一项：

```json
[
  {
    "file": "Recipes.json",
    "paths": [
      "$[*]['Name']",
      "$[*]['Category'][*]"
    ],
    "excluded_paths": [
      "$[*]['Type']",
      "$[*]['Learned']"
    ],
    "skipped": false
  },
  {
    "file": "OldBackup.json",
    "paths": [],
    "excluded_paths": [],
    "skipped": true
  }
]
```

规则字段：

- `file`：`data/` 第一层非标准 JSON 文件名，不能包含目录分隔符。
- `paths`：进入正文翻译的受限 JSONPath 模板。
- `excluded_paths`：已审查但不翻译的受限 JSONPath 模板。
- `skipped`：用户按文件明确确认跳过。

路径语法：

- 每个文件自身 JSON 顶层为 `$`。
- 支持顶层数组和顶层对象。
- 使用受限 JSONPath 括号语法，例如 `$[*]['Name']`。
- 禁止点号路径。

约束：

- `skipped=true` 时，`paths` 和 `excluded_paths` 必须为空。
- `skipped=false` 时，`paths + excluded_paths` 必须覆盖该文件全部源语言自然文本候选。
- `paths` 与 `excluded_paths` 不能重叠。
- `paths` 可以为空，但此时 `excluded_paths` 仍必须覆盖已审查候选，或文件必须 `skipped=true`。
- Agent 不能自行把高风险文件标为 `skipped=true`；该状态只能来自用户按文件明确确认。
- 排除理由不写进规则文件，只写在 Agent 完成报告中。

校验只要求覆盖风险候选中的源语言自然文本字符串，不要求覆盖所有字符串叶子。资源名、公式、协议值等普通字符串不进入全量归类门禁。

## 门禁行为

正文翻译前检查：

```text
低风险 -> 放行
高风险 + 已导入有效规则 -> 放行
高风险 + 用户按文件确认跳过 -> 放行并持续 warning
高风险 + 未处理也未确认跳过 -> 阻止正文翻译
已启动支线但仍有未归类候选 -> 阻止正文翻译
规则过期或模板不命中 -> 阻止正文翻译
```

确认跳过的粒度是文件。跳过后覆盖审计、质量报告或工作区验收仍持续输出 warning，说明对应非标准 data 文件文本可能残留源文。

规则过期策略与现有外部规则一致：文件缺失、文件 hash 或结构变化导致模板失效、规则不再命中当前候选时，返回 error，要求重新导出并导入规则。第一版不做部分命中继续。

## 提取与保存

规则导入后，非标准 JSON 文本进入统一文本清单，不独立建立翻译器。后续复用：

```text
提取 -> 去重 -> 翻译 -> 保存译文 -> 质量检查 -> 写进游戏文件 -> 当前运行视图审计
```

定位路径使用独立前缀，避免与标准 data、插件参数或事件指令混淆：

```text
nonstandard-data/<文件名>/<精确 JSONPath>
```

示例：

```text
nonstandard-data/Recipes.json/$[1]['Name']
nonstandard-data/Disciplines.json/$[1]['Categories'][0]
```

## 写进游戏文件与审计

写进游戏文件时，按规则命中的精确字符串叶子替换译文。未命中的字段不做语义修改。

第一版允许统一重新序列化 JSON，不承诺保留原始格式。验收重点：

- JSON 文件仍合法。
- 未命中字段结构和值保持语义不变。
- 命中字段写入对应译文。
- 当前运行视图能审计已管理非标准 JSON 文本是否仍有漏写、坏结构或规则失效。

写回目标是当前运行 `data/` 目录；规则分析和翻译源提取使用翻译源视图。

## Agent 契约

新增开发版和发行版支线契约：

```text
skills/att-mz/references/nonstandard-data-agent-task.md
skills/att-mz-release/references/nonstandard-data-agent-task.md
```

契约要点：

- 只读 `<工作区>/nonstandard-data/candidates.json` 和 `<工作区>/nonstandard-data/source/*.json`。
- 不读取项目源码、数据库、内部 Python/Rust 对象或游戏其他目录。
- 只判断玩家可见自然文本字段。
- 唯一输出文件是 `<工作区>/nonstandard-data-rules.json`。
- 高风险支线启动后必须全量归类候选。
- `skipped=true` 只能来自用户按文件确认。
- validate 失败时只修规则文件后重跑。
- 完成报告必须说明选中依据、排除依据、是否存在用户确认跳过文件、validate 命令和未解决风险。

## 测试验收

需要覆盖：

- 非标准 JSON 纳入原始备份和可信源快照。
- 低风险只生成风险报告，不生成规则草稿，不阻塞正文翻译。
- 高风险生成规则草稿，并在未处理时阻塞正文翻译。
- 用户按文件 `skipped=true` 后放行，但报告持续 warning。
- `paths/excluded_paths` 全量归类校验。
- `skipped=true` 与路径规则互斥。
- 文件名含目录分隔符、点号 JSONPath、模板重叠、模板不命中、规则过期均报 error。
- 非 UTF-8、JSON 解析失败、顶层对象和顶层数组行为。
- 规则命中文本进入统一文本清单，定位路径使用 `nonstandard-data/` 前缀。
- 翻译后能写回非标准 JSON，且重新序列化后 JSON 合法。
- 写进游戏文件后当前运行视图能审计非标准 JSON 写回结果。
- Skill 开发版和发行版契约语义一致。

## 已确认决策

- 第一版只处理 `data/*.json` 第一层。
- 高风险定义只看当前源语言自然文本。
- 支线启动后全量归类候选。
- 规则使用路径模板，不使用逐条 ID。
- 规则文件同时包含 `paths` 和 `excluded_paths`。
- Agent 输入包含候选报告和原始 JSON 副本。
- 规则分析读翻译源视图，审计读当前运行视图。
- 用户可按文件确认跳过，高风险跳过后持续 warning。
- 候选报告不提供机器初判类别。
- 排除理由不写规则文件。
- 规则过期直接 error。
- 覆盖校验只覆盖风险候选中的源语言自然文本。
- `skipped=true` 放在同一个规则文件内，且与路径规则互斥。
- 非标准 JSON 纳入原始备份和可信源快照。
- CLI 不直接调用模型。
- 工作区低风险只生成风险报告，高风险或已有规则才生成规则草稿。
- 命名统一为 `nonstandard-data` 和“非标准 data 文件文本”。
- CLI 拆分为扫描、导出、校验、导入四段。
- 导出目录为 `<工作区>/nonstandard-data/`。
- JSONPath 根节点为文件自身 `$`。
- 支持顶层对象和顶层数组。
- JSON 读写失败显式 error。
- 写回第一版不保留原始格式。
