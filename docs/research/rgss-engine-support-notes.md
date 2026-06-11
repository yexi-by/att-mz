# RGSS 引擎支持调研记录

本文记录两个非 MV/MZ 样本的处理经验，供后续支持 RPG Maker VX / VX Ace / RGSS 系列引擎时参考。当前工具仍以 MV/MZ 为主；RGSS 支持不能复用 JSON 读取链路，需要先建立独立的引擎适配层。

## 样本结论

| 样本 | 引擎信号 | 数据形态 | 关键经验 |
| --- | --- | --- | --- |
| 勇者様は俺の嫁っ！ | `Game.rgss2a`、`TRGSSX.dll`、`Data/*.rvdata` | RGSSAD v1 归档，Ruby Marshal 对象 | 必须先解包归档，再反序列化 `rvdata`，直接扫描文件或按 JSON 思路处理都不可行 |
| レトリアの大冒険 | `Game.rgss3a`、`RGSS301.dll`、`Data/*.rvdata2` | RGSSAD v3 归档，Ruby Marshal 对象 | 除标准数据库和事件外，还要处理 `Scripts.rvdata2` 中的 Ruby 脚本文本和自定义 UI 字符串 |

两个样本共同说明：RGSS 系列的文本入口不是明文 JSON，而是“归档格式 + Ruby Marshal 对象图 + Ruby 脚本”。支持这类引擎时，正确顺序应是先反序列化，再做 Ruby / RGSS 解析；不能只靠二进制搜索、正则替换或现有 MV/MZ 数据模型硬套。

## 必要适配层

1. **归档层**
   - 识别 `Game.rgss2a`、`Game.rgss3a` 等 RGSSAD 归档头和版本。
   - 解出文件名、大小、加密 key 和 payload，保留原始相对路径。
   - 支持只读 manifest、全量解包、以及写回后重新打包或生成覆盖式补丁。

2. **Ruby Marshal 反序列化层**
   - 对 `Data/*.rvdata`、`Data/*.rvdata2` 执行 Ruby Marshal 反序列化。
   - 需要定义最小 RGSS 类桩，例如 `RPG::Actor`、`RPG::Event`、`RPG::Event::Page`、`RPG::EventCommand`、`RPG::MoveCommand` 等，让 `Marshal.load` 可以恢复对象图。
   - 反序列化后应导出稳定的中间结构，至少包含 `file`、`kind`、`object_path`、`message`、上下文名和原始对象定位信息。

3. **RGSS 文本抽取层**
   - 数据库字段：`@name`、`@description`、`@note`、系统术语、技能、物品、敌人、职业、状态等。
   - 事件指令：显示文本、选项、滚动文本、注释、脚本调用、移动路线脚本等。
   - 脚本字段：`Scripts.rvdata*` 中经压缩保存的 Ruby 源码。
   - 抽取时必须区分玩家可见文本、资源名、内部协议、变量名和脚本标识符。

4. **Ruby 解析层**
   - 需要解析 Ruby 源码中的字符串，而不是用正则全局替换。
   - 至少要识别普通字符串、转义、插值、数组、哈希、常量赋值、方法调用参数、菜单命令列表、`draw_text` / `add_command` 一类 UI 绘制文本。
   - 建议优先复用 Ruby 自带 `Ripper` 或 tree-sitter-ruby 产出 AST；如果自研解析器，必须先覆盖字符串字面量、插值和注释边界，避免误改代码。

5. **写回层**
   - 标准数据应修改反序列化后的对象字段，再 `Marshal.dump` 回原格式。
   - 脚本文本应基于 AST 定位替换字符串字面量，替换后通过 Ruby 语法检查。
   - 未改动文件应尽量保持二进制不变；改动文件必须可被原游戏运行时加载。
   - 字体、窗口尺寸和文本行宽需要独立处理，不能假设 MV/MZ 的网页字体机制适用。

## 风险点

- RGSS 对象图里会有大量内部字段。没有类桩或对象路径定位时，写回很容易破坏 Marshal 结构。
- `Scripts.rvdata*` 里常有自定义菜单、自定义对话框、自定义状态页和标题界面。只翻译数据库和事件会留下明显漏翻。
- Ruby 字符串可能包含控制符、格式协议、变量插值或脚本拼接。模型翻译前必须先转成可保护的占位符。
- 归档写回必须保留路径大小写和目录分隔符语义，否则 Windows 下可能能运行、但补丁或校验结果不稳定。
- VX、VX Ace 和 XP 的 RGSS 版本不同。本文只确认 VX / VX Ace 样本，不应把结论直接扩展成完整 XP 支持。

## 建议落地顺序

1. 做只读 RGSSAD inspector：输出归档版本、entry manifest、文件类型统计和解包预览。
2. 做 Ruby Marshal dumper：用 Ruby 类桩把 `rvdata` / `rvdata2` 导出为稳定 JSON，不写回。
3. 接入当前翻译中间格式：先覆盖数据库字段和标准事件指令，不处理脚本。
4. 做无修改 round-trip：解包、反序列化、再序列化、重打包后游戏可启动。
5. 增加 Ruby 脚本解析：先只读识别玩家可见字符串，再进入翻译和 AST 定位替换。
6. 最后接入质量检查、占位符、写回审计和补丁打包。

## 验收建议

- `extract -> serialize without changes` 后，未改动 entry 的 hash 应保持一致；必须改写的 Marshal 文件要能被 Ruby 再次 `Marshal.load`。
- 修改脚本字符串后，对脚本源码做语法检查，至少保证没有字符串边界、转义和插值破坏。
- 用真实游戏做最小启动测试：标题、读档、菜单、第一段事件文本和一个自定义 UI 页面都要覆盖。
- 把数据库文本、事件文本和脚本文本分开统计覆盖率，避免“正文已翻完”掩盖脚本 UI 漏翻。
