"""事件指令外部规则导入、提取和回写测试。"""

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter, ValidationError

from app.cli import build_parser, read_bool_arg, read_int_set_arg, read_optional_str_arg
from app.config.schemas import EventCommandTextSetting
from app.event_command_text import (
    EventCommandTextExtraction,
    build_event_command_rule_records_from_import,
    export_event_commands_json_file,
    load_event_command_rule_import_file,
    resolve_event_command_codes,
)
from app.native_scope_index import NativeRuleCandidatesResult
from app.rmmz.loader import load_active_runtime_game_data
from app.rmmz.schema import EventCommandTextRuleRecord, GameData, TranslationData, TranslationItem
from app.rmmz.source_snapshot import create_source_snapshot_for_clean_game
from app.rmmz.text_rules import JsonArray, JsonObject, JsonValue, coerce_json_value, ensure_json_array, ensure_json_object
from tests._native_write_plan_helper import reset_writable_copies, write_data_text


def _create_test_source_snapshot(game_data: GameData) -> None:
    """为写回测试显式模拟注册流程已经创建的可信源快照。"""
    layout = game_data.layout
    if (
        layout.data_origin_dir.is_dir()
        and layout.plugins_origin_path.is_file()
        and layout.plugin_source_origin_dir.is_dir()
    ):
        return
    create_source_snapshot_for_clean_game(layout)


