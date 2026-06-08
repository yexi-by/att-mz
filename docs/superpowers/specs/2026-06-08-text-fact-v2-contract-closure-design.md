# Text Fact v2 Contract Closure Design

## 目标

本设计用于关闭 Text Fact Contract v2 review 中发现的阻断问题，并在同一次实现中完成必要的边界内拆分。成功状态是：当前文本事实、已保存译文、质量错误、规则导入、规则校验、工作区验收和写回计划都以 `fact_id + source_fact_raw_hash + source_fact_translatable_hash` 作为唯一成功事实身份；`location_path` 只用于用户路径输入、报告显示、排序和采样。

实现后不得保留旧代码、旧测试或默认回退路径。旧库、旧工作区、旧质量错误形状和旧路径身份模型必须显式失败，提示用户重新生成当前 v2 索引或修正输入。

## 背景

上一轮并发 review 对当前 HEAD 相对 `6efa43e5c578a4e4572ffbfd792caa266273a6e8` 的 Text Fact v2 改动给出 FAIL 结论，核心问题集中在：

- Rust `rebuild-text-index` 在生成 v2 facts 前按 `location_path` 去重，可能让同一路径不同事实无法入库。
- 规则导入仍按路径删除已保存译文，可能误删同路径下仍有效的当前 fact 译文。
- 工作区验收和规则校验仍通过 `translated_paths: set[str]` 计算已翻译数量。
- 质量错误允许缺失 `fact_id`，并存在按路径读取折叠同路径多 fact 的风险。
- 手动补译 fact_id 读取 helper 缺少分块查询护栏。
- Python 写回测试 helper 仍按 `location_path` 合成 v2 fact 身份，形成第二测试模型。
- `app/text_facts.py` 和部分 Agent 服务文件已经承担过多职责，需要在本次触碰范围内拆出清晰边界。

## 非目标

本次不做全仓库风格重排，不重写 CLI，不迁就旧数据库或旧工作区，不建立新的万能身份服务，不把真实游戏性能优化结论写成已通过。本次也不把所有大型文件一次性拆完，只拆与 v2 身份闭环和本次缺陷直接相关的代码。

## 设计原则

1. 单向数据流：Rust 重建当前 facts，SQLite 持久化当前 facts，Python 只按当前 facts 编排报告和用户操作，写回只读取当前 facts 与匹配的 saved translations。
2. 单一事实身份：任何成功、已翻译、质量错误、待清理、可写回判断都不能退回 `location_path`。
3. 显式失败：缺少 `fact_id`、hash、当前 scope、当前 v2 schema 或当前工作区 metadata 时直接失败。
4. 边界内拆分：只拆本次要理解和修改的边界，让后续维护者能按模块名找到 SQL、读取、质量错误、规则身份和测试夹具。
5. 无隐藏时序：不引入缓存同步、后台修正、双写迁移或先 path 后 fact 的补救流程。

## 架构

整体架构保持“Rust 生成事实，Python 编排流程”的方向。Rust 的重建流程必须允许同一 `location_path` 产生多个 v2 fact；若旧 warm index 仍需要路径唯一，它只能作为派生的展示或兼容索引，不能反向决定 v2 fact 数量。

Python 侧将 `app/text_facts.py` 从单个生产汇聚文件拆成小模块：

- `app/text_facts.py`：保留公共 façade、向后兼容的 import 出口和少量类型转换导出。
- `app/text_fact_counts.py`：负责 count/report SQL，包括 pending、translated、stale、quality error 统计。
- `app/text_fact_readers.py`：负责按 fact_id、path、scope 读取当前 facts，并统一分块 `IN` 查询。
- `app/text_fact_quality.py`：负责质量错误 fact 读取、质量检查源文重建和质量报告样本字段。

Agent 服务增加一个窄边界模块：

- `app/agent_toolkit/services/rule_identity.py`：把规则命中、当前 fact、已保存译文转换为 fact identity 集合，并提供 translated_count 和 stale fact 计算。调用方只消费 fact_id 集合或 fact identity 结果，不再传递 `translated_paths: set[str]` 作为成功事实。

测试侧删除第二身份模型：

- `tests/_native_write_plan_helper.py` 不再维护 `fact_identity_by_location`，所有测试译文都从当前 `text_facts_v2.fact_id` 和对应 hash 取得身份。

## 组件设计

### Rust 索引重建

`rust/src/native_core/scope_index/rebuild.rs` 中的行去重必须拆成两个概念：

- fact 输入行：允许同一 `location_path` 出现多次，只要 fact 身份不同。
- warm index 行：如仍需要路径唯一，单独从 fact 输入行派生，并明确只服务旧索引摘要或显示兼容。

v2 fact payload 必须从未按路径去重的 fact 输入行构建。测试需要覆盖同一 Note 字段中两个相同 tag 命中，最终 `text_facts_v2` 有两个不同 `fact_id`。

### 规则导入与规则校验

NoteTag 和 plugin-source 规则导入不得再用 `old_paths - new_paths` 删除译文。导入流程应读取旧规则影响到的已保存译文 fact identity，再读取新规则当前命中的 fact identity，最后按 stale fact_id 删除。

