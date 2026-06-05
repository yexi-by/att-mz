"""统一文本范围构建服务。"""

from __future__ import annotations

from app.event_command_text import EventCommandTextExtraction
from app.note_tag_text import NoteTagTextExtraction
from app.nonstandard_data import (
    NONSTANDARD_DATA_LOCATION_PREFIX,
    NonstandardDataTextExtraction,
    NonstandardDataTextExtractionContext,
    build_nonstandard_data_text_extraction_context,
)
from app.persistence import TargetGameSession
from app.plugin_text import PluginTextExtraction
from app.plugin_source_text import (
    PluginSourceTextExtraction,
    build_native_plugin_source_scan,
    filter_fresh_plugin_source_text_rules,
)
from app.plugin_source_text.models import PluginSourceScan
from app.rmmz import DataTextExtraction
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    GameData,
    MvVirtualNameboxRuleRecord,
    NoteTagTextRuleRecord,
    NonstandardDataTextRuleRecord,
    PLUGINS_FILE_NAME,
    PluginSourceTextRuleRecord,
    PluginTextRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rmmz.text_rules import TextRules

from .models import TextScopeEntry, TextScopeResult, TextScopeRuleHit, TextSourceType, WriteBackProbeError
from .plugin_rules import read_fresh_plugin_text_rules
from .rule_hits import (
    collect_event_command_rule_hits,
    collect_nonstandard_data_rule_hits,
    collect_note_tag_rule_hits,
    collect_plugin_rule_hits,
)
from .write_probe import collect_write_back_probe_reasons


class TextScopeService:
    """构建当前游戏统一文本范围。"""

    async def build(
        self,
        *,
        session: TargetGameSession,
        game_data: GameData,
        text_rules: TextRules,
        translated_items: list[TranslationItem] | None = None,
        include_write_probe: bool = False,
        plugin_source_scan: PluginSourceScan | None = None,
    ) -> TextScopeResult:
        """读取规则、展开命中项，并按需生成写入可行性信息。"""
        plugin_rules, stale_plugin_rules = await read_fresh_plugin_text_rules(
            session=session,
            game_data=game_data,
        )
        event_rules = await session.read_event_command_text_rules()
        raw_nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
        nonstandard_data_context = build_nonstandard_data_text_extraction_context(
            game_data=game_data,
            rule_records=raw_nonstandard_data_rules,
            skip_missing_files=True,
        )
        nonstandard_data_rules = _fresh_nonstandard_data_rules_for_scope(
            game_data=game_data,
            text_rules=text_rules,
            records=raw_nonstandard_data_rules,
            nonstandard_data_context=nonstandard_data_context,
        )
        plugin_source_rule_records = await session.read_plugin_source_text_rules()
        resolved_plugin_source_scan = plugin_source_scan if plugin_source_rule_records else None
        if plugin_source_rule_records and resolved_plugin_source_scan is None:
            resolved_plugin_source_scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
        plugin_source_rules, _stale_plugin_source_rules = filter_fresh_plugin_source_text_rules(
            game_data=game_data,
            rule_records=plugin_source_rule_records,
            text_rules=text_rules,
            scan=resolved_plugin_source_scan,
        )
        note_tag_rules = await session.read_note_tag_text_rules()
        mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
        if translated_items is None:
            translated_items = await session.read_translated_items()
        translated_paths = {item.location_path for item in translated_items}

        translation_data_map = build_translation_data_map(
            game_data=game_data,
            text_rules=text_rules,
            plugin_rules=plugin_rules,
            event_rules=event_rules,
            plugin_source_rules=plugin_source_rules,
            plugin_source_scan=resolved_plugin_source_scan,
            note_tag_rules=note_tag_rules,
            nonstandard_data_rules=nonstandard_data_rules,
            nonstandard_data_context=nonstandard_data_context,
            mv_virtual_namebox_rules=mv_virtual_namebox_rules,
        )
        active_items = {
            item.location_path: item
            for translation_data in translation_data_map.values()
            for item in translation_data.translation_items
        }
        write_back_probe_error = ""
        write_back_reasons: dict[str, str] = {}
        if include_write_probe:
            try:
                write_back_reasons = collect_write_back_probe_reasons(
                    game_data=game_data,
                    active_items=list(active_items.values()),
                    plugin_source_scan=resolved_plugin_source_scan,
                )
            except WriteBackProbeError as error:
                write_back_reasons = {}
                write_back_probe_error = str(error)
        entries = [
            _active_item_to_scope_entry(
                item=item,
                translated_paths=translated_paths,
                write_back_reason=write_back_reasons.get(item.location_path, ""),
            )
            for item in active_items.values()
        ]

        rule_hits = [
            *collect_plugin_rule_hits(
                game_data=game_data,
                plugin_rules=plugin_rules,
            ),
            *collect_event_command_rule_hits(
                game_data=game_data,
                event_rules=event_rules,
            ),
            *collect_note_tag_rule_hits(
                game_data=game_data,
                note_tag_rules=note_tag_rules,
                text_rules=text_rules,
            ),
            *collect_nonstandard_data_rule_hits(
                game_data=game_data,
                nonstandard_data_rules=nonstandard_data_rules,
                text_rules=text_rules,
                nonstandard_data_context=nonstandard_data_context,
            ),
        ]
        active_paths = set(active_items)
        for hit in rule_hits:
            if hit.location_path in active_paths:
                continue
            entries.append(
                _rule_hit_to_inactive_scope_entry(
                    hit=hit,
                    translated_paths=translated_paths,
                    text_rules=text_rules,
                )
            )

        entries.sort(key=lambda item: item.location_path)
        return TextScopeResult(
            translation_data_map=translation_data_map,
            entries=entries,
            stale_plugin_rules=stale_plugin_rules,
            write_back_probe_error=write_back_probe_error,
            write_back_probe_enabled=include_write_probe,
        )


