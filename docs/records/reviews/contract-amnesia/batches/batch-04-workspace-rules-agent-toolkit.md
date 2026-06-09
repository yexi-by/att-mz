# 批次 04：工作区、规则与 Agent toolkit

## 范围

- `app/agent_toolkit/`
- `app/plugin_text/`
- `app/plugin_source_text/`
- `app/event_command_text/`
- `app/note_tag_text/`
- `app/nonstandard_data/`
- `app/config/structured_placeholder_rules.py`
- `app/config/custom_placeholder_rules.py`
- `tests/test_agent_toolkit_*.py`

## 事实源

- 本批只审查工作区导出、工作区验收、规则校验、Agent toolkit 用户文案、运行时诊断输出、内部 helper 注释与相关测试模型。
- 当前契约应只说明当前要求、当前问题和下一步修正；不得把旧索引、旧文件、legacy/fallback 路径、旧 scanner、旧规则链路等历史形态作为当前运行时文案或测试/内部模型。
- `stale` / `过期` 类命中中，若仅表达当前输入与当前游戏内容不匹配，未单独计为确认问题；下列发现只记录明确暴露历史实现或历史文件/数据形态的证据。

## 只读命令

- `rg -n 'manifest|workspace|review|confirm|candidate|sample|legacy|fallback|old|stale|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|旧工作区|旧确认|过期' app/agent_toolkit app/plugin_text app/plugin_source_text app/event_command_text app/note_tag_text app/nonstandard_data app/config/structured_placeholder_rules.py app/config/custom_placeholder_rules.py tests/test_agent_toolkit_*.py`
  - 结果：已执行；PowerShell 未展开 `tests/test_agent_toolkit_*.py`，`rg` 对该字面路径返回 `os error 123`，同时输出了源码范围命中。
- `$testFiles = Get-ChildItem -LiteralPath tests -Filter 'test_agent_toolkit_*.py' -File | ForEach-Object { $_.FullName }; rg -n 'manifest|workspace|review|confirm|candidate|sample|legacy|fallback|old|stale|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式|旧工作区|旧确认|过期' app/agent_toolkit app/plugin_text app/plugin_source_text app/event_command_text app/note_tag_text app/nonstandard_data app/config/structured_placeholder_rules.py app/config/custom_placeholder_rules.py @testFiles`
  - 结果：退出码 0；用于补足第一条命令在 PowerShell 下未覆盖的测试文件。
- `rg -n 'manifest\.files|manifest|exists\(\)|cleanup|validate_agent_workspace|prepare_agent_workspace|plugin-source-rules|nonstandard-data-rules' app/agent_toolkit tests/test_agent_toolkit_workspace.py`
  - 结果：退出码 0；主要命中工作区 manifest 生成、manifest 范围判断、cleanup 与 `validate_agent_workspace` / `prepare_agent_workspace`。
- 写入报告后需执行：`$patterns = @('待' + '定', '未' + '填写', '样本' + '根目录', '占位符' + '未替换'); Select-String -LiteralPath 'docs\records\reviews\contract-amnesia\batches\batch-04-workspace-rules-agent-toolkit.md' -Pattern $patterns`

## 结论

FAIL

## 发现

### P0：反馈文本校验错误文案暴露“旧索引正文”

- 证据：`app/agent_toolkit/services/feedback.py:140`
- 证据：`app/agent_toolkit/services/feedback.py:141`
- 证据：`app/agent_toolkit/services/feedback.py:212`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：`verify_feedback_text` 在当前文本索引记录缺少当前文本事实时，会把用户可见错误写成“不能继续使用旧索引正文”。这把历史索引实现和旧正文来源作为当前用户需要理解的概念，污染运行时错误文案。
- 建议收束：删除“旧索引正文”表达，改为只说明当前要求和修正方式，例如“当前文本索引记录缺少当前文本事实；请运行 rebuild-text-index 重新生成当前文本索引”。同时检查返回 `details` 中是否仍需要暴露 `text_fact_contract_error` 这类内部命名。
- 后续验证：运行 `rg -n '旧索引正文|旧 text_index|old index|legacy index' app/agent_toolkit tests/test_agent_toolkit_*.py`，并运行覆盖 `verify_feedback_text` 缺失 fact 路径的目标测试。

