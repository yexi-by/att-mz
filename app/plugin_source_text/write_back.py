"""插件源码文本 AST selector 写回。"""

from __future__ import annotations

from app.native_javascript_ast import parse_native_javascript_string_spans
from app.rmmz.placeholder_guard import ensure_no_internal_placeholder_tokens
from app.rmmz.schema import GameData, TranslationItem
from app.rmmz.text_rules import TextRules, get_default_text_rules

from .extraction import parse_plugin_source_location_path
from .scanner import find_candidate_by_selector


def write_plugin_source_text(
    game_data: GameData,
    items: list[TranslationItem],
    text_rules: TextRules | None = None,
) -> None:
    """把插件源码译文写入可写源码副本。"""
    rules = text_rules
    replacements_by_file: dict[str, list[tuple[int, int, str]]] = {}
    for item in items:
        parsed = parse_plugin_source_location_path(item.location_path)
        if parsed is None:
            continue
        file_name, selector = parsed
        if rules is not None:
            ensure_no_internal_placeholder_tokens(
                lines=item.translation_lines,
                context=item.location_path,
                text_rules=rules,
            )
        else:
            ensure_no_internal_placeholder_tokens(
                lines=item.translation_lines,
                context=item.location_path,
            )
        if len(item.translation_lines) != 1:
            raise ValueError(f"插件源码短文本只能写入 1 行译文: {item.location_path}")
        source = game_data.writable_plugin_source_files.get(file_name)
        if source is None:
            raise ValueError(f"插件源码文件不存在: {file_name}")
        _ensure_javascript_ast_valid(source=source, file_name=file_name)
        candidate = find_candidate_by_selector(
            source=source,
            file_name=file_name,
            selector=selector,
            active=True,
            text_rules=rules if rules is not None else get_default_text_rules(),
        )
        if candidate is None:
            raise ValueError(f"插件源码 selector 已失效: {item.location_path}")
        if item.original_lines != [candidate.text]:
            raise ValueError(f"插件源码原文已变化，请重新导出 AST 地图: {item.location_path}")
        written_text = _escape_js_string_content(
            text=item.translation_lines[0].strip(),
            quote=candidate.quote,
        )
        replacements_by_file.setdefault(file_name, []).append(
            (
                candidate.content_start_index,
                candidate.content_end_index,
                written_text,
            )
        )

    for file_name, replacements in replacements_by_file.items():
        content = game_data.writable_plugin_source_files[file_name]
        for start_index, end_index, written_text in sorted(replacements, key=lambda item: item[0], reverse=True):
            content = f"{content[:start_index]}{written_text}{content[end_index:]}"
        _ensure_javascript_ast_valid(source=content, file_name=file_name)
        game_data.writable_plugin_source_files[file_name] = content


def _ensure_javascript_ast_valid(*, source: str, file_name: str) -> None:
    """确认原生 AST 可用且源码可解析。"""
    try:
        scan = parse_native_javascript_string_spans(source)
    except (ImportError, RuntimeError) as error:
        raise ValueError(f"插件源码原生 AST 解析器不可用，不能写回源码文件: {file_name}") from error
    if scan.has_error:
        raise ValueError(f"插件源码 JS 语法检查失败: {file_name}")


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
