"""Rust rule_runtime 原生 API 适配器。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from app.native_contract import ensure_native_contract_version
from app.config.schemas import TextRulesSetting
from app.rmmz.json_types import (
    JsonObject,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
)


@dataclass(frozen=True, slots=True)
class RuleRuntimeIssue:
    """Rust rule_runtime 返回的结构化问题。"""

    code: str
    message: str
    field: str | None


@dataclass(frozen=True, slots=True)
class RuleImportPrepareResult:
    """规则导入 prepare 报告。"""

    status: str
    errors: list[RuleRuntimeIssue]
    warnings: list[RuleRuntimeIssue]
    plan_token: str | None
    prepared_plan: JsonObject | None
    summary: JsonObject
    details: JsonObject


@dataclass(frozen=True, slots=True)
class RuleImportCommitResult:
    """规则导入 commit 报告。"""

    status: str
    errors: list[RuleRuntimeIssue]
    warnings: list[RuleRuntimeIssue]
    plan_token: str | None
    summary: JsonObject
    details: JsonObject


@dataclass(frozen=True, slots=True)
class RuntimeConfigEvaluationEntry:
    """单条文本的运行时配置正则执行结果。"""

    id: str
    source_text_required: bool
    line_width_count: int


@dataclass(frozen=True, slots=True)
class RuntimeConfigEvaluationResult:
    """配置正则执行报告。"""

    status: str
    errors: list[RuleRuntimeIssue]
    entries: list[RuntimeConfigEvaluationEntry]


@dataclass(frozen=True, slots=True)
class RuleRuntimeControlSpan:
    """Rust rule_runtime 返回的控制符保护跨度。"""

    start_index: int
    end_index: int
    original: str
    source: str
    placeholder: str | None
    custom_template: str | None
    priority: int
    custom_index_key: str | None


@dataclass(frozen=True, slots=True)
class RuleRuntimeMvVirtualNameboxMatch:
    """Rust rule_runtime 返回的 MV 虚拟名字框命中。"""

    rule_order: int
    rule_name: str
    matched_text: str
    group_values: dict[str, str]


class _NativeRuleRuntimeModule(Protocol):
    """PyO3 扩展暴露的 rule_runtime 接口。"""

    def native_contract_version(self) -> int:
        """返回 Rust/Python JSON 契约版本。"""
        raise NotImplementedError

    def prepare_rule_import(self, payload_json: str) -> str:
        """预检规则导入并返回 JSON 文本。"""
        raise NotImplementedError

    def commit_rule_import(self, payload_json: str) -> str:
        """提交规则导入计划并返回 JSON 文本。"""
        raise NotImplementedError

    def evaluate_runtime_config_patterns(self, payload_json: str) -> str:
        """执行配置中的运行时正则并返回 JSON 文本。"""
        raise NotImplementedError

    def build_rules_fingerprint(self, payload_json: str) -> str:
        """读取统一规则表并返回规则指纹文本。"""
        raise NotImplementedError

    def collect_control_sequence_spans(self, payload_json: str) -> str:
        """执行控制符规则并返回保护跨度 JSON 文本。"""
        raise NotImplementedError

    def match_mv_virtual_namebox_rules(self, payload_json: str) -> str:
        """执行 MV 虚拟名字框规则并返回命中 JSON 文本。"""
        raise NotImplementedError


def prepare_rule_import(payload: JsonObject) -> RuleImportPrepareResult:
    """调用 Rust rule_runtime prepare。"""
    native = _load_native_module()
    result = _call_native_json(
        native.prepare_rule_import,
        payload,
        "rule_runtime.prepare_rule_import",
    )
    return RuleImportPrepareResult(
        status=_read_string(result, "status", "rule_runtime.prepare_rule_import"),
        errors=_read_issues(
            result.get("errors", []),
            "rule_runtime.prepare_rule_import.errors",
        ),
        warnings=_read_issues(
            result.get("warnings", []),
            "rule_runtime.prepare_rule_import.warnings",
        ),
        plan_token=_read_optional_string(
            result,
            "plan_token",
            "rule_runtime.prepare_rule_import",
        ),
        prepared_plan=_read_optional_json_object(
            result,
            "prepared_plan",
            "rule_runtime.prepare_rule_import",
        ),
        summary=ensure_json_object(
            result.get("summary", {}),
            "rule_runtime.prepare_rule_import.summary",
        ),
        details=ensure_json_object(
            result.get("details", {}),
            "rule_runtime.prepare_rule_import.details",
        ),
    )


def commit_rule_import(payload: JsonObject) -> RuleImportCommitResult:
    """调用 Rust rule_runtime commit。"""
    native = _load_native_module()
    result = _call_native_json(
        native.commit_rule_import,
        payload,
        "rule_runtime.commit_rule_import",
    )
    return RuleImportCommitResult(
        status=_read_string(result, "status", "rule_runtime.commit_rule_import"),
        errors=_read_issues(
            result.get("errors", []),
            "rule_runtime.commit_rule_import.errors",
        ),
        warnings=_read_issues(
            result.get("warnings", []),
            "rule_runtime.commit_rule_import.warnings",
        ),
        plan_token=_read_optional_string(
            result,
            "plan_token",
            "rule_runtime.commit_rule_import",
        ),
        summary=ensure_json_object(
            result.get("summary", {}),
            "rule_runtime.commit_rule_import.summary",
        ),
        details=ensure_json_object(
            result.get("details", {}),
            "rule_runtime.commit_rule_import.details",
        ),
    )


def runtime_config_patterns_from_setting(setting: TextRulesSetting) -> JsonObject:
    """把配置中的用户可写正则转换为 rule_runtime 输入。"""
    return {
        "source_text_required_pattern": setting.source_text_required_pattern,
        "source_residual_segment_pattern": setting.source_residual_segment_pattern,
        "line_width_count_pattern": setting.line_width_count_pattern,
        "residual_escape_sequence_pattern": setting.residual_escape_sequence_pattern,
    }


def evaluate_runtime_config_patterns(payload: JsonObject) -> RuntimeConfigEvaluationResult:
    """调用 Rust rule_runtime 执行配置正则。"""
    native = _load_native_module()
    result = _call_native_json(
        native.evaluate_runtime_config_patterns,
        payload,
        "rule_runtime.evaluate_runtime_config_patterns",
    )
    return RuntimeConfigEvaluationResult(
        status=_read_string(
            result,
            "status",
            "rule_runtime.evaluate_runtime_config_patterns",
        ),
        errors=_read_issues(
            result.get("errors", []),
            "rule_runtime.evaluate_runtime_config_patterns.errors",
        ),
        entries=_read_runtime_config_entries(
            result.get("entries", []),
            "rule_runtime.evaluate_runtime_config_patterns.entries",
        ),
    )


def build_rules_fingerprint(payload: JsonObject) -> str:
    """调用 Rust rule_runtime 生成统一规则指纹。"""
    native = _load_native_module()
    raw_text = native.build_rules_fingerprint(json.dumps(payload, ensure_ascii=False))
    return raw_text


def collect_control_sequence_spans(payload: JsonObject) -> list[RuleRuntimeControlSpan]:
    """调用 Rust rule_runtime 执行用户/Agent 可写控制符规则。"""
    native = _load_native_module()
    result = _call_native_json(
        native.collect_control_sequence_spans,
        payload,
        "rule_runtime.collect_control_sequence_spans",
    )
    return _read_control_spans(
        result.get("spans", []),
        "rule_runtime.collect_control_sequence_spans.spans",
    )


def validate_control_sequence_rules(
    *,
    custom_placeholder_rules: list[JsonObject],
    structured_placeholder_rules: list[JsonObject],
) -> None:
    """仅编译校验用户/Agent 可写控制符规则，不消费匹配结果。"""
    payload = cast(
        JsonObject,
        {
            "text": "",
            "custom_placeholder_rules": custom_placeholder_rules,
            "structured_placeholder_rules": structured_placeholder_rules,
        },
    )
    _ = collect_control_sequence_spans(payload)


def match_mv_virtual_namebox_rules(payload: JsonObject) -> list[RuleRuntimeMvVirtualNameboxMatch]:
    """调用 Rust rule_runtime 执行 MV 虚拟名字框规则。"""
    native = _load_native_module()
    result = _call_native_json(
        native.match_mv_virtual_namebox_rules,
        payload,
        "rule_runtime.match_mv_virtual_namebox_rules",
    )
    return _read_mv_virtual_namebox_matches(
        result.get("matches", []),
        "rule_runtime.match_mv_virtual_namebox_rules.matches",
    )


def _load_native_module() -> _NativeRuleRuntimeModule:
    native_module = cast(object, import_module("app._native"))
    ensure_native_contract_version(native_module)
    return cast(_NativeRuleRuntimeModule, native_module)


def _call_native_json(
    native_function: object,
    payload: JsonObject,
    context: str,
) -> JsonObject:
    if not callable(native_function):
        raise RuntimeError(f"Rust 原生扩展缺少 {context} 入口，请重新执行 uv run maturin develop")
    raw_text = native_function(json.dumps(payload, ensure_ascii=False))
    if not isinstance(raw_text, str):
        raise TypeError(f"{context} 必须返回 JSON 字符串")
    raw_result = cast(object, json.loads(raw_text))
    return ensure_json_object(coerce_json_value(raw_result), context)


def _read_issues(value: object, context: str) -> list[RuleRuntimeIssue]:
    issues: list[RuleRuntimeIssue] = []
    for index, raw_issue in enumerate(ensure_json_array(coerce_json_value(value), context)):
        issue = ensure_json_object(raw_issue, f"{context}[{index}]")
        issues.append(
            RuleRuntimeIssue(
                code=_read_string(issue, "code", f"{context}[{index}]"),
                message=_read_string(issue, "message", f"{context}[{index}]"),
                field=_read_optional_string(issue, "field", f"{context}[{index}]"),
            )
        )
    return issues


def _read_runtime_config_entries(
    value: object,
    context: str,
) -> list[RuntimeConfigEvaluationEntry]:
    entries: list[RuntimeConfigEvaluationEntry] = []
    for index, raw_entry in enumerate(ensure_json_array(coerce_json_value(value), context)):
        entry = ensure_json_object(raw_entry, f"{context}[{index}]")
        source_text_required = entry.get("source_text_required")
        if not isinstance(source_text_required, bool):
            raise TypeError(f"{context}[{index}].source_text_required 必须是布尔值")
        entries.append(
            RuntimeConfigEvaluationEntry(
                id=_read_string(entry, "id", f"{context}[{index}]"),
                source_text_required=source_text_required,
                line_width_count=_read_int(
                    entry,
                    "line_width_count",
                    f"{context}[{index}]",
                ),
            )
        )
    return entries


def _read_control_spans(value: object, context: str) -> list[RuleRuntimeControlSpan]:
    spans: list[RuleRuntimeControlSpan] = []
    for index, raw_span in enumerate(ensure_json_array(coerce_json_value(value), context)):
        span = ensure_json_object(raw_span, f"{context}[{index}]")
        spans.append(
            RuleRuntimeControlSpan(
                start_index=_read_int(span, "start_index", f"{context}[{index}]"),
                end_index=_read_int(span, "end_index", f"{context}[{index}]"),
                original=_read_string(span, "original", f"{context}[{index}]"),
                source=_read_string(span, "source", f"{context}[{index}]"),
                placeholder=_read_optional_string(span, "placeholder", f"{context}[{index}]"),
                custom_template=_read_optional_string(
                    span,
                    "custom_template",
                    f"{context}[{index}]",
                ),
                priority=_read_int(span, "priority", f"{context}[{index}]"),
                custom_index_key=_read_optional_string(
                    span,
                    "custom_index_key",
                    f"{context}[{index}]",
                ),
            )
        )
    return spans


def _read_mv_virtual_namebox_matches(
    value: object,
    context: str,
) -> list[RuleRuntimeMvVirtualNameboxMatch]:
    matches: list[RuleRuntimeMvVirtualNameboxMatch] = []
    for index, raw_match in enumerate(ensure_json_array(coerce_json_value(value), context)):
        matched = ensure_json_object(raw_match, f"{context}[{index}]")
        matches.append(
            RuleRuntimeMvVirtualNameboxMatch(
                rule_order=_read_int(matched, "rule_order", f"{context}[{index}]"),
                rule_name=_read_string(matched, "rule_name", f"{context}[{index}]"),
                matched_text=_read_string(matched, "matched_text", f"{context}[{index}]"),
                group_values=_read_string_map(
                    matched.get("group_values", {}),
                    f"{context}[{index}].group_values",
                ),
            )
        )
    return matches


def _read_string_map(value: object, context: str) -> dict[str, str]:
    raw_map = ensure_json_object(coerce_json_value(value), context)
    result: dict[str, str] = {}
    for key, raw_value in raw_map.items():
        if not isinstance(raw_value, str):
            raise TypeError(f"{context}.{key} 必须是字符串")
        result[key] = raw_value
    return result


def _read_string(payload: JsonObject, field_name: str, context: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise TypeError(f"{context}.{field_name} 必须是字符串")
    return value


def _read_optional_string(payload: JsonObject, field_name: str, context: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{context}.{field_name} 必须是字符串或 null")
    return value


def _read_optional_json_object(payload: JsonObject, field_name: str, context: str) -> JsonObject | None:
    value = payload.get(field_name)
    if value is None:
        return None
    return ensure_json_object(
        coerce_json_value(value),
        f"{context}.{field_name}",
    )


def _read_int(payload: JsonObject, field_name: str, context: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{context}.{field_name} 必须是整数")
    return value


__all__ = [
    "RuntimeConfigEvaluationEntry",
    "RuntimeConfigEvaluationResult",
    "RuleRuntimeControlSpan",
    "RuleImportCommitResult",
    "RuleImportPrepareResult",
    "RuleRuntimeMvVirtualNameboxMatch",
    "RuleRuntimeIssue",
    "build_rules_fingerprint",
    "commit_rule_import",
    "collect_control_sequence_spans",
    "evaluate_runtime_config_patterns",
    "match_mv_virtual_namebox_rules",
    "prepare_rule_import",
    "runtime_config_patterns_from_setting",
    "validate_control_sequence_rules",
]
