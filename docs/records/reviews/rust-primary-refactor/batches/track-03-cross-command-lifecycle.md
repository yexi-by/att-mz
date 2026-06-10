# 轨道 03：跨命令生命周期

## 范围

本轮只读审查覆盖跨命令生命周期：`export-*`、`validate-*`、`import-*`、`rebuild-text-index`、`translate`、`quality-report`、`audit-coverage`、`write-back` 是否消费同一规则、候选、索引元数据和写回事实。

重点复盘插件源码规则验收样本：`export-plugin-source-ast-map -> validate-plugin-source-rules -> import-plugin-source-rules -> rebuild-text-index -> translate -> quality-report -> write-back`。同时抽查非标准 data、事件指令、Note 标签、MV 虚拟名字框、占位符、结构化占位符和覆盖审计的生命周期边界。

本轮没有读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。没有执行 `import-*`、`translate`、`write-back`、`rebuild-active-runtime`、`reset-game`、`reset-translations`、`run-all` 或其他会改变运行状态的命令。

## 只读命令

- `Get-Content -LiteralPath 'C:\Users\夜袭\.agents\skills\python-engineering-standards\SKILL.md'`
- `Get-Content -LiteralPath 'C:\Users\夜袭\.agents\skills\rust-engineering-standards\SKILL.md'`
- `Get-Content -LiteralPath 'C:\Users\Public\Documents\CodexHome\plugins\cache\openai-curated\superpowers\c6ea566d\skills\using-superpowers\SKILL.md'`
- `Get-Content -LiteralPath 'docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md'`
- `Get-Content -LiteralPath 'docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md'`
- `rg -n 'export-|validate-|import-|rebuild-text-index|translate|quality-report|audit-coverage|write-back|prepare-agent-workspace|validate-agent-workspace' app tests README.md skills/att-mz-protocol skills/att-mz skills/att-mz-release`
- `rg -n 'plugin-source|plugin_source|PluginSource|selector|excluded_selectors|source_file|ast|runtime_map|stale' app rust/src tests skills/att-mz-protocol skills/att-mz skills/att-mz-release`
- `rg -n 'nonstandard|event_command|note_tag|mv_virtual_namebox|placeholder|structured_placeholder|terminology|rule_hash|scope_hash' app rust/src tests`
- `rg --files app rust/src tests skills/att-mz-protocol skills/att-mz skills/att-mz-release | rg '(cli|text_index|coverage|quality|workspace|rule_validation|plugin_source|nonstandard|writeback|flow_gate|persistence|translation)'`
- `rg -n 'def .*export|def .*validate|def .*import|def .*rebuild|def .*translate|def .*quality|def .*audit|def .*write|@.*command|subparsers|add_parser' app main.py`
- `rg -n 'read_.*rules|replace_.*rules|scope_hash|rules_fingerprint|workflow_gate_scope_hashes|read_current_text|replace_current_text|current_text|text_index|stale' app/agent_toolkit app/application app/persistence app/translation app/rmmz app/plugin_source_text app/nonstandard_data rust/src`
- 多次 `Get-Content` 窄范围行号读取：`app\agent_toolkit\services\text_index.py`、`app\application\handler.py`、`app\agent_toolkit\services\quality.py`、`app\application\flow_gate.py`、`app\agent_toolkit\services\rule_validation.py`、`app\text_index.py`、`app\plugin_source_text\importer.py`、`app\plugin_source_text\rules.py`、`app\agent_toolkit\services\workspace.py`、`app\agent_toolkit\services\nonstandard_data.py`、`app\agent_toolkit\services\coverage.py`、`rust\src\native_core\scope_index\rebuild.rs`、`tests\test_workflow_gate.py`、`tests\test_plugin_source_text.py`、`tests\test_nonstandard_data.py`、`app\persistence\schema\current.sql`。

## 结论

FAIL

