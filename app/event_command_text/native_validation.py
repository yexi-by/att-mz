"""事件指令规则 native 命中上下文。"""

from __future__ import annotations

from dataclasses import dataclass

from app.native_rule_runtime import prepare_rule_import, runtime_config_patterns_from_setting
from app.native_scope_index import (
    build_native_event_command_candidates_payload,
    build_native_event_command_data_files,
    scan_native_rule_candidates,
)
from app.rmmz.source_text_detection import is_source_text_required
from app.rmmz.json_types import ensure_json_array, ensure_json_object
from app.rmmz.schema import GameData, EventCommandTextRuleRecord, TranslationItem
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules


@dataclass(frozen=True, slots=True)
class NativeEventCommandRuleValidationContext:
    """事件指令规则校验和导入共用的 native 命中上下文。"""

    extracted_items: list[TranslationItem]
    record_items_by_index: list[list[TranslationItem]]
    translation_prefixes: list[str]
    translation_prefixes_by_index: list[list[str]]


def build_native_event_command_rule_validation_context(
    *,
    records: list[EventCommandTextRuleRecord],
    game_data: GameData,
    text_rules: TextRules,
    require_command_hits: bool = True,
    require_path_hits: bool = True,
) -> NativeEventCommandRuleValidationContext:
    """用 Rust 事件指令命中明细构造规则校验上下文。"""
    if not records:
        return NativeEventCommandRuleValidationContext(
            extracted_items=[],
            record_items_by_index=[],
            translation_prefixes=[],
            translation_prefixes_by_index=[],
        )

    rules = event_command_rule_records_to_native_rules(records)
    _ensure_event_command_rule_runtime_prepare(rules=rules, text_rules=text_rules)
    payload = build_native_event_command_candidates_payload(
        event_command_data_files=build_native_event_command_data_files(game_data),
        command_codes=frozenset(),
        rules=rules,
    )
    native_result = scan_native_rule_candidates(payload)
    event_summary = ensure_json_object(
        native_result.scan_summary["event_commands"],
        "native_rule_candidates_result.scan_summary.event_commands",
    )
    rule_summaries = ensure_json_array(
        event_summary["rule_summaries"],
        "native_rule_candidates_result.scan_summary.event_commands.rule_summaries",
    )
    ensure_native_event_command_rules_have_current_hits(
        records=records,
        rule_summaries=rule_summaries,
        require_command_hits=require_command_hits,
        require_path_hits=require_path_hits,
    )

    record_items_by_index: list[list[TranslationItem]] = [[] for _record in records]
    seen_rule_paths: list[set[str]] = [set() for _record in records]
    extracted_items: list[TranslationItem] = []
    seen_extracted_paths: set[str] = set()
    hit_details = ensure_json_array(
        event_summary["hit_details"],
        "native_rule_candidates_result.scan_summary.event_commands.hit_details",
    )
    for index, raw_hit in enumerate(hit_details):
        hit = ensure_json_object(raw_hit, f"event_commands.hit_details[{index}]")
        rule_index = read_json_int_field(hit, "rule_index", f"event_commands.hit_details[{index}]")
        if rule_index < 0 or rule_index >= len(records):
            raise TypeError(f"event_commands.hit_details[{index}].rule_index 超出规则范围")
        location_path = read_json_string_field(hit, "location_path", f"event_commands.hit_details[{index}]")
        original_text = read_json_string_field(hit, "original_text", f"event_commands.hit_details[{index}]")
        if not is_source_text_required(text_rules, original_text):
            continue
        item = TranslationItem(
            location_path=location_path,
            item_type="short_text",
            original_lines=[original_text],
        )
        if location_path not in seen_rule_paths[rule_index]:
            seen_rule_paths[rule_index].add(location_path)
            record_items_by_index[rule_index].append(item)
        if location_path not in seen_extracted_paths:
            seen_extracted_paths.add(location_path)
            extracted_items.append(item)

    prefixes_by_index = event_command_translation_prefixes_by_rule_from_native_rule_summaries(rule_summaries)
    return NativeEventCommandRuleValidationContext(
        extracted_items=extracted_items,
        record_items_by_index=record_items_by_index,
        translation_prefixes=sorted({prefix for prefixes in prefixes_by_index for prefix in prefixes}),
        translation_prefixes_by_index=prefixes_by_index,
    )


def event_command_rule_records_to_native_rules(records: list[EventCommandTextRuleRecord]) -> JsonArray:
    """把事件指令规则记录转换为 Rust event_command_rules 输入。"""
    rules: JsonArray = []
    for record in records:
        rules.append(
            {
                "command_code": record.command_code,
                "parameter_filters": [
                    {
                        "index": parameter_filter.index,
                        "value": parameter_filter.value,
                    }
                    for parameter_filter in record.parameter_filters
                ],
                "path_templates": list(record.path_templates),
            }
        )
    return rules


