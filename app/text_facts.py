"""Text Fact Contract v2 的 Python 适配层。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Literal, cast

import aiosqlite

from app.persistence.records import (
    TextFactScopeV2Record,
    TextFactV2ReadFilter,
    TextFactV2Record,
    TextIndexItemRecord,
)
from app.persistence.rows import row_int, row_str
from app.persistence.sql import (
    TEXT_FACT_SCHEMA_VERSION,
    TEXT_FACT_SCOPE_V2_TABLE_NAME,
    TEXT_FACTS_V2_TABLE_NAME,
    TEXT_INDEX_ITEMS_TABLE_NAME,
    TRANSLATION_QUALITY_ERRORS_TABLE_NAME,
    TRANSLATION_TABLE_NAME,
)
from app.rmmz.schema import ItemType, TranslationData, TranslationItem
from app.rmmz.text_rules import JsonObject, coerce_json_value

if TYPE_CHECKING:
    from app.persistence import TargetGameSession

type SqlParameter = str | int

TEXT_FACT_SELECT_COLUMNS = """
        facts.fact_id,
        facts.schema_version,
        facts.domain,
        facts.location_path,
        facts.source_file,
        facts.source_type,
        facts.item_type,
        facts.role,
        facts.selector,
        facts.raw_text,
        facts.visible_text,
        facts.translatable_text,
        facts.raw_hash,
        facts.visible_hash,
        facts.translatable_hash,
        facts.scope_key
"""


class TextFactContractError(RuntimeError):
    """当前数据库无法按 Text Fact Contract v2 提供正文事实。"""


async def read_current_text_fact_scope_v2(session: TargetGameSession) -> TextFactScopeV2Record:
    """读取并校验当前唯一 v2 scope；缺失或版本不支持时显式失败。"""
    try:
        async with session.connection.execute(
            f"""
--sql
                SELECT scope_key
                FROM [{TEXT_FACT_SCOPE_V2_TABLE_NAME}]
                ORDER BY created_at DESC, scope_key DESC
                LIMIT 1
            ;
            """
        ) as cursor:
            row = await cursor.fetchone()
    except aiosqlite.Error as error:
        raise _text_fact_contract_error(
            f"当前数据库不可读取 {TEXT_FACT_SCOPE_V2_TABLE_NAME}"
        ) from error
    if row is None:
        raise _text_fact_contract_error("当前数据库缺少 text fact v2 scope")
    scope_key = row_str(row, "scope_key", session.db_path)
    try:
        return await session.require_current_text_fact_scope_v2(scope_key)
    except RuntimeError as error:
        raise _text_fact_contract_error(str(error)) from error


async def count_current_text_facts_v2(session: TargetGameSession) -> int:
    """统计当前 scope 内的 v2 文本事实数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS item_count
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="item_count",
    )


async def count_pending_text_facts_v2(session: TargetGameSession) -> int:
    """统计当前 v2 scope 中还没成功保存译文且当前可写的事实数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=_pending_text_fact_count_sql(),
        parameters=(scope.scope_key,),
        column_name="pending_count",
    )


async def count_translated_text_facts_v2(session: TargetGameSession) -> int:
    """统计当前 v2 scope 内已成功保存译文的事实数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS translated_count
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            INNER JOIN [{TRANSLATION_TABLE_NAME}] AS translations
                ON {_translation_matches_fact_sql()}
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            WHERE facts.scope_key = ?
                AND indexed.writable = 1
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="translated_count",
    )


async def count_writable_text_facts_v2(session: TargetGameSession) -> int:
    """统计当前 v2 scope 内可写回的文本事实数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS writable_count
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            WHERE facts.scope_key = ?
                AND indexed.writable = 1
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="writable_count",
    )


async def count_rule_hit_text_facts_v2(session: TargetGameSession) -> int:
    """统计当前 v2 scope 中来自外部规则支线的文本事实数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS rule_hit_count
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
                AND facts.source_type <> 'standard_data'
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="rule_hit_count",
    )


