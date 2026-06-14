# 多模型客户端配置设计

## 背景

当前项目的模型配置只有单个 `[llm]` 配置段，包含 `base_url`、`api_key`、`model`、`timeout` 和 `request_body_extra`。命令行还允许通过 `--llm-model`、`--llm-timeout` 临时覆盖模型名和超时，环境变量也可以覆盖模型地址和 API Key。

这会让模型连接事实分散在配置、命令行和环境变量三处。用户希望改为在 `setting.toml` 中配置多个模型客户端，执行翻译、流水线或模型检查时只通过客户端名称选择具体客户端。模型地址、密钥、模型名、超时和额外请求参数必须全部来自所选客户端配置。

## 目标

- `setting.toml` 只支持多客户端模型配置。
- `provider_type` 是调用协议类型枚举，当前只支持 `openai`，后续可扩展 `gemini` 等协议。
- 命令行只允许通过 `--llm-client <客户端名称>` 选择客户端。
- 删除 `--llm-model`、`--llm-timeout` 和旧的模型地址/API Key 环境变量覆盖。
- 本次选择的客户端信息进入命令摘要、日志、翻译 JSON 报告和 debug 模型消息。
- 同步更新 Skill 协议源、生成物、README 和相关文档。

## 非目标

- 不兼容旧的单客户端 `[llm] base_url/api_key/model/timeout` 配置。
- 不新增数据库字段，不给每条译文记录模型来源。
- 不实现 `gemini`、Claude 或其它非 OpenAI 兼容协议。
- 不新增批量检查全部客户端的 `doctor` 能力。
- 不引入按客户端名称的环境变量覆盖规则。

## 外部配置契约

`setting.toml` 的模型配置改为：

```toml
[llm]
default_client = "deepseek-chat"

[[llm.clients]]
name = "deepseek-chat"
provider_type = "openai"
base_url = "https://api.deepseek.com/v1"
api_key = "YOUR_DEEPSEEK_API_KEY"
model = "deepseek-chat"
timeout = 600

[[llm.clients]]
name = "openrouter-gemini"
provider_type = "openai"
base_url = "https://openrouter.ai/api/v1"
api_key = "YOUR_OPENROUTER_API_KEY"
model = "google/gemini-2.5-pro"
timeout = 600

# 少数 OpenAI 兼容服务需要额外请求参数时，放在对应客户端里。
# request_body_extra = '''
# {
#   "reasoning_effort": "high"
# }
# '''
```

配置规则：

- `default_client` 必填，必须指向 `clients` 中存在的客户端名称。
- `clients` 至少包含一个客户端。
- `name` 必须唯一，只允许小写字母、数字、短横线和下划线。
- `provider_type` 当前只允许 `openai`。
- `request_body_extra` 只允许放在单个客户端里。
- `base_url`、`api_key`、`model`、`timeout` 只能来自所选客户端。

## CLI 契约

删除以下命令行参数：

- `--llm-model`
- `--llm-timeout`

新增统一选择参数：

```powershell
uv run python main.py translate --game <游戏标题> --llm-client deepseek-chat
uv run python main.py run-all --game <游戏标题> --llm-client deepseek-chat
uv run python main.py doctor --llm-client deepseek-chat
```

`--llm-client` 覆盖所有会执行正文翻译或模型检查的命令，包括：

- `doctor`
- `translate`
- `run-all`
- 后续若新增其它会触发“先翻译再写回”的命令，也必须接入同一个 `--llm-client` 选择入口

不传 `--llm-client` 时使用 `[llm].default_client`。

## 环境变量契约

删除旧的模型连接覆盖：

- `ATT_MZ_LLM_BASE_URL`
- `ATT_MZ_LLM_API_KEY`

Rust 线程、debug 等非模型连接环境变量不受影响。

## 架构设计

新增配置模型概念：

- `LLMClientSetting`：单个模型客户端，包含 `name`、`provider_type`、`base_url`、`api_key`、`model`、`timeout` 和 `request_body_extra`。
- `LLMSetting`：多客户端容器，包含 `default_client`、`clients` 和 `active_client`。
- `active_client`：配置加载阶段解析出的本次有效客户端，是运行时唯一使用的模型连接事实。

推荐实现方式是配置加载阶段完成客户端选择：

1. 读取 `setting.toml`。
2. 应用语言档案、提示词注入和其它非 LLM 覆盖。
3. 根据 `--llm-client` 或 `default_client` 选择有效客户端。
4. 校验客户端列表、名称格式、名称唯一性、默认客户端存在和 `provider_type`。
5. `load_runtime_setting()` 使用 `setting.llm.active_client` 配置 `LLMHandler`。
6. 翻译调度器仍只接收已选模型名，不感知多客户端列表。

