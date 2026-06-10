"""插件源码文本规则导入与校验。"""

from __future__ import annotations

import json
from collections import Counter
from typing import cast

from pydantic import TypeAdapter

from app.rmmz.schema import GameData, PluginSourceTextRuleRecord
from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value

from .models import (
    PluginSourceRuleImportEntry,
    PluginSourceRuleImportFile,
    PluginSourceScan,
    PluginSourceSelectorFact,
)
from .native_scan import build_native_plugin_source_scan
from .scanner import build_plugin_source_file_hash

RULE_IMPORT_ADAPTER: TypeAdapter[list[PluginSourceRuleImportEntry]] = TypeAdapter(
    list[PluginSourceRuleImportEntry]
)


def parse_plugin_source_rule_import_text(text: str) -> PluginSourceRuleImportFile:
    """解析插件源码规则 JSON 文本。"""
    raw_value = cast(object, json.loads(text))
    value = coerce_json_value(raw_value)
    if not isinstance(value, list):
        raise TypeError("插件源码规则顶层必须是数组")
    entries = RULE_IMPORT_ADAPTER.validate_python(value)
    return PluginSourceRuleImportFile(rules=entries)


def build_plugin_source_rule_records_from_import(
    *,
    game_data: GameData,
    import_file: PluginSourceRuleImportFile,
    text_rules: TextRules,
    scan: PluginSourceScan | None = None,
) -> list[PluginSourceTextRuleRecord]:
    """按当前游戏源码校验外部插件源码规则并转换为数据库记录。"""
    if not import_file.rules:
        return []
    if scan is None:
        scan = build_native_plugin_source_scan(
            game_data=game_data,
            text_rules=text_rules,
            rule_records=build_plugin_source_rule_scan_records_from_import(
                game_data=game_data,
                import_file=import_file,
            ),
        )
    file_scans = {file_scan.file_name: file_scan for file_scan in scan.files}
    selector_facts_by_file = _selector_facts_by_file(scan)
    file_names = [entry.file for entry in import_file.rules]
    duplicate_files = sorted(file_name for file_name, count in Counter(file_names).items() if count > 1)
    if duplicate_files:
        raise ValueError(f"插件源码规则文件重复: {'、'.join(duplicate_files)}")

    records: list[PluginSourceTextRuleRecord] = []
    for entry in import_file.rules:
        file_name = _validate_plugin_source_file_name(entry.file)
        syntax_error = scan.syntax_errors.get(file_name)
        if syntax_error is not None:
            raise ValueError(f"插件源码无法通过 JS AST 解析，不能导入规则: {file_name}: {syntax_error}")
        file_scan = file_scans.get(file_name)
        if file_scan is None:
            raise ValueError(f"插件源码文件不存在或不是 js/plugins 直接文件: {file_name}")
        if not file_scan.active:
            raise ValueError(f"插件源码文件未在 plugins.js 中启用，不能导入规则: {file_name}")
        selectors = _validate_selectors(
            file_name=file_name,
            selector_label="selector",
            selectors=entry.selectors,
            selector_facts=selector_facts_by_file.get(file_name, {}),
            allow_empty=True,
        )
        excluded_selectors = _validate_selectors(
            file_name=file_name,
            selector_label="排除 selector",
            selectors=entry.excluded_selectors,
            selector_facts=selector_facts_by_file.get(file_name, {}),
            allow_empty=True,
        )
        overlap_selectors = sorted(set(selectors) & set(excluded_selectors))
        if overlap_selectors:
            raise ValueError(f"插件源码 selector 不能同时翻译和排除: {file_name}: {'、'.join(overlap_selectors[:5])}")
        if not selectors and not excluded_selectors:
            raise ValueError(f"插件源码规则缺少 selector: {file_name}")
        records.append(
            PluginSourceTextRuleRecord(
                file_name=file_name,
                file_hash=build_plugin_source_file_hash(game_data.plugin_source_files[file_name]),
                selectors=selectors,
                excluded_selectors=excluded_selectors,
            )
        )
    return records


