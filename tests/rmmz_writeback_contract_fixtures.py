"""RPG Maker 数据加载、可信源和写回业务契约测试夹具。"""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json

import shutil

from pathlib import Path

from types import SimpleNamespace

from typing import NoReturn, cast

import pytest

from app.application.handler import TranslationHandler

from app.application.errors import WriteBackGateError

from app.application.summaries import WriteBackSummary

from app.application.write_plan_applier import RuntimeWritePlan, WritePlanApplier

from app.application.flow_gate import note_tag_rule_scope_hash_for_text_rules, structured_placeholder_scope_hash

from app.application.flow_gate import event_command_rule_scope_hash_for_setting

from app.application.font_replacement import (
    read_plugins_js_file,
    restore_font_references_from_origin_backups,
)

from app.config import SettingOverrides

from app.config.schemas import Setting, TextRulesSetting, WriteBackSetting

from app.note_tag_text import NoteTagTextExtraction, build_note_tag_rule_records_from_import

from app.note_tag_text.exporter import collect_note_tag_candidates

from app.llm import LLMHandler

from app.native_write_plan import NativePlannedFile, NativeWriteBackPlan, NativeWriteBackSummary

from app.persistence import GameRegistry, TargetGameSession

from app.plugin_text import build_plugin_hash

from app.plugin_source_text import (
    ActiveRuntimePluginSourceAudit,
    ActiveRuntimePluginSourceIssue,
    build_native_plugin_source_scan,
    build_plugin_source_rule_records_from_import,
    parse_plugin_source_rule_import_text,
)

from app.nonstandard_data.runtime_audit import ActiveRuntimeNonstandardDataAudit

from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    plugin_rule_scope_hash,
)

from app.rmmz import (
    DataTextExtraction,
    GameFileView,
    load_active_runtime_game_data,
    load_game_data,
    load_game_data_for_view,
    read_game_title,
    resolve_game_layout,
)

from app.rmmz.control_codes import CustomPlaceholderRule

from app.rmmz.schema import (
    EventCommandParameterFilter,
    EventCommandTextRuleRecord,
    GameData,
    MvVirtualNameboxRuleRecord,
    NoteTagTextRuleRecord,
    NonstandardDataTextRuleRecord,
    PLUGINS_FILE_NAME,
    PlaceholderRuleRecord,
    PluginSourceRuntimeWriteMapRecord,
    PluginTextRuleRecord,
    TranslationErrorItem,
    TranslationItem,
)

from app.rmmz.source_snapshot import create_source_snapshot_for_clean_game, validate_source_snapshot_manifest

from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value, ensure_json_array, ensure_json_object, get_default_text_rules

from app.terminology import TerminologyGlossary, TerminologyRegistry

from app.text_scope import TextScopeService

from app.text_facts import read_current_text_fact_translation_items_by_paths

from app.text_index import rebuild_text_index_native_storage

from app.utils.config_loader_utils import load_setting

from tests._native_write_plan_helper import reset_writable_copies, write_data_text, write_game_files

ROOT = Path(__file__).resolve().parents[1]

EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"

def _example_setting_text_with_absolute_prompt_files() -> str:
    """读取示例配置，并把提示词相对路径改成当前仓库的绝对路径。"""
    return (
        EXAMPLE_SETTING_PATH.read_text(encoding="utf-8")
        .replace(
            'ja = "prompts/text_translation_ja_to_zh_system.md"',
            f'ja = "{(ROOT / "prompts" / "text_translation_ja_to_zh_system.md").as_posix()}"',
        )
        .replace(
            'en = "prompts/text_translation_en_to_zh_system.md"',
            f'en = "{(ROOT / "prompts" / "text_translation_en_to_zh_system.md").as_posix()}"',
        )
    )

def _create_test_source_snapshot(game_dir: Path) -> None:
    """为需要写回协议的测试显式创建注册流程同款可信源快照。"""
    layout = resolve_game_layout(game_dir)
    if (
        layout.data_origin_dir.is_dir()
        and layout.plugins_origin_path.is_file()
        and layout.plugin_source_origin_dir.is_dir()
    ):
        return
    create_source_snapshot_for_clean_game(layout)

def _rewrite_json(path: Path, value: JsonValue) -> None:
    """以 UTF-8 写回测试 JSON。"""
    _ = path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def _read_test_json(path: Path) -> JsonValue:
    """读取测试 JSON 并收窄为项目 JSON 类型。"""
    return coerce_json_value(cast(object, json.loads(path.read_text(encoding="utf-8"))))

