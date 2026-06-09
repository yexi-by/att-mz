# 批次 03：Text Fact、索引与 scope

## 范围

- `app/text_facts.py`
- `app/text_fact_core.py`
- `app/text_fact_counts.py`
- `app/text_fact_identity.py`
- `app/text_fact_quality.py`
- `app/text_fact_readers.py`
- `app/text_scope/`
- `app/text_index.py`
- `rust/src/native_core/scope_index/`
- `tests/test_text_protocol.py`
- `tests/test_text_index.py`
- `tests/test_native_scope_index.py`

## 事实源

- 当前事实身份以 Text Fact Contract v2 的 `fact_id + raw_hash + translatable_hash` 为准，`app/text_fact_identity.py:16`、`app/text_fact_core.py:126` 到 `app/text_fact_core.py:131` 已按完整身份判断译文是否属于当前事实。
- 当前 Rust 重建路径会为索引 locator 写入 `source_line_paths`、`terminology_owner_terms`、`display_name` 等字段，见 `rust/src/native_core/scope_index/rebuild.rs:3313` 到 `rust/src/native_core/scope_index/rebuild.rs:3319`。
- 当前 scope 写入前会校验 warm rows 与 v2 facts 的身份一致，见 `rust/src/native_core/scope_index/storage.rs:641` 到 `rust/src/native_core/scope_index/storage.rs:671`。
- `stale_plugin_rules`、`stale_nonstandard_data_rules`、不匹配当前 fact 的译文，属于当前规则新鲜度或当前事实身份失配，不单独视作历史契约；本批只在其文案、命名或容错表达旧形态时记录发现。

## 只读命令

1. `rg -n 'v2|schema_version|legacy|fallback|old|stale|warm index|location_path|identity|scope|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' app/text_facts.py app/text_fact_core.py app/text_fact_counts.py app/text_fact_identity.py app/text_fact_quality.py app/text_fact_readers.py app/text_scope app/text_index.py rust/src/native_core/scope_index tests/test_text_protocol.py tests/test_text_index.py tests/test_native_scope_index.py`
2. `rg -n 'location_path.*identity|identity.*location_path|fact_id|raw_hash|translatable_hash|translated.*path|path.*translated' app rust/src/native_core/scope_index tests`
3. `$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-03-text-fact-index-scope.md' -Pattern $patterns`

第 1 条命令命中当前 `v2`、`scope`、`fact_id`、规则新鲜度，以及多处 `旧`、`legacy`、`兼容`、`迁移`、`回退` 表述；确认发现列在下方。第 2 条命令按要求扫描 `app` 与 `tests`，本批只审查范围文件内证据；范围外命中不在本报告下结论。第 3 条命令在报告写入后执行，自检结果为未命中。

## 结论

FAIL

## 发现

### P0：Text Fact 转换仍容忍旧索引定位缺失

- 证据：`app/text_fact_quality.py:152`
- 证据：`app/text_fact_quality.py:177`
- 证据：`app/text_fact_quality.py:182`
- 证据：`app/text_fact_core.py:185`
- 证据：`app/text_fact_core.py:188`
- 证据：`app/text_fact_core.py:201`
- 证据：`rust/src/native_core/scope_index/rebuild.rs:3313`
- 违反准则：运行时失忆化
- 影响范围：当前 v2 fact 转换为模型翻译输入时，`index_by_path.get()` 允许找不到索引定位记录；缺少 `display_name`、`terminology_owner_terms` 时又返回 `None` 或空列表。当前 Rust 重建已经写出这些 locator 字段，缺失应代表当前索引与事实不一致，而不是继续用路径或空术语生成翻译输入。
- 建议收束：把 `TextFactV2Record` 到 `TranslationItem` / `TranslationData` 的转换改成要求当前索引记录和当前 locator 字段存在；缺失时抛出当前契约错误。删除 `TextIndexItemRecord | None` 的旧形状容忍，或把无索引转换限制在明确的测试辅助函数中。
- 后续验证：补充“当前 fact 缺少对应 text_index_items 或 locator 必需字段时显式失败”的 Python 测试，并运行 `uv run basedpyright` 与相关 `pytest`。

### P0：Text Fact 契约错误文案展示“旧索引正文”

- 证据：`app/text_fact_core.py:224`
- 证据：`app/text_fact_core.py:228`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：所有通过 `text_fact_contract_error()` 抛出的当前契约错误都会把用户引向“旧索引正文”这个历史概念。当前运行时只需要表达“当前文本事实或当前索引不一致，需重新生成当前文本索引”。
- 建议收束：将错误文案改成当前契约描述，例如“当前文本事实与当前文本索引不一致，不能继续执行；请运行 rebuild-text-index 重新生成当前文本索引”，不再出现“旧索引正文”。
- 后续验证：补充或更新错误文案测试，断言用户可见错误不包含 `旧索引`、`legacy`、`old` 等历史词。

### P0：Rust scope storage 的 schema 错误提示引入迁移语义

- 证据：`rust/src/native_core/scope_index/storage.rs:278`
- 证据：`rust/src/native_core/scope_index/storage.rs:286`
- 违反准则：运行时失忆化 | schema 失忆化 | 文案失忆化
- 影响范围：`rebuild-text-index` 相关 native storage 在 schema_version 不可读或不匹配时，会提示“重新注册或迁移数据库”。当前契约应只说明数据库不符合当前要求，以及按当前版本重新注册、重建或修正；迁移属于历史说明，应放迁移指南或发布说明。
- 建议收束：删除运行时错误里的“迁移数据库”，改为当前修正动作；保留结构化错误码，但错误消息只表达当前要求。
- 后续验证：更新 `tests/test_native_scope_index.py:1007` 附近的错误渲染测试，断言 schema 错误中文摘要不包含迁移语义。

