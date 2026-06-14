"""统一流程裁决纯逻辑测试。"""

from app.agent_toolkit.flow_decision import build_flow_decision
from app.agent_toolkit.reports import AgentReport, issue
from app.rmmz.text_rules import JsonObject


def _report(
    *,
    errors: list[str] | None = None,
    summary: JsonObject | None = None,
    details: JsonObject | None = None,
) -> AgentReport:
    """构造最小 Agent 报告。"""
    return AgentReport.from_parts(
        errors=[issue(code, code) for code in errors or []],
        warnings=[],
        summary=summary or {},
        details=details or {},
    )


def test_ready_to_translate_when_only_current_pending_remains() -> None:
    """当前只剩 pending 时，裁决应指向继续正文翻译。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            errors=["coverage_missing_translation"],
            summary={
                "pending_count": 12,
                "quality_error_count": 0,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            },
        ),
        translation_status=_report(
            summary={
                "pending_count": 12,
                "run_pending_count": 30,
                "success_count": 18,
                "quality_error_count": 0,
            }
        ),
        recent_runs=[
            {"run_id": "run3", "pending_count": 12, "success_count": 18, "quality_error_count": 0},
            {"run_id": "run2", "pending_count": 30, "success_count": 40, "quality_error_count": 1},
        ],
    )

    assert decision.result == "ready_to_translate"
    assert decision.stage == "full_translation"
    assert decision.can_continue is True
    assert decision.next_command == "translate --game <游戏标题>"


def test_saved_rule_errors_are_rule_blockers_not_environment() -> None:
    """已保存规则损坏属于规则阻断，不能被泛化成环境错误。"""
    decision = build_flow_decision(
        base_error_codes={"placeholder_rules_invalid"},
        base_warning_codes=set(),
        quality_report=None,
        translation_status=None,
        recent_runs=[],
    )

    assert decision.result == "blocked"
    assert decision.stage == "prepare_rules"
    assert decision.blocking_category == "rules"
    assert decision.next_command == "validate-placeholder-rules --game <游戏标题> --input <规则文件>"


def test_should_stop_retrying_when_recent_runs_no_longer_improve() -> None:
    """连续多轮下降很小时，裁决应要求先诊断而不是继续重试。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            errors=["translation_quality_errors"],
            summary={
                "pending_count": 920,
                "quality_error_count": 920,
                "placeholder_risk_count": 734,
                "text_structure_count": 55,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            },
            details={"error_type_counts": {"placeholder_risk": 734, "text_structure": 55}},
        ),
        translation_status=_report(
            summary={"pending_count": 920, "success_count": 33, "quality_error_count": 920}
        ),
        recent_runs=[
            {"run_id": "run9", "pending_count": 920, "success_count": 33, "quality_error_count": 920},
            {"run_id": "run8", "pending_count": 953, "success_count": 173, "quality_error_count": 953},
            {"run_id": "run7", "pending_count": 1126, "success_count": 223, "quality_error_count": 1126},
        ],
    )

    assert decision.result == "should_stop_retrying"
    assert decision.stage == "retry_diagnosis"
    assert decision.can_continue is False
    assert decision.blocking_category == "translation_retry"
    assert decision.next_command == "quality-report --game <游戏标题> --include-write-probe"


def test_quality_errors_do_not_enter_manual_fix_while_pending_can_continue() -> None:
    """还有 pending 且未证明重试低收益时，质量错误不能提前推到手动修复。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            errors=["translation_quality_errors"],
            summary={
                "pending_count": 120,
                "quality_error_count": 8,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            },
        ),
        translation_status=_report(summary={"pending_count": 120, "quality_error_count": 8}),
        recent_runs=[
            {"run_id": "run2", "pending_count": 120, "success_count": 60, "quality_error_count": 8},
            {"run_id": "run1", "pending_count": 180, "success_count": 70, "quality_error_count": 4},
        ],
    )

    assert decision.result == "ready_to_translate"
    assert decision.stage == "full_translation"
    assert decision.next_command == "translate --game <游戏标题>"


def test_ready_to_write_back_when_quality_and_probe_are_clean() -> None:
    """没有 pending、质量错误和写回级风险时，裁决应允许请求写文件授权。"""
    decision = build_flow_decision(
        base_error_codes=set(),
        base_warning_codes=set(),
        quality_report=_report(
            summary={
                "pending_count": 0,
                "quality_error_count": 0,
                "placeholder_risk_count": 0,
                "text_structure_count": 0,
                "write_back_protocol_count": 0,
                "write_back_probe_executed": True,
                "write_back_probe_mode": "rust_write_gate",
            }
        ),
        translation_status=_report(summary={"pending_count": 0, "run_pending_count": 0}),
        recent_runs=[],
    )

    assert decision.result == "ready_to_write_back"
    assert decision.stage == "before_write_back"
    assert decision.can_continue is True
    assert decision.requires_user_authorization is True
