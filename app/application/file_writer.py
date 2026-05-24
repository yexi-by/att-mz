"""游戏文件回写编排。

普通写回只替换相对翻译源发生变化的文件；重建模式从可信源视图生成完整当前运行文件。
"""

import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import shutil

from app.rmmz.schema import (
    GameData,
    PLUGINS_FILE_NAME,
)
from app.rmmz.loader import validate_data_directory_integrity
from app.rmmz.text_rules import JsonValue


@dataclass(frozen=True, slots=True)
class _WriteOperation:
    """单个目标文件写入操作。"""

    target_path: Path
    content: str
    temp_dir: Path


def reset_writable_copies(game_data: GameData) -> None:
    """重置游戏数据的可写副本，保证每次回写都从加载数据重新套用译文。"""
    game_data.writable_data = copy.deepcopy(game_data.data)
    game_data.writable_plugins_js = copy.deepcopy(game_data.plugins_js)
    game_data.writable_plugin_source_files = dict(game_data.plugin_source_files)


def write_game_files(
    game_data: GameData,
    game_root: Path | None = None,
    *,
    force_full_restore: bool = False,
) -> None:
    """把本轮生成的游戏文件替换到当前运行路径。"""
    _ = game_root
    active_data_dir, origin_data_dir, active_plugins_path, origin_plugins_path = build_game_layout_paths(game_data)
    if force_full_restore:
        changed_data_files = collect_all_data_file_names(game_data)
        plugins_changed = True
        changed_plugin_source_files = collect_all_plugin_source_file_names(game_data)
    else:
        changed_data_files = collect_changed_data_file_names(game_data)
        plugins_changed = is_plugins_file_changed(game_data)
        changed_plugin_source_files = collect_changed_plugin_source_file_names(game_data)

    if not changed_data_files and not plugins_changed and not changed_plugin_source_files:
        return

    if not force_full_restore:
        ensure_active_layout_exists(
            active_data_dir=active_data_dir,
            active_plugins_path=active_plugins_path,
        )
    if not force_full_restore and (changed_data_files or plugins_changed):
        ensure_full_data_origin_backup(
            active_data_dir=active_data_dir,
            origin_data_dir=origin_data_dir,
            temp_dir=game_data.layout.content_root,
        )
        backup_original_plugins_file(
            plugins_changed=plugins_changed,
            active_plugins_path=active_plugins_path,
            origin_plugins_path=origin_plugins_path,
        )
    if changed_plugin_source_files and not force_full_restore:
        backup_original_plugin_source_files(
            game_data=game_data,
        )

    operations = build_write_operations(
        game_data=game_data,
        changed_data_files=changed_data_files,
        active_data_dir=active_data_dir,
        active_plugins_path=active_plugins_path,
        plugins_changed=plugins_changed,
        changed_plugin_source_files=changed_plugin_source_files,
    )
    replace_write_operations_transactionally(
        operations=operations,
        rollback_dir_parent=game_data.layout.content_root,
    )


def build_write_operations(
    *,
    game_data: GameData,
    changed_data_files: list[str],
    active_data_dir: Path,
    active_plugins_path: Path,
    plugins_changed: bool,
    changed_plugin_source_files: list[str],
) -> list[_WriteOperation]:
    """把本轮所有生成物整理成待替换文件列表。"""
    operations: list[_WriteOperation] = []
    for file_name in changed_data_files:
        payload = json.dumps(game_data.writable_data[file_name], ensure_ascii=False, indent=2)
        operations.append(
            _WriteOperation(
                target_path=active_data_dir / file_name,
                content=f"{payload}\n",
                temp_dir=game_data.layout.content_root,
            )
        )
    if plugins_changed:
        plugins_content = game_data.writable_data[PLUGINS_FILE_NAME]
        if isinstance(plugins_content, str):
            content = plugins_content
        else:
            payload = json.dumps(plugins_content, ensure_ascii=False, indent=2)
            content = f"{payload}\n"
        operations.append(
            _WriteOperation(
                target_path=active_plugins_path,
                content=content,
                temp_dir=active_plugins_path.parent,
            )
        )
    active_plugin_source_dir = game_data.layout.js_dir / "plugins"
    for file_name in changed_plugin_source_files:
        operations.append(
            _WriteOperation(
                target_path=active_plugin_source_dir / file_name,
                content=game_data.writable_plugin_source_files[file_name],
                temp_dir=active_plugin_source_dir,
            )
        )
    return operations


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


def collect_changed_data_file_names(game_data: GameData) -> list[str]:
    """找出本轮相对加载源发生变化的标准 data 文件。"""
    changed_files: list[str] = []
    for file_name, writable_value in sorted(game_data.writable_data.items()):
        if file_name == PLUGINS_FILE_NAME:
            continue
        original_value = game_data.data.get(file_name)
        if writable_value != original_value:
            changed_files.append(file_name)
    return changed_files


def collect_all_data_file_names(game_data: GameData) -> list[str]:
    """列出当前可信源视图中的全部标准 data 文件。"""
    return sorted(
        file_name
        for file_name in game_data.writable_data
        if file_name != PLUGINS_FILE_NAME
    )


