"""Text Fact Contract v2 持久化会话能力。"""

from collections.abc import Sequence

import aiosqlite

from .records import (
    TextFactDomainPayloadV2Record,
    TextFactRenderPartV2Record,
    TextFactScopeV2Record,
    TextFactV2ReadFilter,
    TextFactV2Record,
)
from .rows import row_int, row_str
from .session_base import SessionMixinBase
from .sql import (
    COUNT_TEXT_FACTS_V2,
    COUNT_TEXT_FACTS_V2_OUTSIDE_SCOPE,
    CURRENT_SCHEMA_VERSION,
    DELETE_ALL_TEXT_FACT_DOMAIN_PAYLOADS_V2,
    DELETE_ALL_TEXT_FACT_RENDER_PARTS_V2,
    DELETE_ALL_TEXT_FACT_SCOPES_V2,
    DELETE_ALL_TEXT_FACTS_V2,
    INSERT_TEXT_FACT_DOMAIN_PAYLOAD_V2,
    INSERT_TEXT_FACT_RENDER_PART_V2,
    INSERT_TEXT_FACT_SCOPE_V2,
    INSERT_TEXT_FACT_V2,
    SELECT_TEXT_FACT_SCOPE_V2,
    TEXT_FACT_DOMAIN_PAYLOADS_V2_TABLE_NAME,
    TEXT_FACT_RENDER_PARTS_V2_TABLE_NAME,
    TEXT_FACTS_V2_TABLE_NAME,
)

type SqlParameter = str | int

TEXT_FACT_SELECT_COLUMNS = """
        fact_id,
        schema_version,
        domain,
        location_path,
        source_file,
        source_type,
        item_type,
        role,
        selector,
        raw_text,
        visible_text,
        translatable_text,
        raw_hash,
        visible_hash,
        translatable_hash,
        scope_key
"""


