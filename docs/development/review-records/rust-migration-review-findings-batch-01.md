# Rust 迁移分支 Review Findings（第 1 批）

本文档记录 `codex/rust-writeback-hotpath` 相对 `main` 的第 1 批渐进式 review 结果。范围包含静态对照、测试覆盖检查和动态样本验证。本文档只记录问题、证据、影响和建议验证方向，不包含修复补丁。

## 总体结论

- 当前分支与 `main` 指向同一提交，迁移变更主要位于未提交工作区和未跟踪文件中。
- 工具链检查通过：`uv run basedpyright` 为 0 error、0 warning；`uv run pytest` 为 454 passed；`cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`、`cargo test --manifest-path rust/Cargo.toml` 均通过，Rust 测试 33 passed。
- 动态样本已验证：`D:\h-game\测试样本\已汉化\テイルズ・テイルス` 的临时副本可以注册和扫描，但存在规则与占位符阻断；临时目录已删除。
- 当前不建议合入。阻断原因是写入前质量 gate 和写回外部契约出现实质退化，动态样本已复现 `quality-report` 失败但 `write-back`、`rebuild-active-runtime` 返回 `ok`。

以上结论为 review 阶段记录；修复执行后的状态、命令和剩余风险见下一节。

## 修复状态（2026-05-25）

| Findings | 状态 | 修复证据 |
| --- | --- | --- |
| R1-1、R4-1、R5-1、R6-1 | 已修复 | `write-back` 进入统一写文件前检查，覆盖流程前置、质量报告、完整译文、可信源快照和可写范围；新增 handler、CLI JSON 和动态样本回归。 |
| R1-2 | 已修复 | native 写回入口先加载会话游戏数据并校验可信源快照 manifest；缺失 manifest 的直接 handler 测试已覆盖。 |
| R1-3 | 已修复 | Rust 写回计划使用宽松 JSON5 解析 `$plugins` 数组；Rust 样例测试覆盖非严格插件配置。 |
| R1-4 | 已修复 | 新增直接 handler 阻断测试、CLI JSON 业务错误测试和 `run-all` 写回阶段硬检查测试。 |
| R2-1、R4-2、R5-2 | 已修复 | native 写回计划加入 `write_terminology` 模式；术语写入允许正文仍有还没成功保存译文的文本，但仍检查术语表、规则、可信源快照、写入目标和已保存译文质量。 |
| R2-2 | 已修复 | Rust plan 只纳入标准 RPG Maker MV/MZ data JSON；`UnknownPluginData.json` 跳过测试已覆盖。 |
| R2-3 | 已修复 | 插件源码计划构建会检查当前运行插件源码可读性，并对替换后的 JS 内容重新做 AST/语法扫描，失败时直接报错。 |
| R2-4 | 已修复 | 插件配置和 Note 标签写入复用可见文本协议外壳校验，破坏控制符或 JSON 字符串外壳时直接失败。 |
| R3-1 | 已修复 | 写回计划热路径纳入 `ATT_MZ_RUST_THREADS` 线程池包装，非法线程数在 write plan 路径可触发测试。 |
| R3-2 | 已修复 | Python native adapter 校验 `target_path` 必须位于游戏内容目录内，并拒绝绝对 `relative_path`、`..` 和目标不一致。 |
| R3-3、R4-3、R6-3 | 已修复 | native `status=error` 会保留错误消息；应用层硬检查在 `--json` 下返回 `business_error`；Rust 用户文案使用“文本在游戏里的内部位置”。 |
| R5-3 | 已修复 | Rust/Python 边界补齐非标准 data、线程配置、路径越界、native error payload 和等价写回样例测试。 |
| R6-4、R6-5 | 已记录为动态验证限制 | 未导入规则的样本仍不能触发真实模型调用；非 MV/MZ 样本继续跳过，不作为修复缺陷。 |

## 修复后验证命令记录（2026-05-25）

已执行并通过：

```powershell
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
uv run basedpyright
uv run pytest
```

验证结果：

- `cargo test --manifest-path rust/Cargo.toml`：38 passed。
- `uv run basedpyright`：0 errors、0 warnings、0 notes。
- `uv run pytest`：462 passed。

动态样本回归：

