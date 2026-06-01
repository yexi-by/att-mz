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
    _agent_workflow_manifest,
    _build_placeholder_coverage_report_with_context,
    _build_structured_placeholder_coverage_report_with_context,
    _build_custom_placeholder_rule_draft,
    _collect_terminology_duplicate_translation_samples,
    _collect_plugin_json_string_leaf_candidate_details,
    _event_command_rule_records_to_import_json,
    _is_path_inside,
    _merge_terminology_registry,
    _note_tag_rule_records_to_import_json,
    _nonstandard_data_skipped_warnings,
    _placeholder_rule_records_to_import_json,
    _plugin_rule_records_to_import_json,
    _structured_placeholder_rule_records_to_import_json,
    _validate_event_command_rules_with_context,
    _validate_mv_virtual_namebox_rules_with_context,
    _validate_note_tag_rules_with_context,
    _validate_placeholder_rules_with_context,
    _validate_plugin_source_rules_with_context,
    _validate_plugin_rules_with_context,
    _validate_structured_placeholder_rules_with_context,
    _validate_terminology_registry,
    _validate_terminology_registry_shape,
    _noop_quality_progress_callbacks,
    _write_json_object,
    _write_json_value,
    _write_terminology_subtask_files,
    aiofiles,
    cast,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
    export_event_commands_json_file,
    export_note_tag_candidates_file,
    export_plugins_json_file,
    export_terminology_artifacts,
    issue,
    json,
    load_custom_placeholder_rules_text,
    load_setting,
    load_terminology_glossary,
    load_terminology_registry,
    placeholder_candidates_to_details,
    resolve_event_command_codes,
    scan_placeholder_candidates,
    shutil,
    write_field_terms_json,
    write_glossary_json,
)
from app.config.schemas import TextRulesSetting
from app.nonstandard_data import (
    build_nonstandard_data_scan,
    export_nonstandard_data_workspace,
    nonstandard_data_rule_records_to_import_json,
    parse_nonstandard_data_rule_import_text,
    validate_nonstandard_data_rules,
)
from app.plugin_source_text import (
    PluginSourceScan,
    build_plugin_source_scan,
    collect_plugin_source_review_coverage,
    plugin_source_rule_records_to_import_json,
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
)
from app.rmmz.game_file_view import GameFileView, parse_game_file_view
from app.rmmz.schema import MvVirtualNameboxRuleRecord
from app.terminology import collect_terminology_bundle_errors


