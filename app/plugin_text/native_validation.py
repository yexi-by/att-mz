"""插件参数规则 native 命中事实适配。"""

from __future__ import annotations

from dataclasses import dataclass

from app.json_path_protocol import jsonpath_template_is_ancestor
from app.native_rule_runtime import prepare_rule_import, runtime_config_patterns_from_setting
from app.native_scope_index import (
    NativeRuleCandidatesResult,
    build_native_plugin_config_candidates_payload,
    scan_native_rule_candidates,
)
from app.rmmz.schema import PluginTextRuleRecord, TranslationItem
from app.rmmz.schema import GameData
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules, ensure_json_array, ensure_json_object

from .importer import PluginRuleImportFile


@dataclass(frozen=True, slots=True)
class NativePluginRuleValidationContext:
    """插件参数规则 native 命中上下文。"""

    records: list[PluginTextRuleRecord]
    extracted_items: list[TranslationItem]
    record_items_by_index: dict[int, list[TranslationItem]]
    translation_prefixes: list[str]


def build_native_plugin_rule_validation_context_from_import(
    *,
    game_data: GameData,
    import_file: PluginRuleImportFile,
    text_rules: TextRules,
) -> NativePluginRuleValidationContext:
    """从外部插件规则文件构造 native 校验上下文。"""
    rules = plugin_rule_import_file_to_native_rules(import_file)
    if not rules:
        return _empty_context()
    _ensure_plugin_config_rule_runtime_prepare(rules=rules, text_rules=text_rules)
    native_result = scan_native_rule_candidates(
        build_native_plugin_config_candidates_payload(
            game_data=game_data,
            text_rules=text_rules,
            rules=rules,
        )
    )
    plugin_summary = _plugin_config_summary(native_result)
    records = _plugin_rule_records_from_native_summary(import_file=import_file, plugin_summary=plugin_summary)
    return _context_from_native_summary(records=records, plugin_summary=plugin_summary)


def build_native_plugin_rule_validation_context(
    *,
    records: list[PluginTextRuleRecord],
    game_data: GameData,
    text_rules: TextRules,
) -> NativePluginRuleValidationContext:
    """从已保存插件规则记录构造 native 校验上下文。"""
    if not records:
        return _empty_context()
    _ensure_plugin_config_rule_runtime_prepare(
        rules=plugin_rule_records_to_native_rules(records),
        text_rules=text_rules,
    )
    native_result = scan_native_rule_candidates(
        build_native_plugin_config_candidates_payload(
            game_data=game_data,
            text_rules=text_rules,
            rules=plugin_rule_records_to_native_rules(records),
        )
    )
    plugin_summary = _plugin_config_summary(native_result)
    _ensure_plugin_rule_records_have_current_hash(records=records, plugin_summary=plugin_summary)
    return _context_from_native_summary(records=records, plugin_summary=plugin_summary)


def plugin_rule_import_file_to_native_rules(import_file: PluginRuleImportFile) -> JsonArray:
    """把外部插件规则文件转换为 Rust plugin_config 规则载荷。"""
    seen_plugin_indices: set[int] = set()
    rules: JsonArray = []
    for spec in import_file:
        if spec.plugin_index in seen_plugin_indices:
            raise ValueError(f"插件规则不能重复声明 plugin_index: {spec.plugin_index}")
        seen_plugin_indices.add(spec.plugin_index)
        rules.append(
            {
                "plugin_index": spec.plugin_index,
                "plugin_name": spec.plugin_name,
                "path_templates": list(spec.paths),
            }
        )
    return rules


def plugin_rule_records_to_native_rules(records: list[PluginTextRuleRecord]) -> JsonArray:
    """把数据库插件规则记录转换为 Rust plugin_config 规则载荷。"""
    rules: JsonArray = []
    for record in records:
        rules.append(
            {
                "plugin_index": record.plugin_index,
                "plugin_name": record.plugin_name,
                "path_templates": list(record.path_templates),
            }
        )
    return rules


def _ensure_plugin_config_rule_runtime_prepare(*, rules: JsonArray, text_rules: TextRules) -> None:
    """用统一 rule_runtime 校验插件配置规则结构。"""
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "plugin_config",
            "rules_payload": rules,
            "game_context": {},
            "settings_runtime_patterns": runtime_config_patterns_from_setting(text_rules.setting),
        }
    )
    if result.errors:
        messages = "；".join(error.message for error in result.errors)
        raise ValueError(messages)


