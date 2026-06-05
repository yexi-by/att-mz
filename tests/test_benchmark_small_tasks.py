"""小任务链路性能脚本测试。"""

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import cast

import pytest

import scripts.benchmark_small_tasks as small_tasks_benchmark
from scripts.benchmark_rebuild_active_runtime import PreparedBenchmark
from scripts.benchmark_small_tasks import (
    SmallTaskBenchmarkOptions,
    build_command_failures,
    build_command_warnings,
    build_threshold_failures,
    is_simple_benchmark_source,
    parse_args,
)


def test_parse_args_reads_small_task_thresholds(tmp_path: Path) -> None:
    """小任务性能脚本读取各命令阈值和运行规模。"""
    sample = tmp_path / "sample"
    db_path = tmp_path / "game.db"

    options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
        "--db",
        str(db_path),
        "--runs",
        "2",
        "--max-items",
        "3",
        "--manual-item-count",
        "100",
        "--rust-threads",
        "4",
        "--max-rebuild-ms",
        "30000",
        "--max-quality-report-ms",
        "10000",
        "--max-translate-ms",
        "5000",
        "--max-import-ms",
        "2000",
        "--max-reset-ms",
        "1000",
    ])

    assert options.sample_path == sample.resolve()
    assert options.game_title == "测试游戏"
    assert options.source_db_path == db_path.resolve()
    assert options.runs == 2
    assert options.max_items == 3
    assert options.manual_item_count == 100
    assert options.rust_threads == 4
    assert options.max_import_ms == 2000
    assert options.max_reset_ms == 1000
    assert options.use_fake_llm is True


def test_parse_args_requires_explicit_real_llm_opt_in(tmp_path: Path) -> None:
    """小任务性能脚本默认不用真实模型，显式开关才允许真实模型。"""
    sample = tmp_path / "sample"

    default_options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
    ])
    real_options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
        "--allow-real-llm",
    ])

    assert default_options.use_fake_llm is True
    assert real_options.use_fake_llm is False


