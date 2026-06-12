"""写回阶段字体替换公共入口。"""

from .files import read_plugins_js_file, resolve_replacement_font_path
from .models import OriginFontRestoreSummary
from .references import collect_replacement_font_names
from .restore import restore_font_references_from_origin_backups

__all__: list[str] = [
    "OriginFontRestoreSummary",
    "collect_replacement_font_names",
    "read_plugins_js_file",
    "resolve_replacement_font_path",
    "restore_font_references_from_origin_backups",
]
