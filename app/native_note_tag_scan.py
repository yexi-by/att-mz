"""Rust Note 标签候选明细适配。"""

from __future__ import annotations

from typing import cast

from app.native_scope_index import (
    build_native_note_tag_candidates_payload,
    scan_native_rule_candidates,
)
from app.note_tag_text.parser import iter_note_tag_matches
from app.note_tag_text.importer import NoteTagRuleImportFile, normalize_tag_names
from app.note_tag_text.sources import (
    MAP_NOTE_FILE_PATTERN,
    collect_note_tag_sources,
    matched_note_file_names,
    note_file_pattern_matches,
)
from app.rmmz.schema import GameData, NoteTagTextRuleRecord
from app.rmmz.text_rules import (
    JsonArray,
    JsonObject,
    TextRules,
    ensure_json_array,
    ensure_json_object,
    ensure_json_string_list,
)
from app.rmmz.text_protocol import normalize_visible_text_for_extraction


def build_note_tag_rule_records_from_native_candidates(
    *,
    game_data: GameData,
    import_file: NoteTagRuleImportFile,
    text_rules: TextRules,
) -> list[NoteTagTextRuleRecord]:
    """使用 native Note 标签候选摘要校验并构造规则记录。"""
    candidate_details = collect_native_note_tag_candidate_details(game_data=game_data, text_rules=text_rules)
    records: list[NoteTagTextRuleRecord] = []
    for file_name, tag_names in import_file.items():
        normalized_file_name = file_name.strip()
        if not normalized_file_name:
            raise ValueError("Note 标签规则不能包含空文件名")
        if not normalized_file_name.endswith(".json"):
            raise ValueError(f"Note 标签规则文件模式必须指向 data JSON 文件: {normalized_file_name}")
        matched_file_names = matched_note_file_names(game_data=game_data, file_pattern=normalized_file_name)
        if not matched_file_names:
            raise ValueError(f"Note 标签规则文件模式没有匹配当前 data 文件: {normalized_file_name}")
        normalized_tag_names = normalize_tag_names(tag_names)
        if not normalized_tag_names:
            raise ValueError(f"Note 标签规则不能为空: {normalized_file_name}")
        for tag_name in normalized_tag_names:
            if _requires_precise_map_source_validation(
                file_name=normalized_file_name,
                matched_file_names=matched_file_names,
            ):
                _validate_note_tag_precise_source_hit(
                    game_data=game_data,
                    file_name=normalized_file_name,
                    tag_name=tag_name,
                    text_rules=text_rules,
                )
            else:
                _validate_note_tag_candidate_hit(
                    candidate_details=candidate_details,
                    file_name=normalized_file_name,
                    tag_name=tag_name,
                )
        records.append(NoteTagTextRuleRecord(file_name=normalized_file_name, tag_names=normalized_tag_names))
    return records


def collect_native_note_tag_candidate_details(*, game_data: GameData, text_rules: TextRules) -> JsonArray:
    """调用 native Note 标签候选入口并返回旧报告同形明细。"""
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


def collect_native_note_tag_extraction_details(
    *,
    game_data: GameData,
    text_rules: TextRules,
) -> tuple[JsonArray, JsonArray]:
    """调用一次 native Note 标签候选入口并返回正文提取所需来源与命中明细。"""
    payload = build_native_note_tag_candidates_payload(game_data, text_rules)
    result = scan_native_rule_candidates(payload)
    summary_value = result.scan_summary.get("note_tags")
    if summary_value is None:
        return [], []
    summary = ensure_json_object(summary_value, "native_note_tag_extraction.note_tags")
    if "source_details" not in summary:
        raise RuntimeError("native_note_tag_extraction.note_tags.source_details 缺失，请重新构建 Rust 原生扩展")
    if "hit_details" not in summary:
        raise RuntimeError("native_note_tag_extraction.note_tags.hit_details 缺失，请重新构建 Rust 原生扩展")
    raw_source_details = ensure_json_array(
        summary["source_details"],
        "native_note_tag_extraction.note_tags.source_details",
    )
    raw_hit_details = ensure_json_array(
        summary["hit_details"],
        "native_note_tag_extraction.note_tags.hit_details",
    )
    source_details = cast(
        JsonArray,
        [
            _normalize_native_note_tag_source_detail(
                ensure_json_object(item, f"native_note_tag_extraction.source_details[{index}]"),
                f"native_note_tag_extraction.source_details[{index}]",
            )
            for index, item in enumerate(raw_source_details)
        ],
    )
    hit_details = cast(
        JsonArray,
        [
            _normalize_native_note_tag_hit_detail(
                ensure_json_object(item, f"native_note_tag_extraction.hit_details[{index}]"),
                f"native_note_tag_extraction.hit_details[{index}]",
            )
            for index, item in enumerate(raw_hit_details)
        ],
    )
    return source_details, hit_details


