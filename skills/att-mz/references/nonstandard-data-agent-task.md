# 非标准 data 文本支线任务

本任务只处理非标准 `data/*.json` 中已经被工具标成高风险的源语言自然文本候选。它不是日常默认任务；没有非标准 data 文件，或只有资源名、公式、ID、布尔、数字和协议值时，不启动本任务。

本支线一旦启动，必须按 `agent-review-workflow.md` 走工作、审查和主代理裁决。工作子代理全量归类候选，审查子代理检查未归类、误选、误排、路径真实性和用户跳过确认；存在未关闭 `blocker` 时禁止导入。

## 触发条件

- 默认先读取 `nonstandard-data-risk-report.json`。低风险默认只报告，不启动本任务。
- 高风险时按开局支线策略处理；默认自动处理并继续流程。只有策略缺失且处理会显著增加成本/风险，或用户已明确选择快速跳过时，才停下说明并记录跳过确认。
- 需要处理时，只使用 `prepare-agent-workspace` 已生成的 `nonstandard-data/candidates.json` 和 `nonstandard-data/source/*.json`。

## 输入

- `<工作区>/nonstandard-data-risk-report.json`
- `<工作区>/nonstandard-data/candidates.json`
- `<工作区>/nonstandard-data/source/*.json`
- 当前游戏已注册标题和源语言

读取边界：

- 允许读取候选文件中的 `file`、`json_path`、`source_text`、字段名和相邻字段信息。
- 允许只读 `nonstandard-data/source/*.json` 中同名 JSON 副本，用于核对对象结构和上下文。
- 不读取 A.T.T MZ 项目源码、数据库、内部 Python 对象或游戏目录其他文件。
- 不修改源 JSON 副本，不写回游戏文件，不直接改数据库。

## 输出

唯一可写最终规则文件是 `<工作区>/nonstandard-data-rules.json`，顶层必须是数组。工作报告写入 `<工作区>/agent-reports/branch_rules/nonstandard_data_classification.json`，一次性脚本和统计写入 `<工作区>/agent-scratch/branch_rules/nonstandard_data_classification/`：

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

`paths` 表示进入正文翻译并允许后续写回的字符串叶子；`excluded_paths` 表示已经审查但判定不翻译的候选路径。两者都只能使用 `candidates.json` 中同一文件下的括号 JSONPath。不能使用点号 JSONPath，不能手写不存在的路径。

`skipped: true` 只能在用户明确确认“本文件本轮不处理”或开局策略允许快速跳过后使用，并且 `paths` 和 `excluded_paths` 必须为空。跳过会让流程放行，但后续报告会持续 warning，不能把它写成“已确认没有文本”。

## 处理逻辑

- 必须全量归类 `candidates.json` 中的每个候选：进入 `paths`、进入 `excluded_paths`，或按用户已确认的跳过策略按文件 `skipped: true`。
- 只选择玩家可见的 UI、菜单、说明、任务、状态、提示和对话文本。
- 排除资源路径、图片/音频文件名、脚本、公式、ID、布尔值、数字、枚举、内部键、颜色、坐标和纯协议值。
- 判断不清时，用同一对象的字段名、相邻字段、重复结构、同文件样本和源 JSON 副本交叉验证；证据不足时向主代理报告，不编造规则。
- 完成后运行 `uv run python main.py validate-nonstandard-data-rules --game <游戏标题> --input <工作区>/nonstandard-data-rules.json`。
- validate 前必须完成 `nonstandard_data_review`，审查报告写入 `<工作区>/review-reports/branch_rules/nonstandard_data_review.json`。
- 主代理读取工作报告、审查报告和候选文件，写入 `<工作区>/review-decisions/branch_rules.json`；存在未关闭 `blocker` 时停止。
- validate 通过且主代理裁决为 `approved` 后运行 `uv run python main.py import-nonstandard-data-rules --game <游戏标题> --input <工作区>/nonstandard-data-rules.json`。

## 停止条件

- 高风险支线策略缺失，且当前文件不能由主代理在本轮自动处理或跳过。
- `candidates.json` 缺失或与源 JSON 副本对不上。
- 规则校验返回 error。
- 审查报告存在未关闭 `blocker`。
- 仍有候选没有归类。
- 需要读取工作区以外的游戏文件或项目源码才能判断。

## 完成报告

工作报告必须报告处理的文件数、翻译路径数、排除路径数、跳过文件数、未归类候选数、脚本和统计产物、validate 建议命令和仍需主代理确认的风险。交叉验证摘要必须说明选中项依据、重点排除项依据、跳过确认依据和空结果依据。审查报告必须用 `blocker`、`warning`、`info` 分级说明未归类、误选、误排、路径失效和越权读取风险。
