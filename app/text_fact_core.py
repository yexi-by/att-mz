"""当前文本事实契约 的共享基础能力。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

import aiosqlite

from app.persistence.records import TextFactScopeRecord, TextFactRecord, TextIndexItemRecord
from app.persistence.rows import row_int, row_str
from app.persistence.sql import (
    CURRENT_TEXT_FACT_CONTRACT_VERSION,
    TEXT_FACT_SCOPE_TABLE_NAME,
    TEXT_FACTS_TABLE_NAME,
)
from app.rmmz.schema import ItemType
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
    """当前数据库无法提供当前正文文本事实。"""


async def read_current_text_fact_scope(session: TargetGameSession) -> TextFactScopeRecord:
    """读取并校验当前唯一 当前文本事实 scope；缺失或版本不支持时显式失败。"""
    try:
        async with session.connection.execute(
            f"""
--sql
                SELECT scope_key
                FROM [{TEXT_FACT_SCOPE_TABLE_NAME}]
                ORDER BY created_at DESC, scope_key DESC
                LIMIT 1
            ;
            """
        ) as cursor:
            row = await cursor.fetchone()
    except aiosqlite.Error as error:
        raise text_fact_contract_error(
            f"当前数据库不可读取 {TEXT_FACT_SCOPE_TABLE_NAME}"
        ) from error
    if row is None:
        raise text_fact_contract_error("当前数据库缺少 当前文本事实 scope")
    scope_key = row_str(row, "scope_key", session.db_path)
    try:
        return await session.require_current_text_fact_scope(scope_key)
    except RuntimeError as error:
        raise text_fact_contract_error(str(error)) from error


async def assert_current_scope_fact_schema(
    *,
    session: TargetGameSession,
    scope: TextFactScopeRecord,
) -> None:
    """拒绝当前 scope 内混入不支持的 fact schema_version。"""
    mismatch_count = await read_count(
        session=session,
        sql=f"""
--sql
            SELECT COUNT(*) AS mismatch_count
            FROM [{TEXT_FACTS_TABLE_NAME}] AS facts
            WHERE facts.scope_key = ?
                AND facts.schema_version <> ?
        ;
        """,
        parameters=(scope.scope_key, CURRENT_TEXT_FACT_CONTRACT_VERSION),
        column_name="mismatch_count",
    )
    if mismatch_count:
        raise text_fact_contract_error(
            "当前文本事实与当前文本索引不一致，不能继续执行；"
            + f"发现 {mismatch_count} 条文本事实不符合当前要求，请重新运行 rebuild-text-index"
        )


async def read_count(
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
        raise text_fact_contract_error("当前数据库不可读取 当前文本事实 计数") from error
    if row is None:
        return 0
    return row_int(row, column_name, session.db_path)


def chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """把 fact_id 列表分块，避免 SQLite 参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]


def translation_matches_fact_sql() -> str:
    """返回已保存译文和当前文本事实 身份完全一致的 SQL 条件。"""
    return (
        "translations.fact_id = facts.fact_id "
        "AND translations.source_fact_raw_hash = facts.raw_hash "
        "AND translations.source_fact_translatable_hash = facts.translatable_hash"
    )


def text_fact_from_row(
    row: aiosqlite.Row,
    *,
    session: TargetGameSession,
) -> TextFactRecord:
    """把 SQLite 行转换成 当前文本事实记录。"""
    return TextFactRecord(
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


def item_type_from_text_fact(fact: TextFactRecord) -> ItemType:
    """从 current text fact 读取既有 TranslationItem item_type。"""
    if fact.item_type not in {"long_text", "array", "short_text"}:
        raise text_fact_contract_error(f"当前文本事实 item_type 不受支持: {fact.item_type}")
    return cast(ItemType, fact.item_type)


def text_fact_lines(text: str, *, item_type: ItemType) -> list[str]:
    """把当前单字符串正文转换成既有 TranslationItem 行模型。"""
    if item_type in {"long_text", "array"}:
        return text.split("\n")
    return [text]


def short_text_sample(text: str, *, max_chars: int) -> str:
    """生成报告用短样本，避免错误明细展开长文本。"""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def require_current_index_record(
    *,
    fact: TextFactRecord,
    index_record: TextIndexItemRecord | None,
) -> TextIndexItemRecord:
    """读取当前文本事实对应的当前文本索引定位记录。"""
    if index_record is None:
        raise text_fact_contract_error(
            f"当前文本事实缺少对应的当前文本索引定位记录: {fact.location_path}"
        )
    return index_record


def display_name_from_index_record(record: TextIndexItemRecord) -> str | None:
    """从当前文本索引 locator 中读取地图名。"""
    locator = locator_object_from_index_record(record)
    raw_display_name = locator.get("display_name")
    if raw_display_name is None:
        return None
    if not isinstance(raw_display_name, str):
        raise text_fact_contract_error("当前文本索引 locator_json.display_name 必须是字符串或 null")
    return raw_display_name or None


def terminology_owner_terms_from_index_record(record: TextIndexItemRecord) -> list[str]:
    """从当前文本索引 locator 中读取术语 owner 词。"""
    locator = locator_object_from_index_record(record)
    raw_owner_terms = locator.get("terminology_owner_terms")
    if raw_owner_terms is None:
        raise text_fact_contract_error("当前文本索引 locator_json 缺少 terminology_owner_terms")
    if not isinstance(raw_owner_terms, list):
        raise text_fact_contract_error("当前文本索引 locator_json.terminology_owner_terms 必须是字符串数组")
    owner_terms: list[str] = []
    for index, raw_term in enumerate(raw_owner_terms):
        if not isinstance(raw_term, str):
            raise text_fact_contract_error(
                f"当前文本索引 locator_json.terminology_owner_terms[{index}] 必须是字符串"
            )
        if raw_term:
            owner_terms.append(raw_term)
    return owner_terms


def locator_object_from_index_record(record: TextIndexItemRecord) -> JsonObject:
    """读取当前文本索引 locator JSON 对象。"""
    locator = coerce_json_value(cast(object, json.loads(record.locator_json)))
    if not isinstance(locator, dict):
        raise text_fact_contract_error("当前文本索引 locator_json 必须是对象")
    if "display_name" not in locator:
        raise text_fact_contract_error("当前文本索引 locator_json 缺少 display_name")
    if "terminology_owner_terms" not in locator:
        raise text_fact_contract_error("当前文本索引 locator_json 缺少 terminology_owner_terms")
    return locator


def text_fact_contract_error(detail: str) -> TextFactContractError:
    """构造面向用户的当前文本事实契约错误。"""
    return TextFactContractError(
        f"{detail}。影响：当前文本事实与当前文本索引不一致，不能继续执行。"
        + "下一步：请运行 rebuild-text-index 重新生成当前文本索引。"
    )
