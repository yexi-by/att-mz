"""当前翻译源文本范围的持久索引构建与失效检测。"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from app.config import SettingOverrides
from app.config.schemas import Setting
from app.native_scope_index import (
    NativeScopeGateResult,
    build_native_rule_candidate_text_rules_payload,
    evaluate_native_scope_gate,
    rebuild_native_scope_index_storage,
)
from app.persistence import TargetGameSession
from app.persistence.records import (
    TextFactRecord,
    TextIndexInvalidationRecord,
    TextIndexItemRecord,
    TextIndexMetadata,
)
from app.persistence.repository import current_timestamp_text
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    MvVirtualNameboxRuleRecord,
    NonstandardDataTextRuleRecord,
    NoteTagTextRuleRecord,
    PlaceholderRuleRecord,
    PluginSourceTextRuleRecord,
    PluginTextRuleRecord,
    StructuredPlaceholderRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rmmz.source_snapshot import SourceSnapshotFileRecord
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue, TextRules, coerce_json_value
from app.rmmz.loader import resolve_game_layout
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    RuleReviewDomain,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
)
from app.rule_review_decision import (
    RuleCoverageResult,
    RuleReviewDecision,
    RuleReviewStage,
    WorkflowGateIssue,
    build_empty_rule_review_decision,
    build_rule_review_decision,
)
from app.text_fact_core import item_type_from_text_fact, text_fact_lines
from app.text_fact_counts import (
    read_current_matching_translation_fact_ids,
    read_text_fact_quality_error_fact_ids,
)
from app.text_fact_readers import read_current_text_fact_records
TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY = "workflow_gate_prechecked:plugin_source_text"
TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY = "workflow_gate_prechecked:nonstandard_data"
TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE = "passed"
TEXT_INDEX_PLACEHOLDER_GATE_PREFIX = "workflow_gate:placeholder_rules"
TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX = "workflow_gate:structured_placeholder_rules"
TEXT_INDEX_PROMPT_CONTEXT_VERSION = "display_name_owner_system_terms_v3"


@dataclass(frozen=True, slots=True)
class TextIndexNativeRebuildResult:
    """Rust 原生重建后的 metadata 和原生报告摘要。"""

    metadata: TextIndexMetadata
    native_summary: JsonObject


def text_fact_rebuild_report_fields(native_summary: JsonObject) -> JsonObject:
    """从 Rust 原生重建摘要中筛出用户可见的 current text fact 报告字段。"""
    report_fields: JsonObject = {}
    for field_name in (
        "text_fact_count",
        "render_part_count",
        "scan_file_count",
    ):
        value = native_summary.get(field_name)
        if isinstance(value, int) and not isinstance(value, bool):
            report_fields[field_name] = value
    for field_name in (
        "scope_key",
        "scope_hash",
        "source_snapshot_hash",
        "rule_hash",
        "text_rules_hash",
    ):
        value = native_summary.get(field_name)
        if isinstance(value, str) and value:
            report_fields[field_name] = value
    domain_fact_counts = native_summary.get("domain_fact_counts")
    if isinstance(domain_fact_counts, dict):
        report_fields["domain_fact_counts"] = {
            str(key): value
            for key, value in domain_fact_counts.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    index_status = native_summary.get("index_status")
    if isinstance(index_status, str) and index_status:
        report_fields["index_status"] = index_status
    return report_fields


async def rebuild_text_index_native_storage(
    *,
    session: TargetGameSession,
    setting: Setting,
    text_rules: TextRules,
    setting_overrides: SettingOverrides | None = None,
    include_write_probe: bool = False,
) -> TextIndexMetadata:
    """由 Rust 直读 DB/游戏目录并重建持久 text index。"""
    return (
        await rebuild_text_index_native_storage_with_summary(
            session=session,
            setting=setting,
            text_rules=text_rules,
            setting_overrides=setting_overrides,
            include_write_probe=include_write_probe,
        )
    ).metadata


async def rebuild_text_index_native_storage_with_summary(
    *,
    session: TargetGameSession,
    setting: Setting,
    text_rules: TextRules,
    setting_overrides: SettingOverrides | None = None,
    include_write_probe: bool = False,
) -> TextIndexNativeRebuildResult:
    """由 Rust 重建持久 text index，并保留 Rust 内部阶段耗时。"""
    _ = include_write_probe
    source_snapshot_fingerprint = await collect_source_snapshot_fingerprint(session)
    rules_fingerprint = await collect_text_index_rules_fingerprint(
        session=session,
        text_rules=text_rules,
    )
    text_rules_setting = coerce_json_value(cast(object, text_rules.setting.model_dump(mode="json")))
    if not isinstance(text_rules_setting, dict):
        raise TypeError("text_rules.setting JSON 必须是对象")
    text_rules_setting["prompt_context_version"] = TEXT_INDEX_PROMPT_CONTEXT_VERSION
    rule_candidate_text_rules = build_native_rule_candidate_text_rules_payload(text_rules)
    rule_candidate_text_rules["source_text_required_pattern"] = setting.text_rules.source_text_required_pattern
    engine_kind = resolve_game_layout(session.game_path).engine_kind
    event_command_scope_codes = [
        coerce_json_value(code)
        for code in setting.event_command_text.default_codes_for_engine(engine_kind)
    ]
    _ = setting_overrides
    result = rebuild_native_scope_index_storage(
        {
            "db_path": str(session.db_path),
            "game_path": str(session.game_path),
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
            "rules_fingerprint": rules_fingerprint,
            "source_language": session.source_language,
            "target_language": session.target_language,
            "engine_kind": engine_kind,
            "text_rules_setting": text_rules_setting,
            "rule_candidate_text_rules": rule_candidate_text_rules,
            "event_command_scope_codes": event_command_scope_codes,
            "source_text_required_pattern": setting.text_rules.source_text_required_pattern,
            "created_at": current_timestamp_text(),
        }
    )
    if result.get("status") != "ok":
        raise RuntimeError("Rust 原生文本范围索引重建没有返回成功状态")
    metadata = await session.read_text_index_metadata()
    if metadata is None:
        raise RuntimeError("Rust 原生文本范围索引重建后没有写入元信息")
    return TextIndexNativeRebuildResult(metadata=metadata, native_summary=result)


async def detect_text_index_invalidations(
    *,
    session: TargetGameSession,
    text_rules: TextRules,
) -> list[TextIndexInvalidationRecord]:
    """只用数据库元信息判断文本范围索引是否缺失或过期。"""
    metadata = await session.read_text_index_metadata()
    timestamp = current_timestamp_text()
    if metadata is None:
        return [
            TextIndexInvalidationRecord(
                reason_key="text_index_missing",
                detail="当前游戏尚未建立持久文本范围索引",
                created_at=timestamp,
            )
        ]

    invalidations: list[TextIndexInvalidationRecord] = []
    current_source_snapshot_fingerprint = await collect_source_snapshot_fingerprint(session)
    if metadata.source_snapshot_fingerprint != current_source_snapshot_fingerprint:
        invalidations.append(
            TextIndexInvalidationRecord(
                reason_key="source_snapshot_changed",
                detail="可信源快照 manifest 已变化，需要重建文本范围索引",
                created_at=timestamp,
            )
        )
    current_rules_fingerprint = await collect_text_index_rules_fingerprint(
        session=session,
        text_rules=text_rules,
    )
    if metadata.rules_fingerprint != current_rules_fingerprint:
        invalidations.append(
            TextIndexInvalidationRecord(
                reason_key="rules_changed",
                detail="文本提取相关配置或数据库规则已变化，需要重建文本范围索引",
                created_at=timestamp,
            )
        )
    stored_item_count = await session.count_text_index_items()
    if metadata.item_count != stored_item_count:
        invalidations.append(
            TextIndexInvalidationRecord(
                reason_key="text_index_count_mismatch",
                detail="文本范围索引元信息数量与索引项数量不一致，需要重建文本范围索引",
                created_at=timestamp,
            )
        )
    return invalidations


def text_index_source_branch_gates_prechecked(metadata: TextIndexMetadata) -> bool:
    """判断持久索引是否记录过插件源码和非标准 data gate 已通过预检。"""
    scope_hashes = metadata.workflow_gate_scope_hashes
    return (
        scope_hashes.get(TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY) == TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE
        and scope_hashes.get(TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY) == TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE
    )


async def collect_text_index_placeholder_gate_errors(
    *,
    session: TargetGameSession,
    metadata: TextIndexMetadata,
    custom_placeholder_rules_supplied: bool,
) -> list[WorkflowGateIssue]:
    """用索引元信息检查普通/结构化占位符候选审查状态。"""
    decisions, metadata_errors = await collect_text_index_placeholder_gate_decisions(
        session=session,
        metadata=metadata,
        custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
        stage="workflow_gate",
    )
    if metadata_errors:
        return metadata_errors
    return [
        decision.to_issue()
        for decision in decisions
        if decision.severity == "error"
    ]


async def collect_text_index_placeholder_gate_decisions(
    *,
    session: TargetGameSession,
    metadata: TextIndexMetadata,
    custom_placeholder_rules_supplied: bool,
    stage: RuleReviewStage,
) -> tuple[list[RuleReviewDecision], list[WorkflowGateIssue]]:
    """用索引元信息生成普通/结构化占位符候选审查决策。"""
    coverage_or_errors = _placeholder_coverages_from_metadata(metadata)
    if isinstance(coverage_or_errors, list):
        return [], coverage_or_errors
    placeholder_coverage, structured_coverage = coverage_or_errors
    return [
        await _text_index_placeholder_review_decision(
            session=session,
            coverage=placeholder_coverage,
            custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
            stage=stage,
        ),
        await _text_index_placeholder_review_decision(
            session=session,
            coverage=structured_coverage,
            custom_placeholder_rules_supplied=False,
            stage=stage,
        ),
    ], []


async def collect_text_index_scope_gate_errors(
    *,
    session: TargetGameSession,
) -> list[WorkflowGateIssue]:
    """用索引摘要检查文本范围自身的 workflow gate 错误。"""
    scope_summary = await session.read_text_index_scope_summary()
    if scope_summary is None:
        return [
            WorkflowGateIssue(
                code="text_index_scope_summary_missing",
                message="持久文本范围索引缺少范围摘要，请重新运行 rebuild-text-index",
            )
        ]

    errors: list[WorkflowGateIssue] = []
    if scope_summary.stale_rule_count:
        errors.append(
            WorkflowGateIssue(
                code="stale_plugin_rules",
                message=f"存在 {scope_summary.stale_rule_count} 个过期插件规则，请重新导入插件规则",
            )
        )
    if scope_summary.unwritable_count:
        errors.append(
            WorkflowGateIssue(
                code="coverage_unwritable",
                message=f"存在 {scope_summary.unwritable_count} 条当前文本无法写进游戏文件，请先运行 audit-coverage 查看明细",
            )
        )

    domain_summary = await session.read_text_index_domain_summary()
    inactive_rule_hit_count = sum(item.inactive_rule_hit_count for item in domain_summary)
    if inactive_rule_hit_count:
        errors.append(
            WorkflowGateIssue(
                code="rule_hits_unwritable",
                message=f"存在 {inactive_rule_hit_count} 条规则命中文本没有进入当前可写范围，请先运行 audit-coverage 查看明细",
            )
        )
    return errors


async def collect_text_index_external_rule_gate_errors(
    *,
    session: TargetGameSession,
    metadata: TextIndexMetadata,
) -> list[WorkflowGateIssue]:
    """用索引元信息检查外部文本规则是否已导入或确认为空。"""
    errors: list[WorkflowGateIssue] = []
    if not await session.read_plugin_text_rules():
        errors.extend(
            await _empty_text_index_rule_review_errors(
                session=session,
                metadata=metadata,
                rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
                label="插件规则",
            )
        )
    if not await session.read_event_command_text_rules():
        errors.extend(
            await _empty_text_index_rule_review_errors(
                session=session,
                metadata=metadata,
                rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
                label="事件指令规则",
            )
        )
    if not await session.read_note_tag_text_rules():
        errors.extend(
            await _empty_text_index_rule_review_errors(
                session=session,
                metadata=metadata,
                rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
                label="Note 标签规则",
            )
        )
    if resolve_game_layout(session.game_path).engine_kind == "mv" and not await session.read_mv_virtual_namebox_rules():
        errors.extend(
            await _empty_text_index_rule_review_errors(
                session=session,
                metadata=metadata,
                rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
                label="MV 虚拟名字框规则",
            )
        )
    return errors


async def evaluate_text_index_scope_gate(
    *,
    session: TargetGameSession,
    records: Iterable[TextIndexItemRecord],
    required_paths: Iterable[str] = (),
) -> NativeScopeGateResult:
    """用当前文本事实 和已保存译文完整身份调用 Rust 范围门禁摘要。"""
    record_list = list(records)
    current_facts = await read_current_text_fact_records(session, limit=None)
    latest_quality_error_fact_ids = await _read_latest_quality_error_fact_ids(session)
    matched_translation_fact_ids = await read_current_matching_translation_fact_ids(session)
    return evaluate_native_scope_gate(
        _scope_gate_payload_from_text_fact_records(
            records=record_list,
            facts=current_facts,
            matched_translation_fact_ids=matched_translation_fact_ids,
            quality_error_fact_ids=latest_quality_error_fact_ids,
            required_paths=required_paths,
        )
    )


async def _empty_text_index_rule_review_errors(
    *,
    session: TargetGameSession,
    metadata: TextIndexMetadata,
    rule_domain: RuleReviewDomain,
    label: str,
) -> list[WorkflowGateIssue]:
    """用索引保存的 scope hash 复用空规则确认状态。"""
    current_scope_hash = metadata.workflow_gate_scope_hashes.get(rule_domain)
    if current_scope_hash is None:
        _ = session
        return [
            WorkflowGateIssue(
                code="text_index_gate_scope_hash_missing",
                message=f"持久文本范围索引缺少 {label} 的当前审查范围 hash，请重新运行 rebuild-text-index",
            )
        ]
    decision = await build_empty_rule_review_decision(
        session=session,
        rule_domain=rule_domain,
        stage="workflow_gate",
        scope_hash=current_scope_hash,
        label=label,
        missing_code=f"{rule_domain}_missing",
        stale_code=f"{rule_domain}_stale_empty_confirmation",
        missing_severity="error",
        stale_severity="error",
    )
    return [decision.to_issue()] if decision.severity == "error" else []


def _placeholder_coverages_from_metadata(
    metadata: TextIndexMetadata,
) -> tuple[RuleCoverageResult, RuleCoverageResult] | list[WorkflowGateIssue]:
    """从 text index metadata 还原普通/结构化占位符覆盖摘要。"""
    placeholder_coverage = _placeholder_coverage_from_metadata(
        metadata=metadata,
        prefix=TEXT_INDEX_PLACEHOLDER_GATE_PREFIX,
        rule_domain=PLACEHOLDER_RULE_DOMAIN,
        label="普通占位符",
    )
    structured_coverage = _placeholder_coverage_from_metadata(
        metadata=metadata,
        prefix=TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX,
        rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
        label="结构化占位符",
    )
    errors = [
        item
        for item in (placeholder_coverage, structured_coverage)
        if isinstance(item, WorkflowGateIssue)
    ]
    if errors:
        return errors
    return (
        cast(RuleCoverageResult, placeholder_coverage),
        cast(RuleCoverageResult, structured_coverage),
    )


def _placeholder_coverage_from_metadata(
    *,
    metadata: TextIndexMetadata,
    prefix: str,
    rule_domain: RuleReviewDomain,
    label: str,
) -> RuleCoverageResult | WorkflowGateIssue:
    """读取单个占位符候选覆盖摘要。"""
    scope_hash = metadata.workflow_gate_scope_hashes.get(f"{prefix}:scope_hash")
    if scope_hash is None:
        return WorkflowGateIssue(
            code="text_index_workflow_gate_metadata_missing",
            message=f"持久文本范围索引缺少{label}确认范围，请重新运行 rebuild-text-index",
        )
    try:
        rule_count = _read_text_index_metadata_int(metadata, f"{prefix}:rule_count")
        candidate_count = _read_text_index_metadata_int(metadata, f"{prefix}:candidate_count")
        covered_count = _read_text_index_metadata_int(metadata, f"{prefix}:covered_count")
        uncovered_count = _read_text_index_metadata_int(metadata, f"{prefix}:uncovered_count")
    except ValueError as error:
        return WorkflowGateIssue(
            code="text_index_workflow_gate_metadata_invalid",
            message=f"持久文本范围索引里的{label}确认范围已损坏，请重新运行 rebuild-text-index: {error}",
        )
    return RuleCoverageResult(
        rule_domain=rule_domain,
        scope_hash=scope_hash,
        rule_count=rule_count,
        candidate_count=candidate_count,
        covered_count=covered_count,
        uncovered_count=uncovered_count,
        candidates=[],
        sample_limit=0,
    )


def _read_text_index_metadata_int(metadata: TextIndexMetadata, key: str) -> int:
    """读取 text index metadata 中的非负整数字段。"""
    raw_value = metadata.workflow_gate_scope_hashes.get(key)
    if raw_value is None:
        raise ValueError(f"缺少 {key}")
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{key} 不是整数") from error
    if value < 0:
        raise ValueError(f"{key} 不能为负数")
    return value


async def _text_index_placeholder_review_decision(
    *,
    session: TargetGameSession,
    coverage: RuleCoverageResult,
    custom_placeholder_rules_supplied: bool,
    stage: RuleReviewStage,
) -> RuleReviewDecision:
    """按索引里的占位符覆盖摘要生成 workflow gate 审查决策。"""
    if coverage.rule_domain == PLACEHOLDER_RULE_DOMAIN:
        return await build_rule_review_decision(
            session=session,
            coverage=coverage,
            stage=stage,
            unreviewed_code="placeholder_uncovered",
            unreviewed_message=(
                f"发现 {coverage.uncovered_count} 个未覆盖的疑似自定义控制符，"
                "请先导入普通占位符规则或确认当前候选风险"
            ),
            reviewed_code="placeholder_uncovered_reviewed",
            reviewed_message=(
                f"仍有 {coverage.uncovered_count} 个未覆盖的疑似自定义控制符；"
                "当前候选已通过导入命令确认风险"
            ),
            custom_rules_supplied=custom_placeholder_rules_supplied,
        )
    if coverage.rule_domain == STRUCTURED_PLACEHOLDER_RULE_DOMAIN:
        return await build_rule_review_decision(
            session=session,
            coverage=coverage,
            stage=stage,
            unreviewed_code="structured_placeholder_uncovered",
            unreviewed_message=(
                f"发现 {coverage.uncovered_count} 个未被结构化规则覆盖的协议外壳候选，"
                "请先导入结构化占位符规则或确认当前候选风险"
            ),
            reviewed_code="structured_placeholder_uncovered_reviewed",
            reviewed_message=(
                f"仍有 {coverage.uncovered_count} 个未被结构化规则覆盖的协议外壳候选；"
                "当前候选已通过导入命令确认风险"
            ),
            custom_rules_supplied=False,
        )
    raise ValueError(f"不支持的占位符候选审查域: {coverage.rule_domain}")


async def collect_source_snapshot_fingerprint(session: TargetGameSession) -> str:
    """读取数据库可信源快照 manifest 并生成稳定指纹。"""
    records = await session.read_source_snapshot_records()
    return source_snapshot_records_fingerprint(records)


def source_snapshot_records_payload(records: list[SourceSnapshotFileRecord]) -> JsonArray:
    """把可信源快照 manifest 转换为稳定 JSON payload。"""
    return [
        {
            "relative_path": record.relative_path,
            "sha256": record.sha256,
            "byte_size": record.byte_size,
        }
        for record in sorted(records, key=lambda item: item.relative_path)
    ]


def source_snapshot_records_fingerprint(records: list[SourceSnapshotFileRecord]) -> str:
    """对可信源快照 manifest 的结构化内容生成稳定指纹。"""
    return stable_json_fingerprint(source_snapshot_records_payload(records))


async def collect_text_index_rules_fingerprint(
    *,
    session: TargetGameSession,
    text_rules: TextRules,
) -> str:
    """对影响翻译源文本范围的配置和数据库规则生成稳定指纹。"""
    payload: JsonObject = {
        "source_language": session.source_language,
        "target_language": session.target_language,
        "prompt_context_version": TEXT_INDEX_PROMPT_CONTEXT_VERSION,
        "text_rules": coerce_json_value(cast(object, text_rules.setting.model_dump(mode="json"))),
        "plugin_text_rules": _plugin_text_rules_payload(await session.read_plugin_text_rules()),
        "plugin_source_text_rules": _plugin_source_text_rules_payload(
            await session.read_plugin_source_text_rules()
        ),
        "event_command_text_rules": _event_command_text_rules_payload(
            await session.read_event_command_text_rules()
        ),
        "note_tag_text_rules": _note_tag_text_rules_payload(await session.read_note_tag_text_rules()),
        "nonstandard_data_text_rules": _nonstandard_data_text_rules_payload(
            await session.read_nonstandard_data_text_rules()
        ),
        "placeholder_rules": _placeholder_rules_payload(await session.read_placeholder_rules()),
        "structured_placeholder_rules": _structured_placeholder_rules_payload(
            await session.read_structured_placeholder_rules()
        ),
        "mv_virtual_namebox_rules": _mv_virtual_namebox_rules_payload(
            await session.read_mv_virtual_namebox_rules()
        ),
    }
    return stable_json_fingerprint(payload)


async def _read_latest_quality_error_fact_ids(session: TargetGameSession) -> set[str]:
    """读取最新翻译运行中没通过项目检查的 fact_id，用于 Rust quality gate 摘要。"""
    latest_run = await session.read_latest_translation_run()
    if latest_run is None:
        return set()
    return await read_text_fact_quality_error_fact_ids(session, latest_run.run_id)


def _scope_gate_payload_from_text_fact_records(
    *,
    records: Iterable[TextIndexItemRecord],
    facts: Iterable[TextFactRecord],
    matched_translation_fact_ids: Iterable[str],
    quality_error_fact_ids: Iterable[str],
    required_paths: Iterable[str],
) -> JsonObject:
    """把当前文本事实 转换为 Rust evaluate_scope_gate 输入。"""
    record_list = list(records)
    index_by_path = {record.location_path: record for record in record_list}
    facts_by_path: dict[str, list[TextFactRecord]] = {}
    for fact in facts:
        if fact.location_path in index_by_path:
            facts_by_path.setdefault(fact.location_path, []).append(fact)
    missing_fact_paths = sorted(
        record.location_path
        for record in record_list
        if record.location_path not in facts_by_path
    )
    if missing_fact_paths:
        samples = "、".join(missing_fact_paths[:5])
        suffix = f" 等 {len(missing_fact_paths)} 条" if len(missing_fact_paths) > 5 else ""
        raise RuntimeError(
            f"当前文本索引记录缺少 当前文本事实，不能继续评估范围门禁: {samples}{suffix}。"
            + "下一步：请运行 rebuild-text-index 重新生成当前文本索引。"
        )
    entries: JsonArray = []
    for record in record_list:
        for fact in facts_by_path[record.location_path]:
            entries.append(_scope_gate_entry_from_text_fact(record=record, fact=fact))
    return {
        "entries": entries,
        "matched_translation_fact_ids": _string_array(sorted(set(matched_translation_fact_ids))),
        "quality_error_fact_ids": _string_array(sorted(set(quality_error_fact_ids))),
        "required_paths": _string_array(sorted(set(required_paths))),
    }


def _scope_gate_entry_from_text_fact(
    *,
    record: TextIndexItemRecord,
    fact: TextFactRecord,
) -> JsonObject:
    """把单条 current text fact 和索引定位元信息还原为 Rust 范围门禁 entry。"""
    locator = coerce_json_value(cast(object, json.loads(record.locator_json)))
    item_type = item_type_from_text_fact(fact)
    return {
        "fact_id": fact.fact_id,
        "location_path": record.location_path,
        "item_type": item_type,
        "role": fact.role or None,
        "original_lines": _string_array(text_fact_lines(fact.translatable_text, item_type=item_type)),
        "source_line_paths": _string_array(record.source_line_paths),
        "source_type": fact.source_type,
        "source_file": fact.source_file,
        "rule_source": "text_index",
        "enters_translation": True,
        "can_write_back": record.writable,
        "cannot_process_reason": "" if record.writable else "索引项不可写回",
        "locator": locator,
    }


def text_index_item_to_translation_item(
    record: TextIndexItemRecord,
    *,
    locator: JsonObject | None = None,
) -> TranslationItem:
    """把文本范围索引项还原为保存校验使用的翻译条目。"""
    locator_object = locator if locator is not None else _locator_object_from_json(record.locator_json)
    return TranslationItem(
        location_path=record.location_path,
        item_type=record.item_type,
        role=record.role,
        original_lines=list(record.original_lines),
        source_line_paths=list(record.source_line_paths),
        terminology_owner_terms=_terminology_owner_terms_from_locator(locator_object),
    )


def text_index_items_to_translation_data_map(
    records: Iterable[TextIndexItemRecord],
) -> dict[str, TranslationData]:
    """把文本范围索引项按来源文件还原为翻译批次输入。"""
    translation_data_map: dict[str, TranslationData] = {}
    for record in records:
        locator = _locator_object_from_json(record.locator_json)
        display_name = _display_name_from_locator(locator)
        translation_data = translation_data_map.get(record.source_file)
        if translation_data is None:
            translation_data = TranslationData(display_name=display_name, translation_items=[])
            translation_data_map[record.source_file] = translation_data
        elif display_name is not None:
            if translation_data.display_name is None:
                translation_data.display_name = display_name
            elif translation_data.display_name != display_name:
                raise RuntimeError(f"文本范围索引来源文件 {record.source_file} 的地图名不一致")
        translation_data.translation_items.append(text_index_item_to_translation_item(record, locator=locator))
    return translation_data_map


def _locator_object_from_json(locator_json: str) -> JsonObject:
    """读取索引定位元数据对象。"""
    locator = coerce_json_value(cast(object, json.loads(locator_json)))
    if not isinstance(locator, dict):
        raise RuntimeError("文本范围索引 locator_json 必须是对象")
    return locator


def _display_name_from_locator(locator: JsonObject) -> str | None:
    """从索引定位元数据读取可选地图显示名。"""
    raw_display_name = locator.get("display_name")
    if raw_display_name is None:
        return None
    if not isinstance(raw_display_name, str):
        raise RuntimeError("文本范围索引 locator_json.display_name 必须是字符串或 null")
    if not raw_display_name:
        return None
    return raw_display_name


def _terminology_owner_terms_from_locator(locator: JsonObject) -> list[str]:
    """从索引定位元数据读取可选数据库条目名称术语。"""
    raw_owner_terms = locator.get("terminology_owner_terms")
    if raw_owner_terms is None:
        return []
    if not isinstance(raw_owner_terms, list):
        raise RuntimeError("文本范围索引 locator_json.terminology_owner_terms 必须是字符串数组")
    owner_terms: list[str] = []
    for index, raw_term in enumerate(raw_owner_terms):
        if not isinstance(raw_term, str):
            raise RuntimeError(f"文本范围索引 locator_json.terminology_owner_terms[{index}] 必须是字符串")
        if raw_term:
            owner_terms.append(raw_term)
    return owner_terms


def stable_json_fingerprint(payload: JsonValue) -> str:
    """对 JSON 值生成稳定 SHA-256 指纹。"""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_array(values: Iterable[str]) -> JsonArray:
    """把字符串迭代器收窄为 JSON 字符串数组。"""
    result: JsonArray = []
    for value in values:
        result.append(value)
    return result


def _plugin_text_rules_payload(records: list[PluginTextRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: item.plugin_index):
        payload.append(
            {
                "plugin_index": record.plugin_index,
                "plugin_name": record.plugin_name,
                "plugin_hash": record.plugin_hash,
                "path_templates": _string_array(record.path_templates),
            }
        )
    return payload


def _plugin_source_text_rules_payload(records: list[PluginSourceTextRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: item.file_name):
        payload.append(
            {
                "file_name": record.file_name,
                "selectors": _string_array(sorted(record.selectors)),
                "excluded_selectors": _string_array(sorted(record.excluded_selectors)),
            }
        )
    return payload


def _event_command_text_rules_payload(records: list[EventCommandTextRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(
        records,
        key=lambda item: (
            item.command_code,
            [(filter_item.index, filter_item.value) for filter_item in item.parameter_filters],
            item.path_templates,
        ),
    ):
        parameter_filters: JsonArray = [
            {"index": item.index, "value": item.value}
            for item in sorted(record.parameter_filters, key=lambda item: (item.index, item.value))
        ]
        payload.append(
            {
                "command_code": record.command_code,
                "parameter_filters": parameter_filters,
                "path_templates": _string_array(sorted(record.path_templates)),
            }
        )
    return payload


def _note_tag_text_rules_payload(records: list[NoteTagTextRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: item.file_name):
        payload.append(
            {
                "file_name": record.file_name,
                "tag_names": _string_array(sorted(record.tag_names)),
            }
        )
    return payload


def _nonstandard_data_text_rules_payload(records: list[NonstandardDataTextRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: item.file_name):
        payload.append(
            {
                "file_name": record.file_name,
                "file_hash": record.file_hash,
                "path_templates": _string_array(sorted(record.path_templates)),
                "excluded_path_templates": _string_array(sorted(record.excluded_path_templates)),
                "skipped": record.skipped,
            }
        )
    return payload


def _placeholder_rules_payload(records: list[PlaceholderRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: (item.pattern_text, item.placeholder_template)):
        payload.append(
            {
                "pattern_text": record.pattern_text,
                "placeholder_template": record.placeholder_template,
            }
        )
    return payload


def _structured_placeholder_rules_payload(records: list[StructuredPlaceholderRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: item.rule_name):
        protected_groups: JsonObject = {
            key: record.protected_groups[key]
            for key in sorted(record.protected_groups)
        }
        payload.append(
            {
                "rule_name": record.rule_name,
                "rule_type": record.rule_type,
                "pattern_text": record.pattern_text,
                "translatable_group": record.translatable_group,
                "protected_groups": protected_groups,
            }
        )
    return payload


def _mv_virtual_namebox_rules_payload(records: list[MvVirtualNameboxRuleRecord]) -> JsonArray:
    payload: JsonArray = []
    for record in sorted(records, key=lambda item: item.rule_order):
        payload.append(
            {
                "rule_order": record.rule_order,
                "rule_name": record.rule_name,
                "pattern_text": record.pattern_text,
                "speaker_group": record.speaker_group,
                "body_group": record.body_group,
                "speaker_policy": record.speaker_policy,
                "render_template": record.render_template,
            }
        )
    return payload


__all__ = [
    "collect_text_index_external_rule_gate_errors",
    "collect_text_index_placeholder_gate_decisions",
    "collect_text_index_placeholder_gate_errors",
    "collect_text_index_scope_gate_errors",
    "collect_source_snapshot_fingerprint",
    "collect_text_index_rules_fingerprint",
    "detect_text_index_invalidations",
    "evaluate_text_index_scope_gate",
    "rebuild_text_index_native_storage",
    "rebuild_text_index_native_storage_with_summary",
    "source_snapshot_records_fingerprint",
    "stable_json_fingerprint",
    "text_index_item_to_translation_item",
    "text_index_items_to_translation_data_map",
    "text_index_source_branch_gates_prechecked",
    "text_fact_rebuild_report_fields",
]
