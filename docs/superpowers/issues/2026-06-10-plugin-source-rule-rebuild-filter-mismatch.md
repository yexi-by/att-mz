# 插件源码规则校验与重建索引候选口径不一致

## 状态

- 状态：open
- 严重级别：P0
- 类型：工具链阻断
- 发现日期：2026-06-10
- 影响命令：
  - `validate-plugin-source-rules`
  - `import-plugin-source-rules`
  - `export-plugin-source-ast-map`
  - `rebuild-text-index`
  - `translate`
  - `write-back`

## 结论

插件源码规则的导出、校验、导入链路与 Rust `rebuild-text-index` 链路使用了不一致的候选过滤口径。

结果是：规则文件可以被 `validate-plugin-source-rules` 判定为“全部已审查”，也可以被 `import-plugin-source-rules` 成功导入，但随后 `rebuild-text-index` 会在同一批已导入 selector 上报 `stale_plugin_source_rules`，导致翻译续跑和写回无法继续。

这不是目标游戏文本无法修复，也不是继续重试翻译可以收敛的问题；这是工具内部契约冲突。

## 用户可见现象

1. Agent 导入插件源码规则后，校验报告显示：
   - `reviewed_selector_count` 等于当前规则 selector 总数。
   - `unreviewed_selector_count` 为 `0`。
   - `errors` 为空。
