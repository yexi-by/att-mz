"""Agent 工具箱 DoctorAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonObject,
    JsonValue,
    TextRules,
    _append_check,
    _current_python_major_minor,
    collect_saved_rule_runtime_errors,
    ensure_db_directory,
    issue,
    load_environment_overrides,
    load_setting,
    platform,
    resolve_app_path,
    resolve_replacement_font_path,
    resolve_setting_path,
    sys,
)
from app.agent_toolkit.flow_decision import build_flow_decision
from app.persistence import TargetGameSession
from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    RuleReviewDomain,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
)
from app.rule_review_decision import RuleReviewDecision, RuleReviewSeverity, build_empty_rule_review_decision
from app.rmmz.loader import validate_data_directory_integrity
from app.text_index import collect_text_index_placeholder_gate_decisions, detect_text_index_invalidations


class DoctorAgentMixin:
    """承载 AgentToolkitService 的 DoctorAgentMixin 命令族。"""

    async def doctor(self: AgentServiceContext, *, game_title: str | None, check_llm: bool) -> AgentReport:
        """检查项目配置、模型连接和可选目标游戏状态。"""
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
        summary: JsonObject = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "setting_path": str(resolve_setting_path(self.setting_path)),
        }
        details: JsonObject = {
            "environment_overrides": [],
            "checks": [],
        }

        python_major, python_minor = _current_python_major_minor()
        if (python_major, python_minor) < (3, 14):
            errors.append(issue("python_version", "当前 Python 版本低于项目要求的 3.14"))
        else:
            _append_check(details, "python_version", "ok")

        try:
            setting = load_setting(self.setting_path)
            _append_check(details, "setting", "ok")
            summary["llm_model"] = setting.llm.model
            summary["llm_check_performed"] = check_llm
            environment_overrides = load_environment_overrides()
            enabled_names: list[JsonValue] = list(environment_overrides.enabled_names())
            details["environment_overrides"] = enabled_names
            if not setting.llm.base_url.strip():
                errors.append(issue("llm_base_url", "模型服务地址为空"))
            if not setting.llm.api_key.strip():
                errors.append(issue("llm_api_key", "模型 API Key 为空"))
            if check_llm:
                try:
                    self.llm_handler.configure(
                        base_url=setting.llm.base_url,
                        api_key=setting.llm.api_key,
                        timeout=setting.llm.timeout,
                        request_body_extra=setting.llm.request_body_extra,
                    )
                    await self.llm_check(self.llm_handler, setting.llm.model)
                    _append_check(details, "llm", "ok")
                    summary["llm_connection_status"] = "ok"
                except Exception as error:
                    summary["llm_connection_status"] = "failed"
                    errors.append(issue("llm", f"模型连通性检查失败: {type(error).__name__}: {error}"))
            else:
                summary["llm_connection_status"] = "skipped"
                warnings.append(issue("llm_skipped", "已跳过模型连通性检查"))
        except Exception as error:
            errors.append(issue("setting", f"配置加载失败: {type(error).__name__}: {error}"))
            setting = None

        self._check_static_paths(errors=errors, warnings=warnings, details=details)

        if game_title is not None:
            await self._check_game(
                game_title=game_title,
                setting_available=setting is not None,
                errors=errors,
                warnings=warnings,
                summary=summary,
                details=details,
            )
            quality_report: AgentReport | None = None
            translation_status_report: AgentReport | None = None
            recent_run_payloads: list[dict[str, JsonValue]] = []
            if not errors:
                quality_report = await self.quality_report(
                    game_title=game_title,
                    include_write_probe=True,
                )
                translation_status_report = await self.translation_status(
                    game_title=game_title,
                    refresh_scope=True,
                )
                async with await self.game_registry.open_game(game_title) as session:
                    recent_run_payloads = _recent_run_payloads(
                        await session.read_recent_translation_runs(limit=5)
                    )
            decision = build_flow_decision(
                base_error_codes={item.code for item in errors},
                base_warning_codes={item.code for item in warnings},
                quality_report=quality_report,
                translation_status=translation_status_report,
                recent_runs=recent_run_payloads,
            )
            summary.update(decision.summary_fields())
            details["flow_decision"] = decision.detail_fields()
            details["flow_reports"] = {
                "quality": quality_report.model_dump(mode="json") if quality_report is not None else None,
                "translation_status": (
                    translation_status_report.model_dump(mode="json")
                    if translation_status_report is not None
                    else None
                ),
                "recent_runs": recent_run_payloads,
            }
            if not decision.can_continue and not errors:
                errors.append(issue("flow_blocked", decision.reason))

        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary=summary,
            details=details,
        )

    async def _check_game(
        self: AgentServiceContext,
        *,
        game_title: str,
        setting_available: bool,
        errors: list[AgentIssue],
        warnings: list[AgentIssue],
        summary: JsonObject,
        details: JsonObject,
    ) -> None:
        """检查目标游戏数据库、文件和导入状态。"""
        _ = details
        if not setting_available:
            warnings.append(issue("game_skipped", "配置不可用，已跳过目标游戏深度检查"))
            return
        try:
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                saved_rule_errors = await collect_saved_rule_runtime_errors(session, setting)
                if saved_rule_errors:
                    errors.extend(saved_rule_errors)
                    return
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
                validate_data_directory_integrity(
                    data_dir=session.content_root / "data",
                    role="当前运行 data 目录",
                )
                text_index_status = "used"
                text_index_invalidations = await detect_text_index_invalidations(
                    session=session,
                    text_rules=text_rules,
                )
                if text_index_invalidations:
                    text_index_status = "rebuilt"
                    rebuild_report = await self.rebuild_text_index(game_title=game_title)
                    if rebuild_report.status == "error":
                        errors.extend(rebuild_report.errors)
                        warnings.extend(rebuild_report.warnings)
                        return
                    text_index_invalidations = await detect_text_index_invalidations(
                        session=session,
                        text_rules=text_rules,
                    )
                    if text_index_invalidations:
                        errors.append(
                            issue(
                                "text_index_rebuild_mismatch",
                                "文本范围索引重建后仍不匹配本次命令配置，不能使用错配索引完成诊断",
                            )
                        )
                        return
                metadata = await session.read_text_index_metadata()
                if metadata is None:
                    errors.append(issue("text_index_metadata_missing", "持久文本范围索引缺少元信息，请重新运行 rebuild-text-index"))
                    return
                scope_summary = await session.read_text_index_scope_summary()
                plugin_rules = await session.read_plugin_text_rules()
                event_rules = await session.read_event_command_text_rules()
                note_tag_rules = await session.read_note_tag_text_rules()
                mv_virtual_namebox_rules = await session.read_mv_virtual_namebox_rules()
                terminology_registry = await session.read_terminology_registry()
                terminology_glossary = await session.read_terminology_glossary()
                placeholder_rules = await session.read_placeholder_rules()
                structured_placeholder_rules = await session.read_structured_placeholder_rules()
                placeholder_decisions, placeholder_metadata_errors = await collect_text_index_placeholder_gate_decisions(
                    session=session,
                    metadata=metadata,
                    custom_placeholder_rules_supplied=False,
                    stage="doctor",
                )
                placeholder_decision = _find_rule_review_decision(
                    placeholder_decisions,
                    PLACEHOLDER_RULE_DOMAIN,
                )
                structured_placeholder_decision = _find_rule_review_decision(
                    placeholder_decisions,
                    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
                )
                plugin_empty_decision = await _build_text_index_empty_rule_review_decision(
                    session=session,
                    metadata_scope_hashes=metadata.workflow_gate_scope_hashes,
                    rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
                    label="插件文本规则",
                    missing_code="plugin_rules",
                    stale_code="plugin_rules_review_state_stale",
                    missing_severity="warning",
                    stale_severity="warning",
                    missing_message="当前游戏尚未导入插件文本规则",
                    stale_message="插件文本规则曾确认为空，但当前插件配置已变化，请重新导出并检查插件规则",
                )
                event_empty_decision = await _build_text_index_empty_rule_review_decision(
                    session=session,
                    metadata_scope_hashes=metadata.workflow_gate_scope_hashes,
                    rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
                    label="事件指令文本规则",
                    missing_code="event_command_rules",
                    stale_code="event_command_rules_review_state_stale",
                    missing_severity="warning",
                    stale_severity="warning",
                    missing_message="当前游戏尚未导入事件指令文本规则",
                    stale_message="事件指令文本规则曾确认为空，但当前事件指令参数已变化，请重新导出并检查事件指令规则",
                )
                note_empty_decision = await _build_text_index_empty_rule_review_decision(
                    session=session,
                    metadata_scope_hashes=metadata.workflow_gate_scope_hashes,
                    rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
                    label="Note 标签文本规则",
                    missing_code="note_tag_rules",
                    stale_code="note_tag_rules_review_state_stale",
                    missing_severity="warning",
                    stale_severity="warning",
                    missing_message="当前游戏尚未导入 Note 标签文本规则",
                    stale_message="Note 标签规则曾确认为空，但当前 Note 文本已变化，请重新导出并检查 Note 标签规则",
                )
                placeholder_empty_decision = await _build_text_index_empty_rule_review_decision(
                    session=session,
                    metadata_scope_hashes={
                        PLACEHOLDER_RULE_DOMAIN: placeholder_decision.scope_hash
                    }
                    if placeholder_decision is not None
                    else {},
                    rule_domain=PLACEHOLDER_RULE_DOMAIN,
                    label="普通占位符规则",
                    missing_code="placeholder_rules",
                    stale_code="placeholder_rules_review_state_stale",
                    missing_severity="warning",
                    stale_severity="warning",
                    missing_message="当前游戏尚未导入自定义占位符规则",
                    stale_message="普通占位符规则曾确认为空，但当前正文候选已变化，请重新扫描并检查普通占位符规则",
                )
                structured_placeholder_empty_decision = await _build_text_index_empty_rule_review_decision(
                    session=session,
                    metadata_scope_hashes={
                        STRUCTURED_PLACEHOLDER_RULE_DOMAIN: structured_placeholder_decision.scope_hash
                    }
                    if structured_placeholder_decision is not None
                    else {},
                    rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
                    label="结构化占位符规则",
                    missing_code="structured_placeholder_rules",
                    stale_code="structured_placeholder_rules_review_state_stale",
                    missing_severity="warning",
                    stale_severity="warning",
                    missing_message="当前游戏尚未导入结构化占位符规则",
                    stale_message="结构化占位符规则曾确认为空，但当前正文候选已变化，请重新扫描并检查结构化占位符规则",
                )
                mv_virtual_namebox_empty_decision: RuleReviewDecision | None = (
                    await _build_text_index_empty_rule_review_decision(
                        session=session,
                        metadata_scope_hashes=metadata.workflow_gate_scope_hashes,
                        rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
                        label="MV 虚拟名字框规则",
                        missing_code="mv_virtual_namebox_rules",
                        stale_code="mv_virtual_namebox_rules_review_state_stale",
                        missing_severity="warning",
                        stale_severity="warning",
                        missing_message="当前 MV 游戏尚未导入 MV 虚拟名字框规则",
                        stale_message="MV 虚拟名字框规则曾确认为空，但当前候选已变化，请重新导出并检查 MV 虚拟名字框规则",
                    )
                    if session.engine_kind == "mv"
                    else None
                )
                plugin_rules_reviewed_empty = _decision_reviewed_empty(plugin_empty_decision)
                plugin_rules_review_state_stale = _decision_state_stale(plugin_empty_decision)
                event_rules_reviewed_empty = _decision_reviewed_empty(event_empty_decision)
                event_rules_review_state_stale = _decision_state_stale(event_empty_decision)
                note_rules_reviewed_empty = _decision_reviewed_empty(note_empty_decision)
                note_rules_review_state_stale = _decision_state_stale(note_empty_decision)
                placeholder_rules_reviewed_empty = _decision_reviewed_empty(placeholder_empty_decision)
                placeholder_rules_review_state_stale = _decision_state_stale(placeholder_empty_decision)
                structured_placeholder_rules_reviewed_empty = _decision_reviewed_empty(
                    structured_placeholder_empty_decision
                )
                structured_placeholder_rules_review_state_stale = _decision_state_stale(
                    structured_placeholder_empty_decision
                )
                mv_virtual_namebox_rules_reviewed_empty = (
                    _decision_reviewed_empty(mv_virtual_namebox_empty_decision)
                    if mv_virtual_namebox_empty_decision is not None
                    else False
                )
                mv_virtual_namebox_rules_review_state_stale = (
                    _decision_state_stale(mv_virtual_namebox_empty_decision)
                    if mv_virtual_namebox_empty_decision is not None
                    else False
                )
                summary["game_registered"] = True
                summary["source_language"] = session.source_language
                summary["target_language"] = session.target_language
                summary["plugin_rule_count"] = sum(len(rule.path_templates) for rule in plugin_rules)
                summary["stale_plugin_rule_count"] = scope_summary.stale_rule_count if scope_summary is not None else 0
                summary["event_command_rule_count"] = sum(len(rule.path_templates) for rule in event_rules)
                summary["note_tag_rule_count"] = sum(len(rule.tag_names) for rule in note_tag_rules)
                summary["mv_virtual_namebox_candidate_count"] = 0
                summary["mv_virtual_namebox_rule_count"] = len(mv_virtual_namebox_rules)
                summary["text_index_status"] = text_index_status
                summary["plugin_rules_reviewed_empty"] = plugin_rules_reviewed_empty
                summary["plugin_rules_review_state_stale"] = plugin_rules_review_state_stale
                summary["event_command_rules_reviewed_empty"] = event_rules_reviewed_empty
                summary["event_command_rules_review_state_stale"] = event_rules_review_state_stale
                summary["note_tag_rules_reviewed_empty"] = note_rules_reviewed_empty
                summary["note_tag_rules_review_state_stale"] = note_rules_review_state_stale
                summary["mv_virtual_namebox_rules_reviewed_empty"] = mv_virtual_namebox_rules_reviewed_empty
                summary["mv_virtual_namebox_rules_review_state_stale"] = mv_virtual_namebox_rules_review_state_stale
                summary["placeholder_rule_count"] = len(placeholder_rules)
                summary["structured_placeholder_rule_count"] = len(structured_placeholder_rules)
                summary["placeholder_rules_reviewed_empty"] = placeholder_rules_reviewed_empty
                summary["placeholder_rules_review_state_stale"] = placeholder_rules_review_state_stale
                summary["structured_placeholder_rules_reviewed_empty"] = structured_placeholder_rules_reviewed_empty
                summary["structured_placeholder_rules_review_state_stale"] = structured_placeholder_rules_review_state_stale
                summary["terminology_imported"] = terminology_registry is not None
                summary["glossary_imported"] = terminology_glossary is not None
                stale_plugin_rule_count = scope_summary.stale_rule_count if scope_summary is not None else 0
                if not plugin_rules and stale_plugin_rule_count == 0:
                    _append_rule_review_decision_warning(warnings, plugin_empty_decision)
                if stale_plugin_rule_count:
                    warnings.append(issue("stale_plugin_rules", f"发现 {stale_plugin_rule_count} 个过期插件规则，请重新导出并导入插件规则"))
                if not event_rules:
                    _append_rule_review_decision_warning(warnings, event_empty_decision)
                if not note_tag_rules:
                    _append_rule_review_decision_warning(warnings, note_empty_decision)
                if session.engine_kind == "mv" and not mv_virtual_namebox_rules:
                    _append_rule_review_decision_warning(warnings, mv_virtual_namebox_empty_decision)
                if terminology_registry is None:
                    warnings.append(issue("terminology", "当前游戏尚未导入字段译名表"))
                if terminology_glossary is None:
                    warnings.append(issue("glossary", "当前游戏尚未导入正文术语表"))
                if not placeholder_rules:
                    _append_rule_review_decision_warning(warnings, placeholder_empty_decision)
                if not structured_placeholder_rules:
                    _append_rule_review_decision_warning(warnings, structured_placeholder_empty_decision)
                warnings.extend(issue(error.code, error.message) for error in placeholder_metadata_errors)
                font_path = setting.write_back.replacement_font_path
                if font_path is not None:
                    try:
                        _ = resolve_replacement_font_path(font_path)
                    except (FileNotFoundError, ValueError) as error:
                        warnings.append(issue("replacement_font", f"配置的候选覆盖字体文件不可用: {error}"))
                uncovered_count = placeholder_decision.uncovered_count if placeholder_decision is not None else 0
                structured_uncovered_count = (
                    structured_placeholder_decision.uncovered_count
                    if structured_placeholder_decision is not None
                    else 0
                )
                summary["uncovered_placeholder_count"] = uncovered_count
                summary["uncovered_structured_placeholder_count"] = structured_uncovered_count
                if uncovered_count and placeholder_decision is not None:
                    warnings.append(issue(placeholder_decision.code, placeholder_decision.message))
                if structured_uncovered_count and structured_placeholder_decision is not None:
                    warnings.append(issue(structured_placeholder_decision.code, structured_placeholder_decision.message))
        except Exception as error:
            errors.append(issue("game", f"目标游戏检查失败: {type(error).__name__}: {error}"))

    def _check_static_paths(
        self: AgentServiceContext,
        *,
        errors: list[AgentIssue],
        warnings: list[AgentIssue],
        details: JsonObject,
    ) -> None:
        """检查项目固定目录和终端编码。"""
        _ = warnings
        db_dir = self.game_registry.db_directory
        db_dir_already_exists = db_dir.exists()
        try:
            _ = ensure_db_directory(db_dir)
            _append_check(details, "db_dir", "ok" if db_dir_already_exists else "created")
        except Exception as error:
            errors.append(issue("db_dir", f"数据库目录创建失败: {type(error).__name__}: {error}"))
        logs_dir = resolve_app_path("logs")
        if not logs_dir.exists():
            _ = logs_dir.mkdir(exist_ok=True)
        try:
            encoding = sys.stdout.encoding or ""
            details["stdout_encoding"] = encoding
            _append_check(details, "stdout_encoding", "ok" if "utf" in encoding.lower() else "warning")
            if "utf" not in encoding.lower():
                warnings.append(issue("stdout_encoding", "当前 stdout 不是 UTF-8，可能影响 Agent 解析 JSON 输出"))
        except Exception as error:
            warnings.append(issue("stdout_encoding", f"终端编码检查失败: {type(error).__name__}: {error}"))


def _decision_reviewed_empty(decision: RuleReviewDecision | None) -> bool:
    """判断统一决策是否代表仍有效的空规则确认。"""
    return (
        decision is not None
        and decision.confirmed_empty is True
        and decision.confirmation_status == "confirmed"
    )


def _find_rule_review_decision(
    decisions: list[RuleReviewDecision],
    rule_domain: RuleReviewDomain,
) -> RuleReviewDecision | None:
    """按规则域从索引 gate 决策中取一条结果。"""
    for decision in decisions:
        if decision.rule_domain == rule_domain:
            return decision
    return None


async def _build_text_index_empty_rule_review_decision(
    *,
    session: TargetGameSession,
    metadata_scope_hashes: dict[str, str],
    rule_domain: RuleReviewDomain,
    label: str,
    missing_code: str,
    stale_code: str,
    missing_severity: RuleReviewSeverity,
    stale_severity: RuleReviewSeverity,
    missing_message: str,
    stale_message: str,
) -> RuleReviewDecision | None:
    """用 text index metadata 中的范围 hash 生成空规则确认状态。"""
    scope_hash = metadata_scope_hashes.get(rule_domain)
    if not scope_hash:
        state = await session.read_rule_review_state(rule_domain=rule_domain)
        scope_hash = state.scope_hash if state is not None else ""
    return await build_empty_rule_review_decision(
        session=session,
        rule_domain=rule_domain,
        stage="doctor",
        scope_hash=scope_hash,
        label=label,
        missing_code=missing_code,
        stale_code=stale_code,
        missing_severity=missing_severity,
        stale_severity=stale_severity,
        missing_message=missing_message,
        stale_message=stale_message,
    )


def _decision_state_stale(decision: RuleReviewDecision | None) -> bool:
    """判断统一决策是否代表确认范围已失效。"""
    return decision is not None and decision.confirmation_status == "stale"


def _append_rule_review_decision_warning(
    warnings: list[AgentIssue],
    decision: RuleReviewDecision | None,
) -> None:
    """把非 ok 的规则审查决策追加到 doctor 告警。"""
    if decision is not None and decision.severity != "ok" and decision.code:
        warnings.append(issue(decision.code, decision.message))


def _recent_run_payloads(records: object) -> list[dict[str, JsonValue]]:
    """把最近运行记录转成流程裁决只读输入。"""
    if not isinstance(records, list):
        return []
    payloads: list[dict[str, JsonValue]] = []
    for record in records:
        run_id = getattr(record, "run_id", "")
        pending_count = getattr(record, "pending_count", 0)
        success_count = getattr(record, "success_count", 0)
        quality_error_count = getattr(record, "quality_error_count", 0)
        if not isinstance(run_id, str):
            run_id = ""
        if not isinstance(pending_count, int) or isinstance(pending_count, bool):
            pending_count = 0
        if not isinstance(success_count, int) or isinstance(success_count, bool):
            success_count = 0
        if not isinstance(quality_error_count, int) or isinstance(quality_error_count, bool):
            quality_error_count = 0
        payloads.append(
            {
                "run_id": run_id,
                "pending_count": pending_count,
                "success_count": success_count,
                "quality_error_count": quality_error_count,
            }
        )
    return payloads
