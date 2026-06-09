# 契约失忆化专项 Review 总报告

## 执行摘要

本次 review 结论：FAIL。

已完成 10 个只读批次报告，并由主线程合并为本报告。确认发现合计：

- P0：12
- P1：6
- P2：23
- P3：0

批次状态：

| 批次 | 结论 | P0 | P1 | P2 | P3 |
| --- | --- | ---: | ---: | ---: | ---: |
| `batch-01-cli-config-runtime.md` | FAIL | 1 | 0 | 3 | 0 |
| `batch-02-sqlite-persistence.md` | FAIL | 2 | 0 | 1 | 0 |
| `batch-03-text-fact-index-scope.md` | FAIL | 3 | 1 | 3 | 0 |
| `batch-04-workspace-rules-agent-toolkit.md` | FAIL | 2 | 0 | 2 | 0 |
| `batch-05-translation-llm-prompt-quality.md` | FAIL | 1 | 0 | 1 | 0 |
| `batch-06-writeback-rmmz-file-safety.md` | FAIL | 1 | 0 | 3 | 0 |
| `batch-07-rust-native-python-adapters.md` | FAIL | 2 | 0 | 2 | 0 |
| `batch-08-skill-readme-current-docs.md` | FAIL | 0 | 5 | 2 | 0 |
| `batch-09-tests-fixtures-helpers.md` | FAIL | 0 | 0 | 5 | 0 |
| `batch-10-release-build-history-records.md` | NEEDS_REVIEW | 0 | 0 | 1 | 0 |

存在 P0/P1 阻断，说明历史形态已经进入当前运行时、schema、用户文案、README/Skill 当前契约和测试事实源。本次 review 成功状态不是“项目已完成清理”，而是已经形成可审计的问题索引和后续清理入口。

## 最高优先级问题索引

1. 配置加载当前路径仍识别并展示旧模型环境变量。
   证据：`batch-01-cli-config-runtime.md`；`app/config/environment.py:10`、`app/config/environment.py:39`、`app/config/environment.py:74`、`app/config/environment.py:95`。

2. SQLite 当前 schema、Python/Rust SQL 与用户文案仍以 `text_facts_v2` / `text_fact_scope_v2` / `Text Fact Contract v2` 表达正式契约。
   证据：`batch-02-sqlite-persistence.md`；`app/persistence/schema/current.sql:382`、`app/persistence/schema/current.sql:424`、`app/persistence/sql.py:41`、`app/persistence/text_fact_records.py:120`、`rust/src/native_core/write_back_plan/repository.rs:401`、`rust/src/native_core/scope_index/storage.rs:826`。

3. Rust schema 校验错误把“迁移数据库”放进当前运行时修正动作。
   证据：`batch-02-sqlite-persistence.md`、`batch-03-text-fact-index-scope.md`、`batch-07-rust-native-python-adapters.md`；`rust/src/native_core/scope_index/storage.rs:278`、`rust/src/native_core/scope_index/storage.rs:286`。

4. Text Fact 到翻译输入的转换仍容忍当前索引定位缺失。
   证据：`batch-03-text-fact-index-scope.md`；`app/text_fact_quality.py:152`、`app/text_fact_core.py:185`、`app/text_fact_core.py:201`、`rust/src/native_core/scope_index/rebuild.rs:3313`。

5. 当前契约错误和 Agent feedback 错误文案暴露“旧索引正文”。
   证据：`batch-03-text-fact-index-scope.md`、`batch-04-workspace-rules-agent-toolkit.md`；`app/text_fact_core.py:224`、`app/text_fact_core.py:228`、`app/agent_toolkit/services/feedback.py:140`、`app/agent_toolkit/services/feedback.py:212`。

6. 工作区 cleanup 将 manifest 外文件描述为“旧文件”。
   证据：`batch-04-workspace-rules-agent-toolkit.md`；`app/agent_toolkit/services/workspace.py:1461`、`app/agent_toolkit/services/workspace.py:2126`。

7. 模型响应 ID 仍接受数字形态并转为字符串匹配。
   证据：`batch-05-translation-llm-prompt-quality.md`；`app/translation/context.py:237`、`app/translation/verify.py:38`、`app/translation/verify.py:279`、`tests/test_translation_line_alignment.py:477`。

8. RMMZ 兼容完整加载入口在缺可信源快照时回退当前运行文件。
   证据：`batch-06-writeback-rmmz-file-safety.md`；`app/rmmz/loader.py:62`、`app/rmmz/loader.py:66`、`app/rmmz/loader.py:451`、`app/rmmz/loader.py:570`、`app/rmmz/__init__.py:9`、`app/rmmz/__init__.py:24`。

9. native 契约版本错误把当前失败描述为旧扩展。
   证据：`batch-07-rust-native-python-adapters.md`；`app/native_contract.py:6`、`app/native_contract.py:11`、`app/native_contract.py:15`。

