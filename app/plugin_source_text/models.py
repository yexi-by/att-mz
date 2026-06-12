"""插件源码文本扫描、规则和候选数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from pydantic import Field

from app.external_input import ExternalInputModel, ExternalStr
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class PluginSourceCandidate:
    """插件源码中一个 AST 字符串候选。"""

    file_name: str
    selector: str
    text: str
    raw_text: str
    quote: str
    line: int
    start_index: int
    end_index: int
    content_start_index: int
    content_end_index: int
    context: str
    api: str
    key: str
    ast_context: JsonObject
    active: bool
    confidence: str
    structural_flags: tuple[str, ...]

    def to_json_object(self) -> JsonObject:
        """转换成 Agent 可读 JSON 对象。"""
        return {
            "file": self.file_name,
            "line": self.line,
            "selector": self.selector,
            "text": self.text,
            "context": self.context,
            "api": self.api,
            "key": self.key,
            "ast_context": {key: value for key, value in self.ast_context.items()},
            "active": self.active,
            "confidence": self.confidence,
            "structural_flags": [flag for flag in self.structural_flags],
        }


@dataclass(frozen=True, slots=True)
class PluginSourceFileScan:
    """单个插件源码文件的扫描结果。"""

    file_name: str
    file_hash: str
    active: bool
    candidates: tuple[PluginSourceCandidate, ...]
    strong_context_text_count: int
    medium_confidence_text_count: int
    file_score: int

    def to_json_object(self) -> JsonObject:
        """转换成 AST 地图文件中的单文件对象。"""
        return {
            "file": self.file_name,
            "file_hash": self.file_hash,
            "active": self.active,
            "strong_context_text_count": self.strong_context_text_count,
            "medium_confidence_text_count": self.medium_confidence_text_count,
            "file_score": self.file_score,
            "candidates": [candidate.to_json_object() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class PluginSourceRisk:
    """插件源码文本风险摘要。"""

    high_risk: bool
    risk_score: int
    strong_context_text_count: int
    medium_confidence_text_count: int
    scanned_file_count: int
    ignored_file_count: int
    read_error_file_count: int
    syntax_error_file_count: int
    files_score_ge_250: int
    max_file_score: int

    def to_json_object(self) -> JsonObject:
        """转换成风险报告 JSON 对象。"""
        return {
            "high_risk": self.high_risk,
            "risk_score": self.risk_score,
            "strong_context_text_count": self.strong_context_text_count,
            "medium_confidence_text_count": self.medium_confidence_text_count,
            "scanned_file_count": self.scanned_file_count,
            "ignored_file_count": self.ignored_file_count,
            "read_error_file_count": self.read_error_file_count,
            "syntax_error_file_count": self.syntax_error_file_count,
            "files_score_ge_250": self.files_score_ge_250,
            "max_file_score": self.max_file_score,
            "thresholds": {
                "strong_context_text_count": 300,
                "risk_score": 2000,
                "files_score_ge_250": 3,
                "single_file_score": 300,
                "single_file_strong_context_text_count": 80,
            },
        }


@dataclass(frozen=True, slots=True)
class PluginSourceStaleReason:
    """Rust 判断出的插件源码 selector 失效原因。"""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PluginSourceSelectorFact:
    """Rust 输出的插件源码 selector 当前事实。"""

    file_name: str
    selector: str
    role: str
    active: bool
    file_hash: str
    source_text_hash: str
    stale_reason: PluginSourceStaleReason | None = None


@dataclass(frozen=True, slots=True)
class PluginSourceReviewSummary:
    """Rust 输出的插件源码规则审查覆盖摘要。"""

    total_selector_count: int
    translated_selector_count: int
    excluded_selector_count: int
    filtered_selector_count: int
    reviewed_selector_count: int
    stale_selector_count: int
    active_candidate_count: int
    unreviewed_selector_count: int
    review_required: bool


@dataclass(frozen=True, slots=True)
class PluginSourceScan:
    """插件源码扫描总结果。"""

    risk: PluginSourceRisk
    files: tuple[PluginSourceFileScan, ...]
    candidates: tuple[PluginSourceCandidate, ...]
    selector_facts: tuple[PluginSourceSelectorFact, ...] = ()
    review_summary: PluginSourceReviewSummary | None = None
    scope_hash: str = ""
    enabled_plugin_files: frozenset[str] = field(default_factory=frozenset)
    syntax_errors: dict[str, str] = field(default_factory=dict)

    def to_json_object(self) -> JsonObject:
        """转换成完整 AST 地图 JSON 对象。"""
        enabled_plugin_files: list[JsonValue] = [
            cast(JsonValue, file_name) for file_name in sorted(self.enabled_plugin_files)
        ]
        return {
            "risk": self.risk.to_json_object(),
            "enabled_plugin_files": enabled_plugin_files,
            "candidate_count": len(self.candidates),
            "syntax_errors": self.syntax_errors_json(),
            "files": [file_scan.to_json_object() for file_scan in self.files],
        }

    def risk_report_json(self) -> JsonObject:
        """转换成默认工作区使用的轻量风险报告。"""
        enabled_plugin_files: list[JsonValue] = [
            cast(JsonValue, file_name) for file_name in sorted(self.enabled_plugin_files)
        ]
        return {
            "risk": self.risk.to_json_object(),
            "enabled_plugin_files": enabled_plugin_files,
            "candidate_count": len(self.candidates),
            "active_candidate_count": sum(1 for candidate in self.candidates if candidate.active),
            "syntax_errors": self.syntax_errors_json(),
        }

    def candidates_json(self) -> JsonArray:
        """返回插件源码候选数组。"""
        return [candidate.to_json_object() for candidate in self.candidates]

    def syntax_errors_json(self) -> JsonArray:
        """返回跳过的非法 JS 插件源码明细。"""
        return [
            {
                "file": file_name,
                "active": file_name in self.enabled_plugin_files,
                "syntax_error": syntax_error,
            }
            for file_name, syntax_error in sorted(self.syntax_errors.items())
        ]


class PluginSourceRuleImportEntry(ExternalInputModel):
    """插件源码规则导入文件中的单文件规则。"""

    file: ExternalStr
    selectors: list[ExternalStr] = Field(default_factory=list)
    excluded_selectors: list[ExternalStr] = Field(default_factory=list)


class PluginSourceRuleImportFile(ExternalInputModel):
    """插件源码规则导入文件。"""

    rules: list[PluginSourceRuleImportEntry] = Field(default_factory=list)


__all__ = [
    "PluginSourceCandidate",
    "PluginSourceFileScan",
    "PluginSourceRisk",
    "PluginSourceReviewSummary",
    "PluginSourceRuleImportEntry",
    "PluginSourceRuleImportFile",
    "PluginSourceScan",
    "PluginSourceSelectorFact",
    "PluginSourceStaleReason",
]
