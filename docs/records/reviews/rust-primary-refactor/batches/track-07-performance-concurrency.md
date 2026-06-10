# 轨道 07：性能与并发证据

## 范围

本轨道只读审查性能敏感路径和并发配置是否已经进入当前实现的可验收边界。范围覆盖：

- Rust 线程配置入口与 `rayon` 热路径。
- `rebuild-text-index`、`scan_rule_candidates`、质量检查、写入协议检查和 JS AST 批量解析的并发入口。
- scan budget 测试与既有性能记录。
- 当前仍需真实 CLI 计时证明的性能验收缺口。

本轨道未执行真实 CLI benchmark，未运行会写数据库、游戏目录、日志或输出报告的命令。

## 只读命令

```powershell
rg -n 'scan|full|all|walk|iter|collect|load_game_data|TextScopeService|build\(|for .* in|parallel|rayon|threads|ATT_MZ_RUST_THREADS|scan_budget|performance|timing|diagnostics' app rust/src tests docs/records/reviews/rust-migration docs/records/rust-scope-index
rg -n 'ATT_MZ_RUST_THREADS|rayon|ThreadPool|ThreadPoolBuilder|par_iter|join|spawn|threads|concurrency|parallel|num_threads' rust/src app tests
rg -n 'elapsed|ms|seconds|profile|benchmark|scan_budget|真实|性能|耗时|瓶颈|N\+1|全量|重复扫描' docs/records/reviews/rust-migration docs/records/rust-scope-index tests app rust/src
rg -n 'TextScopeService\.build|load_game_data\(|scan_plugin_source|scan_rule_candidates|build_native_.*payload|collect_.*rule|audit_coverage|quality_report|workflow_gate|prepare_agent_workspace|validate_agent_workspace' app tests rust/src
rg -n 'run_with_optional_pool\(|par_iter\(|into_par_iter\(' rust/src/native_core -g '*.rs'
Get-Content -Path 'rust\src\native_core\pool.rs'
Get-Content -Path 'rust\src\native_core\scope_index\mod.rs'
Get-Content -Path 'rust\src\native_core\javascript_ast.rs'
Get-Content -Path 'rust\src\native_core\quality\mod.rs'
Get-Content -Path 'rust\src\native_core\write_protocol.rs'
Get-Content -Path 'app\agent_toolkit\services\text_index.py'
Get-Content -Path 'tests\test_scan_budget.py'
Get-Content -Path 'tests\scan_budget_contract.py'
Get-Content -Path 'docs\records\reviews\rust-migration\non-network-cli-pressure-lessons.md'
Get-Content -Path 'docs\records\reviews\rust-migration\large-game-performance-defect-report.md'
```

## 结论

NEEDS_REVIEW

## 关键发现

### P2：性能验收仍缺当前 HEAD 的真实 CLI 计时闭环

- 证据：`tests/test_scan_budget.py:89` 到 `tests/test_scan_budget.py:115`
- 证据：`docs/records/reviews/rust-migration/non-network-cli-pressure-lessons.md:53` 到 `docs/records/reviews/rust-migration/non-network-cli-pressure-lessons.md:69`
- 证据：`docs/records/reviews/rust-migration/large-game-performance-defect-report.md:20` 到 `docs/records/reviews/rust-migration/large-game-performance-defect-report.md:32`
- 业务事实：性能验收、扫描预算、真实 CLI 墙钟耗时。
- 违反原则：性能并发
- 影响：当前 scan budget 测试能证明旧重型路径没有重新接入默认路径，但不能证明用户实际等待时间已经下降；后续 Rust 主路径重构如果只引用预算表，可能把 Python 启动、配置加载、JSON 输出、文件写入、manifest 生成和日志初始化成本漏掉。
- Python/Rust 职责判断：Rust 应继续承担 CPU 密集扫描、质量检查、候选扫描和写回计划；Python 可以保留 CLI 编排与报告组装，但性能验收必须用真实 CLI 计时证明 Python 编排层没有重新成为瓶颈。
- 建议 Rust 接管点：无新增接管点；本项是验收证据缺口。后续重构触及任一全量扫描或跨命令流程时，应采集对应命令的真实 CLI 耗时和 Rust internal stage timings。
- 应删除或瘦身的 Python 逻辑：本轨道未确认新的 Python 删除对象；如后续真实 CLI 计时显示 Python 编排阶段占比异常，再按命令定位删除或瘦身对象。
- 禁止采用的错误修复方向：禁止把 `scan_budget`、理论复杂度或旧性能报告当成当前 HEAD 的真实性能通过证据。
- 后续验证：对 `rebuild-text-index`、`quality-report`、`audit-coverage`、`prepare-agent-workspace`、`validate-agent-workspace`、`audit-active-runtime`、`diagnose-active-runtime` 至少采集一次当前 HEAD 的真实 CLI 计时；同时记录 `diagnostics.timings`、Rust internal stage timings、扫描文件数和输出体积。

