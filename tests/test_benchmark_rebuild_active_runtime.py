"""重建运行文件性能脚本测试。"""

import json
from pathlib import Path
import sqlite3
import subprocess
from typing import cast

import pytest

import scripts.benchmark_rebuild_active_runtime as rebuild_benchmark
from scripts.benchmark_rebuild_active_runtime import (
    BenchmarkPreparationError,
    BenchmarkOptions,
    PreparedBenchmark,
    build_cli_env,
    prepare_app_home_assets,
    build_threshold_failures,
    collect_game_sample_stats,
    extract_last_json_object,
    parse_args,
    reset_active_data_from_origin,
    resolve_content_root,
    update_database_metadata,
)


def test_extract_last_json_object_reads_report_after_progress() -> None:
    """性能脚本能从进度输出后提取最终 JSON 报告。"""
    text = "\n".join(
        [
            "进度 重建运行文件 | [--------------------] | 0/1",
            '{"status":"debug"}',
            "进度 重建运行文件 | [####################] | 1/1",
            '{"status":"ok","summary":{"rust_plan_ms":12}}',
        ]
    )

    report = extract_last_json_object(text)

    assert report["status"] == "ok"
    assert report["summary"] == {"rust_plan_ms": 12}


def test_extract_last_json_object_rejects_missing_report() -> None:
    """stdout 没有 JSON 对象时直接报错。"""
    with pytest.raises(RuntimeError, match="没有找到 JSON"):
        _ = extract_last_json_object("进度 重建运行文件")


def test_resolve_content_root_supports_direct_and_www_layouts(tmp_path: Path) -> None:
    """性能脚本能识别直根目录和 MV www 目录。"""
    direct_game = tmp_path / "direct"
    direct_data = direct_game / "data"
    direct_js = direct_game / "js"
    direct_data.mkdir(parents=True)
    direct_js.mkdir()
    _ = (direct_js / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")

    mv_game = tmp_path / "mv"
    mv_data = mv_game / "www" / "data"
    mv_js = mv_game / "www" / "js"
    mv_data.mkdir(parents=True)
    mv_js.mkdir()
    _ = (mv_js / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")

    assert resolve_content_root(direct_game) == direct_game
    assert resolve_content_root(mv_game) == mv_game / "www"


def test_parse_args_requires_explicit_sample_and_game() -> None:
    """性能脚本不能带本机样本路径默认值。"""
    with pytest.raises(SystemExit):
        _ = parse_args([])


def test_parse_args_uses_explicit_sample_and_game(tmp_path: Path) -> None:
    """性能脚本参数全部来自显式输入。"""
    sample = tmp_path / "sample"
    db_path = tmp_path / "db" / "game.db"

    options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
        "--db",
        str(db_path),
        "--runs",
        "2",
        "--rust-threads",
        "4",
        "--reset-active-data-from-origin",
    ])

    assert options.sample_path == sample.resolve()
    assert options.game_title == "测试游戏"
    assert options.source_db_path == db_path.resolve()
    assert options.runs == 2
    assert options.rust_threads == 4
    assert options.reset_active_data_from_origin is True
    assert options.max_slowest_ms is None
    assert options.max_average_ms is None


def test_parse_args_reads_explicit_thresholds(tmp_path: Path) -> None:
    """性能脚本只在显式提供阈值时启用自动验收。"""
    sample = tmp_path / "sample"

    options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
        "--max-slowest-ms",
        "1000",
        "--max-average-ms",
        "900",
        "--max-rust-plan-ms",
        "800",
        "--max-file-replacement-ms",
        "700",
        "--max-post-write-audit-ms",
        "600",
    ])

    assert options.max_slowest_ms == 1000
    assert options.max_average_ms == 900
    assert options.max_rust_plan_ms == 800
    assert options.max_file_replacement_ms == 700
    assert options.max_post_write_audit_ms == 600


