"""统一文本范围服务中的外部规则命中展开。"""

from __future__ import annotations

from app.event_command_text.importer import command_matches_filters
from app.note_tag_text.sources import note_file_pattern_matches
from app.nonstandard_data import NonstandardDataTextExtraction, NonstandardDataTextExtractionContext
from app.json_path_protocol import jsonpath_to_event_command_location_path, resolve_event_command_leaves
from app.plugin_text.common import expand_rule_to_leaf_paths, jsonpath_to_location_path, resolve_plugin_leaves
from app.rmmz.commands import iter_all_commands
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    GameData,
    NonstandardDataTextRuleRecord,
    NoteTagTextRuleRecord,
    PluginTextRuleRecord,
)
from app.rmmz.text_protocol import normalize_visible_text_for_extraction
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules, ensure_json_object

from .models import TextScopeRuleHit


def collect_plugin_rule_hits(
    *,
    game_data: GameData,
    plugin_rules: list[PluginTextRuleRecord],
) -> list[TextScopeRuleHit]:
    """展开插件参数规则命中的全部字符串叶子。"""
    hits: list[TextScopeRuleHit] = []
    seen_paths: set[str] = set()
    for rule in plugin_rules:
        if rule.plugin_index >= len(game_data.plugins_js):
            continue
        plugin = game_data.plugins_js[rule.plugin_index]
        resolved_leaves = resolve_plugin_leaves(plugin)
        string_leaf_map = {
            leaf.path: leaf.value
            for leaf in resolved_leaves
            if leaf.value_type == "string" and isinstance(leaf.value, str)
        }
        for path_template in rule.path_templates:
            matched_paths = expand_rule_to_leaf_paths(
                path_template=path_template,
                resolved_leaves=resolved_leaves,
            )
            for leaf_path in matched_paths:
                location_path = jsonpath_to_location_path(
                    json_path=leaf_path,
                    plugin_index=rule.plugin_index,
                )
                if location_path in seen_paths:
                    continue
                seen_paths.add(location_path)
                leaf_value = string_leaf_map.get(leaf_path)
                if leaf_value is None:
                    continue
                hits.append(
                    TextScopeRuleHit(
                        location_path=location_path,
                        source_type="plugin_parameter",
                        rule_source="插件参数规则",
                        original_text=normalize_visible_text_for_extraction(leaf_value),
                    )
                )
    return hits


def collect_event_command_rule_hits(
    *,
    game_data: GameData,
    event_rules: list[EventCommandTextRuleRecord],
) -> list[TextScopeRuleHit]:
    """展开事件指令规则命中的全部字符串叶子。"""
    hits: list[TextScopeRuleHit] = []
    seen_paths: set[str] = set()
    for path, _display_name, command in iter_all_commands(game_data):
        matched_rules = [
            rule
            for rule in event_rules
            if rule.command_code == command.code
            and command_matches_filters(
                parameters=command.parameters,
                filters=rule.parameter_filters,
            )
        ]
        if not matched_rules:
            continue
        command_location_path = "/".join(map(str, path))
        resolved_leaves = resolve_event_command_leaves(command.parameters)
        string_leaf_map = {
            leaf.path: leaf.value
            for leaf in resolved_leaves
            if leaf.value_type == "string" and isinstance(leaf.value, str)
        }
        for rule in matched_rules:
            for path_template in rule.path_templates:
                matched_paths = expand_rule_to_leaf_paths(
                    path_template=path_template,
                    resolved_leaves=resolved_leaves,
                )
                for leaf_path in matched_paths:
                    location_path = jsonpath_to_event_command_location_path(
                        json_path=leaf_path,
                        command_location_path=command_location_path,
                    )
                    if location_path in seen_paths:
                        continue
                    seen_paths.add(location_path)
                    leaf_value = string_leaf_map.get(leaf_path)
                    if leaf_value is None:
                        continue
                    hits.append(
                        TextScopeRuleHit(
                            location_path=location_path,
                            source_type="event_command",
                            rule_source="事件指令规则",
                            original_text=normalize_visible_text_for_extraction(leaf_value),
                        )
                    )
    return hits


def collect_note_tag_rule_hits(
    *,
    game_data: GameData,
    note_tag_rules: list[NoteTagTextRuleRecord],
    text_rules: TextRules,
) -> list[TextScopeRuleHit]:
    """展开 Note 标签规则命中的全部字符串值。"""
    hits: list[TextScopeRuleHit] = []
    seen_paths: set[str] = set()
    native_hit_details = collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules)
    for rule in note_tag_rules:
        tag_names = set(rule.tag_names)
        for index, raw_hit in enumerate(native_hit_details):
            hit = ensure_json_object(raw_hit, f"note_tag_hit_details[{index}]")
            file_name = _read_note_tag_hit_string(hit, "file_name", f"note_tag_hit_details[{index}]")
            tag_name = _read_note_tag_hit_string(hit, "tag_name", f"note_tag_hit_details[{index}]")
            location_path = _read_note_tag_hit_string(hit, "location_path", f"note_tag_hit_details[{index}]")
            original_text = _read_note_tag_hit_string(hit, "original_text", f"note_tag_hit_details[{index}]")
            if tag_name not in tag_names:
                continue
            if not note_file_pattern_matches(file_name=file_name, file_pattern=rule.file_name):
                continue
            if location_path in seen_paths:
                continue
            seen_paths.add(location_path)
            hits.append(
                TextScopeRuleHit(
                    location_path=location_path,
                    source_type="note_tag",
                    rule_source="Note 标签规则",
                    original_text=original_text,
                )
            )
    return hits


def collect_native_note_tag_hit_details(*, game_data: GameData, text_rules: TextRules) -> JsonArray:
    """延迟调用 native Note 标签逐命中明细，避免 Note 标签包初始化循环。"""
    from app.native_note_tag_scan import collect_native_note_tag_hit_details as collect_native

    return collect_native(game_data=game_data, text_rules=text_rules)


def _read_note_tag_hit_string(hit: JsonObject, field_name: str, label: str) -> str:
    """读取 native Note 标签逐命中明细中的字符串字段。"""
    value = hit.get(field_name)
    if not isinstance(value, str):
        raise TypeError(f"{label}.{field_name} 必须是字符串")
    return value


def collect_nonstandard_data_rule_hits(
    *,
    game_data: GameData,
    nonstandard_data_rules: list[NonstandardDataTextRuleRecord],
    text_rules: TextRules,
    nonstandard_data_context: NonstandardDataTextExtractionContext | None = None,
) -> list[TextScopeRuleHit]:
    """展开非标准 data 文件规则命中的全部字符串叶子。"""
    extractor = NonstandardDataTextExtraction(
        game_data=game_data,
        rule_records=nonstandard_data_rules,
        text_rules=text_rules,
        context=nonstandard_data_context,
    )
    return [
        TextScopeRuleHit(
            location_path=location_path,
            source_type="nonstandard_data",
            rule_source="非标准 data 文件文本规则",
            original_text=original_text,
        )
        for location_path, original_text in extractor.collect_rule_hits()
    ]
