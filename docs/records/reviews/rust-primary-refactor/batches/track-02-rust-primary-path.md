# 轨道 02：Rust 主路径

## 范围

- 审查范围：`app/`、`tests/`、`rust/src/` 中与扫描、候选、selector、AST 解析、hash、stale 判断、规则匹配、质量检查、write protocol、native adapter、fallback/cache 相关的只读证据。
- 排除范围：未读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。
- 执行边界：未修改源码、测试、配置、数据库和运行状态；未执行 import、translate、write-back、rebuild-active-runtime、reset、run-all 或其他会改变项目状态的命令。
- 本报告唯一写入文件：`docs/records/reviews/rust-primary-refactor/batches/track-02-rust-primary-path.md`。

## 只读命令

```powershell
Get-Content -LiteralPath 'C:\Users\夜袭\.agents\skills\python-engineering-standards\SKILL.md' -TotalCount 220
Get-Content -LiteralPath 'C:\Users\夜袭\.agents\skills\rust-engineering-standards\SKILL.md' -TotalCount 220
Get-Content -LiteralPath 'docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md'
Get-Content -Raw -LiteralPath 'docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md'
Get-ChildItem -LiteralPath 'docs\records\reviews\rust-primary-refactor\batches' -Force | Select-Object Name,Length,LastWriteTime
git status --short
rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'scan|candidate|selector|AST|parse|hash|stale|quality|write.*protocol|write_back|TextScope|build\(|extract|validate|coverage|cache|fallback|native' app tests
rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'scan|candidate|selector|ast|parse|hash|stale|quality|write_back|scope_index|rule|plugin_source|nonstandard|event_command|note_tag|placeholder' rust/src
rg -n --glob 'native_*.py' --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'native|_native|adapter|fallback|return .*report|schema_version|json|validate|scan_rule_candidates|build_native' app
rg -n --glob 'test_native_*.py' --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'native|_native|adapter|fallback|return .*report|schema_version|json|validate|scan_rule_candidates|build_native' tests
rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'scan_rule_candidates|build_scope_index|evaluate_scope_gate|parse_javascript_string_spans|build_write_back_plan|scan_quality|scan_write_protocol|native_schema_fingerprint' app rust/src tests
rg -n -C 12 'filter_fresh_plugin_source_text_rules|_stale_rule|stale_rules|file_hash !=|enabled_plugin_files|available_selectors|source_text|unreviewed_candidates' app/plugin_source_text/rules.py
rg -n -C 12 'parse_plugin_source_rule_import_text|selectors_by_file|_validate_selectors|available_selectors|file_hash|build_native_plugin_source_scan' app/plugin_source_text/importer.py app/agent_toolkit/services/common.py app/agent_toolkit/services/workspace.py
rg -n -C 12 'PluginSourceManagedTextError|collect_plugin_source_managed_texts|stale_rule_details|ReviewIncomplete|plugin_source_managed_text_from_candidate|active_candidate_count|selector 已无法命中|unreviewed_count' rust/src/native_core/scope_index/plugin_source.rs rust/src/native_core/scope_index/mod.rs rust/src/native_core/scope_index/rebuild.rs
rg -n -C 10 'build_native_plugin_source_scan|_native_plugin_source_candidate_should_translate|for index, candidate|candidates_by_file|active_candidates|file_score|should_translate' app/plugin_source_text/native_scan.py
rg -n -C 12 'fn scan_plugin_source_rule_candidate_file|should_translate|source_text_required_re|source_text_exclusion_profile|candidate_confidence|structural_flags|active' 'rust\src\native_core\scope_index\plugin_source.rs'
rg -n -C 12 'def should_translate_source_text|source_text_required_pattern|source_text_exclusion_profile|strip_wrapping_punctuation|english_protocol' 'app\rmmz\text_rules.py' 'app\config\schemas.py'
rg -n -C 8 'plugin_source_high_risk|plugin_source_required|collect_plugin_source_review_coverage|plugin_source_review_incomplete|_plugin_source_rule_hits_from_scan|_build_rule_hit_metric_detail' 'app\agent_toolkit\services\common.py' 'app\agent_toolkit\services\workspace.py' 'app\application\flow_gate.py' 'app\text_index.py'
rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'collect_note_tag_candidates\(' app tests rust/src
rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'scan_placeholder_candidates\(|count_uncovered_candidates\(|placeholder_candidates_to_details|collect_unprotected_control' app tests rust/src
rg -n --glob '!data/**' --glob '!logs/**' --glob '!outputs/**' --glob '!tmp/**' --glob '!dist/**' --glob '!target/**' --glob '!.venv/**' --glob '!.pytest_cache/**' --glob '!**/__pycache__/**' 'build_nonstandard_data_scan|validate_nonstandard_data_rules|collect_nonstandard|scan_native_rule_candidates|nonstandard_data' app/nonstandard_data app/agent_toolkit/services/common.py app/agent_toolkit/services/workspace.py rust/src/native_core/scope_index/nonstandard_data.rs rust/src/native_core/scope_index/mod.rs tests
rg -n -C 12 'scan_placeholder_candidates|placeholder_candidates_to_details|count_uncovered_candidates|collect_unprotected_control_sequences|iter_unprotected_control_sequence_candidates' 'app\agent_toolkit\placeholder_scan.py' 'app\agent_toolkit\services\common.py' 'app\agent_toolkit\services\placeholder_rules.py' 'app\cli\commands\rules.py'
rg -n -C 12 'collect_native_placeholder_candidate_details|collect_native_placeholder_candidate_details_from_entries|count_uncovered_placeholder_candidate_details|scan_native_rule_candidates|build_native_placeholder_candidates_payload' 'app\native_placeholder_scan.py' 'app\application\flow_gate.py' 'app\agent_toolkit\services\workspace.py' 'rust\src\native_core\scope_index\placeholders.rs' 'rust\src\native_core\scope_index\mod.rs'
rg -n -C 20 'read_current_text_fact_translation_data_map|collect_native_placeholder_candidate_details|scan_placeholder_candidates\(|build_normal_placeholder_coverage_result|placeholder_candidates_to_details|count_uncovered_candidates' 'app\agent_toolkit\services\placeholder_rules.py'
rg -n -C 12 'build_note_tag_rule_records_from_native_candidates|_validate_note_tag_precise_source_hit|_requires_precise_map_source_validation|_validate_note_tag_candidate_hit|iter_note_tag_matches|collect_note_tag_sources|note_file_pattern_matches|matched_note_file_names' 'app\native_note_tag_scan.py' 'app\note_tag_text\sources.py' 'app\note_tag_text\parser.py'
rg -n -C 12 'scan_note_tag_rule_candidates|hit_details|source_details|file_pattern|tag_name|note_tags|scan_note_tag_sources|collect_note_tag' 'rust\src\native_core\scope_index\note_tags.rs' 'rust\src\native_core\scope_index\mod.rs'
rg -n 'collect_note_tag_candidates\(|build_note_tag_rule_records_from_native_candidates|_validate_note_tag_precise_source_hit|scan_rule_candidates\(note_tags\)|note_tags' tests\test_native_scope_index.py tests\test_native_adapters.py tests\test_rmmz_note_nonstandard_data.py tests\test_agent_toolkit_rule_import.py tests\test_workflow_gate.py
rg -n -C 10 'class NativeRuleCandidatesResult|def scan_native_rule_candidates|RULE_CANDIDATES_SCHEMA_VERSION|schema_version|_ensure_supported_rule_candidates_schema|counters|timings_ms|error_code|structured_error' 'app\native_scope_index.py' 'rust\src\native_core\scope_index\mod.rs' 'rust\src\native_core\scope_index\rebuild.rs'
```

