"""事件指令参数 JSON 导出模块。"""

import json
from pathlib import Path

import aiofiles

from app.native_scope_index import (
    build_native_event_command_candidates_payload,
    build_native_event_command_data_files,
    scan_native_rule_candidates,
)
from app.rmmz.schema import GameData
from app.rmmz.text_rules import JsonArray, JsonValue, ensure_json_array, ensure_json_object


def resolve_event_command_codes(
    *,
    command_codes: set[int] | None,
    configured_command_codes: list[int] | None,
) -> frozenset[int]:
    """解析事件指令参数导出的有效编码集合。"""
    if command_codes is None:
        if configured_command_codes is None:
            raise ValueError("未传入 CLI 编码时必须提供按引擎配置的默认编码数组")
        effective_codes = frozenset(configured_command_codes)
    else:
        effective_codes = frozenset(command_codes)

    if not effective_codes:
        raise ValueError("事件指令导出编码不能为空")
    return effective_codes


async def export_event_commands_json_file(
    *,
    game_data: GameData,
    output_path: Path,
    command_codes: frozenset[int],
) -> int:
    """把指定事件指令编码的参数样本导出为 JSON 文件。"""
    resolved_output_path = output_path.resolve()
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_native_event_command_candidates_payload(
        event_command_data_files=build_native_event_command_data_files(game_data),
        command_codes=command_codes,
    )
    native_result = scan_native_rule_candidates(payload)
    samples_by_code = _read_native_event_command_samples_by_code(
        native_result.scan_summary,
        command_codes,
    )

    async with aiofiles.open(resolved_output_path, "w", encoding="utf-8") as file:
        _ = await file.write(f"{json.dumps(samples_by_code, ensure_ascii=False, indent=2)}\n")
    return sum(len(samples) for samples in samples_by_code.values())


def _read_native_event_command_samples_by_code(
    scan_summary: dict[str, JsonValue],
    command_codes: frozenset[int],
) -> dict[str, list[list[JsonValue]]]:
    """读取 Rust event_commands.samples_by_code 并维持导出 JSON 形状。"""
    event_summary_value = scan_summary.get("event_commands")
    if event_summary_value is None:
        raise ValueError("Rust 事件指令扫描结果缺少 event_commands 摘要")
    event_summary = ensure_json_object(
        event_summary_value,
        "native_rule_candidates_result.scan_summary.event_commands",
    )
    samples_root = ensure_json_object(
        event_summary["samples_by_code"],
        "native_rule_candidates_result.scan_summary.event_commands.samples_by_code",
    )
    samples_by_code: dict[str, list[list[JsonValue]]] = {}
    for code in sorted(command_codes):
        code_key = str(code)
        native_samples = ensure_json_array(
            samples_root.get(code_key, []),
            f"native_rule_candidates_result.scan_summary.event_commands.samples_by_code.{code_key}",
        )
        samples_by_code[code_key] = _read_native_event_command_samples(native_samples, code_key)

    expected_sample_count = event_summary["sample_count"]
    actual_sample_count = sum(len(samples) for samples in samples_by_code.values())
    if not isinstance(expected_sample_count, int) or isinstance(expected_sample_count, bool):
        raise TypeError("native_rule_candidates_result.scan_summary.event_commands.sample_count 必须是整数")
    if expected_sample_count != actual_sample_count:
        raise ValueError("Rust 事件指令扫描 sample_count 与 samples_by_code 不一致")
    return samples_by_code


def _read_native_event_command_samples(native_samples: JsonArray, code_key: str) -> list[list[JsonValue]]:
    """读取单个事件指令编码下的参数数组样本。"""
    samples: list[list[JsonValue]] = []
    for index, native_sample in enumerate(native_samples):
        sample = ensure_json_array(
            native_sample,
            f"native_rule_candidates_result.scan_summary.event_commands.samples_by_code.{code_key}[{index}]",
        )
        samples.append(list(sample))
    return samples


__all__: list[str] = [
    "export_event_commands_json_file",
    "resolve_event_command_codes",
]
