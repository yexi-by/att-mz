# RPG Maker 全系列汉化适配理论支持

本文说明 RPG Maker 主要 PC 引擎家族在汉化工具中的可支持边界、共通抽象、文件格式差异和落地顺序。结论来自官方手册、日文与英文技术资料、中文社区资料、公开工具实践和项目已有调研交叉验证。

## 一、核心结论

RPG Maker 系列可以按运行时和数据格式分成三类：LCF 系列、RGSS 系列、HTML5 系列。三类都存在“数据库、地图、事件、系统术语、脚本或扩展规则”等概念，但底层存储完全不同，不能用同一套 JSON 读取链路直接覆盖。

| 引擎家族 | 代表版本 | 运行时 | 主要数据格式 | 脚本或扩展形态 | 适配结论 |
| --- | --- | --- | --- | --- | --- |
| LCF | RPG Maker 2000 / 2003 | `RPG_RT.exe` | `RPG_RT.ldb`、`RPG_RT.lmt`、`Map####.lmu` | 无 RGSS/JS 插件体系，依赖事件和可执行文件补丁生态 | 需要独立 LCF 解析层，不能套 RGSS 或 MV/MZ JSON |
| RGSS1 | RPG Maker XP | Ruby / RGSS1 | `Data/*.rxdata` | `Scripts.rxdata` 中的 Ruby 脚本 | 需要 Ruby Marshal 反序列化、RGSS 类桩和 Ruby 解析 |
| RGSS2 | RPG Maker VX | Ruby / RGSS2 | `Data/*.rvdata` | `Scripts.rvdata` 中的 Ruby 脚本 | 与 XP/VA 同属 RGSS，但类结构、事件参数和归档版本不同 |
| RGSS3 | RPG Maker VX Ace | Ruby / RGSS3 | `Data/*.rvdata2` | `Scripts.rvdata2` 中的 Ruby 脚本 | 可优先适配，但必须处理 Marshal、脚本压缩、归档和字体布局 |
| HTML5 | RPG Maker MV / MZ | JavaScript + NW.js / 浏览器 | `data/*.json`、`js/plugins.js` | `js/plugins/*.js` 插件和插件参数 | 当前工具主支持对象，数据链路可直接基于 JSON 和 JavaScript 解析 |

因此，“支持全系列”的正确设计不是把所有版本转换成普通 JSON 后复用主流程，而是在引擎适配层生成统一的翻译源视图、写回定位和质量检查输入。每个适配层必须保证无修改往返、可定位写回和运行文件审计。

## 二、交叉验证后的事实边界

### MV / MZ

MV/MZ 的核心数据是明文 JSON。官方 MV 插件规格说明插件文件放在 `js/plugins`，编辑器把启用状态和参数写入 `js/plugins.js`，并使用 UTF-8。官方 MZ 转换资料列出地图、数据库、系统术语等数据位于 `data/*.json`，并说明 MV 插件数据在 MZ 中不保证可直接使用。

对汉化工具而言，MV/MZ 可以作为 JSON 和 JavaScript 文本处理：

- 标准数据库和地图事件读取 `data/*.json`。
- 插件参数读取 `js/plugins.js`。
- 插件源码文本必须经过 JavaScript 解析或明确规则筛选。
- Note 标签、插件命令、事件指令参数和源码硬编码文本需要规则导入，不能由程序猜测语义。

### RGSS：XP / VX / VX Ace

RGSS 系列的核心数据不是 JSON。官方 RGSS 手册把 `load_data` 定义为读取文件并执行 `Marshal.load`，把 `save_data` 定义为 `Marshal.dump`。VX 手册对 `.rvdata` 也给出相同机制，VX Ace 手册对 `.rvdata2` 也给出相同机制。

VX Ace 官方 RGSS3 规格还说明：

- 加密发布时，数据和图像通常位于 `Game.rgss3a`，音频和字体通常不在归档内。
- `load_data` 能从加密归档读取数据。
- 存在加密归档时，脚本数据会从归档读取。
- RGSS 使用 UTF-8，RPG Maker 输出的脚本和文本数据是 UTF-8。