- 样本源：`D:\h-game\测试样本\已汉化\頽廃のシスター`。
- 临时副本：`C:\Users\夜袭\AppData\Local\Temp\att-mz-dynamic-fix-74a4173ae66d4c83b8b50cbe0f50529c\game`。
- 临时 `ATT_MZ_HOME`：同一临时目录下的 `home`。
- 执行命令：`add-game`、`doctor --no-check-llm`、`scan-placeholder-candidates`、`text-scope`、`quality-report`、`write-back`、`rebuild-active-runtime`、`translate --json --max-items 3 --max-batches 1 --time-limit-seconds 300 --translation-worker-count 1`。
- 结果：`quality-report` 退出码 1，`status=error`，`code=coverage_missing_translation`，报告 12577 条当前可写文本还没成功保存译文；`write-back`、`rebuild-active-runtime`、`translate` 均退出码 1，`status=error`，`code=business_error`，在模型调用和写文件前停止。
- 写入校验：`data/System.json` 和 `js/plugins.js` 哈希未变化。
- 清理校验：临时目录已删除，`Exists=false`。

剩余风险：

- 本轮动态验证没有进行真实模型调用，因为样本规则和译文覆盖不满足启动条件。
- 本轮动态验证覆盖未准备样本的 fail-fast 语义，没有验证一个规则、译文、质量报告全部完成的大样本真实写入成功路径。

当前实现位置：

- Rust 写回计划稳定入口：`rust/src/native_core/write_back_plan/mod.rs`。
- 写回计划职责模块：`rust/src/native_core/write_back_plan/*.rs`。
- 下方各轮 evidence 保留第 1 批 review 发生时的路径和行号，用于追溯当时证据。

## 第 1 轮：变更地图与阻断风险

### R1-1 [P0] 普通 `write-back` 绕过写入前硬检查

发现：当前 `_write_back_with_native_fast_gate()` 没有调用 `assert_workflow_gate_passed`、`assert_write_back_quality_passed(require_complete_translation=True)` 和 `_filter_writable_translation_items`。

证据：
- 当前 `app/application/handler.py:830` 进入 native 写回快路径。
- `main:app/application/handler.py` 的 `write_back` 在写入前执行 workflow gate、写入质量 gate 和可写范围过滤。
- 当前 `app/application/write_back_gate.py:80` 仍定义 pending、stale 等写入前错误，但 CLI/handler 路由不再稳定触达。

影响：未保存译文、过期规则、不可写路径、源文残留等风险可能进入写回链路，导致游戏文件在不满足验收条件时被写入。

建议验证/修复方向：恢复或等价实现完整写入前 gate，增加 CLI 端到端测试确认 `quality-report` 错误会阻止 `write-back`。

### R1-2 [P1] native 写回未校验可信源快照 manifest

发现：当前 `_write_back_with_native_fast_gate()` 和 `_rebuild_active_runtime_with_native_plan()` 没有调用 `_load_session_game_data()`，因此没有执行 source snapshot manifest 校验。

证据：
- 当前 `app/application/handler.py:230` 的 manifest 校验只在 `_load_session_game_data()` 内执行。
- 当前 native 写回路径直接调用 Rust plan，Rust 侧 `rust/src/native_core/write_back_plan.rs:503` 读取 origin 目录，但没有使用数据库 manifest 做完整性校验。

影响：可信源快照缺失、损坏或被替换时，写回可能继续执行，破坏“从可信源快照重建”的外部语义。

建议验证/修复方向：native 写回入口必须先校验 manifest，或 Rust plan 读取并校验同等 manifest 记录。

### R1-3 [P1] `plugins_origin.js` 解析从 tolerant 退化为严格 JSON

发现：Rust plan 只抽取数组后用 `serde_json::from_str` 解析插件配置，不能覆盖 `main` 中 `demjson3.decode` 支持的非严格 JavaScript 写法。

证据：
- 当前 `rust/src/native_core/write_back_plan.rs:541` 的 `read_plugins_origin_file()` 使用 `serde_json::from_str`。
- `main:app/rmmz/loader.py` 使用 `demjson3.decode` 解析插件配置。

影响：真实 RPG Maker 插件配置里若存在非严格 JSON 结构，当前 Rust 路径会失败，属于兼容真实引擎文件格式能力退化。

建议验证/修复方向：为 Rust 路径补齐同等解析能力，或在注册阶段明确把插件配置规范化并测试固定。

### R1-4 [P1] 高风险 handler 入口测试覆盖不足

发现：新增测试主要覆盖 helper 或 fake native plan，没有覆盖普通 `write-back` CLI/handler 全链路 gate。

