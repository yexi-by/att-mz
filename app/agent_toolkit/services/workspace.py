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
    JsonValue,
    Path,
    QualityProgressCallbacks,
    STRUCTURED_PLACEHOLDER_RULES_FILE_NAME,
    TERMINOLOGY_SUBTASK_GROUPS,
    TargetGameSession,
    TerminologyExtraction,
    TerminologyGlossary,
    TerminologyRegistry,
    CustomPlaceholderRule,
    StructuredPlaceholderRule,
    TextRules,
    _agent_workflow_manifest,
    _build_custom_placeholder_rule_draft_from_details,
    _collect_terminology_duplicate_translation_samples,
    _collect_plugin_json_string_leaf_candidate_details,
    _event_command_rule_records_to_import_json,
    _is_path_inside,
    _merge_terminology_registry,
    _format_mv_namebox_rule_error,
    _mv_namebox_match_key,
    _mv_namebox_match_keys,
    _note_tag_rule_records_to_import_json,
    _nonstandard_data_skipped_warnings,
    _placeholder_rule_records_to_import_json,
    _plugin_rule_records_to_import_json,
    _structured_placeholder_rule_records_to_import_json,
    _validate_event_command_rules_with_context,
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
    load_structured_placeholder_rules_text,
    load_setting,
    load_terminology_glossary,
    load_terminology_registry,
    resolve_event_command_codes,
    shutil,
    write_field_terms_json,
    write_glossary_json,
)
from app.config.schemas import Setting, TextRulesSetting
from app.nonstandard_data import (
    nonstandard_data_rule_records_to_import_json,
    parse_nonstandard_data_rule_import_text,
    validate_nonstandard_data_rules,
)
from app.nonstandard_data.scanner import build_nonstandard_data_scan, export_nonstandard_data_workspace
from app.native_placeholder_scan import (
    collect_native_placeholder_candidate_details_from_entries,
    count_uncovered_placeholder_candidate_details,
)
from app.native_structured_placeholder_scan import (
    collect_native_structured_placeholder_candidate_details_from_entries,
    count_uncovered_structured_placeholder_candidate_details,
)
from app.plugin_source_text import (
    PluginSourceScan,
    collect_plugin_source_review_coverage,
    plugin_source_rule_records_to_import_json,
)
from app.plugin_source_text.native_scan import (
    build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs as _build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs,
    build_native_plugin_source_risk_report_from_inputs as _build_native_plugin_source_risk_report_from_inputs,
    build_native_plugin_source_scan as _build_native_plugin_source_scan,
    native_plugin_source_risk_report_from_scan as _native_plugin_source_risk_report_from_scan,
)
from app.rmmz.mv_namebox import (
    MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME,
    MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME,
    mv_virtual_namebox_rule_records_to_import_json,
    parse_mv_virtual_namebox_rule_import_text,
)
from app.rmmz.mv_namebox_native import (
    native_mv_virtual_namebox_candidates_payload,
    scan_native_mv_virtual_namebox,
)
from app.rmmz.game_file_view import GameFileView, parse_game_file_view
from app.rmmz.loader import load_plugin_source_files_for_view
from app.rmmz.schema import MvVirtualNameboxRuleRecord
from app.rmmz.source_snapshot import validate_plugin_source_snapshot_manifest
from app.rule_review import (
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    placeholder_rule_scope_hash,
    structured_placeholder_rule_scope_hash,
)
from app.rule_review_decision import RuleCoverageResult
from app.terminology import collect_terminology_bundle_errors
from app.text_index import (
    collect_text_index_external_rule_gate_errors,
    detect_text_index_invalidations,
    rebuild_text_index_native_storage,
)

SOURCE_SNAPSHOT_MISSING_MESSAGE = (
    "尚未创建翻译源快照，请使用干净原始游戏目录重新执行 add-game；"
    "如果只是文本范围索引缺失或过期，再运行 rebuild-text-index"
)


def _plugin_source_native_scan_warnings(risk_report: JsonObject) -> list[AgentIssue]:
    """把 Rust 候选扫描跳过的非法插件源码文件转换成 Agent 告警。"""
    syntax_errors = ensure_json_array(risk_report["syntax_errors"], "plugin-source-risk-report.syntax_errors")
    if not syntax_errors:
        return []
    active_count = 0
    for index, raw_error in enumerate(syntax_errors):
        error = ensure_json_object(raw_error, f"plugin-source-risk-report.syntax_errors[{index}]")
        if error.get("active") is True:
            active_count += 1
    return [
        issue(
            "plugin_source_syntax_warning",
            (
                f"发现 {len(syntax_errors)} 个插件源码文件不是合法 JS，已跳过插件源码文本扫描；"
                f"其中启用插件 {active_count} 个，详情见 plugin-source-risk-report.json"
            ),
        )
    ]


