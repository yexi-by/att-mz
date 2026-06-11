# 半迁移与无迁移并发 Review 设计

## 背景

现有并发 review 文档已经能检查双事实源、Rust 主路径缺口、旧路径残留和性能风险，但本次 PCRE2 统一规则运行时暴露出一个更隐蔽的问题：代码、API、测试和文档都可能表现为“已经迁移”，真实生产副作用却仍由旧侧完成，或者根本没有接入生产链路。

典型现象是 `commit_rule_import` 这样的新 API 已经存在并被调用，但它没有真正写 SQLite、没有形成事务边界，也没有调用 Rust store；真实写库仍由 Python persistence 完成。普通 review 容易把“调用到了 Rust”误判为“Rust 已经接管”。本设计专门用于审查这种半迁移、无迁移、空门面、伪删除和假成功测试。

本设计不是之前并发 review 文档的替代品，而是更窄、更硬的一类专项 review。它不问“有没有 Rust 代码”，而问“声明由 Rust 接管的生产事实、生产副作用和用户可见结果，是否真的由 Rust 当前主路径完成”。

## 核心目标

- 建立一套多子代理并发 review 规格，专门检查半迁移、无迁移、伪删除、空门面和假成功测试。
- 强制把 spec、plan、提交信息、API 命名、测试名和文档里的“迁移声明”追到真实生产调用链。
- 强制把真实副作用归属查清楚，包括数据库写入、备份、清理、索引、缓存、报告、写回和事务边界。
- 防止“新模块存在但生产未接”、“native API 返回成功但没有完成承诺”、“旧代码不调用但未物理删除”被误认为完成。
- 为 PCRE2 统一规则运行时提供一次有意义的后置 review 规格，并作为后续 Rust 主路径迁移的专项审查模板。

## 非目标

- 本 spec 不修复代码。
- 本 spec 不规定具体实现任务顺序。
- 本 spec 不替代 PCRE2 规则运行时设计和实现计划。
- 本 spec 不要求为旧规则、旧表、旧测试、旧正则 dialect 或旧 API 提供兼容。
- 本 spec 不把“新增 guard 防止旧路径被调用”视为物理删除的替代方案。

## 定义

### 已完成迁移

满足以下条件才算已完成迁移：

- 迁移声明中的 owner 和真实生产 owner 一致。
- CLI 或生产服务链路已经接到新 owner。
- 核心副作用由新 owner 完成。
- 旧 owner 的同功能生产路径、测试依赖、fixture 依赖和 public re-export 已物理删除或降级到明确非核心边界。
- 测试验证真实副作用和用户可见结果，而不是只验证新 API 返回成功。

### 半迁移

半迁移指新门面、新 API、新模块、新命名或新测试已经存在，生产链路也可能调用到新侧，但核心行为仍由旧侧、旁路侧或另一个事实源完成。

典型信号：

- 新 API 被调用，但只做参数校验、token 校验或返回 report。
- 函数名包含 `commit`、`store`、`write`、`import`、`apply`，实际没有完成对应副作用。
- Rust store、adapter、scanner 已存在，但生产路径仍由 Python 直接写库、扫描、匹配或解释。
- Python 先完成真实写入，Rust 后置返回成功。
- 旧代码入口被 `raise`、guard 或 scan budget 拦住，但旧实现本体仍保留。
- 测试只验证 native success，不验证数据库、文件、索引、报告或写回状态。

### 无迁移

无迁移指文档、计划、提交信息、API 名称或测试声称已经迁移，但真实生产路径没有切到新实现。

典型信号：

- Rust 模块新增了，但 CLI/service/native adapter 没有调用。
- 新 schema 新表存在，但生产读写仍走旧表、旧 Python persistence 或旧 cache。
- 新 Rust 测试只覆盖孤立函数，不覆盖真实命令链路。
- 旧 Python scanner、matcher、validator、quality check 或 writer 仍是唯一生产消费者。
- README、Skill 或错误文案描述新契约，但真实命令仍按旧契约运行。

### 伪删除

伪删除指旧实现从主路径上看似不可达，但没有被仓库物理删除，或测试、fixture、stub、scan budget、canary、re-export 仍依赖它。

典型信号：

- 文件还在，只是函数开头 `raise`。
- Rust 代码加了 `#![allow(dead_code)]` 或 Python 入口没人调，但测试仍引用。
- 旧测试改名成当前测试，但断言仍表达旧契约。
- 旧 dialect、旧字段、旧表、旧 helper 仍出现在当前测试和示例中。
- 旧路径只在 docs/records 历史文件外的当前源码、测试、README、Skill 或配置模板中出现。

