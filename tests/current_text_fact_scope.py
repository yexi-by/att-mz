"""测试专用的当前 text fact 范围构造器。"""

from __future__ import annotations

from typing import cast

from app.config.schemas import Setting
from app.persistence import TargetGameSession
from app.rmmz.text_rules import TextRules
from app.text_facts import (
    read_current_text_fact_records,
    read_current_text_fact_translation_data_map,
    text_fact_record_to_translation_item,
)
from app.text_index import rebuild_text_index_native_storage
from app.text_scope import TextScopeEntry, TextScopeResult, TextSourceType

_TEXT_SOURCE_TYPES = {
    "standard_data",
    "plugin_parameter",
    "plugin_source",
    "event_command",
    "note_tag",
    "nonstandard_data",
}


async def rebuild_current_text_fact_scope_for_test(
    *,
    session: TargetGameSession,
    setting: Setting,
    text_rules: TextRules,
) -> TextScopeResult:
    """重建当前 索引，并返回测试可消费的最小文本范围。"""
    _ = await rebuild_text_index_native_storage(
        session=session,
        setting=setting,
        text_rules=text_rules,
    )
    return await read_current_text_fact_scope_for_test(session=session)


async def read_current_text_fact_scope_for_test(
    *,
    session: TargetGameSession,
) -> TextScopeResult:
    """从当前 text facts 读取测试可消费的最小文本范围。"""
    translation_data_map = await read_current_text_fact_translation_data_map(session)
    facts = await read_current_text_fact_records(session, limit=None)
    index_records = await session.read_text_index_items_by_paths(
        [fact.location_path for fact in facts]
    )
    index_by_path = {record.location_path: record for record in index_records}
    entries: list[TextScopeEntry] = []
    for fact in facts:
        if fact.source_type not in _TEXT_SOURCE_TYPES:
            raise AssertionError(f"测试 text fact 包含未知来源类型: {fact.source_type}")
        index_record = index_by_path.get(fact.location_path)
        item = text_fact_record_to_translation_item(fact, index_record=index_record)
        can_write_back = index_record.writable if index_record is not None else False
        entries.append(
            TextScopeEntry(
                location_path=fact.location_path,
                source_type=cast(TextSourceType, fact.source_type),
                rule_source=_rule_source_label(fact.source_type),
                item_type=item.item_type,
                original_lines=[line for line in item.original_lines],
                role=item.role,
                enters_translation=True,
                can_save_translation=True,
                can_write_back=can_write_back,
                translated=False,
                cannot_process_reason="" if can_write_back else "当前文本事实不可写回",
            )
        )
    return TextScopeResult(translation_data_map=translation_data_map, entries=entries)


def _rule_source_label(source_type: str) -> str:
    """返回测试 scope 中当前来源对应的规则来源说明。"""
    if source_type == "plugin_parameter":
        return "插件参数规则"
    if source_type == "plugin_source":
        return "插件源码规则"
    if source_type == "event_command":
        return "事件指令规则"
    if source_type == "note_tag":
        return "Note 标签规则"
    if source_type == "nonstandard_data":
        return "非标准 data 文件文本规则"
    return "RPG Maker 标准数据结构"
