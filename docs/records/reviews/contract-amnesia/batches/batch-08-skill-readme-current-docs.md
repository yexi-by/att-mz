# 批次 08：Skill 协议、README 与当前文档

## 范围

- `skills/att-mz-protocol/`
- `skills/att-mz/`
- `skills/att-mz-release/`
- `README.md`
- `docs/wiki/`
- `docs/guides/`
- `tests/test_skill_protocol.py`

本批只做只读审查和写入本报告，未检查运行时代码、数据库 schema、发行脚本、数据目录、日志目录、输出目录或缓存目录。

## 事实源

- Skill 协议源：`skills/att-mz-protocol/templates/`、`skills/att-mz-protocol/workflow.toml`、`skills/att-mz-protocol/subagents.toml`、`skills/att-mz-protocol/profiles/`。
- 生成版 Skill：`skills/att-mz/` 与 `skills/att-mz-release/`，由协议源生成；`uv run python scripts/generate_skill_protocol.py --check` 已确认当前无漂移。
- 当前用户文档：`README.md`、`docs/guides/`、`docs/wiki/`。
- 协议测试：`tests/test_skill_protocol.py`，会约束 README 与 Skill 生成物的公开契约内容。

## 只读命令

1. `rg -n 'legacy|deprecated|fallback|compat|old|stale|v[0-9]+|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本|过期|旧工作区|旧确认' README.md docs/wiki docs/guides skills/att-mz-protocol skills/att-mz skills/att-mz-release tests/test_skill_protocol.py`
   - 结果：退出码 0，命中 309 行。命中集中在 README 的 Text Fact Contract v2 恢复说明、Skill CLI 契约的旧数据库/旧工作区/旧 runtime map 描述、占位符确认状态说明、工作区 schema 说明，以及 `tests/test_skill_protocol.py` 的协议保护测试。
2. `uv run python scripts/generate_skill_protocol.py --check`
   - 结果：退出码 0，无输出。说明协议源与开发版、发行版生成物当前一致。
3. `$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-08-skill-readme-current-docs.md' -Pattern $patterns`
   - 结果：退出码 0，无输出；未命中禁用占位文本。

## 结论

FAIL

## 发现

### P1：README 把版本化事实契约与历史恢复入口写成当前用户概念

- 证据：`README.md:76`
- 证据：`README.md:110`
- 证据：`README.md:124`
- 证据：`README.md:126`
- 证据：`README.md:140`
- 违反准则：文案失忆化 | 文档分层
- 影响范围：当前 README 面向普通用户解释 `Text Fact Contract v2`、`v2 facts`、旧数据库、旧工作区、旧 runtime map 和旧项目前缀环境变量。即使文义是在拒绝继续使用历史状态，也要求用户理解历史形态，并把版本号和旧状态纳入当前事实源。
- 建议收束：README 只描述当前可执行要求，例如“索引缺失或不可信时运行 `rebuild-text-index`”“工作区验收失败时重新准备工作区”“运行文件映射不可信时重建当前运行文件”。删除 `v2`、`old/旧`、旧环境变量前缀等历史词，错误修复路径只围绕当前必需输入和下一步命令。
- 后续验证：重新运行本批 `rg`；运行 `uv run python scripts/generate_skill_protocol.py --check`；同步调整 `tests/test_skill_protocol.py` 后运行 `uv run pytest tests/test_skill_protocol.py`。

### P1：Skill CLI 契约源和生成物固定旧数据库、旧工作区、旧 runtime map