@pytest.mark.asyncio
async def test_event_command_json_export_uses_configured_command_codes(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令导出使用配置数组解析出的编码集合。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    output_path = tmp_path / "event-commands.json"

    command_count = await export_event_commands_json_file(
        game_data=game_data,
        output_path=output_path,
        command_codes=resolve_event_command_codes(
            command_codes=None,
            configured_command_codes=[357],
        ),
    )

    assert command_count == 2
    json_value_adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
    exported_value = json_value_adapter.validate_json(output_path.read_text(encoding="utf-8"))
    root = ensure_json_object(exported_value, "event-commands.json")
    commands = ensure_json_array(root["357"], "event-commands.json.357")
    plugin_actions: set[tuple[str, str]] = set()
    for index, command in enumerate(commands):
        parameters = ensure_json_array(command, f"event-commands.json.357[{index}]")
        plugin_name = parameters[0]
        action_name = parameters[1]
        assert isinstance(plugin_name, str)
        assert isinstance(action_name, str)
        plugin_actions.add((plugin_name, action_name))

    assert plugin_actions == {
        ("TestPlugin", "Show"),
        ("ComplexPlugin", "ShowWindow"),
    }


@pytest.mark.asyncio
async def test_event_command_json_export_uses_native_samples(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令导出消费 Rust samples_by_code，不再执行 Python 全量指令遍历。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    output_path = tmp_path / "event-commands-native.json"
    captured_payloads: list[JsonObject] = []

    def fake_scan_native_rule_candidates(payload: JsonObject) -> NativeRuleCandidatesResult:
        captured_payloads.append(payload)
        return NativeRuleCandidatesResult(
            schema_version=1,
            candidates=cast(JsonArray, []),
            candidate_summary=[],
            scan_summary=cast(
                JsonObject,
                {
                    "event_commands": {
                        "sample_count": 1,
                        "samples_by_code": {
                            "357": [["NativePlugin", "ShowNative"]],
                        },
                    }
                },
            ),
            timings_ms={},
            counters={"candidate_count": 0},
        )

    def forbidden_iter_all_commands(_game_data: GameData) -> None:
        raise AssertionError("export_event_commands_json_file 必须改用 Rust samples_by_code")

    monkeypatch.setattr("app.event_command_text.exporter.scan_native_rule_candidates", fake_scan_native_rule_candidates)
    monkeypatch.setattr("app.event_command_text.exporter.iter_all_commands", forbidden_iter_all_commands, raising=False)

    command_count = await export_event_commands_json_file(
        game_data=game_data,
        output_path=output_path,
        command_codes=frozenset({357}),
    )

    assert command_count == 1
    json_value_adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
    exported_value = json_value_adapter.validate_json(output_path.read_text(encoding="utf-8"))
    assert exported_value == {"357": [["NativePlugin", "ShowNative"]]}

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload["event_command_codes"] == [357]
    data_files = ensure_json_array(payload["event_command_data_files"], "event_command_data_files")
    data_file_names = {str(ensure_json_object(item, f"event_command_data_files[{index}]")["file_name"]) for index, item in enumerate(data_files)}
    assert "CommonEvents.json" in data_file_names
    assert "Troops.json" in data_file_names
    assert any(file_name.startswith("Map") for file_name in data_file_names)


@pytest.mark.asyncio
async def test_mv_event_command_json_export_uses_engine_default_356(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 未显式传入编码时使用引擎默认的 356 插件命令。"""
    game_data = await load_active_runtime_game_data(minimal_mv_game_dir)
    setting = EventCommandTextSetting.model_validate(
        {
            "default_command_codes_by_engine": {"mv": [356], "mz": [357]},
        }
    )
    output_path = tmp_path / "mv-event-commands.json"

    command_count = await export_event_commands_json_file(
        game_data=game_data,
        output_path=output_path,
        command_codes=resolve_event_command_codes(
            command_codes=None,
            configured_command_codes=setting.default_codes_for_engine(game_data.layout.engine_kind),
        ),
    )

    assert command_count == 1
    json_value_adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
    exported_value = json_value_adapter.validate_json(output_path.read_text(encoding="utf-8"))
    root = ensure_json_object(exported_value, "mv-event-commands.json")
    commands = ensure_json_array(root["356"], "mv-event-commands.json.356")
    parameters = ensure_json_array(commands[0], "mv-event-commands.json.356[0]")
    assert parameters == ["ShowMvText text:MVプラグイン本文 name:案内人"]


def test_event_command_code_resolution_uses_configured_code_array() -> None:
    """事件指令导出编码未传入时使用配置数组，命令参数可覆盖配置。"""
    assert resolve_event_command_codes(
        command_codes=None,
        configured_command_codes=[357, 999, 357],
    ) == frozenset({357, 999})
    assert resolve_event_command_codes(
        command_codes={102, 103},
        configured_command_codes=[357],
    ) == frozenset({102, 103})


def test_event_command_setting_reads_engine_default_codes() -> None:
    """事件指令默认编码按引擎读取，显式编码仍由调用方覆盖。"""
    setting = EventCommandTextSetting.model_validate(
        {
            "default_command_codes_by_engine": {"mv": [356], "mz": [357]},
        }
    )

    assert setting.default_codes_for_engine("mv") == [356]
    assert setting.default_codes_for_engine("mz") == [357]


def test_event_command_text_setting_requires_engine_code_map() -> None:
    """事件指令按引擎默认编码必须由配置文件显式提供。"""
    with pytest.raises(ValidationError):
        _ = EventCommandTextSetting.model_validate({})


def test_export_event_command_parser_accepts_code_array() -> None:
    """CLI 的 --code 支持一次传入多个事件指令编码。"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "export-event-commands-json",
            "--game",
            "テストゲーム",
            "--output",
            "commands.json",
            "--code",
            "357",
            "999",
        ]
    )

    assert read_int_set_arg(args, "codes") == {357, 999}


def test_import_event_command_parser_accepts_code_array() -> None:
    """事件指令空规则导入可声明本次审查的编码范围。"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "import-event-command-rules",
            "--game",
            "テストゲーム",
            "--input",
            "event-command-rules.json",
            "--confirm-empty",
            "--code",
            "357",
            "999",
        ]
    )

    assert read_int_set_arg(args, "codes") == {357, 999}


def test_write_back_parser_accepts_font_overwrite_confirmation() -> None:
    """write-back 支持显式字体覆盖确认。"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "write-back",
            "--game",
            "テストゲーム",
            "--confirm-font-overwrite",
        ]
    )

    assert read_bool_arg(args, "confirm_font_overwrite") is True


