# Debug LLM 消息观测设计

## 背景

本项目核心业务是通过 OpenAI 兼容接口翻译游戏文本。当前翻译失败、质量检查失败或性能异常时，开发者主要依赖日志、数据库记录和最终报告判断问题，但很难直接观察每次模型调用的完整上下文。

新的 debug 子功能用于记录本次 CLI 运行中成功返回的 LLM 消息。它把每次成功调用的 system、user 和 assistant 内容写成 Markdown 文件，方便开发者观察 prompt 组装、模型回复、JSON 结构、漏翻、控制符破坏和质量检查失败的根因。

该功能属于 debug 体系，不属于普通日志、普通报告或翻译结果输出。普通模式不得写出 LLM 消息文件。

## 目标

- 在统一 debug 模式下新增 `llm_messages` 子功能。
- 所有经过 `LLMHandler.get_ai_response()` 且成功返回非空 assistant 内容的调用，都纳入观测。
- 每次成功调用立即写出一个 Markdown 文件。
- 每次 CLI 正常收尾时生成一个 `index.md` 总览文件。
- 文件名只包含发起顺序和安全任务标签，不包含 `location_path`、prompt id 或游戏文本位置。
- Markdown 中保留完整 system、user、assistant 原文，不截断、不美化。
- 记录完整请求元数据；`base_url` 可以明文，`api_key` 和疑似密钥字段必须脱敏。
- LLM API 成功返回即可写出，即使后续翻译校验或质量检查失败。
- 显式 CLI 参数必须严格校验，避免用户误以为功能已启用或适用于所有命令。

## 非目标

- 不记录失败请求、超时请求、限流失败或空响应。
- 不记录失败响应审计；失败仍走现有日志和 LLM failure 记录。
- 不把 LLM 消息写入普通 stdout JSON 报告。
- 不做 token 计费、成本统计、自动质量分析或事件总线。
- 不为非 LLM 命令创建空目录。
- 不让 `--debug-llm-messages` 隐式开启 debug 总开关。

## 配置与开关

配置文件新增 debug 子域：

```toml
[debug]
enabled = false

[debug.llm_messages]
enabled = true
output_dir = "output/debug/llm-messages"
```

字段语义：

- `debug.enabled`：debug 总开关。
- `debug.llm_messages.enabled`：是否启用 LLM 消息观测子功能。
- `debug.llm_messages.output_dir`：LLM 消息观测运行目录的父目录。

新增 CLI 参数：

- `--debug-llm-messages`：本次强制开启 LLM 消息观测。
- `--no-debug-llm-messages`：本次强制关闭 LLM 消息观测。

新增环境变量：

- `ATT_MZ_DEBUG_LLM_MESSAGES=1|0`

优先级：

```text
debug 总开关：CLI --debug/--no-debug > ATT_MZ_DEBUG > setting.toml debug.enabled > 默认值
llm_messages 子功能：CLI --debug-llm-messages/--no-debug-llm-messages > ATT_MZ_DEBUG_LLM_MESSAGES > setting.toml debug.llm_messages.enabled > 默认值
```

有效条件：

```text
debug.enabled == true
debug.llm_messages.enabled == true
```

`--debug-llm-messages` 不隐式开启 `--debug`。如果用户显式传入 `--debug-llm-messages`，但最终 debug 总开关没有开启，CLI 必须直接报错。

## 命令适用范围

第一版只把以下命令视为 LLM 调用类命令：

- `translate`
- `run-all`

显式传入 `--debug-llm-messages` 时，当前命令必须在该白名单内。否则 CLI 直接报错，例如：

```text
debug.llm_messages 只能用于会调用 LLM 的命令；当前命令 rebuild-text-index 不会调用模型。
```

如果 `setting.toml` 或环境变量开启了 `debug.llm_messages.enabled`，但当前命令不是 LLM 调用类命令，不报错、不创建目录。这样全局 debug 配置不会影响非 LLM 命令。

后续新增 LLM 命令时，必须显式登记到白名单，不允许靠“运行过程中有没有调用 LLM”做隐式判断。

## 运行时架构

新增模块：

```text
app/observability/llm_messages.py
```

核心对象：

- `LLMMessageRuntimeSettings`：合并后的 LLM 消息观测配置。
- `LLMMessageRecorder`：本次 CLI 运行的消息记录器。
- `NoopLLMMessageRecorder`：未启用时的空对象。
- `current_llm_message_recorder()`：通过 `contextvars.ContextVar` 获取当前记录器。

CLI 入口负责：

1. 合并 debug 总开关和 `llm_messages` 子功能配置。
2. 校验显式 CLI 参数是否满足命令白名单和 debug 总开关要求。
3. 为本次 CLI 运行绑定 recorder。
4. 正常收尾时 finalize recorder 并生成 `index.md`。

`LLMHandler.get_ai_response()` 负责：

1. 记录请求发起时间。
2. 调用 OpenAI 兼容 Chat Completions。
3. 成功取得非空 assistant 内容后，调用当前 recorder 写出 Markdown。
4. 返回 assistant 文本给原业务流程。

业务层不应该直接写 LLM 消息文件。翻译、doctor 或后续其他功能只需继续调用 `LLMHandler.get_ai_response()`。

