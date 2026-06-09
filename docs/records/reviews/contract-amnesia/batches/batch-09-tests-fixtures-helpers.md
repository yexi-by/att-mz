# 批次 09：测试、fixtures 与 helper

## 范围

- 本批只审查 `tests/`。
- 本批只写入本报告：`docs/records/reviews/contract-amnesia/batches/batch-09-tests-fixtures-helpers.md`。
- 本批未读取 `data/`、`logs/`、`outputs/`、`tmp/`、`dist/`、`target/`、`.venv/`、`.pytest_cache/`、`__pycache__/`。

## 事实源

- `tests/` 中的测试、fixture、helper、测试契约模块和断言文案。
- 指定三条只读命令的输出，以及围绕命中行执行的窄范围 `rg -C` 复核。
- 本批未审查运行时代码、schema、Skill 正文或 README 正文；涉及这些对象的影响只作为交叉引用。

## 只读命令

已按要求运行：

```powershell
rg -n 'legacy|fallback|old|stale|v[0-9]+|migration|migrate|compat|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|过期|旧式|测试专用' tests
```

结果：有大量命中，确认测试 helper、测试命名、测试文案和测试契约模块仍使用 `legacy`、`fallback`、`旧式`、`旧数据库`、`迁移`、`旧 Python` 等历史模型词。

```powershell
Get-ChildItem -File -LiteralPath tests | Sort-Object Length -Descending | Select-Object -First 20 Name,Length
```

结果：顶层最大测试文件包括 `test_agent_toolkit_rule_import.py`、`test_plugin_source_text.py`、`test_agent_toolkit_manual_import.py`、`test_native_scope_index.py`、`test_rmmz_write_plan.py`、`test_agent_toolkit_workspace.py`、`test_cli_json_output.py`、`test_agent_toolkit_quality_report.py`、`test_agent_toolkit_workflow_gate.py`、`test_persistence.py` 等。

```powershell
rg -n 'make_current|write_v2|stale|generated_stale|ensure_current|read_current|fact_id|location_path' tests/_native_write_plan_helper.py tests/agent_toolkit_contract_fixtures.py tests/current_v2_scope.py tests/rmmz_writeback_contract_fixtures.py
```

结果：确认 `write_v2_test_translation_items`、`_generated_stale_v2_test_item`、`_ensure_current_v2_text_index_for_test`、`fact_id` 和 `location_path` 相关 helper 仍在测试层承担旧形态到当前 v2 fact 的适配职责。

额外只读复核：

```powershell
rg -n -C 4 '旧式测试译文|items_to_migrate|_stale_v2_test_items|_generated_stale_v2_test_item|items_to_migrate|migrated_items' tests/agent_toolkit_contract_fixtures.py
rg -n -C 4 '旧式测试译文|items_to_migrate|_generated_stale_v2_test_item|migrated_items' tests/rmmz_writeback_contract_fixtures.py
rg -n 'legacy|fallback|compat|migration|migrate|旧式|旧数据库|旧空规则确认|旧 Python|回退|迁移|兼容' tests
```

## 结论

FAIL

## 发现

### P2：测试译文写入 helper 仍是旧式译文到当前 v2 fact 的迁移适配层

- 证据：`tests/agent_toolkit_contract_fixtures.py:254`
- 证据：`tests/agent_toolkit_contract_fixtures.py:256`
- 证据：`tests/agent_toolkit_contract_fixtures.py:293`
- 证据：`tests/rmmz_writeback_contract_fixtures.py:305`
- 证据：`tests/rmmz_writeback_contract_fixtures.py:306`
- 证据：`tests/rmmz_writeback_contract_fixtures.py:332`
- 违反准则：测试失忆化
- 影响范围：两个共享测试 fixture 都把输入称为“旧式测试译文”，使用 `items_to_migrate` 和 `migrated_items` 表达适配流程，再写入当前主译文表。测试调用方可以继续按旧 `TranslationItem` 形状组织数据，由 helper 隐式转成当前 v2 fact 身份，导致测试模型保留历史入口而不是直接表达当前事实身份契约。
- 建议收束：删除通用“旧式译文迁移”写入入口，改为只接受当前 v2 fact identity 已完整的测试对象；需要构造无效或过期译文时，使用独立、显式命名的当前无效状态 fixture，避免把普通测试写入路径和历史适配混在一起。
- 后续验证：清理后运行 `rg -n '旧式测试译文|items_to_migrate|migrated_items|write_v2_test_translation_items' tests/agent_toolkit_contract_fixtures.py tests/rmmz_writeback_contract_fixtures.py`，并补跑受影响的写回、agent toolkit 流程测试。

