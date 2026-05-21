"""RPG Maker MV/MZ 标准数据加载、提取与正文回写测试。"""

import json
import shutil
from pathlib import Path
from typing import cast

import pytest

from app.application.file_writer import reset_writable_copies
from app.application.file_writer import write_game_files
from app.application.handler import TranslationHandler
from app.application.flow_gate import note_tag_rule_scope_hash_for_text_rules, structured_placeholder_scope_hash
from app.application.font_replacement import (
    apply_font_replacement,
    read_plugins_js_file,
    restore_font_references_from_origin_backups,
)
from app.config.schemas import TextRulesSetting
from app.note_tag_text import NoteTagTextExtraction, build_note_tag_rule_records_from_import
from app.note_tag_text.exporter import collect_note_tag_candidates
from app.llm import LLMHandler
from app.persistence import GameRegistry
from app.plugin_text import build_plugin_hash
from app.rule_review import NOTE_TAG_TEXT_RULE_DOMAIN, STRUCTURED_PLACEHOLDER_RULE_DOMAIN
from app.rmmz import DataTextExtraction, load_game_data, read_game_title, resolve_game_layout
from app.rmmz.control_codes import CustomPlaceholderRule
from app.rmmz.schema import (
    EventCommandParameterFilter,
    EventCommandTextRuleRecord,
    MvVirtualNameboxRuleRecord,
    NoteTagTextRuleRecord,
    PLUGINS_FILE_NAME,
    PlaceholderRuleRecord,
    PluginTextRuleRecord,
    TranslationErrorItem,
    TranslationItem,
)
from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value, ensure_json_array, ensure_json_object, get_default_text_rules
from app.rmmz.write_back import write_data_text
from app.terminology import TerminologyGlossary, TerminologyRegistry
from app.text_scope import TextScopeService
from app.utils.config_loader_utils import load_setting


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


@pytest.mark.asyncio
async def test_loader_only_keeps_standard_rmmz_data_files(minimal_game_dir: Path) -> None:
    """加载器接收官方 data 文件，并跳过未知插件衍生 JSON。"""
    game_data = await load_game_data(minimal_game_dir)

    assert "UnknownPluginData.json" not in game_data.data
    assert "System.json" in game_data.data
    assert "Map001.json" in game_data.map_data
    assert "Map002.json" in game_data.map_data
    assert game_data.plugins_js[0]["name"] == "TestPlugin"
    assert game_data.plugins_js[1]["name"] == "ComplexPlugin"


@pytest.mark.asyncio
async def test_mv_outer_layout_loads_www_data_and_system_title(minimal_mv_game_dir: Path) -> None:
    """MV 外层目录布局会定位到 www 内容目录，并用 System 标题兜底注册。"""
    layout = resolve_game_layout(minimal_mv_game_dir)
    game_data = await load_game_data(minimal_mv_game_dir)

    assert layout.engine_kind == "mv"
    assert layout.engine_version == "1.6.1"
    assert layout.content_root == minimal_mv_game_dir / "www"
    assert layout.data_dir == minimal_mv_game_dir / "www" / "data"
    assert read_game_title(minimal_mv_game_dir) == "MVテストゲーム"
    assert game_data.layout.engine_kind == "mv"
    assert "Map001.json" in game_data.map_data
    assert game_data.plugins_js[0]["name"] == "MvPlugin"


