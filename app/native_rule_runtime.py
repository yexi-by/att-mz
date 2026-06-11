"""Rust rule_runtime 原生 API 适配器。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from app.native_contract import ensure_native_contract_version
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
    summary: JsonObject


@dataclass(frozen=True, slots=True)
class RuleImportCommitResult:
    """规则导入 commit 报告。"""

    status: str
    errors: list[RuleRuntimeIssue]
    warnings: list[RuleRuntimeIssue]
    plan_token: str | None
    summary: JsonObject


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
        summary=ensure_json_object(
            result.get("summary", {}),
            "rule_runtime.prepare_rule_import.summary",
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


__all__ = [
    "RuleImportCommitResult",
    "RuleImportPrepareResult",
    "RuleRuntimeIssue",
    "commit_rule_import",
    "prepare_rule_import",
]
