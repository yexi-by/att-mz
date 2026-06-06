"""日志系统表现层测试。"""

import json
from pathlib import Path
from typing import cast

import pytest
from pytest import CaptureFixture

from app.llm import ChatMessage
from app.cli.progress import AgentProgressReporter
from app.observability import logger, setup_logger
from app.observability.logging import agent_console_sink


def test_console_sink_outputs_single_plain_line(capsys: CaptureFixture[str]) -> None:
    """stderr 日志 sink 去掉标记并把多行消息折叠成单行。"""
    message = "\n".join(
        [
            "INFO [tag.phase]CLI 运行开始[/tag.phase]",
            "命令参数: list",
            "日志文件: logs/app.log",
        ]
    )
    agent_console_sink(message)

    captured = capsys.readouterr()

    assert captured.err == "INFO CLI 运行开始 | 命令参数: list | 日志文件: logs/app.log\n"
    assert "[tag.phase]" not in captured.err
    assert "\x1b" not in captured.err


def test_file_log_hides_debug_by_default_but_keeps_exception_traceback(tmp_path: Path) -> None:
    """普通模式文件日志不记录 DEBUG 排障细节，但保留未知异常 traceback。"""
    log_path = tmp_path / "app.log"
    setup_logger(level="INFO", use_console=False, file_path=log_path, enqueue_file_log=False)

    logger.debug("[tag.phase]调试细节[/tag.phase] 普通模式不应写入文件")
    try:
        raise RuntimeError("模拟未知异常")
    except RuntimeError:
        logger.bind(file_only=True).exception("[tag.exception]未知异常[/tag.exception]")
    _ = logger.complete()

    content = log_path.read_text(encoding="utf-8")
    assert "调试细节" not in content
    assert "Traceback" in content
    assert "RuntimeError: 模拟未知异常" in content


def test_file_log_keeps_debug_when_debug_logging_file_level_enabled(tmp_path: Path) -> None:
    """debug logging 开启时，文件日志按配置记录 DEBUG 细节。"""
    log_path = tmp_path / "debug.log"
    setup_logger(
        level="INFO",
        file_level="DEBUG",
        use_console=False,
        file_path=log_path,
        enqueue_file_log=False,
    )

    AgentProgressReporter("测试任务").set_status("debug logging 写入文件")
    _ = logger.complete()

    content = log_path.read_text(encoding="utf-8")
    assert "任务状态" in content
    assert "debug logging 写入文件" in content


def test_diagnostics_context_is_isolated_by_contextvars(tmp_path: Path) -> None:
    """当前诊断上下文必须可隔离，避免连续运行串写同一个收集器。"""
    from app.observability.diagnostics import (
        DebugRuntimeSettings,
        DiagnosticsContext,
        bind_diagnostics_context,
        current_diagnostics,
    )

    first = DiagnosticsContext.create_for_command(
        command="quality-report",
        settings=DebugRuntimeSettings(enabled=True, timings_enabled=True),
        diagnostics_dir=tmp_path,
    )
    second = DiagnosticsContext.create_for_command(
        command="write-back",
        settings=DebugRuntimeSettings(enabled=True, timings_enabled=True),
        diagnostics_dir=tmp_path,
    )

    with bind_diagnostics_context(first):
        current_diagnostics().record_timing("quality.native_quality", 12)
        with bind_diagnostics_context(second):
            current_diagnostics().record_timing("write_back.rust_plan.total", 34)
        current_diagnostics().record_timing("quality.read_rules", 5)

    assert first.timings == {"quality.native_quality": 12, "quality.read_rules": 5}
    assert second.timings == {"write_back.rust_plan.total": 34}


def test_diagnostics_context_writes_stable_payload_when_debug_timings_enabled(tmp_path: Path) -> None:
    """debug timings 开启时，每次运行写出稳定顶层 diagnostics JSON。"""
    from app.observability.diagnostics import DebugRuntimeSettings, DiagnosticsContext

    context = DiagnosticsContext.create_for_command(
        command="quality-report",
        settings=DebugRuntimeSettings(
            enabled=True,
            source="cli",
            logging_enabled=True,
            timings_enabled=True,
            timings_source="setting",
        ),
        diagnostics_dir=tmp_path,
    )
    context.record_timing("quality.native_quality", 12)
    context.counter("runtime.native_thread_count", 4)
    context.counter("quality.native_quality_payload_item_count", 20)
    context.artifact("log_file", tmp_path / "app.log")

    diagnostics_path = context.finalize(status="ok", exit_code=0)

    assert diagnostics_path is not None
    payload = cast(dict[str, object], json.loads(diagnostics_path.read_text(encoding="utf-8")))
    debug_payload = cast(dict[str, object], payload["debug"])
    environment_payload = cast(dict[str, object], payload["environment"])
    timings_payload = cast(dict[str, object], payload["timings"])
    counters_payload = cast(dict[str, object], payload["counters"])
    assert set(payload) == {
        "schema_version",
        "run_id",
        "command",
        "status",
        "exit_code",
        "started_at",
        "finished_at",
        "duration_ms",
        "debug",
        "environment",
        "timings",
        "counters",
        "artifacts",
        "warnings",
    }
    assert payload["schema_version"] == 1
    assert payload["command"] == "quality-report"
    assert payload["status"] == "ok"
    assert payload["exit_code"] == 0
    assert debug_payload["source"] == "cli"
    assert debug_payload["timings_source"] == "setting"
    assert environment_payload["native_thread_count"] == 4
    assert timings_payload["quality.native_quality"] == 12
    assert "command.total" in timings_payload
    assert counters_payload["quality.native_quality_payload_item_count"] == 20


