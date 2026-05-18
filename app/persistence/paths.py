"""多游戏数据库路径解析服务。"""

from __future__ import annotations

from pathlib import Path

from app.runtime_paths import resolve_app_path

DB_DIRECTORY = resolve_app_path("data", "db")
INVALID_FILE_NAME_CHARS = set('<>:"/\\|?*')


def resolve_default_db_directory() -> Path:
    """解析默认多游戏数据库目录。"""
    return resolve_app_path("data", "db")


def ensure_db_directory(db_directory: Path | None = None) -> Path:
    """确保固定数据库目录存在。"""
    resolved_db_directory = db_directory if db_directory is not None else resolve_default_db_directory()
    resolved_db_directory.mkdir(parents=True, exist_ok=True)
    return resolved_db_directory


def build_db_path(game_title: str, db_directory: Path | None = None) -> Path:
    """根据游戏标题生成固定数据库路径。"""
    invalid_chars = sorted({char for char in game_title if char in INVALID_FILE_NAME_CHARS})
    if invalid_chars:
        joined_chars = "".join(invalid_chars)
        raise ValueError(f"游戏标题包含非法文件名字，无法创建数据库: {joined_chars}")
    resolved_db_directory = db_directory if db_directory is not None else resolve_default_db_directory()
    return resolved_db_directory / f"{game_title}.db"