当前实现已经把正文索引作为 `translate`、`quality-report`、`audit-coverage`、`write-back` 的主事实源，但插件源码和非标准 data 的“支线 gate 已预检”元数据不是从同一候选发现事实推导出来的硬结论。`rebuild-text-index` 会写入预检标记，后续命令会信任该标记；同时 Python 校验/导入存在只比较已存排除规则的 fast path。结果是导出、导入、重建、报告、写回之间存在 hidden state 和二次解释。

## 关键发现

### P0：索引生命周期把插件源码和非标准 data 标为已预检，但后续命令没有消费当前候选 gate

证据：

- Rust 重建索引时无条件写入插件源码和非标准 data gate 预检标记：`rust/src/native_core/scope_index/rebuild.rs:576`、`rust/src/native_core/scope_index/rebuild.rs:578`、`rust/src/native_core/scope_index/rebuild.rs:582`、`rust/src/native_core/scope_index/rebuild.rs:583`。
- Python 判断预检只读取这两个 metadata 键：`app/text_index.py:235`、`app/text_index.py:237`、`app/text_index.py:239`、`app/text_index.py:240`。
- `rebuild-text-index` 的 indexed workflow gate 明确把插件源码和非标准 data gate errors 传空：`app/agent_toolkit/services/text_index.py:178`、`app/agent_toolkit/services/text_index.py:183`、`app/agent_toolkit/services/text_index.py:184`，并且最终报告 `errors=[]`：`app/agent_toolkit/services/text_index.py:216`、`app/agent_toolkit/services/text_index.py:217`。
- `translate` warm index 前置检查同样传空：`app/application/handler.py:995`、`app/application/handler.py:1000`、`app/application/handler.py:1001`。
- `write-back` 前置检查同样传空：`app/application/handler.py:1422`、`app/application/handler.py:1427`、`app/application/handler.py:1428`。
- 真正的插件源码 gate 会扫描当前源码、过滤 stale 规则并阻断高风险候选：`app/application/flow_gate.py:558`、`app/application/flow_gate.py:568`、`app/application/flow_gate.py:569`、`app/application/flow_gate.py:575`、`app/application/flow_gate.py:584`、`app/application/flow_gate.py:587`。
- 真正的非标准 data gate 会扫描当前 data、按 file hash 判断 stale 并阻断高风险候选：`app/application/flow_gate.py:608`、`app/application/flow_gate.py:617`、`app/application/flow_gate.py:633`、`app/application/flow_gate.py:640`、`app/application/flow_gate.py:650`、`app/application/flow_gate.py:653`。
- `quality-report` 在有插件源码规则且 metadata 标记存在时直接采用 `prechecked_from_text_index`：`app/agent_toolkit/services/quality.py:1311`、`app/agent_toolkit/services/quality.py:1316`、`app/agent_toolkit/services/quality.py:1317`，错误列表只追加该分支产生的 `plugin_source_gate_errors`：`app/agent_toolkit/services/quality.py:1635`、`app/agent_toolkit/services/quality.py:1642`。
- 现有测试固定了这种跳过行为：`tests/test_workflow_gate.py:151`、`tests/test_workflow_gate.py:157`、`tests/test_workflow_gate.py:168`、`tests/test_workflow_gate.py:202`，以及高风险源码/data 重建仍为 ok：`tests/test_workflow_gate.py:207`、`tests/test_workflow_gate.py:222`、`tests/test_workflow_gate.py:227`、`tests/test_workflow_gate.py:242`。

生命周期命令序列：

