"""RPG Maker 文本布局中的可见宽度统计。"""

from __future__ import annotations

from app.native_rule_runtime import evaluate_runtime_config_patterns, runtime_config_patterns_from_setting
from app.rmmz.text_rules import TextRules

from .protected import collect_protected_spans, is_inside_protected_span


def line_width_counted_flags(text: str, text_rules: TextRules) -> list[bool]:
    """按配置正则批量判断每个字符是否计入长文本宽度。"""
    if not text:
        return []
    result = evaluate_runtime_config_patterns(
        {
            "settings_runtime_patterns": runtime_config_patterns_from_setting(text_rules.setting),
            "texts": [
                {
                    "id": str(index),
                    "text": char,
                }
                for index, char in enumerate(text)
            ],
        }
    )
    if result.status != "ok":
        message = result.errors[0].message if result.errors else "运行配置正则执行失败"
        raise RuntimeError(message)
    entries_by_id = {entry.id: entry.line_width_count for entry in result.entries}
    return [entries_by_id.get(str(index), 0) > 0 for index in range(len(text))]


def count_line_width_chars(text: str, text_rules: TextRules) -> int:
    """统计参与长文本行宽判断的可见字符数量。"""
    protected_spans = collect_protected_spans(text=text, text_rules=text_rules)
    counted_flags = line_width_counted_flags(text=text, text_rules=text_rules)
    count = 0
    for index, _char in enumerate(text):
        if is_inside_protected_span(index=index, protected_spans=protected_spans):
            continue
        if counted_flags[index]:
            count += 1
    return count
