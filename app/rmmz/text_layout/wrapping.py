"""RPG Maker 长文本包裹标点修复服务。"""

from __future__ import annotations

from app.rmmz.text_rules import TextRules

from .models import BoundaryChar, ProtectedSpan, WrappingSpan
from .protected import collect_protected_spans, find_containing_span

TRANSLATED_WRAPPING_LEFT_CHARS: frozenset[str] = frozenset(
    {"“", "‘", "「", "『", "《", "〈", "（", "(", "\"", "'", "＂"}
)
TRANSLATED_WRAPPING_RIGHT_CHARS: frozenset[str] = frozenset(
    {"”", "’", "」", "』", "》", "〉", "）", ")", "\"", "'", "＂"}
)
TRANSLATED_WRAPPING_QUOTE_PAIRS: tuple[tuple[str, str], ...] = (
    ("“", "”"),
    ("‘", "’"),
    ("\"", "\""),
    ("'", "'"),
    ("＂", "＂"),
    ("『", "』"),
    ("《", "》"),
    ("〈", "〉"),
)


def normalize_translated_wrapping_punctuation(
    *,
    original_lines: list[str],
    translation_lines: list[str],
    text_rules: TextRules,
) -> list[str]:
    """把源文包裹标点被模型改写的译文修回源文标点。

    外层包裹标点先按首尾边界修复；内层包裹标点只在源文对数与译文可配对
    引号对数一致时按顺序修复。无法安全一一对应时保持原样，避免误改模型
    正常新增的中文引号。
    """
    if not _has_preserved_wrapping_chars(lines=original_lines, text_rules=text_rules):
        return list(translation_lines)
    normalized_lines = _normalize_translated_outer_wrapping_punctuation(
        original_lines=original_lines,
        translation_lines=translation_lines,
        text_rules=text_rules,
    )
    return _normalize_aligned_wrapping_spans(
        original_lines=original_lines,
        translation_lines=normalized_lines,
        text_rules=text_rules,
    )


def find_opening_wrapping_pair(*, line: str, text_rules: TextRules) -> tuple[str, str] | None:
    """返回当前行开头命中的包裹标点配置。"""
    stripped_line = build_wrapping_check_line(line=line, text_rules=text_rules)
    for left, right in text_rules.setting.preserve_wrapping_punctuation_pairs:
        if stripped_line.startswith(left):
            return left, right
    return None


def closes_wrapping_pair(
    *,
    line: str,
    wrapping_pair: tuple[str, str],
    text_rules: TextRules,
) -> bool:
    """判断当前逻辑行是否结束了跨行包裹标点块。"""
    _, right = wrapping_pair
    stripped_line = build_wrapping_check_line(line=line, text_rules=text_rules)
    return stripped_line.endswith(right)


def build_wrapping_check_line(*, line: str, text_rules: TextRules) -> str:
    """去掉控制符后生成包裹标点状态判定用文本。"""
    return text_rules.strip_rm_control_sequences(line).strip()


def prepend_continuation_prefix(*, line: str, prefix: str) -> str:
    """给包裹标点续行补视觉缩进，避免重复添加已有空白。"""
    if not prefix or not line:
        return line
    if line.startswith(prefix):
        return line
    first_char = line[0]
    if first_char.isspace():
        return line
    return f"{prefix}{line}"


def _has_preserved_wrapping_chars(*, lines: list[str], text_rules: TextRules) -> bool:
    """快速判断源文是否可能需要包裹标点修复。"""
    wrapping_chars = {
        char
        for pair in text_rules.setting.preserve_wrapping_punctuation_pairs
        for char in pair
    }
    if not wrapping_chars:
        return False
    return any(char in line for line in lines for char in wrapping_chars)


