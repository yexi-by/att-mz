"""当前文本事实契约 持久化会话能力。"""

from collections.abc import Sequence

import aiosqlite

from .records import (
    TextFactDomainPayloadRecord,
    TextFactRenderPartRecord,
    TextFactScopeRecord,
    TextFactReadFilter,
    TextFactRecord,
)
from .rows import row_int, row_str
from .session_base import SessionMixinBase
from .sql import (
    COUNT_TEXT_FACTS,
    COUNT_TEXT_FACTS_OUTSIDE_SCOPE,
    DELETE_ALL_TEXT_FACT_DOMAIN_PAYLOADS,
    DELETE_ALL_TEXT_FACT_RENDER_PARTS,
    DELETE_ALL_TEXT_FACT_SCOPES,
    DELETE_ALL_TEXT_FACTS,
    INSERT_TEXT_FACT_DOMAIN_PAYLOAD,
    INSERT_TEXT_FACT_RENDER_PART,
    INSERT_TEXT_FACT_SCOPE,
    INSERT_TEXT_FACT,
    SELECT_TEXT_FACT_SCOPE,
    TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME,
    TEXT_FACT_RENDER_PARTS_TABLE_NAME,
    CURRENT_TEXT_FACT_CONTRACT_VERSION,
    TEXT_FACTS_TABLE_NAME,
)