证据：
- `tests/test_rmmz_loader_extraction_writeback.py:169` 使用 fake native plan 测 helper。
- `tests/test_rmmz_loader_extraction_writeback.py:1239` 只覆盖 `write_terminology` 缺 workflow rules 的直接调用。

影响：写入前 gate 退化没有被测试挡住。

建议验证/修复方向：补 CLI 级、handler 级测试，覆盖 pending、质量错误、规则缺失和不可写路径。

## 第 2 轮：写回热路径静态 Review

### R2-1 [P0] `write-terminology` 错误套用完整正文写回条件

发现：`write-terminology` 仍是部分写入语义，但当前会进入 Rust `write_back` plan，Rust plan 无条件拒绝最新运行中未保存完的正文。

证据：
- 当前 `app/application/handler.py:1097` 的 `write_terminology()` 调用 `write_runtime_files_with_native_plan()`。
- 当前 `rust/src/native_core/write_back_plan.rs:245` 到 `270` 加载所有译文并调用 `ensure_no_latest_run_failures()`。
- 当前 `rust/src/native_core/write_back_plan.rs:854` 到 `876` 在 `total_extracted > saved_translation_count` 时返回错误。
- `main:app/application/handler.py` 中 `write_terminology` 使用 `assert_write_back_quality_passed(... require_complete_translation=False)`。

影响：正文没有全部保存时，本应允许写入稳定术语的流程会失败，属于外部命令行为退化。

建议验证/修复方向：增加 native 专用 terminology 模式，或把 `require_complete_translation=False` 传入 Rust plan 并测试。

### R2-2 [P1] Rust 写回会处理并覆盖非标准 data JSON

发现：Rust plan 读取 origin data 目录下所有 `.json`，没有沿用 loader 的标准 RMMZ 文件过滤。

证据：
- `app/rmmz/loader.py:132` 到 `140` 只加载标准 RMMZ 文件，`app/rmmz/loader.py:545` 定义 `_is_standard_rmmz_filename()`。
- `tests/test_rmmz_loader_extraction_writeback.py:247` 确认 `UnknownPluginData.json` 被跳过。
- `rust/src/native_core/write_back_plan.rs:503` 到 `525` 的 `read_origin_data_files()` 读取所有 `.json`。
- `rust/src/native_core/write_back_plan.rs:399` 到 `416` 会把所有 data files 生成计划文件。

影响：插件私有数据或非标准 JSON 可能被 Rust plan 格式化、重写或覆盖，扩大写回面。

建议验证/修复方向：Rust 侧复用标准文件白名单，并增加 `UnknownPluginData.json` 不进入写回计划的测试。

### R2-3 [P1] 插件源码缺少替换后的 AST 审计

发现：当前 Rust plan 在写插件源码时只检查原始源码和计划过程，Python handler 写入后不再执行 `main` 的当前运行文件 AST 审计。

证据：
- `main:app/application/handler.py` 写入后执行 `load_active_runtime_game_data()` 和 `_assert_active_plugin_source_runtime_audit_passed()`。
- `main:app/plugin_source_text/write_back.py` 会对替换后的 `content` 做 AST 检查。
- 当前 `rust/src/native_core/write_back_plan.rs:3379` 到 `3460` 的插件源码处理侧重原始 source 和替换映射。
- 当前 `app/application/handler.py:984` 写文件后只保存 runtime write maps。

影响：替换后的插件源码若产生语法错误、坏控制符或残留，可能不会在写回命令中 fail-fast。

建议验证/修复方向：恢复写入后 active runtime audit，或 Rust plan 生成内容后做同等 AST 审计。

### R2-4 [P1] 插件配置和 Note 标签写回缺少文本协议外壳校验

发现：Rust 写回会编码插件配置和 Note 标签文本，但没有调用等价的 `ensure_encoded_text_valid` 校验。

证据：
- `main:app/plugin_text/write_back.py` 在 `encode_visible_text_like` 后调用 `ensure_encoded_text_valid`。
- 当前 public Note tag parser 仍在 `app/note_tag_text/parser.py:67` 到 `75` 保留外壳校验。
- 当前 `rust/src/native_core/write_back_plan.rs:2499` 到 `2557` 的 `set_nested_text_value()` 和 `rust/src/native_core/write_back_plan.rs:1641` 到 `1672` 的 `replace_note_tag_value()` 没有同等校验。

影响：JSON 字符串外壳、可见文本协议或转义结构被破坏时，写回阶段可能不能及时阻断。