def _normalize_translated_outer_wrapping_punctuation(
    *,
    original_lines: list[str],
    translation_lines: list[str],
    text_rules: TextRules,
) -> list[str]:
    """按首尾边界修复外层包裹标点。"""
    source_pair = _find_source_outer_wrapping_pair(original_lines=original_lines, text_rules=text_rules)
    if source_pair is None:
        return list(translation_lines)

    normalized_lines = list(translation_lines)
    source_left, source_right = source_pair
    first_boundary = _find_first_visible_boundary(lines=normalized_lines, text_rules=text_rules)
    last_boundary = _find_last_visible_boundary(lines=normalized_lines, text_rules=text_rules)
    if first_boundary is None or last_boundary is None:
        return normalized_lines

    if first_boundary.char != source_left and first_boundary.char in TRANSLATED_WRAPPING_LEFT_CHARS:
        normalized_lines[first_boundary.line_index] = _replace_char_at(
            text=normalized_lines[first_boundary.line_index],
            index=first_boundary.char_index,
            char=source_left,
        )
    if last_boundary.char != source_right and last_boundary.char in TRANSLATED_WRAPPING_RIGHT_CHARS:
        normalized_lines[last_boundary.line_index] = _replace_char_at(
            text=normalized_lines[last_boundary.line_index],
            index=last_boundary.char_index,
            char=source_right,
        )
    return normalized_lines


def _normalize_aligned_wrapping_spans(
    *,
    original_lines: list[str],
    translation_lines: list[str],
    text_rules: TextRules,
) -> list[str]:
    """在可安全一一对应时修复文本内部被替换的包裹标点。"""
    source_pairs = tuple(text_rules.setting.preserve_wrapping_punctuation_pairs)
    source_spans = _collect_wrapping_spans(
        lines=original_lines,
        pair_definitions=source_pairs,
        text_rules=text_rules,
    )
    if not source_spans:
        return list(translation_lines)

    translated_source_spans = _collect_wrapping_spans(
        lines=translation_lines,
        pair_definitions=source_pairs,
        text_rules=text_rules,
    )
    alternative_pairs = _build_alternative_wrapping_pairs(source_pairs)
    translated_alternative_spans = _collect_wrapping_spans(
        lines=translation_lines,
        pair_definitions=alternative_pairs,
        text_rules=text_rules,
    )
    if _has_unpaired_wrapping_chars(
        lines=translation_lines,
        pair_definitions=source_pairs,
        spans=translated_source_spans,
        text_rules=text_rules,
    ):
        return list(translation_lines)
    if _has_unpaired_wrapping_chars(
        lines=translation_lines,
        pair_definitions=alternative_pairs,
        spans=translated_alternative_spans,
        text_rules=text_rules,
    ):
        return list(translation_lines)
    translated_spans = sorted(
        [*translated_source_spans, *translated_alternative_spans],
        key=lambda span: (
            span.left.line_index,
            span.left.char_index,
            span.right.line_index,
            span.right.char_index,
        ),
    )
    if len(source_spans) != len(translated_spans):
        return list(translation_lines)

    normalized_lines = list(translation_lines)
    for source_span, translated_span in zip(source_spans, translated_spans, strict=True):
        source_left, source_right = source_span.pair
        if translated_span.left.char != source_left:
            normalized_lines[translated_span.left.line_index] = _replace_char_at(
                text=normalized_lines[translated_span.left.line_index],
                index=translated_span.left.char_index,
                char=source_left,
            )
        if translated_span.right.char != source_right:
            normalized_lines[translated_span.right.line_index] = _replace_char_at(
                text=normalized_lines[translated_span.right.line_index],
                index=translated_span.right.char_index,
                char=source_right,
            )
    return normalized_lines


