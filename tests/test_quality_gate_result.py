"""结构化 QualityGateResult 测试。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_toolkit import AgentToolkitService
from app.native_quality import NativeQualityDetails
from app.persistence import GameRegistry
from app.rmmz import load_game_data
from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import JsonArray, TextRules
from app.text_scope import TextScopeService
from app.utils.config_loader_utils import load_setting

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


@pytest.mark.asyncio
async def test_quality_report_write_probe_renders_structured_quality_gate_result(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include-write-probe 的 summary/details 必须来自同一结构化质量结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        game_data = await load_game_data(minimal_game_dir)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        target_item = next(item for item in scope.active_items() if item.item_type != "array")
        target_path = target_item.location_path
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type=target_item.item_type,
                    role=target_item.role,
                    original_lines=list(target_item.original_lines),
                    source_line_paths=list(target_item.source_line_paths),
                    translation_lines=["结构化质量结果测试译文"],
                )
            ]
        )

    def fake_native_quality_details(**kwargs: object) -> NativeQualityDetails:
        _ = kwargs
        return NativeQualityDetails(
            source_residual_items=[
                {"location_path": target_path, "reason": "源文残留明细"}
            ],
            text_structure_items=[],
            placeholder_risk_items=[],
            overwide_line_items=[
                {"location_path": target_path, "reason": "行宽明细"}
            ],
        )

    def fake_write_protocol_details(**kwargs: object) -> JsonArray:
        _ = kwargs
        return [{"location_path": target_path, "reason": "写回协议明细"}]

    def fake_rust_quality_gate(**kwargs: object) -> object:
        _ = kwargs
        return SimpleNamespace(
            summary=SimpleNamespace(
                data_item_count=1,
                plugin_item_count=0,
                terminology_written_count=0,
                plugin_source_runtime_map_count=0,
            ),
            timings_ms={"quality_gate": 1, "total": 2},
        )

    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.collect_agent_service_native_quality_details",
        fake_native_quality_details,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.collect_agent_service_native_write_protocol_details",
        fake_write_protocol_details,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.build_native_write_back_plan",
        fake_rust_quality_gate,
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).quality_report(game_title="テストゲーム", include_write_probe=True)

    assert report.summary["source_residual_count"] == 1
    assert report.summary["overwide_line_count"] == 1
    assert report.summary["write_back_protocol_count"] == 1
    assert report.details["source_residual_items"] == [
        {"location_path": target_path, "reason": "源文残留明细"}
    ]
    assert report.details["overwide_line_items"] == [
        {"location_path": target_path, "reason": "行宽明细"}
    ]
    assert report.details["write_back_protocol_items"] == [
        {"location_path": target_path, "reason": "写回协议明细"}
    ]
    assert {"source_residual", "overwide_line", "write_back_protocol"} <= {
        error.code for error in report.errors
    }
