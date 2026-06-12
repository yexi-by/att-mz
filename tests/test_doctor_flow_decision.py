"""doctor 统一流程裁决测试。"""

from pathlib import Path

import pytest

from app.agent_toolkit import AgentToolkitService
from app.persistence import GameRegistry

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


@pytest.mark.asyncio
async def test_doctor_game_reports_flow_decision_and_runs_write_probe(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """doctor --game 必须给出统一流程裁决，并默认执行写回级只读检查。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).doctor(game_title="テストゲーム", check_llm=False)

    assert "flow_decision" in report.summary
    assert "flow_stage" in report.summary
    assert "flow_next_command" in report.summary
    assert report.summary["flow_write_back_probe_executed"] is True
    assert report.summary["flow_write_back_probe_mode"] == "rust_write_gate"
    assert "flow_decision" in report.details
    flow_reports = report.details["flow_reports"]
    assert isinstance(flow_reports, dict)
    quality_report = flow_reports["quality"]
    assert isinstance(quality_report, dict)
    quality_summary = quality_report["summary"]
    assert isinstance(quality_summary, dict)
    assert quality_summary["write_back_probe_executed"] is True
