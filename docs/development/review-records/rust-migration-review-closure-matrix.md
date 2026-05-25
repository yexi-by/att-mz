# Rust 迁移 Review Finding 闭环矩阵

## 说明

本矩阵用于跟踪 `rust-migration-review-final-report.md` 中每个 finding 的当前处理状态。它是长期修复 goal 的收口检查清单，不表示 goal 已完成。

状态定义：

- `已闭环`：已有实现、测试或动态验证证据，当前没有已知剩余动作。
- `部分闭环`：核心实现已完成，但仍缺少真实大样本、CI、完整 profile 或最终验收证据。
- `未闭环`：仍需要实现、验证或用户决策。

## 当前全量检查快照

2026-05-25 当前工作区已执行一次本地全量 Python/Rust 检查；2026-05-26 在 P2-17 阶段进度、P2-9 性能门禁脚本和 Skill 线程策略收口后已复跑本地全量检查：

- `uv run basedpyright`：通过，0 error，0 warning。
- `uv run pytest`：通过，523 passed，耗时 77.31s。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`：通过。
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`：通过。
- `cargo test --manifest-path rust/Cargo.toml`：通过，59 passed。
- `uv run python -m py_compile scripts/benchmark_rebuild_active_runtime.py scripts/benchmark_active_runtime_audit.py`：通过。
- `git diff --check`：通过；仅输出当前工作区 LF/CRLF 换行转换警告，没有空白错误。

Workflow 证据：`release.yml` 已在当前工作区加入 Rust fmt、clippy、test；本分支不是主分支，不把实际触发 release workflow 或创建 GitHub Release 当作修复 goal 前置。真实大样本等价门禁已在本机副本通过；性能验证保留本地 benchmark 脚本，不再引入自托管 workflow 证据治理。

说明：该快照证明当前本地检查链路通过，但不替代后续变更后的最终复跑；发布分支或主分支仍应按发布流程执行对应 workflow。

## Finding 覆盖审计

- `rust-migration-review-final-report.md` 中的 28 个 finding 已全部进入本矩阵：P1 4 项、P2 17 项、P3 7 项。
- 当前矩阵没有额外虚构 finding，也没有遗漏 final report 中的编号。
- 状态判定以当前工作区证据为准；本分支只要求 workflow 文件、脚本、文档、测试和本地等价门禁可验证，不要求实际发布。

## P1 阻断项

| Finding | 当前状态 | 已有证据 | 剩余动作 |
| --- | --- | --- | --- |
| P1-1 写入后当前运行文件审计退化 | 已闭环 | 第 1 轮恢复写入后 active runtime 审计，`post_write_audit_ms` 改为真实写后审计耗时；第 2 轮补摘要字段测试；2026-05-26 本地全量 Python/Rust 检查通过。 | 无。 |
| P1-2 Release CI 未执行 Rust 交付红线 | 已闭环 | release workflow 增加 Rust fmt、clippy、test；发布文档和协议测试固定三条 Rust 命令及执行顺序；发行包压缩前 smoke gate 已有测试；2026-05-26 `tests/test_skill_protocol.py` 33 passed；本分支不是主分支，不要求实际发包或触发发布 workflow。 | 无。 |
| P1-3 Rust native 写入范围边界不够 fail-fast | 已闭环 | Rust write plan 缺少 `allowed_translation_paths` 时直接失败；测试 helper 已补齐当前契约；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P1-4 `add-game` 已有可信源快照时 JSON 分类错误 | 已闭环 | `add-game --json` 可信源快照冲突改为 `business_error`；`tests/test_cli_json_output.py::test_add_game_existing_source_snapshot_reports_business_error` 覆盖该分类；2026-05-26 `uv run pytest` 523 passed。 | 无。 |

## P2 主要问题

