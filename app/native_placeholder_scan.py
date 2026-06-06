"""Rust 普通占位符候选明细适配。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.native_scope_index import (
    build_native_rule_candidate_text_rules_payload,
    build_native_placeholder_candidates_payload,
    scan_native_rule_candidates,
)
from app.rmmz.schema import TranslationData
from app.rmmz.text_rules import (
    JsonArray,
    JsonObject,
    TextRules,
    ensure_json_array,
    ensure_json_object,
    ensure_json_string_list,
)


def collect_native_placeholder_candidate_details(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> JsonArray:
    """调用 native 普通占位符候选入口并返回旧报告同形明细。"""
    payload = build_native_placeholder_candidates_payload(translation_data_map, text_rules)
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("placeholders")
    if summary_value is None:
        return []
    summary = ensure_json_object(summary_value, "native_placeholder_candidates.placeholders")
    raw_candidates = ensure_json_array(
        summary.get("candidates", []),
        "native_placeholder_candidates.placeholders.candidates",
    )
    return [
        _normalize_native_placeholder_candidate_detail(
            ensure_json_object(item, f"native_placeholder_candidates.candidates[{index}]"),
            f"native_placeholder_candidates.candidates[{index}]",
        )
        for index, item in enumerate(raw_candidates)
    ]


def collect_native_placeholder_candidate_details_from_entries(
    *,
    entries: Iterable[tuple[str, Sequence[str]]],
    text_rules: TextRules,
) -> JsonArray:
    """用轻量索引正文条目调用 native 普通占位符候选入口。"""
    placeholder_texts: JsonArray = [
        {
            "source_name": f"{location_path}#{line_index}",
            "text": text,
        }
        for location_path, original_lines in entries
        for line_index, text in enumerate(original_lines)
    ]
    result = scan_native_rule_candidates(
        {
            "placeholder_texts": placeholder_texts,
            "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
        }
    )
    summary_value = result.scan_summary.get("placeholders")
    if summary_value is None:
        return []
    summary = ensure_json_object(summary_value, "native_placeholder_candidates.placeholders")
    raw_candidates = ensure_json_array(
        summary.get("candidates", []),
        "native_placeholder_candidates.placeholders.candidates",
    )
    return [
        _normalize_native_placeholder_candidate_detail(
            ensure_json_object(item, f"native_placeholder_candidates.candidates[{index}]"),
            f"native_placeholder_candidates.candidates[{index}]",
        )
        for index, item in enumerate(raw_candidates)
    ]


def count_uncovered_placeholder_candidate_details(candidate_details: JsonArray) -> int:
    """统计 native 普通占位符明细中的未覆盖候选数量。"""
    uncovered_count = 0
    for index, item in enumerate(candidate_details):
        detail = ensure_json_object(item, f"placeholder_candidate_details[{index}]")
        covered = detail.get("covered")
        if not isinstance(covered, bool):
            raise TypeError(f"placeholder_candidate_details[{index}].covered 必须是布尔值")
        if not covered:
            uncovered_count += 1
    return uncovered_count


def _normalize_native_placeholder_candidate_detail(candidate: JsonObject, label: str) -> JsonObject:
    """收窄 native 候选 JSON 字段，避免报告层消费弱类型数据。"""
    marker = candidate.get("marker")
    if not isinstance(marker, str):
        raise TypeError(f"{label}.marker 必须是字符串")
    count = candidate.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        raise TypeError(f"{label}.count 必须是整数")
    sources = ensure_json_string_list(candidate.get("sources", []), f"{label}.sources")
    standard_covered = candidate.get("standard_covered")
    if not isinstance(standard_covered, bool):
        raise TypeError(f"{label}.standard_covered 必须是布尔值")
    custom_covered = candidate.get("custom_covered")
    if not isinstance(custom_covered, bool):
        raise TypeError(f"{label}.custom_covered 必须是布尔值")
    covered = candidate.get("covered")
    if not isinstance(covered, bool):
        raise TypeError(f"{label}.covered 必须是布尔值")
    return {
        "marker": marker,
        "count": count,
        "sources": list(sources),
        "standard_covered": standard_covered,
        "custom_covered": custom_covered,
        "covered": covered,
    }


__all__: list[str] = [
    "collect_native_placeholder_candidate_details",
    "collect_native_placeholder_candidate_details_from_entries",
    "count_uncovered_placeholder_candidate_details",
]
