"""Agent 工具箱 CoverageAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

import time

from app.observability import current_diagnostics
from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonArray,
    JsonObject,
    TextRules,
    _nonstandard_data_skipped_file_names,
    _nonstandard_data_skipped_warnings,
    _string_lines_to_json_array,
    issue,
    load_setting,
    rule_contract_issues_to_agent_issues,
    write_back_probe_report_fields,
)
from app.persistence import TargetGameSession
from app.persistence.records import TextFactV2Record, TextIndexItemRecord, TextIndexMetadata
from app.regex_contract import RegexContractValidationError, validate_mv_virtual_namebox_regex_contract
from app.rmmz.schema import NonstandardDataTextRuleRecord
from app.text_facts import (
    TextFactContractError,
    count_current_text_facts_v2,
    count_pending_text_facts_v2,
    count_rule_hit_text_facts_v2,
    count_stale_translations_outside_writable_text_facts_v2,
    count_translated_text_facts_v2,
    count_writable_text_facts_v2,
    read_current_text_fact_records_v2,
    read_pending_text_fact_path_samples_v2,
    read_stale_translation_path_samples_outside_writable_text_facts_v2,
    read_unwritable_text_fact_records_v2,
)
from app.text_index import (
    collect_text_index_placeholder_gate_decisions,
    detect_text_index_invalidations,
)

TEXT_SCOPE_ENTRY_SAMPLE_LIMIT = 1000
TEXT_FACT_COVERAGE_DETAIL_SAMPLE_LIMIT = 20


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
            index_status, metadata, nonstandard_data_rules, rebuild_summary = index_report
            stage_started = time.perf_counter()
            placeholder_review_decisions, placeholder_metadata_errors = await collect_text_index_placeholder_gate_decisions(
                session=session,
                metadata=metadata,
                custom_placeholder_rules_supplied=False,
                stage="text_scope",
            )
            _record_stage(stage_timings, "text_scope", "placeholder_review", _elapsed_ms(stage_started))
            stage_started = time.perf_counter()
            try:
                report = await _build_text_fact_text_scope_report(
                    session=session,
                    include_write_probe=include_write_probe,
                )
            except TextFactContractError as error:
                return _empty_text_scope_report(
                    errors=[issue("text_fact_contract", str(error))],
                    include_write_probe=include_write_probe,
                    text_index_status=index_status,
                    text_index_rebuild_summary=rebuild_summary,
                )
            _record_stage(stage_timings, "text_scope", "assemble_report", _elapsed_ms(stage_started))
            _record_stage(stage_timings, "text_scope", "total", _elapsed_ms(overall_started))
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
                    "text_index_rebuild_summary": rebuild_summary,
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
            index_status, metadata, nonstandard_data_rules, rebuild_summary = index_report
            stage_started = time.perf_counter()
            placeholder_review_decisions, placeholder_metadata_errors = await collect_text_index_placeholder_gate_decisions(
                session=session,
                metadata=metadata,
                custom_placeholder_rules_supplied=False,
                stage="audit_coverage",
            )
            _record_stage(stage_timings, "audit_coverage", "placeholder_review", _elapsed_ms(stage_started))
            stage_started = time.perf_counter()
            try:
                report = await _build_text_fact_coverage_report(
                    session=session,
                    include_write_probe=include_write_probe,
                )
            except TextFactContractError as error:
                return _empty_audit_coverage_report(
                    errors=[issue("text_fact_contract", str(error))],
                    text_index_status=index_status,
                    text_index_rebuild_summary=rebuild_summary,
                )
            _record_stage(stage_timings, "audit_coverage", "assemble_report", _elapsed_ms(stage_started))
            _record_stage(stage_timings, "audit_coverage", "total", _elapsed_ms(overall_started))
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
                    "text_index_rebuild_summary": rebuild_summary,
                },
                details={
                    **report.details,
                    "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_file_names),
                },
            )


type _IndexReportData = tuple[
    str,
    TextIndexMetadata,
    list[NonstandardDataTextRuleRecord],
    JsonObject,
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
    rebuild_summary: JsonObject = {}
    stage_started = time.perf_counter()
    index_invalidations = await detect_text_index_invalidations(
        session=session,
        text_rules=text_rules,
    )
    _record_stage(stage_timings, stage, "detect_text_index", _elapsed_ms(stage_started))
    if index_invalidations:
        index_status = (
            "cold_rebuilt"
            if any(item.reason_key == "text_index_missing" for item in index_invalidations)
            else "stale_rebuilt"
        )
        rebuild_report = await service.rebuild_text_index(game_title=game_title)
        rebuild_summary = dict(rebuild_report.summary)
        if rebuild_report.status == "error":
            if stage == "text_scope":
                return _empty_text_scope_report(
                    errors=rebuild_report.errors,
                    include_write_probe=include_write_probe,
                    text_index_status="rebuild_failed",
                    text_index_rebuild_summary=rebuild_summary,
                )
            return _empty_audit_coverage_report(
                errors=rebuild_report.errors,
                text_index_status="rebuild_failed",
                text_index_rebuild_summary=rebuild_summary,
            )
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
                    text_index_status=index_status,
                    text_index_rebuild_summary=rebuild_summary,
                )
            return _empty_audit_coverage_report(
                errors=[mismatch_error],
                text_index_status=index_status,
                text_index_rebuild_summary=rebuild_summary,
            )

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
                text_index_status=index_status,
                text_index_rebuild_summary=rebuild_summary,
            )
        return _empty_audit_coverage_report(
            errors=[metadata_error],
            text_index_status=index_status,
            text_index_rebuild_summary=rebuild_summary,
        )
    nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
    _record_stage(stage_timings, stage, "read_index_and_state", _elapsed_ms(stage_started))
    return index_status, metadata, nonstandard_data_rules, rebuild_summary


async def _build_text_fact_text_scope_report(
    *,
    session: TargetGameSession,
    include_write_probe: bool,
) -> AgentReport:
    """用当前 v2 facts 生成文本清单报告，明细按固定上限取样。"""
    text_fact_count = await count_current_text_facts_v2(session)
    translated_count = await count_translated_text_facts_v2(session)
    writable_count = await count_writable_text_facts_v2(session)
    unwritable_count = max(0, text_fact_count - writable_count)
    facts = await read_current_text_fact_records_v2(
        session,
        limit=TEXT_SCOPE_ENTRY_SAMPLE_LIMIT,
    )
    index_records = await session.read_text_index_items_by_paths([fact.location_path for fact in facts])
    index_by_path = {record.location_path: record for record in index_records}
    entries: JsonArray = []
    for fact in facts:
        entries.append(
            _text_fact_scope_entry(
                fact,
                index_record=index_by_path.get(fact.location_path),
            )
        )
    unwritable_items: JsonArray = []
    for entry in entries:
        if len(unwritable_items) >= TEXT_FACT_COVERAGE_DETAIL_SAMPLE_LIMIT:
            break
        if isinstance(entry, dict) and entry.get("can_write_back") is False:
            unwritable_items.append(entry)
    errors: list[AgentIssue] = []
    if unwritable_count:
        errors.append(issue("coverage_unwritable", f"发现 {unwritable_count} 条当前文本无法写进游戏文件，请先运行 audit-coverage 查看明细"))
    probe_fields = write_back_probe_report_fields(
        requested=include_write_probe,
        executed=False,
        mode="index_writable" if include_write_probe else "disabled",
    )
    return AgentReport.from_parts(
        errors=errors,
        warnings=[],
        summary={
            "entry_count": text_fact_count,
            "text_fact_count": text_fact_count,
            "extractable_count": text_fact_count,
            "translated_count": translated_count,
            "writable_count": writable_count,
            "unwritable_count": unwritable_count,
            "inactive_rule_hit_count": 0,
            "stale_plugin_rule_count": 0,
            "write_back_probe_failed": False,
            **probe_fields,
            "text_index_status": "used",
        },
        details={
            "detail_mode": "sampled",
            "entries": entries,
            "entry_omitted_count": max(0, text_fact_count - len(entries)),
            "unwritable_items": unwritable_items,
            "stale_plugin_rules": [],
            "write_back_probe_error": "",
            **probe_fields,
        },
    )


async def _build_text_fact_coverage_report(
    *,
    session: TargetGameSession,
    include_write_probe: bool,
) -> AgentReport:
    """用当前 v2 facts 和 SQL 计数生成覆盖审计报告。"""
    text_fact_count = await count_current_text_facts_v2(session)
    translated_count = await count_translated_text_facts_v2(session)
    writable_count = await count_writable_text_facts_v2(session)
    rule_hit_count = await count_rule_hit_text_facts_v2(session)
    pending_count = await count_pending_text_facts_v2(session)
    stale_count = await count_stale_translations_outside_writable_text_facts_v2(session)
    unwritable_count = max(0, text_fact_count - writable_count)
    unwritable_facts = await read_unwritable_text_fact_records_v2(
        session,
        limit=TEXT_FACT_COVERAGE_DETAIL_SAMPLE_LIMIT,
    )
    pending_samples = await read_pending_text_fact_path_samples_v2(
        session,
        limit=TEXT_FACT_COVERAGE_DETAIL_SAMPLE_LIMIT,
    )
    stale_samples = await read_stale_translation_path_samples_outside_writable_text_facts_v2(
        session,
        limit=TEXT_FACT_COVERAGE_DETAIL_SAMPLE_LIMIT,
    )
    unwritable_index_records = await session.read_text_index_items_by_paths(
        [fact.location_path for fact in unwritable_facts]
    )
    unwritable_index_by_path = {
        record.location_path: record
        for record in unwritable_index_records
    }
    unwritable_samples: JsonArray = [
        _text_fact_sample(
            fact,
            index_record=unwritable_index_by_path.get(fact.location_path),
        )
        for fact in unwritable_facts
    ]

    errors: list[AgentIssue] = []
    if unwritable_count:
        errors.append(issue("coverage_unwritable", f"发现 {unwritable_count} 条当前文本无法写进游戏文件"))
    if pending_count:
        errors.append(issue("coverage_missing_translation", f"存在 {pending_count} 条当前可写文本还没成功保存译文"))
    if stale_count:
        errors.append(issue("stale_saved_translations", f"发现 {stale_count} 条已保存译文不在当前可写范围内"))

    probe_fields = write_back_probe_report_fields(
        requested=include_write_probe,
        executed=False,
        mode="index_writable" if include_write_probe else "disabled",
    )
    return AgentReport.from_parts(
        errors=errors,
        warnings=[],
        summary={
            "rule_hit_count": rule_hit_count,
            "extractable_count": text_fact_count,
            "text_fact_count": text_fact_count,
            "translated_count": translated_count,
            "writable_count": writable_count,
            "pending_count": pending_count,
            "unwritable_count": unwritable_count,
            "unwritable_rule_hit_count": 0,
            "stale_translation_count": stale_count,
            "stale_plugin_rule_count": 0,
            "write_back_probe_failed": False,
            **probe_fields,
        },
        details={
            "detail_mode": "sampled",
            "unwritable_items": _sampled_detail(total=unwritable_count, samples=unwritable_samples),
            "unwritable_rule_items": _sampled_detail(total=0, samples=[]),
            "inactive_rule_hits": _sampled_detail(total=0, samples=[]),
            "pending_location_paths": _sampled_detail(
                total=pending_count,
                samples=[path for path in pending_samples],
            ),
            "stale_translation_paths": _sampled_detail(
                total=stale_count,
                samples=[path for path in stale_samples],
            ),
            "stale_plugin_rules": _sampled_detail(total=0, samples=[]),
            "write_back_probe_error": "",
            **probe_fields,
        },
    )


def _text_fact_scope_entry(
    fact: TextFactV2Record,
    *,
    index_record: TextIndexItemRecord | None,
) -> JsonObject:
    """把 v2 fact 转成 text-scope 兼容 entry。"""
    can_write_back = index_record.writable if index_record is not None else False
    return {
        "location_path": fact.location_path,
        "source_type": fact.source_type,
        "rule_source": "text_index",
        "item_type": fact.item_type,
        "original_lines": _text_fact_lines(fact.translatable_text, item_type=fact.item_type),
        "source_line_paths": (
            [path for path in index_record.source_line_paths]
            if index_record is not None
            else [fact.location_path]
        ),
        "role": fact.role or None,
        "enters_translation": True,
        "can_save_translation": can_write_back,
        "can_write_back": can_write_back,
        "cannot_process_reason": "" if can_write_back else "索引项不可写回",
    }


def _text_fact_sample(
    fact: TextFactV2Record,
    *,
    index_record: TextIndexItemRecord | None,
) -> JsonObject:
    """把 v2 fact 转成 bounded coverage 样本。"""
    entry = _text_fact_scope_entry(fact, index_record=index_record)
    entry["raw_text_sample"] = _short_sample(fact.raw_text)
    entry["visible_text_sample"] = _short_sample(fact.visible_text)
    entry["translatable_text_sample"] = _short_sample(fact.translatable_text)
    return entry


def _text_fact_lines(text: str, *, item_type: str) -> JsonArray:
    """把 v2 单字符串正文转换成报告行数组。"""
    if item_type in {"long_text", "array"}:
        return [line for line in text.split("\n")]
    return [text]


def _short_sample(text: str, *, max_chars: int = 120) -> str:
    """生成报告短样本。"""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _sampled_detail(*, total: int, samples: JsonArray) -> JsonObject:
    """构造 bounded 明细摘要。"""
    return {
        "count": total,
        "samples": samples,
        "omitted_count": max(0, total - len(samples)),
    }


def _empty_text_scope_report(
    *,
    errors: list[AgentIssue],
    include_write_probe: bool,
    nonstandard_data_skipped_file_count: int = 0,
    text_index_status: str | None = None,
    text_index_rebuild_summary: JsonObject | None = None,
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
            "text_fact_count": 0,
            "extractable_count": 0,
            "translated_count": 0,
            "writable_count": 0,
            "unwritable_count": 0,
            "inactive_rule_hit_count": 0,
            "stale_plugin_rule_count": 0,
            "nonstandard_data_skipped_file_count": nonstandard_data_skipped_file_count,
            "write_back_probe_failed": False,
            **probe_fields,
            **({"text_index_status": text_index_status} if text_index_status is not None else {}),
            **(
                {"text_index_rebuild_summary": text_index_rebuild_summary}
                if text_index_rebuild_summary is not None
                else {}
            ),
        },
        details={},
    )


def _empty_audit_coverage_report(
    *,
    errors: list[AgentIssue],
    nonstandard_data_skipped_file_count: int = 0,
    text_index_status: str | None = None,
    text_index_rebuild_summary: JsonObject | None = None,
) -> AgentReport:
    """构造覆盖审计失败时的稳定空报告。"""
    summary: JsonObject = {
        "extractable_count": 0,
        "text_fact_count": 0,
        "translated_count": 0,
        "pending_count": 0,
        "stale_translation_count": 0,
        "unwritable_count": 0,
    }
    if nonstandard_data_skipped_file_count:
        summary["nonstandard_data_skipped_file_count"] = nonstandard_data_skipped_file_count
    if text_index_status is not None:
        summary["text_index_status"] = text_index_status
    if text_index_rebuild_summary is not None:
        summary["text_index_rebuild_summary"] = text_index_rebuild_summary
    return AgentReport.from_parts(errors=errors, warnings=[], summary=summary, details={})


def _elapsed_ms(started: float) -> int:
    """返回从 started 到当前的毫秒耗时。"""
    return int((time.perf_counter() - started) * 1000)


def _record_stage(
    stage_timings: JsonObject,
    domain: str,
    stage_name: str,
    duration_ms: int,
) -> None:
    """记录 coverage 命令阶段耗时到统一 diagnostics。"""
    stage_timings[stage_name] = duration_ms
    current_diagnostics().record_timing(f"{domain}.{stage_name}", duration_ms)
