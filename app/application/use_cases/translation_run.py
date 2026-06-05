"""正文翻译运行用例的状态模型与纯业务辅助函数。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from app.config.schemas import Setting
from app.llm import LLMHandler, LLMRequestFailure
from app.persistence.repository import current_timestamp_text
from app.rmmz.schema import LlmFailureRecord, TranslationData, TranslationErrorItem, TranslationItem
from app.rmmz.text_rules import TextRules
from app.source_residual import SourceResidualRuleSet
from app.terminology import TerminologyPromptIndex
from app.translation import TranslationBatch, TranslationCache, iter_translation_context_batches
from app.translation.retry import request_with_recoverable_retry
from app.translation.verify import verify_translation_batch


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
        state: "TranslationRunState | None" = None,
    ) -> None:
        """保存中断原因和已保存数量。"""
        super().__init__(reason)
        self.reason: str = reason
        self.success_count: int = success_count
        self.quality_error_count: int = quality_error_count
        self.llm_failure: LLMRequestFailure | None = llm_failure
        self.state: TranslationRunState = state or TranslationRunState(
            success_count=success_count,
            quality_error_count=quality_error_count,
            llm_failure_count=1 if llm_failure is not None else 0,
            stopped=True,
            stop_reason=reason,
            last_error=str(self),
            llm_failure=llm_failure,
        )


@dataclass(slots=True)
class TranslationRunState:
    """正文翻译运行控制器的单一状态。"""

    total_batch_count: int = 0
    total_item_count: int = 0
    sent_batch_count: int = 0
    sent_item_count: int = 0
    completed_batch_count: int = 0
    completed_item_count: int = 0
    success_count: int = 0
    quality_error_count: int = 0
    llm_failure_count: int = 0
    stopped: bool = False
    stop_reason: str = ""
    last_error: str = ""
    cancelled_unsent_batch_count: int = 0
    cancelled_unsent_item_count: int = 0
    sent_after_stop_completed_batch_count: int = 0
    sent_after_stop_completed_item_count: int = 0
    llm_failure: LLMRequestFailure | None = None

    def request_stop(self, *, reason: str, last_error: str = "stopped") -> None:
        """记录运行中止原因。"""
        if self.stopped:
            return
        self.stopped = True
        self.stop_reason = reason
        self.last_error = last_error

    def cancel_unsent(self, pending_batches: deque[TranslationBatch]) -> None:
        """记录因中止而不再发送的批次。"""
        self.cancelled_unsent_batch_count += len(pending_batches)
        self.cancelled_unsent_item_count += sum(len(batch.items) for batch in pending_batches)
        pending_batches.clear()

    @property
    def processed_count(self) -> int:
        """返回已经写入成功表或错误表的条目数。"""
        return self.success_count + self.quality_error_count


@dataclass(frozen=True, slots=True)
class TranslationBatchResult:
    """单个模型批次完成后的校验结果。"""

    batch: TranslationBatch
    right_items: list[TranslationItem]
    error_items: list[TranslationErrorItem]


type SaveSuccessItems = Callable[[list[TranslationItem]], Awaitable[int]]
type SaveErrorItems = Callable[[list[TranslationErrorItem]], Awaitable[int]]
type AdvanceProgress = Callable[[int], None]


class TranslationRunController:
    """集中管理正文翻译批次派发、完成、限制和中止状态。"""

    def __init__(
        self,
        *,
        batches: list[TranslationBatch],
        llm_handler: LLMHandler,
        model: str,
        retry_count: int,
        retry_delay: int,
        worker_count: int,
        rpm: int | None,
        text_rules: TextRules,
        source_residual_rule_set: SourceResidualRuleSet | None,
        stop_on_error_rate: float | None,
        state: TranslationRunState,
        save_success_items: SaveSuccessItems,
        save_error_items: SaveErrorItems,
        advance_progress: AdvanceProgress,
    ) -> None:
        """初始化翻译运行控制器。"""
        self._batches: deque[TranslationBatch] = deque(batches)
        self._llm_handler: LLMHandler = llm_handler
        self._model: str = model
        self._retry_count: int = retry_count
        self._retry_delay: int = retry_delay
        self._worker_count: int = max(1, min(worker_count, max(len(batches), 1)))
        self._rpm: int | None = rpm
        self._text_rules: TextRules = text_rules
        self._source_residual_rule_set: SourceResidualRuleSet | None = source_residual_rule_set
        self._stop_on_error_rate: float | None = stop_on_error_rate
        self.state: TranslationRunState = state
        self.state.total_batch_count = len(batches)
        self.state.total_item_count = sum(len(batch.items) for batch in batches)
        self._save_success_items: SaveSuccessItems = save_success_items
        self._save_error_items: SaveErrorItems = save_error_items
        self._advance_progress: AdvanceProgress = advance_progress
        self._in_flight: dict[asyncio.Task[TranslationBatchResult], TranslationBatch] = {}
        self._sent_before_stop_tasks: set[asyncio.Task[TranslationBatchResult]] = set()
        self._last_dispatch_at: float | None = None

    async def run(self) -> TranslationRunState:
        """执行批次调度，必要时抛出带状态的运行中止异常。"""
        try:
            await self._run_loop()
        except LLMRequestFailure as error:
            self._record_llm_failure(error)
            await self.cancel_running_requests()
            raise self._build_interrupted() from error
        except Exception:
            await self.cancel_running_requests()
            raise
        if self.state.stopped:
            raise self._build_interrupted()
        return self.state

    async def cancel_running_requests(self) -> None:
        """取消尚未完成的模型请求并等待任务退出。"""
        tasks = list(self._in_flight)
        self._in_flight.clear()
        for task in tasks:
            _ = task.cancel()
        for task in tasks:
            try:
                _ = await task
            except asyncio.CancelledError:
                pass
            except Exception as error:
                if not self.state.last_error:
                    self.state.last_error = format_exception_summary(error)

    def request_stop(self, *, reason: str, last_error: str) -> None:
        """停止继续派发新批次，并记录尚未发送的批次。"""
        self.state.request_stop(reason=reason, last_error=last_error)
        self.state.cancel_unsent(self._batches)
        self._sent_before_stop_tasks.update(self._in_flight)

    async def _run_loop(self) -> None:
        """按并发上限派发批次，并在阈值触发后停止派发剩余批次。"""
        while self._batches or self._in_flight:
            await self._dispatch_available_batches()
            if not self._in_flight:
                break
            done_tasks, _pending_tasks = await asyncio.wait(
                self._in_flight.keys(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            await self._consume_done_tasks(done_tasks)

    async def _consume_done_tasks(
        self,
        done_tasks: Iterable[asyncio.Task[TranslationBatchResult]],
    ) -> None:
        """保存本轮已完成批次，再上抛首个模型请求异常。"""
        first_error: Exception | None = None
        for task in done_tasks:
            batch = self._in_flight.pop(task)
            try:
                result = task.result()
            except Exception as error:
                if first_error is None:
                    first_error = error
                continue
            await self._save_batch_result(result)
            if task in self._sent_before_stop_tasks:
                self.state.sent_after_stop_completed_batch_count += 1
                self.state.sent_after_stop_completed_item_count += len(batch.items)
            self._request_stop_if_error_rate_reached()
        if first_error is not None:
            raise first_error

    async def _dispatch_available_batches(self) -> None:
        """派发当前可发送批次。"""
        while (
            not self.state.stopped
            and self._batches
            and len(self._in_flight) < self._worker_count
        ):
            batch = self._batches.popleft()
            await self._wait_for_rate_limit()
            task = asyncio.create_task(self._translate_batch(batch))
            self._in_flight[task] = batch
            self.state.sent_batch_count += 1
            self.state.sent_item_count += len(batch.items)

    async def _wait_for_rate_limit(self) -> None:
        """按 RPM 限制等待下一次派发。"""
        if self._rpm is None:
            return
        interval = 60.0 / self._rpm
        now = time.monotonic()
        if self._last_dispatch_at is not None:
            elapsed = now - self._last_dispatch_at
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
        self._last_dispatch_at = time.monotonic()

    async def _translate_batch(self, batch: TranslationBatch) -> TranslationBatchResult:
        """发送并校验单个模型批次。"""
        ai_result = await request_with_recoverable_retry(
            llm_handler=self._llm_handler,
            model=self._model,
            messages=batch.messages,
            retry_count=self._retry_count,
            retry_delay=self._retry_delay,
            task_label="正文翻译",
        )
        right_queue: asyncio.Queue[list[TranslationItem] | None] = asyncio.Queue()
        error_queue: asyncio.Queue[list[TranslationErrorItem] | None] = asyncio.Queue()
        await verify_translation_batch(
            ai_result=ai_result,
            items=batch.items,
            prompt_ids_by_location_path=batch.prompt_ids_by_location_path,
            right_queue=right_queue,
            error_queue=error_queue,
            text_rules=self._text_rules,
            source_residual_rule_set=self._source_residual_rule_set,
        )
        right_items = await _drain_translation_queue(right_queue)
        error_items = await _drain_translation_error_queue(error_queue)
        return TranslationBatchResult(batch=batch, right_items=right_items, error_items=error_items)

    async def _save_batch_result(self, result: TranslationBatchResult) -> None:
        """保存单个批次结果并更新统一状态。"""
        saved_success_count = await self._save_success_items(result.right_items)
        saved_error_count = await self._save_error_items(result.error_items)
        processed_count = saved_success_count + saved_error_count
        self.state.success_count += saved_success_count
        self.state.quality_error_count += saved_error_count
        self.state.completed_batch_count += 1
        self.state.completed_item_count += len(result.batch.items)
        if processed_count:
            self._advance_progress(processed_count)

    def _request_stop_if_error_rate_reached(self) -> None:
        """按错误率阈值停止继续派发新批次。"""
        if self.state.stopped or self._stop_on_error_rate is None:
            return
        processed_count = self.state.processed_count
        if processed_count <= 0:
            return
        if self.state.quality_error_count / processed_count < self._stop_on_error_rate:
            return
        self.state.request_stop(
            reason=f"检查没通过的译文比例达到停止阈值: {self._stop_on_error_rate}",
            last_error="stop_on_error_rate",
        )
        self.state.cancel_unsent(self._batches)
        self._sent_before_stop_tasks.update(self._in_flight)

    def _record_llm_failure(self, error: LLMRequestFailure) -> None:
        """记录模型请求失败并停止运行。"""
        self.state.llm_failure_count = 1
        self.state.llm_failure = error
        self.state.request_stop(
            reason=f"模型请求失败: {error.info.message}",
            last_error=error.info.error_type,
        )
        self.state.cancel_unsent(self._batches)

    def _build_interrupted(self) -> TranslationRunInterrupted:
        """根据统一状态构造运行中止异常。"""
        return TranslationRunInterrupted(
            reason=self.state.stop_reason,
            success_count=self.state.success_count,
            quality_error_count=self.state.quality_error_count,
            llm_failure=self.state.llm_failure,
            state=self.state,
        )


async def _drain_translation_queue(
    queue: asyncio.Queue[list[TranslationItem] | None],
) -> list[TranslationItem]:
    """读取校验器写入成功队列的所有条目。"""
    items: list[TranslationItem] = []
    while not queue.empty():
        batch_items = await queue.get()
        if batch_items is not None:
            items.extend(batch_items)
    return items


async def _drain_translation_error_queue(
    queue: asyncio.Queue[list[TranslationErrorItem] | None],
) -> list[TranslationErrorItem]:
    """读取校验器写入错误队列的所有条目。"""
    items: list[TranslationErrorItem] = []
    while not queue.empty():
        batch_items = await queue.get()
        if batch_items is not None:
            items.extend(batch_items)
    return items


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
    max_batches: int | None = None,
) -> list[TranslationBatch]:
    """构建正文翻译批次。"""
    if max_batches is not None and max_batches <= 0:
        raise ValueError("max_batches 必须是正整数")
    batches: list[TranslationBatch] = []
    for translation_data in translation_data_map.values():
        for batch in iter_translation_context_batches(
            translation_data=translation_data,
            token_size=setting.translation_context.token_size,
            factor=setting.translation_context.factor,
            max_command_items=setting.translation_context.max_command_items,
            system_prompt=setting.text_translation.system_prompt,
            text_rules=text_rules,
            terminology_prompt_index=terminology_prompt_index,
        ):
            batches.append(batch)
            if max_batches is not None and len(batches) >= max_batches:
                return batches
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
