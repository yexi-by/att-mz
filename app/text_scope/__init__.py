"""当前文本范围模型和规则辅助的公共入口。"""

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
    "TextSourceType",
    "WriteBackProbeError",
    "read_fresh_plugin_text_rules",
]