| Finding | 当前状态 | 已有证据 | 剩余动作 |
| --- | --- | --- | --- |
| P2-1 旧 CLI 写入 gate 残留且测试仍依赖旧接口 | 已闭环 | 第 2 轮删除旧 CLI gate 与相关测试依赖，`rg` 无剩余旧 gate 引用；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-2 `run-all` 写入 gate 测试是弱证明 | 已闭环 | `run-all` 测试穿过真实 `write_back_for_handler()` 并进入 handler 写回入口；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-3 Rust plan 对结构化字段二次质检有覆盖风险 | 已闭环 | Rust 写回计划恢复插件配置、事件参数、Note 标签原字段语义；多行短文本测试覆盖；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P2-4 插件源码 runtime 映射缺少最终 AST 验证 | 已闭环 | Rust plan 保存 runtime map 前验证 selector 位于最终 AST 且 raw text 与写入文本一致；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P2-5 写入差异生成仍有全集读写成本 | 已闭环 | 已完成 diff 输出并行化、插件源码 diff 范围收窄、普通写回 data diff 范围收窄、origin data 按需读取；サキュバスアカデミア 大样本临时副本重置 137 个 data 文件后真实 `rebuild-active-runtime` 成功，4 线程 elapsed 68269ms，`planned_file_count=137`、`skipped_file_count=177`。 | 无。 |
| P2-6 Python 与 Rust 双重质量门禁 | 已闭环 | 写文件 handler 跳过 Python 侧重复原生质量和写入协议检查，由 Rust 计划执行最终 native gate；摘要新增 `pre_write_check_ms`；大样本实际替换 profile 记录 4 线程 `rust_plan_ms=22405`、`file_replacement_ms=328`、`post_write_audit_ms=8129`。 | 无。 |
| P2-7 测试缺少真实 CLI/handler/native 闭环 | 已闭环 | 已补 `write-back --json`、`rebuild-active-runtime --json` 摘要测试和 `rebuild-active-runtime` handler 级真实成功路径测试；2026-05-26 本地全量 Python/Rust 检查通过；サキュバスアカデミア 大样本临时副本穿过真实 CLI/handler/native plan/文件替换/写后审计并成功。 | 无。 |
| P2-8 `write-back` JSON 摘要缺少测试 | 已闭环 | `build_write_back_summary_report()` 字段语义测试固定 `pre_write_check_ms`、`rust_plan_ms`、`file_replacement_ms`、`post_write_audit_ms`；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-9 性能与并发缺少自动验收 | 已闭环 | Rust AST 热路径线程配置测试、benchmark 阈值脚本、当前运行审计真实样本缓存阈值验证已完成；线程配置单测固定 `ATT_MZ_RUST_THREADS=64` 高于 4 时仍合法；サキュバスアカデミア 大样本实际替换对照显示 4 线程 elapsed 68269ms，1 线程 elapsed 155495ms，线程配置真实影响热路径；`benchmark_rebuild_active_runtime.py --reset-active-data-from-origin` 已能强制验证真实替换路径；发布文档给出 4 线程阈值但明确 4 不是运行上限；开发版和发行版 Skill 要求长任务按主机逻辑处理器尽量设置 `ATT_MZ_RUST_THREADS`；正式门禁命令本地通过，elapsed 72785ms，`threshold_failures=[]`，重置并替换 137 个 data JSON。 | 无。 |
| P2-10 大规模插件源码 AST 重复解析且 Python 外层串行 | 已闭环 | Rust 批量 JS AST 入口、Rayon 并发、多处上下文复用、当前运行审计真实样本第二轮 55 hit / 0 rescan；大样本实际替换对照中 4 线程 Rust plan 22405ms、写后审计 8129ms，1 线程 Rust plan 63585ms、写后审计 18728ms；新增 CLI/benchmark 摘要指标并在サキュバスアカデミア大样本上记录源 AST 扫描 98 个文件、写后 AST 验证 98 个文件、runtime map 23799 条。 | 无。 |
| P2-11 工作区验收重复调用全量校验器 | 已闭环 | `validate-agent-workspace` 已复用插件源码扫描、普通占位符、结构化占位符、术语、事件规则、Note 标签等上下文；真实样本工作区验收复测耗时 12647ms，并输出 27 行阶段进度；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-12 文本范围构建默认执行写回探针 | 已闭环 | 只读路径默认 `include_write_probe=False`，需要写入探针时显式开启；报告输出 `write_back_probe_enabled`；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-13 状态查询不是轻量查询 | 已闭环 | `translation-status` 默认数据库快速路径；需要刷新范围时显式 `--refresh-scope`；サキュバスアカデミア 临时副本验证过刷新路径阶段输出，默认路径由测试覆盖。 | 无。 |
| P2-14 当前运行审计缺少可复用扫描结果 | 已闭环 | 当前运行扫描支持文件 hash 跨命令缓存，summary 输出缓存统计；真实样本审计第二轮 55 hit / 0 rescan；真实样本 `diagnose-active-runtime` 复用审计缓存，55 hit / 0 miss / 0 rescan；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-15 原生 Note 标签扫描重复执行 | 已闭环 | 工作区上下文复用阶段已减少 Note 来源和规则验收重复扫描；测试固定 `validate-agent-workspace` 不重新执行 Note 标签全量校验；真实样本工作区验收复测通过；2026-05-26 `uv run pytest` 523 passed。 | 无。 |
| P2-16 Python JSON 边界和深拷贝成本被放大 | 已闭环 | 已完成写回探针浅复制、JSON 收窄、只读 GameData 可写副本减重、AgentToolkit 只读加载减重、origin data 按需读取；Rust 写回计划真实写文件路径已把待写文件正文输出到临时 sidecar，Python 只校验并复制 sidecar 文件，不再让 137 个待写 data JSON 正文穿过 plan JSON；サキュバスアカデミア 大样本临时副本重置 137 个 data 文件后成功，elapsed 77080ms，`file_replacement_ms=425`；runtime map 23799 条仍跨边界返回是为了保存确定性诊断映射，当前不作为无关损耗。 | 无。 |
| P2-17 长任务进度缺少真实阶段 | 已闭环 | 写文件命令已有阶段状态回调和分段计时；`validate-agent-workspace`、`translation-status --refresh-scope`、`export-pending-translations`、`export-quality-fix-template` 已接入阶段进度并补测试；サキュバスアカデミア 临时副本验证显示刷新状态 17981ms、手动译文表导出 84306ms、质量修复表导出 23431ms，JSON 模式阶段输出进入 stderr；默认 `translation-status` 保持数据库快速路径，同时也输出轻量阶段。 | 无。 |

