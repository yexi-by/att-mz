# 轨道 06：迁移与删减

## 范围

本轨道只读审查迁移与删减边界，覆盖 `app/`、`rust/src/`、`tests/`、`docs/records/rust-scope-index/`、`docs/records/reviews/rust-migration/`、`docs/superpowers/plans/`、`docs/superpowers/specs/` 中与 Rust 主路径、Python 旧逻辑、删除条件、瘦身条件和双轨保留风险相关的内容。

未读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。未执行导入、翻译、写回、重建运行文件、重置或 run-all 等会改变状态的命令。

## 只读命令

- `Get-Content -LiteralPath docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md -Raw`
- `Get-Content -LiteralPath docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md -Raw`
- `Get-Content -LiteralPath tests\scan_budget_contract.py -Raw`
- `git status --short`
- `Test-Path -LiteralPath docs\records\reviews\rust-primary-refactor\batches`
- `Test-Path -LiteralPath docs\records\reviews\rust-primary-refactor\batches\track-06-migration-deletion.md`
- `rg -n 'legacy|fallback|deprecated|old|delete|remove|delet|slim|thin|adapter|migration|migrate|Python|Rust|native|旧|历史|兼容|迁移|废弃|回退|删除|瘦身' app rust/src tests docs/records/rust-scope-index docs/records/reviews/rust-migration docs/superpowers/plans docs/superpowers/specs`
- `rg -n 'TextScopeService\.build|PluginSourceTextExtraction|NoteTagTextExtraction|collect_.*candidates|scan_.*candidates|extract_all_text|old|legacy|fallback' app tests`
- `rg -n '下一批|剩余风险|删除|瘦身|旧路径|native|Rust|Python|主路径|事实来源' docs/records/rust-scope-index docs/records/reviews/rust-migration docs/superpowers/plans docs/superpowers/specs`
- 补充窄范围 `rg -n -C`：插件源码、Note 标签、非标准 data、事件指令、MV 虚拟名字框、占位符、scan budget、P1-B 收束记录、旧提取器与候选 helper。

## 结论

FAIL

## 关键发现

### P1：插件源码规则已宣称 Rust 主路径，但 Python 仍承担 selector 校验、stale 判断和覆盖门禁

- 证据：`tests/scan_budget_contract.py:426`、`tests/scan_budget_contract.py:432`、`app/plugin_source_text/importer.py:33`、`app/plugin_source_text/importer.py:46`、`app/plugin_source_text/importer.py:66`、`app/plugin_source_text/importer.py:120`、`app/plugin_source_text/importer.py:137`、`app/plugin_source_text/rules.py:34`、`app/plugin_source_text/rules.py:76`、`app/plugin_source_text/rules.py:91`、`app/application/flow_gate.py:569`、`app/application/flow_gate.py:594`、`app/agent_toolkit/services/rule_validation.py:845`、`app/agent_toolkit/services/rule_validation.py:928`、`app/agent_toolkit/services/rule_validation.py:934`、`app/agent_toolkit/services/workspace.py:674`
- 业务事实：插件源码候选、selector、excluded selector、stale 规则、review coverage 和 workflow gate。
- 违反原则：迁移删减、Rust 主路径、单一事实来源。
- 影响：预算表把 `validate-plugin-source-rules` 和 `import-plugin-source-rules` 的事实来源固定为 `Rust scan_rule_candidates(plugin_source)`，但生产路径仍由 Python 根据 Rust 返回的候选集合再次判断 selector 是否存在、是否 stale、候选是否审查完成。后续如果 Rust 扩展 candidate 分类或区分“AST 中存在但被候选口径过滤”，Python 的 `未命中当前 AST 地图` 判断仍会把不同失效原因折叠成旧语义。
- Python/Rust 职责判断：Rust 应产出 selector 命中、排除命中、未审查候选、stale 原因和可恢复错误码；Python 只解析外部 JSON、调用 native、渲染报告和执行数据库事务。
- 建议 Rust 接管点：扩展 `scan_rule_candidates(plugin_source)` 或新增同一系列的规则校验输出，让 Rust 返回每条规则的 `matched_selectors`、`missing_selectors`、`filtered_selectors`、`unreviewed_candidates`、`stale_reason_code` 和可用户行动的摘要。
- 应删除或瘦身的 Python 逻辑：删除或降级 `build_plugin_source_rule_records_from_import` 中的 selector membership 校验；删除或瘦身 `filter_fresh_plugin_source_text_rules`、`collect_plugin_source_review_coverage`；将 `_plugin_source_rule_hits_from_scan` 保留为短期 adapter 时必须有删除条件。
- 禁止采用的错误修复方向：禁止继续在 Python 里补 selector fallback、字符串特判、二次 stale 判断或只改报告文案。
- 后续验证：新增 Rust 单测覆盖 selector 存在、候选过滤、排除 selector、文件停用、语法错误和高风险未审查；新增 Python 流程测试证明 validate/import/workflow/workspace 只消费 native 规则摘要，不调用上述 Python 判断 helper。

