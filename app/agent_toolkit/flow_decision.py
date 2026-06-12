"""统一流程裁决纯逻辑。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.agent_toolkit.reports import AgentReport
from app.rmmz.text_rules import JsonObject, JsonValue

type FlowDecisionResult = Literal[
    "blocked",
    "ready_to_translate",
    "should_stop_retrying",
    "ready_for_manual_fix",
    "ready_to_write_back",
    "needs_runtime_audit",
]
type FlowStage = Literal[
    "environment",
    "prepare_rules",
    "full_translation",
    "retry_diagnosis",
    "manual_fix",
    "before_write_back",
    "runtime_audit",
]
type FlowBlockingCategory = Literal[
    "none",
    "environment",
    "rules",
    "terminology",
    "translation_quality",
    "translation_retry",
    "write_back_fact",
    "runtime",
]

RULE_ERROR_CODES = {
    "plugin_rules",
    "event_command_rules",
    "note_tag_rules",
    "placeholder_rules",
    "structured_placeholder_rules",
    "mv_virtual_namebox_rules",
    "plugin_source_review_incomplete",
    "placeholder_rules_invalid",
    "structured_placeholder_rules_invalid",
    "mv_virtual_namebox_rules_invalid",
}
TERMINOLOGY_ERROR_CODES = {
    "terminology_missing",
    "terminology_empty_translation",
    "terminology_invalid",
}
WRITE_BACK_RISK_CODES = {
    "placeholder_risk",
    "text_structure",
    "write_back_protocol",
    "write_back_gate",
    "coverage_unwritable",
}
QUALITY_ERROR_CODES = {
    "translation_quality_errors",
    "source_residual",
    "overwide_line",
}


@dataclass(frozen=True, slots=True)
class FlowDecision:
    """Agent 下一步流程裁决。"""

    result: FlowDecisionResult
    stage: FlowStage
    can_continue: bool
    blocking_category: FlowBlockingCategory
    reason: str
    next_command: str
    write_back_probe_executed: bool
    write_back_probe_mode: str
    requires_user_authorization: bool = False

    def summary_fields(self) -> JsonObject:
        """转换成 `AgentReport.summary` 的稳定字段。"""
        return {
            "flow_decision": self.result,
            "flow_stage": self.stage,
            "flow_can_continue": self.can_continue,
            "flow_blocking_category": self.blocking_category,
            "flow_reason": self.reason,
            "flow_next_command": self.next_command,
            "flow_write_back_probe_executed": self.write_back_probe_executed,
            "flow_write_back_probe_mode": self.write_back_probe_mode,
            "flow_requires_user_authorization": self.requires_user_authorization,
        }

    def detail_fields(self) -> JsonObject:
        """转换成 `AgentReport.details.flow_decision` 的稳定字段。"""
        return {
            "result": self.result,
            "stage": self.stage,
            "can_continue": self.can_continue,
            "blocking_category": self.blocking_category,
            "reason": self.reason,
            "next_command": self.next_command,
            "write_back_probe_executed": self.write_back_probe_executed,
            "write_back_probe_mode": self.write_back_probe_mode,
            "requires_user_authorization": self.requires_user_authorization,
        }


def build_flow_decision(
    *,
    base_error_codes: set[str],
    base_warning_codes: set[str],
    quality_report: AgentReport | None,
    translation_status: AgentReport | None,
    recent_runs: list[Mapping[str, JsonValue]],
) -> FlowDecision:
    """从已有报告归并出一个 Agent 可执行的流程裁决。"""
    _ = base_warning_codes
    quality_codes = {error.code for error in quality_report.errors} if quality_report is not None else set()
    quality_summary = quality_report.summary if quality_report is not None else {}
    status_summary = translation_status.summary if translation_status is not None else {}
    write_probe_executed = _bool(quality_summary.get("write_back_probe_executed"))
    write_probe_mode = _str(quality_summary.get("write_back_probe_mode"))

    if base_error_codes:
        return FlowDecision(
            result="blocked",
            stage="environment",
            can_continue=False,
            blocking_category="environment",
            reason="环境、配置或目标游戏基础检查没通过",
            next_command="doctor --game <游戏标题> --no-check-llm",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    if quality_report is None:
        return FlowDecision(
            result="blocked",
            stage="prepare_rules",
            can_continue=False,
            blocking_category="rules",
            reason="缺少完整质量和写回级检查结果",
            next_command="quality-report --game <游戏标题> --include-write-probe",
            write_back_probe_executed=False,
            write_back_probe_mode="not_run",
        )

    if quality_codes & RULE_ERROR_CODES:
        return _blocked(
            "rules",
            "规则或候选审查没通过",
            "doctor --game <游戏标题> --no-check-llm",
            write_probe_executed,
            write_probe_mode,
        )
    if quality_codes & TERMINOLOGY_ERROR_CODES:
        return _blocked(
            "terminology",
            "术语表与当前规则或写回需求不一致",
            "export-terminology --game <游戏标题> --output-dir <输出目录>",
            write_probe_executed,
            write_probe_mode,
        )
    if quality_codes & WRITE_BACK_RISK_CODES:
        return _blocked(
            "write_back_fact",
            "写回级只读检查发现控制符、结构或当前文本事实风险",
            "quality-report --game <游戏标题> --include-write-probe",
            write_probe_executed,
            write_probe_mode,
        )

    pending_count = _int(quality_summary.get("pending_count", status_summary.get("pending_count", 0)))
    quality_error_count = _int(
        quality_summary.get("quality_error_count", status_summary.get("quality_error_count", 0))
    )
    if _should_stop_retrying(recent_runs=recent_runs, quality_error_count=quality_error_count):
        return FlowDecision(
            result="should_stop_retrying",
            stage="retry_diagnosis",
            can_continue=False,
            blocking_category="translation_retry",
            reason="最近多轮正文翻译下降很小，继续重试收益低",
            next_command="quality-report --game <游戏标题> --include-write-probe",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    if quality_error_count > 0 or quality_codes & QUALITY_ERROR_CODES:
        return FlowDecision(
            result="ready_for_manual_fix",
            stage="manual_fix",
            can_continue=True,
            blocking_category="translation_quality",
            reason="剩余质量问题适合导出修复表或待补译表精确处理",
            next_command="export-quality-fix-template --game <游戏标题> --output <输出文件>",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    if pending_count > 0:
        return FlowDecision(
            result="ready_to_translate",
            stage="full_translation",
            can_continue=True,
            blocking_category="none",
            reason=f"当前还有 {pending_count} 条文本没成功保存译文，可以继续正文翻译",
            next_command="translate --game <游戏标题>",
            write_back_probe_executed=write_probe_executed,
            write_back_probe_mode=write_probe_mode,
        )
    return FlowDecision(
        result="ready_to_write_back",
        stage="before_write_back",
        can_continue=True,
        blocking_category="none",
        reason="当前可写范围没有 pending、质量错误或写回级风险",
        next_command="write-back --game <游戏标题>",
        write_back_probe_executed=write_probe_executed,
        write_back_probe_mode=write_probe_mode,
        requires_user_authorization=True,
    )


def _blocked(
    category: FlowBlockingCategory,
    reason: str,
    next_command: str,
    write_probe_executed: bool,
    write_probe_mode: str,
) -> FlowDecision:
    """生成阻断裁决。"""
    return FlowDecision(
        result="blocked",
        stage="prepare_rules",
        can_continue=False,
        blocking_category=category,
        reason=reason,
        next_command=next_command,
        write_back_probe_executed=write_probe_executed,
        write_back_probe_mode=write_probe_mode,
    )


def _should_stop_retrying(*, recent_runs: list[Mapping[str, JsonValue]], quality_error_count: int) -> bool:
    """根据最近几轮变化判断继续重试是否已经低收益。"""
    if len(recent_runs) < 3 or quality_error_count <= 0:
        return False
    newest = recent_runs[0]
    oldest = recent_runs[min(2, len(recent_runs) - 1)]
    newest_pending = _int(newest.get("pending_count"))
    oldest_pending = _int(oldest.get("pending_count"))
    newest_success = _int(newest.get("success_count"))
    if oldest_pending <= 0:
        return False
    low_latest_success = newest_success <= max(50, newest_pending // 20)
    quality_errors_still_dominate = quality_error_count >= max(20, newest_pending // 2)
    if low_latest_success and quality_errors_still_dominate:
        return True
    improvement = oldest_pending - newest_pending
    return improvement <= max(10, oldest_pending // 20) and newest_success <= max(10, newest_pending // 20)


def _int(value: object) -> int:
    """把 JSON 数字收窄成非 bool 整数。"""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _bool(value: object) -> bool:
    """把 JSON 值收窄成 bool。"""
    return isinstance(value, bool) and value


def _str(value: object) -> str:
    """把 JSON 值收窄成字符串。"""
    return value if isinstance(value, str) else ""
