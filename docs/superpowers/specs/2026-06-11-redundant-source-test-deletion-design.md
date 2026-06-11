# 全仓库冗余源码与测试删除设计

## 背景

项目已经完成多轮 Rust 主事实源迁移，近期变更持续收束旧 Python 扫描器、旧 extraction、旧 text fact 和旧测试保护网。当前剩余风险不是测试不足，而是部分测试和生产源码仍在保护历史实现：这些旧代码在正式生产路径中已经不用，或只是被浅层绕过，但因为测试、fixture、canary、scan budget 账本、mock、stub 或迁移保护仍依赖它们，导致旧实现无法物理删除。

本设计的目标是把测试重新约束为当前生产契约的验证工具，而不是历史实现的事实源。

## 目标

本次工作是一次全仓库源码与测试冗余清理审计。目标是以当前生产事实源为唯一依据，物理删除已经不属于正式生产使用路径的源码、测试、fixture、mock、stub、canary、scan budget 账本、旧 adapter、旧 extraction、旧 scanner、旧 fallback、旧 re-export 和旧兼容分支。

当前生产事实源包括：

- `main.py` / `app.cli_main:main` 可达的当前 CLI 命令。
- 发行包实际包含并使用的入口、配置、prompt、Skill 流程。
- 当前 SQLite schema：`app/persistence/schema/current.sql`。
- 当前 Rust 原生扩展暴露并被生产路径调用的能力。
- README / Skill 中描述给真实用户执行的当前流程。
- 用户可见外部契约：CLI 参数、配置字段、JSON 报告、错误码、写回结果、日志摘要、目录结构。

核心原则：测试不能作为需求来源；旧代码必须证明自己仍属于当前生产契约。证明不了就删除。

## 非目标

本次不处理文档和历史记录，不修改：

- `docs/`
- `skills/`
- `README.md`
- `CHANGELOG.md`
- 历史 plans、records、batch 记录

这些内容可以作为审计线索，但不能作为保留旧源码或旧测试的理由，也不作为本次删除对象。

本次不追求保留 Python/Rust 内部 public symbol 兼容性。项目按 CLI 应用治理，不按公共库治理。包根 re-export、`__all__`、测试导入路径、内部 import 便利性都不构成外部契约。

## 物理范围

可修改：

- `app/`
- `rust/`
- `main.py`
- `tests/`
- `scripts/`
- `pyproject.toml`
- 配置模板、类型 stub、构建/校验入口等必要非文档工程文件

不修改：

- `docs/`
- `skills/`
- `README.md`
- `CHANGELOG.md`
- 历史记录、输出目录、构建产物、虚拟环境、本地数据和日志

本 spec 文件本身是设计产物，写入 `docs/superpowers/specs/`；后续实现阶段不以修改文档为目标。

## 删除准则

采用“生产事实源反推 + 默认删除”的规则。不是证明某段旧代码没用才删，而是它必须证明自己仍服务当前生产契约才留。

满足以下任一条件的源码对象、测试对象或辅助对象，默认删除：

- 只被测试引用。
- 只服务 mock、stub、fixture、canary、scan budget、历史迁移保护。
- 只验证内部 batch、cache、adapter、fallback、legacy scanner、legacy extraction 机制。
- 与 Rust/native 当前事实源重复。
- 属于旧 Python scanner、旧 extraction、旧 write-probe、旧 text scope 构造、旧 schema 形状、旧 prompt 组装保护。
- 入口存在但生产路径只是“过个样子”调用，结果不参与当前外部契约。
- 通过包根 re-export 或 `__all__` 暴露，但没有当前 CLI、发行或用户流程依赖。
- 留下来的主要理由是“可能以后有用”“以前迁移时保留过”“删了测试会坏”。

如果某个旧模块整体身份是历史包袱，即便里面有少量能力仍可能被当前路径需要，也优先删除整模块。当前路径确实需要的能力，应迁到当前事实源所属模块，或接到 Rust/native/CLI 当前边界；不在旧模块里摘叶子续命。

删除后如果真实生产流程报错，应让问题显式暴露，再按当前生产契约修当前路径。禁止恢复旧兼容层、静默兜底或 mock 成功。

## 测试准则

测试也是清理对象。保留或新增测试的依据只能是当前真实生产契约，不是历史实现细节。

默认删除以下测试：

- 固定旧实现内部机制的测试。
- 验证 legacy 调用计数、历史批次记录、迁移残留分类的测试。
- 只证明 mock、fixture、stub、adapter 还能工作的测试。
- 保护 Python fallback、旧 scanner、旧 extraction、旧 text scope 的测试。
- 为了让旧代码继续存在而写的 canary 或 scan budget 账本测试。

可以保留或改造的测试：

- 验证当前 CLI、JSON 报告、错误码、schema、写回结果、prompt 输出隔离、Rust/native 主路径的黑盒契约测试。
- 验证“当前生产命令不能回到旧 Python 重扫描”的测试，但必须表达为当前生产路径约束，而不是历史批次账本。
- 验证删除后暴露出的当前生产契约缺口的少量黑盒测试。

执行中不采用 TDD：

- 不先写失败测试驱动删除。
- 不为了让测试绿而制造新 adapter、fallback 或兼容层。
- 默认动作是删除旧测试，必要时改成当前契约验收。
- 只有核心外部契约明显缺少验证时，才允许极少量补充黑盒验收测试。

## 执行策略

采用“生产事实源反推判定，模块批次落地删除”。

