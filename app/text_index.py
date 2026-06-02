"""当前翻译源文本范围的持久索引构建与失效检测。"""

import hashlib
import json
from collections.abc import Iterable
from typing import cast

from app.application.flow_gate import (
    event_command_rule_scope_hash_for_setting,
    note_tag_rule_scope_hash_for_text_rules,
)
from app.config.schemas import Setting
from app.persistence import TargetGameSession
from app.persistence.records import TextIndexInvalidationRecord, TextIndexItemRecord, TextIndexMetadata
from app.persistence.repository import current_timestamp_text
from app.rmmz.mv_namebox import mv_virtual_namebox_candidate_details
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    GameData,
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
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    RuleReviewDomain,
    mv_virtual_namebox_rule_scope_hash,
    plugin_rule_scope_hash,
)
from app.rule_review_decision import WorkflowGateIssue, build_empty_rule_review_decision
from app.text_scope import TextScopeResult, TextScopeService, TextSourceType


async def rebuild_text_index(
    *,
    session: TargetGameSession,
    game_data: GameData,
    setting: Setting,
    text_rules: TextRules,
    scope: TextScopeResult | None = None,
    include_write_probe: bool = False,
) -> TextIndexMetadata:
    """重建并保存当前翻译源文本范围索引。"""
    if scope is None:
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
            include_write_probe=include_write_probe,
        )
    source_snapshot_fingerprint = await collect_source_snapshot_fingerprint(session)
    rules_fingerprint = await collect_text_index_rules_fingerprint(
        session=session,
        text_rules=text_rules,
    )
    items = build_text_index_items_from_scope(
        scope=scope,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        rules_fingerprint=rules_fingerprint,
    )
    metadata = TextIndexMetadata(
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        rules_fingerprint=rules_fingerprint,
        item_count=len(items),
        workflow_gate_scope_hashes=build_text_index_workflow_gate_scope_hashes(
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
        ),
        created_at=current_timestamp_text(),
    )
    await session.replace_text_index(metadata=metadata, items=items)
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
        scope_hashes[MV_VIRTUAL_NAMEBOX_RULE_DOMAIN] = mv_virtual_namebox_rule_scope_hash(
            mv_virtual_namebox_candidate_details(game_data)
        )
    return scope_hashes


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


async def collect_source_snapshot_fingerprint(session: TargetGameSession) -> str:
    """读取数据库可信源快照 manifest 并生成稳定指纹。"""
    records = await session.read_source_snapshot_records()
    return source_snapshot_records_fingerprint(records)


def source_snapshot_records_fingerprint(records: list[SourceSnapshotFileRecord]) -> str:
    """对可信源快照 manifest 的结构化内容生成稳定指纹。"""
    return stable_json_fingerprint(
        [
            {
                "relative_path": record.relative_path,
                "sha256": record.sha256,
                "byte_size": record.byte_size,
            }
            for record in sorted(records, key=lambda item: item.relative_path)
        ]
    )


async def collect_text_index_rules_fingerprint(
    *,
    session: TargetGameSession,
    text_rules: TextRules,
) -> str:
    """对影响翻译源文本范围的配置和数据库规则生成稳定指纹。"""
    payload: JsonObject = {
        "source_language": session.source_language,
        "target_language": session.target_language,
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


def build_text_index_items_from_scope(
    *,
    scope: TextScopeResult,
    source_snapshot_fingerprint: str,
    rules_fingerprint: str,
) -> list[TextIndexItemRecord]:
    """把统一文本范围结果转换成可持久化索引项。"""
    entries_by_path = {
        entry.location_path: entry
        for entry in scope.entries
        if entry.enters_translation
    }
    records: list[TextIndexItemRecord] = []
    for file_name in sorted(scope.translation_data_map):
        translation_data = scope.translation_data_map[file_name]
        for item in translation_data.translation_items:
            entry = entries_by_path.get(item.location_path)
            if entry is None:
                raise RuntimeError(f"文本范围索引缺少 active entry: {item.location_path}")
            records.append(
                TextIndexItemRecord(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    source_line_paths=list(item.source_line_paths),
                    source_type=entry.source_type,
                    source_file=file_name,
                    writable=entry.can_write_back,
                    source_snapshot_fingerprint=source_snapshot_fingerprint,
                    rules_fingerprint=rules_fingerprint,
                    locator_json=_locator_json(
                        file_name=file_name,
                        source_type=entry.source_type,
                        location_path=item.location_path,
                        source_line_paths=item.source_line_paths,
                    ),
                )
            )
    records.sort(key=lambda item: item.location_path)
    return records


def text_index_item_to_translation_item(record: TextIndexItemRecord) -> TranslationItem:
    """把文本范围索引项还原为保存校验使用的翻译条目。"""
    return TranslationItem(
        location_path=record.location_path,
        item_type=record.item_type,
        role=record.role,
        original_lines=list(record.original_lines),
        source_line_paths=list(record.source_line_paths),
    )


def text_index_items_to_translation_data_map(
    records: Iterable[TextIndexItemRecord],
) -> dict[str, TranslationData]:
    """把文本范围索引项按来源文件还原为翻译批次输入。"""
    translation_data_map: dict[str, TranslationData] = {}
    for record in records:
        translation_data = translation_data_map.setdefault(
            record.source_file,
            TranslationData(display_name=None, translation_items=[]),
        )
        translation_data.translation_items.append(text_index_item_to_translation_item(record))
    return translation_data_map


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


def _locator_json(
    *,
    file_name: str,
    source_type: TextSourceType,
    location_path: str,
    source_line_paths: list[str],
) -> str:
    """生成索引定位元数据 JSON。"""
    payload: JsonObject = {
        "file_name": file_name,
        "source_type": source_type,
        "location_path": location_path,
        "source_line_paths": list(source_line_paths),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    "build_text_index_items_from_scope",
    "build_text_index_workflow_gate_scope_hashes",
    "collect_text_index_external_rule_gate_errors",
    "collect_source_snapshot_fingerprint",
    "collect_text_index_rules_fingerprint",
    "detect_text_index_invalidations",
    "rebuild_text_index",
    "source_snapshot_records_fingerprint",
    "stable_json_fingerprint",
    "text_index_item_to_translation_item",
    "text_index_items_to_translation_data_map",
]
