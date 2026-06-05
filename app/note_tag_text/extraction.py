"""Note 标签规则驱动提取模块。"""

from app.note_tag_text.sources import note_file_pattern_matches
from app.rmmz.schema import (
    GameData,
    NoteTagTextRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules, ensure_json_object, get_default_text_rules


class NoteTagTextExtraction:
    """从标准 `data/*.json` 的 `note` 字段提取已授权标签文本。"""

    def __init__(
        self,
        game_data: GameData,
        rule_records: list[NoteTagTextRuleRecord],
        text_rules: TextRules | None = None,
    ) -> None:
        """初始化 Note 标签文本提取器。"""
        self.game_data: GameData = game_data
        self.rule_records: list[NoteTagTextRuleRecord] = rule_records
        self.text_rules: TextRules = text_rules if text_rules is not None else get_default_text_rules()

    def extract_all_text(self) -> dict[str, TranslationData]:
        """按数据库规则全量提取 Note 标签值。"""
        translation_data_map: dict[str, TranslationData] = {}
        seen_location_paths: set[str] = set()
        source_details, hit_details = collect_native_note_tag_extraction_details(
            game_data=self.game_data,
            text_rules=self.text_rules,
        )
        source_order = _native_note_tag_source_order(source_details)
        hits_by_source_tag = _native_note_tag_hits_by_source_tag(hit_details)
        for rule_record in self.rule_records:
            matching_sources = [
                source
                for source in source_order
                if note_file_pattern_matches(file_name=source[0], file_pattern=rule_record.file_name)
            ]
            if not matching_sources:
                raise RuntimeError(
                    f"Note 标签规则已过期: {rule_record.file_name} 没有命中当前游戏 note 字段，请重新导出并导入 Note 标签规则"
                )
            tag_hit_counts = {tag_name: 0 for tag_name in rule_record.tag_names}
            for file_name, location_prefix in matching_sources:
                for tag_name in rule_record.tag_names:
                    hits = hits_by_source_tag.get((file_name, location_prefix, tag_name), [])
                    if not hits:
                        continue
                    tag_hit_counts[tag_name] += len(hits)
                    if len(hits) > 1:
                        raise ValueError(f"{location_prefix}/note/{tag_name} 标签重复，无法生成唯一定位路径")
                    hit = hits[0]
                    if not hit[2]:
                        continue
                    location_path = hit[0]
                    if location_path in seen_location_paths:
                        continue
                    seen_location_paths.add(location_path)
                    translation_data = translation_data_map.setdefault(
                        file_name,
                        TranslationData(display_name=None, translation_items=[]),
                    )
                    translation_data.translation_items.append(
                        TranslationItem(
                            location_path=location_path,
                            item_type="short_text",
                            original_lines=[hit[1]],
                        )
                    )
            _ensure_note_tag_rule_has_current_hits(
                rule_record=rule_record,
                tag_hit_counts=tag_hit_counts,
            )
        return translation_data_map


def collect_native_note_tag_extraction_details(
    *,
    game_data: GameData,
    text_rules: TextRules,
) -> tuple[JsonArray, JsonArray]:
    """延迟调用 native Note 标签正文提取明细，避免 Note 标签包初始化循环。"""
    from app.native_note_tag_scan import collect_native_note_tag_extraction_details as collect_native

    return collect_native(game_data=game_data, text_rules=text_rules)


def _native_note_tag_source_order(source_details: JsonArray) -> list[tuple[str, str]]:
    """读取 native 来源摘要，保留旧提取路径的来源遍历顺序。"""
    sources: list[tuple[str, str]] = []
    for index, raw_source in enumerate(source_details):
        source = ensure_json_object(raw_source, f"native_note_tag_extraction.source_details[{index}]")
        file_name = _read_note_tag_string(
            source,
            "file_name",
            f"native_note_tag_extraction.source_details[{index}]",
        )
        location_prefix = _read_note_tag_string(
            source,
            "location_prefix",
            f"native_note_tag_extraction.source_details[{index}]",
        )
        sources.append((file_name, location_prefix))
    return sources


def _native_note_tag_hits_by_source_tag(
    hit_details: JsonArray,
) -> dict[tuple[str, str, str], list[tuple[str, str, bool]]]:
    """按真实来源和标签组织 native 逐命中，供规则顺序主循环消费。"""
    hits_by_source_tag: dict[tuple[str, str, str], list[tuple[str, str, bool]]] = {}
    for index, raw_hit in enumerate(hit_details):
        hit = ensure_json_object(raw_hit, f"native_note_tag_extraction.hit_details[{index}]")
        file_name = _read_note_tag_string(hit, "file_name", f"native_note_tag_extraction.hit_details[{index}]")
        tag_name = _read_note_tag_string(hit, "tag_name", f"native_note_tag_extraction.hit_details[{index}]")
        location_path = _read_note_tag_string(
            hit,
            "location_path",
            f"native_note_tag_extraction.hit_details[{index}]",
        )
        original_text = _read_note_tag_string(
            hit,
            "original_text",
            f"native_note_tag_extraction.hit_details[{index}]",
        )
        translatable = hit.get("translatable")
        if not isinstance(translatable, bool):
            raise TypeError(f"native_note_tag_extraction.hit_details[{index}].translatable 必须是布尔值")
        location_prefix = _native_note_tag_location_prefix(location_path, f"native_note_tag_extraction.hit_details[{index}]")
        hits_by_source_tag.setdefault((file_name, location_prefix, tag_name), []).append(
            (location_path, original_text, translatable)
        )
    return hits_by_source_tag


def _native_note_tag_location_prefix(location_path: str, label: str) -> str:
    """从 native 定位路径还原 note 来源前缀。"""
    if "/note/" not in location_path:
        raise ValueError(f"{label}.location_path 必须包含 /note/")
    return location_path.rsplit("/note/", maxsplit=1)[0]


def _read_note_tag_string(value: JsonObject, field_name: str, label: str) -> str:
    """读取 native Note 标签明细中的字符串字段。"""
    field_value = value.get(field_name)
    if not isinstance(field_value, str):
        raise TypeError(f"{label}.{field_name} 必须是字符串")
    return field_value


def _ensure_note_tag_rule_has_current_hits(
    *,
    rule_record: NoteTagTextRuleRecord,
    tag_hit_counts: dict[str, int],
) -> None:
    """确认已保存 Note 标签规则仍然命中当前游戏。"""
    for tag_name in rule_record.tag_names:
        rule_label = f"{rule_record.file_name}/{tag_name}"
        if tag_hit_counts[tag_name] == 0:
            raise RuntimeError(
                f"Note 标签规则已过期: {rule_label} 没有命中当前游戏 Note 标签，请重新导出并导入 Note 标签规则"
            )


def note_tag_location_path_matches_rule(
    *,
    location_path: str,
    rule_record: NoteTagTextRuleRecord,
) -> bool:
    """判断已保存译文定位是否属于指定 Note 标签规则。"""
    parts = location_path.split("/")
    if len(parts) < 3 or parts[-2] != "note":
        return False
    file_name = parts[0]
    tag_name = parts[-1]
    return (
        tag_name in rule_record.tag_names
        and note_file_pattern_matches(file_name=file_name, file_pattern=rule_record.file_name)
    )


__all__: list[str] = ["NoteTagTextExtraction", "note_tag_location_path_matches_rule"]
