"""Agent 工具箱 PlaceholderRuleAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentReport,
    AgentServiceContext,
    Path,
    Sequence,
    TextRules,
    _build_custom_placeholder_rule_draft_from_details,
    _build_joined_text_boundary_warnings,
    _build_placeholder_coverage_report_with_context,
    _build_structured_placeholder_coverage_report_with_context,
    _build_unprotected_control_warnings,
    _joined_text_boundary_markers_from_details,
    _validate_placeholder_rules_with_context,
    _validate_structured_placeholder_rules_with_context,
    aiofiles,
    build_rule_runtime_settings_patterns,
    issue,
    json,
    load_custom_placeholder_rules_import_payload,
    load_custom_placeholder_rules_import_text,
    load_custom_placeholder_rules_text,
    load_structured_placeholder_rules_import_payload,
    load_structured_placeholder_rules_import_text,
    load_setting,
)
from app.application.flow_gate import (
    build_normal_placeholder_coverage_result,
    build_structured_placeholder_coverage_result,
    ensure_empty_rule_confirmed,
)
from app.native_rule_runtime import (
    RuleImportCommitResult,
    RuleImportPrepareResult,
    RuleRuntimeIssue,
    prepare_rule_import,
)
from app.agent_toolkit.services.rule_import_runtime import (
    cleanup_input_from_stale_items,
    commit_deleted_translation_count,
    commit_prepared_rule_import,
    write_prepared_cleanup_backup,
)
from app.agent_toolkit.reports import AgentIssue
from app.native_placeholder_scan import (
    collect_native_placeholder_candidate_details_from_entries,
    count_uncovered_placeholder_candidate_details,
)
from app.config.schemas import Setting, TextRulesSetting
from app.persistence import TargetGameSession
from app.rmmz.control_codes import CustomPlaceholderRule, StructuredPlaceholderRule
from app.rmmz.json_types import JsonArray, JsonObject, JsonValue
from app.rmmz.schema import (
    PlaceholderRuleRecord,
    StructuredPlaceholderRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rule_review_decision import RuleCoverageResult
from app.text_index import (
    collect_text_index_external_rule_gate_errors,
    detect_text_index_invalidations,
    rebuild_text_index_native_storage,
)
from app.text_facts import (
    read_current_text_fact_placeholder_entries,
    read_current_text_fact_translation_data_map,
)


async def _ensure_current_text_facts_for_placeholder_rules(
    *,
    session: TargetGameSession,
    setting: Setting,
    text_rules: TextRules,
) -> None:
    """确保当前 DB 已有与规则上下文一致的 current text facts。"""
    invalidations = await detect_text_index_invalidations(
        session=session,
        text_rules=text_rules,
    )
    if invalidations:
        _ = await rebuild_text_index_native_storage(
            session=session,
            setting=setting,
            text_rules=text_rules,
            include_write_probe=False,
        )


async def _load_placeholder_rule_runtime_payload(
    *,
    session: TargetGameSession,
    rules_text: str | None,
) -> JsonObject:
    """读取普通占位符 rule_runtime 原始载荷。"""
    if rules_text is not None:
        return load_custom_placeholder_rules_import_payload(rules_text)
    records = await session.read_placeholder_rules()
    return {record.pattern_text: record.placeholder_template for record in records}


def _placeholder_rule_runtime_payload(
    *,
    mode: str,
    domain: str,
    rules_payload: JsonObject,
    setting: Setting,
    db_path: Path | None,
    confirm_empty: bool = False,
    game_context: JsonObject | None = None,
) -> JsonObject:
    """构造普通占位符规则运行时载荷。"""
    payload: JsonObject = {
        "mode": mode,
        "domain": domain,
        "rules_payload": rules_payload,
        "game_context": game_context or {},
        "settings_runtime_patterns": build_rule_runtime_settings_patterns(setting),
        "confirm_empty": confirm_empty,
    }
    if db_path is not None:
        payload["db_path"] = str(db_path)
    return payload


def _placeholder_rule_runtime_prepare_report(
    *,
    result: RuleImportPrepareResult,
    source_label: str,
    game_title: str | None,
    sample_count: int,
    details: JsonObject,
) -> AgentReport:
    """把 rule_runtime prepare 结果转换成 Agent 报告。"""
    rule_runtime_summary = _rule_runtime_summary(result.summary)
    summary: JsonObject = {
        "source": source_label,
        "mode": _summary_string(result.summary, "mode", "validate"),
        "rule_count": _summary_int(rule_runtime_summary, "rule_count", 0),
        "sample_count": sample_count,
        "rule_runtime": rule_runtime_summary,
    }
    if game_title is not None:
        summary["game"] = game_title
    return AgentReport.from_parts(
        errors=_runtime_issues_to_agent_issues(result.errors),
        warnings=_runtime_issues_to_agent_issues(result.warnings),
        summary=summary,
        details=details,
    )


def _augment_validation_report_with_runtime(
    *,
    report: AgentReport,
    prepare_result: RuleImportPrepareResult,
) -> AgentReport:
    """把 rule_runtime 摘要补进现有业务校验报告。"""
    summary = dict(report.summary)
    summary["rule_runtime"] = _rule_runtime_summary(prepare_result.summary)
    diagnostics = _rule_runtime_diagnostics(prepare_result)
    if diagnostics:
        summary["diagnostics"] = diagnostics
    details = dict(report.details)
    _merge_rule_runtime_details(details, prepare_result)
    return AgentReport.from_parts(
        errors=[*report.errors, *_runtime_issues_to_agent_issues(prepare_result.errors)],
        warnings=[*report.warnings, *_runtime_issues_to_agent_issues(prepare_result.warnings)],
        summary=summary,
        details=details,
    )


def _merge_rule_runtime_details(
    details: JsonObject,
    prepare_result: RuleImportPrepareResult | RuleImportCommitResult,
) -> None:
    """在不破坏既有 details 形状的前提下挂载 runtime 诊断。"""
    if prepare_result.details:
        details["rule_runtime"] = prepare_result.details
    diagnostics = _rule_runtime_diagnostics(prepare_result)
    if diagnostics:
        details["diagnostics"] = diagnostics


def _rule_runtime_diagnostics(
    result: RuleImportPrepareResult | RuleImportCommitResult,
) -> JsonObject:
    value = result.summary.get("diagnostics")
    if isinstance(value, dict):
        return dict(value)
    value = result.details.get("diagnostics")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _coverage_report_details(coverage: RuleCoverageResult) -> JsonObject:
    """把覆盖结果渲染成 Agent 报告 details.coverage。"""
    return {
        "summary": coverage.summary(detail_mode="full"),
        **coverage.full_details(),
    }


async def _placeholder_cleanup_input_for_text_rule_change(
    *,
    session: TargetGameSession,
    prior_text_rules: TextRules | None = None,
    proposed_text_rules: TextRules | None = None,
) -> JsonObject:
    """为 Rust prepare 生成占位符规则变化导致的译文清理输入。"""
    translated_items = await session.read_translated_items()
    if prior_text_rules is not None and proposed_text_rules is not None:
        stale_items = [
            item
            for item in translated_items
            if _translation_item_model_lines(item, prior_text_rules)
            != _translation_item_model_lines(item, proposed_text_rules)
        ]
    else:
        stale_items = []
    return cleanup_input_from_stale_items(stale_items)


def _translation_item_model_lines(item: TranslationItem, text_rules: TextRules) -> list[str]:
    """按指定规则计算已保存译文原文对应的模型可见文本。"""
    probe = TranslationItem(
        location_path=item.location_path,
        item_type=item.item_type,
        role=item.role,
        original_lines=list(item.original_lines),
        source_line_paths=list(item.source_line_paths),
    )
    probe.build_placeholders(text_rules)
    return list(probe.original_lines_with_placeholders)


def _placeholder_rule_records(
    custom_rules: tuple[CustomPlaceholderRule, ...],
) -> list[PlaceholderRuleRecord]:
    """把运行时可执行普通占位符规则转换成持久化记录。"""
    return [
        PlaceholderRuleRecord(
            pattern_text=rule.pattern_text,
            placeholder_template=rule.placeholder_template,
        )
        for rule in custom_rules
    ]


def _structured_placeholder_rule_records(
    structured_rules: tuple[StructuredPlaceholderRule, ...],
) -> list[StructuredPlaceholderRuleRecord]:
    """把运行时可执行结构化占位符规则转换成持久化记录。"""
    return [
        StructuredPlaceholderRuleRecord(
            rule_name=rule.rule_name,
            rule_type=rule.rule_type,
            pattern_text=rule.pattern_text,
            translatable_group=rule.translatable_group,
            protected_groups=dict(rule.protected_groups),
        )
        for rule in structured_rules
    ]


def _placeholder_import_report(
    *,
    game_title: str,
    prepare_result: RuleImportPrepareResult,
    commit_result: RuleImportCommitResult,
    validation_report: AgentReport,
    coverage: RuleCoverageResult,
    imported_rule_count: int,
    deleted_translation_count: int,
    deleted_translation_backup_path: str | None,
    cleanup_plan: JsonObject,
    reviewed_warning_code: str,
    reviewed_warning_message: str,
) -> AgentReport:
    """汇总普通/结构化占位符规则导入结果。"""
    rule_runtime_summary = _rule_runtime_summary(prepare_result.summary)
    summary: JsonObject = {
        "game": game_title,
        "mode": "import",
        "imported_rule_count": imported_rule_count,
        "validated_rule_count": imported_rule_count,
        "sample_count": _summary_int(validation_report.summary, "sample_count", 0),
        "rule_runtime": rule_runtime_summary,
        **coverage.summary(detail_mode="full"),
        "deleted_translation_items": deleted_translation_count,
        "cleanup_count": deleted_translation_count,
        "deleted_translation_backup_path": deleted_translation_backup_path,
    }
    diagnostics = _rule_runtime_diagnostics(prepare_result)
    if diagnostics:
        summary["diagnostics"] = diagnostics
    warnings = [
        *validation_report.warnings,
        *_runtime_issues_to_agent_issues(prepare_result.warnings),
        *_runtime_issues_to_agent_issues(commit_result.warnings),
    ]
    if coverage.uncovered_count:
        warnings.append(issue(reviewed_warning_code, reviewed_warning_message))
    if deleted_translation_count > 0 and deleted_translation_backup_path is not None:
        warnings.append(
            issue(
                "deleted_translations_backed_up",
                f"本次导入规则已清理 {deleted_translation_count} 条不再属于当前文本范围的已保存译文；已先备份到 {deleted_translation_backup_path}",
            )
        )
    details: JsonObject = {
        "validation": validation_report.details,
        "coverage": _coverage_report_details(coverage),
        "cleanup_plan": cleanup_plan,
    }
    _merge_rule_runtime_details(details, prepare_result)
    if commit_result.details:
        details["rule_runtime_commit"] = commit_result.details
    return AgentReport.from_parts(
        errors=[
            *validation_report.errors,
            *_runtime_issues_to_agent_issues(prepare_result.errors),
            *_runtime_issues_to_agent_issues(commit_result.errors),
        ],
        warnings=warnings,
        summary=summary,
        details=details,
    )


def _rule_runtime_summary(summary: JsonObject) -> JsonObject:
    value = summary.get("rule_runtime", {})
    if isinstance(value, dict):
        return dict(value)
    return {}


def _summary_string(summary: JsonObject, key: str, default: str) -> str:
    value = summary.get(key)
    if isinstance(value, str):
        return value
    return default


def _summary_int(summary: JsonObject, key: str, default: int) -> int:
    value = summary.get(key)
    if isinstance(value, int):
        return value
    return default


def _runtime_issues_to_agent_issues(items: list[RuleRuntimeIssue]) -> list[AgentIssue]:
    return [issue(item.code, item.message) for item in items]


def _custom_placeholder_prepare_details(
    *,
    rules_payload: JsonValue,
    setting_text_rules: TextRulesSetting,
) -> JsonObject:
    """按旧验证报告形状渲染普通占位符规则明细。"""
    if not isinstance(rules_payload, dict):
        return {"rules": [], "samples": []}
    text_rules = TextRules.from_setting(setting_text_rules)
    rules: JsonArray = []
    for pattern, template in rules_payload.items():
        if not isinstance(template, str):
            continue
        rules.append(
            {
                "pattern": pattern,
                "placeholder_template": template,
                "placeholder_preview": text_rules.format_custom_placeholder(
                    template=template,
                    index=1,
                ),
            }
        )
    return {"rules": rules, "samples": []}


def _structured_placeholder_prepare_details(
    *,
    rules_payload: JsonValue,
    setting_text_rules: TextRulesSetting,
) -> JsonObject:
    """按旧验证报告形状渲染结构化占位符规则明细。"""
    if not isinstance(rules_payload, dict):
        return {"rules": [], "samples": []}
    raw_rules = rules_payload.get("paired_shell_rules", [])
    if not isinstance(raw_rules, list):
        return {"rules": [], "samples": []}
    text_rules = TextRules.from_setting(setting_text_rules)
    rules: JsonArray = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        protected_groups = raw_rule.get("protected_groups", {})
        protected_group_details: JsonArray = []
        if isinstance(protected_groups, dict):
            for group_name, placeholder_template in sorted(protected_groups.items()):
                if not isinstance(placeholder_template, str):
                    continue
                protected_group_details.append(
                    {
                        "group_name": str(group_name),
                        "placeholder_template": placeholder_template,
                        "placeholder_preview": text_rules.format_custom_placeholder(
                            template=placeholder_template,
                            index=1,
                        ),
                    }
                )
        rules.append(
            {
                "name": raw_rule.get("name", ""),
                "type": "paired_shell",
                "pattern": raw_rule.get("pattern", ""),
                "translatable_group": raw_rule.get("translatable_group", ""),
                "protected_groups": protected_group_details,
            }
        )
    return {"rules": rules, "samples": []}


class PlaceholderRuleAgentMixin:
    """承载 AgentToolkitService 的 PlaceholderRuleAgentMixin 命令族。"""

    async def scan_placeholder_candidates(
        self: AgentServiceContext,
        *,
        game_title: str,
        custom_placeholder_rules_text: str | None,
    ) -> AgentReport:
        """扫描目标游戏中疑似需要自定义保护的控制符。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            custom_rules = await self._resolve_custom_rules(
                session=session,
                custom_placeholder_rules_text=custom_placeholder_rules_text,
            )
            structured_rules = await self._resolve_structured_rules(session=session)
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            text_index_invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=text_rules,
            )
            if text_index_invalidations:
                _ = await rebuild_text_index_native_storage(
                    session=session,
                    setting=setting,
                    text_rules=text_rules,
                    include_write_probe=False,
                )
            translation_data_map = await read_current_text_fact_translation_data_map(session)

        return _build_placeholder_coverage_report_with_context(
            setting_text_rules=setting.text_rules,
            custom_rules=custom_rules,
            structured_rules=structured_rules,
            translation_data_map=translation_data_map,
        )

    async def validate_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str | None,
        custom_placeholder_rules_text: str | None,
        sample_texts: Sequence[str],
    ) -> AgentReport:
        """校验自定义占位符规则。"""
        source_label = "--placeholder-rules"
        if custom_placeholder_rules_text is None and game_title is not None:
            source_label = "当前游戏数据库"
        elif custom_placeholder_rules_text is None:
            source_label = "空规则"

        try:
            if game_title is not None:
                async with await self.game_registry.open_game(game_title) as session:
                    setting = load_setting(self.setting_path, source_language=session.source_language)
                    if custom_placeholder_rules_text is None:
                        rules_payload = await _load_placeholder_rule_runtime_payload(
                            session=session,
                            rules_text=None,
                        )
                        custom_rules = await self._resolve_custom_rules(
                            session=session,
                            custom_placeholder_rules_text=None,
                        )
                    else:
                        rules_payload = load_custom_placeholder_rules_import_payload(
                            custom_placeholder_rules_text
                        )
                        custom_rules = ()
                    structured_rules = await self._resolve_structured_rules(session=session)
                    db_path = session.db_path
                    translation_data_map: dict[str, TranslationData] | None = None
            elif custom_placeholder_rules_text is None:
                setting = load_setting(self.setting_path)
                rules_payload = {}
                custom_rules = ()
                structured_rules = ()
                db_path = None
                translation_data_map = None
            else:
                setting = load_setting(self.setting_path)
                rules_payload = load_custom_placeholder_rules_import_payload(custom_placeholder_rules_text)
                custom_rules = ()
                structured_rules = ()
                db_path = None
                translation_data_map = None
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
                    "source": source_label,
                    "rule_count": 0,
                    "sample_count": len(sample_texts),
                },
                details={},
            )

        prepare_result = prepare_rule_import(
            _placeholder_rule_runtime_payload(
                mode="validate",
                domain="placeholders",
                rules_payload=rules_payload,
                setting=setting,
                db_path=db_path,
            )
        )
        if prepare_result.errors:
            return _placeholder_rule_runtime_prepare_report(
                result=prepare_result,
                source_label=source_label,
                game_title=game_title,
                sample_count=len(sample_texts),
                details=_custom_placeholder_prepare_details(
                    rules_payload=rules_payload,
                    setting_text_rules=setting.text_rules,
                ),
            )
        if custom_placeholder_rules_text is not None:
            custom_rules = load_custom_placeholder_rules_import_text(
                custom_placeholder_rules_text
            )
        if game_title is not None:
            async with await self.game_registry.open_game(game_title) as session:
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                _ = await _ensure_current_text_facts_for_placeholder_rules(
                    session=session,
                    setting=setting,
                    text_rules=text_rules,
                )
                translation_data_map = await read_current_text_fact_translation_data_map(session)
        validation_report = _validate_placeholder_rules_with_context(
            source_label=source_label,
            setting_text_rules=setting.text_rules,
            custom_rules=custom_rules,
            structured_rules=structured_rules,
            sample_texts=sample_texts,
            translation_data_map=translation_data_map,
        )
        return _augment_validation_report_with_runtime(
            report=validation_report,
            prepare_result=prepare_result,
        )

    async def import_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
        backup_output_dir: Path | None = None,
    ) -> AgentReport:
        """导入当前游戏专用自定义占位符规则。"""
        try:
            rules_payload = load_custom_placeholder_rules_import_payload(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                db_path = session.db_path
                structured_rules = await self._resolve_structured_rules(session=session)
                prepare_result = prepare_rule_import(
                    _placeholder_rule_runtime_payload(
                        mode="import",
                        domain="placeholders",
                        rules_payload=rules_payload,
                        setting=setting,
                        db_path=db_path,
                        confirm_empty=confirm_empty,
                    )
                )
                if prepare_result.errors:
                    return _placeholder_rule_runtime_prepare_report(
                        result=prepare_result,
                        source_label="--placeholder-rules",
                        game_title=game_title,
                        sample_count=0,
                        details=_custom_placeholder_prepare_details(
                            rules_payload=rules_payload,
                            setting_text_rules=setting.text_rules,
                        ),
                    )
                custom_rules = load_custom_placeholder_rules_import_text(rules_text)
                if not custom_rules:
                    ensure_empty_rule_confirmed(
                        rule_label="自定义占位符规则",
                        confirm_empty=confirm_empty,
                    )
                current_custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                current_text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=current_custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                _ = await _ensure_current_text_facts_for_placeholder_rules(
                    session=session,
                    setting=setting,
                    text_rules=current_text_rules,
                )
                current_translation_data_map = await read_current_text_fact_translation_data_map(
                    session
                )
                validation_report = _validate_placeholder_rules_with_context(
                    source_label="--placeholder-rules",
                    setting_text_rules=setting.text_rules,
                    custom_rules=custom_rules,
                    structured_rules=structured_rules,
                    sample_texts=[],
                    translation_data_map=current_translation_data_map,
                )
                if validation_report.errors:
                    return _augment_validation_report_with_runtime(
                        report=validation_report,
                        prepare_result=prepare_result,
                    )
                proposed_text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                _ = await _ensure_current_text_facts_for_placeholder_rules(
                    session=session,
                    setting=setting,
                    text_rules=proposed_text_rules,
                )
                translation_data_map = await read_current_text_fact_translation_data_map(session)
                coverage = build_normal_placeholder_coverage_result(
                    translation_data_map=translation_data_map,
                    text_rules=proposed_text_rules,
                    rule_count=len(custom_rules),
                )
                cleanup_input = await _placeholder_cleanup_input_for_text_rule_change(
                    session=session,
                    prior_text_rules=current_text_rules,
                    proposed_text_rules=proposed_text_rules,
                )
                prepare_payload = _placeholder_rule_runtime_payload(
                    mode="import",
                    domain="placeholders",
                    rules_payload=rules_payload,
                    setting=setting,
                    db_path=db_path,
                    confirm_empty=confirm_empty,
                    game_context={"scope_hash": coverage.scope_hash},
                )
                prepare_payload["cleanup_input"] = cleanup_input
                prepare_result = prepare_rule_import(prepare_payload)
                if prepare_result.errors:
                    return _placeholder_rule_runtime_prepare_report(
                        result=prepare_result,
                        source_label="--placeholder-rules",
                        game_title=game_title,
                        sample_count=0,
                        details=_custom_placeholder_prepare_details(
                            rules_payload=rules_payload,
                            setting_text_rules=setting.text_rules,
                        ),
                    )
                rule_records = _placeholder_rule_records(custom_rules)
                (
                    deleted_translation_items,
                    deleted_translation_backup_path,
                    cleanup_plan,
                ) = await write_prepared_cleanup_backup(
                    session=session,
                    game_title=game_title,
                    backup_domain="placeholder-rules",
                    prepare_result=prepare_result,
                    output_dir=backup_output_dir,
                )
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
                    "game": game_title,
                    "imported_rule_count": 0,
                    "validated_rule_count": 0,
                    "sample_count": 0,
                },
                details={},
            )
        commit_result = commit_prepared_rule_import(
            db_path=db_path,
            domain="placeholders",
            prepare_result=prepare_result,
            backup_path=deleted_translation_backup_path,
        )
        deleted_translation_items = commit_deleted_translation_count(commit_result)
        return _placeholder_import_report(
            game_title=game_title,
            prepare_result=prepare_result,
            commit_result=commit_result,
            validation_report=validation_report,
            coverage=coverage,
            imported_rule_count=len(rule_records),
            deleted_translation_count=deleted_translation_items,
            deleted_translation_backup_path=deleted_translation_backup_path,
            cleanup_plan=cleanup_plan,
            reviewed_warning_code="placeholder_uncovered_reviewed",
            reviewed_warning_message=f"仍有 {coverage.uncovered_count} 个疑似自定义控制符未被规则覆盖，本次导入已记录当前审查状态",
        )

    async def validate_structured_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        sample_texts: Sequence[str],
    ) -> AgentReport:
        """校验结构化占位符规则。"""
        try:
            rules_payload = load_structured_placeholder_rules_import_payload(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                db_path = session.db_path
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
        prepare_result = prepare_rule_import(
            _placeholder_rule_runtime_payload(
                mode="validate",
                domain="structured_placeholders",
                rules_payload=rules_payload,
                setting=setting,
                db_path=db_path,
            )
        )
        if prepare_result.errors:
            return _placeholder_rule_runtime_prepare_report(
                result=prepare_result,
                source_label="structured-placeholder-rules",
                game_title=game_title,
                sample_count=len(sample_texts),
                details=_structured_placeholder_prepare_details(
                    rules_payload=rules_payload,
                    setting_text_rules=setting.text_rules,
                ),
            )
        try:
            structured_rules = load_structured_placeholder_rules_import_text(rules_text)
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
        async with await self.game_registry.open_game(game_title) as session:
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
            _ = await _ensure_current_text_facts_for_placeholder_rules(
                session=session,
                setting=setting,
                text_rules=text_rules,
            )
            translation_data_map = await read_current_text_fact_translation_data_map(session)
        validation_report = _validate_structured_placeholder_rules_with_context(
            game_title=game_title,
            rules_text=rules_text,
            setting_text_rules=setting.text_rules,
            custom_rules=custom_rules,
            sample_texts=sample_texts,
            translation_data_map=translation_data_map,
        )
        return _augment_validation_report_with_runtime(
            report=validation_report,
            prepare_result=prepare_result,
        )

    async def scan_structured_placeholder_candidates(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """扫描结构化规则对当前正文中协议外壳候选的覆盖情况。"""
        try:
            structured_rules = load_structured_placeholder_rules_import_text(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                _ = await _ensure_current_text_facts_for_placeholder_rules(
                    session=session,
                    setting=setting,
                    text_rules=text_rules,
                )
                translation_data_map = await read_current_text_fact_translation_data_map(session)
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

        return _build_structured_placeholder_coverage_report_with_context(
            game_title=game_title,
            rules_text=rules_text,
            translation_data_map=translation_data_map,
            text_rules=text_rules,
            structured_rules=structured_rules,
        )

    async def import_structured_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
        backup_output_dir: Path | None = None,
    ) -> AgentReport:
        """导入当前游戏专用结构化占位符规则。"""
        try:
            rules_payload = load_structured_placeholder_rules_import_payload(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                db_path = session.db_path
                custom_rules = await self._resolve_custom_rules(
                    session=session,
                    custom_placeholder_rules_text=None,
                )
                prepare_result = prepare_rule_import(
                    _placeholder_rule_runtime_payload(
                        mode="import",
                        domain="structured_placeholders",
                        rules_payload=rules_payload,
                        setting=setting,
                        db_path=db_path,
                        confirm_empty=confirm_empty,
                    )
                )
                if prepare_result.errors:
                    return _placeholder_rule_runtime_prepare_report(
                        result=prepare_result,
                        source_label="structured-placeholder-rules",
                        game_title=game_title,
                        sample_count=0,
                        details=_structured_placeholder_prepare_details(
                            rules_payload=rules_payload,
                            setting_text_rules=setting.text_rules,
                        ),
                    )
                structured_rules = load_structured_placeholder_rules_import_text(rules_text)
                if not structured_rules:
                    ensure_empty_rule_confirmed(
                        rule_label="结构化占位符规则",
                        confirm_empty=confirm_empty,
                    )
                current_structured_rules = await self._resolve_structured_rules(session=session)
                current_text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=current_structured_rules,
                )
                _ = await _ensure_current_text_facts_for_placeholder_rules(
                    session=session,
                    setting=setting,
                    text_rules=current_text_rules,
                )
                current_translation_data_map = await read_current_text_fact_translation_data_map(
                    session
                )
                validation_report = _validate_structured_placeholder_rules_with_context(
                    game_title=game_title,
                    rules_text=rules_text,
                    setting_text_rules=setting.text_rules,
                    custom_rules=custom_rules,
                    sample_texts=[],
                    translation_data_map=current_translation_data_map,
                )
                if validation_report.errors:
                    return _augment_validation_report_with_runtime(
                        report=validation_report,
                        prepare_result=prepare_result,
                    )
                proposed_text_rules = TextRules.from_setting(
                    setting.text_rules,
                    custom_placeholder_rules=custom_rules,
                    structured_placeholder_rules=structured_rules,
                )
                _ = await _ensure_current_text_facts_for_placeholder_rules(
                    session=session,
                    setting=setting,
                    text_rules=proposed_text_rules,
                )
                translation_data_map = await read_current_text_fact_translation_data_map(session)
                coverage = build_structured_placeholder_coverage_result(
                    translation_data_map=translation_data_map,
                    structured_rules=structured_rules,
                    rule_count=len(structured_rules),
                    text_rules=proposed_text_rules,
                )
                cleanup_input = await _placeholder_cleanup_input_for_text_rule_change(
                    session=session,
                    prior_text_rules=current_text_rules,
                    proposed_text_rules=proposed_text_rules,
                )
                prepare_payload = _placeholder_rule_runtime_payload(
                    mode="import",
                    domain="structured_placeholders",
                    rules_payload=rules_payload,
                    setting=setting,
                    db_path=db_path,
                    confirm_empty=confirm_empty,
                    game_context={"scope_hash": coverage.scope_hash},
                )
                prepare_payload["cleanup_input"] = cleanup_input
                prepare_result = prepare_rule_import(prepare_payload)
                if prepare_result.errors:
                    return _placeholder_rule_runtime_prepare_report(
                        result=prepare_result,
                        source_label="structured-placeholder-rules",
                        game_title=game_title,
                        sample_count=0,
                        details=_structured_placeholder_prepare_details(
                            rules_payload=rules_payload,
                            setting_text_rules=setting.text_rules,
                        ),
                    )
                rule_records = _structured_placeholder_rule_records(structured_rules)
                (
                    deleted_translation_items,
                    deleted_translation_backup_path,
                    cleanup_plan,
                ) = await write_prepared_cleanup_backup(
                    session=session,
                    game_title=game_title,
                    backup_domain="structured-placeholder-rules",
                    prepare_result=prepare_result,
                    output_dir=backup_output_dir,
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
                    "imported_rule_count": 0,
                    "validated_rule_count": 0,
                    "sample_count": 0,
                },
                details={},
            )
        commit_result = commit_prepared_rule_import(
            db_path=db_path,
            domain="structured_placeholders",
            prepare_result=prepare_result,
            backup_path=deleted_translation_backup_path,
        )
        deleted_translation_items = commit_deleted_translation_count(commit_result)
        return _placeholder_import_report(
            game_title=game_title,
            prepare_result=prepare_result,
            commit_result=commit_result,
            validation_report=validation_report,
            coverage=coverage,
            imported_rule_count=len(rule_records),
            deleted_translation_count=deleted_translation_items,
            deleted_translation_backup_path=deleted_translation_backup_path,
            cleanup_plan=cleanup_plan,
            reviewed_warning_code="structured_placeholder_uncovered_reviewed",
            reviewed_warning_message=f"仍有 {coverage.uncovered_count} 个协议外壳候选未被结构化规则覆盖，本次导入已记录当前审查状态",
        )

    async def build_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_path: Path,
    ) -> AgentReport:
        """根据未覆盖候选生成可编辑的自定义占位符规则草稿。"""
        async with await self.game_registry.open_game(game_title) as session:
            setting = load_setting(self.setting_path, source_language=session.source_language)
            structured_rules = await self._resolve_structured_rules(session=session)
            empty_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=(),
                structured_placeholder_rules=structured_rules,
            )
            text_index_invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=empty_rules,
            )
            metadata = await session.read_text_index_metadata()
            if text_index_invalidations:
                metadata = await rebuild_text_index_native_storage(
                    session=session,
                    setting=setting,
                    text_rules=empty_rules,
                    include_write_probe=False,
                )
            if metadata is None:
                return AgentReport.from_parts(
                    errors=[issue("text_index_missing", "当前游戏尚未建立持久文本范围索引，请先重建文本范围索引")],
                    warnings=[],
                    summary={
                        "game": game_title,
                        "candidate_count": 0,
                        "uncovered_count_before_draft": 0,
                        "uncovered_count_after_draft_preview": 0,
                        "draft_rule_count": 0,
                        "manual_boundary_candidate_count": 0,
                        "output": str(output_path),
                    },
                    details={},
                )
            external_rule_errors = await collect_text_index_external_rule_gate_errors(
                session=session,
                metadata=metadata,
            )
            if external_rule_errors:
                return AgentReport.from_parts(
                    errors=[issue(error.code, error.message) for error in external_rule_errors],
                    warnings=[],
                    summary={
                        "game": game_title,
                        "candidate_count": 0,
                        "uncovered_count_before_draft": 0,
                        "uncovered_count_after_draft_preview": 0,
                        "draft_rule_count": 0,
                        "manual_boundary_candidate_count": 0,
                        "output": str(output_path),
                    },
                    details={},
                )
            placeholder_entries = await read_current_text_fact_placeholder_entries(session)
        candidate_details = collect_native_placeholder_candidate_details_from_entries(
            entries=placeholder_entries,
            text_rules=empty_rules,
        )
        uncovered_count_before_draft = count_uncovered_placeholder_candidate_details(candidate_details)
        draft_rules = _build_custom_placeholder_rule_draft_from_details(candidate_details)
        manual_boundary_markers = _joined_text_boundary_markers_from_details(candidate_details)
        draft_custom_rules = load_custom_placeholder_rules_text(json.dumps(draft_rules, ensure_ascii=False))
        draft_text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=draft_custom_rules,
            structured_placeholder_rules=structured_rules,
        )
        draft_preview_candidate_details = collect_native_placeholder_candidate_details_from_entries(
            entries=placeholder_entries,
            text_rules=draft_text_rules,
        )
        uncovered_count_after_draft_preview = count_uncovered_placeholder_candidate_details(
            draft_preview_candidate_details
        )
        warnings = _build_unprotected_control_warnings(
            _collect_unprotected_control_warning_samples_from_entries(placeholder_entries, empty_rules),
            empty_rules,
        )
        warnings.extend(_build_joined_text_boundary_warnings(manual_boundary_markers))
        if not draft_rules:
            warnings.append(issue("placeholder_draft_empty", "没有发现需要生成草稿的自定义控制符候选"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
            _ = await file.write(f"{json.dumps(draft_rules, ensure_ascii=False, indent=2)}\n")
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "candidate_count": len(candidate_details),
                "uncovered_count_before_draft": uncovered_count_before_draft,
                "uncovered_count_after_draft_preview": uncovered_count_after_draft_preview,
                "draft_rule_count": len(draft_rules),
                "manual_boundary_candidate_count": len(manual_boundary_markers),
                "output": str(output_path),
            },
            details={
                "rules": {key: value for key, value in draft_rules.items()},
                "manual_boundary_candidates": [marker for marker in manual_boundary_markers],
            },
        )


def _collect_unprotected_control_warning_samples_from_entries(
    entries: Sequence[tuple[str, Sequence[str]]],
    text_rules: TextRules,
) -> list[str]:
    """从轻量索引正文收集裸露控制符边界风险样本。"""
    samples: list[str] = []
    for _location_path, original_lines in entries:
        for text in original_lines:
            if not text_rules.iter_unprotected_control_sequence_candidates(text):
                continue
            samples.append(text)
            if len(samples) >= 10:
                return samples
    return samples
