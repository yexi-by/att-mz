"""Agent 工具箱 CoverageAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentReport,
    AgentServiceContext,
    TextRules,
    TextScopeService,
    _build_coverage_report,
    _nonstandard_data_skipped_file_names,
    _nonstandard_data_skipped_warnings,
    _string_lines_to_json_array,
    _text_scope_blocking_errors,
    issue,
    load_setting,
)
from app.application.flow_gate import collect_placeholder_candidate_review_warnings


class CoverageAgentMixin:
    """承载 AgentToolkitService 的 CoverageAgentMixin 命令族。"""

    async def text_scope(
        self: AgentServiceContext,
        *,
        game_title: str,
        include_write_probe: bool = False,
    ) -> AgentReport:
        """输出当前游戏统一文本清单。"""
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
            nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
            scope = await TextScopeService().build(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
                include_write_probe=include_write_probe,
            )
            placeholder_review_warnings = await collect_placeholder_candidate_review_warnings(
                session=session,
                scope=scope,
                text_rules=text_rules,
                custom_placeholder_rules_supplied=False,
            )
        translated_paths = {item.location_path for item in translated_items}
        inactive_entries = [
            entry
            for entry in scope.entries
            if not entry.enters_translation
        ]
        unwritable_entries = scope.unwritable_entries
        errors = _text_scope_blocking_errors(scope)
        warnings = [
            *_nonstandard_data_skipped_warnings(nonstandard_data_rules),
            *(issue(warning.code, warning.message) for warning in placeholder_review_warnings),
        ]
        skipped_file_names = _nonstandard_data_skipped_file_names(nonstandard_data_rules)
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "entry_count": len(scope.entries),
                "extractable_count": len(scope.active_paths),
                "translated_count": len(translated_paths & scope.active_paths),
                "writable_count": len(scope.writable_paths),
                "unwritable_count": len(unwritable_entries),
                "inactive_rule_hit_count": len(inactive_entries),
                "stale_plugin_rule_count": len(scope.stale_plugin_rules),
                "nonstandard_data_skipped_file_count": len(skipped_file_names),
                "write_back_probe_failed": bool(scope.write_back_probe_error),
                "write_back_probe_enabled": scope.write_back_probe_enabled,
            },
            details={
                "entries": scope.entries_json(),
                "unwritable_items": [entry.to_json_object() for entry in unwritable_entries],
                "stale_plugin_rules": scope.stale_plugin_rules_json(),
                "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_file_names),
                "write_back_probe_error": scope.write_back_probe_error,
                "write_back_probe_enabled": scope.write_back_probe_enabled,
            },
        )

    async def audit_coverage(
        self: AgentServiceContext,
        *,
        game_title: str,
        include_write_probe: bool = False,
    ) -> AgentReport:
        """审计规则命中、文本清单、已保存译文和写入范围是否一致。"""
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
            nonstandard_data_rules = await session.read_nonstandard_data_text_rules()
            scope = await TextScopeService().build(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                translated_items=translated_items,
                include_write_probe=include_write_probe,
            )
            placeholder_review_warnings = await collect_placeholder_candidate_review_warnings(
                session=session,
                scope=scope,
                text_rules=text_rules,
                custom_placeholder_rules_supplied=False,
            )
        report = _build_coverage_report(
            scope=scope,
            translated_items=translated_items,
            text_rules=text_rules,
        )
        skipped_file_names = _nonstandard_data_skipped_file_names(nonstandard_data_rules)
        return AgentReport.from_parts(
            errors=report.errors,
            warnings=[
                *report.warnings,
                *_nonstandard_data_skipped_warnings(nonstandard_data_rules),
                *(issue(warning.code, warning.message) for warning in placeholder_review_warnings),
            ],
            summary={
                **report.summary,
                "nonstandard_data_skipped_file_count": len(skipped_file_names),
            },
            details={
                **report.details,
                "nonstandard_data_skipped_files": _string_lines_to_json_array(skipped_file_names),
            },
        )