def build_translation_data_map(
    *,
    game_data: GameData,
    text_rules: TextRules,
    plugin_rules: list[PluginTextRuleRecord],
    event_rules: list[EventCommandTextRuleRecord],
    plugin_source_rules: list[PluginSourceTextRuleRecord],
    note_tag_rules: list[NoteTagTextRuleRecord],
    nonstandard_data_rules: list[NonstandardDataTextRuleRecord],
    mv_virtual_namebox_rules: list[MvVirtualNameboxRuleRecord] | None = None,
    plugin_source_scan: PluginSourceScan | None = None,
    nonstandard_data_context: NonstandardDataTextExtractionContext | None = None,
) -> dict[str, TranslationData]:
    """按同一组规则构建当前可翻译文本集合。"""
    translation_data_map = DataTextExtraction(
        game_data,
        text_rules,
        mv_virtual_namebox_rule_records=mv_virtual_namebox_rules,
    ).extract_all_text()
    merge_translation_data_map(
        translation_data_map,
        EventCommandTextExtraction(game_data, event_rules, text_rules).extract_all_text(),
    )
    merge_translation_data_map(
        translation_data_map,
        PluginTextExtraction(game_data, plugin_rules, text_rules).extract_all_text(),
    )
    merge_translation_data_map(
        translation_data_map,
        PluginSourceTextExtraction(
            game_data,
            plugin_source_rules,
            text_rules,
            scan=plugin_source_scan,
        ).extract_all_text(),
    )
    merge_translation_data_map(
        translation_data_map,
        NoteTagTextExtraction(game_data, note_tag_rules, text_rules).extract_all_text(),
    )
    merge_translation_data_map(
        translation_data_map,
        NonstandardDataTextExtraction(
            game_data,
            nonstandard_data_rules,
            text_rules,
            context=nonstandard_data_context,
        ).extract_all_text(),
    )
    return translation_data_map


def merge_translation_data_map(
    target: dict[str, TranslationData],
    source: dict[str, TranslationData],
) -> None:
    """合并两个文件维度翻译数据映射。"""
    for file_name, translation_data in source.items():
        existing_data = target.get(file_name)
        if existing_data is None:
            target[file_name] = translation_data
            continue
        existing_data.translation_items.extend(translation_data.translation_items)


