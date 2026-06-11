"""Note 标签规则驱动提取模块。"""

from app.note_tag_text.sources import note_file_pattern_matches
from app.rmmz.schema import (
    NoteTagTextRuleRecord,
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


__all__: list[str] = ["note_tag_location_path_matches_rule"]
