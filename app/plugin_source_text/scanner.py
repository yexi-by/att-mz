"""插件源码文本 AST 地图扫描。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.native_javascript_ast import parse_native_javascript_string_spans
from app.plugin_text import extract_plugin_name
from app.rmmz.schema import GameData
from app.rmmz.text_rules import TextRules
from app.rmmz.text_protocol import normalize_visible_text_for_extraction

from .models import PluginSourceCandidate, PluginSourceFileScan, PluginSourceRisk, PluginSourceScan

STRONG_TEXT_KEYS: frozenset[str] = frozenset(
    {
        "body",
        "caption",
        "description",
        "help",
        "helpLines",
        "label",
        "longDescription",
        "message",
        "name",
        "nickName",
        "param1",
        "param2",
        "shortDescription",
        "stanceDescription",
        "text",
        "title",
    }
)
STRONG_CALL_SUFFIXES: tuple[str, ...] = (
    "addCommand",
    "addText",
    "drawText",
    "drawTextEx",
    "setText",
    "$gameMessage.add",
)
RESOURCE_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"\.(?:png|jpg|jpeg|webp|gif|ogg|m4a|mp3|wav|json|js|css|ttf|woff2?)$",
    re.IGNORECASE,
)
IDENTIFIER_OR_PATH_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_./:$-]+$")
CALL_CONTEXT_PATTERN: re.Pattern[str] = re.compile(
    r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(\s*$"
)
KEY_CONTEXT_PATTERN: re.Pattern[str] = re.compile(
    r"(?:([A-Za-z_$][\w$]*)|['\"]([^'\"]+)['\"])\s*:\s*$"
)


def build_plugin_source_scan(*, game_data: GameData, text_rules: TextRules) -> PluginSourceScan:
    """扫描 `js/plugins` 直接源码文件并计算高风险摘要。"""
    enabled_plugin_files = _enabled_plugin_source_file_names(game_data)
    file_scans: list[PluginSourceFileScan] = []
    candidates: list[PluginSourceCandidate] = []
    for file_name, source in sorted(game_data.plugin_source_files.items()):
        active = file_name in enabled_plugin_files
        file_candidates = tuple(
            _scan_source_candidates(
                file_name=file_name,
                source=source,
                active=active,
                text_rules=text_rules,
            )
        )
        active_candidates = [candidate for candidate in file_candidates if candidate.active]
        strong_count = sum(1 for candidate in active_candidates if candidate.confidence == "strong")
        medium_count = sum(1 for candidate in active_candidates if candidate.confidence == "medium")
        file_score = strong_count * 3 + medium_count
        file_scans.append(
            PluginSourceFileScan(
                file_name=file_name,
                file_hash=build_plugin_source_file_hash(source),
                active=active,
                candidates=file_candidates,
                strong_context_text_count=strong_count,
                medium_confidence_text_count=medium_count,
                file_score=file_score,
            )
        )
        candidates.extend(file_candidates)

    risk = _build_risk(
        file_scans,
        read_error_file_count=len(game_data.plugin_source_read_errors),
    )
    return PluginSourceScan(
        risk=risk,
        files=tuple(file_scans),
        candidates=tuple(candidates),
        enabled_plugin_files=enabled_plugin_files,
    )


def build_plugin_source_file_hash(source: str) -> str:
    """计算插件源码文件内容哈希。"""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def candidate_selector_for_span(*, start_index: int, end_index: int, raw_text: str) -> str:
    """按字符串节点位置和原始内容生成稳定 AST selector。"""
    digest = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()[:12]
    return f"ast:string:{start_index}:{end_index}:{digest}"


def find_candidate_by_selector(
    *,
    source: str,
    file_name: str,
    selector: str,
    active: bool,
    text_rules: TextRules,
) -> PluginSourceCandidate | None:
    """重新扫描源码并按 selector 定位候选。"""
    for candidate in _scan_source_candidates(
        file_name=file_name,
        source=source,
        active=active,
        text_rules=text_rules,
    ):
        if candidate.selector == selector:
            return candidate
    return None


def _enabled_plugin_source_file_names(game_data: GameData) -> frozenset[str]:
    """从 `plugins.js` 读取启用插件对应的源码文件名。"""
    file_names: set[str] = set()
    for plugin_index, plugin in enumerate(game_data.plugins_js):
        status = plugin.get("status")
        if status is not True:
            continue
        plugin_name = extract_plugin_name(plugin, plugin_index).strip()
        if not plugin_name:
            continue
        file_names.add(f"{plugin_name}.js")
    return frozenset(file_names)


def _scan_source_candidates(
    *,
    file_name: str,
    source: str,
    active: bool,
    text_rules: TextRules,
) -> list[PluginSourceCandidate]:
    """扫描单个 JS 源码中的字符串字面量候选。"""
    spans = _collect_string_literal_spans(source)
    candidates: list[PluginSourceCandidate] = []
    for span in spans:
        raw_text = source[span.content_start_index:span.content_end_index]
        text = normalize_visible_text_for_extraction(_unescape_js_text(raw_text))
        if not text:
            continue
        structural_flags = tuple(_plugin_source_text_structural_flags(text))
        should_translate = text_rules.should_translate_source_text(text)
        api = _call_api_before(source, span.start_index)
        key = _property_key_before(source, span.start_index)
        confidence = _candidate_confidence(
            text=text,
            should_translate=should_translate,
            api=api,
            key=key,
            structural_flags=structural_flags,
        )
        if confidence == "ignored" and not (api or key):
            continue
        candidates.append(
            PluginSourceCandidate(
                file_name=file_name,
                selector=candidate_selector_for_span(
                    start_index=span.start_index,
                    end_index=span.end_index,
                    raw_text=raw_text,
                ),
                text=text,
                raw_text=raw_text,
                quote=span.quote,
                line=source.count("\n", 0, span.start_index) + 1,
                start_index=span.start_index,
                end_index=span.end_index,
                content_start_index=span.content_start_index,
                content_end_index=span.content_end_index,
                context=_candidate_context(api=api, key=key),
                api=api,
                key=key,
                active=active,
                confidence=confidence,
                structural_flags=structural_flags,
            )
        )
    return candidates


@dataclass(frozen=True, slots=True)
class _StringLiteralSpan:
    """源码字符串字面量范围。"""

    quote: str
    start_index: int
    end_index: int
    content_start_index: int
    content_end_index: int


def _collect_string_literal_spans(source: str) -> list[_StringLiteralSpan]:
    """优先用 Rust AST 收集普通字符串字面量范围。"""
    native_spans = _collect_native_string_literal_spans(source)
    if native_spans is not None:
        return native_spans
    return _collect_string_literal_spans_fallback(source)


def _collect_native_string_literal_spans(source: str) -> list[_StringLiteralSpan] | None:
    """调用 Rust AST 解析器，解析失败时交给低成本回退扫描。"""
    try:
        scan = parse_native_javascript_string_spans(source)
    except (ImportError, RuntimeError):
        return None
    if scan.has_error:
        return None
    return [
        _StringLiteralSpan(
            quote=span.quote,
            start_index=span.start_index,
            end_index=span.end_index,
            content_start_index=span.content_start_index,
            content_end_index=span.content_end_index,
        )
        for span in scan.spans
    ]


def _collect_string_literal_spans_fallback(source: str) -> list[_StringLiteralSpan]:
    """跳过注释并收集普通字符串字面量范围。"""
    spans: list[_StringLiteralSpan] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        next_char = source[index + 1] if index + 1 < length else ""
        if char == "/" and next_char == "/":
            newline_index = source.find("\n", index + 2)
            index = length if newline_index == -1 else newline_index + 1
            continue
        if char == "/" and next_char == "*":
            close_index = source.find("*/", index + 2)
            index = length if close_index == -1 else close_index + 2
            continue
        if char not in {"'", '"'}:
            index += 1
            continue
        start_index = index
        index += 1
        escaped = False
        while index < length:
            current = source[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if current == "\\":
                escaped = True
                index += 1
                continue
            if current == char:
                spans.append(
                    _StringLiteralSpan(
                        quote=char,
                        start_index=start_index,
                        end_index=index + 1,
                        content_start_index=start_index + 1,
                        content_end_index=index,
                    )
                )
                index += 1
                break
            index += 1
    return spans


def _call_api_before(source: str, start_index: int) -> str:
    """读取字符串前的调用 API 名称。"""
    prefix = source[max(0, start_index - 160):start_index]
    match = CALL_CONTEXT_PATTERN.search(prefix)
    if match is None:
        return ""
    return match.group(1)


def _property_key_before(source: str, start_index: int) -> str:
    """读取对象属性值字符串前的 key。"""
    prefix = source[max(0, start_index - 120):start_index]
    match = KEY_CONTEXT_PATTERN.search(prefix)
    if match is None:
        return ""
    key = match.group(1) or match.group(2)
    return key or ""


def _candidate_confidence(
    *,
    text: str,
    should_translate: bool,
    api: str,
    key: str,
    structural_flags: tuple[str, ...],
) -> str:
    """按上下文给源码字符串候选分级。"""
    if not should_translate:
        return "ignored"
    if "resource_path_like" in structural_flags or "number_like" in structural_flags:
        return "ignored"
    if api and any(api.endswith(suffix) or api == suffix for suffix in STRONG_CALL_SUFFIXES):
        return "strong"
    if key in STRONG_TEXT_KEYS:
        return "strong"
    if len(text) >= 8 and "identifier_or_path_like" not in structural_flags:
        return "medium"
    return "ignored"


def _candidate_context(*, api: str, key: str) -> str:
    """生成候选上下文描述。"""
    if api:
        return f"call:{api}"
    if key:
        return f"property:{key}"
    return "literal"


def _build_risk(file_scans: list[PluginSourceFileScan], *, read_error_file_count: int) -> PluginSourceRisk:
    """按固定阈值生成风险摘要。"""
    active_files = [file_scan for file_scan in file_scans if file_scan.active]
    ignored_file_count = sum(1 for file_scan in file_scans if not file_scan.active)
    strong_total = sum(file_scan.strong_context_text_count for file_scan in active_files)
    medium_total = sum(file_scan.medium_confidence_text_count for file_scan in active_files)
    risk_score = strong_total * 3 + medium_total
    files_score_ge_250 = sum(1 for file_scan in active_files if file_scan.file_score >= 250)
    max_file_score = max((file_scan.file_score for file_scan in active_files), default=0)
    high_risk = (
        strong_total >= 300
        or risk_score >= 2000
        or files_score_ge_250 >= 3
        or any(
            file_scan.file_score >= 300 and file_scan.strong_context_text_count >= 80
            for file_scan in active_files
        )
    )
    return PluginSourceRisk(
        high_risk=high_risk,
        risk_score=risk_score,
        strong_context_text_count=strong_total,
        medium_confidence_text_count=medium_total,
        scanned_file_count=len(file_scans),
        ignored_file_count=ignored_file_count,
        read_error_file_count=read_error_file_count,
        files_score_ge_250=files_score_ge_250,
        max_file_score=max_file_score,
    )


def _unescape_js_text(text: str) -> str:
    """解析候选展示与写回校验需要的常见 JS 字符串转义。"""
    return (
        text.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\'", "'")
        .replace(r'\"', '"')
        .replace(r"\\", "\\")
    )


def _plugin_source_text_structural_flags(text: str) -> list[str]:
    """给源码字符串候选附加结构提示。"""
    flags: list[str] = []
    lowered_text = text.lower()
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        flags.append("number_like")
    if RESOURCE_PATH_PATTERN.search(lowered_text):
        flags.append("resource_path_like")
    if IDENTIFIER_OR_PATH_PATTERN.fullmatch(text) and ("_" in text or "/" in text):
        flags.append("identifier_or_path_like")
    return flags


__all__ = [
    "build_plugin_source_file_hash",
    "build_plugin_source_scan",
    "candidate_selector_for_span",
    "find_candidate_by_selector",
]