### P1：非标准 data 文本范围仍通过 Python 提取器展开规则命中，迁移完成状态缺少删除条件

- 证据：`tests/scan_budget_contract.py:312`、`tests/scan_budget_contract.py:318`、`tests/test_scan_budget.py:215`、`tests/test_scan_budget.py:237`、`app/text_scope/rule_hits.py:7`、`app/text_scope/rule_hits.py:175`、`app/text_scope/rule_hits.py:183`、`app/nonstandard_data/extraction.py:33`、`app/nonstandard_data/extraction.py:49`、`app/nonstandard_data/extraction.py:71`、`app/nonstandard_data/extraction.py:88`、`app/nonstandard_data/extraction.py:157`、`app/nonstandard_data/extraction.py:278`、`app/nonstandard_data/__init__.py:33`
- 业务事实：非标准 data 候选、path template、字符串叶子、当前文本范围 rule hit。
- 违反原则：迁移删减、Rust 主路径。
- 影响：候选扫描已经以 `Rust scan_rule_candidates(nonstandard_data)` 为权威来源，但文本范围的规则命中展开仍由 `NonstandardDataTextExtraction` 在 Python 里按 path template 遍历叶子并决定命中文本。测试还明确允许 `NonstandardDataTextExtraction` 继续作为包根导出，说明当前“收束”没有绑定删除对象。
- Python/Rust 职责判断：Rust 应负责 path template 展开、字符串叶子匹配和命中项输出；Python 只应把 native hit 转成报告、文本 fact 或数据库事务输入。
- 建议 Rust 接管点：让 `scan_rule_candidates(nonstandard_data)` 在带规则输入时返回 rule hit details、matched leaf paths、translation prefixes 和 stale reason code，供 text scope / rebuild / validate / import 共同消费。
- 应删除或瘦身的 Python 逻辑：删除或瘦身 `NonstandardDataTextExtraction.collect_rule_hits`、`NonstandardDataTextExtraction.extract_all_text` 中的 path template 展开；将 `app/text_scope/rule_hits.py::collect_nonstandard_data_rule_hits` 改成 native hit adapter；从包根移除 `NonstandardDataTextExtraction` 作为当前公共能力的表达。
- 禁止采用的错误修复方向：禁止把 Rust leaves 当底层数据源、再长期用 Python 展开 path template；禁止用 scan budget 的“候选已迁移”替代规则命中迁移。
- 后续验证：新增 Rust 单测覆盖非标准 data path template 命中、重复叶子、缺失路径、skipped 规则；新增 Python contract 测试证明 text scope rule hit 不实例化 `NonstandardDataTextExtraction`。

### P2：旧 Python 提取器和 helper 仍作为包根公共 API 暴露，后续重构容易把旧路径当当前事实源复用

- 证据：`app/plugin_source_text/__init__.py:4`、`app/plugin_source_text/__init__.py:50`、`app/plugin_source_text/__init__.py:61`、`app/plugin_source_text/__init__.py:62`、`app/plugin_source_text/extraction.py:14`、`app/plugin_source_text/extraction.py:30`、`app/note_tag_text/__init__.py:18`、`app/note_tag_text/__init__.py:19`、`app/note_tag_text/exporter.py:67`、`app/agent_toolkit/placeholder_scan.py:20`、`app/agent_toolkit/services/common.py:22`、`app/agent_toolkit/services/common.py:3265`
- 业务事实：插件源码提取、Note 标签候选、普通占位符候选、公共服务导出面。
- 违反原则：迁移删减。
- 影响：即使部分运行路径已有防回退测试，旧提取器、旧候选扫描器和旧规则构造器仍在包根或公共服务模块暴露。后续小步重构时，开发者可以从当前公共 API 直接导入这些旧对象，形成“Rust 已有主路径，但 Python 旧入口仍可作为当前事实源”的长期双轨。
- Python/Rust 职责判断：Python 可保留外部 JSON 解析、typed adapter 和报告组装；旧扫描、候选、提取、coverage helper 不应继续作为公共入口表达当前能力。
- 建议 Rust 接管点：不需要新增独立 Rust 入口；先把已有 native scan 的 adapter 输出补齐到能替代旧 helper，再收窄 Python 包导出。
- 应删除或瘦身的 Python 逻辑：从 `app/plugin_source_text/__init__.py` 移除 `PluginSourceTextExtraction`、`collect_plugin_source_review_coverage`、`filter_fresh_plugin_source_text_rules` 的公共导出；从 `app/note_tag_text/__init__.py` 移除旧 `NoteTagTextExtraction` 和 `build_note_tag_rule_records_from_import` 的公共导出；从 `app/agent_toolkit/services/common.py` 移除旧 `scan_placeholder_candidates` 导入和 `__all__` 暴露。
- 禁止采用的错误修复方向：禁止只在测试里 monkeypatch 禁止旧路径，而让生产包继续公开同名事实入口。
- 后续验证：新增静态测试禁止这些旧对象出现在包根 `__all__` 和服务公共导出；需要保留的内部 adapter 改为模块内私有名或移入明确的迁移隔离模块。

