"""运行目录解析测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import runtime_paths
from app.application.font_replacement import resolve_replacement_font_path
from app.config.custom_placeholder_rules import resolve_custom_placeholder_rules_path
from app.observability import resolve_log_file_path
from app.persistence import GameRegistry, build_db_path, resolve_default_db_directory
from app.utils.config_loader_utils import resolve_setting_path


def test_app_home_uses_environment_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """应用运行目录优先使用显式环境变量。"""
    monkeypatch.setenv(runtime_paths.APP_HOME_ENV_NAME, str(tmp_path))

    assert runtime_paths.resolve_app_home() == tmp_path.resolve()
    assert runtime_paths.resolve_app_home_path("setting.toml") == (tmp_path / "setting.toml").resolve()


def test_app_home_uses_executable_directory_when_packaged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """发布态默认把可执行文件所在目录作为应用运行目录。"""
    fake_executable = tmp_path / "att-mz.exe"
    monkeypatch.delenv(runtime_paths.APP_HOME_ENV_NAME, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_executable))
    monkeypatch.setitem(runtime_paths.__dict__, "__compiled__", object())

    assert runtime_paths.resolve_app_home() == tmp_path.resolve()


def test_app_home_uses_pex_entrypoint_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PEX scie 发布包默认把入口文件所在目录作为应用运行目录。"""
    fake_entrypoint = tmp_path / "att-mz.exe"
    monkeypatch.delenv(runtime_paths.APP_HOME_ENV_NAME, raising=False)
    monkeypatch.setenv("__PEX_EXE__", str(fake_entrypoint))
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "cache" / "bootstrap.py")])

    assert runtime_paths.resolve_app_home() == tmp_path.resolve()


def test_app_home_uses_non_python_executable_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """缺少 PEX 环境变量时仍可从当前入口文件识别发布目录。"""
    fake_entrypoint = tmp_path / "att-mz.exe"
    monkeypatch.delenv(runtime_paths.APP_HOME_ENV_NAME, raising=False)
    monkeypatch.delenv("PEX", raising=False)
    monkeypatch.delenv("SCIE", raising=False)
    monkeypatch.setattr(sys, "argv", [str(fake_entrypoint)])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    assert runtime_paths.resolve_app_home() == tmp_path.resolve()


def test_default_project_paths_use_app_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """配置、数据库、日志和规则文件默认都落在应用运行目录下。"""
    monkeypatch.setenv(runtime_paths.APP_HOME_ENV_NAME, str(tmp_path))

    assert resolve_setting_path() == (tmp_path / "setting.toml").resolve()
    assert resolve_default_db_directory() == (tmp_path / "data" / "db").resolve()
    assert GameRegistry().db_directory == (tmp_path / "data" / "db").resolve()
    assert build_db_path("测试游戏") == (tmp_path / "data" / "db" / "测试游戏.db").resolve()
    assert resolve_log_file_path() == (tmp_path / "logs" / "app.log").resolve()
    assert resolve_custom_placeholder_rules_path() == (tmp_path / "custom_placeholder_rules.json").resolve()


def test_relative_replacement_font_uses_app_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """候选覆盖字体的相对路径按应用运行目录解析。"""
    font_path = tmp_path / "fonts" / "Test.ttf"
    font_path.parent.mkdir()
    _ = font_path.write_bytes(b"font")
    monkeypatch.setenv(runtime_paths.APP_HOME_ENV_NAME, str(tmp_path))

    assert resolve_replacement_font_path("fonts/Test.ttf") == font_path.resolve()
