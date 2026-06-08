"""RPG Maker 文件写回事务和正文写入业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *
from app.agent_toolkit import AgentToolkitService
from app.text_index import rebuild_text_index_native_storage, text_index_item_to_translation_item

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
async def test_english_visible_401_control_only_letters_do_not_extract_chinese_text(
    minimal_game_dir: Path,
) -> None:
    """英文事件正文判断先剥离控制符，避免把颜色控制符当英文源文。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 3,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2, "Guide"]},
                {"code": 401, "parameters": [r"\c[14]水池的水位已然降低..."]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    text_rules = TextRules.from_setting(
        TextRulesSetting(
            source_language="en",
            source_text_required_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
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

    assert "CommonEvents.json/3/0" not in items_by_path
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
    setting_text = _example_setting_text_with_absolute_prompt_files()
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
        _ = await rebuild_text_index_native_storage(
            session=session,
            setting=setting,
            text_rules=text_rules,
        )
        await write_v2_test_translation_items(
            session,
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

    _ = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title="テストゲーム")
    async with await registry.open_game("テストゲーム") as session:
        index_items = await session.read_text_index_items()
        indexed_translation_items: list[TranslationItem] = []
        for index_record in index_items:
            item = text_index_item_to_translation_item(index_record)
            item.translation_lines = (
                ["但是——"]
                if item.location_path == "CommonEvents.json/3/0"
                else [
                    _translated_test_line_preserving_controls(line, text_rules)
                    for line in item.original_lines
                ]
            )
            indexed_translation_items.append(item)
        await write_v2_test_translation_items(session, indexed_translation_items)

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
    _create_test_source_snapshot(minimal_game_dir)
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
    _create_test_source_snapshot(minimal_game_dir)
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
    _create_test_source_snapshot(minimal_game_dir)

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
    _create_test_source_snapshot(minimal_game_dir)
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
    _create_test_source_snapshot(minimal_game_dir)

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
    _create_test_source_snapshot(minimal_game_dir)

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
    _create_test_source_snapshot(minimal_game_dir)
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
    _create_test_source_snapshot(minimal_game_dir)
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
    _create_test_source_snapshot(minimal_game_dir)

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
    _create_test_source_snapshot(minimal_game_dir)

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
    _create_test_source_snapshot(minimal_game_dir)

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
async def test_written_game_reads_complete_origin_without_mutating_snapshot(minimal_game_dir: Path) -> None:
    """已有完整原始 data 备份时，后续写回不修改 `data_origin/`。"""
    _create_test_source_snapshot(minimal_game_dir)
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
