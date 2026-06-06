"""Agent 工具箱 CoverageAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

import time

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonObject,
    TextRules,
    build_text_index_coverage_report,
    build_text_index_text_scope_report,
    _nonstandard_data_skipped_file_names,
    _nonstandard_data_skipped_warnings,
    _string_lines_to_json_array,
    issue,
    load_setting,
    rule_contract_issues_to_agent_issues,
    write_back_probe_report_fields,
)
from app.persistence import TargetGameSession
from app.persistence.records import TextIndexItemRecord, TextIndexMetadata
from app.regex_contract import RegexContractValidationError, validate_mv_virtual_namebox_regex_contract
from app.rmmz.schema import NonstandardDataTextRuleRecord, TranslationItem
from app.text_index import (
    collect_text_index_placeholder_gate_decisions,
    detect_text_index_invalidations,
)


class CoverageAgentMixin:
    """承载 AgentToolkitService 的 CoverageAgentMixin 命令族。"""

    async def text_scope(
        self: AgentServiceContext,
        *,
        game_title: str,
        include_write_probe: bool = False,
    ) -> AgentReport:
        """输出当前游戏统一文本清单。"""
        async with await self.game_registry.open_game(game_title) as session:
            overall_started = time.perf_counter()
            stage_timings: JsonObject = {}
            text_rules_or_report = await _load_text_rules_or_text_scope_report(
                service=self,
                session=session,
                include_write_probe=include_write_probe,
            )
            if isinstance(text_rules_or_report, AgentReport):
                return text_rules_or_report
            text_rules = text_rules_or_report
            index_report = await _read_current_index_report(
                service=self,
                session=session,
                game_title=game_title,
                text_rules=text_rules,
                include_write_probe=include_write_probe,
                stage="text_scope",
                stage_timings=stage_timings,
            )
            if isinstance(index_report, AgentReport):
                return index_report
            index_status, metadata, index_records, translated_items, nonstandard_data_rules = index_report
            stage_started = time.perf_counter()
            placeholder_review_decisions, placeholder_metadata_errors = await collect_text_index_placeholder_gate_decisions(
                session=session,
                metadata=metadata,
                custom_placeholder_rules_supplied=False,
                stage="text_scope",
            )
            stage_timings["placeholder_review"] = _elapsed_ms(stage_started)
            stage_started = time.perf_counter()
            report = build_text_index_text_scope_report(
                index_records=index_records,
                translated_items=translated_items,
                include_write_probe=include_write_probe,
            )
            stage_timings["assemble_report"] = _elapsed_ms(stage_started)
            stage_timings["total"] = _elapsed_ms(overall_started)
            placeholder_review_warnings = [
                issue(decision.code, decision.message)
                for decision in placeholder_review_decisions
                if decision.severity == "warning"
            ]
            placeholder_review_warnings.extend(
                issue(error.code, error.message)
                for error in placeholder_metadata_errors
            )
            skipped_file_names = _nonstandard_data_skipped_file_names(nonstandard_data_rules)
            return AgentReport.from_parts(
                errors=report.errors,
                warnings=[
                    *report.warnings,
                    *_nonstandard_data_skipped_warnings(nonstandard_data_rules),
                    *placeholder_review_warnings,
                ],
                summary={
                    **report.summary,
                    "nonstandard_data_skipped_file_count": len(skipped_file_names),
                    "text_index_status": index_status,
                    "stage_timings": stage_timings,
                },
                details={
                    **report.details,
                    "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_file_names),
                },
            )

    async def audit_coverage(
        self: AgentServiceContext,
        *,
        game_title: str,
        include_write_probe: bool = False,
    ) -> AgentReport:
        """审计规则命中、文本清单、已保存译文和写入范围是否一致。"""
        async with await self.game_registry.open_game(game_title) as session:
            overall_started = time.perf_counter()
            stage_timings: JsonObject = {}
            text_rules_or_report = await _load_text_rules_or_audit_report(
                service=self,
                session=session,
            )
            if isinstance(text_rules_or_report, AgentReport):
                return text_rules_or_report
            text_rules = text_rules_or_report
            index_report = await _read_current_index_report(
                service=self,
                session=session,
                game_title=game_title,
                text_rules=text_rules,
                include_write_probe=include_write_probe,
                stage="audit_coverage",
                stage_timings=stage_timings,
            )
            if isinstance(index_report, AgentReport):
                return index_report
            index_status, metadata, index_records, translated_items, nonstandard_data_rules = index_report
            stage_started = time.perf_counter()
            placeholder_review_decisions, placeholder_metadata_errors = await collect_text_index_placeholder_gate_decisions(
                session=session,
                metadata=metadata,
                custom_placeholder_rules_supplied=False,
                stage="audit_coverage",
            )
            stage_timings["placeholder_review"] = _elapsed_ms(stage_started)
            stage_started = time.perf_counter()
            report = build_text_index_coverage_report(
                index_records=index_records,
                translated_items=translated_items,
                include_write_probe=include_write_probe,
            )
            stage_timings["assemble_report"] = _elapsed_ms(stage_started)
            stage_timings["total"] = _elapsed_ms(overall_started)
            placeholder_review_warnings = [
                issue(decision.code, decision.message)
                for decision in placeholder_review_decisions
                if decision.severity == "warning"
            ]
            placeholder_review_warnings.extend(
                issue(error.code, error.message)
                for error in placeholder_metadata_errors
            )
            skipped_file_names = _nonstandard_data_skipped_file_names(nonstandard_data_rules)
            return AgentReport.from_parts(
                errors=report.errors,
                warnings=[
                    *report.warnings,
                    *_nonstandard_data_skipped_warnings(nonstandard_data_rules),
                    *placeholder_review_warnings,
                ],
                summary={
                    **report.summary,
                    "nonstandard_data_skipped_file_count": len(skipped_file_names),
                    "text_index_status": index_status,
                    "stage_timings": stage_timings,
                },
                details={
                    **report.details,
                    "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_file_names),
                },
            )


type _IndexReportData = tuple[
    str,
    TextIndexMetadata,
    list[TextIndexItemRecord],
    list[TranslationItem],
    list[NonstandardDataTextRuleRecord],
]


async def _load_text_rules_or_text_scope_report(
    *,
    service: AgentServiceContext,
    session: TargetGameSession,
    include_write_probe: bool,
) -> TextRules | AgentReport:
    """加载文本规则；规则错误时返回 text-scope 空报告。"""
    setting = load_setting(service.setting_path, source_language=session.source_language)
    custom_rules = await service._resolve_custom_rules(
        session=session,
        custom_placeholder_rules_text=None,
    )
    structured_rules = await service._resolve_structured_rules(session=session)
    try:
        text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=custom_rules,
            structured_placeholder_rules=structured_rules,
        )
    except RegexContractValidationError as error:
        return _empty_text_scope_report(
            errors=rule_contract_issues_to_agent_issues(error),
            include_write_probe=include_write_probe,
        )
    mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
    try:
        validate_mv_virtual_namebox_regex_contract(tuple(mv_virtual_namebox_rules))
    except RegexContractValidationError as error:
        return _empty_text_scope_report(
            errors=rule_contract_issues_to_agent_issues(error),
            include_write_probe=include_write_probe,
        )
    return text_rules


async def _load_text_rules_or_audit_report(
    *,
    service: AgentServiceContext,
    session: TargetGameSession,
) -> TextRules | AgentReport:
    """加载文本规则；规则错误时返回 audit-coverage 空报告。"""
    setting = load_setting(service.setting_path, source_language=session.source_language)
    custom_rules = await service._resolve_custom_rules(
        session=session,
        custom_placeholder_rules_text=None,
    )
    structured_rules = await service._resolve_structured_rules(session=session)
    try:
        text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=custom_rules,
            structured_placeholder_rules=structured_rules,
        )
    except RegexContractValidationError as error:
        return _empty_audit_coverage_report(
            errors=rule_contract_issues_to_agent_issues(error),
        )
    mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
    try:
        validate_mv_virtual_namebox_regex_contract(tuple(mv_virtual_namebox_rules))
    except RegexContractValidationError as error:
        return _empty_audit_coverage_report(
            errors=rule_contract_issues_to_agent_issues(error),
        )
    return text_rules


async def _read_current_index_report(
    *,
    service: AgentServiceContext,
    session: TargetGameSession,
    game_title: str,
    text_rules: TextRules,
    include_write_probe: bool,
    stage: str,
    stage_timings: JsonObject,
) -> _IndexReportData | AgentReport:
    """确保并读取当前 text index；不回退构建 Python 完整文本范围。"""
    index_status = "used"
    stage_started = time.perf_counter()
    index_invalidations = await detect_text_index_invalidations(
        session=session,
        text_rules=text_rules,
    )
    stage_timings["detect_text_index"] = _elapsed_ms(stage_started)
    if index_invalidations:
        index_status = "rebuilt"
        rebuild_report = await service.rebuild_text_index(game_title=game_title)
        if rebuild_report.status == "error":
            if stage == "text_scope":
                return _empty_text_scope_report(
                    errors=rebuild_report.errors,
                    include_write_probe=include_write_probe,
                )
            return _empty_audit_coverage_report(errors=rebuild_report.errors)
        index_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        if index_invalidations:
            mismatch_error = issue(
                "text_index_rebuild_mismatch",
                "文本范围索引重建后仍不匹配本次命令配置，不能使用错配索引生成报告",
            )
            if stage == "text_scope":
                return _empty_text_scope_report(
                    errors=[mismatch_error],
                    include_write_probe=include_write_probe,
                )
            return _empty_audit_coverage_report(errors=[mismatch_error])

    stage_started = time.perf_counter()
    metadata = await session.read_text_index_metadata()
    if metadata is None:
        metadata_error = issue(
            "text_index_metadata_missing",
            "持久文本范围索引缺少元信息，请重新运行 rebuild-text-index",
        )
        if stage == "text_scope":
            return _empty_text_scope_report(
                errors=[metadata_error],
                include_write_probe=include_write_probe,
            )
        return _empty_audit_coverage_report(errors=[metadata_error])
    index_records = await session.read_text_index_items()
    translated_items = await session.read_translated_items()
    nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
    stage_timings["read_index_and_state"] = _elapsed_ms(stage_started)
    return index_status, metadata, index_records, translated_items, nonstandard_data_rules


def _empty_text_scope_report(
    *,
    errors: list[AgentIssue],
    include_write_probe: bool,
    nonstandard_data_skipped_file_count: int = 0,
) -> AgentReport:
    """构造文本范围失败时的稳定空报告。"""
    probe_fields = write_back_probe_report_fields(
        requested=include_write_probe,
        executed=False,
        mode="index_writable" if include_write_probe else "disabled",
    )
    return AgentReport.from_parts(
        errors=errors,
        warnings=[],
        summary={
            "entry_count": 0,
            "extractable_count": 0,
            "translated_count": 0,
            "writable_count": 0,
            "unwritable_count": 0,
            "inactive_rule_hit_count": 0,
            "stale_plugin_rule_count": 0,
            "nonstandard_data_skipped_file_count": nonstandard_data_skipped_file_count,
            "write_back_probe_failed": False,
            **probe_fields,
        },
        details={},
    )


def _empty_audit_coverage_report(
    *,
    errors: list[AgentIssue],
    nonstandard_data_skipped_file_count: int = 0,
) -> AgentReport:
    """构造覆盖审计失败时的稳定空报告。"""
    summary: JsonObject = {
        "extractable_count": 0,
        "translated_count": 0,
        "pending_count": 0,
        "stale_translation_count": 0,
        "unwritable_count": 0,
    }
    if nonstandard_data_skipped_file_count:
        summary["nonstandard_data_skipped_file_count"] = nonstandard_data_skipped_file_count
    return AgentReport.from_parts(errors=errors, warnings=[], summary=summary, details={})


def _elapsed_ms(started: float) -> int:
    """返回从 started 到当前的毫秒耗时。"""
    return int((time.perf_counter() - started) * 1000)
