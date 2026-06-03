"""阶段 7 扫描预算测试契约。

只供测试验证生产命令不重复全量扫描的设计边界。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScanBudget:
    """单个命令内重型扫描和计划构建的允许次数。"""

    command_name: str
    game_data_load_count: int
    text_scope_build_count: int
    candidate_scan_count: int
    plugin_source_ast_scan_count: int
    quality_gate_count: int
    write_plan_count: int
    evidence: str


_SCAN_BUDGETS: dict[str, ScanBudget] = {
    "prepare-agent-workspace": ScanBudget(
        command_name="prepare-agent-workspace",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        evidence="工作区准备只生成本轮 manifest 和规则候选，不执行写回级质量 gate。",
    ),
    "validate-agent-workspace": ScanBudget(
        command_name="validate-agent-workspace",
        game_data_load_count=1,
        text_scope_build_count=0,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        evidence="工作区校验消费 manifest，并在同一轮内复用规则候选扫描结果。",
    ),
    "rebuild-text-index": ScanBudget(
        command_name="rebuild-text-index",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        evidence="TextScopeSnapshot 是索引重建的唯一当前范围事实。",
    ),
    "translate": ScanBudget(
        command_name="translate",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=0,
        write_plan_count=0,
        evidence="正文翻译前置 gate 与批次准备消费同一 TextScope 或 warm index。",
    ),
    "run-all": ScanBudget(
        command_name="run-all",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=1,
        write_plan_count=1,
        evidence="run-all 的翻译限制和写回阶段应复用同一命令内已建立的当前范围事实。",
    ),
    "quality-report": ScanBudget(
        command_name="quality-report",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=1,
        write_plan_count=0,
        evidence="普通质量报告从当前 TextScope 生成一个 QualityGateResult。",
    ),
    "quality-report --include-write-probe": ScanBudget(
        command_name="quality-report --include-write-probe",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=1,
        write_plan_count=1,
        evidence="写回预检报告允许一次 Rust write plan，用同一结果渲染报告和 gate。",
    ),
    "import-manual-translations": ScanBudget(
        command_name="import-manual-translations",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=0,
        plugin_source_ast_scan_count=0,
        quality_gate_count=0,
        write_plan_count=0,
        evidence="手动导入先确认路径属于当前 TextScope 或 warm index，不复扫质量 gate。",
    ),
    "write-back": ScanBudget(
        command_name="write-back",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=1,
        write_plan_count=1,
        evidence="写回 gate、字体副作用、插件源码映射和文件计划统一进入 Rust WritePlan。",
    ),
    "rebuild-active-runtime": ScanBudget(
        command_name="rebuild-active-runtime",
        game_data_load_count=1,
        text_scope_build_count=1,
        candidate_scan_count=1,
        plugin_source_ast_scan_count=1,
        quality_gate_count=1,
        write_plan_count=1,
        evidence="重建当前运行文件和 write-back 共用 Rust WritePlan 边界。",
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


__all__ = [
    "ScanBudget",
    "scan_budget_for_command",
    "scan_budgets_by_command",
]
