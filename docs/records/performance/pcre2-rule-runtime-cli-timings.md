# PCRE2 统一规则运行时 CLI 性能证据

## 环境

- 日期：2026-06-11
- 平台：Windows 本机开发环境
- 运行方式：`uv run python main.py`
- 原生扩展：本机 `maturin develop` 后的 Rust/PyO3 dev build
- 配置：`ATT_MZ_HOME=<项目目录>/perf-app-home`，`setting.example.toml` 复制为 `setting.toml`

## 样本

- 样本来源：测试夹具生成的最小 RPG Maker MZ 项目，不使用真实用户项目。
- 游戏标题占位：`<游戏标题>`
- 游戏目录占位：`<项目目录>/mini-game`
- 工作区占位：`<工作区>`
- 数据规模：16 个 data JSON 文件，20 条 text fact。
- 规则规模：普通占位符规则 1 条，PCRE2 pattern 为 `\\\\F\[[^\]\r\n]+\]`，模板为 `[CUSTOM_FACE_{index}]`。

## 命令结果

| 命令 | 线程 | 总耗时 | rule_runtime.compile_ms | rule_runtime.scan_ms | rule_runtime.store_ms | JIT | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `uv run python main.py --debug-timings validate-placeholder-rules --game-path <项目目录>/mini-game --input <工作区>/placeholder-rules.json --output <工作区>/validate-placeholder-rules.json` | rule_runtime 1 | 1.261s | 0 | 0 | 0 | true | 成功，1 条 PCRE2 规则通过校验并生成 4 条预览样本。 |
| `uv run python main.py --debug-timings import-placeholder-rules --game-path <项目目录>/mini-game --input <工作区>/placeholder-rules.json` | rule_runtime 1 | 1.262s | 0 | 0 | 0 | true | 成功，导入 1 条规则，6 个候选全部覆盖，清理译文 0 条。 |
| `uv run python main.py --debug-timings rebuild-text-index --game-path <项目目录>/mini-game --output <工作区>/rebuild-text-index.json` | Rust native auto | 1.249s | N/A | N/A | N/A | N/A | 成功，重建 20 条 text fact，扫描 16 个 data 文件。 |
| `uv run python main.py --debug-timings quality-report --game-path <项目目录>/mini-game --output <工作区>/quality-report.json` | Rust native 12 | 1.217s | N/A | N/A | N/A | N/A | 命令完整执行并写出报告；因样本没有译文、术语和其他规则，按业务门禁返回 error。 |

## 瓶颈归因

- 该样本规模很小，CLI 总耗时主要来自 Python 进程启动、配置加载、数据库打开和报告渲染。
- rule_runtime prepare/commit 暴露的 `compile_ms`、`scan_ms`、`store_ms` 均为 0ms 量级，未在该样本上形成可观察瓶颈。
- `rebuild-text-index` 和 `quality-report` 的重活走 Rust native 主路径；这两个命令当前报告不暴露 rule_runtime 细分计时，因此表中对应列记为 N/A。

## 剩余风险

- 本次证据只覆盖最小夹具，不代表大型真实游戏吞吐上限。
- 当前 rule_runtime 诊断以毫秒整数展示，小样本下会被取整为 0；后续若要比较微小规则集差异，需要更大样本或更细粒度 profiling。
- `quality-report` 在无译文样本上返回业务 error 属于预期；本记录只用它证明质量报告路径可完成扫描与报告生成。