def collect_translation_data_paths(translation_data_map: dict[str, TranslationData]) -> set[str]:
    """收集翻译数据中的全部定位路径。"""
    return {
        item.location_path
        for translation_data in translation_data_map.values()
        for item in translation_data.translation_items
    }


def _active_item_to_scope_entry(
    *,
    item: TranslationItem,
    translated_paths: set[str],
    write_back_reason: str,
) -> TextScopeEntry:
    """把当前可翻译条目转换成文本清单记录。"""
    source_type = _source_type_from_location_path(item.location_path)
    can_write_back = not write_back_reason
    return TextScopeEntry(
        location_path=item.location_path,
        source_type=source_type,
        rule_source=_rule_source_label(source_type),
        item_type=item.item_type,
        original_lines=[line for line in item.original_lines],
        role=item.role,
        enters_translation=True,
        can_save_translation=True,
        can_write_back=can_write_back,
        translated=item.location_path in translated_paths,
        cannot_process_reason=write_back_reason,
    )


def _rule_hit_to_inactive_scope_entry(
    *,
    hit: TextScopeRuleHit,
    translated_paths: set[str],
    text_rules: TextRules,
) -> TextScopeEntry:
    """把未进入翻译集合的规则命中项转换成文本清单记录。"""
    normalized_text = text_rules.normalize_extraction_text(hit.original_text)
    if not normalized_text:
        reason = "规则命中的是空文本"
    elif not text_rules.should_translate_source_text(normalized_text):
        reason = "规则命中的字符串不包含当前源语言字符"
    else:
        reason = "规则命中项没有进入统一文本清单"
    return TextScopeEntry(
        location_path=hit.location_path,
        source_type=hit.source_type,
        rule_source=hit.rule_source,
        item_type="short_text",
        original_lines=[normalized_text],
        role=None,
        enters_translation=False,
        can_save_translation=False,
        can_write_back=False,
        translated=hit.location_path in translated_paths,
        cannot_process_reason=reason,
    )


def _source_type_from_location_path(location_path: str) -> TextSourceType:
    """根据定位路径判断文本来源类型。"""
    if location_path.startswith(f"{PLUGINS_FILE_NAME}/"):
        return "plugin_parameter"
    if location_path.startswith("js/plugins/"):
        return "plugin_source"
    if location_path.startswith(f"{NONSTANDARD_DATA_LOCATION_PREFIX}/"):
        return "nonstandard_data"
    if "/note/" in location_path:
        return "note_tag"
    if "/parameters/" in location_path:
        return "event_command"
    return "standard_data"


def _rule_source_label(source_type: TextSourceType) -> str:
    """返回当前来源对应的规则来源说明。"""
    if source_type == "plugin_parameter":
        return "插件参数规则"
    if source_type == "plugin_source":
        return "插件源码规则"
    if source_type == "event_command":
        return "事件指令规则"
    if source_type == "note_tag":
        return "Note 标签规则"
    if source_type == "nonstandard_data":
        return "非标准 data 文件文本规则"
    return "RPG Maker 标准数据结构"


def _fresh_nonstandard_data_rules_for_scope(
    *,
    game_data: GameData,
    text_rules: TextRules,
    records: list[NonstandardDataTextRuleRecord],
    nonstandard_data_context: NonstandardDataTextExtractionContext,
) -> list[NonstandardDataTextRuleRecord]:
    """文本清单构建时跳过已知过期的非标准 data 规则，由 workflow gate 报告原因。"""
    fresh_records: list[NonstandardDataTextRuleRecord] = []
    for record in records:
        try:
            _ = NonstandardDataTextExtraction(
                game_data=game_data,
                rule_records=[record],
                text_rules=text_rules,
                context=nonstandard_data_context,
            ).collect_rule_hits()
        except RuntimeError:
            continue
        fresh_records.append(record)
    return fresh_records