1. `export-plugin-source-ast-map`：读取当前插件源码、`plugins.js` 和翻译源快照，并用当前 `TextRules` 生成 AST 候选，事实源是当前文件和 Rust native scan。证据：`app/agent_toolkit/services/workspace.py:567`、`app/agent_toolkit/services/workspace.py:578`、`app/agent_toolkit/services/workspace.py:586`、`app/agent_toolkit/services/workspace.py:587`、`app/agent_toolkit/services/workspace.py:588`。
2. `validate-plugin-source-rules` / `import-plugin-source-rules` 完整路径：读取当前源码并构建 native scan，事实源是当前 AST selector 和导入 JSON。证据：`app/agent_toolkit/services/rule_validation.py:923`、`app/agent_toolkit/services/rule_validation.py:927`、`app/agent_toolkit/services/rule_validation.py:928`。
3. `rebuild-text-index`：Rust 能把已导入插件源码规则写入当前 text index 行，事实源是 `context.plugin_source_rules` 与 managed texts。证据：`rust/src/native_core/scope_index/rebuild.rs:2119`、`rust/src/native_core/scope_index/rebuild.rs:2123`、`rust/src/native_core/scope_index/rebuild.rs:2126`、`rust/src/native_core/scope_index/rebuild.rs:2156`、`rust/src/native_core/scope_index/rebuild.rs:2163`。
4. `translate` / `write-back`：使用 indexed workflow gate，但插件源码和非标准 data gate 事实被空列表替代。证据：`app/application/handler.py:995`、`app/application/handler.py:1000`、`app/application/handler.py:1422`、`app/application/handler.py:1427`。
5. `quality-report`：消费 text index metadata 的预检标记，不重新消费当前候选 gate。证据：`app/agent_toolkit/services/quality.py:1311`、`app/agent_toolkit/services/quality.py:1317`。
6. `audit-coverage`：会确保/读取当前 text index，后续以当前 text fact SQL 计数为报告事实。证据：`app/agent_toolkit/services/coverage.py:153`、`app/agent_toolkit/services/coverage.py:306`、`app/agent_toolkit/services/coverage.py:317`、`app/agent_toolkit/services/coverage.py:453`。

业务事实：插件源码 AST selector 候选、非标准 data 文件候选、高风险支线 gate、text index metadata、当前 text facts 被拆成多个事实入口。导出和完整导入使用当前源码/当前 data；重建写入一个不等价的预检标记；后续命令把该标记当作 gate 已完成。

违反原则：违反单一事实来源、跨命令生命周期一致性和显式失败原则。尤其是 “报告是否被下一命令真实消费” 这一点不成立：`rebuild-text-index` 的报告/metadata 声称预检，但它没有携带当前插件源码/非标准 data gate 的真实结论。

影响：高风险插件源码或非标准 data 可以在未处理支线规则时被 `rebuild-text-index` 标记为已预检，随后 `translate`、`quality-report`、`write-back` 继续消费该 metadata。用户会看到重建成功、报告没有对应高风险错误，并可能进入翻译或写回流程。

Python/Rust 职责判断：Rust 已经是 text index 主路径，source branch gate 结果也必须由 Rust 重建索引时统一生成或由 Rust 暴露的结构化结果统一消费。Python 可以保留 CLI 编排、报告格式化和错误映射，不应在跨命令 gate 中注入空事实。

建议 Rust 接管点：在 `rust/src/native_core/scope_index/rebuild.rs` 的索引重建中统一产出插件源码和非标准 data 的 gate 结论，包括 high risk、stale、review incomplete、当前 selector/path/file hash 覆盖状态；`workflow_gate_scope_hashes` 只记录真实结论的 scope hash 或错误摘要。

应删除或瘦身的 Python 逻辑：删除 `collect_indexed_workflow_gate_errors(... plugin_source_rule_gate_errors=[], nonstandard_data_rule_gate_errors=[])` 这种空列表捷径，或改为只接收 Rust 重建返回的结构化 gate 结果。`quality-report` 的 `prechecked_from_text_index` 只能用于显示 Rust 已完成的具体 gate 结论，不能作为硬 gate 事实本身。

禁止方向：不要在 `translate`、`quality-report`、`write-back` 的 Python hot path 重新全量扫描来补洞；不要继续用 metadata precheck 字符串代表 “没有问题”；不要只改报告文案掩盖生命周期断点。

