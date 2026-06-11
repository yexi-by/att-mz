"""Agent 工具箱 RuleValidationAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonArray,
    JsonObject,
    NoteTagTextRuleRecord,
    Path,
    SourceResidualRuleRecord,
    TextRules,
    TranslationItem,
    _format_mv_namebox_rule_error,
    _note_tag_rule_hits_from_native_details,
    _note_tag_item_matches_rule,
    _plugin_source_rule_hits_from_scan,
    _RuleHitMetric,
    _validate_event_command_rule_records_with_context,
    _validate_mv_virtual_namebox_rules_with_context,
    _validate_note_tag_rule_records_with_context,
    _validate_plugin_source_rules_with_context,
    _write_json_object,
    build_native_plugin_rule_validation_context_from_import,
    build_event_command_rule_records_from_import_shape,
    build_plugin_rule_validation_report_from_native_context,
    build_rule_runtime_settings_patterns,
    export_note_tag_candidates_file,
    issue,
    load_setting,
    parse_event_command_rule_import_text,
    parse_note_tag_rule_import_text,
    parse_plugin_rule_import_text,
)
from .rule_identity import (
    RuleFactProbe,
    resolve_current_rule_fact_hits,
    resolve_current_rule_translation_items,
    stale_translation_fact_ids,
)
from app.text_fact_identity import require_translation_fact_identities
from app.event_command_text.native_validation import (
    NativeEventCommandRuleValidationContext,
    build_native_event_command_rule_validation_context,
)
from app.application.rule_import_backup import write_rule_import_translation_backup
from app.application.flow_gate import (
    ensure_empty_rule_confirmed,
    note_tag_rule_scope_hash_for_text_rules,
)
from app.config import Setting
from app.native_note_tag_scan import (
    build_note_tag_rule_records_from_native_candidates,
    collect_native_note_tag_hit_details,
)
from app.native_rule_runtime import (
    RuleImportCommitResult,
    RuleImportPrepareResult,
    RuleRuntimeIssue,
    commit_rule_import,
    prepare_rule_import,
)
from app.note_tag_text.sources import matched_note_file_names
from app.persistence import RuleImportUnitOfWork, TargetGameSession
from app.plugin_text import NativePluginRuleValidationContext
from app.plugin_source_text import (
    build_plugin_source_rule_records_from_import,
    collect_plugin_source_review_coverage,
    parse_plugin_source_rule_import_text,
    plugin_source_rule_records_to_import_json,
)
from app.plugin_source_text.importer import build_plugin_source_rule_scan_records_from_import
from app.rmmz.mv_namebox import (
    mv_virtual_namebox_rule_records_to_import_json,
    parse_mv_virtual_namebox_rule_import_text,
)
from app.rmmz.mv_namebox_native import native_mv_virtual_namebox_candidates_payload, scan_native_mv_virtual_namebox
from app.rmmz.schema import GameData, PluginSourceTextRuleRecord
from app.rule_review import (
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
)
from app.plugin_source_text import build_native_plugin_source_scan
from app.source_residual import parse_source_residual_rule_import_payload


def _note_tag_rule_prefixes(
    *,
    game_data: GameData,
    rule_records: list[NoteTagTextRuleRecord],
) -> list[str]:
    """返回 Note 标签规则影响的已保存译文路径前缀。"""
    return sorted(
        {
            f"{file_name}/"
            for record in rule_records
            for file_name in matched_note_file_names(game_data=game_data, file_pattern=record.file_name)
        }
    )


def _translation_items_matching_note_rules(
    *,
    translated_items: list[TranslationItem],
    rule_records: list[NoteTagTextRuleRecord],
) -> list[TranslationItem]:
    """按 Note 标签规则筛出实际属于规则范围的已保存译文。"""
    return [
        item
        for item in translated_items
        if any(_note_tag_item_matches_rule(item=item, rule_record=record) for record in rule_records)
    ]


def _plugin_source_rule_prefixes(rule_records: list[PluginSourceTextRuleRecord]) -> list[str]:
    """返回插件源码规则影响的已保存译文路径前缀。"""
    return sorted({f"js/plugins/{record.file_name}/" for record in rule_records})


def _plugin_source_file_prefixes(game_data: GameData) -> list[str]:
    """返回当前启用插件源码文件对应的已保存译文路径前缀。"""
    return sorted({f"js/plugins/{file_name}/" for file_name in game_data.plugin_source_files})


def _source_residual_rule_runtime_payload(
    *,
    mode: str,
    rules_payload: JsonObject,
    setting: Setting,
    db_path: Path | None,
) -> JsonObject:
    """构造源文残留规则运行时载荷。"""
    payload: JsonObject = {
        "mode": mode,
        "domain": "source_residual",
        "rules_payload": rules_payload,
        "game_context": {},
        "settings_runtime_patterns": build_rule_runtime_settings_patterns(setting),
    }
    if db_path is not None:
        payload["db_path"] = str(db_path)
    return payload


def _source_residual_prepare_report(
    *,
    result: RuleImportPrepareResult,
    records: list[SourceResidualRuleRecord],
) -> AgentReport:
    """把源文残留 rule_runtime prepare 结果转换成 Agent 报告。"""
    warnings = _rule_runtime_issues_to_agent_issues(result.warnings)
    if not records and not result.errors:
        warnings.append(issue("source_residual_rules_empty", "源文残留例外规则为空"))
    summary = _source_residual_rule_counts(records)
    summary["mode"] = _source_residual_summary_string(result.summary, "mode", "validate")
    summary["rule_runtime"] = _source_residual_rule_runtime_summary(result.summary)
    return AgentReport.from_parts(
        errors=_rule_runtime_issues_to_agent_issues(result.errors),
        warnings=warnings,
        summary=summary,
        details={"rules": _source_residual_rule_details(records)},
    )


def _source_residual_commit_report(
    *,
    result: RuleImportCommitResult,
    prepare_result: RuleImportPrepareResult,
    records: list[SourceResidualRuleRecord],
) -> AgentReport:
    """把源文残留 rule_runtime commit 结果转换成导入报告。"""
    warnings = [
        *_rule_runtime_issues_to_agent_issues(prepare_result.warnings),
        *_rule_runtime_issues_to_agent_issues(result.warnings),
    ]
    if not records and not result.errors:
        warnings.append(issue("source_residual_rules_empty", "已导入空源文残留例外规则"))
    summary = _source_residual_rule_counts(records if not result.errors else [])
    summary["mode"] = "import"
    summary["rule_runtime"] = _source_residual_rule_runtime_summary(prepare_result.summary)
    return AgentReport.from_parts(
        errors=_rule_runtime_issues_to_agent_issues(result.errors),
        warnings=warnings,
        summary=summary,
        details={"rules": _source_residual_rule_details(records if not result.errors else [])},
    )


def _source_residual_rule_counts(records: list[SourceResidualRuleRecord]) -> JsonObject:
    """统计源文残留规则报告字段。"""
    return {
        "rule_count": len(records),
        "position_rule_count": sum(1 for record in records if record.rule_type == "position"),
        "structural_rule_count": sum(1 for record in records if record.rule_type == "structural"),
        "term_count": sum(len(record.allowed_terms) for record in records),
    }


def _source_residual_rule_details(records: list[SourceResidualRuleRecord]) -> JsonArray:
    """渲染源文残留规则报告明细。"""
    details: JsonArray = []
    for record in records:
        details.append(
            {
                "rule_id": record.rule_id,
                "rule_type": record.rule_type,
                "location_path": record.location_path,
                "pattern": record.pattern_text,
                "allowed_terms": list(record.allowed_terms),
                "check_group": record.check_group,
                "reason": record.reason,
            }
        )
    return details


def _source_residual_rule_runtime_summary(summary: JsonObject) -> JsonObject:
    value = summary.get("rule_runtime", {})
    if isinstance(value, dict):
        return dict(value)
    return {}


def _source_residual_summary_string(summary: JsonObject, key: str, default: str) -> str:
    value = summary.get(key)
    if isinstance(value, str):
        return value
    return default


def _rule_runtime_issues_to_agent_issues(items: list[RuleRuntimeIssue]) -> list[AgentIssue]:
    return [issue(item.code, item.message) for item in items]


async def _resolve_rule_hit_metrics(
    *,
    session: TargetGameSession,
    domain: str,
    grouped_hits: list[list[_RuleHitMetric]],
) -> list[list[_RuleHitMetric]]:
    """把 native 规则命中补齐当前文本事实 fact_id，保留未解析命中供报告展示。"""
    probes = [
        RuleFactProbe(
            domain=domain,
            location_path=hit.location_path,
            translatable_text=hit.sample_text,
        )
        for record_hits in grouped_hits
        for hit in record_hits
    ]
    rule_fact_hits = await resolve_current_rule_fact_hits(session, probes)
    resolved_by_probe = {
        (hit.location_path, hit.sample_text): hit
        for hit in rule_fact_hits
    }
    resolved_groups: list[list[_RuleHitMetric]] = []
    for record_hits in grouped_hits:
        resolved_record_hits: list[_RuleHitMetric] = []
        for hit in record_hits:
            resolved_hit = resolved_by_probe.get((hit.location_path, hit.sample_text))
            if resolved_hit is None:
                resolved_record_hits.append(
                    _RuleHitMetric(location_path=hit.location_path, sample_text=hit.sample_text)
                )
                continue
            resolved_record_hits.append(
                _RuleHitMetric(
                    location_path=hit.location_path,
                    sample_text=hit.sample_text,
                    fact_id=resolved_hit.fact_id,
                    source_fact_raw_hash=resolved_hit.source_fact_raw_hash,
                    source_fact_translatable_hash=resolved_hit.source_fact_translatable_hash,
                )
            )
        resolved_groups.append(resolved_record_hits)
    return resolved_groups


async def _resolve_plugin_source_hit_metrics(
    *,
    session: TargetGameSession,
    grouped_hits: dict[str, list[_RuleHitMetric]],
) -> dict[str, list[_RuleHitMetric]]:
    """把插件源码命中补齐当前文本事实 fact_id。"""
    resolved_groups = await _resolve_rule_hit_metrics(
        session=session,
        domain="plugin_source",
        grouped_hits=list(grouped_hits.values()),
    )
    return {
        file_name: resolved_hits
        for file_name, resolved_hits in zip(grouped_hits, resolved_groups, strict=True)
    }


async def _resolve_plugin_rule_validation_context(
    *,
    session: TargetGameSession,
    context: NativePluginRuleValidationContext,
) -> NativePluginRuleValidationContext:
    """把插件参数 native 命中回填当前文本事实 fact_id。"""
    resolved_items = await resolve_current_rule_translation_items(
        session,
        domain="plugin_config",
        items=context.extracted_items,
    )
    resolved_by_item_id = {
        id(original_item): resolved_item
        for original_item, resolved_item in zip(context.extracted_items, resolved_items, strict=True)
    }
    return NativePluginRuleValidationContext(
        records=context.records,
        extracted_items=resolved_items,
        record_items_by_index={
            plugin_index: [
                resolved_by_item_id.get(id(item), item)
                for item in record_items
            ]
            for plugin_index, record_items in context.record_items_by_index.items()
        },
        translation_prefixes=context.translation_prefixes,
    )


async def _resolve_event_command_rule_validation_context(
    *,
    session: TargetGameSession,
    context: NativeEventCommandRuleValidationContext,
) -> NativeEventCommandRuleValidationContext:
    """把事件指令 native 命中回填当前文本事实 fact_id。"""
    resolved_items = await resolve_current_rule_translation_items(
        session,
        domain="event_command",
        items=context.extracted_items,
    )
    resolved_by_item_id = {
        id(original_item): resolved_item
        for original_item, resolved_item in zip(context.extracted_items, resolved_items, strict=True)
    }
    return NativeEventCommandRuleValidationContext(
        extracted_items=resolved_items,
        record_items_by_index=[
            [
                resolved_by_item_id.get(id(item), item)
                for item in record_items
            ]
            for record_items in context.record_items_by_index
        ],
        translation_prefixes=context.translation_prefixes,
        translation_prefixes_by_index=context.translation_prefixes_by_index,
    )

class RuleValidationAgentMixin:
    """承载 AgentToolkitService 的 RuleValidationAgentMixin 命令族。"""

    async def export_mv_virtual_namebox_candidates(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
    ) -> AgentReport:
        """导出 MV 虚拟名字框候选，供主代理填写外部规则。"""
        async with await self.game_registry.open_game(game_title) as session:
            game_data = await self._load_translation_source_game_data(session)
        if game_data.layout.engine_kind != "mv":
            return AgentReport.from_parts(
                errors=[issue("mv_virtual_namebox_rules_forbidden", "MV 虚拟名字框规则只允许 RPG Maker MV 游戏使用")],
                warnings=[],
                summary={"output": str(output_path), "candidate_count": 0},
                details={},
            )
        payload = native_mv_virtual_namebox_candidates_payload(game_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await _write_json_object(output_path, payload)
        candidate_count = _summary_int_from_payload(payload, "candidate_count")
        warnings: list[AgentIssue] = []
        if candidate_count == 0:
            warnings.append(issue("mv_virtual_namebox_candidates_empty", "当前 MV 游戏没有发现 `101` 后首条非空 `401` 候选"))
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={"output": str(output_path), "candidate_count": candidate_count},
            details=payload,
        )

    async def validate_mv_virtual_namebox_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """校验 MV 虚拟名字框规则 JSON 文本并报告候选命中情况。"""
        try:
            async with await self.game_registry.open_game(game_title) as session:
                game_data = await self._load_translation_source_game_data(session)
                existing_records = []
                if game_data.layout.engine_kind == "mv":
                    existing_records = await session.read_mv_virtual_namebox_rules()
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("mv_virtual_namebox_rules_invalid", f"MV 虚拟名字框规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "rule_count": 0,
                    "candidate_count": 0,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details={"rules": [], "matched_candidates": []},
            )
        return _validate_mv_virtual_namebox_rules_with_context(
            rules_text=rules_text,
            game_data=game_data,
            existing_records=existing_records,
        )

    async def import_mv_virtual_namebox_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
    ) -> AgentReport:
        """校验并导入当前 MV 游戏的虚拟名字框规则。"""
        try:
            records = parse_mv_virtual_namebox_rule_import_text(rules_text)
            if not records and not confirm_empty:
                raise RuntimeError("MV 虚拟名字框规则为空，必须确认当前游戏不需要虚拟名字框后传 --confirm-empty")
            async with await self.game_registry.open_game(game_title) as session:
                game_data = await self._load_translation_source_game_data(session)
                if game_data.layout.engine_kind != "mv":
                    raise RuntimeError("MV 虚拟名字框规则只允许 RPG Maker MV 游戏使用")
                native_scan = scan_native_mv_virtual_namebox(
                    game_data=game_data,
                    records=records,
                )
                rule_errors = native_scan.rule_errors
                match_details = native_scan.match_details
                if rule_errors:
                    messages = "；".join(_format_mv_namebox_rule_error(error_detail) for error_detail in rule_errors)
                    raise RuntimeError(messages)
                async with RuleImportUnitOfWork(session):
                    await session.replace_mv_virtual_namebox_rules(records)
                    if records:
                        await session.delete_rule_review_state(rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN)
                    else:
                        await session.replace_rule_review_state(
                            rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
                            scope_hash=native_scan.scope_hash,
                            reviewed_empty=True,
                        )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("mv_virtual_namebox_rules_invalid", f"MV 虚拟名字框规则导入失败: {type(error).__name__}: {error}")],
                warnings=[],
                summary={"rule_count": 0, "matched_candidate_count": 0},
                details={},
            )
        warnings = [] if records else [issue("mv_virtual_namebox_rules_empty", "已导入空 MV 虚拟名字框规则")]
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "rule_count": len(records),
                "matched_candidate_count": len(match_details),
            },
            details={
                "rules": mv_virtual_namebox_rule_records_to_import_json(records)["rules"],
                "matched_candidates": match_details,
            },
        )

    async def export_note_tag_candidates(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
    ) -> AgentReport:
        """导出标准 data JSON Note 标签候选，供外部 Agent 判断可见文本标签。"""
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
        report = await export_note_tag_candidates_file(
            game_data=game_data,
            output_path=output_path,
            text_rules=text_rules,
        )
        warnings: list[AgentIssue] = []
        if report.candidate_tag_count == 0:
            warnings.append(issue("note_tag_candidates_empty", "当前游戏没有发现 data Note 标签候选"))
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "candidate_tag_count": report.candidate_tag_count,
                "candidate_value_count": report.candidate_value_count,
                "translatable_value_count": report.translatable_value_count,
                "output": str(output_path),
            },
            details=report.details,
        )

    async def validate_note_tag_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验 Note 标签规则 JSON 文本并报告命中情况。"""
        try:
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
                import_file = parse_note_tag_rule_import_text(rules_text)
                records = build_note_tag_rule_records_from_native_candidates(
                    game_data=game_data,
                    import_file=import_file,
                    text_rules=text_rules,
                )
                translated_note_items = await session.read_translated_items_by_prefixes(
                    _note_tag_rule_prefixes(game_data=game_data, rule_records=records)
                )
                translated_identities = require_translation_fact_identities(translated_note_items)
                note_hit_metrics = _note_tag_rule_hits_from_native_details(
                    records=records,
                    hit_details=collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules),
                )
                resolved_note_hit_metrics = await _resolve_rule_hit_metrics(
                    session=session,
                    domain="note_tag",
                    grouped_hits=note_hit_metrics,
                )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("note_tag_rules_invalid", f"Note 标签规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "file_count": 0,
                    "tag_count": 0,
                    "hit_count": 0,
                    "extractable_count": 0,
                    "translated_count": 0,
                    "writable_count": 0,
                    "unwritable_count": 0,
                },
                details={"rules": []},
            )
        return _validate_note_tag_rule_records_with_context(
            records=records,
            game_data=game_data,
            text_rules=text_rules,
            translated_identities=translated_identities,
            hits_by_record=resolved_note_hit_metrics,
        )

    async def import_note_tag_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
    ) -> AgentReport:
        """校验并导入当前游戏的 Note 标签文本规则。"""
        try:
            import_file = parse_note_tag_rule_import_text(rules_text)
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
                records = build_note_tag_rule_records_from_native_candidates(
                    game_data=game_data,
                    import_file=import_file,
                    text_rules=text_rules,
                )
                if not records:
                    ensure_empty_rule_confirmed(
                        rule_label="Note 标签规则",
                        confirm_empty=confirm_empty,
                    )
                prior_records = await session.read_note_tag_text_rules()
                prior_note_items = await session.read_translated_items_by_prefixes(
                    _note_tag_rule_prefixes(game_data=game_data, rule_records=prior_records)
                )
                prior_note_rule_items = _translation_items_matching_note_rules(
                    translated_items=prior_note_items,
                    rule_records=prior_records,
                )
                new_note_hit_metrics = _note_tag_rule_hits_from_native_details(
                    records=records,
                    hit_details=collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules),
                )
                new_note_probes = [
                    RuleFactProbe(
                        domain="note_tag",
                        location_path=hit.location_path,
                        translatable_text=hit.sample_text,
                    )
                    for record_hits in new_note_hit_metrics
                    for hit in record_hits
                ]
                new_note_hits = await resolve_current_rule_fact_hits(session, new_note_probes)
                stale_fact_ids = stale_translation_fact_ids(
                    old_items=prior_note_rule_items,
                    current_rule_hits=new_note_hits,
                )
                deleted_translation_items = 0
                deleted_translation_backup_path: str | None = None
                async with RuleImportUnitOfWork(session):
                    if stale_fact_ids:
                        stale_items = await session.read_translated_items_by_fact_ids(stale_fact_ids)
                        backup = await write_rule_import_translation_backup(
                            game_title=game_title,
                            domain="note-tag-rules",
                            items=stale_items,
                        )
                        if backup is not None:
                            deleted_translation_backup_path = backup.backup_path
                        deleted_translation_items = await session.delete_translation_items_by_fact_ids(stale_fact_ids)
                    await session.replace_note_tag_text_rules(records)
                    if records:
                        await session.delete_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)
                    else:
                        await session.replace_rule_review_state(
                            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
                            scope_hash=note_tag_rule_scope_hash_for_text_rules(
                                game_data=game_data,
                                text_rules=text_rules,
                            ),
                            reviewed_empty=True,
                        )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("note_tag_rules_invalid", f"Note 标签规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "file_count": 0,
                    "tag_count": 0,
                    "deleted_translation_items": 0,
                    "deleted_translation_backup_path": "",
                },
                details={},
            )
        warnings = [] if records else [issue("note_tag_rules_empty", "已导入空 Note 标签规则")]
        if deleted_translation_items > 0 and deleted_translation_backup_path is not None:
            warnings.append(
                issue(
                    "deleted_translations_backed_up",
                    f"本次导入 Note 标签规则已清理 {deleted_translation_items} 条不再属于当前规则范围的已保存译文；已先备份到 {deleted_translation_backup_path}。如果发现规则导错，先重新导入正确规则，再用 import-manual-translations 读取该备份文件恢复这些译文",
                )
            )
        elif deleted_translation_items > 0:
            warnings.append(
                issue(
                    "deleted_translations_without_backup",
                    f"本次导入 Note 标签规则已清理 {deleted_translation_items} 条不再属于当前规则范围的已保存译文；没有生成备份文件",
                )
            )
        details: JsonObject = {
            "rules": [
                {
                    "file_name": record.file_name,
                    "tag_names": list(record.tag_names),
                }
                for record in records
            ]
        }
        if deleted_translation_backup_path is not None:
            details["deleted_translation_backup"] = {
                "path": deleted_translation_backup_path,
                "restore_step": "先重新导入正确规则，再运行 import-manual-translations 并把 input 指向该备份文件。",
            }
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "file_count": len(records),
                "tag_count": sum(len(record.tag_names) for record in records),
                "deleted_translation_items": deleted_translation_items,
                "deleted_translation_backup_path": deleted_translation_backup_path or "",
            },
            details=details,
        )

    async def validate_source_residual_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验源文残留例外规则 JSON 文本并报告命中情况。"""
        try:
            rules_payload = parse_source_residual_rule_import_payload(rules_text)
            records = await self._build_source_residual_rule_records(
                game_title=game_title,
                rules_text=rules_text,
            )
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                db_path = session.db_path
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("source_residual_rules_invalid", f"源文残留例外规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={"rule_count": 0, "position_rule_count": 0, "structural_rule_count": 0, "term_count": 0},
                details={"rules": []},
            )
        prepare_result = prepare_rule_import(
            _source_residual_rule_runtime_payload(
                mode="validate",
                rules_payload=rules_payload,
                setting=setting,
                db_path=db_path,
            )
        )
        return _source_residual_prepare_report(result=prepare_result, records=records)

    async def import_source_residual_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验并导入当前游戏的源文残留例外规则。"""
        try:
            rules_payload = parse_source_residual_rule_import_payload(rules_text)
            records = await self._build_source_residual_rule_records(
                game_title=game_title,
                rules_text=rules_text,
            )
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                db_path = session.db_path
                prepare_result = prepare_rule_import(
                    _source_residual_rule_runtime_payload(
                        mode="import",
                        rules_payload=rules_payload,
                        setting=setting,
                        db_path=db_path,
                    )
                )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("source_residual_rules_invalid", f"源文残留例外规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={"rule_count": 0, "position_rule_count": 0, "structural_rule_count": 0, "term_count": 0},
                details={},
            )
        if prepare_result.errors:
            return _source_residual_prepare_report(result=prepare_result, records=records)
        if prepare_result.plan_token is None:
            raise RuntimeError("源文残留例外规则导入缺少 rule_runtime plan token")

        commit_result = commit_rule_import(
            {
                "db_path": str(db_path),
                "domain": "source_residual",
                "plan_token": prepare_result.plan_token,
                "backup_path": None,
            }
        )
        if commit_result.errors:
            return _source_residual_commit_report(
                result=commit_result,
                prepare_result=prepare_result,
                records=records,
            )
        async with await self.game_registry.open_game(game_title) as session:
            await session.replace_source_residual_rules(records)
        return _source_residual_commit_report(
            result=commit_result,
            prepare_result=prepare_result,
            records=records,
        )

    async def validate_plugin_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验插件规则 JSON 文本并报告命中情况。"""
        try:
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
                import_file = parse_plugin_rule_import_text(rules_text)
                context = build_native_plugin_rule_validation_context_from_import(
                    game_data=game_data,
                    import_file=import_file,
                    text_rules=text_rules,
                )
                translated_plugin_items = await session.read_translated_items_by_prefixes(
                    context.translation_prefixes
                )
                translated_identities = require_translation_fact_identities(translated_plugin_items)
                context = await _resolve_plugin_rule_validation_context(
                    session=session,
                    context=context,
                )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("plugin_rules_invalid", f"插件规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "plugin_count": 0,
                    "rule_count": 0,
                    "hit_count": 0,
                    "extractable_count": 0,
                    "translated_count": 0,
                    "writable_count": 0,
                    "unwritable_count": 0,
                },
                details={"rules": []},
            )
        return build_plugin_rule_validation_report_from_native_context(
            context=context,
            game_data=game_data,
            translated_identities=translated_identities,
        )

    async def validate_plugin_source_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验插件源码文本规则 JSON 文本并报告命中情况。"""
        try:
            import_file = parse_plugin_source_rule_import_text(rules_text)
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
                game_data = await self._load_translation_source_game_data(
                    session,
                    include_plugin_source_files=True,
                )
                translated_plugin_source_items = await session.read_translated_items_by_prefixes(
                    _plugin_source_file_prefixes(game_data)
                )
                translated_identities = require_translation_fact_identities(translated_plugin_source_items)
                scan_records = build_plugin_source_rule_scan_records_from_import(
                    game_data=game_data,
                    import_file=import_file,
                )
                scan = build_native_plugin_source_scan(
                    game_data=game_data,
                    text_rules=text_rules,
                    rule_records=scan_records,
                )
                records = build_plugin_source_rule_records_from_import(
                    game_data=game_data,
                    import_file=import_file,
                    text_rules=text_rules,
                    scan=scan,
                )
                plugin_source_hit_metrics = _plugin_source_rule_hits_from_scan(
                    records=records,
                    scan=scan,
                )
                resolved_plugin_source_hit_metrics = await _resolve_plugin_source_hit_metrics(
                    session=session,
                    grouped_hits=plugin_source_hit_metrics,
                )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("plugin_source_rules_invalid", f"插件源码规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "file_count": 0,
                    "selector_count": 0,
                    "excluded_selector_count": 0,
                    "reviewed_selector_count": 0,
                    "unreviewed_selector_count": 0,
                    "hit_count": 0,
                    "extractable_count": 0,
                    "translated_count": 0,
                    "writable_count": 0,
                    "unwritable_count": 0,
                },
                details={"rules": []},
            )
        return _validate_plugin_source_rules_with_context(
            rules_text=rules_text,
            game_data=game_data,
            text_rules=text_rules,
            scan=scan,
            translated_identities=translated_identities,
            hits_by_file=resolved_plugin_source_hit_metrics,
        )

    async def import_plugin_source_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
    ) -> AgentReport:
        """校验并导入当前游戏的插件源码文本规则。"""
        try:
            import_file = parse_plugin_source_rule_import_text(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                prior_records = await session.read_plugin_source_text_rules()
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
                game_data = await self._load_translation_source_game_data(
                    session,
                    include_plugin_source_files=True,
                )
                scan_records = build_plugin_source_rule_scan_records_from_import(
                    game_data=game_data,
                    import_file=import_file,
                )
                scan = build_native_plugin_source_scan(
                    game_data=game_data,
                    text_rules=text_rules,
                    rule_records=scan_records,
                )
                records = build_plugin_source_rule_records_from_import(
                    game_data=game_data,
                    import_file=import_file,
                    text_rules=text_rules,
                    scan=scan,
                )
                review = collect_plugin_source_review_coverage(scan=scan, rule_records=records)
                unreviewed_count = len(review.unreviewed_candidates)
                reviewed_selector_count = sum(
                    len(record.selectors) + len(record.excluded_selectors)
                    for record in records
                )
                if unreviewed_count and (scan.risk.high_risk or records or prior_records):
                    return AgentReport.from_parts(
                        errors=[
                            issue(
                                "plugin_source_review_incomplete",
                                f"插件源码规则还有 {unreviewed_count} 个候选未归入翻译或排除",
                            )
                        ],
                        warnings=[],
                        summary={
                            "file_count": len(records),
                            "selector_count": sum(len(record.selectors) for record in records),
                            "excluded_selector_count": sum(len(record.excluded_selectors) for record in records),
                            "reviewed_selector_count": reviewed_selector_count,
                            "unreviewed_selector_count": unreviewed_count,
                            "deleted_translation_items": 0,
                            "deleted_translation_backup_path": "",
                        },
                        details={
                            "rules": plugin_source_rule_records_to_import_json(records),
                        },
                    )
                if not records:
                    ensure_empty_rule_confirmed(
                        rule_label="插件源码规则",
                        confirm_empty=confirm_empty,
                    )
                prior_translated_items = await session.read_translated_items_by_prefixes(
                    _plugin_source_rule_prefixes(prior_records)
                )
                new_plugin_source_hit_metrics = _plugin_source_rule_hits_from_scan(
                    records=records,
                    scan=scan,
                )
                new_plugin_source_probes = [
                    RuleFactProbe(
                        domain="plugin_source",
                        location_path=hit.location_path,
                        translatable_text=hit.sample_text,
                    )
                    for record_hits in new_plugin_source_hit_metrics.values()
                    for hit in record_hits
                ]
                new_plugin_source_hits = await resolve_current_rule_fact_hits(session, new_plugin_source_probes)
                stale_fact_ids = stale_translation_fact_ids(
                    old_items=prior_translated_items,
                    current_rule_hits=new_plugin_source_hits,
                )
                deleted_translation_items = 0
                deleted_translation_backup_path: str | None = None
                async with RuleImportUnitOfWork(session):
                    if stale_fact_ids:
                        stale_items = await session.read_translated_items_by_fact_ids(stale_fact_ids)
                        backup = await write_rule_import_translation_backup(
                            game_title=game_title,
                            domain="plugin-source-rules",
                            items=stale_items,
                        )
                        if backup is not None:
                            deleted_translation_backup_path = backup.backup_path
                        deleted_translation_items = await session.delete_translation_items_by_fact_ids(stale_fact_ids)
                    await session.replace_plugin_source_text_rules(records)
                    await session.clear_plugin_source_runtime_write_maps()
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("plugin_source_rules_invalid", f"插件源码规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "file_count": 0,
                    "selector_count": 0,
                    "excluded_selector_count": 0,
                    "reviewed_selector_count": 0,
                    "unreviewed_selector_count": 0,
                    "deleted_translation_items": 0,
                    "deleted_translation_backup_path": "",
                },
                details={},
            )
        warnings = [] if records else [issue("plugin_source_rules_empty", "已导入空插件源码规则")]
        if unreviewed_count:
            warnings.append(issue("plugin_source_review_incomplete", f"插件源码规则还有 {unreviewed_count} 个候选未归入翻译或排除"))
        if deleted_translation_items > 0 and deleted_translation_backup_path is not None:
            warnings.append(
                issue(
                    "deleted_translations_backed_up",
                    f"本次导入插件源码规则已清理 {deleted_translation_items} 条不再属于当前规则范围的已保存译文；已先备份到 {deleted_translation_backup_path}",
                )
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "file_count": len(records),
                "selector_count": sum(len(record.selectors) for record in records),
                "excluded_selector_count": sum(len(record.excluded_selectors) for record in records),
                "reviewed_selector_count": sum(
                    len(record.selectors) + len(record.excluded_selectors)
                    for record in records
                ),
                "unreviewed_selector_count": unreviewed_count,
                "deleted_translation_items": deleted_translation_items,
                "deleted_translation_backup_path": deleted_translation_backup_path or "",
            },
            details={
                "rules": plugin_source_rule_records_to_import_json(records),
            },
        )

    async def validate_event_command_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验事件指令规则 JSON 文本并报告命中情况。"""
        try:
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
                import_file = parse_event_command_rule_import_text(rules_text)
                records = build_event_command_rule_records_from_import_shape(import_file=import_file)
                native_validation_context = build_native_event_command_rule_validation_context(
                    records=records,
                    game_data=game_data,
                    text_rules=text_rules,
                )
                extracted_paths = {item.location_path for item in native_validation_context.extracted_items}
                if extracted_paths:
                    translated_event_items = await session.read_translated_items_by_paths(sorted(extracted_paths))
                else:
                    translated_event_items = []
                translated_identities = require_translation_fact_identities(translated_event_items)
                native_validation_context = await _resolve_event_command_rule_validation_context(
                    session=session,
                    context=native_validation_context,
                )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("event_command_rules_invalid", f"事件指令规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "rule_group_count": 0,
                    "path_rule_count": 0,
                    "hit_count": 0,
                    "extractable_count": 0,
                    "translated_count": 0,
                    "writable_count": 0,
                    "unwritable_count": 0,
                },
                details={"rules": []},
            )
        return _validate_event_command_rule_records_with_context(
            records=records,
            game_data=game_data,
            text_rules=text_rules,
            translated_identities=translated_identities,
            native_validation_context=native_validation_context,
        )


def _summary_int_from_payload(payload: JsonObject, key: str) -> int:
    """从导出载荷读取整数统计字段。"""
    raw_value = payload.get(key)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise RuntimeError(f"MV 虚拟名字框候选导出缺少有效计数字段: {key}")
    return raw_value
