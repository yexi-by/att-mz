"""CLI 机器可读 JSON 输出薄契约测试。"""

from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
from typing import cast

import pytest
from pytest import CaptureFixture, MonkeyPatch

from main import main

from app.agent_toolkit import AgentReport
from app.application.errors import WorkflowGateError
from app.cli import build_parser, parser_command_names, registered_command_names, write_report_outputs
from app.cli.errors import CliArgumentError
from app.cli.reports import SAMPLED_STDOUT_REPORT_POLICY
from app.runtime_paths import APP_HOME_ENV_NAME
from app.rmmz.json_types import JsonObject, coerce_json_value, ensure_json_array, ensure_json_object


def _stdout_json(capsys: CaptureFixture[str]) -> JsonObject:
    """读取 CLI stdout 中的 JSON 报告。"""
    captured = capsys.readouterr()
    payload = cast(object, json.loads(captured.out))
    return ensure_json_object(coerce_json_value(payload), "CLI JSON 输出")


def test_parser_commands_have_dispatch_handlers() -> None:
    """解析器暴露的每个子命令都必须在分发器中有处理函数。"""
    parser = build_parser()

    assert parser_command_names(parser) == registered_command_names()


def test_add_game_requires_explicit_source_language() -> None:
    """注册游戏必须显式声明源语言，避免 CLI 默默按日文处理。"""
    parser = build_parser()

    with pytest.raises(CliArgumentError):
        _ = parser.parse_args(["add-game", "--path", "demo"])

    args = parser.parse_args(["add-game", "--path", "demo", "--source-language", "ja"])
    assert getattr(args, "source_language") == "ja"


def test_global_debug_switches_parse() -> None:
    """debug 总开关和子功能开关必须作为全局 CLI 参数解析。"""
    parser = build_parser()

    args = parser.parse_args(
        [
            "--debug",
            "--debug-timings",
            "--debug-llm-messages",
            "--no-debug-logging",
            "translate",
            "--game",
            "demo",
        ]
    )

    assert getattr(args, "debug") is True
    assert getattr(args, "debug_timings") is True
    assert getattr(args, "debug_llm_messages") is True
    assert getattr(args, "debug_logging") is False


def test_debug_llm_messages_cli_requires_debug_enabled(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """显式开启 LLM 消息观测时必须同时开启 debug 总开关。"""
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(tmp_path))

    exit_code = main(["--debug-llm-messages", "translate", "--game", "demo"])

    payload = _stdout_json(capsys)
    errors = ensure_json_array(payload["errors"], "errors")
    first_error = ensure_json_object(errors[0], "errors[0]")

    assert exit_code == 2
    assert first_error["code"] == "argument_error"
    assert "--debug-llm-messages" in str(first_error["message"])
    assert "--debug" in str(first_error["message"])


def test_unknown_command_reports_json_argument_error(capsys: CaptureFixture[str]) -> None:
    """未知命令必须返回机器可读参数错误。"""
    exit_code = main(["unknown-command"])

    payload = _stdout_json(capsys)
    errors = ensure_json_array(payload["errors"], "errors")
    first_error = ensure_json_object(errors[0], "errors[0]")

    assert exit_code == 2
    assert payload["status"] == "error"
    assert first_error["code"] == "argument_error"


def test_json_command_reports_application_gate_error_as_business_error(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """应用层硬闸失败在 JSON CLI 中必须是业务错误。"""

    async def fake_dispatch_command(args: object) -> int:
        """模拟翻译前置检查失败。"""
        _ = args
        raise WorkflowGateError("检查没通过，不能继续：插件规则为空")

    monkeypatch.setattr("app.cli_main.dispatch_command", fake_dispatch_command)

    exit_code = main(["translate", "--game", "demo"])

    payload = _stdout_json(capsys)
    errors = ensure_json_array(payload["errors"], "errors")
    first_error = ensure_json_object(errors[0], "errors[0]")

    assert exit_code == 1
    assert first_error["code"] == "business_error"
    assert "插件规则为空" in str(first_error["message"])


def test_report_output_can_leave_data_output_file_untouched(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """业务数据导出命令打印报告时不得覆盖自己的输出文件。"""
    output_path = tmp_path / "pending-translations.json"
    data_json = '{"entry": {"translation_lines": []}}\n'
    output_path.write_text(data_json, encoding="utf-8")
    report = AgentReport(status="ok", summary={"exported_item_count": 1})

    write_report_outputs(
        report=report,
        args=Namespace(output=str(output_path)),
        title="手动填写译文表导出报告",
        write_output_file=False,
    )

    payload = _stdout_json(capsys)
    assert payload["status"] == "ok"
    assert output_path.read_text(encoding="utf-8") == data_json


def test_validation_report_output_writes_full_file_and_prints_summary(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """大校验报告的完整明细写入文件，stdout 只保留计数和样例。"""
    output_path = tmp_path / "validation-report.json"
    report = AgentReport(
        status="ok",
        summary={"candidate_count": 25},
        details={"matched_candidates": [{"index": index} for index in range(25)]},
    )

    write_report_outputs(
        report=report,
        args=Namespace(output=str(output_path)),
        title="校验报告",
        detail_policy=SAMPLED_STDOUT_REPORT_POLICY,
    )

    stdout_payload = _stdout_json(capsys)
    output_payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(output_path.read_text(encoding="utf-8")))),
        "output JSON",
    )
    stdout_summary = ensure_json_object(stdout_payload["summary"], "stdout summary")
    output_summary = ensure_json_object(output_payload["summary"], "output summary")
    stdout_details = ensure_json_object(stdout_payload["details"], "stdout details")
    stdout_matches = ensure_json_object(stdout_details["matched_candidates"], "stdout matched_candidates")
    output_details = ensure_json_object(output_payload["details"], "output details")
    output_matches = ensure_json_array(output_details["matched_candidates"], "output matched_candidates")

    assert stdout_summary["report_detail_mode"] == "sampled"
    assert output_summary["report_detail_mode"] == "full"
    assert stdout_matches["count"] == 25
    assert len(ensure_json_array(stdout_matches["samples"], "stdout matched_candidates.samples")) == 20
    assert stdout_matches["omitted_count"] == 5
    assert len(output_matches) == 25
