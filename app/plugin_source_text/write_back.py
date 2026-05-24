"""插件源码文本 AST selector 写回。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.rmmz.placeholder_guard import ensure_no_internal_placeholder_tokens
from app.rmmz.schema import (
    GameData,
    PluginSourceRuntimeProvenanceRecord,
    PluginSourceTextRuleRecord,
    TranslationItem,
)
from app.rmmz.text_rules import TextRules, get_default_text_rules

from .extraction import parse_plugin_source_location_path
from .models import PluginSourceCandidate
from .runtime_mapping import plugin_source_runtime_hash_lines, plugin_source_runtime_hash_text
from .scanner import (
    build_plugin_source_file_hash,
    candidate_selector_for_span,
    PluginSourceFileTextScan,
    PluginSourceStringLiteral,
    scan_plugin_source_file_text,
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


@dataclass(frozen=True, slots=True)
class _PluginSourceRuleIndex:
    """按源码文件索引插件源码审查结果。"""

    translate_selectors_by_file: dict[str, set[str]]
    excluded_selectors_by_file: dict[str, set[str]]
    file_hash_by_file: dict[str, str]


def write_plugin_source_text(
    game_data: GameData,
    items: list[TranslationItem],
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None = None,
    text_rules: TextRules | None = None,
) -> list[PluginSourceRuntimeProvenanceRecord]:
    """把插件源码译文写入可写源码副本，并生成完整当前运行来源映射。"""
    rules = text_rules if text_rules is not None else get_default_text_rules()
    items_by_file: dict[str, list[tuple[str, TranslationItem]]] = {}
    translated_items_by_selector: dict[tuple[str, str], TranslationItem] = {}
    for item in items:
        parsed = parse_plugin_source_location_path(item.location_path)
        if parsed is None:
            continue
        file_name, selector = parsed
        translated_items_by_selector[(file_name, selector)] = item
        ensure_no_internal_placeholder_tokens(
            lines=item.translation_lines,
            context=item.location_path,
            text_rules=rules,
        )
        if len(item.translation_lines) != 1:
            raise ValueError(f"插件源码短文本只能写入 1 行译文: {item.location_path}")
        items_by_file.setdefault(file_name, []).append((selector, item))

    replacements_by_file: dict[str, list[_PluginSourceReplacement]] = {}
    source_scan_by_file: dict[str, PluginSourceFileTextScan] = {}
    runtime_scan_by_file: dict[str, PluginSourceFileTextScan] = {}
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
        source_scan_by_file[file_name] = source_scan
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
        _verify_replacement_results(
            replacement_results=replacement_results,
            runtime_literals=runtime_scan.literals,
        )
        game_data.writable_plugin_source_files[file_name] = content
        runtime_scan_by_file[file_name] = runtime_scan
    return _build_runtime_provenance_records(
        game_data=game_data,
        translated_items_by_selector=translated_items_by_selector,
        plugin_source_rule_records=plugin_source_rule_records or [],
        text_rules=rules,
        source_scan_by_file=source_scan_by_file,
        runtime_scan_by_file=runtime_scan_by_file,
    )


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


def _verify_replacement_results(
    *,
    replacement_results: list[_PluginSourceReplacementResult],
    runtime_literals: tuple[PluginSourceStringLiteral, ...],
) -> None:
    """确认每条替换后的最终 selector 可被当前源码精确定位。"""
    literals_by_selector = {
        literal.selector: literal
        for literal in runtime_literals
    }
    for result in replacement_results:
        replacement = result.replacement
        literal = literals_by_selector.get(result.runtime_selector)
        if literal is None or literal.raw_text != replacement.written_text:
            raise ValueError(f"插件源码写回映射无法验证最终 selector: {replacement.item.location_path}")


def _build_runtime_provenance_records(
    *,
    game_data: GameData,
    translated_items_by_selector: dict[tuple[str, str], TranslationItem],
    plugin_source_rule_records: list[PluginSourceTextRuleRecord],
    text_rules: TextRules,
    source_scan_by_file: dict[str, PluginSourceFileTextScan],
    runtime_scan_by_file: dict[str, PluginSourceFileTextScan],
) -> list[PluginSourceRuntimeProvenanceRecord]:
    """为写回后的所有插件源码字符串生成确定性来源映射。"""
    rule_index = _build_plugin_source_rule_index(
        game_data=game_data,
        plugin_source_rule_records=plugin_source_rule_records,
    )
    created_at = datetime.now().isoformat(timespec="seconds")
    records: list[PluginSourceRuntimeProvenanceRecord] = []
    for file_name, source in sorted(game_data.plugin_source_files.items()):
        runtime_source = game_data.writable_plugin_source_files.get(file_name)
        if runtime_source is None:
            raise ValueError(f"插件源码当前运行来源映射缺少运行文件: {file_name}")
        source_scan = source_scan_by_file.get(file_name)
        if source_scan is None or source_scan.file_hash != build_plugin_source_file_hash(source):
            source_scan = scan_plugin_source_file_text(
                file_name=file_name,
                source=source,
                active=True,
                text_rules=text_rules,
            )
            source_scan_by_file[file_name] = source_scan
        runtime_scan = runtime_scan_by_file.get(file_name)
        if runtime_source == source:
            runtime_literals = source_scan.literals
            runtime_file_hash = source_scan.file_hash
        else:
            runtime_file_hash = build_plugin_source_file_hash(runtime_source)
            if runtime_scan is None or runtime_scan.file_hash != runtime_file_hash:
                runtime_scan = _strict_plugin_source_scan(
                    file_name=file_name,
                    source=runtime_source,
                    active=True,
                    text_rules=None,
                )
                runtime_scan_by_file[file_name] = runtime_scan
            runtime_literals = runtime_scan.literals
        source_literals = source_scan.literals
        if len(source_literals) != len(runtime_literals):
            raise ValueError(f"插件源码当前运行来源映射无法对齐字符串数量: {file_name}")
        source_file_hash = source_scan.file_hash
        candidate_selectors = set(source_scan.candidate_index.by_selector)
        translate_selectors = rule_index.translate_selectors_by_file.get(file_name, set())
        excluded_selectors = rule_index.excluded_selectors_by_file.get(file_name, set())
        for source_literal, runtime_literal in zip(source_literals, runtime_literals, strict=True):
            review_kind = _runtime_review_kind(
                file_name=file_name,
                source_selector=source_literal.selector,
                candidate_selectors=candidate_selectors,
                translate_selectors=translate_selectors,
                excluded_selectors=excluded_selectors,
                translated_items_by_selector=translated_items_by_selector,
            )
            translated_item = translated_items_by_selector.get((file_name, source_literal.selector))
            location_path = (
                f"js/plugins/{file_name}/{source_literal.selector}"
                if review_kind == "translate"
                else ""
            )
            records.append(
                PluginSourceRuntimeProvenanceRecord(
                    source_file_name=file_name,
                    source_selector=source_literal.selector,
                    source_file_hash=source_file_hash,
                    source_text_hash=plugin_source_runtime_hash_text(source_literal.text),
                    review_kind=review_kind,
                    location_path=location_path,
                    translation_lines_hash=(
                        plugin_source_runtime_hash_lines(translated_item.translation_lines)
                        if translated_item is not None
                        else ""
                    ),
                    runtime_file_name=file_name,
                    runtime_selector=runtime_literal.selector,
                    runtime_file_hash=runtime_file_hash,
                    runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                    runtime_line=runtime_literal.line,
                    created_at=created_at,
                )
            )
    return records


def _build_plugin_source_rule_index(
    *,
    game_data: GameData,
    plugin_source_rule_records: list[PluginSourceTextRuleRecord],
) -> _PluginSourceRuleIndex:
    """按文件索引插件源码规则，并确认规则仍匹配当前翻译源源码。"""
    translate_selectors_by_file: dict[str, set[str]] = {}
    excluded_selectors_by_file: dict[str, set[str]] = {}
    file_hash_by_file: dict[str, str] = {}
    for record in plugin_source_rule_records:
        source = game_data.plugin_source_files.get(record.file_name)
        if source is None:
            raise ValueError(f"插件源码规则文件不存在: {record.file_name}")
        source_file_hash = build_plugin_source_file_hash(source)
        if record.file_hash != source_file_hash:
            raise ValueError(f"插件源码规则哈希不匹配: {record.file_name}")
        file_hash_by_file[record.file_name] = record.file_hash
        translate_selectors_by_file.setdefault(record.file_name, set()).update(record.selectors)
        excluded_selectors_by_file.setdefault(record.file_name, set()).update(record.excluded_selectors)
    return _PluginSourceRuleIndex(
        translate_selectors_by_file=translate_selectors_by_file,
        excluded_selectors_by_file=excluded_selectors_by_file,
        file_hash_by_file=file_hash_by_file,
    )


def _runtime_review_kind(
    *,
    file_name: str,
    source_selector: str,
    candidate_selectors: set[str],
    translate_selectors: set[str],
    excluded_selectors: set[str],
    translated_items_by_selector: dict[tuple[str, str], TranslationItem],
) -> str:
    """确定单个源码字符串在当前运行审计中的审查状态。"""
    if source_selector in translate_selectors or (file_name, source_selector) in translated_items_by_selector:
        return "translate"
    if source_selector in excluded_selectors:
        return "excluded"
    if source_selector in candidate_selectors:
        return "unreviewed"
    return "non_source"


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