### P2：测试 helper 会为缺失当前 fact 的输入自动生成过期 v2 行

- 证据：`tests/agent_toolkit_contract_fixtures.py:261`
- 证据：`tests/agent_toolkit_contract_fixtures.py:281`
- 证据：`tests/agent_toolkit_contract_fixtures.py:331`
- 证据：`tests/rmmz_writeback_contract_fixtures.py:317`
- 证据：`tests/rmmz_writeback_contract_fixtures.py:347`
- 违反准则：测试失忆化
- 影响范围：普通测试写入 helper 遇到缺失当前 fact 的路径时，会自动写入 `_generated_stale_v2_test_item` 生成的过期行。这让测试中的无效输入不是显式失败或显式 fixture，而是通过 helper 内部转成历史/过期形态，容易掩盖调用方没有提供当前契约数据的问题。
- 建议收束：把“构造过期译文行”从普通写入 helper 中移除，只保留专用函数给明确测试过期数据拒绝、清理或诊断的用例调用；普通写入缺少当前 fact 时应直接测试失败。
- 后续验证：清理后运行 `rg -n '_generated_stale_v2_test_item|test-stale-fact|stale_items|remaining_missing_items' tests/agent_toolkit_contract_fixtures.py tests/rmmz_writeback_contract_fixtures.py`，并确认普通写入 helper 不再静默生成过期行。

### P2：测试契约模块和回归测试继续以旧 Python/fallback/迁移路径命名当前断言

- 证据：`tests/scan_budget_contract.py:3`
- 证据：`tests/scan_budget_contract.py:397`
- 证据：`tests/scan_budget_contract.py:409`
- 证据：`tests/test_agent_toolkit_coverage.py:115`
- 证据：`tests/test_agent_toolkit_coverage.py:120`
- 证据：`tests/test_workflow_gate.py:212`
- 证据：`tests/test_scan_budget.py:363`
- 违反准则：测试失忆化
- 影响范围：扫描预算和多处回归测试用“旧 Python”“fallback”“已迁移”等词描述当前生产事实来源。它们确实在保护当前 Rust/native 路径，但测试事实源仍以历史路径为参照，容易让后续维护者把“不要回到旧实现”当成当前契约，而不是直接固定“当前命令必须只消费当前事实源/当前 native 输出”。
- 建议收束：将这些测试标题、docstring、断言错误文案和预算说明改写为当前契约语言，例如“必须消费 Rust scope/index 输出”“不得构造第二文本事实来源”“当前命令只读取 text_facts_v2”；删除 `legacy`、`fallback`、`已迁移` 这类历史参照词。
- 后续验证：清理后运行 `rg -n 'legacy|fallback|旧 Python|已迁移|迁移|不回退|不能回退|不应回退' tests/scan_budget_contract.py tests/test_scan_budget.py tests/test_agent_toolkit_coverage.py tests/test_workflow_gate.py`。

### P2：配置、持久化和原生适配测试保留旧版本/旧名称的专用模型

