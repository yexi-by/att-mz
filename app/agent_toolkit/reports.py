"""Agent 工具包报告模型。"""

import json
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.rmmz.text_rules import JsonObject

type AgentReportStatus = Literal["ok", "warning", "error"]


class AgentIssue(BaseModel):
    """诊断报告中的单条问题。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    code: str
    message: str


class AgentReport(BaseModel):
    """供终端和外部 Agent 使用的统一报告结构。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: AgentReportStatus
    errors: list[AgentIssue] = Field(default_factory=list)
    warnings: list[AgentIssue] = Field(default_factory=list)
    summary: JsonObject = Field(default_factory=dict)
    details: JsonObject = Field(default_factory=dict)

    @classmethod
    def from_parts(
        cls,
        *,
        errors: list[AgentIssue],
        warnings: list[AgentIssue],
        summary: JsonObject,
        details: JsonObject,
    ) -> "AgentReport":
        """根据错误和告警集合构造报告状态。"""
        errors = _deduplicate_issues(errors)
        warnings = _deduplicate_issues(warnings)
        if errors:
            status: AgentReportStatus = "error"
        elif warnings:
            status = "warning"
        else:
            status = "ok"
        return cls(
            status=status,
            errors=errors,
            warnings=warnings,
            summary=summary,
            details=details,
        )

    def to_json_text(self) -> str:
        """序列化为稳定的 UTF-8 JSON 文本。"""
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2)


def issue(code: str, message: str) -> AgentIssue:
    """创建报告问题对象。"""
    return AgentIssue(code=code, message=message)


def _deduplicate_issues(items: list[AgentIssue]) -> list[AgentIssue]:
    """按稳定 code/message 去掉重复报告项，保留首次出现顺序。"""
    deduplicated_items: list[AgentIssue] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in items:
        key = (item.code, item.message)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduplicated_items.append(item)
    return deduplicated_items


__all__: list[str] = [
    "AgentIssue",
    "AgentReport",
    "AgentReportStatus",
    "issue",
]
