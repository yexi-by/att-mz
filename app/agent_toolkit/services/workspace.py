"""Agent 工具箱 WorkspaceAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    GameData,
    JsonArray,
    JsonObject,
    Path,
    PLUGINS_FILE_NAME,
    QualityProgressCallbacks,
    STRUCTURED_PLACEHOLDER_RULES_FILE_NAME,
    TargetGameSession,
    TERMINOLOGY_SUBTASK_GROUPS,
    TerminologyExtraction,
    TerminologyGlossary,
    TerminologyRegistry,
    CustomPlaceholderRule,
    StructuredPlaceholderRule,
    TextRules,
    TranslationData,
    TranslationItem,
    EventCommandTextExtraction,
    NoteTagTextExtraction,
    PluginTextExtraction,
    _agent_workflow_manifest,
    _build_rule_metric_detail,
    _build_custom_placeholder_rule_draft,
    _collect_terminology_duplicate_translation_samples,
    _collect_plugin_json_string_leaf_candidate_details,
    _event_command_rule_records_to_import_json,
    _is_path_inside,
    _json_items_by_location_path,
    _merge_terminology_registry,
    _note_tag_item_matches_rule,
    _note_tag_rule_records_to_import_json,
    _placeholder_rule_records_to_import_json,
    _placeholder_preview_loses_visible_source_text,
    _preview_placeholder_sample,
    _plugin_rule_records_to_import_json,
    _structured_placeholder_rule_records_to_import_json,
    _collect_write_protocol_unwritable_items,
    _preview_event_command_write_back,
    _validate_terminology_registry,
    _validate_terminology_registry_shape,
    _noop_quality_progress_callbacks,
    _write_json_object,
    _write_json_value,
    _write_terminology_subtask_files,
    aiofiles,
    cast,
    coerce_json_value,
    count_uncovered_candidates,
    ensure_json_array,
    ensure_json_object,
    export_event_commands_json_file,
    export_note_tag_candidates_file,
    export_plugins_json_file,
    export_terminology_artifacts,
    issue,
    json,
    build_event_command_rule_records_from_import,
    build_note_tag_rule_records_from_import,
    build_plugin_rule_records_from_import,
    load_custom_placeholder_rules_text,
    load_structured_placeholder_rules_text,
    load_setting,
    load_terminology_glossary,
    load_terminology_registry,
    placeholder_candidates_to_details,
    parse_event_command_rule_import_text,
    parse_note_tag_rule_import_text,
    parse_plugin_rule_import_text,
    resolve_event_command_codes,
    scan_placeholder_candidates,
    shutil,
    write_field_terms_json,
    write_glossary_json,
)
from app.agent_toolkit.services.placeholder_rules import (
    _collect_structured_placeholder_candidate_details,
    _collect_structured_placeholder_preview_samples,
)
from app.config.schemas import TextRulesSetting
from app.plugin_source_text import (
    PluginSourceScan,
    PluginSourceTextExtraction,
    build_plugin_source_rule_records_from_import,
    build_plugin_source_scan,
    collect_plugin_source_review_coverage,
    parse_plugin_source_rule_import_text,
    plugin_source_rule_records_to_import_json,
)
from app.agent_toolkit.services.rule_validation import _collect_plugin_source_unwritable_items
from app.agent_toolkit.services.rule_validation import (
    _format_mv_namebox_rule_error,
    _mv_namebox_match_key,
    _mv_namebox_match_keys,
)
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    PLUGIN_SOURCE_TEXT_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    RuleReviewDomain,
    mv_virtual_namebox_rule_scope_hash,
    plugin_rule_scope_hash,
    plugin_source_rule_scope_hash,
)
from app.application.flow_gate import (
    event_command_rule_scope_hash_for_setting,
    event_command_rule_scope_hash_for_command_codes,
    normal_placeholder_scope_hash,
    note_tag_rule_scope_hash_for_text_rules,
    structured_placeholder_scope_hash,
)
from app.rmmz.mv_namebox import (
    MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME,
    MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME,
    mv_virtual_namebox_candidate_details,
    mv_virtual_namebox_candidates_payload,
    mv_virtual_namebox_rule_records_to_import_json,
    parse_mv_virtual_namebox_rule_import_text,
    validate_mv_virtual_namebox_rules_against_game,
)
from app.rmmz.game_file_view import GameFileView, parse_game_file_view
from app.rmmz.schema import MvVirtualNameboxRuleRecord, PluginSourceTextRuleRecord
from app.terminology import collect_terminology_bundle_errors


class WorkspaceAgentMixin:
    """承载 AgentToolkitService 的 WorkspaceAgentMixin 命令族。"""

    async def scan_plugin_source_text(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
        source_view: GameFileView | str = GameFileView.TRANSLATION_SOURCE,
    ) -> AgentReport:
        """扫描插件源码文本风险，只输出轻量风险报告。"""
        resolved_view = parse_game_file_view(str(source_view))
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            game_data = await self._load_game_data_for_view(
                session,
                source_view=resolved_view,
                include_writable_copies=False,
            )
            text_rules = TextRules.from_setting(setting.text_rules)
        scan = build_plugin_source_scan(game_data=game_data, text_rules=text_rules)
        risk_report = scan.risk_report_json()
        risk_report["source_view"] = resolved_view.value
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await _write_json_object(output_path, risk_report)
        warnings: list[AgentIssue] = []
        if not scan.candidates:
            warnings.append(issue("plugin_source_text_empty", "没有扫描到插件源码硬编码文本候选"))
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "source_view": resolved_view.value,
                "candidate_count": len(scan.candidates),
                "output": str(output_path),
                **scan.risk.to_json_object(),
            },
            details={
                **risk_report,
                "output": str(output_path),
            },
        )

    async def export_plugin_source_ast_map(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
        source_view: GameFileView | str = GameFileView.TRANSLATION_SOURCE,
    ) -> AgentReport:
        """导出插件源码 AST 地图和候选文本。"""
        resolved_view = parse_game_file_view(str(source_view))
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            game_data = await self._load_game_data_for_view(
                session,
                source_view=resolved_view,
                include_writable_copies=False,
            )
            text_rules = TextRules.from_setting(setting.text_rules)
        scan = build_plugin_source_scan(game_data=game_data, text_rules=text_rules)
        payload = scan.to_json_object()
        payload["source_view"] = resolved_view.value
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await _write_json_object(output_path, payload)
        details = scan.risk_report_json()
        details["source_view"] = resolved_view.value
        details["output"] = str(output_path)
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "source_view": resolved_view.value,
                "output": str(output_path),
                "candidate_count": len(scan.candidates),
                **scan.risk.to_json_object(),
            },
            details=details,
        )

    async def prepare_agent_workspace(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_dir: Path,
        command_codes: set[int] | None,
    ) -> AgentReport:
        """导出 Agent 分析所需的全部临时输入文件并生成 manifest。"""
        target_dir = output_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            game_data = await self._load_translation_source_game_data(
                session,
                include_writable_copies=False,
            )
            terminology_registry = await session.read_terminology_registry()
            terminology_glossary = await session.read_terminology_glossary()
            plugin_rules, stale_plugin_rule_count = await self._read_fresh_plugin_text_rules(
                session=session,
                game_data=game_data,
            )
            note_tag_rules = await session.read_note_tag_text_rules()
            event_rules = await session.read_event_command_text_rules()
            plugin_source_rules = await session.read_plugin_source_text_rules()
            mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
            placeholder_records = await session.read_placeholder_rules()
            structured_placeholder_records = await session.read_structured_placeholder_rules()
            custom_rules = await self._resolve_custom_rules(session=session, custom_placeholder_rules_text=None)
            structured_rules = await self._resolve_structured_rules(session=session)
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            translation_data_map = await self._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
            )
            plugin_source_scan = build_plugin_source_scan(game_data=game_data, text_rules=text_rules)
            plugin_source_review = collect_plugin_source_review_coverage(
                scan=plugin_source_scan,
                rule_records=plugin_source_rules,
            )
            plugin_source_extension_active = plugin_source_scan.risk.high_risk or bool(plugin_source_rules)
        terminology_summary = await export_terminology_artifacts(
            game_data=game_data,
            output_dir=target_dir / "terminology",
            mv_virtual_namebox_rule_records=mv_virtual_namebox_rules,
            text_rules=text_rules,
        )
        if terminology_registry is not None:
            exported_registry = await load_terminology_registry(field_terms_path=terminology_summary.field_terms_path)
            merged_registry = _merge_terminology_registry(
                exported_registry=exported_registry,
                stored_registry=terminology_registry,
            )
            await write_field_terms_json(terminology_summary.field_terms_path, merged_registry)
        if terminology_glossary is not None:
            await write_glossary_json(terminology_summary.glossary_path, terminology_glossary)
        terminology_subtasks_dir = target_dir / "terminology" / "subtasks"
        terminology_subtask_summary = await _write_terminology_subtask_files(
            field_terms_path=terminology_summary.field_terms_path,
            subtasks_dir=terminology_subtasks_dir,
        )
        plugins_path = target_dir / "plugins.json"
        await export_plugins_json_file(game_data=game_data, output_path=plugins_path)
        plugin_json_string_leaf_candidates_path = target_dir / "plugin-json-string-leaf-candidates.json"
        plugin_json_string_leaf_candidates = _collect_plugin_json_string_leaf_candidate_details(game_data)
        await _write_json_value(plugin_json_string_leaf_candidates_path, plugin_json_string_leaf_candidates)
        plugin_rules_path = target_dir / "plugin-rules.json"
        await _write_json_value(plugin_rules_path, _plugin_rule_records_to_import_json(plugin_rules))
        plugin_source_risk_path = target_dir / "plugin-source-risk-report.json"
        plugin_source_risk_report = plugin_source_scan.risk_report_json()
        plugin_source_risk_report["source_view"] = GameFileView.TRANSLATION_SOURCE.value
        await _write_json_object(plugin_source_risk_path, plugin_source_risk_report)
        plugin_source_rules_path: Path | None = None
        if plugin_source_extension_active:
            plugin_source_rules_path = target_dir / "plugin-source-rules.json"
            await _write_json_value(
                plugin_source_rules_path,
                plugin_source_rule_records_to_import_json(plugin_source_rules),
            )
        note_tag_candidates_path = target_dir / "note-tag-candidates.json"
        note_tag_report = await export_note_tag_candidates_file(
            game_data=game_data,
            output_path=note_tag_candidates_path,
            text_rules=text_rules,
        )
        note_tag_rules_path = target_dir / "note-tag-rules.json"
        await _write_json_object(note_tag_rules_path, _note_tag_rule_records_to_import_json(note_tag_rules))
        default_command_codes = (
            None
            if command_codes is not None
            else setting.event_command_text.default_codes_for_engine(game_data.layout.engine_kind)
        )
        effective_codes = resolve_event_command_codes(command_codes=command_codes, default_command_codes=default_command_codes)
        event_commands_path = target_dir / "event-commands.json"
        event_command_count = await export_event_commands_json_file(
            game_data=game_data,
            output_path=event_commands_path,
            command_codes=effective_codes,
        )
        event_rules_path = target_dir / "event-command-rules.json"
        await _write_json_object(event_rules_path, _event_command_rule_records_to_import_json(event_rules))
        placeholder_candidates = scan_placeholder_candidates(translation_data_map, text_rules)
        placeholder_report = AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={},
            details={"candidates": placeholder_candidates_to_details(placeholder_candidates)},
        )
        placeholder_path = target_dir / "placeholder-candidates.json"
        async with aiofiles.open(placeholder_path, "w", encoding="utf-8") as file:
            _ = await file.write(f"{placeholder_report.to_json_text()}\n")
        placeholder_rule_drafts = _build_custom_placeholder_rule_draft(placeholder_candidates)
        placeholder_rules_path = target_dir / "placeholder-rules.json"
        placeholder_rule_payload: JsonObject = (
            _placeholder_rule_records_to_import_json(placeholder_records)
            if placeholder_records
            else {key: value for key, value in placeholder_rule_drafts.items()}
        )
        await _write_json_object(placeholder_rules_path, placeholder_rule_payload)
        structured_placeholder_rules_path = target_dir / STRUCTURED_PLACEHOLDER_RULES_FILE_NAME
        await _write_json_object(
            structured_placeholder_rules_path,
            _structured_placeholder_rule_records_to_import_json(structured_placeholder_records),
        )
        mv_virtual_namebox_candidates_path: Path | None = None
        mv_virtual_namebox_rules_path: Path | None = None
        mv_virtual_namebox_candidate_count = 0
        if game_data.layout.engine_kind == "mv":
            mv_virtual_namebox_candidates_path = target_dir / MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME
            mv_candidates_payload = mv_virtual_namebox_candidates_payload(game_data)
            mv_virtual_namebox_candidate_count = _summary_int(mv_candidates_payload, "candidate_count")
            await _write_json_object(mv_virtual_namebox_candidates_path, mv_candidates_payload)
            mv_virtual_namebox_rules_path = target_dir / MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME
            await _write_json_object(
                mv_virtual_namebox_rules_path,
                mv_virtual_namebox_rule_records_to_import_json(mv_virtual_namebox_rules),
            )
        generated_summary: JsonObject = {
            "engine": game_data.layout.engine_label,
            "engine_kind": game_data.layout.engine_kind,
            "engine_version": game_data.layout.engine_version,
            "source_language": session.source_language,
            "target_language": session.target_language,
            "content_root": str(game_data.layout.content_root),
            "data_dir": str(game_data.layout.data_dir),
            "event_command_codes": list(sorted(effective_codes)),
            "speaker_entry_count": terminology_summary.speaker_entry_count,
            "map_entry_count": terminology_summary.map_entry_count,
            "terminology_entry_count": terminology_summary.entry_count,
            "terminology_database_entry_count": terminology_summary.database_entry_count,
            "terminology_subtask_count": len(TERMINOLOGY_SUBTASK_GROUPS),
            "glossary_term_count": terminology_glossary.term_count() if terminology_glossary is not None else 0,
            "plugin_count": len(game_data.plugins_js),
            "plugin_json_string_leaf_candidate_count": len(plugin_json_string_leaf_candidates),
            "plugin_rule_count": sum(len(rule.path_templates) for rule in plugin_rules),
            "plugin_source_candidate_count": len(plugin_source_scan.candidates),
            "plugin_source_high_risk": plugin_source_scan.risk.high_risk,
            "stale_plugin_rule_count": stale_plugin_rule_count,
            "note_tag_candidate_count": note_tag_report.candidate_tag_count,
            "note_tag_rule_count": sum(len(rule.tag_names) for rule in note_tag_rules),
            "event_command_count": event_command_count,
            "event_command_rule_count": sum(len(rule.path_templates) for rule in event_rules),
            "placeholder_rule_count": len(placeholder_records),
            "placeholder_rule_draft_count": len(placeholder_rule_drafts),
            "structured_placeholder_rule_count": len(structured_placeholder_records),
            "mv_virtual_namebox_candidate_count": mv_virtual_namebox_candidate_count,
            "mv_virtual_namebox_rule_count": len(mv_virtual_namebox_rules),
        }
        if plugin_source_extension_active:
            generated_summary.update(
                {
                    "plugin_source_rule_count": sum(len(rule.selectors) for rule in plugin_source_rules),
                    "plugin_source_excluded_selector_count": sum(
                        len(rule.excluded_selectors)
                        for rule in plugin_source_rules
                    ),
                    "plugin_source_reviewed_selector_count": plugin_source_review.reviewed_selector_count,
                    "plugin_source_unreviewed_count": len(plugin_source_review.unreviewed_candidates),
                }
            )
        manifest_files: JsonArray = [
            str(terminology_summary.field_terms_path),
            str(terminology_summary.glossary_path),
            str(terminology_summary.contexts_dir),
            str(terminology_subtasks_dir),
            str(plugins_path),
            str(plugin_json_string_leaf_candidates_path),
            str(plugin_rules_path),
            str(plugin_source_risk_path),
            str(note_tag_candidates_path),
            str(note_tag_rules_path),
            str(event_commands_path),
            str(event_rules_path),
            str(placeholder_path),
            str(placeholder_rules_path),
            str(structured_placeholder_rules_path),
        ]
        if plugin_source_rules_path is not None:
            manifest_files.append(str(plugin_source_rules_path))
        if mv_virtual_namebox_candidates_path is not None:
            manifest_files.append(str(mv_virtual_namebox_candidates_path))
        if mv_virtual_namebox_rules_path is not None:
            manifest_files.append(str(mv_virtual_namebox_rules_path))
        manifest: JsonObject = {
            "files": manifest_files,
            "generated": generated_summary,
            "layout": {
                "engine": game_data.layout.engine_label,
                "engine_kind": game_data.layout.engine_kind,
                "engine_version": game_data.layout.engine_version,
                "game_root": str(game_data.layout.game_root),
                "content_root": str(game_data.layout.content_root),
                "data_dir": str(game_data.layout.data_dir),
                "js_dir": str(game_data.layout.js_dir),
                "plugins_path": str(game_data.layout.plugins_path),
            },
            "workflow": _agent_workflow_manifest(
                engine_kind=game_data.layout.engine_kind,
                terminology_subtask_summary=terminology_subtask_summary,
            ),
        }
        manifest_path = target_dir / "manifest.json"
        async with aiofiles.open(manifest_path, "w", encoding="utf-8") as file:
            _ = await file.write(f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n")
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={**generated_summary, "workspace": str(target_dir), "manifest": str(manifest_path)},
            details={"manifest": manifest},
        )

    async def validate_agent_workspace(
        self: AgentServiceContext,
        *,
        game_title: str,
        workspace: Path,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """检查 Agent 临时工作区里的可导入文件。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        set_progress(0, 12)
        set_status("读取工作区清单")
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
        details: JsonObject = {}
        field_terms_path = workspace / "terminology" / "field-terms.json"
        glossary_path = workspace / "terminology" / "glossary.json"
        plugin_rules_path = workspace / "plugin-rules.json"
        plugin_source_rules_path = workspace / "plugin-source-rules.json"
        note_tag_rules_path = workspace / "note-tag-rules.json"
        event_rules_path = workspace / "event-command-rules.json"
        mv_virtual_namebox_rules_path = workspace / MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME
        placeholder_rules_path = workspace / "placeholder-rules.json"
        structured_placeholder_rules_path = workspace / STRUCTURED_PLACEHOLDER_RULES_FILE_NAME
        event_command_codes, event_command_codes_issue = await _read_workspace_event_command_codes(workspace)
        if event_command_codes_issue is not None:
            errors.append(event_command_codes_issue)
        advance_progress(1)
        async with await self.game_registry.open_game(game_title) as session:
            set_status("加载翻译源视图")
            setting = load_setting(self.setting_path, source_language=session.source_language)
            game_data = await self._load_translation_source_game_data(
                session,
                include_writable_copies=False,
            )
            advance_progress(1)
            set_status("解析规则上下文")
            mv_virtual_namebox_rule_records = await session.read_mv_virtual_namebox_rules()
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
            advance_progress(1)
            set_status("抽取当前文本范围")
            translation_data_map = await self._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
            )
            advance_progress(1)
            set_status("扫描插件源码")
            plugin_source_scan = build_plugin_source_scan(
                game_data=game_data,
                text_rules=text_rules,
            )
            plugin_source_required = plugin_source_scan.risk.high_risk
            advance_progress(1)
            set_status("读取已保存译文和空规则复核状态")
            stored_plugin_source_rules = await session.read_plugin_source_text_rules()
            plugin_source_started = bool(stored_plugin_source_rules)
            translated_paths = await session.read_translation_location_paths()
            empty_rule_issues = await _read_empty_rule_review_issues(
                session=session,
                game_data=game_data,
                event_command_scope_hash=(
                    event_command_rule_scope_hash_for_setting(
                        game_data=game_data,
                        setting=setting,
                    )
                    if event_command_codes is None
                    else event_command_rule_scope_hash_for_command_codes(
                        game_data=game_data,
                        command_codes=event_command_codes,
                    )
                ),
                note_tag_scope_hash=note_tag_rule_scope_hash_for_text_rules(
                    game_data=game_data,
                    text_rules=text_rules,
                ),
                plugin_source_scope_hash=plugin_source_rule_scope_hash(game_data),
                placeholder_scope_hash=normal_placeholder_scope_hash(
                    translation_data_map=translation_data_map,
                    text_rules=text_rules,
                ),
                structured_placeholder_scope_hash_value=structured_placeholder_scope_hash(
                    translation_data_map=translation_data_map,
                    structured_rules=text_rules.structured_placeholder_rules,
                ),
            )
            advance_progress(1)
        set_status("校验术语文件")
        if field_terms_path.exists():
            registry: TerminologyRegistry | None = None
            try:
                registry = await load_terminology_registry(field_terms_path=field_terms_path)
                expected_registry, _speaker_contexts, _database_contexts = TerminologyExtraction(
                    game_data=game_data,
                    mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
                    text_rules=text_rules,
                ).extract_registry_and_contexts()
                _validate_terminology_registry_shape(
                    imported_registry=registry,
                    expected_registry=expected_registry,
                    errors=errors,
                )
            except Exception as error:
                errors.append(issue("terminology_validate_failed", f"字段译名表结构校验失败: {type(error).__name__}: {error}"))
            if registry is not None:
                terminology_issues = _validate_terminology_registry(registry)
                errors.extend(issue_item for issue_item in terminology_issues if issue_item.code == "terminology_empty_translation")
                warnings.extend(issue_item for issue_item in terminology_issues if issue_item.code != "terminology_empty_translation")
                details["terminology"] = {
                    "entry_count": registry.total_entry_count(),
                    "filled_count": registry.filled_entry_count(),
                    "speaker_count": len(registry.speaker_names),
                    "map_count": len(registry.map_display_names),
                    "duplicate_translation_samples": _collect_terminology_duplicate_translation_samples(registry),
                }
        else:
            errors.append(issue("terminology_missing", "工作区缺少 terminology/field-terms.json"))
            registry = None
        if glossary_path.exists():
            glossary: TerminologyGlossary | None = None
            try:
                glossary = await load_terminology_glossary(glossary_path=glossary_path)
            except Exception as error:
                errors.append(issue("glossary_validate_failed", f"正文术语表结构校验失败: {type(error).__name__}: {error}"))
            if glossary is not None:
                details["glossary"] = {
                    "term_count": glossary.term_count(),
                }
        else:
            errors.append(issue("glossary_missing", "工作区缺少 terminology/glossary.json"))
            glossary = None
        if registry is not None or glossary is not None:
            errors.extend(
                issue("terminology_bundle_invalid", message)
                for message in collect_terminology_bundle_errors(registry=registry, glossary=glossary)
            )
        advance_progress(1)
        set_status("校验插件规则")
        if plugin_rules_path.exists():
            async with aiofiles.open(plugin_rules_path, "r", encoding="utf-8") as file:
                plugin_report = _validate_workspace_plugin_rules(
                    rules_text=await file.read(),
                    game_data=game_data,
                    text_rules=text_rules,
                    translated_paths=translated_paths,
                )
            errors.extend(plugin_report.errors)
            warnings.extend(plugin_report.warnings)
            details["plugin_rules"] = plugin_report.details
            if _summary_int(plugin_report.summary, "rule_count") == 0:
                plugin_empty_issue = empty_rule_issues["plugin_rules"]
                if plugin_empty_issue is not None:
                    errors.append(plugin_empty_issue)
        else:
            errors.append(issue("plugin_rules_missing", "工作区缺少 plugin-rules.json"))
        if plugin_source_rules_path.exists():
            async with aiofiles.open(plugin_source_rules_path, "r", encoding="utf-8") as file:
                plugin_source_report = _validate_workspace_plugin_source_rules(
                    rules_text=await file.read(),
                    game_data=game_data,
                    text_rules=text_rules,
                    scan=plugin_source_scan,
                    translated_paths=translated_paths,
                )
            errors.extend(plugin_source_report.errors)
            plugin_source_warnings = plugin_source_report.warnings
            plugin_source_reviewed_count = _summary_int(plugin_source_report.summary, "reviewed_selector_count")
            promoted_plugin_source_warnings: list[AgentIssue] = []
            kept_plugin_source_warnings: list[AgentIssue] = []
            for warning in plugin_source_warnings:
                if warning.code == "plugin_source_review_incomplete" and (
                    plugin_source_required or plugin_source_reviewed_count > 0
                ):
                    promoted_plugin_source_warnings.append(warning)
                else:
                    kept_plugin_source_warnings.append(warning)
            plugin_source_warnings = kept_plugin_source_warnings
            errors.extend(promoted_plugin_source_warnings)
            if not plugin_source_required and plugin_source_reviewed_count == 0:
                plugin_source_warnings = [
                    warning
                    for warning in plugin_source_warnings
                    if warning.code != "plugin_source_rules_empty"
                ]
            warnings.extend(plugin_source_warnings)
            details["plugin_source_rules"] = plugin_source_report.details
            if plugin_source_reviewed_count == 0:
                if plugin_source_required:
                    errors.append(
                        issue(
                            "plugin_source_rules_empty_high_risk",
                            "插件源码风险较高，但工作区没有保存任何已审查的插件源码 selector；请先完成插件源码 AST 审查",
                        )
                    )
                elif plugin_source_started:
                    errors.append(
                        issue(
                            "plugin_source_rules_empty_started",
                            "插件源码支线已有审查结果，但工作区没有保存任何插件源码 selector；请补全翻译或排除 selector",
                        )
                    )
        else:
            if plugin_source_required or plugin_source_started:
                errors.append(issue("plugin_source_rules_missing", "工作区缺少 plugin-source-rules.json"))
        advance_progress(1)
        set_status("校验 Note 和事件规则")
        if note_tag_rules_path.exists():
            async with aiofiles.open(note_tag_rules_path, "r", encoding="utf-8") as file:
                note_tag_report = _validate_workspace_note_tag_rules(
                    rules_text=await file.read(),
                    game_data=game_data,
                    text_rules=text_rules,
                    translated_paths=translated_paths,
                )
            errors.extend(note_tag_report.errors)
            warnings.extend(note_tag_report.warnings)
            details["note_tag_rules"] = note_tag_report.details
            if _summary_int(note_tag_report.summary, "tag_count") == 0:
                note_tag_empty_issue = empty_rule_issues["note_tag_rules"]
                if note_tag_empty_issue is not None:
                    errors.append(note_tag_empty_issue)
        else:
            errors.append(issue("note_tag_rules_missing", "工作区缺少 note-tag-rules.json"))
        if event_rules_path.exists():
            async with aiofiles.open(event_rules_path, "r", encoding="utf-8") as file:
                event_report = _validate_workspace_event_command_rules(
                    rules_text=await file.read(),
                    game_data=game_data,
                    text_rules=text_rules,
                    translated_paths=translated_paths,
                )
            errors.extend(event_report.errors)
            warnings.extend(event_report.warnings)
            details["event_command_rules"] = event_report.details
            if _summary_int(event_report.summary, "path_rule_count") == 0:
                event_empty_issue = empty_rule_issues["event_command_rules"]
                if event_empty_issue is not None:
                    errors.append(event_empty_issue)
        else:
            errors.append(issue("event_command_rules_missing", "工作区缺少 event-command-rules.json"))
        advance_progress(1)
        set_status("校验名字框和普通占位符规则")
        if game_data.layout.engine_kind == "mv":
            if mv_virtual_namebox_rules_path.exists():
                async with aiofiles.open(mv_virtual_namebox_rules_path, "r", encoding="utf-8") as file:
                    mv_namebox_report = _validate_workspace_mv_virtual_namebox_rules(
                        rules_text=await file.read(),
                        game_data=game_data,
                        existing_records=mv_virtual_namebox_rule_records,
                    )
                errors.extend(mv_namebox_report.errors)
                warnings.extend(mv_namebox_report.warnings)
                details["mv_virtual_namebox_rules"] = mv_namebox_report.details
                if _summary_int(mv_namebox_report.summary, "rule_count") == 0:
                    mv_namebox_empty_issue = empty_rule_issues["mv_virtual_namebox_rules"]
                    if mv_namebox_empty_issue is not None:
                        errors.append(mv_namebox_empty_issue)
            else:
                errors.append(issue("mv_virtual_namebox_rules_missing", f"MV 工作区缺少 {MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME}"))
        if placeholder_rules_path.exists():
            async with aiofiles.open(placeholder_rules_path, "r", encoding="utf-8") as file:
                placeholder_rules_text = await file.read()
                placeholder_report = await self.validate_placeholder_rules(
                    game_title=game_title,
                    custom_placeholder_rules_text=placeholder_rules_text,
                    sample_texts=[],
                )
            errors.extend(placeholder_report.errors)
            warnings.extend(placeholder_report.warnings)
            details["placeholder_rules"] = placeholder_report.details
            if _summary_int(placeholder_report.summary, "rule_count") == 0:
                placeholder_empty_issue = empty_rule_issues["placeholder_rules"]
                if placeholder_empty_issue is not None:
                    errors.append(placeholder_empty_issue)
            try:
                placeholder_coverage_report = _build_workspace_placeholder_coverage_report(
                    rules_text=placeholder_rules_text,
                    setting_text_rules=setting.text_rules,
                    structured_rules=text_rules.structured_placeholder_rules,
                    translation_data_map=translation_data_map,
                )
                errors.extend(placeholder_coverage_report.errors)
                details["placeholder_coverage"] = {
                    "summary": placeholder_coverage_report.summary,
                    "details": placeholder_coverage_report.details,
                }
                uncovered_value = placeholder_coverage_report.summary.get("uncovered_count")
                if isinstance(uncovered_value, bool) or not isinstance(uncovered_value, int):
                    errors.append(issue("placeholder_coverage_invalid", "占位符候选扫描缺少有效的 uncovered_count"))
                elif uncovered_value > 0:
                    errors.append(
                        issue(
                            "placeholder_coverage_uncovered",
                            f"还有 {uncovered_value} 个当前正文会使用但未被规则覆盖的游戏控制符",
                        )
                    )
            except Exception as error:
                errors.append(
                    issue(
                        "placeholder_coverage_scan_failed",
                        f"占位符覆盖扫描失败: {type(error).__name__}: {error}",
                    )
                )
        else:
            errors.append(issue("placeholder_rules_missing", "工作区缺少 placeholder-rules.json"))
        advance_progress(1)
        set_status("校验结构化占位符规则")
        if structured_placeholder_rules_path.exists():
            async with aiofiles.open(structured_placeholder_rules_path, "r", encoding="utf-8") as file:
                structured_placeholder_rules_text = await file.read()
                structured_placeholder_report = _validate_workspace_structured_placeholder_rules(
                    game_title=game_title,
                    rules_text=structured_placeholder_rules_text,
                    setting_text_rules=setting.text_rules,
                    custom_rules=text_rules.custom_placeholder_rules,
                    translation_data_map=translation_data_map,
                )
            errors.extend(structured_placeholder_report.errors)
            warnings.extend(
                warning
                for warning in structured_placeholder_report.warnings
                if warning.code not in {"structured_placeholder_rules_empty", "structured_placeholder_samples_empty"}
            )
            details["structured_placeholder_rules"] = structured_placeholder_report.details
            if _summary_int(structured_placeholder_report.summary, "rule_count") == 0:
                structured_placeholder_empty_issue = empty_rule_issues["structured_placeholder_rules"]
                if structured_placeholder_empty_issue is not None:
                    errors.append(structured_placeholder_empty_issue)
            try:
                structured_placeholder_coverage_report = _build_workspace_structured_placeholder_coverage_report(
                    game_title=game_title,
                    rules_text=structured_placeholder_rules_text,
                    translation_data_map=translation_data_map,
                )
                errors.extend(structured_placeholder_coverage_report.errors)
                warnings.extend(structured_placeholder_coverage_report.warnings)
                details["structured_placeholder_coverage"] = {
                    "summary": structured_placeholder_coverage_report.summary,
                    "details": structured_placeholder_coverage_report.details,
                }
                uncovered_value = structured_placeholder_coverage_report.summary.get("uncovered_count")
                if isinstance(uncovered_value, bool) or not isinstance(uncovered_value, int):
                    errors.append(issue("structured_placeholder_coverage_invalid", "结构化占位符候选扫描缺少有效的 uncovered_count"))
                elif uncovered_value > 0:
                    errors.append(
                        issue(
                            "structured_placeholder_coverage_uncovered",
                            f"还有 {uncovered_value} 个当前正文会使用但未被结构化规则覆盖的协议外壳候选",
                        )
                    )
            except Exception as error:
                errors.append(
                    issue(
                        "structured_placeholder_coverage_scan_failed",
                        f"结构化占位符覆盖扫描失败: {type(error).__name__}: {error}",
                    )
                )
        else:
            errors.append(issue("structured_placeholder_rules_missing", f"工作区缺少 {STRUCTURED_PLACEHOLDER_RULES_FILE_NAME}"))
        advance_progress(1)
        set_status("汇总工作区校验报告")
        advance_progress(1)
        return AgentReport.from_parts(errors=errors, warnings=warnings, summary={"workspace": str(workspace)}, details=details)

    async def cleanup_agent_workspace(self: AgentServiceContext, *, workspace: Path) -> AgentReport:
        """按 manifest 删除 Agent 临时工作区文件。"""
        manifest_path = workspace / "manifest.json"
        if not manifest_path.exists():
            return AgentReport.from_parts(
                errors=[issue("manifest_missing", "工作区缺少 manifest.json，拒绝自动清理")],
                warnings=[],
                summary={"workspace": str(workspace)},
                details={},
            )
        async with aiofiles.open(manifest_path, "r", encoding="utf-8") as file:
            # `json.loads` 在类型存根中返回 Any；这里立刻收窄到项目 JSON 类型边界。
            raw_manifest = cast(object, json.loads(await file.read()))
        manifest = ensure_json_object(coerce_json_value(raw_manifest), "manifest")
        deleted_count = 0
        try:
            files_value = ensure_json_array(manifest.get("files"), "manifest.files")
        except TypeError:
            return AgentReport.from_parts(
                errors=[issue("manifest_invalid", "manifest.files 必须是数组")],
                warnings=[],
                summary={"workspace": str(workspace)},
                details={},
            )
        for raw_path in files_value:
            if not isinstance(raw_path, str):
                continue
            path = Path(raw_path).resolve()
            if not _is_path_inside(path, workspace.resolve()):
                continue
            if path.is_dir():
                shutil.rmtree(path)
                deleted_count += 1
            elif path.exists():
                path.unlink()
                deleted_count += 1
        if manifest_path.exists():
            manifest_path.unlink()
            deleted_count += 1
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={"workspace": str(workspace), "deleted_count": deleted_count},
            details={},
        )