后续验证：新增插件源码和非标准 data 的跨命令测试：存在高风险候选且未导入规则时，`rebuild-text-index` 应返回可消费的 gate error，或后续 `translate`、`quality-report --include-write-probe`、`write-back` 必须阻断；导入规则后，重建、报告和写回必须消费同一 Rust 事实并通过。

### P1：插件源码 `excluded_selectors` fast path 只比对已存规则，跳过当前 AST、启用状态和 selector 新鲜度

证据：

- `_plugin_source_import_matches_current_exclusions()` 只比较导入文件和已存记录的 `selectors` / `excluded_selectors`，没有读取当前插件源码、`plugins.js`、file hash 或 AST scan：`app/agent_toolkit/services/rule_validation.py:235`、`app/agent_toolkit/services/rule_validation.py:246`、`app/agent_toolkit/services/rule_validation.py:255`、`app/agent_toolkit/services/rule_validation.py:262`、`app/agent_toolkit/services/rule_validation.py:266`。
- `validate_plugin_source_rules` 在 metadata 预检标记存在且排除规则匹配时直接返回当前排除规则报告：`app/agent_toolkit/services/rule_validation.py:809`、`app/agent_toolkit/services/rule_validation.py:814`、`app/agent_toolkit/services/rule_validation.py:817`、`app/agent_toolkit/services/rule_validation.py:818`、`app/agent_toolkit/services/rule_validation.py:824`。
- `import_plugin_source_rules` 同样 shortcut，不进入后续当前源码 scan 和记录重建：`app/agent_toolkit/services/rule_validation.py:886`、`app/agent_toolkit/services/rule_validation.py:897`、`app/agent_toolkit/services/rule_validation.py:900`、`app/agent_toolkit/services/rule_validation.py:901`、`app/agent_toolkit/services/rule_validation.py:907`。
- 完整路径才会加载当前翻译源插件源码并构建 native scan：`app/agent_toolkit/services/rule_validation.py:912`、`app/agent_toolkit/services/rule_validation.py:923`、`app/agent_toolkit/services/rule_validation.py:925`、`app/agent_toolkit/services/rule_validation.py:927`。
- 完整 importer 会校验 JS AST、文件存在、启用状态和 selector 命中：`app/plugin_source_text/importer.py:58`、`app/plugin_source_text/importer.py:63`、`app/plugin_source_text/importer.py:65`、`app/plugin_source_text/importer.py:73`、`app/plugin_source_text/importer.py:137`、`app/plugin_source_text/importer.py:139`。
- 新鲜度过滤函数本身也知道要按当前源码文件、启用状态和 selector 命中过滤：`app/plugin_source_text/rules.py:34`、`app/plugin_source_text/rules.py:41`、`app/plugin_source_text/rules.py:44`、`app/plugin_source_text/rules.py:68`、`app/plugin_source_text/rules.py:76`、`app/plugin_source_text/rules.py:79`。

生命周期命令序列：

1. `export-plugin-source-ast-map` 产出当前 AST 候选，事实源是当前源码和 Rust native scan。证据：`app/agent_toolkit/services/workspace.py:567`、`app/agent_toolkit/services/workspace.py:588`。
2. `validate-plugin-source-rules` 预期应校验导入 JSON 是否命中当前 AST；但 `excluded_selectors` only 且当前保存记录一致时，使用 metadata 与已存记录 shortcut。证据：`app/agent_toolkit/services/rule_validation.py:817`、`app/agent_toolkit/services/rule_validation.py:824`。
3. `import-plugin-source-rules` 预期应重新写入当前规则并清理受影响译文；但 shortcut 直接返回报告。证据：`app/agent_toolkit/services/rule_validation.py:900`、`app/agent_toolkit/services/rule_validation.py:907`。
4. `rebuild-text-index` 才会在 Rust managed text 路径发现 stale 或 review incomplete。证据：`rust/src/native_core/scope_index/rebuild.rs:2171`、`rust/src/native_core/scope_index/rebuild.rs:2173`、`rust/src/native_core/scope_index/rebuild.rs:2176`。

