"""Agent 规则命中与当前 v2 fact 身份的解析。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.persistence.records import TextFactV2ReadFilter, TextFactV2Record
from app.rmmz.schema import TranslationItem

if TYPE_CHECKING:
    from app.persistence import TargetGameSession


@dataclass(frozen=True, slots=True)
class RuleFactProbe:
    """规则扫描命中中可用于解析当前 v2 fact 的最小信息。"""

    domain: str
    location_path: str
    translatable_text: str


@dataclass(frozen=True, slots=True)
class RuleFactHit:
    """已解析到当前 v2 fact 的规则命中。"""

    fact_id: str
    location_path: str
    sample_text: str


def require_translation_fact_ids(items: Iterable[TranslationItem]) -> set[str]:
    """读取已保存译文 fact_id；缺失说明旧形状混入当前流程。"""
    fact_ids: set[str] = set()
    for item in items:
        if not item.fact_id:
            raise ValueError(f"已保存译文缺少 fact_id，无法判断当前事实身份: {item.location_path}")
        fact_ids.add(item.fact_id)
    return fact_ids


def count_translated_rule_hits(hits: Iterable[RuleFactHit], translated_fact_ids: set[str]) -> int:
    """按 fact_id 计算规则命中中已经成功保存译文的数量。"""
    return sum(1 for hit in hits if hit.fact_id in translated_fact_ids)


def stale_translation_fact_ids(
    *,
    old_items: Sequence[TranslationItem],
    current_rule_hits: Sequence[RuleFactHit],
) -> list[str]:
    """计算规则变更后需要删除的旧译文 fact_id。"""
    old_fact_ids = require_translation_fact_ids(old_items)
    current_fact_ids = {hit.fact_id for hit in current_rule_hits}
    return sorted(old_fact_ids - current_fact_ids)


def _translation_item_translatable_text(item: TranslationItem) -> str:
    """读取规则命中 TranslationItem 对应的单条可翻译文本。"""
    if item.item_type in {"long_text", "array"}:
        return "\n".join(item.original_lines)
    if not item.original_lines:
        return ""
    return item.original_lines[0]


async def resolve_current_rule_translation_items(
    session: TargetGameSession,
    *,
    domain: str,
    items: Sequence[TranslationItem],
) -> list[TranslationItem]:
    """把规则命中 TranslationItem 回填当前 v2 fact_id；未解析项保留为未翻译。"""
    probes = [
        RuleFactProbe(
            domain=domain,
            location_path=item.location_path,
            translatable_text=_translation_item_translatable_text(item),
        )
        for item in items
    ]
    rule_fact_hits = await resolve_current_rule_fact_hits(session, probes)
    resolved_by_probe = {
        (hit.location_path, hit.sample_text): hit.fact_id
        for hit in rule_fact_hits
    }
    return [
        item.model_copy(
            update={
                "fact_id": resolved_by_probe.get(
                    (item.location_path, _translation_item_translatable_text(item))
                )
            }
        )
        for item in items
    ]


async def resolve_current_rule_fact_hits(
    session: TargetGameSession,
    probes: Sequence[RuleFactProbe],
) -> list[RuleFactHit]:
    """把规则命中解析到当前 v2 facts；未解析命中不冒充已翻译。"""
    if not probes:
        return []
    location_paths = sorted({probe.location_path for probe in probes})
    facts = await session.read_text_facts_v2(TextFactV2ReadFilter(location_paths=location_paths))
    facts_by_key: dict[tuple[str, str, str], list[TextFactV2Record]] = {}
    for fact in facts:
        key = (fact.domain, fact.location_path, fact.translatable_text)
        facts_by_key.setdefault(key, []).append(fact)
    hits: list[RuleFactHit] = []
    for probe in probes:
        key = (probe.domain, probe.location_path, probe.translatable_text)
        matched = facts_by_key.get(key, [])
        if len(matched) > 1:
            raise ValueError(f"当前规则命中解析到多个 v2 fact: {probe.location_path}")
        if not matched:
            continue
        if len(matched) == 1:
            fact = matched[0]
            hits.append(
                RuleFactHit(
                    fact_id=fact.fact_id,
                    location_path=fact.location_path,
                    sample_text=fact.translatable_text,
                )
            )
    return hits