### 空门面

空门面指 API、类型、模块或报告字段名称承诺了生产行为，但实现没有完成承诺的行为。

典型信号：

- `commit_*` 不提交。
- `store_*` 不写 store。
- `validate_*` 和 `import_*` 名义共用 prepare，实际走不同语义。
- `fingerprint` 没覆盖真实影响运行的输入。
- `report` 声称写入、清理或确认成功，但没有真实状态变化证据。

### 假成功测试

假成功测试指测试通过只证明“新函数能返回成功”，不能证明迁移真实完成。

典型信号：

- 只断言 `ok == true`、`status == success`、错误码为空。
- 不打开 SQLite 验证表内容。
- 不检查旧侧函数未被生产调用。
- 不验证事务失败不会留下半状态。
- 不验证 CLI 用户路径的最终 JSON、报告、写回或缓存状态。

## 硬约束

### 真实副作用优先

review 必须优先追踪真实副作用。名称、模块边界、测试名和文档都只能作为线索，不能作为迁移完成证据。

必须追踪的副作用包括：

- SQLite 写入、删除、替换、事务提交和回滚。
- 备份文件写入和备份失败处理。
- 文本索引、规则 store、domain state、fingerprint 和 metadata 更新。
- 缓存命中、fast path 跳过条件和 stale 判定。
- 写回计划、写回文件内容和清理结果。
- 用户可见 JSON 报告、错误码、日志摘要和下一步提示。

### 生产链路优先

孤立 Rust 测试、孤立 Python 单元测试和工具函数测试不能证明迁移完成。review 必须从当前 CLI、Agent service、native adapter 或发行入口追到最终副作用。

### 旧代码物理删除

如果迁移声明是“最终状态”“已接管”“不兼容旧形态”或“旧路径删除”，则旧代码、旧测试、旧 fixture、旧 helper、旧 re-export 和旧示例必须物理删除。`raise`、`allow(dead_code)`、注释说明、scan budget 禁止项和未调用状态都不能替代删除。

### 无迁移按失败处理

新增代码没有进入生产链路，不算低风险准备工作。只要文档、计划、提交信息、测试名或 API 命名声称迁移完成，而真实生产路径没接入，就按 review failure 处理。

### 半迁移按 P1 起步

声明主路径已经切到 Rust/native/current model，但真实副作用仍由 Python、旧表、旧 helper、旁路 store 或空门面完成，默认至少 P1。若会导致半提交、错误清理、错误写回或数据破坏，升级为 P0。

## 审查范围

本专项 review 第一批应用于 PCRE2 统一规则运行时，但规则适用于所有“迁移到 Rust/current model”的后续工作。

第一批必审范围：

- PCRE2 规则运行时 prepare/commit/scan/fingerprint API。
- 统一规则 SQLite store：`rule_sets`、`rules`、`rule_domain_states`。
- Python rule import service 和 persistence rule records。
- 旧 regex contract、旧规则表、旧 Python 正则解释、旧 `TextRules` 规则语义。
- 普通占位符、结构化占位符、源文残留、MV 虚拟名字框、插件配置、事件指令、Note、非标准 data、插件源码规则链路。
- tests、fixtures、scan budget、Skill、README、配置示例和错误文案中的旧契约残留。

历史 docs、records、已完成 plan 可以作为审查线索，但不作为当前运行契约，也不作为旧代码保留理由。

## 迁移证据模型

每个子代理都必须围绕同一套证据模型审查，避免各看各的。

### 1. 迁移声明清单

先列出“谁声称迁移已经发生”。来源包括：

- spec、plan、README、CHANGELOG、Skill。
- commit message。
- API 名称、模块名称、函数名称、测试名称。
- schema 字段、JSON report 字段、错误码。
- 删除说明、scan budget 防回退说明。

每条声明必须写成：

```text
声明：<谁应该接管什么>
来源：<文件:行号或提交摘要>
承诺的 owner：<Rust rule_runtime | Python CLI 编排 | SQLite store | 其他>
承诺的副作用：<写库 | 清理 | 扫描 | 校验 | 报告 | 写回 | 其他>
```

### 2. 真实生产链路

从当前用户入口追踪真实调用链：

```text
CLI / Agent service
-> Python 编排
-> native adapter
-> Rust API
-> Rust store / scanner / adapter
-> SQLite / 文件 / report / cache / write-back
```

每条链路必须标出：

