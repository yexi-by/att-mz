"""非标准 data 文本规则解析与覆盖校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePath
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.plugin_text.paths import (
    ResolvedLeaf,
    expand_rule_to_leaf_paths,
    jsonpath_to_path_parts,
)
from app.rmmz.json_types import JsonArray, JsonObject, coerce_json_value
from app.rmmz.schema import NonstandardDataTextRuleRecord

from .scanner import NonstandardDataScan, build_nonstandard_data_file_hash


class StrictNonstandardDataRuleModel(BaseModel):
    """非标准 data 规则文件严格模型基类。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)


class NonstandardDataRuleSpec(StrictNonstandardDataRuleModel):
    """单个非标准 data JSON 文件的文本规则。"""

    file: str
    paths: list[str] = Field(default_factory=list)
    excluded_paths: list[str] = Field(default_factory=list)
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
) -> NonstandardDataRuleValidationResult:
    """校验规则结构、路径命中和候选全量归类状态。"""
    nonstandard_file_names = {file.file_name for file in scan.files}
    candidate_paths = {
        (candidate.file_name, candidate.json_path)
        for candidate in scan.candidates
    }
    seen_files: set[str] = set()
    translated_candidate_paths: set[tuple[str, str]] = set()
    excluded_candidate_paths: set[tuple[str, str]] = set()
    skipped_files: set[str] = set()
    rule_details: JsonArray = []

    for rule in import_file:
        if rule.file in seen_files:
            raise ValueError(f"非标准 data 文件规则不能重复声明 file: {rule.file}")
        seen_files.add(rule.file)
        if rule.file not in nonstandard_file_names:
            raise ValueError(f"非标准 data 文件规则指向不存在的文件: {rule.file}")
        if rule.skipped:
            skipped_files.add(rule.file)
            rule_details.append(
                {
                    "file": rule.file,
                    "skipped": True,
                    "translated_candidate_count": 0,
                    "excluded_candidate_count": 0,
                }
            )
            continue

        file_leaves = list(scan.leaves_by_file.get(rule.file, ()))
        translated_hits = _collect_rule_hits(
            file_name=rule.file,
            path_templates=rule.paths,
            leaves=file_leaves,
            candidate_paths=candidate_paths,
            require_candidate_hit=True,
        )
        excluded_hits = _collect_rule_hits(
            file_name=rule.file,
            path_templates=rule.excluded_paths,
            leaves=file_leaves,
            candidate_paths=candidate_paths,
            require_candidate_hit=True,
        )
        overlap = translated_hits & excluded_hits
        if overlap:
            overlap_preview = _format_path_pairs(overlap)
            raise ValueError(f"非标准 data 文件规则 paths 与 excluded_paths 命中同一候选: {overlap_preview}")
        translated_candidate_paths.update(translated_hits)
        excluded_candidate_paths.update(excluded_hits)
        rule_details.append(
            {
                "file": rule.file,
                "skipped": False,
                "translated_candidate_count": len(translated_hits),
                "excluded_candidate_count": len(excluded_hits),
                "paths": list(rule.paths),
                "excluded_paths": list(rule.excluded_paths),
            }
        )

    reviewed_paths = translated_candidate_paths | excluded_candidate_paths
    skipped_candidate_paths = {
        path_pair
        for path_pair in candidate_paths
        if path_pair[0] in skipped_files
    }
    unreviewed_candidate_paths = tuple(sorted(candidate_paths - reviewed_paths - skipped_candidate_paths))
    if unreviewed_candidate_paths:
        raise ValueError(
            f"非标准 data 文件文本候选未全量归类: {_format_path_pairs(set(unreviewed_candidate_paths))}"
        )

    skipped_file_items: JsonArray = [
        file_name
        for file_name in sorted(skipped_files)
    ]
    return NonstandardDataRuleValidationResult(
        rules=tuple(import_file),
        translated_candidate_paths=frozenset(translated_candidate_paths),
        excluded_candidate_paths=frozenset(excluded_candidate_paths),
        skipped_files=frozenset(skipped_files),
        unreviewed_candidate_paths=unreviewed_candidate_paths,
        details={
            "rules": rule_details,
            "translated_candidates": _path_pairs_to_json_array(translated_candidate_paths),
            "excluded_candidates": _path_pairs_to_json_array(excluded_candidate_paths),
            "skipped_files": skipped_file_items,
        },
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


def _collect_rule_hits(
    *,
    file_name: str,
    path_templates: list[str],
    leaves: list[ResolvedLeaf],
    candidate_paths: set[tuple[str, str]],
    require_candidate_hit: bool,
) -> set[tuple[str, str]]:
    """展开一组路径模板并返回命中的候选路径。"""
    hits: set[tuple[str, str]] = set()
    for path_template in path_templates:
        matched_leaf_paths = expand_rule_to_leaf_paths(
            path_template=path_template,
            resolved_leaves=leaves,
        )
        if not matched_leaf_paths:
            raise ValueError(f"非标准 data 文件 {file_name} 的路径没有命中字符串叶子: {path_template}")
        candidate_hits = {
            (file_name, leaf_path)
            for leaf_path in matched_leaf_paths
            if (file_name, leaf_path) in candidate_paths
        }
        if require_candidate_hit and not candidate_hits:
            raise ValueError(f"非标准 data 文件 {file_name} 的路径没有命中源语言自然文本候选: {path_template}")
        hits.update(candidate_hits)
    return hits


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


def _path_pairs_to_json_array(path_pairs: set[tuple[str, str]]) -> JsonArray:
    """把文件和 JSONPath 集合转为 JSON 数组。"""
    return [
        {"file": file_name, "json_path": json_path}
        for file_name, json_path in sorted(path_pairs)
    ]


__all__ = [
    "NonstandardDataRuleImportFile",
    "NonstandardDataRuleSpec",
    "NonstandardDataRuleValidationResult",
    "build_nonstandard_data_rule_records_from_validation",
    "nonstandard_data_rule_records_to_import_json",
    "nonstandard_data_rule_records_to_import_file",
    "parse_nonstandard_data_rule_import_text",
    "validate_nonstandard_data_rules",
]
