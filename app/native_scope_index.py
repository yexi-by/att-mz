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
    PluginSourceTextRuleRecord,
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
_RULE_CANDIDATES_SCHEMA_VERSION = 1
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
RUST_SCOPE_FACTS_CONTRACT_VERSION = 1
PARSER_CONTRACT_VERSION = 1
SOURCE_BRANCH_CONTRACT_VERSION = 1


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

    def native_schema_fingerprint(self) -> str:
        """返回共享 SQLite schema SQL 的 SHA-256 指纹。"""
        raise NotImplementedError

    def inspect_scope_index_storage(self, payload_json: str) -> str:
        """直读 Scope/Index 所需的 DB 状态和游戏文件摘要。"""
        raise NotImplementedError

    def write_scope_index_storage(self, payload_json: str) -> str:
        """直接写入 text index 存储表并返回 JSON 文本。"""
        raise NotImplementedError

    def rebuild_scope_index_storage(self, payload_json: str) -> str:
        """直读 DB/游戏目录并重建 text index 存储。"""
        raise NotImplementedError


class NativeScopeIndexStorageError(RuntimeError):
    """Rust Scope/Index storage 结构化错误。"""

    def __init__(self, *, code: str, message: str) -> None:
        """保留 Rust error code，供 Agent 报告返回稳定错误码。"""
        super().__init__(message)
        self.code: str = code
        self.message: str = message


@dataclass(frozen=True, slots=True)
class NativeContractVersions:
    """Rust scope/index 输出的契约版本集合。"""

    rust_scope_facts: int
    parser: int
    source_branch: int
    text_fact_schema: int


@dataclass(frozen=True, slots=True)
class NativeScopeIndexResult:
    """Rust Scope/Index Engine 构建结果。"""

    contract_versions: NativeContractVersions
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

    schema_version: int
    contract_versions: NativeContractVersions
    candidates: JsonArray
    candidate_summary: list[JsonObject]
    scan_summary: JsonObject
    timings_ms: dict[str, int]
    counters: dict[str, int]


@dataclass(frozen=True, slots=True)
class NativeScopeGateResult:
    """Rust 范围门禁评估结果。"""

    contract_versions: NativeContractVersions
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
        contract_versions=_read_contract_versions(result, "native_scope_index_result"),
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
    schema_version = _read_int(
        result,
        "schema_version",
        "native_rule_candidates_result",
    )
    if schema_version != _RULE_CANDIDATES_SCHEMA_VERSION:
        raise RuntimeError(f"不支持的规则候选 native schema_version: {schema_version}")
    return NativeRuleCandidatesResult(
        schema_version=schema_version,
        contract_versions=_read_contract_versions(result, "native_rule_candidates_result"),
        candidates=ensure_json_array(result["candidates"], "native_rule_candidates_result.candidates"),
        candidate_summary=_read_object_array(result, "candidate_summary", "native_rule_candidates_result"),
        scan_summary=ensure_json_object(
            result["scan_summary"],
            "native_rule_candidates_result.scan_summary",
        ),
        timings_ms=_read_int_map(result, "timings_ms", "native_rule_candidates_result"),
        counters=_read_int_map(result, "counters", "native_rule_candidates_result"),
    )


def native_scan_summary_scope_hash(result: NativeRuleCandidatesResult, summary_key: str) -> str:
    """读取 native 规则候选摘要里的 scope_hash。"""
    summary = ensure_json_object(
        result.scan_summary.get(summary_key),
        f"native_rule_candidates_result.scan_summary.{summary_key}",
    )
    value = summary.get("scope_hash")
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _HEX_DIGITS:
        raise TypeError(f"native_rule_candidates_result.scan_summary.{summary_key}.scope_hash 必须是 64 位 SHA-256 十六进制字符串")
    return value


def collect_native_plugin_config_scope_hash(*, game_data: GameData, text_rules: TextRules) -> str:
    """读取 Rust 插件参数规则确认范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(
            build_native_plugin_config_candidates_payload(
                game_data=game_data,
                text_rules=text_rules,
            )
        ),
        "plugin_config",
    )


def collect_native_event_command_scope_hash(
    *,
    game_data: GameData,
    command_codes: set[int] | frozenset[int],
) -> str:
    """读取 Rust 事件指令规则确认范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(
            build_native_event_command_candidates_payload(
                event_command_data_files=build_native_event_command_data_files(game_data),
                command_codes=command_codes,
            )
        ),
        "event_commands",
    )