10. 当前 README、Skill canonical 源、生成 Skill 和 docs/guides 把历史恢复对象写成用户/Agent 当前概念。
    证据：`batch-08-skill-readme-current-docs.md`；`README.md:76`、`README.md:110`、`skills/att-mz-protocol/templates/references/cli-command-contract.md.in:33`、`skills/att-mz/references/cli-command-contract.md:33`、`skills/att-mz-release/references/cli-command-contract.md:33`、`docs/guides/advanced-usage.md:208`、`skills/att-mz-protocol/workflow.toml:56`、`skills/att-mz/SKILL.md:136`、`skills/att-mz-release/SKILL.md:136`。

11. 写回探针文案要求用户理解“临时回退扫描插件源码”。
    证据：`batch-03-text-fact-index-scope.md`；`app/text_scope/write_probe.py:78`、`app/text_scope/write_probe.py:80`。

## 横向矩阵

### 运行时历史记忆

- 配置层会显式收集、命名并拒绝旧环境变量前缀，属于当前运行路径识别历史形态。来源：`batch-01-cli-config-runtime.md`。
- Text Fact 转换允许缺失当前索引定位，RMMZ 公共加载入口允许缺可信源快照时读取当前运行文件，LLM 响应解析允许数字 ID 进入当前匹配路径。来源：`batch-03-text-fact-index-scope.md`、`batch-05-translation-llm-prompt-quality.md`、`batch-06-writeback-rmmz-file-safety.md`。
- native 契约检查和应用层导出仍以旧扩展、历史包级导出、旧调用点参数解释当前边界。来源：`batch-06-writeback-rmmz-file-safety.md`、`batch-07-rust-native-python-adapters.md`。

### Schema 历史记忆

- 当前 SQLite schema、Python 常量、Rust SQL、错误文案和测试共同使用 `v2` 作为正式业务名称。来源：`batch-02-sqlite-persistence.md`。
- `schema_version` 作为当前完整性校验可以存在，但运行时文案把不匹配解释为迁移问题。来源：`batch-02-sqlite-persistence.md`、`batch-03-text-fact-index-scope.md`、`batch-07-rust-native-python-adapters.md`。

### 文案历史记忆

- 用户可见错误中出现“旧模型环境变量”“旧索引正文”“旧文件”“回退扫描”“迁移数据库”“扩展版本过旧”。来源：`batch-01-cli-config-runtime.md`、`batch-03-text-fact-index-scope.md`、`batch-04-workspace-rules-agent-toolkit.md`、`batch-07-rust-native-python-adapters.md`。
- README、Skill、guides 把旧数据库、旧工作区、旧 runtime map、旧确认和版本化规则描述成当前用户/Agent 需要理解的对象。来源：`batch-08-skill-readme-current-docs.md`。

### 测试历史模型

- 配置、CLI JSON、persistence、native adapter、quality gate、writeback、agent toolkit、text index、Skill protocol 测试都以 legacy/old/旧/迁移/fallback 命名当前失败或当前禁止路径。来源：`batch-01-cli-config-runtime.md`、`batch-02-sqlite-persistence.md`、`batch-03-text-fact-index-scope.md`、`batch-04-workspace-rules-agent-toolkit.md`、`batch-05-translation-llm-prompt-quality.md`、`batch-06-writeback-rmmz-file-safety.md`、`batch-07-rust-native-python-adapters.md`、`batch-08-skill-readme-current-docs.md`、`batch-09-tests-fixtures-helpers.md`。
- 共享测试 helper 会把旧式译文对象迁成当前 fact 身份，并自动生成过期行，导致普通测试路径继续接受历史输入模型。来源：`batch-09-tests-fixtures-helpers.md`。

### 文档与 Skill 当前契约漂移

- Skill canonical 源和生成物语义一致，`uv run python scripts/generate_skill_protocol.py --check` 已通过；问题不是生成物漂移，而是 canonical 当前文案本身保留历史模型。来源：`batch-08-skill-readme-current-docs.md`。
- `tests/test_skill_protocol.py` 强制 README 与 Skill 保留历史恢复术语，会阻止文档失忆化修复。来源：`batch-08-skill-readme-current-docs.md`、`batch-09-tests-fixtures-helpers.md`。

### 归档记录污染风险

- 未确认 P3 归档污染。
- `batch-10-release-build-history-records.md` 标记一项 NEEDS_REVIEW：`tests/test_release_notes.py` 读取日期命名设计文档作为当前 fact domain 事实源。证据：`tests/test_release_notes.py:83`、`tests/test_release_notes.py:85`、`tests/test_release_notes.py:90`、`tests/test_release_notes.py:92`。

## 跨批重复与同根问题

1. `Text Fact v2` 已从 schema 名称扩散到运行时 API、Rust SQL、错误文案、README、Skill 和测试。清理时不能只改文档或只改表名，需要同步收束 schema、adapter、用户文案和测试事实源。

