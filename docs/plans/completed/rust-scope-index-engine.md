# Rust Scope/Index Engine 性能改造计划

状态：已完成（已下线）
日期：2026-06-03
范围：本计划限定 Rust Scope/Index Engine 性能改造，不包含完整 Rust CLI 重写。

## 执行约定

本文是源码开发的人类计划与验收索引，不是翻译流程 Agent 契约，也不覆盖项目 `AGENTS.md`、Codex Skill、源码测试或公开 CLI 契约。新会话可以用本文定位下一批源码开发任务；实际执行仍必须遵循当前仓库源码、测试、项目规范、相关工程 Skill 和公开外部契约。若本文与这些更具体依据冲突，以更具体依据为准，并把冲突写入当批验收记录。

执行按批次推进，每轮对话完成一个可验证批次。一个批次必须包含：本批范围、涉及文件、先建立或调整的行为测试、删除或收束的旧路径、运行命令和结果、性能证据、外部契约变化、剩余风险和下一批入口。上一批没有验收记录时，不进入下一批。

每个批次先建立保护网，再改生产代码。保护网优先是行为级测试、外部 JSON/CLI 契约测试、扫描预算测试和性能基线；确实只能用静态审计证明的项目，必须说明不能动态验证的原因。

## 批次进度

| 批次 | 状态 | 验收记录 | 下一批入口 |
| --- | --- | --- | --- |
| 1. 结构审计、性能基线和扫描预算表 | 已完成 | `docs/records/rust-scope-index/batches/batch-001.md` | 配置收口并删除 `ATT_MZ_RUST_THREADS` |
| 2. 配置收口 | 已完成 | `docs/records/rust-scope-index/batches/batch-002.md` | Rust Scope/Index Engine 核心 |
| 3A. Scope/Index Engine 三入口契约与最小核心 | 已完成 | `docs/records/rust-scope-index/batches/batch-003.md` | SQLite summary schema 与真实扫描接入 |
| 3B. SQLite summary schema 与 rebuild 写入链路 | 已完成 | `docs/records/rust-scope-index/batches/batch-004.md` | 真实 Rust 扫描接入 |
| 3C. 标准 data 与事件指令 Rust 扫描最小闭环 | 已完成 | `docs/records/rust-scope-index/batches/batch-005.md` | P0 pending 导出快路径 |
| 4. P0 pending 导出快路径 | 已完成 | `docs/records/rust-scope-index/batches/batch-006.md` | P1-A 核心命令索引消费 |
| 5A. audit-coverage warm index 索引消费 | 已完成 | `docs/records/rust-scope-index/batches/batch-007.md` | text-scope 索引清单输出 |
| 5B. text-scope warm index 索引清单输出 | 已完成 | `docs/records/rust-scope-index/batches/batch-008.md` | translation-status 或 translate 前置索引消费 |
| 5C. translation-status refresh-scope 索引统计收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-009.md` | translate --max-items 前置索引消费 |
| 5D. translate --max-items warm index 前置 scope 收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-010.md` | translate --max-items 完整 index gate |
| 5E. translate --max-items 外部规则 gate 索引化 | 已完成 | `docs/records/rust-scope-index/batches/batch-011.md` | translate --max-items 插件源码/非标准 data gate 索引化 |
| 5F. translate --max-items 源码支线 gate 预检索引化 | 已完成 | `docs/records/rust-scope-index/batches/batch-012.md` | translate --max-items 术语/占位符/evaluate_scope_gate 索引化 |
| 5G. translate --max-items indexed workflow gate 去除 GameData 加载 | 已完成 | `docs/records/rust-scope-index/batches/batch-013.md` | translate --max-items Rust evaluate_scope_gate 接入 |
| 5H. translate --max-items Rust evaluate_scope_gate 最小接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-014.md` | translate --max-items 占位符/质量 gate 继续索引化 |
| 5I. translate --max-items quality gate 路径快路径 | 已完成 | `docs/records/rust-scope-index/batches/batch-015.md` | translate --max-items 占位符 gate 索引化 |
| 5J. translate --max-items 占位符 gate 元信息复用 | 已完成 | `docs/records/rust-scope-index/batches/batch-016.md` | translate --max-items text-scope gate 继续索引化 |
| 5K. translate --max-items text-scope gate 元信息复用 | 已完成 | `docs/records/rust-scope-index/batches/batch-017.md` | translate --max-items warm index 前置完整 scope 还原收束 |
| 5L. translate --max-items warm index 前置完整 scope 还原收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-018.md` | translate --max-items Rust gate 输入行读取继续收束 |
| 5M. translate --max-items SQL pending 总数收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-019.md` | translate --max-items 启动运行记录前置统计继续收束 |
| 5N. translate --max-items no-pending 小批读取早退 | 已完成 | `docs/records/rust-scope-index/batches/batch-020.md` | translate --max-items 术语加载和批次构建前置继续收束 |
| 5O. translate --max-items max-batches 批次构建收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-021.md` | translate --max-items 术语加载边界继续收束 |
| 5P. translate --max-items 空术语 prompt 索引跳过 | 已完成 | `docs/records/rust-scope-index/batches/batch-022.md` | translate --max-items 非空术语索引裁剪审计 |
| 5Q. translate --max-items 非空术语 prompt 索引预裁剪 | 已完成 | `docs/records/rust-scope-index/batches/batch-023.md` | translate --max-items GameData 派生术语元信息审计 |
| 5R. translate --max-items 地图显示名术语上下文索引化 | 已完成 | `docs/records/rust-scope-index/batches/batch-024.md` | translate --max-items 数据库条目名称术语上下文索引化 |
| 5S. translate --max-items 数据库条目名称术语上下文索引化 | 已完成 | `docs/records/rust-scope-index/batches/batch-025.md` | translate --max-items System 字段术语上下文索引化 |
| 5T. translate --max-items System 字段术语上下文索引化 | 已完成 | `docs/records/rust-scope-index/batches/batch-026.md` | translate --max-items prompt context 索引元信息收尾审计 |
| 5U. translate --max-items prompt context 索引元信息收尾审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-027.md` | 写回相关命令可写范围与质量 gate 复用索引事实审计 |
| 5V. 写回相关命令可写范围与质量 gate 复用索引事实审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-028.md` | 写回快路径索引行读取与 fallback 自动重建继续收束 |
| 5W. 写回快路径 SQL gate 摘要收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-029.md` | 写回入口索引缺失/过期自动重建审计 |
| 5X. 写回入口索引缺失/过期自动重建审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-030.md` | 写回计划可写路径直连 SQLite/Rust 评估 |
| 5Y. 写回计划可写路径直连 SQLite/Rust 评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-031.md` | P1-B 工作区和规则命令迁移审计 |
| 6A. P1-B 工作区和规则命令静态审计矩阵 | 已完成 | `docs/records/rust-scope-index/batches/batch-032.md` | 插件源码候选扫描 Rust 入口 |
| 6B. 插件源码候选扫描 Rust 入口 | 已完成 | `docs/records/rust-scope-index/batches/batch-033.md` | scan-plugin-source-text 薄适配接入 |
| 6C. scan-plugin-source-text 薄适配接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-034.md` | export-plugin-source-ast-map Rust 候选接入 |
| 6D. export-plugin-source-ast-map Rust 候选接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-035.md` | prepare-agent-workspace 插件源码风险报告接入 Rust AST map 事实 |
| 6E. prepare-agent-workspace 插件源码风险报告接入 Rust 事实 | 已完成 | `docs/records/rust-scope-index/batches/batch-036.md` | validate-agent-workspace 插件源码支线候选事实接入 Rust |
| 6F. validate-agent-workspace 插件源码支线候选事实接入 Rust | 已完成 | `docs/records/rust-scope-index/batches/batch-037.md` | validate-plugin-source-rules 插件源码候选事实接入 Rust |
| 6G. validate-plugin-source-rules 插件源码候选事实接入 Rust | 已完成 | `docs/records/rust-scope-index/batches/batch-038.md` | import-plugin-source-rules 插件源码候选事实接入 Rust |
| 6H. import-plugin-source-rules 插件源码候选事实接入 Rust | 已完成 | `docs/records/rust-scope-index/batches/batch-039.md` | 插件源码运行审计和写回定位相关路径候选事实审计 |
| 6I. 插件源码运行审计和写回定位相关路径候选事实审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-040.md` | 翻译源 `PluginSourceScan` 通用 fallback 接入 Rust-derived scan |
| 6J. 翻译源 `PluginSourceScan` 通用 fallback 接入 Rust-derived scan | 已完成 | `docs/records/rust-scope-index/batches/batch-041.md` | active runtime 插件源码扫描缓存 Rust 化审计和接入 |
| 6K. active runtime 插件源码扫描缓存 Rust-AST runtime 入口接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-042.md` | 写回诊断源码扫描缓存与 write map source scan 审计 |
| 6L. diagnose-active-runtime 写回映射 source scan 接入 runtime 字面量扫描 | 已完成 | `docs/records/rust-scope-index/batches/batch-043.md` | 写回探针 fallback 与旧 `build_plugin_source_scan` 公共导出审计 |
| 6M. 写回探针 fallback 接入 runtime 字面量扫描 | 已完成 | `docs/records/rust-scope-index/batches/batch-044.md` | 旧 `build_plugin_source_scan` 公共导出与翻译源 strict scan 保留边界审计 |
| 6N. 旧插件源码扫描公共导出收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-045.md` | 旧 scanner 主扫描本体私有化或测试夹具替换评估 |
| 6O. 旧 scanner 主扫描本体私有化 | 已完成 | `docs/records/rust-scope-index/batches/batch-046.md` | 旧 scanner 测试夹具 Rust-derived 替换评估 |
| 6P. 旧 scanner 测试夹具首组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-047.md` | 旧 scanner 测试夹具第二组 Rust-derived 替换 |
| 6Q. 旧 scanner 写回测试夹具第二组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-048.md` | 旧 scanner 测试夹具第三组 Rust-derived 替换 |
| 6R. 旧 scanner 规则排除测试夹具第三组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-049.md` | 旧 scanner 测试夹具第四组 Rust-derived 替换 |
| 6S. 旧 scanner 工作流/备份测试夹具第四组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-050.md` | 旧 scanner 测试夹具第五组 Rust-derived 替换 |
| 6T. AgentToolkit 规则输入测试夹具第五组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-051.md` | 旧 scanner 测试夹具第六组 Rust-derived 替换 |
| 6U. AgentToolkit 导入/质量/TextScope 测试夹具第六组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-052.md` | 旧 scanner 测试夹具第七组 Rust-derived 替换 |
| 6V. 剩余旧 scanner 残留夹具第七组 Rust-derived 替换与边界保护 | 已完成 | `docs/records/rust-scope-index/batches/batch-053.md` | 旧 scanner 私有兼容入口删除或替代评估 |
| 6W. feedback runtime 夹具第八组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-054.md` | workspace/write-plan/rule-import 残留夹具替换评估 |
| 6X. workspace/write-plan/rule-import 夹具第九组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-055.md` | 旧 scanner repo-wide 残留入口审计 |
| 6Y. 旧 scanner repo-wide 残留入口审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-056.md` | 共享 fixture legacy 导出删除或隔离评估 |
| 6Z. 共享 fixture legacy 导出收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-057.md` | 旧 scanner 语义测试收束评估 |
| 6AA. 旧 scanner 语义测试首组 Rust-derived 替换 | 已完成 | `docs/records/rust-scope-index/batches/batch-058.md` | 旧 scanner batch/cache 对照测试保留边界审计 |
| 6AB. 旧 scanner batch/cache 对照测试保留边界审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-059.md` | 旧 scanner 私有 helper 删除评估 |
| 6AC. 旧 scanner 私有 helper 删除评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-060.md` | 旧 scanner 历史记录残留收尾审计 |
| 6AD. 旧 scanner 历史记录残留收尾审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-061.md` | 插件源码支线收束回归审计 |
| 6AE. 插件源码支线收束回归审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-062.md` | P1-B 插件源码阶段收束回顾 |
| 6AF. P1-B 插件源码阶段收束回顾 | 已完成 | `docs/records/rust-scope-index/batches/batch-063.md` | P1-B 非标准 data 支线入口审计 |
| 6AG. P1-B 非标准 data 支线入口审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-064.md` | 非标准 data Rust 候选入口最小契约 |
| 6AH. 非标准 data Rust 候选入口最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-065.md` | 非标准 data 规则校验覆盖统计 native 化 |
| 6AI. 非标准 data 规则校验覆盖统计 native 化 | 已完成 | `docs/records/rust-scope-index/batches/batch-066.md` | 非标准 data 已导入规则提取链路 native leaves 复用 |
| 6AJ. 非标准 data 已导入规则提取链路 native leaves 复用 | 已完成 | `docs/records/rust-scope-index/batches/batch-067.md` | 非标准 data 已导入规则链路重复 native leaves 扫描收束审计 |
| 6AK. 非标准 data 已导入规则链路重复 native leaves 扫描收束审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-068.md` | 非标准 data 支线收束回归审计 |
| 6AL. 非标准 data 支线收束回归审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-069.md` | P1-B 非标准 data 阶段收束回顾 |
| 6AM. P1-B 非标准 data 阶段收束回顾 | 已完成 | `docs/records/rust-scope-index/batches/batch-070.md` | P1-B 普通占位符支线入口审计 |
| 6AN. P1-B 普通占位符支线入口审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-071.md` | 普通占位符 Rust 候选入口最小契约 |
| 6AO. 普通占位符 Rust 候选入口最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-072.md` | 普通占位符扫描命令薄适配接入 |
| 6AP. 普通占位符扫描命令薄适配接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-073.md` | 普通占位符覆盖报告 native 化 |
| 6AQ. 普通占位符覆盖报告 native 化 | 已完成 | `docs/records/rust-scope-index/batches/batch-074.md` | 普通占位符 workflow gate native 化审计 |
| 6AR. 普通占位符 workflow gate native 化审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-075.md` | 普通占位符 workspace manifest native 化 |
| 6AS. 普通占位符 workspace manifest native 化 | 已完成 | `docs/records/rust-scope-index/batches/batch-076.md` | 普通占位符 workspace 草稿生成 native 化评估 |
| 6AT. 普通占位符 workspace 草稿生成 native 化评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-077.md` | 普通占位符 build-placeholder-rules 草稿生成 native 化评估 |
| 6AU. 普通占位符 build-placeholder-rules 草稿生成 native 化评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-078.md` | 普通占位符 build-placeholder-rules 预览/手动边界 native 化评估 |
| 6AV. 普通占位符 build-placeholder-rules 预览/手动边界 native 化评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-079.md` | 普通占位符支线收束回归审计 |
| 6AW. 普通占位符支线收束回归审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-080.md` | P1-B 普通占位符阶段收束回顾 |
| 6AX. P1-B 普通占位符阶段收束回顾 | 已完成 | `docs/records/rust-scope-index/batches/batch-081.md` | P1-B 结构化占位符支线入口审计 |
| 6AY. P1-B 结构化占位符支线入口审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-082.md` | 结构化占位符 Rust 候选入口最小契约 |
| 6AZ. 结构化占位符 Rust 候选入口最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-083.md` | 结构化占位符扫描命令 native 薄适配接入 |
| 6BA. 结构化占位符扫描命令 native 薄适配接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-084.md` | 结构化占位符覆盖报告 native 化 |
| 6BB. 结构化占位符覆盖报告 native 化 | 已完成 | `docs/records/rust-scope-index/batches/batch-085.md` | 结构化占位符 workflow gate native 化审计 |
| 6BC. 结构化占位符 workflow gate native 化审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-086.md` | 结构化占位符旧 helper 删除或隔离评估 |
| 6BD. 结构化占位符旧 helper 删除或隔离评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-087.md` | 结构化占位符支线收束回归审计 |
| 6BE. 结构化占位符支线收束回归审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-088.md` | P1-B 结构化占位符阶段收束回顾 |
| 6BF. P1-B 结构化占位符阶段收束回顾 | 已完成 | `docs/records/rust-scope-index/batches/batch-089.md` | P1-B Note 标签支线入口审计 |
| 6BG. P1-B Note 标签支线入口审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-090.md` | Note 标签 Rust 候选入口最小契约 |
| 6BH. Note 标签 Rust 候选入口最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-091.md` | Note 标签扫描命令 native 薄适配接入 |
| 6BI. Note 标签扫描命令 native 薄适配接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-092.md` | Note 标签规则校验 native 候选接入 |
| 6BJ. Note 标签规则校验 native 候选接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-093.md` | Note 标签规则导入 native 候选接入 |
| 6BK. Note 标签规则导入 native 候选接入 | 已完成 | `docs/records/rust-scope-index/batches/batch-094.md` | Note 标签导入后旧 handler/common 收束评估 |
| 6BL. Note 标签导入后旧 handler/common 收束评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-095.md` | Note 标签支线收束回归审计 |
| 6BM. Note 标签支线收束回归审计 | 已完成 | `docs/records/rust-scope-index/batches/batch-096.md` | Note 标签 scope hash/text-scope native 化评估 |
| 6BN. Note 标签 scope hash/text-scope native 化评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-097.md` | Note 标签 scope hash/count native 薄适配 |
| 6BO. Note 标签 scope hash/count native 薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-098.md` | Note 标签 text-scope 逐命中 native 明细评估 |
| 6BP. Note 标签 text-scope 逐命中 native 明细评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-099.md` | Note 标签逐命中 Rust 明细最小契约 |
| 6BQ. Note 标签逐命中 Rust 明细最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-100.md` | Note 标签 text-scope native 明细替换评估 |
| 6BR. Note 标签 text-scope native 明细替换评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-101.md` | Note 标签 text-scope native 明细薄适配 |
| 6BS. Note 标签 text-scope native 明细薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-102.md` | NoteTagTextExtraction native 明细替换评估 |
| 6BT. NoteTagTextExtraction native 明细替换评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-103.md` | NoteTagTextExtraction native 来源存在契约补强 |
| 6BU. NoteTagTextExtraction native 来源存在契约补强 | 已完成 | `docs/records/rust-scope-index/batches/batch-104.md` | NoteTagTextExtraction native 明细薄适配 |
| 6BV. NoteTagTextExtraction native 明细薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-105.md` | P1-B Note 标签阶段收束回顾 |
| 6BW. P1-B Note 标签阶段收束回顾 | 已完成 | `docs/records/rust-scope-index/batches/batch-106.md` | P1-B 工作区和规则命令阶段总收束回顾 |
| 6BX. P1-B 工作区和规则命令阶段总收束回顾 | 已完成 | `docs/records/rust-scope-index/batches/batch-107.md` | P1-B 预算事实来源复核 |
| 6BY. P1-B 预算事实来源复核 | 已完成 | `docs/records/rust-scope-index/batches/batch-108.md` | P1-B 事件指令候选 Rust 入口评估 |
| 6BZ. P1-B 事件指令候选 Rust 入口评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-109.md` | P1-B 事件指令 Rust 候选入口最小契约 |
| 6CA. P1-B 事件指令 Rust 候选入口最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-110.md` | P1-B 事件指令候选薄适配接入评估 |
| 6CB. P1-B 事件指令候选薄适配接入评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-111.md` | P1-B export-event-commands-json native samples 薄适配 |
| 6CC. P1-B export-event-commands-json native samples 薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-112.md` | P1-B validate-event-command-rules native hit details 适配评估 |
| 6CD. P1-B validate-event-command-rules native hit details 适配评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-113.md` | P1-B validate-event-command-rules native hit details 最小契约补强 |
| 6CE. P1-B validate-event-command-rules native hit details 最小契约补强 | 已完成 | `docs/records/rust-scope-index/batches/batch-114.md` | P1-B validate-event-command-rules native hit details 薄适配 |
| 6CF. P1-B validate-event-command-rules native hit details 薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-115.md` | P1-B import-event-command-rules native hit details 适配评估 |
| 6CG. P1-B import-event-command-rules native hit details 薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-116.md` | P1-B 插件参数规则 validate/import 迁移评估与最小契约 |
| 6CH. P1-B 插件参数规则 validate/import 迁移评估与最小契约 | 已完成 | `docs/records/rust-scope-index/batches/batch-117.md` | P1-B 插件参数规则 validate/import 薄适配与旧路径收束 |
| 6CI. P1-B 插件参数规则 validate/import 薄适配与旧路径收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-118.md` | P1-B MV 虚拟名字框 export/validate/import 迁移评估 |
| 6CJ. P1-B MV 虚拟名字框 export/validate/import 迁移评估 | 已完成 | `docs/records/rust-scope-index/batches/batch-119.md` | P1-B MV 虚拟名字框命令族 native 薄适配 |
| 6CK. P1-B MV 虚拟名字框命令族 native 薄适配 | 已完成 | `docs/records/rust-scope-index/batches/batch-120.md` | P1-B 源文残留 validate/import 迁移评估与契约补强 |
| 6CL. P1-B 源文残留 validate/import 迁移评估与契约补强 | 已完成 | `docs/records/rust-scope-index/batches/batch-121.md` | P1-B 源文残留 validate/import 薄适配与旧路径收束 |
| 6CM. P1-B 源文残留 validate/import 薄适配与旧路径收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-122.md` | P1-B 工作区和规则命令总收束 |
| 6CN. P1-B 工作区和规则命令总收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-123.md` | P1-C 运行审计命令组 |
| 7A. P1-C 运行审计命令组 | 已完成 | `docs/records/rust-scope-index/batches/batch-124.md` | P1-C 术语和语言探测命令组 |
| 7B. P1-C 术语和语言探测命令组 | 已完成 | `docs/records/rust-scope-index/batches/batch-125.md` | P1-C 插件导出和文档契约收束 |
| 7C. P1-C 插件导出和文档契约收束 | 已完成 | `docs/records/rust-scope-index/batches/batch-126.md` | 全计划收束验收 |
| 7D. 全计划收束验收 | 已完成 | `docs/records/rust-scope-index/batches/batch-127.md` | 已下线，无下一批入口 |

## 计划下线状态

7D 完成后，本计划已从活跃推进态下线；剩余批次数为 0 批，无剩余批次。后续不再从本文新增 Rust Scope/Index Engine 分批任务；若发现新的性能缺陷、外部契约变化或 Rust 原生能力缺口，必须新建独立计划或 issue，并重新建立 RED/GREEN、scan_budget/记录保护和验证边界。

## 结论

本计划目标是把当前性能缺陷相关的重型扫描、文本范围构建、候选筛选、质量统计和覆盖统计收口到 Rust + SQLite 快路径。Python 保留 CLI 编排、配置读取、模型调用、报告组装和数据库事务编排职责，不再承担大规模文本扫描和筛选职责。

性能验收以逐命令改造前后对比为准。P0/P1 命令必须显著降低耗时，并消除不合理复杂度、重复全量扫描、`limit` 后置和 O(N^2) Python 筛选。90% 降幅作为排查阈值：未达到时必须说明剩余耗时来自磁盘 I/O、报告输出、SQLite 写入、AST 解析或其他必要成本。

## 已确认的问题

在 `Summer Stolen v0.2` 上已经确认：

- `export-pending-translations --limit 20` 超过 600 秒仍未完成。
- `translation-status --refresh-scope` 在索引缺失后重建文本索引约 63 秒，其中构建文本范围约 52 秒。
- `doctor --game ... --no-check-llm` 约 66 秒。
- `audit-coverage` 约 59 秒。
- `text-scope` 约 63 秒，输出约 43MB。
- `quality-report` 约 13 秒。
- `scan-plugin-source-text` 约 4 秒。
- `scan-nonstandard-data` 约 3 秒。

已有验证表明，根因不是 SQLite 本身。直接从 text index 查询 pending 的耗时低于 0.1 秒，瓶颈在 Python 侧：

- `app/agent_toolkit/services/manual_translation.py` 构建完整 `TextScopeService` 后再筛选 pending，`limit` 在全量筛选后才应用。
- `app/text_scope/models.py` 的 `writable_paths` 每次访问都会重新遍历全部 entries，导致大样本下接近 O(N^2)。
- 多个 CLI 命令会重复加载 `GameData`、重复构建 `TextScopeService`、重复扫描插件源码或非标准 data。

## 非目标

- 不做完整 Rust CLI 重写。
- 不删除 Python CLI 外壳。
- 不迁移模型调用、OpenAI SDK 调用、prompt 组装和翻译 worker。
- 不重写发行版构建流程。
- 不为旧数据库做静默兼容转换；旧 schema 或旧索引不符合当前契约时显式失败或要求重建。
- 不为了追求 90% 数字牺牲外部契约、错误可解释性和测试可维护性。

## P0 / P1 范围

### P0

P0 是本次性能缺陷的直接修复对象。

- `export-pending-translations --limit N`

要求：

- `limit` 必须在 SQLite 或 Rust 层提前生效。
- 不能为了导出前 N 条 pending 构建完整 Python `TextScopeService`。
- 有效 text index 可用时目标返回时间小于 3 秒。
- text index 缺失或失效时允许触发一次 Rust 索引重建，但不能进入 O(N^2) Python 筛选。

### P1-A 核心慢链路

这些命令直接参与翻译、范围索引、质量报告、覆盖审计或写回，必须作为核心验收命令：

- `rebuild-text-index`
- `translation-status --refresh-scope`
- `text-scope`
- `audit-coverage`
- `quality-report`
- `export-quality-fix-template`
- `import-manual-translations`
- `reset-translations`
- `translate`
- `run-all`
- `write-back`
- `rebuild-active-runtime`
- `write-terminology`

要求：

- 对每个命令记录改造前和改造后耗时。
- 不允许重复构建文本范围，除非报告说明不可复用原因。
- `translate --max-items N` 的前置门禁不能再构建完整 Python scope 后才读取 indexed pending。
- 写回相关命令的前置检查、质量 gate 和可写路径过滤要复用同一个 Rust/SQLite 范围事实。

### P1-B 规则、候选和工作区命令

这些命令不一定全部实测慢，但静态调用链会触发全量扫描、AST 扫描、非标准 data 扫描、text index 或规则覆盖检查，必须纳入本次审计：

- `prepare-agent-workspace`
- `validate-agent-workspace`
- `scan-plugin-source-text`
- `export-plugin-source-ast-map`
- `scan-nonstandard-data`
- `export-nonstandard-data-json`
- `validate-nonstandard-data-rules`
- `import-nonstandard-data-rules`
- `scan-placeholder-candidates`
- `validate-placeholder-rules`
- `build-placeholder-rules`
- `import-placeholder-rules`
- `validate-structured-placeholder-rules`
- `scan-structured-placeholder-candidates`
- `import-structured-placeholder-rules`
- `export-note-tag-candidates`
- `validate-note-tag-rules`
- `import-note-tag-rules`
- `export-event-commands-json`
- `validate-event-command-rules`
- `import-event-command-rules`
- `validate-plugin-rules`
- `import-plugin-rules`
- `validate-plugin-source-rules`
- `import-plugin-source-rules`
- `export-mv-virtual-namebox-candidates`
- `validate-mv-virtual-namebox-rules`
- `import-mv-virtual-namebox-rules`
- `validate-source-residual-rules`
- `import-source-residual-rules`

要求：

- 命令可以共享 Rust Scope/Index Engine、插件源码扫描、非标准 data 扫描或 SQLite 快路径。
- 不是每个命令都必须单独重写，但每个命令都必须被静态审计并标注处理结论。
- 如果命令仍保留 Python 路径，必须说明规模边界和不迁移原因。

### P1-C 静态审计但排序靠后

这些命令需要纳入审计表，但不作为第一批实现入口：

- `audit-active-runtime`
- `diagnose-active-runtime`
- `verify-feedback-text`
- `export-terminology`
- `import-terminology`
- `probe-source-language`
- `export-plugins-json`

要求：

- 它们是否受益于 Rust Scope/Index Engine 要明确记录。
- 如果瓶颈来自真实运行文件审计、术语上下文生成或输出文件大小，不得归因为 scope/index 问题。

### 暂不纳入 P1

这些命令不是本次 Scope/Index 性能缺陷主链路：

- `list`
- `add-game`
- `reset-game`
- `cleanup-agent-workspace`
- `restore-font`

## 目标架构

### 单一事实来源

建立一个 Rust Scope/Index Engine，统一负责：

- 扫描 RPG Maker 标准 data JSON。
- 扫描插件参数。
- 扫描事件指令参数。
- 扫描 Note 标签。
- 扫描 MV 虚拟名字框候选。
- 扫描插件源码 AST 候选。
- 扫描非标准 data 文件候选。
- 判断文本是否进入正文翻译。
- 判断文本是否可写回。
- 生成稳定 `location_path`。
- 生成 text index 写入记录。
- 生成候选覆盖和规则命中统计所需的中间索引。

Python 不再并行维护大规模文本范围事实。Python 可以把 Rust 结果转换成现有 JSON 报告，但不能重新全量扫描做重复验证。

### 结构审计交付物

正式实现前必须先形成结构审计交付物，用于防止性能改造变成“新增一套 Rust 机制，但旧 Python 路径仍在默认流程里运行”。

必须产出以下审计表：

1. 主流程图
   - 覆盖 P0、P1-A、P1-B 三类命令。
   - 按真实运行顺序列出输入、配置解析、文本范围产生、门禁判断、数据库写入、报告输出和失败暴露位置。
   - 标注每一步的权威事实来源。

2. 事实来源矩阵

| 业务结论 | 权威产出位置 | 消费位置 | 是否允许重复计算 | 旧来源处理 |
| --- | --- | --- | --- | --- |
| 当前可处理范围 | Rust `build_scope_index` / text index | CLI、质量报告、覆盖审计、工作区、写回 | 否 | 删除或改为薄适配层 |
| 当前可写范围 | Rust `build_scope_index` / `evaluate_scope_gate` | pending 导出、写回、质量报告、覆盖审计 | 否 | 删除 Python 重复推导 |
| pending 列表 | SQLite text index 快路径 | pending 导出、翻译批次准备 | 否 | 删除 Python 全量筛选 |
| 规则命中统计 | Rust scope summary / rule hit summary | 工作区、规则校验、覆盖审计 | 否 | 删除 Python 全量统计 |
| 插件源码候选 | Rust `scan_rule_candidates` | 插件源码扫描、工作区、规则校验 | 否 | 删除 Python AST 扫描主路径 |
| 非标准 data 候选 | Rust `scan_rule_candidates` | 非标准 data 扫描、工作区、规则校验 | 否 | 删除 Python 扫描主路径 |
| 质量门禁结果 | Rust `evaluate_scope_gate` / Rust quality | 质量报告、写回、翻译门禁 | 否 | 删除重复门禁 |
| Rust 线程数 | `[runtime].rust_threads` | 所有 Rust 并行入口、报告摘要 | 否 | 删除环境变量入口 |
| Rust API 契约版本 | `app/native_contract.py` 与 Rust native contract | `build_scope_index`、`scan_rule_candidates`、`evaluate_scope_gate` 和已有 native 热路径 | 否 | 禁止只检查函数存在而跳过版本门槛 |

3. 门禁链审计
   - 明确输入校验、规则校验、工作流门禁、质量门禁、写回前检查和写后审计各自职责。
   - 每个门禁必须消费同一个核心结果，禁止因为“不信任上一层”而重复扫描。
   - 报告环节只能展示或解释门禁结果，不能重新计算业务结论。

4. 旧路径删除清单
   - 每个新增 Rust 能力必须写明替代哪条 Python 旧路径。
   - 每条旧路径必须分类为：删除、改为薄适配层、外部契约保留但显式失败、测试夹具保留。
   - 不允许把旧路径作为默认流程的永久回退路径。

5. 测试分类清单
   - 标记必须保留的外部行为契约测试。
   - 标记会锁死旧结构的内部形态测试，并在对应批次中改写。
   - 新增测试必须优先覆盖业务行为、外部报告、失败路径和扫描预算，不绑定临时内部函数形态。

6. 文档和指令审计
   - 检查 README、Skill、开发文档、CLI 契约和 AGENTS.md 是否仍描述当前实现。
   - 删除或修正文档中关于旧路径、旧环境变量、旧扫描流程和多事实来源的描述。
   - AGENTS.md 不应把本次改造中的临时实现细节固化成长期规则。

7. 外部契约矩阵
   - 覆盖 CLI 子命令和参数、stdout Agent JSON、SQLite schema、`setting.toml`、Rust native payload、工作区 JSON、README、Skill、日志摘要和 benchmark 脚本。
   - 对每个契约标注处理方式：保持不变、破坏性调整、显式失败或仅历史记录保留。
   - 任何破坏性调整都必须有测试或静态审计固定，不允许只写在交付说明里。

8. 批次验收记录
   - 每个批次结束时记录本批改了什么、删了什么旧路径、验证了什么、哪些命令耗时变化、哪些风险仍保留。
   - P0/P1 命令要有 burn-down 表：命令、改造前耗时、改造后耗时、剩余耗时归因、旧路径处理结论、验证命令。
   - 若本批发现计划遗漏的慢命令或旧路径，先更新 P0/P1 范围和事实来源矩阵，再继续实现。

### SQLite 快路径

`text_index_items` 是索引有效状态下的主要查询入口。以下查询必须从数据库或 Rust 层提前筛选：

- pending count
- pending list with limit
- translated count
- quality error count
- writable count
- unwritable count
- rule/domain coverage count
- requested paths validation
- reset/import 路径归属校验

除非命令的外部契约要求输出完整清单，否则禁止在 Python 中读取全量记录后再做大规模筛选。

本计划需要新增 summary 表，而不是只复用 `text_index_items`。最低限度新增：

- `text_index_scope_summary`：保存当前索引的总量、可翻译量、可写量、不可写量、规则过期量、扫描耗时摘要和 Rust 原生线程数。
- `text_index_domain_summary`：按 domain 保存 item 数、active 数、writable 数、unwritable 数、inactive rule hit 数。
- `text_index_rule_hit_summary`：按规则 domain 和稳定 rule key 保存 hit 数、extractable 数、writable 数、unwritable 数。

动态统计，例如 pending、translated、quality error，继续通过 `text_index_items` 与译文/错误表查询得出，不写进静态 summary，避免第二事实来源。

### Rust 线程配置

新增全局配置：

```toml
[runtime]
rust_threads = "auto"
```

语义：

- `"auto"`：Rust 使用自动线程数。
- 正整数：Rust 使用指定线程数。
- 不接受 `0`、负数、空字符串或无法解析的文本。

实现要求：

- `setting.toml` 是唯一入口。
- `setting.example.toml` 必须声明默认值。
- `app/config/schemas.py` 增加严格配置模型，完成 pydantic 校验。
- Python 调用 Rust 时必须显式传入线程配置。
- Rust 侧删除 `ATT_MZ_RUST_THREADS` 读取逻辑。
- 测试和 benchmark 脚本不得再设置或断言 `ATT_MZ_RUST_THREADS`。
- `native_thread_count` 的报告值要来自本次配置，而不是环境变量。

### 已决策实现选择

本节把关键设计点定案，执行时按这里的边界推进。

#### Rust API 入口

不采用单一大型 JSON 入口，也不为每个 CLI 单独开 Rust 原生 API。采用三个稳定入口族：

1. `build_scope_index`
   - 唯一允许做完整翻译源扫描的入口。
   - 输出 text index rows、scope summary、domain summary、rule hit summary、candidate summary、unwritable reasons、过期规则明细。
   - 用于 `rebuild-text-index`、索引缺失或失效后的 rebuild、`text-scope` 完整清单和 P1-A/P1-B 的共享范围事实。

2. `scan_rule_candidates`
   - 使用和 `build_scope_index` 相同的 Rust 扫描器，但只返回某些规则支线需要的候选报告。
   - 用于插件源码、非标准 data、占位符、结构化占位符、Note、事件、插件规则、MV 虚拟名字框等 P1-B 命令。
   - 命令内已有 `build_scope_index` 结果时必须复用该结果，不允许再扫一遍。

3. `evaluate_scope_gate`
   - 消费 scope/index rows、已保存译文和规则摘要，返回工作流门禁、质量门禁、可写路径和写回前置检查需要的 compact summary。
   - 用于 `quality-report`、`write-back`、`rebuild-active-runtime`、`write-terminology` 等仍需要 compact gate 结果的路径；`translate --max-items` warm index 已预检路径的 workflow gate 使用 index metadata / SQLite summary，pending 总数使用 SQLite COUNT。

pending 查询不做 Rust API。有效 text index 下由 Python persistence 层直接执行 SQLite 查询，例如 `read_pending_text_index_items(limit=N)`。这是数据库快路径，不是 Python 全量扫描。

所有新增 Rust 入口都必须纳入现有 native contract 版本门槛。Python adapter 不能只检查函数是否存在；版本不匹配时必须显式失败，并输出用户可理解的中文摘要。

#### Schema 决策

schema 必须升级，计划按当前 schema 之后新增一版。实现时如果当前 schema 号已变化，使用“当前最新 + 1”，但迁移内容必须包含 scope summary、domain summary、rule hit summary 三类能力。

summary 表只保存由当前文本范围和规则决定的静态事实。译文状态、pending 状态、质量错误状态仍通过查询实时计算。

#### P1-B 策略

P1-B 不采用 Python 共享扫描缓存作为过渡方案。交付时，P1-B 涉及的大规模文本、候选、AST、非标准 data 扫描必须由 Rust 执行。

允许 Python 保留：

- CLI 参数解析。
- JSON 报告渲染。
- 工作区文件写出。
- 小规模输入文件解析。
- 数据库事务编排。

不允许 Python 保留：

- 全量文本范围扫描。
- 插件源码 AST 扫描。
- 非标准 data 文本候选扫描。
- 大规模占位符覆盖扫描。
- 规则命中全量统计。
- 为了校验而重复构建一份当前文本范围。

执行者可以按实际代码结构调整模块名、结构体名和局部拆分，但不能改变上述入口族、summary 表能力和 P1-B Rust 迁移边界。

#### 旧实现清理要求

Rust Scope/Index Engine 接管对应职责后，旧 Python 重型实现必须删除或改造成薄适配层，禁止保留隐藏回退路径、兼容旁路或第二套事实来源。

必须清理的旧实现包括：

- Python 全量 `TextScopeService` 构建路径中已由 Rust 接管的扫描、候选汇总、可写路径判断和规则命中统计。
- Python 插件源码 AST 扫描主路径。
- Python 非标准 data 文本候选扫描主路径。
- Python 大规模占位符覆盖扫描主路径。
- Python 中读取全量记录后再筛选 pending、coverage、路径归属校验、rule hit summary 的代码路径。
- `ATT_MZ_RUST_THREADS` 的生产读取、benchmark 注入、测试断言和文档说明。

允许保留的代码仅限：

- CLI 参数解析和报告渲染。
- Rust 结果到现有 JSON schema 的转换。
- 数据库事务编排。
- 小规模输入文件解析。
- 测试夹具和公共契约样例。

如果某个旧函数仍需保留名称以维持内部调用稳定性，其实现必须只委托到 Rust 或 SQLite 快路径，并通过测试证明不会执行旧的 Python 全量扫描。

## 主要改造步骤

### 1. 建立结构审计、性能基线和扫描预算表

目标：固化 P0/P1 命令的主流程、事实来源、旧路径处理方式、重型扫描次数和实测耗时。

涉及文件：

- `tests/scan_budget_contract.py`
- `tests/test_scan_budget.py`
- `scripts/benchmark_small_tasks.py`
- `scripts/benchmark_rebuild_active_runtime.py`
- `scripts/benchmark_active_runtime_audit.py`
- `docs/plans/completed/rust-scope-index-engine.md`
- 新增或更新一份性能基线记录文档。

任务：

- 补齐主流程图、事实来源矩阵、门禁链审计、旧路径删除清单、测试分类清单和文档指令审计。
- 建立外部契约矩阵，逐项标注 CLI、stdout JSON、SQLite schema、配置、Rust payload、工作区 JSON、Skill/README 和 benchmark 脚本的处理方式。
- 建立 CLI/Agent 主链路金丝雀测试，使用临时 `ATT_MZ_HOME`、临时游戏夹具和假模型服务覆盖注册、工作区准备、规则导入、`translate --max-items`、`quality-report`、`export-pending-translations --limit` 和可执行范围内的写回前置检查。
- 每条新增 Rust 能力都必须对应至少一条旧 Python 路径处理结论。
- 把 P0/P1 命令全部纳入扫描预算表。
- 标注每个命令允许的 `GameData` 加载、scope 构建、候选扫描、AST 扫描、quality gate 和 write plan 次数。
- benchmark 脚本移除 `--rust-threads` 通过环境变量传递的设计，改为生成临时 `setting.toml`。
- 记录 `Summer Stolen v0.2` 改造前性能数据。

### 2. 配置收口

涉及文件：

- `setting.example.toml`
- `app/config/schemas.py`
- `app/config/overrides.py`
- `app/cli/runtime.py`
- `app/native_quality.py`
- `rust/src/native_core/pool.rs`
- `rust/src/lib.rs`
- `tests/test_config_overrides.py`
- `tests/test_native_adapters.py`
- benchmark 相关测试。

任务：

- 新增 `RuntimeSetting`，字段 `rust_threads: Literal["auto"] | PositiveInt` 或等价 pydantic 校验。
- 删除 `ATT_MZ_RUST_THREADS` 的生产读取。
- Rust 暴露统一线程配置入口，例如 `configure_runtime_threads` 或在每个重型 Rust 原生 API 入参中传递线程数。
- 所有 Rust 并行入口使用同一个池配置函数。
- 修改错误文案，不再出现 `ATT_MZ_RUST_THREADS`。

### 3. Rust Scope/Index Engine 核心

建议新增 Rust 模块：

- `rust/src/native_core/scope_index/mod.rs`
- `rust/src/native_core/scope_index/models.rs`
- `rust/src/native_core/scope_index/data_scan.rs`
- `rust/src/native_core/scope_index/plugin_config.rs`
- `rust/src/native_core/scope_index/plugin_source.rs`
- `rust/src/native_core/scope_index/nonstandard_data.rs`
- `rust/src/native_core/scope_index/placeholders.rs`

Python 桥接：

- `app/native_scope_index.py`
- `app/text_index.py`
- `app/text_scope/builder.py`
- `app/text_scope/models.py`

任务：

- Rust 输入使用结构化 payload，不做路径硬编码。
- Rust 输出包含 text index rows、domain summary、rule hit summary、unwritable reasons、过期规则明细和可写路径集合。
- Rust API 按 `build_scope_index`、`scan_rule_candidates`、`evaluate_scope_gate` 三个入口族实现。
- SQLite schema 增加 scope/domain/rule hit summary 能力，迁移版本使用“当前最新 + 1”。
- Python `TextScopeService` 逐步收敛为薄适配层，优先消费 Rust 结果。
- 修掉 `writable_paths` 重复构建问题，即使过渡期保留 Python model，也必须缓存或直接使用 Rust 输出集合。
- Rust 入口接管后删除旧 Python 重型实现，避免保留并行扫描路径。

### 4. P0 快路径

涉及文件：

- `app/agent_toolkit/services/manual_translation.py`
- `app/persistence/text_index_records.py`
- `app/persistence/repository.py`
- `tests/test_agent_toolkit_manual_import.py`
- `tests/test_manual_translation_scope.py`

任务：

- `export-pending-translations --limit N` 先检查 text index。
- 有效 index 可用时直接 `read_pending_text_index_items(limit=N)`。
- text index 缺失或失效时触发一次 Rust rebuild，再走数据库 limit 查询。
- `include-write-probe` 如需要完整写回探针，必须由 Rust scope/index 或 write plan 一次性给出，不允许 Python 全量二次筛选。
- 增加测试证明 `limit` 不会构建全量 pending list。

### 5. P1-A 核心命令迁移

涉及文件：

- `app/agent_toolkit/services/text_index.py`
- `app/agent_toolkit/services/coverage.py`
- `app/agent_toolkit/services/quality.py`
- `app/agent_toolkit/services/manual_translation.py`
- `app/application/handler.py`
- `app/application/write_back_gate.py`
- `app/text_index.py`
- `app/text_scope/*`
- `tests/test_text_index.py`
- `tests/test_agent_toolkit_coverage.py`
- `tests/test_agent_toolkit_quality_report.py`
- `tests/test_agent_toolkit_translation_limits.py`
- `tests/test_write_back_transactions.py`

任务：

- `rebuild-text-index` 改为 Rust 构建 scope/index rows。
- `translation-status --refresh-scope` 只在索引缺失或失效时重建，统计走 SQLite。
- `text-scope` 输出完整清单时可以读取全量，但清单来源必须是 Rust/index，不重新 Python 扫。
- `audit-coverage` 使用 index/domain summary。
- `quality-report` 在索引有效时避免读取全量 index 后再由 Python 大规模筛选；质量明细需要 Rust 原生质量检查时，按当前已保存译文子集处理。
- `translate --max-items` warm index 已预检路径的前置 gate 改用 index metadata / SQLite summary，不构建完整 Python scope；pending 总数走 SQLite COUNT，批次输入仍由 `read_pending_text_index_items(limit=N)` 在 SQL 层限制。
- `write-back`、`rebuild-active-runtime`、`write-terminology` 的可写路径和质量 gate 复用 Rust 范围事实。

### 6. P1-B 工作区和规则命令迁移

涉及文件：

- `app/agent_toolkit/services/workspace.py`
- `app/agent_toolkit/services/rule_validation.py`
- `app/agent_toolkit/services/placeholder_rules.py`
- `app/agent_toolkit/services/nonstandard_data.py`
- `app/plugin_source_text/*`
- `app/nonstandard_data/*`
- `app/event_command_text/*`
- `app/note_tag_text/*`
- `tests/test_agent_toolkit_workspace.py`
- `tests/test_agent_toolkit_rule_import.py`
- `tests/test_agent_toolkit_diagnostics.py`
- `tests/test_nonstandard_data.py`
- `tests/test_plugin_source_text.py`

任务：

- `prepare-agent-workspace` 一次加载和扫描，所有输出复用同一 Rust scope/index/candidate result。
- `validate-agent-workspace` 消费 manifest，并复用一次候选扫描结果。
- 插件源码 AST 扫描迁到 Rust 统一入口，Python 只渲染风险报告和规则文件。
- 非标准 data 扫描迁到 Rust 统一入口，Python 只渲染风险报告、导出工作区和执行数据库事务。
- 占位符、结构化占位符、Note、事件、插件规则校验全部优先消费 Rust/index 结果。

### 7. P1-C 审计命令处理

涉及文件：

- `app/agent_toolkit/services/quality.py`
- `app/agent_toolkit/services/feedback.py`
- `app/application/handler.py`
- `app/source_language_probe.py`
- `app/terminology/*`

任务：

- 标注每个命令是否受 Rust Scope/Index Engine 影响。
- 对真实 active runtime 审计、术语上下文生成、源语言探测等命令，区分真实 I/O/输出成本和 scope/index 成本。
- 仅迁移共享热点；不为边缘命令新增独立复杂抽象。

### 8. 删除环境变量契约

涉及文件：

- `rust/src/native_core/pool.rs`
- `rust/src/native_core/javascript_ast.rs`
- `rust/src/native_core/write_back_plan/test_support.rs`
- `tests/test_benchmark_small_tasks.py`
- `tests/test_benchmark_active_runtime_audit.py`
- `tests/test_benchmark_rebuild_active_runtime.py`
- `docs/wiki/development/native-core.md`
- `README.md`
- `skills/att-mz*/references/cli-command-contract.md` 中涉及相关文案的部分。

任务：

- 删除 `ATT_MZ_RUST_THREADS` 文案、测试、benchmark env 注入和 Rust 读取。
- 测试改为 `setting.toml` 或直接 Rust 原生 API 参数。
- 文档只描述 `[runtime].rust_threads`。

## 验收标准

### 行为标准

- P0/P1 命令外部 JSON schema、退出码和主要错误文案保持当前契约，除非计划中明确记录破坏性变更。
- 旧索引、错配规则和无法重建的状态必须显式报错。
- `limit`、`--max-items` 等限制参数必须在数据库或 Rust 层真实参与调度。
- 不允许吞异常、伪造成功或静默降级到旧 Python 全量慢路径。
- Rust 接管后的旧 Python 重型实现必须删除或变成薄适配层，不允许保留隐藏回退路径或第二套事实来源。
- 每个核心业务结论必须能在事实来源矩阵中找到唯一权威产出位置。
- 每条旧路径必须能在旧路径删除清单中找到处理结论。

### 性能标准

- 每个 P0/P1-A 命令必须提供改造前和改造后耗时表。
- P0 必须从超时或长时间无可用结果改为 3 秒内可用。
- P1-A 必须大幅下降；未达到 90% 时要给出剩余耗时归因。
- P1-B 完成静态审计，并把大规模文本、候选、AST、非标准 data 扫描迁到 Rust；有实测条件的命令补充改造前后耗时对比。

### 测试标准

必须执行：

```powershell
uv run basedpyright
uv run pytest
cargo fmt --manifest-path rust/Cargo.toml -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

