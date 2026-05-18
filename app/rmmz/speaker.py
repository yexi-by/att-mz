"""MV 虚拟名字框解析与重建工具。"""

import re
from dataclasses import dataclass
from typing import Literal

from app.rmmz.schema import GameData


type MvSpeakerStyle = Literal[
    "standalone_colon",
    "actor_control_colon",
    "yep_name_box",
    "dark_plasma_quote",
    "dark_plasma_paren",
]

ACTOR_NAME_PREFIX_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<control>\\[Nn]\[(?P<actor_id>\d+)\])\s*[:：]\s*(?P<body>.*)$",
)
YEP_NAME_BOX_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<command>\\(?:n(?:c|r)?|r))<(?P<speaker>[^>\r\n]{1,80})>(?P<body>.*)$",
)
DARK_PLASMA_AUTO_NAME_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<speaker>[^\\「（:：\r\n]{1,40})\s*(?P<connector>[:：]?「|（)(?P<body>.*)$"
)
DARK_PLASMA_SPEAKER_STOP_PATTERN: re.Pattern[str] = re.compile(r"[。！？!?、，,；;…—]")
STANDALONE_SPEAKER_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<speaker>[^\\「『【\[\]()（）:：\r\n]{1,40})\s*[:：]\s*$"
)


@dataclass(frozen=True, slots=True)
class MvVirtualSpeaker:
    """MV 文本首行抽象出的虚拟名字框。"""

    speaker: str
    style: MvSpeakerStyle
    body_text: str
    name_command: str = ""
    connector: str = ""

    def render(self, *, translated_speaker: str, translated_body: str | None = None) -> str:
        """按原协议样式重建写回到 `401` 的文本。"""
        body_text = "" if translated_body is None else translated_body
        if self.style in {"standalone_colon", "actor_control_colon"}:
            if body_text:
                return f"{translated_speaker}：{body_text}"
            return f"{translated_speaker}："
        if self.style == "yep_name_box":
            return f"{self.name_command}<{translated_speaker}>{body_text}"
        return f"{translated_speaker}{self.connector}{body_text}"


def parse_mv_virtual_speaker_line(
    *,
    text: str,
    game_data: GameData,
) -> MvVirtualSpeaker | None:
    """从 MV `401` 首条非空正文中解析可写回的虚拟名字框。"""
    normalized_text = text.strip()
    if not normalized_text:
        return None

    actor_match = ACTOR_NAME_PREFIX_PATTERN.match(normalized_text)
    if actor_match is not None:
        actor_id = int(actor_match.group("actor_id"))
        actor_name = _actor_name_by_id(game_data=game_data, actor_id=actor_id)
        if actor_name is None:
            return None
        return MvVirtualSpeaker(
            speaker=actor_name,
            style="actor_control_colon",
            body_text=_clean_body_text(actor_match.group("body")),
        )

    yep_match = YEP_NAME_BOX_PATTERN.match(normalized_text)
    if yep_match is not None:
        speaker = _clean_speaker_text(yep_match.group("speaker"))
        if speaker:
            return MvVirtualSpeaker(
                speaker=speaker,
                style="yep_name_box",
                body_text=_clean_body_text(yep_match.group("body")),
                name_command=yep_match.group("command"),
            )

    dark_plasma_match = DARK_PLASMA_AUTO_NAME_PATTERN.match(normalized_text)
    if dark_plasma_match is not None:
        speaker = _clean_speaker_text(dark_plasma_match.group("speaker"))
        if _is_plausible_dark_plasma_speaker(speaker):
            connector = dark_plasma_match.group("connector")
            style: MvSpeakerStyle = "dark_plasma_paren" if connector == "（" else "dark_plasma_quote"
            return MvVirtualSpeaker(
                speaker=speaker,
                style=style,
                body_text=_clean_body_text(dark_plasma_match.group("body")),
                connector=connector,
            )

    standalone_match = STANDALONE_SPEAKER_LINE_PATTERN.match(normalized_text)
    if standalone_match is not None:
        speaker = _clean_speaker_text(standalone_match.group("speaker"))
        if speaker:
            return MvVirtualSpeaker(
                speaker=speaker,
                style="standalone_colon",
                body_text="",
            )

    return None


def _actor_name_by_id(*, game_data: GameData, actor_id: int) -> str | None:
    """按数据库角色 ID 读取角色名。"""
    for actor in game_data.base_data.get("Actors.json", []):
        if actor is None or actor.id != actor_id:
            continue
        actor_name = actor.name.strip()
        if actor_name:
            return actor_name
    return None


def _clean_speaker_text(text: str) -> str:
    """清理说话人文本外侧空白。"""
    return text.strip()


def _clean_body_text(text: str) -> str:
    """清理虚拟名字框剥离后的正文外侧空白。"""
    return text.strip()


def _is_plausible_dark_plasma_speaker(text: str) -> bool:
    """判断 DarkPlasma 行首候选是否更像名字而不是普通叙述句。"""
    speaker = text.strip()
    if not speaker:
        return False
    if all(character in "?？!！" for character in speaker):
        return True
    return DARK_PLASMA_SPEAKER_STOP_PATTERN.search(speaker) is None


__all__: list[str] = [
    "MvSpeakerStyle",
    "MvVirtualSpeaker",
    "parse_mv_virtual_speaker_line",
]