## 双事实来源清单

- 未确认新的性能事实双源。当前代码侧有两类事实需要在总报告中区分：
  - 静态/预算事实：`tests/test_scan_budget.py:89` 到 `tests/test_scan_budget.py:115` 固定每类重型动作次数上限。
  - 历史真实性能事实：`docs/records/reviews/rust-migration/large-game-performance-defect-report.md:20` 到 `docs/records/reviews/rust-migration/large-game-performance-defect-report.md:32` 是过去采样，不应直接等同当前 HEAD。

## Rust 主路径缺口

- 未确认当前 Rust 并发入口缺失。已查到的主路径接入包括：
  - `rust/src/native_core/pool.rs:15` 到 `rust/src/native_core/pool.rs:35` 用局部 Rayon 线程池执行任务。
  - `app/utils/config_loader_utils.py:90` 到 `app/utils/config_loader_utils.py:93` 在配置加载后调用原生线程配置。
  - `rust/src/native_core/scope_index/mod.rs:328` 到 `rust/src/native_core/scope_index/mod.rs:343` 将 scope index 构建、候选扫描和 gate 评估包进线程池。
  - `rust/src/native_core/javascript_ast.rs:115` 到 `rust/src/native_core/javascript_ast.rs:128` 批量 JS AST 解析使用 `par_iter` 并受线程池包装。
  - `rust/src/native_core/quality/mod.rs:65` 到 `rust/src/native_core/quality/mod.rs:89` 质量检查各类明细并行扫描并受线程池包装。
  - `rust/src/native_core/write_protocol.rs:14` 到 `rust/src/native_core/write_protocol.rs:46` 写入协议检查和计数受线程池包装。

## Python 删除候选

- 本轨道未确认新的 Python 删除候选。
- 已查到工作区插件源码规则校验复用上下文，避免重扫 AST：`app/agent_toolkit/services/workspace.py:1743` 到 `app/agent_toolkit/services/workspace.py:1796`。
- 已查到当前运行插件源码审计使用文件 hash 缓存和未命中文件批量扫描：`app/plugin_source_text/runtime_audit.py:339` 到 `app/plugin_source_text/runtime_audit.py:410`。

## 测试缺口

- 缺当前 HEAD 的真实 CLI 性能验收记录。`tests/test_scan_budget.py:89` 到 `tests/test_scan_budget.py:115` 只证明预算表覆盖和动作次数上限；`docs/records/reviews/rust-migration/non-network-cli-pressure-lessons.md:53` 到 `docs/records/reviews/rust-migration/non-network-cli-pressure-lessons.md:69` 明确说明 scan budget 不能替代真实 CLI 证据。
- 后续性能敏感重构应同时保留行为测试、scan budget 保护和真实 CLI 计时，而不是只新增静态预算。

## 交叉引用

- 轨道 02 应复核 Rust 主路径缺口是否还有 CPU 密集逻辑留在 Python。
- 轨道 04 应复核 active runtime scan cache、text index metadata 和 workflow gate fast path 是否会绕过当前事实源。
- 轨道 05 应复核 scan budget 测试是否只固定外部可观察行为，而不是固定旧实现形状。

## 已查无发现范围

- 未发现 `runtime.rust_threads` 配置链路缺失：配置读取、Python native adapter 和 Rust 线程池入口均可定位。
- 未发现 scope index、JS AST 批量解析、质量检查、写入协议检查这几类 Rust 热路径缺少线程池包装。
- 未确认当前 HEAD 仍存在历史性能报告中的 P0/P1 性能缺陷；历史报告只作为性能风险样本和真实 CLI 证据格式参考。