- 哪一步真正完成副作用。
- 哪一步只是校验、转换、报告或 no-op。
- 哪一步仍使用旧模块、旧表、旧 helper、旧 dialect 或旧事实源。

### 3. 副作用归属矩阵

对每个 domain 或命令建立矩阵：

```text
副作用：替换规则
声明 owner：Rust rule_runtime store
真实 owner：Python rule_records
证据：<文件:行号>
结论：半迁移
严重程度：P1
```

### 4. 物理删除矩阵

对每个被替换对象建立矩阵：

```text
对象：旧 Python source residual helper
声明状态：最终删除
当前状态：文件内仍存在，入口 raise
证据：<文件:行号>
结论：伪删除
严重程度：P2
```

### 5. 测试真实性矩阵

对关键测试建立矩阵：

```text
测试：native commit returns success
验证内容：返回 ok
未验证内容：SQLite rules/rule_sets/rule_domain_states 变化
结论：假成功测试
严重程度：P2 或 P1，取决于是否掩盖半迁移
```

## 多子代理 Review 轨道

### 轨道 A：迁移声明与生产链路

目标：找出所有声称已经迁移、接管、删除或统一的地方，并追到真实生产链路。

重点：

- spec、plan、README、Skill、commit message 是否声明 Rust/current model 已接管。
- API 名称是否承诺了比实现更多的副作用。
- CLI/service 是否真的调用新路径。
- 新路径是否只在测试中使用。

必须输出：

- 迁移声明清单。
- 每条声明对应的真实生产链路。
- 已完成迁移、半迁移、无迁移分类。
- 证据不足但需要复核的声明。

### 轨道 B：副作用归属与事务边界

目标：审查真实写入、清理、备份、commit、rollback 和 token 校验是否由声明 owner 完成。

重点：

- `commit` 是否真的写库或提交事务。
- prepare/commit 是否同属一个规则生命周期。
- Python 是否先完成真实写入，Rust 后置确认。
- 失败时是否会留下半导入、半清理或半报告状态。
- `plan_token` 是否覆盖真实 DB 状态和 cleanup plan。

必须输出：

- 副作用归属矩阵。
- 事务边界。
- 半提交风险。
- no-op commit、空 store、未使用 db path、未调用 store 的证据。

### 轨道 C：无迁移与孤立新代码

目标：审查新增 Rust/native/current model 是否只是孤立存在，没有进入生产主路径。

重点：

- 新 Rust 模块是否只有 Rust 单测调用。
- 新 PyO3 API 是否没有生产 service 调用。
- 新 schema 是否没有生产读写。
- 新 diagnostics/report 字段是否没有真实数据来源。
- 新错误码是否不会从真实 CLI 触发。

必须输出：

- 孤立新代码清单。
- 未接入生产链路的位置。
- 文档或测试是否已经声称它生效。
- 无迁移分类和严重程度。

### 轨道 D：半迁移与空门面

目标：审查新 API 是否只做表面接入，核心行为仍在旧侧完成。

重点：

- 名为 commit/store/write/import/apply 的函数是否完成对应副作用。
- 参数名带下划线、dead code、unused store、只返回 report 的实现。
- Python 仍直接处理 capture、matcher、模板、规则命中、规则写库或清理。
- Rust API 调用位置是否在旧侧副作用之后。

必须输出：

- 空门面清单。
- 半迁移调用链。
- 旧侧真实副作用证据。
- 应由新 owner 完成但没有完成的行为。

### 轨道 E：伪删除与旧代码旧测试残留

目标：审查被替换对象是否物理删除，而不是只禁用、绕过或未调用。

重点：

- 旧源码文件、旧模块、旧 helper、旧 re-export。
- 旧测试、fixture、stub、mock、canary、scan budget 账本。
- 旧字段、旧表、旧 dialect、旧报告字段。
- 当前源码和测试中出现的 `legacy`、`old`、`fallback`、`compat`、`deprecated`、旧正则写法和旧表名。

必须输出：

- 物理删除矩阵。
- 仍保留对象是否属于当前生产契约。
- 不能作为保留理由的测试或 fixture。
- 应删除、应改写为当前契约、或允许保留为内部固定逻辑的分类。

### 轨道 F：测试真实性与防假成功

目标：审查测试是否验证真实迁移，而不是验证新门面能返回 success。

重点：

- native commit 是否验证真实 SQLite 状态。
- import 命令是否验证规则 store、domain state、备份和清理。
- validate dry-run 是否验证不写库。
- 旧 dialect 是否仍出现在当前测试示例。
- 是否存在只 mock 新路径、但生产仍走旧路径的测试。
- 是否有 no-fallback 测试覆盖旧侧函数不能被生产调用。

