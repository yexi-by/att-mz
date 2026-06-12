# 翻译、LLM 与术语

## 职责

`app.translation` 负责正文翻译批次、上下文构造、运行内去重复用、LLM 请求重试、文本结构校验和译文验证。`app.llm` 是 OpenAI 兼容聊天客户端门面，`app.llm_request_body_extra` 负责额外请求体参数解析与限制。`app.language` 与 `app.language_profiles` 定义源语言和语言档案。`app.terminology` 负责术语候选提取、临时文件读写和正文提示词术语索引，术语写入由 Rust 写回计划统一生成。

## 输入

- 当前文本索引和当前文本事实中的可翻译正文条目。
- 模型配置、请求体额外参数、并发数量、限速、重试次数和运行停止条件。
- 已导入的字段译名表、正文术语表和语言档案。

## 输出

- 带当前 `fact_id` 和文本 hash 的成功译文记录。
- 检查没通过的译文记录和模型失败记录。
- 术语表工程文件、导入后的术语记录和写回后的稳定名词。

## 失败策略

- 模型响应必须符合结构化协议，解析或结构校验失败时记录为本条译文失败，不静默保存。
- 可恢复的模型错误按重试策略处理；达到停止条件时结束本轮运行并保留已完成结果。
- `stream=true` 或不适合完整 JSON 校验的请求体额外参数不能进入正文翻译请求。
- 术语文件必须通过 schema 校验后才能写入数据库。

## 协作模块

- `app.rmmz.text_rules` 提供控制符保护、源语言识别和行宽规则。
- `app.text_index`、`app.text_fact_readers` 和 `app.native_scope_index` 提供当前需要处理的文本范围与当前文本事实身份。
- `app.persistence` 保存译文、失败记录和术语记录。
- `app.agent_toolkit` 导出人工修复表和质量报告。
- `app.native_write_plan` 调用 Rust 写回计划生成术语和译文的文件替换内容。

## 主要入口

- `app.translation.text_translation.TextTranslation`
- `app.translation.context.iter_translation_context_batches`
- `app.translation.verify.verify_translation_batch`
- `app.translation.retry.request_with_recoverable_retry`
- `app.llm.handler.LLMHandler`
- `app.terminology.extraction`
- `app.terminology.files`
- `app.native_write_plan.build_native_write_back_plan`

## 测试覆盖

- `tests/test_translation_cache_context.py` 覆盖上下文和去重复用逻辑。
- 译文结构、长行切分和模型响应校验不再由 Python 矩阵 pytest 固定；当前结构边界由 Rust/native owner 测试和公开翻译报告契约覆盖。
- `tests/test_llm_retry.py` 覆盖可恢复请求重试。
- `tests/test_terminology.py` 覆盖术语提取、文件格式、导入和写入。