### P2：测试仍把 Python 旧实现当 native 对照 oracle，缺少“对照测试退场”条件

- 证据：`tests/test_agent_toolkit_manual_import.py:494`、`tests/test_agent_toolkit_manual_import.py:503`、`tests/test_agent_toolkit_rule_import.py:3552`、`tests/test_agent_toolkit_rule_import.py:3560`、`tests/test_agent_toolkit_rule_import.py:3595`、`tests/test_agent_toolkit_rule_import.py:3596`、`tests/test_agent_toolkit_rule_import.py:3598`、`tests/test_agent_toolkit_coverage.py:401`、`tests/test_agent_toolkit_coverage.py:406`、`tests/test_agent_toolkit_manual_import.py:230`、`tests/test_agent_toolkit_manual_import.py:325`
- 业务事实：Note 标签候选、普通占位符候选、native/Python parity、旧路径防回退。
- 违反原则：迁移删减、测试验收。
- 影响：测试已经能证明部分命令不调用旧 Python scanner，但仍保留“native 输出等于 Python collect_note_tag_candidates”的对照测试，以及大量通过 monkeypatch 证明旧路径没被调用的用例。防回退测试有价值，但如果没有退场条件，会让旧 Python 实现为了测试 oracle 长期存在，削弱删除动力。
- Python/Rust 职责判断：Rust 单测应固定候选和覆盖细节；Python 流程测试只固定 CLI/报告/数据库可观察契约，不应长期依赖 Python 旧实现作为真值。
- 建议 Rust 接管点：把 Note 标签、占位符候选的细粒度匹配样例迁到 Rust 单测或 native contract 测试；Python 只断言调用 native adapter 和报告字段。
- 应删除或瘦身的 Python 逻辑：删除 parity 依赖的 Python 旧候选函数后，同步删除或改写 `native == python` 对照测试；保留少量静态防回退测试，但将其目标改为“旧对象已不存在或不导出”。
- 禁止采用的错误修复方向：禁止为了保留测试 oracle 而保留旧 scanner；禁止新增更多 Python parity 测试覆盖 Rust 内部规则。
- 后续验证：迁移后运行 Rust 候选单测、Python 命令流程测试和 scan budget 静态边界测试，确认没有以旧 Python helper 作为 expected value。

## 双事实来源清单

- 插件源码 selector / stale / review coverage：Rust 产出候选扫描结果，Python `build_plugin_source_rule_records_from_import`、`filter_fresh_plugin_source_text_rules`、`collect_plugin_source_review_coverage` 继续解释 selector membership 和未审查候选。
- 非标准 data 规则命中：Rust 产出候选和 leaves，Python `NonstandardDataTextExtraction` 继续展开 path template 并构造文本范围命中。
- Note 标签候选测试 oracle：Rust native 候选与 Python `collect_note_tag_candidates` 并存，测试仍比较两者相等。
- 普通占位符旧 scanner：运行路径已有 native scan，但旧 `app.agent_toolkit.placeholder_scan.scan_placeholder_candidates` 仍被公共服务模块导入和导出。

## Rust 主路径缺口

- 插件源码缺少 native 规则校验摘要，无法完全替代 Python selector 校验、excluded selector 处理、review coverage 和 stale reason。
- 非标准 data 缺少 native rule hit details / translation prefixes / stale reason，导致文本范围和规则命中还要回到 Python 展开 path template。
- Note 标签与占位符候选的 Rust contract 需要承接旧 Python oracle 覆盖的边界样例，才具备删除旧 scanner 的测试支撑。

## Python 删除候选

删除清单：

