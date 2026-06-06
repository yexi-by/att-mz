# 非网络 CLI 性能收束完成记录

## 状态

已完成并下线。临时性能工具、runner、manifest、夹具、专用测试和生成数据只作为执行期资产使用，计划完成时已删除。

## 完成内容

- 冷索引重建改为 Rust 直接读取游戏目录并写入 SQLite，生产 CLI 不再通过 Python 完整 `TextScopeService.build()` 构建重型文本范围。
- 报告、诊断、覆盖、工作区、规则校验/导入、翻译本地阶段和写回前后本地阶段改为复用持久 text index、SQL 汇总或 Rust native 扫描结果。
- 已删除旧 Python 重型扫描、候选、校验和 AST 生产回退路径；保留的 Python 代码只承担配置、I/O 编排、JSON 报告和小规模适配。
- 工作区和占位符草稿生成改为读取 text index 轻量正文 entries，避免为小报告恢复完整 `TranslationData` map。
- 插件源码命令改为只校验自身消费的可信源快照文件，并复用同一次 native AST 结果派生报告。

## 性能结论

- 第一层核心命令真实 CLI 复测中，重建、诊断、质量、覆盖、text-scope、pending 导出、状态、翻译本地阶段和流水线本地阶段均达到 80% 目标。
- `write-back` 的写回本地阶段低于 80% 目标阈值；runner wall 仍受 Python 进程启动、日志初始化和命令框架固定成本影响。
- 第二层扩展命令中，workspace、占位符、结构化占位符、Note、事件、插件参数、MV 虚拟名字框、源文残留等重型命令均达到 80% 目标。
- 低基线小命令的 runner wall 主要被进程启动地板主导；CLI 自耗时显示非标准 data、插件源码规则、非标准 data 规则已达 80%-90% 或更高，插件源码 AST map 在 80% 阈值附近波动，剩余瓶颈为命令启动、配置初始化、源码读取和候选 JSON 输出。

## 验证边界

最终收束保留生产行为测试、scan budget 保护、CLI JSON 契约测试、Rust 门禁和类型检查；不保留本轮临时性能工具链。
