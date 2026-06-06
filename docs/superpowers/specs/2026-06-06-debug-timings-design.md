# Debug 模式统一计时诊断设计

## 背景

本项目已有全局 `--debug`，但目前主要作用是调整终端日志等级。计时能力已经分散存在于 CLI 总耗时、部分 `summary.stage_timings`、Rust `timings_ms`、文本索引 `internal_stage_timings`、写回摘要字段和性能脚本中。这些字段能帮助排查问题，但出口分散、粒度不一致，也会在日常报告中暴露调试信息，增加后续维护成本。

新的 debug 模式第一项功能是统一计时诊断。它服务三类场景：

- 用户定位命令慢在哪个大阶段。
- 开发者诊断高压性能回退和隐藏逻辑问题。
- Agent 读取稳定 JSON 后自动判断下一步排障方向。

## 目标

- 建立统一 debug 配置域，而不是把 debug 当成单个布尔开关。
- 建立统一 `DiagnosticsContext` 和 `TimingCollector`，收束散落计时。
- debug logging 开启时，现有 DEBUG 日志由统一 debug 域控制，不再由零散 `--debug` 行为控制。
- debug timings 开启时，在 stdout JSON 报告中追加简短诊断摘要，并为每次 CLI 运行写出一个完整诊断 JSON 文件。
- 普通模式不再输出原有散落计时字段，避免日常使用出现意外调试信息。
- 第一版覆盖 L0 命令级、L1 关键阶段级、关键 L2 重资源指标，禁止默认 per-row、per-text、per-candidate 明细计时。
- 顶层诊断 schema 半稳定：顶层字段和 P0 关键阶段稳定，非关键内部阶段允许随实现演进。

## 非目标

- 第一版不做事件总线式 observability。
- 第一版不记录完整 prompt、模型响应、游戏原文、译文正文或逐条 `location_path`。
- 第一版不做默认 L3 细粒度明细诊断。
- 第一版不修改 Rust 计时输出 schema；优先桥接现有 Rust `timings_ms` 和 `internal_stage_timings`。

## 配置与优先级

配置文件新增 debug 域：

```toml
[debug]
enabled = false

[debug.logging]
enabled = true
console_level = "DEBUG"
file_level = "DEBUG"

[debug.timings]
enabled = true
write_file = true
include_summary_in_report = true
detail_level = "standard"
```

字段语义：

- `debug.enabled`：本次是否进入 debug 模式。
- `debug.logging.enabled`：是否启用 debug 日志输出控制。
- `debug.logging.console_level`：debug 模式下终端日志等级。
- `debug.logging.file_level`：debug 模式下文件日志等级。
- `debug.timings.enabled`：是否启用统一计时诊断。
- `debug.timings.write_file`：是否写完整诊断 JSON 文件。
- `debug.timings.include_summary_in_report`：是否在 stdout JSON 报告中追加摘要。
- `debug.timings.detail_level`：第一版只支持 `standard`，保留扩展空间。

CLI 新增或调整：

- `--debug`：本次进入 debug 模式。
- `--no-debug`：本次关闭 debug 模式。
- `--debug-logging`：本次强制开启 debug 日志。
- `--no-debug-logging`：本次强制关闭 debug 日志。
- `--debug-timings`：本次强制开启计时诊断。
- `--no-debug-timings`：本次强制关闭计时诊断。

环境变量：

- `ATT_MZ_DEBUG=1|0`
- `ATT_MZ_DEBUG_LOGGING=1|0`
- `ATT_MZ_DEBUG_TIMINGS=1|0`

优先级：

```text
debug 总开关：CLI --debug/--no-debug > ATT_MZ_DEBUG > setting.toml debug.enabled > 默认值
logging 子功能：CLI --debug-logging/--no-debug-logging > ATT_MZ_DEBUG_LOGGING > setting.toml debug.logging.enabled > 默认值
timings 子功能：CLI --debug-timings/--no-debug-timings > ATT_MZ_DEBUG_TIMINGS > setting.toml debug.timings.enabled > 默认值
```

`--debug` 只覆盖 debug 总开关，不覆盖 `debug.logging.enabled` 或 `debug.timings.enabled`，也不强制开启全部 debug 子功能。只有 debug 总开关和对应子功能同时开启时，对应 debug 能力才生效。

普通模式下终端日志等级保持 `INFO`。文件日志也不再默认记录 DEBUG 级排障细节；未知异常的完整 traceback 仍通过 ERROR 级文件日志写出。debug logging 开启时，终端和文件日志等级使用 `debug.logging.console_level` 与 `debug.logging.file_level`。

## 运行时架构

新增统一诊断运行时，建议模块为 `app.observability.diagnostics`。

核心对象：