def _translated_test_line_preserving_controls(line: str, text_rules: TextRules) -> str:
    """生成测试译文，并保留原文中必须原样保留的控制符。"""
    spans = text_rules.iter_control_sequence_spans(line)
    if not spans:
        return "测试"
    translated_parts: list[str] = []
    last_end = 0
    visible_text_inserted = False
    for span in spans:
        if span.start_index > last_end and not visible_text_inserted:
            translated_parts.append("测试")
            visible_text_inserted = True
        translated_parts.append(span.original)
        last_end = span.end_index
    if last_end < len(line) and not visible_text_inserted:
        translated_parts.append("测试")
    if not visible_text_inserted:
        translated_parts.append("测试")
    return "".join(translated_parts)

def _mv_virtual_namebox_rule_records() -> list[MvVirtualNameboxRuleRecord]:
    """生成测试用 MV 虚拟名字框外部规则。"""
    return [
        MvVirtualNameboxRuleRecord(
            rule_order=0,
            rule_name="quote-inline",
            pattern_text=r"^(?P<speaker>[^\\「（:：<>\r\n]{1,40})\s*(?P<connector>[:：]?「)(?P<body>.*)$",
            speaker_group="speaker",
            body_group="body",
            speaker_policy="translate",
            render_template="{speaker}{connector}{body}",
        ),
        MvVirtualNameboxRuleRecord(
            rule_order=1,
            rule_name="standalone-colon",
            pattern_text=r"^(?P<speaker>[^\\「『【\[\]()（）:：\r\n]{1,40})\s*[:：]\s*$",
            speaker_group="speaker",
            body_group="",
            speaker_policy="translate",
            render_template="{speaker}：",
        ),
        MvVirtualNameboxRuleRecord(
            rule_order=2,
            rule_name="actor-inline",
            pattern_text=r"^(?P<speaker>\\[Nn]\[(?P<actor_id>1)\])(?P<separator>[:：])(?P<body>.*)$",
            speaker_group="speaker",
            body_group="body",
            speaker_policy="actor_name",
            render_template="{speaker}{separator}{body}",
        ),
        MvVirtualNameboxRuleRecord(
            rule_order=3,
            rule_name="yep-inline",
            pattern_text=r"^(?P<command>\\(?:[Nn](?:[CcRr])?|[Rr]))<(?P<speaker>[^>\r\n]{1,80})>(?P<body>.*)$",
            speaker_group="speaker",
            body_group="body",
            speaker_policy="translate",
            render_template="{command}<{speaker}>{body}",
        ),
        MvVirtualNameboxRuleRecord(
            rule_order=4,
            rule_name="angle-standalone",
            pattern_text=r"^<(?P<speaker>[^\\<>\r\n]{1,80})>\s*$",
            speaker_group="speaker",
            body_group="",
            speaker_policy="translate",
            render_template="<{speaker}>",
        ),
        MvVirtualNameboxRuleRecord(
            rule_order=5,
            rule_name="dynamic-angle",
            pattern_text=r"^<(?P<speaker>\\[Nn]\[\d+\])>\s*$",
            speaker_group="speaker",
            body_group="",
            speaker_policy="preserve",
            render_template="<{speaker}>",
        ),
    ]

async def _prepare_write_gate_session(
    *,
    session: TargetGameSession,
    game_dir: Path,
    registry: TerminologyRegistry | None = None,
    glossary: TerminologyGlossary | None = None,
) -> tuple[GameData, Setting, TextRules]:
    """让最小游戏通过写文件前置规则，便于测试特定写入风险。"""
    game_data = await load_game_data(game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
    placeholder_record = PlaceholderRuleRecord(
        pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
        placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
    )
    await session.replace_terminology_bundle(
        registry=registry or TerminologyRegistry(),
        glossary=glossary or TerminologyGlossary(),
    )
    await session.replace_placeholder_rules([placeholder_record])
    text_rules = TextRules.from_setting(
        setting.text_rules,
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                pattern_text=placeholder_record.pattern_text,
                placeholder_template=placeholder_record.placeholder_template,
            ),
        ),
        structured_placeholder_rules=(),
    )
    await session.replace_rule_review_state(
        rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
        scope_hash=plugin_rule_scope_hash(game_data),
        reviewed_empty=True,
    )
    await session.replace_rule_review_state(
        rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN,
        scope_hash=event_command_rule_scope_hash_for_setting(
            game_data=game_data,
            setting=setting,
        ),
        reviewed_empty=True,
    )
    await session.replace_rule_review_state(
        rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
        scope_hash=note_tag_rule_scope_hash_for_text_rules(
            game_data=game_data,
            text_rules=text_rules,
        ),
        reviewed_empty=True,
    )
    scope = await TextScopeService().build(
        session=session,
        game_data=game_data,
        text_rules=text_rules,
    )
    await session.replace_rule_review_state(
        rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
        scope_hash=structured_placeholder_scope_hash(
            translation_data_map=scope.translation_data_map,
            structured_rules=(),
        ),
        reviewed_empty=True,
    )
    await session.replace_rule_review_state(
        rule_domain=PLACEHOLDER_RULE_DOMAIN,
        scope_hash="placeholder-rules-imported",
        reviewed_empty=False,
    )
    _ = await rebuild_text_index_native_storage(
        session=session,
        setting=setting,
        text_rules=text_rules,
    )
    return game_data, setting, text_rules

