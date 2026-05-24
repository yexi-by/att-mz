"""游戏文件读取视图定义。"""

from enum import StrEnum


class GameFileView(StrEnum):
    """区分翻译来源文件和当前游戏实际运行文件。"""

    TRANSLATION_SOURCE = "translation-source"
    ACTIVE_RUNTIME = "active-runtime"


def parse_game_file_view(value: str) -> GameFileView:
    """把 CLI 字符串解析为游戏文件读取视图。"""
    try:
        return GameFileView(value)
    except ValueError as error:
        supported_values = "、".join(item.value for item in GameFileView)
        raise ValueError(f"未知游戏文件读取视图: {value}，可选值: {supported_values}") from error


__all__: list[str] = [
    "GameFileView",
    "parse_game_file_view",
]
