# 契约失忆化破坏性清理设计

## 背景

`docs/records/reviews/contract-amnesia/contract-amnesia-review-final-report.md` 已完成一次只读专项 review。报告确认当前项目仍有 P0/P1/P2 问题：历史形态进入运行时分支、SQLite schema 和 API 命名、用户错误文案、README/Skill 当前契约、测试 helper 与测试命名。

本设计用于后续破坏性清理。它不追求兼容历史输入，不提供迁移路线，也不通过“识别历史形态并拒绝它”来证明清理完成。目标是让当前系统只表达当前契约；不符合当前契约的输入就是普通无效输入。

## 核心目标

完成一次贯穿 Python、Rust、SQLite、Skill、README、docs 和 tests 的契约失忆化清理：

- 当前正式命名不再使用 `v2` 表达业务契约。
- 当前运行时不再识别、解释、迁就或展示历史形态。
- 当前错误文案只说明当前要求、当前问题和下一步当前修正动作。
- 当前测试只固定当前成功行为和当前无效输入失败行为。
- 当前 README、docs、Skill 只描述当前流程，不解释历史形态。

## 最高优先级原则：禁止反向记忆

修复不得制造新的历史记忆。

禁止以下套娃式修复：

- 为删除历史环境变量识别，又新增历史环境变量识别测试。
- 为删除历史 schema 或历史输入，又新增专门构造历史形态的 helper。
- 为证明历史 loader、fallback、adapter 被删除，又在当前测试中固定这些历史入口名称。
- 为证明某个历史字段不再支持，又在当前 README、Skill、错误文案或 JSON 报告中解释该历史字段。
- 为防止回退，新增 `legacy`、`old`、`fallback`、`compat`、`旧`、`迁移`、`回退`、`v2` 等历史哨兵命名。

验收标准不是“历史形态会被识别并拒绝”，而是：

- 当前契约定义清楚。
- 当前有效输入通过。
- 缺少当前必需字段、类型不符、schema 不满足当前要求、索引缺当前必需定位信息等非当前输入自然失败。
- 代码、测试、文档和 Skill 不需要知道非当前输入过去叫什么。

## 非目标

- 不保留旧数据库、旧工作区、旧运行映射、旧环境变量、旧测试输入或旧 helper 的兼容层。
- 不提供迁移命令。
- 不新建迁移指南。
- 不把历史说明写入 README、docs/wiki、docs/guides、Skill、CLI/help/error 文案、JSON 报告字段说明或测试事实源。
- 不清理合法的软件生态版本，例如依赖版本、项目发布号、OpenAI 兼容接口 `/v1`、RPG Maker 引擎版本或字体替换业务字段。

历史说明只允许保留在：

- `CHANGELOG.md`
- GitHub Release 正文或发布说明
- `docs/records/`
- 明确归档性质、不会被当前流程当作事实源的记录目录

## 当前契约命名

当前正式业务命名必须去版本化。

需要统一收束的对象包括：

- SQLite 表名与索引名：`text_facts_v2`、`text_fact_scope_v2` 等改为当前无版本名称。
- Python/Rust 常量：`TEXT_FACT_SCHEMA_VERSION` 一类名称若继续存在，只能表示内部 schema 完整性校验，不能作为业务契约名或用户文案。
- Python/Rust 类型、函数和模块边界：`TextFactV2Record`、`v2 fact identity` 等当前正式类型与说明改为无版本名称。
- README、docs、Skill、CLI/help/error 文案和 JSON 报告说明不再把 `Text Fact Contract v2`、`v2 facts` 作为当前概念。
- 测试名、docstring、fixture、helper 和断言文案不再用 `v2` 表达当前业务对象。

允许保留的版本概念只有两类：

- 当前 schema 完整性校验所需的内部数值字段，例如数据库 `schema_version`。
- 合法生态版本，例如依赖版本、发行版本、外部 API 版本和 RPG Maker 引擎版本。

