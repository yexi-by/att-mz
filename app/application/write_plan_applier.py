"""统一应用写回计划的文件和数据库副作用。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from app.persistence import TargetGameSession
from app.rmmz.schema import (
    FontReplacementRecord,
    PluginSourceRuntimeScanCacheRecord,
    PluginSourceRuntimeWriteMapRecord,
)

from .file_writer import WriteFileTransaction, WriteOperation


@dataclass(frozen=True, slots=True)
class RuntimeWritePlan:
    """Python 最终写入阶段的统一计划。"""

    file_operations: list[WriteOperation]
    plugin_source_runtime_write_maps: list[PluginSourceRuntimeWriteMapRecord]
    font_replacement_records: list[FontReplacementRecord]


class WritePlanApplier:
    """把写回计划应用到文件系统和数据库。

    成功路径：先替换文件并完成写后审计，再保存运行映射、扫描缓存和字体记录，
    最后统一提交数据库并清理文件备份。

    失败路径：回滚数据库事务，并用写前备份恢复已替换文件。
    """

    def __init__(self, *, session: TargetGameSession, rollback_dir_parent: Path) -> None:
        """初始化写回计划执行器。"""
        self._session: TargetGameSession = session
        self._file_transaction: WriteFileTransaction = WriteFileTransaction(rollback_dir_parent=rollback_dir_parent)
        self._records_saved: bool = False

    async def __aenter__(self) -> Self:
        """进入写回数据库事务。"""
        await self._session.begin_transaction()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """按最终结果提交或回滚文件与数据库副作用。"""
        _ = (exc_value, traceback)
        if exc_type is not None:
            await self.rollback()
            return
        try:
            await self._session.commit_transaction()
        except Exception:
            self._file_transaction.rollback()
            await self._session.rollback_transaction()
            raise
        self._file_transaction.commit()

    def apply_files(self, plan: RuntimeWritePlan) -> None:
        """应用计划中的文件替换，保留回滚备份直到执行器退出。"""
        self._file_transaction.apply(operations=plan.file_operations)

    async def save_success_records(
        self,
        plan: RuntimeWritePlan,
        *,
        runtime_scan_cache_records: Sequence[PluginSourceRuntimeScanCacheRecord] | None,
    ) -> None:
        """写后审计通过后保存所有数据库副作用记录。"""
        await self._session.replace_plugin_source_runtime_write_maps(plan.plugin_source_runtime_write_maps)
        if runtime_scan_cache_records is not None:
            await self._session.replace_plugin_source_runtime_scan_cache(list(runtime_scan_cache_records))
        await self._session.replace_font_replacement_records(plan.font_replacement_records)
        self._records_saved = True

    async def rollback(self) -> None:
        """回滚数据库事务和文件替换。"""
        self._file_transaction.rollback()
        await self._session.rollback_transaction()

    @property
    def records_saved(self) -> bool:
        """返回成功记录是否已经保存。"""
        return self._records_saved


__all__ = ["RuntimeWritePlan", "WritePlanApplier"]
