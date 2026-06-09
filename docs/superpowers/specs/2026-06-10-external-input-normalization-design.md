# 外部输入类型规范化设计

## 目标

本设计用于建立三类外部输入的统一类型规范化边界：游戏原文、Agent 导入数据、LLM 翻译结果。

成功状态是：这些外部输入进入业务流程前完成明确、可测试、可复用的类型规范化；业务层、数据库记录、配置、CLI、环境变量和 native 跨层契约继续只接收已经干净的当前类型。

本次当前契约为：

- 目标字段是字符串时，允许 JSON 字符串和 JSON 整数，统一输出 Python `str`。
- 目标字段是整数时，允许 JSON 整数和整数字符串，统一输出 Python `int`。
- 布尔值、浮点数、空值、数组和对象不参与字符串/整数互转。
- 规范化只发生在本设计列出的外部输入入口。
- 不符合当前契约的输入按普通无效输入处理，错误只说明当前字段要求、当前收到的问题和修正方式。

## 背景

项目的外部输入来源不同：RPG Maker 游戏文件来自真实游戏生态，Agent 导入文件来自人工或模型协作编辑，LLM 翻译结果来自模型生成 JSON。它们都属于不可信边界，可能把同一个业务标识写成 JSON 字符串或 JSON 整数。

内部运行时则不同。内部数据由本项目生成、校验和持久化，属于闭环契约，应继续保持严格类型，避免隐藏状态修正、第二事实来源和难以定位的错误。

## 非目标

- 不修改 `setting.toml` 配置契约。
- 不修改 CLI 参数契约。
- 不修改环境变量契约。
- 不修改 SQLite schema。
- 不修改 Rust native 输入输出契约。
- 不修改业务规则、写回逻辑、翻译调度、文本事实身份或质量检查语义。
- 不用递归 JSON 预处理替代模型字段声明。
- 不在运行时代码、测试、文档或错误文案中保留非当前形态的专用分支或专用命名。

## 设计原则

1. 外部宽容，内部严格：外部输入先规范化，内部流程只消费当前类型。
2. 单一事实来源：允许的类型转换只定义在一个模块，不在各入口手写 `str(...)`、`int(...)` 或散落 validator。
3. 字段显式声明：每个外部字段通过类型标注明确是否允许规范化，不做无 schema 的递归猜测。
4. 布尔值显式拒绝：JSON `true` 和 `false` 虽然在 Python 中是 `int` 子类，但不能作为整数或字符串。
5. 浮点数显式拒绝：`1.0`、`"1.0"` 和其他小数不参与整数/字符串互转。
6. 错误按当前契约表达：错误信息只描述字段当前允许什么、收到什么、如何修正。

## 转换矩阵

| 目标类型 | 输入 | 结果 |
| --- | --- | --- |
| `ExternalStr` | `"1"` | `"1"` |
| `ExternalStr` | `1` | `"1"` |
| `ExternalStr` | `true` / `false` | 失败 |
| `ExternalStr` | `1.0` | 失败 |
| `ExternalStr` | `null` | 失败 |
| `ExternalStr` | `[]` / `{}` | 失败 |
| `ExternalInt` | `1` | `1` |
| `ExternalInt` | `"1"` | `1` |
| `ExternalInt` | `true` / `false` | 失败 |
| `ExternalInt` | `1.0` | 失败 |
| `ExternalInt` | `"1.0"` | 失败 |
| `ExternalInt` | `""` | 失败 |
| `ExternalInt` | `null` | 失败 |
| `ExternalInt` | `[]` / `{}` | 失败 |

整数字符串只接受可被当前字段语义使用的十进制整数文本。是否允许负数由字段 validator 决定，例如插件下标仍必须是非负整数。

## 架构

新增模块：

- `app/external_input/__init__.py`
- `app/external_input/types.py`

`types.py` 只提供外部输入类型和错误工具，不依赖业务模块。

建议公开类型：