`SettingOverrides` 不再保存模型名和超时覆盖，只保存 `llm_client_name` 这类客户端选择输入。

## 报告与观测

配置摘要和日志显示：

```text
正文接口: openai / 客户端 deepseek-chat / 模型 deepseek-chat / 地址 https://api.deepseek.com/v1 / 超时 600 秒
```

翻译 JSON 报告加入：

```json
{
  "llm_client": {
    "name": "deepseek-chat",
    "provider_type": "openai",
    "model": "deepseek-chat"
  }
}
```

debug 模型消息记录：

- 客户端名称
- `provider_type`
- 模型名称
- 地址
- 脱敏后的密钥展示值
- 额外请求参数

`doctor` 输出显示正在检查的客户端。不传 `--llm-client` 时检查默认客户端。

## 错误处理

关键业务错误使用中文错误：

- 客户端列表为空：说明没有配置任何模型客户端。
- `default_client` 不存在：说明默认客户端找不到，并列出可用客户端名称。
- `--llm-client` 不存在：说明本次指定客户端找不到，并列出可用客户端名称。
- 客户端名称重复：说明重复的客户端名称。
- 客户端名称格式错误：说明只能使用小写字母、数字、短横线和下划线。
- `provider_type` 不支持：说明当前只支持 `openai`。

其它字段类型错误继续由严格配置校验处理。旧单客户端字段出现在 `[llm]` 下时按当前无效配置失败，不做兼容迁移。

## Skill 与文档

Skill 协议必须从协议源头修改：

- 修改 `skills/att-mz-protocol/templates/SKILL.md.in` 中模型配置来源描述。
- 修改 `skills/att-mz-protocol/templates/references/cli-command-contract.md.in`，删除旧模型环境变量说明，补充 `--llm-client` 使用边界。
- 运行 `uv run python scripts/generate_skill_protocol.py --write` 更新 `skills/att-mz` 和 `skills/att-mz-release`。
- 交付前运行 `uv run python scripts/generate_skill_protocol.py --check`，确认生成物没有漂移。

README、`docs/guides/advanced-usage.md` 和开发文档里的旧 `[llm] base_url/api_key/model/timeout` 示例、旧环境变量说明也必须同步更新。

## 测试策略

配置加载测试：

- 多客户端配置成功加载。
- 不传 `--llm-client` 时选择默认客户端。
- 传入 `--llm-client` 时覆盖默认客户端。
- 客户端列表为空失败。
- 默认客户端不存在失败。
- 指定客户端不存在失败。
- 客户端名称重复失败。
- 客户端名称格式非法失败。
- `provider_type` 非 `openai` 失败。
- 旧单客户端字段不被接受。

CLI 契约测试：

- parser 不再暴露 `--llm-model` 和 `--llm-timeout`。
- `doctor`、`translate`、`run-all` 和会触发正文翻译的写回相关命令支持 `--llm-client`。

运行装配测试：

- `load_runtime_setting()` 使用所选客户端配置 `LLMHandler`。
- 翻译运行使用所选客户端的模型名。

报告与观测测试：

- 翻译摘要 JSON 含 `llm_client` 对象。
- debug 模型消息写出客户端名称、`provider_type` 和模型，同时保持密钥脱敏。
- `doctor` 摘要显示本次检查的客户端。

Skill 与文档测试：

- 运行 `uv run python scripts/generate_skill_protocol.py --check`。
- 文档不再展示旧单客户端配置和旧模型环境变量覆盖。

## 验证要求

本改动触及 Python 源码、CLI 契约、配置、Skill 和文档。交付前必须执行：

```powershell
uv run basedpyright
$env:ATT_MZ_RUST_THREADS = "1"
uv run pytest -q -n 12 --dist=load --durations=30 --durations-min=0.5
uv run python scripts/generate_skill_protocol.py --check
```

若实现过程中触及 Rust 原生扩展、构建流程或发行流程，还必须补充 Rust 格式检查、clippy 和 Rust 测试。

## 风险与边界

- 这是破坏性配置变更。旧 `setting.toml` 必须手动改成多客户端格式后才能继续运行。
- 删除模型地址/API Key 环境变量覆盖后，临时测试脚本不能再依赖旧变量伪造模型服务；对应脚本和文档必须同步调整。
- 当前只实现 `openai` 类型。后续新增 `gemini` 时，应在 `provider_type` 分派层新增客户端配置和请求门面，不能把 Gemini 特例塞进 OpenAI 兼容请求路径。
