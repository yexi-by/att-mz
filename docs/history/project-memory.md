# 项目历史记忆

本文极度压缩 `docs/` 中开发过程文档、spec、plan、review、批次记录和归档材料所沉淀的长期记忆。它不作为当前运行契约；当前事实仍以源码、schema、README、Skill、wiki 和测试为准。

## 1. 从 Python 全量扫描到 Rust/SQLite 主路径

项目早期最大问题是大游戏下非网络 CLI 反复构建 `GameData`、文本范围、插件源码 AST、Note、占位符和写回探针，导致状态查询、工作区验收、质量报告都变成重型命令。后续通过 Rust Scope/Index、warm index、scan budget 和分阶段命令迁移，把重型扫描与当前事实逐步推向 Rust/SQLite。留下的原则是：性能问题不能靠局部缓存糊住，必须收束事实源、复用当前索引，并用真实 CLI 计时证明。

## 2. 从路径定位到当前文本事实身份

Text Fact 这条线的核心不是版本名，而是项目意识到路径不是身份：同一路径可能有多个可翻译事实，保存译文、质量错误、规则命中和写回都必须绑定当前 fact 与 hash。`location_path` 只适合展示、排序和用户定位，不适合作为成功事实。留下的原则是：用户路径不是数据身份，当前事实必须可稳定重建、可校验、可写回。

## 3. 契约失忆化

大量历史词汇曾进入运行时、错误文案、测试、README 和 Skill：旧环境变量、旧数据库、旧索引、迁移、fallback、版本化旧名等。契约失忆化的结论是，当前系统只需要“当前契约有效 / 输入无效”，不需要让用户、测试或 Agent 理解历史形态。留下的原则是：历史只进历史记录，当前代码和当前文档只描述现在。

## 4. 规则运行时统一

外部规则曾分散在 Python、Rust、多个 domain 表、多个正则方言和多个校验入口里，导致 validate、import、rebuild、quality、write-back 对同一规则给出不同结论。PCRE2 规则运行时这条线的核心，是把用户和 Agent 可写规则统一进 Rust rule runtime、domain adapter、统一 store、fingerprint 和 prepare/commit 生命周期。留下的原则是：规则不是文件读写小功能，而是一条完整生命周期。

## 5. 生产链路真实性

多次 review 发现，新 API、新模块、新名字和测试通过都不等于主路径真的接管；`commit` 可能没有提交，`store` 可能没有写库，report 可能只是拼出成功感。后来这条经验被抽象成生产链路真实性：任何承诺都要从当前入口追到真实副作用。留下的原则是：看真实写库、写文件、清理、索引、缓存、报告和错误状态，不看名字。

## 6. 半迁移之后必须物理删除旧路径

Rust 接管一条路径后，旧 Python scanner、extractor、helper、fixture、mock、re-export 和测试 oracle 常常继续存在，造成双事实源或假安全感。冗余删除这条线的核心不是“清理文件”，而是防止旧实现继续塑造当前测试和维护者直觉。留下的原则是：不用的生产路径和只为旧测试存在的东西要退场，不能靠 guard、raise 或注释当删除。

## 7. 诊断和性能证据要有边界

debug timings、LLM 消息观测和性能记录共同沉淀出一个判断：诊断是功能，但不能污染普通报告，也不能 per-row、per-text 打点制造新成本。`scan_budget` 只能防复杂度回退，不能替代当前 HEAD 的真实 CLI 性能证据。留下的原则是：普通用户看行动摘要，开发者用 debug artifact，性能结论必须有命令级证据。

## 8. Agent、Skill、docs 的事实边界

曾经 docs、Skill、README、测试互相固定流程事实，导致历史文档反过来约束当前实现。后来项目明确：docs 给人读，Skill 是 Agent 执行契约，`skills/att-mz-protocol/` 是生成源，README 面向用户，wiki 描述当前实现。留下的原则是：Agent 契约不要放 docs，docs 也不要覆盖 CLI、Skill、schema 或代码事实。

## 9. Review 工作流从一次性审查变成长期尺子

多子代理 review、契约失忆化 review、Rust 主路径 review、半迁移 review 最后都沉淀成更通用的四把尺子：当前契约、单一事实源、生产链路真实性、冗余删除。留下的原则是：以后不要为每次大审查重新发明审查方法，直接调用长期 Review Spec。

## 10. RPG Maker 全系列支持不能硬套 MV/MZ 模型

RGSS、LCF、MV/MZ 共享“数据库、事件、脚本或扩展文本”这类业务概念，但文件格式完全不同。未来支持 VX、VX Ace、XP、2000、2003 时，不能把一切转成普通 JSON 硬套现有链路，而要用引擎适配层生成统一翻译视图和写回定位。留下的原则是：业务流程可统一，解析和写回必须尊重引擎事实。

## 过程文档退场原则

上述记忆承接后，过程文档不应再作为日常入口。批次记录、执行计划、一次性 spec 和大型归档材料的原文追溯交给 git 历史；当前仓库只保留压缩后的长期记忆。若某段历史结论仍影响当前开发，应优先沉淀到 `AGENTS.md`、`docs/wiki/` 或 `docs/superpowers/review-specs/`，而不是继续引用原始流水文档。