新增或更新测试：

- 配置链路：`[runtime].rust_threads` 定义、解析、校验、应用、报告。
- 环境变量删除：`ATT_MZ_RUST_THREADS` 不再影响线程数。
- P0：`export-pending-translations --limit N` 不构建全量 pending list。
- 扫描预算：P0/P1 命令不会重复构建 scope 或重复扫描候选。
- Rust scope/index：大样本索引构建、路径稳定性、可写路径、规则命中和错误路径。
- SQLite 快路径：pending count/list、路径归属校验、coverage summary。
- schema 迁移：scope summary、domain summary、rule hit summary 写入和读取。
- 工作区命令：prepare/validate 复用一次候选扫描。
- CLI/Agent 主链路金丝雀：临时应用目录、临时游戏夹具、假模型服务和公开 CLI 命令能串起本次性能路径，不依赖真实用户配置或真实模型额度。
- Rust native contract：`build_scope_index`、`scan_rule_candidates`、`evaluate_scope_gate` 和已有 Rust 热路径版本不匹配时显式失败。
- 旧实现清理：静态搜索确认 `ATT_MZ_RUST_THREADS` 和被替代的 Python 重型扫描入口不再作为生产路径存在。
- 测试改写：不再断言被删除的旧 Python 重型函数必须存在，只断言外部行为和报告契约。

