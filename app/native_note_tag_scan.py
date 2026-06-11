"""Rust Note 标签候选明细适配。"""

from __future__ import annotations

from app.native_scope_index import (
    build_native_note_tag_candidates_payload,
    build_native_note_tag_validation_payload,
    scan_native_rule_candidates,
)
from app.note_tag_text.importer import NoteTagRuleImportFile, normalize_tag_names
from app.rmmz.schema import GameData, NoteTagTextRuleRecord
from app.rmmz.text_rules import (
    JsonArray,
    JsonObject,
    TextRules,
    ensure_json_array,
    ensure_json_object,
    ensure_json_string_list,
)


def build_note_tag_rule_records_from_native_candidates(
    *,
    game_data: GameData,
    import_file: NoteTagRuleImportFile,
    text_rules: TextRules,
) -> list[NoteTagTextRuleRecord]:
    """使用 native Note 标签候选摘要校验并构造规则记录。"""
    records: list[NoteTagTextRuleRecord] = []
    for file_name, tag_names in import_file.items():
        normalized_file_name = file_name.strip()
        if not normalized_file_name:
            raise ValueError("Note 标签规则不能包含空文件名")
        if not normalized_file_name.endswith(".json"):
            raise ValueError(f"Note 标签规则文件模式必须指向 data JSON 文件: {normalized_file_name}")
        normalized_tag_names = normalize_tag_names(tag_names)
        if not normalized_tag_names:
            raise ValueError(f"Note 标签规则不能为空: {normalized_file_name}")
        records.append(NoteTagTextRuleRecord(file_name=normalized_file_name, tag_names=normalized_tag_names))
    validation = collect_native_note_tag_rule_validation(
        game_data=game_data,
        text_rules=text_rules,
        rule_records=records,
    )
    if validation["status"] != "pass":
        raise ValueError(_format_note_tag_validation_errors(validation))
    return records


def collect_native_note_tag_candidate_details(*, game_data: GameData, text_rules: TextRules) -> JsonArray:
    """调用 native Note 标签候选入口并返回当前候选明细。"""
    payload = build_native_note_tag_candidates_payload(game_data, text_rules)
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("note_tags")
    if summary_value is None:
        return []
    summary = ensure_json_object(summary_value, "native_note_tag_candidates.note_tags")
    raw_candidates = ensure_json_array(
        summary.get("candidates", []),
        "native_note_tag_candidates.note_tags.candidates",
    )
    return [
        _normalize_native_note_tag_candidate_detail(
            ensure_json_object(item, f"native_note_tag_candidates.candidates[{index}]"),
            f"native_note_tag_candidates.candidates[{index}]",
        )
        for index, item in enumerate(raw_candidates)
    ]


def collect_native_note_tag_hit_details(*, game_data: GameData, text_rules: TextRules) -> JsonArray:
    """调用 native Note 标签候选入口并返回完整逐命中明细。"""
    payload = build_native_note_tag_candidates_payload(game_data, text_rules)
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("note_tags")
    if summary_value is None:
        return []
    summary = ensure_json_object(summary_value, "native_note_tag_hits.note_tags")
    if "hit_details" not in summary:
        raise RuntimeError("native_note_tag_hits.note_tags.hit_details 缺失，请重新构建 Rust 原生扩展")
    raw_hit_details = ensure_json_array(
        summary["hit_details"],
        "native_note_tag_hits.note_tags.hit_details",
    )
    return [
        _normalize_native_note_tag_hit_detail(
            ensure_json_object(item, f"native_note_tag_hits.hit_details[{index}]"),
            f"native_note_tag_hits.hit_details[{index}]",
        )
        for index, item in enumerate(raw_hit_details)
    ]


def collect_native_note_tag_source_details(*, game_data: GameData, text_rules: TextRules) -> JsonArray:
    """调用 native Note 标签候选入口并返回 Note 来源存在摘要。"""
    payload = build_native_note_tag_candidates_payload(game_data, text_rules)
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("note_tags")
    if summary_value is None:
        return []
    summary = ensure_json_object(summary_value, "native_note_tag_sources.note_tags")
    if "source_details" not in summary:
        raise RuntimeError("native_note_tag_sources.note_tags.source_details 缺失，请重新构建 Rust 原生扩展")
    raw_source_details = ensure_json_array(
        summary["source_details"],
        "native_note_tag_sources.note_tags.source_details",
    )
    return [
        _normalize_native_note_tag_source_detail(
            ensure_json_object(item, f"native_note_tag_sources.source_details[{index}]"),
            f"native_note_tag_sources.source_details[{index}]",
        )
        for index, item in enumerate(raw_source_details)
    ]


def collect_native_note_tag_rule_validation(
    *,
    game_data: GameData,
    text_rules: TextRules,
    rule_records: list[NoteTagTextRuleRecord],
) -> JsonObject:
    """调用 native Note 标签规则验证入口并返回覆盖事实。"""
    payload = build_native_note_tag_validation_payload(
        game_data=game_data,
        text_rules=text_rules,
        rules=_note_tag_rule_records_to_native_rules(rule_records),
    )
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("note_tag_rule_validation")
    if summary_value is None:
        raise RuntimeError("native_note_tag_rule_validation 缺失，请重新构建 Rust 原生扩展")
    summary = ensure_json_object(summary_value, "native_note_tag_rule_validation")
    errors = ensure_json_array(summary["errors"], "native_note_tag_rule_validation.errors")
    return {
        "status": _read_string(summary, "status", "native_note_tag_rule_validation"),
        "scope_hash": _read_string(summary, "scope_hash", "native_note_tag_rule_validation"),
        "candidate_count": _read_int(summary, "candidate_count", "native_note_tag_rule_validation"),
        "covered_count": _read_int(summary, "covered_count", "native_note_tag_rule_validation"),
        "translatable_hit_count": _read_int(
            summary,
            "translatable_hit_count",
            "native_note_tag_rule_validation",
        ),
        "errors": [
            _normalize_native_note_tag_validation_error(
                ensure_json_object(error, f"native_note_tag_rule_validation.errors[{index}]"),
                f"native_note_tag_rule_validation.errors[{index}]",
            )
            for index, error in enumerate(errors)
        ],
    }


