"""
RPG Maker 原始数据结构模型模块。

这里定义与 RPG Maker MV/MZ 标准 `data/*.json` 高度对应的基础模型，供加载、
提取和回写流程共享。
"""

from typing import ClassVar, cast

from pydantic import ConfigDict, Field, model_validator

from app.external_input import ExternalInputModel, ExternalInt, ExternalStr, normalize_external_int
from app.rmmz.text_rules import JsonValue


class RmmzDataModel(ExternalInputModel):
    """RPG Maker 标准 data 模型基类，只解析本工具关心的字段。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", strict=True)


class BaseItem(RmmzDataModel):
    """RPG Maker 数据库基础条目通用模型。"""

    id: ExternalInt
    name: ExternalStr
    note: ExternalStr = ""
    nickname: ExternalStr = ""
    profile: ExternalStr = ""
    description: ExternalStr = ""
    message1: ExternalStr = ""
    message2: ExternalStr = ""
    message3: ExternalStr = ""
    message4: ExternalStr = ""


class EventCommand(RmmzDataModel):
    """RPG Maker 事件指令模型。"""

    code: ExternalInt
    parameters: list[JsonValue]

    @model_validator(mode="before")
    @classmethod
    def normalize_end_command_parameters(cls, data: object) -> object:
        """为少量省略 `parameters` 的结束指令补齐空数组。"""
        if not isinstance(data, dict):
            return data
        raw_data = cast(dict[object, object], data)
        try:
            is_end_command = normalize_external_int(raw_data.get("code"), "code") == 0
        except TypeError:
            return raw_data
        if not is_end_command or "parameters" in raw_data:
            return raw_data
        normalized_data: dict[object, object] = dict(raw_data)
        normalized_data["parameters"] = []
        return normalized_data


class Page(RmmzDataModel):
    """事件页模型。"""

    commands: list[EventCommand] = Field(..., alias="list")


class Event(RmmzDataModel):
    """地图事件模型。"""

    id: ExternalInt
    name: ExternalStr
    note: ExternalStr
    pages: list[Page]


class MapData(RmmzDataModel):
    """地图数据模型，对应 `data/MapXXX.json`。"""

    displayName: ExternalStr
    note: ExternalStr
    events: list[Event | None]


class Terms(RmmzDataModel):
    """系统基础词汇模型。"""

    basic: list[ExternalStr]
    commands: list[ExternalStr | None]
    params: list[ExternalStr]
    messages: dict[ExternalStr, ExternalStr]


class System(RmmzDataModel):
    """系统全局配置模型，对应 `data/System.json`。"""

    gameTitle: ExternalStr
    terms: Terms
    elements: list[ExternalStr]
    skillTypes: list[ExternalStr]
    weaponTypes: list[ExternalStr]
    armorTypes: list[ExternalStr]
    equipTypes: list[ExternalStr]


class Troop(RmmzDataModel):
    """敌群战役模型，对应 `data/Troops.json`。"""

    id: ExternalInt
    pages: list[Page]


class CommonEvent(RmmzDataModel):
    """全局公共事件模型，对应 `data/CommonEvents.json`。"""

    id: ExternalInt
    commands: list[EventCommand] = Field(..., alias="list")


__all__: list[str] = [
    "BaseItem",
    "CommonEvent",
    "Event",
    "EventCommand",
    "MapData",
    "Page",
    "RmmzDataModel",
    "System",
    "Terms",
    "Troop",
]
