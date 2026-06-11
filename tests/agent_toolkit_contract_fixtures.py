"""Agent 工具包业务契约测试夹具。"""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json

import shutil

from collections.abc import Sequence

from pathlib import Path

from types import SimpleNamespace

from typing import NoReturn, cast, override

import pytest

from app.agent_toolkit import AgentToolkitService

from app.agent_toolkit.placeholder_scan import (
    count_uncovered_candidates,
    scan_placeholder_candidates as scan_placeholder_candidate_spans,
)

from app.agent_toolkit.reports import AgentReport

from app.application.flow_gate import (
    build_normal_placeholder_coverage_result,
    build_structured_placeholder_coverage_result,
    collect_placeholder_candidate_review_decisions,
    collect_workflow_gate_errors,
    event_command_rule_scope_hash_for_command_codes,
    event_command_rule_scope_hash_for_setting,
    mv_virtual_namebox_rule_scope_hash_for_game_data,
    normal_placeholder_scope_hash,
    note_tag_rule_scope_hash_for_text_rules,
    structured_placeholder_scope_hash,
)

from app.application.handler import TranslationHandler, TranslationRunLimits

from app.application.use_cases.translation_run import TranslationRunState

from app.config import SettingOverrides

from app.config.schemas import Setting, TextRulesSetting

from app.event_command_text import EventCommandTextExtraction

from app.language import SourceLanguage

from app.llm import LLMHandler

from app.native_quality import NativeQualityDetails, collect_native_quality_counts, collect_native_quality_details

from app.persistence import GameRegistry, TargetGameSession
from app.persistence.records import TextFactReadFilter

from app.plugin_text import build_plugin_hash

from app.plugin_source_text import (
    PluginSourceScan,
    build_native_plugin_source_scan,
)

from app.plugin_source_text.scanner import (
    PluginSourceBatchTextScan,
    build_plugin_source_file_hash,
    iter_plugin_source_string_literals,
    scan_plugin_source_runtime_files_text_strict as real_scan_plugin_source_runtime_files_text_strict,
)

from app.plugin_source_text.runtime_mapping import (
    plugin_source_runtime_hash_lines,
    plugin_source_runtime_hash_text,
)

from app.rmmz.control_codes import CustomPlaceholderRule, StructuredPlaceholderRule

from app.rmmz.game_file_view import GameFileView

from app.rmmz.json_types import JsonArray, JsonObject, JsonValue, coerce_json_value, ensure_json_array, ensure_json_object

from app.rmmz.loader import load_active_runtime_game_data, load_game_data_for_view as real_load_game_data_for_view

from app.rmmz.schema import (
    EventCommandParameterFilter,
    EventCommandTextRuleRecord,
    GameData,
    ItemType,
    NoteTagTextRuleRecord,
    MvVirtualNameboxRuleRecord,
    PlaceholderRuleRecord,
    PluginTextRuleRecord,
    PluginSourceRuntimeWriteMapRecord,
    PluginSourceTextRuleRecord,
    SourceResidualRuleRecord,
    StructuredPlaceholderRuleRecord,
    TranslationErrorItem,
    TranslationData,
    TranslationItem,
)

from app.rmmz.text_rules import TextRules

from app.runtime_paths import APP_HOME_ENV_NAME

from app.terminology import TerminologyCategory, TerminologyGlossary, TerminologyRegistry

from app.rule_review import (
    EVENT_COMMAND_TEXT_RULE_DOMAIN,
    NOTE_TAG_TEXT_RULE_DOMAIN,
    PLACEHOLDER_RULE_DOMAIN,
    PLUGIN_TEXT_RULE_DOMAIN,
    STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
    MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
)

from app.text_scope import TextScopeEntry, TextScopeResult

from app.translation import TranslationBatch

from app.text_scope.write_probe import collect_write_back_probe_reasons
from app.text_index import detect_text_index_invalidations, rebuild_text_index_native_storage
from app.text_facts import (
    read_current_text_fact_translation_data_map,
    read_current_text_fact_scope,
    read_current_text_fact_translation_items_by_paths,
    read_writable_text_fact_translation_items,
    text_fact_record_to_translation_item,
)

from app.utils.config_loader_utils import load_setting

ROOT = Path(__file__).resolve().parents[1]

EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"

