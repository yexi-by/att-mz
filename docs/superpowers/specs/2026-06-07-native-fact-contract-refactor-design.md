# Native Fact Contract 完整重构设计

## 背景

当前规则候选、术语需求、占位符覆盖、运行源码审计、CLI 输出和手动译文导入分别由不同模块处理。部分能力已经迁到 Rust 原生扩展，但 Python 侧仍保留了一些扫描、归类、报告和门禁判断。结果是同一类事实会在导出、校验、写回和报告之间出现细小缝隙。

本设计要处理的不是单个样本里的特殊现象，而是收束这些缝隙背后的共同根因：

- 事实来源分散。
- Rust/Python 职责边界不够硬。
- CLI 大报告输出策略不统一。
- 导出、校验、写回之间存在契约漂移。
- 部分错误解释依赖用户或 Agent 回看原始明细。
- 部分运行审计把正则、压缩器或 eval 包裹代码当作用户可见文本风险。
- 手动译文导入只能全有全无，不能在显式选择下保存有效项。

本设计采用完整重构，但交付方式是多个连续提交。每个提交必须完成一个可验证里程碑，最终删除旧的重复事实来源，避免长期并存两套判断。

## 目标

- 建立 `Native Fact Contract`，由 Rust 统一产出规则候选、覆盖关系、分类、默认严重级别、解释 hint 和 scope hash。
- 让 MV virtual namebox 的导出、术语候选、workspace 校验和 write-back 使用同一批 speaker requirements。
- 让 structured placeholder 候选覆盖同时考虑 standard、custom 和 structured placeholder span。
- 让 active runtime 审计使用原生 literal classification 区分正则、packer/eval 包裹、用户可见候选和未知文本。
- 在控制符错误路径提供稳定 hint，解释类似 `\fb21st` 的可能拆分，不改变主解析规则。
- 统一 CLI 大报告 stdout 策略：终端输出摘要和采样明细，完整明细写文件。
- 重构手动译文导入为 plan/apply 两段：默认保持原子导入，显式参数允许保存有效项并报告无效项。
- 删除 Rust 已接管路径上的 Python 重型重复扫描、字符串特判和第二事实来源。
- 用测试和真实 CLI 性能证据证明重构没有让重型逻辑回到 Python，也没有引入明显性能回退。

## 非目标

- 不重写翻译模型调用、prompt 生成、SQLite schema 主体或文件写回格式。
- 不为某个游戏样本写特判规则。
- 不新增长期兼容旧规则语义的隐式回退。
- 不把文档作为运行时事实源。
- 不为了报告字段补齐而新增额外全量扫描。
- 不在 Python 里重建 Rust 已能产出的扫描事实。

## 总体架构

重构后的职责边界：

```text
游戏数据 / 规则 / 文本规则
  -> Rust Native Fact Contract
  -> Python adapter 解析 schema
  -> CLI/service 编排、事务、报告、用户文案
  -> validate/import/write-back/diagnose
```

Rust 负责：

- 全量文本、插件配置、插件源码、规则候选和占位符覆盖的重型扫描。
- 候选分类、覆盖关系、scope hash、默认严重级别和错误 hint。
- 与写回计划、质量检查和 scope index 共享的核心事实。
- Rust 单测固定规则匹配、覆盖、分类、hash 和错误码。

Python 负责：

- CLI 参数解析、配置校验和命令编排。
- 调用 native API 并把 JSON payload 转换为 typed adapter。
- 决定事务模式，例如手动导入的原子或部分应用。
- 渲染报告、输出摘要、用户中文文案和错误映射。
- Python 测试固定 CLI 参数链路、JSON 契约、报告行为和数据库可观察结果。

禁止新增：

- Python 侧扫描全游戏文本来复现 Rust 候选。
- Python 侧按字符串片段判断正则、packer、eval 或特殊控制符。
- 导出、校验、写回各自计算同一 scope hash。
- 长期保留的新旧候选事实并行判断。

## Native Fact Contract

新增或扩展 native 规则候选接口，建议保持在现有 `scan_rule_candidates` 系列下，不另起第二套入口。顶层 payload 必须带 schema 版本：

```json
{
  "schema_version": 1,
  "scan_summary": {
    "mv_virtual_namebox": {},
    "structured_placeholders": {},
    "active_runtime": {},
    "control_code_hints": {}
  },
  "timings_ms": {},
  "counters": {}
}
```

Python adapter 必须显式校验：

- `schema_version` 是支持版本。
- 必需字段存在且类型正确。
- 枚举字段只允许文档列出的值。
- 未识别字段可以忽略，但不能影响核心门禁。

