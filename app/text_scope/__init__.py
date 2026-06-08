"""统一文本范围服务公共入口。

`TextScopeService` 和 `build_translation_data_map` 的导出只服务 legacy 测试、
写回契约测试和少量未迁移诊断工具；已迁移生产命令不得通过这里重建
Python full scope，应读取 text fact v2 或 Rust native storage。
"""

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
