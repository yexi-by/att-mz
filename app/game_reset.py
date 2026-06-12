"""已注册游戏回到注册前状态的危险操作。"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.agent_toolkit.reports import AgentIssue, AgentReport, issue
from app.application.file_writer import cleanup_path, replace_text_file_from_path
from app.application.font_replacement.constants import (
    FONTS_DIRECTORY_NAME,
    GAMEFONT_CSS_FILE_NAME,
    GAMEFONT_CSS_ORIGIN_FILE_NAME,
)
from app.persistence import GameRegistry, build_db_path
from app.persistence.repository import (
    check_connection_readable,
    open_connection,
    read_metadata,
    read_source_snapshot_records,
)
from app.rmmz.source_snapshot import SourceSnapshotFileRecord
from app.rmmz.json_types import JsonArray, JsonObject
from app.rmmz.schema import (
    DATA_DIRECTORY_NAME,
    DATA_ORIGIN_DIRECTORY_NAME,
    JS_DIRECTORY_NAME,
    PLUGINS_FILE_NAME,
    PLUGINS_ORIGIN_FILE_NAME,
    PLUGIN_SOURCE_ORIGIN_DIRECTORY_NAME,
    EngineKind,
    GameLayout,
)
from app.rmmz.source_snapshot import remove_source_snapshot_artifacts, validate_source_snapshot_manifest


@dataclass(frozen=True, slots=True)
class GameResetPlan:
    """一次游戏注册回溯操作的文件计划。"""

    game_title: str
    game_path: Path
    content_root: Path
    db_path: Path
    layout: GameLayout
    data_file_count: int
    plugin_source_restore_names: list[str]
    plugin_source_delete_names: list[str]
    restores_gamefont_css: bool
    db_sidecar_paths: list[Path]


@dataclass(frozen=True, slots=True)
class GameResetTarget:
    """reset-game 所需的最小注册信息。"""

    game_title: str
    game_path: Path
    content_root: Path
    db_path: Path
    engine_kind: EngineKind
    engine_version: str
    snapshot_records: list[SourceSnapshotFileRecord]


async def reset_registered_game(
    *,
    dry_run: bool,
    confirm_game_title: str | None,
    game_title: str | None = None,
    game_path: Path | None = None,
    game_registry: GameRegistry | None = None,
) -> AgentReport:
    """把已注册游戏恢复到注册前状态，并删除本项目注册痕迹。

    Args:
        game_title: 已注册游戏标题。
        dry_run: 只输出计划，不修改文件。
        confirm_game_title: 真正执行时必须等于游戏标题。
        game_registry: 测试或嵌入调用时注入的注册表。

    Returns:
        面向 CLI 和外部 Agent 的机器可读报告。
    """
    registry = game_registry or GameRegistry()
    errors: list[AgentIssue] = []
    warnings: list[AgentIssue] = []
    plan: GameResetPlan | None = None
    try:
        target = await resolve_game_reset_target(
            registry=registry,
            game_title=game_title,
            game_path=game_path,
        )
    except Exception as error:
        return AgentReport.from_parts(
            errors=[issue("reset_target", str(error))],
            warnings=[],
            summary={
                "game_title": game_title or "",
                "game_path": str(game_path) if game_path is not None else "",
                "mode": "dry_run" if dry_run else "blocked",
                "changed": False,
            },
            details={},
        )

    layout = build_layout_from_target(target)
    snapshot_records = target.snapshot_records
    if not snapshot_records:
        errors.append(issue("source_snapshot_missing", "当前游戏数据库缺少可信源快照记录，不能执行时光回溯"))
    try:
        if snapshot_records:
            validate_source_snapshot_manifest(layout=layout, records=snapshot_records)
    except Exception as error:
        errors.append(issue("source_snapshot_invalid", str(error)))
    if not _is_path_inside(layout.content_root, layout.game_root):
        errors.append(issue("registered_path_invalid", f"游戏内容目录不在游戏根目录内: {layout.content_root}"))
    if not _is_path_inside(target.db_path, registry.db_directory):
        errors.append(issue("registered_db_invalid", f"游戏数据库不在注册表目录内: {target.db_path}"))
    if not errors:
        plan = build_game_reset_plan(target=target, layout=layout)
        warnings.extend(build_game_reset_warnings(plan))

    if plan is None:
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "game_title": game_title,
                "game_path": str(game_path) if game_path is not None else "",
                "mode": "dry_run" if dry_run else "blocked",
                "changed": False,
            },
            details={},
        )

    if dry_run:
        return build_game_reset_report(
            plan=plan,
            errors=[],
            warnings=warnings,
            mode="dry_run",
            changed=False,
        )

    if confirm_game_title != plan.game_title:
        errors.append(
            issue(
                "dangerous_confirmation_required",
                f"reset-game 会覆盖当前运行文件并删除游戏数据库；真正执行必须传入 --confirm-game-title {plan.game_title}",
            )
        )
        return build_game_reset_report(
            plan=plan,
            errors=errors,
            warnings=warnings,
            mode="confirmation_required",
            changed=False,
        )

    execute_game_reset_plan(plan)
    return build_game_reset_report(
        plan=plan,
        errors=[],
        warnings=warnings,
        mode="reset",
        changed=True,
    )


async def resolve_game_reset_target(
    *,
    registry: GameRegistry,
    game_title: str | None,
    game_path: Path | None,
) -> GameResetTarget:
    """宽松解析 reset-game 目标，不要求整库 schema 与当前版本一致。"""
    if (game_title is None) == (game_path is None):
        raise ValueError("reset-game 必须且只能提供 --game 或 --game-path")
    if game_title is not None:
        db_path = build_db_path(game_title, registry.db_directory)
        if not db_path.is_file():
            raise FileNotFoundError(f"未找到游戏数据库: {game_title}")
        target = await read_game_reset_target_from_db(db_path)
        if target.game_title != game_title:
            raise RuntimeError(f"数据库元数据标题不匹配: 期望 {game_title}，实际 {target.game_title}")
        return target

    if game_path is None:
        raise ValueError("reset-game 缺少游戏路径")
    requested_path = game_path.resolve()
    if not requested_path.exists():
        raise FileNotFoundError(f"游戏目录不存在: {requested_path}")
    if not registry.db_directory.is_dir():
        raise FileNotFoundError(f"游戏数据库目录不存在: {registry.db_directory}")
    for db_path in sorted(registry.db_directory.glob("*.db")):
        try:
            target = await read_game_reset_target_from_db(db_path)
        except Exception:
            continue
        if target.game_path == requested_path or target.content_root == requested_path:
            return target
    raise ValueError(f"游戏目录尚未注册，请先执行 add-game: {requested_path}")


async def read_game_reset_target_from_db(db_path: Path) -> GameResetTarget:
    """从数据库读取 reset-game 最小必需信息，不做完整 schema 校验。"""
    connection = await open_connection(db_path)
    try:
        await check_connection_readable(connection=connection, db_path=db_path)
        metadata = await read_metadata(connection=connection, db_path=db_path)
        snapshot_records = await read_source_snapshot_records(
            connection=connection,
            db_path=db_path,
        )
        return GameResetTarget(
            game_title=metadata.game_title,
            game_path=metadata.game_path,
            content_root=metadata.content_root,
            db_path=db_path,
            engine_kind=metadata.engine_kind,
            engine_version=metadata.engine_version,
            snapshot_records=snapshot_records,
        )
    finally:
        await connection.close()


def build_layout_from_target(target: GameResetTarget) -> GameLayout:
    """只依赖注册元数据重建布局，允许激活 data 或 plugins.js 已损坏。"""
    content_root = target.content_root.resolve()
    game_root = target.game_path.resolve()
    js_dir = content_root / JS_DIRECTORY_NAME
    return GameLayout(
        game_root=game_root,
        content_root=content_root,
        data_dir=content_root / DATA_DIRECTORY_NAME,
        data_origin_dir=content_root / DATA_ORIGIN_DIRECTORY_NAME,
        js_dir=js_dir,
        plugins_path=js_dir / PLUGINS_FILE_NAME,
        plugins_origin_path=js_dir / PLUGINS_ORIGIN_FILE_NAME,
        plugin_source_origin_dir=js_dir / PLUGIN_SOURCE_ORIGIN_DIRECTORY_NAME,
        package_path=target.content_root / "package.json",
        engine_kind=target.engine_kind,
        engine_version=target.engine_version,
        is_www_layout=content_root != game_root,
    )


def build_game_reset_plan(*, target: GameResetTarget, layout: GameLayout) -> GameResetPlan:
    """根据当前磁盘状态生成回溯计划。"""
    origin_plugin_names = _direct_js_file_names(layout.plugin_source_origin_dir)
    active_plugin_names = _direct_js_file_names(layout.js_dir / "plugins")
    db_sidecar_paths = [
        path
        for path in (
            target.db_path.with_name(target.db_path.name + suffix)
            for suffix in ("-wal", "-shm", "-journal")
        )
        if path.exists()
    ]
    return GameResetPlan(
        game_title=target.game_title,
        game_path=target.game_path,
        content_root=target.content_root,
        db_path=target.db_path,
        layout=layout,
        data_file_count=_count_files(layout.data_origin_dir),
        plugin_source_restore_names=origin_plugin_names,
        plugin_source_delete_names=sorted(set(active_plugin_names) - set(origin_plugin_names)),
        restores_gamefont_css=_gamefont_origin_path(layout).is_file(),
        db_sidecar_paths=db_sidecar_paths,
    )


def build_game_reset_warnings(plan: GameResetPlan) -> list[AgentIssue]:
    """生成回溯计划中无法证明完全恢复的边界提醒。"""
    warnings: list[AgentIssue] = []
    if plan.restores_gamefont_css:
        warnings.append(
            issue(
                "font_file_inventory_not_snapshotted",
                "将还原 gamefont.css 并删除 gamefont_origin.css；字体目录文件清单没有注册快照，不能安全判断替换字体文件是否应删除",
            )
        )
    return warnings


def execute_game_reset_plan(plan: GameResetPlan) -> None:
    """执行回溯计划；先恢复当前运行文件，再删除注册痕迹。"""
    layout = plan.layout
    _restore_directory_from_snapshot(
        source_dir=layout.data_origin_dir,
        target_dir=layout.data_dir,
        temp_parent=layout.content_root,
    )
    replace_text_file_from_path(
        target_path=layout.plugins_path,
        source_path=layout.plugins_origin_path,
        temp_dir=layout.js_dir,
    )
    _restore_direct_plugin_sources(
        source_dir=layout.plugin_source_origin_dir,
        target_dir=layout.js_dir / "plugins",
        temp_parent=layout.js_dir,
    )
    origin_css_path = _gamefont_origin_path(layout)
    if origin_css_path.is_file():
        replace_text_file_from_path(
            target_path=_gamefont_active_path(layout),
            source_path=origin_css_path,
            temp_dir=origin_css_path.parent,
        )
        origin_css_path.unlink()

    remove_source_snapshot_artifacts(layout)
    _delete_database_files(plan)


def build_game_reset_report(
    *,
    plan: GameResetPlan,
    errors: list[AgentIssue],
    warnings: list[AgentIssue],
    mode: str,
    changed: bool,
) -> AgentReport:
    """把回溯计划和执行结果转换为统一 JSON 报告。"""
    delete_paths: JsonArray = [
        str(plan.layout.data_origin_dir),
        str(plan.layout.plugins_origin_path),
        str(plan.layout.plugin_source_origin_dir),
        str(_gamefont_origin_path(plan.layout)),
        str(plan.db_path),
        *[str(path) for path in plan.db_sidecar_paths],
    ]
    details: JsonObject = {
        "restore": {
            "data": {
                "from": str(plan.layout.data_origin_dir),
                "to": str(plan.layout.data_dir),
                "file_count": plan.data_file_count,
            },
            "plugins": {
                "from": str(plan.layout.plugins_origin_path),
                "to": str(plan.layout.plugins_path),
            },
            "plugin_sources": {
                "from_dir": str(plan.layout.plugin_source_origin_dir),
                "to_dir": str(plan.layout.js_dir / "plugins"),
                "restored_file_names": list(plan.plugin_source_restore_names),
                "deleted_extra_file_names": list(plan.plugin_source_delete_names),
            },
            "gamefont_css": {
                "from": str(_gamefont_origin_path(plan.layout)),
                "to": str(_gamefont_active_path(plan.layout)),
                "will_restore": plan.restores_gamefont_css,
            },
        },
        "delete": {
            "paths": delete_paths,
        },
    }
    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "game_title": plan.game_title,
            "mode": mode,
            "changed": changed,
            "game_path": str(plan.game_path),
            "content_root": str(plan.content_root),
            "db_path": str(plan.db_path),
            "restored_data_file_count": plan.data_file_count if changed else 0,
            "restored_plugin_source_file_count": len(plan.plugin_source_restore_names) if changed else 0,
            "deleted_extra_plugin_source_file_count": len(plan.plugin_source_delete_names) if changed else 0,
            "restored_gamefont_css": plan.restores_gamefont_css and changed,
            "deleted_database": changed,
            "deleted_source_snapshot": changed,
        },
        details=details,
    )


def _restore_directory_from_snapshot(*, source_dir: Path, target_dir: Path, temp_parent: Path) -> None:
    """用快照目录替换目标目录，并在单目录范围内失败回滚。"""
    if not source_dir.is_dir():
        raise NotADirectoryError(f"可信源快照目录不存在: {source_dir}")
    temp_parent.mkdir(parents=True, exist_ok=True)
    transaction_dir = Path(tempfile.mkdtemp(prefix="att_mz_reset_", dir=temp_parent))
    staged_dir = transaction_dir / "staged"
    backup_dir = transaction_dir / "active_backup"
    target_existed = target_dir.exists()
    try:
        _ = shutil.copytree(source_dir, staged_dir)
        if target_existed:
            _ = target_dir.rename(backup_dir)
        _ = staged_dir.rename(target_dir)
    except Exception:
        if target_existed and not target_dir.exists() and backup_dir.exists():
            _ = backup_dir.rename(target_dir)
        raise
    finally:
        cleanup_path(transaction_dir)


def _restore_direct_plugin_sources(*, source_dir: Path, target_dir: Path, temp_parent: Path) -> None:
    """恢复 `js/plugins` 直接 JS 文件，并删除注册后新增的直接 JS 文件。"""
    if not source_dir.is_dir():
        raise NotADirectoryError(f"可信源插件源码备份目录不存在: {source_dir}")
    temp_parent.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    transaction_dir = Path(tempfile.mkdtemp(prefix="att_mz_reset_plugins_", dir=temp_parent))
    backups: dict[Path, Path] = {}
    created_targets: set[Path] = set()
    try:
        origin_paths = {source_path.name: source_path for source_path in _direct_js_files(source_dir)}
        for target_path in _direct_js_files(target_dir):
            if target_path.name in origin_paths:
                continue
            backup_path = transaction_dir / f"delete_{target_path.name}"
            _ = shutil.copy2(target_path, backup_path)
            backups[target_path] = backup_path
            target_path.unlink()
        for file_name, source_path in origin_paths.items():
            target_path = target_dir / file_name
            if target_path.exists() and target_path not in backups:
                backup_path = transaction_dir / f"replace_{file_name}"
                _ = shutil.copy2(target_path, backup_path)
                backups[target_path] = backup_path
            if not target_path.exists():
                created_targets.add(target_path)
            replace_text_file_from_path(
                target_path=target_path,
                source_path=source_path,
                temp_dir=target_dir,
            )
    except Exception:
        for target_path in created_targets:
            if target_path.exists() and target_path not in backups:
                target_path.unlink()
        for target_path, backup_path in backups.items():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copy2(backup_path, target_path)
        raise
    finally:
        cleanup_path(transaction_dir)


def _delete_database_files(plan: GameResetPlan) -> None:
    """删除游戏数据库及 SQLite 临时边车文件。"""
    for db_path in [plan.db_path, *plan.db_sidecar_paths]:
        if db_path.exists():
            db_path.unlink()


def _direct_js_files(directory: Path) -> list[Path]:
    """列出目录中的直接 JS 文件。"""
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.glob("*.js") if path.is_file()),
        key=lambda path: path.name.lower(),
    )


def _direct_js_file_names(directory: Path) -> list[str]:
    """列出目录中的直接 JS 文件名。"""
    return [path.name for path in _direct_js_files(directory)]


def _count_files(directory: Path) -> int:
    """统计目录内全部普通文件数量。"""
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.rglob("*") if path.is_file())


def _gamefont_active_path(layout: GameLayout) -> Path:
    """返回激活字体样式表路径。"""
    return layout.content_root / FONTS_DIRECTORY_NAME / GAMEFONT_CSS_FILE_NAME


def _gamefont_origin_path(layout: GameLayout) -> Path:
    """返回字体样式表原始备份路径。"""
    return layout.content_root / FONTS_DIRECTORY_NAME / GAMEFONT_CSS_ORIGIN_FILE_NAME


def _is_path_inside(path: Path, parent: Path) -> bool:
    """判断路径是否位于指定父目录内。"""
    try:
        _ = path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


__all__ = [
    "build_game_reset_plan",
    "build_layout_from_target",
    "execute_game_reset_plan",
    "resolve_game_reset_target",
    "reset_registered_game",
]
