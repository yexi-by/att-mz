# Pytest 当前契约治理闭环设计

## 背景

当前 pytest 套件已经从保护生产行为扩张到保护测试基础设施、历史实现路径、发行文档、Skill 协议、benchmark runner 和 TDD 过程遗迹。现状基线约为：

- `pytest --collect-only -q` 收集 1038 个测试。
- `tests/**/*.py` 约 43067 行。
- 多个测试文件超过 1000 行，最大文件超过 4000 行。
- 存在大量 `monkeypatch`、`forbidden_*`、`without_python`、`does_not_call_*`、`scan_budget`、benchmark、release/docs/Skill 测试。

本设计要求一次性完成 pytest 治理闭环，不做只清理部分热点文件的最小实现。执行顺序可以先处理最大文件，但交付范围必须覆盖全部 `tests/**/*.py`、测试夹具、测试运行配置、根目录 `AGENTS.md`，以及必要的 Rust `#[cfg(test)]` 安全网。

## 目标

1. 让剩余 pytest 只保护当前生产契约：`app/` 生产行为、Rust/native 边界、公开 CLI 行为。
2. 删除不保护当前生产契约的 pytest：测试基础设施、benchmark/performance、release/package/docs/Skill/release notes、旧契约、历史 canary、实现路径哨兵、重复铺开的输入校验。
3. 将 Python 大集成测试改薄：Python pytest 只验证公开入口、配置、JSON 输出、数据库可观察结果、write-back 文件副作用。
4. 将核心逻辑安全网放回 owner 层：规则匹配、候选扫描、占位符、hash/stale、native schema、错误码、写回计划等由 Rust `#[cfg(test)]` 或 native contract 保护。
5. 实打实降低测试规模和运行成本：pytest 收集数减少至少 50%，`tests/**/*.py` 总行数减少至少 50%，本机全量 pytest 小于 60 秒。

不设最终测试数量上限。最终保留多少测试由“是否保护当前生产契约”决定；但达不到 50% 瘦身和 60 秒全量运行就是不合格，必须继续删除、合并、迁移或重写测试。

## 非目标

- 不以 CI 耗时作为硬验收目标。CI 会因本机套件变轻自然受益，但本轮不围绕 GitHub 环境做专项优化。
- 不通过 pytest 保护发行包布局、Skill 协议、发布说明或文档生成物。
- 不通过 pytest 证明性能敏感路径正确或足够快。性能路径由真实 CLI 性能证据、阶段耗时和真实命令结果证明。
- 不借测试治理顺手重构当前正常运行的生产逻辑。生产源码发现历史分支或职责混乱时记录问题，除非它直接破坏当前运行契约，否则本轮不改运行逻辑。

## 测试存在资格

保留 pytest 必须满足至少一条：

1. 直接保护 `app/` 当前生产源码的公开行为：CLI 参数、配置加载、JSON 输出、数据库读写、错误退出、write-back 文件副作用。
2. 直接保护 Rust/native 当前边界：Python 调用 native 的输入输出契约、错误码映射、可观察数据库或文件结果。
3. 作为极少量公开 CLI 主流程 canary，证明真实入口能完成核心链路。

默认删除：

- 测试基础设施测试，包括 fixture 调度、模板复制、pytest worker 调度、测试 helper 自证。
- benchmark/performance pytest，包括 benchmark runner、小任务 runner、`scan_budget`、mock 调用次数证明。
- release/package/docs/Skill/release notes pytest。
- 旧数据库、旧 schema、旧 metadata、旧 workspace、旧规则、历史 canary 和兼容性测试。
- `monkeypatch` 禁止内部路径、`forbidden_*`、`without_python`、`does_not_call_*` 等实现路径哨兵。
- 重复铺到每个 CLI 的输入归一化和 reject 测试；只在生产 owner 层保留最少表驱动契约测试。

如果某条 pytest 看似有价值但不满足资格，不能以“以后可能用到”保留。必须删除、合并到合格测试、迁移到 Rust `#[cfg(test)]`，或改写成薄公开契约测试。

## 允许修改范围

允许修改：

- `tests/` 下 pytest、夹具和测试辅助代码。
- Rust 源文件中的 `#[cfg(test)]` 测试模块。
- 根目录 `AGENTS.md` 中关于 pytest 验证边界、全量 pytest 命令、release/docs/Skill pytest 要求的规则。
- 必要的测试运行配置和 CI 命令同步；仅当 CI 仍引用旧 pytest 命令或旧测试契约并与 `AGENTS.md` 冲突时修改。

原则上不修改：

- `app/` 生产运行逻辑。
- Rust 非测试生产逻辑。
- release、Skill、docs 正文。若实现过程中确实修改这些文件，必须按对应生成物或文档检查验证，但不得为它们保留 pytest。

## 执行流程

### 1. 建立基线

执行并记录：

- `pytest --collect-only -q` 收集数量。
- `tests/**/*.py` 总行数。
- pytest 文件数量。
- 超过 1000 行的测试文件列表。
- `monkeypatch`、`forbidden_*`、`without_python`、`does_not_call_*`、`scan_budget`、benchmark、release/docs/Skill 测试的数量和文件列表。
- 当前本机全量 pytest 命令、worker 数、总耗时和最慢测试列表。

这些基线用于最终对比，不作为保留测试的理由。

### 2. 全量归类

覆盖全部 `tests/**/*.py`，每个测试文件必须归入以下裁决之一：

