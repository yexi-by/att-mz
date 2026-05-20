"""正文翻译运行用例的状态模型与纯业务辅助函数。"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.schemas import Setting
from app.llm import LLMRequestFailure
from app.persistence.repository import current_timestamp_text
from app.rmmz.schema import LlmFailureRecord, TranslationData, TranslationErrorItem, TranslationItem
from app.rmmz.text_rules import TextRules
from app.terminology import TerminologyPromptIndex
from app.translation import TranslationBatch, TranslationCache, iter_translation_context_batches


@dataclass(frozen=True, slots=True)
class TranslationRunLimits:
    """正文翻译单次运行控制参数。"""

    max_items: int | None = None
    max_batches: int | None = None
    time_limit_seconds: int | None = None
    stop_on_error_rate: float | None = None


class TranslationRunInterrupted(Exception):
    """正文翻译运行被模型故障或控制条件中断。"""

    def __init__(
        self,
        *,
        reason: str,
        success_count: int,
        quality_error_count: int,
        llm_failure: LLMRequestFailure | None = None,
    ) -> None:
        """保存中断原因和已保存数量。"""
        super().__init__(reason)
        self.reason: str = reason
        self.success_count: int = success_count
        self.quality_error_count: int = quality_error_count
        self.llm_failure: LLMRequestFailure | None = llm_failure


@dataclass(slots=True)
class TranslationProgressState:
    """正文翻译运行期间共享的保存计数。"""

    success_count: int = 0
    quality_error_count: int = 0


def filter_pending_translation_data(
    *,
    translation_data_map: dict[str, TranslationData],
    translated_paths: set[str],
) -> dict[str, TranslationData]:
    """过滤掉数据库中已经存在译文的条目。"""
    pending_translation_data_map: dict[str, TranslationData] = {}
    for file_name, translation_data in translation_data_map.items():
        pending_items = [
            item
            for item in translation_data.translation_items
            if item.location_path not in translated_paths
        ]
        if not pending_items:
            continue
        pending_translation_data_map[file_name] = TranslationData(
            display_name=translation_data.display_name,
            translation_items=pending_items,
        )
    return pending_translation_data_map


def deduplicate_translation_data(
    *,
    translation_data_map: dict[str, TranslationData],
    translation_cache: TranslationCache,
) -> dict[str, TranslationData]:
    """按正文内容执行请求级去重。"""
    deduplicated_translation_data_map: dict[str, TranslationData] = {}
    for file_name, translation_data in translation_data_map.items():
        deduplicated_items = [
            item
            for item in translation_data.translation_items
            if translation_cache.remember_or_defer(item)
        ]
        if not deduplicated_items:
            continue
        deduplicated_translation_data_map[file_name] = TranslationData(
            display_name=translation_data.display_name,
            translation_items=deduplicated_items,
        )
    return deduplicated_translation_data_map


def limit_translation_data(
    *,
    translation_data_map: dict[str, TranslationData],
    max_items: int | None,
) -> dict[str, TranslationData]:
    """按本轮上限截取还没成功保存译文的条目，便于 Agent 分批运行。"""
    if max_items is None:
        return translation_data_map
    if max_items <= 0:
        raise ValueError("max_items 必须是正整数")

    remaining_count = max_items
    limited_data_map: dict[str, TranslationData] = {}
    for file_name, translation_data in translation_data_map.items():
        if remaining_count <= 0:
            break
        selected_items = translation_data.translation_items[:remaining_count]
        if selected_items:
            limited_data_map[file_name] = TranslationData(
                display_name=translation_data.display_name,
                translation_items=selected_items,
            )
            remaining_count -= len(selected_items)
    return limited_data_map


def count_translation_items(translation_data_map: dict[str, TranslationData]) -> int:
    """统计翻译数据中的条目数量。"""
    return sum(len(data.translation_items) for data in translation_data_map.values())


def build_translation_batches(
    *,
    translation_data_map: dict[str, TranslationData],
    setting: Setting,
    text_rules: TextRules,
    terminology_prompt_index: TerminologyPromptIndex | None,
) -> list[TranslationBatch]:
    """构建正文翻译批次。"""
    batches: list[TranslationBatch] = []
    for translation_data in translation_data_map.values():
        batches.extend(
            iter_translation_context_batches(
                translation_data=translation_data,
                token_size=setting.translation_context.token_size,
                factor=setting.translation_context.factor,
                max_command_items=setting.translation_context.max_command_items,
                system_prompt=setting.text_translation.system_prompt,
                text_rules=text_rules,
                terminology_prompt_index=terminology_prompt_index,
            )
        )
    return batches


def expand_cached_error_items(
    error_items: list[TranslationErrorItem],
    translation_cache: TranslationCache,
) -> list[TranslationErrorItem]:
    """在错误落库前展开失败正文同键的重复条目。"""
    expanded_error_items: list[TranslationErrorItem] = []
    for error_item in error_items:
        expanded_error_items.append(error_item)
        duplicate_items = translation_cache.pop_duplicate_items_by_fields(
            original_lines=error_item.original_lines,
            item_type=error_item.item_type,
            role=error_item.role,
        )
        for duplicate_item in duplicate_items:
            expanded_error_items.append(
                TranslationErrorItem(
                    location_path=duplicate_item.location_path,
                    item_type=duplicate_item.item_type,
                    role=duplicate_item.role,
                    original_lines=list(duplicate_item.original_lines),
                    translation_lines=list(error_item.translation_lines),
                    error_type=error_item.error_type,
                    error_detail=list(error_item.error_detail),
                    model_response=error_item.model_response,
                )
            )
    return expanded_error_items


def expand_cached_translation_items(
    items: list[TranslationItem],
    translation_cache: TranslationCache,
) -> list[TranslationItem]:
    """在成功写库前展开与首条正文同键的重复条目。"""
    expanded_items: list[TranslationItem] = []
    for item in items:
        expanded_items.append(item)
        duplicate_items = translation_cache.pop_duplicate_items(item)
        for duplicate_item in duplicate_items:
            duplicate_item.translation_lines = list(item.translation_lines)
            expanded_items.append(duplicate_item)
    return expanded_items


def build_llm_failure_record(
    *,
    run_id: str,
    failure: LLMRequestFailure,
) -> LlmFailureRecord:
    """把模型请求异常转换成数据库运行级故障记录。"""
    return LlmFailureRecord(
        run_id=run_id,
        category=failure.info.category,
        error_type=failure.info.error_type,
        error_message=failure.info.message,
        retryable=failure.info.retryable,
        attempt_count=failure.attempt_count,
        created_at=current_timestamp_text(),
    )


def format_exception_summary(error: Exception) -> str:
    """将异常压缩为适合日志首行展示的稳定摘要。"""
    message = str(error).strip()
    if message:
        return f"{type(error).__name__}: {message}"
    return type(error).__name__
