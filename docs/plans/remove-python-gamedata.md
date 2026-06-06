# Python GameData 彻底删除执行计划

> 本计划是源码破坏性迁移执行文档，不是翻译流程 Agent 契约，不覆盖 `AGENTS.md`、Skill、README 或公开 CLI 当前实现。执行会话必须按本文件推进；如执行中发现本文件与当前源码事实冲突，先以当前源码和测试为准定位根因，再同步修正文档和实现。

## 0. 已确认决策

本计划基于用户已确认的硬决策：

| 决策项 | 已选方案 |
| --- | --- |
| 删除强度 | 第一批直接物理删除 Python `GameData`、`load_game_data*`、`TextScopeService`，再同步迁移到全绿 |
| 中间红构建 | 允许执行会话中间长期红；整个计划完成时必须 `basedpyright`、全量 `pytest`、Rust 门禁和真实 CLI 性能证据全绿 |
| 测试代码 | 测试也彻底迁移，不允许继续 import/use Python `GameData` |
| Python 游戏文件读取 | Python 连游戏 JSON 读取都不碰，生产和测试都必须通过 Rust/SQLite/narrow DTO |
| 写回实际应用阶段 | 同批迁 Rust，不允许 Python 依赖 `GameData` 写文件 |
| 规则导出/工作区准备 | 同批迁 Rust/SQLite，不保留 Python `GameData` 候选导出 |
| 源语言探测/add-game | 同批改成 Rust/SQLite/snapshot，不走 Python `GameData` |
| 执行粒度 | 只按 8 个大工程批次推进；严禁拆成大量微批次 |

## 1. 目标

彻底删除 Python 端 `GameData` 聚合模型、加载器和完整文本范围构建器。迁移完成后，生产代码和测试代码中不得继续引用：

- `app.rmmz.schema.GameData`
- `app.rmmz.loader.load_game_data`
- `app.rmmz.loader.load_game_data_for_view`
- `app.rmmz.loader.load_active_runtime_game_data`
- `app.rmmz.loader.GameDataManager`
- `app.text_scope.TextScopeService`
- `app.text_scope.builder.TextScopeService`
- 依赖 Python `GameData` 的旧 workflow gate、候选扫描、规则命中、质量检查、写回探针和写回应用路径

完成后，Python 只保留：

- CLI 参数解析、配置解析、环境变量读取、日志和 Agent JSON 报告组装。
- SQLite 事务、轻量查询和 Rust native DTO 的类型收窄。
- OpenAI 兼容模型调用编排。
- 文件路径和运行目录解析，但不得读取游戏 JSON 内容。

游戏文件读取、source snapshot、源语言探测、文本索引、规则候选、scope hash、workflow gate、质量检查、写回计划和写回应用全部由 Rust/SQLite 接管。

## 2. 非目标

- 不迁移模型调用、OpenAI SDK 调用或 prompt 组装到 Rust。
- 不引入 Python 生产 fallback。
- 不保留“Rust 失败后走 Python `GameData`”的兼容路径。
- 不保留旧 Python 重型扫描作为公共 API。
- 不为了旧数据库或旧规则自动迁移；遇到不兼容状态必须显式失败，并给出重新注册、重建索引或重新导入规则的说明。
- 不提交大样本游戏、性能执行脚本、性能清单或性能报告生成数据；这些只能是执行期临时资产。

## 3. 完成标准

### 3.1 搜索清零

执行完成后，下列命令在 `app/` 和 `tests/` 中不得命中任何生产或测试引用：

```powershell
rg -n "GameData|load_game_data_for_view|load_active_runtime_game_data|load_game_data\(|GameDataManager|TextScopeService|collect_workflow_gate_errors" app tests -g "*.py"
```

允许命中的范围只有：

- 本计划文档。
- 历史记录 `docs/records/` 和 `docs/plans/completed/`。
- changelog 或迁移说明中描述已删除历史的文字。

`app/text_scope/`、`app/rmmz/loader.py` 中相关实现文件应被删除或改名为不含 `GameData` 语义的 Rust DTO 适配层；不得留下可被生产 import 的旧入口。

### 3.2 热路径归零

这些 CLI 不得加载 Python `GameData`，不得构建 Python `TextScopeService`，不得读取游戏 JSON：

