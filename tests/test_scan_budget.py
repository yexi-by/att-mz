"""阶段 7 扫描预算和中性 JSON path 协议测试。"""

from __future__ import annotations

from pathlib import Path

from app.json_path_protocol import (
    jsonpath_to_event_command_location_path,
    jsonpath_to_plugin_location_path,
)
from tests.scan_budget_contract import scan_budget_for_command, scan_budgets_by_command


def test_json_path_protocol_is_neutral_between_plugin_and_event_domains() -> None:
    """插件和事件指令共享的 JSON 路径协议不能继续挂在插件域模块下。"""
    assert jsonpath_to_plugin_location_path(
        json_path="$['parameters']['title']",
        plugin_index=3,
    ) == "plugins.js/3/title"
    assert jsonpath_to_event_command_location_path(
        json_path="$['parameters'][2]",
        command_location_path="CommonEvents.json/1/4",
    ) == "CommonEvents.json/1/4/parameters/2"

    event_sources = [
        Path("app/event_command_text/extraction.py").read_text(encoding="utf-8"),
        Path("app/event_command_text/importer.py").read_text(encoding="utf-8"),
        Path("app/text_scope/rule_hits.py").read_text(encoding="utf-8"),
    ]
    assert all("app.plugin_text.paths" not in source for source in event_sources)


def test_stage7_scan_budget_table_limits_reusable_full_scans() -> None:
    """阶段 7 预算表必须把可复用全量扫描限制在单命令 1 次以内。"""
    required_commands = {
        "prepare-agent-workspace",
        "validate-agent-workspace",
        "rebuild-text-index",
        "translate",
        "run-all",
        "quality-report",
        "quality-report --include-write-probe",
        "import-manual-translations",
        "write-back",
        "rebuild-active-runtime",
    }
    budgets = scan_budgets_by_command()

    assert required_commands <= set(budgets)
    for command_name, budget in budgets.items():
        assert budget.game_data_load_count <= 1, command_name
        assert budget.text_scope_build_count <= 1, command_name
        assert budget.candidate_scan_count <= 1, command_name
        assert budget.plugin_source_ast_scan_count <= 1, command_name
        assert budget.quality_gate_count <= 1, command_name
        assert budget.write_plan_count <= 1, command_name

    include_write_probe = scan_budget_for_command("quality-report --include-write-probe")
    assert include_write_probe.quality_gate_count == 1
    assert include_write_probe.write_plan_count == 1

    translate = scan_budget_for_command("translate")
    assert translate.game_data_load_count == 1
    assert translate.text_scope_build_count == 1
    assert translate.write_plan_count == 0
