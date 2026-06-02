"""
正文翻译校验模块。

负责解析模型返回的 JSON，按批次内临时 ID 映射回翻译条目，并执行漏翻、
占位符和源文残留校验。
"""

import asyncio

from json_repair import repair_json
from pydantic import BaseModel, RootModel

from app.rmmz.schema import ErrorType, TranslationErrorItem, TranslationItem
from app.rmmz.placeholder_mapping import (
    build_original_placeholder_queues,
    consume_original_placeholder,
)
from app.rmmz.text_rules import ControlSequenceSpan, TextRules
from app.source_residual import SourceResidualRuleSet, check_source_residual_for_item
from app.rmmz.text_layout import (
    align_long_text_lines,
    normalize_translated_wrapping_punctuation,
)
from app.translation.text_structure import validate_translation_text_structure

ERR_PARSE_FAILED: ErrorType = "模型返回不可解析"
ERR_MISSING_KEY: ErrorType = "AI漏翻"
ERR_TEXT_STRUCTURE: ErrorType = "文本结构不匹配"
ERR_PLACEHOLDER_MISMATCH: ErrorType = "控制符不匹配"
ERR_SOURCE_RESIDUAL: ErrorType = "源文残留"
ERR_ARRAY_LINE_COUNT: ErrorType = "选项行数不匹配"
ERR_EMPTY_TRANSLATION: ErrorType = "AI漏翻"


class TranslationResponseItem(BaseModel):
    """模型返回的单条对照译文。"""

    id: str | int
    translation_lines: list[str]


class TranslationResponse(RootModel[list[TranslationResponseItem]]):
    """正文翻译返回结果模型。"""


async def verify_translation_batch(
    *,
    ai_result: str,
    items: list[TranslationItem],
    prompt_ids_by_location_path: dict[str, str],
    right_queue: asyncio.Queue[list[TranslationItem] | None],
    error_queue: asyncio.Queue[list[TranslationErrorItem] | None],
    text_rules: TextRules,
    source_residual_rule_set: SourceResidualRuleSet | None = None,
) -> None:
    """解析模型返回并把通过校验/失败条目分别推入队列。"""
    right_items: list[TranslationItem] = []
    error_items: list[TranslationErrorItem] = []

    try:
        response_items = _parse_translation_response_items(ai_result)
        prompt_id_by_location_path = _validate_prompt_id_map(
            items=items,
            prompt_ids_by_location_path=prompt_ids_by_location_path,
        )
        translation_map = _build_translation_line_map(
            response_items=response_items,
            valid_prompt_ids=set(prompt_id_by_location_path.values()),
        )
    except Exception as error:
        for item in items:
            error_items.append(
                TranslationErrorItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    translation_lines=[],
                    error_type=ERR_PARSE_FAILED,
                    error_detail=["模型返回无法解析为 JSON 数组", f"详细错误: {error}"],
                    model_response=ai_result,
                )
            )
        if error_items:
            await error_queue.put(error_items)
        return

    for item in items:
        prompt_id = prompt_id_by_location_path[item.location_path]
        model_translation_lines = translation_map.get(prompt_id)
        if model_translation_lines is None:
            error_items.append(
                TranslationErrorItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    translation_lines=[],
                    error_type=ERR_MISSING_KEY,
                    error_detail=[f"AI漏翻: 未找到键 {prompt_id}"],
                    model_response=ai_result,
                )
            )
            continue
        if _is_empty_translation_lines(model_translation_lines):
            error_items.append(
                TranslationErrorItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    translation_lines=list(model_translation_lines),
                    error_type=ERR_EMPTY_TRANSLATION,
                    error_detail=["AI漏翻: 模型返回空译文"],
                    model_response=ai_result,
                )
            )
            continue
        normalized_model_translation_lines = text_rules.normalize_translation_lines(model_translation_lines)

        if item.item_type == "long_text":
            translation_lines = align_long_text_lines(
                text="\n".join(normalized_model_translation_lines),
                target_lines=len(item.original_lines),
                location_path=item.location_path,
                text_rules=text_rules,
                original_lines=item.original_lines,
            )
        elif item.item_type == "array":
            translation_lines = list(normalized_model_translation_lines)
            translation_lines = normalize_translated_wrapping_punctuation(
                original_lines=item.original_lines,
                translation_lines=translation_lines,
                text_rules=text_rules,
            )
            if len(translation_lines) != len(item.original_lines):
                error_items.append(
                    TranslationErrorItem(
                        location_path=item.location_path,
                        item_type=item.item_type,
                        role=item.role,
                        original_lines=list(item.original_lines),
                        translation_lines=list(translation_lines),
                        error_type=ERR_ARRAY_LINE_COUNT,
                        error_detail=[f"选项行数不匹配: 期望 {len(item.original_lines)} 行, 实际 {len(translation_lines)} 行"],
                        model_response=ai_result,
                    )
                )
                continue
        else:
            translation_lines = list(normalized_model_translation_lines)
            translation_lines = normalize_translated_wrapping_punctuation(
                original_lines=item.original_lines,
                translation_lines=translation_lines,
                text_rules=text_rules,
            )

        item.translation_lines_with_placeholders = _mask_known_translation_controls(
            item=item,
            translation_lines=translation_lines,
            text_rules=text_rules,
        )
        item.translation_lines = []

        try:
            validate_translation_text_structure(
                item=item,
                translation_lines=translation_lines,
                translation_lines_with_placeholders=item.translation_lines_with_placeholders,
                text_rules=text_rules,
            )
        except ValueError as error:
            error_items.append(
                TranslationErrorItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    translation_lines=list(translation_lines),
                    error_type=ERR_TEXT_STRUCTURE,
                    error_detail=str(error).split(";\n"),
                    model_response=ai_result,
                )
            )
            continue

        try:
            item.verify_placeholders(text_rules)
            item.translation_lines = list(item.translation_lines_with_placeholders)
        except ValueError as error:
            error_items.append(
                TranslationErrorItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    translation_lines=list(item.translation_lines_with_placeholders),
                    error_type=ERR_PLACEHOLDER_MISMATCH,
                    error_detail=str(error).split(";\n"),
                    model_response=ai_result,
                )
            )
            continue

        try:
            check_source_residual_for_item(
                item=item,
                text_rules=text_rules,
                rule_set=source_residual_rule_set,
            )
        except ValueError as error:
            error_items.append(
                TranslationErrorItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=list(item.original_lines),
                    translation_lines=list(item.translation_lines),
                    error_type=ERR_SOURCE_RESIDUAL,
                    error_detail=[str(error)],
                    model_response=ai_result,
                )
            )
            continue

        item.restore_placeholders()
        right_items.append(item)

    if right_items:
        await right_queue.put(right_items)
    if error_items:
        await error_queue.put(error_items)