### P1：写回探针错误文案暴露临时回退扫描概念

- 证据：`app/text_scope/write_probe.py:78`
- 证据：`app/text_scope/write_probe.py:80`
- 违反准则：文案失忆化
- 影响范围：插件源码写入探针缺少当前扫描结果时，用户可见错误说明“不能临时回退扫描插件源码”。这把内部退路当成用户需要理解的当前概念；用户只需要知道当前命令缺少当前 text fact v2 生成的扫描结果，以及下一步重新生成索引或重新导入规则。
- 建议收束：改成当前状态描述，删除“回退扫描”字样。
- 后续验证：补充写回探针错误文案测试，断言不出现 `回退`、`fallback`。

### P2：运行时模块仍公开 legacy Python scope 辅助层

- 证据：`app/text_scope/__init__.py:3`
- 证据：`app/text_scope/__init__.py:29`
- 证据：`app/text_scope/builder.py:3`
- 证据：`app/text_scope/builder.py:53`
- 证据：`app/text_scope/builder.py:56`
- 违反准则：测试失忆化 | 文档分层
- 影响范围：`TextScopeService` 和 `build_translation_data_map` 仍作为 `app.text_scope` 公共导出存在，并在模块 docstring 中说明只服务 legacy 测试、未迁移工具。即使当前生产命令不应调用，这仍把历史模型留在运行时公共入口和内部注释里，容易让后续实现继续引用旧 scope。
- 建议收束：将仅供测试或未迁移诊断的构造器移出公共运行时入口，或改为当前命名与当前用途；若确需保留，放入测试辅助模块并删除运行时代码里的 legacy 叙述。
- 后续验证：用 `rg -n 'TextScopeService|build_translation_data_map' app tests` 确认生产调用点已经迁出或有明确当前用途，再运行相关测试。

### P2：`text_index_items_to_scope` 把历史 scope helper 固定在当前模块

- 证据：`app/text_index.py:763`
- 证据：`app/text_index.py:766`
- 证据：`app/text_index.py:768`
- 违反准则：测试失忆化 | 文档分层
- 影响范围：`text_index_items_to_scope()` 位于当前文本索引模块，却说明它为 legacy 测试和旧 workflow gate / 写回契约测试服务。该 adapter 层会让旧 scope 断言继续成为当前运行时事实源附近的概念。
- 建议收束：把该 helper 移到测试夹具或专用测试 adapter；当前 `app/text_index.py` 只保留当前 text fact v2 / native scope index 的契约函数。
- 后续验证：迁移后运行 `rg -n 'legacy|旧 workflow gate|text_index_items_to_scope' app/text_index.py tests/test_text_index.py`，确保运行时模块不再承载历史 scope 叙述。

### P2：测试命名和 fixture 值继续表达 legacy/old 模型

- 证据：`tests/test_text_index.py:170`
- 证据：`tests/test_text_index.py:180`
- 证据：`tests/test_text_index.py:938`
- 证据：`tests/test_text_index.py:955`
- 证据：`tests/test_native_scope_index.py:579`
- 证据：`tests/test_native_scope_index.py:1009`
- 证据：`rust/src/native_core/scope_index/storage.rs:1528`
- 违反准则：测试失忆化
- 影响范围：测试仍使用 `legacy-prompt-context-test`、`old_confirmation`、`legacy-confirmed-scope`、`old.db`、“旧范围服务”、“replaces_old_text_fact_v2_scope”等历史命名。测试语义多半是在验证“当前 scope hash / schema / fact 身份不匹配时拒绝复用”，但命名把历史模型固化成测试事实。
- 建议收束：将测试名、fixture 值和注释改为当前契约语言，例如 `previous_prompt_context_test`、`non_current_scope_hash`、`mismatched_schema.db`、`replaces_previous_text_fact_v2_scope`。
- 后续验证：运行 `rg -n 'legacy|old|旧|历史|兼容|迁移|回退' tests/test_text_index.py tests/test_native_scope_index.py rust/src/native_core/scope_index/storage.rs`，确认剩余命中只属于当前规则新鲜度或必要 schema 字段。

## 交叉引用

- 第 2 条强制命令在范围外 `app/agent_toolkit/`、`app/persistence/`、`tests/test_agent_toolkit_*` 等文件也命中 `fact_id`、`raw_hash`、`legacy`、`old` 相关内容；这些不属于批次 03 的确认范围，应由对应批次继续审查。
- `stale_plugin_rules` 与 `stale_nonstandard_data_rules` 在本批 Rust/Python scope index 中作为当前规则新鲜度错误使用，本报告未将其本身判为历史契约。

## 已查无发现范围

- `tests/test_text_protocol.py`：文本协议外壳测试只描述当前 JSON 外壳、控制符和容器编码规则，未发现历史契约污染。
- `app/text_fact_identity.py`：身份辅助函数按当前 `fact_id + raw_hash + translatable_hash` 显式失败，未发现历史形态容错。
- `app/text_fact_counts.py`：计数查询按当前 scope 与当前事实身份匹配统计；`stale_translation_count` 表达当前不匹配译文数量，未发现历史 schema 兼容分支。
- `app/text_facts.py`：仅聚合当前 Text Fact Contract v2 入口，除被引用函数自身问题外未发现额外历史契约。
- `rust/src/native_core/scope_index/plugin_source.rs`、`rust/src/native_core/scope_index/nonstandard_data.rs` 的过期规则错误用于当前源文件或规则新鲜度校验，未发现自动迁就旧规则。