def _json_bool(payload: JsonObject, key: str, label: str) -> bool:
    """读取 JSON 布尔字段。"""
    value = payload.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{label}.{key} 必须是布尔值")
    return value


async def _write_compact_json_value(path: Path, payload: JsonValue) -> None:
    """写入大型工作区 JSON，避免 pretty 输出主导本地 CLI 耗时。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        _ = await file.write(f"{text}\n")


def _sampled_coverage_report_details(
    coverage: RuleCoverageResult,
    *,
    summary_extra: JsonObject | None = None,
) -> JsonObject:
    """工作区验收报告只输出覆盖样本；完整候选已在工作区候选文件中。"""
    summary: JsonObject = {
        **coverage.summary(detail_mode="sampled"),
        **(summary_extra or {}),
    }
    return {
        "summary": summary,
        "details": coverage.sampled_details(),
    }


async def _read_workspace_placeholder_entries_from_text_index(
    *,
    session: TargetGameSession,
    setting: Setting,
    text_rules: TextRules,
) -> tuple[list[tuple[str, list[str]]], str]:
    """工作区命令从持久文本索引读取占位符扫描所需的轻量正文。"""
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
        _ = await rebuild_text_index_native_storage(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
    else:
        text_index_status = "used"
    return await session.read_text_index_placeholder_texts(), text_index_status


def _normal_placeholder_coverage_result_from_entries(
    *,
    entries: list[tuple[str, list[str]]],
    text_rules: TextRules,
    rule_count: int,
) -> RuleCoverageResult:
    """用轻量索引正文构建普通占位符覆盖结果。"""
    candidate_details = collect_native_placeholder_candidate_details_from_entries(
        entries=entries,
        text_rules=text_rules,
    )
    uncovered_count = count_uncovered_placeholder_candidate_details(candidate_details)
    return RuleCoverageResult(
        rule_domain=PLACEHOLDER_RULE_DOMAIN,
        scope_hash=placeholder_rule_scope_hash(candidate_details),
        rule_count=rule_count,
        candidate_count=len(candidate_details),
        covered_count=len(candidate_details) - uncovered_count,
        uncovered_count=uncovered_count,
        candidates=candidate_details,
    )


def _structured_placeholder_coverage_result_from_entries(
    *,
    entries: list[tuple[str, list[str]]],
    text_rules: TextRules,
    rule_count: int,
) -> RuleCoverageResult:
    """用轻量索引正文构建结构化占位符覆盖结果。"""
    candidate_details = collect_native_structured_placeholder_candidate_details_from_entries(
        entries=entries,
        text_rules=text_rules,
    )
    uncovered_count = count_uncovered_structured_placeholder_candidate_details(candidate_details)
    return RuleCoverageResult(
        rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
        scope_hash=structured_placeholder_rule_scope_hash(candidate_details),
        rule_count=rule_count,
        candidate_count=len(candidate_details),
        covered_count=len(candidate_details) - uncovered_count,
        uncovered_count=uncovered_count,
        candidates=candidate_details,
    )


def _workspace_preview_sample_texts(
    entries: list[tuple[str, list[str]]],
    *,
    limit: int = 100,
) -> list[str]:
    """从轻量索引正文提取有限预览样本，避免还原完整 TranslationData。"""
    samples: list[str] = []
    seen: set[str] = set()
    for _location_path, original_lines in entries:
        for text in original_lines:
            stripped_text = text.strip()
            if not stripped_text or stripped_text in seen:
                continue
            seen.add(stripped_text)
            samples.append(stripped_text)
            if len(samples) >= limit:
                return samples
    return samples


def _workspace_placeholder_preview_sample_texts(
    entries: list[tuple[str, list[str]]],
    *,
    text_rules: TextRules,
    limit: int = 100,
) -> list[str]:
    """从轻量索引正文提取普通占位符规则预览样本。"""
    custom_rules = text_rules.custom_placeholder_rules
    structured_rules = text_rules.structured_placeholder_rules

    def likely_placeholder_text(text: str) -> bool:
        return (
            "\\" in text
            or "<" in text
            or any(rule.pattern.search(text) is not None for rule in custom_rules)
            or any(rule.pattern.search(text) is not None for rule in structured_rules)
        )

    return _workspace_preview_sample_texts(
        [
            (
                location_path,
                [text for text in original_lines if likely_placeholder_text(text)],
            )
            for location_path, original_lines in entries
        ],
        limit=limit,
    )


def _workspace_structured_placeholder_preview_sample_texts(
    entries: list[tuple[str, list[str]]],
    *,
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    limit: int = 100,
) -> list[str]:
    """从轻量索引正文提取结构化占位符规则预览样本。"""

    def matches_structured_rule(text: str) -> bool:
        return any(rule.pattern.search(text) is not None for rule in structured_rules)

    return _workspace_preview_sample_texts(
        [
            (
                location_path,
                [text for text in original_lines if matches_structured_rule(text)],
            )
            for location_path, original_lines in entries
        ],
        limit=limit,
    )


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
            layout, plugins_js, plugin_source_files, plugin_source_read_errors = await load_plugin_source_files_for_view(
                session.game_path,
                source_view=resolved_view,
            )
            if resolved_view == GameFileView.TRANSLATION_SOURCE:
                snapshot_records = await session.read_source_snapshot_records()
                if not snapshot_records:
                    raise RuntimeError(SOURCE_SNAPSHOT_MISSING_MESSAGE)
                validate_plugin_source_snapshot_manifest(layout=layout, records=snapshot_records)
            text_rules = TextRules.from_setting(setting.text_rules)
        risk_report = _build_native_plugin_source_risk_report_from_inputs(
            plugins_js=plugins_js,
            plugin_source_files=plugin_source_files,
            plugin_source_read_errors=plugin_source_read_errors,
            text_rules=text_rules,
        )
        risk_report["source_view"] = resolved_view.value
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await _write_compact_json_value(output_path, risk_report)
        risk = ensure_json_object(risk_report["risk"], "plugin-source-risk-report.risk")
        candidate_count = _summary_int(risk_report, "candidate_count")
        warnings: list[AgentIssue] = []
        if candidate_count == 0:
            warnings.append(issue("plugin_source_text_empty", "没有扫描到插件源码硬编码文本候选"))
        warnings.extend(_plugin_source_native_scan_warnings(risk_report))
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "source_view": resolved_view.value,
                "candidate_count": candidate_count,
                "output": str(output_path),
                **risk,
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
            layout, plugins_js, plugin_source_files, plugin_source_read_errors = await load_plugin_source_files_for_view(
                session.game_path,
                source_view=resolved_view,
            )
            if resolved_view == GameFileView.TRANSLATION_SOURCE:
                snapshot_records = await session.read_source_snapshot_records()
                if not snapshot_records:
                    raise RuntimeError(SOURCE_SNAPSHOT_MISSING_MESSAGE)
                validate_plugin_source_snapshot_manifest(layout=layout, records=snapshot_records)
            text_rules = TextRules.from_setting(setting.text_rules)
        payload, details = _build_native_plugin_source_ast_map_payload_and_risk_report_from_inputs(
            plugins_js=plugins_js,
            plugin_source_files=plugin_source_files,
            plugin_source_read_errors=plugin_source_read_errors,
            text_rules=text_rules,
        )
        payload["source_view"] = resolved_view.value
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await _write_compact_json_value(output_path, payload)
        details["source_view"] = resolved_view.value
        details["output"] = str(output_path)
        risk = ensure_json_object(payload["risk"], "plugin-source-ast-map.risk")
        candidate_count = _summary_int(payload, "candidate_count")
        return AgentReport.from_parts(
            errors=[],
            warnings=_plugin_source_native_scan_warnings(details),
            summary={
                "source_view": resolved_view.value,
                "output": str(output_path),
                "candidate_count": candidate_count,
                **risk,
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
                include_plugin_source_files=True,
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
            plugin_source_scan = _build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
            plugin_source_risk_report = _native_plugin_source_risk_report_from_scan(plugin_source_scan)
            plugin_source_risk = ensure_json_object(
                plugin_source_risk_report["risk"],
                "plugin-source-risk-report.risk",
            )
            placeholder_entries, text_index_status = await _read_workspace_placeholder_entries_from_text_index(
                session=session,
                setting=setting,
                text_rules=text_rules,
            )
            text_index_metadata = await session.read_text_index_metadata()
            mv_virtual_namebox_review_required = game_data.layout.engine_kind == "mv"
            if text_index_metadata is not None:
                external_rule_gate_errors = await collect_text_index_external_rule_gate_errors(
                    session=session,
                    metadata=text_index_metadata,
                )
                mv_virtual_namebox_review_required = any(
                    error.code.startswith(MV_VIRTUAL_NAMEBOX_RULE_DOMAIN)
                    for error in external_rule_gate_errors
                )
            translation_scope_mode = "text_index"
            plugin_source_review = collect_plugin_source_review_coverage(
                scan=plugin_source_scan,
                rule_records=plugin_source_rules,
            )
            plugin_source_extension_active = (
                _json_bool(plugin_source_risk, "high_risk", "plugin-source-risk-report.risk")
                or bool(plugin_source_rules)
            )
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
        nonstandard_data_export_details: JsonObject | None = None
        if nonstandard_data_extension_active:
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
        configured_command_codes = (
            None
            if command_codes is not None
            else setting.event_command_text.default_codes_for_engine(game_data.layout.engine_kind)
        )
        effective_codes = resolve_event_command_codes(command_codes=command_codes, configured_command_codes=configured_command_codes)
        event_commands_path = target_dir / "event-commands.json"
        event_command_count = await export_event_commands_json_file(
            game_data=game_data,
            output_path=event_commands_path,
            command_codes=effective_codes,
        )
        event_rules_path = target_dir / "event-command-rules.json"
        await _write_json_object(event_rules_path, _event_command_rule_records_to_import_json(event_rules))
        placeholder_candidate_details = collect_native_placeholder_candidate_details_from_entries(
            entries=placeholder_entries,
            text_rules=text_rules,
        )
        placeholder_report = AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={},
            details={"candidates": placeholder_candidate_details},
        )
        placeholder_path = target_dir / "placeholder-candidates.json"
        await _write_compact_json_value(placeholder_path, placeholder_report.model_dump(mode="json"))
        placeholder_rule_drafts = _build_custom_placeholder_rule_draft_from_details(placeholder_candidate_details)
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
        mv_virtual_namebox_workspace_active = (
            game_data.layout.engine_kind == "mv"
            and mv_virtual_namebox_review_required
        )
        if mv_virtual_namebox_workspace_active:
            mv_virtual_namebox_candidates_path = target_dir / MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME
            mv_candidates_payload = native_mv_virtual_namebox_candidates_payload(game_data)
            mv_virtual_namebox_candidate_count = _summary_int(mv_candidates_payload, "candidate_count")
            await _write_compact_json_value(mv_virtual_namebox_candidates_path, mv_candidates_payload)
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
            "translation_scope_mode": translation_scope_mode,
            "text_index_status": text_index_status,
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
            "plugin_source_candidate_count": _summary_int(plugin_source_risk_report, "candidate_count"),
            "plugin_source_high_risk": _json_bool(
                plugin_source_risk,
                "high_risk",
                "plugin-source-risk-report.risk",
            ),
            "plugin_source_syntax_error_file_count": len(
                ensure_json_array(
                    plugin_source_risk_report["syntax_errors"],
                    "plugin-source-risk-report.syntax_errors",
                )
            ),
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
            "mv_virtual_namebox_workspace_active": mv_virtual_namebox_workspace_active,
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
        if nonstandard_data_export_details is not None:
            manifest_files.append(str(nonstandard_data_dir))
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
                include_mv_virtual_namebox_round=mv_virtual_namebox_workspace_active,
                terminology_subtask_summary=terminology_subtask_summary,
            ),
        }
        manifest_path = target_dir / "manifest.json"
        async with aiofiles.open(manifest_path, "w", encoding="utf-8") as file:
            _ = await file.write(f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n")
        details: JsonObject = {"manifest": manifest}
        if nonstandard_data_export_details is not None:
            details["nonstandard_data_export"] = nonstandard_data_export_details
        return AgentReport.from_parts(
            errors=[],
            warnings=[
                *_nonstandard_data_skipped_warnings(nonstandard_data_rules),
                *_plugin_source_native_scan_warnings(plugin_source_risk_report),
            ],
            summary={**generated_summary, "workspace": str(target_dir), "manifest": str(manifest_path)},
            details=details,
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
        mv_virtual_namebox_candidates_path = workspace / MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME
        mv_virtual_namebox_rules_path = workspace / MV_VIRTUAL_NAMEBOX_RULES_FILE_NAME
        placeholder_rules_path = workspace / "placeholder-rules.json"
        structured_placeholder_rules_path = workspace / STRUCTURED_PLACEHOLDER_RULES_FILE_NAME
        workspace_manifest, manifest_issue = await _read_workspace_manifest(workspace)
        if manifest_issue is not None:
            errors.append(manifest_issue)
        manifest_generated = _workspace_manifest_generated(workspace_manifest)
        _event_command_codes, event_command_codes_issue = _workspace_event_command_codes_from_manifest(workspace_manifest)
        if event_command_codes_issue is not None:
            errors.append(event_command_codes_issue)
        plugin_source_rules_in_manifest = _workspace_manifest_includes_path(
            workspace_manifest,
            plugin_source_rules_path,
        )
        nonstandard_data_rules_in_manifest = _workspace_manifest_includes_path(
            workspace_manifest,
            nonstandard_data_rules_path,
        )
        mv_virtual_namebox_rules_in_manifest = _workspace_manifest_includes_path(
            workspace_manifest,
            mv_virtual_namebox_rules_path,
        )
        advance_progress(1)
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            stored_plugin_source_rules = await session.read_plugin_source_text_rules()
            stored_nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
            plugin_source_scan_required = (
                plugin_source_rules_in_manifest
                or bool(stored_plugin_source_rules)
                or _manifest_bool(manifest_generated, "plugin_source_high_risk")
            )
            nonstandard_data_scan_required = (
                nonstandard_data_rules_in_manifest
                or bool(stored_nonstandard_data_rules)
                or _manifest_bool(manifest_generated, "nonstandard_data_high_risk")
            )
            set_status("加载翻译源视图")
            game_data = await self._load_translation_source_game_data(
                session,
                include_plugin_source_files=plugin_source_scan_required,
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
            plugin_source_scan: PluginSourceScan | None = None
            plugin_source_required = _manifest_bool(manifest_generated, "plugin_source_high_risk")
            if plugin_source_scan_required:
                set_status("扫描插件源码")
                plugin_source_scan = _build_native_plugin_source_scan(
                    game_data=game_data,
                    text_rules=text_rules,
                )
                plugin_source_required = plugin_source_scan.risk.high_risk
            set_status("读取文本范围索引")
            placeholder_entries, _text_index_status = await _read_workspace_placeholder_entries_from_text_index(
                session=session,
                setting=setting,
                text_rules=text_rules,
            )
            advance_progress(1)
            nonstandard_data_scan = None
            nonstandard_data_scan_error: Exception | None = None
            if nonstandard_data_scan_required:
                set_status("扫描非标准 data 文件")
                try:
                    nonstandard_data_scan = await build_nonstandard_data_scan(
                        layout=game_data.layout,
                        source_view=GameFileView.TRANSLATION_SOURCE,
                        text_rules=text_rules,
                    )
                except Exception as error:
                    nonstandard_data_scan_error = error
            advance_progress(1)
            set_status("读取已保存译文和支线状态")
            plugin_source_started = bool(stored_plugin_source_rules)
            nonstandard_data_started = bool(stored_nonstandard_data_rules)
            translated_paths = await session.read_translation_location_paths()
            empty_rule_issues = _workspace_empty_rule_warnings(game_data=game_data)
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
        if plugin_source_rules_in_manifest:
            if not plugin_source_rules_path.is_file():
                errors.append(issue("plugin_source_rules_missing", "工作区缺少 plugin-source-rules.json"))
            elif plugin_source_scan is None:
                raise RuntimeError("插件源码规则文件存在，但工作区验收没有执行插件源码扫描")
            else:
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
        elif nonstandard_data_rules_in_manifest:
            if not nonstandard_data_rules_path.is_file():
                errors.append(issue("nonstandard_data_rules_missing", "工作区缺少 nonstandard-data-rules.json"))
            elif nonstandard_data_scan is None:
                raise RuntimeError("非标准 data 规则文件存在，但工作区验收没有执行非标准 data 扫描")
            else:
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
        if game_data.layout.engine_kind == "mv" and mv_virtual_namebox_rules_in_manifest:
            if mv_virtual_namebox_rules_path.exists():
                async with aiofiles.open(mv_virtual_namebox_rules_path, "r", encoding="utf-8") as file:
                    mv_namebox_report = _validate_workspace_mv_virtual_namebox_rules(
                        rules_text=await file.read(),
                        game_data=game_data,
                        existing_records=mv_virtual_namebox_rule_records,
                        candidate_path=mv_virtual_namebox_candidates_path,
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
        workspace_custom_rules = text_rules.custom_placeholder_rules
        if placeholder_rules_path.exists():
            async with aiofiles.open(placeholder_rules_path, "r", encoding="utf-8") as file:
                placeholder_rules_text = await file.read()
                placeholder_report = _validate_workspace_placeholder_rules(
                    rules_text=placeholder_rules_text,
                    setting_text_rules=setting.text_rules,
                    structured_rules=text_rules.structured_placeholder_rules,
                    entries=placeholder_entries,
                )
            errors.extend(placeholder_report.errors)
            warnings.extend(placeholder_report.warnings)
            details["placeholder_rules"] = placeholder_report.details
            if _summary_int(placeholder_report.summary, "rule_count") == 0:
                placeholder_empty_issue = empty_rule_issues["placeholder_rules"]
                if placeholder_empty_issue is not None:
                    warnings.append(placeholder_empty_issue)
            try:
                workspace_custom_rules = load_custom_placeholder_rules_text(placeholder_rules_text)
                workspace_text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=workspace_custom_rules,
                    structured_placeholder_rules=text_rules.structured_placeholder_rules,
                )
                placeholder_coverage = _normal_placeholder_coverage_result_from_entries(
                    entries=placeholder_entries,
                    text_rules=workspace_text_rules,
                    rule_count=len(workspace_custom_rules),
                )
                if placeholder_coverage.uncovered_count:
                    warnings.append(
                        issue(
                            "placeholder_uncovered",
                            f"发现 {placeholder_coverage.uncovered_count} 个未覆盖的疑似自定义控制符",
                        )
                    )
                details["placeholder_coverage"] = _sampled_coverage_report_details(
                    placeholder_coverage,
                    summary_extra={"custom_rule_count": len(workspace_custom_rules)},
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
                    custom_rules=workspace_custom_rules,
                    entries=placeholder_entries,
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
                workspace_structured_rules = load_structured_placeholder_rules_text(structured_placeholder_rules_text)
                workspace_structured_text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=workspace_custom_rules,
                    structured_placeholder_rules=workspace_structured_rules,
                )
                structured_placeholder_coverage = _structured_placeholder_coverage_result_from_entries(
                    entries=placeholder_entries,
                    text_rules=workspace_structured_text_rules,
                    rule_count=len(workspace_structured_rules),
                )
                if structured_placeholder_coverage.uncovered_count:
                    warnings.append(
                        issue(
                            "structured_placeholder_uncovered",
                            f"发现 {structured_placeholder_coverage.uncovered_count} 个未被结构化规则覆盖的协议外壳候选",
                        )
                    )
                details["structured_placeholder_coverage"] = _sampled_coverage_report_details(
                    structured_placeholder_coverage,
                    summary_extra={"game": game_title},
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
        unlisted_paths = _collect_workspace_unlisted_paths(
            workspace=workspace,
            manifest_path=manifest_path,
            manifest_files=files_value,
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
        warnings: list[AgentIssue] = []
        details: JsonObject = {}
        if unlisted_paths:
            warnings.append(
                issue(
                    "workspace_unlisted_files_ignored",
                    f"发现 {len(unlisted_paths)} 个 manifest 外旧文件，旧文件不会参与本轮验收；"
                    + "请确认后手动删除或重新生成工作区",
                )
            )
            details["unlisted_files"] = [str(path) for path in unlisted_paths[:50]]
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "workspace": str(workspace),
                "deleted_count": deleted_count,
                "unlisted_file_count": len(unlisted_paths),
            },
            details=details,
        )


def _validate_workspace_mv_virtual_namebox_rules(
    *,
    rules_text: str,
    game_data: GameData,
    existing_records: list[MvVirtualNameboxRuleRecord],
    candidate_path: Path,
) -> AgentReport:
    """复用工作区候选文件校验 MV 虚拟名字框规则。"""
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    details: JsonObject = {"rules": [], "matched_candidates": []}
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
        if not candidate_path.exists():
            errors.append(issue("mv_virtual_namebox_candidates_missing", f"工作区缺少 {MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME}"))
            return AgentReport.from_parts(
                errors=errors,
                warnings=[],
                summary={
                    "rule_count": len(records),
                    "candidate_count": 0,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details=details,
            )
        payload = ensure_json_object(
            coerce_json_value(cast(object, json.loads(candidate_path.read_text(encoding="utf-8")))),
            MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME,
        )
        exported_scope_hash = payload.get("scope_hash")
        if not isinstance(exported_scope_hash, str) or not exported_scope_hash:
            errors.append(
                issue(
                    "mv_virtual_namebox_candidates_invalid",
                    f"{MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME} 缺少当前候选 scope_hash，请重新准备工作区",
                )
            )
            return AgentReport.from_parts(
                errors=errors,
                warnings=[],
                summary={
                    "rule_count": len(records),
                    "candidate_count": 0,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details=details,
            )
        exported_candidates = payload.get("candidates")
        exported_speaker_requirements = payload.get("speaker_requirements")
        if not isinstance(exported_candidates, list) or not isinstance(exported_speaker_requirements, list):
            errors.append(
                issue(
                    "mv_virtual_namebox_candidates_invalid",
                    f"{MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME} 缺少当前候选明细或说话人需求，请重新准备工作区",
                )
            )
            return AgentReport.from_parts(
                errors=errors,
                warnings=[],
                summary={
                    "rule_count": len(records),
                    "candidate_count": 0,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details=details,
            )
        candidate_scan = scan_native_mv_virtual_namebox(game_data=game_data)
        if exported_scope_hash != candidate_scan.scope_hash:
            errors.append(
                issue(
                    "mv_virtual_namebox_candidates_stale",
                    "MV 虚拟名字框候选文件已不是当前游戏内容，请重新准备工作区",
                )
            )
            return AgentReport.from_parts(
                errors=errors,
                warnings=[],
                summary={
                    "rule_count": len(records),
                    "candidate_count": candidate_scan.candidate_count,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details=details,
            )
        if (
            len(exported_candidates) != candidate_scan.candidate_count
            or len(exported_speaker_requirements) != len(candidate_scan.speaker_requirements)
        ):
            errors.append(
                issue(
                    "mv_virtual_namebox_candidates_invalid",
                    f"{MV_VIRTUAL_NAMEBOX_CANDIDATES_FILE_NAME} 内容与当前 native facts 不一致，请重新准备工作区",
                )
            )
            return AgentReport.from_parts(
                errors=errors,
                warnings=[],
                summary={
                    "rule_count": len(records),
                    "candidate_count": candidate_scan.candidate_count,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details=details,
            )
        if not records:
            warnings.append(issue("mv_virtual_namebox_rules_empty", "MV 虚拟名字框规则为空"))
            return AgentReport.from_parts(
                errors=[],
                warnings=warnings,
                summary={
                    "rule_count": 0,
                    "candidate_count": candidate_scan.candidate_count,
                    "matched_candidate_count": 0,
                    "newly_matched_candidate_count": 0,
                },
                details={
                    "rules": [],
                    "matched_candidates": [],
                    "newly_matched_candidates": [],
                    "candidate_count": candidate_scan.candidate_count,
                },
            )
        native_scan = scan_native_mv_virtual_namebox(
            game_data=game_data,
            records=records,
        )
        rule_errors = native_scan.rule_errors
        match_details = native_scan.match_details
        errors.extend(
            issue("mv_virtual_namebox_rules_invalid", _format_mv_namebox_rule_error(error_detail))
            for error_detail in rule_errors
        )
        existing_scan = scan_native_mv_virtual_namebox(
            game_data=game_data,
            records=existing_records,
        )
        existing_match_keys = _mv_namebox_match_keys(existing_scan.match_details)
        newly_matched_candidates: JsonArray = [
            detail
            for detail in match_details
            if _mv_namebox_match_key(detail) not in existing_match_keys
        ]
        candidate_count = native_scan.candidate_count
        matched_candidate_count = native_scan.matched_candidate_count
        if matched_candidate_count == 0 and candidate_count > 0:
            warnings.append(issue("mv_virtual_namebox_rules_no_hits", "MV 虚拟名字框规则没有命中任何候选"))
        details = {
            "rules": mv_virtual_namebox_rule_records_to_import_json(records)["rules"],
            "matched_candidates": match_details,
            "newly_matched_candidates": newly_matched_candidates,
            "candidate_count": candidate_count,
        }
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "rule_count": len(records),
                "candidate_count": candidate_count,
                "matched_candidate_count": matched_candidate_count,
                "newly_matched_candidate_count": len(newly_matched_candidates),
            },
            details=details,
        )
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


def _validate_workspace_placeholder_rules(
    *,
    rules_text: str,
    setting_text_rules: TextRulesSetting,
    structured_rules: tuple[StructuredPlaceholderRule, ...],
    entries: list[tuple[str, list[str]]],
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
    text_rules = TextRules.from_setting(
        setting_text_rules,
        custom_placeholder_rules=custom_rules,
        structured_placeholder_rules=structured_rules,
    )
    return _validate_placeholder_rules_with_context(
        source_label="--placeholder-rules",
        setting_text_rules=setting_text_rules,
        custom_rules=custom_rules,
        structured_rules=structured_rules,
        sample_texts=_workspace_placeholder_preview_sample_texts(entries, text_rules=text_rules),
        translation_data_map=None,
    )


def _validate_workspace_structured_placeholder_rules(
    *,
    game_title: str,
    rules_text: str,
    setting_text_rules: TextRulesSetting,
    custom_rules: tuple[CustomPlaceholderRule, ...],
    entries: list[tuple[str, list[str]]],
) -> AgentReport:
    """复用工作区上下文校验结构化占位符规则。"""
    try:
        structured_rules = load_structured_placeholder_rules_text(rules_text)
    except Exception:
        structured_rules = ()
    return _validate_structured_placeholder_rules_with_context(
        game_title=game_title,
        rules_text=rules_text,
        setting_text_rules=setting_text_rules,
        custom_rules=custom_rules,
        sample_texts=_workspace_structured_placeholder_preview_sample_texts(
            entries,
            structured_rules=structured_rules,
        ),
        translation_data_map=None,
    )


def _summary_int(summary: JsonObject, key: str) -> int:
    """从 Agent 报告摘要中读取整数计数字段。"""
    raw_value = summary.get(key)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise RuntimeError(f"报告缺少有效计数字段: {key}")
    return raw_value


def _workspace_empty_rule_warnings(*, game_data: GameData) -> dict[str, AgentIssue | None]:
    """工作区空规则文件只提示导入阶段需要确认，不读取数据库确认状态。"""
    warnings_by_file: dict[str, AgentIssue | None] = {
        "plugin_rules": issue("plugin_rules_empty_needs_import_confirmation", "插件规则为空；导入时需要传 --confirm-empty 确认当前范围无需插件规则"),
        "plugin_source_rules": issue("plugin_source_rules_empty_needs_import_confirmation", "插件源码规则为空；导入时需要传 --confirm-empty 或完成插件源码翻译/排除审查"),
        "event_command_rules": issue("event_command_rules_empty_needs_import_confirmation", "事件指令规则为空；导入时需要传 --confirm-empty 确认当前事件指令范围无需规则"),
        "note_tag_rules": issue("note_tag_rules_empty_needs_import_confirmation", "Note 标签规则为空；导入时需要传 --confirm-empty 确认当前 Note 候选无需规则"),
        "placeholder_rules": issue("placeholder_rules_empty_needs_import_confirmation", "普通占位符规则为空；导入时需要传 --confirm-empty 确认当前候选风险"),
        "structured_placeholder_rules": issue("structured_placeholder_rules_empty_needs_import_confirmation", "结构化占位符规则为空；导入时需要传 --confirm-empty 确认当前候选风险"),
    }
    warnings_by_file["mv_virtual_namebox_rules"] = (
        issue("mv_virtual_namebox_rules_empty_needs_import_confirmation", "MV 虚拟名字框规则为空；导入时需要传 --confirm-empty 确认当前候选无需规则")
        if game_data.layout.engine_kind == "mv"
        else None
    )
    return warnings_by_file


async def _read_workspace_manifest(workspace: Path) -> tuple[JsonObject | None, AgentIssue | None]:
    """读取工作区 manifest；缺失或损坏时返回单个错误。"""
    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        return None, issue("manifest_missing", "工作区缺少 manifest.json，无法确认工作区来源和事件指令编码")
    try:
        async with aiofiles.open(manifest_path, "r", encoding="utf-8") as file:
            raw_manifest = cast(object, json.loads(await file.read()))
        return ensure_json_object(coerce_json_value(raw_manifest), "manifest"), None
    except Exception as error:
        return None, issue("manifest_invalid", f"读取工作区 manifest 失败: {type(error).__name__}: {error}")


def _workspace_manifest_includes_path(manifest: JsonObject | None, path: Path) -> bool:
    """确认路径是否属于本轮 manifest 明确导出的工作区文件。"""
    if manifest is None:
        return False
    try:
        manifest_files = ensure_json_array(manifest.get("files"), "manifest.files")
        resolved_path = path.resolve()
        for raw_path in manifest_files:
            if not isinstance(raw_path, str):
                continue
            if Path(raw_path).resolve() == resolved_path:
                return True
    except Exception:
        return False
    return False


def _workspace_manifest_generated(manifest: JsonObject | None) -> JsonObject:
    """取出 manifest.generated；manifest 不可用时返回空对象。"""
    if manifest is None:
        return {}
    try:
        generated = ensure_json_object(manifest.get("generated"), "manifest.generated")
    except Exception:
        return {}
    return generated


def _collect_workspace_unlisted_paths(
    *,
    workspace: Path,
    manifest_path: Path,
    manifest_files: JsonArray,
) -> list[Path]:
    """列出 manifest.files 之外的工作区旧文件，供 cleanup 报告但不自动删除。"""
    workspace_root = workspace.resolve()
    manifest_resolved = manifest_path.resolve()
    listed_paths: list[Path] = []
    for raw_path in manifest_files:
        if not isinstance(raw_path, str):
            continue
        listed_path = Path(raw_path).resolve()
        if _is_path_inside(listed_path, workspace_root):
            listed_paths.append(listed_path)

    unlisted_paths: list[Path] = []
    for candidate in sorted(workspace.rglob("*"), key=lambda path: path.as_posix()):
        resolved_candidate = candidate.resolve()
        if resolved_candidate == manifest_resolved:
            continue
        if any(_path_matches_manifest_entry(resolved_candidate, listed_path) for listed_path in listed_paths):
            continue
        unlisted_paths.append(resolved_candidate)
    return unlisted_paths


def _path_matches_manifest_entry(path: Path, listed_path: Path) -> bool:
    """判断路径是否等于 manifest 条目，或属于 manifest 条目目录内部。"""
    if path == listed_path:
        return True
    return listed_path.is_dir() and _is_path_inside(path, listed_path)


def _workspace_event_command_codes_from_manifest(
    manifest: JsonObject | None,
) -> tuple[frozenset[int] | None, AgentIssue | None]:
    """从工作区 manifest 读取本轮事件指令候选编码。"""
    if manifest is None:
        return None, None
    try:
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
        return None, issue("manifest_invalid", f"读取工作区事件指令编码失败: {type(error).__name__}: {error}")


def _manifest_bool(generated: JsonObject, key: str) -> bool:
    """读取 manifest.generated 中的布尔开关，非法值按未启用处理。"""
    value = generated.get(key)
    return value is True
