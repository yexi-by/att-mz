"""源文字符检测的 Rust rule_runtime 适配入口。"""

from __future__ import annotations

from app.native_rule_runtime import (
    evaluate_runtime_config_patterns,
    runtime_config_patterns_from_setting,
)
from app.rmmz.text_rules import TextRules


def normalize_source_detection_text(
    text_rules: TextRules,
    text: str,
    *,
    apply_exclusion_profile: bool = True,
) -> str:
    """按提取语义清理文本，并剥离 RPG Maker 控制符。"""
    normalized_text = text_rules.normalize_extraction_text(text)
    if not normalized_text:
        return ""
    if apply_exclusion_profile and text_rules.is_source_text_excluded(normalized_text):
        return ""
    return text_rules.strip_rm_control_sequences(normalized_text)


def source_text_required_flags(text_rules: TextRules, texts: list[str]) -> list[bool]:
    """批量判断文本是否命中当前源文必需正则。"""
    if not texts:
        return []
    result = evaluate_runtime_config_patterns(
        {
            "settings_runtime_patterns": runtime_config_patterns_from_setting(text_rules.setting),
            "texts": [
                {
                    "id": str(index),
                    "text": text,
                }
                for index, text in enumerate(texts)
            ],
        }
    )
    if result.status != "ok":
        message = result.errors[0].message if result.errors else "运行配置正则执行失败"
        raise RuntimeError(message)
    entries_by_id = {entry.id: entry.source_text_required for entry in result.entries}
    return [entries_by_id.get(str(index), False) for index in range(len(texts))]


def source_text_required_by_line_groups(
    text_rules: TextRules,
    line_groups: list[list[str]],
    *,
    apply_exclusion_profile: bool = True,
) -> list[bool]:
    """批量判断多组文本是否包含源文字符。"""
    detection_texts: list[str] = []
    ranges: list[tuple[int, int]] = []
    for lines in line_groups:
        start_index = len(detection_texts)
        for line in lines:
            detection_text = normalize_source_detection_text(
                text_rules,
                line,
                apply_exclusion_profile=apply_exclusion_profile,
            )
            if detection_text:
                detection_texts.append(detection_text)
        ranges.append((start_index, len(detection_texts)))

    flags = source_text_required_flags(text_rules, detection_texts)
    return [any(flags[start_index:end_index]) for start_index, end_index in ranges]


def any_source_text_required(
    text_rules: TextRules,
    lines: list[str],
    *,
    apply_exclusion_profile: bool = True,
) -> bool:
    """判断多行文本是否至少有一行包含源文字符。"""
    return source_text_required_by_line_groups(
        text_rules,
        [lines],
        apply_exclusion_profile=apply_exclusion_profile,
    )[0]


def is_source_text_required(
    text_rules: TextRules,
    text: str,
    *,
    apply_exclusion_profile: bool = True,
) -> bool:
    """判断单条文本是否包含源文字符。"""
    detection_text = normalize_source_detection_text(
        text_rules,
        text,
        apply_exclusion_profile=apply_exclusion_profile,
    )
    if not detection_text:
        return False
    return source_text_required_flags(text_rules, [detection_text])[0]
