"""当前运行插件源码审计。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.plugin_text import extract_plugin_name
from app.rmmz.schema import GameData, PluginSourceRuntimeProvenanceRecord
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules

from .scanner import (
    PluginSourceStringLiteral,
    iter_plugin_source_string_literals,
    scan_plugin_source_file_text_strict,
)

RAW_LITERAL_LINE_BREAK_CONTROL_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\\)\\n(?P<fragment>[A-Za-z]+\d*\[[^\]\r\n]{0,64}\])"
)
VISIBLE_LINE_START_CONTROL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:(?<=\n)|(?<=\r))(?P<fragment>[A-Za-z]+\d*\[[^\]\r\n]{0,64}\])"
)


@dataclass(frozen=True, slots=True)
class ActiveRuntimePluginSourceIssue:
    """当前运行插件源码中的一个审计问题。"""

    code: str
    message: str
    file_name: str
    blocking: bool = True
    fragment: str = ""
    literal: PluginSourceStringLiteral | None = None
    review_kind: str = ""
    mapping_reason: str = ""
    read_error: str = ""
    syntax_error: str = ""

    def to_json_object(self) -> JsonObject:
        """转换成报告 JSON 对象。"""
        if self.literal is None:
            payload: JsonObject = {
                "file": self.file_name,
                "active": True,
            }
        else:
            payload = self.literal.to_json_object()
        payload["code"] = self.code
        payload["message"] = self.message
        payload["blocking"] = self.blocking
        payload["fragment"] = self.fragment
        if self.review_kind:
            payload["review_kind"] = self.review_kind
        if self.mapping_reason:
            payload["mapping_reason"] = self.mapping_reason
        if self.read_error:
            payload["read_error"] = self.read_error
        if self.syntax_error:
            payload["syntax_error"] = self.syntax_error
        return payload


@dataclass(frozen=True, slots=True)
class ActiveRuntimePluginSourceAudit:
    """当前运行插件源码审计结果。"""

    issues: tuple[ActiveRuntimePluginSourceIssue, ...]
    scanned_file_count: int
    active_file_count: int
    literal_count: int
    active_literal_count: int
    read_error_file_count: int

    @property
    def issue_counts(self) -> Counter[str]:
        """按问题编码统计数量。"""
        return Counter(issue.code for issue in self.issues)

    @property
    def blocking_issues(self) -> tuple[ActiveRuntimePluginSourceIssue, ...]:
        """返回会阻塞写回验收的问题。"""
        return tuple(issue for issue in self.issues if issue.blocking)

    @property
    def blocking_issue_counts(self) -> Counter[str]:
        """按问题编码统计阻塞问题数量。"""
        return Counter(issue.code for issue in self.blocking_issues)

    def summary_json(self) -> JsonObject:
        """转换成质量报告摘要字段。"""
        counts = self.issue_counts
        blocking_counts = self.blocking_issue_counts
        ignored_issues = [issue for issue in self.issues if not issue.blocking]
        ignored_review_counts = Counter(issue.review_kind for issue in ignored_issues)
        return {
            "active_runtime_scanned_file_count": self.scanned_file_count,
            "active_runtime_active_file_count": self.active_file_count,
            "active_runtime_literal_count": self.literal_count,
            "active_runtime_active_literal_count": self.active_literal_count,
            "active_runtime_read_error_file_count": self.read_error_file_count,
            "active_runtime_issue_count": len(self.blocking_issues),
            "active_runtime_observed_issue_count": len(self.issues),
            "active_runtime_ignored_issue_count": len(ignored_issues),
            "active_runtime_ignored_excluded_count": ignored_review_counts.get("excluded", 0),
            "active_runtime_ignored_non_source_count": ignored_review_counts.get("non_source", 0),
            "active_runtime_read_error_count": blocking_counts.get("active_runtime_read_error", 0),
            "active_runtime_syntax_error_count": blocking_counts.get("active_runtime_syntax_error", 0),
            "active_runtime_source_residual_count": blocking_counts.get("active_runtime_source_residual", 0),
            "active_runtime_placeholder_risk_count": blocking_counts.get("active_runtime_placeholder_risk", 0),
            "active_runtime_provenance_missing_count": blocking_counts.get("active_runtime_provenance_missing", 0),
            "active_runtime_provenance_stale_count": blocking_counts.get("active_runtime_provenance_stale", 0),
            "active_runtime_observed_source_residual_count": counts.get("active_runtime_source_residual", 0),
            "active_runtime_observed_placeholder_risk_count": counts.get("active_runtime_placeholder_risk", 0),
        }

    def issues_json(self, *, limit: int = 100) -> JsonArray:
        """返回前 N 条阻塞审计问题。"""
        return [issue.to_json_object() for issue in self.blocking_issues[:limit]]


def audit_active_runtime_plugin_source(
    *,
    game_data: GameData,
    text_rules: TextRules,
    plugin_source_files: dict[str, str] | None = None,
    plugin_source_read_errors: dict[str, str] | None = None,
    runtime_provenance_records: list[PluginSourceRuntimeProvenanceRecord] | None = None,
) -> ActiveRuntimePluginSourceAudit:
    """审计当前运行插件源码中的源文残留和坏控制符。"""
    enabled_plugin_files = _enabled_plugin_source_file_names(game_data)
    source_files = plugin_source_files if plugin_source_files is not None else game_data.plugin_source_files
    read_errors = (
        plugin_source_read_errors
        if plugin_source_read_errors is not None
        else game_data.plugin_source_read_errors
    )
    provenance_by_runtime_key = _runtime_provenance_by_key(runtime_provenance_records or [])
    provenance_by_file = _runtime_provenance_by_file(runtime_provenance_records or [])
    issues: list[ActiveRuntimePluginSourceIssue] = []
    literal_count = 0
    active_literal_count = 0
    active_read_error_file_names = {
        file_name
        for file_name in read_errors
        if file_name in enabled_plugin_files
    }
    active_missing_file_names = set(enabled_plugin_files) - set(source_files) - set(read_errors)
    active_file_count = len(active_read_error_file_names) + len(active_missing_file_names)
    for file_name in sorted(active_read_error_file_names):
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_read_error",
                message="当前游戏运行文件里的插件源码读取失败，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
                file_name=file_name,
                read_error=read_errors[file_name],
            )
        )
    for file_name in sorted(active_missing_file_names):
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_read_error",
                message="当前游戏运行文件里的启用插件源码文件不存在，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
                file_name=file_name,
                read_error=f"启用插件源码文件不存在: js/plugins/{file_name}",
            )
        )
    for file_name, source in sorted(source_files.items()):
        active = file_name in enabled_plugin_files
        if active:
            active_file_count += 1
            try:
                file_scan = scan_plugin_source_file_text_strict(
                    file_name=file_name,
                    source=source,
                    active=True,
                )
            except (ImportError, RuntimeError) as error:
                issues.append(
                    _strict_active_runtime_syntax_issue(
                        file_name=file_name,
                        error=error,
                    )
                )
                continue
            literals = file_scan.literals
            runtime_file_hash = file_scan.file_hash
        else:
            literals = iter_plugin_source_string_literals(
                file_name=file_name,
                source=source,
                active=False,
            )
            runtime_file_hash = ""
        literal_count += len(literals)
        if not active:
            continue
        active_literal_count += len(literals)
        provenance_issue = _runtime_provenance_file_issue(
            file_name=file_name,
            runtime_file_hash=runtime_file_hash,
            has_literals=bool(literals),
            provenance_by_file=provenance_by_file,
        )
        if provenance_issue is not None:
            issues.append(provenance_issue)
            continue
        for literal in literals:
            provenance = provenance_by_runtime_key.get((literal.file_name, literal.selector))
            if provenance is None:
                issues.append(
                    ActiveRuntimePluginSourceIssue(
                        code="active_runtime_provenance_missing",
                        message="当前运行插件源码缺少来源映射，无法判断该字符串是否应该翻译；请重新执行 rebuild-active-runtime 生成映射",
                        file_name=literal.file_name,
                        literal=literal,
                        mapping_reason="runtime_provenance_missing",
                    )
                )
                continue
            issues.extend(
                _classify_literal_issues(
                    issues=_audit_literal(literal=literal, text_rules=text_rules),
                    provenance=provenance,
                )
            )
    return ActiveRuntimePluginSourceAudit(
        issues=tuple(issues),
        scanned_file_count=len(set(source_files) | set(read_errors) | active_missing_file_names),
        active_file_count=active_file_count,
        literal_count=literal_count,
        active_literal_count=active_literal_count,
        read_error_file_count=len(set(read_errors) | active_missing_file_names),
    )


def _strict_active_runtime_syntax_issue(
    *,
    file_name: str,
    error: BaseException,
) -> ActiveRuntimePluginSourceIssue:
    """把严格 AST 扫描失败转换成当前运行语法问题。"""
    return ActiveRuntimePluginSourceIssue(
        code="active_runtime_syntax_error",
        message="当前游戏运行文件里的插件源码无法完成 JS 语法检查，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
        file_name=file_name,
        syntax_error=f"{type(error).__name__}: {error}",
    )


def _audit_literal(
    *,
    literal: PluginSourceStringLiteral,
    text_rules: TextRules,
) -> list[ActiveRuntimePluginSourceIssue]:
    """审计单个当前运行字符串字面量。"""
    issues: list[ActiveRuntimePluginSourceIssue] = []
    for fragment in _collect_bad_control_fragments(literal):
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_placeholder_risk",
                message="当前游戏运行文件里的插件源码疑似把游戏控制符反斜杠写坏",
                file_name=literal.file_name,
                fragment=fragment,
                literal=literal,
            )
        )
    for candidate in text_rules.iter_unprotected_control_sequence_candidates(literal.text):
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_placeholder_risk",
                message="当前游戏运行文件里的插件源码存在未受保护的游戏控制符片段",
                file_name=literal.file_name,
                fragment=candidate.original,
                literal=literal,
            )
        )
    try:
        text_rules.check_source_residual([literal.text])
    except ValueError as error:
        issues.append(
            ActiveRuntimePluginSourceIssue(
                code="active_runtime_source_residual",
                message=f"当前游戏运行文件里的插件源码仍有源文残留: {error}",
                file_name=literal.file_name,
                fragment="",
                literal=literal,
            )
        )
    return _deduplicate_issues(issues)


def _runtime_provenance_by_key(
    records: list[PluginSourceRuntimeProvenanceRecord],
) -> dict[tuple[str, str], PluginSourceRuntimeProvenanceRecord]:
    """按当前运行文件和 selector 索引来源映射。"""
    return {
        (record.runtime_file_name, record.runtime_selector): record
        for record in records
    }


def _runtime_provenance_by_file(
    records: list[PluginSourceRuntimeProvenanceRecord],
) -> dict[str, list[PluginSourceRuntimeProvenanceRecord]]:
    """按当前运行文件索引来源映射。"""
    by_file: dict[str, list[PluginSourceRuntimeProvenanceRecord]] = {}
    for record in records:
        by_file.setdefault(record.runtime_file_name, []).append(record)
    return by_file


def _runtime_provenance_file_issue(
    *,
    file_name: str,
    runtime_file_hash: str,
    has_literals: bool,
    provenance_by_file: dict[str, list[PluginSourceRuntimeProvenanceRecord]],
) -> ActiveRuntimePluginSourceIssue | None:
    """检查当前运行插件源码文件是否存在缺失或过期的来源映射。"""
    file_records = provenance_by_file.get(file_name, [])
    if not file_records:
        if not has_literals:
            return None
        return ActiveRuntimePluginSourceIssue(
            code="active_runtime_provenance_missing",
            message="当前运行插件源码没有来源映射，无法判断残留文本是否应翻译；请重新执行 rebuild-active-runtime 生成映射",
            file_name=file_name,
            mapping_reason="runtime_provenance_missing",
        )
    expected_hashes = {record.runtime_file_hash for record in file_records}
    if expected_hashes != {runtime_file_hash}:
        return ActiveRuntimePluginSourceIssue(
            code="active_runtime_provenance_stale",
            message="当前运行插件源码已变化，来源映射失效；请重新执行 rebuild-active-runtime 生成映射",
            file_name=file_name,
            mapping_reason="runtime_file_changed",
        )
    return None


def _classify_literal_issues(
    *,
    issues: list[ActiveRuntimePluginSourceIssue],
    provenance: PluginSourceRuntimeProvenanceRecord,
) -> list[ActiveRuntimePluginSourceIssue]:
    """按来源审查状态决定单个字符串问题是否阻塞验收。"""
    if provenance.review_kind in {"translate", "unreviewed"}:
        return [
            _issue_with_runtime_mapping(
                issue=issue,
                provenance=provenance,
                blocking=True,
            )
            for issue in issues
        ]
    if provenance.review_kind in {"excluded", "non_source"}:
        return [
            _issue_with_runtime_mapping(
                issue=issue,
                provenance=provenance,
                blocking=False,
            )
            for issue in issues
        ]
    return [
        ActiveRuntimePluginSourceIssue(
            code="active_runtime_provenance_missing",
            message=f"当前运行插件源码来源映射状态无效: {provenance.review_kind}",
            file_name=issue.file_name,
            literal=issue.literal,
            mapping_reason="invalid_review_kind",
        )
        for issue in issues
    ]


def _issue_with_runtime_mapping(
    *,
    issue: ActiveRuntimePluginSourceIssue,
    provenance: PluginSourceRuntimeProvenanceRecord,
    blocking: bool,
) -> ActiveRuntimePluginSourceIssue:
    """把来源映射状态补入单条审计问题。"""
    return ActiveRuntimePluginSourceIssue(
        code=issue.code,
        message=issue.message,
        file_name=issue.file_name,
        blocking=blocking,
        fragment=issue.fragment,
        literal=issue.literal,
        review_kind=provenance.review_kind,
        mapping_reason="runtime_provenance_exact_match",
        read_error=issue.read_error,
        syntax_error=issue.syntax_error,
    )


def _collect_bad_control_fragments(literal: PluginSourceStringLiteral) -> list[str]:
    """收集反斜杠被 JS 换行转义吃掉后的裸控制符片段。"""
    fragments: list[str] = []
    for match in RAW_LITERAL_LINE_BREAK_CONTROL_PATTERN.finditer(literal.raw_text):
        fragments.append(match.group("fragment"))
    for match in VISIBLE_LINE_START_CONTROL_PATTERN.finditer(literal.text):
        fragments.append(match.group("fragment"))
    return sorted(set(fragments))


def _deduplicate_issues(
    issues: list[ActiveRuntimePluginSourceIssue],
) -> list[ActiveRuntimePluginSourceIssue]:
    """去掉同一字面量内重复报告的问题。"""
    seen: set[tuple[str, str, str, str, str, str]] = set()
    deduplicated: list[ActiveRuntimePluginSourceIssue] = []
    for issue in issues:
        selector = issue.literal.selector if issue.literal is not None else ""
        key = (issue.code, issue.file_name, selector, issue.fragment, issue.read_error, issue.syntax_error)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(issue)
    return deduplicated


def _enabled_plugin_source_file_names(game_data: GameData) -> frozenset[str]:
    """从当前插件配置读取实际启用的直接插件源码文件名。"""
    file_names: set[str] = set()
    for plugin_index, plugin in enumerate(game_data.plugins_js):
        if plugin.get("status") is not True:
            continue
        plugin_name = extract_plugin_name(plugin, plugin_index).strip()
        if plugin_name:
            file_names.add(f"{plugin_name}.js")
    return frozenset(file_names)


__all__ = [
    "ActiveRuntimePluginSourceAudit",
    "ActiveRuntimePluginSourceIssue",
    "audit_active_runtime_plugin_source",
]