社区脚本和日文技术资料进一步验证了 `Scripts.rvdata2` 的常见结构：先 `Marshal.load` 得到脚本条目数组，每个条目包含脚本 ID、脚本名和源码字段，源码字段需要 `Zlib::Inflate.inflate` 还原为 Ruby 源码。写回时需要按相同结构压缩和序列化。

对汉化工具而言，RGSS 适配必须具备：

- 归档识别、解包、写回或补丁生成。
- Ruby Marshal 反序列化和序列化。
- 最小 RGSS 类桩，例如 `RPG::Actor`、`RPG::Event`、`RPG::EventCommand`、`RPG::MoveCommand`、`Table`、`Color`、`Tone` 等。
- 对标准数据库字段、事件指令、脚本源码分别建立文本领域。
- Ruby 源码必须通过 AST 或等价解析方式定位字符串，不能用全局正则替换。

### LCF：RPG Maker 2000 / 2003

RPG Maker 2000/2003 使用 LCF 文件族。公开格式资料和 EasyRPG / Makerpendium 资料确认：

- `RPG_RT.ldb` 保存数据库、开关、变量等全局数据。
- `RPG_RT.lmt` 保存地图树和地图全局关系。
- `Map####.lmu` 保存单张地图数据。
- LCF 文件是带标识和分块结构的二进制格式，不是 JSON，也不是 Ruby Marshal。

对汉化工具而言，2000/2003 应作为独立适配层处理，优先复用 `liblcf`、EasyRPG 相关工具或等价解析器。它与 RGSS 系列共享“事件命令”和“数据库文本”概念，但不共享序列化机制、脚本语言或归档规则。

## 三、可复用的统一抽象

不同引擎可以统一到同一个翻译中间模型，但中间模型必须来自可信解析结果，而不是从文件里搜索字符串。

统一模型至少包含：

- 文本原文。
- 文本领域，例如数据库名称、数据库说明、地图显示名、事件正文、选项、滚动文本、系统术语、插件参数、脚本 UI 文本。
- 引擎类型和数据来源。
- 可写回定位。
- 上下文信息，例如地图名、事件名、数据库对象名、事件页、指令编号。
- 原样保留规则，例如控制符、变量插值、资源名、脚本标识符、格式化占位符。
- 行宽和字体布局参数。
- 写回后审计所需的确定性映射。

这套模型可以让翻译、质量检查、术语表、占位符、日志和报告保持统一；读取、定位和写回仍由每个引擎适配层负责。

## 四、文本来源分层

### 标准数据库文本

标准数据库文本包括角色、职业、技能、物品、武器、防具、敌人、状态、系统术语、类型名、属性名、开关名、变量名、地图名等。

MV/MZ 中这些文本位于 `data/*.json`。RGSS 中这些文本是 Marshal 对象图字段。LCF 中这些文本位于 `RPG_RT.ldb` 和相关分块。适配层应导出稳定对象路径，写回时修改结构化字段。

### 地图与事件文本

RPG Maker 系列长期保留了事件命令列表这一抽象，常见结构包含指令编码、缩进层级和参数数组。MV 官方文档把事件命令 JSON 结构描述为 `code`、`indent`、`parameters`；VX Ace 官方数据结构也包含 `RPG::EventCommand`。

事件命令编号和参数语义不能跨版本硬套。显示文本、后续文本行、选项、滚动文本、注释、脚本调用、插件命令、移动路线脚本等都可能包含玩家可见文本或运行协议。适配层必须按引擎版本和规则导入结果提取。

### 插件、脚本和自定义 UI 文本

MV/MZ 的扩展文本主要来自插件参数、插件命令、Note 标签和 JavaScript 源码。RGSS 的扩展文本主要来自 `Scripts.rxdata`、`Scripts.rvdata`、`Scripts.rvdata2` 中的 Ruby 源码。2000/2003 的扩展文本通常来自事件系统、可执行文件补丁生态或工具生成数据。

脚本源码处理必须区分：

