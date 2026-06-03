"""统一文本范围服务公共入口。"""

from .builder import (
    TextScopeService,
    build_translation_data_map,
    collect_translation_data_paths,
    merge_translation_data_map,
)
from .models import (
    TextScopeEntry,
    TextScopeResult,
    TextScopeRuleHit,
    TextScopeSnapshot,
    TextSourceType,
    WriteBackProbeError,
)
from .plugin_rules import read_fresh_plugin_text_rules

__all__ = [
    "TextScopeEntry",
    "TextScopeResult",
    "TextScopeRuleHit",
    "TextScopeSnapshot",
    "TextScopeService",
    "TextSourceType",
    "WriteBackProbeError",
    "build_translation_data_map",
    "collect_translation_data_paths",
    "merge_translation_data_map",
    "read_fresh_plugin_text_rules",
]
