"""插件源码当前运行写回映射记录会话能力。"""

from app.rmmz.schema import PluginSourceRuntimeWriteMapRecord

from .rows import row_int, row_str
from .session_base import SessionMixinBase
from .sql import (
    DELETE_ALL_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS,
    INSERT_PLUGIN_SOURCE_RUNTIME_WRITE_MAP,
    SELECT_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS,
)


class PluginSourceRuntimeRecordSessionMixin(SessionMixinBase):
    """负责插件源码当前运行写回映射的保存、读取与清理。"""

    async def upsert_plugin_source_runtime_write_maps(
        self,
        records: list[PluginSourceRuntimeWriteMapRecord],
    ) -> None:
        """保存插件源码写回后可用于确定性反推的映射记录。"""
        if records:
            _ = await self.connection.executemany(
                INSERT_PLUGIN_SOURCE_RUNTIME_WRITE_MAP,
                [
                    (
                        record.location_path,
                        record.source_file_name,
                        record.source_selector,
                        record.source_file_hash,
                        record.source_text_hash,
                        record.translation_lines_hash,
                        record.runtime_file_name,
                        record.runtime_selector,
                        record.runtime_file_hash,
                        record.runtime_text_hash,
                        record.runtime_line,
                        record.created_at,
                    )
                    for record in records
                ],
            )
        await self.connection.commit()

    async def read_plugin_source_runtime_write_maps(self) -> list[PluginSourceRuntimeWriteMapRecord]:
        """读取全部插件源码当前运行写回映射。"""
        async with self.connection.execute(SELECT_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS) as cursor:
            rows = await cursor.fetchall()
        return [
            PluginSourceRuntimeWriteMapRecord(
                location_path=row_str(row, "location_path", self.db_path),
                source_file_name=row_str(row, "source_file_name", self.db_path),
                source_selector=row_str(row, "source_selector", self.db_path),
                source_file_hash=row_str(row, "source_file_hash", self.db_path),
                source_text_hash=row_str(row, "source_text_hash", self.db_path),
                translation_lines_hash=row_str(row, "translation_lines_hash", self.db_path),
                runtime_file_name=row_str(row, "runtime_file_name", self.db_path),
                runtime_selector=row_str(row, "runtime_selector", self.db_path),
                runtime_file_hash=row_str(row, "runtime_file_hash", self.db_path),
                runtime_text_hash=row_str(row, "runtime_text_hash", self.db_path),
                runtime_line=row_int(row, "runtime_line", self.db_path),
                created_at=row_str(row, "created_at", self.db_path),
            )
            for row in rows
        ]

    async def clear_plugin_source_runtime_write_maps(self) -> None:
        """清空插件源码当前运行写回映射。"""
        _ = await self.connection.execute(DELETE_ALL_PLUGIN_SOURCE_RUNTIME_WRITE_MAPS)
        await self.connection.commit()


__all__ = ["PluginSourceRuntimeRecordSessionMixin"]
