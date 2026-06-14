"""计时大型游戏小任务链路的 warm index 性能。"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast

from app.rmmz.control_codes import ALL_PLACEHOLDER_PATTERN
from scripts.benchmark_rebuild_active_runtime import (
    BenchmarkOptions,
    BenchmarkPreparationError,
    PreparedBenchmark,
    build_cli_env,
    build_error_result,
    build_unprepared_error_result,
    collect_game_sample_stats,
    ensure_int,
    ensure_object,
    extract_last_json_object,
    load_diagnostics_from_summary,
    optional_positive_int,
    prepare_benchmark,
    remove_tree_with_retries,
)


ROOT = Path(__file__).resolve().parents[1]
TASK_ORDER = (
    "rebuild_text_index",
    "quality_report",
    "translate_max_items",
    "import_manual_translations",
    "reset_translations_input",
)
BENCHMARK_UNSAFE_SOURCE_CHARS = frozenset("\\[]{}<>$`%")
BENCHMARK_MAX_SIMPLE_LINE_COUNT = 4
BENCHMARK_MAX_SIMPLE_LINE_LENGTH = 80


@dataclass(frozen=True, slots=True)
class SmallTaskBenchmarkOptions:
    """小任务性能测试参数。"""

    sample_path: Path
    game_title: str
    source_db_path: Path
    runs: int
    keep_temp: bool
    max_items: int
    manual_item_count: int
    rust_threads: int | None
    max_rebuild_ms: int | None
    max_quality_report_ms: int | None
    max_translate_ms: int | None
    max_import_ms: int | None
    max_reset_ms: int | None
    use_fake_llm: bool


def parse_args(argv: Sequence[str] | None = None) -> SmallTaskBenchmarkOptions:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="计时小任务链路 warm index 性能")
    _ = parser.add_argument("--sample", required=True, help="性能样本游戏目录；脚本会复制到临时工作目录后运行")
    _ = parser.add_argument("--game", required=True, help="数据库和 CLI 使用的游戏标题")
    _ = parser.add_argument("--db", default=None, help="源数据库路径；默认使用 data/db/<游戏标题>.db")
    _ = parser.add_argument("--runs", type=int, default=1, help="重复运行次数，默认 1")
    _ = parser.add_argument("--keep-temp", action="store_true", help="保留临时样本和临时 ATT_MZ_HOME")
    _ = parser.add_argument("--max-items", type=int, default=3, help="translate --max-items 使用的数量")
    _ = parser.add_argument("--manual-item-count", type=int, default=100, help="手动导入和精确重置输入路径数量")
    _ = parser.add_argument("--rust-threads", type=int, default=None, help="本次性能命令使用的 Rust Rayon 线程数")
    _ = parser.add_argument("--max-rebuild-ms", type=int, default=None, help="rebuild-text-index 单次耗时上限")
    _ = parser.add_argument("--max-quality-report-ms", type=int, default=None, help="普通 quality-report 单次耗时上限")
    _ = parser.add_argument("--max-translate-ms", type=int, default=None, help="translate --max-items 单次耗时上限")
    _ = parser.add_argument("--max-import-ms", type=int, default=None, help="import-manual-translations 单次耗时上限")
    _ = parser.add_argument("--max-reset-ms", type=int, default=None, help="reset-translations --input 单次耗时上限")
    _ = parser.add_argument(
        "--allow-real-llm",
        action="store_true",
        help="允许 benchmark 使用当前配置中的真实模型；默认使用本地假 OpenAI 兼容服务",
    )
    namespace = parser.parse_args(argv)
    game_title = cast(str, namespace.game)
    db_arg = cast(str | None, namespace.db)
    source_db_path = Path(db_arg).expanduser().resolve() if db_arg else ROOT / "data" / "db" / f"{game_title}.db"
    runs = ensure_positive_int(cast(int, namespace.runs), "--runs")
    max_items = ensure_positive_int(cast(int, namespace.max_items), "--max-items")
    manual_item_count = ensure_positive_int(cast(int, namespace.manual_item_count), "--manual-item-count")
    return SmallTaskBenchmarkOptions(
        sample_path=Path(cast(str, namespace.sample)).expanduser().resolve(),
        game_title=game_title,
        source_db_path=source_db_path,
        runs=runs,
        keep_temp=cast(bool, namespace.keep_temp),
        max_items=max_items,
        manual_item_count=manual_item_count,
        rust_threads=optional_positive_int(cast(int | None, namespace.rust_threads), "--rust-threads"),
        max_rebuild_ms=optional_non_negative_int(cast(int | None, namespace.max_rebuild_ms), "--max-rebuild-ms"),
        max_quality_report_ms=optional_non_negative_int(
            cast(int | None, namespace.max_quality_report_ms),
            "--max-quality-report-ms",
        ),
        max_translate_ms=optional_non_negative_int(cast(int | None, namespace.max_translate_ms), "--max-translate-ms"),
        max_import_ms=optional_non_negative_int(cast(int | None, namespace.max_import_ms), "--max-import-ms"),
        max_reset_ms=optional_non_negative_int(cast(int | None, namespace.max_reset_ms), "--max-reset-ms"),
        use_fake_llm=not cast(bool, namespace.allow_real_llm),
    )


def run_benchmark(options: SmallTaskBenchmarkOptions, prepared: PreparedBenchmark) -> dict[str, object]:
    """执行小任务性能测试并返回 JSON 可序列化结果。"""
    env = build_cli_env(app_home=prepared.app_home, rust_threads=options.rust_threads)
    fake_server: FakeOpenAICompatibleServer | None = None
    if options.use_fake_llm:
        fake_server = FakeOpenAICompatibleServer()
        fake_server.start()
        write_fake_llm_client_setting(
            prepared.app_home / "setting.toml",
            base_url=fake_server.base_url,
        )
    runs: list[dict[str, object]] = []
    try:
        for run_index in range(1, options.runs + 1):
            run_items: list[dict[str, object]] = []
            rebuild_result = run_task(
                task_name="rebuild_text_index",
                command=rebuild_text_index_command(options.game_title),
                env=env,
                allow_report_error=False,
            )
            rebuild_result["run_index"] = run_index
            run_items.append(rebuild_result)
            manual_input_path, reset_input_path = write_manual_and_reset_inputs(
                db_path=prepared.db_path,
                output_dir=prepared.temp_root / f"small-task-inputs-{run_index}",
                item_count=options.manual_item_count,
            )
            task_commands = [
                ("quality_report", quality_report_command(options.game_title)),
                ("translate_max_items", translate_max_items_command(options.game_title, options.max_items)),
                ("import_manual_translations", import_manual_translations_command(options.game_title, manual_input_path)),
                ("reset_translations_input", reset_translations_command(options.game_title, reset_input_path)),
            ]
            for task_name, command in task_commands:
                task_result = run_task(
                    task_name=task_name,
                    command=command,
                    env=env,
                    allow_report_error=True,
                )
                task_result["run_index"] = run_index
                run_items.append(task_result)
            runs.extend(run_items)
        result: dict[str, object] = {
            "status": "ok",
            "game": options.game_title,
            "sample_path": str(options.sample_path),
            "sample_stats": collect_game_sample_stats(prepared.game_path),
            "temp_game_path": str(prepared.game_path),
            "temp_app_home": str(prepared.app_home),
            "source_db_path": str(options.source_db_path),
            "temp_db_path": str(prepared.db_path),
            "rust_threads": options.rust_threads,
            "llm_mode": "fake" if options.use_fake_llm else "real",
            "run_count": options.runs,
            "tasks": runs,
        }
        threshold_failures = build_threshold_failures(options=options, tasks=runs)
        command_failures = build_command_failures(tasks=runs)
        command_warnings = build_command_warnings(tasks=runs)
        result["threshold_failures"] = threshold_failures
        result["command_failures"] = command_failures
        result["command_warnings"] = command_warnings
        if threshold_failures or command_failures or command_warnings:
            result["status"] = "error"
        return result
    finally:
        if fake_server is not None:
            fake_server.stop()


def run_task(
    *,
    task_name: str,
    command: list[str],
    env: dict[str, str],
    allow_report_error: bool,
) -> dict[str, object]:
    """运行单个 CLI 命令并提取耗时摘要。"""
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
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
        summary = ensure_object(report.get("summary"), "summary")
        diagnostics = load_diagnostics_from_summary(summary)
    except Exception as error:
        if completed.returncode != 0:
            raise RuntimeError(
                f"小任务性能命令 {task_name} 失败，退出码 {completed.returncode}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ) from error
        raise
    if completed.returncode != 0 and not allow_report_error:
        raise RuntimeError(
            f"小任务性能命令 {task_name} 失败，退出码 {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    raw_status = report.get("status")
    report_status = raw_status if isinstance(raw_status, str) else ""
    return build_task_result(
        task_name=task_name,
        command=command,
        elapsed_ms=elapsed_ms,
        return_code=completed.returncode,
        report_status=report_status,
        summary=summary,
        diagnostics=diagnostics,
    )


def build_task_result(
    *,
    task_name: str,
    command: list[str],
    elapsed_ms: int,
    return_code: int,
    report_status: str,
    summary: dict[str, object],
    diagnostics: dict[str, object],
) -> dict[str, object]:
    """从 CLI JSON 摘要提取小任务性能字段。"""
    return {
        "task": task_name,
        "command": command,
        "elapsed_ms": elapsed_ms,
        "return_code": return_code,
        "report_status": report_status,
        "report_index_status": summary.get("index_status") or summary.get("text_index_status") or "",
        "diagnostics_file": str(ensure_diagnostics_file(summary)),
        "diagnostics_timings": ensure_object(diagnostics.get("timings"), "diagnostics.timings"),
        "diagnostics_counters": ensure_object(diagnostics.get("counters"), "diagnostics.counters"),
        "summary": summary,
    }


def write_manual_and_reset_inputs(
    *,
    db_path: Path,
    output_dir: Path,
    item_count: int,
) -> tuple[Path, Path]:
    """从文本索引生成手动导入和精确重置输入文件。"""
    rows = read_writable_index_rows(db_path=db_path, limit=item_count)
    if not rows:
        raise RuntimeError("文本范围索引没有可写条目，不能生成小任务输入")
    output_dir.mkdir(parents=True, exist_ok=True)
    manual_payload: dict[str, object] = {}
    reset_paths: list[str] = []
    for location_path, original_lines in rows:
        manual_payload[location_path] = {
            "translation_lines": build_benchmark_translation_lines(original_lines),
        }
        reset_paths.append(location_path)
    manual_input_path = output_dir / "manual-translations.json"
    reset_input_path = output_dir / "reset-translations.json"
    manual_input_path.write_text(json.dumps(manual_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    reset_input_path.write_text(
        json.dumps({"location_paths": reset_paths}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manual_input_path, reset_input_path


def read_writable_index_rows(*, db_path: Path, limit: int) -> list[tuple[str, list[str]]]:
    """读取 warm index 中用于小任务输入的可写路径。"""
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.execute(
            """
            SELECT location_path, original_lines
            FROM text_index_items
            WHERE writable = 1
            ORDER BY location_path
            """
        )
        rows: list[tuple[str, list[str]]] = []
        for location_path, original_lines_text in cursor.fetchall():
            if not isinstance(location_path, str) or not isinstance(original_lines_text, str):
                raise TypeError("text_index_items 字段类型异常")
            decoded = json.loads(original_lines_text)
            if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
                raise TypeError(f"{location_path} original_lines 必须是字符串数组")
            original_lines = list(decoded)
            if not is_simple_benchmark_source(original_lines):
                continue
            rows.append((location_path, original_lines))
            if len(rows) >= limit:
                break
        if len(rows) < limit:
            raise RuntimeError(
                f"文本范围索引只有 {len(rows)} 条简单可写条目，不能生成 {limit} 条干净小任务输入"
            )
        return rows
    finally:
        connection.close()


def is_simple_benchmark_source(lines: list[str]) -> bool:
    """判断原文是否适合生成不带业务语义的 benchmark 假译文。"""
    if not lines or len(lines) > BENCHMARK_MAX_SIMPLE_LINE_COUNT:
        return False
    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) > BENCHMARK_MAX_SIMPLE_LINE_LENGTH:
            return False
        if any(char in BENCHMARK_UNSAFE_SOURCE_CHARS for char in stripped):
            return False
        if "\n" in stripped or "\r" in stripped:
            return False
        if ALL_PLACEHOLDER_PATTERN.search(stripped) is not None:
            return False
        if re.search(r"\\[A-Za-z0-9]", stripped):
            return False
    return True


def build_benchmark_translation_lines(original_lines: list[str]) -> list[str]:
    """按原文行数生成低风险中文假译文。"""
    return ["测试译文" for _line in original_lines]


def rebuild_text_index_command(game_title: str) -> list[str]:
    """返回重建文本范围索引命令。"""
    return debug_cli_command("rebuild-text-index", "--game", game_title)


def quality_report_command(game_title: str) -> list[str]:
    """返回普通质量报告命令。"""
    return debug_cli_command("quality-report", "--game", game_title)


def translate_max_items_command(game_title: str, max_items: int) -> list[str]:
    """返回小批翻译命令。"""
    return debug_cli_command("translate", "--game", game_title, "--max-items", str(max_items))


def write_fake_llm_client_setting(setting_path: Path, *, base_url: str) -> None:
    """把临时配置中的模型客户端替换为本地假 OpenAI 兼容服务。"""
    fake_section = [
        "[llm]",
        'default_client = "benchmark-fake"',
        "",
        "[[llm.clients]]",
        'name = "benchmark-fake"',
        'provider_type = "openai"',
        f'base_url = "{base_url}"',
        'api_key = "att-mz-benchmark-fake-key"',
        'model = "att-mz-benchmark-fake"',
        "timeout = 30",
        "",
    ]
    lines = setting_path.read_text(encoding="utf-8-sig").splitlines()
    output_lines: list[str] = []
    skipping_llm_section = False
    inserted = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[llm]":
            output_lines.extend(fake_section)
            skipping_llm_section = True
            inserted = True
            continue
        if skipping_llm_section:
            if stripped.startswith("[") and not stripped.startswith("[llm") and not stripped.startswith("[[llm"):
                skipping_llm_section = False
                output_lines.append(line)
            continue
        output_lines.append(line)
    if not inserted:
        output_lines = [*fake_section, *output_lines]
    setting_path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")


def import_manual_translations_command(game_title: str, input_path: Path) -> list[str]:
    """返回手动译文导入命令。"""
    return debug_cli_command("import-manual-translations", "--game", game_title, "--input", str(input_path))


def reset_translations_command(game_title: str, input_path: Path) -> list[str]:
    """返回精确重置译文命令。"""
    return debug_cli_command("reset-translations", "--game", game_title, "--input", str(input_path))


def debug_cli_command(command_name: str, *args: str) -> list[str]:
    """构造启用统一计时、关闭 debug 日志的 CLI 命令。"""
    return [
        "uv",
        "run",
        "python",
        "main.py",
        "--debug",
        "--debug-timings",
        "--no-debug-logging",
        command_name,
        *args,
    ]


def ensure_diagnostics_file(summary: dict[str, object]) -> Path:
    """读取 stdout summary 中的 diagnostics 文件路径。"""
    diagnostics_summary = ensure_object(summary.get("diagnostics"), "summary.diagnostics")
    file_value = diagnostics_summary.get("file")
    if not isinstance(file_value, str) or not file_value.strip():
        raise TypeError("summary.diagnostics.file 必须是非空字符串")
    return Path(file_value)


class FakeOpenAICompatibleServer:
    """小任务 benchmark 专用本地 OpenAI 兼容假服务。"""

    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def base_url(self) -> str:
        """返回 OpenAI SDK 可使用的 `/v1` 根地址。"""
        if self._server is None:
            raise RuntimeError("假模型服务尚未启动")
        host, port = cast(tuple[str, int], self._server.server_address)
        return f"http://{host}:{port}/v1"

    def start(self) -> None:
        """启动本地 HTTP 服务。"""
        if self._server is not None:
            raise RuntimeError("假模型服务已经启动")
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIRequestHandler)
        self._thread = Thread(target=self._server.serve_forever, name="att-mz-benchmark-fake-llm", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止本地 HTTP 服务。"""
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


