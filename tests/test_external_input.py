"""外部输入类型规范化契约测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.external_input import (
    ExternalInputModel,
    ExternalInt,
    ExternalStr,
    normalize_external_int,
    normalize_external_str,
    normalize_external_str_list,
)


class ExternalStrPayload(ExternalInputModel):
    """测试用外部字符串字段模型。"""

    value: ExternalStr


class ExternalIntPayload(ExternalInputModel):
    """测试用外部整数字段模型。"""

    value: ExternalInt


def test_external_str_accepts_string_and_integer() -> None:
    """字符串字段允许字符串和整数输入。"""
    assert ExternalStrPayload.model_validate({"value": "1"}).value == "1"
    assert ExternalStrPayload.model_validate({"value": 1}).value == "1"
    assert normalize_external_str(2, "id") == "2"


@pytest.mark.parametrize("value", [True, False, 1.0, None, [], {}])
def test_external_str_rejects_non_string_integer_values(value: object) -> None:
    """字符串字段拒绝布尔、浮点和复合值。"""
    with pytest.raises(ValidationError):
        _ = ExternalStrPayload.model_validate({"value": value})


def test_external_int_accepts_integer_and_integer_string() -> None:
    """整数字段允许整数和整数字符串输入。"""
    assert ExternalIntPayload.model_validate({"value": 1}).value == 1
    assert ExternalIntPayload.model_validate({"value": "1"}).value == 1
    assert ExternalIntPayload.model_validate({"value": " 12 "}).value == 12
    assert normalize_external_int("3", "plugin_index") == 3


@pytest.mark.parametrize("value", [True, False, 1.0, "1.0", "", " ", None, [], {}])
def test_external_int_rejects_non_integer_values(value: object) -> None:
    """整数字段拒绝布尔、浮点、小数文本、空文本和复合值。"""
    with pytest.raises(ValidationError):
        _ = ExternalIntPayload.model_validate({"value": value})


def test_external_string_list_reports_indexed_value() -> None:
    """字符串列表规范化错误必须能定位到具体下标。"""
    assert normalize_external_str_list(["a", 1], "translation_lines") == ["a", "1"]

    with pytest.raises(TypeError) as error_info:
        _ = normalize_external_str_list(["a", True], "translation_lines")

    message = str(error_info.value)
    assert "translation_lines[1]" in message
    assert "bool" in message