def _plugin_rule_records_from_native_summary(
    *,
    import_file: PluginRuleImportFile,
    plugin_summary: JsonObject,
) -> list[PluginTextRuleRecord]:
    """用 native rule_summaries 构造数据库插件规则记录。"""
    rule_summaries = _rule_summaries(plugin_summary)
    if len(rule_summaries) != len(import_file):
        raise ValueError("插件参数 native 规则摘要数量与导入文件不一致")
    records: list[PluginTextRuleRecord] = []
    for rule_summary in rule_summaries:
        rule_index = _json_int(rule_summary, "rule_index", "plugin_config.rule_summaries[]")
        spec = import_file[rule_index]
        _ensure_plugin_rule_paths_have_hits(
            rule_summary=rule_summary,
            plugin_summary=plugin_summary,
        )
        records.append(
            PluginTextRuleRecord(
                plugin_index=_json_int(rule_summary, "plugin_index", "plugin_config.rule_summaries[]"),
                plugin_name=_json_str(rule_summary, "plugin_name", "plugin_config.rule_summaries[]"),
                plugin_hash=_json_str(rule_summary, "plugin_hash", "plugin_config.rule_summaries[]"),
                path_templates=list(spec.paths),
            )
        )
    return records


def _ensure_plugin_rule_records_have_current_hash(
    *,
    records: list[PluginTextRuleRecord],
    plugin_summary: JsonObject,
) -> None:
    """确认已保存插件规则仍匹配当前插件配置。"""
    summaries_by_plugin_index = {
        _json_int(rule_summary, "plugin_index", "plugin_config.rule_summaries[]"): rule_summary
        for rule_summary in _rule_summaries(plugin_summary)
    }
    for record in records:
        rule_summary = summaries_by_plugin_index.get(record.plugin_index)
        if rule_summary is None:
            raise RuntimeError(
                f"插件规则已过期: plugin_index={record.plugin_index} 已超出当前 plugins.js 范围，请重新导出并导入插件规则"
            )
        current_plugin_hash = _json_str(rule_summary, "plugin_hash", "plugin_config.rule_summaries[]")
        if record.plugin_hash != current_plugin_hash:
            raise RuntimeError(
                f"插件规则已过期: plugin_index={record.plugin_index} 插件配置 hash 不匹配，请重新导出并导入插件规则"
            )
        _ensure_plugin_rule_paths_have_hits(
            rule_summary=rule_summary,
            plugin_summary=plugin_summary,
            require_translatable_hits=False,
        )


def _ensure_plugin_rule_paths_have_hits(
    *,
    rule_summary: JsonObject,
    plugin_summary: JsonObject,
    require_translatable_hits: bool = True,
) -> None:
    """确认规则路径命中当前可翻译插件文本。"""
    plugin_name = _json_str(rule_summary, "plugin_name", "plugin_config.rule_summaries[]")
    for path_hit_count in ensure_json_array(
        rule_summary["path_hit_counts"],
        "plugin_config.rule_summaries[].path_hit_counts",
    ):
        path_hit = ensure_json_object(path_hit_count, "plugin_config.rule_summaries[].path_hit_counts[]")
        path_template = _json_str(path_hit, "path_template", "plugin_config.path_hit_counts[]")
        string_hit_count = _json_int(path_hit, "string_hit_count", "plugin_config.path_hit_counts[]")
        translatable_hit_count = _json_int(path_hit, "translatable_hit_count", "plugin_config.path_hit_counts[]")
        if string_hit_count == 0:
            hint = _native_json_string_leaf_path_hint(
                path_template=path_template,
                plugin_summary=plugin_summary,
            )
            raise ValueError(f"插件 {plugin_name} 的路径没有命中当前插件字符串叶子: {path_template}{hint}")
        if require_translatable_hits and translatable_hit_count == 0:
            raise ValueError(f"插件 {plugin_name} 的路径没有命中玩家可见可翻译文本: {path_template}")