## 并发与编号

正文翻译存在高并发 worker。LLM 消息文件按请求发起顺序编号，而不是按返回顺序编号：

```text
000001_text-translation.md
000002_text-translation.md
000003_text-translation.md
```

文件头记录发起时间和返回时间，以便同时观察派发顺序和完成顺序。

记录器必须保证：

- 并发请求不会拿到重复编号。
- 并发写文件不会破坏 Markdown 内容。
- 每个成功响应对应一个文件。
- 写文件失败直接抛错，不静默吞掉。

实现可使用 async lock 或同步 lock 保护编号与索引记录。文件写入可以保持同步写入；该功能只在显式 debug 模式启用。

## 输出目录

默认父目录：

```text
output/debug/llm-messages
```

每次 CLI 运行在父目录下创建一个运行目录：

```text
<output_dir>/<timestamp>_<command>_<run_id>/
```

示例：

```text
output/debug/llm-messages/2026-06-07_143012_translate_a1b2c3d4/
```

没有成功 LLM 调用时不创建运行目录。

如果运行中断，已经成功写出的 `.md` 文件保留；`index.md` 只在 CLI 正常收尾时保证生成。

## Markdown 文件格式

单次调用文件示例：

````md
# LLM 调用 000001

## 元数据

- command: translate
- task_label: 正文翻译
- model: example-model
- base_url: https://api.example.com/v1
- temperature: null
- request_started_at: 2026-06-07T14:30:12+08:00
- response_received_at: 2026-06-07T14:30:21+08:00
- message_count: 2
- system_chars: 1234
- user_chars: 5281
- assistant_chars: 1832

## 请求元数据

```json
{
  "model": "example-model",
  "temperature": null,
  "base_url": "https://api.example.com/v1",
  "api_key": "<redacted>",
  "extra_body": {
    "reasoning_effort": "high",
    "private_token": "<redacted>"
  }
}
```

## message 1: system

```text
...
```

## message 2: user

```text
...
```

## assistant

```text
...
```
````

内容规则：

- system、user、assistant 均按原文写入 fenced block。
- 不截断、不美化、不重新格式化 prompt 或 assistant 内容。
- `base_url` 可以明文记录。
- `api_key` 必须脱敏。
- `extra_body` 完整记录，但字段名疑似密钥、token、secret、password、credential、authorization 时递归脱敏。
- 文件名不包含 `location_path`、prompt id、游戏名或真实路径。

## 索引文件

CLI 正常收尾时生成：

```text
index.md
```

示例：

```md
# LLM 消息观测

| 序号 | 任务 | 模型 | 发起时间 | 返回时间 | user 字符 | assistant 字符 | 文件 |
|---|---|---|---|---|---:|---:|---|
| 000001 | 正文翻译 | example-model | 2026-06-07T14:30:12+08:00 | 2026-06-07T14:30:21+08:00 | 5281 | 1832 | 000001_text-translation.md |
```

索引只列成功写出的调用。失败请求、空响应和未完成请求不出现在索引里。

## 错误边界

- LLM 客户端未配置：保持现有错误，不写 LLM 消息文件。
- LLM 请求失败：保持现有日志和失败记录，不写 LLM 消息文件。
- LLM 空响应：保持现有 `EmptyLLMResponseError`，不写 LLM 消息文件。
- LLM 成功返回非空 assistant：立即写 Markdown，即使后续翻译校验失败。
- Markdown 写入失败：直接抛错，让 CLI 失败。
- `index.md` 写入失败：直接抛错，让 CLI 失败。

显式启用 debug 文件观测时，写文件失败不能静默忽略。否则用户会误判观测文件可靠性。

## 测试要求

测试应覆盖以下外部可观察行为：

- `setting.toml` 能解析 `[debug.llm_messages]`。
- CLI 能识别 `--debug-llm-messages` 和 `--no-debug-llm-messages`。
- 显式 `--debug-llm-messages` 未启用 debug 总开关时报错。
- 显式 `--debug-llm-messages` 用在非 LLM 命令时报错。
- setting/env 开启但非 LLM 命令不创建目录、不报错。
- 成功 LLM 调用会生成运行目录和 `.md` 文件。
- Markdown 文件包含 system、user、assistant 原文 fenced block。
- `api_key` 和 `extra_body` 中疑似密钥字段会脱敏。
- LLM 成功返回但后续翻译校验失败时，仍生成 `.md`。
- 正常收尾生成 `index.md`。
- 失败请求和空响应不写 `.md`。

涉及 CLI 参数、配置字段、环境变量和输出目录结构的测试，必须覆盖“定义 -> 解析 -> 校验 -> 应用”的完整链路。

## 维护边界

- LLM 消息观测是 debug 子功能，不是翻译业务的一部分。
- 新增 LLM 调用路径时，优先复用 `LLMHandler.get_ai_response()`，不要在业务模块绕过统一门面。
- 新增会调用 LLM 的 CLI 命令时，必须显式登记为 LLM 调用类命令，才能使用 `--debug-llm-messages`。
- 后续若增加失败请求审计、token 成本统计或自动分析，应作为新的 debug 子功能或扩展配置设计，不混入第一版消息观测。