@pytest.mark.asyncio
async def test_mv_data_extraction_reads_role_from_first_401(
    minimal_mv_game_dir: Path,
) -> None:
    """MV 对话会从首条正文协议提取内部说话人。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.extend(
        [
            {
                "id": 2,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["案内人「こんにちは」"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 3,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["案内人："]},
                    {"code": 401, "parameters": ["次の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 4,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\N[1]:"]},
                    {"code": 401, "parameters": ["役者の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 5,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\n<店員>いらっしゃいませ"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 6,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\n[999]:普通の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 7,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2, "誤った名前"]},
                    {"code": 401, "parameters": ["案内人「第五参数を無視します」"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 8,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["まだやるかい？掛け金はそのままだぜ？（掛け金\\V[48])"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 9,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<案内人>"]},
                    {"code": 401, "parameters": ["独立行の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 10,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\N<店員>大文字制御の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 11,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<\\n[1]>"]},
                    {"code": 401, "parameters": ["動的名の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 12,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["こちらはステラ（1戦目）の回想です。"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 13,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<ステラ><ソフィア>"]},
                    {"code": 401, "parameters": ["複合名の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
        ]
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    mv_namebox_rules = _mv_virtual_namebox_rule_records()
    extracted = DataTextExtraction(
        game_data,
        get_default_text_rules(),
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    ).extract_all_text()
    items_by_path = {
        item.location_path: item
        for data in extracted.values()
        for item in data.translation_items
    }

    assert items_by_path["CommonEvents.json/1/0"].role == "旁白"
    assert items_by_path["CommonEvents.json/2/0"].role == "案内人"
    assert items_by_path["CommonEvents.json/2/0"].original_lines == ["こんにちは」"]
    assert items_by_path["CommonEvents.json/2/0"].source_line_paths == ["CommonEvents.json/2/1"]
    assert items_by_path["CommonEvents.json/3/0"].role == "案内人"
    assert items_by_path["CommonEvents.json/3/0"].original_lines == ["次の本文です"]
    assert items_by_path["CommonEvents.json/3/0"].source_line_paths == ["CommonEvents.json/3/2"]
    assert items_by_path["CommonEvents.json/4/0"].role == "MV勇者"
    assert items_by_path["CommonEvents.json/4/0"].original_lines == ["役者の本文です"]
    assert items_by_path["CommonEvents.json/5/0"].role == "店員"
    assert items_by_path["CommonEvents.json/5/0"].original_lines == ["いらっしゃいませ"]
    assert items_by_path["CommonEvents.json/6/0"].role == "旁白"
    assert items_by_path["CommonEvents.json/6/0"].original_lines == ["\\n[999]:普通の本文です"]
    assert items_by_path["CommonEvents.json/7/0"].role == "案内人"
    assert items_by_path["CommonEvents.json/7/0"].original_lines == ["第五参数を無視します」"]
    assert items_by_path["CommonEvents.json/8/0"].role == "旁白"
    assert items_by_path["CommonEvents.json/8/0"].original_lines == ["まだやるかい？掛け金はそのままだぜ？（掛け金\\V[48])"]
    assert items_by_path["CommonEvents.json/9/0"].role == "案内人"
    assert items_by_path["CommonEvents.json/9/0"].original_lines == ["独立行の本文です"]
    assert items_by_path["CommonEvents.json/9/0"].source_line_paths == ["CommonEvents.json/9/2"]
    assert items_by_path["CommonEvents.json/10/0"].role == "店員"
    assert items_by_path["CommonEvents.json/10/0"].original_lines == ["大文字制御の本文です"]
    assert items_by_path["CommonEvents.json/11/0"].role == "\\n[1]"
    assert items_by_path["CommonEvents.json/11/0"].original_lines == ["動的名の本文です"]
    assert items_by_path["CommonEvents.json/11/0"].source_line_paths == ["CommonEvents.json/11/2"]
    assert items_by_path["CommonEvents.json/12/0"].role == "旁白"
    assert items_by_path["CommonEvents.json/12/0"].original_lines == ["こちらはステラ（1戦目）の回想です。"]
    assert items_by_path["CommonEvents.json/13/0"].role == "旁白"
    assert items_by_path["CommonEvents.json/13/0"].original_lines == ["<ステラ><ソフィア>", "複合名の本文です"]


@pytest.mark.asyncio
async def test_mv_data_extraction_without_virtual_namebox_rules_keeps_401_as_body(
    minimal_mv_game_dir: Path,
) -> None:
    """MV 没有外部规则时不会用内置格式猜测虚拟名字框。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["次の本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )

    assert item.role == "旁白"
    assert item.original_lines == ["案内人：", "次の本文です"]


@pytest.mark.asyncio
async def test_english_visible_401_short_fragment_is_extracted(
    minimal_game_dir: Path,
) -> None:
    """英文 `401` 短断句也是玩家可见正文，不能按协议噪音跳过。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 3,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2, "Adriel"]},
                {"code": 401, "parameters": ["But-"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    text_rules = TextRules.from_setting(
        TextRulesSetting(
            source_text_required_pattern=r"[A-Za-z]+",
            source_text_exclusion_profile="english_protocol_noise",
        )
    )
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, text_rules).extract_all_text()
    items_by_path = {
        item.location_path: item
        for data in extracted.values()
        for item in data.translation_items
    }

    assert items_by_path["CommonEvents.json/3/0"].role == "Adriel"
    assert items_by_path["CommonEvents.json/3/0"].original_lines == ["But-"]
    assert items_by_path["CommonEvents.json/3/0"].source_line_paths == ["CommonEvents.json/3/1"]


@pytest.mark.asyncio
async def test_english_description_with_this_is_extracted(minimal_english_game_dir: Path) -> None:
    """英文说明里的自然语言 this 不能被当作脚本协议噪音过滤。"""
    items_path = minimal_english_game_dir / "data" / "Items.json"
    items = ensure_json_array(_read_test_json(items_path), "Items.json")
    item = ensure_json_object(items[1], "Items[1]")
    item["description"] = "With this rope, you can cross the old bridge."
    _rewrite_json(items_path, items)

    text_rules = TextRules.from_setting(
        TextRulesSetting(
            source_language="en",
            source_text_required_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
            source_text_exclusion_profile="english_protocol_noise",
        )
    )
    game_data = await load_game_data(minimal_english_game_dir)
    extracted = DataTextExtraction(game_data, text_rules).extract_all_text()
    items_by_path = {
        item.location_path: item
        for data in extracted.values()
        for item in data.translation_items
    }

    assert items_by_path["Items.json/1/description"].original_lines == [
        "With this rope, you can cross the old bridge."
    ]


@pytest.mark.asyncio
async def test_write_back_keeps_english_visible_401_short_fragment(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回前过滤不能再次跳过已经保存的英文短断句正文。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 3,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2, "Adriel"]},
                {"code": 401, "parameters": ["But-"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    app_home = tmp_path / "app-home"
    app_home.mkdir()
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "text_translation_ja_to_zh_system.md"
    setting_text = (Path(__file__).resolve().parents[1] / "setting.example.toml").read_text(
        encoding="utf-8"
    )
    setting_text = setting_text.replace(
        'system_prompt_file = "prompts/text_translation_ja_to_zh_system.md"',
        f'system_prompt_file = "{prompt_path.as_posix()}"',
    )
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="en")
    async with await registry.open_game("テストゲーム") as session:
        game_data = await load_game_data(minimal_game_dir)
        placeholder_record = PlaceholderRuleRecord(
            pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[EventCommandParameterFilter(index=0, value="TestPlugin")],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_placeholder_rules([placeholder_record])
        setting = load_setting(source_language=session.source_language)
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
        active_items = scope.active_items()
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=["但是——"]
                    if item.location_path == "CommonEvents.json/3/0"
                    else [
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in active_items
            ]
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        _ = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    written_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    written_commands = ensure_json_array(
        ensure_json_object(written_events[3], "CommonEvents[3]")["list"],
        "CommonEvents[3].list",
    )
    written_line = ensure_json_array(
        ensure_json_object(written_commands[1], "CommonEvents[3].list[1]")["parameters"],
        "CommonEvents[3].list[1].parameters",
    )[0]

    assert written_line == "但是——"


@pytest.mark.asyncio
async def test_direct_write_back_rejects_latest_quality_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接调用业务写回也必须拦截模型翻了但项目检查没通过的译文。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "text_translation_ja_to_zh_system.md"
    setting_text = (Path(__file__).resolve().parents[1] / "setting.example.toml").read_text(
        encoding="utf-8"
    )
    setting_text = setting_text.replace(
        'system_prompt_file = "prompts/text_translation_ja_to_zh_system.md"',
        f'system_prompt_file = "{prompt_path.as_posix()}"',
    )
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data = await load_game_data(minimal_game_dir)
        placeholder_record = PlaceholderRuleRecord(
            pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[EventCommandParameterFilter(index=0, value="TestPlugin")],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_placeholder_rules([placeholder_record])
        setting = load_setting(source_language=session.source_language)
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
        active_items = scope.active_items()
        assert active_items
        failed_item = active_items[0]
        run_record = await session.start_translation_run(
            total_extracted=len(active_items),
            pending_count=1,
            deduplicated_count=1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path=failed_item.location_path,
                    item_type=failed_item.item_type,
                    role=failed_item.role,
                    original_lines=[line for line in failed_item.original_lines],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析模型输出"],
                    model_response="{}",
                )
            ],
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="项目检查没通过"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()


@pytest.mark.asyncio
async def test_direct_write_terminology_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接调用术语写回也必须经过写入前流程检查。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "text_translation_ja_to_zh_system.md"
    setting_text = (Path(__file__).resolve().parents[1] / "setting.example.toml").read_text(
        encoding="utf-8"
    )
    setting_text = setting_text.replace(
        'system_prompt_file = "prompts/text_translation_ja_to_zh_system.md"',
        f'system_prompt_file = "{prompt_path.as_posix()}"',
    )
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="检查没通过"):
            _ = await handler.write_terminology(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()


@pytest.mark.asyncio
async def test_mv_virtual_name_box_write_back_rebuilds_speaker_lines(minimal_mv_game_dir: Path) -> None:
    """MV 写回用术语表译名重建虚拟名字框，正文只写剥离后的对白。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.extend(
        [
            {
                "id": 2,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["案内人："]},
                    {"code": 401, "parameters": ["次の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 3,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["案内人「こんにちは」"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 4,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\n<店員>いらっしゃいませ"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 5,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\N[1]:役者の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 6,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<案内人>"]},
                    {"code": 401, "parameters": ["独立行の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 7,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["\\N<店員>大文字制御の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 8,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<\\n[1]>"]},
                    {"code": 401, "parameters": ["動的名の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
        ]
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    mv_namebox_rules = _mv_virtual_namebox_rule_records()
    extracted = DataTextExtraction(
        game_data,
        get_default_text_rules(),
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    ).extract_all_text()
    items_by_path = {
        item.location_path: item
        for data in extracted.values()
        for item in data.translation_items
    }
    items_by_path["CommonEvents.json/2/0"].translation_lines = ["你好"]
    items_by_path["CommonEvents.json/3/0"].translation_lines = ["你好」"]
    items_by_path["CommonEvents.json/4/0"].translation_lines = ["欢迎光临"]
    items_by_path["CommonEvents.json/5/0"].translation_lines = ["勇者正文"]
    items_by_path["CommonEvents.json/6/0"].translation_lines = ["独立正文"]
    items_by_path["CommonEvents.json/7/0"].translation_lines = ["大写正文"]
    items_by_path["CommonEvents.json/8/0"].translation_lines = ["动态正文"]

    reset_writable_copies(game_data)
    write_data_text(
        game_data,
        [
            items_by_path["CommonEvents.json/2/0"],
            items_by_path["CommonEvents.json/3/0"],
            items_by_path["CommonEvents.json/4/0"],
            items_by_path["CommonEvents.json/5/0"],
            items_by_path["CommonEvents.json/6/0"],
            items_by_path["CommonEvents.json/7/0"],
            items_by_path["CommonEvents.json/8/0"],
        ],
        speaker_name_translations={"案内人": "向导", "店員": "店员", "MV勇者": "勇者"},
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    )

    writable_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    standalone_commands = ensure_json_array(
        ensure_json_object(writable_events[2], "CommonEvents[2]")["list"],
        "CommonEvents[2].list",
    )
    inline_commands = ensure_json_array(
        ensure_json_object(writable_events[3], "CommonEvents[3]")["list"],
        "CommonEvents[3].list",
    )
    yep_commands = ensure_json_array(
        ensure_json_object(writable_events[4], "CommonEvents[4]")["list"],
        "CommonEvents[4].list",
    )
    actor_commands = ensure_json_array(
        ensure_json_object(writable_events[5], "CommonEvents[5]")["list"],
        "CommonEvents[5].list",
    )
    angle_commands = ensure_json_array(
        ensure_json_object(writable_events[6], "CommonEvents[6]")["list"],
        "CommonEvents[6].list",
    )
    upper_commands = ensure_json_array(
        ensure_json_object(writable_events[7], "CommonEvents[7]")["list"],
        "CommonEvents[7].list",
    )
    dynamic_commands = ensure_json_array(
        ensure_json_object(writable_events[8], "CommonEvents[8]")["list"],
        "CommonEvents[8].list",
    )

    assert ensure_json_array(ensure_json_object(standalone_commands[1], "standalone.speaker")["parameters"], "standalone.speaker.parameters")[0] == "向导："
    assert ensure_json_array(ensure_json_object(standalone_commands[2], "standalone.body")["parameters"], "standalone.body.parameters")[0] == "你好"
    assert ensure_json_array(ensure_json_object(inline_commands[1], "inline.speaker")["parameters"], "inline.speaker.parameters")[0] == "向导「你好」"
    assert ensure_json_array(ensure_json_object(yep_commands[1], "yep.speaker")["parameters"], "yep.speaker.parameters")[0] == "\\n<店员>欢迎光临"
    assert ensure_json_array(ensure_json_object(actor_commands[1], "actor.speaker")["parameters"], "actor.speaker.parameters")[0] == "勇者:勇者正文"
    assert ensure_json_array(ensure_json_object(angle_commands[1], "angle.speaker")["parameters"], "angle.speaker.parameters")[0] == "<向导>"
    assert ensure_json_array(ensure_json_object(angle_commands[2], "angle.body")["parameters"], "angle.body.parameters")[0] == "独立正文"
    assert ensure_json_array(ensure_json_object(upper_commands[1], "upper.speaker")["parameters"], "upper.speaker.parameters")[0] == "\\N<店员>大写正文"
    assert ensure_json_array(ensure_json_object(dynamic_commands[1], "dynamic.speaker")["parameters"], "dynamic.speaker.parameters")[0] == "<\\n[1]>"
    assert ensure_json_array(ensure_json_object(dynamic_commands[2], "dynamic.body")["parameters"], "dynamic.body.parameters")[0] == "动态正文"


@pytest.mark.asyncio
async def test_mv_virtual_name_box_write_back_requires_speaker_translation(minimal_mv_game_dir: Path) -> None:
    """MV 虚拟名字框缺少说话人译名时禁止写回。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["次の本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    mv_namebox_rules = _mv_virtual_namebox_rule_records()
    extracted = DataTextExtraction(
        game_data,
        get_default_text_rules(),
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    ).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )
    item.translation_lines = ["你好"]

    reset_writable_copies(game_data)
    with pytest.raises(ValueError) as exc_info:
        write_data_text(
            game_data,
            [item],
            speaker_name_translations={},
            mv_virtual_namebox_rule_records=mv_namebox_rules,
        )
    message = str(exc_info.value)
    assert "缺少术语译名" in message
    assert "文本路径=CommonEvents.json/2/0" in message
    assert "触发路径=CommonEvents.json/2/1" in message
    assert "规则=standalone-colon" in message
    assert "原始匹配=案内人：" in message


@pytest.mark.asyncio
async def test_mv_virtual_name_box_write_back_keeps_dynamic_speaker_without_translation(
    minimal_mv_game_dir: Path,
) -> None:
    """MV 动态名字框控制符写回时原样保留，不要求术语译名。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["<\\n[1]>"]},
                {"code": 401, "parameters": ["動的名の本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    mv_namebox_rules = _mv_virtual_namebox_rule_records()
    extracted = DataTextExtraction(
        game_data,
        get_default_text_rules(),
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    ).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )
    item.translation_lines = ["动态正文"]

    reset_writable_copies(game_data)
    write_data_text(
        game_data,
        [item],
        speaker_name_translations={},
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    )

    writable_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    commands = ensure_json_array(
        ensure_json_object(writable_events[2], "CommonEvents[2]")["list"],
        "CommonEvents[2].list",
    )

    assert ensure_json_array(ensure_json_object(commands[1], "dynamic.speaker")["parameters"], "dynamic.speaker.parameters")[0] == "<\\n[1]>"
    assert ensure_json_array(ensure_json_object(commands[2], "dynamic.body")["parameters"], "dynamic.body.parameters")[0] == "动态正文"


@pytest.mark.asyncio
async def test_mv_virtual_name_box_write_back_rejects_speaker_line_paths_in_body(minimal_mv_game_dir: Path) -> None:
    """MV 译文把独立说话人行当正文时，写回必须提示完整重置。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["次の本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    mv_namebox_rules = _mv_virtual_namebox_rule_records()
    extracted = DataTextExtraction(
        game_data,
        get_default_text_rules(),
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    ).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )
    invalid_item = item.model_copy(deep=True)
    invalid_item.source_line_paths = ["CommonEvents.json/2/1", "CommonEvents.json/2/2"]
    invalid_item.translation_lines = ["向导：", "你好"]

    reset_writable_copies(game_data)
    with pytest.raises(ValueError) as exc_info:
        write_data_text(
            game_data,
            [invalid_item],
            speaker_name_translations={"案内人": "向导"},
            mv_virtual_namebox_rule_records=mv_namebox_rules,
        )
    message = str(exc_info.value)
    assert "当前 MV 译文仍包含说话人行" in message
    assert "文本路径=CommonEvents.json/2/0" in message
    assert "触发路径=CommonEvents.json/2/1" in message


@pytest.mark.asyncio
async def test_mv_virtual_name_box_rule_conflict_reports_text_location(minimal_mv_game_dir: Path) -> None:
    """MV 虚拟名字框规则冲突时报告触发的正文行路径。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["次の本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    game_data = await load_game_data(minimal_mv_game_dir)
    mv_namebox_rules = _mv_virtual_namebox_rule_records()
    extracted = DataTextExtraction(
        game_data,
        get_default_text_rules(),
        mv_virtual_namebox_rule_records=mv_namebox_rules,
    ).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )
    item.translation_lines = ["你好"]
    conflict_rules = [
        *mv_namebox_rules,
        MvVirtualNameboxRuleRecord(
            rule_order=999,
            rule_name="standalone-colon-copy",
            pattern_text=r"^(?P<speaker>[^\\「『【\[\]()（）:：\r\n]{1,40})\s*[:：]\s*$",
            speaker_group="speaker",
            body_group="",
            speaker_policy="translate",
            render_template="{speaker}：",
        ),
    ]

    reset_writable_copies(game_data)
    with pytest.raises(ValueError) as exc_info:
        write_data_text(
            game_data,
            [item],
            speaker_name_translations={"案内人": "向导"},
            mv_virtual_namebox_rule_records=conflict_rules,
        )
    message = str(exc_info.value)
    assert "MV 虚拟名字框规则命中冲突" in message
    assert "文本路径=CommonEvents.json/2/1" in message
    assert "standalone-colon" in message
    assert "standalone-colon-copy" in message


def test_empty_metadata_title_falls_back_to_game_directory_name(minimal_mv_game_dir: Path) -> None:
    """窗口标题和系统标题都为空时，注册标题使用游戏目录名。"""
    package_path = minimal_mv_game_dir / "package.json"
    package_object = ensure_json_object(_read_test_json(package_path), "package.json")
    window_object = ensure_json_object(package_object["window"], "package.window")
    window_object["title"] = ""
    _rewrite_json(package_path, package_object)
    system_path = minimal_mv_game_dir / "www" / "data" / "System.json"
    system_object = ensure_json_object(_read_test_json(system_path), "System.json")
    system_object["gameTitle"] = ""
    _rewrite_json(system_path, system_object)

    assert read_game_title(minimal_mv_game_dir) == minimal_mv_game_dir.name


@pytest.mark.asyncio
async def test_mv_write_back_uses_www_active_and_origin_paths(minimal_mv_game_dir: Path) -> None:
    """MV 外层目录写回只触碰 www 内的 data 和 plugins.js。"""
    game_data = await load_game_data(minimal_mv_game_dir)
    reset_writable_copies(game_data)
    system_object = ensure_json_object(game_data.writable_data["System.json"], "System.json")
    system_object["gameTitle"] = "MV测试游戏"
    game_data.writable_data[PLUGINS_FILE_NAME] = "var $plugins = [];\n"

    write_game_files(game_data, minimal_mv_game_dir)

    assert (minimal_mv_game_dir / "www" / "data_origin" / "System.json").exists()
    assert (minimal_mv_game_dir / "www" / "js" / "plugins_origin.js").exists()
    assert not (minimal_mv_game_dir / "data_origin").exists()
    assert not (minimal_mv_game_dir / "js").exists()
    restored_system = ensure_json_object(
        _read_test_json(minimal_mv_game_dir / "www" / "data_origin" / "System.json"),
        "System.json",
    )
    assert restored_system["gameTitle"] == "MVテストゲーム"


@pytest.mark.asyncio
async def test_data_extraction_covers_core_text_sources(minimal_game_dir: Path) -> None:
    """正文提取覆盖正文文本，并排除术语表直接写回字段。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    paths = {
        item.location_path
        for data in extracted.values()
        for item in data.translation_items
    }

    assert "Map001.json/1/0/0" in paths
    assert "CommonEvents.json/1/0" in paths
    assert "CommonEvents.json/1/2" in paths
    assert "CommonEvents.json/1/3" in paths
    assert "CommonEvents.json/1/4/parameters/3/message" not in paths
    assert "CommonEvents.json/2/0" in paths
    assert "CommonEvents.json/2/4" in paths
    assert "CommonEvents.json/2/5" in paths
    assert "CommonEvents.json/2/8" in paths
    assert "Map001.json/2/0/0" in paths
    assert "Map001.json/2/0/3" in paths
    assert "Map002.json/1/0/0" in paths
    assert "System.json/gameTitle" in paths
    assert "System.json/terms/basic/1" not in paths
    assert "System.json/elements/1" not in paths
    assert "System.json/skillTypes/1" not in paths
    assert "Actors.json/1/name" not in paths
    assert "Actors.json/1/nickname" not in paths
    assert "Actors.json/1/profile" in paths
    assert "Items.json/1/name" not in paths
    assert "Skills.json/1/name" not in paths
    assert "Items.json/1/description" in paths
    assert "Skills.json/1/message1" in paths


@pytest.mark.asyncio
async def test_data_extraction_strips_outer_whitespace_from_core_sources(minimal_game_dir: Path) -> None:
    """标准提取入口保存清理后的玩家可见原文。"""
    system_path = minimal_game_dir / "data" / "System.json"
    system = ensure_json_object(_read_test_json(system_path), "System.json")
    system["gameTitle"] = "　テストゲーム　"
    _rewrite_json(system_path, system)

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents.json[1].list")
    choice_command = ensure_json_object(commands[2], "CommonEvents.json[1].list[2]")
    choice_parameters = ensure_json_array(choice_command["parameters"], "CommonEvents.json[1].list[2].parameters")
    choice_parameters[0] = ["　はい　", " いいえ "]
    _rewrite_json(common_events_path, common_events)

    actors_path = minimal_game_dir / "data" / "Actors.json"
    actors = ensure_json_array(_read_test_json(actors_path), "Actors.json")
    actor = ensure_json_object(actors[1], "Actors.json[1]")
    actor["profile"] = "　プロフィール　"
    _rewrite_json(actors_path, actors)

    items_path = minimal_game_dir / "data" / "Items.json"
    items = ensure_json_array(_read_test_json(items_path), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["description"] = "　体力を回復する。　"
    _rewrite_json(items_path, items)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    items_by_path = {
        item.location_path: item
        for data in extracted.values()
        for item in data.translation_items
    }

    assert items_by_path["System.json/gameTitle"].original_lines == ["テストゲーム"]
    assert items_by_path["CommonEvents.json/1/2"].original_lines == ["はい", "いいえ"]
    assert items_by_path["Actors.json/1/profile"].original_lines == ["プロフィール"]
    assert items_by_path["Items.json/1/description"].original_lines == ["体力を回復する。"]


@pytest.mark.asyncio
async def test_note_tag_rules_extract_and_write_back_only_target_values(minimal_game_dir: Path) -> None:
    """Note 标签只有导入规则后才进入正文提取，回写只替换目标标签值。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目\n二行目>\n<upgrade:1,2,3>\n<ExtendDesc:別説明>"
    _rewrite_json(items_path, raw_items)

    game_data = await load_game_data(minimal_game_dir)
    standard_extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    standard_paths = {
        candidate.location_path
        for data in standard_extracted.values()
        for candidate in data.translation_items
    }
    note_extracted = NoteTagTextExtraction(
        game_data=game_data,
        rule_records=[
            NoteTagTextRuleRecord(
                file_name="Items.json",
                tag_names=["拡張説明", "ExtendDesc"],
            )
        ],
        text_rules=get_default_text_rules(),
    ).extract_all_text()
    note_items = note_extracted["Items.json"].translation_items

    assert "Items.json/1/note/拡張説明" not in standard_paths
    assert [candidate.location_path for candidate in note_items] == [
        "Items.json/1/note/拡張説明",
        "Items.json/1/note/ExtendDesc",
    ]
    assert note_items[0].original_lines == ["一行目\n二行目"]

    note_items[0].translation_lines = ["第一行\n第二行"]
    reset_writable_copies(game_data)
    write_data_text(game_data, [note_items[0]])
    writable_items = ensure_json_array(game_data.writable_data["Items.json"], "Items.json")
    writable_item = ensure_json_object(writable_items[1], "Items.json[1]")

    assert writable_item["note"] == "<拡張説明:第一行\n第二行>\n<upgrade:1,2,3>\n<ExtendDesc:別説明>"


@pytest.mark.asyncio
async def test_note_tag_multiline_value_keeps_line_break_structure_before_write_back(minimal_game_dir: Path) -> None:
    """Note 标签单字段写回不再为了切宽新增换行。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:説明\n「原文」>"
    _rewrite_json(items_path, raw_items)
    text_rules = TextRules.from_setting(
        TextRulesSetting(
            long_text_line_width_limit=8,
            line_split_punctuations=["，", "。"],
        )
    )

    game_data = await load_game_data(minimal_game_dir)
    note_items = NoteTagTextExtraction(
        game_data=game_data,
        rule_records=[
            NoteTagTextRuleRecord(
                file_name="Items.json",
                tag_names=["拡張説明"],
            )
        ],
        text_rules=text_rules,
    ).extract_all_text()["Items.json"].translation_items
    note_items[0].translation_lines = ["说明\n「甲乙丙丁戊己，庚辛壬癸」"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [note_items[0]], text_rules)

    writable_items = ensure_json_array(game_data.writable_data["Items.json"], "Items.json")
    writable_item = ensure_json_object(writable_items[1], "Items.json[1]")
    assert writable_item["note"] == "<拡張説明:说明\n「甲乙丙丁戊己，庚辛壬癸」>"


@pytest.mark.asyncio
async def test_note_tag_json_string_leaf_uses_visible_text_protocol(minimal_game_dir: Path) -> None:
    """Note 标签值如果带 JSON 字符串外壳，只翻玩家可见文本并按原结构写回。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    source_note = "\n　" + r"\C[2]詳細説明\C[0]\n次の行" + "　\n"
    item["note"] = f"<拡張説明:{json.dumps(source_note, ensure_ascii=False)}>\n<upgrade:1,2,3>"
    _rewrite_json(items_path, raw_items)

    game_data = await load_game_data(minimal_game_dir)
    candidates = collect_note_tag_candidates(
        game_data=game_data,
        text_rules=get_default_text_rules(),
    )
    candidate = next(
        ensure_json_object(candidate_value, "note_tag_candidate")
        for candidate_value in candidates
        if isinstance(candidate_value, dict)
        and candidate_value.get("file_name") == "Items.json"
        and candidate_value.get("tag_name") == "拡張説明"
    )
    assert candidate["sample_values"] == [source_note.strip()]

    rule_records = build_note_tag_rule_records_from_import(
        game_data=game_data,
        import_file={"Items.json": ["拡張説明"]},
        text_rules=get_default_text_rules(),
    )
    note_items = NoteTagTextExtraction(
        game_data=game_data,
        rule_records=rule_records,
        text_rules=get_default_text_rules(),
    ).extract_all_text()["Items.json"].translation_items

    assert note_items[0].original_lines == [source_note.strip()]

    translated_note = "\n　" + r"\C[2]详细说明\C[0]\n下一行" + "　\n"
    note_items[0].translation_lines = [translated_note]
    reset_writable_copies(game_data)
    write_data_text(game_data, [note_items[0]])

    writable_items = ensure_json_array(game_data.writable_data["Items.json"], "Items.json")
    writable_item = ensure_json_object(writable_items[1], "Items.json[1]")
    writable_note = writable_item["note"]
    assert isinstance(writable_note, str)
    assert writable_note.endswith("\n<upgrade:1,2,3>")
    tag_value = writable_note.removeprefix("<拡張説明:").split(">", maxsplit=1)[0]
    assert json.loads(tag_value) == translated_note.strip()


@pytest.mark.asyncio
async def test_map_event_note_tag_rules_extract_and_write_back(minimal_game_dir: Path) -> None:
    """Note 标签规则覆盖地图事件 note 字段，并支持 Map*.json 文件模式。"""
    map_path = minimal_game_dir / "data" / "Map001.json"
    raw_map = _read_test_json(map_path)
    map_object = ensure_json_object(raw_map, "Map001.json")
    events = ensure_json_array(map_object["events"], "Map001.json.events")
    event = ensure_json_object(events[2], "Map001.json.events[2]")
    event["note"] = "<namePop:導き手>\n<machine:1>"
    _rewrite_json(map_path, raw_map)

    game_data = await load_game_data(minimal_game_dir)
    candidates = collect_note_tag_candidates(
        game_data=game_data,
        text_rules=get_default_text_rules(),
    )
    name_pop_candidate = next(
        ensure_json_object(candidate_value, "note_tag_candidate")
        for candidate_value in candidates
        if isinstance(candidate_value, dict)
        and candidate_value.get("file_name") == "Map*.json"
        and candidate_value.get("tag_name") == "namePop"
    )
    assert name_pop_candidate["translatable_hit_count"] == 1
    assert name_pop_candidate["sample_locations"] == ["Map001.json/events/2/note/namePop"]

    rule_records = build_note_tag_rule_records_from_import(
        game_data=game_data,
        import_file={"Map*.json": ["namePop"]},
        text_rules=get_default_text_rules(),
    )
    note_items = NoteTagTextExtraction(
        game_data=game_data,
        rule_records=rule_records,
        text_rules=get_default_text_rules(),
    ).extract_all_text()["Map001.json"].translation_items

    assert [item.location_path for item in note_items] == ["Map001.json/events/2/note/namePop"]
    assert note_items[0].original_lines == ["導き手"]

    note_items[0].translation_lines = ["引导者"]
    reset_writable_copies(game_data)
    write_data_text(game_data, [note_items[0]])
    writable_map = ensure_json_object(game_data.writable_data["Map001.json"], "Map001.json")
    writable_events = ensure_json_array(writable_map["events"], "Map001.json.events")
    writable_event = ensure_json_object(writable_events[2], "Map001.json.events[2]")

    assert writable_event["note"] == "<namePop:引导者>\n<machine:1>"


@pytest.mark.asyncio
async def test_fixture_custom_control_sequences_can_be_protected(minimal_game_dir: Path) -> None:
    """测试夹具里的自定义控制符可通过外部规则保护。"""
    text_rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(r"\\F\[[^\]]+\]", "[CUSTOM_FACE_PORTRAIT_{index}]"),
        ),
    )
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, text_rules).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )

    item.build_placeholders(text_rules)

    assert item.original_lines_with_placeholders[0] == "[CUSTOM_FACE_PORTRAIT_1]テスト一行目です。[RMMZ_WAIT_INPUT]"
    assert item.original_lines_with_placeholders[1] == "[RMMZ_TEXT_COLOR_4]重要語[RMMZ_TEXT_COLOR_0]を含む二行目です。"


@pytest.mark.asyncio
async def test_write_data_text_updates_writable_copy(minimal_game_dir: Path) -> None:
    """正文回写修改可写副本，原始加载数据保持不变。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.translation_lines = ["你好"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    text_command = ensure_json_object(commands[1], "CommonEvents[1].list[1]")
    parameters = ensure_json_array(text_command["parameters"], "CommonEvents[1].list[1].parameters")
    assert parameters[0] == "你好"


@pytest.mark.asyncio
async def test_write_data_text_rejects_internal_placeholder_leak(minimal_game_dir: Path) -> None:
    """正文写回前必须拒绝项目内部占位符。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.translation_lines = ["你好[RMMZ_TEXT_COLOR_0]"]

    reset_writable_copies(game_data)
    with pytest.raises(ValueError, match="译文残留项目内部占位符"):
        write_data_text(game_data, [item])


@pytest.mark.asyncio
async def test_name_text_write_back_uses_real_401_paths(minimal_game_dir: Path) -> None:
    """名字框正文按实际 401 路径写回，不按相邻下标猜测。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_events = _read_test_json(common_events_path)
    events = ensure_json_array(raw_events, "CommonEvents")
    event = ensure_json_object(events[1], "CommonEvents[1]")
    event_commands = ensure_json_array(event["list"], "CommonEvents[1].list")
    event_commands.insert(1, {"code": 401, "parameters": [""]})
    _rewrite_json(common_events_path, raw_events)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    assert item.original_lines == ["こんにちは"]
    assert item.source_line_paths == ["CommonEvents.json/1/2"]

    item.translation_lines = ["你好"]
    reset_writable_copies(game_data)
    write_data_text(game_data, [item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    blank_text_command = ensure_json_object(commands[1], "CommonEvents[1].list[1]")
    translated_text_command = ensure_json_object(commands[2], "CommonEvents[1].list[2]")
    blank_parameters = ensure_json_array(blank_text_command["parameters"], "blank.parameters")
    translated_parameters = ensure_json_array(
        translated_text_command["parameters"],
        "translated.parameters",
    )
    assert blank_parameters[0] == ""
    assert translated_parameters[0] == "你好"


@pytest.mark.asyncio
async def test_name_text_write_back_inserts_extra_401_lines(minimal_game_dir: Path) -> None:
    """名字框正文译文行数增加时，在原文本块末尾插入新的 401。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.translation_lines = ["你好", "第二行", "第三行"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    first_text = ensure_json_object(commands[1], "CommonEvents[1].list[1]")
    second_text = ensure_json_object(commands[2], "CommonEvents[1].list[2]")
    third_text = ensure_json_object(commands[3], "CommonEvents[1].list[3]")
    choice_command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")

    assert first_text["code"] == 401
    assert second_text["code"] == 401
    assert third_text["code"] == 401
    assert choice_command["code"] == 102
    assert ensure_json_array(first_text["parameters"], "first.parameters")[0] == "你好"
    assert ensure_json_array(second_text["parameters"], "second.parameters")[0] == "第二行"
    assert ensure_json_array(third_text["parameters"], "third.parameters")[0] == "第三行"


@pytest.mark.asyncio
async def test_write_back_inserts_401_without_shifting_later_name_block(minimal_game_dir: Path) -> None:
    """前一个名字框插入额外 401 时，后一个名字框仍按原始定位正确写回。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_events = _read_test_json(common_events_path)
    events = ensure_json_array(raw_events, "CommonEvents")
    event = ensure_json_object(events[1], "CommonEvents[1]")
    event["list"] = [
        {"code": 101, "parameters": [0, 0, 0, 2, "案内人A"]},
        {"code": 401, "parameters": ["前半一行目"]},
        {"code": 101, "parameters": [0, 0, 0, 2, "案内人B"]},
        {"code": 401, "parameters": ["後半一行目"]},
        {"code": 0, "parameters": []},
    ]
    _rewrite_json(common_events_path, raw_events)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    common_items = extracted["CommonEvents.json"].translation_items
    first_item = next(item for item in common_items if item.location_path == "CommonEvents.json/1/0")
    second_item = next(item for item in common_items if item.location_path == "CommonEvents.json/1/2")
    first_item.translation_lines = ["前半译文一", "前半译文二", "前半译文三"]
    second_item.translation_lines = ["后半译文"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [first_item, second_item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_object(commands[0], "command0")["code"] == 101
    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "前半译文一"
    assert ensure_json_array(ensure_json_object(commands[2], "command2")["parameters"], "command2.parameters")[0] == "前半译文二"
    assert ensure_json_array(ensure_json_object(commands[3], "command3")["parameters"], "command3.parameters")[0] == "前半译文三"
    assert ensure_json_object(commands[4], "command4")["code"] == 101
    assert ensure_json_array(ensure_json_object(commands[5], "command5")["parameters"], "command5.parameters")[0] == "后半译文"


@pytest.mark.asyncio
async def test_write_back_deletes_401_without_shifting_later_name_block(minimal_game_dir: Path) -> None:
    """前一个名字框删除多余 401 时，后一个名字框仍按原始定位正确写回。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_events = _read_test_json(common_events_path)
    events = ensure_json_array(raw_events, "CommonEvents")
    event = ensure_json_object(events[1], "CommonEvents[1]")
    event["list"] = [
        {"code": 101, "parameters": [0, 0, 0, 2, "案内人A"]},
        {"code": 401, "parameters": ["前半一行目"]},
        {"code": 401, "parameters": ["前半二行目"]},
        {"code": 101, "parameters": [0, 0, 0, 2, "案内人B"]},
        {"code": 401, "parameters": ["後半一行目"]},
        {"code": 0, "parameters": []},
    ]
    _rewrite_json(common_events_path, raw_events)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    common_items = extracted["CommonEvents.json"].translation_items
    first_item = next(item for item in common_items if item.location_path == "CommonEvents.json/1/0")
    second_item = next(item for item in common_items if item.location_path == "CommonEvents.json/1/3")
    first_item.translation_lines = ["前半译文"]
    second_item.translation_lines = ["后半译文"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [first_item, second_item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_object(commands[0], "command0")["code"] == 101
    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "前半译文"
    assert ensure_json_object(commands[2], "command2")["code"] == 101
    assert ensure_json_array(ensure_json_object(commands[3], "command3")["parameters"], "command3.parameters")[0] == "后半译文"
    assert ensure_json_object(commands[4], "command4")["code"] == 0


@pytest.mark.asyncio
async def test_write_data_text_splits_overwide_long_text_before_write_back(minimal_game_dir: Path) -> None:
    """写回阶段按当前行宽配置再次切分已有长译文。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.translation_lines = ["甲乙丙丁戊己庚辛"]
    text_rules = TextRules.from_setting(
        TextRulesSetting(
            long_text_line_width_limit=3,
            line_width_count_pattern=r"\S",
            line_split_punctuations=["，", "。"],
        )
    )

    reset_writable_copies(game_data)
    write_data_text(game_data, [item], text_rules=text_rules)

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "甲乙丙"
    assert ensure_json_array(ensure_json_object(commands[2], "command2")["parameters"], "command2.parameters")[0] == "丁戊己"
    assert ensure_json_array(ensure_json_object(commands[3], "command3")["parameters"], "command3.parameters")[0] == "庚辛"


@pytest.mark.asyncio
async def test_write_data_text_indents_wrapping_punctuation_continuation_lines(minimal_game_dir: Path) -> None:
    """写回阶段清理译文外层空白，并为跨行引号续行补视觉缩进。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.translation_lines = ["　「甲乙丙。　", "　丁戊己」　"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item], text_rules=get_default_text_rules())

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "「甲乙丙。"
    assert ensure_json_array(ensure_json_object(commands[2], "command2")["parameters"], "command2.parameters")[0] == "　丁戊己」"


@pytest.mark.asyncio
async def test_write_data_text_restores_converted_outer_quote_before_indent(minimal_game_dir: Path) -> None:
    """写回阶段先修复被模型改写的外层引号，再补跨行视觉缩进。"""
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.original_lines = ["「甲。", "乙」"]
    item.translation_lines = ["“甲乙丙。", "丁戊己。”"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item], text_rules=get_default_text_rules())

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "「甲乙丙。"
    assert ensure_json_array(ensure_json_object(commands[2], "command2")["parameters"], "command2.parameters")[0] == "　丁戊己。」"


@pytest.mark.asyncio
async def test_scroll_text_commands_are_grouped_by_adjacent_405(minimal_game_dir: Path) -> None:
    """连续 405 滚动文本作为一个翻译单元提取，并支持额外译文行写回。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_events = _read_test_json(common_events_path)
    events = ensure_json_array(raw_events, "CommonEvents")
    event = ensure_json_object(events[1], "CommonEvents[1]")
    event["list"] = [
        {"code": 101, "parameters": [0, 0, 0, 2, "アリス"]},
        {"code": 401, "parameters": ["こんにちは"]},
        {"code": 405, "parameters": ["スクロール一行目"]},
        {"code": 405, "parameters": ["スクロール二行目"]},
        {"code": 405, "parameters": [""]},
        {"code": 405, "parameters": ["別段落"]},
        {"code": 0, "parameters": []},
    ]
    _rewrite_json(common_events_path, raw_events)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    first_scroll_item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/2"
    )
    second_scroll_item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/5"
    )
    assert first_scroll_item.original_lines == ["スクロール一行目", "スクロール二行目"]
    assert first_scroll_item.source_line_paths == [
        "CommonEvents.json/1/2",
        "CommonEvents.json/1/3",
    ]
    assert second_scroll_item.original_lines == ["別段落"]

    first_scroll_item.translation_lines = ["滚动第一行", "滚动第二行", "滚动第三行"]
    second_scroll_item.translation_lines = ["另一段"]
    reset_writable_copies(game_data)
    write_data_text(game_data, [first_scroll_item, second_scroll_item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    assert ensure_json_array(ensure_json_object(commands[2], "command2")["parameters"], "command2.parameters")[0] == "滚动第一行"
    assert ensure_json_array(ensure_json_object(commands[3], "command3")["parameters"], "command3.parameters")[0] == "滚动第二行"
    assert ensure_json_array(ensure_json_object(commands[4], "command4")["parameters"], "command4.parameters")[0] == "滚动第三行"
    assert ensure_json_array(ensure_json_object(commands[5], "command5")["parameters"], "command5.parameters")[0] == ""
    assert ensure_json_array(ensure_json_object(commands[6], "command6")["parameters"], "command6.parameters")[0] == "另一段"


@pytest.mark.asyncio
async def test_long_text_write_back_deletes_extra_original_lines(minimal_game_dir: Path) -> None:
    """译文行数少于原始 405 行数时，删除多余原始行指令。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_events = _read_test_json(common_events_path)
    events = ensure_json_array(raw_events, "CommonEvents")
    event = ensure_json_object(events[1], "CommonEvents[1]")
    event["list"] = [
        {"code": 405, "parameters": ["スクロール一行目"]},
        {"code": 405, "parameters": ["スクロール二行目"]},
        {"code": 0, "parameters": []},
    ]
    _rewrite_json(common_events_path, raw_events)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    scroll_item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    assert scroll_item.original_lines == ["スクロール一行目", "スクロール二行目"]

    scroll_item.translation_lines = ["滚动第一行"]
    reset_writable_copies(game_data)
    write_data_text(game_data, [scroll_item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    assert ensure_json_array(ensure_json_object(commands[0], "command0")["parameters"], "command0.parameters")[0] == "滚动第一行"
    assert ensure_json_object(commands[1], "command1")["code"] == 0


@pytest.mark.asyncio
async def test_long_text_write_back_ignores_trailing_empty_translation_lines(minimal_game_dir: Path) -> None:
    """长文本写回忽略译文尾部空行，避免生成空白文本指令。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_events = _read_test_json(common_events_path)
    events = ensure_json_array(raw_events, "CommonEvents")
    event = ensure_json_object(events[1], "CommonEvents[1]")
    event["list"] = [
        {"code": 405, "parameters": ["スクロール一行目"]},
        {"code": 405, "parameters": ["スクロール二行目"]},
        {"code": 0, "parameters": []},
    ]
    _rewrite_json(common_events_path, raw_events)

    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    scroll_item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    scroll_item.translation_lines = ["滚动第一行", ""]

    reset_writable_copies(game_data)
    write_data_text(game_data, [scroll_item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    assert ensure_json_array(ensure_json_object(commands[0], "command0")["parameters"], "command0.parameters")[0] == "滚动第一行"
    assert ensure_json_object(commands[1], "command1")["code"] == 0


@pytest.mark.asyncio
async def test_first_write_back_archives_complete_original_data_snapshot(minimal_game_dir: Path) -> None:
    """首次磁盘回写把完整原始 data 复制到 `data_origin/`。"""
    game_data = await load_game_data(minimal_game_dir)
    active_data_names = sorted(path.name for path in (minimal_game_dir / "data").glob("*.json"))
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.translation_lines = ["你好"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item])
    write_game_files(game_data, minimal_game_dir)

    origin_data_dir = minimal_game_dir / "data_origin"
    origin_data_names = sorted(path.name for path in origin_data_dir.glob("*.json"))
    assert origin_data_names == active_data_names
    assert (origin_data_dir / "Animations.json").exists()
    assert (origin_data_dir / "CommonEvents.json").exists()
    assert (origin_data_dir / "MapInfos.json").exists()
    assert (origin_data_dir / "System.json").exists()
    assert (origin_data_dir / "Tilesets.json").exists()
    assert (origin_data_dir / "UnknownPluginData.json").exists()
    assert not (minimal_game_dir / "js" / "plugins_origin.js").exists()

    active_common_events = ensure_json_array(
        _read_test_json(minimal_game_dir / "data" / "CommonEvents.json"),
        "CommonEvents",
    )
    active_event = ensure_json_object(active_common_events[1], "CommonEvents[1]")
    active_commands = ensure_json_array(active_event["list"], "CommonEvents[1].list")
    active_text_command = ensure_json_object(active_commands[1], "CommonEvents[1].list[1]")
    active_parameters = ensure_json_array(
        active_text_command["parameters"],
        "CommonEvents[1].list[1].parameters",
    )
    assert active_parameters[0] == "你好"


@pytest.mark.asyncio
async def test_written_game_reads_complete_origin_without_mutating_snapshot(minimal_game_dir: Path) -> None:
    """已有完整原始 data 备份时，后续写回不修改 `data_origin/`。"""
    first_game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(first_game_data, get_default_text_rules()).extract_all_text()
    common_item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    common_item.translation_lines = ["你好"]
    reset_writable_copies(first_game_data)
    write_data_text(first_game_data, [common_item])
    write_game_files(first_game_data, minimal_game_dir)
    origin_data_dir = minimal_game_dir / "data_origin"
    origin_snapshot = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(origin_data_dir.glob("*.json"), key=lambda candidate: candidate.name)
    }

    reloaded_game_data = await load_game_data(minimal_game_dir)
    reloaded_extracted = DataTextExtraction(reloaded_game_data, get_default_text_rules()).extract_all_text()
    reloaded_common_item = next(
        candidate
        for candidate in reloaded_extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    assert reloaded_common_item.original_lines == ["こんにちは"]

    actor_item = next(
        candidate
        for candidate in reloaded_extracted["Actors.json"].translation_items
        if candidate.location_path == "Actors.json/1/profile"
    )
    actor_item.translation_lines = ["角色简介译文"]
    reset_writable_copies(reloaded_game_data)
    write_data_text(reloaded_game_data, [actor_item])
    write_game_files(reloaded_game_data, minimal_game_dir)
    assert {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(origin_data_dir.glob("*.json"), key=lambda candidate: candidate.name)
    } == origin_snapshot

    origin_actors_path = origin_data_dir / "Actors.json"
    assert origin_actors_path.exists()
    origin_actors = ensure_json_array(_read_test_json(origin_actors_path), "data_origin/Actors.json")
    active_actors = ensure_json_array(_read_test_json(minimal_game_dir / "data" / "Actors.json"), "Actors.json")
    origin_actor = ensure_json_object(origin_actors[1], "data_origin/Actors.json[1]")
    active_actor = ensure_json_object(active_actors[1], "Actors.json[1]")
    assert origin_actor["profile"] == "プロフィール"
    assert active_actor["profile"] == "角色简介译文"

    plugin_game_data = await load_game_data(minimal_game_dir)
    reset_writable_copies(plugin_game_data)
    plugin_text = plugin_game_data.writable_data[PLUGINS_FILE_NAME]
    assert isinstance(plugin_text, str)
    plugin_game_data.writable_data[PLUGINS_FILE_NAME] = plugin_text.replace("プラグイン本文", "插件正文")
    write_game_files(plugin_game_data, minimal_game_dir)

    origin_plugins_path = minimal_game_dir / "js" / "plugins_origin.js"
    assert origin_plugins_path.exists()
    assert "プラグイン本文" in origin_plugins_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_loader_rejects_missing_fixed_active_data_file(minimal_game_dir: Path) -> None:
    """激活 data 缺标准文件时禁止加载游戏。"""
    (minimal_game_dir / "data" / "Animations.json").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "激活数据目录" in message
    assert "Animations.json" in message


@pytest.mark.asyncio
async def test_loader_rejects_map_infos_with_missing_map_file(minimal_game_dir: Path) -> None:
    """MapInfos.json 引用不存在的地图文件时禁止加载游戏。"""
    map_infos_path = minimal_game_dir / "data" / "MapInfos.json"
    map_infos = ensure_json_array(_read_test_json(map_infos_path), "MapInfos.json")
    map_infos.append(
        {
            "id": 14,
            "expanded": False,
            "name": "",
            "order": 14,
            "parentId": 0,
            "scrollX": 0,
            "scrollY": 0,
        }
    )
    _rewrite_json(map_infos_path, map_infos)

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "MapInfos.json" in message
    assert "Map014.json" in message


@pytest.mark.asyncio
async def test_loader_rejects_incomplete_data_origin(minimal_game_dir: Path) -> None:
    """data_origin 必须是完整原始 data 备份。"""
    origin_data_dir = minimal_game_dir / "data_origin"
    origin_data_dir.mkdir()
    _ = shutil.copy2(
        minimal_game_dir / "data" / "CommonEvents.json",
        origin_data_dir / "CommonEvents.json",
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "原始 data 备份" in message
    assert "Animations.json" in message


@pytest.mark.asyncio
async def test_loader_rejects_active_missing_file_even_when_origin_is_complete(minimal_game_dir: Path) -> None:
    """激活 data 损坏时不能靠完整 data_origin 掩盖。"""
    _ = shutil.copytree(minimal_game_dir / "data", minimal_game_dir / "data_origin")
    (minimal_game_dir / "data" / "Animations.json").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "激活数据目录" in message
    assert "Animations.json" in message


@pytest.mark.asyncio
async def test_font_replacement_updates_only_writable_outputs(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """字体替换只作用于本轮可写副本，并复制目标字体到游戏目录。"""
    fonts_dir = minimal_game_dir / "fonts"
    fonts_dir.mkdir()
    old_font = "OldFont.woff"
    another_font = "AnotherFont.woff"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    _ = (fonts_dir / another_font).write_bytes(b"another font")
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

    game_data = await load_game_data(minimal_game_dir)
    reset_writable_copies(game_data)
    system = ensure_json_object(game_data.writable_data["System.json"], "System")
    system["advanced"] = {
        "mainFontFilename": old_font,
        "numberFontFilename": another_font,
    }
    plugin = ensure_json_object(game_data.writable_plugins_js[0], "plugins[0]")
    parameters = ensure_json_object(plugin["parameters"], "plugins[0].parameters")
    parameters["FontFace"] = old_font
    parameters["FontStem"] = Path(old_font).stem
    parameters["Nested"] = json.dumps(
        {"font": another_font, "text": "プラグイン本文"},
        ensure_ascii=False,
    )
    parameters["HelpText"] = f"请在设置中选择 {Path(old_font).stem} 字体。"

    summary = apply_font_replacement(
        game_data=game_data,
        game_root=minimal_game_dir,
        replacement_font_path=str(replacement_font),
    )

    replacement_name = replacement_font.name
    assert (fonts_dir / replacement_name).exists()
    assert summary.target_font_name == replacement_name
    assert summary.source_font_count == 2
    assert summary.replaced_reference_count == 5
    assert len(summary.records) == 5
    writable_system = ensure_json_object(game_data.writable_data["System.json"], "System")
    advanced = ensure_json_object(writable_system["advanced"], "System.advanced")
    writable_plugin = ensure_json_object(game_data.writable_plugins_js[0], "plugins[0]")
    writable_parameters = ensure_json_object(writable_plugin["parameters"], "plugins[0].parameters")
    assert advanced["mainFontFilename"] == replacement_name
    assert advanced["numberFontFilename"] == replacement_name
    assert writable_parameters["FontFace"] == replacement_name
    assert writable_parameters["FontStem"] == replacement_name
    nested_text = writable_parameters["Nested"]
    assert isinstance(nested_text, str)
    nested_value = ensure_json_object(coerce_json_value(cast(object, json.loads(nested_text))), "Nested")
    assert nested_value["font"] == replacement_name
    assert nested_value["text"] == "プラグイン本文"
    assert writable_parameters["HelpText"] == f"请在设置中选择 {Path(old_font).stem} 字体。"
    original_system = json.dumps(game_data.data["System.json"], ensure_ascii=False)
    assert old_font not in original_system
    assert another_font not in original_system

    assert replacement_name not in original_system


@pytest.mark.asyncio
async def test_mv_font_replacement_updates_gamefont_css_and_css_declared_font_stems(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 字体覆盖会同步改写 gamefont.css，并识别样式表里声明但缺失的旧字体。"""
    fonts_dir = minimal_mv_game_dir / "www" / "fonts"
    fonts_dir.mkdir()
    old_font = "YujiSyuku-Regular.ttf"
    css_only_font = "衡山毛筆フォント_0.TTF"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    gamefont_css_path = fonts_dir / "gamefont.css"
    _ = gamefont_css_path.write_text(
        "\n".join(
            [
                "@font-face {",
                "  font-family: GameFont;",
                "  src: url('YujiSyuku-Regular.ttf');",
                "}",
                "@font-face {",
                "  font-family: 'GameFont2';",
                f"  src: url(\"{css_only_font}\");",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

    game_data = await load_game_data(minimal_mv_game_dir)
    reset_writable_copies(game_data)
    plugin = ensure_json_object(game_data.writable_plugins_js[0], "plugins[0]")
    parameters = ensure_json_object(plugin["parameters"], "plugins[0].parameters")
    parameters["BrushFont"] = Path(css_only_font).stem
    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    command_list = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(command_list[2], "CommonEvents[1].list[2]")
    command["parameters"] = ["MultiFont change GameFont2"]

    summary = apply_font_replacement(
        game_data=game_data,
        game_root=minimal_mv_game_dir,
        replacement_font_path=str(replacement_font),
    )

    replacement_name = replacement_font.name
    origin_css_path = fonts_dir / "gamefont_origin.css"
    active_css = gamefont_css_path.read_text(encoding="utf-8")
    origin_css = origin_css_path.read_text(encoding="utf-8")
    writable_plugin = ensure_json_object(game_data.writable_plugins_js[0], "plugins[0]")
    writable_parameters = ensure_json_object(writable_plugin["parameters"], "plugins[0].parameters")
    writable_common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    writable_common_event = ensure_json_object(writable_common_events[1], "CommonEvents[1]")
    writable_command_list = ensure_json_array(writable_common_event["list"], "CommonEvents[1].list")
    writable_command = ensure_json_object(writable_command_list[2], "CommonEvents[1].list[2]")

    assert (fonts_dir / replacement_name).exists()
    assert origin_css_path.exists()
    assert "YujiSyuku-Regular.ttf" in origin_css
    assert "衡山毛筆フォント_0.TTF" in origin_css
    assert active_css.count(replacement_name) == 2
    assert "YujiSyuku-Regular.ttf" not in active_css
    assert "衡山毛筆フォント_0.TTF" not in active_css
    assert writable_parameters["BrushFont"] == replacement_name
    assert writable_command["parameters"] == ["MultiFont change GameFont2"]
    assert summary.source_font_count == 2
    assert summary.replaced_reference_count == 3
    assert len(summary.records) == 3


@pytest.mark.asyncio
async def test_restore_font_references_restores_mv_gamefont_css_without_rolling_back_other_css(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """字体还原会按 gamefont.css 原始备份恢复 MV 字体族入口。"""
    fonts_dir = minimal_mv_game_dir / "www" / "fonts"
    fonts_dir.mkdir()
    old_font = "YujiSyuku-Regular.ttf"
    css_only_font = "衡山毛筆フォント_0.TTF"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    gamefont_css_path = fonts_dir / "gamefont.css"
    _ = gamefont_css_path.write_text(
        "\n".join(
            [
                "@font-face {",
                "  font-family: GameFont;",
                "  src: url('YujiSyuku-Regular.ttf');",
                "}",
                "@font-face {",
                "  font-family: 'GameFont2';",
                f"  src: url(\"{css_only_font}\");",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

    game_data = await load_game_data(minimal_mv_game_dir)
    reset_writable_copies(game_data)
    _ = apply_font_replacement(
        game_data=game_data,
        game_root=minimal_mv_game_dir,
        replacement_font_path=str(replacement_font),
    )
    active_css = gamefont_css_path.read_text(encoding="utf-8")
    _ = gamefont_css_path.write_text(
        f"{active_css}\n/* 已写入译文后新增的样式 */\n",
        encoding="utf-8",
    )

    restore_summary = restore_font_references_from_origin_backups(
        game_root=minimal_mv_game_dir,
        replacement_font_names=[replacement_font.name],
    )

    restored_css = gamefont_css_path.read_text(encoding="utf-8")
    assert restore_summary.restored_field_count == 2
    assert restore_summary.restored_reference_count == 2
    assert "url('YujiSyuku-Regular.ttf')" in restored_css
    assert "url(\"衡山毛筆フォント_0.TTF\")" in restored_css
    assert replacement_font.name not in restored_css
    assert "已写入译文后新增的样式" in restored_css


@pytest.mark.asyncio
async def test_restore_font_references_uses_origin_backups_without_rolling_back_text(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """字体还原按原始备份替回旧字体引用，不回滚已经写入的译文。"""
    fonts_dir = minimal_game_dir / "fonts"
    fonts_dir.mkdir()
    old_font = "OldFont.woff"
    another_font = "AnotherFont.woff"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    _ = (fonts_dir / another_font).write_bytes(b"another font")
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

    system_path = minimal_game_dir / "data" / "System.json"
    raw_system = _read_test_json(system_path)
    system = ensure_json_object(raw_system, "System.json")
    system["advanced"] = {
        "mainFontFilename": old_font,
        "numberFontFilename": another_font,
    }
    _rewrite_json(system_path, raw_system)

    base_game_data = await load_game_data(minimal_game_dir)
    plugin = ensure_json_object(base_game_data.plugins_js[0], "plugins[0]")
    parameters = ensure_json_object(plugin["parameters"], "plugins[0].parameters")
    parameters["FontFace"] = old_font
    parameters["FontStem"] = Path(old_font).stem
    parameters["Nested"] = json.dumps(
        {"font": another_font, "text": "プラグイン本文"},
        ensure_ascii=False,
    )
    parameters["HelpText"] = f"请在设置中选择 {old_font} 字体。"
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(base_game_data.plugins_js, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )

    game_data = await load_game_data(minimal_game_dir)
    reset_writable_copies(game_data)
    writable_system = ensure_json_object(game_data.writable_data["System.json"], "System")
    writable_system["gameTitle"] = "翻译标题"
    writable_plugin = ensure_json_object(game_data.writable_plugins_js[0], "plugins[0]")
    writable_parameters = ensure_json_object(writable_plugin["parameters"], "plugins[0].parameters")
    replacement_name = replacement_font.name
    writable_parameters["Nested"] = json.dumps(
        {"font": another_font, "text": "插件正文"},
        ensure_ascii=False,
    )
    writable_parameters["HelpText"] = f"请在设置中选择 {replacement_name} 字体。"

    _ = apply_font_replacement(
        game_data=game_data,
        game_root=minimal_game_dir,
        replacement_font_path=str(replacement_font),
    )
    write_game_files(game_data, minimal_game_dir)

    restore_summary = restore_font_references_from_origin_backups(
        game_root=minimal_game_dir,
        replacement_font_names=[replacement_name],
    )

    assert restore_summary.restored_reference_count == 5
    active_system = ensure_json_object(_read_test_json(system_path), "System.json")
    active_advanced = ensure_json_object(active_system["advanced"], "System.advanced")
    assert active_system["gameTitle"] == "翻译标题"
    assert active_advanced["mainFontFilename"] == old_font
    assert active_advanced["numberFontFilename"] == another_font

    restored_plugins = read_plugins_js_file(plugins_path)
    restored_plugin = ensure_json_object(restored_plugins[0], "plugins[0]")
    restored_parameters = ensure_json_object(restored_plugin["parameters"], "plugins[0].parameters")
    assert restored_parameters["FontFace"] == old_font
    assert restored_parameters["FontStem"] == Path(old_font).stem
    nested_text = restored_parameters["Nested"]
    assert isinstance(nested_text, str)
    nested_value = ensure_json_object(coerce_json_value(cast(object, json.loads(nested_text))), "Nested")
    assert nested_value["font"] == another_font
    assert nested_value["text"] == "插件正文"
    assert restored_parameters["HelpText"] == f"请在设置中选择 {replacement_name} 字体。"
