# 轨道 05：测试与验收

## 范围

本轨道只读审查 `tests/`、`rust/src/`、`app/persistence/schema/current.sql`、`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md` 和执行计划中与测试验收相关的内容。审查目标是确认现有测试是否固定跨语言、跨命令业务契约，尤其是导出、导入、重建、翻译、质量检查和 write-back 生命周期是否消费同一事实。

未读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。

## 只读命令

- `Get-Content -LiteralPath 'C:\Users\夜袭\.agents\skills\python-engineering-standards\SKILL.md' -TotalCount 220`
- `Get-Content -LiteralPath 'C:\Users\夜袭\.agents\skills\rust-engineering-standards\SKILL.md' -TotalCount 220`
- `rg -n 'plugin_source|plugin-source|nonstandard|event_command|note_tag|placeholder|structured_placeholder|text_fact|scope|fact_id|location_path|stale|same path|write_back|scan_budget|native|fallback|legacy' tests rust/src`
- `rg -n 'export.*import|import.*rebuild|rebuild.*stale|translate.*write|write.*fact_id|same.*path|excluded_selectors|quality_error|error_code|source_hash|rule_hash' tests rust/src`
- `rg -n 'make_|fixture|helper|fake|stub|mock|legacy|fallback|old|location_path|fact_id|schema|current|native' tests`
- `Get-Content -LiteralPath 'docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md' -TotalCount 260`
- `rg -n -C 8 'test_import_plugin_rules_deletes_only_stale|test_import_event_command_rules_deletes_only_stale|test_import_note_tag_rules_deletes_only_stale|test_import_plugin_source_rules_deletes_only_stale|test_rule_fact_resolver_does_not_match_same_path_when_text_differs' tests\test_agent_toolkit_rule_import.py`
- `rg -n -C 8 'test_rebuild_native_scope_index_storage_counts_stale_plugin_rules|test_rebuild_native_scope_index_storage_keeps_same_path_note_tag_facts|test_rebuild_native_scope_index_storage' tests\test_native_scope_index.py`
- `rg -n -C 8 'test_write_back_warm_index_rejects_quality_errors_without_python_scope_build|test_direct_rebuild_active_runtime_uses_real_native_success_path|test_rebuild_active_runtime_uses_native_rebuild_helper|test_native_write_back_reads_mv_namebox_render_parts|test_native_plugin_source_runtime_maps_use_v2_fact_hashes|test_native_write_back_blocks_mismatched_plugin_source_raw_selector' tests\test_rmmz_write_plan.py`
- `rg -n -C 8 'test_manual_pending_translation_export_and_import|test_export_quality_fix_template_preserves_same_path_quality_error_facts|test_writable_path_reader_preserves_same_path_text_facts|test_manual_import_rejects_latest_quality_error_outside_current_scope' tests\test_agent_toolkit_manual_import.py tests\test_manual_translation_scope.py`
- `rg -n -C 8 '_insert_current_text_fact_contract|CREATE TABLE text_fact_scopes|CREATE TABLE text_facts|CREATE TABLE text_index|_text_fact_domain_for_helper|_is_note_tag_location_path|_is_event_command_location_path|_source_file_for_helper|_selector_for_helper' tests\_native_write_plan_helper.py`
- `rg -n -C 8 'CREATE TABLE text_fact_scopes|CREATE TABLE text_facts|CREATE TABLE text_index|test_support|fixture|insert_current|scope_key|current text fact' rust\src\native_core\write_back_plan\test_support.rs rust\src\native_core\scope_index\storage.rs`
- `rg -n -C 6 'rebuild_current_text_fact_scope_for_test|read_current_text_fact_scope_for_test|read_current_text_fact_records|read_current_text_fact_translation_data_map|index_by_path|location_path' tests\current_text_fact_scope.py tests\agent_toolkit_contract_fixtures.py tests\rmmz_writeback_contract_fixtures.py`
- `rg -n 'mock|monkeypatch|fake|forbidden_.*read|fake_rebuild|stub|test-helper|legacy|fallback' tests\test_rmmz_write_plan.py tests\test_agent_toolkit_manual_import.py tests\test_text_index.py tests\test_agent_toolkit_rule_import.py tests\_native_write_plan_helper.py`
- `rg -n 'import_.*rule|rule_import|delete.*stale|stale.*fact|current.*fact|same_path|same path|source_hash_matches|error_code|structured_error|quality_error_fact_ids|matched_translation_fact_ids' rust\src`
- `rg -n 'error_codes = \{error\.code|assert .*error\.code|assert .*\.status|summary\[".*count"\]|read_translated_items|read_translation_quality_errors|read_text_facts|read_text_index|read_text_fact_scope|stale_rule_count|source_hash_matches' tests\test_agent_toolkit_rule_import.py tests\test_agent_toolkit_manual_import.py tests\test_agent_toolkit_quality_report.py tests\test_rmmz_write_plan.py tests\test_text_index.py tests\test_native_scope_index.py`
- `rg -n 'import.*rebuild|rebuild.*import|导入.*重建|重建.*导入|stale_rule_count == 0|stale.*立刻|立刻.*stale|rebuild.*stale' tests rust\src`
- `rg -n 'export_pending|import_manual|pending.*import|rebuild_text_index|translation_status|quality_report|write_back|rebuild_active_runtime|translate|run_all|write_terminology|export_quality_fix_template' tests`
- `rg -n 'test_.*(export|import|rebuild|translate|write|quality|status|workflow|run_all|terminology)' tests`
- `rg -n 'test_.*(scope|index|stale|same_path|fact_id|quality_error|write_back|rebuild|plugin_source|nonstandard|event_command|note_tag|placeholder)' rust\src`
- `rg -n 'write_scope_index_storage_rejects_extra_fact_with_same_path|write_scope_index_storage_rejects_text_index_fact_identity_mismatch|write_back_reads_saved_translation_by_fact_id_without_duplicate_location_gate|write_back_reports_saved_translation_with_stale_fact_id_as_unresolved|evaluate_scope_gate_outputs_compact_workflow_and_quality_summary' rust\src`
- `Get-Content` 行号抽取：`tests\test_text_index.py`、`tests\test_agent_toolkit_rule_import.py`、`tests\test_rmmz_write_plan.py`、`docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md`
- `rg -n -C 6 'fn build_scope_index_outputs_text_rows_and_summaries|fn evaluate_scope_gate_outputs_compact_workflow_and_quality_summary|fn scan_rule_candidates_scans_event_command_candidates' rust\src\native_core\scope_index\mod.rs`
- `rg -n -C 6 'fn write_scope_index_storage_rejects_extra_fact_with_same_path_but_different_locator|fn write_scope_index_storage_rejects_text_index_fact_identity_mismatch|fn write_scope_index_storage_writes_text_fact_rows' rust\src\native_core\scope_index\storage.rs`
- `rg -n -C 6 'fn write_back_reads_saved_translation_by_fact_id_without_duplicate_location_gate|fn write_back_reports_saved_translation_with_stale_fact_id_as_unresolved' rust\src\native_core\write_back_plan\test_support.rs`
- `rg -n -C 6 'fn collect_plugin_source_managed_texts_rejects_stale_file_selector_or_inactive_file|fn plugin_source_managed_text_rejects_candidate_missing_raw_span_fields|fn scan_plugin_source_candidates_decodes_escapes' rust\src\native_core\scope_index\plugin_source.rs`
- `rg -n -i 'create table.*text_index_items|create table.*text_facts|create table.*text_fact_scope|create table.*text_fact_render_parts|create table.*translation_items|create table.*translation_quality_errors' app\persistence\schema\current.sql`
- `rg -n 'CREATE_TEXT_INDEX_ITEMS_TABLE|CREATE_TEXT_FACTS_TABLE|CREATE_TEXT_FACT_SCOPE_TABLE|CREATE_TEXT_FACT_RENDER_PARTS_TABLE|CURRENT_TEXT_FACT_CONTRACT_VERSION' app tests rust\src`
- `rg -n 'CURRENT_SCHEMA_SQL|current_schema_fingerprint|include_str!|schema/current.sql' rust\src app tests`
- `rg -n 'prepare-agent-workspace|validate-agent-workspace|import-plugin-source-rules|import-nonstandard-data-rules|import-note-tag-rules|translate|write-back|quality-report|rebuild-text-index' docs\superpowers\specs\2026-06-10-rust-primary-multi-agent-refactor-review-design.md docs\superpowers\plans\2026-06-10-rust-primary-refactor-review-execution.md`
- `git status --short`

