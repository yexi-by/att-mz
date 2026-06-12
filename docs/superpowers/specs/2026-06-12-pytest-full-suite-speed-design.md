# 全量 pytest 提速与 CI 恢复设计

## 背景

当前本机全量 Python 业务测试执行结果为 `1052 passed in 268.01s`，约 4 分 28 秒。临时使用 `pytest-xdist` 以 8 个 worker 并行执行，结果为 `1052 passed in 89.59s`，说明测试隔离基础可以支撑并行，但距离本机 1 分钟目标仍需要线程限额和必要的重复准备成本治理。

GitHub Actions 远端全量 pytest 耗时约 28 分钟，且当前 release workflow 已临时改为只执行少量 release path 测试。这与项目文档和 `AGENTS.md` 中“Python 业务测试交付红线是全量 pytest”的当前契约不一致。此次变更要恢复全量 pytest 门禁，并把本机和远端的执行时间压到可接受范围。

## 目标

- 本机全量 pytest 保持等价覆盖，推荐命令稳定进入 60 秒以内。
- GitHub Actions 的全量 pytest 步骤恢复为发布阻断门禁，并在 Windows runner 上进入 5 分钟以内。
- 新增常规 CI，在 pull request 和普通 push 阶段执行 `basedpyright` 与全量 pytest，提前发现 release 前的问题。
- `AGENTS.md` 写入当前 pytest 性能规范，删除或改写“不跑全量 pytest / 只跑测试子集替代全量”的临时约定。
- `.github/workflows/release.yml` 恢复全量 pytest 步骤，不再用少量 release path 测试作为 Python 业务测试门禁。
- 测试质量不降低，不通过跳过慢测试、减少断言、缩小测试输入真实性或隐藏失败来换取速度。

## 非目标

- 不重构业务逻辑。
- 不为本次测试提速引入 TDD 流程；本次修改对象就是测试运行与 CI 门禁，不为了“测试优化测试”新增元测试或套娃式测试。
- 不把 Rust fmt、clippy、Rust test 纳入新增常规 CI 的第一阶段范围；release workflow 继续保留这些发布门禁。
- 不使用测试分组矩阵替代项目级全量 pytest 命令。
- 不把私有样本、真实本机路径或开发机状态写入仓库配置。

## 推荐方案

第一阶段采用“全量 pytest 并行执行 + Rust 线程限额 + CI 恢复/新增门禁”。

`pyproject.toml` 的 dev 依赖加入 `pytest-xdist`。本机和 CI 的 pytest 命令使用全量测试集，而不是测试子集。并行执行时设置 `ATT_MZ_RUST_THREADS=1`，避免每个 pytest worker 内部再通过 Rust/Rayon 吃满 CPU，导致 Windows runner 上 worker 之间互相抢核。

本机推荐命令先以 8 worker 为基线：

```powershell
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 8 --durations=30 --durations-min=0.5
```

如果实测不稳定达标，再比较 `-n auto`、`-n 10`、`-n 12` 或更低 worker 数。最终写入 `AGENTS.md` 的命令必须来自实测最快且稳定的配置。

GitHub Actions 的全量 pytest 步骤使用固定 worker 数，避免不同 runner 环境下 `auto` 带来不可控波动。CI 的 pytest 步骤要保留耗时输出，用于后续判断是否需要进入第二阶段。

## CI 设计

`release.yml` 保留现有发布流程，但把当前 `Release path tests` 临时步骤改为 `Full Python tests`。该步骤执行全量并行 pytest，并在通过后继续执行 Rust fmt、clippy、Rust test、发行包构建和 GitHub Release 发布。

新增 `.github/workflows/ci.yml`。触发条件为 pull request 和普通 push，排除 `v*` tag，避免和 release workflow 重复。常规 CI 使用 Windows runner、Python 3.14、uv cache 和 Rust toolchain，执行：

- `uv sync --locked --dev`
- `uv run basedpyright`
- 全量并行 pytest

常规 CI 第一阶段不执行 Rust fmt、clippy、Rust test；这些仍由 release workflow 覆盖。若后续希望把 Rust 检查提前到 PR 阶段，应作为单独 spec 或后续扩展处理。

