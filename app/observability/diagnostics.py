"""统一 debug 诊断运行时。"""

from __future__ import annotations

import json
import os
import re
import time
import tomllib
from collections.abc import Generator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Literal, cast
from uuid import uuid4

from pydantic import ValidationError

from app.config.schemas import DebugSetting
from app.rmmz.json_types import JsonArray, JsonObject, JsonValue
from app.runtime_paths import resolve_app_path

DEBUG_ENV_NAME = "ATT_MZ_DEBUG"
DEBUG_LOGGING_ENV_NAME = "ATT_MZ_DEBUG_LOGGING"
DEBUG_TIMINGS_ENV_NAME = "ATT_MZ_DEBUG_TIMINGS"
DEBUG_LLM_MESSAGES_ENV_NAME = "ATT_MZ_DEBUG_LLM_MESSAGES"
DEFAULT_SETTING_FILE_NAME = "setting.toml"
DIAGNOSTICS_SCHEMA_VERSION = 1

type DebugValueSource = Literal["cli", "env", "setting", "default"]


@dataclass(frozen=True, slots=True)
class DebugRuntimeSettings:
    """合并后的 debug 运行配置。"""

    enabled: bool = False
    source: DebugValueSource = "default"
    logging_enabled: bool = True
    logging_source: DebugValueSource = "default"
    logging_console_level: str = "DEBUG"
    logging_file_level: str = "DEBUG"
    timings_enabled: bool = True
    timings_source: DebugValueSource = "default"
    timings_write_file: bool = True
    timings_include_summary_in_report: bool = True
    timings_detail_level: str = "standard"
    llm_messages_enabled: bool = True
    llm_messages_source: DebugValueSource = "default"
    llm_messages_output_dir: str = "output/debug/llm-messages"

    @property
    def effective_logging_enabled(self) -> bool:
        """判断本次是否启用 debug 日志。"""
        return self.enabled and self.logging_enabled

    @property
    def effective_timings_enabled(self) -> bool:
        """判断本次是否启用统一计时诊断。"""
        return self.enabled and self.timings_enabled

    @property
    def effective_llm_messages_enabled(self) -> bool:
        """判断本次是否启用 LLM 消息观测。"""
        return self.enabled and self.llm_messages_enabled