- 证据：`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:33`
- 证据：`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:35`
- 证据：`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:36`
- 证据：`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:37`
- 证据：`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:38`
- 证据：`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:39`
- 证据：`skills/att-mz/references/cli-command-contract.md:33`
- 证据：`skills/att-mz/references/cli-command-contract.md:35`
- 证据：`skills/att-mz/references/cli-command-contract.md:36`
- 证据：`skills/att-mz/references/cli-command-contract.md:37`
- 证据：`skills/att-mz/references/cli-command-contract.md:38`
- 证据：`skills/att-mz/references/cli-command-contract.md:39`
- 证据：`skills/att-mz-release/references/cli-command-contract.md:33`
- 证据：`skills/att-mz-release/references/cli-command-contract.md:35`
- 证据：`skills/att-mz-release/references/cli-command-contract.md:36`
- 证据：`skills/att-mz-release/references/cli-command-contract.md:37`
- 证据：`skills/att-mz-release/references/cli-command-contract.md:38`
- 证据：`skills/att-mz-release/references/cli-command-contract.md:39`
- 违反准则：文案失忆化 | 文档分层
- 影响范围：Agent 翻译流程的核心 CLI 契约把当前文本事实称为 `Text Fact Contract v2`，并显式指导不要从旧索引、旧工作区或旧 runtime map 反推当前范围。开发版和发行版生成物都继承该表述，说明历史模型不是单点文案，而是协议源层面的当前事实源。
- 建议收束：优先改 `skills/att-mz-protocol/templates/references/cli-command-contract.md.in`，将该段改成当前索引、当前范围、当前运行映射的有效性要求；生成物在后续修复批次按项目 Skill 生成流程统一刷新，本次 review 不执行写入模式。历史形态解释如确需保留，应移到 CHANGELOG、迁移指南、发布说明或记录目录。
- 后续验证：运行 `uv run python scripts/generate_skill_protocol.py --check`；运行本批 `rg` 确认 `Text Fact Contract v2`、`v2 facts`、旧数据库、旧索引、旧工作区、旧 runtime map 不再出现在当前 Skill/README/docs。

### P1：占位符与结构化规则文档要求理解旧版样本确认和旧确认过期

- 证据：`docs/guides/advanced-usage.md:208`
- 证据：`skills/att-mz-protocol/templates/references/placeholder-rules.md.in:81`
- 证据：`skills/att-mz/references/placeholder-rules.md:81`
- 证据：`skills/att-mz-release/references/placeholder-rules.md:81`
- 证据：`skills/att-mz-protocol/templates/references/structured-placeholder-rules.md.in:67`
- 证据：`skills/att-mz/references/structured-placeholder-rules.md:67`
- 证据：`skills/att-mz-release/references/structured-placeholder-rules.md:67`
- 违反准则：文案失忆化 | 文档分层
- 影响范围：当前进阶指南和 Skill 规则说明把“旧版样本确认不再作为当前确认依据”“旧确认过期”作为 Agent 和用户需要理解的规则。实际当前契约只需要表达“确认状态必须匹配当前候选范围；不匹配则重新审查并导入当前规则”，不需要保留旧版确认模型。
- 建议收束：将说明改为当前候选范围与已保存确认状态的匹配规则，删除“旧版样本确认”“旧确认过期”等历史措辞；用当前无效状态和修正命令表达失败路径。
- 后续验证：运行本批 `rg`；运行 `uv run python scripts/generate_skill_protocol.py --check`；针对协议测试改为断言当前确认语义而非旧版说法。

### P1：工作区文档和流程图把旧工作区、旧文件作为当前操作模型

- 证据：`skills/att-mz-protocol/workflow.toml:56`
- 证据：`skills/att-mz/SKILL.md:136`
- 证据：`skills/att-mz-release/SKILL.md:136`
- 证据：`skills/att-mz-protocol/templates/references/workspace-schema.md.in:7`
- 证据：`skills/att-mz-protocol/templates/references/workspace-schema.md.in:39`
- 证据：`skills/att-mz/references/workspace-schema.md:7`
- 证据：`skills/att-mz/references/workspace-schema.md:39`
- 证据：`skills/att-mz-release/references/workspace-schema.md:7`
- 证据：`skills/att-mz-release/references/workspace-schema.md:39`
- 证据：`docs/guides/att-mz-skill-flow-review.html:762`
- 证据：`docs/guides/att-mz-skill-flow-review.html:942`
- 违反准则：文案失忆化 | 文档分层
- 影响范围：Skill 主流程、工作区 schema 参考和 guides 可视化材料把“继续使用旧工作区”“旧文件不参与本轮输入”“复用旧工作区”作为当前流程停机条件或解释对象。当前契约应只以本轮 `manifest.files` 和当前工作区验收结果作为事实源，不需要把历史目录状态建模给 Agent 或用户。
- 建议收束：将停机条件改成“工作区 manifest 不覆盖当前插件配置/当前输入范围”或“目录外文件不属于本轮输入”；删除旧工作区、旧文件等历史标签。协议源修改后再生成开发版和发行版 Skill，并同步 guides 可视化材料。
- 后续验证：运行本批 `rg`；运行 `uv run python scripts/generate_skill_protocol.py --check`；如更新 HTML 生成链路，补充对应生成物检查。

### P1：结构化占位符规则以 v1 命名当前 schema

