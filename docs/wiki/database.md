# 数据库 Wiki

本文档说明 A.T.T MZ 当前 SQLite 数据库结构。数据库只保存项目运行状态、统一规则模型、当前文本事实、已保存译文和诊断记录；游戏原始数据仍以 RPG Maker MV/MZ 自身的 `data/*.json`、`js/plugins.js`、`js/plugins/*.js`、`fonts/gamefont.css` 等文件为准。

## 存放方式

- 每个游戏使用一个独立 SQLite 文件：`data/db/<游戏标题>.db`。
- 数据库文件名来自游戏标题。标题不能包含 Windows 文件名非法字符。
- `metadata` 表固定保存一条 `metadata_key = current_game` 的绑定记录。
- 数据库由 CLI 自动创建和维护。翻译任务、外部 Agent 和临时脚本不得直接改数据库，业务数据进出必须走 CLI。
- 打开数据库时会校验 `schema_version`、项目声明的完整表集合、列定义、外键和唯一索引。结构不匹配会直接报错，提示删除对应游戏数据库后重新注册并重新导入规则和译名。

## 当前表总览

| 表名 | 职责 | 主要写入入口 |
|------|------|--------------|
| `schema_version` | 保存当前数据库 schema 版本 | `add-game` |
| `metadata` | 保存当前数据库绑定的游戏目录、真实内容目录、引擎类型和版本 | `add-game` |
| `language_settings` | 保存当前游戏的源语言和目标语言 | `add-game` |
| `source_snapshot_files` | 保存可信源快照 manifest 和文件哈希 | `add-game` |
| `rule_sets` | 保存每个规则 domain 的导入摘要、上下文 hash、规则 hash 和运行时版本 | `import-*rules` |
| `rules` | 保存所有用户或 Agent 导入规则的统一明细 | `import-*rules` |
| `rule_domain_states` | 保存空规则确认、未覆盖候选确认和其它 domain 状态 | `import-*rules --confirm-empty` 与规则导入 |
| `text_index_meta` | 保存当前翻译源文本范围索引的源快照指纹、规则指纹、条目数和创建时间 | `rebuild-text-index` |
| `text_index_items` | 保存当前翻译源文本范围索引项 | `rebuild-text-index` |
| `text_index_scope_summary` | 保存当前索引范围统计 | `rebuild-text-index` |
| `text_index_domain_summary` | 保存当前索引按 domain 聚合的统计 | `rebuild-text-index` |
| `text_index_rule_hit_summary` | 保存当前索引按规则命中聚合的统计 | `rebuild-text-index` |
| `text_index_invalidations` | 保存文本范围索引失效原因 | `rebuild-text-index`、索引检查流程 |
| `text_facts` | 保存当前文本事实主记录 | `rebuild-text-index` |
| `text_fact_render_parts` | 保存当前文本事实的写回结构片段 | `rebuild-text-index` |
| `text_fact_domain_payloads` | 保存当前文本事实的 domain 专用载荷 | `rebuild-text-index` |
| `text_fact_scope` | 保存当前文本事实范围 hash、源快照 hash 和规则 hash | `rebuild-text-index` |
| `translation_items` | 保存已经通过项目检查的正文译文记录 | `translate`、`import-manual-translations` |
| `translation_runs` | 保存正文翻译运行状态和统计快照 | `translate` |
| `llm_failures` | 保存正文翻译运行中的模型故障记录 | `translate` |
| `translation_quality_errors` | 保存模型返回后未通过项目检查的译文问题 | `translate`、`quality-report` 相关流程 |
| `terminology_field_terms` | 保存字段译名表 | `import-terminology` |
| `text_glossary_terms` | 保存正文翻译提示词使用的正文术语表 | `import-terminology` |
| `terminology_bundle_state` | 标记字段译名表和正文术语表已经作为同一批导入 | `import-terminology` |
| `plugin_source_runtime_write_map` | 保存插件源码写回后的可选诊断映射 | `write-back`、`rebuild-active-runtime`、`write-terminology` |
| `plugin_source_runtime_scan_cache` | 保存当前运行插件源码扫描缓存 | `rebuild-active-runtime`、当前运行审计 |
| `font_replacement_records` | 保存最近一次字体覆盖产生的可还原字体引用记录 | `write-back --confirm-font-overwrite`、`write-terminology --confirm-font-overwrite` |

## 统一规则模型

所有插件配置规则、事件指令规则、Note 标签规则、非标准 data 规则、插件源码规则、普通占位符规则、结构化占位符规则、MV 虚拟名字框规则和源文残留规则都写入统一规则模型。

### `rule_sets`

`rule_sets` 按 domain 保存一次导入的整体摘要。