- `DebugRuntimeSettings`：合并 CLI、环境变量、配置文件和默认值后的 debug 运行配置。
- `DiagnosticsContext`：每次 CLI 运行创建一个，包含 run id、命令名、开始时间、结束状态、诊断文件路径和收集器。
- `TimingCollector`：记录阶段耗时、外部桥接耗时、关键计数和产物路径。
- `DebugLoggingSettings`：集中决定终端日志等级、文件日志等级和 DEBUG 级内容是否生效。
- `NoopDiagnosticsContext`：普通模式使用，业务代码无需判断 debug 是否开启。

业务代码接入方式：

```python
with diagnostics.stage("quality.read_rules"):
    event_rules = await session.read_event_command_text_rules()
```

已有计时桥接方式：

```python
diagnostics.record_timing("quality.native_quality", stage_timings["native_quality"])
diagnostics.counter("quality.native_quality_payload_item_count", len(native_quality_items))
```

Rust 计时桥接方式：

```python
for name, value in plan.timings_ms.items():
    diagnostics.record_timing(f"write_back.rust_plan.{name}", value)
```

边界规则：

- `DiagnosticsContext` 由 CLI 入口创建，最终也由 CLI 入口 finalize。
- P0 主路径优先显式传递诊断上下文。
- 不允许业务模块自己决定是否向公开报告塞计时字段；报告层统一注入 diagnostics 摘要。
- 普通模式下 no-op 对象不写文件、不改 stdout 报告、不输出计时日志。
- 现有 `logger.debug(...)` 调用可以保留，但是否输出由统一 debug logging 配置控制。

## 输出契约

每次 CLI 运行最多写一个完整诊断文件：

```text
logs/diagnostics/<timestamp>-<command>-<run_id>.json
```

完整诊断 JSON 顶层结构：

```json
{
  "schema_version": 1,
  "run_id": "20260606-153012-quality-report-a1b2c3",
  "command": "quality-report",
  "status": "ok",
  "exit_code": 0,
  "started_at": "2026-06-06T15:30:12+08:00",
  "finished_at": "2026-06-06T15:30:15+08:00",
  "duration_ms": 3120,
  "debug": {
    "enabled": true,
    "source": "cli",
    "logging_enabled": true,
    "logging_source": "setting",
    "timings_enabled": true,
    "timings_source": "setting"
  },
  "environment": {
    "native_thread_count": 8,
    "cwd": "<项目目录>"
  },
  "timings": {
    "command.total": 3120,
    "quality.read_index_and_state": 20,
    "quality.read_rules": 12,
    "quality.build_index_scope": 44,
    "quality.native_quality": 1800
  },
  "counters": {
    "quality.native_quality_payload_item_count": 12000,
    "text_index.item_count": 50000
  },
  "artifacts": {
    "stdout_report_output": "<输出文件>",
    "log_file": "<日志文件>"
  },
  "warnings": []
}
```

稳定字段：

- `schema_version`
- `run_id`
- `command`
- `status`
- `exit_code`
- `started_at`
- `finished_at`
- `duration_ms`
- `debug`
- `environment`
- `timings`
- `counters`
- `artifacts`
- `warnings`

P0 关键 timing 名需要稳定，例如：

- `command.total`
- `text_index.rebuild.rust`
- `quality.native_quality`
- `translation.model_request`
- `translation.local_total_excluding_model`
- `write_back.rust_plan.total`
- `write_back.file_replacement`
- `write_back.post_write_audit`

stdout JSON 中只追加摘要：

```json
"diagnostics": {
  "enabled": true,
  "timings_enabled": true,
  "duration_ms": 3120,
  "slowest_timings": [
    {"name": "quality.native_quality", "duration_ms": 1800}
  ],
  "file": "logs/diagnostics/20260606-153012-quality-report-a1b2c3.json"
}
```

## 旧计时字段收口

本设计接受破坏性变更，目的是避免长期维护两套计时出口。

普通模式下不再输出以下类型的性能诊断字段：

- `elapsed_ms`
- `stage_timings`
- `rust_stage_timings`
- `timings_ms`
- `rust_plan_ms`
- `file_replacement_ms`
- `post_write_audit_ms`
- 其他只表达耗时的 summary 字段

debug timings 开启时，这些信息统一进入：

- stdout JSON 的 `summary.diagnostics` 摘要。
- 完整诊断 JSON 的 `timings`、`counters` 和 `artifacts`。

日志中的分段耗时也只在 debug timings 开启时输出。普通模式保留成功、失败、数量、下一步动作等业务摘要，不输出性能诊断细节。

## 已有 debug 行为收口

本次变更也纳入已有 debug 日志能力，避免后续继续维护旧 `--debug` 行为和新 debug runtime 两套机制。

破坏性收口规则：

