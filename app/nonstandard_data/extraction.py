"""非标准 data 文件文本规则驱动提取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from app.plugin_text.paths import ResolvedLeaf, expand_rule_to_leaf_paths
from app.rmmz.loader import resolve_data_source_dir
from app.rmmz.schema import GameData, NonstandardDataTextRuleRecord, TranslationData, TranslationItem
from app.rmmz.text_protocol import normalize_visible_text_for_extraction
from app.rmmz.text_rules import TextRules, coerce_json_value, get_default_text_rules

from .scanner import (
    NonstandardDataFile,
    build_nonstandard_data_file_hash,
    resolve_nonstandard_data_leaves,
)

NONSTANDARD_DATA_LOCATION_PREFIX = "nonstandard-data"


class NonstandardDataTextExtraction:
    """从已确认非标准 data JSON 路径提取正文文本。"""

    def __init__(
        self,
        game_data: GameData,
        rule_records: list[NonstandardDataTextRuleRecord],
        text_rules: TextRules | None = None,
    ) -> None:
        """初始化非标准 data 文本提取器。"""
        self.game_data: GameData = game_data
        self.rule_records: list[NonstandardDataTextRuleRecord] = rule_records
        self.text_rules: TextRules = text_rules if text_rules is not None else get_default_text_rules()

    def extract_all_text(self) -> dict[str, TranslationData]:
        """按数据库规则提取非标准 data 文件文本。"""
        if not self.rule_records:
            return {}
        files_by_name = self._load_nonstandard_files_by_name()
        result: dict[str, TranslationData] = {}
        for record in self.rule_records:
            if record.skipped or not record.path_templates:
                continue
            nonstandard_file = self._validated_file(record=record, files_by_name=files_by_name)
            items = self._extract_file_items(record=record, nonstandard_file=nonstandard_file)
            if not items:
                continue
            result[nonstandard_data_file_key(record.file_name)] = TranslationData(
                display_name=None,
                translation_items=items,
            )
        return result

    def collect_rule_hits(self) -> list[tuple[str, str]]:
        """展开规则命中的全部字符串叶子，用于统一文本清单诊断。"""
        if not self.rule_records:
            return []
        files_by_name = self._load_nonstandard_files_by_name()
        hits: list[tuple[str, str]] = []
        seen_paths: set[str] = set()
        for record in self.rule_records:
            if record.skipped:
                continue
            nonstandard_file = self._validated_file(record=record, files_by_name=files_by_name)
            resolved_leaves = resolve_nonstandard_data_leaves(nonstandard_file.value)
            string_leaf_map = {
                leaf.path: leaf.value
                for leaf in resolved_leaves
                if leaf.value_type == "string" and isinstance(leaf.value, str)
            }
            for path_template in record.path_templates:
                matched_paths = expand_rule_to_leaf_paths(
                    path_template=path_template,
                    resolved_leaves=resolved_leaves,
                )
                for leaf_path in matched_paths:
                    location_path = nonstandard_data_location_path(
                        file_name=record.file_name,
                        json_path=leaf_path,
                    )
                    if location_path in seen_paths:
                        continue
                    leaf_value = string_leaf_map.get(leaf_path)
                    if leaf_value is None:
                        continue
                    seen_paths.add(location_path)
                    hits.append(
                        (
                            location_path,
                            normalize_visible_text_for_extraction(
                                leaf_value,
                                plain_text_normalizer=self.text_rules.normalize_extraction_text,
                            ),
                        )
                    )
        return hits

    def _load_nonstandard_files_by_name(self) -> dict[str, NonstandardDataFile]:
        """同步读取翻译源视图里的非标准 data 文件。"""
        data_dir = resolve_data_source_dir(
            layout=self.game_data.layout,
            use_origin_backups=True,
            require_origin_backups=True,
        )
        file_names = {record.file_name for record in self.rule_records}
        files: dict[str, NonstandardDataFile] = {}
        for file_name in sorted(file_names):
            path = data_dir / file_name
            files[file_name] = _read_nonstandard_data_file(path)
        return files

    def _validated_file(
        self,
        *,
        record: NonstandardDataTextRuleRecord,
        files_by_name: dict[str, NonstandardDataFile],
    ) -> NonstandardDataFile:
        """确认规则仍然匹配当前翻译源文件。"""
        nonstandard_file = files_by_name.get(record.file_name)
        if nonstandard_file is None:
            raise RuntimeError(f"非标准 data 文件规则已过期: 文件不存在: {record.file_name}")
        current_hash = build_nonstandard_data_file_hash(nonstandard_file.raw_text)
        if current_hash != record.file_hash:
            raise RuntimeError(f"非标准 data 文件规则已过期: 文件 hash 不匹配: {record.file_name}")
        return nonstandard_file

    def _extract_file_items(
        self,
        *,
        record: NonstandardDataTextRuleRecord,
        nonstandard_file: NonstandardDataFile,
    ) -> list[TranslationItem]:
        """提取单个非标准 data 文件的规则命中项。"""
        resolved_leaves = resolve_nonstandard_data_leaves(nonstandard_file.value)
        string_leaf_map = {
            leaf.path: leaf.value
            for leaf in resolved_leaves
            if leaf.value_type == "string" and isinstance(leaf.value, str)
        }
        items: list[TranslationItem] = []
        seen_leaf_paths: set[str] = set()
        for path_template in record.path_templates:
            matched_string_paths = _matched_string_leaf_paths(
                path_template=path_template,
                resolved_leaves=resolved_leaves,
                string_leaf_map=string_leaf_map,
            )
            if not matched_string_paths:
                raise RuntimeError(
                    f"非标准 data 文件规则已过期: {record.file_name} 路径没有命中当前字符串叶子: {path_template}"
                )
            for leaf_path in matched_string_paths:
                if leaf_path in seen_leaf_paths:
                    continue
                seen_leaf_paths.add(leaf_path)
                leaf_value = string_leaf_map[leaf_path]
                normalized_value = normalize_visible_text_for_extraction(
                    leaf_value,
                    plain_text_normalizer=self.text_rules.normalize_extraction_text,
                )
                if not self.text_rules.should_translate_source_text(normalized_value):
                    continue
                items.append(
                    TranslationItem(
                        location_path=nonstandard_data_location_path(
                            file_name=record.file_name,
                            json_path=leaf_path,
                        ),
                        item_type="short_text",
                        original_lines=[normalized_value],
                    )
                )
        return items


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


def _matched_string_leaf_paths(
    *,
    path_template: str,
    resolved_leaves: list[ResolvedLeaf],
    string_leaf_map: dict[str, str],
) -> list[str]:
    """展开路径模板并只保留当前字符串叶子。"""
    return [
        leaf_path
        for leaf_path in expand_rule_to_leaf_paths(
            path_template=path_template,
            resolved_leaves=resolved_leaves,
        )
        if leaf_path in string_leaf_map
    ]


__all__ = [
    "NONSTANDARD_DATA_LOCATION_PREFIX",
    "NonstandardDataTextExtraction",
    "nonstandard_data_file_key",
    "nonstandard_data_location_path",
    "parse_nonstandard_data_location_path",
]
