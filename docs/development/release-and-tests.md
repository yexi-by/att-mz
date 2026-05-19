# 发布与测试

## 职责

发布与测试文档覆盖发行包构建、Skill 分发、提示词、GitHub Actions 和自动化测试。正式发行包只由 GitHub Actions `release` 工作流生成。`scripts/build_release.py` 负责发布目录、可执行文件、发行版 README、发行版 Skill、字体、提示词和空数据目录的包装。

## 输入

- GitHub Actions 触发标签或手动输入的发布标签。
- 源码仓库中的配置模板、字体、提示词、发行版 Skill 和发布 README。
- Python、Rust 和测试依赖。

## 输出

- `att-mz-windows-x86_64.zip`。
- 发行包内的 `att-mz.exe`、`README.md`、`setting.toml`、`skills/att-mz/SKILL.md`、字体、提示词和空数据目录。
- CI 中的类型检查、测试、构建和冒烟测试结果。

## 失败策略

- 本机执行发行版构建脚本会失败；正式发行版只能由 GitHub Actions 构建。
- 发布工作流先执行 `uv run basedpyright` 和 `uv run pytest`，通过后才构建发行包。
- 发行包冒烟测试必须验证 `att-mz.exe --help` 和空注册表读取。

## 协作模块

- 开发版 Skill 位于 `skills/att-mz/SKILL.md`，用于源码环境。
- 发行版 Skill 位于 `skills/att-mz-release/SKILL.md`，发布时改写为发行包内的 `skills/att-mz/SKILL.md`。
- 提示词位于 `prompts/`，正文翻译 prompt 不应暴露数据库字段、内部路径或程序定位细节。
- 测试目录按业务域覆盖 CLI、配置、Agent 工具箱、文本规则、翻译、术语、持久化和发布协议。

## 主要入口

- `.github/workflows/release.yml`
- `scripts/build_release.py`
- `skills/att-mz/SKILL.md`
- `skills/att-mz-release/SKILL.md`
- `prompts/text_translation_system.md`
- `tests/`

## 测试覆盖

- `uv run basedpyright` 是 Python 静态类型交付红线。
- `uv run pytest` 是 Python 业务测试交付红线。
- 改到 Rust 或 PyO3 相关代码时执行 `cargo fmt -- --check`、`cargo clippy --all-targets -- -D warnings` 和 `cargo test`。
- 改到 Skill、README、提示词或工作区协议时同步检查 `tests/test_skill_protocol.py`。