def _normalize_native_note_tag_candidate_detail(candidate: JsonObject, label: str) -> JsonObject:
    """收窄 native Note 标签候选 JSON 字段，避免报告层消费弱类型数据。"""
    file_name = candidate.get("file_name")
    if not isinstance(file_name, str):
        raise TypeError(f"{label}.file_name 必须是字符串")
    tag_name = candidate.get("tag_name")
    if not isinstance(tag_name, str):
        raise TypeError(f"{label}.tag_name 必须是字符串")
    return {
        "file_name": file_name,
        "tag_name": tag_name,
        "hit_count": _read_int(candidate, "hit_count", label),
        "value_hit_count": _read_int(candidate, "value_hit_count", label),
        "translatable_hit_count": _read_int(candidate, "translatable_hit_count", label),
        "matched_file_count": _read_int(candidate, "matched_file_count", label),
        "sample_locations": list(
            ensure_json_string_list(candidate.get("sample_locations", []), f"{label}.sample_locations")
        ),
        "sample_values": list(
            ensure_json_string_list(candidate.get("sample_values", []), f"{label}.sample_values")
        ),
    }


def _normalize_native_note_tag_hit_detail(hit_detail: JsonObject, label: str) -> JsonObject:
    """收窄 native Note 标签逐命中 JSON 字段，避免报告层消费弱类型数据。"""
    file_name = hit_detail.get("file_name")
    if not isinstance(file_name, str):
        raise TypeError(f"{label}.file_name 必须是字符串")
    tag_name = hit_detail.get("tag_name")
    if not isinstance(tag_name, str):
        raise TypeError(f"{label}.tag_name 必须是字符串")
    location_path = hit_detail.get("location_path")
    if not isinstance(location_path, str):
        raise TypeError(f"{label}.location_path 必须是字符串")
    original_text = hit_detail.get("original_text")
    if not isinstance(original_text, str):
        raise TypeError(f"{label}.original_text 必须是字符串")
    translatable = hit_detail.get("translatable")
    if not isinstance(translatable, bool):
        raise TypeError(f"{label}.translatable 必须是布尔值")
    return {
        "file_name": file_name,
        "tag_name": tag_name,
        "location_path": location_path,
        "original_text": original_text,
        "translatable": translatable,
    }


def _normalize_native_note_tag_source_detail(source_detail: JsonObject, label: str) -> JsonObject:
    """收窄 native Note 标签来源存在 JSON 字段，避免与逐命中值混用。"""
    file_name = source_detail.get("file_name")
    if not isinstance(file_name, str):
        raise TypeError(f"{label}.file_name 必须是字符串")
    location_prefix = source_detail.get("location_prefix")
    if not isinstance(location_prefix, str):
        raise TypeError(f"{label}.location_prefix 必须是字符串")
    return {
        "file_name": file_name,
        "location_prefix": location_prefix,
    }


def _normalize_native_note_tag_validation_error(error: JsonObject, label: str) -> JsonObject:
    """收窄 native Note 标签规则验证错误字段。"""
    code = _read_string(error, "code", label)
    file_name = _read_string(error, "file_name", label)
    message = _read_string(error, "message", label)
    tag_name = error.get("tag_name")
    if tag_name is not None and not isinstance(tag_name, str):
        raise TypeError(f"{label}.tag_name 必须是字符串或 null")
    return {
        "code": code,
        "file_name": file_name,
        "message": message,
        "tag_name": tag_name or "",
    }


def _note_tag_rule_records_to_native_rules(records: list[NoteTagTextRuleRecord]) -> JsonArray:
    """把数据库规则记录转换为 Rust Note 标签验证输入。"""
    return [
        {
            "file_name": record.file_name,
            "tag_names": list(record.tag_names),
        }
        for record in records
    ]


def _format_note_tag_validation_errors(validation: JsonObject) -> str:
    """渲染 native Note 标签规则验证错误。"""
    errors = ensure_json_array(validation["errors"], "note_tag_rule_validation.errors")
    messages: list[str] = []
    for index, raw_error in enumerate(errors):
        error = ensure_json_object(raw_error, f"note_tag_rule_validation.errors[{index}]")
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(message)
            continue
        code = error.get("code")
        code_text = code if isinstance(code, str) and code else "unknown"
        messages.append(f"Note 标签规则无效: {code_text}")
    if not messages:
        return "Note 标签规则无效"
    suffix = f" 等 {len(messages)} 项" if len(messages) > 5 else ""
    return "；".join(messages[:5]) + suffix


def _read_string(candidate: JsonObject, field_name: str, label: str) -> str:
    """读取 native 输出中的字符串字段。"""
    value = candidate.get(field_name)
    if not isinstance(value, str):
        raise TypeError(f"{label}.{field_name} 必须是字符串")
    return value


def _read_int(candidate: JsonObject, field_name: str, label: str) -> int:
    """读取 native 候选中的非布尔整数字段。"""
    value = candidate.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label}.{field_name} 必须是整数")
    return value


__all__: list[str] = [
    "build_note_tag_rule_records_from_native_candidates",
    "collect_native_note_tag_candidate_details",
    "collect_native_note_tag_hit_details",
    "collect_native_note_tag_rule_validation",
    "collect_native_note_tag_source_details",
]
