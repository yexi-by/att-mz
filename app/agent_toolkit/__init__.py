"""Agent 自主翻译工具包服务导出入口。"""

from typing import TYPE_CHECKING

from .placeholder_scan import (
    PlaceholderCandidate,
    count_uncovered_candidates,
    placeholder_candidates_to_details,
    scan_placeholder_candidates,
)
from .reports import AgentIssue, AgentReport, AgentReportStatus

if TYPE_CHECKING:
    from .service import AgentToolkitService


def __getattr__(name: str) -> object:
    """按需加载服务门面，避免子模块导入时触发循环依赖。"""
    if name == "AgentToolkitService":
        from .service import AgentToolkitService

        return AgentToolkitService
    raise AttributeError(name)

__all__: list[str] = [
    "AgentIssue",
    "AgentReport",
    "AgentReportStatus",
    "AgentToolkitService",
    "PlaceholderCandidate",
    "count_uncovered_candidates",
    "placeholder_candidates_to_details",
    "scan_placeholder_candidates",
]