def test_run_benchmark_records_all_small_task_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行结果包含小任务命令、耗时、索引状态和线程环境。"""
    prepared = PreparedBenchmark(
        temp_root=tmp_path / "bench",
        app_home=tmp_path / "bench" / "app-home",
        game_path=tmp_path / "bench" / "game",
        db_path=tmp_path / "bench" / "app-home" / "data" / "db" / "测试游戏.db",
    )
    (prepared.game_path / "data").mkdir(parents=True)
    (prepared.game_path / "js").mkdir()
    _ = (prepared.game_path / "data" / "System.json").write_text("{}", encoding="utf-8")
    _ = (prepared.game_path / "js" / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    prepared.db_path.parent.mkdir(parents=True)
    seed_text_index(prepared.db_path)
    options = SmallTaskBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "source.db",
        runs=1,
        keep_temp=False,
        max_items=3,
        manual_item_count=2,
        rust_threads=4,
        max_rebuild_ms=None,
        max_quality_report_ms=None,
        max_translate_ms=None,
        max_import_ms=None,
        max_reset_ms=None,
        use_fake_llm=True,
    )
    captured_commands: list[list[str]] = []
    captured_env: dict[str, str] = {}

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        text: bool,
        encoding: str,
        errors: str,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        """返回可解析的 CLI JSON 报告。"""
        _ = (cwd, text, encoding, errors, stdout, stderr, check)
        captured_commands.append(args)
        captured_env.update(env)
        task_status = "rebuilt" if "rebuild-text-index" in args else "used"
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "ok",
                    "summary": {
                        "index_status": task_status,
                        "text_index_status": task_status,
                        "stage_timings": {"total": 1},
                        "native_thread_count": 4,
                    },
                },
                ensure_ascii=False,
            ),
            stderr="",
        )

    monkeypatch.setattr("scripts.benchmark_small_tasks.subprocess.run", fake_run)

    result = small_tasks_benchmark.run_benchmark(options, prepared)

    assert captured_env["ATT_MZ_HOME"] == str(prepared.app_home)
    assert captured_env["ATT_MZ_LLM_BASE_URL"].startswith("http://127.0.0.1:")
    assert captured_env["ATT_MZ_LLM_BASE_URL"].endswith("/v1")
    assert captured_env["ATT_MZ_LLM_API_KEY"] == "att-mz-benchmark-fake-key"
    assert [task["task"] for task in cast(list[dict[str, object]], result["tasks"])] == list(
        small_tasks_benchmark.TASK_ORDER
    )
    assert any("import-manual-translations" in command for command in captured_commands)
    assert any("reset-translations" in command for command in captured_commands)
    assert result["status"] == "ok"
    assert result["llm_mode"] == "fake"
    assert result["command_failures"] == []
    assert result["command_warnings"] == []


def test_run_benchmark_records_json_command_failure_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """结构化质量失败应进入结果清单，但不能吞掉后续任务计时。"""
    prepared = PreparedBenchmark(
        temp_root=tmp_path / "bench",
        app_home=tmp_path / "bench" / "app-home",
        game_path=tmp_path / "bench" / "game",
        db_path=tmp_path / "bench" / "app-home" / "data" / "db" / "测试游戏.db",
    )
    (prepared.game_path / "data").mkdir(parents=True)
    (prepared.game_path / "js").mkdir()
    _ = (prepared.game_path / "data" / "System.json").write_text("{}", encoding="utf-8")
    _ = (prepared.game_path / "js" / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    prepared.db_path.parent.mkdir(parents=True)
    seed_text_index(prepared.db_path)
    options = SmallTaskBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "source.db",
        runs=1,
        keep_temp=False,
        max_items=3,
        manual_item_count=2,
        rust_threads=None,
        max_rebuild_ms=None,
        max_quality_report_ms=None,
        max_translate_ms=None,
        max_import_ms=None,
        max_reset_ms=None,
        use_fake_llm=True,
    )
    captured_commands: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        text: bool,
        encoding: str,
        errors: str,
        stdout: int,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        """普通质量报告返回结构化失败，其余命令正常。"""
        _ = (cwd, env, text, encoding, errors, stdout, stderr, check)
        captured_commands.append(args)
        is_quality_report = "quality-report" in args
        return subprocess.CompletedProcess(
            args=args,
            returncode=1 if is_quality_report else 0,
            stdout=json.dumps(
                {
                    "status": "error" if is_quality_report else "ok",
                    "summary": {
                        "index_status": "used",
                        "text_index_status": "used",
                        "stage_timings": {"total": 1},
                        "native_thread_count": 0,
                    },
                },
                ensure_ascii=False,
            ),
            stderr="质量报告发现问题" if is_quality_report else "",
        )

    monkeypatch.setattr("scripts.benchmark_small_tasks.subprocess.run", fake_run)

    result = small_tasks_benchmark.run_benchmark(options, prepared)
    tasks = cast(list[dict[str, object]], result["tasks"])

    assert [task["task"] for task in tasks] == list(small_tasks_benchmark.TASK_ORDER)
    assert result["status"] == "error"
    assert result["command_failures"] == [
        {
            "task": "quality_report",
            "return_code": 1,
            "report_status": "error",
            "run_index": 1,
        }
    ]
    assert any("import-manual-translations" in command for command in captured_commands)
    assert any("reset-translations" in command for command in captured_commands)


def test_threshold_failures_check_each_small_task() -> None:
    """小任务性能阈值按任务类型生成失败清单。"""
    options = SmallTaskBenchmarkOptions(
        sample_path=Path("sample"),
        game_title="测试游戏",
        source_db_path=Path("game.db"),
        runs=1,
        keep_temp=False,
        max_items=3,
        manual_item_count=100,
        rust_threads=None,
        max_rebuild_ms=10,
        max_quality_report_ms=10,
        max_translate_ms=10,
        max_import_ms=10,
        max_reset_ms=10,
        use_fake_llm=True,
    )
    tasks: list[dict[str, object]] = [
        {"task": "rebuild_text_index", "elapsed_ms": 11, "run_index": 1},
        {"task": "quality_report", "elapsed_ms": 9, "run_index": 1},
        {"task": "translate_max_items", "elapsed_ms": 12, "run_index": 1},
        {"task": "import_manual_translations", "elapsed_ms": 13, "run_index": 1},
        {"task": "reset_translations_input", "elapsed_ms": 14, "run_index": 1},
    ]

    assert build_threshold_failures(options=options, tasks=tasks) == [
        {"task": "rebuild_text_index", "actual": 11, "limit": 10, "run_index": 1},
        {"task": "translate_max_items", "actual": 12, "limit": 10, "run_index": 1},
        {"task": "import_manual_translations", "actual": 13, "limit": 10, "run_index": 1},
        {"task": "reset_translations_input", "actual": 14, "limit": 10, "run_index": 1},
    ]


def test_command_failures_check_return_code_and_report_status() -> None:
    """benchmark 汇总必须区分性能阈值失败和 CLI 结构化失败。"""
    tasks: list[dict[str, object]] = [
        {"task": "quality_report", "return_code": 0, "report_status": "ok", "run_index": 1},
        {"task": "reset_translations_input", "return_code": 0, "report_status": "warning", "run_index": 1},
        {"task": "translate_max_items", "return_code": 1, "report_status": "error", "run_index": 1},
        {"task": "import_manual_translations", "return_code": 0, "report_status": "error", "run_index": 1},
    ]

    assert build_command_failures(tasks=tasks) == [
        {
            "task": "translate_max_items",
            "return_code": 1,
            "report_status": "error",
            "run_index": 1,
        },
        {
            "task": "import_manual_translations",
            "return_code": 0,
            "report_status": "error",
            "run_index": 1,
        },
    ]
    assert build_command_warnings(tasks=tasks) == [
        {
            "task": "reset_translations_input",
            "return_code": 0,
            "report_status": "warning",
            "run_index": 1,
        }
    ]


def test_parse_args_rejects_non_positive_counts(tmp_path: Path) -> None:
    """运行次数和输入规模必须是正整数。"""
    sample = tmp_path / "sample"

    with pytest.raises(ValueError, match="--manual-item-count 必须是正整数"):
        _ = parse_args([
            "--sample",
            str(sample),
            "--game",
            "测试游戏",
            "--manual-item-count",
            "0",
        ])


def test_fake_llm_response_matches_prompt_ids_and_array_line_counts() -> None:
    """benchmark 假模型按 prompt id 和 line_count 生成 JSON 数组。"""
    user_prompt = """# 正文

