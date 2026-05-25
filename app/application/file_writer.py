"""文件替换事务工具。"""

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.rmmz.text_rules import JsonValue


@dataclass(frozen=True, slots=True)
class _WriteOperation:
    """单个目标文件写入操作。"""

    target_path: Path
    content: str | None
    source_path: Path | None
    temp_dir: Path


def write_planned_text_files(
    *,
    files: list[tuple[Path, str]],
    rollback_dir_parent: Path,
) -> None:
    """按 Rust 生成计划事务性替换文本文件。"""
    operations = [
        _WriteOperation(
            target_path=target_path,
            content=content,
            source_path=None,
            temp_dir=target_path.parent,
        )
        for target_path, content in files
    ]
    replace_write_operations_transactionally(
        operations=operations,
        rollback_dir_parent=rollback_dir_parent,
    )


def write_planned_text_file_sources(
    *,
    files: list[tuple[Path, str | None, Path | None]],
    rollback_dir_parent: Path,
) -> None:
    """按 Rust 计划替换文本文件，支持内容 sidecar 文件以避免大 JSON 文本。"""
    operations = [
        _WriteOperation(
            target_path=target_path,
            content=content,
            source_path=source_path,
            temp_dir=target_path.parent,
        )
        for target_path, content, source_path in files
    ]
    replace_write_operations_transactionally(
        operations=operations,
        rollback_dir_parent=rollback_dir_parent,
    )


def replace_write_operations_transactionally(
    *,
    operations: list[_WriteOperation],
    rollback_dir_parent: Path,
) -> None:
    """逐文件替换生成物；任一失败时恢复已替换文件。"""
    if not operations:
        return
    rollback_dir = Path(tempfile.mkdtemp(prefix="att_mz_rollback_", dir=rollback_dir_parent))
    replaced_targets: list[tuple[Path, Path | None]] = []
    try:
        for index, operation in enumerate(operations):
            backup_path: Path | None = None
            if operation.target_path.exists():
                backup_path = rollback_dir / f"{index}_{operation.target_path.name}"
                _ = shutil.copy2(operation.target_path, backup_path)
            if (operation.content is None) == (operation.source_path is None):
                raise RuntimeError("文件替换操作必须且只能包含文本内容或 sidecar 文件路径")
            if operation.source_path is not None:
                replace_text_file_from_path(
                    target_path=operation.target_path,
                    source_path=operation.source_path,
                    temp_dir=operation.temp_dir,
                )
            elif operation.content is not None:
                replace_text_file(
                    target_path=operation.target_path,
                    content=operation.content,
                    temp_dir=operation.temp_dir,
                )
            replaced_targets.append((operation.target_path, backup_path))
    except Exception:
        for target_path, backup_path in reversed(replaced_targets):
            if backup_path is None:
                target_path.unlink(missing_ok=True)
            elif backup_path.exists():
                _ = backup_path.replace(target_path)
        raise
    finally:
        cleanup_path(rollback_dir)


def replace_json_file(*, target_path: Path, data: JsonValue, temp_dir: Path) -> None:
    """用临时文件替换目标 JSON 文件。"""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    replace_text_file(target_path=target_path, content=f"{payload}\n", temp_dir=temp_dir)


def replace_plugins_file(*, plugins_path: Path, data: JsonValue, temp_dir: Path) -> None:
    """替换激活版插件配置文件。"""
    if isinstance(data, str):
        replace_text_file(target_path=plugins_path, content=data, temp_dir=temp_dir)
        return
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    replace_text_file(target_path=plugins_path, content=f"{payload}\n", temp_dir=temp_dir)


def replace_text_file(*, target_path: Path, content: str, temp_dir: Path) -> None:
    """先写入临时文件，再用 `replace` 切换到目标路径。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=target_path.suffix,
        prefix=f"{target_path.stem}_",
        dir=temp_dir,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
        _ = temp_file.write(content)

    try:
        _ = temp_path.replace(target_path)
    except Exception:
        cleanup_path(temp_path)
        raise


def replace_text_file_from_path(*, target_path: Path, source_path: Path, temp_dir: Path) -> None:
    """把已生成的 sidecar 文件复制到临时文件，再切换到目标路径。"""
    if not source_path.is_file():
        raise FileNotFoundError(f"写回计划 sidecar 文件不存在: {source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        suffix=target_path.suffix,
        prefix=f"{target_path.stem}_",
        dir=temp_dir,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        _ = shutil.copyfile(source_path, temp_path)
        _ = temp_path.replace(target_path)
    except Exception:
        cleanup_path(temp_path)
        raise


def cleanup_path(target_path: Path) -> None:
    """清理临时目录或临时文件。"""
    if target_path.is_dir():
        shutil.rmtree(target_path, ignore_errors=True)
    elif target_path.exists():
        target_path.unlink()


__all__: list[str] = [
    "cleanup_path",
    "replace_json_file",
    "replace_plugins_file",
    "replace_text_file",
    "replace_text_file_from_path",
    "write_planned_text_file_sources",
    "write_planned_text_files",
]
