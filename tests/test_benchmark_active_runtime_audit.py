"""当前运行审计性能脚本测试。"""

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

import scripts.benchmark_active_runtime_audit as active_runtime_benchmark
from scripts.benchmark_rebuild_active_runtime import (
    BenchmarkPreparationError,
    PreparedBenchmark,
    collect_game_sample_stats,
)
from scripts.benchmark_active_runtime_audit import (
    ActiveRuntimeAuditBenchmarkOptions,
    build_error_result,
    build_run_result,
    build_threshold_failures,
    parse_args,
    rebuild_options_for_prepare,
)


def test_parse_args_reads_cache_thresholds(tmp_path: Path) -> None:
    """当前运行审计性能脚本读取显式缓存阈值。"""
    sample = tmp_path / "sample"

    options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
        "--runs",
        "2",
        "--max-slowest-ms",
        "1000",
        "--max-average-ms",
        "900",
        "--max-warm-rescan-file-count",
        "0",
        "--min-warm-cache-hit-file-count",
        "10",
        "--rust-threads",
        "4",
    ])

    assert options.sample_path == sample.resolve()
    assert options.game_title == "测试游戏"
    assert options.runs == 2
    assert options.max_slowest_ms == 1000
    assert options.max_average_ms == 900
    assert options.max_warm_rescan_file_count == 0
    assert options.min_warm_cache_hit_file_count == 10
    assert options.rust_threads == 4
    assert options.register_sample is False
    assert options.source_language == "ja"


def test_parse_args_reads_register_sample_mode(tmp_path: Path) -> None:
    """当前运行审计性能脚本支持在临时工作目录注册样本副本。"""
    sample = tmp_path / "sample"

    options = parse_args([
        "--sample",
        str(sample),
        "--game",
        "测试游戏",
        "--register-sample",
        "--source-language",
        "en",
    ])

    assert options.register_sample is True
    assert options.source_language == "en"


def test_parse_args_rejects_warm_threshold_without_warm_run(tmp_path: Path) -> None:
    """缓存预热阈值至少需要两轮审计。"""
    sample = tmp_path / "sample"

    with pytest.raises(ValueError, match="缓存预热阈值需要 --runs 至少为 2"):
        _ = parse_args([
            "--sample",
            str(sample),
            "--game",
            "测试游戏",
            "--runs",
            "1",
            "--max-warm-rescan-file-count",
            "0",
        ])


def test_parse_args_rejects_negative_cache_threshold(tmp_path: Path) -> None:
    """缓存阈值不能是负数。"""
    sample = tmp_path / "sample"

    with pytest.raises(ValueError, match="--min-warm-cache-hit-file-count 必须是非负整数"):
        _ = parse_args([
            "--sample",
            str(sample),
            "--game",
            "测试游戏",
            "--runs",
            "2",
            "--min-warm-cache-hit-file-count",
            "-1",
        ])


def test_parse_args_rejects_non_positive_rust_threads(tmp_path: Path) -> None:
    """当前运行审计性能脚本拒绝非正 Rust 线程数。"""
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


def test_build_run_result_extracts_cache_summary_even_when_audit_reports_error() -> None:
    """审计业务 error 仍可用于记录缓存性能指标。"""
    result = build_run_result(
        index=2,
        elapsed_ms=123,
        return_code=1,
        report={"status": "error"},
        summary={
            "active_runtime_scanned_file_count": 12,
            "active_runtime_issue_count": 3,
            "active_runtime_scan_cache_current_file_count": 12,
            "active_runtime_scan_cache_hit_file_count": 12,
            "active_runtime_scan_cache_miss_file_count": 0,
            "active_runtime_scan_cache_stale_file_count": 0,
            "active_runtime_scan_cache_rescan_file_count": 0,
        },
    )

    assert result == {
        "run_index": 2,
        "elapsed_ms": 123,
        "return_code": 1,
        "report_status": "error",
        "active_runtime_scanned_file_count": 12,
        "active_runtime_issue_count": 3,
        "active_runtime_scan_cache_current_file_count": 12,
        "active_runtime_scan_cache_hit_file_count": 12,
        "active_runtime_scan_cache_miss_file_count": 0,
        "active_runtime_scan_cache_stale_file_count": 0,
        "active_runtime_scan_cache_rescan_file_count": 0,
    }