## 结论

FAIL

## 关键发现

### P1：插件源码候选、selector、stale 和风险判断仍在 Python 二次实现，Rust 已有同职能主路径

- 证据：Rust 已导出规则候选扫描入口，`rust/src/lib.rs:79` 暴露 `scan_rule_candidates`，`rust/src/native_core/scope_index/mod.rs:607` 进入 `plugin_source` 分支，`rust/src/native_core/scope_index/plugin_source.rs:162` 使用 `par_iter` 并行扫描插件源码候选，`rust/src/native_core/scope_index/plugin_source.rs:411` 到 `rust/src/native_core/scope_index/plugin_source.rs:523` 完成 AST 字符串提取、源文过滤、selector、confidence 和 structural flags，`rust/src/native_core/scope_index/plugin_source.rs:203` 到 `rust/src/native_core/scope_index/plugin_source.rs:287` 已能检查文件缺失、文件未启用、selector 命中和 review incomplete，`rust/src/native_core/scope_index/rebuild.rs:2126` 到 `rust/src/native_core/scope_index/rebuild.rs:2179` 已在 rebuild 主路径使用同一 Rust 检查并输出错误码。
- 证据：Python 仍重算核心业务，`app/plugin_source_text/native_scan.py:273` 到 `app/plugin_source_text/native_scan.py:290` 在 native 候选返回后再次按 Python 规则过滤，`app/plugin_source_text/native_scan.py:301` 到 `app/plugin_source_text/native_scan.py:312` 重算 active/strong/medium/file_score，`app/plugin_source_text/native_scan.py:418` 到 `app/plugin_source_text/native_scan.py:466` 重算 high_risk 和风险阈值，`app/plugin_source_text/native_scan.py:605` 到 `app/plugin_source_text/native_scan.py:612` 再次调用 `text_rules.should_translate_source_text` 判断源文。
- 证据：规则导入、stale 和覆盖率也仍在 Python，`app/plugin_source_text/importer.py:46` 到 `app/plugin_source_text/importer.py:90` 从 Python scan 构建 selector/file_hash 并校验 import，`app/plugin_source_text/importer.py:120` 到 `app/plugin_source_text/importer.py:139` 在 Python 做 selector 命中校验，`app/plugin_source_text/rules.py:34` 到 `app/plugin_source_text/rules.py:87` 在 Python 判断 stale，`app/plugin_source_text/rules.py:91` 到 `app/plugin_source_text/rules.py:124` 在 Python 计算 review coverage，`app/plugin_source_text/extraction.py:56` 到 `app/plugin_source_text/extraction.py:83` 在提取时又按 Python scan/candidate_index 读取 selector。
- 业务事实：插件源码是 CPU 密集型 AST 扫描和规则候选路径；当前 Rust 已具备主路径能力，但 Python adapter 不是单纯传参和报告组装，而是在 native 输出后继续执行源文识别、风险、stale、selector、覆盖率和提取判断。
- 违反原则：违反 Rust 主路径、单一事实来源、并发真实有效和“Rust 接管生产主路径后删除旧 Python 重型扫描/候选/校验路径”的项目边界。
- 影响：同一条插件源码规则在 `scan_rule_candidates`、workspace gate、规则导入、runtime/extraction、rebuild storage 中可能被两套 selector、源文过滤、风险阈值或 stale 语义解释；后续继续扩展 Python 会让 Rust 输出 schema 变成数据原料，而不是事实源。
- Python/Rust 职责判断：Rust 应拥有 AST 解析、候选过滤、selector/hash/stale、review coverage、风险摘要和规则命中报告；Python 只应读取配置、调用 native、校验 schema version、映射中文报告和 CLI JSON。
- 建议 Rust 接管点：将 `scan_rule_candidates(plugin_source)` 或新增 native 规则验证入口扩展为直接返回 import 记录、selector 命中、file_hash、review coverage、risk summary、rule hit metrics 和 stale/review error code；rebuild 中 `collect_plugin_source_managed_texts` 使用的检查应成为导入/validate/extract 的同一事实源。
- 应删除或瘦身的 Python 逻辑：删除或瘦身 `app/plugin_source_text/native_scan.py:273` 到 `app/plugin_source_text/native_scan.py:466` 的 Python 二次过滤/风险重算，删除 `app/plugin_source_text/native_scan.py:605` 到 `app/plugin_source_text/native_scan.py:612` 的 Python 源文判断，瘦身 `app/plugin_source_text/importer.py:46` 到 `app/plugin_source_text/importer.py:139` 的 selector/stale 校验，瘦身 `app/plugin_source_text/rules.py:34` 到 `app/plugin_source_text/rules.py:124` 的 stale 和 coverage 计算，瘦身 `app/plugin_source_text/extraction.py:56` 到 `app/plugin_source_text/extraction.py:83` 的 Python candidate_index 读取。
- 禁止方向：不要再在 Python 增加 selector fallback、风险阈值分支、stale 旁路、字符串补扫或“报告层重新解释 native 候选”的逻辑。
- 后续验证：补 Rust 单测覆盖插件源码导入、selector 缺失、file_hash 变化、review incomplete、risk summary 和 rule hit metrics；Python 测试只固定 CLI/JSON/中文文案，并断言 Python 不再调用 `text_rules.should_translate_source_text` 处理插件源码候选。

