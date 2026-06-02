"""Agent 工具箱非标准 data 文件文本子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    Path,
    TextRules,
    issue,
    load_setting,
)
from app.nonstandard_data import (
    build_nonstandard_data_rule_records_from_import,
    build_nonstandard_data_scan,
    export_nonstandard_data_workspace,
    parse_nonstandard_data_rule_import_text,
    validate_nonstandard_data_rules,
)
from app.rmmz.game_file_view import GameFileView


class NonstandardDataAgentMixin:
    """承载非标准 data 文件文本扫描、导出和规则校验命令。"""

    async def scan_nonstandard_data(
        self: AgentServiceContext,
        *,
        game_title: str,
    ) -> AgentReport:
        """扫描非标准 data 文件文本风险。"""
        try:
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
                scan = await build_nonstandard_data_scan(
                    layout=game_data.layout,
                    source_view=GameFileView.TRANSLATION_SOURCE,
                    text_rules=text_rules,
                )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("nonstandard_data_scan_failed", f"非标准 data 文件文本扫描失败: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "game": game_title,
                    "report_detail_mode": "full",
                    "nonstandard_file_count": 0,
                    "candidate_count": 0,
                    "high_risk": False,
                },
                details={"files": [], "candidates": []},
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=_scan_warnings(scan_candidate_count=len(scan.candidates)),
            summary={
                "game": game_title,
                "report_detail_mode": "full",
                **scan.summary_json(),
            },
            details=scan.details_json(),
        )

    async def export_nonstandard_data_json(
        self: AgentServiceContext,
        *,
        game_title: str,
        output_dir: Path,
    ) -> AgentReport:
        """导出非标准 data 文件候选报告和原始 JSON 副本。"""
        try:
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
                scan = await build_nonstandard_data_scan(
                    layout=game_data.layout,
                    source_view=GameFileView.TRANSLATION_SOURCE,
                    text_rules=text_rules,
                )
            export_details = await export_nonstandard_data_workspace(
                scan=scan,
                output_dir=output_dir,
            )
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("nonstandard_data_export_failed", f"非标准 data 文件文本导出失败: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "game": game_title,
                    "output_dir": str(output_dir),
                    "report_detail_mode": "full",
                    "nonstandard_file_count": 0,
                    "candidate_count": 0,
                    "high_risk": False,
                },
                details={},
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=_scan_warnings(scan_candidate_count=len(scan.candidates)),
            summary={
                "game": game_title,
                "output_dir": str(output_dir.resolve()),
                "report_detail_mode": "full",
                **scan.summary_json(),
            },
            details={
                **export_details,
                **scan.details_json(),
            },
        )

    async def validate_nonstandard_data_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """校验非标准 data 文件文本规则。"""
        try:
            import_file = parse_nonstandard_data_rule_import_text(rules_text)
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
                scan = await build_nonstandard_data_scan(
                    layout=game_data.layout,
                    source_view=GameFileView.TRANSLATION_SOURCE,
                    text_rules=text_rules,
                )
            validation = validate_nonstandard_data_rules(scan=scan, import_file=import_file)
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("nonstandard_data_rules_invalid", f"非标准 data 文件文本规则不可导入: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "game": game_title,
                    "report_detail_mode": "full",
                    "file_count": 0,
                    "path_rule_count": 0,
                    "excluded_path_rule_count": 0,
                    "skipped_file_count": 0,
                    "candidate_count": 0,
                    "reviewed_candidate_count": 0,
                    "unreviewed_candidate_count": 0,
                },
                details={"rules": []},
            )
        warnings: list[AgentIssue] = []
        if validation.skipped_files:
            warnings.append(
                issue(
                    "nonstandard_data_files_skipped",
                    f"已确认跳过 {len(validation.skipped_files)} 个非标准 data 文件，后续报告仍会提示这些文件可能残留源文",
                )
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "game": game_title,
                "report_detail_mode": "full",
                "file_count": len(validation.rules),
                "path_rule_count": validation.rule_count,
                "excluded_path_rule_count": validation.excluded_rule_count,
                "skipped_file_count": len(validation.skipped_files),
                "candidate_count": len(scan.candidates),
                "reviewed_candidate_count": validation.reviewed_candidate_count,
                "unreviewed_candidate_count": len(validation.unreviewed_candidate_paths),
            },
            details=validation.details,
        )

    async def import_nonstandard_data_rules(
        self: AgentServiceContext,
        *,
        game_title: str,
        rules_text: str,
    ) -> AgentReport:
        """导入非标准 data 文件文本规则到当前游戏数据库。"""
        try:
            import_file = parse_nonstandard_data_rule_import_text(rules_text)
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
                scan = await build_nonstandard_data_scan(
                    layout=game_data.layout,
                    source_view=GameFileView.TRANSLATION_SOURCE,
                    text_rules=text_rules,
                )
                rule_records = build_nonstandard_data_rule_records_from_import(
                    scan=scan,
                    import_file=import_file,
                )
                await session.replace_nonstandard_data_text_rules(rule_records)
            validation = validate_nonstandard_data_rules(scan=scan, import_file=import_file)
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("nonstandard_data_rules_invalid", f"非标准 data 文件文本规则导入失败: {type(error).__name__}: {error}")],
                warnings=[],
                summary={
                    "game": game_title,
                    "report_detail_mode": "full",
                    "file_count": 0,
                    "path_rule_count": 0,
                    "excluded_path_rule_count": 0,
                    "skipped_file_count": 0,
                    "candidate_count": 0,
                    "reviewed_candidate_count": 0,
                    "unreviewed_candidate_count": 0,
                },
                details={"rules": []},
            )
        warnings: list[AgentIssue] = []
        if validation.skipped_files:
            warnings.append(
                issue(
                    "nonstandard_data_files_skipped",
                    f"已确认跳过 {len(validation.skipped_files)} 个非标准 data 文件，后续报告仍会提示这些文件可能残留源文",
                )
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=warnings,
            summary={
                "game": game_title,
                "report_detail_mode": "full",
                "file_count": len(validation.rules),
                "path_rule_count": validation.rule_count,
                "excluded_path_rule_count": validation.excluded_rule_count,
                "skipped_file_count": len(validation.skipped_files),
                "candidate_count": len(scan.candidates),
                "reviewed_candidate_count": validation.reviewed_candidate_count,
                "unreviewed_candidate_count": len(validation.unreviewed_candidate_paths),
            },
            details=validation.details,
        )


def _scan_warnings(*, scan_candidate_count: int) -> list[AgentIssue]:
    """根据扫描候选数量生成风险告警。"""
    if scan_candidate_count == 0:
        return []
    return [
        issue(
            "nonstandard_data_high_risk",
            f"发现 {scan_candidate_count} 条非标准 data 文件文本候选，请导出工作区并导入规则或按文件确认跳过后再继续正文翻译",
        )
    ]


__all__ = ["NonstandardDataAgentMixin"]