说明：有两次 PowerShell glob 写法检索失败，分别是 `rg ... tests\test_*.py` 和 `rg ... tests\test_agent_toolkit_*.py`，均未读取或修改状态；已改用目录级 `rg ... tests` 补查。

## 结论

FAIL

## 关键发现

### P1：缺少“规则导入成功后冷重建不能立刻 stale”的非空规则生命周期回归

- 证据：`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md:151`、`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md:152`、`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md:351`、`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md:352`、`tests/test_agent_toolkit_rule_import.py:3730`、`tests/test_agent_toolkit_rule_import.py:3749`、`tests/test_text_index.py:673`、`tests/test_text_index.py:688`、`tests/test_text_index.py:809`、`tests/test_text_index.py:830`
- 业务事实：插件源码、Note 标签等外部规则导入时产生 selector、tag、path 与规则 hash；后续 `rebuild-text-index` 应继续消费同一候选事实。现有 `test_public_rule_validation_and_import_use_native_candidate_paths` 只验证 validate/import 返回 ok 和计数，未进入 `rebuild_text_index`；现有冷重建测试通过 `session.replace_plugin_source_text_rules` 直接放入规则记录，再验证 ok 或 `stale_plugin_source_rules`，没有验证公开 import 生成的规则记录在下一次冷重建中保持新鲜。
- 违反原则：跨命令生命周期 | 测试验收 | Rust 主路径
- 影响：可能出现 `import-plugin-source-rules` 或 `import-note-tag-rules` 报告成功，但下一步 `rebuild-text-index`、`translate` 或 `write-back` 立即因 stale 阻断。用户会看到“导入成功后马上要求重新导出并导入”的循环，主路径收束也无法证明同一候选事实跨命令稳定。
- Python/Rust 职责判断：Python 应保留公开命令编排和 JSON 报告断言；候选命中、selector 新鲜度、规则身份判断应由 Rust 主路径固定。
- 建议 Rust 接管点：在 Rust `scan_rule_candidates` / scope rebuild 的规则解析边界增加以“import 归一化后的规则 payload”为输入的核心测试，覆盖 plugin_source、note_tag、event_command、nonstandard_data 至少一个非空规则链路。
- 应删除或瘦身的 Python 逻辑：不要继续用 Python 直接 `replace_*_rules` 构造与导入输出相似但不等价的测试前置状态；保留少量 Python 流程测试验证公开命令串联即可。
- 禁止采用的错误修复方向：禁止只在 Python import 后补一次静默重建、补报告文案或把 stale 当 warning；也禁止新增 Python fallback 来迁就 Rust 判断差异。
- 后续验证：新增最小生命周期测试：`export-plugin-source-ast-map` 或 native candidate scan 取候选 -> `validate-plugin-source-rules` -> `import-plugin-source-rules` -> `rebuild-text-index` -> `quality-report` 或 `translate --max-items 1` -> `write-back` gate；断言无 `stale_plugin_source_rules`，并断言 `fact_id`、selector、source hash、rule hash 在报告和数据库状态中一致。