### P1：Note 标签规则验证仍由 Python 执行精确匹配和可翻译判断，Rust 输出 schema 尚不足以删除 Python 逻辑

- 证据：Rust 已实现 Note 标签候选扫描，`rust/src/native_core/scope_index/mod.rs:692` 到 `rust/src/native_core/scope_index/mod.rs:712` 返回 `note_tags` 的 `candidates`、`hit_details` 和 `source_details`，`rust/src/native_core/scope_index/note_tags.rs:67` 到 `rust/src/native_core/scope_index/note_tags.rs:90` 并行扫描 note 源，`rust/src/native_core/scope_index/note_tags.rs:100` 到 `rust/src/native_core/scope_index/note_tags.rs:147` 解析 tag 并判断 translatable，`rust/src/native_core/scope_index/note_tags.rs:178` 到 `rust/src/native_core/scope_index/note_tags.rs:194` 构造 hit/source details，`rust/src/native_core/scope_index/note_tags.rs:197` 到 `rust/src/native_core/scope_index/note_tags.rs:201` 将 Map 文件归并到 `Map*.json`。
- 证据：Python 仍执行规则验证主判断，`app/native_note_tag_scan.py:31` 到 `app/native_note_tag_scan.py:38` 遍历 import 规则，`app/native_note_tag_scan.py:46` 到 `app/native_note_tag_scan.py:64` 根据 file pattern 切换普通命中和精确命中，`app/native_note_tag_scan.py:187` 到 `app/native_note_tag_scan.py:219` 用 Python 汇总 hit/translatable/unique source，`app/native_note_tag_scan.py:222` 到 `app/native_note_tag_scan.py:253` 重新遍历 note source 并调用 `iter_note_tag_matches` 与 `text_rules.should_translate_source_text`，`app/native_note_tag_scan.py:256` 到 `app/native_note_tag_scan.py:270` 在 Python 决定哪些规则需要精确 Map 源验证。
- 证据：旧 Python note tag 解析仍存在，`app/note_tag_text/parser.py:29` 到 `app/note_tag_text/parser.py:48` 用正则解析 note 标签，`app/note_tag_text/sources.py:23` 到 `app/note_tag_text/sources.py:44` 在 Python 过滤 note 文件模式，`app/note_tag_text/exporter.py:67` 到 `app/note_tag_text/exporter.py:73` 仍可通过 Python 候选摘要构建规则。
- 业务事实：Note 标签规则导入需要判定 tag/file_pattern 是否命中、是否有可翻译文本、Map 精确源是否匹配；这些都属于规则匹配和质量前置判断，不应在 Python adapter 中二次实现。
- 违反原则：违反 Rust 主路径和跨层契约单一事实来源；当前 native schema 提供扫描事实，但没有直接提供“给定导入规则是否合法”的 Rust 结果，迫使 Python 继续保留业务判断。
- 影响：Rust 对 Map 聚合、translatable、tag 解析的解释与 Python 精确验证可能漂移；大规模 note 扫描会在 Python 中重复遍历源，影响导入和 gate 性能，也让删除旧 Python parser 变困难。
- Python/Rust 职责判断：Rust 应拥有 Note 标签解析、file pattern 匹配、Map 精确源验证、translatable 统计和导入规则错误码；Python 只应传入 import 规则、展示错误和写入报告。
- 建议 Rust 接管点：为 `note_tags` 增加 native rule validation 输入输出，或扩展 `scan_rule_candidates(note_tags)` 让 Rust 接收导入规则并返回每条规则的 matched files、hit count、translatable count、source preview、错误码和用户可读建议字段。
- 应删除或瘦身的 Python 逻辑：瘦身 `app/native_note_tag_scan.py:46` 到 `app/native_note_tag_scan.py:270`，删除或测试专用化 `app/note_tag_text/parser.py:29` 到 `app/note_tag_text/parser.py:48` 与 `app/note_tag_text/exporter.py:67` 到 `app/note_tag_text/exporter.py:73` 的旧候选构造路径。
- 禁止方向：不要继续在 Python 为 Map 精确源、tag 重名、file pattern 或 translatable 增加新分支；这些分支应转为 Rust 输入参数和错误码。
- 后续验证：补 Rust 测试覆盖 `Map001.json` 精确规则、`Map*.json` 聚合规则、tag 重名、无可翻译文本和 file pattern 未命中；Python 测试只验证 JSON 报告字段和中文错误映射。