| 字段 | 说明 |
|------|------|
| `domain` | 规则域，例如 `plugin_config`、`event_commands`、`note_tags`、`nonstandard_data`、`plugin_source`、`placeholders`、`structured_placeholders`、`mv_virtual_namebox`、`source_residual` |
| `source_kind` | 规则来源 |
| `rule_count` | 当前 domain 的规则数量 |
| `context_hash` | 导入时依赖的当前游戏上下文 hash |
| `rules_hash` | 当前规则集合 hash |
| `rule_runtime_contract_version` | 规则运行时契约版本 |
| `rule_store_schema_version` | 规则存储模型版本 |
| `imported_at` | 导入时间 |

### `rules`

`rules` 保存所有 domain 的规则明细。业务代码通过 domain adapter 把公开导入格式转换成当前模型。

| 字段 | 说明 |
|------|------|
| `rule_id` | 稳定规则 ID |
| `domain` | 规则域 |
| `rule_order` | 同 domain 内匹配顺序 |
| `matcher_kind` | matcher 类型，例如 `pcre2_pattern`、`json_path_template`、`literal`、`selector`、`fnmatch` |
| `matcher_value` | matcher 的主要匹配值 |
| `payload_json` | domain 专用 JSON 载荷 |
| `enabled` | 是否启用 |
| `source_kind` | 规则来源 |
| `rule_hash` | 单条规则 hash |

用户可写正则统一使用 PCRE2 当前契约。需要命名 capture 时使用 `(?<name>...)`。JSONPath、path template、selector、literal 和 fnmatch 仍按各自 domain 的公开导入格式处理，它们不是正则。

### `rule_domain_states`

`rule_domain_states` 保存 domain 状态，例如空规则确认、普通/结构化占位符候选已审查状态和对应完整候选范围 hash。

| 字段 | 说明 |
|------|------|
| `domain` | 规则域 |
| `state_json` | 当前状态 JSON |
| `scope_hash` | 该确认状态对应的完整候选范围 hash |
| `confirmed_at` | 确认时间 |
| `rule_runtime_contract_version` | 规则运行时契约版本 |
| `rule_store_schema_version` | 规则存储模型版本 |

确认状态只在当前候选范围一致时有效。游戏源文件、配置或规则变化后，相关命令会要求重新扫描、重新审查并按当前命令导入规则。

## 当前文本事实与译文

`rebuild-text-index` 会写入当前文本索引和当前文本事实。翻译、质量检查、手动补译、覆盖审计和写进游戏文件都以当前文本事实为成功事实源。

### `text_facts`

| 字段 | 说明 |
|------|------|
| `fact_id` | 当前文本事实 ID |
| `schema_version` | 当前文本事实 schema 版本 |
| `domain` | 文本来源 domain |
| `location_path` | 文本在游戏里的内部位置 |
| `source_file` | 来源文件 |
| `source_type` | 来源类型 |
| `item_type` | `long_text`、`array` 或 `short_text` |
| `role` | 对话角色或空字符串 |
| `selector` | domain 内 selector |
| `raw_text` | 原始文本 |
| `visible_text` | 玩家可见文本 |
| `translatable_text` | 模型应翻译文本 |
| `raw_hash`、`visible_hash`、`translatable_hash` | 三类文本 hash |
| `scope_key` | 当前文本事实范围 key |

### `translation_items`

`translation_items` 只保存已经通过项目检查的正文译文。写入时必须携带当前文本事实身份：`fact_id`、`source_fact_raw_hash` 和 `source_fact_translatable_hash`。当前事实不匹配的译文不会被当作成功译文继续使用。

| 字段 | 说明 |
|------|------|
| `fact_id` | 对应当前文本事实 ID |
| `location_path` | 文本在游戏里的内部位置 |
| `item_type` | 文本类型 |
| `role` | 对话角色 |
| `original_lines` | 原文行 JSON |
| `source_line_paths` | 原文行定位 JSON |
| `source_fact_raw_hash` | 保存时的原始文本 hash |
| `source_fact_translatable_hash` | 保存时的可翻译文本 hash |
| `translation_lines` | 中文译文行 JSON |

## CLI 与 Skill 对齐

- `add-game` 负责解析干净原始游戏目录，并把 `metadata` 的游戏目录、真实内容目录、引擎类型和版本写入数据库，同时把当前游戏源语言写入 `language_settings`。
- `add-game` 首次注册会创建可信源快照，并把快照路径、大小、哈希和更新时间写入 `source_snapshot_files`；翻译源读取只信这组快照。
- `prepare-agent-workspace` 会导出当前工作区文件。外部 Agent 应以 CLI 输出和工作区文件为准，不直接读取或修改数据库。
- `rebuild-text-index` 会写入当前索引和当前文本事实。大型游戏完成规则导入、源文件变化或规则变化后应先重建索引。
- 规则导入命令会先校验当前公开导入格式，再写入统一规则模型。导入时若清理不再属于当前规则范围的已保存译文，会先写入可恢复备份。
- Skill 只要求 Agent 读取 CLI 输出和工作区文件，不要求也不允许 Agent 直接读取或修改数据库表。