### P2：写回验收 helper 在测试层手工构造 current text fact，容易绕开 Rust 冷重建事实源

- 证据：`tests/_native_write_plan_helper.py:303`、`tests/_native_write_plan_helper.py:312`、`tests/_native_write_plan_helper.py:357`、`tests/_native_write_plan_helper.py:454`、`tests/_native_write_plan_helper.py:776`、`tests/_native_write_plan_helper.py:787`、`app/persistence/schema/current.sql:323`、`app/persistence/schema/current.sql:382`、`app/persistence/schema/current.sql:424`
- 业务事实：`_insert_current_text_fact_contract` 在测试临时库里写入 `text_fact_scope`、`text_facts` 和 `text_index_items`，并由 Python helper 根据 `location_path` 推断 domain、source_file、selector。这些字段正是 Rust 冷重建事实身份和 write-back 读取契约的核心输入。
- 违反原则：单一事实来源 | Rust 主路径 | 测试验收
- 影响：写回测试可能在“Python helper 构造的 current facts”下通过，但真实 `rebuild_text_index_native_storage` 生成的事实身份、render parts、selector 或 source_file 若漂移，测试无法及时暴露。该风险尤其影响 MV 虚拟名字框、插件源码、Note 标签和非标准 data 这类跨域写回。
- Python/Rust 职责判断：Python 流程测试可以读取 current facts、写入译文和断言报告；current fact 身份构造、domain 路由和 selector 解析不应由 Python 测试 helper 再实现一套。
- 建议 Rust 接管点：以 Rust rebuild/storage 输出作为 write plan 测试的事实源；Rust 单测可继续使用 `CURRENT_SCHEMA_SQL` 初始化库，但事实行应尽量由 Rust builder 或 production rebuild path 生成。
- 应删除或瘦身的 Python 逻辑：瘦身 `tests/_native_write_plan_helper.py` 中 `_text_fact_domain_for_helper`、`_source_file_for_helper`、`_selector_for_helper` 这类路径解析；Python helper 只负责把真实 current fact 读出后组装译文输入。
- 禁止采用的错误修复方向：禁止在 helper 中继续追加路径分支来追赶生产逻辑；禁止把 helper 的推断结果当生产契约说明。
- 后续验证：为 write-back、rebuild-active-runtime、write-terminology 的关键测试增加基于 `service.rebuild_text_index` 或 Rust rebuild 输出的夹具；保留一个 helper 单测用于拒绝未知路径，但不扩大 helper 的 domain 识别范围。

