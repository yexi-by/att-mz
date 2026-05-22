# 插件源码文本支线任务

本任务只处理 `<游戏目录>/js/plugins` 直接 `.js` 文件中的硬编码显示文本。它是罕见高风险支线，不替代插件参数规则、事件指令规则或 Note 标签规则。

## 触发条件

- 默认先读取 `plugin-source-risk-report.json`。低风险只报告，不启动本任务。
- 高风险时必须先问用户是否处理插件源码文本；用户没有肯定回复时，停止正文翻译。
- 用户肯定后，运行 `export-plugin-source-ast-map --game <游戏标题> --output <工作区>/plugin-source-ast-map.json --json`。

## 输入

- `<工作区>/plugin-source-risk-report.json`
- `<工作区>/plugin-source-ast-map.json`
- 当前游戏已注册标题和源语言

AST 地图用于候选筛选和写回定位，插件源码只读用于语义交叉验证。用户确认启动本支线后，允许读取 `<游戏目录>/js/plugins/*.js` 直接文件，结合源码注释、插件头、相邻对象字段、函数名、数组语义和调用位置判断 selector 是否属于玩家可见文本。

读取边界：

- 允许读取 AST 地图中的候选、文件名、selector、上下文和风险摘要。
- 允许只读对应的 `<游戏目录>/js/plugins/<插件源码文件名>.js` 直接文件。
- 不扫描 `js` 根目录，不递归子目录，不读取 `data` 目录。
- 不读取 A.T.T MZ 项目源码或数据库。
- 不修改 JS 源码，不写回游戏文件，不直接改数据库。

## 输出

唯一可写文件是 `<工作区>/plugin-source-rules.json`，顶层必须是数组：

```json
[
  {
    "file": "<插件源码文件名>.js",
    "selectors": ["ast:string:<start>:<end>:<hash>"]
  }
]
```

合法空结构是 `[]`。高风险空结构只能在用户明确确认当前游戏不需要插件源码文本规则后，用 `import-plugin-source-rules --confirm-empty` 保存。

## 处理逻辑

- 先用 AST 地图按文件、上下文和置信度做第一轮筛选；对无法仅凭候选判断的文件，再只读对应插件源码交叉验证。
- 源码注释、插件头、相邻 key、对象/数组结构和调用函数只能用于判断语义，不能写进规则文件。
- 只选择玩家可见 UI、说明、角色简介、战斗消息、菜单项和对话文本。
- 不选择资源路径、脚本片段、开关名、内部状态、调试文本、公式、数字和布尔枚举。
- 同一显示文本有多个 selector 时，只保留真实写回位置；无法判断时不要编造规则。
- selector 必须来自 AST 地图原样复制，禁止手写字节范围或改写 selector。
- `plugin-source-rules.json` 完成后运行 `validate-plugin-source-rules --game <游戏标题> --input <工作区>/plugin-source-rules.json --json`。
- validate 通过后运行 `import-plugin-source-rules --game <游戏标题> --input <工作区>/plugin-source-rules.json --json`。

## 停止条件

- 用户未确认处理高风险插件源码文本。
- AST 地图无法生成或 selector 反复失效。
- 规则校验返回 error。
- 需要扫描 `js/plugins` 以外目录。

## 完成报告

报告选择的文件数、selector 数、交叉验证摘要、validate 结果、导入结果和仍需人工确认的候选类别。交叉验证摘要必须说明读取过哪些直接插件源码文件、源码注释或相邻结构如何支持选中项、哪些高疑似候选被排除。导入完成后，重新准备工作区或重新扫描占位符候选，再进入占位符收束阶段。
