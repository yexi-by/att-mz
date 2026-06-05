"""阶段 0 业务级金丝雀测试。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import NoReturn, cast

import pytest
from pytest import CaptureFixture, MonkeyPatch

from app.agent_toolkit import AgentToolkitService
from app.cli_main import main
from app.config.environment import LLM_API_KEY_ENV_NAME, LLM_BASE_URL_ENV_NAME
from app.persistence import GameRegistry
from app.rmmz.json_types import JsonObject, JsonValue
from app.terminology import TerminologyCategory, TerminologyGlossary, TerminologyRegistry
from scripts.benchmark_small_tasks import FakeOpenAICompatibleServer


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: JsonValue) -> None:
    """写入测试 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_stdout_json(capsys: CaptureFixture[str]) -> JsonObject:
    """读取公开 CLI stdout 中的单个 Agent JSON 报告。"""
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
    assert code == expected_code, report
    status = report.get("status")
    assert isinstance(status, str)
    assert status in (expected_statuses or {"ok"})
    return report


def _summary(report: JsonObject) -> JsonObject:
    """读取报告 summary 对象。"""
    summary = report.get("summary")
    assert isinstance(summary, dict)
    return cast(JsonObject, summary)


def _fill_terminology_workspace(workspace: Path) -> None:
    """把工作区导出的字段译名表填完整，并同步生成正文术语表。"""
    field_terms_path = workspace / "terminology" / "field-terms.json"
    glossary_path = workspace / "terminology" / "glossary.json"
    registry = TerminologyRegistry.model_validate(json.loads(field_terms_path.read_text(encoding="utf-8")))
    filled_categories: dict[TerminologyCategory, dict[str, str]] = {}
    glossary_terms: dict[str, str] = {}
    for category, entries in registry.as_category_map().items():
        filled_entries = {source_text: f"{source_text}译" for source_text in entries}
        filled_categories[category] = filled_entries
        glossary_terms.update(filled_entries)
    filled_registry = TerminologyRegistry.from_category_map(filled_categories)
    filled_glossary = TerminologyGlossary(terms=glossary_terms)
    _ = field_terms_path.write_text(
        f"{filled_registry.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    _ = glossary_path.write_text(
        f"{filled_glossary.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )


def _import_workspace_file(
    capsys: CaptureFixture[str],
    workspace: Path,
    *,
    command: str,
    file_name: str,
    extra_args: list[str] | None = None,
) -> None:
    """导入工作区中的一个规则文件。"""
    input_path = workspace / file_name
    if not input_path.exists():
        return
    _ = _run_cli(
        [
            command,
            "--game",
            "テストゲーム",
            "--input",
            str(input_path),
            *(extra_args or []),
        ],
        capsys,
        expected_statuses={"ok", "warning"},
    )


@pytest.mark.usefixtures("app_home_with_example_setting")
def test_stage0_cli_agent_canary_runs_full_public_flow(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """公开 CLI 主链路可在临时工作目录和假模型下跑完。"""
    fake_server = FakeOpenAICompatibleServer()
    fake_server.start()
    monkeypatch.setenv(LLM_BASE_URL_ENV_NAME, fake_server.base_url)
    monkeypatch.setenv(LLM_API_KEY_ENV_NAME, "att-mz-stage0-fake-key")
    workspace = tmp_path / "agent-workspace"
    feedback_path = tmp_path / "feedback.json"
    font_target = app_home_with_example_setting / "fonts" / "NotoSansSC-Regular.ttf"
    font_target.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(ROOT / "fonts" / "NotoSansSC-Regular.ttf", font_target)
    try:
        _ = _run_cli(
            ["add-game", "--path", str(minimal_game_dir), "--source-language", "ja"],
            capsys,
            expected_statuses={"ok"},
        )
        _ = _run_cli(
            ["prepare-agent-workspace", "--game", "テストゲーム", "--output-dir", str(workspace)],
            capsys,
            expected_statuses={"ok"},
        )
        _fill_terminology_workspace(workspace)
        _ = _run_cli(
            ["validate-agent-workspace", "--game", "テストゲーム", "--workspace", str(workspace)],
            capsys,
            expected_statuses={"ok", "warning"},
        )
        _ = _run_cli(
            [
                "import-terminology",
                "--game",
                "テストゲーム",
                "--input",
                str(workspace / "terminology" / "field-terms.json"),
                "--glossary-input",
                str(workspace / "terminology" / "glossary.json"),
            ],
            capsys,
            expected_statuses={"ok"},
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-plugin-rules",
            file_name="plugin-rules.json",
            extra_args=["--confirm-empty"],
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-event-command-rules",
            file_name="event-command-rules.json",
            extra_args=["--confirm-empty"],
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-note-tag-rules",
            file_name="note-tag-rules.json",
            extra_args=["--confirm-empty"],
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-placeholder-rules",
            file_name="placeholder-rules.json",
            extra_args=["--confirm-empty"],
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-structured-placeholder-rules",
            file_name="structured-placeholder-rules.json",
            extra_args=["--confirm-empty"],
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-plugin-source-rules",
            file_name="plugin-source-rules.json",
            extra_args=["--confirm-empty"],
        )
        _import_workspace_file(
            capsys,
            workspace,
            command="import-nonstandard-data-rules",
            file_name="nonstandard-data-rules.json",
        )

        translate_report = _run_cli(
            ["translate", "--game", "テストゲーム"],
            capsys,
            expected_statuses={"ok"},
        )
        translate_summary = _summary(translate_report)
        assert isinstance(translate_summary.get("success_count"), int)
        assert cast(int, translate_summary["success_count"]) > 0
        assert translate_summary.get("quality_error_count") == 0

        _ = _run_cli(
            ["quality-report", "--game", "テストゲーム"],
            capsys,
            expected_statuses={"ok", "warning"},
        )
        write_back_report = _run_cli(
            ["write-back", "--game", "テストゲーム", "--confirm-font-overwrite"],
            capsys,
            expected_statuses={"ok"},
        )
        write_back_summary = _summary(write_back_report)
        assert isinstance(write_back_summary.get("data_item_count"), int)
        assert cast(int, write_back_summary["data_item_count"]) > 0

        _write_json(feedback_path, ["こんにちは"])
        feedback_report = _run_cli(
            ["verify-feedback-text", "--game", "テストゲーム", "--input", str(feedback_path)],
            capsys,
            expected_statuses={"ok"},
        )
        assert _summary(feedback_report).get("occurrence_count") == 0
    finally:
        fake_server.stop()


@pytest.mark.asyncio
async def test_stage0_stale_workspace_optional_files_not_in_manifest_are_ignored(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """第二次 prepare 后残留的旧重支线文件不能参与本轮工作区校验。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=Path("setting.example.toml"))
    workspace = tmp_path / "workspace"
    prepare_report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=workspace,
        command_codes=None,
    )
    assert prepare_report.status == "ok"
    _write_json(workspace / "plugin-source-rules.json", {"stale": ["not", "a", "rule"]})
    _write_json(workspace / "nonstandard-data-rules.json", {"stale": ["not", "a", "rule"]})
    _write_json(workspace / "nonstandard-data" / "OldPluginData.json", {"text": "旧工作区残留"})

    def forbidden_plugin_source_scan(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("旧 plugin-source-rules.json 不应触发插件源码扫描")

    async def forbidden_nonstandard_data_scan(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("旧 nonstandard-data-rules.json 不应触发非标准 data 扫描")

    monkeypatch.setattr(
        "app.agent_toolkit.services.workspace.build_plugin_source_scan",
        forbidden_plugin_source_scan,
        raising=False,
    )
    monkeypatch.setattr("app.agent_toolkit.services.workspace.build_nonstandard_data_scan", forbidden_nonstandard_data_scan)

    report = await service.validate_agent_workspace(game_title="テストゲーム", workspace=workspace)

    error_codes = {error.code for error in report.errors}
    assert "plugin_source_rules_missing" not in error_codes
    assert "plugin_source_rules_invalid" not in error_codes
    assert "nonstandard_data_rules_missing" not in error_codes
    assert "nonstandard_data_rules_invalid" not in error_codes
    assert "nonstandard_data_scan_failed" not in error_codes