def example_setting_text_with_absolute_prompt_files() -> str:
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

class _AgentToolkitServiceProbe(AgentToolkitService):
    """暴露测试用公开方法，避免测试直接访问受保护 mixin API。"""

    async def load_translation_source_for_test(
        self,
        session: TargetGameSession,
        *,
        include_plugin_source_files: bool | None = None,
        include_writable_copies: bool | None = None,
    ) -> GameData:
        """调用翻译源加载入口并保留默认参数行为。"""
        if include_plugin_source_files is None and include_writable_copies is None:
            return await self._load_translation_source_game_data(session)
        return await self._load_translation_source_game_data(
            session,
            include_plugin_source_files=include_plugin_source_files or False,
            include_writable_copies=include_writable_copies or False,
        )

def load_json_object(path: Path) -> dict[str, object]:
    """读取测试产物 JSON 对象，并在边界处收窄动态解析结果。"""
    raw_value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    json_object = ensure_json_object(coerce_json_value(raw_value), str(path))
    return {key: value for key, value in json_object.items()}

def load_json_array(path: Path) -> list[object]:
    """读取测试产物 JSON 数组，并在边界处收窄动态解析结果。"""
    raw_value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    json_array = ensure_json_array(coerce_json_value(raw_value), str(path))
    return [item for item in json_array]

async def _rebuild_text_index_for_test(
    service: AgentToolkitService,
    *,
    game_title: str = "テストゲーム",
) -> AgentReport:
    """测试中显式建立 warm index，固定小任务不再隐式全量建范围的契约。"""
    report = await service.rebuild_text_index(game_title=game_title)
    assert report.status == "ok"
    return report

async def make_current_saved_translation_item_for_test(
    session: TargetGameSession,
    *,
    location_path: str,
    translation_lines: Sequence[str],
    original_lines: Sequence[str] | None = None,
    item_type: ItemType | None = None,
    role: str | None = None,
    source_line_paths: Sequence[str] | None = None,
) -> TranslationItem:
    """按当前 text fact 身份构造可写入主译文表的测试译文。"""
    scope = await read_current_text_fact_scope(session)
    records = await session.read_text_facts(
        TextFactReadFilter(scope_key=scope.scope_key, location_paths=[location_path])
    )
    if not records:
        raise AssertionError(f"测试夹具缺少当前 text fact: {location_path}")
    fact = records[0]
    index_records = await session.read_text_index_items_by_paths([fact.location_path])
    if not index_records:
        raise AssertionError(f"测试夹具缺少当前文本索引定位记录: {location_path}")
    item = text_fact_record_to_translation_item(fact, index_record=index_records[0])
    if original_lines is not None:
        item.original_lines = [line for line in original_lines]
    if item_type is not None:
        item.item_type = item_type
    if role is not None:
        item.role = role
    if source_line_paths is not None:
        item.source_line_paths = [path for path in source_line_paths]
    item.translation_lines = [line for line in translation_lines]
    return item

async def make_current_saved_translation_items_for_test(
    session: TargetGameSession,
    *,
    location_paths: Sequence[str],
    translations_by_path: dict[str, Sequence[str]],
) -> list[TranslationItem]:
    """按一组 path 读取当前 text fact，并写入指定译文行。"""
    items = await read_current_text_fact_translation_items_by_paths(session, location_paths)
    for item in items:
        item.translation_lines = [line for line in translations_by_path[item.location_path]]
    return items

async def write_current_translation_items_for_test(
    session: TargetGameSession,
    items: Sequence[TranslationItem],
) -> None:
    """按当前 text fact 身份写入测试译文；缺少当前事实时显式失败。"""
    await _ensure_current_text_index_for_test(session)
    items_to_write = [item for item in items]
    current_items = await _read_current_items_for_test_write(session, items_to_write)
    current_by_path: dict[str, list[TranslationItem]] = {}
    for current_item in current_items:
        current_by_path.setdefault(current_item.location_path, []).append(current_item)
    current_items_to_write: list[TranslationItem] = []
    for item in items_to_write:
        candidates = current_by_path.get(item.location_path, [])
        current_item = _pop_matching_current_test_item(candidates, item)
        if current_item is None:
            raise AssertionError(f"测试夹具缺少当前 text fact: {item.location_path}")
        current_item.translation_lines = [line for line in item.translation_lines]
        current_items_to_write.append(current_item)
    await session.write_translation_items(current_items_to_write)

