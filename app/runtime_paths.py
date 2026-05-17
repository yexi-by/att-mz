"""运行目录解析工具。

本模块负责统一判断当前程序应该把配置、数据库、日志和随包资源放在哪里。
开发态默认使用源码根目录；发布态默认使用可执行文件所在目录；用户也可以通过
`ATT_MZ_HOME` 显式指定完整应用目录。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_HOME_ENV_NAME = "ATT_MZ_HOME"
_PYTHON_EXECUTABLE_NAMES = {"python.exe", "pythonw.exe", "python", "pythonw"}


def source_root() -> Path:
    """返回源码布局下的项目根目录。"""
    return Path(__file__).resolve().parents[1]


def is_packaged_runtime() -> bool:
    """判断当前是否运行在打包后的可执行程序中。"""
    frozen_value = getattr(sys, "frozen", False)
    if isinstance(frozen_value, bool) and frozen_value:
        return True
    return "__compiled__" in globals()


def executable_directory() -> Path:
    """返回当前进程可执行文件所在目录。"""
    return Path(sys.executable).resolve().parent


def _resolve_packaged_executable(path_text: str | None) -> Path | None:
    """从候选路径中识别发布包入口可执行文件。"""
    if path_text is None or not path_text.strip():
        return None
    candidate = Path(path_text).expanduser()
    if candidate.suffix.lower() != ".exe":
        return None
    if candidate.name.lower() in _PYTHON_EXECUTABLE_NAMES:
        return None
    resolved = candidate.resolve()
    if ".venv" in {part.lower() for part in resolved.parts}:
        return None
    return resolved


def packaged_entrypoint_path() -> Path | None:
    """返回 PEX scie 等单文件发布入口路径。"""
    for env_name in ("__PEX_EXE__", "PEX", "SCIE"):
        candidate = _resolve_packaged_executable(os.environ.get(env_name))
        if candidate is not None:
            return candidate
    argv0 = sys.argv[0] if sys.argv else None
    return _resolve_packaged_executable(argv0)


def resolve_app_home() -> Path:
    """解析应用运行目录。"""
    env_value = os.environ.get(APP_HOME_ENV_NAME)
    if env_value is not None and env_value.strip():
        return Path(env_value).expanduser().resolve()
    if is_packaged_runtime():
        return executable_directory()
    packaged_entrypoint = packaged_entrypoint_path()
    if packaged_entrypoint is not None:
        return packaged_entrypoint.parent
    return source_root()


def resolve_app_path(*parts: str) -> Path:
    """在应用运行目录下拼接路径。"""
    return resolve_app_home().joinpath(*parts).resolve()


def resolve_app_home_path(path_text: str | Path) -> Path:
    """把绝对路径原样解析，把相对路径解析到应用运行目录下。"""
    path = Path(path_text)
    if path.is_absolute():
        return path.resolve()
    return (resolve_app_home() / path).resolve()


__all__: list[str] = [
    "APP_HOME_ENV_NAME",
    "executable_directory",
    "is_packaged_runtime",
    "packaged_entrypoint_path",
    "resolve_app_home",
    "resolve_app_home_path",
    "resolve_app_path",
    "source_root",
]