## 1

id: 1
type: short_text
role:

タイトル

## 2

id: 2
type: array
role:
line_count: 3

[RMMZ_TEXT_COLOR_1]はい[CUSTOM_LABEL_1]
いいえ
戻る
"""

    response = small_tasks_benchmark.build_fake_translation_response_items(user_prompt)

    assert response == [
        {"id": "1", "translation_lines": ["测试译文"]},
        {
            "id": "2",
            "translation_lines": [
                "测试译文 [RMMZ_TEXT_COLOR_1] [CUSTOM_LABEL_1]",
                "测试译文",
                "测试译文",
            ],
        },
    ]


def test_manual_input_generation_skips_protocol_like_source_rows(tmp_path: Path) -> None:
    """手动导入 benchmark 只选择适合生成干净假译文的简单行。"""
    db_path = tmp_path / "game.db"
    seed_text_index(
        db_path,
        rows=[
            ("A", [r"\C[1]Hello"]),
            ("B", ["Simple title"]),
            ("C", ["Another line"]),
        ],
    )

    manual_input, reset_input = small_tasks_benchmark.write_manual_and_reset_inputs(
        db_path=db_path,
        output_dir=tmp_path / "inputs",
        item_count=2,
    )

    assert json.loads(manual_input.read_text(encoding="utf-8")) == {
        "B": {"translation_lines": ["测试译文"]},
        "C": {"translation_lines": ["测试译文"]},
    }
    assert json.loads(reset_input.read_text(encoding="utf-8")) == {"location_paths": ["B", "C"]}
    assert is_simple_benchmark_source([r"\C[1]Hello"]) is False


def seed_text_index(db_path: Path, rows: list[tuple[str, list[str]]] | None = None) -> None:
    """写入脚本生成手动输入所需的最小索引表。"""
    rows = rows or [
        ("A", ["原文一"]),
        ("B", ["原文二"]),
    ]
    connection = sqlite3.connect(db_path)
    try:
        _ = connection.execute(
            """
            CREATE TABLE text_index_items (
                location_path TEXT NOT NULL,
                original_lines TEXT NOT NULL,
                writable INTEGER NOT NULL
            )
            """
        )
        _ = connection.executemany(
            "INSERT INTO text_index_items (location_path, original_lines, writable) VALUES (?, ?, ?)",
            [
                (location_path, json.dumps(original_lines, ensure_ascii=False), 1)
                for location_path, original_lines in rows
            ],
        )
        connection.commit()
    finally:
        connection.close()
