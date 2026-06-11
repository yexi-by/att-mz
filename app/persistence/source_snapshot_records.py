"""可信源快照 manifest 记录会话能力。"""

from app.rmmz.source_snapshot import SourceSnapshotFileRecord

from .rows import row_int, row_str
from .session_base import SessionMixinBase
from .sql import (
    DELETE_ALL_SOURCE_SNAPSHOT_FILES,
    INSERT_SOURCE_SNAPSHOT_FILE,
    SELECT_SOURCE_SNAPSHOT_FILES,
)


class SourceSnapshotRecordSessionMixin(SessionMixinBase):
    """负责可信源快照 manifest 的保存、读取与替换。"""

    async def replace_source_snapshot_records(
        self,
        records: list[SourceSnapshotFileRecord],
    ) -> None:
        """用当前可信源快照 manifest 替换数据库现有记录。"""
        _ = await self.connection.execute(DELETE_ALL_SOURCE_SNAPSHOT_FILES)
        if records:
            _ = await self.connection.executemany(
                INSERT_SOURCE_SNAPSHOT_FILE,
                [
                    (
                        record.relative_path,
                        record.sha256,
                        record.byte_size,
                        record.updated_at,
                    )
                    for record in records
                ],
            )
        await self.connection.commit()

    async def read_source_snapshot_records(self) -> list[SourceSnapshotFileRecord]:
        """读取当前游戏数据库中的可信源快照 manifest。"""
        async with self.connection.execute(SELECT_SOURCE_SNAPSHOT_FILES) as cursor:
            rows = await cursor.fetchall()
        return [
            SourceSnapshotFileRecord(
                relative_path=row_str(row, "relative_path", self.db_path),
                sha256=row_str(row, "sha256", self.db_path),
                byte_size=row_int(row, "byte_size", self.db_path),
                updated_at=row_str(row, "updated_at", self.db_path),
            )
            for row in rows
        ]


__all__ = ["SourceSnapshotRecordSessionMixin"]