业务事实：只包含 `excluded_selectors` 的规则也是当前 AST selector 事实的一部分；它不写入可翻译文本，但会改变高风险支线是否已覆盖。导入时有效的 selector，在源码、启用状态和配置未变时，后续重建不应立刻 stale；反过来，若这些事实已变，validate/import 不能只因为已存记录匹配就报告成功。

违反原则：违反跨命令生命周期一致性、显式失败和单一事实来源。这里的 `text_index_source_branch_gates_prechecked(metadata)` 被二次解释为 “当前 AST 可跳过”，但它本身不是 selector 新鲜度证明。

影响：排除规则可能在当前源码/启用状态/selector 事实已变化时仍通过 validate/import，直到 `rebuild-text-index` 或写回相关流程才暴露 stale。用户会误以为导入文件已经针对当前游戏通过校验。

Python/Rust 职责判断：当前 Python fast path 是事实捷径，不是编排。selector、active、AST 命中、新鲜度判断应由 Rust 插件源码扫描/规则验证统一提供；Python 只应接收结构化校验结果并渲染报告。

建议 Rust 接管点：提供 Rust 侧 `validate_plugin_source_rules_current` 或扩展现有 native scan，使 `selectors` 和 `excluded_selectors` 都基于同一 AST map、active plugins 和规则 hash 校验；重复导入也必须确认 current scope hash 与规则记录一致。

应删除或瘦身的 Python 逻辑：删除 `_plugin_source_import_matches_current_exclusions()` 作为跳过当前 scan 的条件，或把它降级为 “Rust 已返回同一 scope hash 后的报告优化”。`_plugin_source_current_exclusions_report()` 不能独立代表当前校验通过。

禁止方向：不要在 Python 里继续补更多字符串比较来判断 selector；不要让 metadata precheck 继续承担 AST 新鲜度语义；不要只通过更新测试期望保留 shortcut。

后续验证：新增 `excluded_selectors` only 生命周期测试：导出 AST 后导入排除规则，源码/启用状态/配置未变时重复 validate/import 与 `rebuild-text-index` 都通过；改变源码 selector 或插件启用状态后，validate/import 必须在同一阶段报 stale/invalid，不能等待后续重建。

### P2：测试把“不在 Python 热路径偷扫”固定成“后续命令不消费插件源码高风险”

证据：

- 翻译测试禁止 Python 隐式扫描插件源码，并断言高风险插件源码存在时 `translate --max-items` 仍不阻断：`tests/test_workflow_gate.py:151`、`tests/test_workflow_gate.py:157`、`tests/test_workflow_gate.py:168`、`tests/test_workflow_gate.py:188`、`tests/test_workflow_gate.py:202`、`tests/test_workflow_gate.py:203`。
- 重建索引测试在高风险插件源码和高风险非标准 data 下仍断言 `status == "ok"`：`tests/test_workflow_gate.py:207`、`tests/test_workflow_gate.py:222`、`tests/test_workflow_gate.py:227`、`tests/test_workflow_gate.py:242`。
- 质量报告测试断言不扫描插件源码且错误中没有 `plugin_source_text_high_risk`：`tests/test_plugin_source_text.py:2766`、`tests/test_plugin_source_text.py:2771`、`tests/test_plugin_source_text.py:2773`。
- 含写回探针的质量报告测试同样断言没有 `plugin_source_text_high_risk` 且写回探针执行：`tests/test_plugin_source_text.py:2816`、`tests/test_plugin_source_text.py:2821`、`tests/test_plugin_source_text.py:2823`、`tests/test_plugin_source_text.py:2825`。
- 另有测试把 `plugin_source_review_status` 固定为 `prechecked_from_text_index` 并不输出 reviewed/unreviewed selector count：`tests/test_plugin_source_text.py:2896`、`tests/test_plugin_source_text.py:2901`、`tests/test_plugin_source_text.py:2902`、`tests/test_plugin_source_text.py:2903`。

生命周期命令序列：

