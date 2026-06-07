"""翻译去重记录与提示词组装测试。"""

import hashlib

from app.application.use_cases.translation_run import count_translation_items, deduplicate_translation_data
from app.persistence.records import TextFactV2Record
from app.persistence.sql import TEXT_FACT_SCHEMA_VERSION
from app.rmmz.control_codes import REAL_LINE_BREAK_PLACEHOLDER
from app.rmmz.schema import TranslationData, TranslationItem
from app.rmmz.text_rules import get_default_text_rules
from app.text_facts import text_fact_records_to_translation_data_map
from app.translation import TranslationCache, iter_translation_context_batches


def _sha256_text(text: str) -> str:
    """计算测试用 v2 fact 文本 hash。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_text_fact_record(
    *,
    fact_id: str,
    location_path: str,
    raw_text: str,
    visible_text: str,
    translatable_text: str,
    role: str = "Dan",
    item_type: str = "long_text",
) -> TextFactV2Record:
    """构造最小 Text Fact Contract v2 记录。"""
    return TextFactV2Record(
        fact_id=fact_id,
        schema_version=TEXT_FACT_SCHEMA_VERSION,
        domain="mv_virtual_namebox",
        location_path=location_path,
        source_file="Map001.json",
        source_type="event_command",
        item_type=item_type,
        role=role,
        selector=f"selector:{location_path}",
        raw_text=raw_text,
        visible_text=visible_text,
        translatable_text=translatable_text,
        raw_hash=_sha256_text(raw_text),
        visible_hash=_sha256_text(visible_text),
        translatable_hash=_sha256_text(translatable_text),
        scope_key="scope-v2",
    )


def test_translation_cache_deduplicates_and_expands_items() -> None:
    """同轮重复正文只送模一次，成功后可展开重复项用于断点续传写库。"""
    cache = TranslationCache()
    first = TranslationItem(location_path="A/1", item_type="short_text", original_lines=["こんにちは"])
    duplicate = TranslationItem(location_path="B/1", item_type="short_text", original_lines=["こんにちは"])

    assert cache.remember_or_defer(first)
    assert not cache.remember_or_defer(duplicate)
    assert cache.pop_duplicate_items(first) == [duplicate]


def test_text_fact_v2_adapter_uses_translatable_text_and_hash_dedupes_prompt() -> None:
    """v2 fact 送模只使用 translatable_text，并按相同可译正文合并请求。"""
    first = _make_text_fact_record(
        fact_id="fact-1",
        location_path="Map001.json/1/0",
        raw_text=r"\n<Dan:> Hello",
        visible_text=r"\n<Dan:> Hello",
        translatable_text="Hello",
    )
    duplicate = _make_text_fact_record(
        fact_id="fact-2",
        location_path="Map001.json/1/1",
        raw_text=r"\n<Dan:> Hello  ",
        visible_text=r"\n<Dan:> Hello  ",
        translatable_text="Hello",
    )

    translation_data_map = text_fact_records_to_translation_data_map([first, duplicate])
    deduplicated_map = deduplicate_translation_data(
        translation_data_map=translation_data_map,
        translation_cache=TranslationCache(),
    )
    batches = list(
        iter_translation_context_batches(
            translation_data=next(iter(deduplicated_map.values())),
            token_size=100,
            factor=1.0,
            max_command_items=3,
            system_prompt="系统提示",
            text_rules=get_default_text_rules(),
        )
    )
    user_prompt = batches[0].messages[1].text

    assert count_translation_items(translation_data_map) == 2
    assert count_translation_items(deduplicated_map) == 1
    assert batches[0].items[0].original_lines == ["Hello"]
    assert "role: Dan" in user_prompt
    assert "Hello" in user_prompt
    assert r"\n<Dan:>" not in user_prompt
    assert "selector:" not in user_prompt
    assert "Map001.json" not in user_prompt
    assert "location_path" not in user_prompt
    assert "translated_text" not in user_prompt
    assert "位置:" not in user_prompt


def test_text_fact_v2_dedupe_keeps_role_and_item_type_boundaries() -> None:
    """v2 相同可译正文只在同结构和同说话人内去重。"""
    first = _make_text_fact_record(
        fact_id="fact-1",
        location_path="Map001.json/1/0",
        raw_text=r"\n<Dan:> Hello",
        visible_text=r"\n<Dan:> Hello",
        translatable_text="Hello",
        role="Dan",
    )
    same_text_different_role = _make_text_fact_record(
        fact_id="fact-2",
        location_path="Map001.json/1/1",
        raw_text=r"\n<Eve:> Hello",
        visible_text=r"\n<Eve:> Hello",
        translatable_text="Hello",
        role="Eve",
    )
    same_text_different_item_type = _make_text_fact_record(
        fact_id="fact-3",
        location_path="Map001.json/1/2",
        raw_text="Hello",
        visible_text="Hello",
        translatable_text="Hello",
        role="Dan",
        item_type="short_text",
    )

    translation_data_map = text_fact_records_to_translation_data_map(
        [first, same_text_different_role, same_text_different_item_type]
    )
    deduplicated_map = deduplicate_translation_data(
        translation_data_map=translation_data_map,
        translation_cache=TranslationCache(),
    )

    assert count_translation_items(deduplicated_map) == 3


def test_translation_context_prompt_contains_map_and_body_without_terms() -> None:
    """未传入术语表索引时，提示词包含地图名与正文上下文。"""
    data = TranslationData(
        display_name="始まりの町",
        translation_items=[
            TranslationItem(
                location_path="Map001.json/1/0/0",
                item_type="long_text",
                role="村人",
                original_lines=["こんにちは"],
            )
        ],
    )

    batches = list(
        iter_translation_context_batches(
            translation_data=data,
            token_size=100,
            factor=1.0,
            max_command_items=3,
            system_prompt="系统提示",
            text_rules=get_default_text_rules(),
        )
    )
    user_prompt = batches[0].messages[1].text

    assert "术语" not in user_prompt
    assert "源语言" not in user_prompt
    assert "[建议换行数]" not in user_prompt
    assert "[[地图名]]" not in user_prompt
    assert "[[需要翻译的正文]]" not in user_prompt
    assert "# 场景" in user_prompt
    assert "# 正文" in user_prompt
    assert "## 1" in user_prompt
    assert "地图：始まりの町" in user_prompt
    assert batches[0].prompt_ids_by_location_path == {"Map001.json/1/0/0": "1"}
    assert "id: 1" in user_prompt
    assert "Map001.json" not in user_prompt
    assert "location_path" not in user_prompt
    assert "位置:" not in user_prompt
    assert "type: long_text" in user_prompt
    assert "role: 村人" in user_prompt
    assert "こんにちは" in user_prompt


def test_translation_context_keeps_array_output_line_count_hint() -> None:
    """选项数组仍然向模型提供严格输出行数。"""
    data = TranslationData(
        display_name=None,
        translation_items=[
            TranslationItem(
                location_path="Map001.json/1/0/2",
                item_type="array",
                original_lines=["はい", "いいえ"],
            )
        ],
    )

    batches = list(
        iter_translation_context_batches(
            translation_data=data,
            token_size=100,
            factor=1.0,
            max_command_items=3,
            system_prompt="系统提示",
            text_rules=get_default_text_rules(),
        )
    )
    user_prompt = batches[0].messages[1].text

    assert "line_count: 2" in user_prompt


def test_translation_context_resets_prompt_ids_for_each_batch() -> None:
    """每个模型批次独立使用短 ID，不把真实内部位置暴露给模型。"""
    data = TranslationData(
        display_name=None,
        translation_items=[
            TranslationItem(
                location_path="Map001.json/1/0/0",
                item_type="short_text",
                original_lines=["一つ目"],
            ),
            TranslationItem(
                location_path="Map001.json/1/0/1",
                item_type="short_text",
                original_lines=["二つ目"],
            ),
        ],
    )

    batches = list(
        iter_translation_context_batches(
            translation_data=data,
            token_size=1,
            factor=1.0,
            max_command_items=3,
            system_prompt="系统提示",
            text_rules=get_default_text_rules(),
        )
    )

    assert [batch.prompt_ids_by_location_path for batch in batches] == [
        {"Map001.json/1/0/0": "1"},
        {"Map001.json/1/0/1": "1"},
    ]
    assert all("id: 1" in batch.messages[1].text for batch in batches)
    assert all("Map001.json" not in batch.messages[1].text for batch in batches)


def test_short_text_real_line_break_is_hidden_from_prompt() -> None:
    """单字段文本送模前必须把真实换行替换为文本标记。"""
    data = TranslationData(
        display_name=None,
        translation_items=[
            TranslationItem(
                location_path="Items.json/1/description",
                item_type="short_text",
                original_lines=["武器スキル\n\\C[14]敵単体"],
            )
        ],
    )

    batches = list(
        iter_translation_context_batches(
            translation_data=data,
            token_size=100,
            factor=1.0,
            max_command_items=3,
            system_prompt="系统提示",
            text_rules=get_default_text_rules(),
        )
    )
    user_prompt = batches[0].messages[1].text

    assert f"武器スキル{REAL_LINE_BREAK_PLACEHOLDER}[RMMZ_TEXT_COLOR_14]敵単体" in user_prompt
    assert "武器スキル\n[RMMZ_TEXT_COLOR_14]" not in user_prompt
