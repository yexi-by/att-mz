"""用户可写正则的跨核心契约预检。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import import_module
from typing import Literal, Protocol, cast

from app.config.schemas import TextRulesSetting
from app.native_contract import ensure_native_contract_version
from app.rmmz.control_codes import CustomPlaceholderRule, StructuredPlaceholderRule
from app.rmmz.json_types import JsonArray, JsonObject, coerce_json_value, ensure_json_array, ensure_json_object

type RegexContractIssueCode = Literal[
    "placeholder_rules_invalid",
    "structured_placeholder_rules_invalid",
    "mv_virtual_namebox_rules_invalid",
    "source_residual_rules_invalid",
    "text_rules_invalid",
]
type _SourceResidualRuleType = Literal["position", "structural"]


@dataclass(frozen=True, slots=True)
class RegexContractIssue:
    """单条用户可写正则契约问题。"""

    issue_code: RegexContractIssueCode
    rule_type: str
    field_name: str
    pattern: str
    engine: str
    message: str
    recovery: str

    def to_message(self) -> str:
        """渲染给 AgentReport 和异常文本使用的中文说明。"""
        return (
            f"{self.rule_type} {self.field_name} 不符合正则语法契约: {self.pattern}; "
            f"{self.message}; 恢复方式: {self.recovery}"
        )


class RegexContractValidationError(ValueError):
    """用户可写正则不满足跨核心契约。"""

    issues: tuple[RegexContractIssue, ...]

    def __init__(self, issues: tuple[RegexContractIssue, ...]) -> None:
        self.issues = issues
        super().__init__("；".join(issue.to_message() for issue in issues))


class _NativeRegexContractModule(Protocol):
    """Rust 原生正则契约预检入口。"""

    def native_contract_version(self) -> int:
        """返回 Rust/Python JSON 契约版本。"""
        ...

    def validate_regex_contract(self, payload_json: str) -> str:
        """编译并校验 payload 中声明的正则规则。"""
        ...


class _SourceResidualRuleRecordLike(Protocol):
    """源文残留规则记录在正则预检中需要的字段。"""

    @property
    def rule_type(self) -> _SourceResidualRuleType:
        """规则类型。"""
        ...

    @property
    def pattern_text(self) -> str:
        """结构规则正则文本。"""
        ...

    @property
    def check_group(self) -> str:
        """需要检查的命名分组。"""
        ...


class _MvVirtualNameboxRuleRecordLike(Protocol):
    """MV 虚拟名字框规则记录在正则预检中需要的字段。"""

    @property
    def pattern_text(self) -> str:
        """名字框匹配正则文本。"""
        ...

    @property
    def speaker_group(self) -> str:
        """说话人命名分组。"""
        ...

    @property
    def body_group(self) -> str:
        """正文命名分组。"""
        ...


def validate_text_rules_regex_contract(
    *,
    setting: TextRulesSetting,
    custom_placeholder_rules: tuple[CustomPlaceholderRule, ...] = (),
    structured_placeholder_rules: tuple[StructuredPlaceholderRule, ...] = (),
) -> None:
    """校验 TextRules 中的用户可写正则契约。"""
    python_patterns: JsonArray = [
        _regex_pattern_spec(
            "text_rules_invalid",
            "配置文本规则",
            "text_rules.source_text_required_pattern",
            setting.source_text_required_pattern,
        )
    ]
    fancy_patterns: JsonArray = []
    for rule in custom_placeholder_rules:
        fancy_patterns.append(
            _regex_pattern_spec(
                "placeholder_rules_invalid",
                "普通占位符规则",
                "pattern",
                rule.pattern_text,
            )
        )
    for rule in structured_placeholder_rules:
        required_groups = (rule.translatable_group, *sorted(rule.protected_groups))
        fancy_patterns.append(
            _regex_pattern_spec(
                "structured_placeholder_rules_invalid",
                "结构化占位符规则",
                "pattern",
                rule.pattern_text,
                required_python_named_groups=required_groups,
            )
        )
    regex_patterns: JsonArray = [
        _regex_pattern_spec(
            "text_rules_invalid",
            "配置文本规则",
            "text_rules.line_width_count_pattern",
            setting.line_width_count_pattern,
        ),
        _regex_pattern_spec(
            "text_rules_invalid",
            "配置文本规则",
            "text_rules.source_residual_segment_pattern",
            setting.source_residual_segment_pattern,
        ),
        _regex_pattern_spec(
            "text_rules_invalid",
            "配置文本规则",
            "text_rules.residual_escape_sequence_pattern",
            setting.residual_escape_sequence_pattern,
        ),
    ]
    _assert_regex_contract(
        {
            "python_patterns": python_patterns,
            "fancy_patterns": fancy_patterns,
            "regex_patterns": regex_patterns,
        }
    )


def validate_source_residual_regex_contract(records: tuple[_SourceResidualRuleRecordLike, ...]) -> None:
    """校验源文残留结构规则能被 Python re 和 Rust regex 同时识别。"""
    regex_patterns: JsonArray = []
    for record in records:
        if record.rule_type != "structural":
            continue
        regex_patterns.append(
            _regex_pattern_spec(
                "source_residual_rules_invalid",
                "结构性源文残留规则",
                "pattern",
                record.pattern_text,
                required_groups=(record.check_group,),
            )
        )
    _assert_regex_contract({"regex_patterns": regex_patterns})


def validate_mv_virtual_namebox_regex_contract(records: tuple[_MvVirtualNameboxRuleRecordLike, ...]) -> None:
    """校验 MV 虚拟名字框规则能被 Rust fancy-regex 和写回分组收集器使用。"""
    fancy_patterns: JsonArray = []
    for record in records:
        required_groups = [record.speaker_group]
        if record.body_group:
            required_groups.append(record.body_group)
        fancy_patterns.append(
            _regex_pattern_spec(
                "mv_virtual_namebox_rules_invalid",
                "MV 虚拟名字框规则",
                "pattern",
                record.pattern_text,
                required_python_named_groups=tuple(required_groups),
            )
        )
    _assert_regex_contract({"fancy_patterns": fancy_patterns})


def _regex_pattern_spec(
    issue_code: RegexContractIssueCode,
    rule_type: str,
    field_name: str,
    pattern: str,
    *,
    required_groups: tuple[str, ...] = (),
    required_python_named_groups: tuple[str, ...] = (),
) -> JsonObject:
    """构造传给 Python/Rust 预检入口的单条规则描述。"""
    spec: JsonObject = {
        "issue_code": issue_code,
        "rule_type": rule_type,
        "field_name": field_name,
        "pattern": pattern,
    }
    if required_groups:
        groups: JsonArray = []
        groups.extend(required_groups)
        spec["required_groups"] = groups
    if required_python_named_groups:
        python_named_groups: JsonArray = []
        python_named_groups.extend(required_python_named_groups)
        spec["required_python_named_groups"] = python_named_groups
    return spec


def _assert_regex_contract(payload: JsonObject) -> None:
    if not _payload_has_patterns(payload):
        return
    issues = _collect_python_re_contract_issues(payload)
    if _payload_has_rust_patterns(payload):
        native = _load_native_module()
        raw_result = cast(object, json.loads(native.validate_regex_contract(json.dumps(payload, ensure_ascii=False))))
        result = ensure_json_object(coerce_json_value(raw_result), "regex_contract_result")
        errors = ensure_json_array(result.get("errors", []), "regex_contract_result.errors")
        issues.extend(_parse_rust_regex_contract_issues(errors))
    if issues:
        raise RegexContractValidationError(tuple(issues))


def _payload_has_patterns(payload: JsonObject) -> bool:
    for key in ("python_patterns", "fancy_patterns", "regex_patterns"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _payload_has_rust_patterns(payload: JsonObject) -> bool:
    for key in ("fancy_patterns", "regex_patterns"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _load_native_module() -> _NativeRegexContractModule:
    try:
        native_module = cast(object, import_module("app._native"))
    except ImportError as error:
        raise RuntimeError("Rust 原生扩展不可用，请先执行 uv run maturin develop") from error
    ensure_native_contract_version(native_module)
    return cast(_NativeRegexContractModule, native_module)


def _collect_python_re_contract_issues(payload: JsonObject) -> list[RegexContractIssue]:
    """收集 Python re 编译和命名分组错误。"""
    issues: list[RegexContractIssue] = []
    issues.extend(
        _collect_python_re_issues_for_specs(
            payload=payload,
            key="python_patterns",
            required_group_key="required_groups",
            rust_engine_label="Python re",
        )
    )
    issues.extend(
        _collect_python_re_issues_for_specs(
            payload=payload,
            key="fancy_patterns",
            required_group_key="required_python_named_groups",
            rust_engine_label="Rust fancy-regex",
        )
    )
    issues.extend(
        _collect_python_re_issues_for_specs(
            payload=payload,
            key="regex_patterns",
            required_group_key="required_groups",
            rust_engine_label="Rust regex",
        )
    )
    return issues


def _collect_python_re_issues_for_specs(
    *,
    payload: JsonObject,
    key: str,
    required_group_key: str,
    rust_engine_label: str,
) -> list[RegexContractIssue]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []

    issues: list[RegexContractIssue] = []
    for index, spec_value in enumerate(value):
        context = f"regex_contract_payload.{key}[{index}]"
        spec = ensure_json_object(coerce_json_value(spec_value), context)
        issue_code = _read_contract_issue_code(spec, context)
        rule_type = _read_contract_string(spec, "rule_type", context)
        field_name = _read_contract_string(spec, "field_name", context)
        pattern_text = _read_contract_string(spec, "pattern", context)
        try:
            compiled_pattern = re.compile(pattern_text)
        except re.error as error:
            issues.append(
                RegexContractIssue(
                    issue_code=issue_code,
                    rule_type=rule_type,
                    field_name=field_name,
                    pattern=pattern_text,
                    engine="python_re",
                    message=f"Python re 无法编译: {error}",
                    recovery=f"请改成 Python re 与 {rust_engine_label} 都支持的正则语法后重新校验或导入。",
                )
            )
            continue

        for group_name in _read_contract_string_list(spec, required_group_key, context):
            if group_name in compiled_pattern.groupindex:
                continue
            issues.append(
                RegexContractIssue(
                    issue_code=issue_code,
                    rule_type=rule_type,
                    field_name=field_name,
                    pattern=pattern_text,
                    engine="python_re_group",
                    message=f"Python re 缺少命名分组: {group_name}",
                    recovery="请使用 Python 风格命名分组 (?P<name>...)，并让规则字段引用已存在的分组。",
                )
            )
    return issues


def _parse_rust_regex_contract_issues(errors: JsonArray) -> list[RegexContractIssue]:
    return [_parse_rust_regex_contract_issue(error, index) for index, error in enumerate(errors)]


def _parse_rust_regex_contract_issue(error_value: object, index: int) -> RegexContractIssue:
    error = ensure_json_object(coerce_json_value(error_value), f"regex_contract_result.errors[{index}]")
    return RegexContractIssue(
        issue_code=_read_result_issue_code(error, index),
        rule_type=_read_error_string(error, "rule_type", index),
        field_name=_read_error_string(error, "field_name", index),
        pattern=_read_error_string(error, "pattern", index),
        engine=_read_error_string(error, "engine", index),
        message=_read_error_string(error, "message", index),
        recovery=_read_error_string(error, "recovery", index),
    )


def _read_contract_issue_code(spec: JsonObject, context: str) -> RegexContractIssueCode:
    value = _read_contract_string(spec, "issue_code", context)
    return _coerce_issue_code(value, f"{context}.issue_code")


def _read_result_issue_code(error: JsonObject, index: int) -> RegexContractIssueCode:
    value = _read_error_string(error, "issue_code", index)
    return _coerce_issue_code(value, f"regex_contract_result.errors[{index}].issue_code")


def _coerce_issue_code(value: str, context: str) -> RegexContractIssueCode:
    valid_codes: tuple[RegexContractIssueCode, ...] = (
        "placeholder_rules_invalid",
        "structured_placeholder_rules_invalid",
        "mv_virtual_namebox_rules_invalid",
        "source_residual_rules_invalid",
        "text_rules_invalid",
    )
    if value not in valid_codes:
        raise TypeError(f"{context} 不是有效的规则错误码: {value}")
    return value


def _read_contract_string(spec: JsonObject, key: str, context: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{context}.{key} 必须是字符串")
    return value


def _read_contract_string_list(spec: JsonObject, key: str, context: str) -> list[str]:
    value = spec.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"{context}.{key} 必须是字符串数组")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{context}.{key}[{index}] 必须是字符串")
        result.append(item)
    return result


def _read_error_string(error: JsonObject, key: str, index: int) -> str:
    value = error.get(key)
    if not isinstance(value, str):
        raise TypeError(f"regex_contract_result.errors[{index}].{key} 必须是字符串")
    return value


__all__: list[str] = [
    "RegexContractIssue",
    "RegexContractValidationError",
    "validate_mv_virtual_namebox_regex_contract",
    "validate_source_residual_regex_contract",
    "validate_text_rules_regex_contract",
]
