"""非标准 data 文件文本规则驱动提取。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.json_path_protocol import ResolvedLeaf
from app.rmmz.loader import resolve_data_source_dir
from app.rmmz.schema import GameData, NonstandardDataTextRuleRecord
from app.rmmz.text_rules import coerce_json_value

from .scanner import (
    NonstandardDataFile,
    resolve_nonstandard_data_file_leaves_native,
)

NONSTANDARD_DATA_LOCATION_PREFIX = "nonstandard-data"


@dataclass(frozen=True, slots=True)
class NonstandardDataTextExtractionContext:
    """非标准 data 文本提取在同一轮流程内复用的文件和叶子事实。"""

    files_by_name: dict[str, NonstandardDataFile]
    leaves_by_file: dict[str, tuple[ResolvedLeaf, ...]]


def nonstandard_data_file_key(file_name: str) -> str:
    """返回统一文本范围中的非标准 data 文件键。"""
    return f"{NONSTANDARD_DATA_LOCATION_PREFIX}/{file_name}"


def nonstandard_data_location_path(*, file_name: str, json_path: str) -> str:
    """返回非标准 data 文本内部定位键。"""
    return f"{nonstandard_data_file_key(file_name)}/{json_path}"


def parse_nonstandard_data_location_path(location_path: str) -> tuple[str, str] | None:
    """从内部定位键解析非标准 data 文件名和 JSONPath。"""
    prefix = f"{NONSTANDARD_DATA_LOCATION_PREFIX}/"
    if not location_path.startswith(prefix):
        return None
    remain = location_path[len(prefix):]
    parts = remain.split("/", 1)
    if len(parts) != 2:
        return None
    file_name, json_path = parts
    if not file_name.endswith(".json") or not json_path.startswith("$"):
        return None
    return file_name, json_path


def _read_nonstandard_data_file(path: Path) -> NonstandardDataFile:
    """严格读取并解析一个非标准 data JSON 文件。"""
    if not path.is_file():
        raise RuntimeError(f"非标准 data 文件规则已过期: 文件不存在: {path.name}")
    raw_text = path.read_bytes().decode("utf-8")
    decoded_raw = cast(object, json.loads(raw_text))
    value = coerce_json_value(decoded_raw)
    return NonstandardDataFile(
        file_name=path.name,
        path=path,
        raw_text=raw_text,
        value=value,
    )


def build_nonstandard_data_text_extraction_context(
    *,
    game_data: GameData,
    rule_records: list[NonstandardDataTextRuleRecord],
    skip_missing_files: bool = False,
) -> NonstandardDataTextExtractionContext:
    """为同一轮非标准 data 文本流程构建可复用的文件和 native leaves 事实。"""
    files_by_name = _load_nonstandard_files_by_name(
        game_data=game_data,
        rule_records=rule_records,
        skip_missing_files=skip_missing_files,
    )
    return NonstandardDataTextExtractionContext(
        files_by_name=files_by_name,
        leaves_by_file=_native_leaves_by_file(files_by_name),
    )


def _load_nonstandard_files_by_name(
    *,
    game_data: GameData,
    rule_records: list[NonstandardDataTextRuleRecord],
    skip_missing_files: bool = False,
) -> dict[str, NonstandardDataFile]:
    """同步读取翻译源视图里的非标准 data 文件。"""
    data_dir = resolve_data_source_dir(
        layout=game_data.layout,
        use_origin_backups=True,
        require_origin_backups=True,
    )
    file_names = {record.file_name for record in rule_records}
    files: dict[str, NonstandardDataFile] = {}
    for file_name in sorted(file_names):
        path = data_dir / file_name
        try:
            files[file_name] = _read_nonstandard_data_file(path)
        except RuntimeError:
            if skip_missing_files:
                continue
            raise
    return files


def _native_leaves_by_file(
    files_by_name: dict[str, NonstandardDataFile],
) -> dict[str, tuple[ResolvedLeaf, ...]]:
    """从当前文件值一次性获取 Rust 展开的叶子事实。"""
    return resolve_nonstandard_data_file_leaves_native(
        {file_name: nonstandard_file.value for file_name, nonstandard_file in files_by_name.items()}
    )


__all__ = [
    "NONSTANDARD_DATA_LOCATION_PREFIX",
    "NonstandardDataTextExtractionContext",
    "build_nonstandard_data_text_extraction_context",
    "nonstandard_data_file_key",
    "nonstandard_data_location_path",
    "parse_nonstandard_data_location_path",
]