async def count_stale_translations_outside_writable_text_facts_v2(session: TargetGameSession) -> int:
    """统计不属于当前可写 v2 fact 范围的已保存译文数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS stale_translation_count
            FROM [{TRANSLATION_TABLE_NAME}] AS translations
            LEFT JOIN [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                ON {_translation_matches_fact_sql()}
                AND facts.scope_key = ?
            LEFT JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
                AND indexed.writable = 1
            WHERE indexed.location_path IS NULL
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="stale_translation_count",
    )


async def count_pending_text_fact_quality_errors_v2(
    session: TargetGameSession,
    run_id: str,
) -> int:
    """统计当前 v2 pending 范围内最新运行的质量错误数量。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    return await _read_count(
        session=session,
        sql=_pending_text_fact_quality_error_sql(
            select_clause="COUNT(*) AS quality_error_count",
            group_by="",
            order_by="",
        ),
        parameters=(run_id, scope.scope_key),
        column_name="quality_error_count",
    )


async def count_pending_text_fact_quality_errors_by_type_v2(
    session: TargetGameSession,
    run_id: str,
) -> dict[str, int]:
    """按错误类型统计当前 v2 pending 范围内的质量错误。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    sql = _pending_text_fact_quality_error_sql(
        select_clause="quality_errors.error_type, COUNT(*) AS error_count",
        group_by="GROUP BY quality_errors.error_type",
        order_by="ORDER BY quality_errors.error_type",
    )
    async with session.connection.execute(sql, (run_id, scope.scope_key)) as cursor:
        rows = await cursor.fetchall()
    return {
        row_str(row, "error_type", session.db_path): row_int(row, "error_count", session.db_path)
        for row in rows
    }


async def read_pending_text_fact_quality_error_paths_v2(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前 v2 pending 范围内指定运行没通过项目检查的定位路径。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    sql = _pending_text_fact_quality_error_sql(
        select_clause="quality_errors.location_path",
        group_by="",
        order_by="ORDER BY quality_errors.location_path",
    )
    async with session.connection.execute(sql, (run_id, scope.scope_key)) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "location_path", session.db_path) for row in rows}


async def read_pending_text_fact_quality_error_fact_ids_v2(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前 v2 pending 范围内指定运行没通过项目检查的 fact_id。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    sql = _pending_text_fact_quality_error_sql(
        select_clause="quality_errors.fact_id",
        group_by="",
        order_by="ORDER BY quality_errors.fact_id",
    )
    async with session.connection.execute(sql, (run_id, scope.scope_key)) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "fact_id", session.db_path) for row in rows}


async def read_text_fact_quality_error_paths_v2(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前 v2 scope 内指定运行没通过项目检查的定位路径。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT quality_errors.location_path
            FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
            INNER JOIN [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                ON facts.fact_id = quality_errors.fact_id
                AND quality_errors.fact_id <> ''
            WHERE quality_errors.run_id = ?
                AND facts.scope_key = ?
            ORDER BY quality_errors.location_path
        ;
        """,
        (run_id, scope.scope_key),
    ) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "location_path", session.db_path) for row in rows}


