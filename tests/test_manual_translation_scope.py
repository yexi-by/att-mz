"""手动译文导入当前范围校验测试。"""

import json
from pathlib import Path

import pytest

from app.agent_toolkit import AgentToolkitService
from app.persistence import GameRegistry
from app.rmmz.schema import TranslationErrorItem

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


@pytest.mark.asyncio
async def test_manual_import_rejects_latest_quality_error_outside_current_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """最新质量错误只能提供候选路径，不能让过期路径绕过当前 TextScope。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    stale_path = "Map999.json/ghost"
    async with await registry.open_game("テストゲーム") as session:
        run_record = await session.start_translation_run(
            total_extracted=1,
            pending_count=1,
            deduplicated_count=1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id="fact-stale-quality-error",
                    location_path=stale_path,
                    item_type="short_text",
                    role=None,
                    original_lines=["消えた原文"],
                    translation_lines=["消えた原文"],
                    error_type="源文残留",
                    error_detail=["过期质量错误"],
                    model_response="",
                )
            ],
        )
    input_path = tmp_path / "manual.json"
    _ = input_path.write_text(
        json.dumps(
            {
                stale_path: {
                    "item_type": "short_text",
                    "role": "",
                    "original_lines": ["消えた原文"],
                    "translation_lines": ["已修复译文"],
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).import_manual_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "error"
    assert report.summary["scope_mode"] == "text_index"
    assert "manual_translation_location" in {error.code for error in report.errors}
    async with await registry.open_game("テストゲーム") as session:
        translated_paths = await session.read_translation_location_paths()
    assert stale_path not in translated_paths