### P2：普通 placeholder 生产路径已转 native，但旧 Python 扫描器仍在 `app` 包导出

- 证据：旧 Python 扫描器仍存在，`app/agent_toolkit/placeholder_scan.py:20` 到 `app/agent_toolkit/placeholder_scan.py:54` 遍历译文记录扫描 placeholder，`app/agent_toolkit/placeholder_scan.py:57` 到 `app/agent_toolkit/placeholder_scan.py:80` 继续在 Python 转换和计数候选，`app/agent_toolkit/placeholder_scan.py:117` 到 `app/agent_toolkit/placeholder_scan.py:121` 仍导出这些函数。
- 证据：生产路径已经使用 native，`app/native_placeholder_scan.py:23` 到 `app/native_placeholder_scan.py:45` 构造 native payload，`app/native_placeholder_scan.py:48` 到 `app/native_placeholder_scan.py:82` 调用 `scan_native_rule_candidates` 并读取 native `details`，`app/native_placeholder_scan.py:85` 到 `app/native_placeholder_scan.py:95` 只做 native detail 计数，`app/application/flow_gate.py:395` 到 `app/application/flow_gate.py:406` 使用 `collect_native_placeholder_candidate_details` 和 `count_uncovered_placeholder_candidate_details`，`rust/src/native_core/scope_index/placeholders.rs:52` 到 `rust/src/native_core/scope_index/placeholders.rs:60` 在 Rust 并行扫描 placeholder 候选。
- 证据：旧导出仍被公共服务模块保留，`app/agent_toolkit/services/common.py:18` 到 `app/agent_toolkit/services/common.py:22` 导入旧 scanner，`app/agent_toolkit/services/common.py:3263` 到 `app/agent_toolkit/services/common.py:3265` 继续在 `__all__` 暴露旧函数；规则 CLI 当前路径则已由 `app/agent_toolkit/services/placeholder_rules.py:80` 到 `app/agent_toolkit/services/placeholder_rules.py:117` 进入 native coverage 构造。
- 业务事实：当前未确认普通 placeholder 生产 gate 仍走旧 scanner；问题在于旧 Python 重型扫描器仍位于 app 包并作为公共 API 暴露，容易被后续功能继续引用。
- 违反原则：违反 Rust 接管后删除旧 Python 同功能路径和契约失忆化；旧 scanner 让测试和服务层存在第二套候选模型。
- 影响：后续改动可能误用 Python scanner，造成 native detail schema 与 Python candidate schema 并存；测试若继续围绕旧 scanner，会阻碍删除 Python 逻辑。
- Python/Rust 职责判断：Rust 应拥有 placeholder 候选扫描和覆盖计数；Python 只保留 native payload 构造、schema 校验和报告渲染。
- 建议 Rust 接管点：当前生产 native 接管点基本存在，重点是把旧 Python scanner 从公共 app API 中移除，并让所有入口只使用 `app/native_placeholder_scan.py`。
- 应删除或瘦身的 Python 逻辑：删除或迁入测试夹具的候选为 `app/agent_toolkit/placeholder_scan.py:20` 到 `app/agent_toolkit/placeholder_scan.py:121`；移除 `app/agent_toolkit/services/common.py:18` 到 `app/agent_toolkit/services/common.py:22` 和 `app/agent_toolkit/services/common.py:3263` 到 `app/agent_toolkit/services/common.py:3265` 的公共导出。
- 禁止方向：不要为旧 scanner 添加兼容 wrapper、fallback 或新测试覆盖；应该让误用旧 scanner 的调用点显式失败并改走 native。
- 后续验证：在删除旧 scanner 后运行 placeholder 规则导入、flow gate、workspace validate 的 Python 流程测试，并保留 Rust placeholder 单测作为候选扫描事实源。

