"""Note 标签规则驱动提取模块。"""

from app.note_tag_text.parser import iter_note_tag_matches
from app.note_tag_text.sources import collect_note_tag_sources, note_file_pattern_matches
from app.rmmz.schema import (
    GameData,
    NoteTagTextRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rmmz.text_rules import TextRules, get_default_text_rules
from app.rmmz.text_protocol import normalize_visible_text_for_extraction


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
        all_sources = collect_note_tag_sources(game_data=self.game_data)
        for rule_record in self.rule_records:
            matching_sources = [
                source
                for source in all_sources
                if note_file_pattern_matches(file_name=source.file_name, file_pattern=rule_record.file_name)
            ]
            if not matching_sources:
                raise RuntimeError(
                    f"Note 标签规则已过期: {rule_record.file_name} 没有命中当前游戏 note 字段，请重新导出并导入 Note 标签规则"
                )
            tag_names = set(rule_record.tag_names)
            tag_hit_counts = {tag_name: 0 for tag_name in rule_record.tag_names}
            for source in matching_sources:
                matches_by_tag: dict[str, list[str]] = {}
                for match in iter_note_tag_matches(source.note_text):
                    if match.tag_name not in tag_names or match.value_span is None:
                        continue
                    matches_by_tag.setdefault(match.tag_name, []).append(match.value)

                for tag_name in rule_record.tag_names:
                    values = matches_by_tag.get(tag_name, [])
                    if not values:
                        continue
                    tag_hit_counts[tag_name] += len(values)
                    if len(values) > 1:
                        raise ValueError(
                            f"{source.location_prefix}/note/{tag_name} 标签重复，无法生成唯一定位路径"
                        )
                    normalized_value = normalize_visible_text_for_extraction(
                        values[0],
                        plain_text_normalizer=self.text_rules.normalize_extraction_text,
                    )
                    if not self.text_rules.should_translate_source_text(normalized_value):
                        continue
                    location_path = f"{source.location_prefix}/note/{tag_name}"
                    if location_path in seen_location_paths:
                        continue
                    seen_location_paths.add(location_path)
                    translation_data = translation_data_map.setdefault(
                        source.file_name,
                        TranslationData(display_name=None, translation_items=[]),
                    )
                    translation_data.translation_items.append(
                        TranslationItem(
                            location_path=location_path,
                            item_type="short_text",
                            original_lines=[normalized_value],
                        )
                    )
            _ensure_note_tag_rule_has_current_hits(
                rule_record=rule_record,
                tag_hit_counts=tag_hit_counts,
            )
        return translation_data_map


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
