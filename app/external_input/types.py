"""外部输入类型规范化工具。"""

from __future__ import annotations

import re
from typing import Annotated, ClassVar, TypeAlias, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict

INTEGER_TEXT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")


class ExternalInputModel(BaseModel):
    """外部 JSON 输入模型基类，只允许显式字段类型执行规范化。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)


def describe_external_value(value: object) -> str:
    """返回适合外部输入错误信息的短类型描述。"""
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "null"
    if isinstance(value, str):
        return f'string: "{value}"'
    if isinstance(value, int):
        return f"integer: {value}"
    if isinstance(value, float):
        return f"float: {value}"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def normalize_external_str(value: object, field_label: str = "值") -> str:
    """把外部字符串字段规范化为 Python str。"""
    if isinstance(value, bool):
        raise TypeError(f"{field_label} 必须是字符串或整数，当前收到 {describe_external_value(value)}")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"{field_label} 必须是字符串或整数，当前收到 {describe_external_value(value)}")


def normalize_external_int(value: object, field_label: str = "值") -> int:
    """把外部整数字段规范化为 Python int。"""
    if isinstance(value, bool):
        raise TypeError(f"{field_label} 必须是整数或整数字符串，当前收到 {describe_external_value(value)}")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value or INTEGER_TEXT_PATTERN.fullmatch(normalized_value) is None:
            raise TypeError(f"{field_label} 必须是整数或整数字符串，当前收到 {describe_external_value(value)}")
        return int(normalized_value)
    raise TypeError(f"{field_label} 必须是整数或整数字符串，当前收到 {describe_external_value(value)}")


def normalize_external_str_list(value: object, field_label: str) -> list[str]:
    """把外部字符串数组规范化为 Python str 列表。"""
    if not isinstance(value, list):
        raise TypeError(f"{field_label} 必须是字符串数组，当前收到 {describe_external_value(value)}")
    items = cast(list[object], value)
    normalized_items: list[str] = []
    for index, item in enumerate(items):
        normalized_items.append(normalize_external_str(item, f"{field_label}[{index}]"))
    return normalized_items


def _validate_external_str(value: object) -> str:
    """Pydantic 字符串字段 validator。"""
    try:
        return normalize_external_str(value)
    except TypeError as error:
        raise ValueError(str(error)) from error


def _validate_external_int(value: object) -> int:
    """Pydantic 整数字段 validator。"""
    try:
        return normalize_external_int(value)
    except TypeError as error:
        raise ValueError(str(error)) from error


ExternalStr: TypeAlias = Annotated[str, BeforeValidator(_validate_external_str)]
ExternalInt: TypeAlias = Annotated[int, BeforeValidator(_validate_external_int)]
ExternalStrList: TypeAlias = list[ExternalStr]


__all__ = [
    "ExternalInputModel",
    "ExternalInt",
    "ExternalStr",
    "ExternalStrList",
    "describe_external_value",
    "normalize_external_int",
    "normalize_external_str",
    "normalize_external_str_list",
]