这些版本概念不得进入当前用户文案，也不得成为业务对象名称。

## 运行时清理边界

运行时代码只接受当前契约输入。非当前输入按普通无效输入处理。

必须删除或重塑的边界：

- 配置加载只读取当前 `ATT_MZ_*` 配置入口；删除历史环境变量前缀收集、格式化错误和专门拒绝逻辑。
- RMMZ 数据加载必须显式区分当前翻译来源文件和当前运行文件；删除或重塑 `load_game_data()` 的兼容完整加载语义，禁止缺可信源快照时回退读取当前运行文件。
- 翻译模型响应 ID 只接受当前字符串 ID；删除数字 ID 转字符串匹配路径。
- native 契约校验只表达“不满足当前 Python/Rust 契约”；不说扩展过旧。
- Rust schema 校验只表达“当前数据库结构不满足要求”；不说迁移数据库。
- Text Fact 到翻译输入、质量检查和写回计划的转换必须要求当前索引定位信息存在；缺失时按当前契约错误失败。
- legacy scope helper、旧报告同形 adapter、历史包级导出、旧调用点参数等如果没有当前职责，直接删除；如果仍有当前职责，改成当前命名和当前说明。

## 错误文案规则

错误文案只回答三件事：

1. 当前缺什么。
2. 当前为什么不能继续。
3. 下一步如何重新生成或修正当前数据。

错误文案禁止：

- 解释历史形态。
- 展示历史名称。
- 使用历史修复动作。
- 暗示系统识别了某个历史输入。

禁止出现在当前错误文案中的表达包括：

- `legacy`
- `old`
- `fallback`
- `compat`
- `deprecated`
- `旧`
- `旧版`
- `历史`
- `迁移`
- `兼容`
- `回退`
- `过旧`
- `旧索引正文`
- `旧工作区`
- `旧数据库`
- `旧 runtime map`

示例口径：

- 使用“当前文本事实与当前文本索引不一致，不能继续执行；请重新生成当前文本索引”。
- 不使用“不能继续使用旧索引正文”。
- 使用“Rust 原生扩展不满足当前 Python 契约，请重新构建原生扩展”。
- 不使用“Rust 原生扩展版本过旧”。

## 测试设计规则

测试必须证明当前契约，而不是证明历史形态被识别。

应该覆盖：

- 当前配置字段和环境变量覆盖成功。
- 未知配置字段失败。
- 当前必需字段缺失失败。
- 当前响应字段类型不符失败。
- 当前 schema 不满足要求失败。
- 当前索引缺必需 locator 或 fact 身份不一致失败。
- 当前唯一事实源、唯一 loader 或唯一 native 路径被使用。

不应该覆盖：

- 历史环境变量会失败。
- 历史 schema 会失败。
- 历史 loader 不会被调用。
- 历史 helper 不会被调用。
- 历史输入被拒绝。
- 某个历史名称不再出现。

测试 helper 规则：

- 普通 helper 只构造当前有效对象。
- 无效输入 fixture 必须使用中性当前语言命名，例如 `missing_required_field`、`invalid_schema_shape`、`mismatched_scope_hash`。
- 不允许普通 helper 自动迁移输入、自动生成过期记录或自动补历史形态。
- 需要测试当前无效状态时，必须使用显式专用 fixture，不能复用正常写入 helper。
- 测试中的禁止调用断言应表达当前唯一入口，例如“只调用 Rust scope index 输出”，不表达“没有调用旧 Python fallback”。

## 文档与 Skill 边界

当前事实源只描述当前流程。

需要清理的当前事实源包括：

- `README.md`
- `docs/wiki/`
- `docs/guides/`
- `skills/att-mz-protocol/`
- `skills/att-mz/`
- `skills/att-mz-release/`
- CLI/help/error 文案
- JSON 报告字段说明
- 测试名、docstring、fixture/helper 命名

