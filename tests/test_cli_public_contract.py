"""公开 CLI 主链路薄契约测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pytest import CaptureFixture

from app.cli_main import main
from app.rmmz.json_types import JsonObject


def _read_stdout_json(capsys: CaptureFixture[str]) -> JsonObject:
    """读取公开 CLI stdout 中的单个 JSON 报告。"""
    captured = capsys.readouterr()
    stdout = captured.out.strip()
    assert stdout, f"CLI 没有输出 JSON 报告，stderr={captured.err}"
    payload = cast(object, json.loads(stdout))
    assert isinstance(payload, dict)
    return cast(JsonObject, payload)


def _run_cli(
    argv: list[str],
    capsys: CaptureFixture[str],
    *,
    expected_code: int = 0,
    expected_statuses: set[str] | None = None,
) -> JsonObject:
    """通过公开 CLI main 入口运行命令并返回 stdout JSON。"""
    code = main(argv)
    report = _read_stdout_json(capsys)
    assert code == expected_code, json.dumps(report, ensure_ascii=False, indent=2)
    status = report.get("status")
    assert isinstance(status, str)
    assert status in (expected_statuses or {"ok"})
    return report


@pytest.mark.usefixtures("app_home_with_example_setting")
def test_public_cli_register_prepare_and_validate_workspace(
    minimal_game_dir: Path,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """公开 CLI 可注册游戏、准备工作区并校验当前工作区 JSON 报告。"""
    workspace = tmp_path / "agent-workspace"

    add_report = _run_cli(
        ["add-game", "--path", str(minimal_game_dir), "--source-language", "ja"],
        capsys,
    )
    prepare_report = _run_cli(
        ["prepare-agent-workspace", "--game", "テストゲーム", "--output-dir", str(workspace)],
        capsys,
    )
    validate_report = _run_cli(
        ["validate-agent-workspace", "--game", "テストゲーム", "--workspace", str(workspace)],
        capsys,
        expected_code=1,
        expected_statuses={"error"},
    )

    assert add_report["status"] == "ok"
    assert prepare_report["status"] == "ok"
    errors = validate_report.get("errors")
    assert isinstance(errors, list)
    error_codes = {error.get("code") for error in errors if isinstance(error, dict)}
    assert "terminology_empty_translation" in error_codes
    assert (workspace / "manifest.json").is_file()
    assert (workspace / "terminology" / "field-terms.json").is_file()


def test_public_cli_cleanup_workspace_keeps_unlisted_files(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """公开 CLI 清理工作区时只删除 manifest 列出的文件。"""
    workspace = tmp_path / "agent-workspace"
    generated_file = workspace / "generated.json"
    unlisted_file = workspace / "notes.txt"
    workspace.mkdir()
    generated_file.write_text("{}", encoding="utf-8")
    unlisted_file.write_text("keep", encoding="utf-8")
    manifest = {
        "files": [
            str(generated_file),
            str(workspace / "missing.json"),
            str(tmp_path / "outside.json"),
        ]
    }
    (workspace / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    cleanup_report = _run_cli(
        ["cleanup-agent-workspace", "--workspace", str(workspace)],
        capsys,
        expected_statuses={"warning"},
    )

    assert cleanup_report["status"] == "warning"
    summary = cleanup_report.get("summary")
    assert isinstance(summary, dict)
    assert summary["deleted_count"] == 2
    assert summary["unlisted_file_count"] == 1
    warnings = cleanup_report.get("warnings")
    assert isinstance(warnings, list)
    warning_codes = {warning.get("code") for warning in warnings if isinstance(warning, dict)}
    assert "workspace_unlisted_files_ignored" in warning_codes
    assert not generated_file.exists()
    assert not (workspace / "manifest.json").exists()
    assert unlisted_file.read_text(encoding="utf-8") == "keep"
