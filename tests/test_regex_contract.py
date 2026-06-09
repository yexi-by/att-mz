"""用户可写正则契约预检的强类型错误测试。"""

import subprocess
import sys
from pathlib import Path

import pytest

from app.config.schemas import TextRulesSetting
from app import regex_contract
from app.regex_contract import (
    RegexContractValidationError,
    validate_mv_virtual_namebox_regex_contract,
    validate_text_rules_regex_contract,
)
from app.rmmz.control_codes import CustomPlaceholderRule
from app.rmmz.schema import MvVirtualNameboxRuleRecord

ROOT = Path(__file__).resolve().parents[1]


class _MissingNativeContractModule:
    """模拟不符合当前契约的 Rust 扩展：没有契约版本函数。"""

    def validate_regex_contract(self, payload_json: str) -> str:
        """即使有同名函数，也必须先被契约检查拦住。"""
        _ = payload_json
        return '{"errors":[]}'


class _MismatchedNativeContractModule:
    """模拟不符合当前契约的 Rust 扩展：契约版本不匹配。"""

    def native_contract_version(self) -> int:
        """返回不满足当前要求的契约版本。"""
        return 1

    def validate_regex_contract(self, payload_json: str) -> str:
        """即使能返回结果，也不能继续参与正则预检。"""
        _ = payload_json
        return '{"errors":[]}'


def _import_missing_native_contract(_name: str) -> object:
    """返回缺少契约版本函数的扩展替身。"""
    return _MissingNativeContractModule()


def _import_mismatched_native_contract(_name: str) -> object:
    """返回契约版本不匹配的扩展替身。"""
    return _MismatchedNativeContractModule()


def test_regex_contract_rejects_invalid_native_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """正则预检不能让无效 Rust 契约以内部 AttributeError 形式失败。"""
    monkeypatch.setattr(regex_contract, "import_module", _import_missing_native_contract)
    with pytest.raises(RuntimeError, match="Rust 原生扩展不满足当前 Python 契约"):
        validate_text_rules_regex_contract(setting=TextRulesSetting())

    monkeypatch.setattr(regex_contract, "import_module", _import_mismatched_native_contract)
    with pytest.raises(RuntimeError, match="Rust 原生扩展不满足当前 Python 契约"):
        validate_text_rules_regex_contract(setting=TextRulesSetting())


def test_text_rules_import_does_not_require_native_contract() -> None:
    """导入文本规则模块不能在 CLI 错误包装前强制加载 Rust 扩展。"""
    script = """
import importlib

real_import_module = importlib.import_module

def missing_native_module(name: str, package: str | None = None):
    if name == "app._native":
        raise ImportError("missing native")
    return real_import_module(name, package=package)


importlib.import_module = missing_native_module
text_rules_module = real_import_module("app.rmmz.text_rules")
try:
    text_rules_module.get_default_text_rules()
except RuntimeError as error:
    assert "Rust 原生扩展不可用" in str(error)
else:
    raise AssertionError("默认文本规则实际使用时必须显式报告 Rust 扩展不可用")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_regex_contract_error_exposes_typed_placeholder_issue() -> None:
    """普通占位符规则失败必须暴露稳定 issue_code，而不是只靠错误字符串。"""
    rule = CustomPlaceholderRule.create(
        r"(?a:@PLUGIN\[[^\]]+\])",
        "[CUSTOM_PLUGIN_MARKER_{index}]",
    )

    with pytest.raises(RegexContractValidationError) as error_info:
        validate_text_rules_regex_contract(
            setting=TextRulesSetting(),
            custom_placeholder_rules=(rule,),
        )

    assert error_info.value.issues[0].issue_code == "placeholder_rules_invalid"
    assert error_info.value.issues[0].rule_type == "普通占位符规则"
    assert error_info.value.issues[0].engine == "rust_fancy_regex"


def test_regex_contract_error_exposes_python_only_text_rule_issue() -> None:
    """source_text_required_pattern 只承诺 Python re，但仍必须走统一强类型入口。"""
    setting = TextRulesSetting(source_text_required_pattern="[")

    with pytest.raises(RegexContractValidationError) as error_info:
        validate_text_rules_regex_contract(setting=setting)

    assert error_info.value.issues[0].issue_code == "text_rules_invalid"
    assert error_info.value.issues[0].field_name == "text_rules.source_text_required_pattern"
    assert error_info.value.issues[0].engine == "python_re"


def test_mv_virtual_namebox_requires_python_style_named_groups() -> None:
    """MV 虚拟名字框规则不能使用非 Python 风格命名分组。"""
    record = MvVirtualNameboxRuleRecord(
        rule_order=0,
        rule_name="bad-named-group",
        pattern_text=r"(?<speaker>[^:：]+)[:：](?<body>.*)",
        speaker_group="speaker",
        body_group="body",
        speaker_policy="translate",
        render_template="{speaker}：{body}",
    )

    with pytest.raises(RegexContractValidationError) as error_info:
        validate_mv_virtual_namebox_regex_contract((record,))

    assert error_info.value.issues[0].issue_code == "mv_virtual_namebox_rules_invalid"
    assert error_info.value.issues[0].engine == "python_re"