- `add-game`
- `probe-source-language`
- `rebuild-text-index`
- `text-scope`
- `audit-coverage`
- `quality-report`
- `export-pending-translations --limit 20`
- `translation-status --refresh-scope`
- `translate --max-items`
- `write-back`
- `rebuild-active-runtime`
- `write-terminology`
- `prepare-agent-workspace`
- `validate-agent-workspace`
- 规则导出、规则导入和规则验证命令
- 插件源码、非标准 data、事件指令、Note 标签、MV 虚拟名字框相关命令
- 源文残留、术语导出/导入和试玩反馈命令

### 3.3 性能回归门槛

大样本真实 CLI 复测必须满足：

- `rebuild-text-index` 不再出现 Python `source_branch_workflow_gate` 级别阶段；如果保留同名字段，值必须为 `0` 或 SQLite 小查询级。
- Rust 冷重建不得因为存在一条插件源码规则而读取整个插件源码目录；只能读取规则引用的插件文件和必要的 `plugins.js` 配置。
- 所有非网络本地阶段必须相对迁 Rust 前基线达到 80%-90% 提速；若低于 80%，计划不能完成。
- 网络/模型等待不计入性能目标，但模型调用前后本地阶段计入。

### 3.4 质量门禁

最终必须通过：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
git diff --check
```

并执行文档敏感路径、临时资产、旧入口残留搜索：

```powershell
$patterns = @(
  "C:" + "\\Users",
  "夜" + "袭",
  "pytest" + "-of-",
  "att-mz-cli-" + "perf",
  "benchmark " + "runner",
  "perf " + "manifest",
  "TO" + "DO",
  "TB" + "D",
  "临时" + "测试",
  "temporary " + "test"
)
$pattern = ($patterns | ForEach-Object { [regex]::Escape($_) }) -join "|"
rg -n $pattern docs skills README.md app tests -g "*.md" -g "*.py" -g "*.toml"
rg -n "GameData|load_game_data_for_view|load_active_runtime_game_data|load_game_data\(|GameDataManager|TextScopeService|collect_workflow_gate_errors" app tests -g "*.py"
```

## 4. 当前待删除入口清单

执行前先用 `rg` 重新生成清单。当前已知核心定义点：

| 文件 | 当前职责 | 迁移结果 |
| --- | --- | --- |
| `app/rmmz/schema.py` | 定义 `GameData` 聚合模型 | 删除 `GameData`；保留独立记录类型时不得再聚合整游戏 |
| `app/rmmz/loader.py` | Python 游戏文件加载器、`load_game_data*`、`GameDataManager` | 删除文件或拆到只含路径解析的模块；不得读取游戏 JSON |
| `app/text_scope/builder.py` | `TextScopeService.build()` 完整文本范围构建 | 删除生产入口；文本范围只来自 Rust text index |
| `app/application/flow_gate.py` | 旧完整 workflow gate | 删除 `collect_workflow_gate_errors`；保留 indexed/Rust gate 聚合 |
| `app/application/handler.py` | CLI 应用编排，多处加载 GameData | 改为 Rust native / SQLite DTO |
| `app/agent_toolkit/services/core.py` | `_load_*_game_data` 门面 | 删除这些方法和协议声明 |
| `app/agent_toolkit/services/common.py` | 大量 `GameData` helper 和协议导出 | 分批删除或迁移到 Rust DTO helper |
| `app/agent_toolkit/services/text_index.py` | 冷重建后仍可进入完整 workflow gate | 删除完整 gate，Rust rebuild 写入完整 gate metadata |
| `app/agent_toolkit/services/workspace.py` | 工作区候选导出依赖 GameData | 迁到 Rust candidates / SQLite index |
| `app/agent_toolkit/services/quality.py` | active runtime、插件源码、写回协议部分仍依赖 GameData | 迁 Rust runtime audit / write gate DTO |
| `app/native_scope_index.py` | 一些 payload builder 从 GameData 构造 Rust 输入 | 改为 Rust 直读文件或 SQLite 输入，不由 Python 组装整游戏 JSON |
| `app/rmmz/commands.py` | 从 GameData 遍历事件命令 | 删除或改为 Rust 命令迭代 |
| `app/plugin_text/*` | 插件规则导出/校验依赖 GameData | 迁 Rust plugin config reader |
| `app/plugin_source_text/*` | 插件源码扫描/规则/运行审计依赖 GameData | 迁 Rust source/runtime reader 和 AST DTO |
| `app/nonstandard_data/*` | 非标准 data 提取依赖 GameData | 迁 Rust JSON leaves/index |
| `app/event_command_text/*` | 事件指令导出/校验/提取依赖 GameData | 迁 Rust event command candidates |
| `app/note_tag_text/*` | Note 标签导出/校验/提取依赖 GameData | 迁 Rust note tag candidates |
| `app/rmmz/mv_namebox*.py` | MV 虚拟名字框候选依赖 GameData | 迁 Rust MV namebox scan |
| `app/terminology/*` | 术语导出/字段表校验依赖 GameData | 迁 Rust terminology context DTO |
| `app/application/font_replacement/*` | 字体替换读取 GameData | 迁 Rust manifest/write apply DTO |
| `tests/agent_toolkit_contract_fixtures.py` | 测试夹具构建 GameData/TextScope | 改为生成游戏目录后走 CLI/Rust/SQLite |
| `tests/rmmz_writeback_contract_fixtures.py` | 写回夹具依赖 GameData/TextScope | 改为 Rust write plan/apply fixture |

## 5. 新架构边界

### 5.1 Rust native 入口族

Rust native 必须提供下列能力。入口名可按现有 native contract 风格命名，但能力边界必须完整：

| Rust 能力 | 输入 | 输出 | 用途 |
| --- | --- | --- | --- |
| 游戏 manifest / source snapshot 建立 | `game_path`、source view | 标准 data、插件配置、插件源码、字节大小、hash、引擎类型、游戏标题 | `add-game`、重建索引、写回校验 |
| 源语言探测 | `game_path` | 样本、置信度、建议源语言、可行动错误 | `probe-source-language` |
| text index rebuild | `db_path`、`game_path`、配置 DTO、规则表 | text index rows、scope summary、domain summary、gate metadata | `rebuild-text-index` 和自动重建 |
| external rule candidates | `db_path`、`game_path`、配置 DTO、候选类型 | 插件参数、事件指令、Note、MV 名字框、插件源码、非标准 data 候选 JSON | 规则导出、工作区准备、导入验证 |
| workflow gate metadata | `db_path`、`game_path`、配置 DTO、规则表 | 空规则 scope hash、stale rule errors、precheck flags | 翻译、质量、写回前置检查 |
| quality/report gate | `db_path`、配置 DTO、source residual rules | counts、details、blocking errors | `quality-report` |
| runtime audit | `db_path`、`game_path`、runtime view | active runtime audit、write map diagnostics | `audit-active-runtime`、`diagnose-active-runtime` |
| write plan + apply | `db_path`、`game_path`、配置 DTO、mode | 写回计划、事务变更、运行摘要 | `write-back`、`rebuild-active-runtime`、`write-terminology` |
| terminology context | `db_path`、`game_path`、配置 DTO | 字段表、系统术语、角色/地图/数据库上下文 | 术语导出/导入校验、prompt 术语裁剪 |

### 5.2 Python 允许职责

Python 允许做：

- 组装 CLI 入参为 Rust payload。
- 读取 SQLite 小结果。
- 把 Rust JSON DTO 转成 `AgentReport`。
- 管理模型请求、重试、批次保存。
- 管理配置和环境变量。

Python 不允许做：

- 读取 `data/*.json`、`www/data/*.json`、`js/plugins.js`、`js/plugins/*.js` 的内容。
- 聚合整游戏数据对象。
- 遍历所有事件命令、Note、插件参数、插件源码、非标准 data。
- 构造完整文本范围。
- 执行写回文件内容修改。

## 6. 执行批次

只允许按以下 8 个工程批次推进。执行期间可以红构建，但每个批次结束必须记录当前红/绿状态、剩余错误数量、真实 CLI 性能证据和下一批接力点。第 8 批结束必须全绿。

### 批次 1：物理删除 Python GameData 和 TextScope 入口

目标：第一刀删除旧主路径，让所有残留编译错误显性暴露。

必须执行：

1. 删除 `app.rmmz.schema.GameData`。
2. 删除 `app/rmmz/loader.py` 中 `load_game_data`、`load_game_data_for_view`、`load_active_runtime_game_data`、`GameDataManager`。
3. 删除 `app/text_scope/builder.py::TextScopeService`，并从 `app/text_scope/__init__.py` 移除导出。
4. 删除 `app/application/flow_gate.py::collect_workflow_gate_errors`。
5. 删除 `app/agent_toolkit/services/core.py` 和 `common.py` 中 `_load_*_game_data` 协议和导出。
6. 运行 `uv run basedpyright`，保存错误清单作为迁移 inventory。
7. 用 `rg` 生成所有残留引用列表，按模块归入批次 2-7。

批次结束标准：

- 旧入口物理不存在。
- 不允许因为错误多而恢复旧入口。
- 文档记录当前 `basedpyright` 错误数量和最高频残留模块。

### 批次 2：Rust 游戏 manifest、source snapshot、add-game、源语言探测

目标：替代 Python 游戏加载器的基础 I/O 能力。

必须执行：

1. Rust 新增或扩展 manifest reader，直读游戏目录并识别 MV/MZ 布局。
2. Rust 生成 source snapshot 文件清单、hash、byte size、插件配置和插件源码 manifest。
3. Rust 实现源语言探测 raw sampler，不经过 Python JSON 读取。
4. `add-game` 改为调用 Rust manifest/snapshot。
5. `probe-source-language` 改为调用 Rust source-language probe。
6. 删除 Python 侧 source snapshot 构建中读取游戏 JSON 的逻辑。
7. 迁移对应测试夹具，测试只能生成文件目录，不能调用 Python `load_game_data`。

验证命令：

```powershell
uv run pytest tests/test_rmmz_source_snapshot.py tests/test_source_language_probe.py tests/test_stage0_canaries.py
uv run basedpyright
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

### 批次 3：Rust text index rebuild 成为唯一文本范围事实源

目标：`rebuild-text-index` 不再触发 Python workflow gate 或任何游戏数据读取。

必须执行：

1. Rust rebuild 一次写入 text index rows、scope summary、domain summary、rule hit summary。
2. Rust rebuild 写入 external rule gate scope hash。
3. Rust rebuild 写入插件源码和非标准 data source branch precheck metadata。
4. Rust 插件源码规则只读取规则引用文件，不读取整个插件源码目录。
5. Python `rebuild-text-index` 删除完整 gate 分支，只读取 Rust/SQLite summary。
6. `source_branch_workflow_gate` 删除或固定为 `0`；文档和测试同步。
7. 增加大样本生成式测试：无关巨大插件源码文件不得被读取。

验证命令：

```powershell
uv run pytest tests/test_text_index.py tests/test_scan_budget.py
uv run basedpyright
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

真实 CLI 必测：

```powershell
uv run python main.py rebuild-text-index --game <临时大样本游戏标题> --output <临时报告路径>
uv run python main.py text-scope --game <临时大样本游戏标题> --output <临时报告路径>
uv run python main.py audit-coverage --game <临时大样本游戏标题> --output <临时报告路径>
```

临时大样本目录必须创建在系统临时目录，并在脚本 `finally` 删除。

### 批次 4：规则候选、规则导出、规则导入验证迁 Rust

目标：所有规则命令不再依赖 Python `GameData`。

必须迁移：

- `export-plugins-json`
- `validate-plugin-rules`
- `import-plugin-rules`
- `export-event-commands-json`
- `validate-event-command-rules`
- `import-event-command-rules`
- `export-note-tag-candidates`
- `validate-note-tag-rules`
- `import-note-tag-rules`
- `export-mv-namebox-candidates`
- `validate-mv-namebox-rules`
- `import-mv-namebox-rules`
- `scan-plugin-source-text`
- `export-plugin-source-ast-map`
- `validate-plugin-source-rules`
- `import-plugin-source-rules`
- `scan-nonstandard-data`
- `validate-nonstandard-data-rules`
- `import-nonstandard-data-rules`

必须执行：

1. Rust candidates API 直读游戏目录和规则表。
2. Python 只保存 Rust 返回的候选 JSON 和导入记录。
3. 删除 `app/plugin_text/*`、`app/event_command_text/*`、`app/note_tag_text/*`、`app/plugin_source_text/*`、`app/nonstandard_data/*` 中依赖 `GameData` 的生产函数。
4. 测试迁移到 CLI/Rust DTO，不允许直接构造 Python `GameData`。

验证命令：

```powershell
uv run pytest tests/test_agent_toolkit_rule_import.py tests/test_plugin_text.py tests/test_event_command_text.py tests/test_plugin_source_text.py tests/test_nonstandard_data.py tests/test_rmmz_mv_namebox.py tests/test_rmmz_note_nonstandard_data.py
uv run basedpyright
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

### 批次 5：工作区、占位符、术语、源文残留迁 Rust/SQLite

目标：工作区准备和辅助规则命令不再读取 Python 游戏数据。

必须迁移：

- `prepare-agent-workspace`
- `validate-agent-workspace`
- `scan-placeholder-candidates`
- `build-placeholder-rules`
- `validate-placeholder-rules`
- `import-placeholder-rules`
- `scan-structured-placeholder-candidates`
- `validate-structured-placeholder-rules`
- `import-structured-placeholder-rules`
- `export-terminology`
- `import-terminology`
- `validate-source-residual-rules`
- `import-source-residual-rules`

必须执行：

1. 工作区 manifest、候选文件、规则文件都从 Rust candidates / SQLite text index 生成。
2. 术语字段表、系统词、角色/地图上下文由 Rust terminology context DTO 提供。
3. 占位符候选只读 text index entries 或 Rust candidate details。
4. 源文残留规则只读 text index 和 Rust validation result。
5. 删除 Python `GameData` helper 和测试 fixture 中的 scope 构建。

验证命令：

```powershell
uv run pytest tests/test_agent_toolkit_workspace.py tests/test_agent_toolkit_manual_import.py tests/test_terminology.py tests/test_text_rules.py tests/test_workspace_manifest.py
uv run basedpyright
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

### 批次 6：质量、覆盖、翻译前置、反馈诊断迁 Rust/SQLite

目标：模型调用前后本地阶段不再回到 Python 游戏数据或旧 scope。

必须迁移：

- `quality-report`
- `audit-coverage`
- `text-scope`
- `export-pending-translations`
- `translation-status --refresh-scope`
- `translate --max-items` 前置 gate
- `import-manual-translations`
- `export-quality-fix-template`
- `import-quality-fixes`
- `verify-feedback-text`
- `audit-active-runtime`
- `diagnose-active-runtime`

必须执行：

1. 质量检查只消费 SQLite text index、译文表、Rust quality result。
2. 覆盖和文本范围只读 SQLite summary 和 sampled details。
3. 翻译 pending 只走 SQL limit，不构建完整范围。
4. 反馈诊断和 active runtime audit 由 Rust runtime DTO 提供。
5. 删除 `app/application/flow_gate.py` 中剩余依赖 Python game data 的 gate helper。
6. 删除 `app/agent_toolkit/services/common.py` 中旧 `GameData` 导出和 helper。

验证命令：

```powershell
uv run pytest tests/test_agent_toolkit_coverage.py tests/test_agent_toolkit_quality_report.py tests/test_agent_toolkit_workflow_gate.py tests/test_agent_toolkit_feedback.py tests/test_translation_run_limits.py tests/test_translation_cache_context.py tests/test_manual_translation_scope.py tests/test_scan_budget.py
uv run basedpyright
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

### 批次 7：写回计划、写回应用、字体替换、runtime 重建全 Rust 化

目标：写文件阶段也不再依赖 Python `GameData`。

必须迁移：

- `write-back`
- `rebuild-active-runtime`
- `write-terminology`
- 字体替换和字体恢复
- 写回前 source snapshot 校验
- 写回事务应用
- 写回后审计

必须执行：

1. Rust write plan 直接读取 active runtime / translation source view。
2. Rust apply 在事务目录中写文件，并返回变更摘要。
3. Python 只展示摘要和处理错误码。
4. 删除 `app/rmmz/extraction.py`、`app/rmmz/write_*`、`app/application/font_replacement/*` 中所有 Python `GameData` 依赖。
5. 测试 fixture 改为通过 CLI 或 Rust DTO 写入，不再构造 Python game model。

验证命令：

```powershell
uv run pytest tests/test_rmmz_write_plan.py tests/test_write_back_transactions.py tests/test_rmmz_file_transaction.py tests/test_rmmz_font_transaction.py tests/test_rmmz_post_write_audit.py tests/test_font_replacement_transactions.py
uv run basedpyright
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

### 批次 8：全仓清零、文档同步、大样本性能验收

目标：删除残留文件、清理测试、完成文档和性能验收。

必须执行：

1. 删除所有未被生产和测试引用的旧 Python模块。
2. 确认 `app/` 和 `tests/` 对 `GameData`、`load_game_data*`、`TextScopeService`、`collect_workflow_gate_errors` 搜索清零。
3. 更新 `docs/wiki/development/*.md`，把当前实现改成 Rust/SQLite/narrow DTO；不能写历史回忆。
4. 更新 README、Skill、CLI command contract 中涉及扫描、写回、质量和性能语义的描述。
5. 清理 scan budget 表，所有命令 `GameData` load budget 归零。
6. 跑真实大样本 CLI 性能复测。
7. 删除执行期临时性能脚本、runner、manifest、夹具和生成数据。

最终验证命令：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
rg -n "GameData|load_game_data_for_view|load_active_runtime_game_data|load_game_data\(|GameDataManager|TextScopeService|collect_workflow_gate_errors" app tests -g "*.py"
$patterns = @(
  "C:" + "\\Users",
  "夜" + "袭",
  "pytest" + "-of-",
  "att-mz-cli-" + "perf",
  "benchmark " + "runner",
  "perf " + "manifest",
  "TO" + "DO",
  "TB" + "D",
  "临时" + "测试",
  "temporary " + "test"
)
$pattern = ($patterns | ForEach-Object { [regex]::Escape($_) }) -join "|"
rg -n $pattern docs skills README.md app tests -g "*.md" -g "*.py" -g "*.toml"
git diff --check
```

## 7. 大样本性能测试要求

执行期必须生成临时大样本，不能提交到仓库。

大样本至少包含：

- 1000 个 map 文件。
- 50000 条以上事件正文。
- 300 个插件源码文件。
- 至少 2 个插件源码规则，其中只有规则引用文件允许被 Rust rebuild 读取。
- 至少 5 个非标准 data 文件，总计 10000 条以上 JSON leaf。
- 已保存译文和 pending 译文混合数据。

必须验证这些命令：

```powershell
add-game
probe-source-language
rebuild-text-index
text-scope
audit-coverage
quality-report
export-pending-translations --limit 20
translation-status --refresh-scope
translate --max-items 20 --max-batches 1
write-back
rebuild-active-runtime
scan-plugin-source-text
scan-nonstandard-data
prepare-agent-workspace
```

性能报告必须列出：

- wall time。
- CLI JSON `elapsed_ms`。
- `stage_timings`。
- Rust `native_thread_count`。
- 每条命令是否读取 Python 游戏数据，必须为否。
- 每条命令是否构建 Python text scope，必须为否。
- 临时目录删除结果。

## 8. 执行纪律

- 允许中间红，但每轮提交给用户的状态必须诚实列出当前红点和下一批接力点。
- 不允许恢复 Python `GameData` 或 `TextScopeService` 来让测试暂时变绿。
- 不允许新增生产 fallback。
- 不允许用 mock 成功掩盖 Rust 迁移缺口。
- 不允许把大样本、runner、manifest、benchmark 输出提交到仓库。
- 每批必须给出真实 CLI 性能证据；不能只引用 scan budget 表。
- 如果第 8 批结束仍未清零，必须停止继续施工，提交失控复盘和重新压缩方案。

## 9. 新会话执行提示词

新会话可以直接使用：

```text
/goal @superpowers
你要执行 att-mz 的“Python GameData 彻底删除”破坏性迁移计划。

先完整阅读：
- AGENTS.md
- docs/plans/README.md
- docs/plans/remove-python-gamedata.md

严格按 docs/plans/remove-python-gamedata.md 的 8 个工程批次推进。

硬要求：
- 第一批直接物理删除 Python GameData、load_game_data*、GameDataManager、TextScopeService 和 collect_workflow_gate_errors。
- 允许执行中间长期红，但不得恢复旧入口求绿。
- 生产代码和测试代码最终都不得 import/use GameData 或 Python 游戏加载器。
- Python 不允许读取游戏 JSON；游戏文件读取、扫描、候选、写回全部迁 Rust/SQLite/narrow DTO。
- 不保留 Python fallback。
- 每批必须给出真实 CLI 性能证据。
- 临时性能脚本、runner、manifest、夹具和生成数据必须在执行期删除。
- 第 8 批结束必须 basedpyright、全量 pytest、Rust 门禁、旧入口搜索、临时资产搜索和 git diff --check 全绿。

交付格式：
- 本批完成了什么
- 当前红/绿状态
- 删除/迁移范围
- 性能结果和瓶颈归因
- 验证命令与结果
- 未验证范围和风险
- 下一批建议
```
