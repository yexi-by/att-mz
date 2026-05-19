"""外部文本规则审查状态与输入范围哈希工具。"""

import hashlib
import json
from typing import Literal

from app.plugin_text import build_plugins_file_hash
from app.rmmz.commands import iter_all_commands
from app.rmmz.schema import GameData
from app.rmmz.text_rules import JsonArray, JsonValue

type RuleReviewDomain = Literal["plugin_text", "event_command_text", "note_tag_text"]

PLUGIN_TEXT_RULE_DOMAIN: RuleReviewDomain = "plugin_text"
EVENT_COMMAND_TEXT_RULE_DOMAIN: RuleReviewDomain = "event_command_text"
NOTE_TAG_TEXT_RULE_DOMAIN: RuleReviewDomain = "note_tag_text"


def plugin_rule_scope_hash(game_data: GameData) -> str:
    """计算插件规则空结果审查依赖的当前插件配置哈希。"""
    return build_plugins_file_hash(game_data.plugins_js)


def event_command_rule_scope_hash(game_data: GameData) -> str:
    """计算事件指令规则空结果审查依赖的当前事件指令参数哈希。"""
    command_snapshots: JsonArray = []
    for path, _display_name, command in iter_all_commands(game_data):
        command_snapshots.append(
            {
                "path": [part for part in path],
                "code": command.code,
                "parameters": [parameter for parameter in command.parameters],
            }
        )
    return _stable_json_hash(command_snapshots)


def note_tag_rule_scope_hash(game_data: GameData) -> str:
    """计算 Note 标签规则空结果审查依赖的当前 Note 文本哈希。"""
    notes: JsonArray = []
    for file_name, value in sorted(game_data.data.items()):
        _append_note_values(value=value, path=[file_name], notes=notes)
    return _stable_json_hash(notes)


def _append_note_values(*, value: JsonValue, path: list[str | int], notes: JsonArray) -> None:
    """递归收集 data JSON 中的 Note 字段值。"""
    if isinstance(value, dict):
        for key, child in sorted(value.items()):
            child_path = [*path, key]
            if key == "note" and isinstance(child, str):
                notes.append(
                    {
                        "path": [part for part in child_path],
                        "value": child,
                    }
                )
                continue
            _append_note_values(value=child, path=child_path, notes=notes)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _append_note_values(value=child, path=[*path, index], notes=notes)


def _stable_json_hash(payload: JsonValue) -> str:
    """对 JSON 兼容载荷计算稳定哈希。"""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_rule_review_domain(value: str) -> RuleReviewDomain:
    """校验并收窄数据库中的外部规则审查领域。"""
    if value == PLUGIN_TEXT_RULE_DOMAIN:
        return PLUGIN_TEXT_RULE_DOMAIN
    if value == EVENT_COMMAND_TEXT_RULE_DOMAIN:
        return EVENT_COMMAND_TEXT_RULE_DOMAIN
    if value == NOTE_TAG_TEXT_RULE_DOMAIN:
        return NOTE_TAG_TEXT_RULE_DOMAIN
    raise ValueError(f"未知外部规则审查领域: {value}")


__all__: list[str] = [
    "EVENT_COMMAND_TEXT_RULE_DOMAIN",
    "NOTE_TAG_TEXT_RULE_DOMAIN",
    "PLUGIN_TEXT_RULE_DOMAIN",
    "RuleReviewDomain",
    "event_command_rule_scope_hash",
    "note_tag_rule_scope_hash",
    "parse_rule_review_domain",
    "plugin_rule_scope_hash",
]