def collect_native_note_tag_scope_hash(*, game_data: GameData, text_rules: TextRules) -> str:
    """读取 Rust Note 标签规则确认范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(build_native_note_tag_candidates_payload(game_data, text_rules)),
        "note_tags",
    )


def collect_native_mv_virtual_namebox_scope_hash(*, game_data: GameData) -> str:
    """读取 Rust MV 虚拟名字框规则确认范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(build_native_mv_virtual_namebox_candidates_payload(game_data=game_data)),
        "mv_virtual_namebox",
    )


def collect_native_placeholder_scope_hash(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> str:
    """读取 Rust 普通占位符规则确认范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(build_native_placeholder_candidates_payload(translation_data_map, text_rules)),
        "placeholders",
    )


def collect_native_structured_placeholder_scope_hash(
    *,
    translation_data_map: dict[str, TranslationData],
    text_rules: TextRules,
) -> str:
    """读取 Rust 结构化占位符规则确认范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(
            build_native_structured_placeholder_candidates_payload(translation_data_map, text_rules)
        ),
        "structured_placeholders",
    )


def collect_native_nonstandard_data_scope_hash(
    *,
    nonstandard_data_files: dict[str, JsonValue],
    text_rules: TextRules,
) -> str:
    """读取 Rust 非标准 data 候选范围哈希。"""
    return native_scan_summary_scope_hash(
        scan_native_rule_candidates(
            build_native_nonstandard_data_candidates_payload(
                nonstandard_data_files=nonstandard_data_files,
                text_rules=text_rules,
            )
        ),
        "nonstandard_data",
    )