## P3 次要问题

| Finding | 当前状态 | 已有证据 | 剩余动作 |
| --- | --- | --- | --- |
| P3-1 `TextPlanRules` 对缺失布局字段使用默认值 | 已闭环 | Rust 关键布局字段缺失直接失败，测试载荷补齐必需字段；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P3-2 事件命令排序解析失败默认为 0 | 已闭环 | 事件路径编号解析失败直接报错；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P3-3 启用插件缺失名称时生成 `unnamed_plugin_{index}.js` | 已闭环 | 启用插件缺失 `name` 直接失败；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P3-4 缺失译文行仍存在空字符串兜底 | 已闭环 | Rust 写入协议缺失译文行、空白译文行、全空白译文行均 fail-fast；2026-05-26 `cargo test` 59 passed。 | 无。 |
| P3-5 `rebuild-active-runtime` 部分测试只验证 helper | 已闭环 | 已补 handler 级真实成功路径测试，穿过真实 native plan 和写后审计；サキュバスアカデミア 大样本临时副本实际替换 137 个 data 文件并成功。 | 无。 |
| P3-6 文档/注释仍有历史叙事残留 | 已闭环 | 已清理 `candidates_json()` docstring 和 `_decode_json_value()` 注释中的历史叙事。 | 无。 |
| P3-7 性能脚本包含本机样本路径默认值 | 已闭环 | benchmark 脚本要求显式 `--sample` 和 `--game`，不再带本机路径默认值；2026-05-26 benchmark 脚本语法检查和全量 pytest 通过。 | 无。 |

## 性能补充与动态验证

| 项目 | 当前状态 | 已有证据 | 剩余动作 |
| --- | --- | --- | --- |
| 当前运行审计缓存热路径 | 已闭环 | 真实样本 `頽廃のシスター` 两轮审计，第二轮 `active_runtime_scan_cache_hit_file_count=55`、`active_runtime_scan_cache_rescan_file_count=0`；同一样本 `diagnose-active-runtime` 预热后命中 55、miss 0、rescan 0。 | 无。 |
| benchmark 动态证据字段 | 已闭环 | benchmark 结果包含 `command`、`sample_stats`、`rust_threads`、每轮退出码和缓存指标。 | 无。 |
| 真实大样本成功写入性能基线 | 已闭环 | 使用 `data/db/サキュバスアカデミア.db` 的临时 v10 副本和真实样本副本完成两轮实际替换：4 线程 elapsed 68269ms，1 线程 elapsed 155495ms；每轮均重置并替换 137 个 data JSON，样本约 3.94GB。 | 无。 |
| 真实大样本性能阈值与本地自动化 | 已闭环 | 阈值已写入发布文档和本地 benchmark 脚本；发布文档明确 `--rust-threads 4` 只是门禁基线，不是运行上限；正式门禁命令使用サキュバスアカデミア临时副本通过，`threshold_failures=[]`，elapsed 72785ms，`rust_plan_ms=24555`，`file_replacement_ms=427`，`post_write_audit_ms=9314`，`active_data_reset_from_origin_count=137`。 | 无。 |
| GitHub Actions release workflow 文件验收 | 已闭环 | workflow 文件、文档和协议测试已覆盖 Rust gate 与 smoke gate；2026-05-26 `tests/test_skill_protocol.py` 33 passed；本分支不是主分支，不要求实际发包。 | 无。 |

## 当前 goal 状态

- `rust-migration-review-final-report.md` 的 28 个 finding 已全部进入闭环矩阵。
- 当前本地全量 Python/Rust 检查已通过；后续继续修改后仍需复跑并记录最新结果。
- 本分支不要求实际发包，也不要求真实调度 release workflow。
- 长期 goal 仍等待用户最终确认；未经用户明确允许，不调用 `update_goal(status="complete")`。
