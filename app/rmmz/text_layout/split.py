"""RPG Maker 长文本行宽兜底切分服务。"""

from __future__ import annotations

from app.observability import logger
from app.rmmz.control_codes import LITERAL_LINE_BREAK_MARKER, LITERAL_LINE_BREAK_PLACEHOLDER
from app.rmmz.text_rules import TextRules

from .models import ProtectedSpan
from .protected import collect_protected_spans, is_inside_protected_span, move_split_position_outside_protected_span
from .width import count_line_width_chars
from .wrapping import closes_wrapping_pair, find_opening_wrapping_pair, prepend_continuation_prefix

WRAPPING_CONTINUATION_INDENT = "　"


def split_overwide_lines(
    *,
    lines: list[str],
    location_path: str | None,
    text_rules: TextRules,
) -> list[str]:
    """按配置宽度切开过长非空行，并整理跨行包裹标点的续行缩进。"""
    split_lines: list[str] = []
    active_wrapping_pair: tuple[str, str] | None = None
    for line in lines:
        if not line:
            split_lines.append(line)
            continue

        current_wrapping_pair = active_wrapping_pair
        opening_pair = find_opening_wrapping_pair(line=line, text_rules=text_rules)
        if current_wrapping_pair is None:
            current_wrapping_pair = opening_pair

        first_line_prefix = WRAPPING_CONTINUATION_INDENT if active_wrapping_pair is not None else ""
        wrapped_tail_prefix = WRAPPING_CONTINUATION_INDENT if current_wrapping_pair is not None else ""
        split_lines.extend(
            _split_single_overwide_line(
                line=line,
                location_path=location_path,
                text_rules=text_rules,
                first_line_prefix=first_line_prefix,
                wrapped_tail_prefix=wrapped_tail_prefix,
            )
        )

        if current_wrapping_pair is None:
            active_wrapping_pair = None
            continue
        if closes_wrapping_pair(
            line=line,
            wrapping_pair=current_wrapping_pair,
            text_rules=text_rules,
        ):
            active_wrapping_pair = None
        else:
            active_wrapping_pair = current_wrapping_pair
    return split_lines


def split_overwide_single_text_value_if_needed(
    *,
    original_lines: list[str],
    translation_text: str,
    location_path: str | None,
    text_rules: TextRules,
) -> str:
    """对承载多行显示内容的单值文本执行行宽兜底。

    Note 标签、插件参数等来源在数据库里可能只能作为一个字符串写回，但字符串
    内部的换行会被游戏窗口当作多行显示。只要源文或译文已经带有换行，就按
    显示行拆开执行与 long_text 相同的宽度保护，再重新拼回单个字符串。
    """
    if _has_literal_line_break_marker(original_lines):
        line_break_token = (
            LITERAL_LINE_BREAK_PLACEHOLDER
            if LITERAL_LINE_BREAK_PLACEHOLDER in translation_text
            else LITERAL_LINE_BREAK_MARKER
        )
        stripped_translation_text = translation_text.strip()
        normalized_text = stripped_translation_text.replace(LITERAL_LINE_BREAK_PLACEHOLDER, line_break_token)
        normalized_text = normalized_text.replace(LITERAL_LINE_BREAK_MARKER, line_break_token)
        normalized_text = normalized_text.replace("\n", line_break_token)
        return line_break_token.join(
            split_overwide_lines(
                lines=text_rules.normalize_translation_lines(normalized_text.split(line_break_token)),
                location_path=location_path,
                text_rules=text_rules,
            )
        )
    stripped_translation_text = translation_text.strip()
    if "\n" not in stripped_translation_text and not _has_embedded_line_break(original_lines):
        return stripped_translation_text
    return "\n".join(
        split_overwide_lines(
            lines=text_rules.normalize_translation_lines(stripped_translation_text.split("\n")),
            location_path=location_path,
            text_rules=text_rules,
        )
    )


def _has_literal_line_break_marker(lines: list[str]) -> bool:
    """判断源文是否用字面量反斜杠 n 表达游戏内换行。"""
    return any(LITERAL_LINE_BREAK_MARKER in line for line in lines)


def _split_single_overwide_line(
    *,
    line: str,
    location_path: str | None,
    text_rules: TextRules,
    first_line_prefix: str = "",
    wrapped_tail_prefix: str = "",
) -> list[str]:
    """切开单个超宽文本行。"""
    line_width_limit = text_rules.setting.long_text_line_width_limit
    result: list[str] = []
    pending_line = prepend_continuation_prefix(line=line, prefix=first_line_prefix)
    while count_line_width_chars(pending_line, text_rules) > line_width_limit:
        split_position = _find_preferred_split_position(pending_line, text_rules)
        if split_position is None:
            split_position = _find_hard_split_position(pending_line, text_rules)

        if split_position is None or split_position <= 0 or split_position >= len(pending_line):
            _log_align_warning(
                location_path=location_path,
                line=pending_line,
                reason="无法找到安全切分点，保留当前行",
                text_rules=text_rules,
            )
            break

        head = pending_line[:split_position].rstrip()
        tail = pending_line[split_position:].lstrip()
        if not head or not tail:
            _log_align_warning(
                location_path=location_path,
                line=pending_line,
                reason="切分后出现空片段，保留当前行",
                text_rules=text_rules,
            )
            break

        result.append(head)
        pending_line = prepend_continuation_prefix(line=tail, prefix=wrapped_tail_prefix)

    result.append(pending_line)
    return result


