"""写回阶段字体替换公共入口。"""

from .service import (
    FontReplacementSummary,
    OriginFontRestoreSummary,
    apply_font_replacement,
    build_empty_font_replacement_summary,
    collect_replacement_font_names,
    read_plugins_js_file,
    resolve_replacement_font_path,
    restore_font_references_from_origin_backups,
)

__all__: list[str] = [
    "FontReplacementSummary",
    "OriginFontRestoreSummary",
    "apply_font_replacement",
    "build_empty_font_replacement_summary",
    "collect_replacement_font_names",
    "read_plugins_js_file",
    "resolve_replacement_font_path",
    "restore_font_references_from_origin_backups",
]
