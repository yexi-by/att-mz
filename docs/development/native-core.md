# 原生核心

## 职责

`rust/` 提供 Python 扩展 `_native`，把 CPU 密集型扫描和写回计划构建交给 Rust 执行。`rust/src/lib.rs` 只负责 PyO3 绑定和释放 Python 运行时锁。`rust/src/native_core.rs` 是 Rust 业务门面，内部按控制符、详情构造、字体替换、模型、Note 来源、占位符、线程池、质量检查、写回计划、规则和写入协议拆分。Python 侧通过 `app.native_quality` 和 `app.native_write_plan` 做 JSON 适配和错误转换。

## 输入

- Python 侧序列化后的 JSON 字符串。
- 写回计划模式、允许写入的文本内部位置清单和写文件策略。
- 当前游戏路径、当前游戏数据库路径、文本条目、文本规则、源文残留例外规则、写入协议检查数据和字体扫描数据。
- 线程池配置环境变量。

## 输出

- 质量检查详情：源语言残留、文本结构、必须原样保留的游戏控制符风险和过长行。
- 写入协议详情：当前译文是否会破坏游戏文本协议。
- Note 标签来源扫描结果和字体替换扫描结果。
- 写回计划：待替换文件内容、当前运行映射、字体替换记录、统计和性能分段。计划模式包括完整写回、重建当前运行文件和术语专用写入。
- 当前 Rust 线程数量。

## 失败策略

- Rust 核心解析输入失败或发现规则损坏时返回错误字符串，由 Python 侧转成业务报告。
- PyO3 入口不做复杂业务，只做参数转换、释放 Python 运行时锁和错误转换。
- 原生写回计划只读数据库和游戏文件，不直接写文件、不直接写数据库。
- 写回计划只处理标准 RPG Maker MV/MZ data JSON、插件配置和直接插件源码；计划结果返回 Python 后仍必须通过路径归属校验再进入文件替换。
- 写回计划必须按模式和允许写入清单过滤译文，不能把未获准写入的已保存译文带入计划。
- 必要输入、规则、文件或能力缺失时直接报错。

## 协作模块

- `app.native_quality` 调用 `_native` 并将结果转换为 Python JSON 模型。
- `app.native_write_plan` 调用 `_native` 并将写回计划转换为 Python 数据模型。
- `app.agent_toolkit.services.quality` 使用原生质量检查生成质量报告。
- `app.text_scope` 和写入流程使用写入协议扫描判断是否可以写进游戏文件。
- `app.application.font_replacement` 使用字体扫描结果替换和还原引用。

## 主要入口

- `rust/Cargo.toml`
- `rust/src/lib.rs`
- `rust/src/native_core.rs`
- `rust/src/native_core/quality/mod.rs`
- `rust/src/native_core/write_back_plan/mod.rs`
- `rust/src/native_core/write_back_plan/*.rs`
- `rust/src/native_core/write_protocol.rs`
- `rust/src/native_core/note_sources.rs`
- `rust/src/native_core/font_replacement.rs`
- `app.native_quality`
- `app.native_write_plan`

## 测试覆盖

- `cargo test --manifest-path rust/Cargo.toml` 覆盖 Rust 质量检查、规则错误、写回计划模式、线程配置和结构性边界。
- `tests/test_agent_toolkit.py` 间接覆盖 Python 调用原生质量检查。
- `tests/test_native_adapters.py` 覆盖 Python 原生适配层错误状态、字段类型和写文件路径归属校验。
- `tests/test_rmmz_loader_extraction_writeback.py` 间接覆盖写文件前检查、写入协议和字体扫描协作。