必须输出：

- 假成功测试清单。
- 缺失的真实副作用断言。
- 旧契约测试残留。
- 需要新增或改写的测试类型。

### 轨道 G：文档、Skill 与用户契约

目标：审查用户可见契约是否与真实生产行为一致，且只描述当前契约。

重点：

- README、Skill、配置示例和错误文案是否声称迁移完成。
- 当前示例是否仍保留旧 dialect 或旧字段。
- 用户可见报告是否可能把半迁移报告成完成。
- docs 是否倒置覆盖 Skill 或当前实现。
- 破坏性变化是否只描述当前要求，不解释旧路径。

必须输出：

- 文档声明和真实行为对照。
- 旧契约表述残留。
- 用户会被误导的报告或错误文案。
- Skill canonical 源与生成目标一致性。

### 轨道 H：性能与并发真实路径

目标：审查性能敏感逻辑是否真的迁移到 Rust/current owner，而不是只新增 Rust 包装。

重点：

- 大规模扫描、匹配、hash、stale 判断、质量检查、写回协议是否仍由 Python 串行完成。
- Rust 线程配置是否真实参与生产调度。
- diagnostics 是否来自真实 Rust 阶段，而不是报告层拼接。
- scan budget 是否掩盖真实性能证据缺失。

必须输出：

- 性能敏感副作用归属。
- Python 串行重活残留。
- Rust 并发入口是否生产可达。
- 真实 CLI 性能证据缺口。

## PCRE2 规则运行时专项必查项

执行本专项 review 时，PCRE2 统一规则运行时至少必须回答以下问题：

- `commit_rule_import` 是否真的打开 SQLite，并在 Rust 事务中替换当前 domain 规则。
- Rust `store::replace_domain_rules` 是否进入生产调用链。
- `db_path` 是否真实使用，而不是被命名为 `_db_path` 或等价 unused 参数。
- Python 是否仍直接调用 `replace_*_rules` 写统一规则表。
- Python 是否仍解释用户、Agent 或配置正则。
- Python 是否仍解释 capture、模板语义、规则命中、规则影响分析或清理计划。
- `validate-*` 是否只 dry-run 且不写库。
- `import-*` 是否走 prepare -> Python 备份 -> Rust commit 的同一 plan_token 生命周期。
- commit 失败是否不会留下半导入规则或半清理译文。
- 空规则确认是否也走统一 prepare/commit，并写 `rule_domain_states`。
- `rules_fingerprint` 是否覆盖当前所有 domain、domain state、配置正则、runtime contract version 和 store schema version。
- 旧 domain 规则表读写 API 是否删除，而不是只改成写新表但仍保留旧 owner。
- `TextRules` 中旧规则语义是否物理删除或明确瘦身为非规则 DTO/展示辅助。
- 当前 tests、fixtures、Skill 和配置示例是否只使用 PCRE2 推荐写法 `(?<name>...)`。
- `regex_contract.py`、Rust `regex_contract.rs`、`fancy-regex` 和旧 regex contract 测试是否物理删除。
- 新测试是否验证 DB 状态、备份文件、清理结果、错误码和 no-fallback，而不是只验证 native 返回 ok。

## 子代理权限

本专项 review 默认只读。

允许：

- 读取仓库文件。
- 使用 `rg`、`rg --files`、`Get-Content`、`git diff`、`git log`、`git show` 等只读命令。
- 运行不会写真实数据库、不会写游戏目录、不会改源码或生成物的只读检查。
- 输出 Markdown review 报告。

禁止：

- 修改源码、测试、schema、Skill、README、docs、脚本、配置或发行文件。
- 执行会写 `data/db/`、游戏目录、日志、输出目录或发行目录的命令。
- 为了证明修复可行而实施修复。
- 把“增加 Python guard”“保留旧路径但不调用”“补一个 success 测试”写成完成方案。

如需运行测试或静态检查，必须说明命令是否会写缓存或生成文件。全量 `uv run pytest` 不作为本专项 review 的默认动作。

## 子代理报告格式

每个轨道输出以下结构：