class StageTimer:
    """记录一个同步阶段耗时的上下文管理器。"""

    def __init__(self, context: "DiagnosticsContext", name: str) -> None:
        self._context: DiagnosticsContext = context
        self._name: str = name
        self._started_at: float = 0.0

    def __enter__(self) -> "StageTimer":
        """进入阶段计时。"""
        self._started_at = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出阶段并记录毫秒耗时。"""
        _ = (exc_type, exc, traceback)
        self._context.record_timing(
            self._name,
            int((time.perf_counter() - self._started_at) * 1000),
        )


class NoopDiagnosticsContext:
    """普通模式下的空诊断上下文。"""

    @property
    def timings_enabled(self) -> bool:
        """普通模式未启用统一计时诊断。"""
        return False

    @property
    def timings(self) -> dict[str, int]:
        """返回空计时结果。"""
        return {}

    @property
    def counters(self) -> dict[str, int]:
        """返回空计数结果。"""
        return {}

    def stage(self, name: str) -> nullcontext[None]:
        """返回空阶段上下文。"""
        _ = name
        return nullcontext()

    def record_timing(self, name: str, duration_ms: int) -> None:
        """忽略阶段耗时。"""
        _ = (name, duration_ms)

    def counter(self, name: str, value: int) -> None:
        """忽略计数。"""
        _ = (name, value)

    def artifact(self, name: str, path: str | Path) -> None:
        """忽略产物路径。"""
        _ = (name, path)

    def build_report_summary(self) -> JsonObject | None:
        """普通模式不注入诊断摘要。"""
        return None

    def finalize(self, *, status: str, exit_code: int) -> Path | None:
        """普通模式不写诊断文件。"""
        _ = (status, exit_code)
        return None


class DiagnosticsContext:
    """一次 CLI 运行的诊断上下文。"""

    def __init__(
        self,
        *,
        command: str,
        settings: DebugRuntimeSettings,
        diagnostics_dir: Path,
    ) -> None:
        self.command: str = command
        self.settings: DebugRuntimeSettings = settings
        self.started_at: str = _now_iso()
        self._started_perf: float = time.perf_counter()
        self._finished_at: str | None = None
        self._status: str = "running"
        self._exit_code: int = 0
        self._timings: dict[str, int] = {}
        self._counters: dict[str, int] = {}
        self._artifacts: dict[str, str] = {}
        self._warnings: list[str] = []
        self.run_id: str = _build_run_id(command)
        self.diagnostics_dir: Path = diagnostics_dir.resolve()
        self.file_path: Path = self.diagnostics_dir / f"{self.run_id}.json"

    @classmethod
    def create_for_command(
        cls,
        *,
        command: str,
        settings: DebugRuntimeSettings,
        diagnostics_dir: Path | None = None,
    ) -> "DiagnosticsContext":
        """创建一次 CLI 运行的诊断上下文。"""
        return cls(
            command=command,
            settings=settings,
            diagnostics_dir=diagnostics_dir or resolve_app_path("logs", "diagnostics"),
        )

    @property
    def timings_enabled(self) -> bool:
        """判断当前上下文是否会记录统一计时诊断。"""
        return self.settings.effective_timings_enabled

    @property
    def timings(self) -> dict[str, int]:
        """返回当前已记录的计时。"""
        return dict(self._timings)

    @property
    def counters(self) -> dict[str, int]:
        """返回当前已记录的计数。"""
        return dict(self._counters)

    def stage(self, name: str) -> StageTimer | nullcontext[None]:
        """记录一个阶段耗时。"""
        if not self.settings.effective_timings_enabled:
            return nullcontext()
        return StageTimer(self, name)

    def record_timing(self, name: str, duration_ms: int) -> None:
        """记录外部阶段耗时。"""
        if not self.settings.effective_timings_enabled:
            return
        if duration_ms < 0:
            raise ValueError("duration_ms 必须大于等于 0")
        self._timings[name] = duration_ms

    def counter(self, name: str, value: int) -> None:
        """记录关键计数。"""
        if not self.settings.effective_timings_enabled:
            return
        self._counters[name] = value

    def artifact(self, name: str, path: str | Path) -> None:
        """记录诊断相关产物路径。"""
        if not self.settings.effective_timings_enabled:
            return
        self._artifacts[name] = str(path)

    def build_report_summary(self) -> JsonObject | None:
        """构造 stdout JSON 中的诊断摘要。"""
        if (
            not self.settings.effective_timings_enabled
            or not self.settings.timings_include_summary_in_report
        ):
            return None
        slowest_timings: JsonArray = [
            {"name": name, "duration_ms": duration}
            for name, duration in sorted(
                self._timings.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ]
        return {
            "enabled": self.settings.enabled,
            "timings_enabled": self.settings.timings_enabled,
            "duration_ms": self._current_duration_ms(),
            "slowest_timings": slowest_timings,
            "file": str(self.file_path),
        }

    def finalize(self, *, status: str, exit_code: int) -> Path | None:
        """结束诊断上下文并按配置写出完整 JSON。"""
        self._status = status
        self._exit_code = exit_code
        self._finished_at = _now_iso()
        if self.settings.effective_timings_enabled:
            _ = self._timings.setdefault("command.total", self._current_duration_ms())
        if not (
            self.settings.effective_timings_enabled
            and self.settings.timings_write_file
        ):
            return None
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        _ = self.file_path.write_text(
            f"{json.dumps(self._build_payload(), ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        return self.file_path

    def _current_duration_ms(self) -> int:
        return int((time.perf_counter() - self._started_perf) * 1000)

    def _build_payload(self) -> JsonObject:
        return {
            "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
            "run_id": self.run_id,
            "command": self.command,
            "status": self._status,
            "exit_code": self._exit_code,
            "started_at": self.started_at,
            "finished_at": self._finished_at or _now_iso(),
            "duration_ms": self._current_duration_ms(),
            "debug": {
                "enabled": self.settings.enabled,
                "source": self.settings.source,
                "logging_enabled": self.settings.logging_enabled,
                "logging_source": self.settings.logging_source,
                "timings_enabled": self.settings.timings_enabled,
                "timings_source": self.settings.timings_source,
                "llm_messages_enabled": self.settings.llm_messages_enabled,
                "llm_messages_source": self.settings.llm_messages_source,
            },
            "environment": self._build_environment_payload(),
            "timings": dict(self._timings),
            "counters": dict(self._counters),
            "artifacts": dict(self._artifacts),
            "warnings": list(self._warnings),
        }

    def _build_environment_payload(self) -> JsonObject:
        environment: JsonObject = {"cwd": str(Path.cwd())}
        native_threads = self._counters.get("runtime.native_thread_count")
        if native_threads is not None:
            environment["native_thread_count"] = native_threads
        return environment


_CURRENT_DIAGNOSTICS: ContextVar[DiagnosticsContext | NoopDiagnosticsContext] = ContextVar(
    "att_mz_current_diagnostics",
    default=NoopDiagnosticsContext(),
)


def current_diagnostics() -> DiagnosticsContext | NoopDiagnosticsContext:
    """读取当前 CLI 运行的诊断上下文。"""
    return _CURRENT_DIAGNOSTICS.get()


@contextmanager
def bind_diagnostics_context(
    context: DiagnosticsContext | NoopDiagnosticsContext,
) -> Generator[DiagnosticsContext | NoopDiagnosticsContext, None, None]:
    """把诊断上下文绑定到当前 contextvars 上下文。"""
    token: Token[DiagnosticsContext | NoopDiagnosticsContext] = _CURRENT_DIAGNOSTICS.set(context)
    try:
        yield context
    finally:
        _CURRENT_DIAGNOSTICS.reset(token)


def resolve_debug_runtime_settings(
    *,
    args: object | None = None,
    setting_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DebugRuntimeSettings:
    """轻量读取 debug 配置并合并 CLI、环境变量和配置文件覆盖。"""
    raw_debug = _read_debug_setting(setting_path)
    environment = os.environ if environ is None else environ

    enabled, enabled_source = _resolve_bool_value(
        cli_value=_read_optional_bool_attr(args, "debug"),
        env_value=_read_env_bool(environment, DEBUG_ENV_NAME),
        setting_value=raw_debug.enabled,
    )
    logging_enabled, logging_source = _resolve_bool_value(
        cli_value=_read_optional_bool_attr(args, "debug_logging"),
        env_value=_read_env_bool(environment, DEBUG_LOGGING_ENV_NAME),
        setting_value=raw_debug.logging.enabled,
    )
    timings_enabled, timings_source = _resolve_bool_value(
        cli_value=_read_optional_bool_attr(args, "debug_timings"),
        env_value=_read_env_bool(environment, DEBUG_TIMINGS_ENV_NAME),
        setting_value=raw_debug.timings.enabled,
    )
    llm_messages_enabled, llm_messages_source = _resolve_bool_value(
        cli_value=_read_optional_bool_attr(args, "debug_llm_messages"),
        env_value=_read_env_bool(environment, DEBUG_LLM_MESSAGES_ENV_NAME),
        setting_value=raw_debug.llm_messages.enabled,
    )
    return DebugRuntimeSettings(
        enabled=enabled,
        source=enabled_source,
        logging_enabled=logging_enabled,
        logging_source=logging_source,
        logging_console_level=raw_debug.logging.console_level,
        logging_file_level=raw_debug.logging.file_level,
        timings_enabled=timings_enabled,
        timings_source=timings_source,
        timings_write_file=raw_debug.timings.write_file,
        timings_include_summary_in_report=raw_debug.timings.include_summary_in_report,
        timings_detail_level=raw_debug.timings.detail_level,
        llm_messages_enabled=llm_messages_enabled,
        llm_messages_source=llm_messages_source,
        llm_messages_output_dir=raw_debug.llm_messages.output_dir,
    )


def _read_debug_setting(setting_path: str | Path | None) -> DebugSetting:
    resolved_path = resolve_app_path(DEFAULT_SETTING_FILE_NAME) if setting_path is None else Path(setting_path)
    if not resolved_path.exists():
        return DebugSetting()
    raw_text = resolved_path.read_text(encoding="utf-8-sig")
    raw_config = cast(dict[str, JsonValue], tomllib.loads(raw_text))
    raw_debug = raw_config.get("debug", {})
    if raw_debug is None:
        return DebugSetting()
    if not isinstance(raw_debug, dict):
        raise ValueError("配置文件中 debug 必须是表")
    try:
        return DebugSetting.model_validate(raw_debug)
    except ValidationError as error:
        raise ValueError(f"debug 配置无效: {error}") from error


def _resolve_bool_value(
    *,
    cli_value: bool | None,
    env_value: bool | None,
    setting_value: bool,
) -> tuple[bool, DebugValueSource]:
    if cli_value is not None:
        return cli_value, "cli"
    if env_value is not None:
        return env_value, "env"
    return setting_value, "setting"


def _read_optional_bool_attr(args: object | None, name: str) -> bool | None:
    if args is None or not hasattr(args, name):
        return None
    value = cast(object, getattr(args, name))
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{name} 必须是布尔值")
    return value


def _read_env_bool(source: Mapping[str, str], name: str) -> bool | None:
    raw_value = source.get(name)
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 只能是 1/0 或 true/false")


def _build_run_id(command: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_command = re.sub(r"[^A-Za-z0-9_.-]+", "-", command).strip("-") or "command"
    return f"{timestamp}-{safe_command}-{uuid4().hex[:6]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


__all__ = [
    "DEBUG_ENV_NAME",
    "DEBUG_LLM_MESSAGES_ENV_NAME",
    "DEBUG_LOGGING_ENV_NAME",
    "DEBUG_TIMINGS_ENV_NAME",
    "DIAGNOSTICS_SCHEMA_VERSION",
    "DebugRuntimeSettings",
    "DiagnosticsContext",
    "NoopDiagnosticsContext",
    "StageTimer",
    "bind_diagnostics_context",
    "current_diagnostics",
    "resolve_debug_runtime_settings",
]
