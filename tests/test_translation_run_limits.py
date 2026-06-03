"""翻译运行限制和取消语义测试。"""

from __future__ import annotations

import json
import asyncio
from collections.abc import Iterable
from typing import override

import pytest

from app.application.summaries import TextTranslationSummary
from app.application.use_cases.translation_run import (
    TranslationRunController,
    TranslationRunInterrupted,
    TranslationRunState,
)
from app.cli.reports import build_run_all_summary_report, build_translate_summary_report
from app.config.schemas import TextRulesSetting
from app.llm import ChatMessage, EmptyLLMResponseError, LLMHandler
from app.rmmz.schema import TranslationErrorItem, TranslationItem
from app.rmmz.text_rules import TextRules
from app.translation import TranslationBatch


class AlwaysQualityErrorLLMHandler(LLMHandler):
    """持续返回项目检查失败译文的假模型。"""

    def __init__(self) -> None:
        """初始化请求计数。"""
        super().__init__()
        self.call_count: int = 0

    @override
    async def get_ai_response(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float | None = None,
    ) -> str:
        """返回空数组，让校验器把整个批次记录为 AI 漏翻。"""
        _ = (messages, model, temperature)
        self.call_count += 1
        return "[]"


class SlowSecondQualityErrorLLMHandler(LLMHandler):
    """第二个请求会稍后完成，用于模拟阈值触发时的进行中请求。"""

    def __init__(self) -> None:
        """初始化请求计数。"""
        super().__init__()
        self.call_count: int = 0

    @override
    async def get_ai_response(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float | None = None,
    ) -> str:
        """第二个已发送请求延迟返回质量错误。"""
        _ = (messages, model, temperature)
        self.call_count += 1
        if self.call_count == 2:
            await asyncio.sleep(0.01)
        return "[]"


class OneSuccessOneFailureLLMHandler(LLMHandler):
    """两个并发请求同时完成，其中一个成功、一个模型请求失败。"""

    def __init__(self) -> None:
        """初始化并发启动屏障。"""
        super().__init__()
        self.call_count: int = 0
        self._all_started: asyncio.Event = asyncio.Event()

    @override
    async def get_ai_response(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float | None = None,
    ) -> str:
        """等待两个请求都发出后分别返回成功和失败结果。"""
        _ = (model, temperature)
        self.call_count += 1
        if self.call_count >= 2:
            _ = self._all_started.set()
        _ = await self._all_started.wait()
        request_text = messages[0].text
        if "translate 2" in request_text:
            raise EmptyLLMResponseError("空响应")
        return json.dumps(
            [{"id": "id-1", "translation_lines": ["译文 1"]}],
            ensure_ascii=False,
        )


def _build_batch(index: int) -> TranslationBatch:
    """构造一个单条正文的测试批次。"""
    location_path = f"Map001.json/{index}"
    item = TranslationItem(
        location_path=location_path,
        item_type="short_text",
        original_lines=[f"原文 {index}"],
    )
    return TranslationBatch(
        items=[item],
        prompt_ids_by_location_path={location_path: f"id-{index}"},
        messages=[ChatMessage(role="user", text=f"translate {index}")],
    )


@pytest.mark.asyncio
async def test_stop_on_error_rate_stops_dispatching_unsent_batches() -> None:
    """错误率达到阈值后，控制器不能继续发送剩余批次。"""
    llm_handler = AlwaysQualityErrorLLMHandler()
    saved_errors: list[TranslationErrorItem] = []
    state = TranslationRunState(total_batch_count=3, total_item_count=3)

    async def save_success(items: list[TranslationItem]) -> int:
        """本用例不会产生成功译文。"""
        return len(items)

    async def save_errors(items: list[TranslationErrorItem]) -> int:
        """记录已保存的质量错误。"""
        saved_errors.extend(items)
        return len(items)

    controller = TranslationRunController(
        batches=[_build_batch(1), _build_batch(2), _build_batch(3)],
        llm_handler=llm_handler,
        model="fake-model",
        retry_count=0,
        retry_delay=0,
        worker_count=1,
        rpm=None,
        text_rules=TextRules.from_setting(TextRulesSetting()),
        source_residual_rule_set=None,
        stop_on_error_rate=1.0,
        state=state,
        save_success_items=save_success,
        save_error_items=save_errors,
        advance_progress=lambda _count: None,
    )

    with pytest.raises(TranslationRunInterrupted) as caught:
        _ = await controller.run()

    interrupted_state = caught.value.state
    assert llm_handler.call_count == 1
    assert len(saved_errors) == 1
    assert interrupted_state.stopped is True
    assert interrupted_state.success_count == 0
    assert interrupted_state.quality_error_count == 1
    assert interrupted_state.cancelled_unsent_batch_count == 2
    assert interrupted_state.cancelled_unsent_item_count == 2
    assert interrupted_state.sent_after_stop_completed_batch_count == 0
    assert "停止阈值" in interrupted_state.stop_reason