- 证据：`tests/test_config_overrides.py:423`
- 证据：`tests/test_config_overrides.py:582`
- 证据：`tests/test_config_overrides.py:590`
- 证据：`tests/test_persistence.py:368`
- 证据：`tests/test_persistence.py:375`
- 证据：`tests/test_persistence.py:831`
- 证据：`tests/test_native_adapters.py:89`
- 证据：`tests/test_native_adapters.py:255`
- 证据：`tests/test_native_adapters.py:293`
- 违反准则：测试失忆化
- 影响范围：测试中仍有 `legacy` 环境变量、旧 CLI 用法、旧注册库、旧 Rust 扩展等专用模型。部分测试是在确认当前入口显式拒绝无效状态，但命名和 fixture 仍记住历史来源，且配置/持久化/原生适配属于外部契约边界，需要其他批次复核运行时是否也保留了历史识别分支。
- 建议收束：把这些 fixture 和测试改成“当前不支持的配置键”“缺少当前 schema 的注册库”“缺少当前 native_contract_version 的扩展”等当前无效状态；错误文案断言只说明当前要求，不要求出现历史名称。
- 后续验证：清理后运行 `rg -n 'legacy|旧 CLI|旧模型环境变量|RPG_MAKER_TOOLS_|旧版注册库|旧 Rust|旧契约|版本过旧' tests/test_config_overrides.py tests/test_persistence.py tests/test_native_adapters.py`，并由配置、schema、native 相关批次复核是否存在 P0。

### P2：测试要求当前 Skill/README 契约继续包含历史恢复对象

- 证据：`tests/test_skill_protocol.py:146`
- 证据：`tests/test_skill_protocol.py:151`
- 证据：`tests/test_skill_protocol.py:152`
- 证据：`tests/test_skill_protocol.py:153`
- 证据：`tests/test_release_notes.py:43`
- 证据：`tests/test_release_notes.py:47`
- 违反准则：测试失忆化 | 文档分层
- 影响范围：`test_skill_protocol.py` 要求 README 与 Skill CLI 契约包含“旧数据库”“旧工作区”“旧 runtime map”。发布说明保留历史更新内容可以接受，但当前 Skill/README 是当前事实源；测试把历史恢复对象固定为当前文档必须解释的概念，可能把 P1 文档污染变成持续契约。
- 建议收束：保留发布说明测试对历史更新说明的覆盖；移除当前 Skill/README 测试中的历史词要求，改为断言当前恢复入口和当前无效状态处理，例如重建文本索引、重建工作区、重建 runtime map 的当前命令与错误处理。
- 后续验证：清理后运行 `rg -n '旧数据库|旧工作区|旧 runtime map|legacy_hash|前 100 个候选' tests/test_skill_protocol.py tests/test_release_notes.py`，并运行 `uv run python scripts/generate_skill_protocol.py --check`。

## 交叉引用

- 配置、持久化、native 运行时批次应复核 `tests/test_config_overrides.py`、`tests/test_persistence.py`、`tests/test_native_adapters.py` 暗示的旧名称/旧 schema/旧扩展处理是否在运行时代码中构成 P0。
- docs 与 Skill 批次应复核 `test_skill_protocol.py` 固定的“旧数据库”“旧工作区”“旧 runtime map”是否已经污染当前 README 或 Skill 正文；若正文仍出现，应按 P1 收束到发布说明或迁移指南。
- 扫描预算、agent toolkit 与写回批次应复核“旧 Python fallback”相关测试是否只是测试文案残留，还是生产路径中仍有第二事实源或保留入口。

## 已查无发现范围

- `tests/conftest.py:618` 与 `tests/test_translation_line_alignment.py:158` 等命中的 `old gate` 属于测试游戏文本内容，不确认作为契约历史形态。
- `tests/current_v2_scope.py` 中的“测试专用”用于说明测试范围构造器，未确认直接违反契约失忆化。
- `tests/test_workspace_manifest.py` 中“旧文件不会参与本轮”描述 manifest 外遗留文件处理，未确认是历史契约形态。
- `stale` 用于当前 v2 fact/hash 不匹配、规则输入范围变化等无效状态的测试不全部视为问题；本批只记录普通 helper 隐式生成过期行、或用历史对象命名当前契约的确认发现。