def is_plugins_file_changed(game_data: GameData) -> bool:
    """判断本轮是否需要替换 `js/plugins.js`。"""
    writable_plugins = game_data.writable_data.get(PLUGINS_FILE_NAME)
    original_plugins = game_data.data.get(PLUGINS_FILE_NAME)
    return writable_plugins != original_plugins


def collect_changed_plugin_source_file_names(game_data: GameData) -> list[str]:
    """找出本轮相对加载源发生变化的插件源码文件。"""
    changed_files: list[str] = []
    for file_name, writable_content in sorted(game_data.writable_plugin_source_files.items()):
        if game_data.plugin_source_files.get(file_name) != writable_content:
            changed_files.append(file_name)
    return changed_files


def collect_all_plugin_source_file_names(game_data: GameData) -> list[str]:
    """列出当前可信源视图中的全部直接插件源码文件。"""
    return sorted(game_data.writable_plugin_source_files)


def build_game_layout_paths(game_data: GameData) -> tuple[Path, Path, Path, Path]:
    """构造当前游戏目录下激活版与原件备份路径。"""
    layout = game_data.layout
    return layout.data_dir, layout.data_origin_dir, layout.plugins_path, layout.plugins_origin_path


def ensure_active_layout_exists(*, active_data_dir: Path, active_plugins_path: Path) -> None:
    """确认激活版数据目录和插件配置文件存在。"""
    if not active_data_dir.exists():
        raise FileNotFoundError(f"激活数据目录不存在: {active_data_dir}")
    if not active_plugins_path.exists():
        raise FileNotFoundError(f"激活插件配置文件不存在: {active_plugins_path}")


def ensure_full_data_origin_backup(
    *,
    active_data_dir: Path,
    origin_data_dir: Path,
    temp_dir: Path,
) -> None:
    """确保 `data_origin/` 是首次写回前的完整原始 data 备份。"""
    validate_data_directory_integrity(data_dir=active_data_dir, role="激活数据目录")
    if origin_data_dir.exists():
        validate_data_directory_integrity(data_dir=origin_data_dir, role="原始 data 备份")
        return

    origin_data_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_backup_dir = Path(
        tempfile.mkdtemp(
            prefix=f"{origin_data_dir.name}_",
            dir=temp_dir,
        )
    )
    try:
        _ = shutil.copytree(active_data_dir, temp_backup_dir, dirs_exist_ok=True)
        validate_data_directory_integrity(data_dir=temp_backup_dir, role="临时原始 data 备份")
        _ = shutil.move(str(temp_backup_dir), str(origin_data_dir))
    except Exception:
        cleanup_path(temp_backup_dir)
        raise


def backup_original_plugins_file(
    *,
    plugins_changed: bool,
    active_plugins_path: Path,
    origin_plugins_path: Path,
) -> None:
    """写回插件配置前保存原始 `plugins.js`。"""
    if not plugins_changed:
        return

    if origin_plugins_path.exists():
        return
    origin_plugins_path.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(active_plugins_path, origin_plugins_path)


def backup_original_plugin_source_files(
    *,
    game_data: GameData,
) -> None:
    """写回插件源码前保存完整直接插件源码快照。"""
    origin_dir = game_data.layout.plugin_source_origin_dir
    active_dir = game_data.layout.js_dir / "plugins"
    origin_dir.mkdir(parents=True, exist_ok=True)
    if not active_dir.is_dir():
        raise FileNotFoundError(f"激活插件源码目录不存在: {active_dir}")
    for active_path in sorted(active_dir.glob("*.js"), key=lambda path: path.name):
        if not active_path.is_file():
            continue
        file_name = active_path.name
        origin_path = origin_dir / file_name
        if origin_path.exists():
            continue
        _ = shutil.copy2(active_path, origin_path)


def replace_changed_data_files(
    *,
    game_data: GameData,
    changed_data_files: list[str],
    active_data_dir: Path,
    temp_dir: Path,
) -> None:
    """把变化后的 data 文件逐个替换到激活版目录。"""
    for file_name in changed_data_files:
        target_path = active_data_dir / file_name
        data = game_data.writable_data[file_name]
        replace_json_file(target_path=target_path, data=data, temp_dir=temp_dir)


def replace_changed_plugin_source_files(
    *,
    game_data: GameData,
    changed_file_names: list[str],
) -> None:
    """把变化后的插件源码文件逐个替换到激活版目录。"""
    active_dir = game_data.layout.js_dir / "plugins"
    for file_name in changed_file_names:
        replace_text_file(
            target_path=active_dir / file_name,
            content=game_data.writable_plugin_source_files[file_name],
            temp_dir=active_dir,
        )


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


def cleanup_path(target_path: Path) -> None:
    """清理临时目录或临时文件。"""
    if target_path.is_dir():
        shutil.rmtree(target_path, ignore_errors=True)
    elif target_path.exists():
        target_path.unlink()


__all__: list[str] = [
    "collect_all_data_file_names",
    "collect_all_plugin_source_file_names",
    "collect_changed_data_file_names",
    "collect_changed_plugin_source_file_names",
    "ensure_full_data_origin_backup",
    "is_plugins_file_changed",
    "reset_writable_copies",
    "write_game_files",
]