- 删除：不保护当前生产契约。
- 合并：重复输入校验、重复错误映射、重复 JSON 形状检查。
- 改写为薄契约：保留公开 CLI、数据库、文件副作用、JSON 输出等可观察行为。
- 迁移到 Rust：核心规则、候选、hash/stale、占位符、写回计划、错误码等 owner 在 native 的行为。
- 保留：已经直接保护当前 `app/`、native 边界或公开 CLI 行为，且无法用更薄测试表达。

大文件优先处理，但不是交付边界。所有小文件、helper、fixture、benchmark/canary、release/docs/Skill 测试都必须纳入裁决。

### 3. 删除无资格测试

整文件删除优先：

- 测试基础设施测试。
- benchmark/performance pytest。
- release/package/docs/Skill/release notes pytest。
- 历史 canary 和旧契约测试。

同步清理 `AGENTS.md` 中要求通过 pytest 固定这些非生产契约内容的规则。`AGENTS.md` 必须改成当前测试策略：pytest 只保护 `app/` 生产契约、Rust/native 边界和公开 CLI 行为；发行文档、Skill、发布说明不再由 pytest 保护。

### 4. 改写剩余 Python 测试

对仍有当前生产价值的 Python 大集成测试：

- 将多步骤内部路径断言改成公开入口和可观察结果断言。
- 删除禁止调用某个内部函数的 monkeypatch 哨兵；用数据库结果、文件变化、JSON 输出、错误码或真实 CLI 性能证据替代。
- 删除只为证明“不走旧 Python 路径”的测试。若旧路径仍存在但当前运行不应使用，只保留当前公开行为验证。
- 合并重复 parser、输入归一化、boolean reject、空输入 reject 测试到 owner 层表驱动测试。
- 减少重复注册游戏、重复构造大 fixture、重复全流程导入和重复异步链路。
- 保留少量公开 CLI 主流程 canary，数量必须克制，只证明真实入口可用，不覆盖每个历史阶段。

### 5. 补足 Rust/native 安全网

删除 Python 大集成测试前，如果核心行为会失去保护，优先补 Rust `#[cfg(test)]` 或 native contract：

- 规则匹配和 selector。
- 候选扫描。
- 占位符和结构化占位符。
- hash、stale 判断、scope fingerprint。
- native schema、错误码和错误映射边界。
- 写回计划、质量 gate、文件写回协议。

Rust 新增测试必须贴近 owner 层，禁止把 Python 大集成流程原样搬成 Rust 大集成测试。交付说明必须列出新增 Rust 测试数量和大致覆盖范围。

### 6. 重构测试运行性能

全量 pytest 小于 60 秒是交付硬门槛。不能只靠删除测试数量，还必须重构剩余测试结构：

- 复用可安全复用的测试数据模板，避免每条测试重复构造相同游戏目录。
- 保证每条测试仍有独立可写目录、独立数据库、独立日志，不能牺牲隔离换速度。
- 减少参数化膨胀，只保留能代表不同生产契约分支的参数。
- 删除测试 helper 自证，精简 `conftest.py` 中只为旧测试存在的调度逻辑。
- 允许根据本机实测调整最终 worker 数，例如 `-n auto` 或固定 `-n 8`。
- 最终全量 pytest 命令必须写回 `AGENTS.md`，成为唯一推荐命令。

禁止通过以下方式达标：

- `skip`、`xfail`、`-k` 排除、移动慢测试出默认收集。
- local/CI 两套测试标准。
- mock 成功、吞异常、伪造副作用。
- 保留隐藏慢路径但不在全量命令中运行。

## 验收标准

交付必须同时满足：

1. pytest 收集数相比基线减少至少 50%。
2. `tests/**/*.py` 总行数相比基线减少至少 50%。
3. 剩余 pytest 均能说明其保护的当前生产契约。
4. release/package/docs/Skill/release notes、benchmark/performance、测试基础设施 pytest 已删除。
5. 实现路径哨兵数量显著下降；剩余 `monkeypatch` 必须用于隔离外部依赖或构造输入，不得用于禁止内部路径。
6. 本机全量 pytest 小于 60 秒。
7. `AGENTS.md` 已同步新的 pytest 边界和最终全量 pytest 命令。
8. 如果新增 Rust `#[cfg(test)]`，其范围只覆盖被删除 Python 测试留下的核心逻辑安全网缺口。

## 验证命令

最终交付必须运行：

```powershell
uv run basedpyright
```

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q <最终 worker 参数> --durations=30 --durations-min=0.5
```

如修改或新增 Rust 测试，还必须运行项目 Rust 格式检查、clippy 和 Rust 测试。最终使用的 Rust 命令以项目现有工具链为准，并在交付说明中写清。

交付说明必须包含：

- pytest 收集数前后对比。
- `tests/**/*.py` 行数前后对比。
- 超过 1000 行测试文件前后对比。
- 本机全量 pytest 最终命令、worker 数、总耗时、最慢测试列表。
- 新增 Rust 测试数量和覆盖范围。
- 未修改生产逻辑的确认；若确实修改了生产逻辑，必须逐项说明原因、影响和验证。

## 风险控制

- 如果删除测试后发现当前运行契约没有安全网，不得回退为保留大 Python 集成测试；必须改写为薄契约测试或迁移到 Rust/native owner 层。
- 如果 50% 瘦身达标但全量 pytest 超过 60 秒，继续重构测试结构。
- 如果全量 pytest 小于 60 秒但剩余测试仍包含无资格内容，继续删除或改写。
- 如果某条测试无法删除，必须能用当前生产契约解释它的存在；不能使用历史兼容、测试方便、保守、TDD 过程或未来可能需要作为理由。