- 玩家可见字符串。
- 资源文件名。
- 内部 key、Symbol、方法名、常量名、类名。
- Ruby 插值 `#{...}`、JavaScript 模板表达式、`sprintf` / `%s` / `%d` 格式化片段。
- 游戏控制符和窗口绘制协议。
- 注释、帮助文本和编辑器说明。

只翻译配置区字符串会漏掉自定义菜单、标题界面、状态页、战斗 UI、任务系统、日志系统和自定义对话框。全局翻译所有字符串会破坏资源路径、内部协议和脚本逻辑。正确做法是 AST 定位、规则筛选、预览命中、用户或 Agent 确认、语法检查、再写回。

## 五、编码、字体与布局原则

编码不能用“某个系列固定 Shift-JIS”或“统一 UTF-8 补丁”概括。

- MV/MZ 按官方插件规格使用 UTF-8。
- VX Ace 官方 RGSS3 规格说明 RGSS 使用 UTF-8，RPG Maker 输出的脚本和文本数据是 UTF-8。
- RGSS 游戏可能包含外部 Ruby 文件、第三方脚本、文本资源或补丁，它们的编码需要检测和记录。
- 2000/2003 的日文游戏常见 CP932 / Shift-JIS 生态，翻译到中文时需要同时处理编码、字体和运行时渲染能力。

汉化适配应把编码作为输入事实检测和运行能力验证，不应默认注入通用补丁。字体、字号、窗口宽度、换行、控制符宽度和目标语言字形覆盖都属于功能验收范围。

## 六、归档与发布形态

MV/MZ 部署目录可能出现项目根布局或 `www` 布局，标准数据仍可通过 `data`、`js`、`fonts` 等目录定位。

RGSS 系列可能以明文 `Data` 目录分发，也可能使用 `Game.rgssad`、`Game.rgss2a`、`Game.rgss3a` 归档。官方资料说明 VX Ace 加密归档格式未公开，且存在脚本读取归档的限制。工具支持这类游戏时应输出清晰边界：

- 能只读识别归档版本和文件清单。
- 能在合法授权场景下解包或生成覆盖补丁。
- 能保留路径大小写、目录分隔符和归档入口顺序。
- 能在写回后验证游戏运行时可读取。

2000/2003 通常以目录文件形式分发，重点是 LCF 文件结构、RTP 依赖、字体和可执行文件补丁兼容。

## 七、落地架构

全系列支持应拆成以下边界：

1. **引擎识别层**：根据 `data/System.json`、`Game.ini`、`Game.rgss3a`、`Data/*.rvdata2`、`RPG_RT.ldb` 等信号判断引擎和目录布局。
2. **容器层**：处理普通目录、RGSSAD 归档、部署目录和补丁输出。
3. **结构解码层**：MV/MZ 解析 JSON；RGSS 执行 Marshal 反序列化；LCF 解析分块数据。
4. **可信中间层**：生成带可写回定位的翻译源视图，不暴露内部对象给模型。
5. **文本领域层**：按标准数据、事件、插件参数、Note 标签、脚本源码等领域提取文本。
6. **规则层**：导入术语、占位符、插件规则、事件指令规则和源文残留例外。
7. **翻译层**：只给模型提供原文、必要上下文、术语表、输出协议和原样保留约束。
8. **质量层**：检查漏翻、控制符破坏、插值破坏、源文残留、行宽超限和脚本语法。
9. **写回层**：按确定性定位修改原结构，执行无修改和有修改往返验证。
10. **运行审计层**：检查玩家实际运行文件，反推问题时只使用写回阶段保存的确定性映射。

## 八、建议适配顺序

1. **VX Ace 只读 inspector**：识别 `Game.ini`、`Data/*.rvdata2`、`Game.rgss3a`，输出文件清单、引擎信号和风险报告。
2. **VX Ace Marshal dumper**：用最小 RGSS3 类桩导出标准数据和事件命令中间结构，不写回。
3. **VX Ace 无修改往返**：反序列化后再序列化，验证可 `Marshal.load`，必要时启动真实游戏做标题和菜单检查。
4. **VX Ace 标准数据翻译**：覆盖数据库名称、说明、系统术语、地图显示名和标准事件文本。
5. **VX Ace 脚本只读分析**：导出脚本源码，构建 Ruby AST 命中报告，只统计候选，不写回。
6. **VX Ace 脚本写回**：按 AST 定位替换字符串，执行 Ruby 语法检查和游戏启动检查。
7. **VX / XP 适配**：复用 RGSS 架构，分别补齐 RGSS2 和 RGSS1 类桩、文件后缀、归档版本和事件差异。
8. **2000/2003 适配**：接入 LCF 解析器，覆盖 `RPG_RT.ldb`、`RPG_RT.lmt`、`Map####.lmu` 的数据库和事件文本。