先从当前 CLI、发行入口、schema、Rust/native 主路径和用户流程反推允许存在的生产路径。凡是不在这些路径上，且无法证明自己服务当前外部契约的源码和测试，默认删除。实际动手时按模块批次推进，避免一次性无边界改动；模块内部不为每个旧 helper 单独审批。

执行约束：

- 主线程负责实际文件修改、删除、重接线、最终判断和交付结论。
- 子代理可并行用于发现、审计、复核、独立视角检查和风险提示；子代理不直接修改文件，不决定最终保留或删除。
- 执行期按模块运行针对性测试、类型检查或静态搜索；全量 `uv run pytest` 只在最终收尾阶段执行。
- 删除旧代码后出现失败时，只修当前生产契约路径，不恢复旧 fallback、旧 adapter、旧 scanner 或旧兼容层。

## 首批清理地图

1. `plugin_source_text`

   清理旧 scanner、旧 extraction、旧 write-probe 测试残留，重点处理 batch/cache 对照测试、旧 scanner 入口、只为旧路径存在的 monkeypatch 和 canary。

2. `note_tag_text`

   清理旧 extraction、包根 re-export、只为测试保留的定位/匹配辅助，以及与当前 Rust/native Note 标签事实源重复的 Python 路径。

3. `nonstandard_data`

   清理旧 extraction、旧规则展开/命中统计、只为历史覆盖检查存在的 Python 形状。

4. `text_scope`

   审计旧范围构造、旧 `TranslationItem` 形状依赖、旧 write-probe、旧 source snapshot / text fact 辅助。当前生产确实需要的能力应接到 current text fact / Rust/native 当前边界。

5. `agent_toolkit` 服务层

   删除只为旧流程、旧测试或旧 workspace 形状存在的 adapter、服务函数和内部转发。生产命令需要的服务层只保留当前 CLI / Agent 工作流直接使用的路径。

6. `scan_budget` 与 canary 测试

   删除历史批次计数、legacy 残留分类、记录存在性保护。只保留能约束当前生产路径复杂度、避免回到旧 Python 重扫描的少量检查。

7. 测试 fixture 与 `conftest`

   删除只为旧实现准备状态的 helper、stub、mock、直接写入旧形状数据的夹具。当前契约确实需要的测试数据应更接近真实 CLI / DB / Rust 主路径。

8. `scripts/`、`typings/`、配置和工程入口

   清理指向旧对象的维护残留。若删除源码导致类型 stub、脚本映射、配置入口仍引用旧路径，应同步删除或改到当前边界。

## 模块落地流程

每个模块批次按以下顺序处理：

1. 从生产事实源反查当前可达路径。
2. 列出本模块待删对象：源码、测试、fixture、monkeypatch、re-export、canary。
3. 删除旧模块或旧路径；若当前生产仍需要少量能力，按当前边界重接或重建。
4. 删除或改造对应测试，禁止保留只为旧实现服务的测试。
5. 运行静态和行为验证，失败时只修当前契约路径，不恢复旧兼容层。
6. 记录本批删除范围、验证结果和剩余风险。

## 验证方式

本次不以 TDD 作为推进方式，验证放在删除和重接线之后，用来确认当前生产契约没有被破坏。

最终收尾必须执行：

- `uv run basedpyright`
- `uv run pytest`

触及 Rust 原生扩展、Rust 主路径、构建流程或发行流程时，还必须执行：

- `cargo fmt --check`
- `cargo clippy`
- `cargo test`

实现过程中允许按改动范围执行针对性验证，例如单个测试文件、单个测试函数、静态 import 搜索、CLI 抽样命令或类型检查。全量 `uv run pytest` 只在最终收尾阶段运行，因为本项目全量 pytest 耗时巨大。

需要按改动范围补充执行真实 CLI 抽样验证，优先覆盖：

- 注册 / 当前文本索引重建。
- 规则扫描与导入。
- 翻译状态 / 质量报告。
- 写回计划或写回前置检查。
- 当前被清理模块对应的生产命令。

CLI 抽样不是为了覆盖旧实现，而是证明当前用户流程仍可走通。

## 失败处理

验证失败时先判断失败对象属于哪类：

- 如果失败来自旧测试、旧 fixture、旧 scan budget 账本：删除或改写为当前契约测试。
- 如果失败来自生产路径仍引用旧对象：改当前生产路径，接到当前事实源。
- 如果失败暴露当前生产契约缺口：按当前契约修复，必要时补少量黑盒验收。
- 如果失败要求恢复旧 fallback、旧 adapter、旧 scanner 或旧兼容分支：拒绝恢复，重新设计当前路径。

删除后真实生产过程中暴露的问题，允许显式报错。后续修复只面向当前契约，不以旧实现为恢复目标。

## 成功标准

本次清理成功时，应满足：

- 旧源码和旧测试被物理删除，而不是标记 deprecated 或藏到新路径。
- 没有为了测试继续保留生产不用的代码。
- 没有新增 Python fallback、mock 成功、兼容开关或第二事实源。
- 保留测试只证明当前真实生产契约，不证明历史实现机制。
- `scan_budget`、canary、fixture 不再承担历史批次账本职责。
- Python/Rust 内部 public symbol 不再作为保留理由。
- 当前 CLI、schema、JSON 报告、写回、prompt 隔离、Rust/native 主路径等核心外部契约通过验证。
- 最终交付说明列出删除范围、结构调整、验证命令结果、未覆盖风险和后续发现问题的处理原则。

## 风险接受

本设计明确接受一种风险：删除旧代码后，某些过去被旧路径暗中支撑的生产边缘流程可能暴露错误。这个风险优于继续保留冗余旧实现。暴露错误后应让它显式失败，再按当前生产契约修复。
