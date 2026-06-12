"""正文翻译运行内去重记录模块。"""

from app.rmmz.schema import ItemType, TranslationItem


type TranslationCacheKey = tuple[str, str | tuple[str, ...], ItemType | None, str | None]


class TranslationCache:
    """单轮正文翻译使用的请求级去重记录。"""

    def __init__(self) -> None:
        """初始化本轮翻译所需的内存容器。"""
        self.seen_keys: set[TranslationCacheKey] = set()
        self.duplicate_items: dict[TranslationCacheKey, list[TranslationItem]] = {}

    def build_cache_key(self, item: TranslationItem) -> TranslationCacheKey:
        """为单个正文条目构造稳定去重键。"""
        if item.translation_dedupe_key:
            return ("dedupe_key", item.translation_dedupe_key, item.item_type, item.role)
        return ("source_fields", tuple(item.original_lines), item.item_type, item.role)

    def remember_or_defer(self, item: TranslationItem) -> bool:
        """记录首条正文或暂存重复正文。"""
        cache_key = self.build_cache_key(item)
        if cache_key not in self.seen_keys:
            self.seen_keys.add(cache_key)
            return True

        self.duplicate_items.setdefault(cache_key, []).append(item)
        return False

    def pop_duplicate_items(self, item: TranslationItem) -> list[TranslationItem]:
        """取出与成功正文同键的全部重复条目。"""
        cache_key = self.build_cache_key(item)
        return self.duplicate_items.pop(cache_key, [])

    def pop_duplicate_items_by_fields(
        self,
        *,
        original_lines: list[str],
        item_type: ItemType,
        role: str | None,
        translation_dedupe_key: str | None = None,
    ) -> list[TranslationItem]:
        """根据正文主键字段取出重复条目。"""
        if translation_dedupe_key:
            cache_key: TranslationCacheKey = ("dedupe_key", translation_dedupe_key, item_type, role)
        else:
            cache_key = ("source_fields", tuple(original_lines), item_type, role)
        return self.duplicate_items.pop(cache_key, [])


__all__: list[str] = ["TranslationCache", "TranslationCacheKey"]