def _validate_workspace_mv_virtual_namebox_rules(
    *,
    rules_text: str,
    game_data: GameData,
    existing_records: list[MvVirtualNameboxRuleRecord],
) -> AgentReport:
    """复用工作区上下文校验 MV 虚拟名字框规则。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    details: JsonObject = {"rules": [], "matched_candidates": []}
    records: list[MvVirtualNameboxRuleRecord] = []
    candidate_count = 0
    matched_candidate_count = 0
    newly_matched_candidate_count = 0
    try:
        records = parse_mv_virtual_namebox_rule_import_text(rules_text)
        if game_data.layout.engine_kind != "mv":
            errors.append(issue("mv_virtual_namebox_rules_forbidden", "MV 虚拟名字框规则只允许 RPG Maker MV 游戏使用"))
            return AgentReport.from_parts(
                errors=errors,
                warnings=[],
                summary={
                    "rule_count": 0,
                    "candidate_count": 0,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details=details,
            )
        candidates = mv_virtual_namebox_candidate_details(game_data)
        candidate_count = len(candidates)
        rule_errors, match_details = validate_mv_virtual_namebox_rules_against_game(
            game_data=game_data,
            records=records,
        )
        errors.extend(
            issue("mv_virtual_namebox_rules_invalid", _format_mv_namebox_rule_error(error_detail))
            for error_detail in rule_errors
        )
        matched_candidate_count = len(match_details)
        _existing_errors, existing_match_details = validate_mv_virtual_namebox_rules_against_game(
            game_data=game_data,
            records=existing_records,
        )
        existing_match_keys = _mv_namebox_match_keys(existing_match_details)
        newly_matched_candidates: JsonArray = [
            detail
            for detail in match_details
            if _mv_namebox_match_key(detail) not in existing_match_keys
        ]
        newly_matched_candidate_count = len(newly_matched_candidates)
        details = {
            "rules": mv_virtual_namebox_rule_records_to_import_json(records)["rules"],
            "matched_candidates": match_details,
            "newly_matched_candidates": newly_matched_candidates,
            "candidate_count": candidate_count,
        }
        if not records:
            warnings.append(issue("mv_virtual_namebox_rules_empty", "MV 虚拟名字框规则为空"))
        elif matched_candidate_count == 0 and candidate_count > 0:
            warnings.append(issue("mv_virtual_namebox_rules_no_hits", "MV 虚拟名字框规则没有命中任何候选"))
    except Exception as error:
        errors.append(issue("mv_virtual_namebox_rules_invalid", f"MV 虚拟名字框规则不可导入: {type(error).__name__}: {error}"))
        records = []
    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "rule_count": len(records),
            "candidate_count": candidate_count,
            "matched_candidate_count": matched_candidate_count,
            "newly_matched_candidate_count": newly_matched_candidate_count,
        },
        details=details,
    )


def _validate_workspace_plugin_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验插件参数规则。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    details: JsonObject = {"rules": []}
    try:
        import_file = parse_plugin_rule_import_text(rules_text)
        records = build_plugin_rule_records_from_import(
            game_data=game_data,
            import_file=import_file,
            text_rules=text_rules,
        )
        extracted_map = PluginTextExtraction(
            game_data,
            plugin_rule_records=records,
            text_rules=text_rules,
        ).extract_all_text()
        extracted_items = [
            item
            for translation_data in extracted_map.values()
            for item in translation_data.translation_items
        ]
        unwritable_items = _collect_write_protocol_unwritable_items(
            game_data=game_data,
            extracted_items=extracted_items,
        )
        if unwritable_items:
            errors.append(issue("plugin_rules_unwritable", f"插件规则存在 {len(unwritable_items)} 个不可写命中项"))
        unwritable_items_by_path = _json_items_by_location_path(unwritable_items)
        details["rules"] = [
            {
                "plugin_index": record.plugin_index,
                "plugin_name": record.plugin_name,
                "plugin_hash": record.plugin_hash,
                "path_count": len(record.path_templates),
                "paths": list(record.path_templates),
                **_build_rule_metric_detail(
                    record_items=record_items,
                    translated_paths=translated_paths,
                    unwritable_items_by_path=unwritable_items_by_path,
                ),
            }
            for record in records
            for record_items in [[
                item
                for item in extracted_items
                if item.location_path.startswith(f"{PLUGINS_FILE_NAME}/{record.plugin_index}/")
            ]]
        ]
        if not records:
            warnings.append(issue("plugin_rules_empty", "插件规则为空"))
        if records and not extracted_items:
            errors.append(issue("plugin_rules_no_hits", "插件规则没有提取到任何可翻译文本"))
    except Exception as error:
        errors.append(issue("plugin_rules_invalid", f"插件规则不可导入: {type(error).__name__}: {error}"))
        records = []
        extracted_items = []
        unwritable_items = []
    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "plugin_count": len(records),
            "rule_count": sum(len(record.path_templates) for record in records),
            "hit_count": len(extracted_items),
            "extractable_count": len(extracted_items),
            "translated_count": sum(1 for item in extracted_items if item.location_path in translated_paths),
            "writable_count": len(extracted_items) - len(unwritable_items),
            "unwritable_count": len(unwritable_items),
        },
        details=details,
    )


def _validate_workspace_plugin_source_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    scan: PluginSourceScan,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验插件源码规则，避免重新加载游戏并重扫 AST。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    details: JsonObject = {"rules": []}
    records: list[PluginSourceTextRuleRecord] = []
    extracted_items: list[TranslationItem] = []
    unwritable_items: JsonArray = []
    unreviewed_count = 0
    try:
        import_file = parse_plugin_source_rule_import_text(rules_text)
        records = build_plugin_source_rule_records_from_import(
            game_data=game_data,
            import_file=import_file,
            text_rules=text_rules,
            scan=scan,
        )
        review = collect_plugin_source_review_coverage(scan=scan, rule_records=records)
        unreviewed_count = len(review.unreviewed_candidates)
        extracted_map = PluginSourceTextExtraction(
            game_data,
            rule_records=records,
            text_rules=text_rules,
            scan=scan,
        ).extract_all_text()
        extracted_items = [
            item
            for translation_data in extracted_map.values()
            for item in translation_data.translation_items
        ]
        unwritable_items = _collect_plugin_source_unwritable_items(
            game_data=game_data,
            extracted_items=extracted_items,
        )
        if unwritable_items:
            errors.append(
                issue(
                    "plugin_source_write_back_unwritable",
                    f"插件源码规则存在 {len(unwritable_items)} 个不可写命中项",
                )
            )
        unwritable_items_by_path = _json_items_by_location_path(unwritable_items)
        details["rules"] = [
            {
                "file": record.file_name,
                "file_hash": record.file_hash,
                "selector_count": len(record.selectors),
                "excluded_selector_count": len(record.excluded_selectors),
                "reviewed_selector_count": len(record.selectors) + len(record.excluded_selectors),
                "selectors": list(record.selectors),
                "excluded_selectors": list(record.excluded_selectors),
                **_build_rule_metric_detail(
                    record_items=record_items,
                    translated_paths=translated_paths,
                    unwritable_items_by_path=unwritable_items_by_path,
                ),
            }
            for record in records
            for record_items in [[
                item
                for item in extracted_items
                if item.location_path.startswith(f"js/plugins/{record.file_name}/")
            ]]
        ]
        if not records:
            warnings.append(issue("plugin_source_rules_empty", "插件源码规则为空"))
        excluded_selector_count = sum(len(record.excluded_selectors) for record in records)
        if records and not extracted_items and excluded_selector_count == 0:
            warnings.append(issue("plugin_source_rules_no_hits", "插件源码规则没有提取到任何可翻译文本"))
        if unreviewed_count:
            review_issue = issue(
                "plugin_source_review_incomplete",
                f"插件源码规则还有 {unreviewed_count} 个候选未归入翻译或排除",
            )
            if scan.risk.high_risk or records:
                errors.append(review_issue)
            else:
                warnings.append(review_issue)
    except Exception as error:
        errors.append(issue("plugin_source_rules_invalid", f"插件源码规则不可导入: {type(error).__name__}: {error}"))
        records = []
        extracted_items = []
        unwritable_items = []
        unreviewed_count = 0
    return AgentReport.from_parts(
        errors=errors,
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
            "hit_count": len(extracted_items),
            "extractable_count": len(extracted_items),
            "translated_count": sum(1 for item in extracted_items if item.location_path in translated_paths),
            "writable_count": len(extracted_items) - len(unwritable_items),
            "unwritable_count": len(unwritable_items),
        },
        details=details,
    )


def _validate_workspace_note_tag_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验 Note 标签规则。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    details: JsonObject = {"rules": []}
    try:
        import_file = parse_note_tag_rule_import_text(rules_text)
        records = build_note_tag_rule_records_from_import(
            game_data=game_data,
            import_file=import_file,
            text_rules=text_rules,
        )
        extracted_map = NoteTagTextExtraction(
            game_data=game_data,
            rule_records=records,
            text_rules=text_rules,
        ).extract_all_text()
        extracted_items = [
            item
            for translation_data in extracted_map.values()
            for item in translation_data.translation_items
        ]
        unwritable_items = _collect_write_protocol_unwritable_items(
            game_data=game_data,
            extracted_items=extracted_items,
        )
        try:
            _preview_event_command_write_back(
                game_data=game_data,
                extracted_items=extracted_items,
                text_rules=text_rules,
            )
            details["write_back_preview"] = {
                "checked_item_count": len(extracted_items),
                "status": "ok",
            }
        except Exception as error:
            errors.append(
                issue(
                    "note_tag_write_back_invalid",
                    f"Note 标签规则命中项无法回写: {type(error).__name__}: {error}",
                )
            )
            details["write_back_preview"] = {
                "checked_item_count": len(extracted_items),
                "status": "error",
                "reason": f"{type(error).__name__}: {error}",
            }
        if unwritable_items:
            errors.append(issue("note_tag_write_back_unwritable", f"Note 标签规则存在 {len(unwritable_items)} 个不可写命中项"))
        unwritable_items_by_path = _json_items_by_location_path(unwritable_items)
        details["rules"] = [
            {
                "file_name": record.file_name,
                "tag_count": len(record.tag_names),
                "tag_names": list(record.tag_names),
                **_build_rule_metric_detail(
                    record_items=record_items,
                    translated_paths=translated_paths,
                    unwritable_items_by_path=unwritable_items_by_path,
                ),
            }
            for record in records
            for record_items in [[
                item
                for item in extracted_items
                if _note_tag_item_matches_rule(item=item, rule_record=record)
            ]]
        ]
        if not records:
            warnings.append(issue("note_tag_rules_empty", "Note 标签规则为空"))
    except Exception as error:
        errors.append(issue("note_tag_rules_invalid", f"Note 标签规则不可导入: {type(error).__name__}: {error}"))
        records = []
        extracted_items = []
        unwritable_items = []
    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "file_count": len(records),
            "tag_count": sum(len(record.tag_names) for record in records),
            "hit_count": len(extracted_items),
            "extractable_count": len(extracted_items),
            "translated_count": sum(1 for item in extracted_items if item.location_path in translated_paths),
            "writable_count": len(extracted_items) - len(unwritable_items),
            "unwritable_count": len(unwritable_items),
        },
        details=details,
    )


def _validate_workspace_event_command_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验事件指令规则。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    details: JsonObject = {"rules": []}
    try:
        import_file = parse_event_command_rule_import_text(rules_text)
        records = build_event_command_rule_records_from_import(game_data=game_data, import_file=import_file)
        extracted_map = EventCommandTextExtraction(
            game_data,
            rule_records=records,
            text_rules=text_rules,
        ).extract_all_text()
        extracted_items = [
            item
            for translation_data in extracted_map.values()
            for item in translation_data.translation_items
        ]
        unwritable_items = _collect_write_protocol_unwritable_items(
            game_data=game_data,
            extracted_items=extracted_items,
        )
        try:
            _preview_event_command_write_back(
                game_data=game_data,
                extracted_items=extracted_items,
                text_rules=text_rules,
            )
            details["write_back_preview"] = {
                "checked_item_count": len(extracted_items),
                "status": "ok",
            }
        except Exception as error:
            errors.append(
                issue(
                    "event_command_write_back_invalid",
                    f"事件指令规则命中项无法回写: {type(error).__name__}: {error}",
                )
            )
            details["write_back_preview"] = {
                "checked_item_count": len(extracted_items),
                "status": "error",
                "reason": f"{type(error).__name__}: {error}",
            }
        if unwritable_items:
            errors.append(issue("event_command_rules_unwritable", f"事件指令规则存在 {len(unwritable_items)} 个不可写命中项"))
        unwritable_items_by_path = _json_items_by_location_path(unwritable_items)
        rule_details: JsonArray = []
        for record in records:
            record_extracted_map = EventCommandTextExtraction(
                game_data,
                rule_records=[record],
                text_rules=text_rules,
            ).extract_all_text()
            record_items = [
                item
                for translation_data in record_extracted_map.values()
                for item in translation_data.translation_items
            ]
            rule_details.append(
                {
                    "command_code": record.command_code,
                    "match_count": len(record.parameter_filters),
                    "path_count": len(record.path_templates),
                    "paths": list(record.path_templates),
                    **_build_rule_metric_detail(
                        record_items=record_items,
                        translated_paths=translated_paths,
                        unwritable_items_by_path=unwritable_items_by_path,
                    ),
                }
            )
        details["rules"] = rule_details
        if not records:
            warnings.append(issue("event_command_rules_empty", "事件指令规则为空"))
        if records and not extracted_items:
            warnings.append(issue("event_command_rules_no_hits", "事件指令规则没有提取到任何可翻译文本"))
    except Exception as error:
        errors.append(issue("event_command_rules_invalid", f"事件指令规则不可导入: {type(error).__name__}: {error}"))
        records = []
        extracted_items = []
        unwritable_items = []
    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "rule_group_count": len(records),
            "path_rule_count": sum(len(record.path_templates) for record in records),
            "hit_count": len(extracted_items),
            "extractable_count": len(extracted_items),
            "translated_count": sum(1 for item in extracted_items if item.location_path in translated_paths),
            "writable_count": len(extracted_items) - len(unwritable_items),
            "unwritable_count": len(unwritable_items),
        },
        details=details,
    )


def _build_workspace_placeholder_coverage_report(
    *,
    rules_text: str,
    setting_text_rules: TextRulesSetting,
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    translation_data_map: dict[str, TranslationData],
) -> AgentReport:
    """复用已抽取文本扫描普通占位符覆盖情况。"""
    custom_rules = load_custom_placeholder_rules_text(rules_text)
    text_rules = TextRules.from_setting(
        setting_text_rules,
        custom_placeholder_rules=custom_rules,
        structured_placeholder_rules=structured_rules,
    )
    candidates = scan_placeholder_candidates(translation_data_map, text_rules)
    uncovered_count = count_uncovered_candidates(candidates)
    warnings: list[AgentIssue] = []
    if uncovered_count:
        warnings.append(issue("uncovered_placeholder", f"发现 {uncovered_count} 个未覆盖的疑似自定义控制符"))
    return AgentReport.from_parts(
        errors=[],
        warnings=warnings,
        summary={
            "candidate_count": len(candidates),
            "uncovered_count": uncovered_count,
            "custom_rule_count": len(custom_rules),
        },
        details={
            "candidates": placeholder_candidates_to_details(candidates),
        },
    )


def _validate_workspace_structured_placeholder_rules(
    *,
    game_title: str,
    rules_text: str,
    setting_text_rules: TextRulesSetting,
    custom_rules: tuple[CustomPlaceholderRule, ...],
    translation_data_map: dict[str, TranslationData],
) -> AgentReport:
    """复用工作区上下文校验结构化占位符规则。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    sample_texts: list[str] = []
    try:
        structured_rules = load_structured_placeholder_rules_text(rules_text)
        text_rules = TextRules.from_setting(
            setting_text_rules,
            custom_placeholder_rules=custom_rules,
            structured_placeholder_rules=structured_rules,
        )
        sample_texts = _collect_structured_placeholder_preview_samples(
            translation_data_map=translation_data_map,
            structured_rules=structured_rules,
        )
    except Exception as error:
        return AgentReport.from_parts(
            errors=[
                issue(
                    "structured_placeholder_rules_invalid",
                    f"结构化占位符规则不可用: {type(error).__name__}: {error}",
                )
            ],
            warnings=[],
            summary={
                "game": game_title,
                "rule_count": 0,
                "sample_count": len(sample_texts),
            },
            details={},
        )

    rule_details: JsonArray = []
    for rule in structured_rules:
        protected_group_details: JsonArray = []
        for group_name, placeholder_template in sorted(rule.protected_groups.items()):
            protected_group_details.append(
                {
                    "group_name": group_name,
                    "placeholder_template": placeholder_template,
                    "placeholder_preview": text_rules.format_custom_placeholder(
                        template=placeholder_template,
                        index=1,
                    ),
                }
            )
        rule_details.append(
            {
                "name": rule.rule_name,
                "type": rule.rule_type,
                "pattern": rule.pattern_text,
                "translatable_group": rule.translatable_group,
                "protected_groups": protected_group_details,
            }
        )

    sample_details: JsonArray = []
    for sample_text in sample_texts:
        try:
            sample_preview = _preview_placeholder_sample(text_rules, sample_text)
            sample_details.append(sample_preview)
            if _placeholder_preview_loses_visible_source_text(
                text_rules=text_rules,
                sample_preview=sample_preview,
            ):
                errors.append(
                    issue(
                        "structured_placeholder_loses_translatable_text",
                        "结构化占位符规则把含源语言正文的样本文本整体遮蔽，模型将看不到需要翻译的内容",
                    )
                )
        except Exception as error:
            errors.append(
                issue(
                    "structured_placeholder_preview",
                    f"结构化占位符样本文本预览失败: {type(error).__name__}: {error}",
                )
            )

    if not structured_rules:
        warnings.append(issue("structured_placeholder_rules_empty", "当前没有结构化占位符规则"))
    if structured_rules and not sample_texts:
        warnings.append(issue("structured_placeholder_samples_empty", "当前正文没有命中结构化占位符规则的样本文本"))

    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "game": game_title,
            "rule_count": len(structured_rules),
            "sample_count": len(sample_texts),
        },
        details={
            "rules": rule_details,
            "samples": sample_details,
        },
    )