type SqlParameter = str | int
PATH_QUERY_BATCH_SIZE = 500

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
    """负责 当前文本事实契约 表的保存、读取与 scope 校验。"""

    async def replace_text_facts(
        self,
        *,
        scope: TextFactScopeRecord,
        facts: Sequence[TextFactRecord],
        render_parts: Sequence[TextFactRenderPartRecord] = (),
        domain_payloads: Sequence[TextFactDomainPayloadRecord] = (),
    ) -> None:
        """用一次完整重建结果替换当前文本事实记录。"""
        self._validate_text_fact_replace_payload(
            scope=scope,
            facts=facts,
            render_parts=render_parts,
            domain_payloads=domain_payloads,
        )
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACT_DOMAIN_PAYLOADS)
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACT_RENDER_PARTS)
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACTS)
        _ = await self.connection.execute(DELETE_ALL_TEXT_FACT_SCOPES)
        _ = await self.connection.execute(
            INSERT_TEXT_FACT_SCOPE,
            self._serialize_text_fact_scope(scope),
        )
        if facts:
            _ = await self.connection.executemany(
                INSERT_TEXT_FACT,
                [self._serialize_text_fact(fact) for fact in _sort_text_facts(facts)],
            )
        if render_parts:
            _ = await self.connection.executemany(
                INSERT_TEXT_FACT_RENDER_PART,
                [
                    self._serialize_text_fact_render_part(part)
                    for part in _sort_text_fact_render_parts(render_parts)
                ],
            )
        if domain_payloads:
            _ = await self.connection.executemany(
                INSERT_TEXT_FACT_DOMAIN_PAYLOAD,
                [
                    self._serialize_text_fact_domain_payload(payload)
                    for payload in _sort_text_fact_domain_payloads(domain_payloads)
                ],
            )
        await self.commit()

    async def read_text_fact_scope(self, scope_key: str) -> TextFactScopeRecord | None:
        """读取指定 当前文本事实 scope 元数据；scope 缺失时返回空。"""
        async with self.connection.execute(SELECT_TEXT_FACT_SCOPE, (scope_key,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._text_fact_scope_from_row(row)

    async def require_current_text_fact_scope(self, scope_key: str) -> TextFactScopeRecord:
        """读取并校验当前文本事实 scope；缺失或不一致状态必须显式失败。"""
        try:
            scope = await self.read_text_fact_scope(scope_key)
        except aiosqlite.Error as error:
            raise _text_fact_scope_error(
                f"text_fact_scope 不可读取或缺失，当前数据库还没有 当前文本事实 scope: {scope_key}"
            ) from error
        if scope is None:
            raise _text_fact_scope_error(
                f"没有找到 当前文本事实 scope: {scope_key}"
            )
        if scope.schema_version != CURRENT_TEXT_FACT_CONTRACT_VERSION:
            raise _text_fact_scope_error(
                "当前文本事实范围不符合当前要求，不能继续执行；请重新运行 rebuild-text-index"
            )
        try:
            async with self.connection.execute(COUNT_TEXT_FACTS_OUTSIDE_SCOPE, (scope_key,)) as cursor:
                row = await cursor.fetchone()
        except aiosqlite.Error as error:
            raise _text_fact_scope_error(
                f"{TEXT_FACTS_TABLE_NAME} 不可读取或缺失，无法确认当前文本事实范围"
            ) from error
        mismatch_count = 0 if row is None else row_int(row, "mismatch_count", self.db_path)
        if mismatch_count > 0:
            raise _text_fact_scope_error(
                f"当前文本事实 scope 不一致: {mismatch_count} 条文本事实不属于当前 scope {scope_key}"
            )
        return scope

    async def read_text_facts(
        self,
        filter: TextFactReadFilter | None = None,
    ) -> list[TextFactRecord]:
        """按稳定顺序读取 当前文本事实。"""
        if filter is not None and filter.location_paths:
            records: list[TextFactRecord] = []
            location_paths = sorted(set(filter.location_paths))
            for batch in _chunks(location_paths, PATH_QUERY_BATCH_SIZE):
                records.extend(await self._read_text_facts_batch(filter=filter, location_paths=batch))
            return _sort_text_facts(records)
        return await self._read_text_facts_batch(filter=filter)

    async def _read_text_facts_batch(
        self,
        *,
        filter: TextFactReadFilter | None,
        location_paths: Sequence[str] = (),
    ) -> list[TextFactRecord]:
        """读取单批 当前文本事实。"""
        where_clause, parameters = _build_text_fact_filter_sql(filter, location_paths=location_paths)
        query = f"""
--sql
            SELECT
{TEXT_FACT_SELECT_COLUMNS}
            FROM [{TEXT_FACTS_TABLE_NAME}]
            {where_clause}
            ORDER BY domain, location_path, fact_id
        ;
        """
        async with self.connection.execute(query, tuple(parameters)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_fact_from_row(row) for row in rows]

    async def read_text_fact_render_parts(
        self,
        fact_ids: Sequence[str],
    ) -> list[TextFactRenderPartRecord]:
        """按 fact_id 和 part_order 稳定读取 当前渲染片段。"""
        unique_fact_ids = sorted(set(fact_ids))
        if not unique_fact_ids:
            return []
        records: list[TextFactRenderPartRecord] = []
        for batch in _chunks(unique_fact_ids, PATH_QUERY_BATCH_SIZE):
            records.extend(await self._read_text_fact_render_parts_batch(batch))
        return _sort_text_fact_render_parts(records)

    async def _read_text_fact_render_parts_batch(
        self,
        fact_ids: Sequence[str],
    ) -> list[TextFactRenderPartRecord]:
        """读取单批 当前渲染片段。"""
        placeholders = ", ".join("?" for _fact_id in fact_ids)
        query = f"""
--sql
            SELECT fact_id, part_order, part_kind, raw_text, semantic_text, template_key
            FROM [{TEXT_FACT_RENDER_PARTS_TABLE_NAME}]
            WHERE fact_id IN ({placeholders})
            ORDER BY fact_id, part_order
        ;
        """
        async with self.connection.execute(query, tuple(fact_ids)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_fact_render_part_from_row(row) for row in rows]

    async def read_text_fact_domain_payloads(
        self,
        fact_ids: Sequence[str],
    ) -> list[TextFactDomainPayloadRecord]:
        """按 fact_id 稳定读取 当前领域 payload。"""
        unique_fact_ids = sorted(set(fact_ids))
        if not unique_fact_ids:
            return []
        records: list[TextFactDomainPayloadRecord] = []
        for batch in _chunks(unique_fact_ids, PATH_QUERY_BATCH_SIZE):
            records.extend(await self._read_text_fact_domain_payloads_batch(batch))
        return _sort_text_fact_domain_payloads(records)

    async def _read_text_fact_domain_payloads_batch(
        self,
        fact_ids: Sequence[str],
    ) -> list[TextFactDomainPayloadRecord]:
        """读取单批 当前领域 payload。"""
        placeholders = ", ".join("?" for _fact_id in fact_ids)
        query = f"""
--sql
            SELECT fact_id, payload_json
            FROM [{TEXT_FACT_DOMAIN_PAYLOADS_TABLE_NAME}]
            WHERE fact_id IN ({placeholders})
            ORDER BY fact_id
        ;
        """
        async with self.connection.execute(query, tuple(fact_ids)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_fact_domain_payload_from_row(row) for row in rows]

    async def count_text_facts(self) -> int:
        """统计当前文本事实数量。"""
        async with self.connection.execute(COUNT_TEXT_FACTS) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "fact_count", self.db_path)

    def _validate_text_fact_replace_payload(
        self,
        *,
        scope: TextFactScopeRecord,
        facts: Sequence[TextFactRecord],
        render_parts: Sequence[TextFactRenderPartRecord],
        domain_payloads: Sequence[TextFactDomainPayloadRecord],
    ) -> None:
        """在写库前显式拒绝不一致的当前文本事实替换数据。"""
        fact_ids: set[str] = set()
        for fact in facts:
            if fact.fact_id in fact_ids:
                raise ValueError(f"当前文本事实 fact_id 重复: {fact.fact_id}")
            fact_ids.add(fact.fact_id)
            if fact.schema_version != scope.schema_version:
                raise ValueError("当前文本事实 schema_version 必须等于 scope schema_version")
            if fact.scope_key != scope.scope_key:
                raise ValueError("当前文本事实 scope_key 必须等于当前 scope_key")
        render_part_keys: set[tuple[str, int]] = set()
        for part in render_parts:
            if part.fact_id not in fact_ids:
                raise ValueError("当前渲染片段必须引用本次替换中的文本事实")
            render_part_key = (part.fact_id, part.part_order)
            if render_part_key in render_part_keys:
                raise ValueError(f"当前渲染片段重复: fact_id={part.fact_id}, part_order={part.part_order}")
            render_part_keys.add(render_part_key)
        payload_fact_ids: set[str] = set()
        for payload in domain_payloads:
            if payload.fact_id not in fact_ids:
                raise ValueError("当前领域 payload 必须引用本次替换中的文本事实")
            if payload.fact_id in payload_fact_ids:
                raise ValueError(f"当前领域 payload 重复: fact_id={payload.fact_id}")
            payload_fact_ids.add(payload.fact_id)

    def _serialize_text_fact_scope(self, scope: TextFactScopeRecord) -> tuple[SqlParameter, ...]:
        """把 当前文本事实 scope 转换为 SQLite 参数。"""
        return (
            scope.scope_key,
            scope.schema_version,
            scope.scope_hash,
            scope.source_snapshot_hash,
            scope.rule_hash,
            scope.text_rules_hash,
            scope.created_at,
        )

    def _serialize_text_fact(self, fact: TextFactRecord) -> tuple[SqlParameter, ...]:
        """把 当前文本事实转换为 SQLite 参数。"""
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

    def _serialize_text_fact_render_part(
        self,
        part: TextFactRenderPartRecord,
    ) -> tuple[SqlParameter, ...]:
        """把 当前渲染片段转换为 SQLite 参数。"""
        return (
            part.fact_id,
            part.part_order,
            part.part_kind,
            part.raw_text,
            part.semantic_text,
            part.template_key,
        )

    def _serialize_text_fact_domain_payload(
        self,
        payload: TextFactDomainPayloadRecord,
    ) -> tuple[SqlParameter, ...]:
        """把 当前领域 payload 转换为 SQLite 参数。"""
        return (payload.fact_id, payload.payload_json)

    def _text_fact_scope_from_row(self, row: aiosqlite.Row) -> TextFactScopeRecord:
        """把数据库行还原为 当前文本事实 scope。"""
        return TextFactScopeRecord(
            scope_key=row_str(row, "scope_key", self.db_path),
            schema_version=row_int(row, "schema_version", self.db_path),
            scope_hash=row_str(row, "scope_hash", self.db_path),
            source_snapshot_hash=row_str(row, "source_snapshot_hash", self.db_path),
            rule_hash=row_str(row, "rule_hash", self.db_path),
            text_rules_hash=row_str(row, "text_rules_hash", self.db_path),
            created_at=row_str(row, "created_at", self.db_path),
        )

    def _text_fact_from_row(self, row: aiosqlite.Row) -> TextFactRecord:
        """把数据库行还原为 当前文本事实。"""
        return TextFactRecord(
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

    def _text_fact_render_part_from_row(
        self,
        row: aiosqlite.Row,
    ) -> TextFactRenderPartRecord:
        """把数据库行还原为 当前渲染片段。"""
        return TextFactRenderPartRecord(
            fact_id=row_str(row, "fact_id", self.db_path),
            part_order=row_int(row, "part_order", self.db_path),
            part_kind=row_str(row, "part_kind", self.db_path),
            raw_text=row_str(row, "raw_text", self.db_path),
            semantic_text=row_str(row, "semantic_text", self.db_path),
            template_key=row_str(row, "template_key", self.db_path),
        )

    def _text_fact_domain_payload_from_row(
        self,
        row: aiosqlite.Row,
    ) -> TextFactDomainPayloadRecord:
        """把数据库行还原为 当前领域 payload。"""
        return TextFactDomainPayloadRecord(
            fact_id=row_str(row, "fact_id", self.db_path),
            payload_json=row_str(row, "payload_json", self.db_path),
        )


def _build_text_fact_filter_sql(
    filter: TextFactReadFilter | None,
    *,
    location_paths: Sequence[str] = (),
) -> tuple[str, list[SqlParameter]]:
    """把 current text fact 过滤条件转换成参数化 SQL 片段。"""
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
    selected_location_paths = location_paths if location_paths else filter.location_paths
    if selected_location_paths:
        unique_location_paths = sorted(set(selected_location_paths))
        placeholders = ", ".join("?" for _path in unique_location_paths)
        clauses.append(f"location_path IN ({placeholders})")
        parameters.extend(unique_location_paths)
    if not clauses:
        return "", parameters
    return "WHERE " + " AND ".join(clauses), parameters


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """把字符串列表分块，避免单条 SQLite 查询参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]


def _text_fact_scope_error(detail: str) -> RuntimeError:
    """构造 当前文本事实 scope 契约失败错误，包含影响和下一步命令。"""
    message = (
        f"{detail}。影响：当前命令需要读取当前文本事实 scope，无法在索引缺失或事实不一致时继续。"
        + "下一步：请运行 rebuild-text-index 重新生成当前文本索引。"
    )
    return RuntimeError(message)


def _sort_text_facts(records: Sequence[TextFactRecord]) -> list[TextFactRecord]:
    """按稳定顺序排列 当前文本事实。"""
    return sorted(records, key=lambda record: (record.domain, record.location_path, record.fact_id))


def _sort_text_fact_render_parts(
    records: Sequence[TextFactRenderPartRecord],
) -> list[TextFactRenderPartRecord]:
    """按稳定顺序排列 当前渲染片段。"""
    return sorted(records, key=lambda record: (record.fact_id, record.part_order))


def _sort_text_fact_domain_payloads(
    records: Sequence[TextFactDomainPayloadRecord],
) -> list[TextFactDomainPayloadRecord]:
    """按稳定顺序排列 当前领域 payload。"""
    return sorted(records, key=lambda record: record.fact_id)


__all__ = ["TextFactRecordSessionMixin"]