class FakeOpenAIRequestHandler(BaseHTTPRequestHandler):
    """响应 OpenAI Chat Completions 请求。"""

    def do_POST(self) -> None:
        """返回可通过项目 JSON 译文解析的假响应。"""
        try:
            payload = read_request_json(self)
            content = build_fake_chat_completion_content(payload)
            response = {
                "id": "chatcmpl-att-mz-benchmark",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "att-mz-benchmark-fake",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
            response_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)
        except Exception as error:
            response_bytes = json.dumps(
                {
                    "error": {
                        "message": f"benchmark fake llm error: {type(error).__name__}: {error}",
                        "type": "benchmark_fake_llm_error",
                    }
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)

    def log_message(self, format: str, *args: object) -> None:
        """benchmark 输出只保留 CLI JSON，不输出 HTTP 访问日志。"""
        _ = (format, args)


def read_request_json(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    """读取 OpenAI 兼容请求 JSON。"""
    length_text = handler.headers.get("Content-Length", "0")
    length = int(length_text)
    raw_body = handler.rfile.read(length)
    raw_payload = json.loads(raw_body.decode("utf-8"))
    if not isinstance(raw_payload, dict):
        raise TypeError("OpenAI 请求体必须是 JSON 对象")
    return cast(dict[str, object], raw_payload)


def build_fake_chat_completion_content(payload: dict[str, object]) -> str:
    """根据 user prompt 中的 id 和 line_count 生成假译文 JSON。"""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise TypeError("OpenAI 请求体缺少 messages 数组")
    user_prompt = ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        user_prompt = content
        break
    if not user_prompt:
        raise ValueError("OpenAI 请求体缺少 user prompt")
    return json.dumps(build_fake_translation_response_items(user_prompt), ensure_ascii=False)


def build_fake_translation_response_items(user_prompt: str) -> list[dict[str, object]]:
    """从正文 prompt 中提取每条 id，生成行数匹配的测试译文。"""
    items: list[dict[str, object]] = []
    current_id: str | None = None
    current_line_count = 1
    current_placeholders: list[str] = []
    for raw_line in user_prompt.splitlines():
        line = raw_line.strip()
        if line.startswith("id:"):
            if current_id is not None:
                items.append(_fake_translation_item(current_id, current_line_count, current_placeholders))
            current_id = line.removeprefix("id:").strip()
            current_line_count = 1
            current_placeholders = []
            continue
        if current_id is not None:
            current_placeholders.extend(ALL_PLACEHOLDER_PATTERN.findall(line))
        if current_id is not None and line.startswith("line_count:"):
            count_text = line.removeprefix("line_count:").strip()
            current_line_count = max(int(count_text), 1)
    if current_id is not None:
        items.append(_fake_translation_item(current_id, current_line_count, current_placeholders))
    return items


def _fake_translation_item(prompt_id: str, line_count: int, placeholders: list[str]) -> dict[str, object]:
    """构造一条假译文响应。"""
    first_line = "测试译文"
    if placeholders:
        first_line = f"{first_line} {' '.join(placeholders)}"
    translation_lines = [first_line]
    translation_lines.extend("测试译文" for _index in range(1, line_count))
    return {
        "id": prompt_id,
        "translation_lines": translation_lines,
    }


def build_threshold_failures(
    *,
    options: SmallTaskBenchmarkOptions,
    tasks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """按显式阈值生成性能失败清单。"""
    thresholds = {
        "rebuild_text_index": options.max_rebuild_ms,
        "quality_report": options.max_quality_report_ms,
        "translate_max_items": options.max_translate_ms,
        "import_manual_translations": options.max_import_ms,
        "reset_translations_input": options.max_reset_ms,
    }
    failures: list[dict[str, object]] = []
    for task in tasks:
        task_name = task.get("task")
        if not isinstance(task_name, str):
            raise TypeError("task 必须是字符串")
        limit = thresholds.get(task_name)
        if limit is None:
            continue
        elapsed_ms = ensure_int(task.get("elapsed_ms"), "elapsed_ms")
        if elapsed_ms > limit:
            failures.append({
                "task": task_name,
                "actual": elapsed_ms,
                "limit": limit,
                "run_index": ensure_int(task.get("run_index"), "run_index"),
            })
    return failures


def build_command_failures(*, tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    """把结构化 CLI 失败记录为 benchmark 失败，但不丢失已测得耗时。"""
    failures: list[dict[str, object]] = []
    for task in tasks:
        task_name = task.get("task")
        if not isinstance(task_name, str):
            raise TypeError("task 必须是字符串")
        return_code = ensure_int(task.get("return_code"), "return_code")
        raw_status = task.get("report_status")
        report_status = raw_status if isinstance(raw_status, str) else ""
        if return_code == 0 and report_status != "error":
            continue
        failures.append({
            "task": task_name,
            "return_code": return_code,
            "report_status": report_status,
            "run_index": ensure_int(task.get("run_index"), "run_index"),
        })
    return failures


def build_command_warnings(*, tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    """记录 CLI 成功退出但报告状态不是 ok 的任务。"""
    warnings: list[dict[str, object]] = []
    for task in tasks:
        task_name = task.get("task")
        if not isinstance(task_name, str):
            raise TypeError("task 必须是字符串")
        return_code = ensure_int(task.get("return_code"), "return_code")
        raw_status = task.get("report_status")
        report_status = raw_status if isinstance(raw_status, str) else ""
        if return_code != 0 or report_status in ("", "ok", "error"):
            continue
        warnings.append({
            "task": task_name,
            "return_code": return_code,
            "report_status": report_status,
            "run_index": ensure_int(task.get("run_index"), "run_index"),
        })
    return warnings


def prepare_small_task_benchmark(options: SmallTaskBenchmarkOptions) -> PreparedBenchmark:
    """复用写回性能脚本的样本复制和临时应用目录准备。"""
    return prepare_benchmark(
        BenchmarkOptions(
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
    )


def optional_non_negative_int(value: int | None, label: str) -> int | None:
    """确认可选阈值是非负整数。"""
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{label} 必须是非负整数")
    return value


def ensure_positive_int(value: int, label: str) -> int:
    """确认参数是正整数。"""
    if value <= 0:
        raise ValueError(f"{label} 必须是正整数")
    return value


def main() -> int:
    """执行小任务性能测试入口。"""
    options = parse_args()
    prepared: PreparedBenchmark | None = None
    try:
        prepared = prepare_small_task_benchmark(options)
        result = run_benchmark(options, prepared)
    except BenchmarkPreparationError as error:
        result = build_error_result(options=rebuild_options_for_error(options), prepared=error.prepared, error=error)
        result["temp_preserved"] = error.temp_preserved
        if error.cleanup_error is not None:
            result["cleanup_error"] = error.cleanup_error
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    except Exception as error:
        if prepared is None:
            result = build_unprepared_error_result(options=rebuild_options_for_error(options), error=error)
            result["temp_preserved"] = False
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        result = build_error_result(options=rebuild_options_for_error(options), prepared=prepared, error=error)
    cleanup_error: str | None = None
    if prepared is not None and not options.keep_temp:
        cleanup_error = remove_tree_with_retries(prepared.temp_root)
    result["temp_preserved"] = options.keep_temp or cleanup_error is not None
    if cleanup_error is not None:
        result["cleanup_error"] = cleanup_error
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "error" else 0


def rebuild_options_for_error(options: SmallTaskBenchmarkOptions) -> BenchmarkOptions:
    """把小任务参数转换为现有错误报告辅助函数需要的参数。"""
    return BenchmarkOptions(
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


if __name__ == "__main__":
    raise SystemExit(main())