def test_parse_args_rejects_negative_threshold(tmp_path: Path) -> None:
    """性能阈值不能是负数。"""
    sample = tmp_path / "sample"

    with pytest.raises(ValueError, match="--max-slowest-ms 必须是非负整数"):
        _ = parse_args([
            "--sample",
            str(sample),
            "--game",
            "测试游戏",
            "--max-slowest-ms",
            "-1",
        ])


def test_parse_args_rejects_non_positive_rust_threads(tmp_path: Path) -> None:
    """Rust 线程数必须是正整数。"""
    sample = tmp_path / "sample"

    with pytest.raises(ValueError, match="--rust-threads 必须是正整数"):
        _ = parse_args([
            "--sample",
            str(sample),
            "--game",
            "测试游戏",
            "--rust-threads",
            "0",
        ])


def test_build_cli_env_sets_att_mz_home(tmp_path: Path) -> None:
    """性能命令环境只携带临时应用目录，Rust 线程数由 setting.toml 控制。"""
    env = build_cli_env(app_home=tmp_path / "app-home", rust_threads=4)

    assert env["ATT_MZ_HOME"] == str(tmp_path / "app-home")


def test_prepare_app_home_assets_writes_runtime_thread_setting(tmp_path: Path) -> None:
    """benchmark 显式线程数必须写入临时 setting.toml。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()

    prepare_app_home_assets(app_home, rust_threads=4)

    setting_text = (app_home / "setting.toml").read_text(encoding="utf-8")
    assert "[runtime]" in setting_text
    assert "rust_threads = 4" in setting_text


def test_collect_game_sample_stats_records_copied_sample_scale(tmp_path: Path) -> None:
    """性能结果记录临时副本的文件规模。"""
    game = tmp_path / "game"
    data_dir = game / "data"
    plugin_dir = game / "js" / "plugins"
    data_dir.mkdir(parents=True)
    plugin_dir.mkdir(parents=True)
    _ = (game / "js" / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    _ = (data_dir / "System.json").write_text("{}", encoding="utf-8")
    _ = (plugin_dir / "Foo.js").write_text("console.log('x');\n", encoding="utf-8")

    stats = collect_game_sample_stats(game)

    assert stats["file_count"] == 3
    assert stats["total_bytes"] > 0
    assert stats["data_json_file_count"] == 1
    assert stats["plugin_js_file_count"] == 1


def test_reset_active_data_from_origin_copies_origin_json(tmp_path: Path) -> None:
    """性能脚本能在临时副本中强制制造真实替换输入。"""
    game = tmp_path / "game"
    data_dir = game / "data"
    origin_dir = game / "data_origin"
    js_dir = game / "js"
    data_dir.mkdir(parents=True)
    origin_dir.mkdir()
    js_dir.mkdir()
    _ = (js_dir / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    _ = (data_dir / "System.json").write_text('{"gameTitle":"已汉化"}', encoding="utf-8")
    _ = (origin_dir / "System.json").write_text('{"gameTitle":"原文"}', encoding="utf-8")
    _ = (origin_dir / "Ignored.txt").write_text("不是 JSON", encoding="utf-8")

    reset_count = reset_active_data_from_origin(game)

    assert reset_count == 1
    assert (data_dir / "System.json").read_text(encoding="utf-8") == '{"gameTitle":"原文"}'


def test_reset_active_data_from_origin_requires_origin_dir(tmp_path: Path) -> None:
    """缺少 data_origin 时不能假装执行真实替换性能门禁。"""
    game = tmp_path / "game"
    data_dir = game / "data"
    js_dir = game / "js"
    data_dir.mkdir(parents=True)
    js_dir.mkdir()
    _ = (js_dir / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="缺少 data_origin"):
        _ = reset_active_data_from_origin(game)


def test_run_benchmark_records_rust_threads_and_passes_child_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实性能命令会记录命令、副本规模、退出码和显式 Rust 线程配置。"""
    prepared = PreparedBenchmark(
        temp_root=tmp_path / "bench",
        app_home=tmp_path / "bench" / "app-home",
        game_path=tmp_path / "bench" / "game",
        db_path=tmp_path / "bench" / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
        rust_threads=4,
        reset_active_data_from_origin=True,
    )
    data_dir = prepared.game_path / "data"
    origin_dir = prepared.game_path / "data_origin"
    plugin_dir = prepared.game_path / "js" / "plugins"
    data_dir.mkdir(parents=True)
    origin_dir.mkdir()
    plugin_dir.mkdir(parents=True)
    _ = (prepared.game_path / "js" / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    system_path = data_dir / "System.json"
    _ = system_path.write_text('{"gameTitle":"已汉化"}', encoding="utf-8")
    _ = (origin_dir / "System.json").write_text('{"gameTitle":"原文"}', encoding="utf-8")
    _ = (plugin_dir / "Foo.js").write_text("console.log('x');\n", encoding="utf-8")
    captured_env: dict[str, str] = {}
    active_data_seen_by_runs: list[str] = []

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
        """记录子进程环境并返回最小成功 JSON。"""
        _ = (args, cwd, text, encoding, errors, stdout, stderr, check)
        captured_env.update(env)
        active_data_seen_by_runs.append(system_path.read_text(encoding="utf-8"))
        _ = system_path.write_text('{"gameTitle":"命令写入后"}', encoding="utf-8")
        return subprocess.CompletedProcess(
            args="uv run python main.py",
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "ok",
                    "summary": {
                        "rust_plan_ms": 1,
                        "file_replacement_ms": 2,
                        "post_write_audit_ms": 3,
                        "planned_file_count": 4,
                        "skipped_file_count": 5,
                        "plugin_source_ast_source_scan_file_count": 9,
                        "plugin_source_ast_runtime_scan_file_count": 10,
                        "plugin_source_runtime_map_count": 11,
                        "data_item_count": 6,
                        "plugin_item_count": 7,
                        "terminology_written_count": 8,
                    },
                },
                ensure_ascii=False,
            ),
            stderr="",
        )

    monkeypatch.setattr("scripts.benchmark_rebuild_active_runtime.subprocess.run", fake_run)

    result = rebuild_benchmark.run_benchmark(options, prepared)

    assert captured_env["ATT_MZ_HOME"] == str(prepared.app_home)
    assert result["command"] == rebuild_benchmark.rebuild_active_runtime_command("测试游戏")
    assert result["sample_stats"] == collect_game_sample_stats(prepared.game_path)
    runs = cast(list[dict[str, object]], result["runs"])
    assert runs[0]["return_code"] == 0
    assert runs[0]["active_data_reset_from_origin_count"] == 1
    assert active_data_seen_by_runs == ['{"gameTitle":"原文"}']
    assert runs[0]["plugin_source_ast_source_scan_file_count"] == 9
    assert runs[0]["plugin_source_ast_runtime_scan_file_count"] == 10
    assert runs[0]["plugin_source_runtime_map_count"] == 11
    assert result["rust_threads"] == 4
    assert result["reset_active_data_from_origin"] is True
    assert result["active_data_reset_from_origin_count"] == 1
    assert result["status"] == "ok"


