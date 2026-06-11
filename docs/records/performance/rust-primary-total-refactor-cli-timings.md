# Rust 主路径重构 CLI 性能记录

记录日期：2026-06-11

## 测量范围

- 目标：为 Rust 主路径重构补充真实 CLI 计时证据，避免把 scan budget 当成性能成功依据。
- 夹具：仓库测试代码生成的最小 RPG Maker MZ 游戏夹具，标题为 `テストゲーム`。
- 夹具规模：`20` 条 current text facts，`20` 个 render parts，`16` 个扫描文件。
- 配置：临时应用目录使用 `setting.example.toml` 派生配置，`ATT_MZ_HOME=<临时应用目录>`。
- 诊断：命令启用 `--debug --debug-timings`，总耗时由 PowerShell `Measure-Command` 采集，内部阶段由 diagnostics JSON 采集。

## 执行命令

```powershell
$env:ATT_MZ_HOME = "<临时应用目录>"
Measure-Command {
  uv run python main.py --debug --debug-timings rebuild-text-index --game "テストゲーム" --output "<输出文件>"
}

Measure-Command {
  uv run python main.py --debug --debug-timings quality-report --game "テストゲーム" --output "<输出文件>"
}

$env:ATT_MZ_RUST_THREADS = "2"
Measure-Command {
  uv run python main.py --debug --debug-timings rebuild-text-index --game "テストゲーム" --output "<输出文件>"
}

Measure-Command {
  uv run python main.py --debug --debug-timings quality-report --game "テストゲーム" --output "<输出文件>"
}
```

`quality-report` 在该夹具上退出码为 `1`，原因是夹具没有导入译文、术语和规则，报告发现了业务问题；本记录把它作为带错误报告的真实计时样本，不把退出码 `1` 视为性能命令失败。

## 结果摘要

| 命令 | 线程配置 | 退出码 | CLI 总耗时 | 诊断总耗时 | 诊断线程数 | 扫描/输入计数 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `rebuild-text-index` | `runtime.rust_threads=auto` | 0 | 1318 ms | 193 ms | 12 | `scan_file_count=16`, `text_index.item_count=20` |
| `quality-report` | `runtime.rust_threads=auto` | 1 | 1248 ms | 138 ms | 12 | `text_fact_count=20`, `extractable_count=20`, `pending_count=20` |
| `rebuild-text-index` | `ATT_MZ_RUST_THREADS=2` | 0 | 1232 ms | 171 ms | 2 | `scan_file_count=16`, `text_index.item_count=20` |
| `quality-report` | `ATT_MZ_RUST_THREADS=2` | 1 | 1215 ms | 153 ms | 2 | `text_fact_count=20`, `extractable_count=20`, `pending_count=20` |

## 内部阶段

| 命令 | 线程配置 | Rust 阶段 | Python/编排阶段 | 最慢内部阶段 |
| --- | --- | ---: | ---: | --- |
| `rebuild-text-index` | `auto` | `text_index.rebuild.rust=64 ms` | `text_index.rebuild.load_config_and_rules=116 ms` | `build_workflow_gate_metadata=35 ms`, `workflow_gate_placeholder_hash=19 ms`, `write_storage=10 ms` |
| `quality-report` | `auto` | `quality.native_quality=9 ms` | `quality.total=29 ms` | `quality.build_index_scope=10 ms`, `quality.read_index_and_state=4 ms`, `quality.read_rules=1 ms` |
| `rebuild-text-index` | `ATT_MZ_RUST_THREADS=2` | `text_index.rebuild.rust=57 ms` | `text_index.rebuild.load_config_and_rules=102 ms` | `build_workflow_gate_metadata=31 ms`, `workflow_gate_placeholder_hash=18 ms`, `write_storage=9 ms` |
| `quality-report` | `ATT_MZ_RUST_THREADS=2` | `quality.native_quality=10 ms` | `quality.total=30 ms` | `quality.build_index_scope=10 ms`, `quality.read_index_and_state=4 ms`, `quality.read_rules=2 ms` |

## 结论与风险

- `ATT_MZ_RUST_THREADS=2` 已真实进入运行配置，诊断里的 `runtime.native_thread_count` 从默认 `12` 变为 `2`。
- `rebuild-text-index` 真实扫描 `16` 个文件，生成并保存 `20` 条 current text facts；`quality-report` 复用现有文本索引，未触发重建扫描。
- 小夹具下 CLI 总耗时主要由 `uv`/Python 进程启动、导入和配置加载占据；诊断内总耗时约 `138-193 ms`，Rust 主阶段约 `57-64 ms`。
- 该记录只证明当前最小夹具的命令级表现和线程配置链路；大规模项目仍需要单独采集真实游戏样本，并重点观察 `text_index.rebuild.rust`、`build_workflow_gate_metadata`、`write_storage` 和 `quality.build_index_scope`。