## 九、必须停止的条件

出现以下情况时，工具应停止并报告原因、影响和下一步处理方式：

- 引擎类型无法识别或多个引擎信号冲突。
- 归档无法合法解包或无法确认写回策略。
- Marshal 对象缺少必要类桩，无法稳定定位字段。
- LCF 分块无法解析或存在未知关键字段。
- 脚本源码无法还原、无法解析或语法检查失败。
- 候选文本无法区分玩家可见文本和内部协议。
- 控制符、插值、格式化占位符或资源路径规则未确认。
- 写回定位缺失，无法保证修改对应到同一条原文。
- 字体或行宽无法满足目标语言运行验证。

## 十、结论

RPG Maker 全系列汉化可以统一在“文本提取、翻译、质量检查、写回审计”的业务流程上，但不能统一在“文件读取方式”上。MV/MZ 是 JSON 和 JavaScript 解析问题；XP/VX/VX Ace 是归档、Ruby Marshal 对象图和 Ruby 脚本解析问题；2000/2003 是 LCF 二进制分块解析问题。

可靠支持的判断标准是：能识别引擎、能解出可信结构、能生成稳定可写回定位、能无修改往返、能保护运行协议、能验证写回后的实际运行文件。达不到这些条件时，只能做只读诊断或候选报告，不能进入消耗模型额度的正文翻译和写回。

## 交叉验证资料

- RPG Maker VX Ace RGSS3 规格：说明加密归档、脚本读取限制和 UTF-8 字符集。<https://rpgmaker.fixato.org/Manual/RPGVXAce/rgss/rgss.html>
- RPG Maker VX Ace RGSS 内置函数：说明 `load_data` / `save_data` 与 `Marshal.load` / `Marshal.dump` 的关系。<https://rpgmaker.fixato.org/Manual/RPGVXAce/rgss/g_functions.html>
- RPG Maker VX RGSS 内置函数：说明 `.rvdata` 使用相同 Marshal 读取与保存机制。<https://www.rpg-maker.fr/dl/monos/aide/vx/source/rgss/g_functions.html>
- RPG Maker VX Ace 数据结构：列出 `RPG::EventCommand`、`RPG::Map`、`RPG::Actor`、`RPG::System` 等对象类型。<https://rpgmaker.fixato.org/Manual/RPGVXAce/rgss/g_rpg_data.html>
- RPG Maker MV 插件规格：说明 `js/plugins`、`js/plugins.js`、插件参数、Note 元数据和 UTF-8。<https://rpgmakerofficial.com/product/MV_Help/page/01_11_03.html>
- RPG Maker MZ 官方 MV 数据转换资料：列出 `data/*.json` 迁移范围，并说明插件数据不保证可用。<https://rpgmakerofficial.com/product/mz/course/convert/convert.html>
- MakerDev / Makerpendium LCF 资料：说明 `Map####.lmu`、`RPG_RT.lmt`、`RPG_RT.ldb` 的职责。<https://dev.makerpendium.de/docs/lucifer/lmu-en.htm>、<https://www.makerpendium.de/wiki/RPG_RT.ldb>
- `Scripts.rvdata2` 导出脚本实践：验证 `Marshal.load` 后脚本源码字段需要 `Zlib::Inflate.inflate`。<https://gist.github.com/FiXato/5323361>
- 中文 RGSS 资料：说明 XP/VX/VX Ace 分别对应 RGSS1/RGSS2/RGSS3，以及 `Scripts.rxdata`、`Scripts.rvdata`、`Scripts.rvdata2`。<https://rpgmaker.wiki/index.php/RGSS>
