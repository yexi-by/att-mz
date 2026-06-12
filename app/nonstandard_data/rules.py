"""非标准 data 文本规则解析与覆盖校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePath
from typing import cast

from pydantic import Field, TypeAdapter, field_validator, model_validator

from app.config.schemas import TextRulesSetting
from app.external_input import ExternalInputModel, ExternalStr
from app.json_path_protocol import ResolvedLeaf, jsonpath_to_path_parts
from app.native_rule_runtime import prepare_rule_import, runtime_config_patterns_from_setting
from app.native_scope_index import scan_native_rule_candidates
from app.rmmz.json_types import JsonArray, JsonObject, coerce_json_value, ensure_json_array, ensure_json_object
from app.rmmz.schema import NonstandardDataTextRuleRecord

from .scanner import NonstandardDataFile, NonstandardDataScan, build_nonstandard_data_file_hash


class StaleNonstandardDataRulesError(ValueError):
    """已保存的非标准 data 规则不再匹配当前翻译源文件。"""


_FILE_STALE_REASON_CODES = frozenset({"file_missing", "file_hash_mismatch"})


class NonstandardDataRuleSpec(ExternalInputModel):
    """单个非标准 data JSON 文件的文本规则。"""

    file: ExternalStr
    paths: list[ExternalStr] = Field(default_factory=list)
    excluded_paths: list[ExternalStr] = Field(default_factory=list)
    skipped: bool = False

    @field_validator("file")
    @classmethod
    def _validate_file(cls, value: str) -> str:
        """规则只能指向 data 第一层 JSON 文件名。"""
        file_name = value.strip()
        if not file_name:
            raise ValueError("file 不能为空")
        if "/" in file_name or "\\" in file_name:
            raise ValueError("file 只能是 data 第一层文件名，不能包含目录分隔符")
        if PurePath(file_name).name != file_name:
            raise ValueError("file 只能是 data 第一层文件名")
        if not file_name.lower().endswith(".json"):
            raise ValueError("file 必须是 JSON 文件名")
        return file_name

    @field_validator("paths", "excluded_paths")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        """清理并校验路径模板。"""
        normalized_paths = _normalize_path_templates(value)
        for path_template in normalized_paths:
            _ = jsonpath_to_path_parts(path_template)
        return normalized_paths

    @model_validator(mode="after")
    def _validate_skipped_paths(self) -> "NonstandardDataRuleSpec":
        """确认 skipped 规则不同时携带路径。"""
        if self.skipped and (self.paths or self.excluded_paths):
            raise ValueError("skipped=true 时 paths 和 excluded_paths 必须为空")
        return self


type NonstandardDataRuleImportFile = list[NonstandardDataRuleSpec]
_RULE_IMPORT_ADAPTER: TypeAdapter[NonstandardDataRuleImportFile] = TypeAdapter(NonstandardDataRuleImportFile)


@dataclass(frozen=True, slots=True)
class NonstandardDataRuleValidationResult:
    """规则覆盖校验结果。"""

    rules: tuple[NonstandardDataRuleSpec, ...]
    translated_candidate_paths: frozenset[tuple[str, str]]
    excluded_candidate_paths: frozenset[tuple[str, str]]
    skipped_files: frozenset[str]
    unreviewed_candidate_paths: tuple[tuple[str, str], ...]
    hit_details: JsonArray
    translation_prefixes: tuple[str, ...]
    stale_reasons: JsonArray
    details: JsonObject

    @property
    def rule_count(self) -> int:
        """需要翻译的路径模板数量。"""
        return sum(len(rule.paths) for rule in self.rules)

    @property
    def excluded_rule_count(self) -> int:
        """确认排除的路径模板数量。"""
        return sum(len(rule.excluded_paths) for rule in self.rules)

    @property
    def reviewed_candidate_count(self) -> int:
        """已归类候选数量。"""
        return len(self.translated_candidate_paths) + len(self.excluded_candidate_paths)


@dataclass(frozen=True, slots=True)
class _NativeNonstandardDataRuleCoverage:
    """Rust 规则覆盖统计结果。"""

    translated_candidate_paths: frozenset[tuple[str, str]]
    excluded_candidate_paths: frozenset[tuple[str, str]]
    skipped_files: frozenset[str]
    unreviewed_candidate_paths: tuple[tuple[str, str], ...]
    hit_details: JsonArray
    translation_prefixes: tuple[str, ...]
    stale_reasons: JsonArray
    details: JsonObject


def parse_nonstandard_data_rule_import_text(raw_text: str) -> NonstandardDataRuleImportFile:
    """解析非标准 data 规则 JSON 文本。"""
    decoded_raw = cast(object, json.loads(raw_text))
    decoded = coerce_json_value(decoded_raw)
    if not isinstance(decoded, list):
        raise TypeError("非标准 data 文件文本规则顶层必须是数组")
    return _RULE_IMPORT_ADAPTER.validate_python(decoded)


def validate_nonstandard_data_rules(
    *,
    scan: NonstandardDataScan,
    import_file: NonstandardDataRuleImportFile,
    rule_records: list[NonstandardDataTextRuleRecord] | None = None,
) -> NonstandardDataRuleValidationResult:
    """校验规则结构、路径命中和候选全量归类状态。"""
    _ensure_nonstandard_data_rule_runtime_prepare(import_file=import_file)
    coverage = _evaluate_native_nonstandard_data_rule_coverage(
        scan=scan,
        import_file=import_file,
        rule_records=rule_records,
    )
    if coverage.stale_reasons:
        message = _format_stale_reasons(coverage.stale_reasons)
        if _contains_file_stale_reason(coverage.stale_reasons):
            raise StaleNonstandardDataRulesError(message)
        raise ValueError(message)
    if coverage.unreviewed_candidate_paths:
        raise ValueError(
            f"非标准 data 文件文本候选未全量归类: {_format_path_pairs(set(coverage.unreviewed_candidate_paths))}"
        )

    return NonstandardDataRuleValidationResult(
        rules=tuple(import_file),
        translated_candidate_paths=coverage.translated_candidate_paths,
        excluded_candidate_paths=coverage.excluded_candidate_paths,
        skipped_files=coverage.skipped_files,
        unreviewed_candidate_paths=coverage.unreviewed_candidate_paths,
        hit_details=coverage.hit_details,
        translation_prefixes=coverage.translation_prefixes,
        stale_reasons=coverage.stale_reasons,
        details=coverage.details,
    )


def build_nonstandard_data_rule_records_from_validation(
    *,
    scan: NonstandardDataScan,
    validation: NonstandardDataRuleValidationResult,
) -> list[NonstandardDataTextRuleRecord]:
    """使用已验证结果生成可持久化的数据库记录。"""
    files_by_name = {
        nonstandard_file.file_name: nonstandard_file
        for nonstandard_file in scan.files
    }
    return [
        NonstandardDataTextRuleRecord(
            file_name=rule.file,
            file_hash=build_nonstandard_data_file_hash(files_by_name[rule.file].raw_text),
            path_templates=list(rule.paths),
            excluded_path_templates=list(rule.excluded_paths),
            skipped=rule.skipped,
        )
        for rule in validation.rules
    ]


def nonstandard_data_rule_records_to_import_file(
    records: list[NonstandardDataTextRuleRecord],
) -> NonstandardDataRuleImportFile:
    """把数据库记录还原为规则校验使用的导入结构。"""
    return [
        NonstandardDataRuleSpec(
            file=record.file_name,
            paths=list(record.path_templates),
            excluded_paths=list(record.excluded_path_templates),
            skipped=record.skipped,
        )
        for record in records
    ]


def nonstandard_data_rule_records_to_import_json(
    records: list[NonstandardDataTextRuleRecord],
) -> JsonArray:
    """把数据库记录还原为可写入工作区的 JSON 数组。"""
    return [
        spec.model_dump(mode="json")
        for spec in nonstandard_data_rule_records_to_import_file(records)
    ]


def _ensure_nonstandard_data_rule_runtime_prepare(
    *,
    import_file: NonstandardDataRuleImportFile,
) -> None:
    """用统一 rule_runtime 校验非标准 data 规则结构。"""
    rules_payload: JsonArray = [
        ensure_json_object(
            coerce_json_value(cast(object, rule.model_dump(mode="json"))),
            "nonstandard_data_rule",
        )
        for rule in import_file
    ]
    result = prepare_rule_import(
        {
            "mode": "validate",
            "domain": "nonstandard_data",
            "rules_payload": rules_payload,
            "game_context": {},
            "settings_runtime_patterns": runtime_config_patterns_from_setting(TextRulesSetting()),
        }
    )
    if result.errors:
        messages = "；".join(error.message for error in result.errors)
        raise ValueError(messages)


def _evaluate_native_nonstandard_data_rule_coverage(
    *,
    scan: NonstandardDataScan,
    import_file: NonstandardDataRuleImportFile,
    rule_records: list[NonstandardDataTextRuleRecord] | None = None,
) -> _NativeNonstandardDataRuleCoverage:
    """调用 Rust 入口评估非标准 data 规则覆盖统计。"""
    rule_file_hashes = (
        {record.file_name: record.file_hash for record in rule_records}
        if rule_records is not None
        else {}
    )
    candidate_paths = tuple(
        (candidate.file_name, candidate.json_path)
        for candidate in scan.candidates
    )
    return _evaluate_native_nonstandard_data_rule_coverage_from_parts(
        files=scan.files,
        leaves_by_file=scan.leaves_by_file,
        candidate_paths=candidate_paths,
        import_file=import_file,
        rule_file_hashes=rule_file_hashes,
    )


def _evaluate_native_nonstandard_data_rule_coverage_from_parts(
    *,
    files: tuple[NonstandardDataFile, ...],
    leaves_by_file: dict[str, tuple[ResolvedLeaf, ...]],
    candidate_paths: tuple[tuple[str, str], ...],
    import_file: NonstandardDataRuleImportFile,
    rule_file_hashes: dict[str, str],
) -> _NativeNonstandardDataRuleCoverage:
    """按 Rust 已展开事实评估非标准 data 规则覆盖。"""
    native_result = scan_native_rule_candidates(
        {
            "nonstandard_data_rule_coverage": {
                "rules": [
                    _native_rule_payload(rule=rule, rule_file_hashes=rule_file_hashes)
                    for rule in import_file
                ],
                "files": [
                    {
                        "file": nonstandard_file.file_name,
                        "file_hash": build_nonstandard_data_file_hash(nonstandard_file.raw_text),
                        "leaves": [
                            {
                                "path": leaf.path,
                                "value_type": leaf.value_type,
                                "value": leaf.value,
                            }
                            for leaf in leaves_by_file.get(nonstandard_file.file_name, ())
                        ],
                    }
                    for nonstandard_file in files
                ],
                "candidates": [
                    {
                        "file": file_name,
                        "json_path": json_path,
                    }
                    for file_name, json_path in candidate_paths
                ],
            }
        }
    )
    coverage = ensure_json_object(
        native_result.scan_summary["nonstandard_data_rule_coverage"],
        "native_rule_candidates_result.scan_summary.nonstandard_data_rule_coverage",
    )
    translated_candidate_paths = _path_pairs_from_json_array(
        ensure_json_array(coverage["translated_candidates"], "nonstandard_data_rule_coverage.translated_candidates"),
        "nonstandard_data_rule_coverage.translated_candidates",
    )
    excluded_candidate_paths = _path_pairs_from_json_array(
        ensure_json_array(coverage["excluded_candidates"], "nonstandard_data_rule_coverage.excluded_candidates"),
        "nonstandard_data_rule_coverage.excluded_candidates",
    )
    unreviewed_candidate_paths = tuple(
        sorted(
            _path_pairs_from_json_array(
                ensure_json_array(coverage["unreviewed_candidates"], "nonstandard_data_rule_coverage.unreviewed_candidates"),
                "nonstandard_data_rule_coverage.unreviewed_candidates",
            )
        )
    )
    skipped_files = frozenset(
        _string_array_from_json_array(
            ensure_json_array(coverage["skipped_files"], "nonstandard_data_rule_coverage.skipped_files"),
            "nonstandard_data_rule_coverage.skipped_files",
        )
    )
    hit_details = ensure_json_array(coverage["hit_details"], "nonstandard_data_rule_coverage.hit_details")
    translation_prefixes = tuple(
        _string_array_from_json_array(
            ensure_json_array(coverage["translation_prefixes"], "nonstandard_data_rule_coverage.translation_prefixes"),
            "nonstandard_data_rule_coverage.translation_prefixes",
        )
    )
    stale_reasons = ensure_json_array(coverage["stale_reasons"], "nonstandard_data_rule_coverage.stale_reasons")
    details: JsonObject = {
        "rules": ensure_json_array(coverage["rules"], "nonstandard_data_rule_coverage.rules"),
        "rule_summaries": ensure_json_array(
            coverage["rule_summaries"],
            "nonstandard_data_rule_coverage.rule_summaries",
        ),
        "hit_details": hit_details,
        "translation_prefixes": list(translation_prefixes),
        "stale_reasons": stale_reasons,
        "translated_candidates": ensure_json_array(
            coverage["translated_candidates"],
            "nonstandard_data_rule_coverage.translated_candidates",
        ),
        "excluded_candidates": ensure_json_array(
            coverage["excluded_candidates"],
            "nonstandard_data_rule_coverage.excluded_candidates",
        ),
        "skipped_files": ensure_json_array(coverage["skipped_files"], "nonstandard_data_rule_coverage.skipped_files"),
    }
    return _NativeNonstandardDataRuleCoverage(
        translated_candidate_paths=frozenset(translated_candidate_paths),
        excluded_candidate_paths=frozenset(excluded_candidate_paths),
        skipped_files=skipped_files,
        unreviewed_candidate_paths=unreviewed_candidate_paths,
        hit_details=hit_details,
        translation_prefixes=translation_prefixes,
        stale_reasons=stale_reasons,
        details=details,
    )


def _native_rule_payload(
    *,
    rule: NonstandardDataRuleSpec,
    rule_file_hashes: dict[str, str],
) -> JsonObject:
    """构造仅供 Rust coverage 使用的规则载荷。"""
    payload = ensure_json_object(
        coerce_json_value(cast(object, rule.model_dump(mode="json"))),
        "nonstandard_data_rule",
    )
    file_hash = rule_file_hashes.get(rule.file)
    if file_hash is not None:
        payload["file_hash"] = file_hash
    return payload


def _path_pairs_from_json_array(items: JsonArray, label: str) -> set[tuple[str, str]]:
    """读取 native 输出的文件和 JSONPath 对。"""
    path_pairs: set[tuple[str, str]] = set()
    for index, raw_item in enumerate(items):
        item_label = f"{label}[{index}]"
        item = ensure_json_object(raw_item, item_label)
        file_name = item.get("file")
        json_path = item.get("json_path")
        if not isinstance(file_name, str):
            raise TypeError(f"{item_label}.file 必须是字符串")
        if not isinstance(json_path, str):
            raise TypeError(f"{item_label}.json_path 必须是字符串")
        path_pairs.add((file_name, json_path))
    return path_pairs


def _string_array_from_json_array(items: JsonArray, label: str) -> list[str]:
    """读取 native 输出的字符串数组。"""
    values: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise TypeError(f"{label}[{index}] 必须是字符串")
        values.append(item)
    return values


def _contains_file_stale_reason(items: JsonArray) -> bool:
    """判断 native stale reasons 是否包含文件级过期。"""
    for index, raw_item in enumerate(items):
        item = ensure_json_object(raw_item, f"nonstandard_data_rule_coverage.stale_reasons[{index}]")
        code = item.get("code")
        if isinstance(code, str) and code in _FILE_STALE_REASON_CODES:
            return True
    return False


def _format_stale_reasons(items: JsonArray) -> str:
    """把 Rust stale reasons 渲染为当前规则问题摘要。"""
    messages: list[str] = []
    for index, raw_item in enumerate(items):
        item = ensure_json_object(raw_item, f"nonstandard_data_rule_coverage.stale_reasons[{index}]")
        message = item.get("message")
        if not isinstance(message, str) or not message.strip():
            code = item.get("code")
            code_text = code if isinstance(code, str) and code else "unknown"
            message = f"非标准 data 文件文本规则无效: {code_text}"
        messages.append(message)
    if not messages:
        return "非标准 data 文件文本规则无效"
    suffix = f" 等 {len(messages)} 项" if len(messages) > 5 else ""
    return "；".join(messages[:5]) + suffix


def _normalize_path_templates(path_templates: list[str]) -> list[str]:
    """清理并去重路径模板。"""
    normalized_paths: list[str] = []
    seen_paths: set[str] = set()
    for path_template in path_templates:
        normalized_path = path_template.strip()
        if not normalized_path or normalized_path in seen_paths:
            continue
        normalized_paths.append(normalized_path)
        seen_paths.add(normalized_path)
    return normalized_paths


def _format_path_pairs(path_pairs: set[tuple[str, str]]) -> str:
    """把文件和 JSONPath 列表转成用户可读片段。"""
    return "、".join(
        f"{file_name}:{json_path}"
        for file_name, json_path in sorted(path_pairs)[:20]
    )


__all__ = [
    "StaleNonstandardDataRulesError",
    "NonstandardDataRuleImportFile",
    "NonstandardDataRuleSpec",
    "NonstandardDataRuleValidationResult",
    "build_nonstandard_data_rule_records_from_validation",
    "nonstandard_data_rule_records_to_import_json",
    "nonstandard_data_rule_records_to_import_file",
    "parse_nonstandard_data_rule_import_text",
    "validate_nonstandard_data_rules",
]
