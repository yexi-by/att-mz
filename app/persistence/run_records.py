"""正文翻译运行状态和检查问题记录会话能力。"""

import json
from datetime import datetime

import aiosqlite

from app.rmmz.schema import LlmFailureRecord, TranslationErrorItem, TranslationRunRecord

from .rows import decode_string_list, row_int, row_item_type, row_optional_str, row_str
from .session_base import SessionMixinBase
from .session_utils import current_timestamp_text, parse_error_type, parse_llm_failure_category, parse_translation_run_status
from .sql import (
    COUNT_TRANSLATION_QUALITY_ERRORS_BY_RUN,
    DELETE_ALL_TRANSLATION_QUALITY_ERRORS,
    INSERT_LLM_FAILURE,
    INSERT_TRANSLATION_QUALITY_ERROR,
    SELECT_LATEST_TRANSLATION_RUN,
    SELECT_LLM_FAILURES_BY_RUN,
    SELECT_TRANSLATION_QUALITY_ERROR_TYPE_COUNTS_BY_RUN,
    SELECT_TRANSLATION_QUALITY_ERRORS_BY_RUN,
    SELECT_TRANSLATION_RUN,
    TRANSLATION_QUALITY_ERRORS_TABLE_NAME,
    UPSERT_TRANSLATION_RUN,
)

PATH_QUERY_BATCH_SIZE = 500