schema 版本升级规则：

- 新增非必需字段可以保持 `schema_version=1`。
- 删除字段、改变字段语义或改变枚举含义必须升级版本。
- Python adapter 遇到不支持版本时显式失败，提示升级工具或重新生成规则。

## MV Virtual Namebox

### 事实模型

Rust native 对 MV virtual namebox 输出 `speaker_requirements`：

```json
{
  "scope_hash": "<hash>",
  "candidate_details": [],
  "speaker_requirements": [
    {
      "source_text": "???",
      "policy": "translate | preserve | actor_name",
      "requires_speaker_name": true,
      "rule_name": "angle_namebox",
      "location_paths": ["<location_path>"],
      "sample_body_lines": ["<正文样本>"],
      "render_template": "<speaker>{body}",
      "confidence": "rule_match"
    }
  ],
  "errors": []
}
```

字段语义：

- `source_text` 是规则捕获到的说话人原文。
- `policy=preserve` 的条目必须出现在事实里，但 `requires_speaker_name=false`。
- `policy=translate` 和需要术语表译名的 `actor_name` 必须 `requires_speaker_name=true`。
- `scope_hash` 必须绑定游戏源文本快照和 MV namebox 规则 hash。
- `sample_body_lines` 只用于报告和审查，不参与写回逻辑。

### 消费端

`export-terminology`、`validate-agent-workspace` 和 write-back 都消费同一批 `speaker_requirements`：

- 导出术语候选时，只导出 `requires_speaker_name=true` 的 speaker。
- workspace 校验时，用同一批 requirements 检查 `speaker_names` 缺项。
- write-back 前不重新解释 Python 规则，只读取同一事实或复用同一 native 逻辑。
- 如果规则或游戏源文本变化导致 scope hash stale，必须显式要求重新导出/重新导入规则。

### 验收

- Rust 单测覆盖 `translate`、`preserve`、`actor_name` 三类 policy。
- Python contract 测试覆盖导出、workspace 校验、write-back 缺译名前置失败。
- 删除 Python 侧只通过 `requires_translation` 单独决定术语候选的重型路径。

## Structured Placeholder Coverage

### 事实模型

Rust structured placeholder 扫描必须使用统一 placeholder coverage facts。结构化候选输出：

```json
{
  "text": "<原文>",
  "range": [0, 10],
  "covered": true,
  "covered_by": "standard_placeholder | custom_placeholder | structured_placeholder | none",
  "matching_rules": ["rule_name"],
  "candidate_kind": "structured_shell | uncovered_candidate",
  "location_paths": ["<location_path>"]
}
```

覆盖判断必须考虑：

- RPG Maker 标准控制符。
- custom placeholder rules。
- structured placeholder rules。

如果普通/custom placeholder 完整覆盖某个结构化候选，该候选应标记为 covered，而不是继续作为 uncovered structured placeholder 风险。

### 验收

- Rust 单测覆盖 standard/custom/structured 三类覆盖。
- Python 扫描报告使用 native `covered_by` 和 `matching_rules`。
- `structured_placeholder_scope_hash` 只基于 native detail 计算，不再用 Python 重扫补齐。

## Active Runtime Literal Classification

### 事实模型

active runtime 审计必须由 Rust native fact contract 为 literal 输出分类和默认严重级别：

```json
{
  "plugin_name": "Plugin.js",
  "selector": "<selector>",
  "raw_text": "\\\\w+",
  "text": "\\w+",
  "literal_kind": "regex_pattern | packer_code | eval_code | user_visible_candidate | unknown",
  "audit_default_severity": "blocking | warning | ignore",
  "issue_codes": ["active_runtime_placeholder_risk"],
  "context": "regex | call:eval | packer | assignment | unknown",
  "mapping_status": "mapped_translate | mapped_excluded | mapping_missing"
}
```

分级规则：

- 已映射为 translate 且存在源文残留或控制符风险时，继续 blocking。
- `regex_pattern` 默认 warning 或 ignore，不能按用户可见文本阻断。
- `packer_code`、`eval_code` 只在有明确用户可见候选或已映射 translate 时阻断。
- `unknown` 保守 warning，除非文本规则确认应翻译且 mapping missing。
- `user_visible_candidate` 且 mapping missing 时可以 blocking，提示补规则或排除。

Python 只消费 `literal_kind` 和 `audit_default_severity`，不得根据 `\\w`、`eval(`、`function(p,h,e...)` 等字符串特征自行降级。