def _build_workspace_structured_placeholder_coverage_report(
    *,
    game_title: str,
    rules_text: str,
    translation_data_map: dict[str, TranslationData],
) -> AgentReport:
    """复用已抽取正文扫描结构化占位符覆盖情况。"""
    try:
        structured_rules = load_structured_placeholder_rules_text(rules_text)
    except Exception as error:
        return AgentReport.from_parts(
            errors=[
                issue(
                    "structured_placeholder_scan_failed",
                    f"结构化占位符覆盖扫描失败: {type(error).__name__}: {error}",
                )
            ],
            warnings=[],
            summary={
                "game": game_title,
                "rule_count": 0,
                "candidate_count": 0,
                "covered_count": 0,
                "uncovered_count": 0,
            },
            details={},
        )

    candidate_details = _collect_structured_placeholder_candidate_details(
        translation_data_map=translation_data_map,
        structured_rules=structured_rules,
    )
    covered_count = sum(
        1
        for detail in candidate_details
        if isinstance(detail, dict) and detail.get("covered") is True
    )
    uncovered_count = len(candidate_details) - covered_count
    warnings: list[AgentIssue] = []
    if uncovered_count:
        warnings.append(issue("structured_placeholder_uncovered", f"发现 {uncovered_count} 个未被结构化规则覆盖的协议外壳候选"))
    return AgentReport.from_parts(
        errors=[],
        warnings=warnings,
        summary={
            "game": game_title,
            "rule_count": len(structured_rules),
            "candidate_count": len(candidate_details),
            "covered_count": covered_count,
            "uncovered_count": uncovered_count,
        },
        details={
            "candidates": candidate_details[:100],
        },
    )


