"""主翻译表读写会话能力。"""

import json
from collections.abc import Sequence

import aiosqlite

from app.rmmz.schema import TranslationItem

from .rows import decode_string_list, row_int, row_item_type, row_optional_str, row_str
from .session_base import SessionMixinBase
from .sql import (
    DELETE_TRANSLATION_ITEMS_BY_PREFIX,
    INSERT_TRANSLATION,
    COUNT_TRANSLATED_ITEMS,
    SELECT_TRANSLATED_ITEMS,
    SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX,
    SELECT_TRANSLATED_ITEMS_BY_PREFIX,
    TRANSLATION_TABLE_NAME,
)

PATH_DELETE_BATCH_SIZE = 500


class TranslationRecordSessionMixin(SessionMixinBase):
    """负责已保存译文记录的读写与清理。"""

    async def write_translation_items(
        self,
        items: Sequence[TranslationItem],
    ) -> None:
        """批量写入已完成译文到主翻译表。"""
        if items:
            serialized_items: list[tuple[str, str, str, str | None, str, str, str, str, str]] = []
            for translation_item in items:
                fact_id, source_fact_raw_hash, source_fact_translatable_hash = (
                    _require_v2_translation_identity(translation_item)
                )
                serialized_items.append(
                    (
                        fact_id,
                        translation_item.location_path,
                        translation_item.item_type,
                        translation_item.role,
                        json.dumps(translation_item.original_lines, ensure_ascii=False),
                        json.dumps(translation_item.source_line_paths, ensure_ascii=False),
                        source_fact_raw_hash,
                        source_fact_translatable_hash,
                        json.dumps(translation_item.translation_lines, ensure_ascii=False),
                    )
                )
            _ = await self.connection.executemany(INSERT_TRANSLATION, serialized_items)
        await self.commit()

    async def count_translated_items(self) -> int:
        """统计主翻译表中的已保存译文数量。"""
        async with self.connection.execute(COUNT_TRANSLATED_ITEMS) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "translated_count", self.db_path)

    async def read_translated_items(self) -> list[TranslationItem]:
        """读取主翻译表中的全部正文译文。"""
        async with self.connection.execute(SELECT_TRANSLATED_ITEMS) as cursor:
            rows = await cursor.fetchall()

        return [self._translation_item_from_row(row) for row in rows]

    async def read_translated_items_for_writable_text_index(self) -> list[TranslationItem]:
        """读取当前可写索引范围内已经保存的译文。"""
        async with self.connection.execute(SELECT_TRANSLATED_ITEMS_FOR_WRITABLE_TEXT_INDEX) as cursor:
            rows = await cursor.fetchall()
        return [self._translation_item_from_row(row) for row in rows]

    async def read_translated_items_by_prefixes(
        self,
        prefixes: Sequence[str],
    ) -> list[TranslationItem]:
        """按路径前缀读取即将受规则变更影响的译文记录。"""
        items: list[TranslationItem] = []
        for prefix in prefixes:
            async with self.connection.execute(
                SELECT_TRANSLATED_ITEMS_BY_PREFIX,
                (f"{prefix}%",),
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                items.append(self._translation_item_from_row(row))
        return sorted(items, key=lambda item: (item.location_path, item.fact_id or ""))

    async def read_translated_items_by_paths(
        self,
        location_paths: Sequence[str],
    ) -> list[TranslationItem]:
        """按精确定位路径读取即将受规则变更影响的译文记录。"""
        unique_paths = sorted(set(location_paths))
        if not unique_paths:
            return []
        items: list[TranslationItem] = []
        for batch in _chunks(unique_paths, PATH_DELETE_BATCH_SIZE):
            placeholders = ", ".join("?" for _path in batch)
            async with self.connection.execute(
                f"""
--sql
                    SELECT
                        fact_id,
                        location_path,
                        item_type,
                        role,
                        original_lines,
                        source_line_paths,
                        source_fact_raw_hash,
                        source_fact_translatable_hash,
                        translation_lines
                    FROM [{TRANSLATION_TABLE_NAME}]
                    WHERE location_path IN ({placeholders})
                    ORDER BY location_path, fact_id
                ;
                """,
                tuple(batch),
            ) as cursor:
                rows = await cursor.fetchall()
            items.extend(self._translation_item_from_row(row) for row in rows)
        return sorted(items, key=lambda item: (item.location_path, item.fact_id or ""))

    async def read_translated_items_by_fact_ids(
        self,
        fact_ids: Sequence[str],
    ) -> list[TranslationItem]:
        """按 v2 fact_id 批量读取已保存译文。"""
        unique_fact_ids = sorted(set(fact_ids))
        if not unique_fact_ids:
            return []
        items: list[TranslationItem] = []
        for batch in _chunks(unique_fact_ids, PATH_DELETE_BATCH_SIZE):
            placeholders = ", ".join("?" for _fact_id in batch)
            async with self.connection.execute(
                f"""
--sql
                    SELECT
                        fact_id,
                        location_path,
                        item_type,
                        role,
                        original_lines,
                        source_line_paths,
                        source_fact_raw_hash,
                        source_fact_translatable_hash,
                        translation_lines
                    FROM [{TRANSLATION_TABLE_NAME}]
                    WHERE fact_id IN ({placeholders})
                    ORDER BY location_path, fact_id
                ;
                """,
                tuple(batch),
            ) as cursor:
                rows = await cursor.fetchall()
            items.extend(self._translation_item_from_row(row) for row in rows)
        return sorted(items, key=lambda item: (item.location_path, item.fact_id or ""))

    async def delete_translation_items_by_prefixes(self, prefixes: list[str]) -> int:
        """按路径前缀批量删除主翻译表中的记录。"""
        deleted_rows = 0
        for prefix in prefixes:
            cursor = await self.connection.execute(
                DELETE_TRANSLATION_ITEMS_BY_PREFIX,
                (f"{prefix}%",),
            )
            if cursor.rowcount > 0:
                deleted_rows += cursor.rowcount
        await self.commit()
        return deleted_rows

    async def delete_translation_items_by_paths(
        self,
        location_paths: Sequence[str],
    ) -> int:
        """按精确定位路径批量删除主翻译表记录。"""
        unique_paths = sorted(set(location_paths))
        if not unique_paths:
            return 0
        deleted_rows = 0
        for batch in _chunks(unique_paths, PATH_DELETE_BATCH_SIZE):
            placeholders = ", ".join("?" for _path in batch)
            sql = f"""
--sql
                DELETE FROM [{TRANSLATION_TABLE_NAME}]
                WHERE location_path IN ({placeholders})
            ;
            """
            cursor = await self.connection.execute(sql, tuple(batch))
            if cursor.rowcount > 0:
                deleted_rows += cursor.rowcount
        await self.commit()
        return deleted_rows

    async def delete_translation_items_by_fact_ids(
        self,
        fact_ids: Sequence[str],
    ) -> int:
        """按 v2 fact_id 批量删除已保存译文。"""
        unique_fact_ids = sorted(set(fact_ids))
        if not unique_fact_ids:
            return 0
        deleted_rows = 0
        for batch in _chunks(unique_fact_ids, PATH_DELETE_BATCH_SIZE):
            placeholders = ", ".join("?" for _fact_id in batch)
            cursor = await self.connection.execute(
                f"""
--sql
                    DELETE FROM [{TRANSLATION_TABLE_NAME}]
                    WHERE fact_id IN ({placeholders})
                ;
                """,
                tuple(batch),
            )
            if cursor.rowcount > 0:
                deleted_rows += cursor.rowcount
        await self.commit()
        return deleted_rows

    def _translation_item_from_row(self, row: aiosqlite.Row) -> TranslationItem:
        """把数据库行还原为已保存译文对象。"""
        original_lines = decode_string_list(row_str(row, "original_lines", self.db_path), "original_lines")
        source_line_paths = decode_string_list(
            row_str(row, "source_line_paths", self.db_path),
            "source_line_paths",
        )
        translation_lines = decode_string_list(
            row_str(row, "translation_lines", self.db_path),
            "translation_lines",
        )
        return TranslationItem(
            fact_id=row_str(row, "fact_id", self.db_path),
            location_path=row_str(row, "location_path", self.db_path),
            item_type=row_item_type(row, "item_type", self.db_path),
            role=row_optional_str(row, "role", self.db_path),
            original_lines=original_lines,
            source_line_paths=source_line_paths,
            source_fact_raw_hash=row_str(row, "source_fact_raw_hash", self.db_path),
            source_fact_translatable_hash=row_str(row, "source_fact_translatable_hash", self.db_path),
            translation_lines=translation_lines,
        )


def _require_v2_translation_identity(item: TranslationItem) -> tuple[str, str, str]:
    """校验保存译文必须携带当前 v2 fact 身份。"""
    if not item.fact_id or not item.source_fact_raw_hash or not item.source_fact_translatable_hash:
        raise ValueError(
            "已保存译文缺少 v2 fact identity；请从 text_facts_v2 adapter 构造 TranslationItem 后再保存"
        )
    return item.fact_id, item.source_fact_raw_hash, item.source_fact_translatable_hash


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """把路径列表分块，避免 SQLite 参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]