### 验收

- Rust native 扫描测试覆盖正则字符串、packer/eval 包裹、普通用户可见文本。
- Python 报告测试覆盖 blocking/warning/ignore 计数。
- 运行审计样例中正则和 packer/eval 误报不再阻断。

## Control-Code Hint

控制符主解析保持严格，不为了提示而放宽合法控制符定义。新增能力只在错误路径运行：

```json
{
  "original": "\\fb21st",
  "candidate": "\\fb21",
  "hint_kind": "possible_control_split",
  "possible_split": {
    "control": "\\fb2",
    "tail": "1st"
  },
  "message": "疑似控制符和后续数字或文本粘连，请确认是否需要把控制符写成独立 placeholder。"
}
```

性能边界：

- 正常通过路径不额外做复杂 hint 推断。
- 只有 placeholder/control-code 校验失败时才生成 hint。
- hint 只解释错误，不改变质量门禁结果。

### 验收

- Rust 单测覆盖 `\fb21st` 一类数字粘连。
- Python 报告测试确认错误里包含 hint 摘要。
- 不改变已有合法控制符识别结果。

## CLI Report Policy

新增集中报告策略，建议命名为 `ReportDetailPolicy`：

```text
stdout: summary + sampled details
output file: full details
json mode: 保持机器可读 JSON
error mode: stdout 保留关键错误和下一步动作
```

所有大输出命令必须通过统一出口应用策略。命令不得各自手写 `build_sampled_stdout_report`。策略应支持：

- 默认 stdout 摘要和采样。
- `--output` 写完整报告。
- 明确需要完整 stdout 的命令必须显式声明原因。
- JSON 字段名保持稳定；采样只影响 stdout 内容，不影响 `--output` 文件内容。

### 验收

- Python 测试列出所有大输出命令，确认使用统一 policy。
- 已有 `--output` 行为保持完整明细。
- stdout 不再输出超大明细。

## Manual Translation Import

手动译文导入重构为两段：

```text
parse input
  -> build ManualTranslationImportPlan
  -> report valid_items / invalid_items / scope_status
  -> apply plan
```

默认行为保持原子导入：

- 只要有 invalid item，就不写任何译文。
- 退出码和报告语义保持现有安全契约。

新增显式模式：

```text
--import-valid
--report-invalid <输出文件>
```

显式模式语义：

- 保存所有 valid items。
- invalid items 写入报告。
- 报告必须清楚说明哪些已保存、哪些未保存、下一步如何修正。
- invalid items 不能静默丢弃。

性能边界：

- 构建 plan 只读取现有 text index 和必要数据库状态。
- 不为了部分导入新增全量游戏文本扫描。
- 批量质量检查优先复用 native quality 能力。

### 验收

- 原子模式现有测试继续成立。
- 新增测试覆盖部分导入、无效项报告、重复导入、scope stale。
- 数据库写入只发生在 apply 阶段。

## 旧路径清理

每个里程碑完成后必须清理对应旧路径：

- Rust 已输出 speaker requirements 后，Python 不再单独计算 speaker 术语需求。
- Rust 已输出 placeholder coverage 后，Python 不再用另一套 span 规则判断 structured 候选是否 covered。
- Rust 已输出 runtime literal classification 后，Python 不再用字符串特征判断误报。
- CLI report policy 落地后，命令不再各自手写 stdout 采样。
- manual import plan/apply 落地后，导入函数不再把验证和写入混在同一段不可复用流程里。

保留短期双跑只允许用于同一提交内的测试迁移。最终提交不得留下生产路径双事实来源。

## 实施交付粒度

采用多个连续提交，同一条重构线。建议提交顺序：

1. Native contract schema 和 Rust 核心测试。
2. MV namebox 消费端迁移。
3. structured placeholder 消费端迁移。
4. active runtime classification 和 control hint 迁移。
5. CLI report policy 和 manual import plan/apply。
6. 删除旧路径、补齐 contract 测试、全量验证和性能证据。

如果某提交无法独立通过必要测试，不应提交半成品。可以在同一轮内继续修正，直到该里程碑可验证。

## 新会话执行协议

这份设计文档面向新的 Codex 实现会话。新会话必须按以下协议执行。

### 轮次预算

最多 8 个实现轮次：

1. Native contract schema + Rust 单测。
2. MV namebox 迁移。
3. structured placeholder 迁移。
4. active runtime + control hint 迁移。
5. CLI report policy + manual import plan/apply。
6. 删除旧路径、补齐 Python/Rust contract 测试、全量验证和性能证据。
7. 缓冲轮：仅用于处理验证失败或契约遗漏。
8. 缓冲轮：仅用于处理性能回归或收束阻塞。

