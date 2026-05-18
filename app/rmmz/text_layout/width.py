"""RPG Maker 文本布局中的可见宽度统计。"""

from __future__ import annotations

from app.rmmz.text_rules import TextRules

from .protected import collect_protected_spans, is_inside_protected_span


def count_line_width_chars(text: str, text_rules: TextRules) -> int:
    """统计参与长文本行宽判断的可见字符数量。"""
    protected_spans = collect_protected_spans(text=text, text_rules=text_rules)
    count = 0
    for index, char in enumerate(text):
        if is_inside_protected_span(index=index, protected_spans=protected_spans):
            continue
        if text_rules.is_line_width_counted_char(char):
            count += 1
    return count
