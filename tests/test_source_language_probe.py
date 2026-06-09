"""源语言探测测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.source_language_probe import probe_source_language
from tests.conftest import write_complete_standard_data_files, write_json


@pytest.mark.asyncio
async def test_source_language_probe_recommends_japanese_visible_text(
    minimal_game_dir: Path,
) -> None:
    """源语言探测只按玩家可见文本给日文游戏高置信度建议。"""
    result = await probe_source_language(minimal_game_dir)

    assert result.recommendation == "ja"
    assert result.confidence == "high"
    assert result.japanese_text_count > result.english_text_count
    assert result.samples["ja"]


@pytest.mark.asyncio
async def test_source_language_probe_recommends_english_visible_text(
    minimal_english_game_dir: Path,
) -> None:
    """源语言探测只按玩家可见文本给英文游戏高置信度建议。"""
    result = await probe_source_language(minimal_english_game_dir)

    assert result.recommendation == "en"
    assert result.confidence == "high"
    assert result.english_text_count > result.japanese_text_count
    assert result.samples["en"]


@pytest.mark.asyncio
async def test_source_language_probe_normalizes_game_data_external_types(tmp_path: Path) -> None:
    """源语言探测按游戏原文入口口径读取可见文本和事件指令 code。"""
    game_root = tmp_path / "probe-game"
    data_dir = game_root / "data"
    js_dir = game_root / "js"
    data_dir.mkdir(parents=True)
    js_dir.mkdir(parents=True)
    write_json(game_root / "package.json", {"window": {"title": ""}})
    write_json(
        data_dir / "System.json",
        {
            "gameTitle": 123,
            "terms": {
                "basic": ["", ""],
                "commands": ["", ""],
                "params": [456],
                "messages": {"alwaysDash": 789},
            },
            "elements": ["", ""],
            "skillTypes": ["", ""],
            "weaponTypes": ["", ""],
            "armorTypes": ["", ""],
            "equipTypes": ["", ""],
        },
    )
    write_json(
        data_dir / "CommonEvents.json",
        [
            None,
            {
                "id": "1",
                "list": [
                    {"code": "401", "parameters": [123456]},
                    {"code": "102", "parameters": [[789012, "345678"], 0, 0, 2, 0]},
                    {"code": 0, "parameters": []},
                ],
            },
        ],
    )
    write_json(data_dir / "Troops.json", [None, {"id": 1, "pages": [{"list": [{"code": 0, "parameters": []}]}]}])
    write_json(
        data_dir / "Map001.json",
        {
            "displayName": 234567,
            "note": "",
            "events": [
                None,
                {"id": "1", "name": 345678, "note": "", "pages": [{"list": [{"code": 0, "parameters": []}]}]},
            ],
        },
    )
    write_json(data_dir / "Items.json", [None, {"id": "1", "name": 456789, "note": "", "description": 567890}])
    write_complete_standard_data_files(data_dir, map_ids=[1])
    _ = (js_dir / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    (js_dir / "plugins").mkdir()

    result = await probe_source_language(game_root)

    assert result.visible_text_count >= 8
    assert result.other_text_count >= 8
    assert result.counts_by_source_kind["system_text"] >= 3
    assert result.counts_by_source_kind["event_text"] >= 1
    assert result.counts_by_source_kind["event_choice"] >= 2
    assert result.counts_by_source_kind["map_display_name"] == 1
    assert result.counts_by_source_kind["database_text"] >= 2
