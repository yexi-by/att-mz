"""Agent 工具箱 QualityAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

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
    TextScopeService,
    TranslationErrorItem,
    _build_coverage_report,
    _build_manual_translation_template_entry,
    _build_quality_error_category_counts,
    _build_quality_fix_categories_by_path,
    _build_translation_error_quality_detail,
    _collect_active_translation_location_paths,
    _collect_quality_fix_problem_paths,
    _count_active_quality_details,
    _count_protocol_sensitive_translation_items,
    _coverage_hard_stop_errors,
    _noop_quality_progress_callbacks,
    _read_reset_translation_location_paths,
    _resolve_quality_fix_translation_lines,
    _string_lines_to_json_array,
    _text_scope_blocking_errors,
    _validate_source_residual_rule_records,
    aiofiles,
    collect_agent_service_native_quality_details,
    collect_agent_service_native_write_protocol_details,
    issue,
    json,
    load_setting,
    native_thread_count,
)
from app.application.flow_gate import collect_workflow_gate_errors
from app.plugin_source_text import (
    ActiveRuntimePluginSourceAudit,
    PluginSourceFileTextScan,
    audit_active_runtime_plugin_source,
    build_plugin_source_file_hash,
    build_plugin_source_scan,
    collect_plugin_source_review_coverage,
    filter_fresh_plugin_source_text_rules,
    plugin_source_runtime_hash_lines,
    plugin_source_runtime_hash_text,
    scan_plugin_source_file_text,
)
from app.rmmz.schema import GameData, PluginSourceRuntimeWriteMapRecord, TranslationItem


def _active_runtime_audit_errors(audit: ActiveRuntimePluginSourceAudit) -> list[AgentIssue]:
    """把当前运行源码审计结果转换为质量报告错误。"""
    counts = audit.issue_counts
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


def _build_active_runtime_diagnosis_items(
    *,
    audit: ActiveRuntimePluginSourceAudit,
    runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord],
    translated_items: list[TranslationItem],
    translation_source_game_data: GameData,
    text_rules: TextRules,
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
    source_scan_cache: dict[str, PluginSourceFileTextScan] = {}
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
        if record is None:
            diagnosis.update(
                {
                    "diagnosis_status": "runtime_mapping_missing",
                    "suggested_action": "当前运行字符串没有可用写回映射，诊断无法反推到已保存译文；请回到规则、反馈文本或重新写回后的已保存译文定位流程处理",
                    "mapping_reason": "runtime_mapping_missing",
                }
            )
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
            text_rules=text_rules,
            source_scan_cache=source_scan_cache,
        )
        suggested_action = _suggested_action_for_write_map(
            cache_hash_matches=cache_hash_matches,
            source_hash_matches=source_hash_matches,
        )
        diagnosis["diagnosis_status"] = "mapped_translate"
        diagnosis["location_path"] = record.location_path
        diagnosis["source_file_name"] = record.source_file_name
        diagnosis["source_selector"] = record.source_selector
        diagnosis["runtime_file_name"] = record.runtime_file_name
        diagnosis["runtime_selector"] = record.runtime_selector
        diagnosis["runtime_line"] = record.runtime_line
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


def _suggested_action_for_write_map(
    *,
    cache_hash_matches: bool,
    source_hash_matches: bool,
) -> str:
    """按写回映射状态生成诊断建议。"""
    if not source_hash_matches:
        return "翻译源插件源码已变化；请重新导出并审查插件源码规则，重新写回后再处理对应已保存译文记录"
    if not cache_hash_matches:
        return "当前已保存译文记录已变化或不存在；请重新写回生成新的当前运行文件，或检查对应译文是否仍需要修复"
    return "请按文本在游戏里的内部位置（location_path）手修已保存译文记录，或重置对应译文后重新翻译，再重新写回"


def _plugin_source_write_map_source_matches(
    *,
    record: PluginSourceRuntimeWriteMapRecord,
    plugin_source_files: dict[str, str],
    text_rules: TextRules,
    source_scan_cache: dict[str, PluginSourceFileTextScan],
) -> tuple[bool, bool]:
    """校验写回映射指向的翻译源 selector 和原文是否仍然存在。"""
    source = plugin_source_files.get(record.source_file_name)
    if source is None:
        return False, False
    current_source_file_hash = build_plugin_source_file_hash(source)
    source_file_hash_matches = current_source_file_hash == record.source_file_hash
    source_scan = source_scan_cache.get(record.source_file_name)
    if source_scan is None or source_scan.file_hash != current_source_file_hash:
        source_scan = scan_plugin_source_file_text(
            source=source,
            file_name=record.source_file_name,
            active=True,
            text_rules=text_rules,
        )
        source_scan_cache[record.source_file_name] = source_scan
    candidate = source_scan.candidate_index.by_selector.get(record.source_selector)
    if candidate is None:
        return False, source_file_hash_matches
    return plugin_source_runtime_hash_text(candidate.text) == record.source_text_hash, source_file_hash_matches


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
        active_runtime_audit = audit_active_runtime_plugin_source(
            game_data=active_runtime_game_data,
            text_rules=text_rules,
        )
        errors = _active_runtime_audit_errors(active_runtime_audit)
        return AgentReport.from_parts(
            errors=errors,
            warnings=[],
            summary={
                "source_view": "active-runtime",
                **active_runtime_audit.summary_json(),
            },
            details={
                "source_view": "active-runtime",
                "active_runtime_plugin_source_items": active_runtime_audit.issues_json(),
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
        active_runtime_audit = audit_active_runtime_plugin_source(
            game_data=active_runtime_game_data,
            text_rules=text_rules,
        )
        diagnosis_items = _build_active_runtime_diagnosis_items(
            audit=active_runtime_audit,
            runtime_write_map_records=runtime_write_map_records,
            translated_items=translated_items,
            translation_source_game_data=translation_source_game_data,
            text_rules=text_rules,
        )
        reset_payload = _build_active_runtime_reset_payload(diagnosis_items)
        report = AgentReport.from_parts(
            errors=_active_runtime_audit_errors(active_runtime_audit),
            warnings=[],
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
    ) -> AgentReport:
        """从质量报告问题生成可填写的修复表。"""
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
            translated_items = await session.read_translated_items()
            scope = await TextScopeService().build(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
            )
            blocking_errors = _text_scope_blocking_errors(scope)
            active_items = {
                item.location_path: item
                for item in scope.active_items()
            }
            active_paths = scope.writable_paths
            translated_by_path = {item.location_path: item for item in translated_items}
            translated_paths = set(translated_by_path)
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

        if blocking_errors:
            return AgentReport.from_parts(
                errors=blocking_errors,
                warnings=[],
                summary={
                    "exported_count": 0,
                    "output": str(output_path),
                    "quality_error_items_count": 0,
                    "quality_error_category_counts": _build_quality_error_category_counts([]),
                    "quality_error_count": 0,
                    "source_residual_count": 0,
                    "text_structure_count": 0,
                    "placeholder_risk_count": 0,
                    "overwide_line_count": 0,
                    "write_back_protocol_count": 0,
                },
                details={
                    "coverage": {
                        "stale_plugin_rules": scope.stale_plugin_rules_json(),
                        "write_back_probe_error": scope.write_back_probe_error,
                        "unwritable_items": [entry.to_json_object() for entry in scope.unwritable_entries],
                    }
                },
            )
        pending_paths = active_paths - translated_paths
        quality_error_items = [
            item
            for item in quality_error_items
            if item.location_path in pending_paths
        ]
        source_residual_rule_errors = _validate_source_residual_rule_records(source_residual_rules)
        if source_residual_rule_errors:
            return AgentReport.from_parts(
                errors=source_residual_rule_errors,
                warnings=[],
                summary={
                    "exported_count": 0,
                    "output": str(output_path),
                    "quality_error_items_count": len(quality_error_items),
                    "quality_error_category_counts": _build_quality_error_category_counts(quality_error_items),
                    "quality_error_count": len(quality_error_items),
                    "source_residual_count": 0,
                    "text_structure_count": 0,
                    "placeholder_risk_count": 0,
                    "overwide_line_count": 0,
                    "write_back_protocol_count": 0,
                },
                details={},
            )
        native_quality_details = collect_agent_service_native_quality_details(
            items=active_translated_items,
            text_rules=text_rules,
            source_residual_rules=source_residual_rules,
        )
        residual_details = native_quality_details.source_residual_items
        text_structure_details = native_quality_details.text_structure_items
        placeholder_details = native_quality_details.placeholder_risk_items
        overwide_details = native_quality_details.overwide_line_items
        write_back_protocol_details = collect_agent_service_native_write_protocol_details(
            game_data=game_data.data,
            plugins_js=[plugin for plugin in game_data.plugins_js],
            items=active_translated_items,
        )
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

        warnings: list[AgentIssue] = []
        if not problem_paths:
            warnings.append(issue("quality_fix_empty", "当前没有可导出的质量修复条目"))
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
            },
            details={
                "location_paths": _string_lines_to_json_array(problem_paths),
                "problem_categories_by_path": categories_by_path,
            },
        )

    async def quality_report(
        self: AgentServiceContext,
        *,
        game_title: str,
        setting_overrides: SettingOverrides | None = None,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """生成目标游戏当前翻译状态和质量风险报告。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        set_progress(0, 1)
        set_status("加载游戏数据和规则")
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
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
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            game_data = await self._load_translation_source_game_data(session)
            plugin_rules, stale_plugin_rule_count = await self._read_fresh_plugin_text_rules(
                session=session,
                game_data=game_data,
            )
            event_rules = await session.read_event_command_text_rules()
            note_tag_rules = await session.read_note_tag_text_rules()
            source_residual_rules = await session.read_source_residual_rules()
            terminology_registry = await session.read_terminology_registry()
            plugin_source_records = await session.read_plugin_source_text_rules()
            plugin_source_scan = build_plugin_source_scan(game_data=game_data, text_rules=text_rules)
            fresh_plugin_source_records, _stale_plugin_source_records = filter_fresh_plugin_source_text_rules(
                game_data=game_data,
                rule_records=plugin_source_records,
                text_rules=text_rules,
                scan=plugin_source_scan,
            )
            plugin_source_review = collect_plugin_source_review_coverage(
                scan=plugin_source_scan,
                rule_records=fresh_plugin_source_records,
            )
            plugin_source_unreviewed_details: JsonArray = []
            for candidate in plugin_source_review.unreviewed_candidates[:100]:
                plugin_source_unreviewed_details.append(candidate.to_json_object())
            latest_run = await session.read_latest_translation_run()
            translated_items = await session.read_translated_items()
            scope = await TextScopeService().build(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
            )
            workflow_gate_errors = await collect_workflow_gate_errors(
                session=session,
                game_data=game_data,
                setting=setting,
                text_rules=text_rules,
                custom_placeholder_rules_supplied=False,
                translated_items=translated_items,
                scope=scope,
                plugin_source_scan=plugin_source_scan,
            )
            active_paths = scope.active_paths
            writable_paths = scope.writable_paths
            translated_paths = {item.location_path for item in translated_items}
            active_translated_items = [
                item
                for item in translated_items
                if item.location_path in active_paths
            ]
            pending_paths = writable_paths - translated_paths
            stale_paths = translated_paths - writable_paths
            stale_source_residual_rule_paths = {
                rule.location_path
                for rule in source_residual_rules
                if rule.rule_type == "position" and rule.location_path not in active_paths
            }
            coverage_report = _build_coverage_report(
                scope=scope,
                translated_items=translated_items,
                text_rules=text_rules,
            )
            if latest_run is None:
                quality_error_items: list[TranslationErrorItem] = []
                llm_failures: list[LlmFailureRecord] = []
            else:
                quality_error_items = await session.read_translation_quality_errors(latest_run.run_id)
                llm_failures = await session.read_llm_failures(latest_run.run_id)

        run_quality_error_count = len(quality_error_items)
        quality_error_items = [
            item
            for item in quality_error_items
            if item.location_path in pending_paths
        ]
        source_residual_rule_errors = _validate_source_residual_rule_records(source_residual_rules)
        filled_terminology_count = 0
        total_terminology_count = 0
        empty_terminology_count = 0
        if terminology_registry is not None:
            total_terminology_count = terminology_registry.total_entry_count()
            filled_terminology_count = terminology_registry.filled_entry_count()
            empty_terminology_count = total_terminology_count - filled_terminology_count

        workflow_gate_agent_errors = [
            issue(error.code, error.message)
            for error in workflow_gate_errors
        ]
        coverage_blocking_errors = _coverage_hard_stop_errors(coverage_report)
        if coverage_blocking_errors or source_residual_rule_errors:
            errors.extend(coverage_report.errors)
            warnings.extend(coverage_report.warnings)
            errors.extend(source_residual_rule_errors)
            errors.extend(workflow_gate_agent_errors)
            set_progress(1, 1)
            set_status("覆盖审计未通过，质量报告已停止")
            return AgentReport.from_parts(
                errors=errors,
                warnings=warnings,
                summary={
                    "extractable_count": len(active_paths),
                    "translated_count": len(translated_paths & active_paths),
                    "pending_count": len(pending_paths),
                    "stale_translation_count": len(stale_paths),
                    "unwritable_count": len(scope.unwritable_entries),
                    "plugin_rule_count": sum(len(rule.path_templates) for rule in plugin_rules),
                    "stale_plugin_rule_count": stale_plugin_rule_count,
                    "event_command_rule_count": sum(len(rule.path_templates) for rule in event_rules),
                    "note_tag_rule_count": sum(len(rule.tag_names) for rule in note_tag_rules),
                    "plugin_source_active_candidate_count": plugin_source_review.active_candidate_count,
                    "plugin_source_translate_selector_count": plugin_source_review.translate_selector_count,
                    "plugin_source_excluded_selector_count": plugin_source_review.excluded_selector_count,
                    "plugin_source_reviewed_selector_count": plugin_source_review.reviewed_selector_count,
                    "plugin_source_unreviewed_count": len(plugin_source_review.unreviewed_candidates),
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
                    "source_residual_count": 0,
                    "text_structure_count": 0,
                    "placeholder_risk_count": 0,
                    "overwide_line_count": 0,
                    "write_back_protocol_count": 0,
                    "writable_translation_count": len(translated_paths & writable_paths),
                },
                details={
                    "error_type_counts": dict(Counter(item.error_type for item in quality_error_items)),
                    "llm_failure_counts": dict(Counter(failure.category for failure in llm_failures)),
                    "quality_error_items": [_build_translation_error_quality_detail(item) for item in quality_error_items],
                    "source_residual_items": [],
                    "text_structure_items": [],
                    "placeholder_risk_items": [],
                    "overwide_line_items": [],
                    "write_back_protocol_items": [],
                    "plugin_source_unreviewed_candidates": plugin_source_unreviewed_details,
                    "coverage": coverage_report.details,
                },
            )

        protocol_probe_count = _count_protocol_sensitive_translation_items(
            items=active_translated_items,
            active_paths=active_paths,
        )
        total_progress_steps = max(
            8
            + len(active_translated_items) * 4
            + protocol_probe_count
            + len(quality_error_items),
            1,
        )
        set_progress(0, total_progress_steps)
        report_status = f"检查 {len(active_translated_items)} 条已保存译文，还没成功保存译文 {len(pending_paths)} 条"
        set_status(report_status)
        advance_progress(1)

        set_status("整理模型检查失败记录")
        for _item in quality_error_items:
            advance_progress(1)
        set_status(f"调用 Rust 原生质检核心（{native_thread_count()} 线程）")
        native_quality_details = collect_agent_service_native_quality_details(
            items=active_translated_items,
            text_rules=text_rules,
            source_residual_rules=source_residual_rules,
        )
        residual_items = native_quality_details.source_residual_items
        text_structure_items = native_quality_details.text_structure_items
        placeholder_risk_items = native_quality_details.placeholder_risk_items
        overwide_line_items = native_quality_details.overwide_line_items
        advance_progress(len(active_translated_items) * 4)
        set_status("整理源文残留")
        residual_count = len(residual_items)
        set_status("检查写回协议")
        if scope.write_back_probe_error:
            write_back_protocol_items: JsonArray = []
        else:
            write_back_protocol_items = collect_agent_service_native_write_protocol_details(
                game_data=game_data.data,
                plugins_js=[plugin for plugin in game_data.plugins_js],
                items=active_translated_items,
            )
        advance_progress(protocol_probe_count)
        set_status("整理质量报告")
        advance_progress(1)
        error_type_counts = Counter(item.error_type for item in quality_error_items)
        quality_error_details: JsonArray = []
        for item in quality_error_items:
            quality_error_details.append(_build_translation_error_quality_detail(item))
        model_response_count = sum(
            1
            for item in quality_error_items
            if item.model_response.strip()
        )
        llm_failure_counts = Counter(failure.category for failure in llm_failures)
        advance_progress(1)
        errors.extend(coverage_report.errors)
        errors.extend(workflow_gate_agent_errors)
        warnings.extend(coverage_report.warnings)
        if llm_failures and pending_paths:
            errors.append(issue("llm_failures", f"最新翻译运行存在 {len(llm_failures)} 条模型运行故障"))
        elif llm_failures:
            warnings.append(issue("historical_llm_failures", f"最新翻译运行记录过 {len(llm_failures)} 条模型故障，但当前没有正文因此无法继续"))
        if quality_error_items:
            errors.append(issue("translation_quality_errors", f"最新翻译运行有 {len(quality_error_items)} 条模型翻了但项目检查没通过的译文"))
        if placeholder_risk_items:
            errors.append(issue("placeholder_risk", f"发现 {len(placeholder_risk_items)} 条译文里的游戏控制符可能被改坏"))
        if residual_count:
            errors.append(issue("source_residual", f"发现 {residual_count} 条译文存在{setting.text_rules.source_residual_label}残留风险"))
        if text_structure_items:
            errors.append(issue("text_structure", f"发现 {len(text_structure_items)} 条译文改动了游戏文本结构"))
        if overwide_line_items:
            errors.append(issue("overwide_line", f"发现 {len(overwide_line_items)} 行译文超过当前长文本宽度上限"))
        if write_back_protocol_items:
            errors.append(issue("write_back_protocol", f"发现 {len(write_back_protocol_items)} 条译文写回后会破坏游戏或插件解析协议"))
        if terminology_registry is None:
            errors.append(issue("terminology_missing", "当前游戏尚未导入字段译名表"))
        elif empty_terminology_count:
            errors.append(issue("terminology_empty_translation", f"字段译名表还有 {empty_terminology_count} 个词条没有填写译名"))
        if stale_source_residual_rule_paths:
            errors.append(issue("stale_source_residual_rules", f"发现 {len(stale_source_residual_rule_paths)} 条不在当前提取范围内的源文残留例外规则"))

        set_progress(total_progress_steps, total_progress_steps)
        set_status("质量报告已完成")
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "extractable_count": len(active_paths),
                "translated_count": len(translated_paths & active_paths),
                "pending_count": len(pending_paths),
                "stale_translation_count": len(stale_paths),
                "unwritable_count": len(scope.unwritable_entries),
                "plugin_rule_count": sum(len(rule.path_templates) for rule in plugin_rules),
                "stale_plugin_rule_count": stale_plugin_rule_count,
                "event_command_rule_count": sum(len(rule.path_templates) for rule in event_rules),
                "note_tag_rule_count": sum(len(rule.tag_names) for rule in note_tag_rules),
                "plugin_source_active_candidate_count": plugin_source_review.active_candidate_count,
                "plugin_source_translate_selector_count": plugin_source_review.translate_selector_count,
                "plugin_source_excluded_selector_count": plugin_source_review.excluded_selector_count,
                "plugin_source_reviewed_selector_count": plugin_source_review.reviewed_selector_count,
                "plugin_source_unreviewed_count": len(plugin_source_review.unreviewed_candidates),
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
                "model_response_error_count": model_response_count,
                "source_residual_count": residual_count,
                "text_structure_count": len(text_structure_items),
                "placeholder_risk_count": len(placeholder_risk_items),
                "overwide_line_count": len(overwide_line_items),
                "write_back_protocol_count": len(write_back_protocol_items),
                "writable_translation_count": len(translated_paths & writable_paths),
            },
            details={
                "error_type_counts": dict(error_type_counts),
                "llm_failure_counts": dict(llm_failure_counts),
                "quality_error_items": quality_error_details,
                "source_residual_items": residual_items,
                "text_structure_items": text_structure_items,
                "placeholder_risk_items": placeholder_risk_items,
                "overwide_line_items": overwide_line_items,
                "write_back_protocol_items": write_back_protocol_items,
                "plugin_source_unreviewed_candidates": plugin_source_unreviewed_details,
                "coverage": coverage_report.details,
            },
        )

    async def translation_status(self: AgentServiceContext, *, game_title: str) -> AgentReport:
        """读取最新正文翻译运行状态，并补充当前还没成功保存译文的数量。"""
        async with await self.game_registry.open_game(game_title) as session:
            latest_run = await session.read_latest_translation_run()
            if latest_run is None:
                return AgentReport.from_parts(
                    errors=[],
                    warnings=[issue("translation_run_missing", "当前游戏尚未产生正文翻译运行记录")],
                    summary={},
                    details={},
                )
            setting = load_setting(self.setting_path, source_language=session.source_language)
            llm_failures = await session.read_llm_failures(latest_run.run_id)
            quality_errors = await session.read_translation_quality_errors(latest_run.run_id)
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
            active_paths = {
                item.location_path
                for translation_data in translation_data_map.values()
                for item in translation_data.translation_items
            }
            translated_paths = await session.read_translation_location_paths()
            current_pending_paths = active_paths - translated_paths
            run_quality_error_count = len(quality_errors)
            quality_errors = [
                error for error in quality_errors if error.location_path in current_pending_paths
            ]
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "run_id": latest_run.run_id,
                "status": latest_run.status,
                "total_extracted": latest_run.total_extracted,
                "pending_count": len(current_pending_paths),
                "run_pending_count": latest_run.pending_count,
                "translated_count": len(translated_paths & active_paths),
                "extractable_count": len(active_paths),
                "deduplicated_count": latest_run.deduplicated_count,
                "batch_count": latest_run.batch_count,
                "success_count": latest_run.success_count,
                "quality_error_count": len(quality_errors),
                "run_quality_error_count": run_quality_error_count,
                "llm_failure_count": len(llm_failures),
                "stop_reason": latest_run.stop_reason,
                "last_error": latest_run.last_error,
            },
            details={
                "llm_failure_counts": dict(Counter(failure.category for failure in llm_failures)),
                "quality_error_counts": dict(Counter(error.error_type for error in quality_errors)),
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
            },
            details=details,
        )