Skill 修改流程：

1. 优先修改 `skills/att-mz-protocol/` canonical 源。
2. 通过项目生成脚本刷新开发版和发行版 Skill。
3. 使用生成物检查确认没有漂移。

README 和 docs 只描述当前命令、当前输入要求、当前失败原因和当前修正动作。历史说明不进入当前用户指南。

## 发布与历史记录边界

不新建迁移指南。

如果需要向真实用户说明破坏性变化，只写入：

- `CHANGELOG.md`
- GitHub Release 正文
- 发布说明

这些说明必须保持具体，但不能被 README、Skill、CLI 或测试引用为当前事实源。

`docs/records/` 可以保存 review 报告、执行记录和历史判断，但后续测试不能把日期命名设计文档或 review 记录当作当前业务契约来源。

## 清理阶段

后续 implementation plan 应按以下阶段拆分：

1. P0 运行时清理：配置、LLM 响应 ID、RMMZ loader、native 契约、Rust schema 错误、Text Fact 缺 locator 失败、旧索引正文文案。
2. schema/API 命名清理：SQLite DDL、Python/Rust SQL、类型、常量、函数、错误码和报告字段同步去版本化。
3. adapter/helper 删除：legacy scope helper、旧报告同形 adapter、历史包级导出、旧调用点参数、测试迁移 helper 和自动过期记录生成。
4. README/docs/Skill 清理：先 canonical，后生成物，再 README/docs/guides。
5. 测试重塑：改为当前契约测试，删除历史哨兵和历史 fixture。
6. 发布说明更新：只在允许的历史记录位置说明破坏性变化。

## 验收标准

实现完成后必须满足：

- 当前正式业务命名不再使用 `v2`。
- 当前运行时不再识别历史形态作为专门分支。
- 当前错误文案不出现禁止词和历史对象。
- 当前 README、docs、Skill 不解释历史形态。
- 当前测试不通过历史哨兵、历史 helper 或历史 fixture 固定修复。
- 普通 helper 不自动迁移输入或生成过期记录。
- Skill canonical 与生成物一致。
- release/history 记录不反向成为当前事实源。

必须执行的验证：

- `uv run basedpyright`
- `uv run pytest`
- 修改 Rust 时执行 Rust 格式检查、clippy 和 Rust 测试。
- 修改 Skill 时执行 `uv run python scripts/generate_skill_protocol.py --check`。
- 针对文案和测试命名执行关键词审计，确认当前事实源中没有新增历史哨兵。

关键词审计不得变成新的历史哨兵测试。它只作为交付前静态审查，不进入运行时代码和业务测试模型。

## 风险与处理

### 大范围重命名风险

去版本化会触及 Python、Rust、SQLite 和测试。实现计划必须先梳理事实源和调用面，再按阶段修改，避免 Python/Rust/schema 三边短暂不一致。

### 测试短期变动风险

删除历史 helper 会让大量测试需要重写。应先建立当前有效 fixture，再迁移调用方，最后删除历史 helper。

### 用户升级体验风险

不提供迁移命令会让不符合当前契约的数据必须重新注册、重新导入规则、重建索引或重新准备工作区。错误文案必须给出这些当前动作，但不能解释历史形态。

### 误删合法版本风险

依赖版本、项目发布号、OpenAI 兼容接口 `/v1`、RPG Maker 引擎版本和字体替换业务字段不是本次清理对象。关键词审计命中这些内容时必须按合法当前概念处理。

## 成功状态

本设计完成后的成功状态是：

- 当前系统只表达当前契约。
- 非当前输入按普通无效输入失败。
- 代码、测试、文档和 Skill 不再需要知道非当前输入过去叫什么。
- 历史说明只留在允许的历史记录位置。
- 后续维护者可以从当前源码、schema、Skill 和测试直接理解当前模型，而不会被历史名称牵引。
