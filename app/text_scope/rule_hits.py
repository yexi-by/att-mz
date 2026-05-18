"""统一文本范围服务中的外部规则命中展开。"""

from __future__ import annotations

from app.event_command_text.importer import command_matches_filters
from app.note_tag_text.parser import iter_note_tag_matches
from app.note_tag_text.sources import collect_note_tag_sources, note_file_pattern_matches
from app.plugin_text.common import expand_rule_to_leaf_paths, jsonpath_to_location_path, resolve_plugin_leaves
from app.plugin_text.paths import jsonpath_to_event_command_location_path, resolve_event_command_leaves
from app.rmmz.commands import iter_all_commands
from app.rmmz.schema import EventCommandTextRuleRecord, GameData, NoteTagTextRuleRecord, PluginTextRuleRecord
from app.rmmz.text_protocol import normalize_visible_text_for_extraction
from app.rmmz.text_rules import TextRules

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
    all_sources = collect_note_tag_sources(game_data=game_data)
    for rule in note_tag_rules:
        tag_names = set(rule.tag_names)
        for source in all_sources:
            if not note_file_pattern_matches(file_name=source.file_name, file_pattern=rule.file_name):
                continue
            for match in iter_note_tag_matches(source.note_text):
                if match.tag_name not in tag_names or match.value_span is None:
                    continue
                location_path = f"{source.location_prefix}/note/{match.tag_name}"
                if location_path in seen_paths:
                    continue
                seen_paths.add(location_path)
                hits.append(
                    TextScopeRuleHit(
                        location_path=location_path,
                        source_type="note_tag",
                        rule_source="Note 标签规则",
                        original_text=normalize_visible_text_for_extraction(
                            match.value,
                            plain_text_normalizer=text_rules.normalize_extraction_text,
                        ),
                    )
                )
    return hits