@pytest.mark.asyncio
async def test_stop_on_error_rate_reports_in_flight_batches_completed_after_stop() -> None:
    """阈值触发时已发出的请求会等待完成，并计入已发送后完成统计。"""
    llm_handler = SlowSecondQualityErrorLLMHandler()
    state = TranslationRunState(total_batch_count=3, total_item_count=3)

    async def save_success(items: list[TranslationItem]) -> int:
        """本用例不会产生成功译文。"""
        return len(items)

    async def save_errors(items: list[TranslationErrorItem]) -> int:
        """返回已保存错误数量。"""
        return len(items)

    controller = TranslationRunController(
        batches=[_build_batch(1), _build_batch(2), _build_batch(3)],
        llm_handler=llm_handler,
        model="fake-model",
        retry_count=0,
        retry_delay=0,
        worker_count=2,
        rpm=None,
        text_rules=TextRules.from_setting(TextRulesSetting()),
        source_residual_rule_set=None,
        stop_on_error_rate=1.0,
        state=state,
        save_success_items=save_success,
        save_error_items=save_errors,
        advance_progress=lambda _count: None,
    )

    with pytest.raises(TranslationRunInterrupted) as caught:
        _ = await controller.run()

    interrupted_state = caught.value.state
    assert llm_handler.call_count == 2
    assert interrupted_state.cancelled_unsent_batch_count == 1
    assert interrupted_state.cancelled_unsent_item_count == 1
    assert interrupted_state.sent_after_stop_completed_batch_count == 1
    assert interrupted_state.sent_after_stop_completed_item_count == 1
    assert interrupted_state.quality_error_count == 2


@pytest.mark.asyncio
async def test_llm_failure_preserves_other_completed_batch_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一轮 wait 中已有成功批次时，模型请求失败不能让成功结果丢失。"""
    llm_handler = OneSuccessOneFailureLLMHandler()
    state = TranslationRunState(total_batch_count=2, total_item_count=2)
    saved_success: list[TranslationItem] = []
    original_wait = asyncio.wait

    async def wait_all_with_failure_first(
        fs: Iterable[asyncio.Task[object]],
        *,
        timeout: float | None = None,
        return_when: str = asyncio.FIRST_COMPLETED,
    ) -> tuple[list[asyncio.Task[object]], set[asyncio.Task[object]]]:
        """模拟 FIRST_COMPLETED 合法返回多个完成任务，且失败任务先被消费。"""
        _ = return_when
        done, pending = await original_wait(fs, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
        ordered_done = sorted(done, key=lambda task: task.exception() is None)
        return ordered_done, pending

    async def save_success(items: list[TranslationItem]) -> int:
        """记录已保存成功译文。"""
        saved_success.extend(items)
        return len(items)

    async def save_errors(items: list[TranslationErrorItem]) -> int:
        """本用例没有项目质量错误。"""
        return len(items)

    monkeypatch.setattr(asyncio, "wait", wait_all_with_failure_first)
    controller = TranslationRunController(
        batches=[_build_batch(1), _build_batch(2)],
        llm_handler=llm_handler,
        model="fake-model",
        retry_count=0,
        retry_delay=0,
        worker_count=2,
        rpm=None,
        text_rules=TextRules.from_setting(TextRulesSetting()),
        source_residual_rule_set=None,
        stop_on_error_rate=None,
        state=state,
        save_success_items=save_success,
        save_error_items=save_errors,
        advance_progress=lambda _count: None,
    )

    with pytest.raises(TranslationRunInterrupted) as caught:
        _ = await controller.run()

    interrupted_state = caught.value.state
    assert [item.location_path for item in saved_success] == ["Map001.json/1"]
    assert saved_success[0].translation_lines == ["译文 1"]
    assert interrupted_state.success_count == 1
    assert interrupted_state.llm_failure_count == 1
    assert interrupted_state.cancelled_unsent_batch_count == 0


def test_translation_summary_reports_stop_state_for_translate_and_run_all() -> None:
    """translate 和 run-all JSON 摘要必须暴露同一运行中止状态。"""
    summary = TextTranslationSummary(
        total_extracted_items=3,
        pending_count=3,
        deduplicated_count=3,
        batch_count=3,
        success_count=0,
        error_count=1,
        llm_failure_count=0,
        blocked_reason="检查没通过的译文比例达到停止阈值: 1.0",
        stopped=True,
        cancelled_unsent_batch_count=2,
        cancelled_unsent_item_count=2,
        sent_after_stop_completed_batch_count=0,
        sent_after_stop_completed_item_count=0,
    )

    translate_report = build_translate_summary_report(summary)
    run_all_report = build_run_all_summary_report(text_summary=summary, write_back_summary=None)

    for payload in (translate_report.summary, run_all_report.summary):
        assert payload["stopped"] is True
        assert payload["blocked_reason"] == summary.blocked_reason
        assert payload["success_count"] == 0
        assert payload["quality_error_count"] == 1
        assert payload["llm_failure_count"] == 0
        assert payload["cancelled_unsent_batch_count"] == 2
        assert payload["cancelled_unsent_item_count"] == 2

    translation_detail = run_all_report.details["translation"]
    assert isinstance(translation_detail, dict)
    assert json.dumps(translation_detail, ensure_ascii=False).count("停止阈值") == 1
