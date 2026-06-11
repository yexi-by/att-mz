"""当前文本事实契约 的翻译条目与质量检查转换。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Literal

from app.persistence.records import TextFactReadFilter, TextFactRecord, TextIndexItemRecord
from app.persistence.sql import CURRENT_TEXT_FACT_CONTRACT_VERSION, TEXT_FACTS_TABLE_NAME
from app.rmmz.schema import TranslationData, TranslationItem
from app.rmmz.text_rules import JsonObject
from app.text_fact_core import (
    TEXT_FACT_SELECT_COLUMNS,
    assert_current_scope_fact_schema,
    chunks,
    display_name_from_index_record,
    item_type_from_text_fact,
    read_current_text_fact_scope,
    require_current_index_record,
    short_text_sample,
    terminology_owner_terms_from_index_record,
    text_fact_contract_error,
    text_fact_lines,
    text_fact_from_row,
)

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


async def read_text_fact_quality_items_for_translations(
    session: TargetGameSession,
    translated_items: Sequence[TranslationItem],
    *,
    source_text: Literal["translatable", "visible", "raw"] = "translatable",
) -> list[TranslationItem]:
    """把已保存译文的源文替换为当前文本事实指定正文，供质量检查使用。"""
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
            f"已保存译文缺少当前文本事实身份，不能重建质量检查源文: {samples}{suffix}"
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
            f"已保存译文缺少当前文本事实，不能重建质量检查源文；请重新运行 rebuild-text-index 后重新翻译或手动导入: {samples}{suffix}"
        )
    quality_items: list[TranslationItem] = []
    for item in translated_items:
        fact = facts_by_id[item.fact_id or ""]
        if (
            item.source_fact_raw_hash != fact.raw_hash
            or item.source_fact_translatable_hash != fact.translatable_hash
        ):
            raise text_fact_contract_error(
                "已保存译文不再匹配当前文本事实，不能重建质量检查源文；请重新运行 rebuild-text-index 后重新翻译或手动导入: "
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


async def read_text_fact_sample_details_by_paths(
    session: TargetGameSession,
    location_paths: Sequence[str],
    *,
    max_chars: int = 120,
) -> dict[str, JsonObject]:
    """读取当前文本事实 的 raw/visible/translatable 短样本。"""
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


async def read_text_fact_sample_details_by_fact_ids(
    session: TargetGameSession,
    fact_ids: Sequence[str],
    *,
    max_chars: int = 120,
) -> dict[str, JsonObject]:
    """读取当前文本事实 的 raw/visible/translatable 短样本，按 fact_id 返回。"""
    if max_chars <= 0:
        raise ValueError("max_chars 必须是正整数")
    facts = await _read_current_text_facts_by_fact_ids_for_quality(
        session=session,
        fact_ids=fact_ids,
    )
    return {
        fact.fact_id: {
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
    facts: Iterable[TextFactRecord],
    *,
    index_records: Sequence[TextIndexItemRecord] = (),
) -> dict[str, TranslationData]:
    """把 当前文本事实按来源文件转换成模型翻译输入。"""
    index_by_path = {record.location_path: record for record in index_records}
    translation_data_map: dict[str, TranslationData] = {}
    for fact in sorted(facts, key=lambda item: (item.domain, item.location_path, item.fact_id)):
        index_record = require_current_index_record(
            fact=fact,
            index_record=index_by_path.get(fact.location_path),
        )
        display_name = display_name_from_index_record(index_record)
        translation_data = translation_data_map.get(fact.source_file)
        if translation_data is None:
            translation_data = TranslationData(display_name=display_name, translation_items=[])
            translation_data_map[fact.source_file] = translation_data
        elif display_name is not None:
            if translation_data.display_name is None:
                translation_data.display_name = display_name
            elif translation_data.display_name != display_name:
                raise RuntimeError(f"当前文本事实来源文件 {fact.source_file} 的地图名不一致")
        translation_data.translation_items.append(
            text_fact_record_to_translation_item(fact, index_record=index_record)
        )
    return translation_data_map


def text_fact_record_to_translation_item(
    fact: TextFactRecord,
    *,
    index_record: TextIndexItemRecord | None = None,
) -> TranslationItem:
    """把单条 current text fact 转成既有 `TranslationItem`，正文使用 translatable_text。"""
    _validate_text_fact_record(fact)
    current_index_record = require_current_index_record(
        fact=fact,
        index_record=index_record,
    )
    item_type = item_type_from_text_fact(fact)
    source_line_paths = list(current_index_record.source_line_paths)
    terminology_owner_terms = terminology_owner_terms_from_index_record(current_index_record)
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
        translation_dedupe_key=f"text_fact:{fact.translatable_hash}",
    )


def text_fact_record_to_quality_item(
    fact: TextFactRecord,
    *,
    index_record: TextIndexItemRecord | None = None,
) -> TranslationItem:
    """把单条 current text fact 转成质量检查输入，源文使用玩家可见文本。"""
    item = text_fact_record_to_translation_item(fact, index_record=index_record)
    item.original_lines = text_fact_lines(fact.visible_text, item_type=item.item_type)
    return item


def _validate_text_fact_record(fact: TextFactRecord) -> None:
    """校验 adapter 消费的单条 current text fact。"""
    if fact.schema_version != CURRENT_TEXT_FACT_CONTRACT_VERSION:
        raise text_fact_contract_error(
            "当前文本事实 schema_version 不受支持: "
            + f"数据库是 {fact.schema_version}，当前工具支持 {CURRENT_TEXT_FACT_CONTRACT_VERSION}"
        )
    if not fact.scope_key:
        raise text_fact_contract_error("当前文本事实 缺少 scope_key")
    if not fact.location_path:
        raise text_fact_contract_error("当前文本事实 缺少 location_path")


async def _read_current_text_facts_by_paths_for_quality(
    *,
    session: TargetGameSession,
    location_paths: Sequence[str],
) -> list[TextFactRecord]:
    """按路径读取当前 scope 内供质量报告使用的 current text facts。"""
    unique_paths = sorted(set(location_paths))
    if not unique_paths:
        return []
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await session.read_text_facts(
        TextFactReadFilter(scope_key=scope.scope_key, location_paths=unique_paths)
    )


async def _read_current_text_facts_by_fact_ids_for_quality(
    *,
    session: TargetGameSession,
    fact_ids: Sequence[str],
) -> list[TextFactRecord]:
    """按 fact_id 读取当前 scope 内供质量检查使用的 current text facts。"""
    unique_fact_ids = sorted(set(fact_ids))
    if not unique_fact_ids:
        return []
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    records: list[TextFactRecord] = []
    for batch in chunks(unique_fact_ids, 500):
        placeholders = ", ".join("?" for _fact_id in batch)
        async with session.connection.execute(
            f"""
--sql
                SELECT
{TEXT_FACT_SELECT_COLUMNS}
                FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
                WHERE facts.scope_key = ?
                    AND facts.fact_id IN ({placeholders})
                ORDER BY facts.domain, facts.location_path, facts.fact_id
            ;
            """,
            (scope.scope_key, *batch),
        ) as cursor:
            rows = await cursor.fetchall()
        records.extend(text_fact_from_row(row, session=session) for row in rows)
    return records
