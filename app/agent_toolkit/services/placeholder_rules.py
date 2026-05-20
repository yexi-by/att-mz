"""Agent 工具箱 PlaceholderRuleAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

import re

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    DEFAULT_SOURCE_LANGUAGE,
    JsonArray,
    JsonObject,
    Path,
    PlaceholderRuleRecord,
    Sequence,
    SourceLanguage,
    StructuredPlaceholderRule,
    StructuredPlaceholderRuleRecord,
    TextRules,
    TranslationData,
    TranslationItem,
    _append_placeholder_rule_safety_issues,
    _build_custom_placeholder_rule_draft,
    _build_joined_text_boundary_warnings,
    _build_unprotected_control_warnings,
    _collect_placeholder_preview_samples,
    _collect_unprotected_control_warning_samples,
    _joined_text_boundary_markers,
    _placeholder_preview_loses_visible_source_text,
    _preview_placeholder_sample,
    _string_lines_to_json_array,
    aiofiles,
    count_uncovered_candidates,
    issue,
    json,
    load_custom_placeholder_rules_text,
    load_structured_placeholder_rules_text,
    load_setting,
    placeholder_candidates_to_details,
    scan_placeholder_candidates,
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
            game_data = await self._load_game_data(session)
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

    async def validate_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str | None,
        custom_placeholder_rules_text: str | None,
        sample_texts: Sequence[str],
    ) -> AgentReport:
        """校验自定义占位符规则，并预览样本文本的替换与还原结果。"""
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
        setting_source_language: SourceLanguage = DEFAULT_SOURCE_LANGUAGE
        source_label = "--placeholder-rules"
        if custom_placeholder_rules_text is None and game_title is not None:
            source_label = "当前游戏数据库"
        elif custom_placeholder_rules_text is None:
            source_label = "空规则"

        try:
            if game_title is not None:
                async with await self.game_registry.open_game(game_title) as session:
                    setting_source_language = session.source_language
                    custom_rules = await self._resolve_custom_rules(
                        session=session,
                        custom_placeholder_rules_text=custom_placeholder_rules_text,
                    )
                    structured_rules = await self._resolve_structured_rules(session=session)
                    if not sample_texts:
                        game_data = await self._load_game_data(session)
                        setting = load_setting(self.setting_path, source_language=session.source_language)
                        preview_rules = TextRules.from_setting(
                            setting.text_rules,
                            custom_placeholder_rules=custom_rules,
                            structured_placeholder_rules=structured_rules,
                        )
                        translation_data_map = await self._extract_active_translation_data_map(
                            session=session,
                            game_data=game_data,
                            text_rules=preview_rules,
                        )
                        sample_texts = _collect_placeholder_preview_samples(translation_data_map, preview_rules)
                        if not sample_texts:
                            sample_texts = _collect_unprotected_control_warning_samples(translation_data_map, preview_rules)
            elif custom_placeholder_rules_text is None:
                custom_rules = ()
                structured_rules = ()
            else:
                custom_rules = load_custom_placeholder_rules_text(custom_placeholder_rules_text)
                structured_rules = ()
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

        try:
            setting = load_setting(self.setting_path, source_language=setting_source_language)
            text_rules = TextRules.from_setting(
                setting.text_rules,
                custom_placeholder_rules=custom_rules,
                structured_placeholder_rules=structured_rules,
            )
        except Exception as error:
            errors.append(issue("setting", f"配置加载失败: {type(error).__name__}: {error}"))
            return AgentReport.from_parts(
                errors=errors,
                warnings=warnings,
                summary={
                    "source": source_label,
                    "rule_count": len(custom_rules),
                    "sample_count": len(sample_texts),
                },
                details={},
            )

        rule_details: JsonArray = []
        for rule in custom_rules:
            placeholder_preview = text_rules.format_custom_placeholder(
                template=rule.placeholder_template,
                index=1,
            )
            _append_placeholder_rule_safety_issues(
                rule=rule,
                errors=errors,
                warnings=warnings,
            )
            rule_details.append(
                {
                    "pattern": rule.pattern_text,
                    "placeholder_template": rule.placeholder_template,
                    "placeholder_preview": placeholder_preview,
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
                            "placeholder_rule_loses_translatable_text",
                            "占位符规则把含源语言正文的样本文本整体遮蔽，模型将看不到需要翻译的内容",
                        )
                    )
            except Exception as error:
                errors.append(
                    issue(
                        "placeholder_preview",
                        f"样本文本预览失败: {type(error).__name__}: {error}",
                    )
                )
        warnings.extend(_build_unprotected_control_warnings(sample_texts, text_rules))

        if not custom_rules:
            warnings.append(issue("placeholder_rules_empty", "当前没有自定义占位符规则"))

        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "source": source_label,
                "rule_count": len(custom_rules),
                "sample_count": len(sample_texts),
            },
            details={
                "rules": rule_details,
                "samples": sample_details,
            },
        )

    async def import_placeholder_rules(self: AgentServiceContext, *, game_title: str, rules_text: str) -> AgentReport:
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
        async with await self.game_registry.open_game(game_title) as session:
            await session.replace_placeholder_rules(rule_records)
        return AgentReport.from_parts(
            errors=[],
            warnings=validation_report.warnings
            if rule_records
            else [
                *validation_report.warnings,
                issue("placeholder_rules_empty", "已导入空自定义占位符规则"),
            ],
            summary={
                "game": game_title,
                "imported_rule_count": len(rule_records),
                "validated_rule_count": validation_report.summary.get("rule_count", len(rule_records)),
                "sample_count": validation_report.summary.get("sample_count", 0),
            },
            details={
                "validation": {
                    "summary": validation_report.summary,
                    "details": validation_report.details,
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
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = []
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
                    game_data = await self._load_game_data(session)
                    translation_data_map = await self._extract_active_translation_data_map(
                        session=session,
                        game_data=game_data,
                        text_rules=text_rules,
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
                game_data = await self._load_game_data(session)
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

    async def import_structured_placeholder_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
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
        async with await self.game_registry.open_game(game_title) as session:
            await session.replace_structured_placeholder_rules(rule_records)
        return AgentReport.from_parts(
            errors=[],
            warnings=validation_report.warnings
            if rule_records
            else [
                *validation_report.warnings,
                issue("structured_placeholder_rules_empty", "已导入空结构化占位符规则"),
            ],
            summary={
                "game": game_title,
                "imported_rule_count": len(rule_records),
                "validated_rule_count": validation_report.summary.get("rule_count", len(rule_records)),
                "sample_count": validation_report.summary.get("sample_count", 0),
            },
            details={
                "validation": {
                    "summary": validation_report.summary,
                    "details": validation_report.details,
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
            game_data = await self._load_game_data(session)
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


STRUCTURED_SHELL_CANDIDATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<[^<>\r\n]{1,160}(?:[:：=])[^<>\r\n]{0,240}>"),
    re.compile(r"◆<[^<>\r\n]{1,160}>[^\s<>\r\n]?"),
    re.compile(r"【[^】\r\n]{1,160}[:：][^】\r\n]{0,240}】"),
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


def _collect_structured_placeholder_preview_samples(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: Sequence[StructuredPlaceholderRule],
) -> list[str]:
    """为结构化占位符规则收集少量当前正文样本。"""
    samples: list[str] = []
    seen_samples: set[str] = set()
    for item in _iter_translation_items_from_map(translation_data_map):
        for text in item.original_lines:
            if not _line_matches_structured_rules(text=text, structured_rules=structured_rules):
                continue
            if text in seen_samples:
                continue
            samples.append(text)
            seen_samples.add(text)
            if len(samples) >= 10:
                return samples
    return samples


def _collect_structured_placeholder_candidate_details(
    *,
    translation_data_map: dict[str, TranslationData],
    structured_rules: Sequence[StructuredPlaceholderRule],
) -> JsonArray:
    """扫描当前正文中的结构化协议外壳候选和规则覆盖情况。"""
    details: JsonArray = []
    seen_candidates: set[tuple[str, int, int, int, str]] = set()
    for item in _iter_translation_items_from_map(translation_data_map):
        for line_index, line in enumerate(item.original_lines):
            covered_ranges = _structured_rule_covered_ranges(
                text=line,
                structured_rules=structured_rules,
            )
            for start, end, candidate in _iter_structured_shell_candidate_matches(line):
                key = (item.location_path, line_index, start, end, candidate)
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                matching_rules = [
                    rule_name
                    for start, end, rule_name in covered_ranges
                    if start <= key[2] and end >= key[3]
                ]
                detail: JsonObject = {
                    "location_path": item.location_path,
                    "line_number": line_index + 1,
                    "candidate": candidate,
                    "covered": bool(matching_rules),
                    "matching_rules": _string_lines_to_json_array(matching_rules),
                }
                details.append(detail)
    return details


def _iter_translation_items_from_map(translation_data_map: dict[str, TranslationData]) -> list[TranslationItem]:
    """从正文提取结果中取出翻译条目。"""
    items: list[TranslationItem] = []
    for translation_data in translation_data_map.values():
        items.extend(translation_data.translation_items)
    return items


def _line_matches_structured_rules(
    *,
    text: str,
    structured_rules: Sequence[StructuredPlaceholderRule],
) -> bool:
    """判断一行文本是否命中任一结构化规则。"""
    return any(rule.pattern.search(text) is not None for rule in structured_rules)


def _iter_structured_shell_candidate_matches(text: str) -> list[tuple[int, int, str]]:
    """扫描常见结构化协议外壳候选。"""
    matches: list[tuple[int, int, str]] = []
    for pattern in STRUCTURED_SHELL_CANDIDATE_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), match.group(0)))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    selected: list[tuple[int, int, str]] = []
    protected_until = -1
    for start, end, candidate in matches:
        if start < protected_until:
            continue
        selected.append((start, end, candidate))
        protected_until = end
    return selected


def _structured_rule_covered_ranges(
    *,
    text: str,
    structured_rules: Sequence[StructuredPlaceholderRule],
) -> list[tuple[int, int, str]]:
    """返回结构化规则完整命中范围。"""
    ranges: list[tuple[int, int, str]] = []
    for rule in structured_rules:
        for match in rule.pattern.finditer(text):
            ranges.append((match.start(), match.end(), rule.rule_name))
    return ranges
