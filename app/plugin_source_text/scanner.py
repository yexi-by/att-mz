"""插件源码文本 AST 地图扫描。"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from bisect import bisect_right
from dataclasses import dataclass

from app.native_javascript_ast import (
    NativeJavaScriptAstContext,
    NativeJavaScriptStringScan,
    parse_native_javascript_string_spans,
    parse_native_javascript_string_spans_batch,
)
from app.rmmz.text_rules import JsonObject, TextRules
from app.rmmz.text_protocol import normalize_visible_text_for_extraction

from .models import PluginSourceCandidate

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
_NATIVE_SCAN_CACHE_MAX_SIZE = 256
_NATIVE_SCAN_CACHE: OrderedDict[str, NativeJavaScriptStringScan] = OrderedDict()


def build_plugin_source_file_hash(source: str) -> str:
    """计算插件源码文件内容哈希。"""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def clear_plugin_source_native_scan_cache() -> None:
    """清空进程内插件源码 AST 扫描缓存。"""
    _NATIVE_SCAN_CACHE.clear()


def candidate_selector_for_span(*, start_index: int, end_index: int, raw_text: str) -> str:
    """按字符串节点位置和原始内容生成稳定 AST selector。"""
    digest = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()[:12]
    return f"ast:string:{start_index}:{end_index}:{digest}"


@dataclass(frozen=True, slots=True)
class PluginSourceCandidateIndex:
    """单个插件源码文件的候选索引。"""

    candidates: tuple[PluginSourceCandidate, ...]
    by_selector: dict[str, PluginSourceCandidate]


@dataclass(frozen=True, slots=True)
class PluginSourceFileTextScan:
    """单个插件源码文件的 AST 文本扫描结果。"""

    file_name: str
    file_hash: str
    literals: tuple["PluginSourceStringLiteral", ...]
    candidate_index: PluginSourceCandidateIndex


@dataclass(frozen=True, slots=True)
class PluginSourceBatchTextScan:
    """多个插件源码文件的严格 AST 批量扫描结果。"""

    file_scans: dict[str, PluginSourceFileTextScan]
    syntax_errors: dict[str, str]


@dataclass(frozen=True, slots=True)
class PluginSourceStringLiteral:
    """插件源码中的一个普通字符串字面量。"""

    file_name: str
    selector: str
    text: str
    raw_text: str
    line: int
    start_index: int
    end_index: int
    active: bool
    context: str

    def to_json_object(self) -> JsonObject:
        """转换成审计报告 JSON 对象。"""
        return {
            "file": self.file_name,
            "line": self.line,
            "selector": self.selector,
            "text": self.text,
            "raw_text": self.raw_text,
            "active": self.active,
            "context": self.context,
        }


def build_plugin_source_candidate_index(
    *,
    file_name: str,
    source: str,
    active: bool,
    text_rules: TextRules,
) -> PluginSourceCandidateIndex:
    """扫描单个源码文件一次，并生成 selector 到候选的索引。"""
    _literals, candidates = _scan_source_literals_and_candidates(
        file_name=file_name,
        source=source,
        active=active,
        text_rules=text_rules,
    )
    return PluginSourceCandidateIndex(
        candidates=candidates,
        by_selector={candidate.selector: candidate for candidate in candidates},
    )


def iter_plugin_source_string_literals(
    *,
    file_name: str,
    source: str,
    active: bool,
) -> tuple[PluginSourceStringLiteral, ...]:
    """返回源码中的全部普通字符串字面量，不按源语言字符过滤。"""
    literals, _candidates = _scan_source_literals_and_candidates(
        file_name=file_name,
        source=source,
        active=active,
        text_rules=None,
    )
    return literals


def scan_plugin_source_runtime_files_text_strict(
    *,
    files: dict[str, str],
    active_file_names: frozenset[str],
) -> PluginSourceBatchTextScan:
    """批量扫描当前运行插件源码的全部字符串字面量，不构造翻译源候选。"""
    return _scan_plugin_source_files_text_from_native_spans(
        files=files,
        active_file_names=active_file_names,
        text_rules=None,
    )


def _scan_plugin_source_files_text_from_native_spans(
    *,
    files: dict[str, str],
    active_file_names: frozenset[str],
    text_rules: TextRules | None,
) -> PluginSourceBatchTextScan:
    """用 Rust AST 批量解析源码字符串，并转换成现有扫描对象。"""
    file_hashes = {
        file_name: build_plugin_source_file_hash(source)
        for file_name, source in files.items()
    }
    scans = _parse_native_javascript_string_spans_batch_cached(
        files=files,
        file_hashes=file_hashes,
    )
    file_scans: dict[str, PluginSourceFileTextScan] = {}
    syntax_errors: dict[str, str] = {}
    for file_name, source in sorted(files.items()):
        scan = scans[file_name]
        if scan.has_error:
            syntax_errors[file_name] = "原生 AST 解析报告 JS 语法错误"
            continue
        literals, candidates = _build_literals_and_candidates_from_spans(
            file_name=file_name,
            source=source,
            active=file_name in active_file_names,
            text_rules=text_rules,
            spans=_native_scan_to_internal_spans(scan),
        )
        file_scans[file_name] = PluginSourceFileTextScan(
            file_name=file_name,
            file_hash=file_hashes[file_name],
            literals=literals,
            candidate_index=PluginSourceCandidateIndex(
                candidates=candidates,
                by_selector={candidate.selector: candidate for candidate in candidates},
            ),
        )
    return PluginSourceBatchTextScan(
        file_scans=file_scans,
        syntax_errors=syntax_errors,
    )


def _scan_source_literals_and_candidates(
    *,
    file_name: str,
    source: str,
    active: bool,
    text_rules: TextRules | None,
) -> tuple[tuple[PluginSourceStringLiteral, ...], tuple[PluginSourceCandidate, ...]]:
    """用一次 AST 扫描同时生成源码字符串字面量和可翻译候选。"""
    spans = _collect_string_literal_spans(source)
    return _build_literals_and_candidates_from_spans(
        file_name=file_name,
        source=source,
        active=active,
        text_rules=text_rules,
        spans=spans,
    )


def _build_literals_and_candidates_from_spans(
    *,
    file_name: str,
    source: str,
    active: bool,
    text_rules: TextRules | None,
    spans: list["_StringLiteralSpan"],
) -> tuple[tuple[PluginSourceStringLiteral, ...], tuple[PluginSourceCandidate, ...]]:
    """把已解析的字符串 span 转换成字面量和候选索引。"""
    newline_indexes = _collect_newline_indexes(source)
    literals: list[PluginSourceStringLiteral] = []
    candidates: list[PluginSourceCandidate] = []
    for span in spans:
        raw_text = source[span.content_start_index:span.content_end_index]
        text = normalize_visible_text_for_extraction(_unescape_js_text(raw_text))
        if not text:
            continue
        api = span.ast_context.call_name or _call_api_before(source, span.start_index)
        key = span.ast_context.property_key or _property_key_before(source, span.start_index)
        selector = candidate_selector_for_span(
            start_index=span.start_index,
            end_index=span.end_index,
            raw_text=raw_text,
        )
        line = _line_number_for_index(newline_indexes=newline_indexes, index=span.start_index)
        literals.append(
            PluginSourceStringLiteral(
                file_name=file_name,
                selector=selector,
                text=text,
                raw_text=raw_text,
                line=line,
                start_index=span.start_index,
                end_index=span.end_index,
                active=active,
                context=_candidate_context(api=api, key=key),
            )
        )
        if text_rules is None:
            continue
        should_translate = text_rules.should_translate_source_text(text)
        if not should_translate:
            continue
        structural_flags = tuple(_plugin_source_text_structural_flags(text))
        confidence = _candidate_confidence(
            text=text,
            should_translate=should_translate,
            api=api,
            key=key,
            ast_context=span.ast_context,
            structural_flags=structural_flags,
        )
        candidates.append(
            PluginSourceCandidate(
                file_name=file_name,
                selector=selector,
                text=text,
                raw_text=raw_text,
                quote=span.quote,
                line=line,
                start_index=span.start_index,
                end_index=span.end_index,
                content_start_index=span.content_start_index,
                content_end_index=span.content_end_index,
                context=_candidate_context(api=api, key=key),
                api=api,
                key=key,
                ast_context=span.ast_context.to_json_object(),
                active=active,
                confidence=confidence,
                structural_flags=structural_flags,
            )
        )
    return tuple(literals), tuple(candidates)


def _collect_newline_indexes(source: str) -> list[int]:
    """收集换行位置，供大量候选快速计算行号。"""
    return [index for index, char in enumerate(source) if char == "\n"]


def _line_number_for_index(*, newline_indexes: list[int], index: int) -> int:
    """根据预计算换行位置返回源码行号。"""
    return bisect_right(newline_indexes, index) + 1


@dataclass(frozen=True, slots=True)
class _StringLiteralSpan:
    """源码字符串字面量范围。"""

    kind: str
    quote: str
    start_index: int
    end_index: int
    content_start_index: int
    content_end_index: int
    ast_context: "_StringAstContext"


@dataclass(frozen=True, slots=True)
class _StringAstContext:
    """源码字符串节点的事实 AST 上下文。"""

    node_kind: str = ""
    property_key: str = ""
    property_path: tuple[str, ...] = ()
    call_name: str = ""
    call_argument_index: int | None = None
    return_function_name: str = ""
    assignment_name: str = ""

    def to_json_object(self) -> JsonObject:
        """转换成 AST 地图可序列化对象。"""
        return {
            "node_kind": self.node_kind,
            "property_key": self.property_key,
            "property_path": [part for part in self.property_path],
            "call_name": self.call_name,
            "call_argument_index": self.call_argument_index,
            "return_function_name": self.return_function_name,
            "assignment_name": self.assignment_name,
        }


def _collect_string_literal_spans(source: str) -> list[_StringLiteralSpan]:
    """使用 Rust AST 收集普通字符串字面量范围，解析失败时直接报错。"""
    return _collect_native_string_literal_spans_required(source)


def _collect_native_string_literal_spans_required(
    source: str,
    *,
    file_hash: str | None = None,
) -> list[_StringLiteralSpan]:
    """调用原生 AST 解析器，禁止在严格流程中退回轻量扫描。"""
    resolved_hash = file_hash if file_hash is not None else build_plugin_source_file_hash(source)
    scan = _read_native_scan_cache(resolved_hash)
    if scan is None:
        scan = parse_native_javascript_string_spans(source)
        _write_native_scan_cache(resolved_hash, scan)
    if scan.has_error:
        raise RuntimeError("原生 AST 解析报告 JS 语法错误")
    return _native_scan_to_internal_spans(scan)


def _parse_native_javascript_string_spans_batch_cached(
    *,
    files: dict[str, str],
    file_hashes: dict[str, str],
) -> dict[str, NativeJavaScriptStringScan]:
    """按源码 hash 复用 Rust AST 字符串节点扫描结果。"""
    scans: dict[str, NativeJavaScriptStringScan] = {}
    uncached_representatives: dict[str, tuple[str, str]] = {}
    for file_name, source in sorted(files.items()):
        file_hash = file_hashes[file_name]
        cached_scan = _read_native_scan_cache(file_hash)
        if cached_scan is not None:
            scans[file_name] = cached_scan
            continue
        if file_hash not in uncached_representatives:
            uncached_representatives[file_hash] = (file_name, source)

    if uncached_representatives:
        fresh_input = {
            representative_name: source
            for representative_name, source in uncached_representatives.values()
        }
        fresh_scans = parse_native_javascript_string_spans_batch(fresh_input)
        fresh_scans_by_hash: dict[str, NativeJavaScriptStringScan] = {}
        for file_hash, (representative_name, _source) in uncached_representatives.items():
            fresh_scan = fresh_scans[representative_name]
            _write_native_scan_cache(file_hash, fresh_scan)
            fresh_scans_by_hash[file_hash] = fresh_scan
        for file_name, file_hash in file_hashes.items():
            if file_name not in scans:
                scans[file_name] = fresh_scans_by_hash[file_hash]
    return scans


def _read_native_scan_cache(file_hash: str) -> NativeJavaScriptStringScan | None:
    """读取并刷新进程内 AST 扫描缓存项。"""
    scan = _NATIVE_SCAN_CACHE.get(file_hash)
    if scan is not None:
        _NATIVE_SCAN_CACHE.move_to_end(file_hash)
    return scan


def _write_native_scan_cache(file_hash: str, scan: NativeJavaScriptStringScan) -> None:
    """写入进程内 AST 扫描缓存并按 LRU 控制大小。"""
    _NATIVE_SCAN_CACHE[file_hash] = scan
    _NATIVE_SCAN_CACHE.move_to_end(file_hash)
    while len(_NATIVE_SCAN_CACHE) > _NATIVE_SCAN_CACHE_MAX_SIZE:
        _ = _NATIVE_SCAN_CACHE.popitem(last=False)


def _native_scan_to_internal_spans(scan: NativeJavaScriptStringScan) -> list[_StringLiteralSpan]:
    """把原生 AST 扫描结果转换为内部 span。"""
    return [
        _StringLiteralSpan(
            kind=span.kind,
            quote=span.quote,
            start_index=span.start_index,
            end_index=span.end_index,
            content_start_index=span.content_start_index,
            content_end_index=span.content_end_index,
            ast_context=_native_ast_context_to_internal(span.ast_context),
        )
        for span in scan.spans
    ]


def _native_ast_context_to_internal(context: NativeJavaScriptAstContext) -> _StringAstContext:
    """转换原生 AST 上下文结构。"""
    return _StringAstContext(
        node_kind=context.node_kind,
        property_key=context.property_key,
        property_path=context.property_path,
        call_name=context.call_name,
        call_argument_index=context.call_argument_index,
        return_function_name=context.return_function_name,
        assignment_name=context.assignment_name,
    )


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
    ast_context: _StringAstContext,
    structural_flags: tuple[str, ...],
) -> str:
    """按上下文给源码字符串候选分级。"""
    if not should_translate:
        return "ignored"
    if "resource_path_like" in structural_flags or "number_like" in structural_flags:
        return "weak"
    if api and any(api.endswith(suffix) or api == suffix for suffix in STRONG_CALL_SUFFIXES):
        return "strong"
    if key in STRONG_TEXT_KEYS:
        return "strong"
    if ast_context.return_function_name or ast_context.assignment_name or ast_context.property_path:
        return "medium"
    if len(text) >= 8 and "identifier_or_path_like" not in structural_flags:
        return "medium"
    return "weak"


def _candidate_context(*, api: str, key: str) -> str:
    """生成候选上下文描述。"""
    if api:
        return f"call:{api}"
    if key:
        return f"property:{key}"
    return "literal"


def _unescape_js_text(text: str) -> str:
    """解析候选展示与写回校验需要的常见 JS 字符串转义。"""
    decoded_parts: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\":
            decoded_parts.append(char)
            index += 1
            continue
        if index + 1 >= len(text):
            decoded_parts.append("\\")
            index += 1
            continue
        escaped = text[index + 1]
        if escaped in {"'", '"', "\\", "/"}:
            decoded_parts.append(escaped)
            index += 2
            continue
        if escaped == "n":
            decoded_parts.append("\n")
            index += 2
            continue
        if escaped == "r":
            decoded_parts.append("\r")
            index += 2
            continue
        if escaped == "t":
            decoded_parts.append("\t")
            index += 2
            continue
        if escaped == "b":
            decoded_parts.append("\b")
            index += 2
            continue
        if escaped == "f":
            decoded_parts.append("\f")
            index += 2
            continue
        if escaped == "v":
            decoded_parts.append("\v")
            index += 2
            continue
        if escaped == "0":
            decoded_parts.append("\0")
            index += 2
            continue
        if escaped == "x" and _has_hex_digits(text, index + 2, 2):
            decoded_parts.append(chr(int(text[index + 2:index + 4], 16)))
            index += 4
            continue
        if escaped == "u":
            unicode_result = _decode_unicode_escape(text, index + 2)
            if unicode_result is not None:
                decoded_char, next_index = unicode_result
                decoded_parts.append(decoded_char)
                index = next_index
                continue
        if escaped in {"\n", "\r"}:
            index += 2
            if escaped == "\r" and index < len(text) and text[index] == "\n":
                index += 1
            continue
        decoded_parts.append(escaped)
        index += 2
    return "".join(decoded_parts)


def _has_hex_digits(text: str, start_index: int, count: int) -> bool:
    """判断指定范围是否全是十六进制字符。"""
    end_index = start_index + count
    if end_index > len(text):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in text[start_index:end_index])


def _decode_unicode_escape(text: str, start_index: int) -> tuple[str, int] | None:
    """解析 JS `\\uXXXX` 或 `\\u{X...}` Unicode 转义。"""
    if start_index < len(text) and text[start_index] == "{":
        end_index = text.find("}", start_index + 1)
        if end_index == -1:
            return None
        hex_text = text[start_index + 1:end_index]
        if not hex_text or not all(char in "0123456789abcdefABCDEF" for char in hex_text):
            return None
        return chr(int(hex_text, 16)), end_index + 1
    if not _has_hex_digits(text, start_index, 4):
        return None
    return chr(int(text[start_index:start_index + 4], 16)), start_index + 4


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
    "PluginSourceCandidateIndex",
    "PluginSourceBatchTextScan",
    "PluginSourceFileTextScan",
    "PluginSourceStringLiteral",
    "build_plugin_source_candidate_index",
    "build_plugin_source_file_hash",
    "candidate_selector_for_span",
    "clear_plugin_source_native_scan_cache",
    "iter_plugin_source_string_literals",
    "scan_plugin_source_runtime_files_text_strict",
]