前 6 轮是正常完成路径。第 7、8 轮只允许处理突发情况，不允许扩大范围或新增无关能力。

### 硬停止条件

如果任一轮判断需要第 9 轮，新会话必须停止并输出：

- 已完成内容。
- 未完成内容。
- 阻塞原因。
- 下一步最小计划。
- 当前验证结果。
- 是否存在性能回归风险。

不得为了“再试一下”继续扩展对话。

### 每轮完成条件

每轮必须做到：

- 给出本轮修改范围。
- 列出涉及的 Rust/Python 文件。
- 补对应测试。
- 运行本轮直接相关验证。
- 确认没有新增 Python 重型扫描或字符串特判。
- 如果修改性能路径，记录至少一个真实 CLI 或针对性性能证据。

### 禁止事项

- 禁止把旧 Python 重型扫描作为 fallback 保留。
- 禁止在 Python 里用字符串片段补判正则、packer、eval 或控制符拆分。
- 禁止导出、校验、写回各算一套 scope hash。
- 禁止让 docs 成为 Agent 或 CLI 的运行事实源。
- 禁止为了通过测试降低错误级别或吞异常。
- 禁止把未验证写成已通过。

## 测试计划

Rust 测试：

- Native fact contract schema 输出。
- MV speaker requirements 的 policy、scope hash 和缺译名需求。
- structured placeholder coverage 的 standard/custom/structured 覆盖。
- active runtime literal classification 的正则、packer/eval、用户可见文本。
- control-code hint 的错误路径。

Python 测试：

- native payload adapter 的版本、字段和枚举校验。
- terminology export、workspace validation、write-back 对 speaker requirements 的同源消费。
- structured placeholder scan/report 消费 native coverage。
- active runtime report 的 blocking/warning/ignore 计数。
- CLI report policy 覆盖大输出命令。
- manual import 原子模式和显式部分导入模式。
- 删除旧路径后的 scan budget 或契约测试。

性能验证：

- 至少对涉及全量扫描的命令记录真实 CLI 耗时。
- 报告扫描文件数、候选数、cache hit/miss/rescan 或等价计数。
- 对比重构前后是否新增全量扫描。
- 如果无法得到可比基线，必须说明原因，并给出本次运行的阶段耗时和剩余风险。

## 必跑验证

涉及 Python/Rust 源码和外部契约，最终必须运行：

```powershell
uv run basedpyright
uv run pytest
```

涉及 Rust 原生扩展，最终必须运行 Rust 格式、clippy 和测试。实际命令以仓库 Rust 工程结构为准，建议从 `rust/` 目录执行：

```powershell
cargo fmt -- --check
cargo clippy --all-targets -- -D warnings
cargo test
```

如果触及 Skill 协议或生成物，还必须运行：

```powershell
uv run python scripts/generate_skill_protocol.py --check
```

本设计本身不要求修改 Skill 协议；只有实现过程中确实改到 `skills/att-mz-protocol/` 或生成目标时才运行该检查。

## 验收标准

最终交付必须满足：

- 7 个反馈问题都有明确实现或明确非实现理由。
- Rust 是重型扫描和事实分类的单一事实来源。
- Python 只负责编排、事务、报告和轻量 adapter。
- 导出、校验、写回共享 MV speaker requirements。
- structured placeholder 覆盖不再漏看普通/custom placeholder。
- active runtime 不再把正则或 packer/eval 包裹文本误当阻断风险。
- control-code 错误解释能指出可能拆分。
- CLI 大输出命令 stdout 默认摘要采样。
- manual translation import 支持默认原子导入和显式部分导入。
- 旧 Python 重型重复路径已删除或不再参与生产路径。
- 所有必跑验证通过，或明确说明未能执行的命令、原因和风险。
- 性能证据没有显示新增全量扫描或明显回退。

## 风险

- native contract schema 一旦落地会成为跨层契约，字段命名和枚举必须谨慎。
- 多个消费者迁移同一事实源时，测试需要覆盖导出、校验和写回三个外部观察点。
- 删除旧路径会触发较多测试更新，必须区分行为变更和测试绑定实现细节。
- active runtime 分类需要保守，不能把真实用户可见源码残留误降级。
- manual import 部分导入会改变用户操作风险，必须默认保持原子模式，并让显式模式报告清楚。
- 性能验证需要真实 CLI 证据，不能只依赖单元测试说明。