def build_plugin_source_rule_scan_records_from_import(
    *,
    game_data: GameData,
    import_file: PluginSourceRuleImportFile,
) -> list[PluginSourceTextRuleRecord]:
    """把导入 JSON 压成 Rust facts 扫描可消费的临时规则。"""
    records: list[PluginSourceTextRuleRecord] = []
    for entry in import_file.rules:
        file_name = _validate_plugin_source_file_name(entry.file)
        source = game_data.plugin_source_files.get(file_name, "")
        records.append(
            PluginSourceTextRuleRecord(
                file_name=file_name,
                file_hash=build_plugin_source_file_hash(source) if source else "",
                selectors=[selector.strip() for selector in entry.selectors if selector.strip()],
                excluded_selectors=[
                    selector.strip() for selector in entry.excluded_selectors if selector.strip()
                ],
            )
        )
    return records


def _selector_facts_by_file(scan: PluginSourceScan) -> dict[str, dict[str, PluginSourceSelectorFact]]:
    """按文件和 selector 整理 Rust selector facts。"""
    facts_by_file: dict[str, dict[str, PluginSourceSelectorFact]] = {}
    for fact in scan.selector_facts:
        file_facts = facts_by_file.setdefault(fact.file_name, {})
        existing = file_facts.get(fact.selector)
        if existing is None or (existing.stale_reason is None and fact.stale_reason is not None):
            file_facts[fact.selector] = fact
    return facts_by_file


def plugin_source_rule_records_to_import_json(records: list[PluginSourceTextRuleRecord]) -> JsonValue:
    """把数据库记录还原为外部可编辑 JSON。"""
    return [
        {
            "file": record.file_name,
            "selectors": [selector for selector in record.selectors],
            "excluded_selectors": [selector for selector in record.excluded_selectors],
        }
        for record in sorted(records, key=lambda item: item.file_name)
    ]


def _validate_plugin_source_file_name(file_name: str) -> str:
    """校验规则中的插件源码文件名只能是直接 `.js` 文件。"""
    normalized_name = file_name.strip()
    if not normalized_name:
        raise ValueError("插件源码文件名不能为空")
    if "/" in normalized_name or "\\" in normalized_name:
        raise ValueError(f"插件源码规则只允许直接文件名: {file_name}")
    if normalized_name in {".", ".."} or not normalized_name.endswith(".js"):
        raise ValueError(f"插件源码规则文件名必须是 .js 文件: {file_name}")
    return normalized_name


def _validate_selectors(
    *,
    file_name: str,
    selector_label: str,
    selectors: list[str],
    selector_facts: dict[str, PluginSourceSelectorFact],
    allow_empty: bool = False,
) -> list[str]:
    """校验 selector 非空、无重复且能命中当前 Rust selector facts。"""
    cleaned_selectors = [selector.strip() for selector in selectors if selector.strip()]
    if not cleaned_selectors and not allow_empty:
        raise ValueError(f"插件源码规则缺少 selector: {file_name}")
    duplicate_selectors = sorted(
        selector for selector, count in Counter(cleaned_selectors).items() if count > 1
    )
    if duplicate_selectors:
        raise ValueError(f"插件源码 {selector_label} 重复: {file_name}: {'、'.join(duplicate_selectors)}")
    stale_messages = [
        f"{selector}: {fact.stale_reason.message}"
        for selector in cleaned_selectors
        if (fact := selector_facts.get(selector)) is not None and fact.stale_reason is not None
    ]
    if stale_messages:
        raise ValueError(f"插件源码 {selector_label} 已过期: {file_name}: {'、'.join(stale_messages[:5])}")
    missing_selectors = sorted(selector for selector in cleaned_selectors if selector not in selector_facts)
    if missing_selectors:
        raise ValueError(f"插件源码 {selector_label} 未命中当前 AST 地图: {file_name}: {'、'.join(missing_selectors[:5])}")
    return cleaned_selectors


__all__ = [
    "build_plugin_source_rule_records_from_import",
    "build_plugin_source_rule_scan_records_from_import",
    "parse_plugin_source_rule_import_text",
    "plugin_source_rule_records_to_import_json",
]
