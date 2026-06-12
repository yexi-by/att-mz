"""Agent 工具箱 ManualTranslationAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from dataclasses import dataclass

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonArray,
    JsonObject,
    Path,
    QualityProgressCallbacks,
    TextRules,
    TranslationItem,
    _build_manual_translation_template_entry,
    _build_translation_line_break_count_detail,
    _prepare_manual_translation_item,
    aiofiles,
    cast,
    coerce_json_value,
    current_timestamp_text,
    ensure_json_object,
    issue,
    json,
    load_setting,
    _noop_quality_progress_callbacks,
    write_back_probe_report_fields,
)
from app.external_input import normalize_external_str, normalize_external_str_list
from app.text_index import (
    collect_text_index_scope_gate_errors,
    detect_text_index_invalidations,
)
from app.text_facts import (
    count_pending_text_facts,
    read_pending_text_fact_records,
    read_writable_text_fact_translation_items_by_fact_ids,
    read_writable_text_fact_translation_items_by_paths,
    text_fact_record_to_translation_item,
)


@dataclass(slots=True)
class ManualTranslationImportPlan:
    """手动译文导入计划，构建阶段不写数据库。"""

    valid_items: list[TranslationItem]
    invalid_items: JsonArray
    errors: list[AgentIssue]


class ManualTranslationAgentMixin:
    """承载 AgentToolkitService 的 ManualTranslationAgentMixin 命令族。"""

    async def export_pending_translations(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
        limit: int | None,
        include_write_probe: bool = False,
        callbacks: QualityProgressCallbacks | None = None,
    ) -> AgentReport:
        """导出还没成功保存译文的条目，供 Agent 手动填写译文。"""
        set_progress, advance_progress, set_status = callbacks or _noop_quality_progress_callbacks()
        set_progress(0, 5)
        set_status("加载配置和规则")
        text_index_status = ""
        text_index_rebuild_summary: JsonObject = {}
        text_index_invalidation_details: JsonArray = []
        rebuild_warnings: list[AgentIssue] = []

        def export_summary(*, pending_exported_count: int, pending_total_count: int | None = None) -> JsonObject:
            summary: JsonObject = {
                "pending_exported_count": pending_exported_count,
                "output": str(output_path),
                **write_back_probe_report_fields(
                    requested=include_write_probe,
                    executed=False,
                    mode="index_writable" if include_write_probe else "disabled",
                ),
                "text_index_status": text_index_status,
            }
            if pending_total_count is not None:
                summary["pending_total_count"] = pending_total_count
            if text_index_rebuild_summary:
                summary["text_index_rebuild_summary"] = text_index_rebuild_summary
            return summary

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
            advance_progress(1)
            set_status("检查持久文本范围索引")
            index_invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=text_rules,
            )
            if index_invalidations:
                text_index_invalidation_details = [
                    {
                        "reason_key": item.reason_key,
                        "detail": item.detail,
                        "created_at": item.created_at,
                    }
                    for item in index_invalidations
                ]
                text_index_status = (
                    "cold_rebuilt"
                    if any(item.reason_key == "text_index_missing" for item in index_invalidations)
                    else "stale_rebuilt"
                )
                rebuild_report = await self.rebuild_text_index(
                    game_title=game_title,
                    include_write_probe=include_write_probe,
                )
                text_index_rebuild_summary = dict(rebuild_report.summary)
                if rebuild_report.status == "error":
                    text_index_status = "rebuild_failed"
                    set_progress(5, 5)
                    set_status("文本范围索引重建失败，停止导出手动填写译文表")
                    return AgentReport.from_parts(
                        errors=rebuild_report.errors,
                        warnings=rebuild_report.warnings,
                        summary=export_summary(pending_exported_count=0),
                        details={
                            "text_index_invalidations": text_index_invalidation_details,
                            "text_index_rebuild": rebuild_report.details,
                        },
                    )
                rebuild_warnings.extend(rebuild_report.warnings)
            else:
                text_index_status = "used"
            advance_progress(1)

            scope_gate_errors = await collect_text_index_scope_gate_errors(session=session)
            if scope_gate_errors:
                report_errors = [
                    issue(error.code, error.message)
                    for error in scope_gate_errors
                ]
                set_progress(5, 5)
                set_status("当前文本范围检查没通过，停止导出手动填写译文表")
                return AgentReport.from_parts(
                    errors=report_errors,
                    warnings=rebuild_warnings,
                    summary=export_summary(pending_exported_count=0),
                    details={
                        "text_index_invalidations": text_index_invalidation_details,
                        "text_index_scope_gate_errors": [
                            {"code": error.code, "message": error.message}
                            for error in scope_gate_errors
                        ],
                    },
                )

            set_status("读取还没成功保存译文的索引条目")
            pending_total_count = await count_pending_text_facts(session)
            if limit is not None and limit <= 0:
                pending_fact_entries: list[tuple[str, TranslationItem]] = []
            else:
                pending_facts = await read_pending_text_fact_records(session, limit=limit)
                index_records = await session.read_text_index_items_by_paths(
                    sorted({fact.location_path for fact in pending_facts})
                )
                index_by_path = {record.location_path: record for record in index_records}
                pending_fact_entries = [
                    (
                        fact.fact_id,
                        text_fact_record_to_translation_item(
                            fact,
                            index_record=index_by_path.get(fact.location_path),
                        ),
                    )
                    for fact in pending_facts
                ]
            advance_progress(1)

        set_status("写出手动填写译文表")
        payload: JsonObject = {}
        for fact_id, item in pending_fact_entries:
            entry = _build_manual_translation_template_entry(
                item=item,
                text_rules=text_rules,
                translation_lines=[],
            )
            entry["fact_id"] = fact_id
            payload[item.location_path] = entry

        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
            _ = await file.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
        advance_progress(1)

        warnings: list[AgentIssue] = []
        if not pending_fact_entries:
            warnings.append(issue("pending_empty", "当前没有需要手动填写译文的条目"))
        set_progress(5, 5)
        set_status("手动填写译文表已完成")
        return AgentReport.from_parts(
            errors=[],
            warnings=[*rebuild_warnings, *warnings],
            summary=export_summary(
                pending_exported_count=len(pending_fact_entries),
                pending_total_count=pending_total_count,
            ),
            details={"text_index_invalidations": text_index_invalidation_details},
        )

    async def import_manual_translations(
        self: AgentServiceContext,
        *,
        game_title: str,
        input_path: Path,
        import_valid: bool = False,
        check_only: bool = False,
        report_invalid_path: Path | None = None,
    ) -> AgentReport:
        """导入 Agent 手动填写的译文，并按项目规则校验后保存。"""
        try:
            async with aiofiles.open(input_path, "r", encoding="utf-8-sig") as file:
                raw_payload = cast(object, json.loads(await file.read()))
            payload = ensure_json_object(coerce_json_value(raw_payload), "manual-translations")
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("manual_translation_file", f"手动填写译文表不可读: {type(error).__name__}: {error}")],
                warnings=[],
                summary={"input": str(input_path), "imported_count": 0},
                details={},
            )

        errors: list[AgentIssue] = []
        invalid_items: JsonArray = []
        valid_items: list[TranslationItem] = []
        scope_mode = "text_index"
        text_index_status = ""
        text_index_rebuild_summary: JsonObject = {}
        rebuild_warnings: list[AgentIssue] = []

        def import_summary(
            *,
            imported_count: int,
            error_count: int | None = None,
            invalid_count: int | None = None,
            invalid_report_path: Path | None = None,
        ) -> JsonObject:
            summary: JsonObject = {
                "input": str(input_path),
                "imported_count": imported_count,
                "would_import_count": imported_count if check_only else 0,
                "mode": "check_only" if check_only else "import",
                "scope_mode": scope_mode,
                "import_valid": import_valid,
            }
            if check_only:
                summary["imported_count"] = 0
            if error_count is not None:
                summary["error_count"] = error_count
            if invalid_count is not None:
                summary["invalid_count"] = invalid_count
            if invalid_report_path is not None:
                summary["invalid_report"] = str(invalid_report_path)
            if scope_mode == "text_index":
                summary["text_index_status"] = text_index_status
                if text_index_rebuild_summary:
                    summary["text_index_rebuild_summary"] = text_index_rebuild_summary
            return summary

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
            payload_paths = {str(location_path) for location_path in payload}
            payload_fact_ids: dict[str, str] = {}
            for location_path, raw_entry in payload.items():
                if not isinstance(raw_entry, dict):
                    continue
                raw_fact_id = raw_entry.get("fact_id")
                if raw_fact_id is None:
                    continue
                try:
                    fact_id = normalize_external_str(raw_fact_id, f"{location_path}.fact_id").strip()
                except Exception:
                    continue
                if fact_id:
                    payload_fact_ids[str(location_path)] = fact_id
            if payload_fact_ids:
                scope_mode = "current_text_fact"
            requires_text_index = any(path not in payload_fact_ids for path in payload_paths)
            latest_run = await session.read_latest_translation_run()
            if requires_text_index:
                index_invalidations = await detect_text_index_invalidations(
                    session=session,
                    text_rules=text_rules,
                )
                if index_invalidations:
                    invalidation_details: JsonArray = [
                        {
                            "reason_key": item.reason_key,
                            "detail": item.detail,
                            "created_at": item.created_at,
                        }
                        for item in index_invalidations
                    ]
                    text_index_status = (
                        "cold_rebuilt"
                        if any(item.reason_key == "text_index_missing" for item in index_invalidations)
                        else "stale_rebuilt"
                    )
                    rebuild_report = await self.rebuild_text_index(game_title=game_title)
                    text_index_rebuild_summary = dict(rebuild_report.summary)
                    if rebuild_report.status == "error":
                        text_index_status = "rebuild_failed"
                        return AgentReport.from_parts(
                            errors=rebuild_report.errors,
                            warnings=rebuild_report.warnings,
                            summary=import_summary(imported_count=0, error_count=len(rebuild_report.errors)),
                            details={
                                "text_index_invalidations": invalidation_details,
                                "text_index_rebuild": rebuild_report.details,
                            },
                        )
                    rebuild_warnings.extend(rebuild_report.warnings)
                else:
                    text_index_status = "used"
            active_item_records: list[TranslationItem] = []
            if requires_text_index:
                active_item_records = await read_writable_text_fact_translation_items_by_paths(
                    session,
                    sorted(path for path in payload_paths if path not in payload_fact_ids),
                )
            active_items = {item.location_path: item for item in active_item_records}
            active_items_by_fact_id: dict[str, TranslationItem] = {}
            if payload_fact_ids:
                requested_fact_ids = set(payload_fact_ids.values())
                active_items_by_fact_id = await read_writable_text_fact_translation_items_by_fact_ids(
                    session,
                    sorted(requested_fact_ids),
                )
            source_residual_rules = await session.read_source_residual_rules()

            for location_path, raw_entry in payload.items():
                if not isinstance(raw_entry, dict):
                    message = f"{location_path} 必须是 JSON 对象"
                    errors.append(issue("manual_translation_entry", message))
                    invalid_items.append({"location_path": location_path, "message": message})
                    continue
                entry = ensure_json_object(raw_entry, f"{location_path}")
                raw_fact_id = entry.get("fact_id")
                fact_id = ""
                if raw_fact_id is not None:
                    try:
                        fact_id = normalize_external_str(raw_fact_id, f"{location_path}.fact_id").strip()
                    except Exception as error:
                        error_message = f"{type(error).__name__}: {error}"
                        invalid_items.append({"location_path": location_path, "message": error_message})
                        errors.append(
                            issue(
                                "manual_translation_invalid",
                                f"{location_path} 手动填写译文不可用: {error_message}",
                            )
                        )
                        continue
                item = active_items_by_fact_id.get(fact_id) if fact_id else active_items.get(location_path)
                if item is None:
                    if fact_id:
                        message = (
                            f"{location_path} 的 fact_id 不属于当前可写 当前文本事实；"
                            "请重新导出 pending translations 后再填写导入"
                        )
                    else:
                        message = (
                            f"{location_path} 不在当前可写 当前文本事实范围内；"
                            "请重新导出 pending translations 后再填写导入"
                        )
                    errors.append(issue("manual_translation_location", message))
                    invalid_items.append({"location_path": location_path, "message": message})
                    continue
                resolved_location_path = item.location_path
                translation_lines: list[str] | None = None
                try:
                    raw_lines_value = entry.get("translation_lines")
                    if raw_lines_value is None:
                        raise TypeError(f"{resolved_location_path}.translation_lines 必须是字符串数组")
                    translation_lines = normalize_external_str_list(
                        raw_lines_value,
                        f"{resolved_location_path}.translation_lines",
                    )
                    cloned_item = _prepare_manual_translation_item(
                        item=item,
                        translation_lines=translation_lines,
                        text_rules=text_rules,
                        source_residual_rules=source_residual_rules,
                    )
                    valid_items.append(cloned_item)
                except Exception as error:
                    error_message = f"{type(error).__name__}: {error}"
                    invalid_detail: JsonObject = {
                        "location_path": resolved_location_path,
                        "message": error_message,
                    }
                    if translation_lines is not None:
                        try:
                            invalid_detail.update(
                                _build_translation_line_break_count_detail(
                                    item=item,
                                    translation_lines=translation_lines,
                                    text_rules=text_rules,
                                )
                            )
                        except Exception as detail_error:
                            invalid_detail["line_break_detail_error"] = f"{type(detail_error).__name__}: {detail_error}"
                    invalid_items.append(invalid_detail)
                    errors.append(
                        issue(
                            "manual_translation_invalid",
                            f"{resolved_location_path} 手动填写译文不可用: {error_message}",
                        )
                    )

            plan = ManualTranslationImportPlan(
                valid_items=valid_items,
                invalid_items=invalid_items,
                errors=errors,
            )
            if check_only:
                if plan.errors:
                    return AgentReport.from_parts(
                        errors=plan.errors,
                        warnings=rebuild_warnings,
                        summary=import_summary(
                            imported_count=len(plan.valid_items),
                            error_count=len(plan.errors),
                            invalid_count=len(plan.invalid_items),
                        ),
                        details={"invalid_items": plan.invalid_items},
                    )
                return AgentReport.from_parts(
                    errors=[],
                    warnings=(
                        rebuild_warnings
                        if plan.valid_items
                        else [*rebuild_warnings, issue("manual_translation_empty", "手动填写译文表没有可导入条目")]
                    ),
                    summary=import_summary(imported_count=len(plan.valid_items)),
                    details={},
                )

            if plan.errors and not import_valid:
                return AgentReport.from_parts(
                    errors=plan.errors,
                    warnings=rebuild_warnings,
                    summary=import_summary(
                        imported_count=0,
                        error_count=len(plan.errors),
                        invalid_count=len(plan.invalid_items),
                    ),
                    details={"invalid_items": plan.invalid_items},
                )

            if plan.errors and report_invalid_path is None:
                return AgentReport.from_parts(
                    errors=[
                        issue(
                            "manual_translation_invalid_report_required",
                            "手动填写译文表包含无效条目；若要保存有效条目，必须同时提供 --report-invalid 写出无效项报告",
                        )
                    ],
                    warnings=rebuild_warnings,
                    summary=import_summary(
                        imported_count=0,
                        error_count=len(plan.errors),
                        invalid_count=len(plan.invalid_items),
                    ),
                    details={"invalid_items": plan.invalid_items},
                )

            if plan.errors and report_invalid_path is not None:
                await _write_manual_translation_invalid_report(
                    input_path=input_path,
                    output_path=report_invalid_path,
                    imported_count=len(plan.valid_items),
                    invalid_items=plan.invalid_items,
                    errors=plan.errors,
                )

            await session.write_translation_items(plan.valid_items)
            imported_fact_ids = {item.fact_id for item in plan.valid_items if item.fact_id}
            _ = await session.delete_translation_quality_errors_by_fact_ids(imported_fact_ids)
            if latest_run is not None:
                remaining_quality_error_count = await session.count_translation_quality_errors(latest_run.run_id)
                llm_failures = await session.read_llm_failures(latest_run.run_id)
                has_pending_items = await count_pending_text_facts(session) > 0
                if not has_pending_items and remaining_quality_error_count == 0 and not llm_failures:
                    await session.write_translation_run(
                        latest_run.model_copy(
                            update={
                                "status": "completed",
                                "quality_error_count": 0,
                                "llm_failure_count": 0,
                                "finished_at": current_timestamp_text(),
                                "stop_reason": "",
                                "last_error": "",
                            }
                        )
                    )

        if errors:
            warnings = [
                *rebuild_warnings,
                issue(
                    "manual_translation_partial_import",
                    f"已保存 {len(valid_items)} 条有效译文，另有 {len(invalid_items)} 条无效条目未保存；无效项报告已写出",
                ),
            ]
            return AgentReport.from_parts(
                errors=[],
                warnings=warnings,
                summary=import_summary(
                    imported_count=len(valid_items),
                    error_count=len(errors),
                    invalid_count=len(invalid_items),
                    invalid_report_path=report_invalid_path,
                ),
                details={"invalid_items": invalid_items},
            )

        return AgentReport.from_parts(
            errors=[],
            warnings=(
                rebuild_warnings
                if valid_items
                else [*rebuild_warnings, issue("manual_translation_empty", "手动填写译文表没有可导入条目")]
            ),
            summary=import_summary(imported_count=len(valid_items)),
            details={},
        )


async def _write_manual_translation_invalid_report(
    *,
    input_path: Path,
    output_path: Path,
    imported_count: int,
    invalid_items: JsonArray,
    errors: list[AgentIssue],
) -> None:
    """写出手动导入无效项报告。"""
    report = AgentReport.from_parts(
        errors=errors,
        warnings=[],
        summary={
            "input": str(input_path),
            "imported_count": imported_count,
            "invalid_count": len(invalid_items),
        },
        details={"invalid_items": invalid_items},
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
        _ = await file.write(f"{report.to_json_text()}\n")
