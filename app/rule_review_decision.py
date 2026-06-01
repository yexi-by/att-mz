"""规则候选覆盖、确认状态和阶段决策的内部权威模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.persistence import TargetGameSession
from app.rmmz.json_types import JsonArray, JsonObject, JsonValue
from app.rule_review import RuleReviewDomain

type RuleReviewStage = Literal[
    "workspace_validate",
    "rule_import",
    "workflow_gate",
    "manual_import",
    "doctor",
    "text_scope",
    "audit_coverage",
    "quality_report",
    "write_back",
]
type RuleReviewSeverity = Literal["ok", "warning", "error"]
type RuleConfirmationStatus = Literal[
    "not_needed",
    "missing",
    "confirmed",
    "confirmed_legacy_hash",
    "stale",
]
type ReportDetailMode = Literal["full", "sampled"]


@dataclass(frozen=True, slots=True)
class WorkflowGateIssue:
    """单个会阻断翻译或写入的流程前置错误。"""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RuleCoverageResult:
    """候选扫描的完整内部结果，业务逻辑只能消费此对象而不是报告 JSON。"""

    rule_domain: RuleReviewDomain
    scope_hash: str
    rule_count: int
    candidate_count: int
    covered_count: int
    uncovered_count: int
    candidates: JsonArray
    sample_limit: int = 100

    def full_details(self) -> JsonObject:
        """渲染完整候选明细。"""
        return {
            "detail_mode": "full",
            "candidates": {
                "count": len(self.candidates),
                "items": [item for item in self.candidates],
            },
        }

    def sampled_details(self) -> JsonObject:
        """渲染采样候选明细。"""
        effective_limit = max(0, self.sample_limit)
        return {
            "detail_mode": "sampled",
            "candidates": {
                "count": len(self.candidates),
                "samples": [item for item in self.candidates[:effective_limit]],
                "omitted_count": max(0, len(self.candidates) - effective_limit),
            },
        }

    def summary(self, *, detail_mode: ReportDetailMode = "full") -> JsonObject:
        """渲染报告 summary。"""
        return {
            "report_detail_mode": detail_mode,
            "rule_count": self.rule_count,
            "candidate_count": self.candidate_count,
            "covered_count": self.covered_count,
            "uncovered_count": self.uncovered_count,
        }


@dataclass(frozen=True, slots=True)
class RuleReviewDecision:
    """规则候选在指定阶段的统一审查决策。"""

    rule_domain: RuleReviewDomain
    stage: RuleReviewStage
    severity: RuleReviewSeverity
    code: str
    message: str
    scope_hash: str
    confirmation_status: RuleConfirmationStatus
    reviewed_empty: bool | None
    uncovered_count: int
    rule_count: int
    samples: JsonArray

    def to_issue(self) -> WorkflowGateIssue:
        """转换成现有流程问题对象。"""
        return WorkflowGateIssue(code=self.code, message=self.message)


async def build_rule_review_decision(
    *,
    session: TargetGameSession,
    coverage: RuleCoverageResult,
    stage: RuleReviewStage,
    unreviewed_code: str,
    unreviewed_message: str,
    reviewed_code: str,
    reviewed_message: str,
    custom_rules_supplied: bool = False,
    legacy_scope_hashes: tuple[str, ...] = (),
) -> RuleReviewDecision:
    """按统一候选覆盖结果和数据库确认状态生成阶段决策。"""
    confirmation_status, reviewed_empty = await read_confirmation_status(
        session=session,
        rule_domain=coverage.rule_domain,
        scope_hash=coverage.scope_hash,
        legacy_scope_hashes=legacy_scope_hashes,
    )
    samples = [item for item in coverage.candidates[: coverage.sample_limit]]
    if coverage.uncovered_count <= 0:
        return RuleReviewDecision(
            rule_domain=coverage.rule_domain,
            stage=stage,
            severity="ok",
            code="",
            message="",
            scope_hash=coverage.scope_hash,
            confirmation_status="not_needed",
            reviewed_empty=reviewed_empty,
            uncovered_count=coverage.uncovered_count,
            rule_count=coverage.rule_count,
            samples=samples,
        )
    if confirmation_status in {"confirmed", "confirmed_legacy_hash"} and not custom_rules_supplied:
        message = reviewed_message
        code = reviewed_code
        if confirmation_status == "confirmed_legacy_hash":
            code = f"{reviewed_code}_legacy_hash"
            message = f"{reviewed_message}；当前数据库使用旧版截断候选确认 hash，本次按兼容规则放行，重新导入规则后会升级为完整 hash"
        return RuleReviewDecision(
            rule_domain=coverage.rule_domain,
            stage=stage,
            severity="warning",
            code=code,
            message=message,
            scope_hash=coverage.scope_hash,
            confirmation_status=confirmation_status,
            reviewed_empty=reviewed_empty,
            uncovered_count=coverage.uncovered_count,
            rule_count=coverage.rule_count,
            samples=samples,
        )
    return RuleReviewDecision(
        rule_domain=coverage.rule_domain,
        stage=stage,
        severity="error",
        code=unreviewed_code,
        message=unreviewed_message,
        scope_hash=coverage.scope_hash,
        confirmation_status=confirmation_status,
        reviewed_empty=reviewed_empty,
        uncovered_count=coverage.uncovered_count,
        rule_count=coverage.rule_count,
        samples=samples,
    )


async def build_empty_rule_review_decision(
    *,
    session: TargetGameSession,
    rule_domain: RuleReviewDomain,
    stage: RuleReviewStage,
    scope_hash: str,
    label: str,
    missing_code: str,
    stale_code: str,
    missing_severity: RuleReviewSeverity,
    stale_severity: RuleReviewSeverity,
    missing_message: str | None = None,
    stale_message: str | None = None,
    legacy_scope_hashes: tuple[str, ...] = (),
) -> RuleReviewDecision:
    """按统一规则生成空规则确认状态决策。"""
    confirmation_status, reviewed_empty = await read_confirmation_status(
        session=session,
        rule_domain=rule_domain,
        scope_hash=scope_hash,
        legacy_scope_hashes=legacy_scope_hashes,
    )
    if confirmation_status in {"confirmed", "confirmed_legacy_hash"} and reviewed_empty is True:
        code = ""
        message = ""
        severity: RuleReviewSeverity = "ok"
        if confirmation_status == "confirmed_legacy_hash":
            code = f"{rule_domain}_legacy_empty_confirmation"
            message = f"{label}空规则确认使用旧版 hash，本阶段按兼容规则放行，重新导入规则后会升级为完整 hash"
            severity = "warning"
        return RuleReviewDecision(
            rule_domain=rule_domain,
            stage=stage,
            severity=severity,
            code=code,
            message=message,
            scope_hash=scope_hash,
            confirmation_status=confirmation_status,
            reviewed_empty=reviewed_empty,
            uncovered_count=0,
            rule_count=0,
            samples=[],
        )
    if confirmation_status == "stale":
        return RuleReviewDecision(
            rule_domain=rule_domain,
            stage=stage,
            severity=stale_severity,
            code=stale_code,
            message=stale_message or f"{label}曾确认为空，但当前游戏内容已经变化，请重新扫描并导入规则",
            scope_hash=scope_hash,
            confirmation_status=confirmation_status,
            reviewed_empty=reviewed_empty,
            uncovered_count=0,
            rule_count=0,
            samples=[],
        )
    return RuleReviewDecision(
        rule_domain=rule_domain,
        stage=stage,
        severity=missing_severity,
        code=missing_code,
        message=missing_message or f"{label}为空且没有显式确认当前游戏没有对应规则，检查没通过，不能继续",
        scope_hash=scope_hash,
        confirmation_status=confirmation_status,
        reviewed_empty=reviewed_empty,
        uncovered_count=0,
        rule_count=0,
        samples=[],
    )


async def read_confirmation_status(
    *,
    session: TargetGameSession,
    rule_domain: RuleReviewDomain,
    scope_hash: str,
    legacy_scope_hashes: tuple[str, ...] = (),
) -> tuple[RuleConfirmationStatus, bool | None]:
    """读取当前规则域确认状态，并兼容旧 hash。"""
    state = await session.read_rule_review_state(rule_domain=rule_domain)
    if state is None:
        return "missing", None
    if state.scope_hash == scope_hash:
        return "confirmed", state.reviewed_empty
    if state.scope_hash in legacy_scope_hashes:
        return "confirmed_legacy_hash", state.reviewed_empty
    return "stale", state.reviewed_empty


def report_array_full(items: JsonArray) -> JsonObject:
    """渲染完整数组报告节点。"""
    return {"count": len(items), "items": [item for item in items]}


def report_array_sampled(items: JsonArray, *, sample_limit: int) -> JsonObject:
    """渲染采样数组报告节点。"""
    effective_limit = max(0, sample_limit)
    return {
        "count": len(items),
        "samples": [item for item in items[:effective_limit]],
        "omitted_count": max(0, len(items) - effective_limit),
    }


def detail_items_from_full_array(value: JsonValue, *, context: str) -> JsonArray:
    """读取完整报告数组节点，仅允许 full/items 形态。"""
    if not isinstance(value, dict):
        raise TypeError(f"{context} 必须是完整数组报告对象")
    items = value.get("items")
    if not isinstance(items, list):
        raise TypeError(f"{context}.items 必须是完整数组")
    return [item for item in items]


__all__: list[str] = [
    "ReportDetailMode",
    "RuleConfirmationStatus",
    "RuleCoverageResult",
    "RuleReviewDecision",
    "RuleReviewSeverity",
    "RuleReviewStage",
    "WorkflowGateIssue",
    "build_empty_rule_review_decision",
    "build_rule_review_decision",
    "detail_items_from_full_array",
    "read_confirmation_status",
    "report_array_full",
    "report_array_sampled",
]