- `ExternalInputModel`：外部输入 Pydantic 模型基类，默认 `extra="forbid"`。
- `ExternalStr`：字符串规范化字段类型。
- `ExternalInt`：整数规范化字段类型。
- `ExternalStrList`：元素使用 `ExternalStr` 的列表类型。
- `normalize_external_str(value, field_label)`：供少量手写 JSON 边界复用。
- `normalize_external_int(value, field_label)`：供少量手写 JSON 边界复用。
- `normalize_external_str_list(value, field_label)`：供手动译文、反馈清单和 reset 输入复用。

Pydantic 字段优先使用 `Annotated[..., BeforeValidator(...)]` 定义。手写 JSON 边界只调用同一模块的函数，禁止在调用点自行实现另一套转换规则。

## 输入入口范围

### LLM 翻译结果

`TranslationResponseItem` 改为外部输入模型。

字段口径：

- `id: ExternalStr`
- `translation_lines: ExternalStrList`

解析仍先尝试严格 JSON，再只做 JSON 语法修复。JSON 语法修复不承担类型规范化；类型规范化由外部输入模型完成。

LLM 响应模型只消费 `id` 和 `translation_lines`。模型额外返回 `role`、`source_lines` 或其他无关字段时不参与业务校验，也不影响当前条目保存；这是当前外部模型输出边界的容错规则，不作为内部数据契约传播。

### Agent 导入数据

以下导入模型改用外部输入类型：

- 插件文本规则：`plugin_index` 使用 `ExternalInt`，`plugin_name` 和 `paths` 使用外部字符串类型。
- 插件源码规则：`file`、`selectors`、`excluded_selectors` 使用外部字符串类型。
- 事件指令规则：`match` 的键和值、`paths` 使用外部字符串类型；命令编码文本继续由当前 `parse_command_code` 转换为整数。
- Note 标签规则：文件模式和标签名使用外部字符串类型。
- 非标准 data 规则：`file`、`paths`、`excluded_paths` 使用外部字符串类型；`skipped` 继续必须是真实 JSON 布尔值。
- MV 虚拟名字框规则：规则名、正则、分组名、渲染模板使用外部字符串类型；枚举字段继续必须命中当前枚举值。
- 源文残留规则：定位路径、`allowed_terms`、`pattern`、`check_group`、`reason` 使用外部字符串类型。
- 手动译文导入：顶层 key 已经来自 JSON 对象键，保持字符串；`fact_id` 和 `translation_lines` 通过统一手写规范化函数处理。
- 反馈原文清单：字符串数组或对象 `texts` 字段通过统一字符串列表规范化函数处理。
- reset translations 输入：`location_paths` 通过统一字符串列表规范化函数处理。

字段业务校验继续留在各自模块，例如路径非空、路径格式、插件下标范围、正则可编译、selector 命中、规则覆盖完整性等。

### 游戏原文

RPG Maker 标准 data 模型改用外部输入类型。

字段口径：

- 标准 id、事件 code 等整数业务字段使用 `ExternalInt`。
- 玩家可见文本字段和标准文本字段使用 `ExternalStr`。
- 字符串数组字段使用 `ExternalStrList` 或等价嵌套类型。
- `EventCommand.parameters` 仍保持 JSON 值，因为事件参数可以承载字符串、数字、布尔、数组或对象；只有被具体提取规则命中的字段再按文本规则判断。

`MapInfos.json` 缺失地图检查也使用同一整数规范化函数，避免同一游戏数据入口里出现两套整数口径。

## 数据流

外部 JSON 文本进入项目后的顺序：

1. `json.loads` 或当前 JS/JSON 解码器得到动态对象。
2. `coerce_json_value` 确认对象仍属于项目允许的 JSON 值集合。
3. 外部输入模型或统一手写函数执行类型规范化。
4. 字段级业务 validator 执行非空、范围、正则、路径、覆盖命中等检查。
5. 转换为内部业务模型、数据库记录或运行时 DTO。

第 3 步之后，业务层不得继续关心字段原本来自 JSON 字符串还是 JSON 整数。

## 错误处理

