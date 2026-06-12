"""插件源码文本规则新鲜度检查。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rmmz.schema import GameData, PluginSourceTextRuleRecord
from app.rmmz.text_rules import TextRules

from .models import PluginSourceCandidate, PluginSourceReviewSummary, PluginSourceScan, PluginSourceSelectorFact
from .native_scan import build_native_plugin_source_scan


@dataclass(frozen=True, slots=True)
class StalePluginSourceTextRule:
    """过期插件源码文本规则明细。"""

    file_name: str
    reason: str


@dataclass(frozen=True, slots=True)
class PluginSourceReviewCoverage:
    """插件源码候选被外部审查结果覆盖的统计。"""

    required: bool
    translate_selector_count: int
    excluded_selector_count: int
    reviewed_selector_count: int
    active_candidate_count: int
    unreviewed_candidates: tuple[PluginSourceCandidate, ...]


def filter_fresh_plugin_source_text_rules(
    *,
    game_data: GameData,
    rule_records: list[PluginSourceTextRuleRecord],
    text_rules: TextRules,
    scan: PluginSourceScan | None = None,
) -> tuple[list[PluginSourceTextRuleRecord], list[StalePluginSourceTextRule]]:
    """按当前源码文件、启用状态和 selector 命中筛出仍有效的源码规则。"""
    if not rule_records:
        return [], []
    if scan is None:
        scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    file_scans = {file_scan.file_name: file_scan for file_scan in scan.files}
    fresh_rules: list[PluginSourceTextRuleRecord] = []
    stale_rules: list[StalePluginSourceTextRule] = []
    for record in rule_records:
        syntax_error = scan.syntax_errors.get(record.file_name)
        if syntax_error is not None:
            stale_rules.append(
                StalePluginSourceTextRule(
                    file_name=record.file_name,
                    reason=f"插件源码无法通过 JS AST 解析: {syntax_error}",
                )
            )
            continue
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
        stale_reasons = _stale_plugin_source_selector_reasons(scan=scan, record=record)
        if stale_reasons:
            stale_rules.append(
                StalePluginSourceTextRule(
                    file_name=record.file_name,
                    reason=stale_reasons[0],
                )
            )
            continue
        fresh_rules.append(record)
    return fresh_rules, stale_rules


def collect_plugin_source_review_coverage(
    *,
    scan: PluginSourceScan,
    rule_records: list[PluginSourceTextRuleRecord],
) -> PluginSourceReviewCoverage:
    """按 Rust selector facts 统计插件源码候选是否已被归入翻译或排除。"""
    summary = scan.review_summary
    if summary is not None and _review_summary_matches_records(summary=summary, rule_records=rule_records):
        unreviewed_candidates = _unreviewed_candidates_from_selector_facts(scan)
        return PluginSourceReviewCoverage(
            required=summary.review_required,
            translate_selector_count=summary.translated_selector_count,
            excluded_selector_count=summary.excluded_selector_count,
            reviewed_selector_count=summary.reviewed_selector_count,
            active_candidate_count=summary.active_candidate_count,
            unreviewed_candidates=unreviewed_candidates,
        )

    reviewed_selectors_by_file: dict[str, set[str]] = {}
    translate_selector_count = 0
    excluded_selector_count = 0
    for record in rule_records:
        reviewed_selectors = reviewed_selectors_by_file.setdefault(record.file_name, set())
        reviewed_selectors.update(record.selectors)
        reviewed_selectors.update(record.excluded_selectors)
        translate_selector_count += len(record.selectors)
        excluded_selector_count += len(record.excluded_selectors)

    current_selector_keys = {
        (fact.file_name, fact.selector)
        for fact in scan.selector_facts
        if fact.active and fact.stale_reason is None
    }
    active_candidates = tuple(
        candidate
        for candidate in scan.candidates
        if candidate.active and (candidate.file_name, candidate.selector) in current_selector_keys
    )
    required = scan.risk.high_risk or bool(rule_records)
    if required:
        unreviewed_candidates = tuple(
            candidate
            for candidate in active_candidates
            if candidate.selector not in reviewed_selectors_by_file.get(candidate.file_name, set())
        )
    else:
        unreviewed_candidates = ()
    reviewed_selector_count = translate_selector_count + excluded_selector_count
    return PluginSourceReviewCoverage(
        required=required,
        translate_selector_count=translate_selector_count,
        excluded_selector_count=excluded_selector_count,
        reviewed_selector_count=reviewed_selector_count,
        active_candidate_count=len(active_candidates),
        unreviewed_candidates=unreviewed_candidates,
    )


def _stale_plugin_source_selector_reasons(
    *,
    scan: PluginSourceScan,
    record: PluginSourceTextRuleRecord,
) -> list[str]:
    """返回指定规则在 Rust facts 中的 selector 失效原因。"""
    facts = _selector_facts_by_file(scan).get(record.file_name, {})
    reasons: list[str] = []
    for selector in [*record.selectors, *record.excluded_selectors]:
        fact = facts.get(selector)
        if fact is None:
            reasons.append("插件源码 selector 已无法命中当前 AST 地图")
        elif fact.stale_reason is not None:
            reasons.append(fact.stale_reason.message)
    return reasons


def _selector_facts_by_file(scan: PluginSourceScan) -> dict[str, dict[str, PluginSourceSelectorFact]]:
    """按文件和 selector 整理 Rust selector facts。"""
    facts_by_file: dict[str, dict[str, PluginSourceSelectorFact]] = {}
    for fact in scan.selector_facts:
        facts_by_file.setdefault(fact.file_name, {})[fact.selector] = fact
    return facts_by_file


def _review_summary_matches_records(
    *,
    summary: PluginSourceReviewSummary,
    rule_records: list[PluginSourceTextRuleRecord],
) -> bool:
    """判断当前 scan 的 Rust review summary 是否已包含传入规则。"""
    translated_count = sum(len(record.selectors) for record in rule_records)
    excluded_count = sum(len(record.excluded_selectors) for record in rule_records)
    return (
        summary.translated_selector_count == translated_count
        and summary.excluded_selector_count == excluded_count
        and summary.reviewed_selector_count == translated_count + excluded_count
    )


def _unreviewed_candidates_from_selector_facts(scan: PluginSourceScan) -> tuple[PluginSourceCandidate, ...]:
    """用 Rust filtered selector facts 定位未审查候选明细。"""
    unreviewed_keys = {
        (fact.file_name, fact.selector)
        for fact in scan.selector_facts
        if fact.role == "filtered" and fact.active and fact.stale_reason is None
    }
    return tuple(
        candidate
        for candidate in scan.candidates
        if (candidate.file_name, candidate.selector) in unreviewed_keys
    )


__all__ = [
    "PluginSourceReviewCoverage",
    "StalePluginSourceTextRule",
    "collect_plugin_source_review_coverage",
    "filter_fresh_plugin_source_text_rules",
]