def test_threshold_failures_report_aggregate_and_run_metrics(tmp_path: Path) -> None:
    """性能脚本按显式阈值输出可验收的失败清单。"""
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=2,
        keep_temp=False,
        max_slowest_ms=100,
        max_average_ms=90,
        max_rust_plan_ms=50,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=30,
    )
    result: dict[str, object] = {
        "slowest_ms": 120,
        "average_ms": 80,
        "runs": [
            {
                "run_index": 1,
                "rust_plan_ms": 40,
                "post_write_audit_ms": 20,
            },
            {
                "run_index": 2,
                "rust_plan_ms": 55,
                "post_write_audit_ms": 35,
            },
        ],
    }

    assert build_threshold_failures(options=options, result=result) == [
        {
            "metric": "slowest_ms",
            "actual": 120,
            "limit": 100,
        },
        {
            "metric": "rust_plan_ms",
            "actual": 55,
            "limit": 50,
            "run_index": 2,
        },
        {
            "metric": "post_write_audit_ms",
            "actual": 35,
            "limit": 30,
            "run_index": 2,
        },
    ]


def test_threshold_failures_empty_without_thresholds(tmp_path: Path) -> None:
    """未配置阈值时性能脚本只记录数据，不自行失败。"""
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )
    result: dict[str, object] = {
        "slowest_ms": 9999,
        "average_ms": 9999,
        "runs": [
            {
                "run_index": 1,
                "rust_plan_ms": 9999,
            }
        ],
    }

    assert build_threshold_failures(options=options, result=result) == []