### P2：部分直接写入命令只断言异常文案，没有固定错误码与事实状态

- 证据：`tests/test_rmmz_write_plan.py:1184`、`tests/test_rmmz_write_plan.py:1208`、`tests/test_rmmz_write_plan.py:1232`、`tests/test_rmmz_write_plan.py:1916`、`tests/test_text_index.py:832`、`tests/test_text_index.py:833`
- 业务事实：`write_back`、`rebuild_active_runtime`、`write_terminology` 都是写入类验收命令，失败时应稳定暴露可消费的错误码和事实状态。当前直接 handler 测试多处只用 `pytest.raises(..., match="检查没通过")` 或类似文案；相比之下，`rebuild_text_index` 相关测试已经断言 `stale_plugin_source_rules` 等错误码。
- 违反原则：测试验收 | 跨命令生命周期
- 影响：错误文案微调可能让测试误报，或者错误码、quality_error fact 归属、写入前状态回滚发生回归时测试仍通过。下游 Agent/CLI 依赖结构化错误判断下一步动作，不能只靠中文文案。
- Python/Rust 职责判断：Python 侧应断言 CLI/handler 对外报告中的结构化错误码、摘要字段和数据库事实状态；Rust 侧应固定 write plan / gate 返回的错误码和事实身份。
- 建议 Rust 接管点：write plan 与 scope gate 返回结构化 code，例如 stale translation、quality_error、workflow gate 缺失等；Python 只映射为 CLI JSON 和用户文案。
- 应删除或瘦身的 Python 逻辑：减少只靠 `RuntimeError` 文案的断言；改为断言 `WriteBackGateError` 或 CLI JSON report 中的 `errors[].code`、`summary`、无文件写入状态。
- 禁止采用的错误修复方向：禁止把新增错误码断言替换为更宽松的正则文案；禁止吞掉结构化错误后统一抛 “检查没通过”。
- 后续验证：为 `write-back`、`rebuild-active-runtime`、`write-terminology` 各补一条失败测试，断言错误码、`quality_error_count` 或规则缺失计数、数据库译文/运行文件未改变。

## 双事实来源清单

- 测试 current fact 构造：生产 schema 在 `app/persistence/schema/current.sql:323`、`app/persistence/schema/current.sql:382`、`app/persistence/schema/current.sql:424`；Python helper 同时手工构造 current fact scope 和路径路由，见 `tests/_native_write_plan_helper.py:303`、`tests/_native_write_plan_helper.py:454`。
- Rust 写回测试临时 schema：`rust/src/native_core/write_back_plan/test_support.rs:2355`、`rust/src/native_core/write_back_plan/test_support.rs:2368`、`rust/src/native_core/write_back_plan/test_support.rs:2395` 也手写表结构；与 `rust/src/native_core/scope_index/storage.rs:19` 使用 `include_str!("../../../../app/persistence/schema/current.sql")` 的模式不一致。
- 规则导入与冷重建状态：公开 import 测试在 `tests/test_agent_toolkit_rule_import.py:3730` 到 `tests/test_agent_toolkit_rule_import.py:3754` 断言导入结果；冷重建测试在 `tests/test_text_index.py:673` 到 `tests/test_text_index.py:688` 直接写规则后重建，两者未形成同一事实链。

## Rust 主路径缺口

- 已有 Rust 覆盖：scope index 输出和质量摘要见 `rust/src/native_core/scope_index/mod.rs:1035`、`rust/src/native_core/scope_index/mod.rs:1158`；storage 身份拒绝见 `rust/src/native_core/scope_index/storage.rs:1469`、`rust/src/native_core/scope_index/storage.rs:1609`；write plan 按 fact_id 读取和 stale fact 拒绝见 `rust/src/native_core/write_back_plan/test_support.rs:224`、`rust/src/native_core/write_back_plan/test_support.rs:280`；插件源码 selector stale 拒绝见 `rust/src/native_core/scope_index/plugin_source.rs:878`。
- 缺口：没有看到 Rust 核心测试直接消费“公开 import 归一化后的规则 payload”，再进入 rebuild freshness 判断。
- 缺口：write-back Rust test support 仍有手写 schema 与测试事实插入；应向 `CURRENT_SCHEMA_SQL` 和 Rust current fact builder 收束。
- 缺口：跨命令 report code 到 Rust gate code 的对应关系尚未被系统性固定，写入类直接 handler 测试偏文案。

