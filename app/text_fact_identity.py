"""Text Fact v2 翻译身份辅助函数。"""

from collections.abc import Iterable

from app.persistence.records import TextFactV2Record
from app.rmmz.schema import TranslationItem

type TranslationFactIdentity = tuple[str, str, str]


def translation_item_fact_identity(
    item: TranslationItem,
    *,
    label: str,
) -> TranslationFactIdentity:
    """读取 `fact_id + raw_hash + translatable_hash` 完整事实身份。"""
    if not item.fact_id or not item.source_fact_raw_hash or not item.source_fact_translatable_hash:
        raise ValueError(f"{label}缺少 v2 fact identity，无法判断当前事实身份: {item.location_path}")
    return item.fact_id, item.source_fact_raw_hash, item.source_fact_translatable_hash


def text_fact_record_identity(fact: TextFactV2Record) -> TranslationFactIdentity:
    """读取当前 v2 fact 的完整翻译事实身份。"""
    if not fact.fact_id or not fact.raw_hash or not fact.translatable_hash:
        raise ValueError(f"当前 v2 fact 缺少完整 identity，无法判断当前事实身份: {fact.location_path}")
    return fact.fact_id, fact.raw_hash, fact.translatable_hash


def require_translation_fact_identities(
    items: Iterable[TranslationItem],
    *,
    label: str = "已保存译文",
) -> set[TranslationFactIdentity]:
    """读取译文条目的完整 v2 fact identity 集合。"""
    return {
        translation_item_fact_identity(item, label=label)
        for item in items
    }