def _plugin_source_scan_warnings(scan: PluginSourceScan) -> list[AgentIssue]:
    """把跳过的非法插件源码文件转换成 Agent 告警。"""
    if not scan.syntax_errors:
        return []
    active_count = sum(1 for file_name in scan.syntax_errors if file_name in scan.enabled_plugin_files)
    return [
        issue(
            "plugin_source_syntax_warning",
            (
                f"发现 {len(scan.syntax_errors)} 个插件源码文件不是合法 JS，已跳过插件源码文本扫描；"
                f"其中启用插件 {active_count} 个，详情见 plugin-source-risk-report.json"
            ),
        )
    ]


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
        warnings.extend(_plugin_source_scan_warnings(scan))
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
            warnings=_plugin_source_scan_warnings(scan),
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
            nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
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
            nonstandard_data_scan = await build_nonstandard_data_scan(
                layout=game_data.layout,
                source_view=GameFileView.TRANSLATION_SOURCE,
                text_rules=text_rules,
            )
            nonstandard_data_extension_active = nonstandard_data_scan.high_risk or bool(nonstandard_data_rules)
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
        nonstandard_data_dir = target_dir / "nonstandard-data"
        nonstandard_data_export_details = await export_nonstandard_data_workspace(
            scan=nonstandard_data_scan,
            output_dir=nonstandard_data_dir,
        )
        nonstandard_data_risk_path = target_dir / "nonstandard-data-risk-report.json"
        await _write_json_object(
            nonstandard_data_risk_path,
            {
                "source_view": GameFileView.TRANSLATION_SOURCE.value,
                "summary": nonstandard_data_scan.summary_json(),
                "files": [file_scan.to_json_object() for file_scan in nonstandard_data_scan.file_scans],
            },
        )
        nonstandard_data_rules_path: Path | None = None
        if nonstandard_data_extension_active:
            nonstandard_data_rules_path = target_dir / "nonstandard-data-rules.json"
            await _write_json_value(
                nonstandard_data_rules_path,
                nonstandard_data_rule_records_to_import_json(nonstandard_data_rules),
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
            "plugin_source_syntax_error_file_count": len(plugin_source_scan.syntax_errors),
            "stale_plugin_rule_count": stale_plugin_rule_count,
            "nonstandard_data_file_count": len(nonstandard_data_scan.files),
            "nonstandard_data_candidate_count": len(nonstandard_data_scan.candidates),
            "nonstandard_data_high_risk": nonstandard_data_scan.high_risk,
            "nonstandard_data_path_rule_count": sum(len(rule.path_templates) for rule in nonstandard_data_rules),
            "nonstandard_data_skipped_file_count": sum(1 for rule in nonstandard_data_rules if rule.skipped),
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
            str(nonstandard_data_risk_path),
            str(nonstandard_data_dir),
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
        if nonstandard_data_rules_path is not None:
            manifest_files.append(str(nonstandard_data_rules_path))
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
            warnings=[
                *_nonstandard_data_skipped_warnings(nonstandard_data_rules),
                *_plugin_source_scan_warnings(plugin_source_scan),
            ],
            summary={**generated_summary, "workspace": str(target_dir), "manifest": str(manifest_path)},
            details={
                "manifest": manifest,
                "nonstandard_data_export": nonstandard_data_export_details,
            },
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
        set_progress(0, 13)
        set_status("读取工作区清单")
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
        details: JsonObject = {}
        field_terms_path = workspace / "terminology" / "field-terms.json"
        glossary_path = workspace / "terminology" / "glossary.json"
        plugin_rules_path = workspace / "plugin-rules.json"
        plugin_source_rules_path = workspace / "plugin-source-rules.json"
        nonstandard_data_risk_path = workspace / "nonstandard-data-risk-report.json"
        nonstandard_data_rules_path = workspace / "nonstandard-data-rules.json"
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
            set_status("扫描非标准 data 文件")
            try:
                nonstandard_data_scan = await build_nonstandard_data_scan(
                    layout=game_data.layout,
                    source_view=GameFileView.TRANSLATION_SOURCE,
                    text_rules=text_rules,
                )
                nonstandard_data_scan_error: Exception | None = None
            except Exception as error:
                nonstandard_data_scan = None
                nonstandard_data_scan_error = error
            advance_progress(1)
            set_status("读取已保存译文和空规则复核状态")
            stored_plugin_source_rules = await session.read_plugin_source_text_rules()
            plugin_source_started = bool(stored_plugin_source_rules)
            stored_nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
            nonstandard_data_started = bool(stored_nonstandard_data_rules)
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
                    warnings.append(plugin_empty_issue)
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
        set_status("校验非标准 data 文件规则")
        if not nonstandard_data_risk_path.exists():
            errors.append(issue("nonstandard_data_risk_report_missing", "工作区缺少 nonstandard-data-risk-report.json"))
        if nonstandard_data_scan_error is not None:
            errors.append(
                issue(
                    "nonstandard_data_scan_failed",
                    f"非标准 data 文件文本扫描失败: {type(nonstandard_data_scan_error).__name__}: {nonstandard_data_scan_error}",
                )
            )
        elif nonstandard_data_scan is not None and nonstandard_data_rules_path.exists():
            try:
                async with aiofiles.open(nonstandard_data_rules_path, "r", encoding="utf-8") as file:
                    nonstandard_data_rules_text = await file.read()
                nonstandard_data_import_file = parse_nonstandard_data_rule_import_text(nonstandard_data_rules_text)
                nonstandard_data_validation = validate_nonstandard_data_rules(
                    scan=nonstandard_data_scan,
                    import_file=nonstandard_data_import_file,
                )
                if nonstandard_data_validation.skipped_files:
                    persistent_warnings = _nonstandard_data_skipped_warnings(stored_nonstandard_data_rules)
                    if persistent_warnings:
                        warnings.extend(persistent_warnings)
                    else:
                        warnings.append(
                            issue(
                                "nonstandard_data_files_skipped",
                                f"已确认跳过 {len(nonstandard_data_validation.skipped_files)} 个非标准 data 文件，后续报告仍会提示这些文件可能残留源文",
                            )
                        )
                details["nonstandard_data_rules"] = nonstandard_data_validation.details
            except Exception as error:
                errors.append(
                    issue(
                        "nonstandard_data_rules_invalid",
                        f"非标准 data 文件文本规则不可导入: {type(error).__name__}: {error}",
                    )
                )
        elif nonstandard_data_scan is not None and (nonstandard_data_scan.high_risk or nonstandard_data_started):
            errors.append(issue("nonstandard_data_rules_missing", "工作区缺少 nonstandard-data-rules.json"))
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
                    warnings.append(note_tag_empty_issue)
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
                    warnings.append(event_empty_issue)
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
                        warnings.append(mv_namebox_empty_issue)
            else:
                errors.append(issue("mv_virtual_namebox_rules_missing", f"MV 工作区缺少 {MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME}"))
        if placeholder_rules_path.exists():
            async with aiofiles.open(placeholder_rules_path, "r", encoding="utf-8") as file:
                placeholder_rules_text = await file.read()
                placeholder_report = _validate_workspace_placeholder_rules(
                    rules_text=placeholder_rules_text,
                    setting_text_rules=setting.text_rules,
                    structured_rules=text_rules.structured_placeholder_rules,
                    translation_data_map=translation_data_map,
                )
            errors.extend(placeholder_report.errors)
            warnings.extend(placeholder_report.warnings)
            details["placeholder_rules"] = placeholder_report.details
            if _summary_int(placeholder_report.summary, "rule_count") == 0:
                placeholder_empty_issue = empty_rule_issues["placeholder_rules"]
                if placeholder_empty_issue is not None:
                    warnings.append(placeholder_empty_issue)
            try:
                placeholder_coverage_report = _build_workspace_placeholder_coverage_report(
                    rules_text=placeholder_rules_text,
                    setting_text_rules=setting.text_rules,
                    structured_rules=text_rules.structured_placeholder_rules,
                    translation_data_map=translation_data_map,
                )
                errors.extend(placeholder_coverage_report.errors)
                warnings.extend(placeholder_coverage_report.warnings)
                details["placeholder_coverage"] = {
                    "summary": placeholder_coverage_report.summary,
                    "details": placeholder_coverage_report.details,
                }
                uncovered_value = placeholder_coverage_report.summary.get("uncovered_count")
                if isinstance(uncovered_value, bool) or not isinstance(uncovered_value, int):
                    errors.append(issue("placeholder_coverage_invalid", "占位符候选扫描缺少有效的 uncovered_count"))
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
                    warnings.append(structured_placeholder_empty_issue)
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
    return _validate_mv_virtual_namebox_rules_with_context(
        rules_text=rules_text,
        game_data=game_data,
        existing_records=existing_records,
    )


def _validate_workspace_plugin_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验插件参数规则。"""
    return _validate_plugin_rules_with_context(
        rules_text=rules_text,
        game_data=game_data,
        text_rules=text_rules,
        translated_paths=translated_paths,
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
    return _validate_plugin_source_rules_with_context(
        rules_text=rules_text,
        game_data=game_data,
        text_rules=text_rules,
        scan=scan,
        translated_paths=translated_paths,
    )


def _validate_workspace_note_tag_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验 Note 标签规则。"""
    return _validate_note_tag_rules_with_context(
        rules_text=rules_text,
        game_data=game_data,
        text_rules=text_rules,
        translated_paths=translated_paths,
    )


def _validate_workspace_event_command_rules(
    *,
    rules_text: str,
    game_data: GameData,
    text_rules: TextRules,
    translated_paths: set[str],
) -> AgentReport:
    """复用工作区上下文校验事件指令规则。"""
    return _validate_event_command_rules_with_context(
        rules_text=rules_text,
        game_data=game_data,
        text_rules=text_rules,
        translated_paths=translated_paths,
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
    return _build_placeholder_coverage_report_with_context(
        setting_text_rules=setting_text_rules,
        custom_rules=custom_rules,
        structured_rules=structured_rules,
        translation_data_map=translation_data_map,
    )


def _validate_workspace_placeholder_rules(
    *,
    rules_text: str,
    setting_text_rules: TextRulesSetting,
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    translation_data_map: dict[str, TranslationData],
) -> AgentReport:
    """复用工作区上下文校验普通占位符规则。"""
    try:
        custom_rules = load_custom_placeholder_rules_text(rules_text)
    except Exception as error:
        return AgentReport.from_parts(
            errors=[
                issue(
                    "placeholder_rules_invalid",
                    f"自定义占位符规则不可用: {type(error).__name__}: {error}",
                )
            ],
            warnings=[],
            summary={
                "source": "--placeholder-rules",
                "rule_count": 0,
                "sample_count": 0,
            },
            details={},
        )
    return _validate_placeholder_rules_with_context(
        source_label="--placeholder-rules",
        setting_text_rules=setting_text_rules,
        custom_rules=custom_rules,
        structured_rules=structured_rules,
        sample_texts=[],
        translation_data_map=translation_data_map,
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
    return _validate_structured_placeholder_rules_with_context(
        game_title=game_title,
        rules_text=rules_text,
        setting_text_rules=setting_text_rules,
        custom_rules=custom_rules,
        sample_texts=[],
        translation_data_map=translation_data_map,
    )


def _build_workspace_structured_placeholder_coverage_report(
    *,
    game_title: str,
    rules_text: str,
    translation_data_map: dict[str, TranslationData],
) -> AgentReport:
    """复用已抽取正文扫描结构化占位符覆盖情况。"""
    return _build_structured_placeholder_coverage_report_with_context(
        game_title=game_title,
        rules_text=rules_text,
        translation_data_map=translation_data_map,
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