def _parse_translation_response_items(ai_result: str) -> list[TranslationResponseItem]:
    """解析模型响应；严格 JSON 失败时只修复 JSON 语法和外层包裹。"""
    try:
        return TranslationResponse.model_validate_json(ai_result).root
    except Exception as strict_error:
        try:
            repaired_json = repair_json(ai_result, ensure_ascii=False)
            return TranslationResponse.model_validate_json(repaired_json).root
        except Exception as repair_error:
            raise ValueError(
                "严格 JSON 解析失败，修复后仍无法解析为 JSON 数组；"
                + f"严格解析错误: {strict_error}; 修复后解析错误: {repair_error}"
            ) from repair_error


def _build_translation_line_map(
    *,
    response_items: list[TranslationResponseItem],
    valid_prompt_ids: set[str],
) -> dict[str, list[str]]:
    """按本地批次条目收窄模型译文，忽略无关字段和未知 ID。"""
    translation_map: dict[str, list[str]] = {}
    for response_item in response_items:
        response_id = str(response_item.id)
        if response_id not in valid_prompt_ids:
            continue
        if response_id in translation_map:
            raise ValueError(f"模型返回重复 ID: {response_id}")
        translation_map[response_id] = list(response_item.translation_lines)
    return translation_map


def _validate_prompt_id_map(
    *,
    items: list[TranslationItem],
    prompt_ids_by_location_path: dict[str, str],
) -> dict[str, str]:
    """校验当前批次真实内部位置和模型临时 ID 的绑定关系。"""
    item_location_paths = {item.location_path for item in items}
    extra_location_paths = sorted(set(prompt_ids_by_location_path).difference(item_location_paths))
    if extra_location_paths:
        joined_paths = "、".join(extra_location_paths)
        raise ValueError(f"批次模型临时 ID 包含未知文本内部位置: {joined_paths}")

    prompt_id_by_location_path: dict[str, str] = {}
    seen_prompt_ids: set[str] = set()
    for item in items:
        prompt_id = prompt_ids_by_location_path.get(item.location_path)
        if prompt_id is None:
            raise ValueError(f"批次缺少模型临时 ID: {item.location_path}")
        if not prompt_id:
            raise ValueError(f"批次模型临时 ID 为空: {item.location_path}")
        if prompt_id in seen_prompt_ids:
            raise ValueError(f"批次模型临时 ID 重复: {prompt_id}")
        seen_prompt_ids.add(prompt_id)
        prompt_id_by_location_path[item.location_path] = prompt_id
    return prompt_id_by_location_path


def _is_empty_translation_lines(translation_lines: list[str]) -> bool:
    """判断模型是否返回了空数组或全空白译文。"""
    return not translation_lines or not any(line.strip() for line in translation_lines)


def _mask_known_translation_controls(
    *,
    item: TranslationItem,
    translation_lines: list[str],
    text_rules: TextRules,
) -> list[str]:
    """把模型返回的原始控制符修回本条原文对应的占位符。"""
    placeholder_queues = build_original_placeholder_queues(
        item=item,
        text_rules=text_rules,
    )
    known_originals = set(placeholder_queues)

    def replacer(span: ControlSequenceSpan) -> str:
        """只修回原文已有的控制符，未知控制符继续交给后续校验。"""
        placeholder = consume_original_placeholder(
            queues=placeholder_queues,
            original=span.original,
        )
        if placeholder is not None:
            return placeholder
        if span.original in known_originals:
            return "[CUSTOM_UNEXPECTED_1]"
        return span.original

    return [
        text_rules.replace_rm_control_sequences(line, replacer)
        for line in translation_lines
    ]


__all__: list[str] = ["verify_translation_batch"]