async def write_v2_test_translation_items(
    session: TargetGameSession,
    items: list[TranslationItem],
) -> None:
    """把旧式测试译文映射到当前 v2 fact 身份后写入主译文表。"""
    items_to_migrate = [item for item in items]
    current_items = await read_current_text_fact_translation_items_by_paths(
        session,
        [item.location_path for item in items_to_migrate],
    )
    current_paths = {item.location_path for item in current_items}
    missing_items = [
        item for item in items_to_migrate if item.location_path not in current_paths
    ]
    if missing_items:
        await session.write_translation_items(
            [_generated_stale_v2_test_item(item) for item in missing_items]
        )
        missing_item_ids = {id(item) for item in missing_items}
        items_to_migrate = [
            item for item in items_to_migrate if id(item) not in missing_item_ids
        ]
        if not items_to_migrate:
            return
        current_items = await read_current_text_fact_translation_items_by_paths(
            session,
            [item.location_path for item in items_to_migrate],
        )
    current_by_path: dict[str, list[TranslationItem]] = {}
    for current_item in current_items:
        current_by_path.setdefault(current_item.location_path, []).append(current_item)
    migrated_items: list[TranslationItem] = []
    for item in items_to_migrate:
        current_item = _pop_matching_v2_test_item(
            current_by_path.get(item.location_path, []),
            item,
        )
        if current_item is None:
            raise AssertionError(f"测试夹具缺少当前 v2 fact: {item.location_path}")
        current_item.role = item.role
        current_item.original_lines = [line for line in item.original_lines]
        current_item.source_line_paths = [path for path in item.source_line_paths]
        current_item.translation_lines = [line for line in item.translation_lines]
        migrated_items.append(current_item)
    await session.write_translation_items(migrated_items)

def _generated_stale_v2_test_item(item: TranslationItem) -> TranslationItem:
    """把无当前 fact 的写回测试译文转成显式过期 v2 行。"""
    identity = item.location_path.replace("'", "_")
    return TranslationItem(
        fact_id=f"test-stale-fact:{identity}",
        source_fact_raw_hash=f"test-stale-raw:{identity}",
        source_fact_translatable_hash=f"test-stale-translatable:{identity}",
        location_path=item.location_path,
        item_type=item.item_type,
        role=item.role,
        original_lines=[line for line in item.original_lines],
        source_line_paths=[path for path in item.source_line_paths],
        translation_lines=[line for line in item.translation_lines],
    )

def _pop_matching_v2_test_item(
    candidates: list[TranslationItem],
    item: TranslationItem,
) -> TranslationItem | None:
    """从同 path 候选中优先取源文一致的 v2 fact 测试项。"""
    if not candidates:
        return None
    for index, candidate in enumerate(candidates):
        if candidate.original_lines == item.original_lines:
            return candidates.pop(index)
    if len(candidates) == 1:
        return candidates.pop()
    return candidates.pop(0)