def evaluate_native_scope_gate(payload: JsonObject) -> NativeScopeGateResult:
    """调用 Rust 评估范围门禁。"""
    native_module = _load_native_scope_index_module()
    result_text = native_module.evaluate_scope_gate(json.dumps(payload, ensure_ascii=False))
    result = _load_result_object(result_text, "native_scope_gate_result")
    return NativeScopeGateResult(
        contract_versions=_read_contract_versions(result, "native_scope_gate_result"),
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


def native_schema_fingerprint() -> str:
    """读取 Rust 编译期包含的共享 SQLite schema SQL 指纹。"""
    native_module = _load_native_scope_index_module()
    rust_fingerprint = native_module.native_schema_fingerprint()
    from app.persistence.sql import current_schema_fingerprint

    python_fingerprint = current_schema_fingerprint()
    if rust_fingerprint != python_fingerprint:
        raise RuntimeError(
            "Rust 原生扩展内置的 SQLite schema 指纹与 Python 当前 schema 不一致，"
            + f"影响命令: rebuild-text-index。Rust={rust_fingerprint}，Python={python_fingerprint}。"
            + "下一步：请执行 uv run maturin develop 重新构建原生扩展，然后运行 rebuild-text-index。"
        )
    return rust_fingerprint


def inspect_native_scope_index_storage(payload: JsonObject) -> JsonObject:
    """调用 Rust 直读 Scope/Index 所需的 DB 与游戏文件状态。"""
    native_module = _load_native_scope_index_module()
    try:
        result_text = native_module.inspect_scope_index_storage(json.dumps(payload, ensure_ascii=False))
    except ValueError as error:
        raise _native_storage_error(str(error)) from error
    result = _load_result_object(result_text, "native_scope_index_storage_inspect")
    _ = _read_contract_versions(result, "native_scope_index_storage_inspect")
    return result


def write_native_scope_index_storage(payload: JsonObject) -> JsonObject:
    """调用 Rust 直接写入 text index 存储表。"""
    native_module = _load_native_scope_index_module()
    try:
        result_text = native_module.write_scope_index_storage(json.dumps(payload, ensure_ascii=False))
    except ValueError as error:
        raise _native_storage_error(str(error)) from error
    result = _load_result_object(result_text, "native_scope_index_storage_write")
    _validate_text_fact_storage_contract(result, "native_scope_index_storage_write")
    _ = _read_contract_versions(result, "native_scope_index_storage_write")
    return result


def rebuild_native_scope_index_storage(payload: JsonObject) -> JsonObject:
    """调用 Rust 直读 DB/游戏目录并重建 text index 存储。"""
    native_module = _load_native_scope_index_module()
    try:
        result_text = native_module.rebuild_scope_index_storage(json.dumps(payload, ensure_ascii=False))
    except ValueError as error:
        raise _native_storage_error(str(error)) from error
    result = _load_result_object(result_text, "native_scope_index_storage_rebuild")
    _validate_text_fact_storage_contract(result, "native_scope_index_storage_rebuild")
    _ = _read_contract_versions(result, "native_scope_index_storage_rebuild")
    return result


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
    plugin_source_text_rules: list[PluginSourceTextRuleRecord] | None = None,
    plugin_source_read_error_file_count: int = 0,
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
        "plugin_source_text_rules": [
            {
                "file_name": record.file_name,
                "selectors": [selector for selector in record.selectors],
                "excluded_selectors": [selector for selector in record.excluded_selectors],
            }
            for record in sorted(plugin_source_text_rules or [], key=lambda item: item.file_name)
        ],
        "plugin_source_read_error_file_count": plugin_source_read_error_file_count,
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
        "placeholder_scope_hash_requested": True,
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
        "structured_placeholder_scope_hash_requested": True,
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


def build_native_note_tag_validation_payload(
    *,
    game_data: GameData,
    text_rules: TextRules,
    rules: JsonArray,
) -> JsonObject:
    """构造 Rust Note 标签规则验证载荷。"""
    payload = build_native_note_tag_candidates_payload(game_data, text_rules)
    payload["note_tag_rule_validation"] = {"rules": list(rules)}
    return payload


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
    for entry_name in (
        "build_scope_index",
        "scan_rule_candidates",
        "evaluate_scope_gate",
        "native_schema_fingerprint",
        "inspect_scope_index_storage",
        "write_scope_index_storage",
        "rebuild_scope_index_storage",
    ):
        if not hasattr(native_module, entry_name):
            raise RuntimeError(f"Rust 原生扩展缺少 Scope/Index Engine 入口 {entry_name}，请重新执行 uv run maturin develop")
    return cast(NativeScopeIndexModule, cast(object, native_module))


def _load_result_object(result_text: str, label: str) -> JsonObject:
    """把 Rust JSON 文本解析为对象。"""
    return ensure_json_object(
        coerce_json_value(cast(object, json.loads(result_text))),
        label,
    )


def _native_storage_error(raw_text: str) -> NativeScopeIndexStorageError:
    """把 Rust storage 结构化错误转成带 code 的 Python 异常。"""
    try:
        payload = ensure_json_object(
            coerce_json_value(cast(object, json.loads(raw_text))),
            "native_scope_index_storage_error",
        )
        error = ensure_json_object(payload["error"], "native_scope_index_storage_error.error")
        code = error.get("code")
        message = error.get("message")
    except (KeyError, TypeError, json.JSONDecodeError):
        return NativeScopeIndexStorageError(code="native_scope_index_storage_error", message=raw_text)
    if isinstance(message, str) and isinstance(code, str):
        public_code = (
            "mv_virtual_namebox_rules_invalid"
            if code == "scope_index_rebuild_rules_unreadable" and "MV 虚拟名字框规则" in message
            else code
        )
        return NativeScopeIndexStorageError(code=public_code, message=f"{message}（{public_code}）")
    if isinstance(message, str):
        return NativeScopeIndexStorageError(code="native_scope_index_storage_error", message=message)
    return NativeScopeIndexStorageError(code="native_scope_index_storage_error", message=raw_text)


def _validate_text_fact_storage_contract(result: JsonObject, label: str) -> None:
    """校验 native storage 输出包含当前文本事实契约字段。"""
    text_fact_schema_version = _text_fact_schema_version()
    schema_version = _read_int(result, "text_fact_schema_version", label)
    if schema_version != text_fact_schema_version:
        raise RuntimeError(
            "文本事实 schema_version 不满足当前要求: "
            + f"Rust 返回 {schema_version}，Python 支持 {text_fact_schema_version}。"
            + "影响命令: rebuild-text-index。"
            + "下一步：请重新构建 Rust 原生扩展或更新发行包，然后再运行 rebuild-text-index。"
        )
    text_fact_count = _read_int(result, "text_fact_count", label)
    render_part_count = _read_int(result, "render_part_count", label)
    if text_fact_count < 0:
        raise ValueError(f"{label}.text_fact_count 必须是非负整数")
    if render_part_count < 0:
        raise ValueError(f"{label}.render_part_count 必须是非负整数")
    scope_key = result["scope_key"]
    if not isinstance(scope_key, str) or not scope_key:
        raise TypeError(f"{label}.scope_key 必须是非空字符串")
    scope_hash = result["scope_hash"]
    if not isinstance(scope_hash, str) or len(scope_hash) != 64 or not set(scope_hash) <= _HEX_DIGITS:
        raise TypeError(f"{label}.scope_hash 必须是 64 位 SHA-256 十六进制字符串")


def _text_fact_schema_version() -> int:
    """延迟读取 Python 持久层文本事实 schema，避免 native adapter 顶层循环导入。"""
    from app.persistence.sql import CURRENT_TEXT_FACT_CONTRACT_VERSION

    return CURRENT_TEXT_FACT_CONTRACT_VERSION


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


def _read_contract_versions(result: JsonObject, label: str) -> NativeContractVersions:
    """读取 Rust scope/index 契约版本集合。"""
    raw_versions = ensure_json_object(result["contract_versions"], f"{label}.contract_versions")
    return NativeContractVersions(
        rust_scope_facts=_read_int(raw_versions, "rust_scope_facts", f"{label}.contract_versions"),
        parser=_read_int(raw_versions, "parser", f"{label}.contract_versions"),
        source_branch=_read_int(raw_versions, "source_branch", f"{label}.contract_versions"),
        text_fact_schema=_read_int(raw_versions, "text_fact_schema", f"{label}.contract_versions"),
    )


def _read_int_map(result: JsonObject, field_name: str, label: str) -> dict[str, int]:
    """读取字符串到非负整数的 JSON 对象字段。"""
    raw_map = ensure_json_object(result[field_name], f"{label}.{field_name}")
    values: dict[str, int] = {}
    for key, value in raw_map.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise TypeError(f"{label}.{field_name}.{key} 必须是非负整数")
        values[key] = value
    return values


__all__ = [
    "NativeContractVersions",
    "NativeRuleCandidatesResult",
    "NativeScopeGateResult",
    "NativeScopeIndexResult",
    "NativeScopeIndexStorageError",
    "PARSER_CONTRACT_VERSION",
    "RUST_SCOPE_FACTS_CONTRACT_VERSION",
    "SOURCE_BRANCH_CONTRACT_VERSION",
    "build_native_event_command_data_files",
    "build_native_event_command_candidates_payload",
    "build_native_mv_virtual_namebox_candidates_payload",
    "build_native_nonstandard_data_candidates_payload",
    "build_native_nonstandard_data_leaves_payload",
    "build_native_note_tag_candidates_payload",
    "build_native_note_tag_validation_payload",
    "build_native_placeholder_candidates_payload",
    "build_native_plugin_config_candidates_payload",
    "build_native_plugin_source_candidates_payload",
    "build_native_rule_candidate_text_rules_payload",
    "build_native_scope_index",
    "build_native_structured_placeholder_candidates_payload",
    "collect_native_event_command_scope_hash",
    "collect_native_mv_virtual_namebox_scope_hash",
    "collect_native_nonstandard_data_scope_hash",
    "collect_native_note_tag_scope_hash",
    "collect_native_placeholder_scope_hash",
    "collect_native_plugin_config_scope_hash",
    "collect_native_structured_placeholder_scope_hash",
    "evaluate_native_scope_gate",
    "inspect_native_scope_index_storage",
    "mv_virtual_namebox_rule_records_to_native_rules",
    "native_schema_fingerprint",
    "native_scan_summary_scope_hash",
    "rebuild_native_scope_index_storage",
    "scan_native_rule_candidates",
    "write_native_scope_index_storage",
]
