"""主翻译表读写会话能力。"""

import json
from collections.abc import Sequence

import aiosqlite

from app.rmmz.schema import TranslationItem

from .rows import decode_string_list, row_int, row_item_type, row_optional_str, row_str
from .session_base import SessionMixinBase
from .sql import (
    DELETE_TRANSLATION_ITEM_BY_PATH,
    DELETE_TRANSLATION_ITEMS_BY_PREFIX,
    INSERT_TRANSLATION,
    COUNT_TRANSLATED_ITEMS,
    SELECT_TRANSLATED_ITEM_BY_PATH,
    SELECT_TRANSLATED_ITEMS,
    SELECT_TRANSLATED_ITEMS_BY_PREFIX,
    SELECT_TRANSLATION_PATHS,
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
            serialized_items = [
                (
                    translation_item.location_path,
                    translation_item.item_type,
                    translation_item.role,
                    json.dumps(translation_item.original_lines, ensure_ascii=False),
                    json.dumps(translation_item.source_line_paths, ensure_ascii=False),
                    json.dumps(translation_item.translation_lines, ensure_ascii=False),
                )
                for translation_item in items
            ]
            _ = await self.connection.executemany(INSERT_TRANSLATION, serialized_items)
        await self.connection.commit()

    async def read_translation_location_paths(self) -> set[str]:
        """读取主翻译表中的全部已完成路径。"""
        async with self.connection.execute(SELECT_TRANSLATION_PATHS) as cursor:
            rows = await cursor.fetchall()
        return {row_str(row, "location_path", self.db_path) for row in rows}

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

    async def read_translated_items_by_prefixes(
        self,
        prefixes: Sequence[str],
    ) -> list[TranslationItem]:
        """按路径前缀读取即将受规则变更影响的译文记录。"""
        items_by_path: dict[str, TranslationItem] = {}
        for prefix in prefixes:
            async with self.connection.execute(
                SELECT_TRANSLATED_ITEMS_BY_PREFIX,
                (f"{prefix}%",),
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                item = self._translation_item_from_row(row)
                items_by_path[item.location_path] = item
        return [items_by_path[path] for path in sorted(items_by_path)]

    async def read_translated_items_by_paths(
        self,
        location_paths: Sequence[str],
    ) -> list[TranslationItem]:
        """按精确定位路径读取即将受规则变更影响的译文记录。"""
        items_by_path: dict[str, TranslationItem] = {}
        for location_path in location_paths:
            async with self.connection.execute(
                SELECT_TRANSLATED_ITEM_BY_PATH,
                (location_path,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                continue
            item = self._translation_item_from_row(row)
            items_by_path[item.location_path] = item
        return [items_by_path[path] for path in sorted(items_by_path)]

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
        await self.connection.commit()
        return deleted_rows

    async def delete_translation_items_except_paths(
        self,
        allowed_paths: set[str],
    ) -> int:
        """删除当前提取规则之外的主翻译表记录。"""
        async with self.connection.execute(SELECT_TRANSLATION_PATHS) as cursor:
            rows = await cursor.fetchall()

        stored_paths = {row_str(row, "location_path", self.db_path) for row in rows}
        stale_paths = sorted(stored_paths - allowed_paths)
        if not stale_paths:
            return 0

        _ = await self.connection.executemany(
            DELETE_TRANSLATION_ITEM_BY_PATH,
            [(path,) for path in stale_paths],
        )
        await self.connection.commit()
        return len(stale_paths)

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
        await self.connection.commit()
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
            location_path=row_str(row, "location_path", self.db_path),
            item_type=row_item_type(row, "item_type", self.db_path),
            role=row_optional_str(row, "role", self.db_path),
            original_lines=original_lines,
            source_line_paths=source_line_paths,
            translation_lines=translation_lines,
        )


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    """把路径列表分块，避免 SQLite 参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]
