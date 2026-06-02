"""持久文本范围索引会话能力。"""

import json
from collections.abc import Sequence
from typing import cast

import aiosqlite

from .records import TextIndexInvalidationRecord, TextIndexItemRecord, TextIndexMetadata
from .rows import decode_string_list, row_int, row_item_type, row_optional_str, row_str
from .session_base import SessionMixinBase
from .sql import (
    DELETE_ALL_TEXT_INDEX_INVALIDATIONS,
    DELETE_ALL_TEXT_INDEX_ITEMS,
    DELETE_ALL_TEXT_INDEX_META,
    COUNT_PENDING_TEXT_INDEX_QUALITY_ERRORS,
    COUNT_TEXT_INDEX_TRANSLATED_ITEMS,
    INSERT_TEXT_INDEX_INVALIDATION,
    INSERT_TEXT_INDEX_ITEM,
    SELECT_PENDING_TEXT_INDEX_COUNT,
    SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_TYPE_COUNTS,
    SELECT_PENDING_TEXT_INDEX_ITEMS,
    SELECT_TEXT_INDEX_INVALIDATIONS,
    SELECT_TEXT_INDEX_ITEM_COUNT,
    SELECT_TEXT_INDEX_ITEMS,
    SELECT_TEXT_INDEX_LOCATION_PATHS,
    SELECT_TEXT_INDEX_META,
    TEXT_INDEX_ITEMS_TABLE_NAME,
    TEXT_INDEX_META_KEY,
    UPSERT_TEXT_INDEX_META,
)


type SqlParameter = str | int | None
PATH_QUERY_BATCH_SIZE = 500


