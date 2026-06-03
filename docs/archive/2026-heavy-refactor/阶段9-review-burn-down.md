# 阶段 9 review burn-down

本表只记录 22 个确认问题在当前源码和阶段文档中的收束证据。历史准备文档可以继续作为历史记录存在，但不再作为当前契约来源。

| 问题编号 | 删除、合并或重建证据 | 测试证据 | 剩余风险 |
|---|---|---|---|
| ATT-MZ-REVIEW-001 | 当前 README、Skill、发行说明和审计文档只使用 `<项目目录>`、`<输入文件>`、`<输出目录>` 等占位符；真实本机路径只保留在闭环执行文档的历史问题描述中。 | `tests/test_stage9_release_contract.py`；阶段 9 路径关键词审计。 | 历史准备文档仍可能含旧例子，只能作为历史材料，不得作为当前契约。 |
| ATT-MZ-REVIEW-002 | 当前流程事实集中在 CLI、README、开发版 Skill 和发行版 Skill；历史反馈修复计划不再作为运行依赖。 | `tests/test_skill_protocol.py`；`tests/test_stage9_release_contract.py`。 | 准备文档仍保留历史描述，后续维护需避免重新引用。 |
| ATT-MZ-REVIEW-003 | CLI 输出统一为 Agent JSON 报告模型，手写 payload 入口已并入统一封装。 | `tests/test_cli_json_output.py`。 | 新增命令必须继续走同一报告模型。 |
| ATT-MZ-REVIEW-004 | Skill 与 CLI 关键协议由机器测试固定，文档只描述当前实现。 | `tests/test_skill_protocol.py`。 | 自然语言文档不测试具体措辞，只测试机器可观察边界。 |
| ATT-MZ-REVIEW-005 | 配置入口统一为 `ATT_MZ_*`；旧 `RPG_MAKER_TOOLS_*` 前缀不再作为成功配置入口。 | `tests/test_config_overrides.py`；`tests/test_skill_protocol.py`。 | 用户旧 shell 配置需要手动迁移。 |
| ATT-MZ-REVIEW-006 | 可信源快照成为注册后的单一事实来源；缺失快照时显式失败。 | `tests/test_rmmz_source_snapshot.py`；`tests/test_rmmz_write_plan.py`。 | 旧游戏数据库需要重新注册或重建快照。 |
| ATT-MZ-REVIEW-007 | 规则候选确认使用当前完整哈希契约；旧截断哈希不再兼容。 | `tests/test_agent_toolkit_rule_import.py`。 | 历史规则表需要重新导出填写。 |
| ATT-MZ-REVIEW-008 | 事件指令 JSONPath 协议从插件文本模块抽离到独立协议模块。 | `tests/test_event_command_text.py`；`tests/test_scan_budget.py`。 | 旧内部 import 需要改到当前协议模块。 |
| ATT-MZ-REVIEW-009 | 插件源码高风险检查由流程检查统一触发，不依赖调用方传入扫描结果。 | `tests/test_workflow_gate.py`；`tests/test_agent_toolkit_workflow_gate.py`；`tests/test_plugin_source_text.py`。 | 直接调用底层模块时仍需经过公开门面。 |
| ATT-MZ-REVIEW-010 | 字体文件替换、CSS 引用和字体记录纳入写入计划与应用阶段，不再散落在事务外。 | `tests/test_font_replacement_transactions.py`；`tests/test_rmmz_font_transaction.py`。 | 文件系统替换无法完全等价 SQLite 事务，失败路径依赖回滚记录。 |
| ATT-MZ-REVIEW-011 | 文本范围索引和配置覆盖共用同一快照元数据，重建时不再混用基础配置。 | `tests/test_text_index.py`。 | 索引元数据变更后旧索引会失效并重建。 |
| ATT-MZ-REVIEW-012 | 翻译停止阈值进入运行控制器，达到错误率后不再继续调度剩余批次。 | `tests/test_translation_run_limits.py`；`tests/test_agent_toolkit_translation_limits.py`。 | 已发出的模型请求无法保证被远端立即取消。 |
| ATT-MZ-REVIEW-013 | 人工质量修复导入必须绑定当前文本范围，不再把历史 quality_error 当作当前范围。 | `tests/test_manual_translation_scope.py`；`tests/test_agent_toolkit_manual_import.py`。 | 旧修复表需要重新导出。 |
| ATT-MZ-REVIEW-014 | Rust 摘要和 Python 明细统一到质量检查结果模型，避免计数不一致。 | `tests/test_quality_gate_result.py`；`tests/test_agent_toolkit_quality_report.py`。 | 后续扩展原生详情时需同步模型测试。 |
| ATT-MZ-REVIEW-015 | 写后审计提前进入提交边界；失败时不保留运行映射和数据库提交。 | `tests/test_write_back_transactions.py`；`tests/test_rmmz_post_write_audit.py`。 | 已触达的文件系统临时状态仍需依赖替换器回滚。 |
| ATT-MZ-REVIEW-016 | 规则导入跨表修改合并为一个工作单元，失败时整体回滚。 | `tests/test_rule_import_transactions.py`；`tests/test_agent_toolkit_rule_import.py`。 | 备份文件位于数据库事务外，但失败会显式报告。 |
| ATT-MZ-REVIEW-017 | JavaScript AST 原生适配层检查当前原生契约版本后才继续调用。 | `tests/test_native_adapters.py`；`cargo test --manifest-path rust/Cargo.toml`。 | 用户混用旧扩展时会直接失败，需要重装或重建。 |
| ATT-MZ-REVIEW-018 | GitHub Release 正文从 CHANGELOG 当前 tag 段落提取，并拒绝空泛或缺少验证、下载信息的正文。 | `tests/test_release_notes.py`。 | 正式发布前仍需维护者为实际 tag 补具体版本段落。 |
| ATT-MZ-REVIEW-019 | 发行包布局和发行版 Skill 转换由构建脚本与测试固定；正式 ZIP 只允许 GitHub Actions 生成。 | `tests/test_release_package_layout.py`；`.github/workflows/release.yml`。 | 本机不能完成正式 Windows ZIP 验收。 |
| ATT-MZ-REVIEW-020 | 公共 CLI 与 Agent 主线增加最小金丝雀，覆盖注册、配置、JSON 输出和关键入口。 | `tests/test_stage0_canaries.py`；`tests/test_cli_json_output.py`。 | 金丝雀使用小 fixture，不替代真实游戏验收。 |
| ATT-MZ-REVIEW-021 | 超大聚合测试拆成领域测试文件，阶段 8 结构测试固定边界。 | `tests/test_stage8_test_structure.py`；各领域 `tests/test_*.py`。 | 后续新增跨域回归时仍需控制单文件规模。 |
| ATT-MZ-REVIEW-022 | 工作区 manifest 是当前输入的单一事实来源；旧可选文件不能被当作当前输入自动校验。 | `tests/test_workspace_manifest.py`；`tests/test_agent_toolkit_workspace.py`；`tests/test_stage0_canaries.py`。 | 用户保留旧工作区文件时需要重新导出 manifest。 |