async def _read_current_items_for_test_write(
    session: TargetGameSession,
    items: Sequence[TranslationItem],
) -> list[TranslationItem]:
    """按测试待写入 path 读取当前 text fact 条目。"""
    return await read_current_text_fact_translation_items_by_paths(
        session,
        [item.location_path for item in items],
    )

async def _ensure_current_text_index_for_test(session: TargetGameSession) -> None:
    """测试写库前确保当前 text fact scope 存在。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
    text_rules = TextRules.from_setting(setting.text_rules)
    invalidations = await detect_text_index_invalidations(session=session, text_rules=text_rules)
    if invalidations:
        _ = await rebuild_text_index_native_storage(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )

def _pop_matching_current_test_item(
    candidates: list[TranslationItem],
    item: TranslationItem,
) -> TranslationItem | None:
    """从同 path 候选中优先取源文一致的当前 text fact 测试项。"""
    if not candidates:
        return None
    for index, candidate in enumerate(candidates):
        if candidate.original_lines == item.original_lines:
            return candidates.pop(index)
    if len(candidates) == 1:
        return candidates.pop()
    return candidates.pop(0)

async def make_writable_current_translation_items_for_test(
    session: TargetGameSession,
    *,
    text_rules: TextRules,
    override_translations_by_path: dict[str, Sequence[str]] | None = None,
) -> list[TranslationItem]:
    """读取当前所有可写 text fact，并生成保留控制符的测试译文。"""
    override_translations = override_translations_by_path or {}
    items = await read_writable_text_fact_translation_items(session)
    for item in items:
        override_lines = override_translations.get(item.location_path)
        item.translation_lines = (
            [line for line in override_lines]
            if override_lines is not None
            else [
                _translated_test_line_preserving_controls(line, text_rules)
                for line in item.original_lines
            ]
        )
    return items

async def insert_invalid_fact_translation_row_for_test(
    session: TargetGameSession,
    *,
    location_path: str,
    item_type: str,
    role: str | None,
    original_lines: Sequence[str],
    source_line_paths: Sequence[str],
    translation_lines: Sequence[str],
    fact_id: str = "tf:invalid-test-row",
    source_fact_raw_hash: str = "invalid-raw-hash",
    source_fact_translatable_hash: str = "invalid-translatable-hash",
) -> None:
    """测试专用：直接插入与当前 text fact 不匹配的无效译文行。"""
    _ = await session.connection.execute(
        """