class TextFactRecordSessionMixin(SessionMixinBase):
    """负责 Text Fact Contract v2 表的保存、读取与 scope 校验。"""

    async def replace_text_facts_v2(
        self,
        *,
        scope: TextFactScopeV2Record,
        facts: Sequence[TextFactV2Record],
        render_parts: Sequence[TextFactRenderPartV2Record] = (),
        domain_payloads: Sequence[TextFactDomainPayloadV2Record] = (),
    ) -> None:
        """用一次完整重建结果替换旧 v2 文本事实。"""
        self._validate_text_fact_v2_replace_payload(
            scope=scope,
            facts=facts,
            render_parts=render_parts,
            domain_payloads=domain_payloads,
        )
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACT_DOMAIN_PAYLOADS_V2)
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACT_RENDER_PARTS_V2)
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACTS_V2)
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACT_SCOPES_V2)
        _ = await self.connection.execute(
            INSERT_TEXT_FACT_SCOPE_V2,
            self._serialize_text_fact_scope_v2(scope),
        )
        if facts:
            _ = await self.connection.executemany(
                INSERT_TEXT_FACT_V2,
                [self._serialize_text_fact_v2(fact) for fact in _sort_text_facts(facts)],
            )
        if render_parts:
            _ = await self.connection.executemany(
                INSERT_TEXT_FACT_RENDER_PART_V2,
                [
                    self._serialize_text_fact_render_part_v2(part)
                    for part in _sort_text_fact_render_parts(render_parts)
                ],
            )
        if domain_payloads:
            _ = await self.connection.executemany(
                INSERT_TEXT_FACT_DOMAIN_PAYLOAD_V2,
                [
                    self._serialize_text_fact_domain_payload_v2(payload)
                    for payload in _sort_text_fact_domain_payloads(domain_payloads)
                ],
            )
        await self.commit()

    async def read_text_fact_scope_v2(self, scope_key: str) -> TextFactScopeV2Record | None:
        """读取指定 v2 scope 元数据；scope 缺失时返回空。"""
        async with self.connection.execute(SELECT_TEXT_FACT_SCOPE_V2, (scope_key,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._text_fact_scope_v2_from_row(row)

    async def require_current_text_fact_scope_v2(self, scope_key: str) -> TextFactScopeV2Record:
        """读取并校验当前 v2 scope；旧库或不一致状态必须显式失败。"""
        try:
            scope = await self.read_text_fact_scope_v2(scope_key)
        except aiosqlite.Error as error:
            raise _text_fact_v2_scope_error(
                f"text_fact_scope_v2 不可读取或缺失，当前数据库还没有 v2 文本事实 scope: {scope_key}"
            ) from error
        if scope is None:
            raise _text_fact_v2_scope_error(
                f"没有找到 text fact v2 scope: {scope_key}"
            )
        if scope.schema_version != CURRENT_SCHEMA_VERSION:
            raise _text_fact_v2_scope_error(
                "text fact v2 scope 的 schema version 不受支持: "
                + f"数据库是 {scope.schema_version}，当前工具支持 {CURRENT_SCHEMA_VERSION}"
            )
        try:
            async with self.connection.execute(COUNT_TEXT_FACTS_V2_OUTSIDE_SCOPE, (scope_key,)) as cursor:
                row = await cursor.fetchone()
        except aiosqlite.Error as error:
            raise _text_fact_v2_scope_error(
                f"{TEXT_FACTS_V2_TABLE_NAME} 不可读取或缺失，无法确认当前 v2 文本事实 scope"
            ) from error
        mismatch_count = 0 if row is None else row_int(row, "mismatch_count", self.db_path)
        if mismatch_count > 0:
            raise _text_fact_v2_scope_error(
                f"text fact v2 scope 不一致: {mismatch_count} 条文本事实不属于当前 scope {scope_key}"
            )
        return scope

    async def read_text_facts_v2(
        self,
        filter: TextFactV2ReadFilter | None = None,
    ) -> list[TextFactV2Record]:
        """按稳定顺序读取 v2 文本事实。"""
        where_clause, parameters = _build_text_fact_filter_sql(filter)
        query = f"""
--sql
            SELECT
{TEXT_FACT_SELECT_COLUMNS}
            FROM [{TEXT_FACTS_V2_TABLE_NAME}]
            {where_clause}
            ORDER BY domain, location_path, fact_id
        ;
        """
        async with self.connection.execute(query, tuple(parameters)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_fact_v2_from_row(row) for row in rows]

    async def read_text_fact_render_parts_v2(
        self,
        fact_ids: Sequence[str],
    ) -> list[TextFactRenderPartV2Record]:
        """按 fact_id 和 part_order 稳定读取 v2 渲染片段。"""
        unique_fact_ids = sorted(set(fact_ids))
        if not unique_fact_ids:
            return []
        placeholders = ", ".join("?" for _fact_id in unique_fact_ids)
        query = f"""
--sql
            SELECT fact_id, part_order, part_kind, raw_text, semantic_text, template_key
            FROM [{TEXT_FACT_RENDER_PARTS_V2_TABLE_NAME}]
            WHERE fact_id IN ({placeholders})
            ORDER BY fact_id, part_order
        ;
        """
        async with self.connection.execute(query, tuple(unique_fact_ids)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_fact_render_part_v2_from_row(row) for row in rows]

    async def read_text_fact_domain_payloads_v2(
        self,
        fact_ids: Sequence[str],
    ) -> list[TextFactDomainPayloadV2Record]:
        """按 fact_id 稳定读取 v2 领域 payload。"""
        unique_fact_ids = sorted(set(fact_ids))
        if not unique_fact_ids:
            return []
        placeholders = ", ".join("?" for _fact_id in unique_fact_ids)
        query = f"""
--sql
            SELECT fact_id, payload_json
            FROM [{TEXT_FACT_DOMAIN_PAYLOADS_V2_TABLE_NAME}]
            WHERE fact_id IN ({placeholders})
            ORDER BY fact_id
        ;
        """
        async with self.connection.execute(query, tuple(unique_fact_ids)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_fact_domain_payload_v2_from_row(row) for row in rows]

    async def count_text_facts_v2(self) -> int:
        """统计当前 v2 文本事实数量。"""
        async with self.connection.execute(COUNT_TEXT_FACTS_V2) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "fact_count", self.db_path)

    def _validate_text_fact_v2_replace_payload(
        self,
        *,
        scope: TextFactScopeV2Record,
        facts: Sequence[TextFactV2Record],
        render_parts: Sequence[TextFactRenderPartV2Record],
        domain_payloads: Sequence[TextFactDomainPayloadV2Record],
    ) -> None:
        """在写库前显式拒绝不一致的 v2 替换数据。"""
        fact_ids = {fact.fact_id for fact in facts}
        for fact in facts:
            if fact.schema_version != scope.schema_version:
                raise ValueError("v2 文本事实 schema_version 必须等于 scope schema_version")
            if fact.scope_key != scope.scope_key:
                raise ValueError("v2 文本事实 scope_key 必须等于当前 scope_key")
        for part in render_parts:
            if part.fact_id not in fact_ids:
                raise ValueError("v2 渲染片段必须引用本次替换中的文本事实")
        for payload in domain_payloads:
            if payload.fact_id not in fact_ids:
                raise ValueError("v2 领域 payload 必须引用本次替换中的文本事实")

    def _serialize_text_fact_scope_v2(self, scope: TextFactScopeV2Record) -> tuple[SqlParameter, ...]:
        """把 v2 scope 转换为 SQLite 参数。"""
        return (
            scope.scope_key,
            scope.schema_version,
            scope.scope_hash,
            scope.source_snapshot_hash,
            scope.rule_hash,
            scope.text_rules_hash,
            scope.created_at,
        )

    def _serialize_text_fact_v2(self, fact: TextFactV2Record) -> tuple[SqlParameter, ...]:
        """把 v2 文本事实转换为 SQLite 参数。"""
        return (
            fact.fact_id,
            fact.schema_version,
            fact.domain,
            fact.location_path,
            fact.source_file,
            fact.source_type,
            fact.item_type,
            fact.role,
            fact.selector,
            fact.raw_text,
            fact.visible_text,
            fact.translatable_text,
            fact.raw_hash,
            fact.visible_hash,
            fact.translatable_hash,
            fact.scope_key,
        )

    def _serialize_text_fact_render_part_v2(
        self,
        part: TextFactRenderPartV2Record,
    ) -> tuple[SqlParameter, ...]:
        """把 v2 渲染片段转换为 SQLite 参数。"""
        return (
            part.fact_id,
            part.part_order,
            part.part_kind,
            part.raw_text,
            part.semantic_text,
            part.template_key,
        )

    def _serialize_text_fact_domain_payload_v2(
        self,
        payload: TextFactDomainPayloadV2Record,
    ) -> tuple[SqlParameter, ...]:
        """把 v2 领域 payload 转换为 SQLite 参数。"""
        return (payload.fact_id, payload.payload_json)

    def _text_fact_scope_v2_from_row(self, row: aiosqlite.Row) -> TextFactScopeV2Record:
        """把数据库行还原为 v2 scope。"""
        return TextFactScopeV2Record(
            scope_key=row_str(row, "scope_key", self.db_path),
            schema_version=row_int(row, "schema_version", self.db_path),
            scope_hash=row_str(row, "scope_hash", self.db_path),
            source_snapshot_hash=row_str(row, "source_snapshot_hash", self.db_path),
            rule_hash=row_str(row, "rule_hash", self.db_path),
            text_rules_hash=row_str(row, "text_rules_hash", self.db_path),
            created_at=row_str(row, "created_at", self.db_path),
        )

    def _text_fact_v2_from_row(self, row: aiosqlite.Row) -> TextFactV2Record:
        """把数据库行还原为 v2 文本事实。"""
        return TextFactV2Record(
            fact_id=row_str(row, "fact_id", self.db_path),
            schema_version=row_int(row, "schema_version", self.db_path),
            domain=row_str(row, "domain", self.db_path),
            location_path=row_str(row, "location_path", self.db_path),
            source_file=row_str(row, "source_file", self.db_path),
            source_type=row_str(row, "source_type", self.db_path),
            item_type=row_str(row, "item_type", self.db_path),
            role=row_str(row, "role", self.db_path),
            selector=row_str(row, "selector", self.db_path),
            raw_text=row_str(row, "raw_text", self.db_path),
            visible_text=row_str(row, "visible_text", self.db_path),
            translatable_text=row_str(row, "translatable_text", self.db_path),
            raw_hash=row_str(row, "raw_hash", self.db_path),
            visible_hash=row_str(row, "visible_hash", self.db_path),
            translatable_hash=row_str(row, "translatable_hash", self.db_path),
            scope_key=row_str(row, "scope_key", self.db_path),
        )

    def _text_fact_render_part_v2_from_row(
        self,
        row: aiosqlite.Row,
    ) -> TextFactRenderPartV2Record:
        """把数据库行还原为 v2 渲染片段。"""
        return TextFactRenderPartV2Record(
            fact_id=row_str(row, "fact_id", self.db_path),
            part_order=row_int(row, "part_order", self.db_path),
            part_kind=row_str(row, "part_kind", self.db_path),
            raw_text=row_str(row, "raw_text", self.db_path),
            semantic_text=row_str(row, "semantic_text", self.db_path),
            template_key=row_str(row, "template_key", self.db_path),
        )

    def _text_fact_domain_payload_v2_from_row(
        self,
        row: aiosqlite.Row,
    ) -> TextFactDomainPayloadV2Record:
        """把数据库行还原为 v2 领域 payload。"""
        return TextFactDomainPayloadV2Record(
            fact_id=row_str(row, "fact_id", self.db_path),
            payload_json=row_str(row, "payload_json", self.db_path),
        )


def _build_text_fact_filter_sql(
    filter: TextFactV2ReadFilter | None,
) -> tuple[str, list[SqlParameter]]:
    """把 v2 fact 过滤条件转换成参数化 SQL 片段。"""
    if filter is None:
        return "", []
    clauses: list[str] = []
    parameters: list[SqlParameter] = []
    if filter.domain is not None:
        clauses.append("domain = ?")
        parameters.append(filter.domain)
    if filter.source_file is not None:
        clauses.append("source_file = ?")
        parameters.append(filter.source_file)
    if filter.scope_key is not None:
        clauses.append("scope_key = ?")
        parameters.append(filter.scope_key)
    if filter.location_paths:
        location_paths = sorted(set(filter.location_paths))
        placeholders = ", ".join("?" for _path in location_paths)
        clauses.append(f"location_path IN ({placeholders})")
        parameters.extend(location_paths)
    if not clauses:
        return "", parameters
    return "WHERE " + " AND ".join(clauses), parameters


def _text_fact_v2_scope_error(detail: str) -> RuntimeError:
    """构造 v2 scope 契约失败错误，包含影响和下一步命令。"""
    message = (
        f"{detail}。影响：当前命令需要读取当前 text fact v2 scope，不能继续使用旧索引或不一致事实。"
        + "下一步：请运行 rebuild-text-index 重新生成当前文本索引。"
    )
    return RuntimeError(message)


def _sort_text_facts(records: Sequence[TextFactV2Record]) -> list[TextFactV2Record]:
    """按稳定顺序排列 v2 文本事实。"""
    return sorted(records, key=lambda record: (record.domain, record.location_path, record.fact_id))


def _sort_text_fact_render_parts(
    records: Sequence[TextFactRenderPartV2Record],
) -> list[TextFactRenderPartV2Record]:
    """按稳定顺序排列 v2 渲染片段。"""
    return sorted(records, key=lambda record: (record.fact_id, record.part_order))


def _sort_text_fact_domain_payloads(
    records: Sequence[TextFactDomainPayloadV2Record],
) -> list[TextFactDomainPayloadV2Record]:
    """按稳定顺序排列 v2 领域 payload。"""
    return sorted(records, key=lambda record: record.fact_id)


__all__ = ["TextFactRecordSessionMixin"]
