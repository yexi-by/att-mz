"""非标准 data JSON 扫描与工作区导出。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import aiofiles

from app.plugin_text.paths import ResolvedLeaf, quote_jsonpath_key
from app.rmmz.game_file_view import GameFileView
from app.rmmz.loader import resolve_data_source_dir
from app.rmmz.schema import FIXED_FILE_NAMES, GameLayout, MAP_PATTERN
from app.rmmz.text_protocol import normalize_visible_text_for_extraction
from app.rmmz.text_rules import JsonObject, JsonValue, TextRules, coerce_json_value

NONSTANDARD_DATA_SOURCE_TYPE = "nonstandard-data"
STRUCTURAL_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "id",
        "key",
        "type",
        "icon",
        "image",
        "picture",
        "file",
        "filename",
        "path",
        "enabled",
        "enable",
        "visible",
        "switch",
        "variable",
        "formula",
        "condition",
        "script",
    }
)


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
    file_scans: list[NonstandardDataFileScan] = []
    candidates: list[NonstandardDataCandidate] = []
    leaves_by_file: dict[str, tuple[ResolvedLeaf, ...]] = {}
    for nonstandard_file in files:
        leaves = tuple(resolve_nonstandard_data_leaves(nonstandard_file.value))
        leaves_by_file[nonstandard_file.file_name] = leaves
        file_candidates = [
            candidate
            for candidate in _iter_candidates_from_file(
                nonstandard_file=nonstandard_file,
                text_rules=text_rules,
            )
        ]
        file_scans.append(
            NonstandardDataFileScan(
                file_name=nonstandard_file.file_name,
                string_leaf_count=sum(1 for leaf in leaves if leaf.value_type == "string"),
                candidate_count=len(file_candidates),
            )
        )
        candidates.extend(file_candidates)
    return NonstandardDataScan(
        files=tuple(files),
        file_scans=tuple(file_scans),
        candidates=tuple(candidates),
        leaves_by_file=leaves_by_file,
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


def resolve_nonstandard_data_leaves(value: JsonValue) -> list[ResolvedLeaf]:
    """递归展开普通 JSON 叶子，不解析字符串里的 JSON 容器。"""
    leaves: list[ResolvedLeaf] = []
    _walk_json_value(
        value=value,
        current_path="$",
        leaves=leaves,
    )
    return leaves


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


def _iter_candidates_from_file(
    *,
    nonstandard_file: NonstandardDataFile,
    text_rules: TextRules,
) -> list[NonstandardDataCandidate]:
    """从单个文件提取源语言自然文本候选。"""
    candidates: list[NonstandardDataCandidate] = []
    _walk_candidates(
        file_name=nonstandard_file.file_name,
        value=nonstandard_file.value,
        current_path="$",
        parent_object_keys=(),
        field_name="",
        text_rules=text_rules,
        candidates=candidates,
    )
    return candidates


def _walk_candidates(
    *,
    file_name: str,
    value: JsonValue,
    current_path: str,
    parent_object_keys: tuple[str, ...],
    field_name: str,
    text_rules: TextRules,
    candidates: list[NonstandardDataCandidate],
) -> None:
    """递归扫描源语言自然文本字符串。"""
    if isinstance(value, dict):
        keys = tuple(value.keys())
        for key, child in value.items():
            _walk_candidates(
                file_name=file_name,
                value=child,
                current_path=f"{current_path}[{quote_jsonpath_key(key)}]",
                parent_object_keys=keys,
                field_name=key,
                text_rules=text_rules,
                candidates=candidates,
            )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_candidates(
                file_name=file_name,
                value=child,
                current_path=f"{current_path}[{index}]",
                parent_object_keys=(),
                field_name="",
                text_rules=text_rules,
                candidates=candidates,
            )
        return
    if not isinstance(value, str):
        return
    if _is_structural_nonstandard_string(field_name=field_name, value=value):
        return
    source_text = normalize_visible_text_for_extraction(
        value,
        plain_text_normalizer=text_rules.normalize_extraction_text,
    )
    if not text_rules.should_translate_source_text(source_text):
        return
    sibling_field_names = tuple(
        key
        for key in parent_object_keys
        if key != field_name
    )
    candidates.append(
        NonstandardDataCandidate(
            file_name=file_name,
            json_path=current_path,
            source_text=source_text,
            raw_text=value,
            field_name=field_name,
            sibling_field_names=sibling_field_names,
            parent_object_keys=parent_object_keys,
        )
    )


def _walk_json_value(
    *,
    value: JsonValue,
    current_path: str,
    leaves: list[ResolvedLeaf],
) -> None:
    """递归展开 JSON 叶子。"""
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_json_value(
                value=child,
                current_path=f"{current_path}[{quote_jsonpath_key(key)}]",
                leaves=leaves,
            )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_json_value(value=child, current_path=f"{current_path}[{index}]", leaves=leaves)
        return
    if isinstance(value, str):
        leaves.append(
            ResolvedLeaf(
                path=current_path,
                value=value,
                value_type="string",
                from_json_string=False,
            )
        )
        return
    if isinstance(value, bool):
        leaves.append(
            ResolvedLeaf(
                path=current_path,
                value=value,
                value_type="boolean",
                from_json_string=False,
            )
        )
        return
    if value is None:
        leaves.append(
            ResolvedLeaf(
                path=current_path,
                value=None,
                value_type="null",
                from_json_string=False,
            )
        )
        return
    leaves.append(
        ResolvedLeaf(
            path=current_path,
            value=value,
            value_type="number",
            from_json_string=False,
        )
    )


def _is_standard_data_file_name(file_name: str) -> bool:
    """判断是否是 RPG Maker 标准 data JSON 文件。"""
    return file_name in FIXED_FILE_NAMES or MAP_PATTERN.fullmatch(file_name) is not None


def _is_structural_nonstandard_string(*, field_name: str, value: str) -> bool:
    """按字段语义排除显然不是自然文本的非标准 data 字符串。"""
    normalized_field_name = field_name.strip().lower()
    stripped_value = value.strip()
    lowered_value = stripped_value.lower()
    if normalized_field_name in STRUCTURAL_FIELD_NAMES:
        return True
    if lowered_value in {"true", "false", "null", "undefined"}:
        return True
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", stripped_value):
        return True
    if re.search(r"(?:^|[\\/])(?:img|audio|fonts|icon|js|data)[\\/]", lowered_value):
        return True
    if re.search(r"\.(?:png|jpe?g|webp|gif|ogg|m4a|mp3|wav|webm|json|js|css|html|ttf|otf|woff2?)$", lowered_value):
        return True
    return False


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
    "resolve_nonstandard_data_leaves",
]