### P0：工作区 cleanup 警告把 manifest 外文件定义为“旧文件”

- 证据：`app/agent_toolkit/services/workspace.py:1461`
- 证据：`app/agent_toolkit/services/workspace.py:2126`
- 违反准则：运行时失忆化 | 文案失忆化
- 影响范围：`cleanup_agent_workspace` 检出 `manifest.files` 之外的路径时，用户可见 warning 写成“manifest 外旧文件，旧文件不会参与本轮验收”。当前契约只需要表达“未列入本轮 manifest 的文件未被自动清理/未参与本轮处理”，不应把它们解释为旧工作区或旧文件。
- 建议收束：将 warning 和注释统一改为“manifest 外文件”或“未列入本轮 manifest 的文件”，保留安全行为与手动处理建议；避免用“旧文件”判断文件来源。
- 后续验证：运行 `rg -n '旧文件|旧工作区|workspace_unlisted_files_ignored' app/agent_toolkit/services/workspace.py tests/test_agent_toolkit_workspace.py`，并运行 cleanup 工作区相关目标测试。

### P2：Agent toolkit 内部 helper 注释保留 legacy / 旧报告 / 旧规则链路模型

- 证据：`app/agent_toolkit/services/common.py:1169`
- 证据：`app/agent_toolkit/services/common.py:1171`
- 证据：`app/agent_toolkit/services/common.py:1589`
- 证据：`app/agent_toolkit/services/common.py:1628`
- 证据：`app/plugin_source_text/native_scan.py:426`
- 证据：`app/plugin_source_text/native_scan.py:470`
- 证据：`app/plugin_source_text/native_scan.py:490`
- 证据：`app/plugin_source_text/native_scan.py:544`
- 证据：`app/plugin_source_text/native_scan.py:562`
- 证据：`app/note_tag_text/extraction.py:93`
- 违反准则：测试失忆化 | 文档分层
- 影响范围：这些注释位于生产代码 helper 和 adapter 周边，持续把当前 helper 描述为 `legacy Python`、`旧报告同形`、`旧风险阈值`、`旧规则链路`、`旧 AST map` 或 `旧提取路径`。虽然主要是内部注释，但会把维护判断锚定在历史迁移过程，而非当前模块职责。
- 建议收束：把注释改成当前职责描述，例如“根据统一文本清单生成覆盖审计报告”“从候选明细生成规则草稿”“将 Rust 候选 JSON 转为 PluginSourceCandidate”。若某 helper 只剩测试使用，应移动到测试 helper 或删除生产导出，避免生产代码携带历史 owner 说明。
- 后续验证：运行 `rg -n 'legacy|旧报告|旧风险|旧规则链路|旧 AST|旧提取路径|non-migrated' app/agent_toolkit app/plugin_source_text app/note_tag_text`。

### P2：Agent toolkit 测试以 legacy / fallback / 旧 scanner 等历史模型命名当前契约

