"""Text Fact Contract v2 的翻译条目与质量检查转换。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Literal

from app.persistence.records import TextFactV2ReadFilter, TextFactV2Record, TextIndexItemRecord
from app.persistence.sql import TEXT_FACT_SCHEMA_VERSION, TEXT_FACTS_V2_TABLE_NAME
from app.rmmz.schema import TranslationData, TranslationItem
from app.rmmz.text_rules import JsonObject
from app.text_fact_core import (
    TEXT_FACT_SELECT_COLUMNS,
    assert_current_scope_fact_schema,
    chunks,
    display_name_from_index_record,
    item_type_from_text_fact,
    read_current_text_fact_scope_v2,
    short_text_sample,
    terminology_owner_terms_from_index_record,
    text_fact_contract_error,
    text_fact_lines,
    text_fact_v2_from_row,
)

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


async def read_text_fact_quality_items_for_translations(
    session: TargetGameSession,
    translated_items: Sequence[TranslationItem],
    *,
    source_text: Literal["translatable", "visible", "raw"] = "translatable",
) -> list[TranslationItem]:
    """把已保存译文的源文替换为 v2 指定正文，供质量检查使用。"""
    if not translated_items:
        return []
    if source_text not in {"translatable", "visible", "raw"}:
        raise ValueError("source_text 必须是 translatable、visible 或 raw")
    fact_ids = [item.fact_id for item in translated_items if item.fact_id]
    if len(fact_ids) != len(translated_items):
        missing_identity_paths = sorted(
            item.location_path for item in translated_items if not item.fact_id
        )
        samples = "、".join(missing_identity_paths[:5])
        suffix = f" 等 {len(missing_identity_paths)} 条" if len(missing_identity_paths) > 5 else ""
        raise text_fact_contract_error(
            f"已保存译文缺少 v2 fact identity，不能重建质量检查源文: {samples}{suffix}"
        )
    facts = await _read_current_text_facts_by_fact_ids_for_quality(
        session=session,
        fact_ids=fact_ids,
    )
    facts_by_id = {fact.fact_id: fact for fact in facts}
    missing_fact_ids = sorted(set(fact_ids) - set(facts_by_id))
    if missing_fact_ids:
        samples = "、".join(missing_fact_ids[:5])
        suffix = f" 等 {len(missing_fact_ids)} 条" if len(missing_fact_ids) > 5 else ""
        raise text_fact_contract_error(
            f"已保存译文缺少当前 v2 文本事实，不能重建质量检查源文: {samples}{suffix}"
        )
    quality_items: list[TranslationItem] = []
    for item in translated_items:
        fact = facts_by_id[item.fact_id or ""]
        if (
            item.source_fact_raw_hash != fact.raw_hash
            or item.source_fact_translatable_hash != fact.translatable_hash
        ):
            raise text_fact_contract_error(
                "已保存译文不再匹配当前 v2 文本事实身份，不能重建质量检查源文: "
                + f"{item.location_path}"
            )
        cloned_item = item.model_copy(deep=True)
        item_type = item_type_from_text_fact(fact)
        cloned_item.item_type = item_type
        cloned_item.role = fact.role or None
        raw_lines = text_fact_lines(fact.raw_text, item_type=item_type)
        visible_lines = text_fact_lines(fact.visible_text, item_type=item_type)
        translatable_lines = text_fact_lines(fact.translatable_text, item_type=item_type)
        if source_text == "raw":
            cloned_item.original_lines = raw_lines
        elif source_text == "visible":
            cloned_item.original_lines = visible_lines
        else:
            cloned_item.original_lines = translatable_lines
        quality_items.append(cloned_item)
    return quality_items


async def read_text_fact_sample_details_by_paths_v2(
    session: TargetGameSession,
    location_paths: Sequence[str],
    *,
    max_chars: int = 120,
) -> dict[str, JsonObject]:
    """读取当前 v2 facts 的 raw/visible/translatable 短样本。"""
    if max_chars <= 0:
        raise ValueError("max_chars 必须是正整数")
    facts = await _read_current_text_facts_by_paths_for_quality(
        session=session,
        location_paths=location_paths,
    )
    return {
        fact.location_path: {
            "raw_text_sample": short_text_sample(fact.raw_text, max_chars=max_chars),
            "visible_text_sample": short_text_sample(fact.visible_text, max_chars=max_chars),
            "translatable_text_sample": short_text_sample(
                fact.translatable_text,
                max_chars=max_chars,
            ),
        }
        for fact in facts
    }


def text_fact_records_to_translation_data_map(
    facts: Iterable[TextFactV2Record],
    *,
    index_records: Sequence[TextIndexItemRecord] = (),
) -> dict[str, TranslationData]:
    """把 v2 文本事实按来源文件转换成模型翻译输入。"""
    index_by_path = {record.location_path: record for record in index_records}
    translation_data_map: dict[str, TranslationData] = {}
    for fact in sorted(facts, key=lambda item: (item.domain, item.location_path, item.fact_id)):
        index_record = index_by_path.get(fact.location_path)
        display_name = display_name_from_index_record(index_record)
        translation_data = translation_data_map.get(fact.source_file)
        if translation_data is None:
            translation_data = TranslationData(display_name=display_name, translation_items=[])
            translation_data_map[fact.source_file] = translation_data
        elif display_name is not None:
            if translation_data.display_name is None:
                translation_data.display_name = display_name
            elif translation_data.display_name != display_name:
                raise RuntimeError(f"v2 文本事实来源文件 {fact.source_file} 的地图名不一致")
        translation_data.translation_items.append(
            text_fact_record_to_translation_item(fact, index_record=index_record)
        )
    return translation_data_map


def text_fact_record_to_translation_item(
    fact: TextFactV2Record,
    *,
    index_record: TextIndexItemRecord | None = None,
) -> TranslationItem:
    """把单条 v2 fact 转成既有 `TranslationItem`，正文使用 translatable_text。"""
    _validate_text_fact_record(fact)
    item_type = item_type_from_text_fact(fact)
    source_line_paths = (
        list(index_record.source_line_paths)
        if index_record is not None
        else [fact.location_path]
    )
    terminology_owner_terms = (
        terminology_owner_terms_from_index_record(index_record)
        if index_record is not None
        else []
    )
    return TranslationItem(
        fact_id=fact.fact_id,
        location_path=fact.location_path,
        item_type=item_type,
        role=fact.role or None,
        original_lines=text_fact_lines(fact.translatable_text, item_type=item_type),
        source_line_paths=source_line_paths,
        source_fact_raw_hash=fact.raw_hash,
        source_fact_translatable_hash=fact.translatable_hash,
        terminology_owner_terms=terminology_owner_terms,
        translation_dedupe_key=f"text_fact_v2:{fact.translatable_hash}",
    )


def text_fact_record_to_quality_item(
    fact: TextFactV2Record,
    *,
    index_record: TextIndexItemRecord | None = None,
) -> TranslationItem:
    """把单条 v2 fact 转成质量检查输入，源文使用玩家可见文本。"""
    item = text_fact_record_to_translation_item(fact, index_record=index_record)
    item.original_lines = text_fact_lines(fact.visible_text, item_type=item.item_type)
    return item


def _validate_text_fact_record(fact: TextFactV2Record) -> None:
    """校验 adapter 消费的单条 v2 fact。"""
    if fact.schema_version != TEXT_FACT_SCHEMA_VERSION:
        raise text_fact_contract_error(
            "text fact v2 schema_version 不受支持: "
            + f"数据库是 {fact.schema_version}，当前工具支持 {TEXT_FACT_SCHEMA_VERSION}"
        )
    if not fact.scope_key:
        raise text_fact_contract_error("text fact v2 缺少 scope_key")
    if not fact.location_path:
        raise text_fact_contract_error("text fact v2 缺少 location_path")


async def _read_current_text_facts_by_paths_for_quality(
    *,
    session: TargetGameSession,
    location_paths: Sequence[str],
) -> list[TextFactV2Record]:
    """按路径读取当前 scope 内供质量报告使用的 v2 facts。"""
    unique_paths = sorted(set(location_paths))
    if not unique_paths:
        return []
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await session.read_text_facts_v2(
        TextFactV2ReadFilter(scope_key=scope.scope_key, location_paths=unique_paths)
    )


async def _read_current_text_facts_by_fact_ids_for_quality(
    *,
    session: TargetGameSession,
    fact_ids: Sequence[str],
) -> list[TextFactV2Record]:
    """按 fact_id 读取当前 scope 内供质量检查使用的 v2 facts。"""
    unique_fact_ids = sorted(set(fact_ids))
    if not unique_fact_ids:
        return []
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    records: list[TextFactV2Record] = []
    for batch in chunks(unique_fact_ids, 500):
        placeholders = ", ".join("?" for _fact_id in batch)
        async with session.connection.execute(
            f"""
--sql
                SELECT
{TEXT_FACT_SELECT_COLUMNS}
                FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                WHERE facts.scope_key = ?
                    AND facts.fact_id IN ({placeholders})
                ORDER BY facts.domain, facts.location_path, facts.fact_id
            ;
            """,
            (scope.scope_key, *batch),
        ) as cursor:
            rows = await cursor.fetchall()
        records.extend(text_fact_v2_from_row(row, session=session) for row in rows)
    return records
