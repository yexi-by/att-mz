"""RPG Maker 长文本布局入口服务。"""

from __future__ import annotations

from app.rmmz.text_rules import TextRules

from .split import split_overwide_lines
from .wrapping import normalize_translated_wrapping_punctuation


def align_long_text_lines(
    text: str,
    target_lines: int,
    *,
    location_path: str | None,
    text_rules: TextRules,
    original_lines: list[str] | None = None,
) -> list[str]:
    """按模型断句保留译文行，再执行行宽兜底。"""
    _ = target_lines
    lines = text_rules.normalize_translation_lines(text.splitlines())
    if original_lines is not None:
        lines = normalize_translated_wrapping_punctuation(
            original_lines=original_lines,
            translation_lines=lines,
            text_rules=text_rules,
        )

    return split_overwide_lines(
        lines=lines,
        location_path=location_path,
        text_rules=text_rules,
    )
