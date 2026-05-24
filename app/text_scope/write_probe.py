"""统一文本范围服务中的写入可行性探针。"""

from __future__ import annotations

from app.native_quality import collect_native_write_protocol_details
from app.plugin_source_text.write_back import write_plugin_source_text
from app.rmmz.schema import GameData, TranslationItem
from app.rmmz.text_rules import JsonArray

from .models import WriteBackProbeError


def collect_write_back_probe_reasons(
    *,
    game_data: GameData,
    active_items: list[TranslationItem],
) -> dict[str, str]:
    """用真实写入协议探针标记当前文本清单中的不可写条目。"""
    if not active_items:
        return {}
    probe_items = [_build_write_back_probe_item(item) for item in active_items]
    try:
        details = collect_native_write_protocol_details(
            game_data=game_data.data,
            plugins_js=[plugin for plugin in game_data.plugins_js],
            items=probe_items,
        )
    except Exception:
        return _collect_individual_write_back_probe_reasons(
            game_data=game_data,
            probe_items=probe_items,
        )
    reasons = _write_protocol_reasons_by_path(details)
    reasons.update(
        _collect_plugin_source_write_back_probe_reasons(
            game_data=game_data,
            probe_items=probe_items,
        )
    )
    return reasons


def _collect_individual_write_back_probe_reasons(
    *,
    game_data: GameData,
    probe_items: list[TranslationItem],
) -> dict[str, str]:
    """逐条回退检查写入协议，让单个坏路径不会遮住完整清单。"""
    reasons: dict[str, str] = {}
    failure_messages: list[str] = []
    success_count = 0
    for item in probe_items:
        try:
            details = collect_native_write_protocol_details(
                game_data=game_data.data,
                plugins_js=[plugin for plugin in game_data.plugins_js],
                items=[item],
            )
        except Exception as error:
            failure_message = f"{type(error).__name__}: {error}"
            failure_messages.append(failure_message)
            reasons[item.location_path] = f"写入协议探针失败: {failure_message}"
            continue
        success_count += 1
        reasons.update(_write_protocol_reasons_by_path(details))
    if success_count == 0 and failure_messages:
        unique_messages = sorted(set(failure_messages))
        first_message = unique_messages[0]
        if len(unique_messages) == 1:
            raise WriteBackProbeError(f"写入协议探针整体失败: {first_message}")
        raise WriteBackProbeError(
            f"写入协议探针整体失败，出现 {len(unique_messages)} 类错误: {first_message}"
        )
    return reasons


def _collect_plugin_source_write_back_probe_reasons(
    *,
    game_data: GameData,
    probe_items: list[TranslationItem],
) -> dict[str, str]:
    """批量预演插件源码 AST 写回，失败时逐条定位不可写原因。"""
    plugin_source_items = [
        item
        for item in probe_items
        if item.location_path.startswith("js/plugins/")
    ]
    if not plugin_source_items:
        return {}
    reasons: dict[str, str] = {}
    original_writable_files = dict(game_data.writable_plugin_source_files)
    try:
        try:
            _ = write_plugin_source_text(game_data, plugin_source_items)
            return {}
        except Exception:
            game_data.writable_plugin_source_files = dict(original_writable_files)
        for item in plugin_source_items:
            try:
                _ = write_plugin_source_text(game_data, [item])
            except Exception as error:
                reasons[item.location_path] = f"插件源码写回预演失败: {error}"
            finally:
                game_data.writable_plugin_source_files = dict(original_writable_files)
    finally:
        game_data.writable_plugin_source_files = original_writable_files
    return reasons


def _build_write_back_probe_item(item: TranslationItem) -> TranslationItem:
    """生成不依赖模型译文的结构性写入探针条目。"""
    probe_item = item.model_copy(deep=True)
    if item.item_type == "array":
        probe_item.translation_lines = ["回写校验" for _line in item.original_lines]
    else:
        probe_item.translation_lines = ["回写校验"]
    return probe_item


def _write_protocol_reasons_by_path(details: JsonArray) -> dict[str, str]:
    """把写入协议明细压成定位路径到原因的索引。"""
    reasons: dict[str, str] = {}
    for detail in details:
        if not isinstance(detail, dict):
            continue
        location_path = detail.get("location_path")
        if not isinstance(location_path, str):
            continue
        reason_value = detail.get("reason")
        if not isinstance(reason_value, str) or not reason_value.strip():
            reason_value = detail.get("message")
        if not isinstance(reason_value, str) or not reason_value.strip():
            reason_value = "写入协议预演失败"
        reasons[location_path] = reason_value
    return reasons
