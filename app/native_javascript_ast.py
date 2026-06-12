"""Rust 原生 JavaScript AST 解析适配层。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from app.native_contract import ensure_native_contract_version
from app.native_quality import build_native_text_rules_payload
from app.rmmz.schema import PluginSourceRuntimeLiteralAuditSeverity, PluginSourceRuntimeLiteralKind
from app.rmmz.text_rules import (
    JsonArray,
    JsonObject,
    JsonValue,
    TextRules,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
)

_LITERAL_KINDS = frozenset(
    {
        "regex_pattern",
        "packer_code",
        "eval_code",
        "user_visible_candidate",
        "unknown",
    }
)
_AUDIT_DEFAULT_SEVERITIES = frozenset({"blocking", "warning", "ignore"})
type NativeRuntimeLiteralIssueInput = (
    tuple[str, str, PluginSourceRuntimeLiteralKind, PluginSourceRuntimeLiteralAuditSeverity]
)


class NativeJavaScriptAstModule(Protocol):
    """PyO3 扩展暴露给 Python 的 JavaScript AST 接口。"""

    def native_contract_version(self) -> int:
        """返回 Rust/Python JSON 契约版本。"""
        raise NotImplementedError

    def parse_javascript_string_spans(self, payload_json: str) -> str:
        """解析 JavaScript 字符串节点范围。"""
        raise NotImplementedError

    def parse_javascript_string_spans_batch(self, payload_json: str) -> str:
        """批量解析 JavaScript 字符串节点范围。"""
        raise NotImplementedError

    def collect_runtime_literal_issue_facts(self, payload_json: str) -> str:
        """批量收集当前运行源码字符串审计风险事实。"""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class NativeJavaScriptAstContext:
    """Rust AST 返回的字符串节点事实语境。"""

    node_kind: str
    property_key: str
    property_path: tuple[str, ...]
    call_name: str
    call_argument_index: int | None
    return_function_name: str
    assignment_name: str


@dataclass(frozen=True, slots=True)
class NativeJavaScriptStringSpan:
    """Rust AST 返回的源码字符串节点范围。"""

    kind: str
    quote: str
    start_index: int
    end_index: int
    content_start_index: int
    content_end_index: int
    ast_context: NativeJavaScriptAstContext
    literal_kind: PluginSourceRuntimeLiteralKind
    audit_default_severity: PluginSourceRuntimeLiteralAuditSeverity


@dataclass(frozen=True, slots=True)
class NativeJavaScriptStringScan:
    """Rust AST 字符串节点扫描结果。"""

    has_error: bool
    spans: list[NativeJavaScriptStringSpan]


@dataclass(frozen=True, slots=True)
class NativeRuntimeLiteralIssueFact:
    """Rust 返回的当前运行源码字符串审计风险事实。"""

    literal_kind: PluginSourceRuntimeLiteralKind
    audit_default_severity: PluginSourceRuntimeLiteralAuditSeverity
    issue_codes: tuple[str, ...]
    placeholder_fragments: tuple[str, ...]
    control_code_hints: JsonArray


def parse_native_javascript_string_spans(source: str) -> NativeJavaScriptStringScan:
    """调用 Rust AST 解析器收集普通字符串节点范围。"""
    native_module = _load_native_javascript_ast_module()
    result_text = native_module.parse_javascript_string_spans(
        json.dumps({"source": source}, ensure_ascii=False)
    )
    result = ensure_json_object(
        # json.loads 的返回值来自动态 JSON 边界，立即交给 coerce_json_value 收窄。
        coerce_json_value(cast(object, json.loads(result_text))),
        "native_javascript_ast_result",
    )
    spans = [
        _parse_native_span(span, index)
        for index, span in enumerate(ensure_json_array(result["spans"], "native_javascript_ast_result.spans"))
    ]
    has_error = result["has_error"]
    if not isinstance(has_error, bool):
        raise TypeError("native_javascript_ast_result.has_error 必须是布尔值")
    return NativeJavaScriptStringScan(
        has_error=has_error,
        spans=spans,
    )


def parse_native_javascript_string_spans_batch(
    files: Mapping[str, str],
) -> dict[str, NativeJavaScriptStringScan]:
    """批量调用 Rust AST 解析器收集多个源码文件的字符串节点范围。"""
    native_module = _load_native_javascript_ast_module()
    result_text = native_module.parse_javascript_string_spans_batch(
        json.dumps(
            {
                "files": [
                    {"file_name": file_name, "source": source}
                    for file_name, source in sorted(files.items())
                ]
            },
            ensure_ascii=False,
        )
    )
    result = ensure_json_object(
        coerce_json_value(cast(object, json.loads(result_text))),
        "native_javascript_ast_batch_result",
    )
    scans: dict[str, NativeJavaScriptStringScan] = {}
    for index, raw_file in enumerate(ensure_json_array(result["files"], "native_javascript_ast_batch_result.files")):
        file_result = ensure_json_object(raw_file, f"native_javascript_ast_batch_result.files[{index}]")
        file_name = _ensure_string(
            file_result["file_name"],
            f"native_javascript_ast_batch_result.files[{index}].file_name",
        )
        has_error = file_result["has_error"]
        if not isinstance(has_error, bool):
            raise TypeError(f"native_javascript_ast_batch_result.files[{index}].has_error 必须是布尔值")
        spans = [
            _parse_native_span(span, span_index)
            for span_index, span in enumerate(
                ensure_json_array(
                    file_result["spans"],
                    f"native_javascript_ast_batch_result.files[{index}].spans",
                )
            )
        ]
        scans[file_name] = NativeJavaScriptStringScan(
            has_error=has_error,
            spans=spans,
        )
    missing_files = set(files) - set(scans)
    if missing_files:
        samples = "、".join(sorted(missing_files)[:5])
        raise RuntimeError(f"批量 JS AST 结果缺少文件: {samples}")
    return scans


def collect_native_runtime_literal_issue_facts(
    *,
    literals: Mapping[str, NativeRuntimeLiteralIssueInput],
    text_rules: TextRules,
) -> dict[str, NativeRuntimeLiteralIssueFact]:
    """调用 Rust 批量收集当前运行源码字符串审计风险事实。"""
    native_module = _load_native_javascript_ast_module()
    result_text = native_module.collect_runtime_literal_issue_facts(
        json.dumps(
            {
                "literals": [
                    _runtime_literal_issue_fact_payload(literal_id, literal)
                    for literal_id, literal in sorted(literals.items())
                ],
                "text_rules": build_native_text_rules_payload(text_rules),
            },
            ensure_ascii=False,
        )
    )
    result = ensure_json_object(
        coerce_json_value(cast(object, json.loads(result_text))),
        "native_runtime_literal_issue_facts_result",
    )
    facts: dict[str, NativeRuntimeLiteralIssueFact] = {}
    raw_facts = ensure_json_array(result["facts"], "native_runtime_literal_issue_facts_result.facts")
    for index, raw_fact in enumerate(raw_facts):
        fact = ensure_json_object(raw_fact, f"native_runtime_literal_issue_facts_result.facts[{index}]")
        literal_id = _ensure_string(
            _required_runtime_literal_fact_field(fact, "id", index),
            f"native_runtime_literal_issue_facts_result.facts[{index}].id",
        )
        literal_kind = _ensure_literal_kind(
            _required_runtime_literal_fact_field(fact, "literal_kind", index, literal_id),
            f"native_runtime_literal_issue_facts_result.facts[{index}].literal_kind",
        )
        audit_default_severity = _ensure_audit_default_severity(
            _required_runtime_literal_fact_field(fact, "audit_default_severity", index, literal_id),
            f"native_runtime_literal_issue_facts_result.facts[{index}].audit_default_severity",
        )
        facts[literal_id] = NativeRuntimeLiteralIssueFact(
            literal_kind=literal_kind,
            audit_default_severity=audit_default_severity,
            issue_codes=tuple(
                _ensure_string(code, f"native_runtime_literal_issue_facts_result.facts[{index}].issue_codes[]")
                for code in ensure_json_array(
                    _required_runtime_literal_fact_field(fact, "issue_codes", index, literal_id),
                    f"native_runtime_literal_issue_facts_result.facts[{index}].issue_codes",
                )
            ),
            placeholder_fragments=tuple(
                _ensure_string(
                    fragment,
                    f"native_runtime_literal_issue_facts_result.facts[{index}].placeholder_fragments[]",
                )
                for fragment in ensure_json_array(
                    _required_runtime_literal_fact_field(fact, "placeholder_fragments", index, literal_id),
                    f"native_runtime_literal_issue_facts_result.facts[{index}].placeholder_fragments",
                )
            ),
            control_code_hints=ensure_json_array(
                _required_runtime_literal_fact_field(fact, "control_code_hints", index, literal_id),
                f"native_runtime_literal_issue_facts_result.facts[{index}].control_code_hints",
            ),
        )
    missing_ids = set(literals) - set(facts)
    if missing_ids:
        samples = "、".join(sorted(missing_ids)[:5])
        raise RuntimeError(f"运行源码字符串风险事实缺少条目: {samples}")
    return facts


def _runtime_literal_issue_fact_payload(
    literal_id: str,
    literal: NativeRuntimeLiteralIssueInput,
) -> JsonObject:
    """构造 Rust runtime literal fact 输入，分类只透传 Rust AST 已产出的字段。"""
    raw_text, text, literal_kind, audit_default_severity = literal
    return {
        "id": literal_id,
        "raw_text": raw_text,
        "text": text,
        "literal_kind": literal_kind,
        "audit_default_severity": audit_default_severity,
    }


def _required_runtime_literal_fact_field(
    fact: JsonObject,
    field_name: str,
    index: int,
    literal_id: str | None = None,
) -> JsonValue:
    """读取 Rust runtime literal fact 必填字段，缺失时给出可定位错误。"""
    if field_name not in fact:
        location = f"native_runtime_literal_issue_facts_result.facts[{index}]"
        if literal_id is not None:
            location = f"{location}, id={literal_id}"
        message = (
            f"Rust runtime literal fact 缺少必填字段 {field_name}: "
            f"{location}"
        )
        raise RuntimeError(message)
    return fact[field_name]


def _load_native_javascript_ast_module() -> NativeJavaScriptAstModule:
    """加载 PyO3 扩展，缺失入口时直接报错。"""
    native_module = import_module("app._native")
    ensure_native_contract_version(cast(object, native_module))
    if not hasattr(native_module, "parse_javascript_string_spans"):
        raise RuntimeError("Rust 原生扩展缺少 JavaScript AST 解析入口，请重新执行 uv run maturin develop")
    return cast(NativeJavaScriptAstModule, cast(object, native_module))


def _parse_native_span(value: JsonValue, index: int) -> NativeJavaScriptStringSpan:
    """把单个 AST 范围从 JSON 收窄成 Python 结构。"""
    span = ensure_json_object(value, f"native_javascript_ast_result.spans[{index}]")
    ast_context = _parse_native_ast_context(
        span.get("ast_context"),
        f"native_javascript_ast_result.spans[{index}].ast_context",
    )
    return NativeJavaScriptStringSpan(
        kind=_ensure_string(span["kind"], f"native_javascript_ast_result.spans[{index}].kind"),
        quote=_ensure_string(span["quote"], f"native_javascript_ast_result.spans[{index}].quote"),
        start_index=_ensure_int(span["start_index"], f"native_javascript_ast_result.spans[{index}].start_index"),
        end_index=_ensure_int(span["end_index"], f"native_javascript_ast_result.spans[{index}].end_index"),
        content_start_index=_ensure_int(
            span["content_start_index"],
            f"native_javascript_ast_result.spans[{index}].content_start_index",
        ),
        content_end_index=_ensure_int(
            span["content_end_index"],
            f"native_javascript_ast_result.spans[{index}].content_end_index",
        ),
        ast_context=ast_context,
        literal_kind=_ensure_literal_kind(
            span["literal_kind"],
            f"native_javascript_ast_result.spans[{index}].literal_kind",
        ),
        audit_default_severity=_ensure_audit_default_severity(
            span["audit_default_severity"],
            f"native_javascript_ast_result.spans[{index}].audit_default_severity",
        ),
    )


def _parse_native_ast_context(value: JsonValue | None, label: str) -> NativeJavaScriptAstContext:
    """把 AST 上下文 JSON 收窄成 Python 结构。"""
    if value is None:
        raise TypeError(f"{label} 必须存在")
    context = ensure_json_object(value, label)
    return NativeJavaScriptAstContext(
        node_kind=_ensure_string(context["node_kind"], f"{label}.node_kind"),
        property_key=_ensure_string(context["property_key"], f"{label}.property_key"),
        property_path=tuple(
            _ensure_string(item, f"{label}.property_path[{index}]")
            for index, item in enumerate(ensure_json_array(context["property_path"], f"{label}.property_path"))
        ),
        call_name=_ensure_string(context["call_name"], f"{label}.call_name"),
        call_argument_index=_ensure_optional_int(context["call_argument_index"], f"{label}.call_argument_index"),
        return_function_name=_ensure_string(
            context["return_function_name"],
            f"{label}.return_function_name",
        ),
        assignment_name=_ensure_string(context["assignment_name"], f"{label}.assignment_name"),
    )


def _ensure_string(value: object, label: str) -> str:
    """校验 JSON 字段是字符串。"""
    if not isinstance(value, str):
        raise TypeError(f"{label} 必须是字符串")
    return value


def _ensure_literal_kind(value: object, label: str) -> PluginSourceRuntimeLiteralKind:
    """校验 literal_kind 是当前 native contract 支持的枚举。"""
    return cast(PluginSourceRuntimeLiteralKind, _ensure_string_choice(value, label, _LITERAL_KINDS))


def _ensure_audit_default_severity(
    value: object,
    label: str,
) -> PluginSourceRuntimeLiteralAuditSeverity:
    """校验 audit_default_severity 是当前 native contract 支持的枚举。"""
    return cast(
        PluginSourceRuntimeLiteralAuditSeverity,
        _ensure_string_choice(value, label, _AUDIT_DEFAULT_SEVERITIES),
    )


def _ensure_string_choice(value: object, label: str, choices: frozenset[str]) -> str:
    """校验 JSON 字段是指定枚举字符串。"""
    text = _ensure_string(value, label)
    if text not in choices:
        expected = "、".join(sorted(choices))
        raise TypeError(f"{label} 必须是以下字符串之一: {expected}")
    return text


def _ensure_int(value: object, label: str) -> int:
    """校验 JSON 字段是整数。"""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} 必须是整数")
    return value


def _ensure_optional_int(value: object, label: str) -> int | None:
    """校验 JSON 字段是整数或 null。"""
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} 必须是整数或 null")
    return value


__all__ = [
    "NativeJavaScriptAstContext",
    "NativeRuntimeLiteralIssueFact",
    "NativeRuntimeLiteralIssueInput",
    "NativeJavaScriptStringScan",
    "NativeJavaScriptStringSpan",
    "collect_native_runtime_literal_issue_facts",
    "parse_native_javascript_string_spans",
    "parse_native_javascript_string_spans_batch",
]
