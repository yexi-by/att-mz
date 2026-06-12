# 原生核心

## 职责

`rust/` 提供 Python 扩展 `_native`，把 CPU 密集型扫描、当前文本索引、统一规则运行时、质量检查和写回计划构建交给 Rust 执行。`rust/src/lib.rs` 负责 PyO3 绑定、释放 Python 运行时锁和暴露原生契约版本。`rust/src/native_core.rs` 是 Rust 业务门面，内部按 Scope/Index、Rule Runtime、当前文本事实、质量检查、JavaScript AST、线程池和写回计划拆分。Python 侧通过 `app.native_scope_index`、`app.native_rule_runtime`、`app.native_quality` 和 `app.native_write_plan` 做 JSON 适配、契约校验和错误转换。

## 输入

- Python 侧序列化后的 JSON 字符串。
- 写回计划模式、允许写入的当前文本事实清单和写文件策略。
- 当前游戏路径、当前游戏数据库路径、文本规则、统一规则模型、源文残留例外规则、写入协议检查数据和字体扫描数据。
- 当前 SQLite schema 指纹、原生契约版本和线程池配置。

## 输出

- 当前文本索引和当前文本事实：索引项、domain 摘要、规则命中摘要、候选摘要、不可写原因和范围门禁事实。
- 统一规则运行时结果：规则导入 prepare/commit 报告、PCRE2 规则匹配结果、规则指纹和配置正则执行结果。
- 质量检查详情：源语言残留、文本结构、必须原样保留的游戏控制符风险和过长行。
- 写入协议详情：当前译文是否会破坏游戏文本协议。
- Note 标签来源扫描、插件源码 AST 扫描和字体替换扫描结果。
- 写回计划：待替换文件内容、当前运行映射、字体替换记录、统计和性能分段。计划模式包括完整写回、重建当前运行文件和术语专用写入。
- 当前 Rust 线程数量。

## 失败策略

- Rust 核心解析输入失败或发现规则损坏时返回错误字符串，由 Python 侧转成业务报告。
- PyO3 入口不做复杂业务，只做参数转换、释放 Python 运行时锁和错误转换。
- Scope/Index storage 入口可以按当前契约写入文本索引和当前文本事实；写回计划只读数据库和游戏文件，不直接写游戏文件。
- 写回计划只处理标准 RPG Maker MV/MZ data JSON、插件配置和直接插件源码；计划结果返回 Python 后仍必须通过路径归属校验再进入文件替换。
- 写回计划必须按模式和允许写入清单过滤译文，不能把未获准写入的已保存译文带入计划。
- 必要输入、规则、文件或能力缺失时直接报错。

## 协作模块

- `app.native_contract` 校验 Python/Rust 原生契约版本。
- `app.native_scope_index` 调用 `_native` 构建当前文本索引、当前文本事实和范围门禁。
- `app.native_rule_runtime` 调用 `_native` 校验、导入和执行统一规则模型。
- `app.native_quality` 调用 `_native` 并将质量检查结果转换为 Python JSON 模型。
- `app.native_write_plan` 调用 `_native` 并将写回计划转换为 Python 数据模型。
- `app.agent_toolkit.services.quality` 使用原生质量检查生成质量报告。
- `app.text_index`、`app.text_fact_*` 和写入流程使用当前索引、当前文本事实和写入协议扫描判断是否可以写进游戏文件。
- `app.application.font_replacement` 使用字体扫描结果替换和还原引用。

## 主要入口

- `rust/Cargo.toml`
- `rust/src/lib.rs`
- `rust/src/native_core.rs`
- `rust/src/native_core/scope_index/*.rs`
- `rust/src/native_core/rule_runtime/*.rs`
- `rust/src/native_core/text_facts.rs`
- `rust/src/native_core/quality/mod.rs`
- `rust/src/native_core/write_back_plan/mod.rs`
- `rust/src/native_core/write_back_plan/*.rs`
- `rust/src/native_core/note_sources.rs`
- `rust/src/native_core/font_replacement.rs`
- `app.native_contract`
- `app.native_scope_index`
- `app.native_rule_runtime`
- `app.native_quality`
- `app.native_write_plan`

## 测试覆盖

- `cargo test --manifest-path rust/Cargo.toml` 覆盖 Rust Scope/Index、Rule Runtime、质量检查、规则错误、写回计划模式、线程配置和结构性边界。
- Python 侧只保留公开入口和原生适配层可观察契约，不再用 Agent 工具箱大集成 pytest 间接固定原生质量检查内部路径。
- `tests/test_native_rule_runtime.py` 和 `tests/test_native_adapters.py` 覆盖 Python 原生适配层错误状态、字段类型和规则运行时契约；Scope/Index 内部行为归 Rust owner 测试。
- `tests/test_write_back_transactions.py` 和 `tests/test_rmmz_font_transaction.py` 覆盖写文件前检查的公开副作用与字体扫描协作；写入协议和写回计划内部归 Rust owner 测试。