- `app/plugin_source_text/extraction.py::PluginSourceTextExtraction`
- `app/plugin_source_text/rules.py::filter_fresh_plugin_source_text_rules`
- `app/plugin_source_text/rules.py::collect_plugin_source_review_coverage`
- `app/note_tag_text/exporter.py::collect_note_tag_candidates`
- `app/note_tag_text/importer.py::build_note_tag_rule_records_from_import`
- `app/agent_toolkit/placeholder_scan.py::scan_placeholder_candidates`

瘦身清单：

- `app/plugin_source_text/importer.py::build_plugin_source_rule_records_from_import`：保留外部 JSON 到 typed record 的薄转换，删除 selector membership / stale 判断。
- `app/nonstandard_data/extraction.py::NonstandardDataTextExtraction`：迁移为 native hit adapter 或删除；短期只允许消费 Rust rule hit details。
- `app/text_scope/rule_hits.py::collect_nonstandard_data_rule_hits`：改为消费 Rust nonstandard hit details。
- `app/agent_toolkit/services/common.py` 和 `app/agent_toolkit/services/rule_validation.py` 中插件源码、Note、占位符相关导入：删除旧 scanner/extractor 公共导入，保留 native adapter 和报告组装。

迁移阶段建议：

1. 插件源码规则摘要阶段：先扩展 Rust plugin_source rule validation 输出，Python validate/import/workflow/workspace 改为同一 native context。
2. 插件源码删除阶段：删除 Python selector/stale/coverage helper，移除包根导出，并以静态测试防止恢复。
3. 非标准 data rule hit 阶段：让 Rust 输出规则命中和 translation prefixes，替换 text scope Python 提取器。
4. 旧 oracle 退场阶段：把 Note/placeholder parity 样例转成 Rust/native contract 测试，删除 Python 旧 scanner。
5. 公共 API 收口阶段：所有包根只导出当前 adapter、record model 和报告转换，不再导出旧 extractor/scanner。

每阶段完成条件：

- 生产入口不再调用对应 Python 旧 helper。
- 包根和服务公共导出不再暴露旧 helper。
- Rust 或 native contract 测试覆盖原 Python helper 负责的边界样例。
- Python 流程测试只验证 CLI、报告、数据库事务和错误码，不以旧实现作为 expected value。
- scan budget 静态测试从“旧路径未调用”升级为“旧路径不存在或不可从公共入口导入”。

不能作为完成状态保留的双轨路径：

- Rust 返回候选，Python 继续判断 selector/stale/coverage。
- Rust 返回 leaves，Python 长期展开 path template。
- native 与 Python scanner 长期做 parity，对照通过即视为完成。
- 旧提取器留在包根 `__all__`，只依赖调用方自觉不用。
- 报告字段改成 Rust 名称，但事实仍由 Python helper 计算。

## 测试缺口

- 缺少插件源码 selector 过滤原因的 Rust 单测和 Python contract 测试，无法删除 Python `未命中当前 AST 地图` 判断。
- 缺少非标准 data native rule hit details 的 Rust 单测，导致 `NonstandardDataTextExtraction` 仍承担规则命中展开。
- 缺少旧公共 API 删除测试：当前测试更多证明旧路径未被调用，而不是证明旧路径已不可作为公共事实源。
- 缺少 Python 测试改写计划：Note 标签和占位符候选仍有旧 Python oracle 依赖，需要迁到 Rust/native contract 层。

## 交叉引用

- 轨道 01 应复核插件源码 selector、非标准 data path template、Note/placeholder 候选的唯一事实源。
- 轨道 02 应复核插件源码规则摘要和非标准 data rule hit 是否属于 Rust 主路径前置缺口。
- 轨道 03 应复核插件源码从 export/validate/import/rebuild/translate/write-back 是否消费同一 native candidate fact。
- 轨道 05 应复核 parity 测试退场和旧公共 API 删除测试。
- 轨道 07 应复核非标准 data Python path template 展开和插件源码 Python coverage 计算的性能影响。

## 已查无发现范围

- 未发现 `legacy`、`fallback`、`deprecated` 这些英文标记直接保留在当前生产路径中作为显式兼容开关。
- 未发现 `docs/records/rust-scope-index` 历史记录本身要求继续保留旧 Python 生产路径；历史记录主要用于确认哪些路径已被声明收束。
- 事件指令规则校验当前已有 `app/event_command_text/native_validation.py` 的 native context，虽然仍有旧 `EventCommandTextExtraction` 测试覆盖，但本轨道未确认它在当前 `app/` 生产入口中直接实例化。
- MV 虚拟名字框候选和规则命中当前通过 `app/rmmz/mv_namebox_native.py::scan_native_mv_virtual_namebox` 消费 Rust 结果；本轨道未确认旧 `collect_mv_virtual_namebox_candidates` 仍在当前生产入口中被调用。