建议验证/修复方向：Rust 侧补同等写入协议校验，并覆盖插件参数、JSON 字符串叶子和 Note 标签。

## 第 3 轮：Native 边界与错误语义 Review

### R3-1 [P1] 写回计划没有接入 `ATT_MZ_RUST_THREADS`

发现：新写回计划直接使用 Rayon 全局线程池，项目已有线程配置对该热路径不生效。

证据：
- `rust/src/native_core/pool.rs:7` 定义 `run_with_optional_pool()`，读取 `ATT_MZ_RUST_THREADS`。
- `rust/src/native_core/quality/mod.rs` 和 `rust/src/native_core/write_protocol.rs` 已接入该包装层。
- `rust/src/native_core/write_back_plan.rs:522`、`563`、`620`、`3359` 直接调用 `.par_iter()` 或 `.into_par_iter()`。
- `rust/src/lib.rs:11` 的 `native_thread_count()` 会按配置报告线程数，但 `build_write_back_plan()` 没有安装配置线程池。

影响：大样本写回、插件源码扫描和运行态重建会绕过用户配置的 Rust 并发数量，资源占用不可控。

建议验证/修复方向：写回计划所有并行段统一纳入 `run_with_optional_pool()`，增加线程配置生效测试。

### R3-2 [P1] Python native 适配层信任 Rust 返回的目标路径

发现：Python 侧直接把 native 返回的 `target_path` 转成 `Path`，写文件前不校验是否仍在游戏运行目录内。

证据：
- `app/native_write_plan.py:111` 到 `126` 解析 `target_path` 和 `relative_path`。
- `app/application/handler.py:984` 把 plan files 直接交给 `write_planned_text_files()`。
- `app/application/file_writer.py:89` 到 `105` 会创建父目录并替换目标路径。

影响：一旦 Rust plan 或 native JSON 边界出现路径 bug，Python 写文件层不会 fail-fast，可能写出 `content_root` 外部。

建议验证/修复方向：Python 边界校验 `target_path.resolve()` 必须落在 `session.content_root` 或明确允许目录内，并拒绝路径穿越。

### R3-3 [P2] native 非 `ok` 返回错误信息不够可定位

发现：`app/native_write_plan.py` 遇到 `status != "ok"` 时只抛出泛化错误，没有保留 native payload 细节。

证据：
- `app/native_write_plan.py:90` 到 `92` 抛出 `Rust 写回计划没有返回 ok 状态`。

影响：动态 review 或自动化排障无法区分配置、数据库、JSON 协议或 Rust 内部错误。

建议验证/修复方向：保留结构化错误字段，补 `status=error`、malformed JSON、缺字段和类型错误测试。

## 第 4 轮：CLI 与外部契约 Review

### R4-1 [P0] `write-back` 和 `rebuild-active-runtime` 移除了 CLI 写入前 `quality-report` gate

发现：两个外部命令不再先执行 `ensure_write_back_gate()`。

证据：
- 当前 `app/cli/runtime.py:115` 的 `write_back_for_handler()` 直接进入 `handler.write_back()`。
- 当前 `app/cli/commands/write_back.py:43` 的 `run_rebuild_active_runtime_command()` 直接进入 `handler.rebuild_active_runtime()`。
- `main:app/cli/runtime.py` 和 `main:app/cli/commands/write_back.py` 先调用 `ensure_write_back_gate(... require_complete_translation=True)`。

影响：`write-back --json` 和 `rebuild-active-runtime --json` 的外部失败边界不再等价于 `quality-report`，可能漏掉规则缺失、过期规则、不可写范围和术语包错误。

建议验证/修复方向：恢复 CLI gate，或保证 handler/native 层等价执行 `quality-report` 的阻断集合。

### R4-2 [P1] `write-terminology` 外部语义和 native 行为冲突

发现：CLI 层仍表示 partial write-back，但 native plan 按完整正文写回条件运行。

证据：
- `app/cli/commands/write_back.py:81` 调用 `ensure_write_back_gate(... require_complete_translation=False)`。
- `app/application/handler.py:1136` 之后使用 `mode="write_back"` 调用 native plan。
- `rust/src/native_core/write_back_plan.rs:270` 调用 `ensure_no_latest_run_failures()`。

影响：用户按命令语义只写术语时，会被正文完整性条件拦截。

建议验证/修复方向：命令语义、handler 模式和 Rust plan 条件必须统一。

### R4-3 [P2] Rust 错误文案暴露 `位置:` 加内部路径

