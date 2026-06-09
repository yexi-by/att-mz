"""Rust Scope/Index Engine 扫描预算测试契约。

只供测试验证 P0/P1 命令不会重复全量扫描，也不会把 Python
重型路径继续作为默认生产事实来源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


type ScanBudgetCategory = Literal["P0", "P1-A", "P1-B", "P1-C"]


@dataclass(frozen=True, slots=True)
class ScanBudget:
    """单个命令内重型扫描和计划构建的允许次数。"""

    command_name: str
    category: ScanBudgetCategory
    game_data_load_count: int
    text_scope_build_count: int
    candidate_scan_count: int
    plugin_source_ast_scan_count: int
    quality_gate_count: int
    write_plan_count: int
    authoritative_source: str
    current_path_requirement: str
    evidence: str


P0_COMMANDS = frozenset({
    "export-pending-translations --limit",
})

P1_A_COMMANDS = frozenset({
    "rebuild-text-index",
    "translation-status --refresh-scope",
    "text-scope",
    "audit-coverage",
    "quality-report",
    "export-quality-fix-template",
    "import-manual-translations",
    "reset-translations",
    "translate",
    "run-all",
    "write-back",
    "rebuild-active-runtime",
    "write-terminology",
})

P1_B_COMMANDS = frozenset({
    "prepare-agent-workspace",
    "validate-agent-workspace",
    "scan-plugin-source-text",
    "export-plugin-source-ast-map",
    "scan-nonstandard-data",
    "export-nonstandard-data-json",
    "validate-nonstandard-data-rules",
    "import-nonstandard-data-rules",
    "scan-placeholder-candidates",
    "validate-placeholder-rules",
    "build-placeholder-rules",
    "import-placeholder-rules",
    "validate-structured-placeholder-rules",
    "scan-structured-placeholder-candidates",
    "import-structured-placeholder-rules",
    "export-note-tag-candidates",
    "validate-note-tag-rules",
    "import-note-tag-rules",
    "export-event-commands-json",
    "validate-event-command-rules",
    "import-event-command-rules",
    "validate-plugin-rules",
    "import-plugin-rules",
    "validate-plugin-source-rules",
    "import-plugin-source-rules",
    "export-mv-virtual-namebox-candidates",
    "validate-mv-virtual-namebox-rules",
    "import-mv-virtual-namebox-rules",
    "validate-source-residual-rules",
    "import-source-residual-rules",
})

P1_B_PENDING_FACT_SOURCE_COMMANDS: frozenset[str] = frozenset()

P1_C_COMMANDS = frozenset({
    "audit-active-runtime",
    "diagnose-active-runtime",
    "verify-feedback-text",
    "export-terminology",
    "import-terminology",
    "probe-source-language",
    "export-plugins-json",
})


def _scope_budget(
    command_name: str,
    category: ScanBudgetCategory,
    *,
    quality_gate_count: int = 0,
    write_plan_count: int = 0,
    authoritative_source: str = "Rust build_scope_index / SQLite text index",
    current_path_requirement: str = "使用当前主路径或薄适配层",
    evidence: str,
) -> ScanBudget:
    """构造默认 scope/index 命令预算。"""
    return ScanBudget(
        command_name=command_name,
        category=category,
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=quality_gate_count,
        write_plan_count=write_plan_count,
        authoritative_source=authoritative_source,
        current_path_requirement=current_path_requirement,
        evidence=evidence,
    )


def _candidate_budget(
    command_name: str,
    *,
    plugin_source_ast_scan_count: int,
    authoritative_source: str,
    evidence: str,
) -> ScanBudget:
    """构造 P1-B 候选扫描命令预算。"""
    return ScanBudget(
        command_name=command_name,
        category="P1-B",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=plugin_source_ast_scan_count,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source=authoritative_source,
        current_path_requirement="使用当前候选扫描主路径或薄适配层",
        evidence=evidence,
    )


def _source_residual_rule_budget(
    command_name: str,
    *,
    evidence: str,
) -> ScanBudget:
    """构造源文残留例外规则命令预算。"""
    return ScanBudget(
        command_name=command_name,
        category="P1-B",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source=(
            "SQLite text_facts / current text fact adapter 精确路径查询 / "
            "Python source_residual 规则解析 / Rust regex contract / Rust quality"
        ),
        current_path_requirement="命令内使用精确路径查询，避免全量文本范围构建和全量译文读取",
        evidence=evidence,
    )


_SCAN_BUDGETS: dict[str, ScanBudget] = {
    "export-pending-translations --limit": _scope_budget(
        "export-pending-translations --limit",
        "P0",
        authoritative_source="SQLite text_facts pending 快路径 / current text fact adapter",
        current_path_requirement="pending limit 必须走 SQLite 快路径",
        evidence="有效索引下 limit 必须在 SQLite 查询中生效；索引失效时最多触发一次 Rust rebuild。",
    ),
    "rebuild-text-index": _scope_budget(
        "rebuild-text-index",
        "P1-A",
        evidence="索引重建是 build_scope_index 的唯一完整范围扫描入口。",
    ),
    "translation-status --refresh-scope": _scope_budget(
        "translation-status --refresh-scope",
        "P1-A",
        evidence="刷新状态只允许在索引缺失或失效时重建一次，然后统计走 SQLite。",
    ),
    "text-scope": _scope_budget(
        "text-scope",
        "P1-A",
        evidence="完整清单可以全量输出，但清单来源必须是 Rust/index。",
    ),
    "audit-coverage": _scope_budget(
        "audit-coverage",
        "P1-A",
        evidence="覆盖统计消费 domain summary 和 rule hit summary，不重复 Python 统计。",
    ),
    "quality-report": _scope_budget(
        "quality-report",
        "P1-A",
        quality_gate_count=1,
        authoritative_source="Rust evaluate_scope_gate / Rust quality / SQLite text_facts / current text fact adapter",
        current_path_requirement="质量门禁和大规模筛选只保留当前主路径",
        evidence="质量报告最多执行一次质量 gate，并复用当前范围事实。",
    ),
    "export-quality-fix-template": _scope_budget(
        "export-quality-fix-template",
        "P1-A",
        quality_gate_count=1,
        authoritative_source="Rust evaluate_scope_gate / Rust quality / SQLite text_facts / current text fact adapter",
        current_path_requirement="质量明细筛选复用当前质量报告结果",
        evidence="修复表导出消费 quality-report 同源结果，不另建范围事实。",
    ),
    "import-manual-translations": ScanBudget(
        command_name="import-manual-translations",
        category="P1-A",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="SQLite text_facts / current text fact adapter 路径归属校验",
        current_path_requirement="路径归属校验走当前 text fact 查询",
        evidence="手动导入只验证路径属于当前范围，不执行候选扫描和质量 gate。",
    ),
    "reset-translations": ScanBudget(
        command_name="reset-translations",
        category="P1-A",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="SQLite text_facts / current text fact adapter 路径归属校验",
        current_path_requirement="路径归属校验走当前 text fact 查询",
        evidence="精确重置输入只做路径归属校验，不能全量构建再筛选。",
    ),
    "translate": _scope_budget(
        "translate",
        "P1-A",
        authoritative_source="SQLite pending 快路径 / Rust evaluate_scope_gate",
        current_path_requirement="translate --max-items 前置 gate 使用当前索引事实",
        evidence="正文翻译的 --max-items 前置 gate 和批次准备消费同一索引事实。",
    ),
    "run-all": _scope_budget(
        "run-all",
        "P1-A",
        quality_gate_count=1,
        write_plan_count=1,
        authoritative_source="Rust build_scope_index / evaluate_scope_gate / write plan",
        current_path_requirement="翻译与写回阶段复用当前范围事实",
        evidence="run-all 翻译限制和写回阶段应复用同一命令内已建立的当前范围事实。",
    ),
    "write-back": _scope_budget(
        "write-back",
        "P1-A",
        quality_gate_count=1,
        write_plan_count=1,
        authoritative_source="Rust evaluate_scope_gate / Rust write plan",
        current_path_requirement="可写路径推导统一进入当前写回计划",
        evidence="写回 gate、字体副作用、插件源码映射和文件计划统一进入 Rust WritePlan。",
    ),
    "rebuild-active-runtime": _scope_budget(
        "rebuild-active-runtime",
        "P1-A",
        quality_gate_count=1,
        write_plan_count=1,
        authoritative_source="Rust evaluate_scope_gate / Rust write plan",
        current_path_requirement="可写路径推导统一进入当前写回计划",
        evidence="重建当前运行文件和 write-back 共用 Rust WritePlan 边界。",
    ),
    "write-terminology": _scope_budget(
        "write-terminology",
        "P1-A",
        quality_gate_count=1,
        write_plan_count=1,
        authoritative_source="Rust evaluate_scope_gate / Rust write plan",
        current_path_requirement="写术语前检查复用当前可写范围",
        evidence="术语写入前检查复用写回可写范围和质量 gate。",
    ),
    "prepare-agent-workspace": _candidate_budget(
        "prepare-agent-workspace",
        plugin_source_ast_scan_count=1,
        authoritative_source="Rust build_scope_index / scan_rule_candidates",
        evidence="工作区准备只生成本轮 manifest 和规则候选，不执行写回级质量 gate。",
    ),
    "validate-agent-workspace": _candidate_budget(
        "validate-agent-workspace",
        plugin_source_ast_scan_count=1,
        authoritative_source="Rust scan_rule_candidates / workspace manifest",
        evidence="工作区校验消费 manifest，并在同一轮内复用规则候选扫描结果。",
    ),
    "scan-plugin-source-text": _candidate_budget(
        "scan-plugin-source-text",
        plugin_source_ast_scan_count=1,
        authoritative_source="Rust scan_rule_candidates(plugin_source)",
        evidence="插件源码候选扫描主路径迁到 Rust AST 扫描器。",
    ),
    "export-plugin-source-ast-map": _candidate_budget(
        "export-plugin-source-ast-map",
        plugin_source_ast_scan_count=1,
        authoritative_source="Rust scan_rule_candidates(plugin_source)",
        evidence="AST map 导出复用 Rust 插件源码扫描结果。",
    ),
    "scan-nonstandard-data": _candidate_budget(
        "scan-nonstandard-data",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(nonstandard_data)",
        evidence="非标准 data 文本候选扫描主路径迁到 Rust。",
    ),
    "export-nonstandard-data-json": _candidate_budget(
        "export-nonstandard-data-json",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(nonstandard_data)",
        evidence="非标准 data 导出只渲染 Rust 候选结果和工作区 JSON。",
    ),
    "validate-nonstandard-data-rules": _candidate_budget(
        "validate-nonstandard-data-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(nonstandard_data)",
        evidence="规则校验消费同一非标准 data 候选结果。",
    ),
    "import-nonstandard-data-rules": _candidate_budget(
        "import-nonstandard-data-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(nonstandard_data)",
        evidence="规则导入前覆盖检查消费同一非标准 data 候选结果。",
    ),
    "scan-placeholder-candidates": _candidate_budget(
        "scan-placeholder-candidates",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(placeholders)",
        evidence="普通占位符候选覆盖扫描迁到 Rust。",
    ),
    "validate-placeholder-rules": _candidate_budget(
        "validate-placeholder-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(placeholders)",
        evidence="普通占位符规则校验消费 Rust 候选覆盖结果。",
    ),
    "build-placeholder-rules": _candidate_budget(
        "build-placeholder-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(placeholders)",
        evidence="占位符规则生成只允许一次候选扫描。",
    ),
    "import-placeholder-rules": _candidate_budget(
        "import-placeholder-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(placeholders)",
        evidence="占位符规则导入前覆盖检查消费同一候选结果。",
    ),
    "validate-structured-placeholder-rules": _candidate_budget(
        "validate-structured-placeholder-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(structured_placeholders)",
        evidence="结构化占位符校验消费 Rust 候选覆盖结果。",
    ),
    "scan-structured-placeholder-candidates": _candidate_budget(
        "scan-structured-placeholder-candidates",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(structured_placeholders)",
        evidence="结构化占位符候选覆盖扫描迁到 Rust。",
    ),
    "import-structured-placeholder-rules": _candidate_budget(
        "import-structured-placeholder-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(structured_placeholders)",
        evidence="结构化占位符导入前覆盖检查消费同一候选结果。",
    ),
    "export-note-tag-candidates": _candidate_budget(
        "export-note-tag-candidates",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(note_tags)",
        evidence="Note 标签候选扫描迁到 Rust。",
    ),
    "validate-note-tag-rules": _candidate_budget(
        "validate-note-tag-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(note_tags)",
        evidence="Note 标签规则校验消费 Rust 候选结果。",
    ),
    "import-note-tag-rules": _candidate_budget(
        "import-note-tag-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(note_tags)",
        evidence="Note 标签规则导入前覆盖检查消费同一候选结果。",
    ),
    "export-event-commands-json": _candidate_budget(
        "export-event-commands-json",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(event_commands) samples_by_code",
        evidence="已收束: 事件指令导出消费 Rust samples_by_code，并维持公开 JSON 输出形状。",
    ),
    "validate-event-command-rules": _candidate_budget(
        "validate-event-command-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(event_commands) rule_summaries/hit_details",
        evidence="已收束: 事件指令规则校验报告消费 Rust rule_summaries 与 hit_details。",
    ),
    "import-event-command-rules": _candidate_budget(
        "import-event-command-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(event_commands) rule_summaries/hit_details",
        evidence="已收束: 事件指令规则导入前覆盖检查和当前译文清理消费 Rust rule_summaries 与 hit_details。",
    ),
    "validate-plugin-rules": _candidate_budget(
        "validate-plugin-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(plugin_config) rule_summaries/hit_details",
        evidence="已收束: 插件参数规则校验报告消费 Rust rule_summaries 与 hit_details。",
    ),
    "import-plugin-rules": _candidate_budget(
        "import-plugin-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(plugin_config) rule_summaries/hit_details",
        evidence="已收束: 插件参数规则导入前覆盖检查和当前译文清理消费 Rust rule_summaries 与 hit_details。",
    ),
    "validate-plugin-source-rules": _candidate_budget(
        "validate-plugin-source-rules",
        plugin_source_ast_scan_count=1,
        authoritative_source="Rust scan_rule_candidates(plugin_source)",
        evidence="插件源码规则校验消费 Rust AST 候选结果。",
    ),
    "import-plugin-source-rules": _candidate_budget(
        "import-plugin-source-rules",
        plugin_source_ast_scan_count=1,
        authoritative_source="Rust scan_rule_candidates(plugin_source)",
        evidence="插件源码规则导入前覆盖检查消费同一 AST 候选结果。",
    ),
    "export-mv-virtual-namebox-candidates": _candidate_budget(
        "export-mv-virtual-namebox-candidates",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(mv_virtual_namebox) candidate_details",
        evidence="已收束: MV 虚拟名字框候选导出消费 Rust candidate_details。",
    ),
    "validate-mv-virtual-namebox-rules": _candidate_budget(
        "validate-mv-virtual-namebox-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(mv_virtual_namebox) rule_summaries/hit_details",
        evidence="已收束: MV 虚拟名字框规则校验报告消费 Rust rule_summaries 与 hit_details。",
    ),
    "import-mv-virtual-namebox-rules": _candidate_budget(
        "import-mv-virtual-namebox-rules",
        plugin_source_ast_scan_count=0,
        authoritative_source="Rust scan_rule_candidates(mv_virtual_namebox) rule_summaries/hit_details",
        evidence="已收束: MV 虚拟名字框规则导入前覆盖检查消费 Rust rule_summaries 与 hit_details。",
    ),
    "validate-source-residual-rules": _source_residual_rule_budget(
        "validate-source-residual-rules",
        evidence="已收束: 规则校验只按 position_rules 路径读取 text_facts 当前事实和对应译文；结构规则只做输入与 Rust regex 契约校验。",
    ),
    "import-source-residual-rules": _source_residual_rule_budget(
        "import-source-residual-rules",
        evidence="已收束: 规则导入复用索引精确路径校验，随后只执行源文残留规则数据库事务。",
    ),
    "audit-active-runtime": ScanBudget(
        command_name="audit-active-runtime",
        category="P1-C",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="active runtime audit cache / Rust plugin source scan",
        current_path_requirement="真实 active runtime I/O 成本保留，不归入 scope/index 重复扫描",
        evidence="当前运行审计加载 active runtime GameData 并消费 Rust runtime scan cache，不构建文本范围。",
    ),
    "diagnose-active-runtime": ScanBudget(
        command_name="diagnose-active-runtime",
        category="P1-C",
        game_data_load_count=2,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="active runtime audit cache / Rust plugin source scan",
        current_path_requirement="保留 active runtime 和 translation source 真实 I/O；source hash 未变时不再扫描翻译源 AST",
        evidence="诊断消费当前运行审计结果和写回映射；只在 source_file_hash 变化时批量扫描涉及的翻译源插件源码。",
    ),
    "verify-feedback-text": ScanBudget(
        command_name="verify-feedback-text",
        category="P1-C",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="SQLite text_index_items / Rust plugin source runtime scan",
        current_path_requirement="反馈定位使用当前索引和 Rust runtime scan",
        evidence="反馈文本残留定位读取 active runtime；缺口分类消费 SQLite text_index_items，不构建完整文本范围。",
    ),
    "export-terminology": ScanBudget(
        command_name="export-terminology",
        category="P1-C",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="terminology repository / terminology context",
        current_path_requirement="静态审计术语上下文成本，不新增独立 scope 抽象",
        evidence="术语导出不需要构建当前可写范围。",
    ),
    "import-terminology": ScanBudget(
        command_name="import-terminology",
        category="P1-C",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="terminology repository / current terminology registry shape",
        current_path_requirement="保留当前 GameData 形状校验；导入不生成导出上下文",
        evidence="术语导入读取输入文件和当前字段表形状，使用 extract_registry 校验，不构建 speaker/database context 输出。",
    ),
    "probe-source-language": ScanBudget(
        command_name="probe-source-language",
        category="P1-C",
        game_data_load_count=0,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="raw JSON visible-text sampler",
        current_path_requirement="静态审计源语言探测真实 I/O 成本，不归入 GameData/scope/index",
        evidence="源语言探测读取标准 data JSON 并采样玩家可见文本，不构建 GameData 或文本范围。",
    ),
    "export-plugins-json": ScanBudget(
        command_name="export-plugins-json",
        category="P1-C",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        authoritative_source="plugins.js parser / plugin config reader",
        current_path_requirement="静态审计插件配置导出成本",
        evidence="插件 JSON 导出只读取插件配置，不构建完整文本范围。",
    ),
}


def scan_budgets_by_command() -> dict[str, ScanBudget]:
    """返回公开命令到扫描预算的只读副本。"""
    return dict(_SCAN_BUDGETS)


def scan_budget_for_command(command_name: str) -> ScanBudget:
    """读取单个公开命令的扫描预算。"""
    try:
        return _SCAN_BUDGETS[command_name]
    except KeyError as error:
        raise KeyError(f"未知扫描预算命令: {command_name}") from error


def required_scan_budget_commands_by_category() -> dict[ScanBudgetCategory, frozenset[str]]:
    """返回本轮计划要求纳入扫描预算的命令分组。"""
    return {
        "P0": P0_COMMANDS,
        "P1-A": P1_A_COMMANDS,
        "P1-B": P1_B_COMMANDS,
        "P1-C": P1_C_COMMANDS,
    }


__all__ = [
    "P0_COMMANDS",
    "P1_A_COMMANDS",
    "P1_B_COMMANDS",
    "P1_B_PENDING_FACT_SOURCE_COMMANDS",
    "P1_C_COMMANDS",
    "ScanBudget",
    "ScanBudgetCategory",
    "required_scan_budget_commands_by_category",
    "scan_budget_for_command",
    "scan_budgets_by_command",
]
