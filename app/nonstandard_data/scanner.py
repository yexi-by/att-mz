"""非标准 data JSON 扫描与工作区导出。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import aiofiles

from app.json_path_protocol import ResolvedLeaf
from app.native_scope_index import (
    NativeRuleCandidatesResult,
    build_native_nonstandard_data_candidates_payload,
    build_native_nonstandard_data_leaves_payload,
    scan_native_rule_candidates,
)
from app.rmmz.game_file_view import GameFileView
from app.rmmz.loader import resolve_data_source_dir
from app.rmmz.schema import FIXED_FILE_NAMES, GameLayout, MAP_PATTERN
from app.rmmz.text_rules import (
    JsonObject,
    JsonValue,
    TextRules,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
)

NONSTANDARD_DATA_SOURCE_TYPE = "nonstandard-data"


@dataclass(frozen=True, slots=True)
class NonstandardDataFile:
    """一个非标准 data JSON 文件的翻译源视图快照。"""

    file_name: str
    path: Path
    raw_text: str
    value: JsonValue


@dataclass(frozen=True, slots=True)
class NonstandardDataCandidate:
    """非标准 data 文件中疑似玩家可见源语言文本候选。"""

    file_name: str
    json_path: str
    source_text: str
    raw_text: str
    field_name: str
    sibling_field_names: tuple[str, ...] = ()
    parent_object_keys: tuple[str, ...] = ()

    def to_json_object(self) -> JsonObject:
        """转换为 Agent 可读的候选 JSON 对象。"""
        return {
            "file": self.file_name,
            "json_path": self.json_path,
            "source_text": self.source_text,
            "field_name": self.field_name,
            "occurrence_count": 1,
            "samples_for_same_path": [self.source_text],
            "sibling_field_names": list(self.sibling_field_names),
            "parent_object_keys": list(self.parent_object_keys),
        }


@dataclass(frozen=True, slots=True)
class NonstandardDataFileScan:
    """单个非标准 data 文件的扫描摘要。"""

    file_name: str
    string_leaf_count: int
    candidate_count: int

    def to_json_object(self) -> JsonObject:
        """转换为报告详情对象。"""
        return {
            "file": self.file_name,
            "string_leaf_count": self.string_leaf_count,
            "candidate_count": self.candidate_count,
        }


@dataclass(frozen=True, slots=True)
class NonstandardDataScan:
    """非标准 data 文件风险扫描结果。"""

    files: tuple[NonstandardDataFile, ...]
    file_scans: tuple[NonstandardDataFileScan, ...]
    candidates: tuple[NonstandardDataCandidate, ...]
    leaves_by_file: dict[str, tuple[ResolvedLeaf, ...]] = field(default_factory=dict)

    @property
    def high_risk(self) -> bool:
        """是否存在疑似源语言自然文本。"""
        return bool(self.candidates)

    def summary_json(self) -> JsonObject:
        """生成稳定摘要 JSON。"""
        return {
            "nonstandard_file_count": len(self.files),
            "candidate_count": len(self.candidates),
            "high_risk": self.high_risk,
        }

    def details_json(self) -> JsonObject:
        """生成完整详情 JSON。"""
        return {
            "files": [file_scan.to_json_object() for file_scan in self.file_scans],
            "candidates": [candidate.to_json_object() for candidate in self.candidates],
        }


async def load_nonstandard_data_files(
    *,
    layout: GameLayout,
    source_view: GameFileView,
) -> list[NonstandardDataFile]:
    """从指定游戏文件视图读取第一层非标准 `data/*.json` 文件。"""
    data_dir = resolve_data_source_dir(
        layout=layout,
        use_origin_backups=source_view == GameFileView.TRANSLATION_SOURCE,
        require_origin_backups=source_view == GameFileView.TRANSLATION_SOURCE,
    )
    file_paths = [
        file_path
        for file_path in sorted(data_dir.glob("*.json"), key=lambda path: path.name)
        if file_path.is_file() and not _is_standard_data_file_name(file_path.name)
    ]
    if not file_paths:
        return []
    return list(await asyncio.gather(*(_read_nonstandard_data_file(file_path) for file_path in file_paths)))


async def build_nonstandard_data_scan(
    *,
    layout: GameLayout,
    source_view: GameFileView,
    text_rules: TextRules,
) -> NonstandardDataScan:
    """扫描非标准 data 文件并收集源语言自然文本候选。"""
    files = await load_nonstandard_data_files(layout=layout, source_view=source_view)
    if not files:
        return NonstandardDataScan(files=(), file_scans=(), candidates=(), leaves_by_file={})
    native_result = scan_native_rule_candidates(
        build_native_nonstandard_data_candidates_payload(
            nonstandard_data_files={file.file_name: file.value for file in files},
            text_rules=text_rules,
        )
    )
    return _nonstandard_data_scan_from_native(files=files, native_result=native_result)


def _nonstandard_data_scan_from_native(
    *,
    files: list[NonstandardDataFile],
    native_result: NativeRuleCandidatesResult,
) -> NonstandardDataScan:
    """把 Rust 非标准 data 候选结果还原成当前公开扫描对象。"""
    file_by_name = {file.file_name: file for file in files}
    nonstandard_summary = ensure_json_object(
        native_result.scan_summary["nonstandard_data"],
        "native_rule_candidates_result.scan_summary.nonstandard_data",
    )
    raw_file_summaries = ensure_json_array(
        nonstandard_summary["files"],
        "native_rule_candidates_result.scan_summary.nonstandard_data.files",
    )
    file_scans: list[NonstandardDataFileScan] = []
    leaves_by_file: dict[str, tuple[ResolvedLeaf, ...]] = {}
    seen_file_names: set[str] = set()
    for file_index, raw_file_summary in enumerate(raw_file_summaries):
        label = f"native_rule_candidates_result.scan_summary.nonstandard_data.files[{file_index}]"
        file_summary = ensure_json_object(raw_file_summary, label)
        file_name = _json_str(file_summary, "file", label)
        if file_name not in file_by_name:
            raise RuntimeError(f"Rust 非标准 data 摘要引用了未知文件: {file_name}")
        seen_file_names.add(file_name)
        file_scans.append(
            NonstandardDataFileScan(
                file_name=file_name,
                string_leaf_count=_json_int(file_summary, "string_leaf_count", label),
                candidate_count=_json_int(file_summary, "candidate_count", label),
            )
        )
        raw_leaves = ensure_json_array(file_summary["leaves"], f"{label}.leaves")
        leaves_by_file[file_name] = tuple(
            _resolved_leaf_from_native(
                ensure_json_object(raw_leaf, f"{label}.leaves[{leaf_index}]"),
                f"{label}.leaves[{leaf_index}]",
            )
            for leaf_index, raw_leaf in enumerate(raw_leaves)
        )
    missing_file_names = sorted(set(file_by_name) - seen_file_names)
    if missing_file_names:
        raise RuntimeError(f"Rust 非标准 data 摘要缺少文件: {', '.join(missing_file_names)}")

    candidates = [
        _candidate_from_native(
            ensure_json_object(raw_candidate, f"native_rule_candidates_result.candidates[{candidate_index}]"),
            f"native_rule_candidates_result.candidates[{candidate_index}]",
            file_by_name=file_by_name,
        )
        for candidate_index, raw_candidate in enumerate(native_result.candidates)
    ]
    return NonstandardDataScan(
        files=tuple(files),
        file_scans=tuple(file_scans),
        candidates=tuple(candidates),
        leaves_by_file=leaves_by_file,
    )


def resolve_nonstandard_data_file_leaves_native(
    nonstandard_data_files: dict[str, JsonValue],
) -> dict[str, tuple[ResolvedLeaf, ...]]:
    """用 Rust 原生入口展开多个非标准 data 文件叶子。"""
    if not nonstandard_data_files:
        return {}
    native_result = scan_native_rule_candidates(
        build_native_nonstandard_data_leaves_payload(nonstandard_data_files)
    )
    nonstandard_summary = ensure_json_object(
        native_result.scan_summary["nonstandard_data_leaves"],
        "native_rule_candidates_result.scan_summary.nonstandard_data_leaves",
    )
    raw_file_summaries = ensure_json_array(
        nonstandard_summary["files"],
        "native_rule_candidates_result.scan_summary.nonstandard_data_leaves.files",
    )
    leaves_by_file: dict[str, tuple[ResolvedLeaf, ...]] = {}
    for file_index, raw_file_summary in enumerate(raw_file_summaries):
        label = f"native_rule_candidates_result.scan_summary.nonstandard_data_leaves.files[{file_index}]"
        file_summary = ensure_json_object(raw_file_summary, label)
        file_name = _json_str(file_summary, "file", label)
        if file_name not in nonstandard_data_files:
            raise RuntimeError(f"Rust 非标准 data leaves 摘要引用了未知文件: {file_name}")
        raw_leaves = ensure_json_array(file_summary["leaves"], f"{label}.leaves")
        leaves_by_file[file_name] = tuple(
            _resolved_leaf_from_native(
                ensure_json_object(raw_leaf, f"{label}.leaves[{leaf_index}]"),
                f"{label}.leaves[{leaf_index}]",
            )
            for leaf_index, raw_leaf in enumerate(raw_leaves)
        )
    missing_file_names = sorted(set(nonstandard_data_files) - set(leaves_by_file))
    if missing_file_names:
        raise RuntimeError(f"Rust 非标准 data leaves 摘要缺少文件: {', '.join(missing_file_names)}")
    return leaves_by_file


def _candidate_from_native(
    candidate: JsonObject,
    label: str,
    *,
    file_by_name: dict[str, NonstandardDataFile],
) -> NonstandardDataCandidate:
    """读取 Rust 非标准 data 候选对象。"""
    domain = _json_str(candidate, "domain", label)
    if domain != "nonstandard_data":
        raise RuntimeError(f"Rust 非标准 data 扫描返回了未知 domain: {domain}")
    file_name = _json_str(candidate, "file", label)
    if file_name not in file_by_name:
        raise RuntimeError(f"Rust 非标准 data 候选引用了未知文件: {file_name}")
    return NonstandardDataCandidate(
        file_name=file_name,
        json_path=_json_str(candidate, "json_path", label),
        source_text=_json_str(candidate, "source_text", label),
        raw_text=_json_str(candidate, "raw_text", label),
        field_name=_json_str(candidate, "field_name", label),
        sibling_field_names=_json_string_tuple(candidate, "sibling_field_names", label),
        parent_object_keys=_json_string_tuple(candidate, "parent_object_keys", label),
    )


def _resolved_leaf_from_native(leaf: JsonObject, label: str) -> ResolvedLeaf:
    """读取 Rust 展开的 JSON 叶子。"""
    value_type = _json_str(leaf, "value_type", label)
    value = leaf["value"]
    if value_type == "string":
        if not isinstance(value, str):
            raise TypeError(f"{label}.value 必须是字符串")
    elif value_type == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeError(f"{label}.value 必须是数字")
    elif value_type == "boolean":
        if not isinstance(value, bool):
            raise TypeError(f"{label}.value 必须是布尔值")
    elif value_type == "null":
        if value is not None:
            raise TypeError(f"{label}.value 必须是 null")
    else:
        raise TypeError(f"{label}.value_type 不支持: {value_type}")
    return ResolvedLeaf(
        path=_json_str(leaf, "path", label),
        value=value,
        value_type=value_type,
        from_json_string=_json_bool(leaf, "from_json_string", label),
    )


async def export_nonstandard_data_workspace(
    *,
    scan: NonstandardDataScan,
    output_dir: Path,
) -> JsonObject:
    """写出 Agent 支线所需的候选报告和原始 JSON 副本。"""
    resolved_output_dir = output_dir.resolve()
    source_dir = resolved_output_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = resolved_output_dir / "candidates.json"
    payload = build_nonstandard_data_candidates_payload(scan)
    async with aiofiles.open(candidates_path, "w", encoding="utf-8") as file:
        _ = await file.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
    for nonstandard_file in scan.files:
        async with aiofiles.open(source_dir / nonstandard_file.file_name, "w", encoding="utf-8") as file:
            _ = await file.write(nonstandard_file.raw_text)
    return {
        "output_dir": str(resolved_output_dir),
        "candidates_path": str(candidates_path),
        "source_dir": str(source_dir),
    }


def build_nonstandard_data_candidates_payload(scan: NonstandardDataScan) -> JsonObject:
    """构造 `nonstandard-data/candidates.json` 的最小事实载荷。"""
    return {
        "source_type": NONSTANDARD_DATA_SOURCE_TYPE,
        "summary": scan.summary_json(),
        "files": [file_scan.to_json_object() for file_scan in scan.file_scans],
        "candidates": [candidate.to_json_object() for candidate in scan.candidates],
    }


def build_nonstandard_data_file_hash(raw_text: str) -> str:
    """计算非标准 data 文件规则绑定用的稳定哈希。"""
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _json_bool(payload: JsonObject, key: str, label: str) -> bool:
    """读取 JSON 布尔字段。"""
    value = payload.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{label}.{key} 必须是布尔值")
    return value


def _json_int(payload: JsonObject, key: str, label: str) -> int:
    """读取 JSON 整数字段。"""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label}.{key} 必须是整数")
    return value


def _json_str(payload: JsonObject, key: str, label: str) -> str:
    """读取 JSON 字符串字段。"""
    value = payload.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{label}.{key} 必须是字符串")
    return value


def _json_string_tuple(payload: JsonObject, key: str, label: str) -> tuple[str, ...]:
    """读取 JSON 字符串数组字段。"""
    values: list[str] = []
    for index, item in enumerate(ensure_json_array(payload[key], f"{label}.{key}")):
        if not isinstance(item, str):
            raise TypeError(f"{label}.{key}[{index}] 必须是字符串")
        values.append(item)
    return tuple(values)


async def _read_nonstandard_data_file(file_path: Path) -> NonstandardDataFile:
    """严格按 UTF-8 读取并解析一个非标准 data JSON 文件。"""
    async with aiofiles.open(file_path, "rb") as file:
        content_bytes = await file.read()
    try:
        raw_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"非标准 data 文件不是 UTF-8 文本: {file_path}") from error
    try:
        decoded_raw = cast(object, json.loads(raw_text))
        value = coerce_json_value(decoded_raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"非标准 data 文件不是合法 JSON: {file_path}") from error
    return NonstandardDataFile(
        file_name=file_path.name,
        path=file_path,
        raw_text=raw_text,
        value=value,
    )


def _is_standard_data_file_name(file_name: str) -> bool:
    """判断是否是 RPG Maker 标准 data JSON 文件。"""
    return file_name in FIXED_FILE_NAMES or MAP_PATTERN.fullmatch(file_name) is not None

__all__ = [
    "NONSTANDARD_DATA_SOURCE_TYPE",
    "NonstandardDataCandidate",
    "NonstandardDataFile",
    "NonstandardDataFileScan",
    "NonstandardDataScan",
    "build_nonstandard_data_candidates_payload",
    "build_nonstandard_data_file_hash",
    "build_nonstandard_data_scan",
    "export_nonstandard_data_workspace",
    "load_nonstandard_data_files",
    "resolve_nonstandard_data_file_leaves_native",
]