发现：Rust 质量错误拼接会把 `location_path` 直接放进普通错误文本。

证据：
- `rust/src/native_core/write_back_plan.rs:797` 到 `803` 追加 `位置: {location_path}`。

影响：普通终端文案暴露内部定位，不符合用户文案映射要求，Agent 也可能误把内部位置当成用户上下文。

建议验证/修复方向：终端文案保留中文摘要，内部路径放入 JSON details 或使用“文本在游戏里的内部位置”说明。

## 第 5 轮：测试覆盖静态 Review

### R5-1 [P1] 测试全绿但没有覆盖 CLI gate 路由

发现：工具链全部通过，但没有测试证明 `write-back`、`rebuild-active-runtime` 会遵守 `quality-report` 阻断结果。

证据：
- `uv run basedpyright` 结果为 0 errors、0 warnings。
- `uv run pytest` 结果为 454 passed。
- `cargo fmt --manifest-path rust/Cargo.toml -- --check`、`cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`、`cargo test --manifest-path rust/Cargo.toml` 均通过，Rust 测试 33 passed。
- 搜索测试只看到 `collect_write_back_gate_errors()` 的纯函数测试，没有 CLI 路由失败测试。

影响：第 4 轮发现的阻断级回归没有被测试捕获。

建议验证/修复方向：新增 CLI 端到端测试，模拟 `quality-report` 有阻断项时两个写入命令必须非零退出。

### R5-2 [P1] `write-terminology` 部分写入契约缺少端到端测试

发现：现有术语写回测试覆盖缺规则阻断和 helper 行为，但没有覆盖“正文 pending 但术语可写”的合法场景。

证据：
- `tests/test_cli_json_output.py:533` 只测 partial gate 纯函数。
- `tests/test_rmmz_loader_extraction_writeback.py:1239` 只测缺 workflow rules 时直接术语写回失败。
- `tests/test_terminology.py` 多数术语写回测试通过 helper 进入 native plan，不覆盖 CLI partial 契约。

影响：`write-terminology` 退化没有测试保护。

建议验证/修复方向：增加“pending 正文存在但术语可写时成功”和“会写入的坏译文存在时失败”的端到端测试。

### R5-3 [P1] Rust 写回计划缺少迁移等价关键测试

发现：Rust plan 测试覆盖了多类成功和错误路径，但缺少非标准 data 跳过、路径越界、线程配置、`status=error` 解析等边界。

证据：
- `rust/src/native_core/write_back_plan.rs:3711` 的成功测试只构造最小 data 文件并断言 1 个输出。
- `tests/test_native_adapters.py:51` 到 `133` 只覆盖少数字段类型错误。
- 没有针对 `UnknownPluginData.json`、`target_path` 越界、`ATT_MZ_RUST_THREADS` 写回计划生效、native `status=error` 的测试。

影响：高风险迁移差异不会被现有测试阻止。

建议验证/修复方向：补齐等价测试和边界测试，尤其是写文件边界与并发配置。

## 第 6 轮：动态样本 Review

### R6-1 [P0] 真实样本复现 gate 退化

发现：同一个临时样本中，`quality-report` 返回 `error`，但 `write-back --json` 返回 `ok`。

证据：
- 样本源：`D:\h-game\测试样本\已汉化\テイルズ・テイルス`。
- 样本只复制到临时目录运行，临时目录已删除。
- `quality-report` 退出码 1，`status=error`，`pending_count=4321`，并报告术语、插件规则、事件指令规则、Note 标签规则、占位符规则缺失。
- 同一状态下 `write-back --json` 退出码 0，`status=ok`，写入计数为 0。

影响：自动化只看 `write-back` JSON 时会误判可以继续。

建议验证/修复方向：修复后用同一样本副本回归，`quality-report` 失败时 `write-back` 必须非零退出。

### R6-2 [P1] `rebuild-active-runtime` 在阻断状态下仍计划并替换文件

发现：同一动态样本中，规则缺失、无译文、质量报告失败，但 `rebuild-active-runtime --json` 返回成功并计划写 77 个文件。

证据：
- `rebuild-active-runtime --json` 退出码 0，`status=ok`。
- 返回 `planned_file_count=77`、`skipped_file_count=18`、`rust_plan_ms=335`、`file_replacement_ms=180`、`post_write_audit_ms=62`。

影响：重建命令会在不满足流程前置条件时实际改写运行文件，风险高于只返回错误状态不一致。

