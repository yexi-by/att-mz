"""当前文本事实契约 的计数与质量错误路径读取。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.persistence.rows import row_int, row_str
from app.persistence.sql import (
    TEXT_FACTS_TABLE_NAME,
    TEXT_INDEX_ITEMS_TABLE_NAME,
    TRANSLATION_QUALITY_ERRORS_TABLE_NAME,
    TRANSLATION_TABLE_NAME,
)
from app.text_fact_core import (
    assert_current_scope_fact_schema,
    read_count,
    read_current_text_fact_scope,
    translation_matches_fact_sql,
)

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


async def count_current_text_facts(session: TargetGameSession) -> int:
    """统计当前 scope 内的 当前文本事实数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS item_count
            FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="item_count",
    )


async def count_pending_text_facts(session: TargetGameSession) -> int:
    """统计当前文本事实范围中还没成功保存译文且当前可写的事实数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=_pending_text_fact_count_sql(),
        parameters=(scope.scope_key,),
        column_name="pending_count",
    )


async def count_translated_text_facts(session: TargetGameSession) -> int:
    """统计当前文本事实范围内已成功保存译文的事实数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS translated_count
            FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
            INNER JOIN [{TRANSLATION_TABLE_NAME}] AS translations
                ON {translation_matches_fact_sql()}
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            WHERE facts.scope_key = ?
                AND indexed.writable = 1
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="translated_count",
    )


async def read_current_matching_translation_fact_ids(session: TargetGameSession) -> set[str]:
    """读取与当前文本事实 完整身份匹配的已保存译文 fact_id。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT facts.fact_id
            FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
            INNER JOIN [{TRANSLATION_TABLE_NAME}] AS translations
                ON {translation_matches_fact_sql()}
            WHERE facts.scope_key = ?
            ORDER BY facts.fact_id
        ;
        """,
        (scope.scope_key,),
    ) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "fact_id", session.db_path) for row in rows}


async def count_writable_text_facts(session: TargetGameSession) -> int:
    """统计当前文本事实范围内可写回的文本事实数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS writable_count
            FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
            INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
                ON indexed.location_path = facts.location_path
            WHERE facts.scope_key = ?
                AND indexed.writable = 1
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="writable_count",
    )


async def count_rule_hit_text_facts(session: TargetGameSession) -> int:
    """统计当前文本事实范围中来自外部规则支线的文本事实数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS rule_hit_count
            FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
                AND facts.source_type <> 'standard_data'
        ;
        """,
        parameters=(scope.scope_key,),
        column_name="rule_hit_count",
    )


async def count_stale_translations_outside_writable_text_facts(session: TargetGameSession) -> int:
    """统计不属于当前可写 current text fact 范围的已保存译文数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS stale_translation_count
            FROM [{TRANSLATION_TABLE_NAME}] AS translations
            LEFT JOIN [{TEXT_FACTS_TABLE_NAME}] AS facts
                ON {translation_matches_fact_sql()}
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


async def count_pending_text_fact_quality_errors(
    session: TargetGameSession,
    run_id: str,
) -> int:
    """统计当前 pending 范围内最新运行的质量错误数量。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    return await read_count(
        session=session,
        sql=_pending_text_fact_quality_error_sql(
            select_clause="COUNT(*) AS quality_error_count",
            group_by="",
            order_by="",
        ),
        parameters=(run_id, scope.scope_key),
        column_name="quality_error_count",
    )


async def count_pending_text_fact_quality_errors_by_type(
    session: TargetGameSession,
    run_id: str,
) -> dict[str, int]:
    """按错误类型统计当前 pending 范围内的质量错误。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
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


async def read_pending_text_fact_quality_error_paths(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前 pending 范围内指定运行没通过项目检查的定位路径。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    sql = _pending_text_fact_quality_error_sql(
        select_clause="quality_errors.location_path",
        group_by="",
        order_by="ORDER BY quality_errors.location_path",
    )
    async with session.connection.execute(sql, (run_id, scope.scope_key)) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "location_path", session.db_path) for row in rows}


async def read_pending_text_fact_quality_error_fact_ids(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前 pending 范围内指定运行没通过项目检查的 fact_id。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    sql = _pending_text_fact_quality_error_sql(
        select_clause="quality_errors.fact_id",
        group_by="",
        order_by="ORDER BY quality_errors.fact_id",
    )
    async with session.connection.execute(sql, (run_id, scope.scope_key)) as cursor:
        rows = await cursor.fetchall()
    return {row_str(row, "fact_id", session.db_path) for row in rows}


async def read_text_fact_quality_error_paths(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前文本事实范围内指定运行没通过项目检查的定位路径。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT quality_errors.location_path
            FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
            INNER JOIN [{TEXT_FACTS_TABLE_NAME}] AS facts
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


async def read_text_fact_quality_error_fact_ids(
    session: TargetGameSession,
    run_id: str,
) -> set[str]:
    """读取当前文本事实范围内指定运行没通过项目检查的 fact_id。"""
    scope = await read_current_text_fact_scope(session)
    await assert_current_scope_fact_schema(session=session, scope=scope)
    async with session.connection.execute(
        f"""
--sql
            SELECT quality_errors.fact_id
            FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
            INNER JOIN [{TEXT_FACTS_TABLE_NAME}] AS facts
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


def _pending_text_fact_count_sql() -> str:
    """返回当前 pending current text fact 计数 SQL。"""
    return f"""
--sql
        SELECT COUNT(*) AS pending_count
        FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
        INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
            ON indexed.location_path = facts.location_path
        LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
            ON {translation_matches_fact_sql()}
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
    """返回当前 pending current text fact 质量错误查询 SQL。"""
    return f"""
--sql
        SELECT {select_clause}
        FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}] AS quality_errors
        INNER JOIN [{TEXT_FACTS_TABLE_NAME}] AS facts
            ON facts.fact_id = quality_errors.fact_id
            AND quality_errors.fact_id <> ''
        INNER JOIN [{TEXT_INDEX_ITEMS_TABLE_NAME}] AS indexed
            ON indexed.location_path = facts.location_path
        LEFT JOIN [{TRANSLATION_TABLE_NAME}] AS translations
            ON {translation_matches_fact_sql()}
        WHERE quality_errors.run_id = ?
            AND facts.scope_key = ?
            AND indexed.writable = 1
            AND translations.fact_id IS NULL
        {group_by}
        {order_by}
    ;
    """
