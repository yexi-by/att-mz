"""复制样本并计时 `rebuild-active-runtime` 热路径。

本脚本只把 CLI 命令运行时间计入性能结果。样本复制、数据库复制、应用运行目录
准备和数据库 metadata 改写都在计时前完成。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import cast


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BenchmarkOptions:
    """性能测试参数。"""

    sample_path: Path
    game_title: str
    source_db_path: Path
    runs: int
    keep_temp: bool
    max_slowest_ms: int | None
    max_average_ms: int | None
    max_rust_plan_ms: int | None
    max_file_replacement_ms: int | None
    max_post_write_audit_ms: int | None
    rust_threads: int | None = None
    reset_active_data_from_origin: bool = False


@dataclass(frozen=True, slots=True)
class PreparedBenchmark:
    """已准备好的临时性能测试目录。"""

    temp_root: Path
    app_home: Path
    game_path: Path
    db_path: Path


class BenchmarkPreparationError(RuntimeError):
    """性能测试准备阶段失败，携带临时目录清理状态。"""

    def __init__(
        self,
        message: str,
        *,
        prepared: PreparedBenchmark,
        temp_preserved: bool,
        cleanup_error: str | None,
    ) -> None:
        super().__init__(message)
        self.prepared = prepared
        self.temp_preserved = temp_preserved
        self.cleanup_error = cleanup_error


def parse_args(argv: Sequence[str] | None = None) -> BenchmarkOptions:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="计时 rebuild-active-runtime 样本热路径")
    _ = parser.add_argument(
        "--sample",
        required=True,
        help="性能样本游戏目录；脚本会复制到临时目录后运行",
    )
    _ = parser.add_argument(
        "--game",
        required=True,
        help="数据库和 CLI 使用的游戏标题",
    )
    _ = parser.add_argument(
        "--db",
        default=None,
        help="源数据库路径；默认使用 data/db/<游戏标题>.db",
    )
    _ = parser.add_argument("--runs", type=int, default=3, help="重复运行次数，默认 3")
    _ = parser.add_argument("--keep-temp", action="store_true", help="保留临时样本和临时 ATT_MZ_HOME")
    _ = parser.add_argument("--max-slowest-ms", type=int, default=None, help="允许的最慢单次总耗时上限")
    _ = parser.add_argument("--max-average-ms", type=int, default=None, help="允许的平均总耗时上限")
    _ = parser.add_argument("--max-rust-plan-ms", type=int, default=None, help="允许的单次 Rust 写回计划耗时上限")
    _ = parser.add_argument("--max-file-replacement-ms", type=int, default=None, help="允许的单次文件替换耗时上限")
    _ = parser.add_argument("--max-post-write-audit-ms", type=int, default=None, help="允许的单次写后审计耗时上限")
    _ = parser.add_argument("--rust-threads", type=int, default=None, help="本次性能命令使用的 Rust Rayon 线程数")
    _ = parser.add_argument(
        "--reset-active-data-from-origin",
        action="store_true",
        help="每轮计时前把临时样本 data_origin/*.json 复制回 data/*.json，用于强制验证真实文件替换路径",
    )
    namespace = parser.parse_args(argv)
    game_title = cast(str, namespace.game)
    db_arg = cast(str | None, namespace.db)
    source_db_path = Path(db_arg).expanduser().resolve() if db_arg else ROOT / "data" / "db" / f"{game_title}.db"
    runs = cast(int, namespace.runs)
    if runs <= 0:
        raise ValueError("--runs 必须是正整数")
    max_slowest_ms = _optional_non_negative_int(cast(int | None, namespace.max_slowest_ms), "--max-slowest-ms")
    max_average_ms = _optional_non_negative_int(cast(int | None, namespace.max_average_ms), "--max-average-ms")
    max_rust_plan_ms = _optional_non_negative_int(cast(int | None, namespace.max_rust_plan_ms), "--max-rust-plan-ms")
    max_file_replacement_ms = _optional_non_negative_int(
        cast(int | None, namespace.max_file_replacement_ms),
        "--max-file-replacement-ms",
    )
    max_post_write_audit_ms = _optional_non_negative_int(
        cast(int | None, namespace.max_post_write_audit_ms),
        "--max-post-write-audit-ms",
    )
    return BenchmarkOptions(
        sample_path=Path(cast(str, namespace.sample)).expanduser().resolve(),
        game_title=game_title,
        source_db_path=source_db_path,
        runs=runs,
        keep_temp=cast(bool, namespace.keep_temp),
        max_slowest_ms=max_slowest_ms,
        max_average_ms=max_average_ms,
        max_rust_plan_ms=max_rust_plan_ms,
        max_file_replacement_ms=max_file_replacement_ms,
        max_post_write_audit_ms=max_post_write_audit_ms,
        rust_threads=optional_positive_int(cast(int | None, namespace.rust_threads), "--rust-threads"),
        reset_active_data_from_origin=cast(bool, namespace.reset_active_data_from_origin),
    )


def prepare_benchmark(options: BenchmarkOptions) -> PreparedBenchmark:
    """复制样本、应用资源和数据库，并把数据库 metadata 指向临时样本。"""
    ensure_directory(options.sample_path, "性能样本目录")
    ensure_file(options.source_db_path, "源数据库")
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
        db_path.parent.mkdir(parents=True)
        shutil.copy2(options.source_db_path, db_path)
        update_database_metadata(
            db_path=db_path,
            game_title=options.game_title,
            game_path=game_path,
            content_root=resolve_content_root(game_path),
        )
    except Exception as error:
        raise build_preparation_error(
            prepared=prepared,
            keep_temp=options.keep_temp,
            error=error,
            context="重建运行文件性能测试准备失败",
        ) from error
    return prepared


def build_preparation_error(
    *,
    prepared: PreparedBenchmark,
    keep_temp: bool,
    error: Exception,
    context: str,
) -> BenchmarkPreparationError:
    """生成带临时目录清理结果的准备阶段错误。"""
    cleanup_error: str | None = None
    temp_preserved = keep_temp
    if not keep_temp:
        cleanup_error = remove_tree_with_retries(prepared.temp_root)
        temp_preserved = cleanup_error is not None
    message = f"{context}: {type(error).__name__}: {error}"
    if cleanup_error is not None:
        message = f"{message}\n清理临时目录失败: {cleanup_error}"
    elif temp_preserved:
        message = f"{message}\n临时目录已保留: {prepared.temp_root}"
    return BenchmarkPreparationError(
        message,
        prepared=prepared,
        temp_preserved=temp_preserved,
        cleanup_error=cleanup_error,
    )


def prepare_app_home_assets(app_home: Path) -> None:
    """复制运行命令需要的配置和随包资源。"""
    setting_source = ROOT / "setting.toml"
    if not setting_source.is_file():
        setting_source = ROOT / "setting.example.toml"
    ensure_file(setting_source, "配置文件")
    shutil.copy2(setting_source, app_home / "setting.toml")
    for directory_name in ("fonts", "prompts"):
        source_dir = ROOT / directory_name
        if source_dir.is_dir():
            shutil.copytree(source_dir, app_home / directory_name)


def update_database_metadata(
    *,
    db_path: Path,
    game_title: str,
    game_path: Path,
    content_root: Path,
) -> None:
    """把复制后的数据库绑定到临时样本路径。"""
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.execute(
            "UPDATE metadata SET game_path = ?, content_root = ? WHERE metadata_key = 'current_game' AND game_title = ?",
            (str(game_path), str(content_root), game_title),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"数据库 metadata 没有唯一命中当前游戏: {db_path}")
        connection.commit()
    finally:
        connection.close()


def run_benchmark(options: BenchmarkOptions, prepared: PreparedBenchmark) -> dict[str, object]:
    """运行 CLI 性能测试并返回 JSON 可序列化结果。"""
    runs: list[dict[str, object]] = []
    command = rebuild_active_runtime_command(options.game_title)
    for index in range(1, options.runs + 1):
        active_data_reset_count = (
            reset_active_data_from_origin(prepared.game_path)
            if options.reset_active_data_from_origin
            else 0
        )
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
        if completed.returncode != 0:
            raise RuntimeError(
                f"性能命令第 {index} 次运行失败，退出码 {completed.returncode}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        report = extract_last_json_object(completed.stdout)
        summary = ensure_object(report.get("summary"), "summary")
        run_result = build_run_result(
            index=index,
            elapsed_ms=elapsed_ms,
            return_code=completed.returncode,
            summary=summary,
        )
        run_result["active_data_reset_from_origin_count"] = active_data_reset_count
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
        "source_db_path": str(options.source_db_path),
        "temp_db_path": str(prepared.db_path),
        "rust_threads": options.rust_threads,
        "reset_active_data_from_origin": options.reset_active_data_from_origin,
        "active_data_reset_from_origin_count": sum(
            ensure_int(run["active_data_reset_from_origin_count"], "active_data_reset_from_origin_count")
            for run in runs
        ),
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


def reset_active_data_from_origin(game_path: Path) -> int:
    """把临时样本的可信源 data JSON 复制回当前运行 data 目录。"""
    content_root = resolve_content_root(game_path)
    origin_dir = content_root / "data_origin"
    data_dir = content_root / "data"
    if not origin_dir.is_dir():
        raise RuntimeError(f"临时样本缺少 data_origin 目录，不能强制验证真实替换路径: {origin_dir}")
    if not data_dir.is_dir():
        raise RuntimeError(f"临时样本缺少 data 目录，不能强制验证真实替换路径: {data_dir}")
    reset_count = 0
    for origin_path in sorted(origin_dir.glob("*.json"), key=lambda path: path.name):
        if not origin_path.is_file():
            continue
        shutil.copy2(origin_path, data_dir / origin_path.name)
        reset_count += 1
    return reset_count


def rebuild_active_runtime_command(game_title: str) -> list[str]:
    """返回本脚本计时的重建运行文件命令。"""
    return [
        "uv",
        "run",
        "python",
        "main.py",
        "--agent-mode",
        "rebuild-active-runtime",
        "--game",
        game_title,
        "--confirm-font-overwrite",
        "--json",
    ]


def build_run_result(
    *,
    index: int,
    elapsed_ms: int,
    return_code: int,
    summary: dict[str, object],
) -> dict[str, object]:
    """从 CLI JSON 摘要提取性能分段。"""
    return {
        "run_index": index,
        "elapsed_ms": elapsed_ms,
        "return_code": return_code,
        "rust_plan_ms": ensure_int(summary.get("rust_plan_ms"), "rust_plan_ms"),
        "file_replacement_ms": ensure_int(summary.get("file_replacement_ms"), "file_replacement_ms"),
        "post_write_audit_ms": ensure_int(summary.get("post_write_audit_ms"), "post_write_audit_ms"),
        "planned_file_count": ensure_int(summary.get("planned_file_count"), "planned_file_count"),
        "skipped_file_count": ensure_int(summary.get("skipped_file_count"), "skipped_file_count"),
        "plugin_source_ast_source_scan_file_count": ensure_int(
            summary.get("plugin_source_ast_source_scan_file_count"),
            "plugin_source_ast_source_scan_file_count",
        ),
        "plugin_source_ast_runtime_scan_file_count": ensure_int(
            summary.get("plugin_source_ast_runtime_scan_file_count"),
            "plugin_source_ast_runtime_scan_file_count",
        ),
        "plugin_source_runtime_map_count": ensure_int(
            summary.get("plugin_source_runtime_map_count"),
            "plugin_source_runtime_map_count",
        ),
        "data_item_count": ensure_int(summary.get("data_item_count"), "data_item_count"),
        "plugin_item_count": ensure_int(summary.get("plugin_item_count"), "plugin_item_count"),
        "terminology_written_count": ensure_int(
            summary.get("terminology_written_count"),
            "terminology_written_count",
        ),
    }


def collect_game_sample_stats(game_path: Path) -> dict[str, int]:
    """统计临时副本样本规模，便于性能结果复核。"""
    content_root = resolve_content_root(game_path)
    file_count = 0
    total_bytes = 0
    for path in game_path.rglob("*"):
        if path.is_file():
            file_count += 1
            total_bytes += path.stat().st_size
    data_dir = content_root / "data"
    plugin_dir = content_root / "js" / "plugins"
    data_json_file_count = sum(1 for path in data_dir.glob("*.json") if path.is_file()) if data_dir.exists() else 0
    plugin_js_file_count = sum(1 for path in plugin_dir.rglob("*.js") if path.is_file()) if plugin_dir.exists() else 0
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "data_json_file_count": data_json_file_count,
        "plugin_js_file_count": plugin_js_file_count,
    }


def build_threshold_failures(*, options: BenchmarkOptions, result: dict[str, object]) -> list[dict[str, object]]:
    """按显式阈值生成性能失败清单。"""
    failures: list[dict[str, object]] = []
    runs = ensure_run_results(result.get("runs"), "runs")
    _check_aggregate_threshold(
        failures=failures,
        metric="slowest_ms",
        actual=ensure_int(result.get("slowest_ms"), "slowest_ms"),
        limit=options.max_slowest_ms,
    )
    _check_aggregate_threshold(
        failures=failures,
        metric="average_ms",
        actual=ensure_int(result.get("average_ms"), "average_ms"),
        limit=options.max_average_ms,
    )
    _check_run_threshold(
        failures=failures,
        runs=runs,
        metric="rust_plan_ms",
        limit=options.max_rust_plan_ms,
    )
    _check_run_threshold(
        failures=failures,
        runs=runs,
        metric="file_replacement_ms",
        limit=options.max_file_replacement_ms,
    )
    _check_run_threshold(
        failures=failures,
        runs=runs,
        metric="post_write_audit_ms",
        limit=options.max_post_write_audit_ms,
    )
    return failures


def _check_aggregate_threshold(
    *,
    failures: list[dict[str, object]],
    metric: str,
    actual: int,
    limit: int | None,
) -> None:
    """检查汇总耗时阈值。"""
    if limit is None or actual <= limit:
        return
    failures.append({
        "metric": metric,
        "actual": actual,
        "limit": limit,
    })


def _check_run_threshold(
    *,
    failures: list[dict[str, object]],
    runs: list[dict[str, object]],
    metric: str,
    limit: int | None,
) -> None:
    """检查每轮运行的耗时阈值。"""
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


def extract_last_json_object(text: str) -> dict[str, object]:
    """从混有进度行的 stdout 中提取最后一个 JSON 对象。"""
    decoder = json.JSONDecoder()
    last_object: dict[str, object] | None = None
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if text[index + end :].strip():
            continue
        if isinstance(value, dict):
            last_object = cast(dict[str, object], value)
    if last_object is None:
        raise RuntimeError("性能命令 stdout 中没有找到 JSON 对象")
    return last_object


def resolve_content_root(game_path: Path) -> Path:
    """解析 RPG Maker 内容目录。"""
    if (game_path / "data").is_dir() and (game_path / "js" / "plugins.js").is_file():
        return game_path
    www_root = game_path / "www"
    if (www_root / "data").is_dir() and (www_root / "js" / "plugins.js").is_file():
        return www_root
    raise RuntimeError(f"未找到可识别的 RPG Maker 游戏结构: {game_path}")


def ensure_file(path: Path, label: str) -> None:
    """确认文件存在。"""
    if not path.is_file():
        raise FileNotFoundError(f"{label}不存在: {path}")


def ensure_directory(path: Path, label: str) -> None:
    """确认目录存在。"""
    if not path.is_dir():
        raise NotADirectoryError(f"{label}不存在: {path}")


def ensure_object(value: object, label: str) -> dict[str, object]:
    """确认 JSON 值是对象。"""
    if not isinstance(value, dict):
        raise TypeError(f"{label} 必须是 JSON 对象")
    return cast(dict[str, object], value)


def ensure_run_results(value: object, label: str) -> list[dict[str, object]]:
    """确认 JSON 值是运行结果对象数组。"""
    if not isinstance(value, list):
        raise TypeError(f"{label} 必须是 JSON 数组")
    runs: list[dict[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"{label}[{index}] 必须是 JSON 对象")
        runs.append(cast(dict[str, object], item))
    return runs


def ensure_int(value: object, label: str) -> int:
    """确认 JSON 值是整数。"""
    if not isinstance(value, int):
        raise TypeError(f"{label} 必须是整数")
    return value


def _optional_non_negative_int(value: int | None, label: str) -> int | None:
    """确认可选阈值是非负整数。"""
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{label} 必须是非负整数")
    return value


def optional_positive_int(value: int | None, label: str) -> int | None:
    """确认可选线程数是正整数。"""
    if value is None:
        return None
    if value <= 0:
        raise ValueError(f"{label} 必须是正整数")
    return value


def build_cli_env(*, app_home: Path, rust_threads: int | None) -> dict[str, str]:
    """构造性能命令环境变量。"""
    env = {**os.environ, "ATT_MZ_HOME": str(app_home)}
    if rust_threads is not None:
        env["ATT_MZ_RUST_THREADS"] = str(rust_threads)
    return env


def main() -> int:
    """执行性能测试入口。"""
    options = parse_args()
    prepared: PreparedBenchmark | None = None
    try:
        prepared = prepare_benchmark(options)
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
    options: BenchmarkOptions,
    error: Exception,
) -> dict[str, object]:
    """准备出临时目录前失败时返回结构化性能失败结果。"""
    return {
        "status": "error",
        "game": options.game_title,
        "sample_path": str(options.sample_path),
        "temp_game_path": None,
        "temp_app_home": None,
        "source_db_path": str(options.source_db_path),
        "temp_db_path": None,
        "rust_threads": options.rust_threads,
        "run_count": 0,
        "threshold_failures": [],
        "error": f"{type(error).__name__}: {error}",
    }


def build_error_result(
    *,
    options: BenchmarkOptions,
    prepared: PreparedBenchmark,
    error: Exception,
) -> dict[str, object]:
    """运行阶段异常时返回可记录的性能失败结果。"""
    return {
        "status": "error",
        "game": options.game_title,
        "sample_path": str(options.sample_path),
        "temp_game_path": str(prepared.game_path),
        "temp_app_home": str(prepared.app_home),
        "source_db_path": str(options.source_db_path),
        "temp_db_path": str(prepared.db_path),
        "rust_threads": options.rust_threads,
        "run_count": 0,
        "threshold_failures": [],
        "error": f"{type(error).__name__}: {error}",
    }


def remove_tree_with_retries(path: Path) -> str | None:
    """删除临时目录，处理 Windows 文件句柄短暂占用。"""
    last_error: OSError | None = None
    for _attempt in range(20):
        try:
            shutil.rmtree(path, ignore_errors=False)
            return None
        except OSError as error:
            last_error = error
            time.sleep(0.5)
    if last_error is not None:
        return str(last_error)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