- 证据：`tests/test_agent_toolkit_workspace.py:158`
- 证据：`tests/test_agent_toolkit_workspace.py:162`
- 证据：`tests/test_agent_toolkit_workspace.py:188`
- 证据：`tests/test_agent_toolkit_workspace.py:192`
- 证据：`tests/test_agent_toolkit_workspace.py:222`
- 证据：`tests/test_agent_toolkit_workspace.py:245`
- 证据：`tests/test_agent_toolkit_workspace.py:247`
- 证据：`tests/test_agent_toolkit_workspace.py:454`
- 证据：`tests/test_agent_toolkit_workspace.py:510`
- 证据：`tests/test_agent_toolkit_workspace.py:512`
- 证据：`tests/test_agent_toolkit_workspace.py:541`
- 证据：`tests/test_agent_toolkit_rule_import.py:1128`
- 证据：`tests/test_agent_toolkit_rule_import.py:1132`
- 证据：`tests/test_agent_toolkit_rule_import.py:1152`
- 证据：`tests/test_agent_toolkit_rule_import.py:1956`
- 证据：`tests/test_agent_toolkit_rule_import.py:1960`
- 证据：`tests/test_agent_toolkit_rule_import.py:1986`
- 证据：`tests/test_agent_toolkit_rule_import.py:2015`
- 证据：`tests/test_agent_toolkit_rule_import.py:2019`
- 证据：`tests/test_agent_toolkit_rule_import.py:2491`
- 证据：`tests/test_agent_toolkit_rule_import.py:2509`
- 证据：`tests/test_agent_toolkit_rule_import.py:2511`
- 证据：`tests/test_agent_toolkit_rule_import.py:3328`
- 证据：`tests/test_agent_toolkit_rule_import.py:3580`
- 证据：`tests/test_agent_toolkit_rule_import.py:3582`
- 证据：`tests/test_agent_toolkit_rule_import.py:3625`
- 证据：`tests/test_agent_toolkit_rule_import.py:3627`
- 证据：`tests/test_agent_toolkit_feedback.py:139`
- 证据：`tests/test_agent_toolkit_feedback.py:208`
- 证据：`tests/test_agent_toolkit_feedback.py:282`
- 证据：`tests/test_agent_toolkit_feedback.py:307`
- 证据：`tests/test_agent_toolkit_feedback.py:813`
- 违反准则：测试失忆化
- 影响范围：测试名、docstring、fixture 变量和 assertion 文案大量使用 `legacy`、`fallbacks`、`旧 scanner`、`旧 Python`、`旧索引`、`旧版 hash`、`旧提取器` 等历史迁移语言。测试虽然在防止回退，但它们仍把历史实现当成当前测试模型，和“测试只描述当前契约”的要求冲突。
- 建议收束：按当前无效输入或当前职责重命名测试与 helper，例如 `rejects_manifest_missing_text_fact_scope`、`uses_native_plugin_source_scan`、`rejects_sampled_scope_hash`、`does_not_call_text_scope_adapter`；断言文案只说明不应调用的当前禁用入口或当前职责，不再称其为旧实现。
- 后续验证：运行 `$testFiles = Get-ChildItem -LiteralPath tests -Filter 'test_agent_toolkit_*.py' -File | ForEach-Object { $_.FullName }; rg -n 'legacy|fallback|old|旧|历史|兼容|迁移|废弃|回退|旧版|旧格式' @testFiles`。

## 交叉引用

- 批次内的 `plugin_text`、`event_command_text`、`note_tag_text`、`plugin_source_text`、`nonstandard_data` 存在多处“规则已过期”命中；本次未直接计为发现，因为对应文案主要表达当前规则与当前游戏内容不匹配，并给出重新导出/导入的当前修正动作。
- `app/plugin_source_text/runtime_audit.py` 的 `stale_file_count`、`runtime_mapping_stale`、缓存 miss/rescan 统计属于当前缓存失效和当前运行文件状态描述；未确认其直接保留历史格式判断。相关测试中 `legacy literal cache` 的历史命名已纳入 P2 测试发现。
- `Text Fact Contract v2` / `text_fact_schema_version` 命中涉及当前事实范围版本校验；本批未单独定性为历史形态，但建议后续批次结合全局用户文案规范判断是否需要改成更面向用户的中文当前契约描述。

## 已查无发现范围

- `app/config/structured_placeholder_rules.py` 与 `app/config/custom_placeholder_rules.py`：未发现 legacy/旧格式/回退等确认问题；命中主要是当前规则解析、校验与导出名。
- `app/nonstandard_data/`：未发现确认的历史实现文案；“规则已过期”类文案按当前规则与当前文件不匹配处理。
- `app/event_command_text/`、`app/plugin_text/`：未发现除“规则已过期”当前失效提示之外的确认问题。
- `app/plugin_source_text/runtime_audit.py`：未发现用户可见的 legacy 文案；缓存统计中的 `stale` 按当前缓存失效处理。
