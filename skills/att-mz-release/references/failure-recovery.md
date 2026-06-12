# 翻译失败与手动修复

`translate` 返回 0 只表示本轮命令正常结束，不代表所有文本都已经成功保存译文。还没成功保存译文和检查没通过译文都是翻译循环里的正常现象，不是阶段失败。每轮后先运行 `doctor --game <游戏标题> --no-check-llm`，按 `flow_decision` 决定继续翻译、补规则、换模型、手动修复或精确重置。

## 小批量定位

小批量试跑只是微型探测环节，用来观察模型是否能正常响应、规则是否明显误伤玩家可见文本、控制符风险是否扩大、错误类型是否能解释。小批量不追求 0 失败，禁止把 0 失败、质量错误清零或待补译清零当成继续全量翻译的前置指标。

小批量阶段禁止导出质量修复表、禁止导出待补译表、禁止手填译文、禁止为了让样本完美而重置译文。小批量如果没有规则性事故、控制符风险扩大或模型配置错误，就进入全量续跑；真正的收敛依靠全量多轮重试和最后小规模手工收尾。

## 续跑判断

- 每轮 `translate` 后运行 `doctor --game <游戏标题> --no-check-llm`；需要拆细证据时再看 `translation-status --game <游戏标题> --refresh-scope` 和 `quality-report --game <游戏标题> --include-write-probe`。
- 记录本轮开始数量、当前剩余数量、检查没通过的译文数量和主要错误类型。
- `flow_decision=ready_to_translate` 时继续下一轮。
- `flow_decision=should_stop_retrying` 时禁止继续撞同一轮重试；先按质量错误补规则、补占位符/结构化占位符、导出质量修复表或待补译表、精确重置坏译文，或在已授权模型策略内换模型。
- 只有需要用户承担额外额度/时间成本、接受风险、跳过问题或完整重译时才询问用户。

## 质量报告分类

质量报告里的常见明细：

- `quality_error_items`：模型翻了但项目检查没通过的译文。
- `placeholder_risk_items`：必须原样保留的游戏控制符可能被改坏。
- `overwide_line_items`：某一行太长，游戏窗口放不下。
- `source_residual_items`：中文译文里还有疑似没翻的源语言文本。

存在 `quality-report` error 时禁止写进游戏文件。

## 手动修复

手动修复只用于全量多轮重试后的收尾，或连续多轮同类失败不下降后的精确处理。小批量试跑阶段绝对禁止手动修复。进入手动修复条件后，主代理应按报告自动导出修复表、只改中文译文行、导入并复查；不要把“继续重跑、换模型、手动修复、直接写回”做成让用户猜的选择题。

全量多轮后如果质量报告仍有少量可修复明细，运行：

```powershell
.\att-mz.exe export-quality-fix-template --game <游戏标题> --output <工作区>/quality-fix-template.json
```

修复表里只改 `translation_lines`。改完后运行：

```powershell
.\att-mz.exe import-manual-translations --game <游戏标题> --input <工作区>/quality-fix-template.json --check-only
.\att-mz.exe import-manual-translations --game <游戏标题> --input <工作区>/quality-fix-template.json
```

如果只剩还没成功保存译文的文本，且已经全量多轮重试并降到适合手动处理的数量，使用：

```powershell
.\att-mz.exe export-pending-translations --game <游戏标题> --output <工作区>/pending-translations.json
```

需要抽样或分批时追加 `--limit N`。不传 `--limit` 时导出全部剩余文本，但全量导出必须满足“已经降到适合手动处理或多轮不下降”的前置条件。

待补译表改完后也先运行 `import-manual-translations --check-only`。只有保存前校验通过，才去掉 `--check-only` 正式导入；失败时修文件本身，不把半包译文写进数据库。

## 源文残留

发现源文残留时先判断是不是漏翻。日文残留通常按假名、片假名等字符级风险处理；英文残留报告偏高精度，优先表示译文连续复制了当前原文的大段英文。漏翻就修中文译文行后导入。只有致谢名单、Staff 名、作品名、品牌名、游戏内专有名词等确实无需翻译，且质量报告实际提示需要放行的片段，才写入 `source-residual-rules.json` 并运行：

```powershell
.\att-mz.exe validate-source-residual-rules --game <游戏标题> --input <工作区>/source-residual-rules.json
.\att-mz.exe import-source-residual-rules --game <游戏标题> --input <工作区>/source-residual-rules.json
```

源文保留例外必须限制到具体文本内部位置或明确结构性片段，并填写原因。禁止用它掩盖整句漏翻，禁止关闭全局源文残留检测。

## 重置译文

只有确认为坏译文需要重新交给模型翻译时，才使用 `reset-translations`。输入文件只接受：

```json
{
  "location_paths": ["<定位路径>"]
}
```

运行：

```powershell
.\att-mz.exe reset-translations --game <游戏标题> --input <工作区>/reset-translations.json
```

用户明确要求完整重译已完成游戏时，使用：

```powershell
.\att-mz.exe reset-translations --game <游戏标题> --all
```

不要手工拼当前提取范围全集路径，不要把 `translation_lines` 写成空数组来绕过导入校验。

## 常见校验失败

- `placeholder_rules_invalid`：检查是否把 `{正则表达式: 占位符模板}` 写反、模板是否能生成 `[CUSTOM_NAME_1]`、正则是否符合 PCRE2 当前契约。
- `structured_placeholder_rules_invalid`：检查结构化规则 `pattern` 是否符合 PCRE2 当前契约，以及 `translatable_group`、`protected_groups` 是否都来自 PCRE2 命名分组 `(?<name>...)`。
- `mv_virtual_namebox_rules_invalid`：检查 MV 虚拟名字框 `pattern` 是否符合 PCRE2 当前契约，`speaker_group` 和 `body_group` 是否使用 `(?<name>...)`。
- `plugin_rules_invalid`：检查顶层数组、插件下标、插件名、括号 JSONPath、路径是否命中字符串叶子；如果提示 JSON 字符串容器，查看 `plugin-json-string-leaf-candidates.json`；如果提示插件哈希或当前配置不一致，说明工作区导出后插件配置已变化，重新运行 `prepare-agent-workspace`，不要靠猜改路径。
- `event_command_rules_invalid`：检查指令编码是否是字符串数字、`match` 键是否是参数索引、`paths` 是否从 `$['parameters']` 开始。
- `note_tag_rules_invalid`：检查顶层 `{data文件名或fnmatch文件通配模式: [note标签名, ...]}`，文件模式是否使用 `Map*.json` 这类通配而不是正则，标签是否精确命中，是否误选机器协议。
- `manual_translation_invalid`：检查 `translation_lines` 是否为字符串数组、行数是否匹配条目类型、是否残留程序占位符或源文残留。
- `source_residual_rules_invalid`：检查顶层是否是 `{position_rules, structural_rules}`；`position_rules` 的定位键必须来自当前文本内部位置，`allowed_terms` 必须是非空字符串数组且片段出现在当前条目原文或译文中，`reason` 必须非空；`structural_rules` 必须包含符合 PCRE2 当前契约的 `pattern`、非空 `allowed_terms`、可用的 `check_group` 和非空 `reason`。

无法把错误信息对应到工作区 JSON，或同一合法文件反复触发无法解释的 CLI 错误时，停止翻译流程并报告工具问题。