def test_run_benchmark_records_command_sample_stats_and_return_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行审计性能结果记录命令、副本规模和每轮退出码。"""
    prepared = PreparedBenchmark(
        temp_root=tmp_path / "bench",
        app_home=tmp_path / "bench" / "app-home",
        game_path=tmp_path / "bench" / "game",
        db_path=tmp_path / "bench" / "app-home" / "data" / "db" / "测试游戏.db",
    )
    data_dir = prepared.game_path / "data"
    plugin_dir = prepared.game_path / "js" / "plugins"
    data_dir.mkdir(parents=True)
    plugin_dir.mkdir(parents=True)
    _ = (prepared.game_path / "js" / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    _ = (data_dir / "System.json").write_text("{}", encoding="utf-8")
    _ = (plugin_dir / "Foo.js").write_text("console.log('x');\n", encoding="utf-8")
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=None,
        min_warm_cache_hit_file_count=None,
        register_sample=False,
        source_language="ja",
        rust_threads=4,
    )
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
        """返回带业务错误状态的审计 JSON，验证脚本仍记录性能指标。"""
        _ = (args, cwd, text, encoding, errors, stdout, stderr, check)
        captured_env.update(env)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=json.dumps(
                {
                    "status": "error",
                    "summary": {
                        "active_runtime_scanned_file_count": 2,
                        "active_runtime_issue_count": 1,
                        "active_runtime_scan_cache_current_file_count": 2,
                        "active_runtime_scan_cache_hit_file_count": 0,
                        "active_runtime_scan_cache_miss_file_count": 2,
                        "active_runtime_scan_cache_stale_file_count": 0,
                        "active_runtime_scan_cache_rescan_file_count": 2,
                    },
                },
                ensure_ascii=False,
            ),
            stderr="",
        )

    monkeypatch.setattr("scripts.benchmark_active_runtime_audit.subprocess.run", fake_run)

    result = active_runtime_benchmark.run_benchmark(options, prepared)

    assert captured_env["ATT_MZ_HOME"] == str(prepared.app_home)
    assert captured_env["ATT_MZ_RUST_THREADS"] == "4"
    assert result["command"] == active_runtime_benchmark.audit_active_runtime_command("测试游戏")
    assert result["sample_stats"] == collect_game_sample_stats(prepared.game_path)
    runs = cast(list[dict[str, object]], result["runs"])
    assert runs[0]["return_code"] == 1
    assert result["status"] == "ok"


def test_threshold_failures_check_warm_cache_metrics(tmp_path: Path) -> None:
    """当前运行审计性能脚本按预热后的缓存指标生成失败清单。"""
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=3,
        keep_temp=False,
        max_slowest_ms=100,
        max_average_ms=None,
        max_warm_rescan_file_count=0,
        min_warm_cache_hit_file_count=10,
        register_sample=False,
        source_language="ja",
    )
    result: dict[str, object] = {
        "slowest_ms": 120,
        "average_ms": 80,
        "runs": [
            {
                "run_index": 1,
                "active_runtime_scan_cache_hit_file_count": 0,
                "active_runtime_scan_cache_rescan_file_count": 12,
            },
            {
                "run_index": 2,
                "active_runtime_scan_cache_hit_file_count": 12,
                "active_runtime_scan_cache_rescan_file_count": 0,
            },
            {
                "run_index": 3,
                "active_runtime_scan_cache_hit_file_count": 8,
                "active_runtime_scan_cache_rescan_file_count": 1,
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
            "metric": "active_runtime_scan_cache_rescan_file_count",
            "actual": 1,
            "limit": 0,
            "run_index": 3,
        },
        {
            "metric": "active_runtime_scan_cache_hit_file_count",
            "actual": 8,
            "limit": 10,
            "run_index": 3,
        },
    ]


def test_rebuild_options_for_prepare_reuses_safe_sample_copy_inputs(tmp_path: Path) -> None:
    """当前运行审计脚本复用副本样本和临时应用目录准备逻辑。"""
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=2,
        keep_temp=True,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=None,
        min_warm_cache_hit_file_count=None,
        register_sample=False,
        source_language="ja",
        rust_threads=4,
    )

    prepare_options = rebuild_options_for_prepare(options)

    assert prepare_options.sample_path == options.sample_path
    assert prepare_options.game_title == options.game_title
    assert prepare_options.source_db_path == options.source_db_path
    assert prepare_options.keep_temp is True
    assert prepare_options.rust_threads == 4


def test_error_result_marks_registered_sample_without_source_db_path(tmp_path: Path) -> None:
    """重新注册样本模式不报告未使用的源数据库路径。"""
    prepared = PreparedBenchmark(
        temp_root=tmp_path / "bench",
        app_home=tmp_path / "bench" / "app-home",
        game_path=tmp_path / "bench" / "game",
        db_path=tmp_path / "bench" / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "unused.db",
        runs=2,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=0,
        min_warm_cache_hit_file_count=None,
        register_sample=True,
        source_language="ja",
    )

    result = build_error_result(options=options, prepared=prepared, error=RuntimeError("boom"))

    assert result["registered_sample"] is True
    assert result["source_db_path"] is None


def test_prepare_registered_benchmark_cleans_temp_when_add_game_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重新注册样本准备失败时清理临时工作目录。"""
    sample = tmp_path / "sample"
    data_dir = sample / "data"
    js_dir = sample / "js"
    data_dir.mkdir(parents=True)
    js_dir.mkdir()
    _ = (js_dir / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    temp_root = tmp_path / "audit-temp"

    def fake_mkdtemp(*, prefix: str) -> str:
        """返回可断言的临时工作目录路径。"""
        assert prefix == "att_mz_rebuild_benchmark_"
        temp_root.mkdir()
        return str(temp_root)

    def fake_subprocess_run(
        _args: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """模拟 add-game 失败。"""
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout='{"status":"error"}',
            stderr="样本不是干净目录",
        )

    monkeypatch.setattr("scripts.benchmark_active_runtime_audit.tempfile.mkdtemp", fake_mkdtemp)
    monkeypatch.setattr("scripts.benchmark_active_runtime_audit.subprocess.run", fake_subprocess_run)
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=sample,
        game_title="测试游戏",
        source_db_path=tmp_path / "unused.db",
        runs=2,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=0,
        min_warm_cache_hit_file_count=None,
        register_sample=True,
        source_language="ja",
    )

    with pytest.raises(BenchmarkPreparationError) as error_info:
        _ = active_runtime_benchmark.prepare_registered_benchmark(options)

    assert not temp_root.exists()
    assert error_info.value.temp_preserved is False
    assert "临时样本 add-game 失败" in str(error_info.value)


