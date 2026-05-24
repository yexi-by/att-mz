"""插件源码当前运行来源映射记录会话能力。"""

from app.rmmz.schema import PluginSourceRuntimeProvenanceRecord

from .rows import row_int, row_str
from .session_base import SessionMixinBase
from .sql import (
    DELETE_ALL_PLUGIN_SOURCE_RUNTIME_PROVENANCE,
    INSERT_PLUGIN_SOURCE_RUNTIME_PROVENANCE,
    SELECT_PLUGIN_SOURCE_RUNTIME_PROVENANCE,
)


class PluginSourceRuntimeRecordSessionMixin(SessionMixinBase):
    """负责插件源码当前运行来源映射的保存、读取与清理。"""

    async def replace_plugin_source_runtime_provenance(
        self,
        records: list[PluginSourceRuntimeProvenanceRecord],
    ) -> None:
        """替换插件源码写回后可用于确定性反推的来源映射记录。"""
        _ = await self.connection.execute(DELETE_ALL_PLUGIN_SOURCE_RUNTIME_PROVENANCE)
        if records:
            _ = await self.connection.executemany(
                INSERT_PLUGIN_SOURCE_RUNTIME_PROVENANCE,
                [
                    (
                        record.source_file_name,
                        record.source_selector,
                        record.source_file_hash,
                        record.source_text_hash,
                        record.review_kind,
                        record.location_path,
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

    async def read_plugin_source_runtime_provenance(self) -> list[PluginSourceRuntimeProvenanceRecord]:
        """读取全部插件源码当前运行来源映射。"""
        async with self.connection.execute(SELECT_PLUGIN_SOURCE_RUNTIME_PROVENANCE) as cursor:
            rows = await cursor.fetchall()
        return [
            PluginSourceRuntimeProvenanceRecord(
                source_file_name=row_str(row, "source_file_name", self.db_path),
                source_selector=row_str(row, "source_selector", self.db_path),
                source_file_hash=row_str(row, "source_file_hash", self.db_path),
                source_text_hash=row_str(row, "source_text_hash", self.db_path),
                review_kind=row_str(row, "review_kind", self.db_path),
                location_path=row_str(row, "location_path", self.db_path),
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

    async def clear_plugin_source_runtime_provenance(self) -> None:
        """清空插件源码当前运行来源映射。"""
        _ = await self.connection.execute(DELETE_ALL_PLUGIN_SOURCE_RUNTIME_PROVENANCE)
        await self.connection.commit()


__all__ = ["PluginSourceRuntimeRecordSessionMixin"]