- `--debug` 不再直接等同于“终端显示 DEBUG 日志”，而是进入统一 debug runtime。
- DEBUG 日志是否输出由 `debug.enabled` 与 `debug.logging.enabled` 共同决定。
- `logger.debug(...)` 只表达日志等级，不表达配置判断；业务代码不新增散落的 `if debug`。
- 普通模式下文件日志不再默认记录 DEBUG 级排障细节；完整异常 traceback 仍按 ERROR 级写入文件日志。
- 任务状态、写文件阶段、扫描细节、分段耗时等旧 DEBUG 内容，需要归类到 `debug.logging` 或 `debug.timings`，不得继续作为自由日志出口存在。
- 新增 debug 功能必须挂在 `[debug.<feature>]` 配置域下，并通过统一 debug runtime 生效。

## 覆盖范围

P0 深度覆盖：

- `rebuild-text-index`
- `quality-report`
- `translate`
- `write-back`
- `rebuild-active-runtime`
- `write-terminology`
- `run-all`

P0 覆盖 L0 命令级、L1 关键阶段级、关键 L2 重资源指标：

- Rust 线程数。
- 文本索引数量。
- native payload 条目数。
- GameData 加载次数。
- 扫描文件数和字节数。
- 写入计划文件数。
- 模型请求总等待。
- 文件替换耗时。
- 写后审计耗时。

P1 中等覆盖：

- `text-scope`
- `audit-coverage`
- `translation-status`
- `export-pending-translations`
- `export-quality-fix-template`
- `import-manual-translations`
- `reset-translations`
- `export-terminology`
- `import-terminology`
- `prepare-agent-workspace`
- `validate-agent-workspace`

P1 至少覆盖 L0 和 L1，关键计数能稳定取得时记录。

P2 基础覆盖：

- `list`
- `doctor`
- `add-game`
- 未列入 P0/P1 的规则导入、校验和候选扫描命令。

P2 只要求命令总耗时、退出状态和基础运行信息。后续发现性能风险再升级。

## 安全与体积边界

允许记录：

- 命令名。
- debug 来源。
- 退出码和状态。
- 阶段名和耗时。
- 计数、线程数、文件数量、字节数。
- 数据库路径、游戏路径、输出文件路径。
- 诊断文件路径和日志文件路径。

禁止记录：

- API key。
- 完整请求体。
- 完整 prompt。
- 模型响应正文。
- 游戏原文或译文正文。
- 逐条 `location_path` 列表。

大对象只记录数量、总字节数、hash/fingerprint 或脱敏后的少量文件名样本，不记录正文内容。

## 测试计划

必须补充以下测试：

- 配置 schema 支持 `[debug]`、`[debug.logging]` 和 `[debug.timings]`。
- CLI、环境变量、配置文件和默认值的优先级。
- `--debug` 不强制开启全部子功能，`--debug-logging` 和 `--no-debug-logging` 只覆盖日志功能，`--debug-timings` 和 `--no-debug-timings` 只覆盖计时功能。
- 普通模式下 DEBUG 日志不进入终端或文件日志；debug logging 开启时按配置等级输出。
- debug timings 开启时 stdout 报告含 `summary.diagnostics`。
- 普通模式不含旧计时字段，也不写诊断文件。
- 每次 CLI 运行只写一个完整诊断文件。
- 诊断 JSON 包含稳定顶层字段、`schema_version=1`、`command`、`duration_ms`、`timings`、`counters`。
- P0 桥接覆盖：
  - `rebuild-text-index` 记录文本索引和 Rust 阶段。
  - `quality-report` 记录质量报告关键阶段。
  - `translate` 记录模型请求、响应校验、保存和本地总耗时。
  - `write-back`、`rebuild-active-runtime`、`write-terminology` 记录 Rust 写回计划、文件替换和写后审计。
- 安全测试确认诊断 JSON 不包含 API key、prompt、模型响应、游戏正文、译文正文和逐条 `location_path`。

交付前必须执行：

```text
uv run basedpyright
uv run pytest
```

如果后续实现改动 Rust 计时输出结构，还必须执行 Rust 格式检查、clippy 和 Rust 测试。第一版优先桥接现有 Rust 字段，不要求改 Rust schema。

## 实施顺序建议

1. 增加 debug 配置 schema、环境变量读取和 CLI 覆盖解析。
2. 将现有 `--debug` 日志行为迁入统一 debug logging 配置。
3. 增加 `DiagnosticsContext`、`TimingCollector` 和 no-op 实现。
4. 在 CLI 入口创建和 finalize 诊断上下文。
5. 在报告层统一注入 `summary.diagnostics`。
6. 迁移并删除普通报告中的旧计时字段。
7. 接入 P0 主路径关键阶段和现有 Rust 计时桥接。
8. 接入 P1 命令 L0/L1。
9. 补齐安全测试、日志收口测试和普通模式无泄漏测试。

## 风险

- 移除旧计时字段是破坏性变更，已有测试和脚本需要同步更新到 `summary.diagnostics` 或完整诊断 JSON。
- P0 主路径较多，第一轮实现应避免顺手重构业务逻辑，只收口计时出口和关键记录点。
- 诊断文件体积需要持续关注，禁止把 L3 明细默认纳入统一 debug timings。