class TextIndexRecordSessionMixin(SessionMixinBase):
    """负责当前翻译源视图索引的保存、读取与失效标记。"""

    async def replace_text_index(
        self,
        *,
        metadata: TextIndexMetadata,
        items: Sequence[TextIndexItemRecord],
    ) -> None:
        """用一次完整索引重建结果替换旧索引。"""
        if metadata.item_count != len(items):
            raise ValueError("文本索引元信息 item_count 必须等于索引项数量")

        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_INVALIDATIONS)
        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_META)
        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_ITEMS)
        _ = await self.connection.execute(
            UPSERT_TEXT_INDEX_META,
            (
                TEXT_INDEX_META_KEY,
                metadata.source_snapshot_fingerprint,
                metadata.rules_fingerprint,
                metadata.item_count,
                _encode_workflow_gate_scope_hashes(metadata.workflow_gate_scope_hashes),
                metadata.created_at,
            ),
        )
        if items:
            _ = await self.connection.executemany(
                INSERT_TEXT_INDEX_ITEM,
                [self._serialize_text_index_item(item) for item in items],
            )
        await self.connection.commit()

    async def clear_text_index(self) -> None:
        """清空当前文本范围索引与失效记录。"""
        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_INVALIDATIONS)
        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_META)
        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_ITEMS)
        await self.connection.commit()

    async def read_text_index_metadata(self) -> TextIndexMetadata | None:
        """读取当前文本范围索引元信息；索引缺失时返回空。"""
        async with self.connection.execute(SELECT_TEXT_INDEX_META, (TEXT_INDEX_META_KEY,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return TextIndexMetadata(
            source_snapshot_fingerprint=row_str(row, "source_snapshot_fingerprint", self.db_path),
            rules_fingerprint=row_str(row, "rules_fingerprint", self.db_path),
            item_count=row_int(row, "item_count", self.db_path),
            workflow_gate_scope_hashes=_decode_workflow_gate_scope_hashes(
                row_str(row, "workflow_gate_scope_hashes", self.db_path)
            ),
            created_at=row_str(row, "created_at", self.db_path),
        )

    async def read_text_index_items(self) -> list[TextIndexItemRecord]:
        """读取全部文本范围索引项。"""
        async with self.connection.execute(SELECT_TEXT_INDEX_ITEMS) as cursor:
            rows = await cursor.fetchall()
        return [self._text_index_item_from_row(row) for row in rows]

    async def count_text_index_items(self) -> int:
        """统计当前文本范围索引项数量。"""
        async with self.connection.execute(SELECT_TEXT_INDEX_ITEM_COUNT) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "item_count", self.db_path)

    async def count_pending_text_index_items(self) -> int:
        """统计当前索引中尚未保存译文且可写回的条目数量。"""
        async with self.connection.execute(SELECT_PENDING_TEXT_INDEX_COUNT) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "pending_count", self.db_path)

    async def count_text_index_translated_items(self) -> int:
        """统计当前索引范围内已有译文的条目数量。"""
        async with self.connection.execute(COUNT_TEXT_INDEX_TRANSLATED_ITEMS) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "translated_count", self.db_path)

    async def count_pending_text_index_quality_errors(self, run_id: str) -> int:
        """统计当前索引 pending 范围内最新运行的质量错误数量。"""
        async with self.connection.execute(COUNT_PENDING_TEXT_INDEX_QUALITY_ERRORS, (run_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "quality_error_count", self.db_path)

    async def count_pending_text_index_quality_errors_by_type(self, run_id: str) -> dict[str, int]:
        """按错误类型统计当前索引 pending 范围内的质量错误。"""
        async with self.connection.execute(SELECT_PENDING_TEXT_INDEX_QUALITY_ERROR_TYPE_COUNTS, (run_id,)) as cursor:
            rows = await cursor.fetchall()
        return {
            row_str(row, "error_type", self.db_path): row_int(row, "error_count", self.db_path)
            for row in rows
        }

    async def read_pending_text_index_items(
        self,
        *,
        limit: int | None,
    ) -> list[TextIndexItemRecord]:
        """按索引顺序读取尚未保存译文且可写回的条目，在 SQL 层应用上限。"""
        sql_limit = -1
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit 必须是正整数")
            sql_limit = limit
        async with self.connection.execute(SELECT_PENDING_TEXT_INDEX_ITEMS, (sql_limit,)) as cursor:
            rows = await cursor.fetchall()
        return [self._text_index_item_from_row(row) for row in rows]

    async def read_text_index_items_by_paths(
        self,
        location_paths: Sequence[str],
    ) -> list[TextIndexItemRecord]:
        """按精确定位路径读取文本范围索引项。"""
        unique_paths = sorted(set(location_paths))
        if not unique_paths:
            return []
        items_by_path: dict[str, TextIndexItemRecord] = {}
        for batch in _chunks(unique_paths, PATH_QUERY_BATCH_SIZE):
            placeholders = ", ".join("?" for _path in batch)
            sql = f"""
--sql
                SELECT
                    location_path,
                    item_type,
                    role,
                    original_lines,
                    source_line_paths,
                    source_type,
                    source_file,
                    writable,
                    source_snapshot_fingerprint,
                    rules_fingerprint,
                    locator_json
                FROM [{TEXT_INDEX_ITEMS_TABLE_NAME}]
                WHERE location_path IN ({placeholders})
            ;
            """
            async with self.connection.execute(sql, tuple(batch)) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                item = self._text_index_item_from_row(row)
                items_by_path[item.location_path] = item
        return [items_by_path[path] for path in unique_paths if path in items_by_path]

    async def read_text_index_location_paths(self) -> set[str]:
        """读取当前文本范围索引中的全部定位路径。"""
        async with self.connection.execute(SELECT_TEXT_INDEX_LOCATION_PATHS) as cursor:
            rows = await cursor.fetchall()
        return {row_str(row, "location_path", self.db_path) for row in rows}

    async def replace_text_index_invalidations(
        self,
        records: Sequence[TextIndexInvalidationRecord],
    ) -> None:
        """替换文本范围索引失效原因。"""
        _ = await self.connection.execute(DELETE_ALL_TEXT_INDEX_INVALIDATIONS)
        if records:
            _ = await self.connection.executemany(
                INSERT_TEXT_INDEX_INVALIDATION,
                [
                    (
                        record.reason_key,
                        record.detail,
                        record.created_at,
                    )
                    for record in records
                ],
            )
        await self.connection.commit()

    async def read_text_index_invalidations(self) -> list[TextIndexInvalidationRecord]:
        """读取文本范围索引失效原因。"""
        async with self.connection.execute(SELECT_TEXT_INDEX_INVALIDATIONS) as cursor:
            rows = await cursor.fetchall()
        return [
            TextIndexInvalidationRecord(
                reason_key=row_str(row, "reason_key", self.db_path),
                detail=row_str(row, "detail", self.db_path),
                created_at=row_str(row, "created_at", self.db_path),
            )
            for row in rows
        ]

    def _serialize_text_index_item(self, item: TextIndexItemRecord) -> tuple[SqlParameter, ...]:
        """把索引项转换为 SQLite 参数。"""
        return (
            item.location_path,
            item.item_type,
            item.role,
            json.dumps(item.original_lines, ensure_ascii=False),
            json.dumps(item.source_line_paths, ensure_ascii=False),
            item.source_type,
            item.source_file,
            1 if item.writable else 0,
            item.source_snapshot_fingerprint,
            item.rules_fingerprint,
            item.locator_json,
        )

    def _text_index_item_from_row(self, row: aiosqlite.Row) -> TextIndexItemRecord:
        """把数据库行还原为文本范围索引项。"""
        writable = row_int(row, "writable", self.db_path)
        if writable not in {0, 1}:
            raise TypeError(f"数据库字段 writable 不是有效布尔值: {self.db_path}")
        return TextIndexItemRecord(
            location_path=row_str(row, "location_path", self.db_path),
            item_type=row_item_type(row, "item_type", self.db_path),
            role=row_optional_str(row, "role", self.db_path),
            original_lines=decode_string_list(row_str(row, "original_lines", self.db_path), "original_lines"),
            source_line_paths=decode_string_list(
                row_str(row, "source_line_paths", self.db_path),
                "source_line_paths",
            ),
            source_type=row_str(row, "source_type", self.db_path),
            source_file=row_str(row, "source_file", self.db_path),
            writable=writable == 1,
            source_snapshot_fingerprint=row_str(row, "source_snapshot_fingerprint", self.db_path),
            rules_fingerprint=row_str(row, "rules_fingerprint", self.db_path),
            locator_json=row_str(row, "locator_json", self.db_path),
        )


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """把路径列表分块，避免 SQLite 参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]


def _encode_workflow_gate_scope_hashes(scope_hashes: dict[str, str]) -> str:
    """把索引门禁 scope hash 元数据序列化为稳定 JSON。"""
    return json.dumps(scope_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_workflow_gate_scope_hashes(raw_value: str) -> dict[str, str]:
    """读取索引门禁 scope hash 元数据，并拒绝非字符串键值。"""
    value = cast(object, json.loads(raw_value))
    if not isinstance(value, dict):
        raise TypeError("workflow_gate_scope_hashes 必须是 JSON 对象")
    result: dict[str, str] = {}
    items = cast(dict[object, object], value)
    for key, raw_hash in items.items():
        if not isinstance(key, str) or not isinstance(raw_hash, str):
            raise TypeError("workflow_gate_scope_hashes 只能包含字符串键值")
        result[key] = raw_hash
    return result


__all__ = ["TextIndexRecordSessionMixin"]
