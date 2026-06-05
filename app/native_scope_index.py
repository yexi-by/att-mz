"""Rust Scope/Index Engine 原生适配层。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from app.native_contract import ensure_native_contract_version
from app.rmmz.schema import (
    COMMON_EVENTS_FILE_NAME,
    MAP_PATTERN,
    MvVirtualNameboxRuleRecord,
    PLUGINS_FILE_NAME,
    TROOPS_FILE_NAME,
    GameData,
    TranslationData,
)
from app.rmmz.text_rules import (
    JsonArray,
    JsonObject,
    JsonValue,
    TextRules,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
)

_PLUGIN_SOURCE_RUST_PREFILTER_PATTERN = r"[\s\S]"


class NativeScopeIndexModule(Protocol):
    """PyO3 扩展暴露的 Scope/Index Engine 接口。"""

    def native_contract_version(self) -> int:
        """返回 Rust/Python JSON 契约版本。"""
        raise NotImplementedError

    def build_scope_index(self, payload_json: str) -> str:
        """构建当前范围索引并返回 JSON 文本。"""
        raise NotImplementedError

    def scan_rule_candidates(self, payload_json: str) -> str:
        """扫描规则候选并返回 JSON 文本。"""
        raise NotImplementedError

    def evaluate_scope_gate(self, payload_json: str) -> str:
        """评估范围门禁并返回 JSON 文本。"""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class NativeScopeIndexResult:
    """Rust Scope/Index Engine 构建结果。"""

    text_index_rows: list[JsonObject]
    scope_summary: JsonObject
    domain_summary: list[JsonObject]
    rule_hit_summary: list[JsonObject]
    candidate_summary: list[JsonObject]
    unwritable_reasons: list[JsonObject]
    stale_rule_details: list[JsonObject]
    writable_location_paths: list[str]


@dataclass(frozen=True, slots=True)
class NativeRuleCandidatesResult:
    """Rust 规则候选扫描结果。"""

    candidates: JsonArray
    candidate_summary: list[JsonObject]
    scan_summary: JsonObject


@dataclass(frozen=True, slots=True)
class NativeScopeGateResult:
    """Rust 范围门禁评估结果。"""

    workflow_gate: JsonObject
    quality_gate: JsonObject
    pending_count: int
    translated_count: int
    quality_error_count: int
    writable_location_paths: list[str]


def build_native_scope_index(payload: JsonObject) -> NativeScopeIndexResult:
    """调用 Rust 构建范围索引。"""
    native_module = _load_native_scope_index_module()
    result_text = native_module.build_scope_index(json.dumps(payload, ensure_ascii=False))
    result = _load_result_object(result_text, "native_scope_index_result")
    return NativeScopeIndexResult(
        text_index_rows=_read_object_array(result, "text_index_rows", "native_scope_index_result"),
        scope_summary=ensure_json_object(result["scope_summary"], "native_scope_index_result.scope_summary"),
        domain_summary=_read_object_array(result, "domain_summary", "native_scope_index_result"),
        rule_hit_summary=_read_object_array(result, "rule_hit_summary", "native_scope_index_result"),
        candidate_summary=_read_object_array(result, "candidate_summary", "native_scope_index_result"),
        unwritable_reasons=_read_object_array(result, "unwritable_reasons", "native_scope_index_result"),
        stale_rule_details=_read_object_array(result, "stale_rule_details", "native_scope_index_result"),
        writable_location_paths=_read_string_array(
            result,
            "writable_location_paths",
            "native_scope_index_result",
        ),
    )


def scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
    """调用 Rust 扫描规则候选。"""
    native_module = _load_native_scope_index_module()
    result_text = native_module.scan_rule_candidates(json.dumps(payload, ensure_ascii=False))
    result = _load_result_object(result_text, "native_rule_candidates_result")
    return NativeRuleCandidatesResult(
        candidates=ensure_json_array(result["candidates"], "native_rule_candidates_result.candidates"),
        candidate_summary=_read_object_array(result, "candidate_summary", "native_rule_candidates_result"),
        scan_summary=ensure_json_object(
            result["scan_summary"],
            "native_rule_candidates_result.scan_summary",
        ),
    )


def evaluate_native_scope_gate(payload: JsonObject) -> NativeScopeGateResult:
    """调用 Rust 评估范围门禁。"""
    native_module = _load_native_scope_index_module()
    result_text = native_module.evaluate_scope_gate(json.dumps(payload, ensure_ascii=False))
    result = _load_result_object(result_text, "native_scope_gate_result")
    return NativeScopeGateResult(
        workflow_gate=ensure_json_object(result["workflow_gate"], "native_scope_gate_result.workflow_gate"),
        quality_gate=ensure_json_object(result["quality_gate"], "native_scope_gate_result.quality_gate"),
        pending_count=_read_int(result, "pending_count", "native_scope_gate_result"),
        translated_count=_read_int(result, "translated_count", "native_scope_gate_result"),
        quality_error_count=_read_int(result, "quality_error_count", "native_scope_gate_result"),
        writable_location_paths=_read_string_array(
            result,
            "writable_location_paths",
            "native_scope_gate_result",
        ),
    )


def build_native_rule_candidate_text_rules_payload(text_rules: TextRules) -> JsonObject:
    """把提取阶段文本规则压成 Rust 规则候选扫描输入结构。"""
    setting = text_rules.setting
    return {
        "custom_placeholder_rules": [
            {
                "pattern_text": rule.pattern_text,
                "placeholder_template": rule.placeholder_template,
            }
            for rule in text_rules.custom_placeholder_rules
        ],
        "structured_placeholder_rules": [
            {
                "rule_name": rule.rule_name,
                "rule_type": rule.rule_type,
                "pattern_text": rule.pattern_text,
                "translatable_group": rule.translatable_group,
                "protected_groups": dict(rule.protected_groups),
            }
            for rule in text_rules.structured_placeholder_rules
        ],
        "strip_wrapping_punctuation_pairs": [
            [left, right] for left, right in setting.strip_wrapping_punctuation_pairs
        ],
        # source_text_required_pattern 只承诺 Python re；Rust 这里只做宽松预筛，
        # 命令报告层再用 TextRules.should_translate_source_text 做最终过滤。
        "source_text_required_pattern": _PLUGIN_SOURCE_RUST_PREFILTER_PATTERN,
        "source_text_exclusion_profile": setting.source_text_exclusion_profile,
    }


def build_native_plugin_source_candidates_payload(
    *,
    plugin_source_files: dict[str, str],
    enabled_plugin_files: set[str] | frozenset[str],
    text_rules: TextRules,
) -> JsonObject:
    """构造 Rust 插件源码候选扫描载荷。"""
    return {
        "plugin_source_files": [
            {
                "file_name": file_name,
                "source": source,
                "active": file_name in enabled_plugin_files,
            }
            for file_name, source in sorted(plugin_source_files.items())
        ],
        "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
    }


def build_native_nonstandard_data_candidates_payload(
    *,
    nonstandard_data_files: dict[str, JsonValue],
    text_rules: TextRules,
) -> JsonObject:
    """构造 Rust 非标准 data 候选扫描载荷。"""
    return {
        "nonstandard_data_files": [
            {
                "file_name": file_name,
                "data": data,
            }
            for file_name, data in sorted(nonstandard_data_files.items())
        ],
        "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
    }


def build_native_nonstandard_data_leaves_payload(
    nonstandard_data_files: dict[str, JsonValue],
) -> JsonObject:
    """构造 Rust 非标准 data leaves-only 扫描载荷。"""
    return {
        "nonstandard_data_leaves": [
            {
                "file_name": file_name,
                "data": data,
            }
            for file_name, data in sorted(nonstandard_data_files.items())
        ],
    }


def build_native_placeholder_candidates_payload(
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> JsonObject:
    """构造 Rust 普通占位符候选扫描载荷。"""
    placeholder_texts: JsonArray = []
    for translation_data in translation_data_map.values():
        for item in translation_data.translation_items:
            for line_index, text in enumerate(item.original_lines):
                placeholder_texts.append(
                    {
                        "source_name": f"{item.location_path}#{line_index}",
                        "text": text,
                    }
                )
    return {
        "placeholder_texts": placeholder_texts,
        "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
    }


def build_native_structured_placeholder_candidates_payload(
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> JsonObject:
    """构造 Rust 结构化占位符候选扫描载荷。"""
    structured_placeholder_texts: JsonArray = []
    for translation_data in translation_data_map.values():
        for item in translation_data.translation_items:
            for line_index, text in enumerate(item.original_lines):
                structured_placeholder_texts.append(
                    {
                        "location_path": item.location_path,
                        "line_number": line_index + 1,
                        "text": text,
                    }
                )
    return {
        "structured_placeholder_texts": structured_placeholder_texts,
        "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
    }


def build_native_note_tag_candidates_payload(game_data: GameData, text_rules: TextRules) -> JsonObject:
    """构造 Rust Note 标签候选扫描载荷。"""
    note_tag_data_files: JsonObject = {}
    for file_name, value in sorted(game_data.data.items()):
        if file_name == PLUGINS_FILE_NAME or not file_name.endswith(".json") or isinstance(value, str):
            continue
        note_tag_data_files[file_name] = value

    text_rules_payload = build_native_rule_candidate_text_rules_payload(text_rules)
    text_rules_payload["source_text_required_pattern"] = text_rules.setting.source_text_required_pattern
    return {
        "note_tag_data_files": note_tag_data_files,
        "text_rules": text_rules_payload,
    }


def build_native_event_command_candidates_payload(
    *,
    event_command_data_files: dict[str, JsonValue],
    command_codes: set[int] | frozenset[int],
    rules: JsonArray | None = None,
) -> JsonObject:
    """构造 Rust 事件指令候选扫描载荷。"""
    data_file_payloads: JsonArray = [
        {
            "file_name": file_name,
            "data": data,
        }
        for file_name, data in sorted(event_command_data_files.items())
    ]
    command_code_payloads = cast(JsonArray, [code for code in sorted(command_codes)])
    payload: JsonObject = {
        "event_command_data_files": data_file_payloads,
        "event_command_codes": command_code_payloads,
    }
    if rules is not None:
        payload["event_command_rules"] = list(rules)
    return payload


def build_native_plugin_config_candidates_payload(
    *,
    game_data: GameData,
    text_rules: TextRules,
    rules: JsonArray | None = None,
) -> JsonObject:
    """构造 Rust 插件参数规则候选扫描载荷。"""
    payload: JsonObject = {
        "plugin_config_plugins": [
            {
                "plugin_index": plugin_index,
                "plugin_name": _extract_native_plugin_name(plugin, plugin_index),
                "plugin": plugin,
            }
            for plugin_index, plugin in enumerate(game_data.plugins_js)
        ],
        "text_rules": build_native_rule_candidate_text_rules_payload(text_rules),
    }
    if rules is not None:
        payload["plugin_config_rules"] = list(rules)
    return payload


def build_native_mv_virtual_namebox_candidates_payload(
    *,
    game_data: GameData,
    rules: JsonArray | None = None,
) -> JsonObject:
    """构造 Rust MV 虚拟名字框候选扫描载荷。"""
    payload: JsonObject = {
        "mv_virtual_namebox_data_files": [
            {
                "file_name": file_name,
                "data": data,
            }
            for file_name, data in sorted(build_native_event_command_data_files(game_data).items())
        ],
        "mv_virtual_namebox_actor_names": [
            {
                "actor_id": actor.id,
                "name": actor.name,
            }
            for actor in game_data.base_data.get("Actors.json", [])
            if actor is not None
        ],
    }
    if rules is not None:
        payload["mv_virtual_namebox_rules"] = list(rules)
    return payload


def mv_virtual_namebox_rule_records_to_native_rules(records: list[MvVirtualNameboxRuleRecord]) -> JsonArray:
    """把 MV 虚拟名字框数据库规则记录转换为 Rust 输入。"""
    return [
        {
            "rule_order": record.rule_order,
            "rule_name": record.rule_name,
            "pattern_text": record.pattern_text,
            "speaker_group": record.speaker_group,
            "body_group": record.body_group,
            "speaker_policy": record.speaker_policy,
            "render_template": record.render_template,
        }
        for record in records
    ]


def build_native_event_command_data_files(game_data: GameData) -> dict[str, JsonValue]:
    """返回事件指令 native 扫描需要的标准 data 文件。"""
    return {
        file_name: data
        for file_name, data in game_data.data.items()
        if _is_event_command_data_file(file_name)
    }


def _is_event_command_data_file(file_name: str) -> bool:
    """判断 data 文件是否包含 RPG Maker 事件指令列表。"""
    return (
        file_name == COMMON_EVENTS_FILE_NAME
        or file_name == TROOPS_FILE_NAME
        or MAP_PATTERN.fullmatch(file_name) is not None
    )


def _extract_native_plugin_name(plugin: dict[str, JsonValue], plugin_index: int) -> str:
    """按插件参数规则语义读取插件名。"""
    plugin_name = plugin.get("name")
    if isinstance(plugin_name, str) and plugin_name.strip():
        return plugin_name.strip()
    return f"unnamed_plugin_{plugin_index}"


def _load_native_scope_index_module() -> NativeScopeIndexModule:
    """加载 PyO3 扩展并确认 Scope/Index Engine 入口存在。"""
    try:
        native_module = import_module("app._native")
    except ImportError as error:
        raise RuntimeError("Rust 原生扩展不可用，请先执行 uv run maturin develop") from error
    ensure_native_contract_version(cast(object, native_module))
    for entry_name in ("build_scope_index", "scan_rule_candidates", "evaluate_scope_gate"):
        if not hasattr(native_module, entry_name):
            raise RuntimeError(f"Rust 原生扩展缺少 Scope/Index Engine 入口 {entry_name}，请重新执行 uv run maturin develop")
    return cast(NativeScopeIndexModule, cast(object, native_module))


def _load_result_object(result_text: str, label: str) -> JsonObject:
    """把 Rust JSON 文本解析为对象。"""
    return ensure_json_object(
        coerce_json_value(cast(object, json.loads(result_text))),
        label,
    )


def _read_object_array(result: JsonObject, field_name: str, label: str) -> list[JsonObject]:
    """读取 JSON 对象数组字段。"""
    return [
        ensure_json_object(item, f"{label}.{field_name}[{index}]")
        for index, item in enumerate(ensure_json_array(result[field_name], f"{label}.{field_name}"))
    ]


def _read_string_array(result: JsonObject, field_name: str, label: str) -> list[str]:
    """读取字符串数组字段。"""
    values: list[str] = []
    for index, item in enumerate(ensure_json_array(result[field_name], f"{label}.{field_name}")):
        if not isinstance(item, str):
            raise TypeError(f"{label}.{field_name}[{index}] 必须是字符串")
        values.append(item)
    return values


def _read_int(result: JsonObject, field_name: str, label: str) -> int:
    """读取非布尔整数字段。"""
    value = result[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label}.{field_name} 必须是整数")
    return value


__all__ = [
    "NativeRuleCandidatesResult",
    "NativeScopeGateResult",
    "NativeScopeIndexResult",
    "build_native_event_command_data_files",
    "build_native_event_command_candidates_payload",
    "build_native_mv_virtual_namebox_candidates_payload",
    "build_native_nonstandard_data_candidates_payload",
    "build_native_nonstandard_data_leaves_payload",
    "build_native_note_tag_candidates_payload",
    "build_native_placeholder_candidates_payload",
    "build_native_plugin_config_candidates_payload",
    "build_native_plugin_source_candidates_payload",
    "build_native_rule_candidate_text_rules_payload",
    "build_native_scope_index",
    "build_native_structured_placeholder_candidates_payload",
    "evaluate_native_scope_gate",
    "mv_virtual_namebox_rule_records_to_native_rules",
    "scan_native_rule_candidates",
]