class RunRecordSessionMixin(SessionMixinBase):
    """负责翻译运行状态、模型故障和检查问题记录。"""

    async def start_translation_run(
        self,
        *,
        total_extracted: int,
        pending_count: int,
        deduplicated_count: int,
        batch_count: int,
    ) -> TranslationRunRecord:
        """创建新的正文翻译运行状态。"""
        _ = await self.connection.execute(DELETE_ALL_TRANSLATION_QUALITY_ERRORS)
        now = current_timestamp_text()
        run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
        record = TranslationRunRecord(
            run_id=run_id,
            status="running",
            total_extracted=total_extracted,
            pending_count=pending_count,
            deduplicated_count=deduplicated_count,
            batch_count=batch_count,
            success_count=0,
            quality_error_count=0,
            llm_failure_count=0,
            started_at=now,
            updated_at=now,
            finished_at=None,
            stop_reason="",
            last_error="",
        )
        await self.write_translation_run(record)
        return record

    async def write_translation_run(self, record: TranslationRunRecord) -> None:
        """写入正文翻译运行状态快照。"""
        _ = await self.connection.execute(
            UPSERT_TRANSLATION_RUN,
            (
                record.run_id,
                record.status,
                record.total_extracted,
                record.pending_count,
                record.deduplicated_count,
                record.batch_count,
                record.success_count,
                record.quality_error_count,
                record.llm_failure_count,
                record.started_at,
                current_timestamp_text(),
                record.finished_at,
                record.stop_reason,
                record.last_error,
            ),
        )
        await self.connection.commit()

    async def read_latest_translation_run(self) -> TranslationRunRecord | None:
        """读取最新正文翻译运行状态。"""
        async with self.connection.execute(SELECT_LATEST_TRANSLATION_RUN) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._decode_translation_run(row)

    async def read_translation_run(self, run_id: str) -> TranslationRunRecord | None:
        """按运行 ID 读取正文翻译状态。"""
        async with self.connection.execute(SELECT_TRANSLATION_RUN, (run_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._decode_translation_run(row)

    async def write_llm_failure(self, failure: LlmFailureRecord) -> None:
        """写入运行级模型故障。"""
        _ = await self.connection.execute(
            INSERT_LLM_FAILURE,
            (
                failure.run_id,
                failure.category,
                failure.error_type,
                failure.error_message,
                1 if failure.retryable else 0,
                failure.attempt_count,
                failure.created_at,
            ),
        )
        await self.connection.commit()

    async def read_llm_failures(self, run_id: str) -> list[LlmFailureRecord]:
        """读取指定运行的模型故障记录。"""
        async with self.connection.execute(SELECT_LLM_FAILURES_BY_RUN, (run_id,)) as cursor:
            rows = await cursor.fetchall()
        return [
            LlmFailureRecord(
                run_id=row_str(row, "run_id", self.db_path),
                category=parse_llm_failure_category(row_str(row, "category", self.db_path), self.db_path),
                error_type=row_str(row, "error_type", self.db_path),
                error_message=row_str(row, "error_message", self.db_path),
                retryable=row_int(row, "retryable", self.db_path) == 1,
                attempt_count=row_int(row, "attempt_count", self.db_path),
                created_at=row_str(row, "created_at", self.db_path),
            )
            for row in rows
        ]

    async def write_translation_quality_errors(
        self,
        run_id: str,
        items: list[TranslationErrorItem],
    ) -> None:
        """写入没通过项目检查的最终译文。"""
        if items:
            serialized_items = [
                (
                    run_id,
                    error_item.fact_id or "",
                    error_item.location_path,
                    error_item.item_type,
                    error_item.role,
                    json.dumps(error_item.original_lines, ensure_ascii=False),
                    json.dumps(error_item.translation_lines, ensure_ascii=False),
                    error_item.error_type,
                    json.dumps(error_item.error_detail, ensure_ascii=False),
                    error_item.model_response,
                )
                for error_item in items
            ]
            _ = await self.connection.executemany(
                INSERT_TRANSLATION_QUALITY_ERROR,
                serialized_items,
            )
        await self.connection.commit()

    async def read_translation_quality_errors(self, run_id: str) -> list[TranslationErrorItem]:
        """读取指定运行中没通过项目检查的最终译文。"""
        async with self.connection.execute(SELECT_TRANSLATION_QUALITY_ERRORS_BY_RUN, (run_id,)) as cursor:
            rows = await cursor.fetchall()
        return [self._decode_translation_quality_error(row) for row in rows]

    async def read_translation_quality_errors_by_paths(
        self,
        run_id: str,
        location_paths: set[str],
    ) -> list[TranslationErrorItem]:
        """按输入定位路径读取指定运行中没通过项目检查的译文。"""
        sorted_paths = sorted(location_paths)
        if not sorted_paths:
            return []
        quality_errors_by_path: dict[str, TranslationErrorItem] = {}
        for batch in _chunks(sorted_paths, PATH_QUERY_BATCH_SIZE):
            placeholders = ", ".join("?" for _path in batch)
            async with self.connection.execute(
                f"""
--sql
                    SELECT *
                    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
                    WHERE run_id = ? AND location_path IN ({placeholders})
                    ORDER BY location_path
                ;
                """,
                (run_id, *batch),
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                item = self._decode_translation_quality_error(row)
                quality_errors_by_path[item.location_path] = item
        return [quality_errors_by_path[path] for path in sorted_paths if path in quality_errors_by_path]

    async def read_translation_quality_errors_by_fact_ids(
        self,
        run_id: str,
        fact_ids: set[str],
    ) -> list[TranslationErrorItem]:
        """按 v2 fact_id 读取指定运行中没通过项目检查的译文。"""
        sorted_fact_ids = sorted(fact_ids)
        if not sorted_fact_ids:
            return []
        quality_errors_by_fact_id: dict[str, TranslationErrorItem] = {}
        for batch in _chunks(sorted_fact_ids, PATH_QUERY_BATCH_SIZE):
            placeholders = ", ".join("?" for _fact_id in batch)
            async with self.connection.execute(
                f"""
--sql
                    SELECT *
                    FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
                    WHERE run_id = ? AND fact_id IN ({placeholders})
                    ORDER BY location_path, fact_id
                ;
                """,
                (run_id, *batch),
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                item = self._decode_translation_quality_error(row)
                if item.fact_id:
                    quality_errors_by_fact_id[item.fact_id] = item
        return [
            quality_errors_by_fact_id[fact_id]
            for fact_id in sorted_fact_ids
            if fact_id in quality_errors_by_fact_id
        ]

    async def count_translation_quality_errors(self, run_id: str) -> int:
        """统计指定运行还剩多少条没通过项目检查的译文。"""
        async with self.connection.execute(COUNT_TRANSLATION_QUALITY_ERRORS_BY_RUN, (run_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return 0
        return row_int(row, "quality_error_count", self.db_path)

    async def count_translation_quality_errors_by_type(self, run_id: str) -> dict[str, int]:
        """按错误类型统计指定运行的质量错误。"""
        async with self.connection.execute(SELECT_TRANSLATION_QUALITY_ERROR_TYPE_COUNTS_BY_RUN, (run_id,)) as cursor:
            rows = await cursor.fetchall()
        return {
            row_str(row, "error_type", self.db_path): row_int(row, "error_count", self.db_path)
            for row in rows
        }

    async def delete_translation_quality_errors_by_paths(self, location_paths: set[str]) -> int:
        """按文本内部位置清理已经修好的译文检查失败明细。"""
        if not location_paths:
            return 0
        sorted_paths = sorted(location_paths)
        placeholders = ", ".join("?" for _ in sorted_paths)
        cursor = await self.connection.execute(
            f"""
--sql
                DELETE FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
                WHERE location_path IN ({placeholders})
            """,
            tuple(sorted_paths),
        )
        await self.connection.commit()
        return max(cursor.rowcount, 0)

    async def delete_translation_quality_errors_by_fact_ids(self, fact_ids: set[str]) -> int:
        """按 v2 fact_id 清理已经修好的译文检查失败明细。"""
        sorted_fact_ids = sorted(fact_ids)
        if not sorted_fact_ids:
            return 0
        deleted_rows = 0
        for batch in _chunks(sorted_fact_ids, PATH_QUERY_BATCH_SIZE):
            placeholders = ", ".join("?" for _fact_id in batch)
            cursor = await self.connection.execute(
                f"""
--sql
                    DELETE FROM [{TRANSLATION_QUALITY_ERRORS_TABLE_NAME}]
                    WHERE fact_id IN ({placeholders})
                """,
                tuple(batch),
            )
            deleted_rows += max(cursor.rowcount, 0)
        await self.connection.commit()
        return deleted_rows

    def _decode_translation_run(self, row: aiosqlite.Row) -> TranslationRunRecord:
        """把 SQLite 行转换成正文翻译运行状态。"""
        return TranslationRunRecord(
            run_id=row_str(row, "run_id", self.db_path),
            status=parse_translation_run_status(row_str(row, "status", self.db_path), self.db_path),
            total_extracted=row_int(row, "total_extracted", self.db_path),
            pending_count=row_int(row, "pending_count", self.db_path),
            deduplicated_count=row_int(row, "deduplicated_count", self.db_path),
            batch_count=row_int(row, "batch_count", self.db_path),
            success_count=row_int(row, "success_count", self.db_path),
            quality_error_count=row_int(row, "quality_error_count", self.db_path),
            llm_failure_count=row_int(row, "llm_failure_count", self.db_path),
            started_at=row_str(row, "started_at", self.db_path),
            updated_at=row_str(row, "updated_at", self.db_path),
            finished_at=row_optional_str(row, "finished_at", self.db_path),
            stop_reason=row_str(row, "stop_reason", self.db_path),
            last_error=row_str(row, "last_error", self.db_path),
        )

    def _decode_translation_quality_error(self, row: aiosqlite.Row) -> TranslationErrorItem:
        """把 SQLite 行转换成质量错误记录。"""
        return TranslationErrorItem(
            fact_id=row_str(row, "fact_id", self.db_path),
            location_path=row_str(row, "location_path", self.db_path),
            item_type=row_item_type(row, "item_type", self.db_path),
            role=row_optional_str(row, "role", self.db_path),
            original_lines=decode_string_list(row_str(row, "original_lines", self.db_path), "original_lines"),
            translation_lines=decode_string_list(
                row_str(row, "translation_lines", self.db_path),
                "translation_lines",
            ),
            error_type=parse_error_type(row_str(row, "error_type", self.db_path), self.db_path),
            error_detail=decode_string_list(row_str(row, "error_detail", self.db_path), "error_detail"),
            model_response=row_str(row, "model_response", self.db_path),
        )


def _chunks(values: list[str], size: int) -> list[list[str]]:
    """把路径列表分块，避免 SQLite 参数过多。"""
    return [values[index:index + size] for index in range(0, len(values), size)]
