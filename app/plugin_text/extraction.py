"""
插件文本规则驱动提取模块。

本模块按照数据库中的外部导入规则，从 `plugins.js` 展开命中的字符串叶子。
外部规则文件是插件参数文本提取的唯一来源。
"""

from __future__ import annotations

from app.rmmz.schema import (
    GameData,
    PLUGINS_FILE_NAME,
    PluginTextRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rmmz.text_rules import JsonValue, TextRules, get_default_text_rules
from app.rmmz.text_protocol import normalize_visible_text_for_extraction
from app.plugin_text.common import (
    build_plugin_hash,
    expand_rule_to_leaf_paths,
    extract_plugin_name,
    jsonpath_to_location_path,
    resolve_plugin_leaves,
)


class PluginTextExtraction:
    """插件文本规则驱动提取器。"""

    def __init__(
        self,
        game_data: GameData,
        plugin_rule_records: list[PluginTextRuleRecord],
        text_rules: TextRules | None = None,
    ) -> None:
        """初始化插件文本提取器。"""
        self.game_data: GameData = game_data
        self.plugin_rule_records: list[PluginTextRuleRecord] = plugin_rule_records
        self.text_rules: TextRules = text_rules if text_rules is not None else get_default_text_rules()

    def extract_all_text(self) -> dict[str, TranslationData]:
        """按规则全量提取 `plugins.js` 中的可翻译文本。"""
        translation_items: list[TranslationItem] = []
        for rule_record in self.plugin_rule_records:
            if not rule_record.path_templates:
                continue
            plugin = self._validated_plugin(rule_record)
            translation_items.extend(
                self._extract_plugin_items(
                    rule_record=rule_record,
                    plugin=plugin,
                )
            )

        if not translation_items:
            return {}

        return {
            PLUGINS_FILE_NAME: TranslationData(
                display_name=None,
                translation_items=translation_items,
            )
        }

    def _validated_plugin(self, rule_record: PluginTextRuleRecord) -> dict[str, JsonValue]:
        """确认数据库规则仍然匹配当前插件配置。"""
        if rule_record.plugin_index >= len(self.game_data.plugins_js):
            raise RuntimeError(
                f"插件规则已过期: plugin_index={rule_record.plugin_index} 已超出当前 plugins.js 范围，请重新导出并导入插件规则"
            )
        plugin = self.game_data.plugins_js[rule_record.plugin_index]
        current_plugin_name = extract_plugin_name(plugin, rule_record.plugin_index)
        if rule_record.plugin_name != current_plugin_name:
            raise RuntimeError(
                f"插件规则已过期: plugin_index={rule_record.plugin_index} 名称不匹配，规则={rule_record.plugin_name}，当前={current_plugin_name}，请重新导出并导入插件规则"
            )
        current_plugin_hash = build_plugin_hash(plugin)
        if rule_record.plugin_hash != current_plugin_hash:
            raise RuntimeError(
                f"插件规则已过期: plugin_index={rule_record.plugin_index} 插件配置 hash 不匹配，请重新导出并导入插件规则"
            )
        return plugin

    def _extract_plugin_items(
        self,
        *,
        rule_record: PluginTextRuleRecord,
        plugin: dict[str, JsonValue],
    ) -> list[TranslationItem]:
        """根据单个插件规则快照提取正文条目。"""
        resolved_leaves = resolve_plugin_leaves(plugin)
        string_leaf_map = {
            leaf.path: leaf.value for leaf in resolved_leaves if leaf.value_type == "string"
        }
        translation_items: list[TranslationItem] = []
        seen_leaf_paths: set[str] = set()

        for path_template in rule_record.path_templates:
            matched_paths = expand_rule_to_leaf_paths(
                path_template=path_template,
                resolved_leaves=resolved_leaves,
            )
            for leaf_path in matched_paths:
                if leaf_path in seen_leaf_paths:
                    continue
                seen_leaf_paths.add(leaf_path)

                leaf_value = string_leaf_map.get(leaf_path)
                if not isinstance(leaf_value, str):
                    continue

                normalized_value = normalize_visible_text_for_extraction(leaf_value)
                if not self.text_rules.should_translate_source_text(normalized_value):
                    continue

                translation_items.append(
                    TranslationItem(
                        location_path=jsonpath_to_location_path(
                            json_path=leaf_path,
                            plugin_index=rule_record.plugin_index,
                        ),
                        item_type="short_text",
                        original_lines=[normalized_value],
                    )
                )

        return translation_items


__all__: list[str] = ["PluginTextExtraction"]
