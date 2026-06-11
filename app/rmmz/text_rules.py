"""
文本规则服务模块。

本模块把 RPG Maker 标准控制符保护、自定义正则占位符、源文残留检查和提取阶段
文本正规化统一收敛到 `TextRules`。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import NoReturn

from app.config.schemas import TextRulesSetting
from app.rmmz.control_codes import (
    ALL_PLACEHOLDER_PATTERN,
    ControlSequenceSpan,
    CustomPlaceholderRule,
    RawControlSequenceCandidate,
    StructuredPlaceholderRule,
    format_placeholder_template,
    iter_raw_control_sequence_candidates,
    iter_standard_control_spans,
    select_non_overlapping_spans,
)
from app.rmmz.json_types import (
    JsonArray,
    JsonObject,
    JsonPrimitive,
    JsonValue,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
    ensure_json_string_list,
)


@dataclass(frozen=True, slots=True)
class TextRules:
    """运行时文本规则集合。"""

    setting: TextRulesSetting
    custom_placeholder_rules: tuple[CustomPlaceholderRule, ...]
    structured_placeholder_rules: tuple[StructuredPlaceholderRule, ...]
    placeholder_token_pattern: re.Pattern[str]

    @classmethod
    def from_setting(
        cls,
        setting: TextRulesSetting,
        custom_placeholder_rules: tuple[CustomPlaceholderRule, ...] = (),
        structured_placeholder_rules: tuple[StructuredPlaceholderRule, ...] = (),
    ) -> "TextRules":
        """根据配置构建文本规则服务。"""
        return cls(
            setting=setting,
            custom_placeholder_rules=custom_placeholder_rules,
            structured_placeholder_rules=structured_placeholder_rules,
            placeholder_token_pattern=ALL_PLACEHOLDER_PATTERN,
        )

    def normalize_extraction_text(self, text: str) -> str:
        """按配置清理提取阶段的包裹标点并去除首尾空白。"""
        normalized_text = text.strip()
        for left, right in self.setting.strip_wrapping_punctuation_pairs:
            if normalized_text.startswith(left) and normalized_text.endswith(right):
                normalized_text = normalized_text[len(left) : len(normalized_text) - len(right)]
        return normalized_text.strip()

    def normalize_translation_lines(self, lines: list[str]) -> list[str]:
        """清理模型或人工译文行的意外首尾空白，保留行内空白。"""
        return [line.strip() for line in lines]

    def replace_rm_control_sequences(
        self,
        text: str,
        replacer: Callable[[ControlSequenceSpan], str],
    ) -> str:
        """按顺序替换文本中的 RPG Maker 控制符。"""
        spans = self.iter_control_sequence_spans(text)
        if not spans:
            return text

        parts: list[str] = []
        last_end = 0
        for span in spans:
            parts.append(text[last_end:span.start_index])
            parts.append(replacer(span))
            last_end = span.end_index
        parts.append(text[last_end:])
        return "".join(parts)

    def strip_rm_control_sequences(self, text: str) -> str:
        """从文本中剥离 RPG Maker 控制符。"""
        return self.replace_rm_control_sequences(text, lambda _span: "")

    def is_source_text_excluded(self, text: str) -> bool:
        """判断文本是否被固定源文排除 profile 过滤。"""
        if self.setting.source_text_exclusion_profile == "english_protocol_noise":
            return self._is_english_protocol_noise_text(text)
        return False

    def iter_control_sequence_spans(self, text: str) -> list[ControlSequenceSpan]:
        """顺序扫描一行文本，识别标准控制符和自定义保护片段。"""
        standard_spans = _filter_standard_prefix_conflicts(
            text=text,
            spans=iter_standard_control_spans(text),
        )
        custom_spans = self._iter_custom_placeholder_spans(text)
        structured_result = self._iter_structured_placeholder_spans(text)
        self._validate_structured_placeholder_conflicts(
            base_spans=[*standard_spans, *custom_spans],
            structured_spans=structured_result.spans,
            translatable_ranges=structured_result.translatable_ranges,
        )
        spans = [*standard_spans, *custom_spans]
        spans.extend(structured_result.spans)
        return select_non_overlapping_spans(spans)

    def format_custom_placeholder(self, *, template: str, index: int) -> str:
        """按外部 JSON 模板格式化自定义占位符。"""
        return format_placeholder_template(
            template=template,
            code="",
            param="",
            index=index,
        )

    def count_line_width_chars(self, text: str) -> int:
        """按配置统计长文本切行时计入长度的字符数量。"""
        _ = text
        _raise_runtime_config_regex_required("长文本宽度统计")

    def should_translate_source_text(self, text: str) -> bool:
        """判断原文是否包含需要交给模型处理的源语言字符。"""
        _ = text
        _raise_runtime_config_regex_required("源文可翻译性判断")

    def should_translate_source_lines(self, lines: list[str]) -> bool:
        """判断多行原文是否至少包含一处需要翻译的源语言字符。"""
        _ = lines
        _raise_runtime_config_regex_required("多行源文可翻译性判断")

    def is_line_width_counted_char(self, char: str) -> bool:
        """判断单个字符是否计入长文本切行长度。"""
        _ = char
        _raise_runtime_config_regex_required("长文本宽度字符判断")

    def collect_placeholder_tokens(self, lines: list[str]) -> set[str]:
        """收集文本行中的翻译占位符集合。"""
        placeholders: set[str] = set()
        for line in lines:
            placeholders.update(self.placeholder_token_pattern.findall(line))
        return placeholders

    def collect_unprotected_control_sequences(self, lines: list[str]) -> dict[str, int]:
        """统计未被标准或自定义规则覆盖的疑似控制符片段。"""
        counts: dict[str, int] = {}
        for line in lines:
            for candidate in self.iter_unprotected_control_sequence_candidates(line):
                counts[candidate.original] = counts.get(candidate.original, 0) + 1
        return counts

    def iter_unprotected_control_sequence_candidates(
        self,
        text: str,
    ) -> list[RawControlSequenceCandidate]:
        """找出一行文本中仍裸露的反斜杠控制符候选。"""
        protected_spans = self.iter_control_sequence_spans(text)
        candidates: list[RawControlSequenceCandidate] = []
        for candidate in iter_raw_control_sequence_candidates(text):
            if _is_covered_by_control_span(candidate, protected_spans):
                continue
            candidates.append(candidate)
        return candidates

    def _iter_custom_placeholder_spans(self, text: str) -> list[ControlSequenceSpan]:
        """扫描外部 JSON 中定义的自定义占位符规则。"""
        spans: list[ControlSequenceSpan] = []
        for rule in self.custom_placeholder_rules:
            for match in rule.pattern.finditer(text):
                spans.append(
                    ControlSequenceSpan(
                        start_index=match.start(),
                        end_index=match.end(),
                        original=match.group(0),
                        source="custom",
                        placeholder=None,
                        custom_template=rule.placeholder_template,
                        priority=1,
                    )
                )
        return spans

    def _iter_structured_placeholder_spans(self, text: str) -> "_StructuredPlaceholderScanResult":
        """扫描外部 JSON 中定义的结构化占位符规则。"""
        spans: list[ControlSequenceSpan] = []
        translatable_ranges: list[_ProtectedRange] = []
        for rule in self.structured_placeholder_rules:
            for match in rule.pattern.finditer(text):
                translatable_range = _match_group_range(
                    match=match,
                    group_name=rule.translatable_group,
                    rule_name=rule.rule_name,
                )
                translatable_ranges.append(translatable_range)
                match_key = f"structured:{rule.rule_name}:{match.start()}:{match.end()}:{match.group(0)}"
                group_ranges: list[_ProtectedRange] = []
                for group_name, placeholder_template in rule.protected_groups.items():
                    protected_range = _match_group_range(
                        match=match,
                        group_name=group_name,
                        rule_name=rule.rule_name,
                    )
                    if protected_range.start == protected_range.end:
                        raise ValueError(f"结构化占位符规则 {rule.rule_name} 的保护分组 {group_name} 命中了空文本")
                    if _ranges_overlap(protected_range, translatable_range):
                        raise ValueError(
                            f"结构化占位符规则 {rule.rule_name} 的保护分组 {group_name} 覆盖了可翻译文本分组"
                        )
                    for existing_range in group_ranges:
                        if _ranges_overlap(protected_range, existing_range):
                            raise ValueError(
                                f"结构化占位符规则 {rule.rule_name} 的保护分组互相重叠"
                            )
                    group_ranges.append(protected_range)
                    spans.append(
                        ControlSequenceSpan(
                            start_index=protected_range.start,
                            end_index=protected_range.end,
                            original=text[protected_range.start:protected_range.end],
                            source="structured",
                            placeholder=None,
                            custom_template=placeholder_template,
                            priority=2,
                            custom_index_key=match_key,
                        )
                    )
        return _StructuredPlaceholderScanResult(
            spans=spans,
            translatable_ranges=translatable_ranges,
        )

    def _validate_structured_placeholder_conflicts(
        self,
        *,
        base_spans: list[ControlSequenceSpan],
        structured_spans: list[ControlSequenceSpan],
        translatable_ranges: list["_ProtectedRange"],
    ) -> None:
        """校验结构化规则与普通保护规则没有抢占同一段文本。"""
        for structured_span in structured_spans:
            structured_range = _ProtectedRange(
                start=structured_span.start_index,
                end=structured_span.end_index,
            )
            for base_span in base_spans:
                base_range = _ProtectedRange(start=base_span.start_index, end=base_span.end_index)
                if _ranges_overlap(structured_range, base_range):
                    raise ValueError(
                        f"结构化占位符保护片段与已有控制符规则重叠: {structured_span.original} / {base_span.original}"
                    )
        for index, left_span in enumerate(structured_spans):
            left_range = _ProtectedRange(start=left_span.start_index, end=left_span.end_index)
            for right_span in structured_spans[index + 1:]:
                right_range = _ProtectedRange(start=right_span.start_index, end=right_span.end_index)
                if _ranges_overlap(left_range, right_range):
                    raise ValueError(
                        f"结构化占位符保护片段互相重叠: {left_span.original} / {right_span.original}"
                    )
        for translatable_range in translatable_ranges:
            for span in [*base_spans, *structured_spans]:
                span_range = _ProtectedRange(start=span.start_index, end=span.end_index)
                if _ranges_overlap(translatable_range, span_range):
                    if span.source == "standard":
                        continue
                    raise ValueError(
                        f"结构化占位符可翻译文本分组被保护规则覆盖: {span.original}"
                    )

    def check_source_residual(
        self,
        translation_lines: list[str],
        *,
        allowed_terms: Sequence[str] = (),
        original_lines: Sequence[str] | None = None,
    ) -> None:
        """检查译文中是否残留当前源语言文本。"""
        _ = (translation_lines, allowed_terms, original_lines)
        _raise_runtime_config_regex_required("源文残留检查")

    def _check_english_source_copy_residual(
        self,
        *,
        original_lines: Sequence[str],
        translation_lines: Sequence[str],
    ) -> None:
        """检查英文译文是否连续复制了当前条目的大段原文。"""
        original_text = "\n".join(
            self._strip_non_content_for_residual(line)
            for line in original_lines
        )
        original_tokens = self._collect_english_residual_tokens(original_text)
        if not original_tokens:
            return
        original_token_values = [token.normalized for token in original_tokens]
        for index, line in enumerate(translation_lines, start=1):
            cleaned_line = self._strip_non_content_for_residual(line)
            translation_tokens = self._collect_english_residual_tokens(cleaned_line)
            copied_segments = self._find_english_source_copy_segments(
                original_tokens=original_token_values,
                translation_tokens=translation_tokens,
            )
            if copied_segments:
                raise ValueError(
                    f"发现{self.setting.source_residual_label}残留(第 {index} 行): {copied_segments}"
                )

    def _check_english_residual_without_original(
        self,
        *,
        translation_lines: Sequence[str],
    ) -> None:
        """缺少当前原文时，按连续英文长段审计当前运行文本。"""
        for index, line in enumerate(translation_lines, start=1):
            cleaned_line = self._strip_non_content_for_residual(line)
            translation_tokens = self._collect_english_residual_tokens(cleaned_line)
            residual_segments = self._find_english_long_residual_segments(
                cleaned_line=cleaned_line,
                translation_tokens=translation_tokens,
            )
            if residual_segments:
                raise ValueError(
                    f"发现{self.setting.source_residual_label}残留(第 {index} 行): {residual_segments}"
                )

    def _collect_english_residual_tokens(self, text: str) -> list["_ResidualToken"]:
        """按残留正则收集拉丁 token，不对 token 语义作任何词表判断。"""
        _ = text
        _raise_runtime_config_regex_required("英文残留 token 收集")

    def _find_english_long_residual_segments(
        self,
        *,
        cleaned_line: str,
        translation_tokens: list["_ResidualToken"],
    ) -> list[str]:
        """在没有原文对照时，找出连续英文长段。"""
        residual_segments: list[str] = []
        current_run: list[_ResidualToken] = []
        previous_token: _ResidualToken | None = None
        for token in translation_tokens:
            if (
                previous_token is not None
                and _english_token_gap_breaks_run(
                    cleaned_line[previous_token.end_index:token.start_index]
                )
            ):
                _append_english_run_if_residual(
                    residual_segments=residual_segments,
                    tokens=current_run,
                    min_words=self.setting.english_source_copy_min_words,
                    min_letters=self.setting.english_source_copy_min_letters,
                )
                current_run = []
            current_run.append(token)
            previous_token = token
        _append_english_run_if_residual(
            residual_segments=residual_segments,
            tokens=current_run,
            min_words=self.setting.english_source_copy_min_words,
            min_letters=self.setting.english_source_copy_min_letters,
        )
        return residual_segments

    def _find_english_source_copy_segments(
        self,
        *,
        original_tokens: list[str],
        translation_tokens: list["_ResidualToken"],
    ) -> list[str]:
        """找出译文里连续复制当前原文的英文 token 片段。"""
        copied_segments: list[str] = []
        start = 0
        while start < len(translation_tokens):
            best_end = 0
            for end in range(start + self.setting.english_source_copy_min_words, len(translation_tokens) + 1):
                candidate_tokens = translation_tokens[start:end]
                letter_count = sum(_ascii_letter_count(token.text) for token in candidate_tokens)
                if letter_count < self.setting.english_source_copy_min_letters:
                    continue
                candidate_values = [token.normalized for token in candidate_tokens]
                if _contains_token_sequence(original_tokens, candidate_values):
                    best_end = end
            if best_end:
                copied_segments.append(" ".join(token.text for token in translation_tokens[start:best_end]))
                start = best_end
                continue
            start += 1
        return copied_segments

    def _strip_non_content_for_residual(self, text: str) -> str:
        """在残留校验前剥离控制符和占位符噪音。"""
        _ = text
        _raise_runtime_config_regex_required("源文残留噪音剥离")

    def _has_non_source_content(self, text: str) -> bool:
        """判断残留检查文本中是否存在源语言片段之外的正文内容。"""
        _ = text
        _raise_runtime_config_regex_required("源文残留正文判断")

    def mask_source_residual_terms(
        self,
        lines: list[str],
        allowed_terms: Sequence[str],
    ) -> list[str]:
        """遮蔽允许保留的源语言片段，供源文残留检测复用。"""
        allowed_terms = [term for term in allowed_terms if term]
        if not allowed_terms:
            return list(lines)
        sorted_terms = sorted(allowed_terms, key=len, reverse=True)
        masked_lines: list[str] = []
        for line in lines:
            masked_line = line
            for term in sorted_terms:
                if self.setting.source_residual_terms_ignore_case:
                    masked_line = re.sub(
                        rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
                        " ",
                        masked_line,
                        flags=re.IGNORECASE,
                    )
                else:
                    masked_line = masked_line.replace(term, " ")
            masked_lines.append(masked_line)
        return masked_lines

    def _is_english_protocol_noise_text(self, text: str) -> bool:
        """排除英文游戏中常见的资源路径、脚本片段和机器协议值。"""
        stripped_text = self.strip_rm_control_sequences(text).strip()
        if not stripped_text:
            return True
        lowered_text = stripped_text.lower()
        if lowered_text in {
            "true",
            "false",
            "null",
            "undefined",
            "gamefont",
        }:
            return True
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", stripped_text):
            return True
        if re.search(r"(?:^|[\\/])(?:img|audio|fonts|icon|js|data)[\\/]", lowered_text):
            return True
        if re.search(r"\.(?:png|jpe?g|webp|gif|ogg|m4a|mp3|wav|webm|json|js|css|html|ttf|otf|woff2?|rpgmvp|rpgmvo|rpgmvm)$", lowered_text):
            return True
        if self._looks_like_english_script_punctuation(stripped_text):
            return True
        if re.search(r"\bthis\s*(?:\.[A-Za-z_$]|\[)", stripped_text, flags=re.IGNORECASE):
            return True
        if re.search(r"\b(?:console|math)\s*\.", stripped_text, flags=re.IGNORECASE):
            return True
        if re.search(r"\b(?:var|let|const)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=", stripped_text):
            return True
        if re.search(r"\bfunction(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\(", stripped_text):
            return True
        if re.search(r"\breturn\b.*(?:[;=<>+\-*/]|\b(?:true|false|null|undefined)\b)", stripped_text):
            return True
        if re.search(r"\b[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\s*\(", stripped_text):
            return True
        if re.search(r"[+\-*/<>=]=?|&&|\|\|", stripped_text) and len(re.findall(r"[A-Za-z]{2,}", stripped_text)) < 2:
            return True
        if re.search(r"[/\\]", stripped_text) and re.fullmatch(r"[A-Za-z0-9_./\\:-]+", stripped_text):
            return True
        if re.fullmatch(r"[a-z][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*", stripped_text):
            return True
        return False

    def _looks_like_english_script_punctuation(self, text: str) -> bool:
        """只在符号呈现明确脚本结构时排除，避免误伤自然英文说明。"""
        if re.search(r"\$\{[^}]+\}", text):
            return True
        if re.search(r"\$[A-Za-z_$][A-Za-z0-9_$]*(?:\s*(?:\.|\[|\())", text):
            return True
        if re.search(
            r"(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*(?:[{(]|[A-Za-z_$][A-Za-z0-9_$]*\s*[+*/<>=])",
            text,
        ):
            return True
        if re.search(
            r"\{[^{}]*(?:\b(?:var|let|const|return|function|if|for|while)\b|[A-Za-z_$][A-Za-z0-9_$]*\s*:|[A-Za-z_$][A-Za-z0-9_$]*\s*=|;)[^{}]*\}",
            text,
        ):
            return True
        if re.search(
            r"(?:\b(?:return|var|let|const|throw|break|continue)\b|[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[[^\]]+\])*\s*(?:[-+*/]?=)|\b[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+\s*\([^)]*\))[^.;!?]*;",
            text,
        ):
            return True
        return False


@cache
def get_default_text_rules() -> TextRules:
    """返回配置缺省值构建的文本规则。"""
    return TextRules.from_setting(TextRulesSetting())


def _filter_standard_prefix_conflicts(
    *,
    text: str,
    spans: list[ControlSequenceSpan],
) -> list[ControlSequenceSpan]:
    """移除只覆盖更长疑似控制符前缀的标准片段。"""
    candidates = iter_raw_control_sequence_candidates(text)
    filtered_spans: list[ControlSequenceSpan] = []
    for span in spans:
        if span.source != "standard":
            filtered_spans.append(span)
            continue
        if _is_standard_prefix_of_longer_candidate(span, candidates):
            continue
        filtered_spans.append(span)
    return filtered_spans


def _is_standard_prefix_of_longer_candidate(
    span: ControlSequenceSpan,
    candidates: list[RawControlSequenceCandidate],
) -> bool:
    """判断标准片段是否只是某个更长候选的前缀。"""
    return any(
        candidate.start_index == span.start_index and candidate.end_index > span.end_index
        for candidate in candidates
    )


def _is_covered_by_control_span(
    candidate: RawControlSequenceCandidate,
    spans: list[ControlSequenceSpan],
) -> bool:
    """判断原始候选是否已经由占位符规则覆盖。"""
    for span in spans:
        if span.source == "standard":
            if candidate.start_index >= span.start_index and candidate.end_index <= span.end_index:
                return True
            continue
        if candidate.start_index < span.end_index and candidate.end_index > span.start_index:
            return True
    return False


@dataclass(frozen=True, slots=True)
class _ProtectedRange:
    """记录单个受保护或可翻译文本范围。"""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _ResidualToken:
    """源文残留检测中的拉丁 token。"""

    text: str
    normalized: str
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class _StructuredPlaceholderScanResult:
    """结构化占位符扫描结果。"""

    spans: list[ControlSequenceSpan]
    translatable_ranges: list[_ProtectedRange]


def _match_group_range(
    *,
    match: re.Match[str],
    group_name: str,
    rule_name: str,
) -> _ProtectedRange:
    """读取命名分组范围并把未命中情况转成业务错误。"""
    try:
        start, end = match.span(group_name)
    except IndexError as error:
        raise ValueError(f"结构化占位符规则 {rule_name} 缺少命名分组: {group_name}") from error
    if start < 0 or end < 0:
        raise ValueError(f"结构化占位符规则 {rule_name} 的命名分组未命中: {group_name}")
    return _ProtectedRange(start=start, end=end)


def _ranges_overlap(left: _ProtectedRange, right: _ProtectedRange) -> bool:
    """判断两个半开范围是否重叠。"""
    return left.start < right.end and left.end > right.start


def _ascii_letter_count(text: str) -> int:
    """统计 ASCII 拉丁字母数量。"""
    return sum(1 for char in text if char.isascii() and char.isalpha())


def _english_token_gap_breaks_run(gap: str) -> bool:
    """判断两个英文 token 之间是否已被非英文正文打断。"""
    for char in gap:
        if char.isspace():
            continue
        if char.isascii() and not char.isalnum():
            continue
        return True
    return False


def _append_english_run_if_residual(
    *,
    residual_segments: list[str],
    tokens: list[_ResidualToken],
    min_words: int,
    min_letters: int,
) -> None:
    """把达到阈值的连续英文 token 片段加入残留列表。"""
    if len(tokens) < min_words:
        return
    letter_count = sum(_ascii_letter_count(token.text) for token in tokens)
    if letter_count < min_letters:
        return
    residual_segments.append(" ".join(token.text for token in tokens))


def _contains_token_sequence(source_tokens: list[str], candidate_tokens: list[str]) -> bool:
    """判断候选 token 序列是否连续出现在源 token 序列中。"""
    if not candidate_tokens or len(candidate_tokens) > len(source_tokens):
        return False
    candidate_length = len(candidate_tokens)
    for start in range(0, len(source_tokens) - candidate_length + 1):
        if source_tokens[start:start + candidate_length] == candidate_tokens:
            return True
    return False


def _raise_runtime_config_regex_required(operation: str) -> NoReturn:
    raise RuntimeError(f"{operation}需要配置正则语义；TextRules 不再执行配置正则语义，请改用 Rust rule_runtime")


__all__: list[str] = [
    "ControlSequenceSpan",
    "CustomPlaceholderRule",
    "JsonArray",
    "JsonObject",
    "JsonPrimitive",
    "JsonValue",
    "StructuredPlaceholderRule",
    "TextRules",
    "coerce_json_value",
    "ensure_json_array",
    "ensure_json_object",
    "ensure_json_string_list",
    "get_default_text_rules",
]
