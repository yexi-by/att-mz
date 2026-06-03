"""应用层公共导出入口。

包级导出只在被直接访问时加载，避免原生适配层导入应用层子模块时触发 handler
循环导入。
"""

from typing import cast

_HANDLER_EXPORTS = {
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
    """按需返回 handler 中的历史包级导出。"""
    if name not in _HANDLER_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import handler

    value = cast(object, getattr(handler, name))
    return value