def test_restore_font_parser_accepts_replacement_font_path() -> None:
    """restore-font 支持字体路径配置覆盖。"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "restore-font",
            "--game",
            "テストゲーム",
            "--replacement-font-path",
            "fonts/NotoSansSC-Regular.ttf",
        ]
    )

    assert read_optional_str_arg(args, "replacement_font_path") == "fonts/NotoSansSC-Regular.ttf"


@pytest.mark.asyncio
async def test_event_command_rule_import_extracts_and_writes_back(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令文本由外部规则导入后按数据库规则提取并写回。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": [
                            "$['parameters'][3]['message']",
                            "$['parameters'][3]['file']",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import_file = await load_event_command_rule_import_file(input_path)
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=import_file,
    )
    assert records[0].command_code == 357
    assert records[0].path_templates == [
        "$['parameters'][3]['message']",
        "$['parameters'][3]['file']",
    ]
    def forbidden_rule_item_extract(
        _self: EventCommandTextExtraction,
    ) -> tuple[dict[str, TranslationData], list[list[TranslationItem]]]:
        raise AssertionError("普通事件指令提取不应构造规则组命中明细")

    monkeypatch.setattr(EventCommandTextExtraction, "extract_all_text_with_rule_items", forbidden_rule_item_extract)

    extracted = EventCommandTextExtraction(game_data, records).extract_all_text()
    items = extracted["CommonEvents.json"].translation_items
    assert [item.location_path for item in items] == [
        "CommonEvents.json/1/4/parameters/3/message",
    ]
    item = items[0]
    assert item.location_path == "CommonEvents.json/1/4/parameters/3/message"
    assert item.original_lines == ["プラグイン台詞"]

    item.translation_lines = ["事件指令译文"]
    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    write_data_text(game_data, [item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    payload = ensure_json_object(parameters[3], "CommonEvents[1].list[4].parameters[3]")
    assert payload["message"] == "事件指令译文"


@pytest.mark.asyncio
async def test_event_command_extraction_rejects_stale_command_match(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令参数变化后，已保存规则不能静默变成空命中。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=await load_event_command_rule_import_file(input_path),
    )

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    parameters[1] = "RenamedAction"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    stale_game_data = await load_active_runtime_game_data(minimal_game_dir)

    with pytest.raises(RuntimeError, match="事件指令规则已过期"):
        _ = EventCommandTextExtraction(stale_game_data, records).extract_all_text()


@pytest.mark.asyncio
async def test_event_command_extraction_rejects_stale_path_template(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令嵌套字段消失后，已保存路径规则必须显式失败。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=await load_event_command_rule_import_file(input_path),
    )

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    payload = ensure_json_object(parameters[3], "CommonEvents[1].list[4].parameters[3]")
    _ = payload.pop("message")
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    stale_game_data = await load_active_runtime_game_data(minimal_game_dir)

    with pytest.raises(RuntimeError, match="路径没有命中当前字符串叶子"):
        _ = EventCommandTextExtraction(stale_game_data, records).extract_all_text()


@pytest.mark.asyncio
async def test_event_command_extraction_rejects_path_changed_to_non_string_leaf(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令路径仍存在但不再是字符串叶子时，规则必须显式过期。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=await load_event_command_rule_import_file(input_path),
    )

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    payload = ensure_json_object(parameters[3], "CommonEvents[1].list[4].parameters[3]")
    payload["message"] = {"text": "イベントコマンド"}
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    stale_game_data = await load_active_runtime_game_data(minimal_game_dir)

    with pytest.raises(RuntimeError, match="路径没有命中当前字符串叶子"):
        _ = EventCommandTextExtraction(stale_game_data, records).extract_all_text()


@pytest.mark.asyncio
async def test_event_command_nested_write_error_reports_location_path(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令嵌套参数写回失败时报告当前文本路径。"""
    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": [
                            "$['parameters'][3]['message']",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import_file = await load_event_command_rule_import_file(input_path)
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=import_file,
    )
    item = EventCommandTextExtraction(game_data, records).extract_all_text()[
        "CommonEvents.json"
    ].translation_items[0]
    item.location_path = "CommonEvents.json/1/4/parameters/3/missing"
    item.translation_lines = ["事件指令译文"]

    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    with pytest.raises(ValueError) as exc_info:
        write_data_text(game_data, [item])

    message = str(exc_info.value)
    assert "CommonEvents.json/1/4/parameters/3/missing" in message
    assert "参数键不存在 missing" in message