## 双事实来源清单

- 插件源码候选扫描与筛选：Rust 在 `rust/src/native_core/scope_index/plugin_source.rs:411` 到 `rust/src/native_core/scope_index/plugin_source.rs:523` 执行 AST/selector/过滤；Python 在 `app/plugin_source_text/native_scan.py:273` 到 `app/plugin_source_text/native_scan.py:312` 和 `app/plugin_source_text/native_scan.py:605` 到 `app/plugin_source_text/native_scan.py:612` 再筛一次。
- 插件源码 stale 与 review coverage：Rust 在 `rust/src/native_core/scope_index/plugin_source.rs:203` 到 `rust/src/native_core/scope_index/plugin_source.rs:287` 和 `rust/src/native_core/scope_index/rebuild.rs:2171` 到 `rust/src/native_core/scope_index/rebuild.rs:2179` 检查；Python 在 `app/plugin_source_text/rules.py:34` 到 `app/plugin_source_text/rules.py:124` 维护另一套判断。
- 插件源码 hash/selector 导入契约：Rust 在 `rust/src/native_core/scope_index/plugin_source.rs:224` 使用文件 hash 参与 stale 判断；Python 在 `app/plugin_source_text/importer.py:46` 到 `app/plugin_source_text/importer.py:90` 构建 selector 和 file_hash 记录。
- Note 标签解析与命中验证：Rust 在 `rust/src/native_core/scope_index/note_tags.rs:100` 到 `rust/src/native_core/scope_index/note_tags.rs:147` 解析和筛选；Python 在 `app/native_note_tag_scan.py:187` 到 `app/native_note_tag_scan.py:253` 与 `app/note_tag_text/parser.py:29` 到 `app/note_tag_text/parser.py:48` 再做匹配。
- 普通 placeholder 候选扫描：Rust 在 `rust/src/native_core/scope_index/placeholders.rs:52` 到 `rust/src/native_core/scope_index/placeholders.rs:60` 扫描；旧 Python scanner 仍在 `app/agent_toolkit/placeholder_scan.py:20` 到 `app/agent_toolkit/placeholder_scan.py:80` 保留。