--sql
            INSERT OR REPLACE INTO translation_items (
                fact_id,
                location_path,
                item_type,
                role,
                original_lines,
                source_line_paths,
                source_fact_raw_hash,
                source_fact_translatable_hash,
                translation_lines
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ;
        """,
        (
            fact_id,
            location_path,
            item_type,
            role,
            json.dumps(list(original_lines), ensure_ascii=False),
            json.dumps(list(source_line_paths), ensure_ascii=False),
            source_fact_raw_hash,
            source_fact_translatable_hash,
            json.dumps(list(translation_lines), ensure_ascii=False),
        ),
    )
    await session.connection.commit()

def _contains_japanese_test_char(text: str) -> bool:
    """判断测试样本文本是否含有日文假名。"""
    return any("\u3040" <= char <= "\u30ff" for char in text)

def _translated_test_line_preserving_controls(line: str, text_rules: TextRules) -> str:
    """生成不含源语言残留且保留原控制符的测试译文。"""
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

def _translated_test_line_preserving_protocol_candidates(line: str, text_rules: TextRules) -> str:
    """生成保留已保护控制符和未覆盖疑似控制符的测试译文。"""
    spans = [
        (span.start_index, span.end_index, span.original)
        for span in text_rules.iter_control_sequence_spans(line)
    ]
    spans.extend(
        (candidate.start_index, candidate.end_index, candidate.original)
        for candidate in text_rules.iter_unprotected_control_sequence_candidates(line)
    )
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected_spans: list[tuple[int, int, str]] = []
    protected_until = -1
    for start_index, end_index, original in spans:
        if start_index < protected_until:
            continue
        selected_spans.append((start_index, end_index, original))
        protected_until = end_index
    if not selected_spans:
        return "测试"

    translated_parts: list[str] = []
    last_end = 0
    visible_text_inserted = False
    for start_index, end_index, original in selected_spans:
        if start_index > last_end and not visible_text_inserted:
            translated_parts.append("测试")
            visible_text_inserted = True
        translated_parts.append(original)
        last_end = end_index
    if last_end < len(line) and not visible_text_inserted:
        translated_parts.append("测试")
        visible_text_inserted = True
    if not visible_text_inserted:
        translated_parts.append("测试")
    return "".join(translated_parts)

def _mv_virtual_namebox_rules_text() -> str:
    """生成测试用 MV 虚拟名字框规则 JSON。"""
    return json.dumps(
        {
            "rules": [
                {
                    "name": "standalone-colon",
                    "pattern": r"^(?P<speaker>案内人)：$",
                    "speaker_group": "speaker",
                    "speaker_policy": "translate",
                    "render_template": "{speaker}：",
                }
            ]
        },
        ensure_ascii=False,
    )

def _broad_mv_angle_namebox_rules_text() -> str:
    """生成会吞掉尖括号候选的测试用 MV 虚拟名字框规则 JSON。"""
    return json.dumps(
        {
            "rules": [
                {
                    "name": "broad-angle",
                    "pattern": r"^<(?P<speaker>[^>\r\n]{1,80})>$",
                    "speaker_group": "speaker",
                    "speaker_policy": "translate",
                    "render_template": "<{speaker}>",
                }
            ]
        },
        ensure_ascii=False,
    )

async def _install_minimal_external_text_rules(
    *,
    registry: GameRegistry,
    game_title: str,
    game_dir: Path,
) -> None:
    """为占位符草稿测试安装三类外部文本规则前置状态。"""
    game_data = await load_active_runtime_game_data(game_dir)
    plugin_name = str(game_data.plugins_js[0].get("name", ""))
    async with await registry.open_game(game_title) as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name=plugin_name,
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[
                        EventCommandParameterFilter(index=0, value=plugin_name),
                        EventCommandParameterFilter(index=1, value="Show"),
                    ],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        await session.replace_rule_review_state(
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            scope_hash=note_tag_rule_scope_hash_for_text_rules(
                game_data=game_data,
                text_rules=TextRules.from_setting(setting.text_rules),
            ),
            reviewed_empty=True,
        )

async def _install_minimal_workflow_gate_prerequisites(
    *,
    registry: GameRegistry,
    game_title: str,
    game_dir: Path,
) -> None:
    """安装与当前占位符测试无关的最小流程前置状态。"""
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title=game_title,
        game_dir=game_dir,
    )
    game_data = await load_active_runtime_game_data(game_dir)
    async with await registry.open_game(game_title) as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        _ = await rebuild_text_index_native_storage(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        translation_data_map = await read_current_text_fact_translation_data_map(session)
        placeholder_coverage = build_normal_placeholder_coverage_result(
            translation_data_map=translation_data_map,
            text_rules=text_rules,
            rule_count=0,
        )
        await session.replace_rule_review_state(
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            scope_hash=placeholder_coverage.scope_hash,
            reviewed_empty=True,
        )
        structured_coverage = build_structured_placeholder_coverage_result(
            translation_data_map=translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=0,
        )
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=structured_coverage.scope_hash,
            reviewed_empty=True,
        )
        if game_data.layout.engine_kind == "mv":
            await session.replace_rule_review_state(
                rule_domain=MV_VIRTUAL_NAMEBOX_RULE_DOMAIN,
                scope_hash=mv_virtual_namebox_rule_scope_hash_for_game_data(game_data),
                reviewed_empty=True,
            )
        await session.clear_text_index()

def _replace_first_common_event_text(game_dir: Path, text: str) -> None:
    """把 fixture 第一个公共事件正文替换为指定文本。"""
    common_events_path = game_dir / "data" / "CommonEvents.json"
    raw_value = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_value), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    text_command = ensure_json_object(commands[1], "CommonEvents.json[1].list[1]")
    parameters = ensure_json_array(text_command["parameters"], "CommonEvents.json[1].list[1].parameters")
    parameters[0] = text
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

def _insert_common_event_texts(game_dir: Path, texts: Sequence[str]) -> None:
    """向 fixture 公共事件插入一组正文指令。"""
    common_events_path = game_dir / "data" / "CommonEvents.json"
    raw_value = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_value), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands[1:1] = [{"code": 401, "parameters": [text]} for text in texts]
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

__all__ = (
    "json",
    "shutil",
    "Sequence",
    "Path",
    "SimpleNamespace",
    "NoReturn",
    "cast",
    "override",
    "pytest",
    "AgentToolkitService",
    "count_uncovered_candidates",
    "scan_placeholder_candidate_spans",
    "AgentReport",
    "build_normal_placeholder_coverage_result",
    "build_structured_placeholder_coverage_result",
    "collect_placeholder_candidate_review_decisions",
    "collect_workflow_gate_errors",
    "event_command_rule_scope_hash_for_command_codes",
    "event_command_rule_scope_hash_for_setting",
    "mv_virtual_namebox_rule_scope_hash_for_game_data",
    "normal_placeholder_scope_hash",
    "note_tag_rule_scope_hash_for_text_rules",
    "structured_placeholder_scope_hash",
    "TranslationHandler",
    "TranslationRunLimits",
    "TranslationRunState",
    "SettingOverrides",
    "Setting",
    "TextRulesSetting",
    "EventCommandTextExtraction",
    "SourceLanguage",
    "LLMHandler",
    "NativeQualityDetails",
    "collect_native_quality_counts",
    "collect_native_quality_details",
    "GameRegistry",
    "TargetGameSession",
    "build_plugin_hash",
    "PluginSourceBatchTextScan",
    "PluginSourceScan",
    "build_native_plugin_source_scan",
    "build_plugin_source_file_hash",
    "iter_plugin_source_string_literals",
    "real_scan_plugin_source_runtime_files_text_strict",
    "plugin_source_runtime_hash_lines",
    "plugin_source_runtime_hash_text",
    "CustomPlaceholderRule",
    "StructuredPlaceholderRule",
    "GameFileView",
    "JsonArray",
    "JsonObject",
    "JsonValue",
    "coerce_json_value",
    "ensure_json_array",
    "ensure_json_object",
    "load_active_runtime_game_data",
    "real_load_game_data_for_view",
    "EventCommandParameterFilter",
    "EventCommandTextRuleRecord",
    "GameData",
    "NoteTagTextRuleRecord",
    "MvVirtualNameboxRuleRecord",
    "PlaceholderRuleRecord",
    "PluginTextRuleRecord",
    "PluginSourceRuntimeWriteMapRecord",
    "PluginSourceTextRuleRecord",
    "SourceResidualRuleRecord",
    "StructuredPlaceholderRuleRecord",
    "TranslationErrorItem",
    "TranslationData",
    "TranslationItem",
    "TextRules",
    "APP_HOME_ENV_NAME",
    "TerminologyCategory",
    "TerminologyGlossary",
    "TerminologyRegistry",
    "EVENT_COMMAND_TEXT_RULE_DOMAIN",
    "NOTE_TAG_TEXT_RULE_DOMAIN",
    "PLACEHOLDER_RULE_DOMAIN",
    "PLUGIN_TEXT_RULE_DOMAIN",
    "STRUCTURED_PLACEHOLDER_RULE_DOMAIN",
    "MV_VIRTUAL_NAMEBOX_RULE_DOMAIN",
    "TextScopeEntry",
    "TextScopeResult",
    "TranslationBatch",
    "collect_write_back_probe_reasons",
    "load_setting",
    "ROOT",
    "EXAMPLE_SETTING_PATH",
    "example_setting_text_with_absolute_prompt_files",
    "_AgentToolkitServiceProbe",
    "load_json_object",
    "load_json_array",
    "_rebuild_text_index_for_test",
    "make_current_saved_translation_item_for_test",
    "make_current_saved_translation_items_for_test",
    "write_current_translation_items_for_test",
    "make_writable_current_translation_items_for_test",
    "insert_invalid_fact_translation_row_for_test",
    "_contains_japanese_test_char",
    "_translated_test_line_preserving_controls",
    "_translated_test_line_preserving_protocol_candidates",
    "_mv_virtual_namebox_rules_text",
    "_broad_mv_angle_namebox_rules_text",
    "_install_minimal_external_text_rules",
    "_install_minimal_workflow_gate_prerequisites",
    "_replace_first_common_event_text",
    "_insert_common_event_texts",
)