错误文案必须使用当前字段语义，不描述非当前来源。

建议格式：

- `id 必须是字符串或整数，当前收到 bool`
- `plugin_index 必须是整数或整数字符串，当前收到 string: "1.0"`
- `translation_lines[0] 必须是字符串或整数，当前收到 null`
- `location_paths[2] 必须是字符串或整数，当前收到 object`

错误里可以包含字段名、数组下标、当前类型和短值样本。真实路径、用户目录、数据库表名和内部实现字段只在排障定位必要时出现。

## 测试设计

新增外部输入规范化单元测试：

- `ExternalStr` 接受字符串和整数。
- `ExternalStr` 拒绝布尔、浮点、空值、数组、对象。
- `ExternalInt` 接受整数和整数字符串。
- `ExternalInt` 拒绝布尔、浮点、小数字符串、空字符串、空值、数组、对象。
- 列表规范化能报告具体下标。

更新或新增入口测试：

- LLM 响应数字 `id` 可通过并匹配当前批次。
- LLM 响应布尔 `id` 失败。
- LLM 响应 `translation_lines` 中的整数按字符串保存。
- LLM 响应 `translation_lines` 中的布尔值失败。
- 插件规则 `plugin_index: "0"` 可导入，`plugin_index: true` 失败。
- 至少一个当前非严格规则入口覆盖字符串/整数规范化，例如事件指令规则或插件源码规则。
- 手动译文导入 `fact_id` 为整数时按当前 fact 文本比较；布尔值失败。
- 反馈清单和 reset 输入中的整数条目按字符串路径文本处理；布尔值失败。
- 游戏原文标准 `id: "1"` 可加载，`id: true` 失败。
- 游戏原文文本字段 `name: 123` 规范化为 `"123"`，`name: true` 失败。
- `MapInfos.json` 的 id 使用同一整数口径。

涉及 Python 源码和外部契约，最终验证必须执行：

- `uv run basedpyright`
- `uv run pytest`

可先执行针对性测试收敛，再跑全量。

## 实施顺序

1. 新增 `app/external_input` 模块和规范化单元测试。
2. 接入 LLM 翻译响应模型，更新 LLM 响应测试。
3. 接入 Agent 规则导入模型，统一已有严格和非严格入口。
4. 接入手写 JSON 边界，包括手动译文、反馈清单和 reset 输入。
5. 接入 RMMZ 标准游戏数据模型和 `MapInfos.json` 检查。
6. 全仓搜索 `str(`、`int(`、`isinstance(..., str)`、`isinstance(..., int)` 相关外部输入边界，删除重复转换或改用统一函数。
7. 运行 targeted tests、`uv run basedpyright`、`uv run pytest`。

## 验收标准

- 三类外部输入的字符串/整数转换口径完全来自 `app/external_input`。
- 外部输入中的 `int <-> str` 在当前字段允许时可规范化。
- 布尔值和浮点数不会被字符串/整数字段接受。
- 内部模型、配置、CLI、环境变量、数据库记录和 native 契约没有引入外部输入规范化类型。
- 错误文案只说明当前字段要求和当前输入问题。
- 测试只固定当前有效输入和当前无效输入，不保留非当前形态的专用命名或专用分支。
- `uv run basedpyright` 和 `uv run pytest` 通过。

## 风险与缓解

- 风险：一次迁移入口较多，容易漏掉手写 JSON 边界。
  - 缓解：实施中使用 `rg` 扫描 `json.loads`、`TypeAdapter`、`BaseModel`、`ensure_json_string_list`、`str(`、`int(`，并为每类入口补一个当前契约测试。
- 风险：把内部模型误改成外部输入类型。
  - 缓解：以模块名和导入方向限制边界；`app/external_input` 只能被入口解析层使用，数据库 record、native adapter 和业务运行态模型不使用。
- 风险：Pydantic 默认宽松行为继续影响未迁移模型。
  - 缓解：外部输入模型基类显式配置，入口测试覆盖字符串/整数和布尔/浮点分界。