@pytest.mark.asyncio
async def test_event_command_json_string_leaf_uses_visible_text_protocol(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令参数里的 JSON 字符串叶子按玩家可见文本提取和写回。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    payload = ensure_json_object(parameters[3], "CommonEvents[1].list[4].parameters[3]")
    source_message = "\n　" + r"\C[2]任務説明\C[0]\n村へ向かう。" + "　\n"
    payload["message"] = json.dumps(source_message, ensure_ascii=False)
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": [
                            "$['parameters'][3]['message']",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import_file = await load_event_command_rule_import_file(input_path)
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=import_file,
    )
    item = EventCommandTextExtraction(game_data, records).extract_all_text()[
        "CommonEvents.json"
    ].translation_items[0]
    assert item.original_lines == [source_message.strip()]

    translated_message = "\n　" + r"\C[2]任务说明\C[0]\n前往村子。" + "　\n"
    item.translation_lines = [translated_message.strip()]
    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    write_data_text(game_data, [item])

    writable_common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    writable_common_event = ensure_json_object(writable_common_events[1], "CommonEvents[1]")
    writable_commands = ensure_json_array(writable_common_event["list"], "CommonEvents[1].list")
    writable_command = ensure_json_object(writable_commands[4], "CommonEvents[1].list[4]")
    writable_parameters = ensure_json_array(writable_command["parameters"], "CommonEvents[1].list[4].parameters")
    writable_payload = ensure_json_object(writable_parameters[3], "CommonEvents[1].list[4].parameters[3]")
    assert isinstance(writable_payload["message"], str)
    assert json.loads(writable_payload["message"]) == translated_message.strip()


@pytest.mark.asyncio
async def test_event_command_direct_parameter_string_writes_back(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令规则直接命中 parameters[N] 字符串叶子时可以写回。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    parameters[2] = "トップパラメータ"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

    game_data = await load_active_runtime_game_data(minimal_game_dir)
    input_path = tmp_path / "event-command-rules.json"
    _ = input_path.write_text(
        json.dumps(
            {
                "357": [
                    {
                        "match": {
                            "0": "TestPlugin",
                            "1": "Show",
                        },
                        "paths": [
                            "$['parameters'][2]",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import_file = await load_event_command_rule_import_file(input_path)
    records = build_event_command_rule_records_from_import(
        game_data=game_data,
        import_file=import_file,
    )
    extracted = EventCommandTextExtraction(game_data, records).extract_all_text()
    items = extracted["CommonEvents.json"].translation_items
    assert [item.location_path for item in items] == [
        "CommonEvents.json/1/4/parameters/2",
    ]
    item = items[0]
    assert item.original_lines == ["トップパラメータ"]

    item.translation_lines = ["顶层参数译文"]
    _create_test_source_snapshot(game_data)
    reset_writable_copies(game_data)
    write_data_text(game_data, [item])

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    assert parameters[2] == "顶层参数译文"


def test_event_command_text_extraction_supports_custom_command_code() -> None:
    """事件指令规则可以指定任意需要处理的指令编码。"""
    rule_record = EventCommandTextRuleRecord(
        command_code=999,
        path_templates=["$['parameters'][0]['label']"],
    )
    assert rule_record.command_code == 999