## 规范与文档

`AGENTS.md` 保留“涉及 Python/Rust 源码、测试、schema、构建流程、发行流程或可执行契约的项目交付前，必须执行 basedpyright 和全量 pytest”的红线，并补充当前推荐并行命令和线程限额。

`AGENTS.md` 必须明确：测试子集不能替代全量 pytest 作为 Python 业务测试交付红线；临时 release path 测试不能作为长期发布门禁。

现有“纯文档、Skill 文案、README 或发布说明改动不得默认运行全量 pytest”的规则可以保留。这条规则用于避免无关重测，不等同于禁止全量 pytest，也不允许在触及源码或可执行契约时绕过全量 pytest。

`docs/wiki/development/release-and-tests.md` 要同步更新，确保 wiki、workflow 和 `AGENTS.md` 对测试门禁的描述一致，只描述当前实现，不保留临时子集门禁作为当前事实。

## 第二阶段补救

如果第一阶段后，本机全量 pytest 仍不能稳定进入 60 秒以内，或 GitHub Actions 全量 pytest 步骤仍超过 5 分钟，则进入同一施工范围内的第二阶段：worker 级测试快照复用。

快照只能由当前生产入口真实生成，例如注册游戏、创建当前 SQLite schema、重建当前文本范围索引。每个测试必须复制独立的 DB 和游戏目录后再修改，不能共享可变文件或可变数据库。

快照 fixture 只能消除重复准备成本，不能替代被测生产链路。仍需保留少数端到端 canary 覆盖真实注册、索引、写回、release 协议和用户可见错误路径。

不得手工构造与生产 schema、Rust 输出、SQLite 当前事实或索引 metadata 平行的第二事实源。若快照数据结构必须被测试辅助代码读取，测试辅助代码应只复制文件和数据库，不重新解释业务事实。

## 验证

本机验证：

- `uv run basedpyright`
- `$env:ATT_MZ_RUST_THREADS = "1"; uv run pytest -q -n <最终 worker 数> --durations=30 --durations-min=0.5`

验收时记录全量 pytest 总耗时、worker 数、`ATT_MZ_RUST_THREADS` 和最慢测试列表。全量 pytest 必须保持 0 failed、0 skipped 的业务测试质量，不因速度目标新增 skip 或 `-k` 排除。

GitHub 验证：

- 新增常规 CI 的 full pytest 步骤通过。
- release workflow 的 full pytest 步骤通过。
- GitHub full pytest 步骤耗时进入 5 分钟以内；若不达标，执行第二阶段快照复用，而不是恢复测试子集。

若并行执行暴露测试互相污染、共享全局状态或路径依赖，按测试隔离缺陷修复。不得用降低并发、跳过测试或恢复子集门禁来隐藏失败。

## 风险

- Windows runner 的 CPU 和磁盘 I/O 弱于本机，worker 数可能需要单独调优。
- `ATT_MZ_RUST_THREADS=1` 会降低单个重型 Rust 调用速度，但可以减少多 worker 并行时的抢核，总体更适合 pytest 并行。
- 如果大量测试仍重复执行注册、索引和 SQLite 准备，第一阶段可能只能把远端从 28 分钟降到数分钟级，未必直接达到本机 60 秒目标。
- worker 级快照复用若设计不严，会变成测试第二事实源；因此第二阶段必须以真实生产入口生成快照，并保持每测试独立副本。

## 通过标准

- 本机全量 pytest 推荐命令进入 60 秒以内，且测试覆盖等价。
- GitHub Actions full pytest 步骤进入 5 分钟以内。
- release workflow 恢复全量 pytest，不再以 release path 子集替代。
- 常规 CI 在 pull request 和普通 push 阶段执行 `basedpyright` 与全量 pytest。
- `AGENTS.md`、workflow 和 wiki 对 pytest 门禁的描述一致。
- 未新增为了测试运行优化而存在的元测试，也未用 TDD 流程要求阻塞本次测试基础设施修改。
