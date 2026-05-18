# 大文件拆分功能对照矩阵

本文档记录本次等价拆分中已经移动的功能边界，供后续继续拆分时核对外部行为是否保持一致。

| 原功能点 | 原位置 | 新位置 | 测试覆盖 | 等价结论 |
| --- | --- | --- | --- | --- |
| 长文本译文行数适配与宽度兜底 | `app.translation.line_wrap` | `app.rmmz.text_layout.service`、`split`、`width`、`wrapping`、`protected` | `tests/test_translation_line_alignment.py` | 公共函数签名保持一致，调用方改为依赖 RMMZ 文本布局包 |
| 写回阶段文本布局依赖 | `app.rmmz.write_back` 直接依赖 `app.translation.line_wrap` | `app.rmmz.write_back` 依赖 `app.rmmz.text_layout` | `tests/test_rmmz_loader_extraction_writeback.py` | 消除了 RMMZ 层对 translation 层的反向依赖 |
| 统一文本范围模型 | `app.text_scope` 单文件 | `app.text_scope.models` | `tests/test_agent_toolkit.py` | JSON 字段和用户可见原因保持不变 |
| 统一文本范围构建 | `app.text_scope.TextScopeService` | `app.text_scope.builder.TextScopeService`，包入口继续导出 | `tests/test_agent_toolkit.py`、`tests/test_cli_json_output.py` | `TranslationHandler` 与 `AgentToolkitService` 仍通过同一服务读取范围 |
| 插件规则新鲜度检查 | `app.text_scope.read_fresh_plugin_text_rules` | `app.text_scope.plugin_rules.read_fresh_plugin_text_rules`，包入口继续导出 | `tests/test_agent_toolkit.py` | 过期规则原因和返回结构保持一致 |
| 写入可行性探针 | `app.text_scope` 内部函数 | `app.text_scope.write_probe` | `tests/test_agent_toolkit.py` | 探针失败策略保持一致，测试 monkeypatch 定位到新子模块 |
| 外部规则命中展开 | `app.text_scope` 内部函数 | `app.text_scope.rule_hits` | `tests/test_agent_toolkit.py` | 插件、事件指令、Note 标签命中展开规则保持一致 |
| 正文翻译运行控制参数 | `app.application.handler` | `app.application.use_cases.translation_run`，`handler` 继续导出 | `tests/test_cli_json_output.py` | CLI 参数构造仍可从原入口导入 |
| 正文翻译批次、去重、缓存展开 | `TranslationHandler` 静态方法 | `app.application.use_cases.translation_run` 纯函数 | `tests/test_translation_cache_context.py`、`tests/test_cli_json_output.py` | 翻译编排入口不变，纯逻辑脱离总编排类 |
| 数据库路径解析 | `app.persistence.repository` | `app.persistence.paths`，`repository` 与 `persistence` 继续导出 | `tests/test_persistence.py`、`tests/test_runtime_paths.py` | 数据库目录、文件名校验和默认路径行为保持一致 |
| 数据库记录模型 | `app.persistence.repository` | `app.persistence.records`，`repository` 与 `persistence` 继续导出 | `tests/test_persistence.py` | 记录字段和读取失败策略保持一致 |
| data 文本写回入口 | `app.rmmz.write_back.py` | `app.rmmz.write_back.service`，包入口导出 `write_data_text` | `tests/test_rmmz_loader_extraction_writeback.py` | 调用路径保持 `app.rmmz.write_back import write_data_text` |
| 字体替换入口 | `app.application.font_replacement.py` | `app.application.font_replacement.service`，包入口导出公共函数 | `tests/test_rmmz_loader_extraction_writeback.py`、`tests/test_runtime_paths.py` | 调用路径保持 `app.application.font_replacement import ...` |

## 后续待拆

- `app.agent_toolkit.service` 仍需按 doctor、placeholder_rules、coverage、quality、manual_translation、workspace、rule_validation、feedback 继续拆成可组合服务。
- `app.persistence.repository` 仍需继续按翻译记录、规则记录、术语记录、运行记录、字体记录拆分会话方法。
- `app.rmmz.write_back.service` 和 `app.application.font_replacement.service` 已完成包入口迁移，后续可继续拆出内部子模块。
- `rust_app/native_core/quality.rs` 尚未拆成 residual、structure、placeholder、line_width 子模块。