def test_diagnostics_context_does_not_write_file_in_ordinary_mode(tmp_path: Path) -> None:
    """普通模式不写 diagnostics 文件。"""
    from app.observability.diagnostics import DebugRuntimeSettings, DiagnosticsContext

    context = DiagnosticsContext.create_for_command(
        command="list",
        settings=DebugRuntimeSettings(enabled=False, timings_enabled=True),
        diagnostics_dir=tmp_path,
    )
    context.record_timing("command.total", 1)

    diagnostics_path = context.finalize(status="ok", exit_code=0)

    assert diagnostics_path is None
    assert list(tmp_path.glob("*.json")) == []


def test_llm_message_recorder_writes_markdown_and_index(tmp_path: Path) -> None:
    """LLM 消息观测保存成功响应、脱敏请求元数据，并在收尾生成索引。"""
    from app.observability.llm_messages import LLMMessageRecorder, LLMMessageRequest

    recorder = LLMMessageRecorder(command="translate", run_id="run123", output_dir=tmp_path)
    request = LLMMessageRequest(
        task_key="text-translation",
        task_label="正文|翻译",
        model="model|x",
        base_url="https://api.example.com/v1",
        api_key_display="<redacted>",
        temperature=None,
        extra_body={
            "reasoning_effort": "high",
            "private_token": "secret-value",
            "nested": {"authorization": "Bearer secret"},
        },
        messages=[
            ChatMessage(role="system", text="系统提示词\n```json\n{}\n```"),
            ChatMessage(role="user", text="用户提示词"),
        ],
        request_started_at="2026-06-07T14:30:12+08:00",
    )

    output_path = recorder.record_success(
        request=request,
        assistant_text='[{"id":"1","translation_lines":["译文"]}]',
        response_received_at="2026-06-07T14:30:21+08:00",
    )
    index_path = recorder.finalize()

    assert output_path.name == "000001_text-translation.md"
    assert index_path is not None
    assert index_path.name == "index.md"
    markdown = output_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    assert "# LLM 调用 000001" in markdown
    assert "- task_key: text-translation" in markdown
    assert "- task_label: 正文|翻译" in markdown
    assert '"api_key": "<redacted>"' in markdown
    assert '"private_token": "<redacted>"' in markdown
    assert '"authorization": "<redacted>"' in markdown
    assert "https://api.example.com/v1" in markdown
    assert "````text\n系统提示词" in markdown
    assert '```json\n{}\n```' in markdown
    assert '[{"id":"1","translation_lines":["译文"]}]' in markdown
    assert "正文\\|翻译" in index
    assert "model\\|x" in index
    assert "000001_text-translation.md" in index


def test_llm_message_recorder_does_not_create_directory_without_success(tmp_path: Path) -> None:
    """没有成功 LLM 调用时，不创建空运行目录。"""
    from app.observability.llm_messages import LLMMessageRecorder

    recorder = LLMMessageRecorder(command="quality-report", run_id="run-empty", output_dir=tmp_path)

    assert recorder.finalize() is None
    assert list(tmp_path.iterdir()) == []


def test_llm_message_recorder_write_failure_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """debug 文件写入失败必须显式抛出专用错误。"""
    from app.observability import llm_messages
    from app.observability.llm_messages import LLMMessageRecorder, LLMMessageRequest, LLMMessageWriteError

    recorder = LLMMessageRecorder(command="translate", run_id="run123", output_dir=tmp_path)
    request = LLMMessageRequest(
        task_key="llm",
        task_label="LLM 调用",
        model="model",
        base_url="https://api.example.com/v1",
        api_key_display="<redacted>",
        temperature=None,
        extra_body={},
        messages=[ChatMessage(role="user", text="你好")],
        request_started_at="2026-06-07T14:30:12+08:00",
    )

    def fail_write_text(path: Path, text: str) -> None:
        _ = (path, text)
        raise OSError("磁盘不可写")

    monkeypatch.setattr(llm_messages, "_write_text", fail_write_text)

    with pytest.raises(LLMMessageWriteError, match="LLM 消息观测文件写出失败"):
        _ = recorder.record_success(
            request=request,
            assistant_text="成功",
            response_received_at="2026-06-07T14:30:21+08:00",
        )