def _has_embedded_line_break(lines: list[str]) -> bool:
    """判断文本行列表中是否存在作为字段内容保存的换行。"""
    return any("\n" in line for line in lines)


def _find_preferred_split_position(text: str, text_rules: TextRules) -> int | None:
    """在宽度上限附近寻找自然标点切分点。"""
    protected_spans = collect_protected_spans(text=text, text_rules=text_rules)
    width_limit = text_rules.setting.long_text_line_width_limit
    min_preferred_width = max(1, int(width_limit * 0.45))
    before_limit_positions: list[int] = []
    preferred_before_limit_positions: list[int] = []
    punctuations = set(text_rules.setting.line_split_punctuations)
    line_width_count = 0

    for index, char in enumerate(text):
        if is_inside_protected_span(index=index, protected_spans=protected_spans):
            continue
        if text_rules.is_line_width_counted_char(char):
            line_width_count += 1

        if char in punctuations and line_width_count >= min_preferred_width:
            if line_width_count <= width_limit:
                preferred_before_limit_positions.append(index + 1)
        if char in punctuations and line_width_count <= width_limit:
            before_limit_positions.append(index + 1)

        if line_width_count > width_limit:
            break

    return _select_split_position_with_readable_tail(
        text=text,
        candidates=preferred_before_limit_positions or before_limit_positions,
        text_rules=text_rules,
    )


def _select_split_position_with_readable_tail(
    *,
    text: str,
    candidates: list[int],
    text_rules: TextRules,
) -> int | None:
    """选择不会把极短语气标点甩到下一行的切分位置。"""
    if not candidates:
        return None
    min_tail_width = min(4, max(1, text_rules.setting.long_text_line_width_limit // 4))
    for position in reversed(candidates):
        tail = text[position:].lstrip()
        if count_line_width_chars(tail, text_rules) >= min_tail_width:
            return position
    return candidates[-1]


def _find_hard_split_position(text: str, text_rules: TextRules) -> int | None:
    """在没有可用标点时按计数字符上限切分。"""
    protected_spans = collect_protected_spans(text=text, text_rules=text_rules)
    line_width_count = 0
    limit = text_rules.setting.long_text_line_width_limit
    for index, char in enumerate(text):
        if is_inside_protected_span(index=index, protected_spans=protected_spans):
            continue
        if not text_rules.is_line_width_counted_char(char):
            continue
        line_width_count += 1
        if line_width_count < limit:
            continue
        split_position = move_split_position_outside_protected_span(
            position=index + 1,
            protected_spans=protected_spans,
        )
        extended_position = _extend_split_position_through_trailing_punctuation(
            text=text,
            position=split_position,
            text_rules=text_rules,
            protected_spans=protected_spans,
        )
        if extended_position >= len(text) and count_line_width_chars(text, text_rules) > limit:
            readable_position = _find_readable_hard_split_position(
                text=text,
                max_position=split_position,
                text_rules=text_rules,
                protected_spans=protected_spans,
            )
            if readable_position is not None:
                return readable_position
        return extended_position
    return None


def _find_readable_hard_split_position(
    *,
    text: str,
    max_position: int,
    text_rules: TextRules,
    protected_spans: list[ProtectedSpan],
) -> int | None:
    """尾部标点导致硬切失败时，回退到能保留可读尾段的位置。"""
    min_tail_width = min(4, max(1, text_rules.setting.long_text_line_width_limit // 4))
    punctuations = set(text_rules.setting.line_split_punctuations)
    candidates: list[int] = []
    for index, char in enumerate(text):
        position = index + 1
        if position > max_position:
            break
        if position >= len(text):
            break
        if is_inside_protected_span(index=index, protected_spans=protected_spans):
            continue
        if not text_rules.is_line_width_counted_char(char):
            continue
        tail = text[position:].lstrip()
        if not tail:
            continue
        if tail[0] in punctuations:
            continue
        if count_line_width_chars(tail, text_rules) < min_tail_width:
            continue
        candidates.append(position)
    if not candidates:
        return None
    return candidates[-1]


def _extend_split_position_through_trailing_punctuation(
    *,
    text: str,
    position: int,
    text_rules: TextRules,
    protected_spans: list[ProtectedSpan],
) -> int:
    """硬切后把紧邻标点留在上一行，避免下一行以标点开头。"""
    punctuations = set(text_rules.setting.line_split_punctuations)
    next_position = position
    while next_position < len(text):
        if is_inside_protected_span(index=next_position, protected_spans=protected_spans):
            break
        if text[next_position] not in punctuations:
            break
        next_position += 1
    return next_position


def _build_warning_preview(text: str, max_length: int = 40) -> str:
    """生成日志预览文本，避免告警刷屏。"""
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _log_align_warning(*, location_path: str | None, line: str, reason: str, text_rules: TextRules) -> None:
    """记录长文本自动补切行失败的告警日志。"""
    logger.warning(
        "长文本自动补切行告警: 路径={}，计数字符数={}，上限={}，原因={}，内容预览={}",
        location_path or "<unknown>",
        count_line_width_chars(line, text_rules),
        text_rules.setting.long_text_line_width_limit,
        reason,
        _build_warning_preview(line),
    )