```markdown
# 轨道 <字母>：<标题>

## 范围

## 只读命令

## 结论

PASS | FAIL | NEEDS_REVIEW

## 迁移声明清单

## 真实生产链路

## 关键发现

### <严重程度>：<标题>

- 现象分类：<半迁移 | 无迁移 | 伪删除 | 空门面 | 假成功测试>
- 证据：<文件:行号或命令输出摘要>
- 声明 owner：<谁被声明接管>
- 真实 owner：<谁实际完成副作用>
- 真实副作用：<写库 | 清理 | 扫描 | 报告 | 写回 | 其他>
- 影响：<用户可见或工程可见问题>
- 应删除或改写的旧对象：<如适用>
- 缺失测试：<如适用>

## 已覆盖但未发现问题的边界

## 证据缺口
```

## 严重程度

- P0：会导致错误写库、半提交、数据破坏、错误写回、备份缺失后清理、用户报告成功但真实状态失败。
- P1：声明迁移完成或 Rust/current owner 已接管，但真实生产副作用仍由旧侧、Python、空门面或旁路完成；或文档声称生效但生产完全未迁移。
- P2：旧代码、旧测试、旧 fixture、旧 dialect、旧 helper 或假成功测试未清理，当前暂未证明会进入生产主路径。
- P3：命名、文档、注释、测试组织或报告表述容易误导后续维护，但不改变当前真实行为。

## 主代理汇总规则

主代理必须：

- 合并多个子代理指向同一根因的问题。
- 优先保留能证明真实副作用归属的证据。
- 将“无调用证据”和“已完成迁移证据”区分开。没有找到调用链不能自动判定通过。
- 对每个 P1/P0 明确写出声明 owner 和真实 owner。
- 对每个伪删除问题明确写出旧对象为什么不属于当前生产契约。
- 对没有使用子代理的情况明确记录原因，并按轨道逐项人工审查。

主代理不得：

- 把“新增 Rust 代码”当作迁移完成。
- 把“测试通过”当作真实副作用已经迁移。
- 把“旧代码目前未调用”当作物理删除。
- 把“Python 仍写新统一表”当作 Rust store 已接管。
- 把文档描述当作生产事实。

## 推荐执行步骤

### 1. 建立基线

运行只读命令：

```powershell
git status --short
git diff --name-status <base>..HEAD
git diff --stat <base>..HEAD
git log --oneline <base>..HEAD
```

`<base>` 由本次 review 的目标决定。对当前开发分支可使用上一次已批准节点、远端跟踪分支或用户指定 commit。最终报告必须写清实际使用的 base。

### 2. 提取迁移声明

用 `rg` 搜索以下线索：

```powershell
rg -n "commit_rule_import|prepare_rule_import|rule_runtime|PCRE2|统一规则|已删除|接管|Rust 主路径|fallback|legacy|old|compat|deprecated|allow\\(dead_code\\)|\\?P<|\\?<" docs README.md CHANGELOG.md skills app rust tests
```

搜索结果不能直接作为问题，必须追到真实生产链路。

### 3. 派发轨道

并发派发 A 到 H。每个子代理只读审查，不修改文件。

### 4. 汇总裁决

按“完成迁移、半迁移、无迁移、伪删除、需复核”分类输出。发现 P0/P1 时，本轮 review 结论为 FAIL。

### 5. 可选验证

review 默认不要求运行全量测试。若需要增强证据，可按范围运行：

```powershell
uv run basedpyright
uv run python scripts/generate_skill_protocol.py --check
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
uv run pytest <focused test path>
```

未运行的验证必须写入剩余风险，不能写成通过。

## 最终输出格式

最终 review 结论必须按以下顺序：

```text
结论：PASS | FAIL | BLOCKED

是否使用子代理并发 review：是 | 否

使用的 base：

发现：
1. [P0/P1/P2/P3] 标题
   现象分类：
   证据：
   声明 owner：
   真实 owner：
   影响：

已确认没有问题的边界：

证据缺口：

未运行验证：
```

结论规则：

- PASS：未发现 P0/P1；P2/P3 不影响迁移真实性。
- FAIL：发现 P0/P1，或发现关键迁移声明无法追到真实生产副作用。
- BLOCKED：关键文件、diff、base 或生产链路不可读，无法可靠判断。

## 成功标准

一次基于本 spec 的 review 成功时，应满足：

- 每条重要迁移声明都有真实生产链路证据。
- 每个核心副作用都有明确真实 owner。
- 半迁移、无迁移、伪删除和假成功测试不会被“测试通过”或“新代码存在”掩盖。
- PCRE2 规则运行时的 prepare/commit/store/report/fingerprint 真实状态被查清。
- 旧代码和旧测试是否物理删除有明确结论。
- 最终报告能直接指导后续修复，而不是只给抽象原则。
