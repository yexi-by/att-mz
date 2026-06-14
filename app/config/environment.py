"""运行环境变量配置适配模块。"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

RUNTIME_RUST_THREADS_ENV_NAME = "ATT_MZ_RUST_THREADS"
type RuntimeRustThreadsOverride = Literal["auto"] | int


@dataclass(frozen=True, slots=True)
class EnvironmentOverrides:
    """从环境变量读取到的运行配置覆盖值。"""

    rust_threads: RuntimeRustThreadsOverride | None = None

    def has_any(self) -> bool:
        """判断当前环境是否提供了覆盖值。"""
        return self.rust_threads is not None

    def enabled_names(self) -> list[str]:
        """返回已经生效的环境变量名。"""
        names: list[str] = []
        if self.rust_threads is not None:
            names.append(RUNTIME_RUST_THREADS_ENV_NAME)
        return names


def load_environment_overrides(
    environ: Mapping[str, str] | None = None,
) -> EnvironmentOverrides:
    """读取运行环境变量覆盖。"""
    source = os.environ if environ is None else environ
    return EnvironmentOverrides(
        rust_threads=_read_rust_threads_env(source),
    )


def apply_environment_overrides(
    raw_config: dict[str, object],
    overrides: EnvironmentOverrides,
) -> None:
    """把环境变量覆盖值写入原始配置字典。"""
    if not overrides.has_any():
        return

    if overrides.rust_threads is not None:
        runtime = _read_or_create_section(raw_config, "runtime")
        runtime["rust_threads"] = overrides.rust_threads


def _read_non_empty_env(source: Mapping[str, str], name: str) -> str | None:
    """读取非空环境变量；空白值按未设置处理。"""
    value = source.get(name)
    if value is None:
        return None
    stripped_value = value.strip()
    if not stripped_value:
        return None
    return stripped_value


def _read_rust_threads_env(
    source: Mapping[str, str],
) -> RuntimeRustThreadsOverride | None:
    """读取 Rust 线程数环境变量；只接受 auto 或正整数。"""
    value = _read_non_empty_env(source, RUNTIME_RUST_THREADS_ENV_NAME)
    if value is None:
        return None
    if value == "auto":
        return "auto"
    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise ValueError(
            f"{RUNTIME_RUST_THREADS_ENV_NAME} 必须是正整数或 auto"
        ) from exc
    if parsed_value <= 0:
        raise ValueError(f"{RUNTIME_RUST_THREADS_ENV_NAME} 必须是正整数或 auto")
    return parsed_value


def _read_or_create_section(
    raw_config: dict[str, object],
    section_name: str,
) -> dict[str, object]:
    """读取配置段；缺失时创建空配置段等待后续校验。"""
    section = raw_config.get(section_name)
    if section is None:
        new_section: dict[str, object] = {}
        raw_config[section_name] = new_section
        return new_section
    if not isinstance(section, dict):
        raise ValueError(f"配置文件中 {section_name} 必须是表")
    return cast(dict[str, object], section)


__all__: list[str] = [
    "EnvironmentOverrides",
    "RUNTIME_RUST_THREADS_ENV_NAME",
    "apply_environment_overrides",
    "load_environment_overrides",
]