def test_main_returns_nonzero_when_threshold_fails_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """性能脚本阈值失败时返回非 0，并清理临时工作目录。"""
    temp_root = tmp_path / "bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=1,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(rebuild_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: BenchmarkOptions) -> PreparedBenchmark:
        """返回预置临时工作目录。"""
        return prepared

    monkeypatch.setattr(rebuild_benchmark, "prepare_benchmark", fake_prepare_benchmark)

    def fake_run_benchmark(
        _options: BenchmarkOptions,
        _prepared: PreparedBenchmark,
    ) -> dict[str, object]:
        """返回阈值失败结果。"""
        return {
            "status": "error",
            "threshold_failures": [{"metric": "slowest_ms", "actual": 2, "limit": 1}],
        }

    monkeypatch.setattr(
        rebuild_benchmark,
        "run_benchmark",
        fake_run_benchmark,
    )

    def fake_remove_tree(path: Path) -> str | None:
        """记录清理路径。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(rebuild_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert rebuild_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == [temp_root]
    assert output["status"] == "error"
    assert output["temp_preserved"] is False


def test_prepare_benchmark_cleans_temp_when_metadata_update_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """准备阶段已创建临时工作目录后失败时必须清理目录。"""
    sample = tmp_path / "sample"
    data_dir = sample / "data"
    js_dir = sample / "js"
    data_dir.mkdir(parents=True)
    js_dir.mkdir()
    _ = (js_dir / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    db_path = tmp_path / "game.db"
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute(
            "CREATE TABLE metadata (metadata_key TEXT PRIMARY KEY, game_title TEXT, game_path TEXT, content_root TEXT)"
        )
        _ = connection.execute(
            "INSERT INTO metadata (metadata_key, game_title, game_path, content_root) VALUES ('current_game', '其它游戏', '旧', '旧')"
        )
        connection.commit()
    temp_root = tmp_path / "bench-temp"

    def fake_mkdtemp(*, prefix: str) -> str:
        """返回可断言的临时工作目录路径。"""
        assert prefix == "att_mz_rebuild_benchmark_"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr("scripts.benchmark_rebuild_active_runtime.tempfile.mkdtemp", fake_mkdtemp)
    options = BenchmarkOptions(
        sample_path=sample,
        game_title="测试游戏",
        source_db_path=db_path,
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )

    with pytest.raises(BenchmarkPreparationError) as error_info:
        _ = rebuild_benchmark.prepare_benchmark(options)

    assert not temp_root.exists()
    assert error_info.value.temp_preserved is False
    assert error_info.value.cleanup_error is None
    assert "数据库 metadata 没有唯一命中当前游戏" in str(error_info.value)


def test_main_reports_unprepared_error_when_prepare_fails_before_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """临时工作目录创建前准备失败时也输出结构化 JSON。"""
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "missing.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )

    monkeypatch.setattr(rebuild_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: BenchmarkOptions) -> PreparedBenchmark:
        """模拟还没创建临时工作目录就失败。"""
        raise FileNotFoundError("源数据库不存在")

    monkeypatch.setattr(rebuild_benchmark, "prepare_benchmark", fake_prepare_benchmark)

    assert rebuild_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert output["status"] == "error"
    assert output["temp_game_path"] is None
    assert output["temp_db_path"] is None
    assert output["temp_preserved"] is False
    assert output["error"] == "FileNotFoundError: 源数据库不存在"


def test_main_reports_preparation_error_without_second_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """准备阶段错误已经处理清理时入口不重复删除。"""
    temp_root = tmp_path / "bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(rebuild_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: BenchmarkOptions) -> PreparedBenchmark:
        """模拟准备阶段已清理后抛出的错误。"""
        raise BenchmarkPreparationError(
            "重建运行文件性能测试准备失败: RuntimeError: metadata 坏了",
            prepared=prepared,
            temp_preserved=False,
            cleanup_error=None,
        )

    def fake_remove_tree(path: Path) -> str | None:
        """记录不应发生的二次清理。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(rebuild_benchmark, "prepare_benchmark", fake_prepare_benchmark)
    monkeypatch.setattr(rebuild_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert rebuild_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == []
    assert output["status"] == "error"
    assert output["temp_game_path"] == str(prepared.game_path)
    assert output["temp_preserved"] is False


def test_main_reports_cleanup_error_without_failing_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """临时工作目录删除失败时报告清理错误，但不改变性能阈值结果。"""
    temp_root = tmp_path / "bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )

    monkeypatch.setattr(rebuild_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: BenchmarkOptions) -> PreparedBenchmark:
        """返回预置临时工作目录。"""
        return prepared

    monkeypatch.setattr(rebuild_benchmark, "prepare_benchmark", fake_prepare_benchmark)

    def fake_run_benchmark(
        _options: BenchmarkOptions,
        _prepared: PreparedBenchmark,
    ) -> dict[str, object]:
        """返回阈值通过结果。"""
        return {"status": "ok", "threshold_failures": []}

    monkeypatch.setattr(
        rebuild_benchmark,
        "run_benchmark",
        fake_run_benchmark,
    )

    def fake_remove_tree(_path: Path) -> str | None:
        """模拟清理失败。"""
        return "文件被占用"

    monkeypatch.setattr(rebuild_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert rebuild_benchmark.main() == 0
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert output["status"] == "ok"
    assert output["temp_preserved"] is True
    assert output["cleanup_error"] == "文件被占用"


def test_main_cleans_temp_and_reports_json_when_run_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """运行阶段异常时仍清理临时工作目录并输出结构化错误。"""
    temp_root = tmp_path / "bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = BenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(rebuild_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: BenchmarkOptions) -> PreparedBenchmark:
        """返回预置临时工作目录。"""
        return prepared

    def fake_run_benchmark(_options: BenchmarkOptions, _prepared: PreparedBenchmark) -> dict[str, object]:
        """模拟运行阶段异常。"""
        raise RuntimeError("stdout 中没有找到 JSON 对象")

    def fake_remove_tree(path: Path) -> str | None:
        """记录清理路径。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(rebuild_benchmark, "prepare_benchmark", fake_prepare_benchmark)
    monkeypatch.setattr(rebuild_benchmark, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(rebuild_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert rebuild_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == [temp_root]
    assert output["status"] == "error"
    assert output["temp_preserved"] is False
    assert output["error"] == "RuntimeError: stdout 中没有找到 JSON 对象"


def test_update_database_metadata_rebinds_temp_sample(tmp_path: Path) -> None:
    """性能脚本会把复制后的数据库绑定到临时样本。"""
    db_path = tmp_path / "game.db"
    game_path = tmp_path / "sample"
    content_root = game_path / "www"
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute(
            "CREATE TABLE metadata (metadata_key TEXT PRIMARY KEY, game_title TEXT, game_path TEXT, content_root TEXT)"
        )
        _ = connection.execute(
            "INSERT INTO metadata (metadata_key, game_title, game_path, content_root) VALUES ('current_game', '测试', '旧', '旧')"
        )
        connection.commit()

    update_database_metadata(
        db_path=db_path,
        game_title="测试",
        game_path=game_path,
        content_root=content_root,
    )

    with sqlite3.connect(db_path) as connection:
        row = cast(tuple[str, str] | None, connection.execute(
            "SELECT game_path, content_root FROM metadata WHERE metadata_key = 'current_game'"
        ).fetchone())

    assert row == (str(game_path), str(content_root))