1. 测试要求 `translate` / `quality-report` 不在 Python hot path 触发重型扫描，这是合理的性能边界。
2. 但现有断言把这个边界进一步固化成：即使高风险插件源码存在，`translate` / `quality-report --include-write-probe` 也不能看到 source branch gate error。
3. 这与 Rust 主路径目标冲突：正确方向应是“不由 Python 偷扫，但由 Rust text index 或其结构化 gate 结果被后续命令真实消费”。

业务事实：测试套件会阻止把插件源码/非标准 data gate 下沉到 Rust 主路径后真实阻断后续命令。

违反原则：测试未覆盖用户可观察生命周期，而是覆盖了当前 shortcut 实现细节；这会让跨命令契约缺口长期保留。

影响：主代理或后续 worker 修复 P0 时会遇到测试倒挂，容易被迫继续保留 metadata shortcut。

Python/Rust 职责判断：测试应继续禁止 Python 热路径重型扫描，但应允许或要求 Rust index gate 消费结果。Python 侧断言应从 “没有 high risk error” 改成 “Python 没有扫描，但 Rust gate 结论被报告/阻断”。

建议 Rust 接管点：测试改造后，以 Rust `rebuild-text-index` 输出的 gate result 和 metadata scope hash 为断言对象；后续命令只读取该结果，不调 Python scan。

应删除或瘦身的 Python 逻辑：删除以 `prechecked_from_text_index` 作为成功证明的测试绑定；保留“不调用 Python heavy scan”的性能断言。

禁止方向：不要为了过旧测试而继续把高风险支线错误藏在 details 或 summary；不要把 `status == ok` 当作支线 gate 已处理。

后续验证：把现有测试拆成两类：性能测试断言 Python hot path 没有扫描；生命周期测试断言 Rust gate 结果能被 `translate`、`quality-report`、`write-back` 消费。

## 双事实来源清单

- 插件源码候选事实：
  - 导出事实源：`export-plugin-source-ast-map` 读取当前插件源码、`plugins.js`、source snapshot、setting text rules 后生成 AST map。证据：`app/agent_toolkit/services/workspace.py:567`、`app/agent_toolkit/services/workspace.py:578`、`app/agent_toolkit/services/workspace.py:586`、`app/agent_toolkit/services/workspace.py:588`。
  - 校验/导入完整事实源：`validate_plugin_source_rules` / `import_plugin_source_rules` 完整路径读取当前 translation source plugin files 并构建 native scan。证据：`app/agent_toolkit/services/rule_validation.py:923`、`app/agent_toolkit/services/rule_validation.py:927`。
  - fast path 事实源：只比较 import JSON 与已存 records 的 selector/excluded selector，且依赖 text index precheck metadata。证据：`app/agent_toolkit/services/rule_validation.py:235`、`app/agent_toolkit/services/rule_validation.py:817`、`app/agent_toolkit/services/rule_validation.py:900`。
  - Rust 重建事实源：`scan_plugin_source_rows` 只在 `context.plugin_source_rules` 非空时收集 managed texts，并在 stale/review incomplete 时转 structured error。证据：`rust/src/native_core/scope_index/rebuild.rs:2119`、`rust/src/native_core/scope_index/rebuild.rs:2123`、`rust/src/native_core/scope_index/rebuild.rs:2126`、`rust/src/native_core/scope_index/rebuild.rs:2173`、`rust/src/native_core/scope_index/rebuild.rs:2176`。
  - 后续报告事实源：`quality-report` 信任 `text_index_source_branch_gates_prechecked(metadata)`。证据：`app/agent_toolkit/services/quality.py:1311`、`app/agent_toolkit/services/quality.py:1317`。

