"""占位符反查队列工具。"""

from __future__ import annotations

from collections import deque

from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import TextRules

type OriginalPlaceholderQueues = dict[str, deque[str]]


def build_original_placeholder_queues(
    *,
    item: TranslationItem,
    text_rules: TextRules,
) -> OriginalPlaceholderQueues:
    """按原文出现顺序建立原始控制符到占位符的可消费队列。"""
    queues: OriginalPlaceholderQueues = {}
    for line in item.original_lines_with_placeholders:
        for match in text_rules.placeholder_token_pattern.finditer(line):
            placeholder = match.group(0)
            original = item.placeholder_map.get(placeholder)
            if original is None:
                continue
            queues.setdefault(original, deque()).append(placeholder)
    if queues:
        return queues

    for placeholder, original in item.placeholder_map.items():
        repeat_count = max(item.placeholder_counts.get(placeholder, 1), 1)
        queue = queues.setdefault(original, deque())
        for _index in range(repeat_count):
            queue.append(placeholder)
    return queues


def consume_original_placeholder(
    *,
    queues: OriginalPlaceholderQueues,
    original: str,
) -> str | None:
    """按译文出现顺序取出当前原始控制符对应的下一个占位符。"""
    queue = queues.get(original)
    if not queue:
        return None
    return queue.popleft()


__all__: list[str] = [
    "OriginalPlaceholderQueues",
    "build_original_placeholder_queues",
    "consume_original_placeholder",
]
