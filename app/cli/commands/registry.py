"""游戏注册与环境诊断命令。

本模块负责列出、注册游戏，并把环境诊断服务适配为 CLI 子命令。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.agent_toolkit import AgentReport, AgentToolkitService
from app.cli.arguments import read_bool_arg, read_str_arg
from app.cli.errors import CliBusinessError
from app.cli.runtime import HandlerSession, resolve_optional_target_game_title
from app.cli.reports import write_report_outputs
from app.language import parse_source_language
from app.persistence import GameRegistry


async def run_list_command(args: argparse.Namespace) -> int:
    """执行 `list` 命令。"""
    _ = args
    registry = GameRegistry()
    items = await registry.list_games()
    report = AgentReport.from_parts(
        errors=[],
        warnings=[],
        summary={"game_count": len(items)},
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
            ]
        },
    )
    print(report.to_json_text())
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
        print(report.to_json_text())
    return 0


async def run_doctor_command(args: argparse.Namespace) -> int:
    """执行 `doctor` 命令。"""
    game_title = await resolve_optional_target_game_title(args)
    check_llm = not read_bool_arg(args, "no_check_llm")
    service = AgentToolkitService()
    report = await service.doctor(game_title=game_title, check_llm=check_llm)
    write_report_outputs(report=report, args=args, title="环境诊断报告")
    return 1 if report.status == "error" else 0
