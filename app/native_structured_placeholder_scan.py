"""Rust 结构化占位符候选明细适配。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.native_scope_index import (
    build_native_rule_candidate_text_rules_payload,
    build_native_structured_placeholder_candidates_payload,
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


def collect_native_structured_placeholder_candidate_details(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> JsonArray:
    """调用 native 结构化占位符候选入口并返回当前候选明细。"""
    if not translation_data_map:
        return []
    payload = build_native_structured_placeholder_candidates_payload(translation_data_map, text_rules)
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("structured_placeholders")
    if summary_value is None:
        raise RuntimeError("native structured_placeholders 扫描结果缺少 structured_placeholders 摘要，请重新执行 uv run maturin develop")
    summary = ensure_json_object(
        summary_value,
        "native_structured_placeholder_candidates.structured_placeholders",
    )
    raw_candidates = ensure_json_array(
        summary.get("candidates", []),
        "native_structured_placeholder_candidates.structured_placeholders.candidates",
    )
    return [
        _normalize_native_structured_placeholder_candidate_detail(
            ensure_json_object(item, f"native_structured_placeholder_candidates.candidates[{index}]"),
            f"native_structured_placeholder_candidates.candidates[{index}]",
        )
        for index, item in enumerate(raw_candidates)
    ]


def collect_native_structured_placeholder_candidate_details_from_entries(
    *,
    entries: Iterable[tuple[str, Sequence[str]]],
    text_rules: TextRules,
) -> JsonArray:
    """用轻量索引正文条目调用 native 结构化占位符候选入口。"""
    structured_placeholder_texts: JsonArray = [
        {
            "location_path": location_path,
            "line_number": line_index + 1,
            "text": text,
        }
        for location_path, original_lines in entries
        for line_index, text in enumerate(original_lines)
    ]
    if not structured_placeholder_texts:
        return []
    result = scan_native_rule_candidates(
        {
            "structured_placeholder_texts": structured_placeholder_texts,
            "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
        }
    )
    summary_value = result.scan_summary.get("structured_placeholders")
    if summary_value is None:
        raise RuntimeError("native structured_placeholders 扫描结果缺少 structured_placeholders 摘要，请重新执行 uv run maturin develop")
    summary = ensure_json_object(
        summary_value,
        "native_structured_placeholder_candidates.structured_placeholders",
    )
    raw_candidates = ensure_json_array(
        summary.get("candidates", []),
        "native_structured_placeholder_candidates.structured_placeholders.candidates",
    )
    return [
        _normalize_native_structured_placeholder_candidate_detail(
            ensure_json_object(item, f"native_structured_placeholder_candidates.candidates[{index}]"),
            f"native_structured_placeholder_candidates.candidates[{index}]",
        )
        for index, item in enumerate(raw_candidates)
    ]


def count_uncovered_structured_placeholder_candidate_details(candidate_details: JsonArray) -> int:
    """统计 native 结构化占位符明细中的未覆盖候选数量。"""
    uncovered_count = 0
    for index, item in enumerate(candidate_details):
        detail = ensure_json_object(item, f"structured_placeholder_candidate_details[{index}]")
        covered = detail.get("covered")
        if not isinstance(covered, bool):
            raise TypeError(f"structured_placeholder_candidate_details[{index}].covered 必须是布尔值")
        if not covered:
            uncovered_count += 1
    return uncovered_count


def _normalize_native_structured_placeholder_candidate_detail(
    candidate: JsonObject,
    label: str,
) -> JsonObject:
    """收窄 native 结构化候选 JSON 字段，避免报告层消费弱类型数据。"""
    location_path = candidate.get("location_path")
    if not isinstance(location_path, str):
        raise TypeError(f"{label}.location_path 必须是字符串")
    line_number = candidate.get("line_number")
    if not isinstance(line_number, int) or isinstance(line_number, bool):
        raise TypeError(f"{label}.line_number 必须是整数")
    marker = candidate.get("candidate")
    if not isinstance(marker, str):
        raise TypeError(f"{label}.candidate 必须是字符串")
    text = candidate.get("text")
    if not isinstance(text, str):
        raise TypeError(f"{label}.text 必须是字符串")
    candidate_range = _read_range(candidate, label)
    covered = candidate.get("covered")
    if not isinstance(covered, bool):
        raise TypeError(f"{label}.covered 必须是布尔值")
    covered_by = _read_enum(
        candidate,
        "covered_by",
        {"standard_placeholder", "custom_placeholder", "structured_placeholder", "none"},
        label,
    )
    candidate_kind = _read_enum(
        candidate,
        "candidate_kind",
        {"structured_shell", "uncovered_candidate"},
        label,
    )
    location_paths = ensure_json_string_list(candidate.get("location_paths"), f"{label}.location_paths")
    matching_rules = ensure_json_string_list(candidate.get("matching_rules", []), f"{label}.matching_rules")
    return {
        "location_path": location_path,
        "location_paths": list(location_paths),
        "line_number": line_number,
        "candidate": marker,
        "text": text,
        "range": candidate_range,
        "covered": covered,
        "covered_by": covered_by,
        "matching_rules": list(matching_rules),
        "candidate_kind": candidate_kind,
    }


def _read_range(candidate: JsonObject, label: str) -> JsonArray:
    raw_range = ensure_json_array(candidate.get("range"), f"{label}.range")
    if len(raw_range) != 2:
        raise TypeError(f"{label}.range 必须包含 2 个整数")
    values: JsonArray = []
    for index, value in enumerate(raw_range):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{label}.range[{index}] 必须是整数")
        values.append(value)
    return values


def _read_enum(candidate: JsonObject, field_name: str, allowed_values: set[str], label: str) -> str:
    value = candidate.get(field_name)
    if not isinstance(value, str):
        raise TypeError(f"{label}.{field_name} 必须是字符串")
    if value not in allowed_values:
        raise ValueError(f"{label}.{field_name} 非法: {value}")
    return value


__all__: list[str] = [
    "collect_native_structured_placeholder_candidate_details",
    "collect_native_structured_placeholder_candidate_details_from_entries",
    "count_uncovered_structured_placeholder_candidate_details",
]