class _NativePlanSessionStub:
    """测试 Rust 写回计划应用层协议的会话桩。"""

    game_path: Path
    db_path: Path
    content_root: Path
    runtime_map_replace_count: int
    runtime_map_replace_calls: int
    nonstandard_data_rules: list[NonstandardDataTextRuleRecord]
    runtime_scan_cache_read_calls: int
    runtime_scan_cache_replace_count: int

    def __init__(self, tmp_path: Path) -> None:
        """初始化可满足写回 helper 的最小会话字段。"""
        self.game_path = tmp_path / "game"
        self.db_path = tmp_path / "game.db"
        self.content_root = tmp_path / "game"
        self.content_root.mkdir()
        self.runtime_map_replace_count = 0
        self.runtime_map_replace_calls = 0
        self.nonstandard_data_rules = []
        self.runtime_scan_cache_read_calls = 0
        self.runtime_scan_cache_replace_count = 0
        self.transaction_depth: int = 0

    async def begin_transaction(self) -> None:
        """开始测试写回事务。"""
        self.transaction_depth += 1

    async def commit_transaction(self) -> None:
        """提交测试写回事务。"""
        self.transaction_depth -= 1

    async def rollback_transaction(self) -> None:
        """回滚测试写回事务。"""
        self.transaction_depth = 0

    async def replace_plugin_source_runtime_write_maps(self, records: list[object]) -> None:
        """记录插件源码当前运行映射是否被替换。"""
        self.runtime_map_replace_calls += 1
        self.runtime_map_replace_count = len(records)

    async def replace_font_replacement_records(self, records: list[object]) -> None:
        """测试中不触发字体记录替换。"""
        _ = records

    async def read_nonstandard_data_text_rules(self) -> list[NonstandardDataTextRuleRecord]:
        """测试写回 helper 时没有非标准 data 规则。"""
        return self.nonstandard_data_rules

    async def read_plugin_source_runtime_scan_cache(self) -> list[object]:
        """读取当前运行插件源码 AST 扫描缓存。"""
        self.runtime_scan_cache_read_calls += 1
        return []

    async def replace_plugin_source_runtime_scan_cache(self, records: list[object]) -> None:
        """记录当前运行插件源码 AST 扫描缓存刷新数量。"""
        self.runtime_scan_cache_replace_count = len(records)

__all__ = (
    "json",
    "shutil",
    "Path",
    "SimpleNamespace",
    "NoReturn",
    "cast",
    "pytest",
    "TranslationHandler",
    "WriteBackGateError",
    "WriteBackSummary",
    "RuntimeWritePlan",
    "WritePlanApplier",
    "note_tag_rule_scope_hash_for_text_rules",
    "structured_placeholder_scope_hash",
    "event_command_rule_scope_hash_for_setting",
    "read_plugins_js_file",
    "restore_font_references_from_origin_backups",
    "SettingOverrides",
    "Setting",
    "TextRulesSetting",
    "WriteBackSetting",
    "NoteTagTextExtraction",
    "build_note_tag_rule_records_from_import",
    "collect_note_tag_candidates",
    "LLMHandler",
    "NativePlannedFile",
    "NativeWriteBackPlan",
    "NativeWriteBackSummary",
    "GameRegistry",
    "TargetGameSession",
    "build_plugin_hash",
    "ActiveRuntimePluginSourceAudit",
    "ActiveRuntimePluginSourceIssue",
    "build_native_plugin_source_scan",
    "build_plugin_source_rule_records_from_import",
    "parse_plugin_source_rule_import_text",
    "ActiveRuntimeNonstandardDataAudit",
    "EVENT_COMMAND_TEXT_RULE_DOMAIN",
    "NOTE_TAG_TEXT_RULE_DOMAIN",
    "PLACEHOLDER_RULE_DOMAIN",
    "PLUGIN_TEXT_RULE_DOMAIN",
    "STRUCTURED_PLACEHOLDER_RULE_DOMAIN",
    "plugin_rule_scope_hash",
    "DataTextExtraction",
    "GameFileView",
    "load_active_runtime_game_data",
    "load_game_data",
    "load_game_data_for_view",
    "read_game_title",
    "resolve_game_layout",
    "CustomPlaceholderRule",
    "EventCommandParameterFilter",
    "EventCommandTextRuleRecord",
    "GameData",
    "MvVirtualNameboxRuleRecord",
    "NoteTagTextRuleRecord",
    "NonstandardDataTextRuleRecord",
    "PLUGINS_FILE_NAME",
    "PlaceholderRuleRecord",
    "PluginSourceRuntimeWriteMapRecord",
    "PluginTextRuleRecord",
    "TranslationErrorItem",
    "TranslationItem",
    "create_source_snapshot_for_clean_game",
    "validate_source_snapshot_manifest",
    "JsonValue",
    "TextRules",
    "coerce_json_value",
    "ensure_json_array",
    "ensure_json_object",
    "get_default_text_rules",
    "TerminologyGlossary",
    "TerminologyRegistry",
    "TextScopeService",
    "load_setting",
    "reset_writable_copies",
    "write_data_text",
    "write_game_files",
    "ROOT",
    "EXAMPLE_SETTING_PATH",
    "_example_setting_text_with_absolute_prompt_files",
    "_create_test_source_snapshot",
    "_rewrite_json",
    "_read_test_json",
    "_translated_test_line_preserving_controls",
    "_mv_virtual_namebox_rule_records",
    "_prepare_write_gate_session",
    "write_v2_test_translation_items",
    "_NativePlanSessionStub",
)
