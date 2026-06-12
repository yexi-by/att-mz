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
- GitHub Release 正文来自 `CHANGELOG.md` 中对应 tag 的版本段落。
- CI 中的类型检查、测试、构建和冒烟测试结果。
- 本地大样本性能基准 JSON 结果。

## 失败策略

- 本机执行发行版构建脚本会失败；正式发行版只能由 GitHub Actions 构建。
- 发布工作流先执行 `uv run basedpyright`、设置 `ATT_MZ_RUST_THREADS=1` 后执行 `uv run pytest -q -n 12 --dist=load --durations=30 --durations-min=0.5`、`cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` 和 `cargo test --manifest-path rust/Cargo.toml`，通过后才构建发行包。
- 发布工作流必须先从 `CHANGELOG.md` 提取当前 tag 的具体更新说明；找不到对应版本段落时停止发布，不能只使用 GitHub 自动生成的 Release notes。
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

该命令会复制样本和数据库到临时工作目录，把临时样本的 `data_origin/*.json` 复制回 `data/*.json`，再计时 `rebuild-active-runtime`，用于验证真实文件替换、Rust 计划、文件替换和写后审计热路径。阈值来自 4 线程大样本基线并留有波动余量；如果硬件、样本规模或线程配置变化，需要先记录新基线，再调整阈值。

性能门禁结果需要记录样本规模、`rust_threads`、`threshold_failures=[]`、总耗时、Rust 计划耗时、文件替换耗时和写后审计耗时。

`--rust-threads 4` 只是发布门禁的可重复基线，不是运行上限。真实翻译、验收、写回和当前运行审计流程应按 Skill 要求设置 `ATT_MZ_RUST_THREADS`，优先使用运行主机可用逻辑处理器数量；如果发布门禁也改用更高线程数，必须同步记录新基线并调整阈值。

小任务链路改到索引、导入、重置、质量报告或小批翻译时，还要在持有样本的环境运行 warm index 小任务性能基准。失败时暂停发布：

```powershell
uv run python scripts/benchmark_small_tasks.py `
  --sample <样本游戏目录> `
  --game <游戏标题> `
  --db <数据库路径> `
  --runs 1 `
  --rust-threads 4 `
  --max-items 3 `
  --manual-item-count 100 `
  --max-quality-report-ms 10000 `
  --max-translate-ms 5000 `
  --max-import-ms 2000 `
  --max-reset-ms 1000
```

该命令会先重建文本范围索引，再依次计时普通 `quality-report`、`translate --max-items`、`import-manual-translations` 和 `reset-translations --input`。脚本默认启动本地假 OpenAI 兼容服务，并通过 `ATT_MZ_LLM_BASE_URL`、`ATT_MZ_LLM_API_KEY` 覆盖临时配置，不消耗真实模型额度；只有显式传入 `--allow-real-llm` 时才使用当前模型配置。结果需要记录每个 task 的 `elapsed_ms`、`return_code`、`report_status`、`report_index_status`、`stage_timings`、`native_thread_count`、`llm_mode=fake`、`threshold_failures=[]`、`command_failures=[]` 和 `command_warnings=[]`。用于该脚本的样本应是可重复的大样本副本，且脚本生成的手动译文能通过当前质量规则；如果样本故意包含质量错误，应先准备专门的合格基线输入，不要把质量错误误判成性能通过。

## 协作模块

- 开发版 Skill 位于 `skills/att-mz/SKILL.md`，用于源码环境中的翻译流程。
- 发行版 Skill 位于 `skills/att-mz-release/SKILL.md`，发布时改写为发行包内的 `skills/att-mz/SKILL.md`。
- 提示词位于 `prompts/`，正文翻译 prompt 不应暴露数据库字段、内部路径或程序定位细节。
- 测试目录按业务域覆盖 CLI、配置、Agent 工具箱、文本规则、翻译、术语和持久化；发布协议由 release workflow、生成检查、脚本检查和人工审查确认。

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
- 设置 `ATT_MZ_RUST_THREADS=1` 后执行 `uv run pytest -q -n 12 --dist=load --durations=30 --durations-min=0.5` 是当前 Python 业务测试交付红线；测试子集不能替代全量 pytest。
- 普通 push 和 pull request 不再自动执行常规 CI；发布工作流在构建发行包前执行 Python 静态类型检查和全量 pytest 门禁。
- 改到 Rust 或 PyO3 相关代码时执行 `cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings` 和 `cargo test --manifest-path rust/Cargo.toml`。
- 改到 Skill、README、提示词或工作区协议时，运行对应生成检查、静态检查或人工审查差异；不再用 pytest 固定这些文档和协议。
- 改到写文件、插件源码扫描、当前运行审计、小任务链路或性能脚本时，使用真实 CLI 性能证据和阶段耗时验证；不再用 benchmark pytest 代替真实性能门禁。
- 不要把私有样本路径写入仓库文件或 release workflow。
