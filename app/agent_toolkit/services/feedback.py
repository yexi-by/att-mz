"""Agent 工具箱 FeedbackAgentMixin 子服务。"""
# pyright: reportPrivateUsage=false
# mixin 通过 AgentToolkitService 组合成同一个服务边界，允许调用同门面的受保护核心方法。

from .common import (
    AgentIssue,
    AgentReport,
    AgentServiceContext,
    JsonObject,
    Path,
    TextRules,
    _classify_feedback_occurrences,
    _collect_feedback_text_occurrences,
    _count_feedback_gap_types,
    _read_feedback_texts,
    issue,
    load_setting,
)
from app.text_index import detect_text_index_invalidations, text_index_items_to_scope


class FeedbackAgentMixin:
    """承载 AgentToolkitService 的 FeedbackAgentMixin 命令族。"""

    async def verify_feedback_text(self: AgentServiceContext, *, game_title: str, input_path: Path) -> AgentReport:
        """按反馈原文清单反查真实游戏文件中是否仍残留对应文本。"""
        try:
            feedback_texts = await _read_feedback_texts(input_path)
        except Exception as error:
            return AgentReport.from_parts(
                errors=[issue("feedback_text_file", f"反馈原文清单不可读: {type(error).__name__}: {error}")],
                warnings=[],
                summary={"input": str(input_path), "feedback_text_count": 0, "occurrence_count": 0},
                details={},
            )
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
            active_game_data = await self._load_active_runtime_game_data(
                session,
                include_plugin_source_files=True,
            )
            occurrences = await _collect_feedback_text_occurrences(
                game_data=active_game_data,
                feedback_texts=feedback_texts,
            )
            index_invalidations = await detect_text_index_invalidations(
                session=session,
                text_rules=text_rules,
            )
            text_index_status = "used"
            text_index_rebuild_summary: JsonObject = {}
            if index_invalidations:
                rebuild_report = await self.rebuild_text_index(
                    game_title=game_title,
                    include_write_probe=False,
                )
                text_index_status = "rebuilt"
                text_index_rebuild_summary = {key: value for key, value in rebuild_report.summary.items()}
                if rebuild_report.status == "error":
                    errors = [*rebuild_report.errors]
                    if occurrences:
                        errors.insert(0, issue("feedback_text_still_exists", f"真实游戏文件中仍存在 {len(occurrences)} 处反馈原文"))
                    return AgentReport.from_parts(
                        errors=errors,
                        warnings=[*rebuild_report.warnings],
                        summary={
                            "input": str(input_path),
                            "feedback_text_count": len(feedback_texts),
                            "occurrence_count": len(occurrences),
                            "text_index_status": "rebuild_failed",
                            "text_index_rebuild_summary": text_index_rebuild_summary,
                        },
                        details={
                            "occurrences": occurrences,
                            "text_index_invalidations": [
                                {
                                    "reason_key": invalidation.reason_key,
                                    "detail": invalidation.detail,
                                    "created_at": invalidation.created_at,
                                }
                                for invalidation in index_invalidations
                            ],
                        },
                    )
            index_records = await session.read_text_index_items()
            translated_paths = await session.read_translation_location_paths()
            scope = text_index_items_to_scope(index_records, translated_paths=translated_paths)
        classified_occurrences = _classify_feedback_occurrences(
            occurrences=occurrences,
            scope=scope,
        )
        gap_counts = _count_feedback_gap_types(classified_occurrences)
        errors: list[AgentIssue] = []
        if occurrences:
            errors.append(issue("feedback_text_still_exists", f"真实游戏文件中仍存在 {len(occurrences)} 处反馈原文"))
        if scope.stale_plugin_rules:
            errors.append(issue("stale_plugin_rules", f"发现 {len(scope.stale_plugin_rules)} 个过期插件规则，请重新导出并导入插件规则"))
        if scope.write_back_probe_error:
            errors.append(issue("write_probe_failed", scope.write_back_probe_error))
        return AgentReport.from_parts(
            errors=errors,
            warnings=[],
            summary={
                "input": str(input_path),
                "feedback_text_count": len(feedback_texts),
                "occurrence_count": len(occurrences),
                "rule_gap_count": gap_counts.get("rule_gap", 0),
                "translation_gap_count": gap_counts.get("translation_gap", 0),
                "write_gap_count": gap_counts.get("write_gap", 0),
                "plugin_source_hardcoded_count": gap_counts.get("plugin_source_hardcoded", 0),
                "text_index_status": text_index_status,
                "text_index_rebuild_summary": text_index_rebuild_summary,
            },
            details={
                "occurrences": classified_occurrences,
                "stale_plugin_rules": scope.stale_plugin_rules_json(),
                "write_back_probe_error": scope.write_back_probe_error,
            },
        )
