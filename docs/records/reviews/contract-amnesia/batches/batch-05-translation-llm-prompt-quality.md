# 批次 05：翻译、LLM、Prompt 与质量

## 范围

- `app/translation/`
- `app/llm/`
- `app/llm_request_body_extra.py`
- `prompts/`
- `app/native_quality.py`
- `rust/src/native_core/quality/`
- `tests/test_translation_*.py`
- `tests/test_quality_gate_result.py`

## 事实源

- `prompts/text_translation_ja_to_zh_system.md` 与 `prompts/text_translation_en_to_zh_system.md` 是本批翻译系统提示词事实源，当前说明输入由 `# 场景`、可选术语表和 `# 正文` 组成，输出为严格 JSON 数组。
- `app/translation/context.py` 负责组装用户 prompt；当前批次给模型的临时 `id` 来自 `str(sequence)`，真实 `location_path` 只保留在本地 `prompt_ids_by_location_path` 映射中。
- `app/translation/verify.py` 负责解析模型返回、按临时 ID 映射译文，并执行文本结构、控制符和源文残留检查。
- `app/native_quality.py` 与 `rust/src/native_core/quality/` 负责质量检查 JSON 输入输出、源文残留、行宽、结构和控制符风险收集。
- `tests/test_translation_*.py` 与 `tests/test_quality_gate_result.py` 固定本批 prompt 组装、模型响应解析、译文结构和质量检查行为。

## 只读命令

1. 必跑检索命令：

```powershell
rg -n 'prompt|location_path|translated_text|位置:|legacy|fallback|old|stale|pending|quality_error|manual|reset|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' app/translation app/llm app/llm_request_body_extra.py prompts app/native_quality.py rust/src/native_core/quality tests/test_translation_*.py tests/test_quality_gate_result.py
```

结果：已执行。PowerShell 下 `tests/test_translation_*.py` 没有展开为实际文件，`rg` 对该参数报 `os error 123`，其余路径仍输出命中。

2. 为覆盖 `tests/test_translation_*.py`，补跑同一检索模式的显式文件列表：

```powershell
rg --files -g 'test_translation_*.py' tests
rg -n 'prompt|location_path|translated_text|位置:|legacy|fallback|old|stale|pending|quality_error|manual|reset|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期' app/translation app/llm app/llm_request_body_extra.py prompts app/native_quality.py rust/src/native_core/quality tests/test_translation_run_limits.py tests/test_translation_line_alignment.py tests/test_translation_cache_context.py tests/test_quality_gate_result.py
```

结果：显式覆盖 `tests/test_translation_run_limits.py`、`tests/test_translation_line_alignment.py`、`tests/test_translation_cache_context.py` 和 `tests/test_quality_gate_result.py`。

3. 必跑 prompt 读取命令：

```powershell
Get-Content -Raw -LiteralPath 'prompts\text_translation_ja_to_zh_system.md'
Get-Content -Raw -LiteralPath 'prompts\text_translation_en_to_zh_system.md'
```

结果：已执行。两个系统提示词均描述当前翻译输入输出要求；直接文本未出现历史形态说明或内部 `location_path`、`translated_text` 暴露。

4. 报告写入后自检命令：

```powershell
$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-05-translation-llm-prompt-quality.md' -Pattern $patterns
```

结果：无命中。

## 结论

FAIL

## 发现

### P0：模型响应 ID 仍接受数字形态并转成字符串匹配

- 证据：`app/translation/context.py:237`、`app/translation/verify.py:38`、`app/translation/verify.py:279`、`tests/test_translation_line_alignment.py:477`
- 违反准则：运行时失忆化 | 测试失忆化
- 影响范围：当前 prompt 批次本地生成的模型临时 ID 是字符串；运行时响应 schema 仍允许 `id: str | int`，并在映射前用 `str(response_item.id)` 把数字 ID 转成字符串。测试 `test_translation_response_accepts_numeric_prompt_id` 还固定了“模型返回 JSON 数字也通过”的行为，使 LLM JSON 契约继续容纳非当前形态。
- 建议收束：将 `TranslationResponseItem.id` 收紧为 `str`，删除响应 ID 的数字转字符串路径；把数字 ID 测试改为当前契约下的失败路径测试，或移除该非当前响应形态。
- 后续验证：清理后运行 `uv run pytest tests/test_translation_line_alignment.py -k "translation_response"`，并运行 `uv run basedpyright` 检查类型收紧影响。

### P2：质量测试仍用“旧 original_lines/回退”表达被删除模型

- 证据：`tests/test_quality_gate_result.py:46`、`tests/test_quality_gate_result.py:73`
- 违反准则：测试失忆化
- 影响范围：该测试实际目标是“缺少当前 v2 fact 时显式失败”，但 docstring 和夹具源文写成“不能回退旧 original_lines”。这把历史来源模型留在测试语义里，后续维护者容易把已删除的数据来源理解成仍需比较或兼容的对象。
- 建议收束：将测试名、docstring 和夹具文本改成只描述当前事实源缺失后的失败要求，例如强调当前文本事实缺失时要求重新构建索引；不要再用“旧 original_lines”或“回退”描述历史路径。
- 后续验证：清理后运行 `uv run pytest tests/test_quality_gate_result.py -k quality_item_rehydrate`，确认失败路径仍覆盖当前事实源缺失。

## 交叉引用

- `text_facts_v2` 在本批仅作为当前事实源名称出现；schema 命名是否需要进一步失忆化由 schema/持久化批次判断。
- JSON repair、Markdown 包裹修复、未知 ID 忽略和额外字段忽略属于当前 LLM 容错策略；本批未确认其来源于历史形态。如后续要收紧“严格 JSON 数组”契约，可作为独立契约变更评审。

## 已查无发现范围

- 两个 `prompts/text_translation_*_system.md` 未发现历史说明、旧格式说明或内部位置字段暴露。
- `app/translation/context.py` 的用户 prompt 组装未向模型输出 `location_path`、`translated_text` 或 `位置:`；相关测试已有禁止泄漏断言。
- `app/llm/` 与 `app/llm_request_body_extra.py` 只描述当前 OpenAI 兼容请求、错误分类和请求体额外参数校验，未发现历史契约分支。
- `app/native_quality.py` 与 `rust/src/native_core/quality/` 的命中多为当前质量检查字段、内部位置定位和控制符风险字段；`old_font_names` 是字体替换当前业务参数，未按历史契约问题记录。
