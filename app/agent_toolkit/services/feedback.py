"""Agent 工具箱 FeedbackAgentMixin 子服务。"""
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
    TextRules,
    _collect_feedback_text_occurrences,
    _count_feedback_gap_types,
    _read_feedback_texts,
    cast,
    issue,
    load_setting,
)
from app.persistence.records import TextFactV2Record, TextIndexItemRecord
from app.text_index import detect_text_index_invalidations
from app.text_facts import TextFactContractError, read_current_text_fact_records_v2


@dataclass(frozen=True, slots=True)
class _FeedbackFactEntry:
    """反馈归类所需的 v2 文本事实投影。"""

    location_path: str
    original_lines: list[str]
    can_write_back: bool
    translated: bool


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
            try:
                current_facts = await read_current_text_fact_records_v2(session, limit=None)
            except TextFactContractError as error:
                return AgentReport.from_parts(
                    errors=[issue("text_fact_contract", str(error))],
                    warnings=[],
                    summary={
                        "input": str(input_path),
                        "feedback_text_count": len(feedback_texts),
                        "occurrence_count": len(occurrences),
                        "text_index_status": text_index_status,
                        "text_index_rebuild_summary": text_index_rebuild_summary,
                    },
                    details={
                        "occurrences": occurrences,
                        "text_fact_contract_error": str(error),
                    },
                )
            facts_by_path = {fact.location_path: fact for fact in current_facts}
            missing_fact_paths = sorted(
                record.location_path
                for record in index_records
                if record.location_path not in facts_by_path
            )
            if missing_fact_paths:
                missing_message = (
                    f"当前文本索引有 {len(missing_fact_paths)} 条记录缺少 text fact v2，"
                    + "不能继续使用旧索引正文；请运行 rebuild-text-index 重新生成当前文本索引"
                )
                missing_fact_path_details = cast(JsonArray, missing_fact_paths[:20])
                return AgentReport.from_parts(
                    errors=[
                        issue(
                            "text_fact_v2_missing",
                            missing_message,
                        )
                    ],
                    warnings=[],
                    summary={
                        "input": str(input_path),
                        "feedback_text_count": len(feedback_texts),
                        "occurrence_count": len(occurrences),
                        "text_index_status": text_index_status,
                        "text_index_rebuild_summary": text_index_rebuild_summary,
                    },
                    details={
                        "occurrences": occurrences,
                        "missing_text_fact_location_paths": missing_fact_path_details,
                    },
                )
            translated_paths = await session.read_translation_location_paths()
            feedback_entries = _feedback_fact_entries_from_v2(
                index_records=index_records,
                facts_by_path=facts_by_path,
                translated_paths=translated_paths,
            )
        classified_occurrences = _classify_feedback_occurrences(
            occurrences=occurrences,
            entries=feedback_entries,
        )
        gap_counts = _count_feedback_gap_types(classified_occurrences)
        errors: list[AgentIssue] = []
        if occurrences:
            errors.append(issue("feedback_text_still_exists", f"真实游戏文件中仍存在 {len(occurrences)} 处反馈原文"))
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
                "stale_plugin_rules": [],
                "write_back_probe_error": "",
            },
        )


def _feedback_fact_entries_from_v2(
    *,
    index_records: list[TextIndexItemRecord],
    facts_by_path: dict[str, TextFactV2Record],
    translated_paths: set[str],
) -> list[_FeedbackFactEntry]:
    """用 v2 facts 和当前 text index 可写状态构造反馈归类输入。"""
    entries: list[_FeedbackFactEntry] = []
    for record in index_records:
        fact = facts_by_path.get(record.location_path)
        if fact is None:
            raise RuntimeError(
                "当前文本索引记录缺少 text fact v2，不能继续使用旧索引正文。"
                + "下一步：请运行 rebuild-text-index 重新生成当前文本索引。"
            )
        entries.append(
            _FeedbackFactEntry(
                location_path=record.location_path,
                original_lines=_feedback_fact_lines(
                    fact.translatable_text,
                    item_type=fact.item_type,
                ),
                can_write_back=record.writable,
                translated=record.location_path in translated_paths,
            )
        )
    return entries


def _classify_feedback_occurrences(
    *,
    occurrences: JsonArray,
    entries: list[_FeedbackFactEntry],
) -> JsonArray:
    """按 v2 文本事实把反馈反查结果归类为结构性缺口。"""
    classified: JsonArray = []
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            continue
        occurrence_object = {key: value for key, value in occurrence.items()}
        feedback_text = occurrence_object.get("text")
        category = occurrence_object.get("category")
        if not isinstance(feedback_text, str):
            occurrence_object["gap_type"] = "rule_gap"
            occurrence_object["gap_label"] = "规则缺口"
            occurrence_object["matching_location_paths"] = []
            classified.append(occurrence_object)
            continue
        if category == "插件源码硬编码文本候选":
            occurrence_object["gap_type"] = "plugin_source_hardcoded"
            occurrence_object["gap_label"] = "插件源码硬编码"
            occurrence_object["matching_location_paths"] = []
            classified.append(occurrence_object)
            continue
        matched_entries = _feedback_entries_containing_text(entries=entries, text=feedback_text)
        gap_type, gap_label = _feedback_gap_from_entries(matched_entries)
        occurrence_object["gap_type"] = gap_type
        occurrence_object["gap_label"] = gap_label
        occurrence_object["matching_location_paths"] = [
            entry.location_path
            for entry in matched_entries[:10]
        ]
        classified.append(occurrence_object)
    return classified


def _feedback_entries_containing_text(
    *,
    entries: list[_FeedbackFactEntry],
    text: str,
) -> list[_FeedbackFactEntry]:
    """查找 v2 文本事实中包含反馈原文的位置。"""
    return [
        entry
        for entry in entries
        if any(text in line for line in entry.original_lines)
    ]


def _feedback_gap_from_entries(entries: list[_FeedbackFactEntry]) -> tuple[str, str]:
    """根据 v2 事实命中情况判断反馈原文残留的结构性原因。"""
    if not entries:
        return "rule_gap", "规则缺口"
    if any(not entry.can_write_back for entry in entries):
        return "write_gap", "写入缺口"
    if any(not entry.translated for entry in entries):
        return "translation_gap", "译文缺口"
    return "write_gap", "写入缺口"


def _feedback_fact_lines(text: str, *, item_type: str) -> list[str]:
    """把 v2 fact 的可译正文转换成反馈归类使用的行模型。"""
    if item_type in {"long_text", "array"}:
        return text.split("\n")
    return [text]