- 非标准 data 候选事实：
  - 导出事实源：`export_nonstandard_data_json` 使用当前 translation source layout、setting text rules、custom/structured rules 扫描。证据：`app/agent_toolkit/services/nonstandard_data.py:89`、`app/agent_toolkit/services/nonstandard_data.py:98`、`app/agent_toolkit/services/nonstandard_data.py:104`、`app/agent_toolkit/services/nonstandard_data.py:110`。
  - validate/import 事实源：单命令服务解析 import JSON 并扫描当前 data。证据：`app/agent_toolkit/services/nonstandard_data.py:148`、`app/agent_toolkit/services/nonstandard_data.py:156`、`app/agent_toolkit/services/nonstandard_data.py:157`。
  - workflow gate 事实源：`_nonstandard_data_rule_gate_errors` 扫描当前 data 并按 file hash 判断 stale。证据：`app/application/flow_gate.py:608`、`app/application/flow_gate.py:617`、`app/application/flow_gate.py:633`、`app/application/flow_gate.py:640`。
  - indexed lifecycle 事实源：`rebuild-text-index`、`translate`、`write-back` 对 nonstandard gate errors 传空。证据：`app/agent_toolkit/services/text_index.py:184`、`app/application/handler.py:1001`、`app/application/handler.py:1428`。

- 空规则 review state 与 text index metadata：
  - `rule_review_states` 保存按 rule domain 的 `scope_hash` / `reviewed_empty`。证据：`app/persistence/schema/current.sql:237`、`app/persistence/schema/current.sql:239`、`app/persistence/schema/current.sql:240`。
  - `text_index_meta` 另存 `workflow_gate_scope_hashes`。证据：`app/persistence/schema/current.sql:312`、`app/persistence/schema/current.sql:317`。
  - 本轮未确认 event_command、note_tag、mv_virtual_namebox、placeholder、structured_placeholder 在这两套 metadata 之间存在 hash 漂移，但它们应纳入后续统一 Rust scope hash 审查。

- 覆盖审计和写回范围：
  - `audit-coverage` 不回退 Python full scope，先检测/重建 text index，再用当前 text fact SQL 计数生成报告。证据：`app/agent_toolkit/services/coverage.py:302`、`app/agent_toolkit/services/coverage.py:306`、`app/agent_toolkit/services/coverage.py:317`、`app/agent_toolkit/services/coverage.py:453`、`app/agent_toolkit/services/coverage.py:455`。
  - 这条主线本身更接近单一事实源；风险是它继承了 text index metadata 中 source branch gate 不真实的问题。

## Rust 主路径缺口

- Rust text index rebuild 已负责写插件源码 text fact 行，但还没有把插件源码/非标准 data 的 high risk、stale、review incomplete gate 作为强约束统一输出给后续命令。证据：`rust/src/native_core/scope_index/rebuild.rs:2119`、`rust/src/native_core/scope_index/rebuild.rs:2173`、`rust/src/native_core/scope_index/rebuild.rs:2176`。
- Rust 当前写入的 `TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY` 与 `TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY` 是无条件 precheck，而不是当前候选扫描结果。证据：`rust/src/native_core/scope_index/rebuild.rs:576`、`rust/src/native_core/scope_index/rebuild.rs:578`、`rust/src/native_core/scope_index/rebuild.rs:582`。
- 插件源码 `excluded_selectors` 的 validate/import 新鲜度仍由 Python shortcut 控制，Rust 没有成为这类规则的唯一 selector 事实源。证据：`app/agent_toolkit/services/rule_validation.py:235`、`app/agent_toolkit/services/rule_validation.py:824`、`app/agent_toolkit/services/rule_validation.py:907`。

## Python 删除候选

- 删除或收束 `collect_indexed_workflow_gate_errors` 调用中对 `plugin_source_rule_gate_errors=[]`、`nonstandard_data_rule_gate_errors=[]` 的空事实注入。证据：`app/agent_toolkit/services/text_index.py:183`、`app/agent_toolkit/services/text_index.py:184`、`app/application/handler.py:1000`、`app/application/handler.py:1001`、`app/application/handler.py:1427`、`app/application/handler.py:1428`。
- 删除 `_plugin_source_import_matches_current_exclusions()` 作为跳过当前 AST scan 的条件，或改成只消费 Rust 已验证的 current scope hash。证据：`app/agent_toolkit/services/rule_validation.py:235`、`app/agent_toolkit/services/rule_validation.py:817`、`app/agent_toolkit/services/rule_validation.py:900`。
- 收束 `quality-report` 的 `prechecked_from_text_index` 分支，让它展示 Rust gate result，而不是代替 gate result。证据：`app/agent_toolkit/services/quality.py:1311`、`app/agent_toolkit/services/quality.py:1317`、`app/agent_toolkit/services/quality.py:1642`。