def _build_alternative_wrapping_pairs(source_pairs: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """生成可被自动修回源文包裹标点的译文替代引号对。"""
    source_pair_set = set(source_pairs)
    return tuple(pair for pair in TRANSLATED_WRAPPING_QUOTE_PAIRS if pair not in source_pair_set)


def _has_unpaired_wrapping_chars(
    *,
    lines: list[str],
    pair_definitions: tuple[tuple[str, str], ...],
    spans: list[WrappingSpan],
    text_rules: TextRules,
) -> bool:
    """判断文本中是否存在未被配对算法消费的包裹标点字符。"""
    wrapping_chars = {char for pair in pair_definitions for char in pair}
    if not wrapping_chars:
        return False
    paired_positions = {
        (span.left.line_index, span.left.char_index)
        for span in spans
    } | {
        (span.right.line_index, span.right.char_index)
        for span in spans
    }
    for boundary in _collect_visible_chars(lines=lines, text_rules=text_rules):
        if boundary.char not in wrapping_chars:
            continue
        if (boundary.line_index, boundary.char_index) not in paired_positions:
            return True
    return False


def _collect_wrapping_spans(
    *,
    lines: list[str],
    pair_definitions: tuple[tuple[str, str], ...],
    text_rules: TextRules,
) -> list[WrappingSpan]:
    """按可见字符顺序收集已配对的包裹标点。"""
    visible_chars = _collect_visible_chars(lines=lines, text_rules=text_rules)
    different_char_pairs = tuple(pair for pair in pair_definitions if pair[0] != pair[1])
    same_char_pairs = tuple(pair for pair in pair_definitions if pair[0] == pair[1])
    spans = _collect_different_char_wrapping_spans(
        visible_chars=visible_chars,
        pair_definitions=different_char_pairs,
    )
    spans.extend(
        _collect_same_char_wrapping_spans(
            visible_chars=visible_chars,
            pair_definitions=same_char_pairs,
        )
    )
    return sorted(
        spans,
        key=lambda span: (
            span.left.line_index,
            span.left.char_index,
            span.right.line_index,
            span.right.char_index,
        ),
    )


def _collect_different_char_wrapping_spans(
    *,
    visible_chars: list[BoundaryChar],
    pair_definitions: tuple[tuple[str, str], ...],
) -> list[WrappingSpan]:
    """收集左右字符不同的包裹标点对。"""
    left_to_pair = {left: (left, right) for left, right in pair_definitions}
    right_chars = {right for _left, right in pair_definitions}
    spans: list[WrappingSpan] = []
    stack: list[tuple[BoundaryChar, tuple[str, str]]] = []
    for boundary in visible_chars:
        pair = left_to_pair.get(boundary.char)
        if pair is not None:
            stack.append((boundary, pair))
            continue
        if boundary.char not in right_chars:
            continue
        if not stack:
            continue
        left_boundary, expected_pair = stack[-1]
        if expected_pair[1] != boundary.char:
            continue
        _ = stack.pop()
        spans.append(WrappingSpan(left=left_boundary, right=boundary, pair=expected_pair))
    return spans


def _collect_same_char_wrapping_spans(
    *,
    visible_chars: list[BoundaryChar],
    pair_definitions: tuple[tuple[str, str], ...],
) -> list[WrappingSpan]:
    """收集左右字符相同的直引号包裹对。"""
    quote_chars = {left for left, _right in pair_definitions}
    open_boundaries: dict[str, BoundaryChar] = {}
    spans: list[WrappingSpan] = []
    for boundary in visible_chars:
        if boundary.char not in quote_chars:
            continue
        open_boundary = open_boundaries.get(boundary.char)
        if open_boundary is None:
            open_boundaries[boundary.char] = boundary
            continue
        spans.append(WrappingSpan(left=open_boundary, right=boundary, pair=(boundary.char, boundary.char)))
        del open_boundaries[boundary.char]
    return spans


def _collect_visible_chars(
    *,
    lines: list[str],
    text_rules: TextRules,
) -> list[BoundaryChar]:
    """收集多行文本中不属于控制符且非空白的可见字符位置。"""
    visible_chars: list[BoundaryChar] = []
    for line_index, line in enumerate(lines):
        protected_spans = collect_protected_spans(text=line, text_rules=text_rules)
        index = 0
        while index < len(line):
            containing_span = find_containing_span(index=index, protected_spans=protected_spans)
            if containing_span is not None:
                index = containing_span.end_index
                continue
            char = line[index]
            if not char.isspace():
                visible_chars.append(
                    BoundaryChar(
                        line_index=line_index,
                        char_index=index,
                        char=char,
                    )
                )
            index += 1
    return visible_chars


def _find_source_outer_wrapping_pair(
    *,
    original_lines: list[str],
    text_rules: TextRules,
) -> tuple[str, str] | None:
    """按源文首尾可见字符判断是否存在需要保留的外层包裹标点。"""
    first_boundary = _find_first_visible_boundary(lines=original_lines, text_rules=text_rules)
    last_boundary = _find_last_visible_boundary(lines=original_lines, text_rules=text_rules)
    if first_boundary is None or last_boundary is None:
        return None
    for left, right in text_rules.setting.preserve_wrapping_punctuation_pairs:
        if first_boundary.char == left and last_boundary.char == right:
            return left, right
    return None


def _find_first_visible_boundary(
    *,
    lines: list[str],
    text_rules: TextRules,
) -> BoundaryChar | None:
    """查找多行文本首个不属于控制符或空白的可见字符。"""
    for line_index, line in enumerate(lines):
        boundary = _find_visible_boundary_in_line(line=line, text_rules=text_rules, reverse=False)
        if boundary is None:
            continue
        return BoundaryChar(
            line_index=line_index,
            char_index=boundary.char_index,
            char=boundary.char,
        )
    return None


def _find_last_visible_boundary(
    *,
    lines: list[str],
    text_rules: TextRules,
) -> BoundaryChar | None:
    """查找多行文本末个不属于控制符或空白的可见字符。"""
    for reverse_line_index, line in enumerate(reversed(lines)):
        boundary = _find_visible_boundary_in_line(line=line, text_rules=text_rules, reverse=True)
        if boundary is None:
            continue
        return BoundaryChar(
            line_index=len(lines) - reverse_line_index - 1,
            char_index=boundary.char_index,
            char=boundary.char,
        )
    return None


def _find_visible_boundary_in_line(
    *,
    line: str,
    text_rules: TextRules,
    reverse: bool,
) -> BoundaryChar | None:
    """在单行内查找首个或末个可见边界字符。"""
    protected_spans = collect_protected_spans(text=line, text_rules=text_rules)
    if reverse:
        return _find_visible_boundary_from_right(line=line, protected_spans=protected_spans)
    return _find_visible_boundary_from_left(line=line, protected_spans=protected_spans)


def _find_visible_boundary_from_left(*, line: str, protected_spans: list[ProtectedSpan]) -> BoundaryChar | None:
    """从左侧查找不在受保护片段中的可见字符。"""
    index = 0
    while index < len(line):
        containing_span = find_containing_span(index=index, protected_spans=protected_spans)
        if containing_span is not None:
            index = containing_span.end_index
            continue
        char = line[index]
        if char.isspace():
            index += 1
            continue
        return BoundaryChar(line_index=0, char_index=index, char=char)
    return None


def _find_visible_boundary_from_right(*, line: str, protected_spans: list[ProtectedSpan]) -> BoundaryChar | None:
    """从右侧查找不在受保护片段中的可见字符。"""
    index = len(line) - 1
    while index >= 0:
        containing_span = find_containing_span(index=index, protected_spans=protected_spans)
        if containing_span is not None:
            index = containing_span.start_index - 1
            continue
        char = line[index]
        if char.isspace():
            index -= 1
            continue
        return BoundaryChar(line_index=0, char_index=index, char=char)
    return None


def _replace_char_at(*, text: str, index: int, char: str) -> str:
    """替换文本指定下标处的单个字符。"""
    return f"{text[:index]}{char}{text[index + 1:]}"