规则校验、工作区验收和 Agent 报告不得再接收 `translated_paths: set[str]`。它们应接收当前命中 fact_id 集合与已保存当前译文 fact_id 集合，并用集合交集计算 translated_count。`location_path` 仍可出现在报告 detail 中，但不得决定 translated_count。

### 质量错误

`TranslationErrorItem.fact_id` 改为必填字段。写入质量错误时必须同时持有 `location_path`、`fact_id` 和当前文本 hash 语义所需的上下文；缺失 fact_id 是非法状态。

读取质量错误时，按 fact_id 的 API 是主路径。按 path 的 API 只允许服务用户指定路径过滤，并且返回 list，不得折叠成 `dict[location_path]`。报告层如需要映射，必须以 fact_id 为 key。

用户可见文案中避免把 `location_path` 当字段名暴露。需要展示定位时使用“文本位置”或“内部位置”，并把具体定位作为值展示，不把内部字段名写进操作建议。

### 手动补译

带 `fact_id` 的手动补译导入只接受当前可写 fact。`read_writable_text_fact_translation_items_by_fact_ids` 必须使用统一分块查询，和其他 fact_id helper 一起被 scan budget 覆盖。

旧工作区缺 fact_id 时继续显式失败，提示重新导出当前工作区或当前待翻译文件；不得自动按 path 匹配。

### Rust 写回前置校验

写回 repository 仍以 `fact_id + raw_hash + translatable_hash` join 当前 facts 和 saved translations。前置校验不得无条件全表扫描所有 `translation_items`。当用户提供 allowed paths 时，校验范围应先落到当前 allowed facts，再检查相关 saved translations；全量写回时才允许全库级校验。

如果存在无法解析到当前 v2 fact 的 saved translation，错误必须说明“已保存译文对应的当前文本事实不存在或已过期”，并给出重新生成索引或重新导入译文的行动建议。

### 文档与契约

README、CHANGELOG 和 Skill 协议只在必要时更新，描述当前实现而不是历史对比。CHANGELOG 需要明确真实游戏性能尚未由自动测试证明，给出维护者 benchmark 命令。涉及 Skill 协议时必须修改 canonical 源并运行生成物检查。

## 数据流

1. `rebuild-text-index` 扫描游戏文本和规则命中，生成未按路径去重的 fact 输入行。
2. Rust 为每条 fact 输入行生成 stable fact_id、raw hash、visible hash、translatable hash、render parts 和 domain payload。
3. SQLite 在一个事务中保存 `text_facts_v2`、render parts、domain payload、scope 和必要的 warm index 派生数据。
4. Python 读取当前 scope 下的 facts，构建待翻译、已翻译、质量错误、规则命中和写回候选。
5. 保存译文和质量错误时必须携带 fact_id 与 source hashes。
6. 规则导入、工作区验收、质量报告和写回只按当前 fact identity 判断成功或过期。

## 错误处理

以下状态必须显式失败：

- 当前数据库 schema version 或 text fact schema version 不匹配。
- 当前 scope 缺失或 scope 中存在不匹配 schema。
- saved translation 缺少 fact_id、raw hash 或 translatable hash。
- quality error 缺少 fact_id。
- 旧工作区或手动补译文件缺少 fact_id。
- 规则导入需要删除译文但无法把候选解析到当前 fact identity。
- 写回发现 saved translation 无法解析到当前 v2 fact。

错误文案先说发生了什么、影响什么、下一步做什么。内部字段只在 JSON schema 或排障定位中出现。

## 测试策略

先写失败测试，再改实现。测试必须固定业务行为，不固定自然语言段落。

必须覆盖：

- 同一路径两个 NoteTag 命中，重建后生成两个 v2 facts。
- 同一路径两个 fact 中，只保存一个当前 fact 译文时，pending/translated/stale 统计正确。
- 规则导入只按 stale fact_id 删除，不误删同路径当前 fact。
- 工作区验收和规则校验的 translated_count 不被同路径 stale 译文污染。
- 缺 fact_id 的质量错误写入失败。
- 同路径多 fact 的质量错误读取不折叠。
- 手动补译 fact_id helper 使用分块查询。
- `tests/_native_write_plan_helper.py` 不再按 location_path 合成 fact identity。
- scan budget 禁止 migrated flows 使用 `translated_paths: set[str]`、`translations.location_path = facts.location_path`、旧 extractor 和未分块 fact_id helper。

## 验证

实现交付前必须执行：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

涉及 Skill 协议、README 或 CHANGELOG 时，还必须执行：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

若真实游戏性能不在本次会话可验证范围内，交付说明必须明确剩余风险，并给出维护者可运行的 benchmark 命令。

## 验收标准

- `location_path` 不再作为 saved translation、quality error、规则 translated_count 或 write-back correctness 的身份。
- 同一路径不同 fact 能同时进入 `text_facts_v2`，并能分别 pending、翻译、报错和写回。
- 旧 path-based 删除、统计、质量错误映射和测试身份模型被删除。
- 所有 fact_id 查询有分块边界和 scan budget 护栏。
- 大文件拆分后，新增模块职责单一，调用关系线性，不引入缓存同步或双事实来源。
- 全量 Python 和 Rust 验证通过，或交付说明清楚列出无法执行的命令、原因和风险。
