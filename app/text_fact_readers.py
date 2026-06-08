"""Text Fact Contract v2 的事实读取与翻译输入读取。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import aiosqlite

from app.persistence.records import TextFactV2ReadFilter, TextFactV2Record, TextIndexItemRecord
from app.persistence.rows import row_str
from app.persistence.sql import (
    TEXT_FACTS_V2_TABLE_NAME,
    TEXT_INDEX_ITEMS_TABLE_NAME,
    TRANSLATION_TABLE_NAME,
)
from app.rmmz.schema import TranslationData, TranslationItem
from app.text_fact_core import (
    TEXT_FACT_SELECT_COLUMNS,
    assert_current_scope_fact_schema,
    chunks,
    item_type_from_text_fact,
    read_current_text_fact_scope_v2,
    text_fact_contract_error,
    text_fact_lines,
    text_fact_v2_from_row,
    translation_matches_fact_sql,
)
from app.text_fact_quality import (
    text_fact_record_to_translation_item,
    text_fact_records_to_translation_data_map,
)

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


async def read_pending_text_fact_records_v2(
    session: TargetGameSession,
    *,
    limit: int | None,
) -> list[TextFactV2Record]:
    """按当前 scope 和 SQLite limit 读取待翻译 v2 facts。"""
    if limit is not None and limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    sql_limit = -1 if limit is None else limit
    async with session.connection.execute(
        f"""
--sql
            SELECT
{TEXT_FACT_SELECT_COLUMNS}
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
                ON {translation_matches_fact_sql()}
            WHERE facts.scope_key = ?
                AND indexed.writable = 1
                AND translations.fact_id IS NULL
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
            LIMIT ?
        ;
        """,
        (scope.scope_key, sql_limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [text_fact_v2_from_row(row, session=session) for row in rows]


async def read_current_text_fact_records_v2(
    session: TargetGameSession,
    *,
    limit: int | None,
) -> list[TextFactV2Record]:
    """按当前 scope 读取 v2 fact；报告明细调用方必须传入有限 limit 或确认小库。"""
    if limit is not None and limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    sql_limit = -1 if limit is None else limit
    async with session.connection.execute(
        f"""