def test_main_reports_preparation_error_without_second_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """当前运行审计准备阶段错误已经处理清理时入口不重复删除。"""
    temp_root = tmp_path / "audit-bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=2,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=0,
        min_warm_cache_hit_file_count=None,
        register_sample=True,
        source_language="ja",
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(active_runtime_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: ActiveRuntimeAuditBenchmarkOptions) -> PreparedBenchmark:
        """模拟准备阶段已清理后抛出的错误。"""
        raise BenchmarkPreparationError(
            "当前运行审计性能测试准备失败: RuntimeError: add-game 失败",
            prepared=prepared,
            temp_preserved=False,
            cleanup_error=None,
        )

    def fake_remove_tree(path: Path) -> str | None:
        """记录不应发生的二次清理。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(active_runtime_benchmark, "prepare_active_runtime_benchmark", fake_prepare_benchmark)
    monkeypatch.setattr(active_runtime_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert active_runtime_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == []
    assert output["status"] == "error"
    assert output["registered_sample"] is True
    assert output["source_db_path"] is None
    assert output["temp_preserved"] is False


def test_main_returns_nonzero_on_cache_threshold_failure_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """当前运行审计缓存阈值失败时返回非 0，并清理临时工作目录。"""
    temp_root = tmp_path / "audit-bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=2,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=0,
        min_warm_cache_hit_file_count=None,
        register_sample=False,
        source_language="ja",
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(active_runtime_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: ActiveRuntimeAuditBenchmarkOptions) -> PreparedBenchmark:
        """返回预置临时工作目录。"""
        return prepared

    monkeypatch.setattr(
        active_runtime_benchmark,
        "prepare_active_runtime_benchmark",
        fake_prepare_benchmark,
    )

    def fake_run_benchmark(
        _options: ActiveRuntimeAuditBenchmarkOptions,
        _prepared: PreparedBenchmark,
    ) -> dict[str, object]:
        """返回缓存阈值失败结果。"""
        return {
            "status": "error",
            "threshold_failures": [
                {
                    "metric": "active_runtime_scan_cache_rescan_file_count",
                    "actual": 1,
                    "limit": 0,
                    "run_index": 2,
                }
            ],
        }

    monkeypatch.setattr(
        active_runtime_benchmark,
        "run_benchmark",
        fake_run_benchmark,
    )

    def fake_remove_tree(path: Path) -> str | None:
        """记录清理路径。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(active_runtime_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert active_runtime_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == [temp_root]
    assert output["status"] == "error"
    assert output["temp_preserved"] is False


def test_main_keep_temp_skips_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """当前运行审计性能脚本保留临时工作目录时不执行删除。"""
    temp_root = tmp_path / "audit-bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=1,
        keep_temp=True,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=None,
        min_warm_cache_hit_file_count=None,
        register_sample=False,
        source_language="ja",
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(active_runtime_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: ActiveRuntimeAuditBenchmarkOptions) -> PreparedBenchmark:
        """返回预置临时工作目录。"""
        return prepared

    monkeypatch.setattr(
        active_runtime_benchmark,
        "prepare_active_runtime_benchmark",
        fake_prepare_benchmark,
    )

    def fake_run_benchmark(
        _options: ActiveRuntimeAuditBenchmarkOptions,
        _prepared: PreparedBenchmark,
    ) -> dict[str, object]:
        """返回缓存阈值通过结果。"""
        return {"status": "ok", "threshold_failures": []}

    monkeypatch.setattr(
        active_runtime_benchmark,
        "run_benchmark",
        fake_run_benchmark,
    )

    def fake_remove_tree(path: Path) -> str | None:
        """记录意外清理路径。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(
        active_runtime_benchmark,
        "remove_tree_with_retries",
        fake_remove_tree,
    )

    assert active_runtime_benchmark.main() == 0
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == []
    assert output["status"] == "ok"
    assert output["temp_preserved"] is True


def test_main_cleans_temp_and_reports_json_when_run_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """当前运行审计脚本运行阶段异常时仍清理临时工作目录。"""
    temp_root = tmp_path / "audit-bench"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=temp_root / "app-home",
        game_path=temp_root / "game",
        db_path=temp_root / "app-home" / "data" / "db" / "测试游戏.db",
    )
    options = ActiveRuntimeAuditBenchmarkOptions(
        sample_path=tmp_path / "sample",
        game_title="测试游戏",
        source_db_path=tmp_path / "game.db",
        runs=2,
        keep_temp=False,
        max_slowest_ms=None,
        max_average_ms=None,
        max_warm_rescan_file_count=0,
        min_warm_cache_hit_file_count=None,
        register_sample=False,
        source_language="ja",
    )
    removed_paths: list[Path] = []

    monkeypatch.setattr(active_runtime_benchmark, "parse_args", lambda: options)

    def fake_prepare_benchmark(_options: ActiveRuntimeAuditBenchmarkOptions) -> PreparedBenchmark:
        """返回预置临时工作目录。"""
        return prepared

    def fake_run_benchmark(
        _options: ActiveRuntimeAuditBenchmarkOptions,
        _prepared: PreparedBenchmark,
    ) -> dict[str, object]:
        """模拟运行阶段异常。"""
        raise TypeError("active_runtime_scanned_file_count 必须是整数")

    def fake_remove_tree(path: Path) -> str | None:
        """记录清理路径。"""
        removed_paths.append(path)
        return None

    monkeypatch.setattr(active_runtime_benchmark, "prepare_active_runtime_benchmark", fake_prepare_benchmark)
    monkeypatch.setattr(active_runtime_benchmark, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(active_runtime_benchmark, "remove_tree_with_retries", fake_remove_tree)

    assert active_runtime_benchmark.main() == 1
    output = cast(dict[str, object], json.loads(capsys.readouterr().out))

    assert removed_paths == [temp_root]
    assert output["status"] == "error"
    assert output["temp_preserved"] is False
    assert output["error"] == "TypeError: active_runtime_scanned_file_count 必须是整数"