async def read_text_fact_quality_error_fact_ids_v2(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前 v2 scope 内指定运行没通过项目检查的 fact_id。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT quality_errors.fact_id
            FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
            INNER JOIN [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                ON facts.fact_id = quality_errors.fact_id
                AND quality_errors.fact_id <> ''
            WHERE quality_errors.run_id = ?
                AND facts.scope_key = ?
            ORDER BY quality_errors.fact_id
        ;
        """,
        (run_id, scope.scope_key),
    ) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "fact_id", session.db_path) for row in rows}


async def read_pending_text_fact_records_v2(
    session: TargetGameSession,
    *,
    limit: int | None,
) -> list[TextFactV2Record]:
    """按当前 scope 和 SQLite limit 读取待翻译 v2 facts。"""
    if limit is not None and limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
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
                ON {_translation_matches_fact_sql()}
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
    return [_text_fact_v2_from_row(row, session=session) for row in rows]


async def read_current_text_fact_records_v2(
    session: TargetGameSession,
    *,
    limit: int | None,
) -> list[TextFactV2Record]:
    """按当前 scope 读取 v2 fact；报告明细调用方必须传入有限 limit 或确认小库。"""
    if limit is not None and limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
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
    return [_text_fact_v2_from_row(row, session=session) for row in rows]


async def read_unwritable_text_fact_records_v2(
    session: TargetGameSession,
    *,
    limit: int,
) -> list[TextFactV2Record]:
    """读取当前 scope 中不可写回的 v2 fact 样本。"""
    if limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
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
    return [_text_fact_v2_from_row(row, session=session) for row in rows]


async def read_pending_text_fact_path_samples_v2(
    session: TargetGameSession,
    *,
    limit: int,
) -> list[str]:
    """读取当前 pending v2 facts 的定位路径样本。"""
    if limit <= 0:
        raise ValueError("limit 必须是正整数")
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT facts.location_path
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
                ON {_translation_matches_fact_sql()}
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
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT translations.location_path
            FROM [{TRANSLATION_TABLE_NAME}] AS translations
            LEFT JOIN [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
                ON {_translation_matches_fact_sql()}
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
            _text_fact_lines(
                fact.translatable_text,
                item_type=_item_type_from_text_fact(fact),
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
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    facts = await session.read_text_facts_v2(
        TextFactV2ReadFilter(scope_key=scope.scope_key, location_paths=unique_paths)
    )
    facts_by_path = {
        fact.location_path: fact
        for fact in facts
        if fact.scope_key == scope.scope_key and fact.location_path in unique_paths
    }
    index_records = await session.read_text_index_items_by_paths(unique_paths)
    items: list[TranslationItem] = []
    for record in index_records:
        if not record.writable:
            continue
        fact = facts_by_path.get(record.location_path)
        if fact is None:
            continue
        items.append(text_fact_record_to_translation_item(fact, index_record=record))
    return items


async def read_writable_text_fact_translation_items_v2(
    session: TargetGameSession,
) -> list[TranslationItem]:
    """读取当前可写 v2 facts，正文使用 translatable_text。"""
    scope = await read_current_text_fact_scope_v2(session)
    await _assert_current_scope_fact_schema(session=session, scope=scope)
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
        raise _text_fact_contract_error("当前数据库不可读取可写 text fact v2") from error
    facts = [_text_fact_v2_from_row(row, session=session) for row in rows]
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
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    placeholders = ", ".join("?" for _fact_id in unique_fact_ids)
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
                    AND facts.fact_id IN ({placeholders})
                ORDER BY indexed.location_path, facts.domain, facts.fact_id
            ;
            """,
            (scope.scope_key, *unique_fact_ids),
        ) as cursor:
            rows = await cursor.fetchall()
    except aiosqlite.Error as error:
        raise _text_fact_contract_error("当前数据库不可按 fact_id 读取可写 text fact v2") from error
    facts = [_text_fact_v2_from_row(row, session=session) for row in rows]
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
        raise _text_fact_contract_error(
            f"已保存译文缺少 v2 fact identity，不能重建质量检查源文: {samples}{suffix}"
        )
    facts = await _read_current_text_facts_by_fact_ids(session=session, fact_ids=fact_ids)
    facts_by_id = {fact.fact_id: fact for fact in facts}
    missing_fact_ids = sorted(set(fact_ids) - set(facts_by_id))
    if missing_fact_ids:
        samples = "、".join(missing_fact_ids[:5])
        suffix = f" 等 {len(missing_fact_ids)} 条" if len(missing_fact_ids) > 5 else ""
        raise _text_fact_contract_error(
            f"已保存译文缺少当前 v2 文本事实，不能重建质量检查源文: {samples}{suffix}"
        )
    quality_items: list[TranslationItem] = []
    for item in translated_items:
        fact = facts_by_id[item.fact_id or ""]
        if (
            item.source_fact_raw_hash != fact.raw_hash
            or item.source_fact_translatable_hash != fact.translatable_hash
        ):
            raise _text_fact_contract_error(
                "已保存译文不再匹配当前 v2 文本事实身份，不能重建质量检查源文: "
                + f"{item.location_path}"
            )
        cloned_item = item.model_copy(deep=True)
        item_type = _item_type_from_text_fact(fact)
        cloned_item.item_type = item_type
        cloned_item.role = fact.role or None
        raw_lines = _text_fact_lines(fact.raw_text, item_type=item_type)
        visible_lines = _text_fact_lines(fact.visible_text, item_type=item_type)
        translatable_lines = _text_fact_lines(fact.translatable_text, item_type=item_type)
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
    facts = await _read_current_text_facts_by_paths(session=session, location_paths=location_paths)
    return {
        fact.location_path: {
            "raw_text_sample": _short_text_sample(fact.raw_text, max_chars=max_chars),
            "visible_text_sample": _short_text_sample(fact.visible_text, max_chars=max_chars),
            "translatable_text_sample": _short_text_sample(
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
        display_name = _display_name_from_index_record(index_record)
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
    item_type = _item_type_from_text_fact(fact)
    source_line_paths = (
        list(index_record.source_line_paths)
        if index_record is not None
        else [fact.location_path]
    )
    terminology_owner_terms = (
        _terminology_owner_terms_from_index_record(index_record)
        if index_record is not None
        else []
    )
    return TranslationItem(
        fact_id=fact.fact_id,
        location_path=fact.location_path,
        item_type=item_type,
        role=fact.role or None,
        original_lines=_text_fact_lines(fact.translatable_text, item_type=item_type),
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
    item.original_lines = _text_fact_lines(fact.visible_text, item_type=item.item_type)
    return item


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
    await _assert_current_scope_fact_schema(session=session, scope=scope)
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
    await _assert_current_scope_fact_schema(session=session, scope=scope)
    records: list[TextFactV2Record] = []
    for batch in _chunks(unique_fact_ids, 500):
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
        records.extend(_text_fact_v2_from_row(row, session=session) for row in rows)
    return records


async def _read_index_records_for_facts(
    *,
    session: TargetGameSession,
    facts: Sequence[TextFactV2Record],
) -> list[TextIndexItemRecord]:
    """读取 v2 facts 对应的旧索引定位元信息。"""
    return await session.read_text_index_items_by_paths([fact.location_path for fact in facts])


async def _assert_current_scope_fact_schema(
    *,
    session: TargetGameSession,
    scope: TextFactScopeV2Record,
) -> None:
    """拒绝当前 scope 内混入不支持的 fact schema_version。"""
    mismatch_count = await _read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS mismatch_count
            FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
                AND facts.schema_version <> ?
        ;
        """,
        parameters=(scope.scope_key, TEXT_FACT_SCHEMA_VERSION),
        column_name="mismatch_count",
    )
    if mismatch_count:
        raise _text_fact_contract_error(
            "当前 text fact v2 scope 中存在不支持的 schema version: "
            + f"{mismatch_count} 条事实不是 {TEXT_FACT_SCHEMA_VERSION}"
        )


async def _read_count(
    *,
    session: TargetGameSession,
    sql: str,
    parameters: Sequence[SqlParameter],
    column_name: str,
) -> int:
    """执行单值 COUNT 查询。"""
    try:
        async with session.connection.execute(sql, tuple(parameters)) as cursor:
            row = await cursor.fetchone()
    except aiosqlite.Error as error:
        raise _text_fact_contract_error("当前数据库不可读取 text fact v2 计数") from error
    if row is None:
        return 0
    return row_int(row, column_name, session.db_path)


def _pending_text_fact_count_sql() -> str:
    """返回当前 pending v2 fact 计数 SQL。"""
    return f"""
--sql
        SELECT COUNT(*) AS pending_count
        FROM [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
        INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
            ON indexed.location_path = facts.location_path
        LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
            ON {_translation_matches_fact_sql()}
        WHERE facts.scope_key = ?
            AND indexed.writable = 1
            AND translations.fact_id IS NULL
    ;
    """


def _pending_text_fact_quality_error_sql(
    *,
    select_clause: str,
    group_by: str,
    order_by: str,
) -> str:
    """返回当前 pending v2 fact 质量错误查询 SQL。"""
    return f"""
--sql
        SELECT {select_clause}
        FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
        INNER JOIN [{TEXT_FACTS_V2_TABLE_NAME}] AS facts
            ON facts.fact_id = quality_errors.fact_id
            AND quality_errors.fact_id <> ''
        INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
            ON indexed.location_path = facts.location_path
        LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
            ON {_translation_matches_fact_sql()}
        WHERE quality_errors.run_id = ?
            AND facts.scope_key = ?
            AND indexed.writable = 1
            AND translations.fact_id IS NULL
        {group_by}
        {order_by}
    ;
    """


def _translation_matches_fact_sql() -> str:
    """返回已保存译文和当前 v2 fact 身份完全一致的 SQL 条件。"""
    return (
        "translations.fact_id = facts.fact_id "
        "AND translations.source_fact_raw_hash = facts.raw_hash "
        "AND translations.source_fact_translatable_hash = facts.translatable_hash"
    )


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """把 fact_id 列表分块，避免 SQLite 参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]


def _text_fact_v2_from_row(
    row: aiosqlite.Row,
    *,
    session: TargetGameSession,
) -> TextFactV2Record:
    """把 SQLite 行转换成 v2 文本事实记录。"""
    return TextFactV2Record(
        fact_id=row_str(row, "fact_id", session.db_path),
        schema_version=row_int(row, "schema_version", session.db_path),
        domain=row_str(row, "domain", session.db_path),
        location_path=row_str(row, "location_path", session.db_path),
        source_file=row_str(row, "source_file", session.db_path),
        source_type=row_str(row, "source_type", session.db_path),
        item_type=row_str(row, "item_type", session.db_path),
        role=row_str(row, "role", session.db_path),
        selector=row_str(row, "selector", session.db_path),
        raw_text=row_str(row, "raw_text", session.db_path),
        visible_text=row_str(row, "visible_text", session.db_path),
        translatable_text=row_str(row, "translatable_text", session.db_path),
        raw_hash=row_str(row, "raw_hash", session.db_path),
        visible_hash=row_str(row, "visible_hash", session.db_path),
        translatable_hash=row_str(row, "translatable_hash", session.db_path),
        scope_key=row_str(row, "scope_key", session.db_path),
    )


def _validate_text_fact_record(fact: TextFactV2Record) -> None:
    """校验 adapter 消费的单条 v2 fact。"""
    if fact.schema_version != TEXT_FACT_SCHEMA_VERSION:
        raise _text_fact_contract_error(
            "text fact v2 schema_version 不受支持: "
            + f"数据库是 {fact.schema_version}，当前工具支持 {TEXT_FACT_SCHEMA_VERSION}"
        )
    if not fact.scope_key:
        raise _text_fact_contract_error("text fact v2 缺少 scope_key")
    if not fact.location_path:
        raise _text_fact_contract_error("text fact v2 缺少 location_path")


def _item_type_from_text_fact(fact: TextFactV2Record) -> ItemType:
    """从 v2 fact 读取既有 TranslationItem item_type。"""
    if fact.item_type not in {"long_text", "array", "short_text"}:
        raise _text_fact_contract_error(f"text fact v2 item_type 不受支持: {fact.item_type}")
    return cast(ItemType, fact.item_type)


def _text_fact_lines(text: str, *, item_type: ItemType) -> list[str]:
    """把 v2 单字符串正文转换成既有 TranslationItem 行模型。"""
    if item_type in {"long_text", "array"}:
        return text.split("\n")
    return [text]


def _short_text_sample(text: str, *, max_chars: int) -> str:
    """生成报告用短样本，避免错误明细展开长文本。"""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _display_name_from_index_record(record: TextIndexItemRecord | None) -> str | None:
    """从旧 text index locator 中读取地图名；v2 adapter 不依赖 docs 或游戏文件。"""
    locator = _locator_object_from_index_record(record)
    if locator is None:
        return None
    raw_display_name = locator.get("display_name")
    if raw_display_name is None:
        return None
    if not isinstance(raw_display_name, str):
        raise RuntimeError("文本范围索引 locator_json.display_name 必须是字符串或 null")
    return raw_display_name or None


def _terminology_owner_terms_from_index_record(record: TextIndexItemRecord | None) -> list[str]:
    """从旧 text index locator 中读取术语 owner 词。"""
    locator = _locator_object_from_index_record(record)
    if locator is None:
        return []
    raw_owner_terms = locator.get("terminology_owner_terms")
    if raw_owner_terms is None:
        return []
    if not isinstance(raw_owner_terms, list):
        raise RuntimeError("文本范围索引 locator_json.terminology_owner_terms 必须是字符串数组")
    owner_terms: list[str] = []
    for index, raw_term in enumerate(raw_owner_terms):
        if not isinstance(raw_term, str):
            raise RuntimeError(f"文本范围索引 locator_json.terminology_owner_terms[{index}] 必须是字符串")
        if raw_term:
            owner_terms.append(raw_term)
    return owner_terms


def _locator_object_from_index_record(record: TextIndexItemRecord | None) -> JsonObject | None:
    """读取旧 text index locator JSON 对象。"""
    if record is None:
        return None
    locator = coerce_json_value(cast(object, json.loads(record.locator_json)))
    if not isinstance(locator, dict):
        raise RuntimeError("文本范围索引 locator_json 必须是对象")
    return locator


def _text_fact_contract_error(detail: str) -> TextFactContractError:
    """构造面向用户的 v2 fact 契约错误。"""
    return TextFactContractError(
        f"{detail}。影响：当前命令需要读取当前 Text Fact Contract v2 文本事实，"
        + "不能继续使用旧索引正文或不一致事实。下一步：请运行 rebuild-text-index 重新生成当前文本索引。"
    )


__all__ = [
    "TextFactContractError",
    "count_current_text_facts_v2",
    "count_pending_text_fact_quality_errors_by_type_v2",
    "count_pending_text_fact_quality_errors_v2",
    "count_pending_text_facts_v2",
    "count_rule_hit_text_facts_v2",
    "count_stale_translations_outside_writable_text_facts_v2",
    "count_translated_text_facts_v2",
    "count_writable_text_facts_v2",
    "read_current_text_fact_scope_v2",
    "read_current_text_fact_records_v2",
    "read_current_text_fact_placeholder_entries_v2",
    "read_current_text_fact_translation_data_map_v2",
    "read_current_text_fact_translation_items_by_paths",
    "read_pending_text_fact_quality_error_paths_v2",
    "read_pending_text_fact_quality_error_fact_ids_v2",
    "read_pending_text_fact_records_v2",
    "read_pending_text_fact_path_samples_v2",
    "read_pending_text_fact_translation_data_map",
    "read_pending_text_fact_translation_items",
    "read_stale_translation_path_samples_outside_writable_text_facts_v2",
    "read_text_fact_sample_details_by_paths_v2",
    "read_text_fact_quality_error_paths_v2",
    "read_text_fact_quality_error_fact_ids_v2",
    "read_text_fact_quality_items_for_translations",
    "read_unwritable_text_fact_records_v2",
    "read_writable_text_fact_translation_items_by_fact_ids",
    "read_writable_text_fact_translation_items_by_paths",
    "read_writable_text_fact_translation_items_v2",
    "text_fact_record_to_quality_item",
    "text_fact_record_to_translation_item",
    "text_fact_records_to_translation_data_map",
]
