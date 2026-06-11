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
    aiofiles,
    issue,
    json,
    load_custom_placeholder_rules_import_payload,
    load_custom_placeholder_rules_text,
    load_structured_placeholder_rules_import_payload,
    load_structured_placeholder_rules_import_text,
    load_setting,
)
from app.native_rule_runtime import (
    RuleImportCommitResult,
    RuleImportPrepareResult,
    RuleRuntimeIssue,
    commit_rule_import,
    prepare_rule_import,
)
from app.agent_toolkit.reports import AgentIssue
from app.native_placeholder_scan import (
    collect_native_placeholder_candidate_details_from_entries,
    count_uncovered_placeholder_candidate_details,
)
from app.config.schemas import Setting
from app.persistence import TargetGameSession
from app.rmmz.json_types import JsonObject
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
) -> JsonObject:
    """构造普通占位符规则运行时载荷。"""
    payload: JsonObject = {
        "mode": mode,
        "domain": domain,
        "rules_payload": rules_payload,
        "game_context": {},
        "settings_runtime_patterns": _settings_runtime_patterns(setting),
    }
    if db_path is not None:
        payload["db_path"] = str(db_path)
    return payload


def _settings_runtime_patterns(setting: Setting) -> JsonObject:
    """把配置里的用户可写正则集中传给 rule_runtime。"""
    text_rules = setting.text_rules
    return {
        "source_text_required_pattern": text_rules.source_text_required_pattern,
        "source_residual_segment_pattern": text_rules.source_residual_segment_pattern,
        "line_width_count_pattern": text_rules.line_width_count_pattern,
        "residual_escape_sequence_pattern": text_rules.residual_escape_sequence_pattern,
    }


def _placeholder_rule_runtime_prepare_report(
    *,
    result: RuleImportPrepareResult,
    source_label: str,
    game_title: str | None,
    sample_count: int,
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
        details={},
    )


def _placeholder_rule_runtime_commit_report(
    *,
    result: RuleImportCommitResult,
    prepare_result: RuleImportPrepareResult,
    game_title: str,
) -> AgentReport:
    """把 rule_runtime commit 结果转换成普通占位符导入报告。"""
    rule_runtime_summary = _rule_runtime_summary(prepare_result.summary)
    rule_count = _summary_int(rule_runtime_summary, "rule_count", 0)
    imported_count = 0 if result.errors else rule_count
    return AgentReport.from_parts(
        errors=_runtime_issues_to_agent_issues(result.errors),
        warnings=[
            *_runtime_issues_to_agent_issues(prepare_result.warnings),
            *_runtime_issues_to_agent_issues(result.warnings),
        ],
        summary={
            "game": game_title,
            "mode": "import",
            "imported_rule_count": imported_count,
            "validated_rule_count": rule_count,
            "sample_count": 0,
            "rule_runtime": rule_runtime_summary,
        },
        details={},
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
                    rules_payload = await _load_placeholder_rule_runtime_payload(
                        session=session,
                        rules_text=custom_placeholder_rules_text,
                    )
                    db_path = session.db_path
            elif custom_placeholder_rules_text is None:
                setting = load_setting(self.setting_path)
                rules_payload = {}
                db_path = None
            else:
                setting = load_setting(self.setting_path)
                rules_payload = load_custom_placeholder_rules_import_payload(custom_placeholder_rules_text)
                db_path = None
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
        return _placeholder_rule_runtime_prepare_report(
            result=prepare_result,
            source_label=source_label,
            game_title=game_title,
            sample_count=len(sample_texts),
        )

    async def import_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
    ) -> AgentReport:
        """导入当前游戏专用自定义占位符规则。"""
        _ = confirm_empty
        try:
            rules_payload = load_custom_placeholder_rules_import_payload(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                db_path = session.db_path
                prepare_result = prepare_rule_import(
                    _placeholder_rule_runtime_payload(
                        mode="import",
                        domain="placeholders",
                        rules_payload=rules_payload,
                        setting=setting,
                        db_path=db_path,
                    )
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
        if prepare_result.errors:
            return _placeholder_rule_runtime_prepare_report(
                result=prepare_result,
                source_label="--placeholder-rules",
                game_title=game_title,
                sample_count=0,
            )
        if prepare_result.plan_token is None:
            raise RuntimeError("普通占位符规则导入缺少 rule_runtime plan token")

        commit_result = commit_rule_import(
            {
                "db_path": str(db_path),
                "domain": "placeholders",
                "plan_token": prepare_result.plan_token,
                "backup_path": None,
            }
        )
        return _placeholder_rule_runtime_commit_report(
            result=commit_result,
            prepare_result=prepare_result,
            game_title=game_title,
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
        return _placeholder_rule_runtime_prepare_report(
            result=prepare_result,
            source_label="structured-placeholder-rules",
            game_title=game_title,
            sample_count=len(sample_texts),
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
    ) -> AgentReport:
        """导入当前游戏专用结构化占位符规则。"""
        _ = confirm_empty
        try:
            rules_payload = load_structured_placeholder_rules_import_payload(rules_text)
            async with await self.game_registry.open_game(game_title) as session:
                setting = load_setting(self.setting_path, source_language=session.source_language)
                db_path = session.db_path
                prepare_result = prepare_rule_import(
                    _placeholder_rule_runtime_payload(
                        mode="import",
                        domain="structured_placeholders",
                        rules_payload=rules_payload,
                        setting=setting,
                        db_path=db_path,
                    )
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
        if prepare_result.errors:
            return _placeholder_rule_runtime_prepare_report(
                result=prepare_result,
                source_label="structured-placeholder-rules",
                game_title=game_title,
                sample_count=0,
            )
        if prepare_result.plan_token is None:
            raise RuntimeError("结构化占位符规则导入缺少 rule_runtime plan token")

        commit_result = commit_rule_import(
            {
                "db_path": str(db_path),
                "domain": "structured_placeholders",
                "plan_token": prepare_result.plan_token,
                "backup_path": None,
            }
        )
        return _placeholder_rule_runtime_commit_report(
            result=commit_result,
            prepare_result=prepare_result,
            game_title=game_title,
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
