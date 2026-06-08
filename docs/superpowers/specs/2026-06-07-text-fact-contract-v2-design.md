# Text Fact Contract v2 当前契约

本文只描述 A.T.T MZ 当前实现中的文本事实契约，供维护者理解源码与用户文档之间的边界。翻译流程、子代理任务、阶段门槛和黑盒执行步骤放在 `skills/att-mz-protocol/`，再由生成脚本输出到开发版与发行版 Skill；本文不作为 Agent 执行契约。

## 当前行为

A.T.T MZ 当前使用 Text Fact Contract v2。`rebuild-text-index` 是生成当前文本事实的入口，会把游戏文本写成 SQLite 中的 v2 facts。迁移后的翻译、质量检查、手动补译、覆盖审计、反馈定位和写进游戏文件流程都读取 v2 facts，不再把旧文本范围、旧工作区或旧 runtime map 当成成功事实源。

用户可执行的重建入口是：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```

发行包中对应入口是：

```powershell
.\att-mz.exe rebuild-text-index --game <游戏标题>
```

## 事实字段

每条 v2 fact 至少区分以下语义：

| 字段 | 当前含义 | 主要用途 |
| --- | --- | --- |
| `raw_text` | 文件、JSON、JS 字符串或事件指令中的原始片段 | selector、stale 判断、写回定位 |
| `visible_text` | 解码后的玩家可见文本 | 候选判断、质量检查、报告展示 |
| `translatable_text` | 真正送模型翻译的正文 | prompt、译文保存、人工修复表 |
| `render_parts` | 写回时必须保留或替换的结构片段 | 写进游戏文件、术语写入、当前运行映射 |
| `raw_hash` | 基于原始片段的身份 | 原始片段 stale 判断 |
| `visible_hash` | 基于玩家可见文本的身份 | 可见文本覆盖和当前运行映射 |
| `translatable_hash` | 基于模型翻译正文的身份 | 去重翻译、译文匹配 |
| `scope_hash` | 绑定源快照、规则、文本规则和 schema version | 工作区、规则、索引和写回门槛 |

`raw_text` 不允许先 trim 再保存；`translatable_text` 不包含格式壳、speaker、selector、协议键、分隔空白或只服务写回的包装符。`render_parts` 是写回协议，不是提示词素材。

当前 v2 fact domains 包含：

- `standard_data`
- `mv_virtual_namebox`
- `plugin_config`
- `event_command`
- `note_tag`
- `nonstandard_data`
- `plugin_source`

## SQLite 边界

当前 schema 以 `text_facts_v2`、`text_fact_render_parts_v2`、`text_fact_domain_payloads_v2` 和 `text_fact_scope_v2` 为 v2 文本事实边界。业务代码只通过持久化会话与 typed adapter 读取这些事实，不在 Python 侧重新构建完整文本范围来替代 Rust 生成结果。

命令需要当前 v2 facts 时，以下状态都会显式失败：

- 旧数据库没有 v2 facts 或 v2 scope。
- v2 scope 的 `schema_version` 不是当前工具支持的版本。
- v2 facts 与当前 scope 不一致。
- 旧文本索引 metadata 仍是旧工作流范围标记。

恢复命令是：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
```

## 旧工作区失败

当前工作区 manifest 和候选文件必须携带 Text Fact Contract v2 范围信息。旧工作区缺少 `scope_key`、`scope_hash` 或 `text_fact_schema_version` 时，`validate-agent-workspace` 会失败，并提示重新准备工作区。

恢复命令是：

```powershell
uv run python main.py prepare-agent-workspace --game <游戏标题> --output-dir <工作区>
```

不要手动补 manifest 字段，也不要把旧候选文件复制到新工作区继续验收。

## 旧 Runtime Map 失败

当前运行文件审计、诊断和反馈定位依赖当前 runtime map。旧 runtime map 缺少 v2 hash、指向过期 selector，或不能和当前 v2 facts 对齐时，命令会把映射标为缺失或过期，不会继续用旧映射猜测文本来源。

恢复顺序是先重建文本索引，再按需要重建当前运行文件：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题>
uv run python main.py rebuild-active-runtime --game <游戏标题>
```

如果错误来自插件源码规则或待补译表过期，还需要重新导出对应文件后再导入。

## MV 虚拟名字框

MV 虚拟名字框使用同一 v2 fact 语义处理 speaker 和正文。例如源文本：

```text
\n<Dan:> Hello
```

当前事实中，`raw_text` 保留完整原始片段，`translatable_text` 只保留 `Hello`，speaker 与分隔空白由 render parts 保留。写进游戏文件时按 render parts 重建结构，因此弱规则只要能指出 speaker/body，就不需要把分隔空白塞进模型正文。

## 性能边界

`rebuild-text-index` 是当前全量重型入口。后续命令优先读取 warm SQLite v2 facts；质量报告、覆盖审计、工作区验收、反馈定位和写回计划不得为了补报告字段重新全量扫描游戏文本。需要解释重建索引耗时时，使用：

```powershell
uv run python main.py rebuild-text-index --game <游戏标题> --debug --debug-timings
```

普通 summary 只作为业务结果；阶段级耗时从 `summary.diagnostics` 或完整诊断 JSON 读取。

## 文档边界

- README 面向用户，只说明发生了什么、影响什么、下一步运行什么命令。
- CHANGELOG 记录破坏性变化、协议变化、验证命令和发行包信息。
- `docs/` 只保存人类阅读的设计说明、使用指南和排障说明，不承载 Agent 工作流。
- Agent 执行契约只放在 `skills/att-mz-protocol/`，并通过 `uv run python scripts/generate_skill_protocol.py --write` 生成到 `skills/att-mz/` 和 `skills/att-mz-release/`。
- 修改 Skill 协议后必须运行 `uv run python scripts/generate_skill_protocol.py --check`，确认生成物没有漂移。
