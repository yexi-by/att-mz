"""运行环境变量配置适配模块。"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

LLM_BASE_URL_ENV_NAME = "ATT_MZ_LLM_BASE_URL"
LLM_API_KEY_ENV_NAME = "ATT_MZ_LLM_API_KEY"
_LEGACY_ENV_PREFIX = "RPG_MAKER_TOOLS" + "_"


@dataclass(frozen=True, slots=True)
class EnvironmentOverrides:
    """从环境变量读取到的运行配置覆盖值。"""

    llm_base_url: str | None = None
    llm_api_key: str | None = None

    def has_any(self) -> bool:
        """判断当前环境是否提供了覆盖值。"""
        return self.llm_base_url is not None or self.llm_api_key is not None

    def enabled_names(self) -> list[str]:
        """返回已经生效的环境变量名。"""
        names: list[str] = []
        if self.llm_base_url is not None:
            names.append(LLM_BASE_URL_ENV_NAME)
        if self.llm_api_key is not None:
            names.append(LLM_API_KEY_ENV_NAME)
        return names


def load_environment_overrides(
    environ: Mapping[str, str] | None = None,
) -> EnvironmentOverrides:
    """读取模型连接相关环境变量。"""
    source = os.environ if environ is None else environ
    legacy_names = _collect_legacy_environment_names(source)
    if legacy_names:
        raise ValueError(_format_legacy_environment_error(legacy_names))
    return EnvironmentOverrides(
        llm_base_url=_read_non_empty_env(source, LLM_BASE_URL_ENV_NAME),
        llm_api_key=_read_non_empty_env(source, LLM_API_KEY_ENV_NAME),
    )


def apply_environment_overrides(
    raw_config: dict[str, object],
    overrides: EnvironmentOverrides,
) -> None:
    """把环境变量覆盖值写入原始配置字典。"""
    if not overrides.has_any():
        return

    llm = _read_or_create_section(raw_config, "llm")
    if overrides.llm_base_url is not None:
        llm["base_url"] = overrides.llm_base_url
    if overrides.llm_api_key is not None:
        llm["api_key"] = overrides.llm_api_key


def _read_non_empty_env(source: Mapping[str, str], name: str) -> str | None:
    """读取非空环境变量；空白值按未设置处理。"""
    value = source.get(name)
    if value is None:
        return None
    stripped_value = value.strip()
    if not stripped_value:
        return None
    return stripped_value


def _collect_legacy_environment_names(source: Mapping[str, str]) -> list[str]:
    """收集旧模型环境变量名；旧前缀不再作为成功配置入口。"""
    legacy_names: list[str] = []
    for legacy_name in (
        _legacy_env_name("LLM_BASE_URL"),
        _legacy_env_name("LLM_API_KEY"),
    ):
        if _read_non_empty_env(source, legacy_name) is not None:
            legacy_names.append(legacy_name)
    return legacy_names


def _legacy_env_name(suffix: str) -> str:
    """生成旧环境变量名。"""
    return f"{_LEGACY_ENV_PREFIX}{suffix}"


def _format_legacy_environment_error(legacy_names: list[str]) -> str:
    """生成旧环境变量的恢复提示。"""
    legacy_label = "、".join(legacy_names)
    return (
        f"旧模型环境变量 {legacy_label} 已停用，不能继续作为成功配置入口；"
        f"请改用 {LLM_BASE_URL_ENV_NAME} 和 {LLM_API_KEY_ENV_NAME} 后重新运行"
    )


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
    "LLM_API_KEY_ENV_NAME",
    "LLM_BASE_URL_ENV_NAME",
    "apply_environment_overrides",
    "load_environment_overrides",
]
