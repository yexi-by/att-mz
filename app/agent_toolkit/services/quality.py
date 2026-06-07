"""Agent 工具箱 QualityAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

import time
from dataclasses import dataclass

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    Counter,
    JsonArray,
    JsonObject,
    JsonValue,
    LlmFailureRecord,
    Path,
    QualityProgressCallbacks,
    SettingOverrides,
    TextRules,
    TranslationErrorItem,
    build_text_index_coverage_report,
    _build_manual_translation_template_entry,
    _build_quality_error_category_counts,
    _build_quality_fix_categories_by_path,
    _build_translation_error_quality_detail,
    _collect_active_translation_location_paths,
    _collect_quality_fix_problem_paths,
    _count_active_quality_details,
    _coverage_hard_stop_errors,
    current_timestamp_text,
    _nonstandard_data_skipped_file_names,
    _nonstandard_data_skipped_warnings,
    _noop_quality_progress_callbacks,
    _read_reset_translation_location_paths,
    _resolve_quality_fix_translation_lines,
    _string_lines_to_json_array,
    _validate_source_residual_rule_records,
    aiofiles,
    collect_agent_service_native_quality_counts,
    collect_agent_service_native_quality_details,
    collect_agent_service_native_write_protocol_details,
    issue,
    json,
    load_setting,
    native_thread_count,
    rule_contract_issues_to_agent_issues,
    write_back_probe_report_fields,
)
from app.config.schemas import Setting
from app.native_write_plan import build_native_write_back_plan, build_native_write_back_setting_payload
from app.regex_contract import RegexContractValidationError, validate_mv_virtual_namebox_regex_contract
from app.nonstandard_data import (
    ActiveRuntimeNonstandardDataAudit,
    audit_active_runtime_nonstandard_data,
)
from app.plugin_source_text import (
    ActiveRuntimePluginSourceAudit,
    ActiveRuntimePluginSourceIssue,
    PluginSourceReviewCoverage,
    audit_active_runtime_plugin_source_with_scan_cache,
    plugin_source_runtime_hash_lines,
    plugin_source_runtime_hash_text,
)
from app.plugin_source_text.scanner import (
    PluginSourceFileTextScan,
    build_plugin_source_file_hash,
    scan_plugin_source_runtime_files_text_strict,
)
from app.rmmz.schema import (
    GameData,
    PluginSourceRuntimeWriteMapRecord,
    PluginSourceTextRuleRecord,
    TranslationItem,
)
from app.persistence import TargetGameSession
from app.text_index import detect_text_index_invalidations
from app.text_index import collect_text_index_external_rule_gate_errors
from app.text_index import collect_text_index_scope_gate_errors
from app.text_index import collect_text_index_placeholder_gate_decisions
from app.text_index import text_index_item_to_translation_item
from app.text_index import text_index_source_branch_gates_prechecked
from app.text_facts import (
    count_pending_text_fact_quality_errors_by_type_v2,
    count_pending_text_fact_quality_errors_v2,
    count_pending_text_facts_v2,
    count_translated_text_facts_v2,
    read_pending_text_fact_quality_error_paths_v2,
    read_text_fact_quality_error_paths_v2,
    read_text_fact_quality_items_for_translations,
)
from app.observability import current_diagnostics

QUALITY_REPORT_FULL_RECHECK_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    """质量 gate 的结构化问题明细和计数字段。"""

    source_residual_items: JsonArray
    text_structure_items: JsonArray
    placeholder_risk_items: JsonArray
    overwide_line_items: JsonArray
    write_back_protocol_items: JsonArray
    source_residual_count_override: int | None = None
    text_structure_count_override: int | None = None
    placeholder_risk_count_override: int | None = None
    overwide_line_count_override: int | None = None

    @classmethod
    def empty(cls) -> "QualityGateResult":
        """构造没有质量问题的 gate 结果。"""
        return cls(
            source_residual_items=[],
            text_structure_items=[],
            placeholder_risk_items=[],
            overwide_line_items=[],
            write_back_protocol_items=[],
        )

    @classmethod
    def from_counts(
        cls,
        *,
        source_residual_count: int,
        text_structure_count: int,
        placeholder_risk_count: int,
        overwide_line_count: int,
    ) -> "QualityGateResult":
        """构造只有计数、无明细的 gate 结果。"""
        return cls(
            source_residual_items=[],
            text_structure_items=[],
            placeholder_risk_items=[],
            overwide_line_items=[],
            write_back_protocol_items=[],
            source_residual_count_override=source_residual_count,
            text_structure_count_override=text_structure_count,
            placeholder_risk_count_override=placeholder_risk_count,
            overwide_line_count_override=overwide_line_count,
        )

    def summary_fields(self) -> JsonObject:
        """返回 Agent summary 中的质量计数字段。"""
        return {
            "source_residual_count": (
                self.source_residual_count_override
                if self.source_residual_count_override is not None
                else len(self.source_residual_items)
            ),
            "text_structure_count": (
                self.text_structure_count_override
                if self.text_structure_count_override is not None
                else len(self.text_structure_items)
            ),
            "placeholder_risk_count": (
                self.placeholder_risk_count_override
                if self.placeholder_risk_count_override is not None
                else len(self.placeholder_risk_items)
            ),
            "overwide_line_count": (
                self.overwide_line_count_override
                if self.overwide_line_count_override is not None
                else len(self.overwide_line_items)
            ),
            "write_back_protocol_count": len(self.write_back_protocol_items),
        }

    def detail_fields(self) -> JsonObject:
        """返回 Agent details 中的质量明细字段。"""
        return {
            "source_residual_items": self.source_residual_items,
            "text_structure_items": self.text_structure_items,
            "placeholder_risk_items": self.placeholder_risk_items,
            "overwide_line_items": self.overwide_line_items,
            "write_back_protocol_items": self.write_back_protocol_items,
        }


def _empty_quality_report(
    *,
    errors: list[AgentIssue],
    source_language: str,
    target_language: str,
    include_write_probe: bool,
    plugin_rule_count: int = 0,
    stale_plugin_rule_count: int = 0,
    event_command_rule_count: int = 0,
    note_tag_rule_count: int = 0,
    nonstandard_data_skipped_file_count: int = 0,
    source_residual_rule_count: int = 0,
    latest_run_id: str = "",
    latest_run_status: str = "",
) -> AgentReport:
    """构造质量报告规则契约失败时的稳定空报告。"""
    quality_gate_result = QualityGateResult.empty()
    probe_fields = write_back_probe_report_fields(
        requested=include_write_probe,
        executed=False,
        mode="disabled",
    )
    return AgentReport.from_parts(
        errors=errors,
        warnings=[],
        summary={
            "extractable_count": 0,
            "translated_count": 0,
            "pending_count": 0,
            "stale_translation_count": 0,
            "unwritable_count": 0,
            "plugin_rule_count": plugin_rule_count,
            "stale_plugin_rule_count": stale_plugin_rule_count,
            "event_command_rule_count": event_command_rule_count,
            "note_tag_rule_count": note_tag_rule_count,
            "nonstandard_data_skipped_file_count": nonstandard_data_skipped_file_count,
            "source_language": source_language,
            "target_language": target_language,
            "source_residual_rule_count": source_residual_rule_count,
            "stale_source_residual_rule_count": 0,
            "terminology_total_count": 0,
            "terminology_filled_count": 0,
            "terminology_empty_count": 0,
            "latest_run_id": latest_run_id,
            "latest_run_status": latest_run_status,
            "llm_failure_count": 0,
            "quality_error_count": 0,
            "run_quality_error_count": 0,
            "model_response_error_count": 0,
            **quality_gate_result.summary_fields(),
            "writable_translation_count": 0,
            **probe_fields,
        },
        details={
            **quality_gate_result.detail_fields(),
        },
    )


def _empty_sampled_detail(total: int) -> JsonObject:
    """返回只有计数、没有样本的 coverage 明细。"""
    return {
        "count": total,
        "samples": [],
        "omitted_count": total,
    }


def _text_index_coverage_report_from_counts(
    *,
    extractable_count: int,
    translated_count: int,
    writable_count: int,
    pending_count: int,
    unwritable_count: int,
    stale_translation_count: int,
) -> AgentReport:
    """用 SQL 计数生成大库 coverage 摘要，避免读全量索引行。"""
    errors: list[AgentIssue] = []
    if unwritable_count:
        errors.append(issue("coverage_unwritable", f"发现 {unwritable_count} 条当前文本无法写进游戏文件"))
    if pending_count:
        errors.append(issue("coverage_missing_translation", f"存在 {pending_count} 条当前可写文本还没成功保存译文"))
    if stale_translation_count:
        errors.append(issue("stale_saved_translations", f"发现 {stale_translation_count} 条已保存译文不在当前可写范围内"))
    return AgentReport.from_parts(
        errors=errors,
        warnings=[],
        summary={
            "rule_hit_count": 0,
            "extractable_count": extractable_count,
            "translated_count": translated_count,
            "writable_count": writable_count,
            "pending_count": pending_count,
            "unwritable_count": unwritable_count,
            "unwritable_rule_hit_count": 0,
            "stale_translation_count": stale_translation_count,
            "stale_plugin_rule_count": 0,
            "write_back_probe_failed": False,
            "write_back_probe_enabled": False,
        },
        details={
            "detail_mode": "count_only",
            "unwritable_items": _empty_sampled_detail(unwritable_count),
            "unwritable_rule_items": _empty_sampled_detail(0),
            "inactive_rule_hits": _empty_sampled_detail(0),
            "pending_location_paths": _empty_sampled_detail(pending_count),
            "stale_translation_paths": _empty_sampled_detail(stale_translation_count),
            "stale_plugin_rules": _empty_sampled_detail(0),
            "write_back_probe_error": "",
            "write_back_probe_enabled": False,
        },
    )


def _active_runtime_audit_errors(audit: ActiveRuntimePluginSourceAudit) -> list[AgentIssue]:
    """把当前运行源码审计结果转换为质量报告错误。"""
    counts = Counter(issue.code for issue in audit.issues if issue.blocking)
    errors: list[AgentIssue] = []
    read_error_count = counts.get("active_runtime_read_error", 0)
    syntax_error_count = counts.get("active_runtime_syntax_error", 0)
    placeholder_count = counts.get("active_runtime_placeholder_risk", 0)
    residual_count = counts.get("active_runtime_source_residual", 0)
    if read_error_count:
        errors.append(
            issue(
                "active_runtime_read_error",
                f"当前游戏运行文件里有 {read_error_count} 个插件源码文件读取失败，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
            )
        )
    if syntax_error_count:
        errors.append(
            issue(
                "active_runtime_syntax_error",
                f"当前游戏运行文件里有 {syntax_error_count} 个插件源码文件 JS 语法检查失败，不能继续视为完成",
            )
        )
    if placeholder_count:
        errors.append(
            issue(
                "active_runtime_placeholder_risk",
                f"当前游戏运行文件里发现 {placeholder_count} 处插件源码坏控制符，不能继续视为完成",
            )
        )
    if residual_count:
        errors.append(
            issue(
                "active_runtime_source_residual",
                f"当前游戏运行文件里发现 {residual_count} 处插件源码源文残留，不能继续视为完成",
            )
        )
    return errors


def _active_runtime_audit_warnings(audit: ActiveRuntimePluginSourceAudit) -> list[AgentIssue]:
    """把不属于 ATT-MZ 写回责任的当前运行源码问题转换为告警。"""
    counts = Counter(issue.code for issue in audit.issues if not issue.blocking)
    warnings: list[AgentIssue] = []
    syntax_error_count = counts.get("active_runtime_syntax_error", 0)
    placeholder_count = counts.get("active_runtime_placeholder_risk", 0)
    residual_count = counts.get("active_runtime_source_residual", 0)
    if syntax_error_count:
        warnings.append(
            issue(
                "active_runtime_syntax_warning",
                f"当前游戏运行文件里有 {syntax_error_count} 个插件源码文件不是合法 JS，已跳过这些文件的插件源码文本审计，不阻断主流程",
            )
        )
    if placeholder_count:
        warnings.append(
            issue(
                "active_runtime_placeholder_risk_warning",
                f"当前游戏运行文件里发现 {placeholder_count} 处插件源码控制符巡检风险，未映射到可修复译文，不阻断主流程",
            )
        )
    if residual_count:
        warnings.append(
            issue(
                "active_runtime_source_residual_warning",
                f"当前游戏运行文件里发现 {residual_count} 处插件源码源文残留巡检风险，未映射到可修复译文，不阻断主流程",
            )
        )
    return warnings


def _active_runtime_nonstandard_data_errors(audit: ActiveRuntimeNonstandardDataAudit) -> list[AgentIssue]:
    """把当前运行非标准 data 审计结果转换为质量报告错误。"""
    counts = audit.issue_counts
    errors: list[AgentIssue] = []
    read_error_count = counts.get("active_runtime_nonstandard_data_read_error", 0)
    path_error_count = counts.get("active_runtime_nonstandard_data_path_error", 0)
    placeholder_count = counts.get("active_runtime_nonstandard_data_placeholder_risk", 0)
    residual_count = counts.get("active_runtime_nonstandard_data_source_residual", 0)
    if read_error_count:
        errors.append(
            issue(
                "active_runtime_nonstandard_data_read_error",
                f"当前游戏运行文件里有 {read_error_count} 个非标准 data JSON 文件读取失败，不能确认已管理文本是否正确写入",
            )
        )
    if path_error_count:
        errors.append(
            issue(
                "active_runtime_nonstandard_data_path_error",
                f"当前游戏运行文件里有 {path_error_count} 个非标准 data JSON 规则路径无法命中字符串叶子",
            )
        )
    if placeholder_count:
        errors.append(
            issue(
                "active_runtime_nonstandard_data_placeholder_risk",
                f"当前游戏运行文件里发现 {placeholder_count} 处非标准 data 文本坏控制符风险",
            )
        )
    if residual_count:
        errors.append(
            issue(
                "active_runtime_nonstandard_data_source_residual",
                f"当前游戏运行文件里发现 {residual_count} 处非标准 data 文本源文残留",
            )
        )
    return errors


def _plugin_source_quality_summary(review: PluginSourceReviewCoverage | None) -> JsonObject:
    """返回插件源码支线已经启动时的质量摘要字段。"""
    if review is None:
        return {}
    return {
        "plugin_source_active_candidate_count": review.active_candidate_count,
        "plugin_source_translate_selector_count": review.translate_selector_count,
        "plugin_source_excluded_selector_count": review.excluded_selector_count,
        "plugin_source_reviewed_selector_count": review.reviewed_selector_count,
        "plugin_source_unreviewed_count": len(review.unreviewed_candidates),
    }


def _plugin_source_quality_details(unreviewed_details: JsonArray | None) -> JsonObject:
    """返回插件源码支线已经启动时的质量明细字段。"""
    if unreviewed_details is None:
        return {}
    return {"plugin_source_unreviewed_candidates": unreviewed_details}


def _int_counts_to_json_object(counts: dict[str, int]) -> JsonObject:
    """把字符串计数字典收窄为 JSON 对象。"""
    result: JsonObject = {}
    for key, value in counts.items():
        result[key] = value
    return result


def _source_branch_gate_errors_from_rebuild_details(details: JsonObject) -> list[AgentIssue] | None:
    """从 rebuild-text-index 明细中恢复源分支 gate 错误。"""
    raw_errors = details.get("source_branch_gate_errors")
    if not isinstance(raw_errors, list):
        return None
    errors: list[AgentIssue] = []
    for index, raw_error in enumerate(raw_errors):
        if not isinstance(raw_error, dict):
            raise TypeError(f"source_branch_gate_errors[{index}] 必须是对象")
        code = raw_error.get("code")
        message = raw_error.get("message")
        if not isinstance(code, str):
            raise TypeError(f"source_branch_gate_errors[{index}].code 必须是字符串")
        if not isinstance(message, str):
            raise TypeError(f"source_branch_gate_errors[{index}].message 必须是字符串")
        errors.append(issue(code, message))
    return errors


def _plugin_source_text_audit_enabled(
    *,
    rule_records: list[PluginSourceTextRuleRecord],
    runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord],
) -> bool:
    """判断当前运行审计是否应进入插件源码文本支线。"""
    return bool(rule_records or runtime_write_map_records)


def _elapsed_ms(started: float) -> int:
    """计算阶段耗时毫秒。"""
    return int((time.perf_counter() - started) * 1000)


def _collect_rust_write_back_gate(
    *,
    session: TargetGameSession,
    setting: Setting,
    text_rules: TextRules,
    writable_paths: set[str],
) -> tuple[AgentIssue | None, JsonObject]:
    """调用 Rust 写回级质量 gate，供质量报告和写回链路共用同一 native gate。"""
    payload, _source_font_path, _source_font_names = build_native_write_back_setting_payload(
        setting=setting,
        text_rules=text_rules,
        content_root=session.content_root,
        confirm_font_overwrite=False,
        writable_location_paths=sorted(writable_paths),
    )
    try:
        plan = build_native_write_back_plan(
            game_path=session.game_path,
            content_root=session.content_root,
            db_path=session.db_path,
            mode="quality_gate",
            confirm_font_overwrite=False,
            setting_payload=payload,
        )
    except RuntimeError as error:
        message = str(error)
        return issue("write_back_gate", message), {
            "status": "error",
            "mode": "quality_gate",
            "message": message,
        }
    diagnostics = current_diagnostics()
    for name, duration_ms in plan.timings_ms.items():
        diagnostics.record_timing(f"quality.write_back_gate.rust_plan.{name}", duration_ms)
    diagnostics.counter("quality.write_back_gate.data_item_count", plan.summary.data_item_count)
    diagnostics.counter("quality.write_back_gate.plugin_item_count", plan.summary.plugin_item_count)
    return None, {
        "status": "ok",
        "mode": "quality_gate",
        "data_item_count": plan.summary.data_item_count,
        "plugin_item_count": plan.summary.plugin_item_count,
        "terminology_written_count": plan.summary.terminology_written_count,
        "plugin_source_runtime_map_count": plan.summary.plugin_source_runtime_map_count,
    }


def _build_active_runtime_diagnosis_items(
    *,
    audit: ActiveRuntimePluginSourceAudit,
    runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord],
    translated_items: list[TranslationItem],
    active_runtime_game_data: GameData,
    translation_source_game_data: GameData,
) -> JsonArray:
    """用确定性写回映射把当前运行问题反推到翻译源条目。"""
    plugin_source_files = translation_source_game_data.plugin_source_files
    write_map_by_runtime_key = {
        (record.runtime_file_name, record.runtime_selector): record
        for record in runtime_write_map_records
    }
    translated_by_path = {
        item.location_path: item
        for item in translated_items
    }
    source_scan_cache = _build_plugin_source_write_map_source_scan_cache(
        records=_collect_runtime_write_map_records_for_issues(
            audit=audit,
            write_map_by_runtime_key=write_map_by_runtime_key,
        ),
        plugin_source_files=plugin_source_files,
    )
    items: JsonArray = []
    for issue_item in audit.issues:
        diagnosis: JsonObject = {
            "issue": issue_item.to_json_object(),
        }
        if issue_item.literal is None:
            diagnosis.update(
                {
                    "diagnosis_status": "runtime_file_unreadable_or_invalid",
                    "suggested_action": "当前运行插件源码读取失败或 JS 语法检查失败；请先修复文件编码、缺失文件或 JS 语法错误",
                    "mapping_reason": "read_error_or_syntax_error",
                }
            )
            items.append(diagnosis)
            continue
        record = write_map_by_runtime_key.get((issue_item.file_name, issue_item.literal.selector))
        if record is None or not _runtime_write_map_matches_issue(
            record=record,
            issue_item=issue_item,
        ):
            diagnosis.update(
                {
                    "diagnosis_status": "runtime_mapping_missing",
                    "suggested_action": "当前运行字符串没有可用写回映射，诊断无法反推到已保存译文；请回到规则、反馈文本或重新写回后的已保存译文定位流程处理",
                    "mapping_reason": "runtime_mapping_missing",
                }
            )
            items.append(diagnosis)
            continue
        runtime_file_hash_matches = _plugin_source_write_map_runtime_file_hash_matches(
            record=record,
            active_runtime_game_data=active_runtime_game_data,
        )
        if record.mapping_kind == "excluded":
            source_hash_matches, source_file_hash_matches = _plugin_source_write_map_source_matches(
                record=record,
                plugin_source_files=plugin_source_files,
                source_scan_cache=source_scan_cache,
            )
            diagnosis["diagnosis_status"] = "mapped_excluded"
            diagnosis["location_path"] = record.location_path
            diagnosis["source_file_name"] = record.source_file_name
            diagnosis["source_selector"] = record.source_selector
            diagnosis["runtime_file_name"] = record.runtime_file_name
            diagnosis["runtime_selector"] = record.runtime_selector
            diagnosis["runtime_line"] = record.runtime_line
            diagnosis["runtime_file_hash_matches"] = runtime_file_hash_matches
            diagnosis["source_hash_matches"] = source_hash_matches
            diagnosis["source_file_hash_matches"] = source_file_hash_matches
            diagnosis["suggested_action"] = _suggested_action_for_excluded_write_map(
                runtime_file_hash_matches=runtime_file_hash_matches,
            )
            diagnosis["mapping_reason"] = "runtime_excluded_map_exact_match"
            items.append(diagnosis)
            continue
        translated_item = translated_by_path.get(record.location_path)
        cache_hash_matches = (
            translated_item is not None
            and plugin_source_runtime_hash_lines(translated_item.translation_lines) == record.translation_lines_hash
        )
        source_hash_matches, source_file_hash_matches = _plugin_source_write_map_source_matches(
            record=record,
            plugin_source_files=plugin_source_files,
            source_scan_cache=source_scan_cache,
        )
        suggested_action = _suggested_action_for_write_map(
            cache_hash_matches=cache_hash_matches,
            source_hash_matches=source_hash_matches,
            runtime_file_hash_matches=runtime_file_hash_matches,
        )
        diagnosis["diagnosis_status"] = "mapped_translate"
        diagnosis["location_path"] = record.location_path
        diagnosis["source_file_name"] = record.source_file_name
        diagnosis["source_selector"] = record.source_selector
        diagnosis["runtime_file_name"] = record.runtime_file_name
        diagnosis["runtime_selector"] = record.runtime_selector
        diagnosis["runtime_line"] = record.runtime_line
        diagnosis["runtime_file_hash_matches"] = runtime_file_hash_matches
        diagnosis["cache_hash_matches"] = cache_hash_matches
        diagnosis["source_hash_matches"] = source_hash_matches
        diagnosis["source_file_hash_matches"] = source_file_hash_matches
        diagnosis["current_translation_lines"] = (
            _string_lines_to_json_array(translated_item.translation_lines)
            if translated_item is not None
            else []
        )
        diagnosis["suggested_action"] = suggested_action
        diagnosis["mapping_reason"] = "runtime_write_map_exact_match"
        items.append(diagnosis)
    return items


def _runtime_write_map_matches_issue(
    *,
    record: PluginSourceRuntimeWriteMapRecord,
    issue_item: ActiveRuntimePluginSourceIssue,
) -> bool:
    """确认当前运行问题仍由同一份 runtime map 精确覆盖。"""
    if issue_item.literal is None:
        return False
    return plugin_source_runtime_hash_text(issue_item.literal.text) == record.runtime_text_hash


def _plugin_source_write_map_runtime_file_hash_matches(
    *,
    record: PluginSourceRuntimeWriteMapRecord,
    active_runtime_game_data: GameData,
) -> bool:
    """判断 runtime map 记录的整文件 hash 是否仍等于当前运行文件。"""
    source = active_runtime_game_data.plugin_source_files.get(record.runtime_file_name)
    return source is not None and build_plugin_source_file_hash(source) == record.runtime_file_hash


def _collect_runtime_write_map_records_for_issues(
    *,
    audit: ActiveRuntimePluginSourceAudit,
    write_map_by_runtime_key: dict[tuple[str, str], PluginSourceRuntimeWriteMapRecord],
) -> list[PluginSourceRuntimeWriteMapRecord]:
    """收集诊断本次确实会用到的写回映射记录。"""
    records: list[PluginSourceRuntimeWriteMapRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for issue_item in audit.issues:
        if issue_item.literal is None:
            continue
        record = write_map_by_runtime_key.get((issue_item.file_name, issue_item.literal.selector))
        if record is None:
            continue
        key = (record.location_path, record.source_file_name, record.source_selector)
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
    return records


def _build_plugin_source_write_map_source_scan_cache(
    *,
    records: list[PluginSourceRuntimeWriteMapRecord],
    plugin_source_files: dict[str, str],
) -> dict[str, PluginSourceFileTextScan]:
    """批量扫描诊断反推需要核对的翻译源插件源码。"""
    file_names = sorted(
        {
            record.source_file_name
            for record in records
            if record.source_file_name in plugin_source_files
            and build_plugin_source_file_hash(plugin_source_files[record.source_file_name]) != record.source_file_hash
        }
    )
    if not file_names:
        return {}
    source_files = {
        file_name: plugin_source_files[file_name]
        for file_name in file_names
    }
    batch_scan = scan_plugin_source_runtime_files_text_strict(
        files=source_files,
        active_file_names=frozenset(source_files),
    )
    if batch_scan.syntax_errors:
        file_name, syntax_error = sorted(batch_scan.syntax_errors.items())[0]
        raise RuntimeError(f"{file_name} {syntax_error}")
    return dict(batch_scan.file_scans)


def _suggested_action_for_write_map(
    *,
    cache_hash_matches: bool,
    source_hash_matches: bool,
    runtime_file_hash_matches: bool,
) -> str:
    """按写回映射状态生成诊断建议。"""
    if not source_hash_matches:
        return "翻译源插件源码已变化；请重新导出并审查插件源码规则，重新写回后再处理对应已保存译文记录"
    if not cache_hash_matches:
        return "当前已保存译文记录已变化或不存在；请重新写回生成新的当前运行文件，或检查对应译文是否仍需要修复"
    if not runtime_file_hash_matches:
        return "当前运行插件源码文件有无关内容变化，但 selector 和文本哈希仍能反推；请按文本在游戏里的内部位置（location_path）手修已保存译文记录，或重置对应译文后重新翻译，再重新写回"
    return "请按文本在游戏里的内部位置（location_path）手修已保存译文记录，或重置对应译文后重新翻译，再重新写回"


def _suggested_action_for_excluded_write_map(
    *,
    runtime_file_hash_matches: bool,
) -> str:
    """按排除映射状态生成诊断建议。"""
    if not runtime_file_hash_matches:
        return "当前运行字符串已由插件源码规则标记为已审查不翻译；当前运行文件有无关内容变化，但 selector 和文本哈希仍能确认该排除映射有效，不要把它加入重置译文清单"
    return "当前运行字符串已由插件源码规则标记为已审查不翻译；不要把它加入重置译文清单"


def _plugin_source_write_map_source_matches(
    *,
    record: PluginSourceRuntimeWriteMapRecord,
    plugin_source_files: dict[str, str],
    source_scan_cache: dict[str, PluginSourceFileTextScan],
) -> tuple[bool, bool]:
    """校验写回映射指向的翻译源 selector 和原文是否仍然存在。"""
    source = plugin_source_files.get(record.source_file_name)
    if source is None:
        return False, False
    current_source_file_hash = build_plugin_source_file_hash(source)
    source_file_hash_matches = current_source_file_hash == record.source_file_hash
    if source_file_hash_matches:
        return True, True
    source_scan = source_scan_cache.get(record.source_file_name)
    if source_scan is None:
        raise RuntimeError(f"翻译源插件源码扫描结果缺失: {record.source_file_name}")
    if source_scan.file_hash != current_source_file_hash:
        raise RuntimeError(f"翻译源插件源码扫描结果已失效: {record.source_file_name}")
    candidate_text = _plugin_source_write_map_source_text(
        source_scan=source_scan,
        selector=record.source_selector,
    )
    if candidate_text is None:
        return False, source_file_hash_matches
    return plugin_source_runtime_hash_text(candidate_text) == record.source_text_hash, source_file_hash_matches


def _plugin_source_write_map_source_text(
    *,
    source_scan: PluginSourceFileTextScan,
    selector: str,
) -> str | None:
    """从诊断 source scan 中读取 selector 对应的翻译源可见文本。"""
    candidate = source_scan.candidate_index.by_selector.get(selector)
    if candidate is not None:
        return candidate.text
    for literal in source_scan.literals:
        if literal.selector == selector:
            return literal.text
    return None


def _active_runtime_diagnosis_summary(
    diagnosis_items: JsonArray,
) -> JsonObject:
    """统计当前运行反推诊断状态。"""
    counts: Counter[str] = Counter()
    for item in diagnosis_items:
        if not isinstance(item, dict):
            continue
        status = item.get("diagnosis_status")
        if isinstance(status, str):
            counts[status] += 1
    return {
        "diagnosis_issue_count": len(diagnosis_items),
        "mapped_translate_count": counts.get("mapped_translate", 0),
        "mapped_excluded_count": counts.get("mapped_excluded", 0),
        "runtime_mapping_missing_count": counts.get("runtime_mapping_missing", 0),
        "runtime_file_unreadable_or_invalid_count": counts.get("runtime_file_unreadable_or_invalid", 0),
    }


def _build_active_runtime_reset_payload(diagnosis_items: JsonArray) -> JsonObject:
    """从确定性诊断结果生成重置清单。"""
    location_paths: list[JsonValue] = []
    seen: set[str] = set()
    for item in diagnosis_items:
        if not isinstance(item, dict):
            continue
        status = item.get("diagnosis_status")
        location_path = item.get("location_path")
        if status != "mapped_translate":
            continue
        if not isinstance(location_path, str) or not location_path or location_path in seen:
            continue
        seen.add(location_path)
        location_paths.append(location_path)
    return {"location_paths": location_paths}


class QualityAgentMixin:
    """承载 AgentToolkitService 的 QualityAgentMixin 命令族。"""

    async def audit_active_runtime(
        self: AgentServiceContext,
        *,
        game_title: str,
    ) -> AgentReport:
        """审计当前游戏实际运行文件中的插件源码问题。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            custom_rules = await self._resolve_custom_rules(
                session=session,
                custom_placeholder_rules_text=None,
            )
            structured_rules = await self._resolve_structured_rules(session=session)
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            active_runtime_game_data = await self._load_active_runtime_game_data(
                session,
                include_plugin_source_files=True,
            )
            plugin_source_rule_records = await session.read_plugin_source_text_rules()
            runtime_write_map_records = await session.read_plugin_source_runtime_write_maps()
            nonstandard_data_records = await session.read_nonstandard_data_text_rules()
            audit_text_issues = _plugin_source_text_audit_enabled(
                rule_records=plugin_source_rule_records,
                runtime_write_map_records=runtime_write_map_records,
            )
            active_runtime_audit, refreshed_scan_cache = audit_active_runtime_plugin_source_with_scan_cache(
                game_data=active_runtime_game_data,
                text_rules=text_rules,
                cache_records=await session.read_plugin_source_runtime_scan_cache(),
                created_at=current_timestamp_text(),
                runtime_write_map_records=runtime_write_map_records,
                plugin_source_rule_records=plugin_source_rule_records,
                audit_text_issues=audit_text_issues,
            )
            await session.replace_plugin_source_runtime_scan_cache(refreshed_scan_cache)
            nonstandard_data_audit = audit_active_runtime_nonstandard_data(
                layout=active_runtime_game_data.layout,
                rule_records=nonstandard_data_records,
                text_rules=text_rules,
            )
        errors = [
            *_active_runtime_audit_errors(active_runtime_audit),
            *_active_runtime_nonstandard_data_errors(nonstandard_data_audit),
        ]
        warnings = [
            *_active_runtime_audit_warnings(active_runtime_audit),
            *_nonstandard_data_skipped_warnings(nonstandard_data_records),
        ]
        skipped_file_names = _nonstandard_data_skipped_file_names(nonstandard_data_records)
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "source_view": "active-runtime",
                **active_runtime_audit.summary_json(),
                **nonstandard_data_audit.summary_json(),
                "nonstandard_data_skipped_file_count": len(skipped_file_names),
            },
            details={
                "source_view": "active-runtime",
                "active_runtime_plugin_source_items": active_runtime_audit.issues_json(),
                "active_runtime_nonstandard_data_items": nonstandard_data_audit.issues_json(),
                "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_file_names),
            },
        )

    async def diagnose_active_runtime(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path | None = None,
    ) -> AgentReport:
        """生成当前运行插件源码问题到翻译源已保存译文记录的确定性反推报告。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            custom_rules = await self._resolve_custom_rules(
                session=session,
                custom_placeholder_rules_text=None,
            )
            structured_rules = await self._resolve_structured_rules(session=session)
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            active_runtime_game_data = await self._load_active_runtime_game_data(
                session,
                include_plugin_source_files=True,
            )
            translation_source_game_data = await self._load_translation_source_game_data(
                session,
                include_plugin_source_files=True,
            )
            runtime_write_map_records = await session.read_plugin_source_runtime_write_maps()
            translated_items = await session.read_translated_items()
            plugin_source_rule_records = await session.read_plugin_source_text_rules()
            audit_text_issues = _plugin_source_text_audit_enabled(
                rule_records=plugin_source_rule_records,
                runtime_write_map_records=runtime_write_map_records,
            )
            active_runtime_audit, refreshed_scan_cache = audit_active_runtime_plugin_source_with_scan_cache(
                game_data=active_runtime_game_data,
                text_rules=text_rules,
                cache_records=await session.read_plugin_source_runtime_scan_cache(),
                created_at=current_timestamp_text(),
                runtime_write_map_records=runtime_write_map_records,
                plugin_source_rule_records=plugin_source_rule_records,
                audit_text_issues=audit_text_issues,
            )
            await session.replace_plugin_source_runtime_scan_cache(refreshed_scan_cache)
        diagnosis_items = _build_active_runtime_diagnosis_items(
            audit=active_runtime_audit,
            runtime_write_map_records=runtime_write_map_records,
            translated_items=translated_items,
            active_runtime_game_data=active_runtime_game_data,
            translation_source_game_data=translation_source_game_data,
        )
        reset_payload = _build_active_runtime_reset_payload(diagnosis_items)
        report = AgentReport.from_parts(
            errors=_active_runtime_audit_errors(active_runtime_audit),
            warnings=_active_runtime_audit_warnings(active_runtime_audit),
            summary={
                "source_view": "active-runtime",
                "output": str(output_path) if output_path is not None else "",
                **active_runtime_audit.summary_json(),
                **_active_runtime_diagnosis_summary(diagnosis_items),
            },
            details={
                "source_view": "active-runtime",
                "active_runtime_diagnosis_items": diagnosis_items,
                "reset_translations_input": reset_payload,
                "manual_translation_location_paths": reset_payload["location_paths"],
            },
        )
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
                _ = await file.write(f"{report.to_json_text()}\n")
        return report

    async def export_quality_fix_template(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
        include_write_probe: bool = False,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """从质量报告问题生成可填写的修复表。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        set_progress(0, 8)
        set_status("加载游戏数据和规则")
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            custom_rules = await self._resolve_custom_rules(
                session=session,
                custom_placeholder_rules_text=None,
            )
            structured_rules = await self._resolve_structured_rules(session=session)
            try:
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
            except RegexContractValidationError as error:
                set_progress(1, 1)
                set_status("文本规则检查没通过，质量报告已停止")
                return _empty_quality_report(
                    errors=rule_contract_issues_to_agent_issues(error),
                    source_language=session.source_language,
                    target_language=session.target_language,
                    include_write_probe=include_write_probe,
                )
            invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=text_rules,
            )
            if invalidations:
                rebuild_report = await self.rebuild_text_index(
                    game_title=game_title,
                    callbacks=(set_progress, advance_progress, set_status),
                )
                if rebuild_report.status == "error":
                    return AgentReport.from_parts(
                        errors=rebuild_report.errors,
                        warnings=rebuild_report.warnings,
                        summary={
                            "exported_count": 0,
                            "output": str(output_path),
                            **write_back_probe_report_fields(
                                requested=include_write_probe,
                                executed=False,
                                mode="index_writable" if include_write_probe else "disabled",
                            ),
                            "text_index_status": "rebuild_failed",
                            "text_index_rebuild_summary": rebuild_report.summary,
                        },
                        details={"text_index_rebuild": rebuild_report.details},
                    )
            metadata = await session.read_text_index_metadata()
            if metadata is None:
                return AgentReport.from_parts(
                    errors=[issue("text_index_metadata_missing", "持久文本范围索引缺少元信息，请重新运行 rebuild-text-index")],
                    warnings=[],
                    summary={
                        "exported_count": 0,
                        "output": str(output_path),
                        **write_back_probe_report_fields(
                            requested=include_write_probe,
                            executed=False,
                            mode="index_writable" if include_write_probe else "disabled",
                        ),
                    },
                    details={},
                )
            index_records = await session.read_text_index_items()
            translated_items = await session.read_translated_items()
            translated_by_path = {item.location_path: item for item in translated_items}
            translated_paths = set(translated_by_path)
            active_items = {
                record.location_path: text_index_item_to_translation_item(record)
                for record in index_records
            }
            active_paths = {
                record.location_path
                for record in index_records
                if record.writable
            }
            active_translated_items = [
                item
                for item in translated_items
                if item.location_path in active_paths
            ]
            latest_run = await session.read_latest_translation_run()
            if latest_run is None:
                quality_error_items: list[TranslationErrorItem] = []
            else:
                quality_error_items = await session.read_translation_quality_errors(latest_run.run_id)
            source_residual_rules = await session.read_source_residual_rules()
            coverage_report = build_text_index_coverage_report(
                index_records=index_records,
                translated_items=translated_items,
                include_write_probe=include_write_probe,
            )
            advance_progress(2)

        blocking_errors = _coverage_hard_stop_errors(coverage_report)
        if blocking_errors:
            set_progress(8, 8)
            set_status("检查没通过，停止导出质量修复表")
            quality_gate_result = QualityGateResult.empty()
            return AgentReport.from_parts(
                errors=blocking_errors,
                warnings=coverage_report.warnings,
                summary={
                    "exported_count": 0,
                    "output": str(output_path),
                    "quality_error_items_count": 0,
                    "quality_error_category_counts": _build_quality_error_category_counts([]),
                    "quality_error_count": 0,
                    **quality_gate_result.summary_fields(),
                    **write_back_probe_report_fields(
                        requested=include_write_probe,
                        executed=False,
                        mode="index_writable" if include_write_probe else "disabled",
                    ),
                },
                details={"coverage": coverage_report.details},
            )
        pending_paths = active_paths - translated_paths
        set_status("整理模型检查失败记录")
        quality_error_items = [
            item
            for item in quality_error_items
            if item.location_path in pending_paths
        ]
        advance_progress(1)
        source_residual_rule_errors = _validate_source_residual_rule_records(source_residual_rules)
        if source_residual_rule_errors:
            set_progress(8, 8)
            set_status("源文残留规则检查没通过，停止导出质量修复表")
            quality_gate_result = QualityGateResult.empty()
            return AgentReport.from_parts(
                errors=source_residual_rule_errors,
                warnings=[],
                summary={
                    "exported_count": 0,
                    "output": str(output_path),
                    "quality_error_items_count": len(quality_error_items),
                    "quality_error_category_counts": _build_quality_error_category_counts(quality_error_items),
                    "quality_error_count": len(quality_error_items),
                    **quality_gate_result.summary_fields(),
                    **write_back_probe_report_fields(
                        requested=include_write_probe,
                        executed=False,
                        mode="index_writable" if include_write_probe else "disabled",
                    ),
                },
                details={},
            )
        set_status(f"调用 Rust 原生质检核心（{native_thread_count()} 线程）")
        native_quality_details = collect_agent_service_native_quality_details(
            items=active_translated_items,
            text_rules=text_rules,
            source_residual_rules=source_residual_rules,
        )
        residual_details = native_quality_details.source_residual_items
        text_structure_details = native_quality_details.text_structure_items
        placeholder_details = native_quality_details.placeholder_risk_items
        overwide_details = native_quality_details.overwide_line_items
        advance_progress(1)
        set_status("检查写回协议")
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_translation_source_game_data(session)
        write_back_protocol_details = collect_agent_service_native_write_protocol_details(
            game_data=game_data.data,
            plugins_js=[plugin for plugin in game_data.plugins_js],
            items=active_translated_items,
        )
        advance_progress(1)
        set_status("整理质量修复条目")
        problem_paths = _collect_quality_fix_problem_paths(
            quality_error_items=quality_error_items,
            residual_details=residual_details,
            text_structure_details=text_structure_details,
            placeholder_details=placeholder_details,
            overwide_details=overwide_details,
            write_back_protocol_details=write_back_protocol_details,
            active_paths=active_paths,
        )
        quality_errors_by_path = {
            item.location_path: item
            for item in quality_error_items
        }
        categories_by_path = _build_quality_fix_categories_by_path(
            quality_error_items=quality_error_items,
            residual_details=residual_details,
            text_structure_details=text_structure_details,
            placeholder_details=placeholder_details,
            overwide_details=overwide_details,
            write_back_protocol_details=write_back_protocol_details,
            active_paths=active_paths,
        )
        advance_progress(1)
        set_status("写出质量修复表")
        payload: JsonObject = {}
        for location_path in problem_paths:
            active_item = active_items[location_path]
            translation_lines = _resolve_quality_fix_translation_lines(
                location_path=location_path,
                quality_errors_by_path=quality_errors_by_path,
                translated_by_path=translated_by_path,
            )
            payload[location_path] = _build_manual_translation_template_entry(
                item=active_item,
                text_rules=text_rules,
                translation_lines=translation_lines,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
            _ = await file.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
        advance_progress(1)

        warnings: list[AgentIssue] = []
        if not problem_paths:
            warnings.append(issue("quality_fix_empty", "当前没有可导出的质量修复条目"))
        set_progress(8, 8)
        set_status("质量修复表已完成")
        diagnostics = current_diagnostics()
        diagnostics.counter("quality_fix.native_quality_payload_item_count", len(active_translated_items))
        diagnostics.counter("quality_fix.native_write_protocol_payload_item_count", len(active_translated_items))
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "exported_count": len(problem_paths),
                "output": str(output_path),
                "quality_error_items_count": len(quality_error_items),
                "quality_error_category_counts": _build_quality_error_category_counts(quality_error_items),
                "quality_error_count": len(quality_error_items),
                "source_residual_count": _count_active_quality_details(residual_details, active_paths),
                "text_structure_count": _count_active_quality_details(text_structure_details, active_paths),
                "placeholder_risk_count": _count_active_quality_details(placeholder_details, active_paths),
                "overwide_line_count": _count_active_quality_details(overwide_details, active_paths),
                "write_back_protocol_count": _count_active_quality_details(write_back_protocol_details, active_paths),
                **write_back_probe_report_fields(
                    requested=include_write_probe,
                    executed=False,
                    mode="index_writable" if include_write_probe else "disabled",
                ),
            },
            details={
                "location_paths": _string_lines_to_json_array(problem_paths),
                "problem_categories_by_path": categories_by_path,
            },
        )
    @staticmethod
    async def _quality_report_from_text_index(
        *,
        service: AgentServiceContext,
        session: TargetGameSession,
        setting: Setting,
        text_rules: TextRules,
        callbacks: QualityProgressCallbacks,
        include_write_probe: bool = False,
        precomputed_source_branch_gate_errors: list[AgentIssue] | None = None,
    ) -> AgentReport:
        """使用持久文本范围索引生成默认质量报告。"""
        set_progress, advance_progress, set_status = callbacks
        overall_started = time.perf_counter()

        def record_stage(stage_name: str, duration_ms: int) -> None:
            current_diagnostics().record_timing(f"quality.{stage_name}", duration_ms)

        set_status("读取持久文本范围索引")
        stage_started = time.perf_counter()
        metadata = await session.read_text_index_metadata()
        if metadata is None:
            raise RuntimeError("持久文本范围索引元信息不可读取，请重新运行 rebuild-text-index")
        latest_run = await session.read_latest_translation_run()
        plugin_rules = await session.read_plugin_text_rules()
        plugin_source_records = await session.read_plugin_source_text_rules()
        external_rule_gate_errors = await collect_text_index_external_rule_gate_errors(
            session=session,
            metadata=metadata,
        )
        text_index_scope_gate_errors = await collect_text_index_scope_gate_errors(session=session)
        record_stage("read_index_and_state", _elapsed_ms(stage_started))
        plugin_source_gate_errors: list[AgentIssue] = []
        plugin_source_review: PluginSourceReviewCoverage | None = None
        plugin_source_unreviewed_details: JsonArray | None = None
        plugin_source_review_status = "not_started"
        source_branch_gates_prechecked = text_index_source_branch_gates_prechecked(metadata)
        if precomputed_source_branch_gate_errors is not None and not source_branch_gates_prechecked:
            plugin_source_gate_errors = list(precomputed_source_branch_gate_errors)
            plugin_source_review_status = "reused_rebuild_gate"
            record_stage("plugin_source_review", 0)
        elif plugin_source_records and source_branch_gates_prechecked:
            plugin_source_review_status = "prechecked_from_text_index"
            record_stage("plugin_source_review", 0)
        elif not source_branch_gates_prechecked:
            plugin_source_gate_errors = [
                issue(
                    "text_index_workflow_gate_metadata_missing",
                    "持久文本范围索引缺少插件源码或非标准 data 预检结果，请重新运行 rebuild-text-index",
                )
            ]
            plugin_source_review_status = "metadata_missing"
            record_stage("plugin_source_review", 0)
        stage_started = time.perf_counter()
        event_rules = await session.read_event_command_text_rules()
        note_tag_rules = await session.read_note_tag_text_rules()
        mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
        mv_virtual_namebox_rule_errors: list[AgentIssue] = []
        try:
            validate_mv_virtual_namebox_regex_contract(tuple(mv_virtual_namebox_rules))
        except RegexContractValidationError as error:
            mv_virtual_namebox_rule_errors = rule_contract_issues_to_agent_issues(error)
        nonstandard_data_records = await session.read_nonstandard_data_text_rules()
        source_residual_rules = await session.read_source_residual_rules()
        terminology_registry = await session.read_terminology_registry()
        record_stage("read_rules", _elapsed_ms(stage_started))
        stage_started = time.perf_counter()
        if latest_run is None:
            run_quality_error_items: list[TranslationErrorItem] = []
            llm_failures: list[LlmFailureRecord] = []
        else:
            stage_started = time.perf_counter()
            run_quality_error_items = await session.read_translation_quality_errors(latest_run.run_id)
            llm_failures = await session.read_llm_failures(latest_run.run_id)
            record_stage("read_run_failures", _elapsed_ms(stage_started))
        run_quality_error_count = len(run_quality_error_items)

        stage_started = time.perf_counter()
        use_count_fast_path = (
            metadata.item_count > QUALITY_REPORT_FULL_RECHECK_LIMIT
            and latest_run is not None
            and not source_residual_rules
            and not include_write_probe
        )
        active_translated_items: list[TranslationItem] = []
        writable_paths: set[str] = set()
        if use_count_fast_path:
            assert latest_run is not None
            scope_summary = await session.read_text_index_scope_summary()
            if scope_summary is None:
                raise RuntimeError("持久文本范围索引摘要不可读取，请重新运行 rebuild-text-index")
            translated_count = await count_translated_text_facts_v2(session)
            pending_count = await count_pending_text_facts_v2(session)
            stale_translation_count = await session.count_translations_outside_writable_text_index()
            active_quality_error_paths = await read_text_fact_quality_error_paths_v2(session, latest_run.run_id)
            pending_quality_error_paths = await read_pending_text_fact_quality_error_paths_v2(
                session,
                latest_run.run_id,
            )
            quality_error_items = [
                item
                for item in run_quality_error_items
                if item.location_path in pending_quality_error_paths
            ]
            native_quality_items = await read_text_fact_quality_items_for_translations(
                session,
                await session.read_translated_items_by_paths(sorted(active_quality_error_paths)),
            )
            active_count = scope_summary.active_count
            writable_count = scope_summary.writable_count
            unwritable_count = scope_summary.unwritable_count
            writable_translation_count = max(0, writable_count - pending_count)
            pending_paths_count = pending_count
            stale_paths_count = stale_translation_count
            stale_source_residual_rule_paths: set[str] = set()
            coverage_report = _text_index_coverage_report_from_counts(
                extractable_count=active_count,
                translated_count=translated_count,
                writable_count=writable_count,
                pending_count=pending_count,
                unwritable_count=unwritable_count,
                stale_translation_count=stale_translation_count,
            )
        else:
            index_records = await session.read_text_index_items()
            translated_items = await session.read_translated_items()
            active_paths = {record.location_path for record in index_records}
            writable_paths = {
                record.location_path
                for record in index_records
                if record.writable
            }
            translated_paths = {item.location_path for item in translated_items}
            active_translated_items = [
                item
                for item in translated_items
                if item.location_path in active_paths
            ]
            index_source_files = {record.source_file for record in index_records}
            source_existing_stale_items = [
                item
                for item in translated_items
                if item.location_path not in active_paths
                and item.location_path.split("/", 1)[0] in index_source_files
            ]
            coverage_report = build_text_index_coverage_report(
                index_records=index_records,
                translated_items=translated_items,
                include_write_probe=include_write_probe,
            )
            stale_paths = translated_paths - writable_paths
            stale_source_residual_rule_paths = {
                rule.location_path
                for rule in source_residual_rules
                if rule.rule_type == "position" and rule.location_path not in active_paths
            }
            if latest_run is None:
                active_quality_error_paths: set[str] = set()
                pending_quality_error_paths: set[str] = set()
            else:
                active_quality_error_paths = await read_text_fact_quality_error_paths_v2(session, latest_run.run_id)
                pending_quality_error_paths = await read_pending_text_fact_quality_error_paths_v2(
                    session,
                    latest_run.run_id,
                )
            quality_error_items = [
                item
                for item in run_quality_error_items
                if item.location_path in pending_quality_error_paths
            ]
            active_count = len(active_paths)
            writable_count = len(writable_paths)
            unwritable_count = len(active_paths - writable_paths)
            translated_count = await count_translated_text_facts_v2(session)
            pending_paths_count = await count_pending_text_facts_v2(session)
            writable_translation_count = max(0, writable_count - pending_paths_count)
            stale_paths_count = len(stale_paths)
            if latest_run is None or len(active_translated_items) <= QUALITY_REPORT_FULL_RECHECK_LIMIT:
                native_quality_items = [
                    *active_translated_items,
                    *source_existing_stale_items,
                ]
            else:
                native_quality_items = [
                    item
                    for item in active_translated_items
                    if item.location_path in active_quality_error_paths
                ]
            native_quality_items = await read_text_fact_quality_items_for_translations(
                session,
                native_quality_items,
            )
        record_stage("build_index_scope", _elapsed_ms(stage_started))
        stage_started = time.perf_counter()
        placeholder_review_decisions, placeholder_metadata_errors = await collect_text_index_placeholder_gate_decisions(
            session=session,
            metadata=metadata,
            custom_placeholder_rules_supplied=False,
            stage="quality_report",
        )
        record_stage("placeholder_review", _elapsed_ms(stage_started))

        total_terminology_count = 0
        filled_terminology_count = 0
        empty_terminology_count = 0
        if terminology_registry is not None:
            total_terminology_count = terminology_registry.total_entry_count()
            filled_terminology_count = terminology_registry.filled_entry_count()
            empty_terminology_count = total_terminology_count - filled_terminology_count

        protocol_probe_count = len(active_translated_items) if include_write_probe else 0
        total_progress_steps = max(5 + len(native_quality_items) * 4 + len(quality_error_items) + protocol_probe_count, 1)
        set_progress(0, total_progress_steps)
        set_status(f"检查 {len(native_quality_items)} 条已保存译文，还没成功保存译文 {pending_paths_count} 条")
        advance_progress(1)
        for _item in quality_error_items:
            advance_progress(1)
        source_residual_rule_errors = _validate_source_residual_rule_records(source_residual_rules)
        if source_residual_rule_errors:
            set_progress(total_progress_steps, total_progress_steps)
            set_status("源文残留例外规则检查没通过，质量报告已停止")
            return AgentReport.from_parts(
                errors=source_residual_rule_errors,
                warnings=[],
                summary={
                    "extractable_count": active_count,
                    "translated_count": translated_count,
                    "pending_count": pending_paths_count,
                    "source_language": session.source_language,
                    "target_language": session.target_language,
                    "source_residual_rule_count": len(source_residual_rules),
                    **write_back_probe_report_fields(
                        requested=include_write_probe,
                        executed=False,
                        mode="rust_write_gate" if include_write_probe else "disabled",
                    ),
                    "text_index_status": "used",
                },
                details={"coverage": coverage_report.details},
            )
        set_status(f"调用 Rust 原生质检核心（{native_thread_count()} 线程）")
        stage_started = time.perf_counter()
        native_quality_counts = collect_agent_service_native_quality_counts(
            items=native_quality_items,
            text_rules=text_rules,
            source_residual_rules=source_residual_rules,
        )
        has_native_quality_issues = any(
            (
                native_quality_counts.source_residual_count,
                native_quality_counts.text_structure_count,
                native_quality_counts.placeholder_risk_count,
                native_quality_counts.overwide_line_count,
            )
        )
        native_quality_details = (
            collect_agent_service_native_quality_details(
                items=native_quality_items,
                text_rules=text_rules,
                source_residual_rules=source_residual_rules,
            )
            if include_write_probe or has_native_quality_issues or len(native_quality_items) <= 1000
            else None
        )
        record_stage("native_quality", _elapsed_ms(stage_started))
        residual_items = native_quality_details.source_residual_items if native_quality_details is not None else []
        text_structure_items = native_quality_details.text_structure_items if native_quality_details is not None else []
        placeholder_risk_items = native_quality_details.placeholder_risk_items if native_quality_details is not None else []
        overwide_line_items = native_quality_details.overwide_line_items if native_quality_details is not None else []
        advance_progress(len(native_quality_items) * 4)

        write_back_gate_summary: JsonObject = {}
        write_back_gate_error: AgentIssue | None = None
        write_back_protocol_items: JsonArray = []
        if include_write_probe:
            set_status(f"调用 Rust 写回级质量 gate（{native_thread_count()} 线程）")
            stage_started = time.perf_counter()
            write_back_gate_error, write_back_gate_summary = _collect_rust_write_back_gate(
                session=session,
                setting=setting,
                text_rules=text_rules,
                writable_paths=writable_paths,
            )
            record_stage("rust_write_back_gate", _elapsed_ms(stage_started))
            stage_started = time.perf_counter()
            game_data = await service._load_translation_source_game_data(session)
            write_back_protocol_items = collect_agent_service_native_write_protocol_details(
                game_data=game_data.data,
                plugins_js=[plugin for plugin in game_data.plugins_js],
                items=active_translated_items,
            )
            record_stage("native_write_protocol", _elapsed_ms(stage_started))
            advance_progress(len(active_translated_items))

        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
        errors.extend(mv_virtual_namebox_rule_errors)
        errors.extend(coverage_report.errors)
        errors.extend(issue(error.code, error.message) for error in external_rule_gate_errors)
        errors.extend(issue(error.code, error.message) for error in text_index_scope_gate_errors)
        errors.extend(issue(error.code, error.message) for error in placeholder_metadata_errors)
        errors.extend(plugin_source_gate_errors)
        warnings.extend(coverage_report.warnings)
        if write_back_gate_error is not None:
            errors.append(write_back_gate_error)
        for decision in placeholder_review_decisions:
            if decision.severity == "ok":
                continue
            candidate_issue = issue(decision.code, decision.message)
            if decision.severity == "warning":
                warnings.append(candidate_issue)
            else:
                errors.append(candidate_issue)
        skipped_nonstandard_data_files = _nonstandard_data_skipped_file_names(nonstandard_data_records)
        warnings.extend(_nonstandard_data_skipped_warnings(nonstandard_data_records))
        if llm_failures and pending_paths_count:
            errors.append(issue("llm_failures", f"最新翻译运行存在 {len(llm_failures)} 条模型运行故障"))
        elif llm_failures:
            warnings.append(issue("historical_llm_failures", f"最新翻译运行记录过 {len(llm_failures)} 条模型故障，但当前没有正文因此无法继续"))
        if quality_error_items:
            errors.append(issue("translation_quality_errors", f"最新翻译运行有 {len(quality_error_items)} 条模型翻了但项目检查没通过的译文"))
        if placeholder_risk_items:
            errors.append(issue("placeholder_risk", f"发现 {len(placeholder_risk_items)} 条译文里的游戏控制符可能被改坏"))
        if residual_items:
            errors.append(issue("source_residual", f"发现 {len(residual_items)} 条译文存在{setting.text_rules.source_residual_label}残留风险"))
        if text_structure_items:
            errors.append(issue("text_structure", f"发现 {len(text_structure_items)} 条译文改动了游戏文本结构"))
        if overwide_line_items:
            errors.append(issue("overwide_line", f"发现 {len(overwide_line_items)} 行译文超过当前长文本宽度上限"))
        if write_back_protocol_items:
            errors.append(issue("write_back_protocol", f"发现 {len(write_back_protocol_items)} 条译文不符合写进游戏文件的协议要求"))
        if terminology_registry is None:
            errors.append(issue("terminology_missing", "当前游戏尚未导入字段译名表"))
        elif empty_terminology_count:
            errors.append(issue("terminology_empty_translation", f"字段译名表还有 {empty_terminology_count} 个词条没有填写译名"))
        if stale_source_residual_rule_paths:
            errors.append(issue("stale_source_residual_rules", f"发现 {len(stale_source_residual_rule_paths)} 条不在当前提取范围内的源文残留例外规则"))

        quality_error_details: JsonArray = []
        for item in quality_error_items:
            quality_error_details.append(_build_translation_error_quality_detail(item))
        error_type_counts = Counter(item.error_type for item in quality_error_items)
        llm_failure_counts = Counter(failure.category for failure in llm_failures)
        plugin_source_summary = _plugin_source_quality_summary(plugin_source_review)
        plugin_source_details = _plugin_source_quality_details(plugin_source_unreviewed_details)
        quality_gate_result = (
            QualityGateResult(
                source_residual_items=residual_items,
                text_structure_items=text_structure_items,
                placeholder_risk_items=placeholder_risk_items,
                overwide_line_items=overwide_line_items,
                write_back_protocol_items=write_back_protocol_items,
            )
            if native_quality_details is not None
            else QualityGateResult.from_counts(
                source_residual_count=native_quality_counts.source_residual_count,
                text_structure_count=native_quality_counts.text_structure_count,
                placeholder_risk_count=native_quality_counts.placeholder_risk_count,
                overwide_line_count=native_quality_counts.overwide_line_count,
            )
        )
        set_progress(total_progress_steps, total_progress_steps)
        set_status("质量报告已完成")
        record_stage("total", _elapsed_ms(overall_started))
        diagnostics = current_diagnostics()
        diagnostics.counter("quality.native_quality_payload_item_count", len(native_quality_items))
        diagnostics.counter(
            "quality.native_write_protocol_payload_item_count",
            len(active_translated_items) if include_write_probe else 0,
        )
        diagnostics.counter("runtime.native_thread_count", native_thread_count())
        probe_fields = write_back_probe_report_fields(
            requested=include_write_probe,
            executed=include_write_probe,
            mode="rust_write_gate" if include_write_probe else "disabled",
        )
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "extractable_count": active_count,
                "translated_count": translated_count,
                "pending_count": pending_paths_count,
                "stale_translation_count": stale_paths_count,
                "unwritable_count": unwritable_count,
                "plugin_rule_count": sum(len(rule.path_templates) for rule in plugin_rules),
                "stale_plugin_rule_count": 0,
                "event_command_rule_count": sum(len(rule.path_templates) for rule in event_rules),
                "note_tag_rule_count": sum(len(rule.tag_names) for rule in note_tag_rules),
                "nonstandard_data_skipped_file_count": len(skipped_nonstandard_data_files),
                "plugin_source_rule_file_count": len(plugin_source_records),
                "plugin_source_review_status": plugin_source_review_status,
                **plugin_source_summary,
                "source_language": session.source_language,
                "target_language": session.target_language,
                "source_residual_rule_count": len(source_residual_rules),
                "stale_source_residual_rule_count": len(stale_source_residual_rule_paths),
                "terminology_total_count": total_terminology_count,
                "terminology_filled_count": filled_terminology_count,
                "terminology_empty_count": empty_terminology_count,
                "latest_run_id": latest_run.run_id if latest_run is not None else "",
                "latest_run_status": latest_run.status if latest_run is not None else "",
                "llm_failure_count": len(llm_failures),
                "quality_error_count": len(quality_error_items),
                "run_quality_error_count": run_quality_error_count,
                "model_response_error_count": sum(1 for item in quality_error_items if item.model_response.strip()),
                **quality_gate_result.summary_fields(),
                "writable_translation_count": writable_translation_count,
                **probe_fields,
                "write_back_gate": write_back_gate_summary,
                "text_index_status": "used",
            },
            details={
                "error_type_counts": dict(error_type_counts),
                "llm_failure_counts": dict(llm_failure_counts),
                "quality_error_items": quality_error_details,
                **quality_gate_result.detail_fields(),
                **plugin_source_details,
                "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_nonstandard_data_files),
                "coverage": {
                    **coverage_report.details,
                    "source": "text_index",
                    "index_item_count": active_count,
                },
            },
        )

    async def quality_report(
        self: AgentServiceContext,
        *,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
        callbacks: QualityProgressCallbacks | None = None,
        include_write_probe: bool = False,
    ) -> AgentReport:
        """生成目标游戏当前翻译状态和质量风险报告。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        set_progress(0, 1)
        set_status("加载游戏数据和规则")
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(
                self.setting_path,
                overrides=setting_overrides,
                source_language=session.source_language,
            )
            custom_rules = await self._resolve_custom_rules(
                session=session,
                custom_placeholder_rules_text=None,
            )
            structured_rules = await self._resolve_structured_rules(session=session)
            try:
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
            except RegexContractValidationError as error:
                set_progress(1, 1)
                set_status("文本规则检查没通过，质量报告已停止")
                return _empty_quality_report(
                    errors=rule_contract_issues_to_agent_issues(error),
                    source_language=session.source_language,
                    target_language=session.target_language,
                    include_write_probe=include_write_probe,
                )

            text_index_invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=text_rules,
            )
            if not text_index_invalidations:
                return await QualityAgentMixin._quality_report_from_text_index(
                    service=self,
                    session=session,
                    setting=setting,
                    text_rules=text_rules,
                    callbacks=(set_progress, advance_progress, set_status),
                    include_write_probe=include_write_probe,
                )

            invalidation_details: JsonArray = [
                {
                    "reason_key": item.reason_key,
                    "detail": item.detail,
                    "created_at": item.created_at,
                }
                for item in text_index_invalidations
            ]
            rebuild_status = (
                "cold_rebuilt"
                if any(item.reason_key == "text_index_missing" for item in text_index_invalidations)
                else "stale_rebuilt"
            )
            set_status("文本范围索引不可用，自动重建索引")
            rebuild_report = await self.rebuild_text_index(
                game_title=game_title,
                setting_overrides=setting_overrides,
                callbacks=(set_progress, advance_progress, set_status),
            )
            if rebuild_report.status == "error":
                set_progress(1, 1)
                set_status("文本范围索引重建失败，质量报告已停止")
                return AgentReport.from_parts(
                    errors=rebuild_report.errors,
                    warnings=rebuild_report.warnings,
                    summary={
                        "extractable_count": 0,
                        "translated_count": 0,
                        "pending_count": 0,
                        "source_language": session.source_language,
                        "target_language": session.target_language,
                        **write_back_probe_report_fields(
                            requested=include_write_probe,
                            executed=False,
                            mode="rust_write_gate" if include_write_probe else "disabled",
                        ),
                        "text_index_status": "rebuild_failed",
                        "text_index_rebuild_summary": rebuild_report.summary,
                    },
                    details={
                        "text_index_invalidations": invalidation_details,
                        "text_index_rebuild": rebuild_report.details,
                    },
                )
            post_rebuild_invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=text_rules,
            )
            if post_rebuild_invalidations:
                set_progress(1, 1)
                set_status("文本范围索引重建后仍与本次配置不匹配，质量报告已停止")
                return AgentReport.from_parts(
                    errors=[
                        issue(
                            "text_index_rebuild_mismatch",
                            "文本范围索引重建后仍不匹配本次命令配置，不能使用错配索引生成质量报告",
                        )
                    ],
                    warnings=rebuild_report.warnings,
                    summary={
                        "extractable_count": 0,
                        "translated_count": 0,
                        "pending_count": 0,
                        "source_language": session.source_language,
                        "target_language": session.target_language,
                        **write_back_probe_report_fields(
                            requested=include_write_probe,
                            executed=False,
                            mode="rust_write_gate" if include_write_probe else "disabled",
                        ),
                        "text_index_status": "rebuild_failed",
                        "text_index_rebuild_summary": rebuild_report.summary,
                    },
                    details={
                        "text_index_invalidations": invalidation_details,
                        "post_rebuild_invalidations": [
                            {
                                "reason_key": item.reason_key,
                                "detail": item.detail,
                                "created_at": item.created_at,
                            }
                            for item in post_rebuild_invalidations
                        ],
                        "text_index_rebuild": rebuild_report.details,
                    },
                )
            report = await QualityAgentMixin._quality_report_from_text_index(
                service=self,
                session=session,
                setting=setting,
                text_rules=text_rules,
                callbacks=(set_progress, advance_progress, set_status),
                include_write_probe=include_write_probe,
                precomputed_source_branch_gate_errors=_source_branch_gate_errors_from_rebuild_details(
                    rebuild_report.details
                ),
            )
            summary = dict(report.summary)
            summary["text_index_status"] = rebuild_status
            summary["text_index_rebuild_summary"] = rebuild_report.summary
            details = dict(report.details)
            details["text_index_invalidations"] = invalidation_details
            return AgentReport.from_parts(
                errors=report.errors,
                warnings=[*rebuild_report.warnings, *report.warnings],
                summary=summary,
                details=details,
            )
    async def translation_status(
        self: AgentServiceContext,
        *,
        game_title: str,
        refresh_scope: bool = False,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """读取最新正文翻译运行状态；默认使用数据库快速路径。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        total_progress = 5 if refresh_scope else 2
        set_progress(0, total_progress)
        set_status("读取最近翻译运行")
        async with await self.game_registry.open_game(game_title) as session:
            latest_run = await session.read_latest_translation_run()
            if latest_run is None:
                set_progress(total_progress, total_progress)
                set_status("当前没有正文翻译运行记录")
                return AgentReport.from_parts(
                    errors=[],
                    warnings=[issue("translation_run_missing", "当前游戏尚未产生正文翻译运行记录")],
                    summary={},
                    details={},
                )
            llm_failures = await session.read_llm_failures(latest_run.run_id)
            run_quality_error_count = await session.count_translation_quality_errors(latest_run.run_id)
            run_quality_error_counts = await session.count_translation_quality_errors_by_type(latest_run.run_id)
            translated_count = await session.count_translated_items()
            advance_progress(1)
            if refresh_scope:
                set_status("加载游戏数据和规则")
                setting = load_setting(self.setting_path, source_language=session.source_language)
                custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                structured_rules = await self._resolve_structured_rules(session=session)
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                text_index_invalidations = await detect_text_index_invalidations(
                    session=session,
                    text_rules=text_rules,
                )
                if not text_index_invalidations:
                    set_status("读取持久文本范围索引")
                    metadata = await session.read_text_index_metadata()
                    extractable_count = metadata.item_count if metadata is not None else latest_run.total_extracted
                    pending_count = await count_pending_text_facts_v2(session)
                    translated_count = await count_translated_text_facts_v2(session)
                    quality_error_count = await count_pending_text_fact_quality_errors_v2(session, latest_run.run_id)
                    quality_error_counts = await count_pending_text_fact_quality_errors_by_type_v2(
                        session,
                        latest_run.run_id,
                    )
                    advance_progress(1)
                    set_progress(total_progress, total_progress)
                    set_status("正文翻译状态已完成")
                    return AgentReport.from_parts(
                        errors=[],
                        warnings=[],
                        summary={
                            "run_id": latest_run.run_id,
                            "status": latest_run.status,
                            "total_extracted": latest_run.total_extracted,
                            "pending_count": pending_count,
                            "run_pending_count": latest_run.pending_count,
                            "translated_count": translated_count,
                            "extractable_count": extractable_count,
                            "deduplicated_count": latest_run.deduplicated_count,
                            "batch_count": latest_run.batch_count,
                            "success_count": latest_run.success_count,
                            "quality_error_count": quality_error_count,
                            "run_quality_error_count": run_quality_error_count,
                            "llm_failure_count": len(llm_failures),
                            "stop_reason": latest_run.stop_reason,
                            "last_error": latest_run.last_error,
                            "scope_refreshed": True,
                            "text_index_status": "used",
                        },
                        details={
                            "llm_failure_counts": dict(Counter(failure.category for failure in llm_failures)),
                            "quality_error_counts": _int_counts_to_json_object(quality_error_counts),
                        },
                    )
                invalidation_details: JsonArray = [
                    {
                        "reason_key": item.reason_key,
                        "detail": item.detail,
                        "created_at": item.created_at,
                    }
                    for item in text_index_invalidations
                ]
                rebuild_status = (
                    "cold_rebuilt"
                    if any(item.reason_key == "text_index_missing" for item in text_index_invalidations)
                    else "stale_rebuilt"
                )
                set_status("文本范围索引不可用，自动重建索引")
                rebuild_report = await self.rebuild_text_index(
                    game_title=game_title,
                    callbacks=(set_progress, advance_progress, set_status),
                )
                if rebuild_report.status == "error":
                    set_progress(total_progress, total_progress)
                    set_status("文本范围索引重建失败，正文翻译状态刷新已停止")
                    return AgentReport.from_parts(
                        errors=rebuild_report.errors,
                        warnings=rebuild_report.warnings,
                        summary={
                            "run_id": latest_run.run_id,
                            "status": latest_run.status,
                            "total_extracted": latest_run.total_extracted,
                            "pending_count": latest_run.pending_count,
                            "run_pending_count": latest_run.pending_count,
                            "translated_count": translated_count,
                            "extractable_count": latest_run.total_extracted,
                            "deduplicated_count": latest_run.deduplicated_count,
                            "batch_count": latest_run.batch_count,
                            "success_count": latest_run.success_count,
                            "quality_error_count": run_quality_error_count,
                            "run_quality_error_count": run_quality_error_count,
                            "llm_failure_count": len(llm_failures),
                            "stop_reason": latest_run.stop_reason,
                            "last_error": latest_run.last_error,
                            "scope_refreshed": False,
                            "text_index_status": "rebuild_failed",
                            "text_index_rebuild_summary": rebuild_report.summary,
                        },
                        details={
                            "llm_failure_counts": dict(Counter(failure.category for failure in llm_failures)),
                            "quality_error_counts": _int_counts_to_json_object(run_quality_error_counts),
                            "text_index_invalidations": invalidation_details,
                            "text_index_rebuild": rebuild_report.details,
                        },
                )
                set_status("读取持久文本范围索引")
                metadata = await session.read_text_index_metadata()
                extractable_count = metadata.item_count if metadata is not None else latest_run.total_extracted
                pending_count = await count_pending_text_facts_v2(session)
                translated_count = await count_translated_text_facts_v2(session)
                quality_error_count = await count_pending_text_fact_quality_errors_v2(session, latest_run.run_id)
                quality_error_counts = await count_pending_text_fact_quality_errors_by_type_v2(
                    session,
                    latest_run.run_id,
                )
                advance_progress(1)
                set_progress(total_progress, total_progress)
                set_status("正文翻译状态已完成")
                return AgentReport.from_parts(
                    errors=[],
                    warnings=rebuild_report.warnings,
                    summary={
                        "run_id": latest_run.run_id,
                        "status": latest_run.status,
                        "total_extracted": latest_run.total_extracted,
                        "pending_count": pending_count,
                        "run_pending_count": latest_run.pending_count,
                        "translated_count": translated_count,
                        "extractable_count": extractable_count,
                        "deduplicated_count": latest_run.deduplicated_count,
                        "batch_count": latest_run.batch_count,
                        "success_count": latest_run.success_count,
                        "quality_error_count": quality_error_count,
                        "run_quality_error_count": run_quality_error_count,
                        "llm_failure_count": len(llm_failures),
                        "stop_reason": latest_run.stop_reason,
                        "last_error": latest_run.last_error,
                        "scope_refreshed": True,
                        "text_index_status": rebuild_status,
                        "text_index_rebuild_summary": rebuild_report.summary,
                    },
                    details={
                        "llm_failure_counts": dict(Counter(failure.category for failure in llm_failures)),
                        "quality_error_counts": _int_counts_to_json_object(quality_error_counts),
                        "text_index_invalidations": invalidation_details,
                    },
                )
            else:
                set_status("读取数据库状态")
                pending_count = latest_run.pending_count
                extractable_count = latest_run.total_extracted
                advance_progress(1)
        set_progress(total_progress, total_progress)
        set_status("正文翻译状态已完成")
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "run_id": latest_run.run_id,
                "status": latest_run.status,
                "total_extracted": latest_run.total_extracted,
                "pending_count": pending_count,
                "run_pending_count": latest_run.pending_count,
                "translated_count": translated_count,
                "extractable_count": extractable_count,
                "deduplicated_count": latest_run.deduplicated_count,
                "batch_count": latest_run.batch_count,
                "success_count": latest_run.success_count,
                "quality_error_count": run_quality_error_count,
                "run_quality_error_count": run_quality_error_count,
                "llm_failure_count": len(llm_failures),
                "stop_reason": latest_run.stop_reason,
                "last_error": latest_run.last_error,
                "scope_refreshed": refresh_scope,
            },
            details={
                "llm_failure_counts": dict(Counter(failure.category for failure in llm_failures)),
                "quality_error_counts": _int_counts_to_json_object(run_quality_error_counts),
            },
        )

    async def reset_translations(
        self: AgentServiceContext,
        *,
        game_title: str,
        input_path: Path | None = None,
        reset_all: bool = False,
    ) -> AgentReport:
        """删除已保存译文，使指定条目或当前提取范围全部条目重新交给模型翻译。"""
        if input_path is not None and reset_all:
            return AgentReport.from_parts(
                errors=[issue("reset_translation_source", "--input 与 --all 不能同时使用")],
                warnings=[],
                summary={
                    "input": str(input_path),
                    "mode": "invalid",
                    "requested_count": 0,
                    "reset_count": 0,
                },
                details={},
            )
        if input_path is None and not reset_all:
            return AgentReport.from_parts(
                errors=[issue("reset_translation_source", "必须通过 --input 或 --all 指定重置范围")],
                warnings=[],
                summary={
                    "input": "",
                    "mode": "invalid",
                    "requested_count": 0,
                    "reset_count": 0,
                },
                details={},
            )
        if input_path is not None:
            try:
                requested_paths = await _read_reset_translation_location_paths(input_path)
            except Exception as error:
                return AgentReport.from_parts(
                    errors=[issue("reset_translation_file", f"重置译文文件不可用: {type(error).__name__}: {error}")],
                    warnings=[],
                    summary={
                        "input": str(input_path),
                        "mode": "input",
                        "requested_count": 0,
                        "reset_count": 0,
                    },
                    details={},
                )
            text_index_status = "used"
            text_index_rebuild_summary: JsonObject = {}
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                structured_rules = await self._resolve_structured_rules(session=session)
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                text_index_invalidations = await detect_text_index_invalidations(
                    session=session,
                    text_rules=text_rules,
                )
                if text_index_invalidations:
                    text_index_status = (
                        "cold_rebuilt"
                        if any(item.reason_key == "text_index_missing" for item in text_index_invalidations)
                        else "stale_rebuilt"
                    )
                    invalidation_details: JsonArray = [
                        {
                            "reason_key": item.reason_key,
                            "detail": item.detail,
                            "created_at": item.created_at,
                        }
                        for item in text_index_invalidations
                    ]
                    rebuild_report = await self.rebuild_text_index(game_title=game_title)
                    text_index_rebuild_summary = dict(rebuild_report.summary)
                    if rebuild_report.status == "error":
                        return AgentReport.from_parts(
                            errors=rebuild_report.errors,
                            warnings=rebuild_report.warnings,
                            summary={
                                "input": str(input_path),
                                "mode": "input",
                                "requested_count": len(requested_paths),
                                "reset_count": 0,
                                "text_index_status": "rebuild_failed",
                                "text_index_rebuild_summary": text_index_rebuild_summary,
                            },
                            details={
                                "text_index_invalidations": invalidation_details,
                                "text_index_rebuild": rebuild_report.details,
                            },
                        )
                requested_path_set = set(requested_paths)
                index_records = await session.read_text_index_items_by_paths(requested_paths)
                active_paths = {record.location_path for record in index_records}
                invalid_paths = sorted(requested_path_set - active_paths)
                if invalid_paths:
                    reset_error_summary: JsonObject = {
                        "input": str(input_path),
                        "mode": "input",
                        "requested_count": len(requested_paths),
                        "reset_count": 0,
                        "text_index_status": text_index_status,
                    }
                    if text_index_rebuild_summary:
                        reset_error_summary["text_index_rebuild_summary"] = text_index_rebuild_summary
                    return AgentReport.from_parts(
                        errors=[
                            issue(
                                "reset_translation_location",
                                f"存在 {len(invalid_paths)} 个定位路径不在当前可提取文本范围内",
                        )
                    ],
                    warnings=[],
                    summary=reset_error_summary,
                    details={
                        "invalid_location_paths": _string_lines_to_json_array(invalid_paths),
                    },
                )
                reset_count = await session.delete_translation_items_by_paths(requested_paths)
            input_warnings: list[AgentIssue] = []
            already_pending_count = len(requested_paths) - reset_count
            if already_pending_count:
                input_warnings.append(issue("reset_translation_already_pending", f"{already_pending_count} 个定位路径当前没有已保存译文"))
            reset_summary: JsonObject = {
                "input": str(input_path),
                "mode": "input",
                "requested_count": len(requested_paths),
                "reset_count": reset_count,
                "already_pending_count": already_pending_count,
                "text_index_status": text_index_status,
            }
            if text_index_rebuild_summary:
                reset_summary["text_index_rebuild_summary"] = text_index_rebuild_summary
            return AgentReport.from_parts(
                errors=[],
                warnings=input_warnings,
                summary=reset_summary,
                details={
                    "location_paths": _string_lines_to_json_array(requested_paths),
                },
            )
        else:
            requested_paths = []

        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            custom_rules = await self._resolve_custom_rules(
                session=session,
                custom_placeholder_rules_text=None,
            )
            structured_rules = await self._resolve_structured_rules(session=session)
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            game_data = await self._load_translation_source_game_data(session)
            translation_data_map = await self._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
            )
            active_location_paths = _collect_active_translation_location_paths(translation_data_map.values())
            active_paths = set(active_location_paths)
            location_paths = active_location_paths if reset_all else requested_paths
            invalid_paths = sorted(set(location_paths) - active_paths)
            if invalid_paths:
                return AgentReport.from_parts(
                    errors=[
                        issue(
                            "reset_translation_location",
                            f"存在 {len(invalid_paths)} 个定位路径不在当前可提取文本范围内",
                        )
                    ],
                    warnings=[],
                    summary={
                        "input": str(input_path) if input_path is not None else "",
                        "mode": "all" if reset_all else "input",
                        "requested_count": len(location_paths),
                        "reset_count": 0,
                    },
                    details={
                        "invalid_location_paths": _string_lines_to_json_array(invalid_paths),
                    },
                )
            reset_count = await session.delete_translation_items_by_paths(location_paths)

        warnings: list[AgentIssue] = []
        already_pending_count = len(location_paths) - reset_count
        if already_pending_count:
            warnings.append(issue("reset_translation_already_pending", f"{already_pending_count} 个定位路径当前没有已保存译文"))
        if reset_all and not location_paths:
            warnings.append(issue("reset_translation_no_active_items", "当前提取范围没有可重置条目"))
        if reset_all:
            details: JsonObject = {
                "location_path_count": len(location_paths),
                "location_path_samples": _string_lines_to_json_array(location_paths[:20]),
            }
        else:
            details = {
                "location_paths": _string_lines_to_json_array(location_paths),
            }
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "input": str(input_path) if input_path is not None else "",
                "mode": "all" if reset_all else "input",
                "requested_count": len(location_paths),
                "reset_count": reset_count,
                "already_pending_count": already_pending_count,
            },
            details=details,
        )
