# 发布与测试

## 职责

发布与测试文档覆盖发行包构建、Skill 分发、提示词、GitHub Actions 和自动化测试。正式发行包只由 GitHub Actions `release` 工作流生成。`scripts/build_release.py` 负责发布目录、可执行文件、发行版 README、发行版 Skill、字体、提示词和空数据目录的包装。

## 输入

- GitHub Actions 触发标签、手动输入的发布标签，或本地大样本性能基准参数。
- 源码仓库中的配置模板、字体、提示词、发行版 Skill 和发布 README。
- Python、Rust 和测试依赖。

## 输出

- `att-mz-windows-x86_64.zip`。
- 发行包内的 `att-mz.exe`、`README.md`、`setting.toml`、`skills/att-mz/SKILL.md`、Skill references、字体、提示词和空数据目录。
- CI 中的类型检查、测试、构建和冒烟测试结果。
- 本地大样本性能基准 JSON 结果。

## 失败策略

- 本机执行发行版构建脚本会失败；正式发行版只能由 GitHub Actions 构建。
- 发布工作流先执行 `uv run basedpyright`、`uv run pytest`、`cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` 和 `cargo test --manifest-path rust/Cargo.toml`，通过后才构建发行包。
- 发行包冒烟测试必须验证 `att-mz.exe --help` 和空注册表读取。
- 大样本性能门禁不能在 GitHub 托管 runner 上伪造执行；私有样本只能放在本机或持有样本的专用环境。发布前在持有样本的环境运行下面的命令。失败时暂停发布：

```powershell
uv run python scripts/benchmark_rebuild_active_runtime.py `
  --sample <样本游戏目录> `
  --game <游戏标题> `
  --db <数据库路径> `
  --runs 1 `
  --rust-threads 4 `
  --reset-active-data-from-origin `
  --max-slowest-ms 120000 `
  --max-rust-plan-ms 45000 `
  --max-file-replacement-ms 1500 `
  --max-post-write-audit-ms 20000
```

该命令会复制样本和数据库到临时目录，把临时样本的 `data_origin/*.json` 复制回 `data/*.json`，再计时 `rebuild-active-runtime`，用于验证真实文件替换、Rust 计划、文件替换和写后审计热路径。阈值来自 4 线程大样本基线并留有波动余量；如果硬件、样本规模或线程配置变化，需要先记录新基线，再调整阈值。

性能门禁结果需要记录样本规模、`rust_threads`、`threshold_failures=[]`、总耗时、Rust 计划耗时、文件替换耗时和写后审计耗时。

`--rust-threads 4` 只是发布门禁的可重复基线，不是运行上限。真实翻译、验收、写回和当前运行审计流程应按 Skill 要求设置 `ATT_MZ_RUST_THREADS`，优先使用运行主机可用逻辑处理器数量；如果发布门禁也改用更高线程数，必须同步记录新基线并调整阈值。

## 协作模块

- 开发版 Skill 位于 `skills/att-mz/SKILL.md`，用于源码环境中的翻译流程。
- 发行版 Skill 位于 `skills/att-mz-release/SKILL.md`，发布时改写为发行包内的 `skills/att-mz/SKILL.md`。
- 提示词位于 `prompts/`，正文翻译 prompt 不应暴露数据库字段、内部路径或程序定位细节。
- 测试目录按业务域覆盖 CLI、配置、Agent 工具箱、文本规则、翻译、术语、持久化和发布协议。

## 主要入口

- `.github/workflows/release.yml`
- `scripts/build_release.py`
- `skills/att-mz/SKILL.md`
- `skills/att-mz-release/SKILL.md`
- `prompts/text_translation_ja_to_zh_system.md`
- `prompts/text_translation_en_to_zh_system.md`
- `tests/`

## 测试覆盖

- `uv run basedpyright` 是 Python 静态类型交付红线。
- `uv run pytest` 是 Python 业务测试交付红线。
- 改到 Rust 或 PyO3 相关代码时执行 `cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` 和 `cargo test --manifest-path rust/Cargo.toml`。
- 改到 Skill、README、提示词或工作区协议时同步检查 `tests/test_skill_protocol.py`。
- 改到写文件、插件源码扫描、当前运行审计或性能脚本时，至少运行对应 benchmark 单测；发布前还要按上面的命令执行真实大样本性能门禁。
- 不要把私有样本路径写入仓库文件或 release workflow。