- 证据：`skills/att-mz-protocol/templates/references/structured-placeholder-rules.md.in:21`
- 证据：`skills/att-mz/references/structured-placeholder-rules.md:21`
- 证据：`skills/att-mz-release/references/structured-placeholder-rules.md:21`
- 违反准则：文案失忆化 | 文档分层
- 影响范围：当前 Skill 对外说明“v1 只支持 `paired_shell_rules`”，把当前规则结构描述成版本序列的一部分。若当前 JSON schema 没有对外版本协商需求，该表述会让 Agent 以历史/未来版本思维理解当前规则。
- 建议收束：改为“当前只支持 `paired_shell_rules`”或直接描述合法顶层结构；若确有外部 schema 版本字段，应只描述当前字段和有效值，不讲历史版本。
- 后续验证：运行本批 `rg`；运行 `uv run python scripts/generate_skill_protocol.py --check`。

### P2：协议测试强制 README 与 Skill 保留历史恢复术语

- 证据：`tests/test_skill_protocol.py:146`
- 证据：`tests/test_skill_protocol.py:147`
- 证据：`tests/test_skill_protocol.py:149`
- 证据：`tests/test_skill_protocol.py:150`
- 证据：`tests/test_skill_protocol.py:151`
- 证据：`tests/test_skill_protocol.py:152`
- 证据：`tests/test_skill_protocol.py:153`
- 证据：`tests/test_skill_protocol.py:167`
- 证据：`tests/test_skill_protocol.py:169`
- 违反准则：测试失忆化
- 影响范围：`test_v2_fact_recovery_entries_are_documented_for_users_and_agents` 明确要求 README 和 Skill CLI 契约包含 `Text Fact Contract v2`、`v2 facts`、旧数据库、旧工作区、旧 runtime map。该测试会阻止后续把当前文档改成失忆化表述。
- 建议收束：改测当前外部可观察契约，例如索引缺失/范围不一致时提示重建索引、工作区验收失败时提示重新准备工作区、运行映射不可信时提示重建当前运行文件；删除对历史术语的必含断言。
- 后续验证：运行 `uv run pytest tests/test_skill_protocol.py`；运行本批 `rg` 确认测试中不再要求历史术语。

### P2：协议测试仍用 legacy/旧版候选 hash 命名历史模型

- 证据：`tests/test_skill_protocol.py:342`
- 证据：`tests/test_skill_protocol.py:343`
- 证据：`tests/test_skill_protocol.py:354`
- 违反准则：测试失忆化
- 影响范围：该测试当前是在防止公开协议承诺 `legacy_hash`，方向上是收束历史兼容；但测试名称、docstring 和断言仍把历史候选 hash 作为被识别对象。长期保留会使测试层继续记忆旧模型。
- 建议收束：改为当前契约的反向断言，例如公开协议只允许当前候选范围确认字段，且不得说明任何按样本 hash 放行的路径；避免 `legacy_hash` 和“旧版候选样本”进入测试命名与正文。
- 后续验证：运行 `uv run pytest tests/test_skill_protocol.py`；运行本批 `rg` 确认测试文件不再出现 legacy/旧版候选 hash 语义。

## 交叉引用

- `uv run python scripts/generate_skill_protocol.py --check` 通过，说明 `skills/att-mz-protocol/` 的历史/版本化表述已经同步进入 `skills/att-mz/` 与 `skills/att-mz-release/`，不是生成漂移。
- `tests/test_skill_protocol.py:146` 至 `tests/test_skill_protocol.py:169` 会强制 README 和 Skill 继续包含历史恢复术语；清理文档前必须同步清理测试契约。
- `README.md`、`docs/guides/advanced-usage.md`、`skills/att-mz-protocol/templates/references/*.md.in` 与生成版 Skill 对同一批历史概念形成互相引用，应作为一次 Skill 协议与用户文档收束处理。

## 已查无发现范围

- `docs/wiki/` 中命中的 “迁移” 出现在开发边界说明，如“不在长期代码里加入一次性迁移逻辑”，本批未确认其污染当前用户契约。
- `compat/兼容` 命中多为 OpenAI 兼容接口或 Python/Rust 正则兼容性，属于当前技术要求，本批未作为历史兼容问题记录。
- `stale/过期` 命中多为当前索引或当前确认状态与范围不一致的业务状态；除已列出的“旧确认过期”外，本批未确认其它命中属于历史形态污染。
- `docs/guides/advanced-usage.md:418` 与 `docs/wiki/development/release-and-tests.md:66` 的性能脚本说明使用可传入样本路径，且强调不要写本机私有路径；本批未发现脱敏问题。