### 文档标准

- README、Skill、开发文档和 CLI 契约必须只描述改造后的当前实现。
- 历史对比、迁移原因和性能缺陷记录只能放在 `CHANGELOG.md`、迁移说明或审查记录中。
- 文档示例不得写入本机私有路径、用户名或用户数据。
- 文档不得把旧路径或旧环境变量描述成可用入口。

## 风险

- Rust Scope/Index Engine 输出结构会成为新的核心契约，必须用测试固定 path 稳定性。
- `text-scope` 这类完整报告命令仍可能受 43MB 输出成本限制，不能把输出 I/O 误判成扫描性能退化。
- 插件源码 AST 和非标准 data 扫描迁移到 Rust 后，需要保持现有风险分类和报告字段。
- 当前工作区存在大量未提交变更，正式实现前必须确认变更归属，避免误改无关文件。

## 实现前停止条件

满足任一条件时，不得进入对应批次实现：

- 主流程图未覆盖当前批次命令。
- 事实来源矩阵缺少当前批次涉及的业务结论。
- 新 Rust 能力没有对应旧路径处理结论。
- 当前批次外部契约未列明。
- 当前批次没有可执行的验收记录格式，或上一批验收记录缺少验证命令、性能证据、旧路径处理结论。
- 当前批次测试仍要求旧 Python 重型函数作为生产路径存在。
- 当前批次涉及 README、Skill、CLI 契约或 AGENTS.md，但没有完成文档和指令审计。

## 实施顺序

1. 完成结构审计、性能基线和扫描预算表。
2. 完成配置收口并删除 `ATT_MZ_RUST_THREADS`，因为这是所有 Rust 并行路径的共同入口。
3. 完成 P0 pending 导出快路径，修复 P0 性能缺陷。
4. 实现 Rust Scope/Index Engine 最小闭环：标准 data、插件参数、事件、Note、可写路径、text index rows。
5. 接入 `rebuild-text-index`、`translation-status --refresh-scope`、`translate --max-items`。
6. 接入 `quality-report`、`audit-coverage`、`text-scope`。
7. 接入写回前置检查和 write plan 复用。
8. 接入工作区和规则命令。
9. 执行完整验证，并生成 `Summer Stolen v0.2` 改造前后性能表。