def _ensure_event_command_rule_runtime_prepare(*, rules: JsonArray, text_rules: TextRules) -> None:
    """用统一 rule_runtime 校验事件指令规则结构。"""
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "event_commands",
            "rules_payload": rules,
            "game_context": {},
            "settings_runtime_patterns": runtime_config_patterns_from_setting(text_rules.setting),
        }
    )
    if result.errors:
        messages = "；".join(error.message for error in result.errors)
        raise ValueError(messages)


def ensure_native_event_command_rules_have_current_hits(
    *,
    records: list[EventCommandTextRuleRecord],
    rule_summaries: JsonArray,
    require_command_hits: bool = True,
    require_path_hits: bool = True,
) -> None:
    """确认 native 规则摘要仍命中当前游戏 command 和路径。"""
    if len(rule_summaries) != len(records):
        raise ValueError("Rust 事件指令规则摘要数量与规则记录数量不一致")
    for index, (record, raw_summary) in enumerate(zip(records, rule_summaries, strict=True)):
        summary = ensure_json_object(raw_summary, f"event_commands.rule_summaries[{index}]")
        rule_index = read_json_int_field(summary, "rule_index", f"event_commands.rule_summaries[{index}]")
        if rule_index != index:
            raise ValueError("Rust 事件指令规则摘要 rule_index 与规则顺序不一致")
        matched_command_count = read_json_int_field(
            summary,
            "matched_command_count",
            f"event_commands.rule_summaries[{index}]",
        )
        rule_label = event_command_rule_label(record)
        if require_command_hits and matched_command_count == 0:
            raise RuntimeError(
                f"事件指令规则已过期: {rule_label} 没有命中当前游戏指令，请重新导出并导入事件指令规则"
            )

        path_hit_counts = ensure_json_array(
            summary["path_hit_counts"],
            f"event_commands.rule_summaries[{index}].path_hit_counts",
        )
        hit_counts_by_path: dict[str, int] = {}
        for path_index, raw_path_hit in enumerate(path_hit_counts):
            path_hit = ensure_json_object(
                raw_path_hit,
                f"event_commands.rule_summaries[{index}].path_hit_counts[{path_index}]",
            )
            path_template = read_json_string_field(
                path_hit,
                "path_template",
                f"event_commands.rule_summaries[{index}].path_hit_counts[{path_index}]",
            )
            hit_counts_by_path[path_template] = read_json_int_field(
                path_hit,
                "hit_count",
                f"event_commands.rule_summaries[{index}].path_hit_counts[{path_index}]",
            )
        for path_template in record.path_templates:
            if require_path_hits and hit_counts_by_path.get(path_template, 0) == 0:
                raise RuntimeError(
                    f"事件指令规则已过期: {rule_label} 路径没有命中当前字符串叶子: {path_template}，请重新导出并导入事件指令规则"
                )


def event_command_translation_prefixes_by_rule_from_native_rule_summaries(
    rule_summaries: JsonArray,
) -> list[list[str]]:
    """从 native 规则摘要按规则收集已保存译文读取前缀。"""
    prefixes_by_index: list[list[str]] = []
    for index, raw_summary in enumerate(rule_summaries):
        summary = ensure_json_object(raw_summary, f"event_commands.rule_summaries[{index}]")
        raw_prefixes = ensure_json_array(
            summary["matched_command_location_paths"],
            f"event_commands.rule_summaries[{index}].matched_command_location_paths",
        )
        prefixes: set[str] = set()
        for prefix_index, raw_prefix in enumerate(raw_prefixes):
            if not isinstance(raw_prefix, str):
                raise TypeError(
                    f"event_commands.rule_summaries[{index}].matched_command_location_paths[{prefix_index}] 必须是字符串"
                )
            prefixes.add(raw_prefix)
        prefixes_by_index.append(sorted(prefixes))
    return prefixes_by_index


def event_command_rule_label(rule: EventCommandTextRuleRecord) -> str:
    """生成适合错误信息展示的事件指令规则摘要。"""
    if not rule.parameter_filters:
        return f"command_code={rule.command_code}"
    filters = ",".join(
        f"{parameter_filter.index}={parameter_filter.value}"
        for parameter_filter in rule.parameter_filters
    )
    return f"command_code={rule.command_code} match={filters}"


def read_json_string_field(payload: JsonObject, field_name: str, context: str) -> str:
    """读取 JSON 对象中的字符串字段。"""
    value = payload[field_name]
    if not isinstance(value, str):
        raise TypeError(f"{context}.{field_name} 必须是字符串")
    return value


def read_json_int_field(payload: JsonObject, field_name: str, context: str) -> int:
    """读取 JSON 对象中的非布尔整数字段。"""
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{context}.{field_name} 必须是整数")
    return value


__all__ = [
    "NativeEventCommandRuleValidationContext",
    "build_native_event_command_rule_validation_context",
    "ensure_native_event_command_rules_have_current_hits",
    "event_command_rule_records_to_native_rules",
    "event_command_translation_prefixes_by_rule_from_native_rule_summaries",
]