## Python 删除候选

- `tests/_native_write_plan_helper.py:454` 的 `_text_fact_domain_for_helper`：删除或降级为极小 helper，避免复制生产 domain 路由。
- `tests/_native_write_plan_helper.py:776` 的 `_source_file_for_helper` 与 `tests/_native_write_plan_helper.py:787` 的 `_selector_for_helper`：改由真实 current facts 提供 source_file 和 selector。
- `tests/current_text_fact_scope.py:43` 读取 current facts 组装旧 `TextScopeResult` 的测试适配层可以保留，但不应继续承载新事实构造职责。

## 测试缺口

当前测试覆盖清单：

- Rust 核心：scope index、scope gate、storage 身份、same-path fact、write plan fact_id/stale 读取已覆盖，证据见 `rust/src/native_core/scope_index/mod.rs:1035`、`rust/src/native_core/scope_index/storage.rs:1469`、`rust/src/native_core/write_back_plan/test_support.rs:224`。
- Python 流程：手动导出/导入/状态/质量检查已覆盖，见 `tests/test_agent_toolkit_manual_import.py:535`；翻译 cold/warm index 已覆盖，见 `tests/test_agent_toolkit_translation_limits.py:8`、`tests/test_agent_toolkit_translation_limits.py:64`；Stage0 CLI 公开流程覆盖规则导入、translate、quality-report、write-back，见 `tests/test_stage0_canaries.py:115`、`tests/test_stage0_canaries.py:162`、`tests/test_stage0_canaries.py:211`、`tests/test_stage0_canaries.py:226`。
- Python 性能/fast path：避免全量读取和 warm index 复用已有覆盖，见 `tests/test_agent_toolkit_manual_import.py:872`、`tests/test_agent_toolkit_workflow_gate.py:345`、`tests/test_agent_toolkit_workflow_gate.py:659`。

应新增 Rust 测试：

- plugin_source：import 归一化规则 payload -> Rust managed text / rebuild freshness ok；同 selector 被过滤规则排除时返回明确 code。
- note_tag、event_command、nonstandard_data：至少各一条“导入规则形状 -> Rust 候选匹配 -> rebuild 不 stale”的核心测试。
- write_back_plan：使用 current schema 与 Rust 生成事实行，覆盖 same-path 多 fact、stale fact、quality_error fact_id。

应保留的 Python 流程测试：

- 公开 CLI/AgentToolkit 的导出、校验、导入、重建、翻译、quality-report、write-back 串联验收。
- CLI JSON report 字段、错误码、摘要计数和用户可行动文案。
- `ATT_MZ_HOME`、`setting.example.toml`、临时游戏目录等外部契约链路。

不应扩大 Python 大集成测试的区域：

- 不用 Python 再实现 AST selector、Note tag path、event command path、nonstandard data path 的候选匹配。
- 不用 Python helper 手工制造更多 current text fact domain/source_file/selector 分支。
- 不用 Python monkeypatch 假 native 成功来替代 Rust 核心测试。

## 交叉引用

- 轨道 03 应复核同一生命周期缺口：`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md:114`、`docs/superpowers/specs/2026-06-10-rust-primary-multi-agent-refactor-review-design.md:115`。
- 轨道 02 应复核 Python helper 构造 current fact 是否仍属于可接受测试胶水，还是 Rust 主路径缺口。
- 轨道 01 应复核 current fact、text index、rule hash、source hash 是否只有一个事实源。
- 轨道 07 应复核新增生命周期测试是否可以最小夹具化，避免全量 CLI canary 变慢。

## 已查无发现范围

- 未发现“只有 Python 单测而完全缺 Rust 核心测试”的情况；Rust 已有 scope、storage、write plan、plugin_source stale 相关单测。
- 未发现手动导入完全不校验 fact_id 的情况；`tests/test_agent_toolkit_manual_import.py:2184` 已覆盖 stale workspace key 时按 current fact_id 保存，`tests/test_agent_toolkit_manual_import.py:2238` 已覆盖缺 current fact_id 时要求重新导出。
- 未发现 Stage0 公开 CLI 主流程完全缺失；`tests/test_stage0_canaries.py:115` 已串起 workspace 导入、translate、quality-report、write-back。
- 未执行任何 `import-*`、`translate`、`write-back`、`rebuild-active-runtime`、`reset-game`、`reset-translations`、`run-all` 或会改变项目运行状态的命令。