2. “旧索引正文”是同根运行时文案问题，至少影响 `text_fact_contract_error()` 和 Agent feedback 校验。建议先改公共错误生成，再检查调用方是否重复拼接历史概念。

3. “迁移数据库”在 Rust schema storage 中被多个批次重复发现。建议集中改 Rust 错误消息和相关测试，再让 Python/Rust 错误映射统一只表达当前结构不满足要求。

4. 当前可信源/当前运行文件的边界仍被兼容 loader 稀释，且 tests 中大量调用默认 `load_game_data()`。应先确定当前唯一入口，再迁移测试调用，避免写回路径继续拥有第二事实来源。

5. 测试层不是单纯命名问题：部分 helper 会自动构造过期或迁移后的数据，使当前成功路径仍依赖历史输入形状。需要先拆普通 helper 与无效状态 fixture，再改测试命名。

6. 文档/Skill 当前事实源由测试反向固定。文档清理前应先改 `tests/test_skill_protocol.py` 的断言模型，否则清理会被现有测试阻止。

## 建议清理批次

1. 先清 P0 运行时分支和用户可见错误：配置旧环境变量识别、LLM 数字 ID、RMMZ 兼容 loader、native 契约错误、Rust schema 迁移文案、旧索引正文。

2. 再清 schema/API 命名面：评估 `text_facts_v2`、`text_fact_scope_v2`、`TextFactV2Record` 等是否改成当前无版本名称，并同步 Python/Rust SQL、schema 常量、错误文案和测试。

3. 清理 README/Skill canonical 源：优先改 `skills/att-mz-protocol/`，再生成开发版和发行版 Skill，随后更新 README 与 guides。生成物检查继续使用 `uv run python scripts/generate_skill_protocol.py --check`。

4. 清测试事实源：拆除迁移 helper、过期行自动生成、legacy/old/fallback 测试命名，把测试改成当前无效输入或当前行为断言。

5. 处理 release/history 边界：确认日期命名 spec 是否仍承担当前 fact domain 事实源；若不是，停止由发布说明测试读取它。

## 剩余不确定项

- `batch-10-release-build-history-records.md` 的发布说明测试问题需要维护者裁决：该日期设计文档是当前事实源，还是只应作为设计记录保存。
- 多个批次把合法生态版本、OpenAI `/v1`、RPG Maker 版本、字体替换 `old_font_names` 等排除在问题之外；后续清理不要把这些业务合法版本一并删除。
- 部分计划指定 `rg` 命令在 PowerShell 下因通配符未展开出现 Windows 路径错误，子代理均记录原命令失败，并用显式文件列表补跑等价只读检索；本报告将这些视为覆盖完成，而非审计缺口。

## 只读边界声明

本次执行使用子代理并发完成 10 个批次审计，最高并发按用户调整后的上限 6 控制，实际最后一轮并发 4。所有子代理完成后均已关闭释放。

执行前 `git status --short` 已存在以下非本次报告改动，未触碰、未还原、未 stage：

- `M rust/src/native_core/scope_index/mv_virtual_namebox.rs`
- `?? docs/superpowers/plans/2026-06-08-text-fact-v2-parallel-review.md`
- `?? docs/superpowers/plans/2026-06-09-contract-amnesia-review-execution.md`

本次审计创建的文件限定在：

- `docs/records/reviews/contract-amnesia/batches/batch-01-cli-config-runtime.md`
- `docs/records/reviews/contract-amnesia/batches/batch-02-sqlite-persistence.md`
- `docs/records/reviews/contract-amnesia/batches/batch-03-text-fact-index-scope.md`
- `docs/records/reviews/contract-amnesia/batches/batch-04-workspace-rules-agent-toolkit.md`
- `docs/records/reviews/contract-amnesia/batches/batch-05-translation-llm-prompt-quality.md`
- `docs/records/reviews/contract-amnesia/batches/batch-06-writeback-rmmz-file-safety.md`
- `docs/records/reviews/contract-amnesia/batches/batch-07-rust-native-python-adapters.md`
- `docs/records/reviews/contract-amnesia/batches/batch-08-skill-readme-current-docs.md`
- `docs/records/reviews/contract-amnesia/batches/batch-09-tests-fixtures-helpers.md`
- `docs/records/reviews/contract-amnesia/batches/batch-10-release-build-history-records.md`
- `docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md`

执行过的命令类型仅限只读检索、文件读取、报告目录创建、报告自检、`git status --short`、`rg --files` 和 `uv run python scripts/generate_skill_protocol.py --check`。未运行会改变游戏、数据库、运行输出、发行产物或源码状态的命令；未读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。

未执行 `uv run pytest`、`uv run basedpyright`、Rust 格式检查、clippy 或 Rust 测试；本任务是只读 review 报告生成，计划只要求报告生成、Skill 协议生成物检查和 Markdown 工件自检。