def _summary_int(summary: JsonObject, key: str) -> int:
    """从 Agent 报告摘要中读取整数计数字段。"""
    raw_value = summary.get(key)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise RuntimeError(f"报告缺少有效计数字段: {key}")
    return raw_value


async def _read_empty_rule_review_issues(
    *,
    session: TargetGameSession,
    game_data: GameData,
    event_command_scope_hash: str,
    note_tag_scope_hash: str,
    plugin_source_scope_hash: str,
    placeholder_scope_hash: str,
    structured_placeholder_scope_hash_value: str,
) -> dict[str, AgentIssue | None]:
    """读取工作区空规则文件对应的显式确认状态。"""
    return {
        "plugin_rules": await _empty_rule_review_issue(
            session=session,
            rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
            current_scope_hash=plugin_rule_scope_hash(game_data),
            unconfirmed_code="plugin_rules_empty_unconfirmed",
            stale_code="plugin_rules_empty_confirmation_stale",
            label="插件规则",
        ),
        "plugin_source_rules": await _empty_rule_review_issue(
            session=session,
            rule_domain=PLUGIN_SOURCE_TEXT_RULE_DOMAIN,
            current_scope_hash=plugin_source_scope_hash,
            unconfirmed_code="plugin_source_rules_empty_unconfirmed",
            stale_code="plugin_source_rules_empty_confirmation_stale",
            label="插件源码规则",
        ),
        "event_command_rules": await _empty_rule_review_issue(
            session=session,
            rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
            current_scope_hash=event_command_scope_hash,
            unconfirmed_code="event_command_rules_empty_unconfirmed",
            stale_code="event_command_rules_empty_confirmation_stale",
            label="事件指令规则",
        ),
        "mv_virtual_namebox_rules": (
            await _empty_rule_review_issue(
                session=session,
                rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
                current_scope_hash=mv_virtual_namebox_rule_scope_hash(
                    mv_virtual_namebox_candidate_details(game_data)
                ),
                unconfirmed_code="mv_virtual_namebox_rules_empty_unconfirmed",
                stale_code="mv_virtual_namebox_rules_empty_confirmation_stale",
                label="MV 虚拟名字框规则",
            )
            if game_data.layout.engine_kind == "mv"
            else None
        ),
        "note_tag_rules": await _empty_rule_review_issue(
            session=session,
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            current_scope_hash=note_tag_scope_hash,
            unconfirmed_code="note_tag_rules_empty_unconfirmed",
            stale_code="note_tag_rules_empty_confirmation_stale",
            label="Note 标签规则",
        ),
        "placeholder_rules": await _empty_rule_review_issue(
            session=session,
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            current_scope_hash=placeholder_scope_hash,
            unconfirmed_code="placeholder_rules_empty_unconfirmed",
            stale_code="placeholder_rules_empty_confirmation_stale",
            label="普通占位符规则",
        ),
        "structured_placeholder_rules": await _empty_rule_review_issue(
            session=session,
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            current_scope_hash=structured_placeholder_scope_hash_value,
            unconfirmed_code="structured_placeholder_rules_empty_unconfirmed",
            stale_code="structured_placeholder_rules_empty_confirmation_stale",
            label="结构化占位符规则",
        ),
    }