def _context_from_native_summary(
    *,
    records: list[PluginTextRuleRecord],
    plugin_summary: JsonObject,
) -> NativePluginRuleValidationContext:
    """把 native hit_details 转为现有 TranslationItem 上下文。"""
    hit_details = [
        ensure_json_object(hit_detail, "plugin_config.hit_details[]")
        for hit_detail in ensure_json_array(plugin_summary["hit_details"], "plugin_config.hit_details")
    ]
    extracted_items = [
        TranslationItem(
            location_path=_json_str(hit_detail, "location_path", "plugin_config.hit_details[]"),
            item_type="short_text",
            original_lines=[_json_str(hit_detail, "original_text", "plugin_config.hit_details[]")],
        )
        for hit_detail in hit_details
    ]
    record_items_by_index: dict[int, list[TranslationItem]] = {
        record.plugin_index: [] for record in records
    }
    for item in extracted_items:
        plugin_index = _plugin_index_from_location_path(item.location_path)
        if plugin_index in record_items_by_index:
            record_items_by_index[plugin_index].append(item)
    return NativePluginRuleValidationContext(
        records=records,
        extracted_items=extracted_items,
        record_items_by_index=record_items_by_index,
        translation_prefixes=_plugin_rule_translation_prefixes(records),
    )


def _plugin_rule_translation_prefixes(records: list[PluginTextRuleRecord]) -> list[str]:
    """返回插件参数规则影响的译文路径前缀。"""
    return sorted({f"plugins.js/{record.plugin_index}/" for record in records})


def _native_json_string_leaf_path_hint(*, path_template: str, plugin_summary: JsonObject) -> str:
    """根据 native leaves 为 JSON 字符串容器误指向生成提示。"""
    candidate_paths: list[str] = []
    for plugin in _plugins(plugin_summary):
        for leaf_value in ensure_json_array(plugin["leaves"], "plugin_config.plugins[].leaves"):
            leaf = ensure_json_object(leaf_value, "plugin_config.plugins[].leaves[]")
            if not _json_bool(leaf, "from_json_string", "plugin_config.plugins[].leaves[]"):
                continue
            leaf_path = _json_str(leaf, "path", "plugin_config.plugins[].leaves[]")
            if jsonpath_template_is_ancestor(template_path=path_template, actual_path=leaf_path):
                candidate_paths.append(leaf_path)
    if not candidate_paths:
        return ""
    preview_paths = sorted(set(candidate_paths))
    preview = "、".join(preview_paths[:5])
    suffix = "" if len(preview_paths) <= 5 else f" 等 {len(preview_paths)} 条候选"
    return f"。该字段疑似是 JSON 字符串容器，请把规则写到解析后的内部字符串叶子，例如: {preview}{suffix}"


def _plugin_config_summary(native_result: NativeRuleCandidatesResult) -> JsonObject:
    return ensure_json_object(
        native_result.scan_summary["plugin_config"],
        "native_rule_candidates_result.scan_summary.plugin_config",
    )


def _rule_summaries(plugin_summary: JsonObject) -> list[JsonObject]:
    return [
        ensure_json_object(rule_summary, f"plugin_config.rule_summaries[{index}]")
        for index, rule_summary in enumerate(
            ensure_json_array(plugin_summary["rule_summaries"], "plugin_config.rule_summaries")
        )
    ]


def _plugins(plugin_summary: JsonObject) -> list[JsonObject]:
    return [
        ensure_json_object(plugin, f"plugin_config.plugins[{index}]")
        for index, plugin in enumerate(ensure_json_array(plugin_summary["plugins"], "plugin_config.plugins"))
    ]


def _plugin_index_from_location_path(location_path: str) -> int:
    prefix = "plugins.js/"
    if not location_path.startswith(prefix):
        raise ValueError(f"插件参数命中路径无效: {location_path}")
    index_text = location_path[len(prefix):].split("/", 1)[0]
    return int(index_text)


def _empty_context() -> NativePluginRuleValidationContext:
    return NativePluginRuleValidationContext(
        records=[],
        extracted_items=[],
        record_items_by_index={},
        translation_prefixes=[],
    )


def _json_int(value: JsonObject, field_name: str, label: str) -> int:
    field_value = value[field_name]
    if not isinstance(field_value, int):
        raise TypeError(f"{label}.{field_name} 必须是整数")
    return field_value


def _json_str(value: JsonObject, field_name: str, label: str) -> str:
    field_value = value[field_name]
    if not isinstance(field_value, str):
        raise TypeError(f"{label}.{field_name} 必须是字符串")
    return field_value


def _json_bool(value: JsonObject, field_name: str, label: str) -> bool:
    field_value = value[field_name]
    if not isinstance(field_value, bool):
        raise TypeError(f"{label}.{field_name} 必须是布尔值")
    return field_value


__all__: list[str] = [
    "NativePluginRuleValidationContext",
    "build_native_plugin_rule_validation_context",
    "build_native_plugin_rule_validation_context_from_import",
    "plugin_rule_import_file_to_native_rules",
    "plugin_rule_records_to_native_rules",
]
