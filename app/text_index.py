"""当前翻译源文本范围的持久索引构建与失效检测。"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict
from typing import cast

from app.application.flow_gate import (
    build_normal_placeholder_coverage_result,
    build_structured_placeholder_coverage_result,
    event_command_rule_scope_hash_for_setting,
    mv_virtual_namebox_rule_scope_hash_for_game_data,
    note_tag_rule_scope_hash_for_text_rules,
)
from app.config import SettingOverrides
from app.config.schemas import Setting
from app.native_scope_index import (
    NativeScopeGateResult,
    NativeScopeIndexResult,
    build_native_scope_index,
    evaluate_native_scope_gate,
)
from app.plugin_source_text import PluginSourceScan
from app.persistence import TargetGameSession
from app.persistence.records import (
    TextIndexDomainSummaryRecord,
    TextIndexInvalidationRecord,
    TextIndexItemRecord,
    TextIndexMetadata,
    TextIndexRuleHitSummaryRecord,
    TextIndexScopeSummaryRecord,
)
from app.persistence.repository import current_timestamp_text
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    GameData,
    ItemType,
    MvVirtualNameboxRuleRecord,
    NonstandardDataTextRuleRecord,
    NoteTagTextRuleRecord,
    PlaceholderRuleRecord,
    PluginSourceTextRuleRecord,
    PluginTextRuleRecord,
    StructuredPlaceholderRuleRecord,
    SYSTEM_FILE_NAME,
    TranslationData,
    TranslationItem,
)
from app.rmmz.source_snapshot import SourceSnapshotFileRecord
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue, TextRules, coerce_json_value
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    RuleReviewDomain,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    plugin_rule_scope_hash,
)
from app.rule_review_decision import (
    RuleCoverageResult,
    RuleReviewDecision,
    WorkflowGateIssue,
    build_empty_rule_review_decision,
    build_rule_review_decision,
)
from app.terminology.extraction import BASE_NAME_CATEGORIES, SYSTEM_TERM_CATEGORIES
from app.text_scope import TextScopeEntry, TextScopeResult, TextScopeService, TextScopeSnapshot, TextSourceType

TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY = "workflow_gate_prechecked:plugin_source_text"
TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY = "workflow_gate_prechecked:nonstandard_data"
TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE = "passed_v1"
TEXT_INDEX_PLACEHOLDER_GATE_PREFIX = "workflow_gate:placeholder_rules"
TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX = "workflow_gate:structured_placeholder_rules"
TEXT_INDEX_PROMPT_CONTEXT_VERSION = "display_name_owner_system_terms_v3"


async def rebuild_text_index(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    setting_overrides: SettingOverrides | None = None,
    scope: TextScopeResult | None = None,
    plugin_source_scan: PluginSourceScan | None = None,
    include_write_probe: bool = False,
    source_branch_workflow_gates_prechecked: bool = False,
) -> TextIndexMetadata:
    """重建并保存当前翻译源文本范围索引。"""
    if scope is None:
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            include_write_probe=include_write_probe,
            plugin_source_scan=plugin_source_scan,
        )
    source_snapshot_records = await session.read_source_snapshot_records()
    source_snapshot_fingerprint = source_snapshot_records_fingerprint(source_snapshot_records)
    rules_fingerprint = await collect_text_index_rules_fingerprint(
        session=session,
        text_rules=text_rules,
    )
    snapshot = TextScopeSnapshot.from_scope(
        scope=scope,
        rules_fingerprint=rules_fingerprint,
        setting_overrides=setting_overrides_payload(setting_overrides),
        source_manifest=source_snapshot_records_payload(source_snapshot_records),
    )
    native_scope_index = build_native_scope_index(
        _scope_index_payload_from_scope(
            game_data=game_data,
            scope=scope,
            source_snapshot_fingerprint=source_snapshot_fingerprint,
            rules_fingerprint=snapshot.rules_fingerprint,
        )
    )
    items = _text_index_records_from_native_rows(native_scope_index)
    metadata = TextIndexMetadata(
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        rules_fingerprint=rules_fingerprint,
        item_count=len(items),
        workflow_gate_scope_hashes=build_text_index_workflow_gate_scope_hashes(
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            scope=scope,
            source_branch_workflow_gates_prechecked=source_branch_workflow_gates_prechecked,
        ),
        created_at=current_timestamp_text(),
    )
    await session.replace_text_index(
        metadata=metadata,
        items=items,
        scope_summary=_scope_summary_record_from_native(native_scope_index),
        domain_summary=_domain_summary_records_from_native(native_scope_index),
        rule_hit_summary=_rule_hit_summary_records_from_native(native_scope_index),
    )
    return metadata


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


def build_text_index_workflow_gate_scope_hashes(
    *,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    scope: TextScopeResult,
    source_branch_workflow_gates_prechecked: bool = False,
) -> dict[str, str]:
    """计算 warm index 可复用的外部规则空确认范围哈希。"""
    scope_hashes: dict[str, str] = {
        PLUGIN_TEXT_RULE_DOMAIN: plugin_rule_scope_hash(game_data),
        EVENT_COMMAND_TEXT_RULE_DOMAIN: event_command_rule_scope_hash_for_setting(
            game_data=game_data,
            setting=setting,
        ),
        NOTE_TAG_TEXT_RULE_DOMAIN: note_tag_rule_scope_hash_for_text_rules(
            game_data=game_data,
            text_rules=text_rules,
        ),
    }
    if game_data.layout.engine_kind == "mv":
        scope_hashes[MV_VIRTUAL_NAMEBOX_RULE_DOMAIN] = mv_virtual_namebox_rule_scope_hash_for_game_data(game_data)
    if source_branch_workflow_gates_prechecked:
        scope_hashes[TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY] = TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE
        scope_hashes[TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY] = TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE
    scope_hashes.update(_placeholder_gate_metadata(scope=scope, text_rules=text_rules))
    return scope_hashes


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
    coverage_or_errors = _placeholder_coverages_from_metadata(metadata)
    if isinstance(coverage_or_errors, list):
        return coverage_or_errors
    placeholder_coverage, structured_coverage = coverage_or_errors
    placeholder_decision = await _text_index_placeholder_review_decision(
        session=session,
        coverage=placeholder_coverage,
        custom_placeholder_rules_supplied=custom_placeholder_rules_supplied,
    )
    structured_decision = await _text_index_placeholder_review_decision(
        session=session,
        coverage=structured_coverage,
        custom_placeholder_rules_supplied=False,
    )
    return [
        decision.to_issue()
        for decision in (placeholder_decision, structured_decision)
        if decision.severity == "error"
    ]


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
    if (
        MV_VIRTUAL_NAMEBOX_RULE_DOMAIN in metadata.workflow_gate_scope_hashes
        and not await session.read_mv_virtual_namebox_rules()
    ):
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
    """用持久索引项和已保存译文状态调用 Rust 范围门禁摘要。"""
    latest_quality_error_paths = await _read_latest_quality_error_paths(session)
    return evaluate_native_scope_gate(
        _scope_gate_payload_from_text_index_items(
            records=records,
            translated_paths=await session.read_translation_location_paths(),
            quality_error_paths=latest_quality_error_paths,
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
        return [
            WorkflowGateIssue(
                code="text_index_workflow_gate_metadata_missing",
                message=f"持久文本范围索引缺少{label}确认范围，请重新运行 rebuild-text-index",
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


def _placeholder_gate_metadata(*, scope: TextScopeResult, text_rules: TextRules) -> dict[str, str]:
    """构建 warm index 可复用的占位符候选覆盖摘要。"""
    placeholder_coverage = build_normal_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        text_rules=text_rules,
        rule_count=len(text_rules.custom_placeholder_rules),
    )
    structured_coverage = build_structured_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        structured_rules=text_rules.structured_placeholder_rules,
        rule_count=len(text_rules.structured_placeholder_rules),
    )
    metadata: dict[str, str] = {}
    metadata.update(_placeholder_coverage_metadata(TEXT_INDEX_PLACEHOLDER_GATE_PREFIX, placeholder_coverage))
    metadata.update(
        _placeholder_coverage_metadata(
            TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX,
            structured_coverage,
        )
    )
    return metadata


def _placeholder_coverage_metadata(prefix: str, coverage: RuleCoverageResult) -> dict[str, str]:
    """把候选覆盖摘要编码进 text index metadata 字符串字典。"""
    return {
        f"{prefix}:scope_hash": coverage.scope_hash,
        f"{prefix}:rule_count": str(coverage.rule_count),
        f"{prefix}:candidate_count": str(coverage.candidate_count),
        f"{prefix}:covered_count": str(coverage.covered_count),
        f"{prefix}:uncovered_count": str(coverage.uncovered_count),
    }


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
) -> RuleReviewDecision:
    """按索引里的占位符覆盖摘要生成 workflow gate 审查决策。"""
    if coverage.rule_domain == PLACEHOLDER_RULE_DOMAIN:
        return await build_rule_review_decision(
            session=session,
            coverage=coverage,
            stage="workflow_gate",
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
            stage="workflow_gate",
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


def setting_overrides_payload(overrides: SettingOverrides | None) -> JsonObject:
    """把本次命令配置覆盖转换为快照 payload。"""
    if overrides is None or not overrides.has_any():
        return {}
    payload: JsonObject = {}
    raw_payload = cast(dict[str, object], asdict(overrides))
    for key, raw_value in raw_payload.items():
        if key == "text_translation_rpm" and not overrides.text_translation_rpm_is_set:
            continue
        if raw_value is None:
            continue
        payload[key] = coerce_json_value(raw_value)
    return payload


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


def _scope_index_payload_from_scope(
    *,
    game_data: GameData,
    scope: TextScopeResult,
    source_snapshot_fingerprint: str,
    rules_fingerprint: str,
) -> JsonObject:
    """把当前 Python scope 过渡转换为 Rust Scope/Index Engine 输入。"""
    source_file_by_path: dict[str, str] = {}
    display_name_by_path: dict[str, str | None] = {}
    active_item_by_path: dict[str, TranslationItem] = {}
    owner_context = _terminology_owner_context(game_data=game_data)
    for file_name, translation_data in scope.translation_data_map.items():
        for item in translation_data.translation_items:
            source_file_by_path[item.location_path] = file_name
            display_name_by_path[item.location_path] = translation_data.display_name
            active_item_by_path[item.location_path] = item

    entries: JsonArray = []
    for entry in scope.entries:
        item = active_item_by_path.get(entry.location_path)
        source_line_paths = list(item.source_line_paths) if item is not None else []
        source_file = source_file_by_path.get(
            entry.location_path,
            _source_file_from_location_path(entry.location_path),
        )
        locator: JsonObject = {
            "file_name": source_file,
            "source_type": entry.source_type,
            "location_path": entry.location_path,
            "source_line_paths": [path for path in source_line_paths],
        }
        display_name = display_name_by_path.get(entry.location_path)
        if display_name:
            locator["display_name"] = display_name
        owner_terms = _terminology_owner_terms_for_location_path(
            owner_context=owner_context,
            location_path=entry.location_path,
        )
        if owner_terms:
            locator["terminology_owner_terms"] = [term for term in owner_terms]
        entry_payload: JsonObject = {
            "location_path": entry.location_path,
            "item_type": entry.item_type,
            "role": entry.role,
            "original_lines": [line for line in entry.original_lines],
            "source_line_paths": [path for path in source_line_paths],
            "source_type": entry.source_type,
            "source_file": source_file,
            "rule_source": entry.rule_source,
            "enters_translation": entry.enters_translation,
            "can_write_back": entry.can_write_back,
            "cannot_process_reason": entry.cannot_process_reason,
            "locator": locator,
        }
        entries.append(entry_payload)

    return {
        "source_snapshot_fingerprint": source_snapshot_fingerprint,
        "rules_fingerprint": rules_fingerprint,
        "entries": entries,
        "stale_rule_details": [
            {
                "domain": "plugin_config",
                "rule_key": f"{rule.plugin_index}:{rule.plugin_name}",
                "reason": rule.reason,
            }
            for rule in scope.stale_plugin_rules
        ],
    }


async def _read_latest_quality_error_paths(session: TargetGameSession) -> set[str]:
    """读取最新翻译运行中没通过项目检查的路径，用于 Rust quality gate 摘要。"""
    latest_run = await session.read_latest_translation_run()
    if latest_run is None:
        return set()
    return await session.read_text_index_quality_error_paths(latest_run.run_id)


def _scope_gate_payload_from_text_index_items(
    *,
    records: Iterable[TextIndexItemRecord],
    translated_paths: Iterable[str],
    quality_error_paths: Iterable[str],
    required_paths: Iterable[str],
) -> JsonObject:
    """把持久索引项转换为 Rust evaluate_scope_gate 输入。"""
    return {
        "entries": coerce_json_value([_scope_gate_entry_from_text_index_item(record) for record in records]),
        "translated_paths": _string_array(sorted(set(translated_paths))),
        "quality_error_paths": _string_array(sorted(set(quality_error_paths))),
        "required_paths": _string_array(sorted(set(required_paths))),
    }


def _scope_gate_entry_from_text_index_item(record: TextIndexItemRecord) -> JsonObject:
    """把单条索引项还原为 Rust 范围门禁 entry。"""
    locator = coerce_json_value(cast(object, json.loads(record.locator_json)))
    return {
        "location_path": record.location_path,
        "item_type": record.item_type,
        "role": record.role,
        "original_lines": _string_array(record.original_lines),
        "source_line_paths": _string_array(record.source_line_paths),
        "source_type": record.source_type,
        "source_file": record.source_file,
        "rule_source": "text_index",
        "enters_translation": True,
        "can_write_back": record.writable,
        "cannot_process_reason": "" if record.writable else "索引项不可写回",
        "locator": locator,
    }


def _text_index_records_from_native_rows(
    native_scope_index: NativeScopeIndexResult,
) -> list[TextIndexItemRecord]:
    """把 Rust text index rows 转换为持久化记录。"""
    records = [
        TextIndexItemRecord(
            location_path=_read_json_string(row, "location_path"),
            item_type=_read_json_item_type(row, "item_type"),
            role=_read_optional_json_string(row, "role"),
            original_lines=_read_json_string_list(row, "original_lines"),
            source_line_paths=_read_json_string_list(row, "source_line_paths"),
            source_type=_read_json_string(row, "source_type"),
            source_file=_read_json_string(row, "source_file"),
            writable=_read_json_bool(row, "writable"),
            source_snapshot_fingerprint=_read_json_string(row, "source_snapshot_fingerprint"),
            rules_fingerprint=_read_json_string(row, "rules_fingerprint"),
            locator_json=_read_json_string(row, "locator_json"),
        )
        for row in native_scope_index.text_index_rows
    ]
    records.sort(key=lambda item: item.location_path)
    return records


def _scope_summary_record_from_native(
    native_scope_index: NativeScopeIndexResult,
) -> TextIndexScopeSummaryRecord:
    """把 Rust scope summary 转换为持久化记录。"""
    summary = native_scope_index.scope_summary
    return TextIndexScopeSummaryRecord(
        total_count=_read_json_int(summary, "total_count"),
        active_count=_read_json_int(summary, "active_count"),
        writable_count=_read_json_int(summary, "writable_count"),
        unwritable_count=_read_json_int(summary, "unwritable_count"),
        stale_rule_count=_read_json_int(summary, "stale_rule_count"),
        native_thread_count=_read_json_int(summary, "native_thread_count"),
    )


def _domain_summary_records_from_native(
    native_scope_index: NativeScopeIndexResult,
) -> list[TextIndexDomainSummaryRecord]:
    """把 Rust domain summary 转换为持久化记录。"""
    return [
        TextIndexDomainSummaryRecord(
            domain=_read_json_string(row, "domain"),
            item_count=_read_json_int(row, "item_count"),
            active_count=_read_json_int(row, "active_count"),
            writable_count=_read_json_int(row, "writable_count"),
            unwritable_count=_read_json_int(row, "unwritable_count"),
            inactive_rule_hit_count=_read_json_int(row, "inactive_rule_hit_count"),
        )
        for row in native_scope_index.domain_summary
    ]


def _rule_hit_summary_records_from_native(
    native_scope_index: NativeScopeIndexResult,
) -> list[TextIndexRuleHitSummaryRecord]:
    """把 Rust rule hit summary 转换为持久化记录。"""
    return [
        TextIndexRuleHitSummaryRecord(
            domain=_read_json_string(row, "domain"),
            rule_key=_read_json_string(row, "rule_key"),
            hit_count=_read_json_int(row, "hit_count"),
            extractable_count=_read_json_int(row, "extractable_count"),
            writable_count=_read_json_int(row, "writable_count"),
            unwritable_count=_read_json_int(row, "unwritable_count"),
        )
        for row in native_scope_index.rule_hit_summary
    ]


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
    """从索引定位元数据读取地图显示名，兼容旧索引缺失字段。"""
    raw_display_name = locator.get("display_name")
    if raw_display_name is None:
        return None
    if not isinstance(raw_display_name, str):
        raise RuntimeError("文本范围索引 locator_json.display_name 必须是字符串或 null")
    if not raw_display_name:
        return None
    return raw_display_name


def _terminology_owner_terms_from_locator(locator: JsonObject) -> list[str]:
    """从索引定位元数据读取数据库条目名称术语，兼容旧索引缺失字段。"""
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


def text_index_items_to_scope(
    records: Iterable[TextIndexItemRecord],
    *,
    translated_paths: set[str] | None = None,
) -> TextScopeResult:
    """把持久索引项还原为 workflow gate 可消费的最小文本范围。"""
    record_list = list(records)
    effective_translated_paths = translated_paths or set()
    translation_data_map = text_index_items_to_translation_data_map(record_list)
    entries: list[TextScopeEntry] = []
    for record in record_list:
        if record.source_type not in {
            "standard_data",
            "plugin_parameter",
            "plugin_source",
            "event_command",
            "note_tag",
            "nonstandard_data",
        }:
            raise RuntimeError(f"文本范围索引包含未知来源类型: {record.source_type}")
        entries.append(
            TextScopeEntry(
                location_path=record.location_path,
                source_type=cast(TextSourceType, record.source_type),
                rule_source="text_index",
                item_type=record.item_type,
                original_lines=list(record.original_lines),
                role=record.role,
                enters_translation=True,
                can_save_translation=True,
                can_write_back=record.writable,
                translated=record.location_path in effective_translated_paths,
                cannot_process_reason="" if record.writable else "索引项不可写回",
            )
        )
    return TextScopeResult(
        translation_data_map=translation_data_map,
        entries=entries,
    )


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


def _source_file_from_location_path(location_path: str) -> str:
    """从定位路径提取保守来源文件名。"""
    return location_path.split("/", 1)[0]


def _database_owner_terms_by_key(*, game_data: GameData | None) -> dict[str, list[str]]:
    """按数据库条目定位键收集名称类术语上下文。"""
    if game_data is None:
        return {}
    owner_terms_by_key: dict[str, list[str]] = {}
    for file_name in BASE_NAME_CATEGORIES:
        for item in game_data.base_data.get(file_name, []):
            if item is None:
                continue
            owner_terms = _database_owner_terms_for_item(
                file_name=file_name,
                name=item.name,
                nickname=item.nickname,
            )
            if owner_terms:
                owner_terms_by_key[f"{file_name}/{item.id}"] = owner_terms
    return owner_terms_by_key


def _terminology_owner_context(*, game_data: GameData | None) -> tuple[dict[str, list[str]], list[str]]:
    """收集 text index 可保存的术语 owner 上下文。"""
    if game_data is None:
        return {}, []
    return (
        _database_owner_terms_by_key(game_data=game_data),
        _system_owner_terms(game_data=game_data),
    )


def _database_owner_terms_for_item(*, file_name: str, name: str, nickname: str) -> list[str]:
    """提取单个数据库条目的名称类术语上下文。"""
    raw_terms = [name]
    if file_name == "Actors.json":
        raw_terms.append(nickname)
    owner_terms: list[str] = []
    for raw_term in raw_terms:
        term = raw_term.strip()
        if term and term not in owner_terms:
            owner_terms.append(term)
    return owner_terms


def _database_owner_key_from_location_path(location_path: str) -> str | None:
    """从文本定位路径提取数据库条目定位键。"""
    parts = location_path.split("/")
    if len(parts) < 2:
        return None
    return "/".join(parts[:2])


def _terminology_owner_terms_for_location_path(
    *,
    owner_context: tuple[dict[str, list[str]], list[str]],
    location_path: str,
) -> list[str]:
    """按文本定位路径读取所属数据库条目或 System 字段术语。"""
    owner_terms_by_key, system_terms = owner_context
    if location_path.startswith(f"{SYSTEM_FILE_NAME}/"):
        return system_terms
    owner_key = _database_owner_key_from_location_path(location_path)
    if owner_key is None:
        return []
    return owner_terms_by_key.get(owner_key, [])


def _system_owner_terms(*, game_data: GameData) -> list[str]:
    """提取 System 类型数组术语上下文。"""
    owner_terms: list[str] = []
    for field_name in SYSTEM_TERM_CATEGORIES:
        for raw_term in _read_system_owner_field_values(game_data=game_data, field_name=field_name):
            term = raw_term.strip()
            if term and term not in owner_terms:
                owner_terms.append(term)
    return owner_terms


def _read_system_owner_field_values(*, game_data: GameData, field_name: str) -> list[str]:
    """读取 System 类型数组，避免把动态字段访问传入索引构建流程。"""
    if field_name == "elements":
        return game_data.system.elements
    if field_name == "skillTypes":
        return game_data.system.skillTypes
    if field_name == "weaponTypes":
        return game_data.system.weaponTypes
    if field_name == "armorTypes":
        return game_data.system.armorTypes
    if field_name == "equipTypes":
        return game_data.system.equipTypes
    raise ValueError(f"未知 System 术语字段: {field_name}")


def _read_json_string(row: JsonObject, field_name: str) -> str:
    """读取 JSON 字符串字段。"""
    value = row[field_name]
    if not isinstance(value, str):
        raise TypeError(f"native_scope_index.{field_name} 必须是字符串")
    return value


def _read_optional_json_string(row: JsonObject, field_name: str) -> str | None:
    """读取 JSON 字符串或 null 字段。"""
    value = row[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"native_scope_index.{field_name} 必须是字符串或 null")
    return value


def _read_json_bool(row: JsonObject, field_name: str) -> bool:
    """读取 JSON 布尔字段。"""
    value = row[field_name]
    if not isinstance(value, bool):
        raise TypeError(f"native_scope_index.{field_name} 必须是布尔值")
    return value


def _read_json_int(row: JsonObject, field_name: str) -> int:
    """读取 JSON 整数字段。"""
    value = row[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"native_scope_index.{field_name} 必须是整数")
    return value


def _read_json_string_list(row: JsonObject, field_name: str) -> list[str]:
    """读取 JSON 字符串数组字段。"""
    value = row[field_name]
    if not isinstance(value, list):
        raise TypeError(f"native_scope_index.{field_name} 必须是数组")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"native_scope_index.{field_name}[{index}] 必须是字符串")
        strings.append(item)
    return strings


def _read_json_item_type(row: JsonObject, field_name: str) -> ItemType:
    """读取并校验文本类型字段。"""
    value = _read_json_string(row, field_name)
    if value not in {"long_text", "array", "short_text"}:
        raise TypeError(f"native_scope_index.{field_name} 不是有效文本类型: {value}")
    return cast(ItemType, value)


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
                "file_hash": record.file_hash,
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
    "build_text_index_workflow_gate_scope_hashes",
    "collect_text_index_external_rule_gate_errors",
    "collect_text_index_placeholder_gate_errors",
    "collect_text_index_scope_gate_errors",
    "collect_source_snapshot_fingerprint",
    "collect_text_index_rules_fingerprint",
    "detect_text_index_invalidations",
    "evaluate_text_index_scope_gate",
    "rebuild_text_index",
    "source_snapshot_records_fingerprint",
    "stable_json_fingerprint",
    "text_index_item_to_translation_item",
    "text_index_items_to_scope",
    "text_index_items_to_translation_data_map",
    "text_index_source_branch_gates_prechecked",
]