async def _empty_rule_review_issue(
    *,
    session: TargetGameSession,
    rule_domain: RuleReviewDomain,
    current_scope_hash: str,
    unconfirmed_code: str,
    stale_code: str,
    label: str,
) -> AgentIssue | None:
    """判断空规则文件是否有仍然有效的显式确认。"""
    state = await session.read_rule_review_state(rule_domain=rule_domain)
    if state is None or not state.reviewed_empty:
        return issue(unconfirmed_code, f"{label}为空，必须先用对应导入命令传 --confirm-empty 保存当前范围的空结果确认")
    if state.scope_hash != current_scope_hash:
        return issue(stale_code, f"{label}曾确认为空，但当前游戏内容已经变化，请重新导出并检查规则")
    return None


async def _read_workspace_event_command_codes(workspace: Path) -> tuple[frozenset[int] | None, AgentIssue | None]:
    """从工作区 manifest 读取本轮事件指令候选编码。"""
    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        return None, issue("manifest_missing", "工作区缺少 manifest.json，无法确认工作区来源和事件指令编码")
    try:
        async with aiofiles.open(manifest_path, "r", encoding="utf-8") as file:
            raw_manifest = cast(object, json.loads(await file.read()))
        manifest = ensure_json_object(coerce_json_value(raw_manifest), "manifest")
        generated = ensure_json_object(manifest.get("generated"), "manifest.generated")
        raw_codes = ensure_json_array(generated.get("event_command_codes"), "manifest.generated.event_command_codes")
        codes: set[int] = set()
        for raw_code in raw_codes:
            if isinstance(raw_code, bool) or not isinstance(raw_code, int):
                return None, issue("manifest_invalid", "manifest.generated.event_command_codes 必须是整数数组")
            codes.add(raw_code)
        if not codes:
            return None, issue("manifest_invalid", "manifest.generated.event_command_codes 不能为空")
        return frozenset(codes), None
    except Exception as error:
        return None, issue("manifest_invalid", f"读取工作区 manifest 失败: {type(error).__name__}: {error}")
