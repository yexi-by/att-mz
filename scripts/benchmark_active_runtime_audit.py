"""复制样本并计时 `audit-active-runtime` 缓存热路径。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.benchmark_rebuild_active_runtime import (
    BenchmarkPreparationError,
    BenchmarkOptions as RebuildBenchmarkOptions,
    PreparedBenchmark,
    build_preparation_error,
    collect_game_sample_stats,
    ensure_directory,
    ensure_int,
    ensure_object,
    ensure_run_results,
    extract_last_json_object,
    build_cli_env,
    prepare_app_home_assets,
    prepare_benchmark,
    optional_positive_int,
    remove_tree_with_retries,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class ActiveRuntimeAuditBenchmarkOptions:
    """当前运行审计性能测试参数。"""

    sample_path: Path
    game_title: str
    source_db_path: Path
    runs: int
    keep_temp: bool
    max_slowest_ms: int | None
    max_average_ms: int | None
    max_warm_rescan_file_count: int | None
    min_warm_cache_hit_file_count: int | None
    register_sample: bool
    source_language: str
    rust_threads: int | None = None


def parse_args(argv: Sequence[str] | None = None) -> ActiveRuntimeAuditBenchmarkOptions:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="计时 audit-active-runtime 缓存热路径")
    _ = parser.add_argument(
        "--sample",
        required=True,
        help="性能样本游戏目录；脚本会复制到临时工作目录后运行",
    )
    _ = parser.add_argument(
        "--game",
        required=True,
        help="数据库和 CLI 使用的游戏标题",
    )
    _ = parser.add_argument(
        "--db",
        default=None,
        help="源数据库路径；默认使用 data/db/<游戏标题>.db；传入 --register-sample 时不会读取该数据库",
    )
    _ = parser.add_argument(
        "--register-sample",
        action="store_true",
        help="在临时 ATT_MZ_HOME 中重新注册样本副本，不复制现有数据库",
    )
    _ = parser.add_argument("--source-language", default="ja", help="--register-sample 使用的源语言，默认 ja")
    _ = parser.add_argument("--runs", type=int, default=3, help="重复运行次数，默认 3")
    _ = parser.add_argument("--keep-temp", action="store_true", help="保留临时样本和临时 ATT_MZ_HOME")
    _ = parser.add_argument("--max-slowest-ms", type=int, default=None, help="允许的最慢单次总耗时上限")
    _ = parser.add_argument("--max-average-ms", type=int, default=None, help="允许的平均总耗时上限")
    _ = parser.add_argument(
        "--max-warm-rescan-file-count",
        type=int,
        default=None,
        help="缓存预热后允许重新扫描的插件源码文件数上限",
    )
    _ = parser.add_argument(
        "--min-warm-cache-hit-file-count",
        type=int,
        default=None,
        help="缓存预热后要求命中的插件源码文件数下限",
    )
    _ = parser.add_argument("--rust-threads", type=int, default=None, help="本次性能命令使用的 Rust Rayon 线程数")
    namespace = parser.parse_args(argv)
    game_title = cast(str, namespace.game)
    db_arg = cast(str | None, namespace.db)
    source_db_path = Path(db_arg).expanduser().resolve() if db_arg else ROOT / "data" / "db" / f"{game_title}.db"
    runs = cast(int, namespace.runs)
    if runs <= 0:
        raise ValueError("--runs 必须是正整数")
    max_warm_rescan_file_count = optional_non_negative_int(
        cast(int | None, namespace.max_warm_rescan_file_count),
        "--max-warm-rescan-file-count",
    )
    min_warm_cache_hit_file_count = optional_non_negative_int(
        cast(int | None, namespace.min_warm_cache_hit_file_count),
        "--min-warm-cache-hit-file-count",
    )
    if runs < 2 and (max_warm_rescan_file_count is not None or min_warm_cache_hit_file_count is not None):
        raise ValueError("缓存预热阈值需要 --runs 至少为 2")
    return ActiveRuntimeAuditBenchmarkOptions(
        sample_path=Path(cast(str, namespace.sample)).expanduser().resolve(),
        game_title=game_title,
        source_db_path=source_db_path,
        runs=runs,
        keep_temp=cast(bool, namespace.keep_temp),
        max_slowest_ms=optional_non_negative_int(cast(int | None, namespace.max_slowest_ms), "--max-slowest-ms"),
        max_average_ms=optional_non_negative_int(cast(int | None, namespace.max_average_ms), "--max-average-ms"),
        max_warm_rescan_file_count=max_warm_rescan_file_count,
        min_warm_cache_hit_file_count=min_warm_cache_hit_file_count,
        register_sample=cast(bool, namespace.register_sample),
        source_language=cast(str, namespace.source_language),
        rust_threads=optional_positive_int(cast(int | None, namespace.rust_threads), "--rust-threads"),
    )


def run_benchmark(options: ActiveRuntimeAuditBenchmarkOptions, prepared: PreparedBenchmark) -> dict[str, object]:
    """运行当前运行审计性能测试并返回 JSON 可序列化结果。"""
    runs: list[dict[str, object]] = []
    command = audit_active_runtime_command(options.game_title)
    for index in range(1, options.runs + 1):
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=build_cli_env(app_home=prepared.app_home, rust_threads=options.rust_threads),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            report = extract_last_json_object(completed.stdout)
        except RuntimeError as error:
            raise RuntimeError(
                f"当前运行审计第 {index} 次运行没有输出可解析 JSON，退出码 {completed.returncode}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ) from error
        summary = ensure_object(report.get("summary"), "summary")
        try:
            run_result = build_run_result(
                index=index,
                elapsed_ms=elapsed_ms,
                return_code=completed.returncode,
                report=report,
                summary=summary,
            )
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"当前运行审计第 {index} 次运行缺少缓存性能指标: {error}\n"
                f"report:\n{json.dumps(report, ensure_ascii=False, indent=2)}\n"
                f"stderr:\n{completed.stderr}"
            ) from error
        runs.append(run_result)
    elapsed_values = [ensure_int(run["elapsed_ms"], "elapsed_ms") for run in runs]
    result: dict[str, object] = {
        "status": "ok",
        "game": options.game_title,
        "command": command,
        "sample_path": str(options.sample_path),
        "sample_stats": collect_game_sample_stats(prepared.game_path),
        "temp_game_path": str(prepared.game_path),
        "temp_app_home": str(prepared.app_home),
        "registered_sample": options.register_sample,
        "source_db_path": result_source_db_path(options),
        "temp_db_path": str(prepared.db_path),
        "rust_threads": options.rust_threads,
        "run_count": len(runs),
        "slowest_ms": max(elapsed_values),
        "fastest_ms": min(elapsed_values),
        "average_ms": sum(elapsed_values) // len(elapsed_values),
        "runs": runs,
    }
    threshold_failures = build_threshold_failures(options=options, result=result)
    result["threshold_failures"] = threshold_failures
    if threshold_failures:
        result["status"] = "error"
    return result


def audit_active_runtime_command(game_title: str) -> list[str]:
    """返回本脚本计时的当前运行审计命令。"""
    return [
        "uv",
        "run",
        "python",
        "main.py",
        "audit-active-runtime",
        "--game",
        game_title,
    ]


def result_source_db_path(options: ActiveRuntimeAuditBenchmarkOptions) -> str | None:
    """返回结果中真实使用的源数据库路径。"""
    if options.register_sample:
        return None
    return str(options.source_db_path)


def build_run_result(
    *,
    index: int,
    elapsed_ms: int,
    return_code: int,
    report: dict[str, object],
    summary: dict[str, object],
) -> dict[str, object]:
    """从当前运行审计 JSON 摘要提取缓存性能指标。"""
    report_status = report.get("status")
    if not isinstance(report_status, str):
        raise TypeError("status 必须是字符串")
    return {
        "run_index": index,
        "elapsed_ms": elapsed_ms,
        "return_code": return_code,
        "report_status": report_status,
        "active_runtime_scanned_file_count": ensure_int(
            summary.get("active_runtime_scanned_file_count"),
            "active_runtime_scanned_file_count",
        ),
        "active_runtime_issue_count": ensure_int(
            summary.get("active_runtime_issue_count"),
            "active_runtime_issue_count",
        ),
        "active_runtime_scan_cache_current_file_count": ensure_int(
            summary.get("active_runtime_scan_cache_current_file_count"),
            "active_runtime_scan_cache_current_file_count",
        ),
        "active_runtime_scan_cache_hit_file_count": ensure_int(
            summary.get("active_runtime_scan_cache_hit_file_count"),
            "active_runtime_scan_cache_hit_file_count",
        ),
        "active_runtime_scan_cache_miss_file_count": ensure_int(
            summary.get("active_runtime_scan_cache_miss_file_count"),
            "active_runtime_scan_cache_miss_file_count",
        ),
        "active_runtime_scan_cache_stale_file_count": ensure_int(
            summary.get("active_runtime_scan_cache_stale_file_count"),
            "active_runtime_scan_cache_stale_file_count",
        ),
        "active_runtime_scan_cache_rescan_file_count": ensure_int(
            summary.get("active_runtime_scan_cache_rescan_file_count"),
            "active_runtime_scan_cache_rescan_file_count",
        ),
    }


def build_threshold_failures(
    *,
    options: ActiveRuntimeAuditBenchmarkOptions,
    result: dict[str, object],
) -> list[dict[str, object]]:
    """按显式阈值生成当前运行审计性能失败清单。"""
    failures: list[dict[str, object]] = []
    runs = ensure_run_results(result.get("runs"), "runs")
    _check_max_threshold(
        failures=failures,
        metric="slowest_ms",
        actual=ensure_int(result.get("slowest_ms"), "slowest_ms"),
        limit=options.max_slowest_ms,
    )
    _check_max_threshold(
        failures=failures,
        metric="average_ms",
        actual=ensure_int(result.get("average_ms"), "average_ms"),
        limit=options.max_average_ms,
    )
    warm_runs = [
        run
        for run in runs
        if ensure_int(run.get("run_index"), "run_index") > 1
    ]
    _check_warm_max_threshold(
        failures=failures,
        runs=warm_runs,
        metric="active_runtime_scan_cache_rescan_file_count",
        limit=options.max_warm_rescan_file_count,
    )
    _check_warm_min_threshold(
        failures=failures,
        runs=warm_runs,
        metric="active_runtime_scan_cache_hit_file_count",
        limit=options.min_warm_cache_hit_file_count,
    )
    return failures


def _check_max_threshold(
    *,
    failures: list[dict[str, object]],
    metric: str,
    actual: int,
    limit: int | None,
) -> None:
    """检查最大值阈值。"""
    if limit is None or actual <= limit:
        return
    failures.append({"metric": metric, "actual": actual, "limit": limit})


def _check_warm_max_threshold(
    *,
    failures: list[dict[str, object]],
    runs: list[dict[str, object]],
    metric: str,
    limit: int | None,
) -> None:
    """检查预热后的最大值阈值。"""
    if limit is None:
        return
    worst_run: dict[str, object] | None = None
    worst_value = -1
    for run in runs:
        value = ensure_int(run.get(metric), metric)
        if value > worst_value:
            worst_value = value
            worst_run = run
    if worst_run is None or worst_value <= limit:
        return
    failures.append({
        "metric": metric,
        "actual": worst_value,
        "limit": limit,
        "run_index": ensure_int(worst_run.get("run_index"), "run_index"),
    })


def _check_warm_min_threshold(
    *,
    failures: list[dict[str, object]],
    runs: list[dict[str, object]],
    metric: str,
    limit: int | None,
) -> None:
    """检查预热后的最小值阈值。"""
    if limit is None:
        return
    worst_run: dict[str, object] | None = None
    worst_value: int | None = None
    for run in runs:
        value = ensure_int(run.get(metric), metric)
        if worst_value is None or value < worst_value:
            worst_value = value
            worst_run = run
    if worst_run is None or worst_value is None or worst_value >= limit:
        return
    failures.append({
        "metric": metric,
        "actual": worst_value,
        "limit": limit,
        "run_index": ensure_int(worst_run.get("run_index"), "run_index"),
    })


def optional_non_negative_int(value: int | None, label: str) -> int | None:
    """确认可选阈值是非负整数。"""
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{label} 必须是非负整数")
    return value


def rebuild_options_for_prepare(options: ActiveRuntimeAuditBenchmarkOptions) -> RebuildBenchmarkOptions:
    """转换成通用样本准备参数。"""
    return RebuildBenchmarkOptions(
        sample_path=options.sample_path,
        game_title=options.game_title,
        source_db_path=options.source_db_path,
        runs=options.runs,
        keep_temp=options.keep_temp,
        max_slowest_ms=None,
        max_average_ms=None,
        max_rust_plan_ms=None,
        max_file_replacement_ms=None,
        max_post_write_audit_ms=None,
        rust_threads=options.rust_threads,
    )


def prepare_active_runtime_benchmark(options: ActiveRuntimeAuditBenchmarkOptions) -> PreparedBenchmark:
    """按参数准备当前运行审计性能测试目录。"""
    if not options.register_sample:
        return prepare_benchmark(rebuild_options_for_prepare(options))
    return prepare_registered_benchmark(options)


def prepare_registered_benchmark(options: ActiveRuntimeAuditBenchmarkOptions) -> PreparedBenchmark:
    """复制样本后在临时应用目录中重新注册游戏。"""
    ensure_directory(options.sample_path, "性能样本目录")
    temp_root = Path(tempfile.mkdtemp(prefix="att_mz_rebuild_benchmark_")).resolve()
    app_home = temp_root / "app-home"
    game_path = temp_root / "game"
    db_path = app_home / "data" / "db" / f"{options.game_title}.db"
    prepared = PreparedBenchmark(
        temp_root=temp_root,
        app_home=app_home,
        game_path=game_path,
        db_path=db_path,
    )
    try:
        app_home.mkdir(parents=True)
        shutil.copytree(options.sample_path, game_path)
        prepare_app_home_assets(app_home)
        completed = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "main.py",
                "add-game",
                "--path",
                str(game_path),
                "--source-language",
                options.source_language,
            ],
            cwd=ROOT,
            env=build_cli_env(app_home=app_home, rust_threads=options.rust_threads),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"临时样本 add-game 失败，退出码 {completed.returncode}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        report = extract_last_json_object(completed.stdout)
        summary = ensure_object(report.get("summary"), "summary")
        registered_title = summary.get("game_title")
        if registered_title != options.game_title:
            raise RuntimeError(
                f"临时样本注册出的游戏标题不是 --game 指定值: {registered_title!r} != {options.game_title!r}"
            )
    except Exception as error:
        raise build_preparation_error(
            prepared=prepared,
            keep_temp=options.keep_temp,
            error=error,
            context="当前运行审计性能测试准备失败",
        ) from error
    return prepared


def main() -> int:
    """执行当前运行审计性能测试入口。"""
    options = parse_args()
    prepared: PreparedBenchmark | None = None
    try:
        prepared = prepare_active_runtime_benchmark(options)
        result = run_benchmark(options, prepared)
    except BenchmarkPreparationError as error:
        result = build_error_result(options=options, prepared=error.prepared, error=error)
        result["temp_preserved"] = error.temp_preserved
        if error.cleanup_error is not None:
            result["cleanup_error"] = error.cleanup_error
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    except Exception as error:
        if prepared is None:
            result = build_unprepared_error_result(options=options, error=error)
            result["temp_preserved"] = False
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        result = build_error_result(options=options, prepared=prepared, error=error)
    cleanup_error: str | None = None
    if not options.keep_temp:
        cleanup_error = remove_tree_with_retries(prepared.temp_root)
    result["temp_preserved"] = options.keep_temp or cleanup_error is not None
    if cleanup_error is not None:
        result["cleanup_error"] = cleanup_error
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "error" else 0


def build_unprepared_error_result(
    *,
    options: ActiveRuntimeAuditBenchmarkOptions,
    error: Exception,
) -> dict[str, object]:
    """准备出临时工作目录前失败时返回结构化当前运行审计性能失败结果。"""
    return {
        "status": "error",
        "game": options.game_title,
        "sample_path": str(options.sample_path),
        "temp_game_path": None,
        "temp_app_home": None,
        "registered_sample": options.register_sample,
        "source_db_path": result_source_db_path(options),
        "temp_db_path": None,
        "rust_threads": options.rust_threads,
        "run_count": 0,
        "threshold_failures": [],
        "error": f"{type(error).__name__}: {error}",
    }


def build_error_result(
    *,
    options: ActiveRuntimeAuditBenchmarkOptions,
    prepared: PreparedBenchmark,
    error: Exception,
) -> dict[str, object]:
    """运行阶段异常时返回可记录的当前运行审计性能失败结果。"""
    return {
        "status": "error",
        "game": options.game_title,
        "sample_path": str(options.sample_path),
        "temp_game_path": str(prepared.game_path),
        "temp_app_home": str(prepared.app_home),
        "registered_sample": options.register_sample,
        "source_db_path": result_source_db_path(options),
        "temp_db_path": str(prepared.db_path),
        "rust_threads": options.rust_threads,
        "run_count": 0,
        "threshold_failures": [],
        "error": f"{type(error).__name__}: {error}",
    }


if __name__ == "__main__":
    raise SystemExit(main())
