# 批次 10：发行、构建与历史记录降级

## 范围

- `.github/`
- `scripts/`
- `CHANGELOG.md`
- `docs/archive/`
- `docs/records/`
- `tests/test_release_package_layout.py`
- `tests/test_release_notes.py`

## 事实源

- 发行工作流事实源：`.github/workflows/release.yml`。
- 发行包布局事实源：`scripts/build_release.py` 与 `tests/test_release_package_layout.py`。
- GitHub Release 正文事实源：`CHANGELOG.md`、`scripts/extract_release_notes.py` 与 `tests/test_release_notes.py`。
- Skill 生成事实源：`scripts/generate_skill_protocol.py` 读取 `skills/att-mz-protocol/` 并生成开发版/发行版 Skill；本批只检查脚本引用关系，不读取 Skill 源。
- 历史记录事实源：`docs/archive/` 与 `docs/records/` 只按历史材料审查；除非反向喂给当前发行、测试或文档事实源，否则降级处理。

## 只读命令

1. `rg -n 'legacy|deprecated|fallback|compat|old|stale|migration|archive|history|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|版本|过期|真实路径|本机路径' .github scripts CHANGELOG.md docs/archive docs/records tests/test_release_package_layout.py tests/test_release_notes.py`
   - 结果：退出码 0。命中主要集中在 `CHANGELOG.md` 的发布说明、`docs/archive/` 与 `docs/records/` 的历史记录、性能脚本的缓存/阈值字段，以及 `tests/test_release_notes.py` 的发布说明断言。
2. `rg -n 'release|package|zip|copy|include|exclude|skill|README|CHANGELOG|dist|source|tests|logs|data' .github scripts tests/test_release_package_layout.py tests/test_release_notes.py`
   - 结果：退出码 0。命中发行工作流、发行包脚本、发布说明脚本和两份发行测试；未发现发行包显式包含源码、测试、开发态 Skill 或历史记录目录。
3. 报告写出后执行：`$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-10-release-build-history-records.md' -Pattern $patterns`

## 结论

NEEDS_REVIEW

## 发现

### P2：发布说明测试把日期设计文档当作当前 fact domain 事实源

- 证据：`tests/test_release_notes.py:83`
- 证据：`tests/test_release_notes.py:85`
- 证据：`tests/test_release_notes.py:90`
- 证据：`tests/test_release_notes.py:92`
- 违反准则：测试失忆化 | 文档分层
- 影响范围：`test_text_fact_v2_design_keeps_runtime_literal_out_of_current_domains` 用 `docs/superpowers/specs/2026-06-07-text-fact-contract-v2-design.md` 判断“当前 v2 fact domain 列表”。该路径是日期命名设计文档，不在本批允许承载历史形态的 `CHANGELOG.md`、发布说明、`docs/archive/` 或 `docs/records/` 内；测试把它作为当前契约事实源后，后续发布说明或 fact domain 调整可能被历史设计稿结构锁住。
- 建议收束：确认该设计文档是否仍是当前契约。如果是当前契约，应迁到明确的当前事实源并让测试断言机器可观察边界；如果只是设计记录，应停止由发布说明测试读取它，改为检查当前运行时、schema、Skill 生成物或正式文档中的当前契约表达。
- 后续验证：清理后运行 `uv run pytest tests/test_release_notes.py`，并执行 `rg -n 'docs/superpowers|2026-06-07-text-fact-contract-v2-design' tests/test_release_notes.py scripts .github CHANGELOG.md` 确认发行测试不再依赖日期设计记录作为当前事实源。

## 交叉引用

- `docs/records/reviews/contract-amnesia/batches/batch-03-text-fact-index-scope.md:20` 已记录 Text Fact Contract v2 的当前事实身份边界。
- `docs/records/reviews/contract-amnesia/batches/batch-04-workspace-rules-agent-toolkit.md:116` 已提示 v2 contract/version 文案后续需结合用户文案规范判断。
- `docs/records/reviews/contract-amnesia/batches/batch-05-translation-llm-prompt-quality.md:76` 已记录测试语义中保留旧来源模型的风险。
- `docs/records/rust-scope-index/batches/batch-126.md:57` 已覆盖 `export-plugins-json`、README、Skill 与 docs 当前边界的历史闭环记录；本批未发现它反向成为发行事实源。

## 已查无发现范围

- `.github/workflows/release.yml`：只从 `CHANGELOG.md` 提取 tag 对应发布说明，执行 type check、pytest、Rust fmt/clippy/test 后调用 `scripts/build_release.py` 生成并上传 Windows ZIP；未发现引用 `docs/archive/` 或 `docs/records/` 作为当前发布事实源。
- `scripts/build_release.py`：发行包资源复制范围为 README、许可证、配置模板、提示词、字体、发行版 Skill、必要 reference 和空数据/日志/输出目录；未发现复制源码目录、测试目录、Rust 源码、GitHub 工作流、开发态 Skill 或历史记录目录。
- `scripts/extract_release_notes.py`：仅从 `CHANGELOG.md` 按 tag 提取发布正文，并校验非空、非空泛、有验证命令和发行包下载信息；历史形态仍限制在更新日志/发布正文语境。
- `scripts/generate_skill_protocol.py`：脚本读取 canonical protocol 并写出开发版/发行版 Skill，未发现从 `docs/archive/` 或 `docs/records/` 生成当前 Skill。
- `scripts/benchmark_rebuild_active_runtime.py`、`scripts/benchmark_active_runtime_audit.py`、`scripts/benchmark_small_tasks.py`：本批未运行这些脚本；静态审查未发现历史记录目录反向参与当前发行或 Skill 生成。
- `CHANGELOG.md`：命中的旧形态描述处于更新日志/发布说明语境，按本批规则允许保留；未发现被构建脚本当作 runtime/schema 当前事实源，除 GitHub Release 正文提取外无额外污染路径。
- `docs/archive/` 与 `docs/records/`：大量命中属于历史审查、迁移记录和阶段记录；本批未发现发行工作流、发行脚本或发行包布局测试读取这些目录。
- `tests/test_release_package_layout.py`：发行包布局测试覆盖发行 Skill 重命名、reference 同步、空运行目录保留，以及 `app`、`tests`、`rust`、`.github`、`.git`、`skills/att-mz-release`、`skills/att-mz-protocol` 不进入发行包；未发现历史兼容路径。
- `tests/test_release_notes.py`：除上述 P2 需复核点外，CHANGELOG/README 相关断言仍围绕当前发布说明、当前文本事实契约命令入口和 release notes 质量门槛。
