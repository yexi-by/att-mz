"""游戏注册与环境诊断命令。

本模块负责列出、注册游戏，并把环境诊断服务适配为 CLI 子命令。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.agent_toolkit import AgentReport, AgentToolkitService
from app.agent_toolkit.reports import issue
from app.cli.arguments import read_bool_arg, read_optional_path_arg, read_optional_str_arg, read_str_arg
from app.cli.errors import CliBusinessError
from app.cli.runtime import HandlerSession, resolve_optional_target_game_title
from app.cli.reports import print_report, write_report_outputs
from app.game_reset import reset_registered_game
from app.language import parse_source_language
from app.persistence import GameRegistry
from app.source_language_probe import build_source_language_probe_report


async def run_list_command(args: argparse.Namespace) -> int:
    """执行 `list` 命令。"""
    _ = args
    registry = GameRegistry()
    items, registry_issues = await registry.list_games_with_issues()
    report = AgentReport.from_parts(
        errors=[],
        warnings=[
            issue("registered_game_unreadable", f"已跳过不可用游戏数据库: {item.db_path}；{item.message}")
            for item in registry_issues
        ],
        summary={"game_count": len(items), "skipped_database_count": len(registry_issues)},
        details={
            "games": [
                {
                    "game_title": item.game_title,
                    "engine_kind": item.engine_kind,
                    "engine_version": item.engine_version,
                    "source_language": item.source_language,
                    "target_language": item.target_language,
                    "game_path": str(item.game_path),
                    "content_root": str(item.content_root),
                    "db_path": str(item.db_path),
                }
                for item in items
            ],
            "skipped_databases": [
                {
                    "db_path": str(item.db_path),
                    "message": item.message,
                }
                for item in registry_issues
            ],
        },
    )
    print_report(report)
    return 0


async def run_add_game_command(args: argparse.Namespace) -> int:
    """执行 `add-game` 命令。"""
    game_path = Path(read_str_arg(args, "path"))
    source_language = parse_source_language(read_str_arg(args, "source_language"))
    async with HandlerSession() as handler:
        try:
            game_title = await handler.add_game(game_path, source_language=source_language)
        except FileExistsError as error:
            raise CliBusinessError(str(error)) from error
        report = AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "game_title": game_title,
                "source_language": source_language,
                "target_language": "zh-Hans",
            },
            details={"next_game_argument": game_title},
        )
        print_report(report)
    return 0


async def run_probe_source_language_command(args: argparse.Namespace) -> int:
    """执行注册前源语言探测命令。"""
    game_path = Path(read_str_arg(args, "path"))
    report = await build_source_language_probe_report(game_path)
    write_report_outputs(report=report, args=args, title="源语言探测报告")
    return 1 if report.status == "error" else 0


async def run_reset_game_command(args: argparse.Namespace) -> int:
    """执行 `reset-game` 危险回溯命令。"""
    game_title = read_optional_str_arg(args, "game")
    game_path = read_optional_path_arg(args, "game_path")
    if game_title is None and game_path is None:
        raise CliBusinessError("reset-game 必须提供 --game 或 --game-path")
    confirm_game_title = getattr(args, "confirm_game_title", None)
    if confirm_game_title is not None and not isinstance(confirm_game_title, str):
        raise TypeError("--confirm-game-title 必须是字符串")
    report = await reset_registered_game(
        game_title=game_title,
        game_path=game_path,
        dry_run=read_bool_arg(args, "dry_run"),
        confirm_game_title=confirm_game_title,
    )
    write_report_outputs(report=report, args=args, title="游戏注册回溯报告")
    return 1 if report.status == "error" else 0


async def run_doctor_command(args: argparse.Namespace) -> int:
    """执行 `doctor` 命令。"""
    game_title = await resolve_optional_target_game_title(args)
    check_llm = not read_bool_arg(args, "no_check_llm")
    service = AgentToolkitService()
    report = await service.doctor(game_title=game_title, check_llm=check_llm)
    write_report_outputs(report=report, args=args, title="环境诊断报告")
    return 1 if report.status == "error" else 0
