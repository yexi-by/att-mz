"""RPG Maker 文本布局中的受保护片段识别。"""

from __future__ import annotations

from app.rmmz.text_rules import TextRules

from .models import ProtectedSpan


def collect_protected_spans(text: str, text_rules: TextRules) -> list[ProtectedSpan]:
    """收集占位符和 RPG Maker 控制符范围。"""
    spans = [
        ProtectedSpan(start_index=match.start(), end_index=match.end())
        for match in text_rules.placeholder_token_pattern.finditer(text)
    ]
    spans.extend(
        ProtectedSpan(start_index=span.start_index, end_index=span.end_index)
        for span in text_rules.iter_control_sequence_spans(text)
    )
    return sorted(spans, key=lambda span: (span.start_index, span.end_index))


def is_inside_protected_span(*, index: int, protected_spans: list[ProtectedSpan]) -> bool:
    """判断字符位置是否位于受保护片段内部。"""
    return any(span.start_index <= index < span.end_index for span in protected_spans)


def find_containing_span(*, index: int, protected_spans: list[ProtectedSpan]) -> ProtectedSpan | None:
    """返回包含指定字符下标的受保护片段。"""
    for span in protected_spans:
        if span.start_index <= index < span.end_index:
            return span
    return None


def move_split_position_outside_protected_span(
    *,
    position: int,
    protected_spans: list[ProtectedSpan],
) -> int:
    """把切分点移动到受保护片段之后，避免破坏控制符。"""
    for span in protected_spans:
        if span.start_index < position < span.end_index:
            return span.end_index
    return position