## Rust 主路径缺口

- 插件源码缺口：`scan_rule_candidates(plugin_source)` 已能返回候选，但还没有替代 Python 导入/validate/extract 所需的完整结果对象；需要 Rust 直接产出 import records、risk summary、review coverage、rule hit metrics、stale/review error code，并让 Python 不再重新解释候选。
- Note 标签缺口：`scan_rule_candidates(note_tags)` 已返回扫描事实，但缺少“给定导入规则验证结果”的 Rust schema；需要把 file_pattern、Map 精确源、tag 命中、translatable count 和错误码纳入 native contract。
- Placeholder 缺口：生产扫描缺口较小，主要缺口是 Python 删除和测试收口；native detail schema 已足以支撑普通 placeholder coverage，见 `app/native_placeholder_scan.py:48` 到 `app/native_placeholder_scan.py:95`。
- 错误码/schema 缺口：`rust/src/native_core/scope_index/rebuild.rs:3975` 到 `rust/src/native_core/scope_index/rebuild.rs:3984` 已有 structured error 包装，`rust/src/native_core/scope_index/rebuild.rs:2171` 到 `rust/src/native_core/scope_index/rebuild.rs:2179` 已有插件源码 stale/review code；同等级错误码还应覆盖插件源码导入验证和 Note 标签规则验证，而不是让 Python 自造错误分支。

