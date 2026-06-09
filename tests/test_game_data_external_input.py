"""RPG Maker 游戏原文外部输入规范化测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.rmmz.game_data import BaseItem, EventCommand
from app.rmmz.loader import collect_missing_map_files_from_map_infos, read_game_title_from_system


def test_base_item_normalizes_string_id_and_integer_text() -> None:
    """标准 data 条目的 id 和文本字段在入口规范化。"""
    item = BaseItem.model_validate(
        {
            "id": "1",
            "name": 123,
            "note": "",
            "description": "",
            "iconIndex": 64,
        }
    )

    assert item.id == 1
    assert item.name == "123"


def test_base_item_rejects_boolean_id_and_boolean_text() -> None:
    """标准 data 条目的字符串/整数字段不能用布尔值表达。"""
    with pytest.raises(ValidationError):
        _ = BaseItem.model_validate(
            {
                "id": True,
                "name": "名前",
                "note": "",
                "description": "",
            }
        )

    with pytest.raises(ValidationError):
        _ = BaseItem.model_validate(
            {
                "id": 1,
                "name": False,
                "note": "",
                "description": "",
            }
        )


def test_event_command_normalizes_string_code() -> None:
    """事件指令 code 可用整数字符串表达。"""
    command = EventCommand.model_validate({"code": "401", "parameters": ["こんにちは"]})

    assert command.code == 401


def test_map_infos_accepts_integer_string_id(tmp_path: Path) -> None:
    """MapInfos.json 的 id 可用整数字符串表达。"""
    data_dir = tmp_path
    _ = (data_dir / "MapInfos.json").write_text(
        json.dumps([None, {"id": "1", "name": "Map"}], ensure_ascii=False),
        encoding="utf-8",
    )
    _ = (data_dir / "Map001.json").write_text("{}", encoding="utf-8")

    assert collect_missing_map_files_from_map_infos(data_dir=data_dir) == []


def test_map_infos_rejects_boolean_id(tmp_path: Path) -> None:
    """MapInfos.json 的 id 不能用布尔值表达。"""
    data_dir = tmp_path
    _ = (data_dir / "MapInfos.json").write_text(
        json.dumps([None, {"id": True, "name": "Map"}], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(TypeError) as error_info:
        _ = collect_missing_map_files_from_map_infos(data_dir=data_dir)

    assert "MapInfos.json[1].id" in str(error_info.value)
    assert "bool" in str(error_info.value)


def test_system_title_reader_normalizes_integer_title(tmp_path: Path) -> None:
    """System.json 标题读取入口使用游戏原文文本字段口径。"""
    system_path = tmp_path / "System.json"
    _ = system_path.write_text(json.dumps({"gameTitle": 123}, ensure_ascii=False), encoding="utf-8")

    assert read_game_title_from_system(system_path) == "123"


def test_system_title_reader_rejects_boolean_title(tmp_path: Path) -> None:
    """System.json 标题读取入口拒绝布尔标题。"""
    system_path = tmp_path / "System.json"
    _ = system_path.write_text(json.dumps({"gameTitle": True}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(TypeError) as error_info:
        _ = read_game_title_from_system(system_path)

    assert "gameTitle" in str(error_info.value)
    assert "bool" in str(error_info.value)
