"""Agent 工具箱 PlaceholderRuleAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentReport,
    AgentServiceContext,
    JsonArray,
    JsonObject,
    Path,
    PlaceholderRuleRecord,
    Sequence,
    StructuredPlaceholderRule,
    StructuredPlaceholderRuleRecord,
    TextRules,
    _build_custom_placeholder_rule_draft,
    _build_joined_text_boundary_warnings,
    _build_placeholder_coverage_report_with_context,
    _build_structured_placeholder_coverage_report_with_context,
    _build_unprotected_control_warnings,
    _collect_unprotected_control_warning_samples,
    _joined_text_boundary_markers,
    _validate_placeholder_rules_with_context,
    _validate_structured_placeholder_rules_with_context,
    aiofiles,
    count_uncovered_candidates,
    issue,
    json,
    load_custom_placeholder_rules_text,
    load_structured_placeholder_rules_text,
    load_setting,
    scan_placeholder_candidates,
)
from app.application.flow_gate import collect_external_text_rule_gate_errors, ensure_empty_rule_import_allowed
from app.rule_review import (
    PLACEHOLDER_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    placeholder_rule_scope_hash,
    structured_placeholder_rule_scope_hash,
)


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
            game_data = await self._load_translation_source_game_data(session)
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
            translation_data_map = await self._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
            )

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
        """校验自定义占位符规则，并预览样本文本的替换与还原结果。"""
        source_label = "--placeholder-rules"
        if custom_placeholder_rules_text is None and game_title is not None:
            source_label = "当前游戏数据库"
        elif custom_placeholder_rules_text is None:
            source_label = "空规则"

        try:
            if game_title is not None:
                async with await self.game_registry.open_game(game_title) as session:
                    setting = load_setting(self.setting_path, source_language=session.source_language)
                    custom_rules = await self._resolve_custom_rules(
                        session=session,
                        custom_placeholder_rules_text=custom_placeholder_rules_text,
                    )
                    structured_rules = await self._resolve_structured_rules(session=session)
                    if not sample_texts:
                        game_data = await self._load_translation_source_game_data(session)
                        extraction_rules = TextRules.from_setting(
                            setting.text_rules,
                            structured_placeholder_rules=structured_rules,
                        )
                        translation_data_map = await self._extract_active_translation_data_map(
                            session=session,
                            game_data=game_data,
                            text_rules=extraction_rules,
                        )
                    else:
                        translation_data_map = None
            elif custom_placeholder_rules_text is None:
                setting = load_setting(self.setting_path)
                custom_rules = ()
                structured_rules = ()
                translation_data_map = None
            else:
                setting = load_setting(self.setting_path)
                custom_rules = load_custom_placeholder_rules_text(custom_placeholder_rules_text)
                structured_rules = ()
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

        return _validate_placeholder_rules_with_context(
            source_label=source_label,
            setting_text_rules=setting.text_rules,
            custom_rules=custom_rules,
            structured_rules=structured_rules,
            sample_texts=sample_texts,
            translation_data_map=translation_data_map,
        )

    async def import_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
    ) -> AgentReport:
        """校验并导入当前游戏专用自定义占位符规则。"""
        validation_report = await self.validate_placeholder_rules(
            game_title=game_title,
            custom_placeholder_rules_text=rules_text,
            sample_texts=[],
        )
        if validation_report.errors:
            return AgentReport.from_parts(
                errors=validation_report.errors,
                warnings=validation_report.warnings,
                summary={
                    "game": game_title,
                    "imported_rule_count": 0,
                    "validated_rule_count": validation_report.summary.get("rule_count", 0),
                    "sample_count": validation_report.summary.get("sample_count", 0),
                },
                details={
                    "validation": {
                        "summary": validation_report.summary,
                        "details": validation_report.details,
                    }
                },
            )

        custom_rules = load_custom_placeholder_rules_text(rules_text)
        rule_records = [
            PlaceholderRuleRecord(
                pattern_text=rule.pattern_text,
                placeholder_template=rule.placeholder_template,
            )
            for rule in custom_rules
        ]
        coverage_report = await self.scan_placeholder_candidates(
            game_title=game_title,
            custom_placeholder_rules_text=rules_text,
        )
        uncovered_count = _summary_int(coverage_report.summary, "uncovered_count")
        if not rule_records:
            try:
                ensure_empty_rule_import_allowed(
                    rule_label="普通占位符规则",
                    confirm_empty=confirm_empty,
                    candidate_count=uncovered_count,
                )
            except RuntimeError as error:
                return AgentReport.from_parts(
                    errors=[issue("placeholder_rules_empty_unconfirmed", str(error))],
                    warnings=validation_report.warnings,
                    summary={
                        "game": game_title,
                        "imported_rule_count": 0,
                        "validated_rule_count": validation_report.summary.get("rule_count", 0),
                        "sample_count": validation_report.summary.get("sample_count", 0),
                    },
                    details={
                        "validation": {
                            "summary": validation_report.summary,
                            "details": validation_report.details,
                        },
                        "coverage": {
                            "summary": coverage_report.summary,
                            "details": coverage_report.details,
                        },
                    },
                )
        candidate_details = _json_array_detail(coverage_report.details, "candidates")
        scope_hash = placeholder_rule_scope_hash(candidate_details)
        async with await self.game_registry.open_game(game_title) as session:
            await session.replace_placeholder_rules(rule_records)
            if uncovered_count:
                await session.replace_rule_review_state(
                    rule_domain=PLACEHOLDER_RULE_DOMAIN,
                    scope_hash=scope_hash,
                    reviewed_empty=not rule_records,
                )
            elif rule_records:
                await session.delete_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
            else:
                await session.replace_rule_review_state(
                    rule_domain=PLACEHOLDER_RULE_DOMAIN,
                    scope_hash=scope_hash,
                    reviewed_empty=True,
                )
        warnings = [*validation_report.warnings]
        if not rule_records:
            warnings.append(issue("placeholder_rules_empty", "已导入空普通占位符规则"))
        if uncovered_count:
            warnings.append(
                issue(
                    "placeholder_uncovered_reviewed",
                    f"仍有 {uncovered_count} 个未覆盖的疑似自定义控制符；本次导入已确认当前候选风险",
                )
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "game": game_title,
                "imported_rule_count": len(rule_records),
                "validated_rule_count": validation_report.summary.get("rule_count", len(rule_records)),
                "sample_count": validation_report.summary.get("sample_count", 0),
                "uncovered_count": uncovered_count,
            },
            details={
                "validation": {
                    "summary": validation_report.summary,
                    "details": validation_report.details,
                },
                "coverage": {
                    "summary": coverage_report.summary,
                    "details": coverage_report.details,
                }
            },
        )

    async def validate_structured_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        sample_texts: Sequence[str],
    ) -> AgentReport:
        """校验结构化占位符规则，并预览协议外壳保护效果。"""
        try:
            structured_rules = load_structured_placeholder_rules_text(rules_text)
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
                if not sample_texts:
                    game_data = await self._load_translation_source_game_data(session)
                    translation_data_map = await self._extract_active_translation_data_map(
                        session=session,
                        game_data=game_data,
                        text_rules=text_rules,
                    )
                else:
                    translation_data_map = None
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
        return _validate_structured_placeholder_rules_with_context(
            game_title=game_title,
            rules_text=rules_text,
            setting_text_rules=setting.text_rules,
            custom_rules=custom_rules,
            sample_texts=sample_texts,
            translation_data_map=translation_data_map,
        )

    async def scan_structured_placeholder_candidates(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """扫描结构化规则对当前正文中协议外壳候选的覆盖情况。"""
        try:
            structured_rules = load_structured_placeholder_rules_text(rules_text)
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
                game_data = await self._load_translation_source_game_data(session)
                translation_data_map = await self._extract_active_translation_data_map(
                    session=session,
                    game_data=game_data,
                    text_rules=text_rules,
                )
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
            structured_rules=structured_rules,
        )

    async def import_structured_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
        confirm_empty: bool = False,
    ) -> AgentReport:
        """校验并导入当前游戏专用结构化占位符规则。"""
        validation_report = await self.validate_structured_placeholder_rules(
            game_title=game_title,
            rules_text=rules_text,
            sample_texts=[],
        )
        if validation_report.errors:
            return AgentReport.from_parts(
                errors=validation_report.errors,
                warnings=validation_report.warnings,
                summary={
                    "game": game_title,
                    "imported_rule_count": 0,
                    "validated_rule_count": validation_report.summary.get("rule_count", 0),
                    "sample_count": validation_report.summary.get("sample_count", 0),
                },
                details={
                    "validation": {
                        "summary": validation_report.summary,
                        "details": validation_report.details,
                    }
                },
            )

        structured_rules = load_structured_placeholder_rules_text(rules_text)
        rule_records = _structured_placeholder_rule_records_from_runtime(structured_rules)
        coverage_report = await self.scan_structured_placeholder_candidates(
            game_title=game_title,
            rules_text=rules_text,
        )
        uncovered_count = _summary_int(coverage_report.summary, "uncovered_count")
        if not rule_records:
            try:
                ensure_empty_rule_import_allowed(
                    rule_label="结构化占位符规则",
                    confirm_empty=confirm_empty,
                    candidate_count=uncovered_count,
                )
            except RuntimeError as error:
                return AgentReport.from_parts(
                    errors=[issue("structured_placeholder_rules_empty_unconfirmed", str(error))],
                    warnings=validation_report.warnings,
                    summary={
                        "game": game_title,
                        "imported_rule_count": 0,
                        "validated_rule_count": validation_report.summary.get("rule_count", 0),
                        "sample_count": validation_report.summary.get("sample_count", 0),
                    },
                    details={
                        "validation": {
                            "summary": validation_report.summary,
                            "details": validation_report.details,
                        },
                        "coverage": {
                            "summary": coverage_report.summary,
                            "details": coverage_report.details,
                        },
                    },
                )
        candidate_details = _json_array_detail(coverage_report.details, "candidates")
        scope_hash = structured_placeholder_rule_scope_hash(candidate_details)
        async with await self.game_registry.open_game(game_title) as session:
            await session.replace_structured_placeholder_rules(rule_records)
            if uncovered_count:
                await session.replace_rule_review_state(
                    rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
                    scope_hash=scope_hash,
                    reviewed_empty=not rule_records,
                )
            elif rule_records:
                await session.delete_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
            else:
                await session.replace_rule_review_state(
                    rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
                    scope_hash=scope_hash,
                    reviewed_empty=True,
                )
        warnings = [*validation_report.warnings]
        if not rule_records:
            warnings.append(issue("structured_placeholder_rules_empty", "已导入空结构化占位符规则"))
        if uncovered_count:
            warnings.append(
                issue(
                    "structured_placeholder_uncovered_reviewed",
                    f"仍有 {uncovered_count} 个未被结构化规则覆盖的协议外壳候选；本次导入已确认当前候选风险",
                )
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "game": game_title,
                "imported_rule_count": len(rule_records),
                "validated_rule_count": validation_report.summary.get("rule_count", len(rule_records)),
                "sample_count": validation_report.summary.get("sample_count", 0),
                "uncovered_count": uncovered_count,
            },
            details={
                "validation": {
                    "summary": validation_report.summary,
                    "details": validation_report.details,
                },
                "coverage": {
                    "summary": coverage_report.summary,
                    "details": coverage_report.details,
                }
            },
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
            game_data = await self._load_translation_source_game_data(session)
            external_rule_errors = await collect_external_text_rule_gate_errors(
                session=session,
                game_data=game_data,
                setting=setting,
                text_rules=empty_rules,
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
            translation_data_map = await self._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=empty_rules,
            )
        candidates = scan_placeholder_candidates(translation_data_map, empty_rules)
        uncovered_count_before_draft = count_uncovered_candidates(candidates)
        manual_boundary_markers = _joined_text_boundary_markers(candidates)
        draft_rules = _build_custom_placeholder_rule_draft(candidates)
        draft_custom_rules = load_custom_placeholder_rules_text(json.dumps(draft_rules, ensure_ascii=False))
        draft_text_rules = TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=draft_custom_rules,
            structured_placeholder_rules=structured_rules,
        )
        draft_preview_candidates = scan_placeholder_candidates(translation_data_map, draft_text_rules)
        uncovered_count_after_draft_preview = count_uncovered_candidates(draft_preview_candidates)
        warnings = _build_unprotected_control_warnings(
            _collect_unprotected_control_warning_samples(translation_data_map, empty_rules),
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
                "candidate_count": len(candidates),
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


def _structured_placeholder_rule_records_from_runtime(
    rules: Sequence[StructuredPlaceholderRule],
) -> list[StructuredPlaceholderRuleRecord]:
    """把运行时结构化规则转换成数据库记录。"""
    return [
        StructuredPlaceholderRuleRecord(
            rule_name=rule.rule_name,
            rule_type=rule.rule_type,
            pattern_text=rule.pattern_text,
            translatable_group=rule.translatable_group,
            protected_groups=dict(rule.protected_groups),
        )
        for rule in rules
    ]


def _summary_int(summary: JsonObject, key: str) -> int:
    """从报告 summary 中读取整数计数字段。"""
    raw_value = summary.get(key)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise RuntimeError(f"报告缺少有效计数字段: {key}")
    return raw_value


def _json_array_detail(details: JsonObject, key: str) -> JsonArray:
    """从报告 details 中读取 JSON 数组字段。"""
    raw_value = details.get(key)
    if not isinstance(raw_value, list):
        raise RuntimeError(f"报告缺少有效数组字段: {key}")
    return [item for item in raw_value]