## 测试缺口

- 缺少完整插件源码验收样本：`export-plugin-source-ast-map -> validate-plugin-source-rules -> import-plugin-source-rules -> rebuild-text-index -> translate -> quality-report --include-write-probe -> write-back`，并断言每一步使用同一 selector/file/active/source hash 事实。
- 缺少 `excluded_selectors` only 的重复导入测试：源码、启用状态、配置未变时不 stale；任一事实变化时 validate/import 立即报错。
- 缺少非标准 data indexed lifecycle 测试：高风险 data 未导入规则时，`rebuild-text-index` 或后续命令必须消费 gate error。现有旧 workflow gate 测试能证明非标准 data gate 本身可阻断：`tests/test_nonstandard_data.py:390`、`tests/test_nonstandard_data.py:408`、`tests/test_nonstandard_data.py:447`、`tests/test_nonstandard_data.py:453`、`tests/test_nonstandard_data.py:480`、`tests/test_nonstandard_data.py:489`；但 indexed path 传空，见 P0 证据。
- 现有测试固定 `quality-report` 和 `translate` 不看到插件源码高风险，应改成禁止 Python 重扫但要求 Rust gate 结果被消费。证据：`tests/test_workflow_gate.py:151`、`tests/test_plugin_source_text.py:2766`、`tests/test_plugin_source_text.py:2816`、`tests/test_plugin_source_text.py:2896`。

## 交叉引用

- 与轨道 01（规则/selector/AST Rust 主路径）交叉：P1 的 `excluded_selectors` selector 新鲜度应归到同一 Rust AST map 和 rule validation。
- 与轨道 02（text index / current facts）交叉：P0 的 gate metadata 由 text index rebuild 写入，后续 `audit-coverage`、`quality-report`、`write-back` 都依赖它。
- 与轨道 04（写回协议）交叉：`quality-report --include-write-probe` 与 `write-back` 应共享 Rust gate，不应因为 source branch metadata shortcut 允许支线错误绕过。
- 与轨道 05（测试与契约）交叉：P2 需要改造现有测试断言，否则修复会被旧测试阻断。

## 已查无发现范围

- CLI 入口到服务调用的基本映射已查，未发现本轮覆盖命令完全未注册的问题：`app/cli/commands/translation.py:88`、`app/cli/commands/translation.py:158`、`app/cli/commands/translation.py:248`、`app/cli/commands/write_back.py:32`。
- `audit-coverage` 主流程已切到 current text facts 和 SQL 计数，没有看到它回退构建 Python 完整文本范围；风险主要来自它读取的 text index metadata。证据：`app/agent_toolkit/services/coverage.py:302`、`app/agent_toolkit/services/coverage.py:447`。
- 非标准 data 的单命令 validate/import 自身会读取当前扫描事实；确认缺口在 indexed lifecycle 对 gate errors 传空，而不是 validate/import 单点。证据：`app/agent_toolkit/services/nonstandard_data.py:148`、`app/agent_toolkit/services/nonstandard_data.py:156`、`app/application/handler.py:1001`。
- event_command、note_tag、mv_virtual_namebox、placeholder、structured_placeholder 只做了抽查，未确认存在同级别生命周期缺陷；但双 metadata 结构需要由主代理或对应轨道继续审查。证据：`app/persistence/schema/current.sql:237`、`app/persistence/schema/current.sql:312`。
- 本轮未执行测试、未执行 CLI 状态变更命令、未修改源码或测试。
