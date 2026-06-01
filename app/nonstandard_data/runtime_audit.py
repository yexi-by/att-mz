"""非标准 data 文件当前运行视图审计。"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import cast

from app.plugin_text.paths import expand_rule_to_leaf_paths
from app.rmmz.loader import resolve_data_source_dir
from app.rmmz.schema import GameLayout, NonstandardDataTextRuleRecord
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue, TextRules, coerce_json_value

from .scanner import resolve_nonstandard_data_leaves


@dataclass(frozen=True, slots=True)
class ActiveRuntimeNonstandardDataIssue:
    """当前运行非标准 data 文件中的一个审计问题。"""

    code: str
    message: str
    file_name: str
    json_path: str = ""
    fragment: str = ""
    read_error: str = ""

    def to_json_object(self) -> JsonObject:
        """转换成报告 JSON 对象。"""
        payload: JsonObject = {
            "file": self.file_name,
            "json_path": self.json_path,
            "active": True,
            "code": self.code,
            "message": self.message,
            "fragment": self.fragment,
        }
        if self.read_error:
            payload["read_error"] = self.read_error
        return payload


@dataclass(frozen=True, slots=True)
class ActiveRuntimeNonstandardDataAudit:
    """当前运行非标准 data 文件审计结果。"""

    issues: tuple[ActiveRuntimeNonstandardDataIssue, ...]
    audit_enabled: bool
    file_count: int
    skipped_file_count: int
    managed_path_count: int

    @property
    def issue_counts(self) -> Counter[str]:
        """按问题编码统计数量。"""
        return Counter(issue.code for issue in self.issues)

    def summary_json(self) -> JsonObject:
        """转换成审计摘要字段。"""
        counts = self.issue_counts
        return {
            "active_runtime_nonstandard_data_audit_enabled": self.audit_enabled,
            "active_runtime_nonstandard_data_file_count": self.file_count,
            "active_runtime_nonstandard_data_skipped_file_count": self.skipped_file_count,
            "active_runtime_nonstandard_data_managed_path_count": self.managed_path_count,
            "active_runtime_nonstandard_data_issue_count": len(self.issues),
            "active_runtime_nonstandard_data_read_error_count": counts.get(
                "active_runtime_nonstandard_data_read_error",
                0,
            ),
            "active_runtime_nonstandard_data_path_error_count": counts.get(
                "active_runtime_nonstandard_data_path_error",
                0,
            ),
            "active_runtime_nonstandard_data_source_residual_count": counts.get(
                "active_runtime_nonstandard_data_source_residual",
                0,
            ),
            "active_runtime_nonstandard_data_placeholder_risk_count": counts.get(
                "active_runtime_nonstandard_data_placeholder_risk",
                0,
            ),
        }

    def issues_json(self, *, limit: int = 100) -> JsonArray:
        """返回前 N 条审计问题。"""
        return [issue.to_json_object() for issue in self.issues[:limit]]


def audit_active_runtime_nonstandard_data(
    *,
    layout: GameLayout,
    rule_records: list[NonstandardDataTextRuleRecord],
    text_rules: TextRules,
) -> ActiveRuntimeNonstandardDataAudit:
    """审计当前运行 data 文件中已被规则管理的非标准 JSON 文本。"""
    if not rule_records:
        return ActiveRuntimeNonstandardDataAudit(
            issues=(),
            audit_enabled=False,
            file_count=0,
            skipped_file_count=0,
            managed_path_count=0,
        )

    data_dir = resolve_data_source_dir(
        layout=layout,
        use_origin_backups=False,
        require_origin_backups=False,
    )
    file_names = {record.file_name for record in rule_records}
    skipped_file_names = {record.file_name for record in rule_records if record.skipped}
    issues: list[ActiveRuntimeNonstandardDataIssue] = []
    managed_path_count = 0
    active_files: dict[str, JsonValue] = {}

    for file_name in sorted(file_names - skipped_file_names):
        try:
            active_files[file_name] = _read_active_nonstandard_data_file(
                data_dir=data_dir,
                file_name=file_name,
            )
        except Exception as error:
            issues.append(
                ActiveRuntimeNonstandardDataIssue(
                    code="active_runtime_nonstandard_data_read_error",
                    message="当前游戏运行文件里的非标准 data JSON 读取失败，不能确认已管理文本是否正确写入",
                    file_name=file_name,
                    read_error=f"{type(error).__name__}: {error}",
                )
            )

    for record in sorted(rule_records, key=lambda item: item.file_name):
        if record.skipped:
            continue
        active_value = active_files.get(record.file_name)
        if active_value is None:
            continue
        file_issues, file_managed_path_count = _audit_record_paths(
            record=record,
            active_value=active_value,
            text_rules=text_rules,
        )
        issues.extend(file_issues)
        managed_path_count += file_managed_path_count

    return ActiveRuntimeNonstandardDataAudit(
        issues=tuple(_deduplicate_issues(issues)),
        audit_enabled=True,
        file_count=len(file_names),
        skipped_file_count=len(skipped_file_names),
        managed_path_count=managed_path_count,
    )


def _read_active_nonstandard_data_file(*, data_dir: Path, file_name: str) -> JsonValue:
    """从当前运行 data 目录读取一个受管理的非标准 JSON 文件。"""
    if PurePath(file_name).name != file_name or "/" in file_name or "\\" in file_name:
        raise ValueError(f"非法非标准 data 文件名: {file_name}")
    file_path = data_dir / file_name
    if not file_path.is_file():
        raise FileNotFoundError(f"当前运行 data 文件不存在: {file_name}")
    raw_text = file_path.read_bytes().decode("utf-8")
    decoded_raw = cast(object, json.loads(raw_text))
    return coerce_json_value(decoded_raw)


def _audit_record_paths(
    *,
    record: NonstandardDataTextRuleRecord,
    active_value: JsonValue,
    text_rules: TextRules,
) -> tuple[list[ActiveRuntimeNonstandardDataIssue], int]:
    """审计一条规则记录在当前运行 JSON 中命中的字符串叶子。"""
    resolved_leaves = resolve_nonstandard_data_leaves(active_value)
    string_leaf_map = {
        leaf.path: leaf.value
        for leaf in resolved_leaves
        if leaf.value_type == "string" and isinstance(leaf.value, str)
    }
    issues: list[ActiveRuntimeNonstandardDataIssue] = []
    managed_path_count = 0
    seen_paths: set[str] = set()
    for path_template in record.path_templates:
        try:
            matched_paths = expand_rule_to_leaf_paths(
                path_template=path_template,
                resolved_leaves=resolved_leaves,
            )
        except ValueError as error:
            issues.append(
                ActiveRuntimeNonstandardDataIssue(
                    code="active_runtime_nonstandard_data_path_error",
                    message="当前游戏运行文件里的非标准 data JSON 规则路径不可解析",
                    file_name=record.file_name,
                    json_path=path_template,
                    read_error=f"{type(error).__name__}: {error}",
                )
            )
            continue
        string_paths = [path for path in matched_paths if path in string_leaf_map]
        if not string_paths:
            issues.append(
                ActiveRuntimeNonstandardDataIssue(
                    code="active_runtime_nonstandard_data_path_error",
                    message="当前游戏运行文件里的非标准 data JSON 规则路径没有命中字符串叶子",
                    file_name=record.file_name,
                    json_path=path_template,
                )
            )
            continue
        for json_path in string_paths:
            if json_path in seen_paths:
                continue
            seen_paths.add(json_path)
            managed_path_count += 1
            issues.extend(
                _audit_managed_text(
                    file_name=record.file_name,
                    json_path=json_path,
                    text=string_leaf_map[json_path],
                    text_rules=text_rules,
                )
            )
    return issues, managed_path_count


def _audit_managed_text(
    *,
    file_name: str,
    json_path: str,
    text: str,
    text_rules: TextRules,
) -> list[ActiveRuntimeNonstandardDataIssue]:
    """审计一个已管理 JSON 字符串叶子的文本质量。"""
    issues: list[ActiveRuntimeNonstandardDataIssue] = []
    for candidate in text_rules.iter_unprotected_control_sequence_candidates(text):
        issues.append(
            ActiveRuntimeNonstandardDataIssue(
                code="active_runtime_nonstandard_data_placeholder_risk",
                message="当前游戏运行文件里的非标准 data 文本存在未受保护的游戏控制符片段",
                file_name=file_name,
                json_path=json_path,
                fragment=candidate.original,
            )
        )
    try:
        text_rules.check_source_residual([text])
    except ValueError as error:
        issues.append(
            ActiveRuntimeNonstandardDataIssue(
                code="active_runtime_nonstandard_data_source_residual",
                message=f"当前游戏运行文件里的非标准 data 文本仍有源文残留: {error}",
                file_name=file_name,
                json_path=json_path,
            )
        )
    return issues


def _deduplicate_issues(
    issues: list[ActiveRuntimeNonstandardDataIssue],
) -> list[ActiveRuntimeNonstandardDataIssue]:
    """按稳定键去重审计问题。"""
    result: list[ActiveRuntimeNonstandardDataIssue] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for issue in issues:
        key = (
            issue.code,
            issue.file_name,
            issue.json_path,
            issue.fragment,
            issue.read_error,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


__all__ = [
    "ActiveRuntimeNonstandardDataAudit",
    "ActiveRuntimeNonstandardDataIssue",
    "audit_active_runtime_nonstandard_data",
]
