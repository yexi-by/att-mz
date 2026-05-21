# 术语工程流程

术语工程负责字段译名表和正文术语表。字段译名表服务游戏字段写回；正文术语表服务正文翻译提示词命中。两者不能互相替代。

## 输入

- `terminology/field-terms.json`
- `terminology/glossary.json`
- `terminology/contexts/speakers/*.json`
- `terminology/contexts/database_terms.json`
- `terminology/subtasks/sources/*.json`

## 第一轮子代理

第一轮只处理术语候选。子代理只能读取自己的源文件和上下文，只写对应候选文件：

| 源文件 | 唯一可写文件 |
| --- | --- |
| `terminology/subtasks/sources/speaker_and_actor_terms.json` | `terminology/subtasks/candidates/speaker_and_actor_terms.json` |
| `terminology/subtasks/sources/map_and_system_terms.json` | `terminology/subtasks/candidates/map_and_system_terms.json` |
| `terminology/subtasks/sources/skill_and_state_terms.json` | `terminology/subtasks/candidates/skill_and_state_terms.json` |
| `terminology/subtasks/sources/item_terms.json` | `terminology/subtasks/candidates/item_terms.json` |
| `terminology/subtasks/sources/equipment_terms.json` | `terminology/subtasks/candidates/equipment_terms.json` |

术语候选子代理任务必须包含：

```text
输入：读取 <工作区>/terminology/subtasks/sources/<术语分组>.json、<工作区>/terminology/contexts/speakers/*.json 和 <工作区>/terminology/contexts/database_terms.json。
逻辑：按源文含义翻译当前分组的全部术语；专名统一，称号、技能、物品、线索句和系统词要译成自然简体中文；禁止机械转写。
输出：只写 <工作区>/terminology/subtasks/candidates/<术语分组>.json，保持类别和 key 不变，只填写 value。
质量要求：不留空值，不残留平假名/片假名，不出现机械音译残渣；不确定项也必须给出当前最合理译名，并在报告说明风险。
完成报告：说明总条数、空值数、读取的上下文、关键统一译名、疑难项和自检结果。
```

## 主代理合并职责

- 等待全部术语候选子代理完成。
- 逐个读取候选文件，不只看完成报告。
- 审查信达雅、源文语义、中文自然度、专名统一、跨类别一致性和游戏 UI 语感。
- 亲自修改候选译名并合并到 `terminology/field-terms.json`。
- 同步维护 `terminology/glossary.json`，正文术语表只保留 `terms` 顶层对象。
- 全量检查空译名、源文残留、机械音译残渣、同一原文跨类别冲突和关键术语口径。

字段译名表的 value 是最终写进游戏字段的完整文本。如果原字段里的 `/c`、引号、`◆...ｔ` 等符号需要在游戏字段中保留，必须在字段译名表 value 中保留或按目标译名重组，不能指望正文术语表补回来。

`/c<角色名>`、`"<角色名>"`、`◆<角色名>ｔ` 等字段包装形式需要主代理人工判断后规范化：真正原文术语写进正文术语表 `terms`，字段包装形式不得写入正文术语表。

## 导入

主代理审查通过后运行：

```powershell
.\att-mz.exe --agent-mode import-terminology --game <游戏标题> --input <工作区>/terminology/field-terms.json --glossary-input <工作区>/terminology/glossary.json --json
```

字段译名表 key 不能改，正文术语表只能包含 `terms`。任一术语候选质量明显不合格时，退回对应候选子代理重做或主代理亲自重译对应字段，不能把坏候选保存为当前游戏术语表。


