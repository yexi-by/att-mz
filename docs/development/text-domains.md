# 文本领域模块

## 职责

文本领域模块负责把 RPG Maker MV/MZ 文件中的可翻译文本提取成统一业务模型，并把已保存译文安全写回游戏文件。`app.rmmz` 处理引擎标准数据、控制符、文本规则、文本布局、写入路径和写入协议。`app.text_scope` 统一回答当前哪些文本可处理、哪些已保存译文、哪些能写进游戏文件。`app.plugin_text`、`app.event_command_text`、`app.note_tag_text` 和 `app.plugin_source_text` 分别处理插件参数、事件指令参数、Note 标签文本和插件源码文本。`rust/src/native_core/write_back_plan/` 生成写回和重建计划，`app.native_write_plan` 负责 Python 侧协议解析。`app.source_residual` 负责源文残留例外规则。

## 输入

- RPG Maker 标准 data JSON、`js/plugins.js` 和 `js/plugins/*.js` 直接插件源码文件。
- 已导入的插件规则、事件指令规则、Note 标签规则、插件源码规则、自定义控制符规则和源文残留例外规则。
- 文本规则配置，例如行宽、标点包裹、源语言识别和自定义占位符。

## 输出

- `TranslationData`、`TranslationItem` 等统一文本模型。
- 当前文本范围报告、规则命中报告和写入可行性结果。
- Rust 写回计划生成的标准数据文件、插件配置、插件源码和字体替换记录。
- 写文件前检查结果，包括覆盖审计、质量报告、完整译文覆盖、可信源快照校验、可写文本范围和术语专用写入范围。

## 失败策略

- RPG Maker 文件结构不符合预期时直接报错，避免生成损坏写入结果。
- 插件、事件指令、Note 标签和插件源码规则必须命中当前游戏文件中的可提取文本，导入失败时不写入数据库。
- 源文残留例外只允许明确保留的源语言片段，不允许掩盖整句漏翻。
- 写入前会整理译文、检查控制符、修复包裹标点并处理过长行；无法定位、协议缺字段或不可写时直接报错。
- `write-back` 和 `rebuild-active-runtime` 只有在覆盖审计、质量报告、完整译文覆盖和可信源快照通过时才写文件。
- `write-terminology` 使用术语专用写入条件，允许正文仍有还没成功保存译文的文本，但不能绕过术语表、源快照、写入目标和已保存译文质量检查。
- 插件配置、Note 标签和插件源码写入必须通过文本协议外壳校验；插件源码替换后的内容必须能通过当前运行协议审计。

## 协作模块

- `app.translation` 使用文本模型构造模型请求和校验译文结构。
- `app.application` 调用领域模块完成提取、质量检查和写入。
- `app.agent_toolkit` 使用领域模块导出候选、审计范围和构建修复表。
- `rust/` 提供质量检查、写入协议扫描、JavaScript AST 扫描和写回计划生成能力。

## 主要入口

- `app.rmmz.loader.load_game_data`
- `app.rmmz.extraction.DataTextExtraction`
- `app.native_write_plan.build_native_write_back_plan`
- `rust/src/native_core/write_back_plan/mod.rs`
- `rust/src/native_core/write_back_plan/*.rs`
- `app.rmmz.text_layout`
- `app.text_scope.TextScopeService`
- `app.plugin_text.*`
- `app.event_command_text.*`
- `app.note_tag_text.*`
- `app.plugin_source_text.*`
- `app.source_residual.*`

## 测试覆盖

- `tests/test_rmmz_loader_extraction_writeback.py` 覆盖标准数据提取和写入。
- `tests/test_plugin_text.py` 覆盖插件规则和插件文本写入。
- `tests/test_event_command_text.py` 覆盖事件指令规则。
- `tests/test_plugin_source_text.py` 覆盖插件源码风险扫描、规则提取和写入。
- `tests/test_text_protocol.py`、`tests/test_text_rules.py` 和 `tests/test_translation_line_alignment.py` 覆盖文本协议、控制符、行宽和结构校验。
