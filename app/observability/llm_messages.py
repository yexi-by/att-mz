"""debug 模式下的 LLM 消息观测运行时。"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.llm_request_body_extra import LLMRequestBodyExtra, LLMRequestBodyValue
from app.runtime_paths import resolve_app_home_path

if TYPE_CHECKING:
    from app.llm.schemas import ChatMessage

REDACTED_VALUE = "<redacted>"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
)
TASK_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class LLMMessageWriteError(RuntimeError):
    """LLM 消息观测文件写出失败。"""


@dataclass(frozen=True, slots=True)
class LLMMessageRequest:
    """一次成功 LLM 调用对应的请求观测输入。"""

    task_key: str
    task_label: str
    client_name: str
    provider_type: str
    model: str
    base_url: str
    api_key_display: str
    temperature: float | None
    extra_body: LLMRequestBodyExtra
    messages: list[ChatMessage]
    request_started_at: str


@dataclass(frozen=True, slots=True)
class _LLMMessageIndexRecord:
    sequence: int
    sequence_text: str
    task_label: str
    model: str
    request_started_at: str
    response_received_at: str
    user_chars: int
    assistant_chars: int
    file_name: str


class NoopLLMMessageRecorder:
    """未启用 LLM 消息观测时的空记录器。"""

    @property
    def run_dir(self) -> Path | None:
        """未启用时没有运行目录。"""
        return None

    def record_success(
        self,
        *,
        request: LLMMessageRequest,
        assistant_text: str,
        response_received_at: str,
        sequence: int | None = None,
    ) -> Path | None:
        """忽略成功响应。"""
        _ = (request, assistant_text, response_received_at, sequence)
        return None

    def reserve_sequence(self) -> int | None:
        """未启用时不预留编号。"""
        return None

    def finalize(self) -> Path | None:
        """未启用时不写索引。"""
        return None


class LLMMessageRecorder:
    """记录一次 CLI 运行中的成功 LLM 调用。"""

    def __init__(
        self,
        *,
        command: str,
        run_id: str,
        output_dir: str | Path,
        started_at: datetime | None = None,
    ) -> None:
        """初始化记录器，但不立即创建输出目录。"""
        self.command: str = command
        self.run_id: str = run_id
        self.output_dir: Path = resolve_app_home_path(output_dir)
        self.started_at: datetime = started_at or datetime.now(timezone.utc).astimezone()
        self._lock: threading.Lock = threading.Lock()
        self._next_sequence: int = 1
        self._records: list[_LLMMessageIndexRecord] = []
        self._run_dir: Path | None = None

    @property
    def run_dir(self) -> Path | None:
        """返回已创建的运行目录。"""
        return self._run_dir

    def record_success(
        self,
        *,
        request: LLMMessageRequest,
        assistant_text: str,
        response_received_at: str,
        sequence: int | None = None,
    ) -> Path:
        """写出一次成功 LLM 调用的 Markdown 文件。"""
        validate_llm_message_task_key(request.task_key)
        with self._lock:
            if sequence is None:
                sequence = self._allocate_sequence_unlocked()
            sequence_text = f"{sequence:06d}"
            safe_task_key = _safe_task_key(request.task_key)
            file_name = f"{sequence_text}_{safe_task_key}.md"
            run_dir = self._ensure_run_dir()
            output_path = run_dir / file_name
            markdown = _render_message_markdown(
                sequence_text=sequence_text,
                command=self.command,
                request=request,
                assistant_text=assistant_text,
                response_received_at=response_received_at,
            )
            try:
                _write_text(output_path, markdown)
            except OSError as error:
                raise LLMMessageWriteError(f"LLM 消息观测文件写出失败: {output_path}") from error

            self._records.append(
                _LLMMessageIndexRecord(
                    sequence=sequence,
                    sequence_text=sequence_text,
                    task_label=request.task_label,
                    model=request.model,
                    request_started_at=request.request_started_at,
                    response_received_at=response_received_at,
                    user_chars=_role_chars(request.messages, "user"),
                    assistant_chars=len(assistant_text),
                    file_name=file_name,
                )
            )
            return output_path

    def reserve_sequence(self) -> int:
        """在请求发起时预留文件编号，保证并发下按发起顺序编号。"""
        with self._lock:
            return self._allocate_sequence_unlocked()

    def finalize(self) -> Path | None:
        """正常收尾时写出索引 Markdown。"""
        with self._lock:
            if not self._records:
                return None
            run_dir = self._ensure_run_dir()
            index_path = run_dir / "index.md"
            try:
                _write_text(index_path, _render_index_markdown(self._records))
            except OSError as error:
                raise LLMMessageWriteError(f"LLM 消息观测索引写出失败: {index_path}") from error
            return index_path

    def _ensure_run_dir(self) -> Path:
        if self._run_dir is None:
            timestamp = self.started_at.strftime("%Y-%m-%d_%H%M%S")
            safe_command = _safe_task_key(self.command)
            safe_run_id = _safe_task_key(self.run_id)
            self._run_dir = self.output_dir / f"{timestamp}_{safe_command}_{safe_run_id}"
            self._run_dir.mkdir(parents=True, exist_ok=True)
        return self._run_dir

    def _allocate_sequence_unlocked(self) -> int:
        sequence = self._next_sequence
        self._next_sequence += 1
        return sequence


_CURRENT_LLM_MESSAGE_RECORDER: ContextVar[LLMMessageRecorder | NoopLLMMessageRecorder] = ContextVar(
    "att_mz_current_llm_message_recorder",
    default=NoopLLMMessageRecorder(),
)


def current_llm_message_recorder() -> LLMMessageRecorder | NoopLLMMessageRecorder:
    """读取当前 CLI 运行的 LLM 消息记录器。"""
    return _CURRENT_LLM_MESSAGE_RECORDER.get()


def validate_llm_message_task_key(task_key: str) -> None:
    """校验 LLM 消息观测任务标识，避免路径或文本位置进入文件名语义。"""
    if not TASK_KEY_PATTERN.fullmatch(task_key):
        raise ValueError("task_key 必须是 1-64 位 ASCII 标识，只能包含字母、数字、下划线、点和短横线")


@contextmanager
def bind_llm_message_recorder(
    recorder: LLMMessageRecorder | NoopLLMMessageRecorder,
) -> Generator[LLMMessageRecorder | NoopLLMMessageRecorder, None, None]:
    """把 LLM 消息记录器绑定到当前 contextvars 上下文。"""
    token: Token[LLMMessageRecorder | NoopLLMMessageRecorder] = _CURRENT_LLM_MESSAGE_RECORDER.set(recorder)
    try:
        yield recorder
    finally:
        _CURRENT_LLM_MESSAGE_RECORDER.reset(token)


def _render_message_markdown(
    *,
    sequence_text: str,
    command: str,
    request: LLMMessageRequest,
    assistant_text: str,
    response_received_at: str,
) -> str:
    metadata_json: dict[str, object] = {
        "model": request.model,
        "llm_client": {
            "name": request.client_name,
            "provider_type": request.provider_type,
            "model": request.model,
        },
        "temperature": request.temperature,
        "base_url": request.base_url,
        "api_key": request.api_key_display,
        "extra_body": _redact_request_body_value(request.extra_body),
    }
    sections = [
        f"# LLM 调用 {sequence_text}",
        "## 元数据",
        "\n".join(
            [
                f"- command: {command}",
                f"- task_key: {request.task_key}",
                f"- task_label: {request.task_label}",
                f"- llm_client: {request.client_name}",
                f"- provider_type: {request.provider_type}",
                f"- model: {request.model}",
                f"- base_url: {request.base_url}",
                f"- temperature: {_format_optional_number(request.temperature)}",
                f"- request_started_at: {request.request_started_at}",
                f"- response_received_at: {response_received_at}",
                f"- message_count: {len(request.messages)}",
                f"- system_chars: {_role_chars(request.messages, 'system')}",
                f"- user_chars: {_role_chars(request.messages, 'user')}",
                f"- assistant_chars: {len(assistant_text)}",
            ]
        ),
        "## 请求元数据",
        _fenced_block(json.dumps(metadata_json, ensure_ascii=False, indent=2), "json"),
    ]
    for index, message in enumerate(request.messages, start=1):
        sections.append(f"## message {index}: {message.role}")
        sections.append(_fenced_block(message.text, "text"))
    sections.append("## assistant")
    sections.append(_fenced_block(assistant_text, "text"))
    return "\n\n".join(sections) + "\n"


def _render_index_markdown(records: list[_LLMMessageIndexRecord]) -> str:
    lines = [
        "# LLM 消息观测",
        "",
        "| 序号 | 任务 | 模型 | 发起时间 | 返回时间 | user 字符 | assistant 字符 | 文件 |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for record in sorted(records, key=lambda item: item.sequence):
        lines.append(
            " | ".join(
                [
                    f"| {_escape_table_cell(record.sequence_text)}",
                    _escape_table_cell(record.task_label),
                    _escape_table_cell(record.model),
                    _escape_table_cell(record.request_started_at),
                    _escape_table_cell(record.response_received_at),
                    str(record.user_chars),
                    str(record.assistant_chars),
                    f"{_escape_table_cell(record.file_name)} |",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _redact_request_body_value(value: LLMRequestBodyValue) -> LLMRequestBodyValue:
    if isinstance(value, dict):
        redacted: dict[str, LLMRequestBodyValue] = {}
        for key, child in value.items():
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = _redact_request_body_value(child)
        return redacted
    if isinstance(value, list):
        return [_redact_request_body_value(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _fenced_block(text: str, language: str) -> str:
    longest_backticks = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest_backticks + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _escape_table_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _safe_task_key(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return safe or "llm"


def _role_chars(messages: list[ChatMessage], role: str) -> int:
    return sum(len(message.text) for message in messages if message.role == role)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "null"
    return str(value)


def _write_text(path: Path, text: str) -> None:
    _ = path.write_text(text, encoding="utf-8")


__all__ = [
    "LLMMessageRecorder",
    "LLMMessageRequest",
    "LLMMessageWriteError",
    "NoopLLMMessageRecorder",
    "bind_llm_message_recorder",
    "current_llm_message_recorder",
    "validate_llm_message_task_key",
]