## Python 删除候选

- 应删除或瘦身：`app/plugin_source_text/native_scan.py:273` 到 `app/plugin_source_text/native_scan.py:466` 的 Python 候选过滤和风险计算。
- 应删除或瘦身：`app/plugin_source_text/native_scan.py:605` 到 `app/plugin_source_text/native_scan.py:612` 的 Python 源文识别。
- 应删除或瘦身：`app/plugin_source_text/importer.py:46` 到 `app/plugin_source_text/importer.py:139` 的 selector/file_hash/stale 校验。
- 应删除或瘦身：`app/plugin_source_text/rules.py:34` 到 `app/plugin_source_text/rules.py:124` 的 stale 与 review coverage。
- 应删除或瘦身：`app/plugin_source_text/extraction.py:56` 到 `app/plugin_source_text/extraction.py:83` 的 Python candidate_index 提取路径。
- 应删除或瘦身：`app/native_note_tag_scan.py:46` 到 `app/native_note_tag_scan.py:270` 的 Python note tag 规则验证。
- 应删除或迁入测试夹具：`app/note_tag_text/parser.py:29` 到 `app/note_tag_text/parser.py:48` 与 `app/note_tag_text/exporter.py:67` 到 `app/note_tag_text/exporter.py:73` 的旧 Python Note 标签候选路径。
- 应删除或迁入测试夹具：`app/agent_toolkit/placeholder_scan.py:20` 到 `app/agent_toolkit/placeholder_scan.py:121` 的旧 Python placeholder scanner。
- Python 只应保留边界：`app/native_scope_index.py:140` 到 `app/native_scope_index.py:161` 这类 native 调用、schema version 校验和结构化结果封装；`app/native_placeholder_scan.py:23` 到 `app/native_placeholder_scan.py:95` 这类 payload/report adapter；CLI 参数解析、配置校验、中文报告和 JSON 输出。
- 不应继续扩展 Python 的位置：`app/plugin_source_text/native_scan.py`、`app/plugin_source_text/importer.py`、`app/plugin_source_text/rules.py`、`app/native_note_tag_scan.py`、`app/agent_toolkit/placeholder_scan.py` 中的扫描、规则匹配、stale、selector、风险和覆盖率判断。

## 测试缺口