建议验证/修复方向：`rebuild-active-runtime` 必须执行与 `quality-report` 等价的前置阻断，或明确限制为独立的恢复命令并重写外部契约。

### R6-3 [P2] `translate --json` gate 失败被包装为 `unexpected_error`

发现：动态样本存在规则缺失和未覆盖占位符时，`translate` 能在模型调用前停止，但 JSON 错误码为 `unexpected_error`。

证据：
- `translate --json --max-items 3 --max-batches 1 --time-limit-seconds 300` 退出码 1。
- 输出 `code=unexpected_error`，message 包含 workflow gate 的业务错误列表。
- 没有发生真实模型调用。

影响：Agent 不能稳定按业务错误码分流修复步骤。

建议验证/修复方向：workflow gate 预期失败应转换为稳定业务错误码，例如 `business_error` 或具体 gate code。

### R6-4 [P2] 动态样本发现大量未覆盖自定义控制符，真实模型调用应停止

发现：样本中存在 73 个疑似控制符候选，其中 64 个未覆盖。

证据：
- `doctor --no-check-llm --json` 返回 warning，`uncovered_placeholder_count=64`。
- `scan-placeholder-candidates` 返回 `candidate_count=73`、`uncovered_count=64`。

影响：该样本不能直接执行真实正文翻译，否则可能破坏游戏控制符。

建议验证/修复方向：先导入或显式传入占位符规则，再执行小批量真实翻译。

### R6-5 [P2] 非目标引擎样本已跳过

发现：`D:\h-game\测试样本\未汉化` 下若干候选不是目标 MV/MZ 引擎。

证据：
- `FantasMv941` 为 RGSS 形态，包含 `Game.rgssad`。
- `【PC】Not a Succubus` 为 Ren'Py 形态，包含 `renpy`、`NotaSuccubus.exe`。
- `dorokei_104`、`女警HRPG女警与H居岛 ケイドロ V1.06` 为旧 RPG Maker/RGSS 形态，包含 `Data`、`Game.ini`、`Game.exe`，没有 MV/MZ `data/System.json` 或 `www/data/System.json`。

影响：这些样本不纳入 att-mz MV/MZ 动态验收。

建议验证/修复方向：后续动态验收继续优先选择带 `data/System.json` 或 `www/data/System.json`、`js/plugins.js`、`package.json` 的 MV/MZ 样本。

## Review 阶段验收命令记录

已执行并通过：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

动态样本已执行：

```powershell
uv run python main.py --agent-mode add-game --path <临时游戏副本> --source-language ja --json
uv run python main.py --agent-mode doctor --game-path <临时游戏副本> --no-check-llm --json
uv run python main.py --agent-mode scan-placeholder-candidates --game-path <临时游戏副本> --output <临时报告> --json
uv run python main.py --agent-mode export-plugins-json --game-path <临时游戏副本> --output <临时报告>
uv run python main.py --agent-mode export-event-commands-json --game-path <临时游戏副本> --output <临时报告>
uv run python main.py --agent-mode text-scope --game-path <临时游戏副本> --output <临时报告> --json
uv run python main.py --agent-mode quality-report --game-path <临时游戏副本> --output <临时报告>
uv run python main.py --agent-mode audit-active-runtime --game-path <临时游戏副本> --output <临时报告>
uv run python main.py --agent-mode write-back --game-path <临时游戏副本> --json
uv run python main.py --agent-mode rebuild-active-runtime --game-path <临时游戏副本> --json
uv run python main.py --agent-mode translate --game-path <临时游戏副本> --max-items 3 --max-batches 1 --time-limit-seconds 300 --json
```

动态样本清理：

- 临时目录：`C:\Users\夜袭\AppData\Local\Temp\att-mz-dynamic-review-27126d32ae424ccf987165c8550719f8`
- 清理校验：`Exists=false`

## 修复优先级建议

1. 先修复 `write-back` 和 `rebuild-active-runtime` 的写入前 gate，动态样本已经证明这是阻断级问题。
2. 单独修复 `write-terminology` 的 partial write-back 语义，避免完整正文条件误伤术语写入。
3. 补 Rust plan 等价问题：标准 data 白名单、manifest 校验、插件配置解析、替换后 AST 审计、文本协议外壳校验。
4. 补 native 边界问题：路径 containment、`status=error` 解析、线程配置接入。
5. 用动态样本和新增测试固定回归，确保工具链通过同时覆盖外部命令语义。

