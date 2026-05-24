"""插件源码文本 AST selector 写回。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.rmmz.placeholder_guard import ensure_no_internal_placeholder_tokens
from app.rmmz.schema import (
    GameData,
    PluginSourceRuntimeWriteMapRecord,
    TranslationItem,
)
from app.rmmz.text_rules import TextRules, get_default_text_rules

from .extraction import parse_plugin_source_location_path
from .models import PluginSourceCandidate
from .runtime_mapping import plugin_source_runtime_hash_lines, plugin_source_runtime_hash_text
from .scanner import (
    candidate_selector_for_span,
    PluginSourceFileTextScan,
    scan_plugin_source_file_text_strict,
)


@dataclass(frozen=True, slots=True)
class _PluginSourceReplacement:
    """单条插件源码替换和映射所需的确定性上下文。"""

    selector: str
    item: TranslationItem
    candidate: PluginSourceCandidate
    written_text: str
    source_file_hash: str


@dataclass(frozen=True, slots=True)
class _PluginSourceReplacementResult:
    """单条插件源码替换后的最终源码坐标。"""

    replacement: _PluginSourceReplacement
    runtime_selector: str


def write_plugin_source_text(
    game_data: GameData,
    items: list[TranslationItem],
    text_rules: TextRules | None = None,
) -> list[PluginSourceRuntimeWriteMapRecord]:
    """把插件源码译文写入可写源码副本，并返回可选诊断映射。"""
    rules = text_rules if text_rules is not None else get_default_text_rules()
    items_by_file: dict[str, list[tuple[str, TranslationItem]]] = {}
    for item in items:
        parsed = parse_plugin_source_location_path(item.location_path)
        if parsed is None:
            continue
        file_name, selector = parsed
        ensure_no_internal_placeholder_tokens(
            lines=item.translation_lines,
            context=item.location_path,
            text_rules=rules,
        )
        if len(item.translation_lines) != 1:
            raise ValueError(f"插件源码短文本只能写入 1 行译文: {item.location_path}")
        items_by_file.setdefault(file_name, []).append((selector, item))

    replacements_by_file: dict[str, list[_PluginSourceReplacement]] = {}
    for file_name, file_items in items_by_file.items():
        source = game_data.writable_plugin_source_files.get(file_name)
        if source is None:
            raise ValueError(f"插件源码文件不存在: {file_name}")
        source_scan = _strict_plugin_source_scan(
            file_name=file_name,
            source=source,
            active=True,
            text_rules=rules,
        )
        candidate_index = source_scan.candidate_index
        for selector, item in file_items:
            candidate = candidate_index.by_selector.get(selector)
            if candidate is None:
                raise ValueError(f"插件源码 selector 已失效: {item.location_path}")
            if item.original_lines != [candidate.text]:
                raise ValueError(f"插件源码原文已变化，请重新导出 AST 地图: {item.location_path}")
            written_text = _escape_js_string_content(
                text=item.translation_lines[0].strip(),
                quote=candidate.quote,
            )
            source_file_hash = source_scan.file_hash
            replacements_by_file.setdefault(file_name, []).append(
                _PluginSourceReplacement(
                    selector=selector,
                    item=item,
                    candidate=candidate,
                    written_text=written_text,
                    source_file_hash=source_file_hash,
                )
            )

    runtime_map_records: list[PluginSourceRuntimeWriteMapRecord] = []
    for file_name, replacements in replacements_by_file.items():
        content = game_data.writable_plugin_source_files[file_name]
        content, replacement_results = _apply_replacements_with_runtime_selectors(
            source=content,
            replacements=replacements,
        )
        runtime_scan = _strict_plugin_source_scan(
            file_name=file_name,
            source=content,
            active=True,
            text_rules=None,
        )
        runtime_map_records.extend(
            _build_runtime_map_records(
                file_name=file_name,
                replacement_results=replacement_results,
                runtime_scan=runtime_scan,
            )
        )
        game_data.writable_plugin_source_files[file_name] = content
    return runtime_map_records


def _apply_replacements_with_runtime_selectors(
    *,
    source: str,
    replacements: list[_PluginSourceReplacement],
) -> tuple[str, list[_PluginSourceReplacementResult]]:
    """应用替换并按最终字符串 span 计算当前运行 selector。"""
    ordered_replacements = sorted(
        replacements,
        key=lambda replacement: replacement.candidate.content_start_index,
    )
    parts: list[str] = []
    current_source_index = 0
    current_runtime_index = 0
    results: list[_PluginSourceReplacementResult] = []
    for replacement in ordered_replacements:
        candidate = replacement.candidate
        unchanged = source[current_source_index:candidate.content_start_index]
        parts.append(unchanged)
        current_runtime_index += len(unchanged)
        runtime_content_start_index = current_runtime_index
        parts.append(replacement.written_text)
        current_runtime_index += len(replacement.written_text)
        runtime_content_end_index = current_runtime_index
        current_source_index = candidate.content_end_index

        literal_prefix_length = candidate.content_start_index - candidate.start_index
        literal_suffix_length = candidate.end_index - candidate.content_end_index
        runtime_start_index = runtime_content_start_index - literal_prefix_length
        runtime_end_index = runtime_content_end_index + literal_suffix_length
        runtime_selector = candidate_selector_for_span(
            start_index=runtime_start_index,
            end_index=runtime_end_index,
            raw_text=replacement.written_text,
        )
        results.append(
            _PluginSourceReplacementResult(
                replacement=replacement,
                runtime_selector=runtime_selector,
            )
        )
    tail = source[current_source_index:]
    parts.append(tail)
    return "".join(parts), results


def _build_runtime_map_records(
    *,
    file_name: str,
    replacement_results: list[_PluginSourceReplacementResult],
    runtime_scan: PluginSourceFileTextScan,
) -> list[PluginSourceRuntimeWriteMapRecord]:
    """为已写入译文生成可选诊断映射；无法匹配时不影响写回结果。"""
    literals_by_selector = {
        literal.selector: literal
        for literal in runtime_scan.literals
    }
    created_at = datetime.now().isoformat(timespec="seconds")
    records: list[PluginSourceRuntimeWriteMapRecord] = []
    for result in replacement_results:
        replacement = result.replacement
        literal = literals_by_selector.get(result.runtime_selector)
        if literal is None or literal.raw_text != replacement.written_text:
            continue
        records.append(
            PluginSourceRuntimeWriteMapRecord(
                location_path=replacement.item.location_path,
                source_file_name=file_name,
                source_selector=replacement.selector,
                source_file_hash=replacement.source_file_hash,
                source_text_hash=plugin_source_runtime_hash_text(replacement.candidate.text),
                translation_lines_hash=plugin_source_runtime_hash_lines(
                    replacement.item.translation_lines
                ),
                runtime_file_name=file_name,
                runtime_selector=literal.selector,
                runtime_file_hash=runtime_scan.file_hash,
                runtime_text_hash=plugin_source_runtime_hash_text(literal.text),
                runtime_line=literal.line,
                created_at=created_at,
            )
        )
    return records


def _strict_plugin_source_scan(
    *,
    file_name: str,
    source: str,
    active: bool,
    text_rules: TextRules | None,
) -> PluginSourceFileTextScan:
    """执行写回阶段严格 AST 扫描，并统一转换错误文案。"""
    try:
        return scan_plugin_source_file_text_strict(
            file_name=file_name,
            source=source,
            active=active,
            text_rules=text_rules,
        )
    except ImportError as error:
        raise ValueError(f"插件源码原生 AST 解析器不可用，不能写回源码文件: {file_name}") from error
    except RuntimeError as error:
        if "JS 语法错误" in str(error):
            raise ValueError(f"插件源码 JS 语法检查失败: {file_name}") from error
        raise ValueError(f"插件源码原生 AST 解析器不可用，不能写回源码文件: {file_name}") from error


def _escape_js_string_content(*, text: str, quote: str) -> str:
    """按原字符串引号类型转义译文内容。"""
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if quote == "'":
        return escaped.replace("'", "\\'")
    if quote == "`":
        return escaped.replace("`", "\\`").replace("${", "\\${")
    return escaped.replace('"', '\\"')


__all__ = ["write_plugin_source_text"]