- 插件源码：需要 Rust 单测覆盖 import validation、selector 缺失、file hash 变化、inactive file、review incomplete、risk summary 和 rule hit metrics；Python 测试只验证 CLI/report 契约，并应断言 Python 不再二次调用源文识别。当前 Rust 已有 plugin source 管理文本错误测试，如 `rust/src/native_core/scope_index/plugin_source.rs:822` 到 `rust/src/native_core/scope_index/plugin_source.rs:875`，但 Python 导入/validate 仍未完全由 Rust contract 承接。
- Note 标签：需要 Rust 单测覆盖 `Map001.json` 精确规则与 `Map*.json` 聚合规则的导入验证；当前 Python 测试仍直接覆盖旧路径，例如 `tests/test_rmmz_note_nonstandard_data.py:545`、`tests/test_rmmz_note_nonstandard_data.py:596`、`tests/test_agent_toolkit_rule_import.py:3595` 和 `tests/test_workflow_gate.py:93` 仍出现 `collect_note_tag_candidates`。
- Placeholder：需要测试删除旧 scanner 后所有规则导入、flow gate、workspace validate 均走 native；当前旧 scanner 仍在 `app/agent_toolkit/services/common.py:18` 到 `app/agent_toolkit/services/common.py:22` 被公共导入，删除前应先把误用测试改成 native adapter 或测试夹具。
- 本轮未运行 `uv run basedpyright`、`uv run pytest`、Rust fmt、clippy 或 Rust tests；原因是任务限定只读审查并禁止状态变更，本报告仅给出基于静态证据的代码审查结论。

## 交叉引用

- 轨道 01：建议复核插件源码 file_hash、selector、runtime/rebuild metadata 的单一事实来源，尤其是 `app/plugin_source_text/importer.py:46` 到 `app/plugin_source_text/importer.py:90` 与 Rust rebuild storage 的契约关系。
- 轨道 03：建议复核插件源码规则导入、workspace prepare/validate、flow gate、rebuild storage 是否共享 Rust 输出，而不是各自调用 Python coverage。
- 轨道 04：建议重点看 `app/plugin_source_text/scanner.py:399` 到 `app/plugin_source_text/scanner.py:446` 的 Python 进程级 scan cache 是否仍有保留必要，以及是否与 Rust 并行扫描/索引缓存重复。
- 轨道 05：建议把仍引用旧 Note 标签和 placeholder scanner 的测试迁移为 Rust contract 或 Python adapter 流程测试。
- 轨道 06：建议将 `app/agent_toolkit/placeholder_scan.py`、旧 Note 标签 parser/exporter 和插件源码 Python 二次过滤列入删除清单。
- 轨道 07：建议用大插件源码、Note 标签和 placeholder 规则导入样例测量 Rust 接管前后的扫描次数、Python 重扫耗时和 native timings。

## 已查无发现范围

- `app/native_scope_index.py:140` 到 `app/native_scope_index.py:161` 当前表现为 native adapter：负责调用 `_native.scan_rule_candidates`、校验 schema version 和封装结果，未在该函数内确认业务规则重写。
- 普通 placeholder 当前生产覆盖路径已转 native：`app/application/flow_gate.py:395` 到 `app/application/flow_gate.py:406` 使用 native detail，`app/native_placeholder_scan.py:48` 到 `app/native_placeholder_scan.py:95` 只做 native 结果读取和计数。
- Nonstandard data 本轮未确认存在同等级 Python 重型 fallback：`app/nonstandard_data/scanner.py:140` 到 `app/nonstandard_data/scanner.py:156` 通过 native rule candidates 构建扫描结果，未作为轨道 02 关键发现列入。
- 质量扫描、write protocol 和 write-back plan 的 Rust 导出存在：`rust/src/lib.rs:30` 到 `rust/src/lib.rs:56` 暴露 quality/write protocol，`rust/src/lib.rs:170` 暴露 write-back plan；本轮未确认 Python 侧存在同等级生产 fallback，但建议其他轨道继续按 CLI 流程验证。
