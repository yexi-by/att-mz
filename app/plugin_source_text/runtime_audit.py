"""当前运行插件源码审计。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.native_javascript_ast import parse_native_javascript_string_spans
from app.plugin_text import extract_plugin_name
from app.rmmz.schema import GameData
from app.rmmz.text_rules import JsonArray, JsonObject, TextRules

from .scanner import PluginSourceStringLiteral, iter_plugin_source_string_literals

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
    fragment: str = ""
    literal: PluginSourceStringLiteral | None = None
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
        payload["fragment"] = self.fragment
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

    def summary_json(self) -> JsonObject:
        """转换成质量报告摘要字段。"""
        counts = self.issue_counts
        return {
            "active_runtime_scanned_file_count": self.scanned_file_count,
            "active_runtime_active_file_count": self.active_file_count,
            "active_runtime_literal_count": self.literal_count,
            "active_runtime_active_literal_count": self.active_literal_count,
            "active_runtime_read_error_file_count": self.read_error_file_count,
            "active_runtime_issue_count": len(self.issues),
            "active_runtime_read_error_count": counts.get("active_runtime_read_error", 0),
            "active_runtime_syntax_error_count": counts.get("active_runtime_syntax_error", 0),
            "active_runtime_source_residual_count": counts.get("active_runtime_source_residual", 0),
            "active_runtime_placeholder_risk_count": counts.get("active_runtime_placeholder_risk", 0),
        }

    def issues_json(self, *, limit: int = 100) -> JsonArray:
        """返回前 N 条审计问题。"""
        return [issue.to_json_object() for issue in self.issues[:limit]]


def audit_active_runtime_plugin_source(
    *,
    game_data: GameData,
    text_rules: TextRules,
    plugin_source_files: dict[str, str] | None = None,
    plugin_source_read_errors: dict[str, str] | None = None,
) -> ActiveRuntimePluginSourceAudit:
    """审计当前运行插件源码中的源文残留和坏控制符。"""
    enabled_plugin_files = _enabled_plugin_source_file_names(game_data)
    source_files = plugin_source_files if plugin_source_files is not None else game_data.plugin_source_files
    read_errors = (
        plugin_source_read_errors
        if plugin_source_read_errors is not None
        else game_data.plugin_source_read_errors
    )
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
            syntax_issue = _strict_active_runtime_syntax_issue(file_name=file_name, source=source)
            if syntax_issue is not None:
                issues.append(syntax_issue)
                continue
        literals = iter_plugin_source_string_literals(
            file_name=file_name,
            source=source,
            active=active,
        )
        literal_count += len(literals)
        if not active:
            continue
        active_literal_count += len(literals)
        for literal in literals:
            issues.extend(_audit_literal(literal=literal, text_rules=text_rules))
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
    source: str,
) -> ActiveRuntimePluginSourceIssue | None:
    """严格检查当前运行源码语法，禁止门禁阶段退回轻量扫描。"""
    try:
        scan = parse_native_javascript_string_spans(source)
    except (ImportError, RuntimeError) as error:
        return ActiveRuntimePluginSourceIssue(
            code="active_runtime_syntax_error",
            message="当前游戏运行文件里的插件源码无法完成 JS 语法检查，不能确认是否存在漏翻、坏控制符或 JS 语法错误",
            file_name=file_name,
            syntax_error=f"{type(error).__name__}: {error}",
        )
    if scan.has_error:
        return ActiveRuntimePluginSourceIssue(
            code="active_runtime_syntax_error",
            message="当前游戏运行文件里的插件源码 JS 语法检查失败，不能继续视为完成",
            file_name=file_name,
            syntax_error="原生 AST 解析报告 JS 语法错误",
        )
    return None


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
