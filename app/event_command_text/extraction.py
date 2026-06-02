"""事件指令文本规则驱动提取模块。"""

from app.event_command_text.importer import command_matches_filters
from app.plugin_text.paths import (
    expand_rule_to_leaf_paths,
    jsonpath_to_event_command_location_path,
    resolve_event_command_leaves,
)
from app.rmmz.commands import iter_all_commands
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    GameData,
    MAP_PATTERN,
    TranslationData,
    TranslationItem,
)
from app.rmmz.text_rules import TextRules, get_default_text_rules
from app.rmmz.text_protocol import normalize_visible_text_for_extraction


class EventCommandTextExtraction:
    """事件指令文本规则驱动提取器。"""

    def __init__(
        self,
        game_data: GameData,
        rule_records: list[EventCommandTextRuleRecord],
        text_rules: TextRules | None = None,
    ) -> None:
        """初始化事件指令文本提取器。"""
        self.game_data: GameData = game_data
        self.rule_records: list[EventCommandTextRuleRecord] = rule_records
        self.text_rules: TextRules = text_rules if text_rules is not None else get_default_text_rules()

    def extract_all_text(self) -> dict[str, TranslationData]:
        """按数据库规则提取事件指令参数中的字符串叶子。"""
        translation_data_map, _rule_items = self._extract_all_text(collect_rule_items=False)
        return translation_data_map

    def extract_all_text_with_rule_items(self) -> tuple[dict[str, TranslationData], list[list[TranslationItem]]]:
        """一次提取事件指令文本，并返回每条规则组对应的命中项。"""
        return self._extract_all_text(collect_rule_items=True)

    def _extract_all_text(self, *, collect_rule_items: bool) -> tuple[dict[str, TranslationData], list[list[TranslationItem]]]:
        """按需提取全量文本和规则组命中项。"""
        if not self.rule_records:
            return {}, []

        translation_data_map: dict[str, TranslationData] = {}
        seen_location_paths: set[str] = set()
        rule_seen_location_paths: list[set[str]] = [set() for _rule in self.rule_records]
        rule_items: list[list[TranslationItem]] = [[] for _rule in self.rule_records]
        command_hit_counts = [0 for _rule in self.rule_records]
        path_hit_counts: dict[tuple[int, str], int] = {
            (rule_index, path_template): 0
            for rule_index, rule in enumerate(self.rule_records)
            for path_template in rule.path_templates
        }
        for path, display_name, command in iter_all_commands(self.game_data):
            matched_rules = [
                (rule_index, rule)
                for rule_index, rule in enumerate(self.rule_records)
                if rule.command_code == command.code
                and command_matches_filters(
                    parameters=command.parameters,
                    filters=rule.parameter_filters,
                )
            ]
            if not matched_rules:
                continue

            file_name_value = path[0]
            if not isinstance(file_name_value, str):
                continue

            file_name = file_name_value
            if file_name not in translation_data_map:
                map_display_name = display_name if MAP_PATTERN.fullmatch(file_name) else None
                translation_data_map[file_name] = TranslationData(
                    display_name=map_display_name,
                    translation_items=[],
                )

            command_location_path = "/".join(map(str, path))
            resolved_leaves = resolve_event_command_leaves(command.parameters)
            string_leaf_map = {
                leaf.path: leaf.value for leaf in resolved_leaves if leaf.value_type == "string"
            }
            for rule_index, rule in matched_rules:
                command_hit_counts[rule_index] += 1
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
                        leaf_value = string_leaf_map.get(leaf_path)
                        if not isinstance(leaf_value, str):
                            continue
                        path_hit_counts[(rule_index, path_template)] += 1
                        normalized_value = normalize_visible_text_for_extraction(leaf_value)
                        if not self.text_rules.should_translate_source_text(normalized_value):
                            continue
                        if collect_rule_items and location_path not in rule_seen_location_paths[rule_index]:
                            rule_seen_location_paths[rule_index].add(location_path)
                            rule_items[rule_index].append(
                                TranslationItem(
                                    location_path=location_path,
                                    item_type="short_text",
                                    original_lines=[normalized_value],
                                )
                            )
                        if location_path not in seen_location_paths:
                            seen_location_paths.add(location_path)
                            translation_data_map[file_name].translation_items.append(
                                TranslationItem(
                                    location_path=location_path,
                                    item_type="short_text",
                                    original_lines=[normalized_value],
                                )
                            )

        result = {
            file_name: data
            for file_name, data in translation_data_map.items()
            if data.translation_items
        }
        _ensure_event_command_rules_have_current_hits(
            rules=self.rule_records,
            command_hit_counts=command_hit_counts,
            path_hit_counts=path_hit_counts,
        )
        return result, rule_items


def _ensure_event_command_rules_have_current_hits(
    *,
    rules: list[EventCommandTextRuleRecord],
    command_hit_counts: list[int],
    path_hit_counts: dict[tuple[int, str], int],
) -> None:
    """确认已保存事件指令规则仍然命中当前游戏。"""
    for rule_index, rule in enumerate(rules):
        rule_label = _event_command_rule_label(rule)
        if command_hit_counts[rule_index] == 0:
            raise RuntimeError(
                f"事件指令规则已过期: {rule_label} 没有命中当前游戏指令，请重新导出并导入事件指令规则"
            )
        for path_template in rule.path_templates:
            if path_hit_counts[(rule_index, path_template)] == 0:
                raise RuntimeError(
                    f"事件指令规则已过期: {rule_label} 路径没有命中当前字符串叶子: {path_template}，请重新导出并导入事件指令规则"
                )


def _event_command_rule_label(rule: EventCommandTextRuleRecord) -> str:
    """生成适合错误信息展示的事件指令规则摘要。"""
    if not rule.parameter_filters:
        return f"command_code={rule.command_code}"
    filters = ",".join(
        f"{parameter_filter.index}={parameter_filter.value}"
        for parameter_filter in rule.parameter_filters
    )
    return f"command_code={rule.command_code} match={filters}"


__all__: list[str] = ["EventCommandTextExtraction"]