2. 继续执行：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```

3. 命令失败，返回：

```json
{
  "status": "error",
  "errors": [
    {
      "code": "stale_plugin_source_rules",
      "message": "插件源码规则已过期: <插件文件名>.js: 插件源码 selector 已无法命中当前 AST 地图，请重新导出并导入插件源码规则（stale_plugin_source_rules）"
    }
  ]
}
```

4. 再次重新导出、重新导入规则后，仍可能重复同样失败。

## 影响

- `rebuild-text-index` 无法完成。
- `translate` 在进入正文重试前被文本范围索引阻断。
- `audit-coverage` 和 `quality-report` 无法进入可写回前置验收。
- `write-back --confirm-font-overwrite` 不能安全执行。
- Agent 容易误判为“插件源码规则没补完”或“翻译质量错误需要继续重试”，从而浪费多轮任务时间。

## 已确认的行为证据

在一个实际任务中，公开 CLI 出现以下互相矛盾的结果：

- 插件源码规则校验通过：

```json
{
  "status": "ok",
  "summary": {
    "file_count": 46,
    "selector_count": 0,
    "excluded_selector_count": 2269,
    "reviewed_selector_count": 2269,
    "unreviewed_selector_count": 0
  }
}
```

- 随后重建文本索引失败：

```json
{
  "status": "error",
  "errors": [
    {
      "code": "stale_plugin_source_rules",
      "message": "插件源码规则已过期: <插件文件名>.js: 插件源码 selector 已无法命中当前 AST 地图，请重新导出并导入插件源码规则（stale_plugin_source_rules）"
    }
  ],
  "summary": {
    "index_status": "rebuild_failed"
  }
}
```

同一目标中，插件源码原始快照与当前源码文件 hash 一致，因此该问题不是由插件源码文件被手动修改引起。

## 初步根因

当前实现里存在两条不同的插件源码候选链路。

### 规则导出、扫描、校验链路

Python 侧构造 Rust 规则候选扫描 payload 时，`build_native_rule_candidate_text_rules_payload()` 使用宽松预筛：

```python
"source_text_required_pattern": r"[\s\S]"
```

然后插件源码扫描结果在 Python 报告层再调用 `TextRules.should_translate_source_text()` 做最终过滤。

相关位置：

- `app/native_scope_index.py`
- `app/plugin_source_text/native_scan.py`
- `app/agent_toolkit/services/rule_validation.py`

### 重建索引链路

`rebuild_text_index_native_storage_with_summary()` 构造 Rust 重建 payload 后，把规则候选文本规则里的 `source_text_required_pattern` 改成配置里的真实源文识别正则：

```python
rule_candidate_text_rules = build_native_rule_candidate_text_rules_payload(text_rules)
rule_candidate_text_rules["source_text_required_pattern"] = setting.text_rules.source_text_required_pattern
```

随后 Rust `collect_plugin_source_managed_texts()` 用这套候选集合检查数据库里已保存的插件源码 selector。只要数据库规则中存在一个 selector 不在这条链路扫描出的 candidates 里，就报：

```text
stale_plugin_source_rules
```

相关位置：

- `app/text_index.py`
- `rust/src/native_core/scope_index/plugin_source.rs`
- `rust/src/native_core/scope_index/rebuild.rs`

### 契约冲突

插件源码规则导入使用的是“公开规则工作流看到的候选集合”，而 `rebuild-text-index` 验证 selector 是否仍有效时使用的是“重建索引看到的候选集合”。

只要两个集合不完全一致，就会出现：

- 规则工作流认为 selector 合法且已审查。
- 重建索引认为同一个 selector 已无法命中当前 AST 地图。

这违反了插件源码 selector 的单一事实来源要求。

## 额外风险点

`validate_plugin_source_rules()` 和 `import_plugin_source_rules()` 还有一个当前排除规则 fast path：

如果导入文件与数据库中当前排除规则一致，并且文本索引 metadata 记录插件源码支线已预检通过，命令可能直接返回当前规则报告，而不重新执行完整插件源码扫描。

这会放大问题：

- 报告仍显示 `unreviewed_selector_count=0`。
- 但 `rebuild-text-index` 仍可能失败。
- Agent 会看到“校验通过”和“重建失败”两个相反信号。

相关位置：

- `app/agent_toolkit/services/rule_validation.py`

## 期望行为

插件源码 selector 的生命周期应只有一套当前事实：

1. `export-plugin-source-ast-map` 导出的候选。
2. `validate-plugin-source-rules` 用来判断 selector 是否有效和是否全量审查的候选。
3. `import-plugin-source-rules` 写入数据库前使用的候选。
4. `rebuild-text-index` 判断 selector 是否 stale 的候选。

以上四者必须完全一致。

如果某个 selector 在导入时有效，且插件源码文件内容未变化、启用状态未变化、规则相关配置未变化，则 `rebuild-text-index` 不能立刻把它判为 stale。

如果配置或规则导致候选集合变化，校验和导入命令必须先暴露同样的变化，不能等到 `rebuild-text-index` 才失败。

## 建议修复方向

优先做结构性修复，不建议用特殊 selector 白名单、字符串识别或错误吞噬绕过。

建议方向：

1. 明确插件源码候选集合的唯一构造入口。
2. 让 `export-plugin-source-ast-map`、`scan-plugin-source-text`、`validate-plugin-source-rules`、`import-plugin-source-rules` 和 `rebuild-text-index` 共享同一套 `RuleCandidateTextRules` 语义。
3. 删除或收紧会掩盖完整扫描的 fast path，至少在规则 hash、文本规则 hash 或候选口径可能变化时不得跳过真实校验。
4. 错误报告应区分：
   - 文件不存在。
   - 插件未启用。
   - 文件内容变化。
   - selector 仍在 AST 中但被当前候选过滤规则排除。
   - selector 真正从 AST 消失。

其中“selector 仍在 AST 中但被过滤规则排除”不应伪装成“当前 AST 地图无法命中”，否则排障方向会错误。

## 验收标准

必须新增回归测试覆盖以下行为：

1. 插件源码规则中只包含 `excluded_selectors` 时，导入后 `rebuild-text-index` 能成功通过。
2. 包含短协议片段、资源路径样式文本或英文协议噪音的插件源码 selector，如果被规则导出和导入链路要求审查，重建索引链路也必须承认同一 selector。
3. 如果 selector 对应的 JS 字符串仍存在 AST 中，但被源文识别规则过滤掉，错误码和错误文案必须指出是候选过滤口径变化，而不是“selector 无法命中当前 AST 地图”。
4. `validate-plugin-source-rules` 的 fast path 不得让已过期或口径不一致的规则显示为完全通过。

建议执行：

```powershell
uv run pytest tests/test_plugin_source_text.py tests/test_text_index.py -q
uv run basedpyright
uv run pytest
```

如果修复触及 Rust 原生扩展，还需要执行 Rust 格式检查、clippy 和 Rust 测试。

## 当前任务处理建议

在该问题修复前，遇到以下组合时应直接停止翻译流程并报告工具阻断：

- `validate-plugin-source-rules` 显示插件源码规则已全量审查。
- `import-plugin-source-rules` 成功。
- `rebuild-text-index` 仍返回 `stale_plugin_source_rules`。
- 已确认插件源码快照和当前源文件未变化。

不要继续执行多轮 `translate`。这类重试不会减少错误数量，也不会解除 `rebuild-text-index` 阻断。
