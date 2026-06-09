"""应用层当前公开入口的懒加载导出。"""

from typing import cast

_APPLICATION_EXPORTS = {
    "EventCommandJsonExportSummary",
    "EventCommandRuleImportSummary",
    "PluginJsonExportSummary",
    "PluginRuleImportSummary",
    "TerminologyImportSummary",
    "TerminologyWriteSummary",
    "TextTranslationSummary",
    "TranslationHandler",
}


def __getattr__(name: str) -> object:
    """按需返回 handler 中的当前公开入口。"""
    if name not in _APPLICATION_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import handler

    value = cast(object, getattr(handler, name))
    return value
