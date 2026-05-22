"""插件源码文本规则新鲜度检查。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rmmz.schema import GameData, PluginSourceTextRuleRecord
from app.rmmz.text_rules import TextRules

from .models import PluginSourceScan
from .scanner import build_plugin_source_scan


@dataclass(frozen=True, slots=True)
class StalePluginSourceTextRule:
    """过期插件源码文本规则明细。"""

    file_name: str
    reason: str


def filter_fresh_plugin_source_text_rules(
    *,
    game_data: GameData,
    rule_records: list[PluginSourceTextRuleRecord],
    text_rules: TextRules,
    scan: PluginSourceScan | None = None,
) -> tuple[list[PluginSourceTextRuleRecord], list[StalePluginSourceTextRule]]:
    """按当前源码文件、启用状态、文件哈希和 selector 命中筛出仍有效的源码规则。"""
    if not rule_records:
        return [], []
    if scan is None:
        scan = build_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    file_scans = {file_scan.file_name: file_scan for file_scan in scan.files}
    fresh_rules: list[PluginSourceTextRuleRecord] = []
    stale_rules: list[StalePluginSourceTextRule] = []
    for record in rule_records:
        file_scan = file_scans.get(record.file_name)
        if file_scan is None:
            stale_rules.append(
                StalePluginSourceTextRule(
                    file_name=record.file_name,
                    reason="插件源码文件不存在或不是 js/plugins 直接文件",
                )
            )
            continue
        if not file_scan.active:
            stale_rules.append(
                StalePluginSourceTextRule(
                    file_name=record.file_name,
                    reason="插件源码文件未在 plugins.js 中启用",
                )
            )
            continue
        if file_scan.file_hash != record.file_hash:
            stale_rules.append(
                StalePluginSourceTextRule(
                    file_name=record.file_name,
                    reason="插件源码文件内容已经变化，规则哈希不匹配",
                )
            )
            continue
        available_selectors = {candidate.selector for candidate in file_scan.candidates}
        missing_selectors = [selector for selector in record.selectors if selector not in available_selectors]
        if missing_selectors:
            stale_rules.append(
                StalePluginSourceTextRule(
                    file_name=record.file_name,
                    reason="插件源码 selector 已无法命中当前 AST 地图",
                )
            )
            continue
        fresh_rules.append(record)
    return fresh_rules, stale_rules


__all__ = [
    "StalePluginSourceTextRule",
    "filter_fresh_plugin_source_text_rules",
]