def _validate_note_tag_candidate_hit(
    *,
    candidate_details: JsonArray,
    file_name: str,
    tag_name: str,
) -> None:
    """用 native 候选摘要校验单个 Note 标签规则至少命中可翻译值。"""
    value_hit_count = 0
    translatable_hit_count = 0
    for index, candidate_value in enumerate(candidate_details):
        candidate = ensure_json_object(candidate_value, f"note_tag_candidates[{index}]")
        candidate_tag_name = candidate.get("tag_name")
        if candidate_tag_name != tag_name:
            continue
        candidate_file_name = candidate.get("file_name")
        if not isinstance(candidate_file_name, str):
            raise TypeError(f"note_tag_candidates[{index}].file_name 必须是字符串")
        if not _candidate_file_matches_rule(
            candidate_file_name=candidate_file_name,
            file_name=file_name,
        ):
            continue
        value_hit_count += _read_int(candidate, "value_hit_count", f"note_tag_candidates[{index}]")
        translatable_hit_count += _read_int(
            candidate,
            "translatable_hit_count",
            f"note_tag_candidates[{index}]",
        )

    if value_hit_count == 0:
        raise ValueError(f"Note 标签规则没有命中当前游戏 Note 标签: {file_name}/{tag_name}")
    if translatable_hit_count == 0:
        raise ValueError(f"Note 标签规则没有命中玩家可见可翻译文本: {file_name}/{tag_name}")


def _validate_note_tag_precise_source_hit(
    *,
    game_data: GameData,
    file_name: str,
    tag_name: str,
    text_rules: TextRules,
) -> None:
    """对精确地图规则保留单文件语义，避免消费 `Map*.json` 聚合候选时误放行。"""
    hit_count = 0
    translatable_hit_count = 0
    for source in collect_note_tag_sources(game_data=game_data, file_pattern=file_name):
        matches = [
            match
            for match in iter_note_tag_matches(source.note_text)
            if match.tag_name == tag_name and match.value_span is not None
        ]
        if len(matches) > 1:
            raise ValueError(f"{source.location_prefix}/note/{tag_name} 标签重复，无法生成唯一定位路径")
        if not matches:
            continue
        hit_count += 1
        normalized_value = normalize_visible_text_for_extraction(
            matches[0].value,
            plain_text_normalizer=text_rules.normalize_extraction_text,
        )
        if normalized_value and text_rules.should_translate_source_text(normalized_value):
            translatable_hit_count += 1

    if hit_count == 0:
        raise ValueError(f"Note 标签规则没有命中当前游戏 Note 标签: {file_name}/{tag_name}")
    if translatable_hit_count == 0:
        raise ValueError(f"Note 标签规则没有命中玩家可见可翻译文本: {file_name}/{tag_name}")


def _requires_precise_map_source_validation(*, file_name: str, matched_file_names: list[str]) -> bool:
    """判断规则是否需要避开 native `Map*.json` 聚合摘要。"""
    if file_name == MAP_NOTE_FILE_PATTERN:
        return False
    return any(
        note_file_pattern_matches(file_name=matched_file_name, file_pattern=MAP_NOTE_FILE_PATTERN)
        for matched_file_name in matched_file_names
    )


def _candidate_file_matches_rule(*, candidate_file_name: str, file_name: str) -> bool:
    """判断 native 候选文件模式是否覆盖当前规则文件模式。"""
    if candidate_file_name == file_name:
        return True
    return note_file_pattern_matches(file_name=candidate_file_name, file_pattern=file_name)


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


def _read_int(candidate: JsonObject, field_name: str, label: str) -> int:
    """读取 native 候选中的非布尔整数字段。"""
    value = candidate.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label}.{field_name} 必须是整数")
    return value


__all__: list[str] = [
    "build_note_tag_rule_records_from_native_candidates",
    "collect_native_note_tag_candidate_details",
    "collect_native_note_tag_extraction_details",
    "collect_native_note_tag_hit_details",
    "collect_native_note_tag_source_details",
]
