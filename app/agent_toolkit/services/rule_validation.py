"""Agent 工具箱 RuleValidationAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonObject,
    NoteTagTextExtraction,
    NoteTagTextRuleRecord,
    Path,
    TextRules,
    TranslationItem,
    _format_mv_namebox_rule_error,
    _note_tag_item_matches_rule,
    _validate_event_command_rule_records_with_context,
    _validate_mv_virtual_namebox_rules_with_context,
    _validate_note_tag_rule_records_with_context,
    _validate_plugin_source_rules_with_context,
    _write_json_object,
    build_native_plugin_rule_validation_context_from_import,
    build_event_command_rule_records_from_import_shape,
    build_plugin_rule_validation_report_from_native_context,
    collect_translation_data_paths,
    export_note_tag_candidates_file,
    issue,
    load_setting,
    parse_event_command_rule_import_text,
    parse_note_tag_rule_import_text,
    parse_plugin_rule_import_text,
)
from app.event_command_text.native_validation import build_native_event_command_rule_validation_context
from app.application.rule_import_backup import write_rule_import_translation_backup
from app.application.flow_gate import (
    ensure_empty_rule_confirmed,
    note_tag_rule_scope_hash_for_text_rules,
)
from app.native_note_tag_scan import build_note_tag_rule_records_from_native_candidates
from app.persistence import RuleImportUnitOfWork
from app.plugin_source_text import (
    PluginSourceTextExtraction,
    build_plugin_source_rule_records_from_import,
    collect_plugin_source_review_coverage,
    parse_plugin_source_rule_import_text,
    plugin_source_rule_records_to_import_json,
)
from app.rmmz.mv_namebox import (
    mv_virtual_namebox_rule_records_to_import_json,
    parse_mv_virtual_namebox_rule_import_text,
)
from app.rmmz.mv_namebox_native import native_mv_virtual_namebox_candidates_payload, scan_native_mv_virtual_namebox
from app.rmmz.schema import GameData, PluginSourceTextRuleRecord
from app.rule_review import (
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLUGIN_SOURCE_TEXT_RULE_DOMAIN,
    plugin_source_rule_scope_hash,
    mv_virtual_namebox_rule_scope_hash,
)
from app.plugin_source_text import build_native_plugin_source_scan


def _translation_paths_matching_note_rules(
    *,
    translated_items: list[TranslationItem],
    rule_records: list[NoteTagTextRuleRecord],
) -> set[str]:
    """从已保存译文中找出属于指定 Note 标签规则的定位路径。"""
    return {
        item.location_path
        for item in translated_items
        for rule_record in rule_records
        if _note_tag_item_matches_rule(item=item, rule_record=rule_record)
    }


def _note_tag_rule_prefixes(rule_records: list[NoteTagTextRuleRecord]) -> list[str]:
    """返回 Note 标签规则影响的已保存译文路径前缀。"""
    return sorted({f"{record.file_name}/" for record in rule_records})


def _plugin_source_rule_prefixes(rule_records: list[PluginSourceTextRuleRecord]) -> list[str]:
    """返回插件源码规则影响的已保存译文路径前缀。"""
    return sorted({f"js/plugins/{record.file_name}/" for record in rule_records})


def _plugin_source_file_prefixes(game_data: GameData) -> list[str]:
    """返回当前启用插件源码文件对应的已保存译文路径前缀。"""
    return sorted({f"js/plugins/{file_name}/" for file_name in game_data.plugin_source_files})


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
                            scope_hash=mv_virtual_namebox_rule_scope_hash(
                                native_scan.candidate_details
                            ),
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
                    _note_tag_rule_prefixes(records)
                )
                translated_paths = {item.location_path for item in translated_note_items}
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
            translated_paths=translated_paths,
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
                old_records = await session.read_note_tag_text_rules()
                old_note_items = await session.read_translated_items_by_prefixes(
                    _note_tag_rule_prefixes(old_records)
                )
                old_note_paths = _translation_paths_matching_note_rules(
                    translated_items=old_note_items,
                    rule_records=old_records,
                )
                new_note_paths = collect_translation_data_paths(
                    NoteTagTextExtraction(
                        game_data=game_data,
                        rule_records=records,
                        text_rules=text_rules,
                    ).extract_all_text()
                )
                stale_paths = sorted(old_note_paths - new_note_paths)
                deleted_translation_items = 0
                deleted_translation_backup_path: str | None = None
                async with RuleImportUnitOfWork(session):
                    if stale_paths:
                        stale_items = await session.read_translated_items_by_paths(stale_paths)
                        backup = await write_rule_import_translation_backup(
                            game_title=game_title,
                            domain="note-tag-rules",
                            items=stale_items,
                        )
                        if backup is not None:
                            deleted_translation_backup_path = backup.backup_path
                        deleted_translation_items = await session.delete_translation_items_by_paths(stale_paths)
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
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
        details: JsonObject = {"rules": []}
        try:
            records = await self._build_source_residual_rule_records(
                game_title=game_title,
                rules_text=rules_text,
            )
            details["rules"] = [
                {
                    "rule_id": record.rule_id,
                    "rule_type": record.rule_type,
                    "location_path": record.location_path,
                    "pattern": record.pattern_text,
                    "allowed_terms": list(record.allowed_terms),
                    "check_group": record.check_group,
                    "reason": record.reason,
                }
                for record in records
            ]
            if not records:
                warnings.append(issue("source_residual_rules_empty", "源文残留例外规则为空"))
        except Exception as error:
            errors.append(issue("source_residual_rules_invalid", f"源文残留例外规则不可导入: {type(error).__name__}: {error}"))
            records = []
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "rule_count": len(records),
                "position_rule_count": sum(1 for record in records if record.rule_type == "position"),
                "structural_rule_count": sum(1 for record in records if record.rule_type == "structural"),
                "term_count": sum(len(record.allowed_terms) for record in records),
            },
            details=details,
        )

    async def import_source_residual_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验并导入当前游戏的源文残留例外规则。"""
        try:
            records = await self._build_source_residual_rule_records(
                game_title=game_title,
                rules_text=rules_text,
            )
            async with await self.game_registry.open_game(game_title) as session:
                await session.replace_source_residual_rules(records)
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("source_residual_rules_invalid", f"源文残留例外规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={"rule_count": 0, "position_rule_count": 0, "structural_rule_count": 0, "term_count": 0},
                details={},
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=[] if records else [issue("source_residual_rules_empty", "已导入空源文残留例外规则")],
            summary={
                "rule_count": len(records),
                "position_rule_count": sum(1 for record in records if record.rule_type == "position"),
                "structural_rule_count": sum(1 for record in records if record.rule_type == "structural"),
                "term_count": sum(len(record.allowed_terms) for record in records),
            },
            details={
                "rules": [
                    {
                        "rule_id": record.rule_id,
                        "rule_type": record.rule_type,
                        "location_path": record.location_path,
                        "pattern": record.pattern_text,
                        "allowed_terms": list(record.allowed_terms),
                        "check_group": record.check_group,
                        "reason": record.reason,
                    }
                    for record in records
                ]
            },
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
                translated_paths = {item.location_path for item in translated_plugin_items}
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
            translated_paths=translated_paths,
        )

    async def validate_plugin_source_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
        """校验插件源码文本规则 JSON 文本并报告命中情况。"""
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
                game_data = await self._load_translation_source_game_data(
                    session,
                    include_plugin_source_files=True,
                )
                translated_plugin_source_items = await session.read_translated_items_by_prefixes(
                    _plugin_source_file_prefixes(game_data)
                )
                translated_paths = {item.location_path for item in translated_plugin_source_items}
            scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
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
            translated_paths=translated_paths,
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
                scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
                records = build_plugin_source_rule_records_from_import(
                    game_data=game_data,
                    import_file=import_file,
                    text_rules=text_rules,
                    scan=scan,
                )
                old_records = await session.read_plugin_source_text_rules()
                review = collect_plugin_source_review_coverage(scan=scan, rule_records=records)
                unreviewed_count = len(review.unreviewed_candidates)
                reviewed_selector_count = sum(
                    len(record.selectors) + len(record.excluded_selectors)
                    for record in records
                )
                if unreviewed_count and (scan.risk.high_risk or records or old_records):
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
                old_translated_items = await session.read_translated_items_by_prefixes(
                    _plugin_source_rule_prefixes(old_records)
                )
                old_paths = {item.location_path for item in old_translated_items}
                new_paths = collect_translation_data_paths(
                    PluginSourceTextExtraction(
                        game_data,
                        rule_records=records,
                        text_rules=text_rules,
                        scan=scan,
                    ).extract_all_text()
                )
                stale_paths = sorted(old_paths - new_paths)
                deleted_translation_items = 0
                deleted_translation_backup_path: str | None = None
                async with RuleImportUnitOfWork(session):
                    if stale_paths:
                        stale_path_set = set(stale_paths)
                        stale_items = [
                            item
                            for item in old_translated_items
                            if item.location_path in stale_path_set
                        ]
                        backup = await write_rule_import_translation_backup(
                            game_title=game_title,
                            domain="plugin-source-rules",
                            items=stale_items,
                        )
                        if backup is not None:
                            deleted_translation_backup_path = backup.backup_path
                        deleted_translation_items = await session.delete_translation_items_by_paths(stale_paths)
                    await session.replace_plugin_source_text_rules(records)
                    await session.clear_plugin_source_runtime_write_maps()
                    if records:
                        await session.delete_rule_review_state(rule_domain=PLUGIN_SOURCE_TEXT_RULE_DOMAIN)
                    else:
                        await session.replace_rule_review_state(
                            rule_domain=PLUGIN_SOURCE_TEXT_RULE_DOMAIN,
                            scope_hash=plugin_source_rule_scope_hash(game_data),
                            reviewed_empty=True,
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
                translated_event_items: list[TranslationItem]
                if not native_validation_context.translation_prefixes:
                    translated_event_items = []
                else:
                    translated_event_items = await session.read_translated_items_by_prefixes(
                        native_validation_context.translation_prefixes
                    )
                translated_paths = {item.location_path for item in translated_event_items}
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
            translated_paths=translated_paths,
            native_validation_context=native_validation_context,
        )


def _summary_int_from_payload(payload: JsonObject, key: str) -> int:
    """从导出载荷读取整数统计字段。"""
    raw_value = payload.get(key)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise RuntimeError(f"MV 虚拟名字框候选导出缺少有效计数字段: {key}")
    return raw_value