--sql
            SELECT
{TEXT_FACT_SELECT_COLUMNS}
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
            ORDER BY facts.domain, facts.location_path, facts.fact_id
            LIMIT ?
        ;
        """,
        (scope.scope_key, sql_limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [text_fact_v2_from_row(row, session=session) for row in rows]


async def read_unwritable_text_fact_records_v2(
    session: TargetGameSession,
    *,
    limit: int,
) -> list[TextFactV2Record]:
    """读取当前 scope 中不可写回的 v2 fact 样本。"""
    if limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT
{TEXT_FACT_SELECT_COLUMNS}
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            LEFT JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            WHERE facts.scope_key = ?
                AND COALESCE(indexed.writable, 0) <> 1
            ORDER BY facts.domain, facts.location_path, facts.fact_id
            LIMIT ?
        ;
        """,
        (scope.scope_key, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [text_fact_v2_from_row(row, session=session) for row in rows]


async def read_pending_text_fact_path_samples_v2(
    session: TargetGameSession,
    *,
    limit: int,
) -> list[str]:
    """读取当前 pending v2 facts 的定位路径样本。"""
    if limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT facts.location_path
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
                ON {translation_matches_fact_sql()}
            WHERE facts.scope_key = ?
                AND indexed.writable = 1
                AND translations.fact_id IS NULL
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
            LIMIT ?
        ;
        """,
        (scope.scope_key, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [row_str(row, "location_path", session.db_path) for row in rows]


async def read_stale_translation_path_samples_outside_writable_text_facts_v2(
    session: TargetGameSession,
    *,
    limit: int,
) -> list[str]:
    """读取不属于当前可写 v2 fact 范围的已保存译文路径样本。"""
    if limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT translations.location_path
            FROM [{TRANSLATION_TABLE_NAME}] AS translations
            LEFT JOIN [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                ON {translation_matches_fact_sql()}
                AND facts.scope_key = ?
            LEFT JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
                AND indexed.writable = 1
            WHERE indexed.location_path IS NULL
            ORDER BY translations.location_path
            LIMIT ?
        ;
        """,
        (scope.scope_key, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [row_str(row, "location_path", session.db_path) for row in rows]


async def read_pending_text_fact_translation_items(
    session: TargetGameSession,
    *,
    limit: int | None,
) -> list[TranslationItem]:
    """读取当前 pending v2 facts，并转换成既有翻译条目模型。"""
    facts = await read_pending_text_fact_records_v2(session, limit=limit)
    index_records = await _read_index_records_for_facts(session=session, facts=facts)
    index_by_path = {record.location_path: record for record in index_records}
    return [
        text_fact_record_to_translation_item(
            fact,
            index_record=index_by_path.get(fact.location_path),
        )
        for fact in facts
    ]


async def read_pending_text_fact_translation_data_map(
    session: TargetGameSession,
    *,
    limit: int | None,
) -> dict[str, TranslationData]:
    """读取 pending v2 facts，并按来源文件组成模型翻译输入。"""
    facts = await read_pending_text_fact_records_v2(session, limit=limit)
    index_records = await _read_index_records_for_facts(session=session, facts=facts)
    return text_fact_records_to_translation_data_map(facts, index_records=index_records)


async def read_current_text_fact_translation_data_map_v2(
    session: TargetGameSession,
) -> dict[str, TranslationData]:
    """读取当前 v2 facts，并转换成规则候选扫描可消费的正文映射。"""
    facts = await read_current_text_fact_records_v2(session, limit=None)
    index_records = await _read_index_records_for_facts(session=session, facts=facts)
    return text_fact_records_to_translation_data_map(facts, index_records=index_records)


async def read_current_text_fact_placeholder_entries_v2(
    session: TargetGameSession,
) -> list[tuple[str, list[str]]]:
    """读取当前 v2 facts 的占位符扫描轻量正文。"""
    facts = await read_current_text_fact_records_v2(session, limit=None)
    return [
        (
            fact.location_path,
            text_fact_lines(
                fact.translatable_text,
                item_type=item_type_from_text_fact(fact),
            ),
        )
        for fact in facts
    ]


async def read_writable_text_fact_translation_items_by_paths(
    session: TargetGameSession,
    location_paths: Sequence[str],
) -> list[TranslationItem]:
    """按定位路径读取当前可写 v2 facts，供手动导入按当前事实校验。"""
    unique_paths = sorted(set(location_paths))
    if not unique_paths:
        return []
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    facts = await session.read_text_facts_v2(
        TextFactV2ReadFilter(scope_key=scope.scope_key, location_paths=unique_paths)
    )
    facts_by_path: dict[str, list[TextFactV2Record]] = {}
    for fact in facts:
        if fact.scope_key == scope.scope_key and fact.location_path in unique_paths:
            facts_by_path.setdefault(fact.location_path, []).append(fact)
    index_records = await session.read_text_index_items_by_paths(unique_paths)
    items: list[TranslationItem] = []
    for record in index_records:
        if not record.writable:
            continue
        for fact in facts_by_path.get(record.location_path, []):
            items.append(text_fact_record_to_translation_item(fact, index_record=record))
    return items


async def read_writable_text_fact_translation_items_v2(
    session: TargetGameSession,
) -> list[TranslationItem]:
    """读取当前可写 v2 facts，正文使用 translatable_text。"""
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    try:
        async with session.connection.execute(
            f"""
--sql
                SELECT
{TEXT_FACT_SELECT_COLUMNS}
                FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                    ON indexed.location_path = facts.location_path
                    AND indexed.writable = 1
                WHERE facts.scope_key = ?
                ORDER BY indexed.location_path, facts.domain, facts.fact_id
            ;
            """,
            (scope.scope_key,),
        ) as cursor:
            rows = await cursor.fetchall()
    except aiosqlite.Error as error:
        raise text_fact_contract_error("当前数据库不可读取可写 text fact v2") from error
    facts = [text_fact_v2_from_row(row, session=session) for row in rows]
    index_records = await _read_index_records_for_facts(session=session, facts=facts)
    index_by_path = {
        record.location_path: record
        for record in index_records
        if record.writable
    }
    return [
        text_fact_record_to_translation_item(
            fact,
            index_record=index_by_path.get(fact.location_path),
        )
        for fact in facts
        if fact.location_path in index_by_path
    ]


async def read_current_text_fact_translation_items_by_paths(
    session: TargetGameSession,
    location_paths: Sequence[str],
) -> list[TranslationItem]:
    """按定位路径读取当前 v2 facts，缺失路径由调用方按业务语义处理。"""
    facts = await _read_current_text_facts_by_paths(
        session=session,
        location_paths=location_paths,
    )
    index_records = await _read_index_records_for_facts(session=session, facts=facts)
    index_by_path = {record.location_path: record for record in index_records}
    return [
        text_fact_record_to_translation_item(
            fact,
            index_record=index_by_path.get(fact.location_path),
        )
        for fact in facts
    ]


async def read_writable_text_fact_translation_items_by_fact_ids(
    session: TargetGameSession,
    fact_ids: Sequence[str],
) -> dict[str, TranslationItem]:
    """按 fact_id 读取当前可写 v2 facts，供手动导入拒绝不可写事实。"""
    unique_fact_ids = sorted(set(fact_ids))
    if not unique_fact_ids:
        return {}
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    try:
        facts: list[TextFactV2Record] = []
        for batch in chunks(unique_fact_ids, 500):
            placeholders = ", ".join("?" for _fact_id in batch)
            async with session.connection.execute(
                f"""
--sql
                SELECT
{TEXT_FACT_SELECT_COLUMNS}
                FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                    ON indexed.location_path = facts.location_path
                    AND indexed.writable = 1
                WHERE facts.scope_key = ?
                    AND facts.fact_id IN ({placeholders})
                ORDER BY indexed.location_path, facts.domain, facts.fact_id
            ;
            """,
                (scope.scope_key, *batch),
            ) as cursor:
                rows = await cursor.fetchall()
            facts.extend(text_fact_v2_from_row(row, session=session) for row in rows)
    except aiosqlite.Error as error:
        raise text_fact_contract_error("当前数据库不可按 fact_id 读取可写 text fact v2") from error
    index_records = await _read_index_records_for_facts(session=session, facts=facts)
    index_by_path = {
        record.location_path: record
        for record in index_records
        if record.writable
    }
    return {
        fact.fact_id: text_fact_record_to_translation_item(
            fact,
            index_record=index_by_path.get(fact.location_path),
        )
        for fact in facts
        if fact.location_path in index_by_path
    }


async def _read_current_text_facts_by_paths(
    *,
    session: TargetGameSession,
    location_paths: Sequence[str],
) -> list[TextFactV2Record]:
    """按路径读取当前 scope 内的 v2 facts。"""
    unique_paths = sorted(set(location_paths))
    if not unique_paths:
        return []
    scope = await read_current_text_fact_scope_v2(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await session.read_text_facts_v2(
        TextFactV2ReadFilter(scope_key=scope.scope_key, location_paths=unique_paths)
    )


async def _read_current_text_facts_by_fact_ids(
    *,
    session: TargetGameSession,
    fact_ids: Sequence[str],
) -> list[TextFactV2Record]:
    """按 fact_id 读取当前 scope 内的 v2 facts。"""
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


async def _read_index_records_for_facts(
    *,
    session: TargetGameSession,
    facts: Sequence[TextFactV2Record],
) -> list[TextIndexItemRecord]:
    """读取 v2 facts 对应的旧索引定位元信息。"""
    return await session.read_text_index_items_by_paths([fact.location_path for fact in facts])


__all__ = [
    "_read_current_text_facts_by_fact_ids",
    "_read_current_text_facts_by_paths",
    "_read_index_records_for_facts",
    "read_current_text_fact_placeholder_entries_v2",
    "read_current_text_fact_records_v2",
    "read_current_text_fact_translation_data_map_v2",
    "read_current_text_fact_translation_items_by_paths",
    "read_pending_text_fact_path_samples_v2",
    "read_pending_text_fact_records_v2",
    "read_pending_text_fact_translation_data_map",
    "read_pending_text_fact_translation_items",
    "read_stale_translation_path_samples_outside_writable_text_facts_v2",
    "read_unwritable_text_fact_records_v2",
    "read_writable_text_fact_translation_items_by_fact_ids",
    "read_writable_text_fact_translation_items_by_paths",
    "read_writable_text_fact_translation_items_v2",
]
