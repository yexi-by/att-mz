"""RPG Maker MV 名字框业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *
from tests.current_text_fact_scope import read_current_text_fact_scope_for_test

from app.agent_toolkit import AgentToolkitService
from app.persistence.records import TextFactReadFilter
from app.rmmz.mv_namebox import parse_mv_virtual_namebox_rule_import_text


async def _load_current_runtime_game_data(game_dir: Path) -> GameData:
    """按当前运行视图加载测试游戏数据。"""
    return await load_active_runtime_game_data(
        game_dir,
        include_plugin_source_files=True,
        include_writable_copies=True,
        run_dialogue_probe_check=True,
    )


def test_mv_virtual_namebox_rule_import_accepts_current_pcre2_capture() -> None:
    """MV 虚拟名字框规则导入接受 PCRE2 当前命名捕获写法。"""
    records = parse_mv_virtual_namebox_rule_import_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "colon-name",
                        "pattern": "^(?<speaker>[^：]+)：$",
                        "speaker_group": "speaker",
                        "speaker_policy": "translate",
                        "render_template": "{speaker}：",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    assert records[0].speaker_group == "speaker"


@pytest.mark.asyncio
async def test_mv_outer_layout_loads_www_data_and_system_title(minimal_mv_game_dir: Path) -> None:
    """MV 外层目录布局会定位到 www 内容目录，并用 System 标题兜底注册。"""
    layout = resolve_game_layout(minimal_mv_game_dir)
    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)

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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/2/0"
    )

    assert item.role == "旁白"
    assert item.original_lines == ["案内人：", "次の本文です"]


@pytest.mark.asyncio
async def test_native_rebuild_persists_mv_virtual_namebox_v2_fact_split(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷重建保存 MV 虚拟名字框 raw/render/translatable 三层事实。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 91,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": [r"  \n<Dan:> Hello  "]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="en")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_mv_virtual_namebox_rules(
            [
                MvVirtualNameboxRuleRecord(
                    rule_order=0,
                    rule_name="yep-namebox-with-colon",
                    pattern_text=r"^\\n<(?P<speaker>[^:>\r\n]+):> (?P<body>.*)$",
                    speaker_group="speaker",
                    body_group="body",
                    speaker_policy="translate",
                    render_template=r"\n<{speaker}:> {body}",
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"
    scope_key = str(report.summary["scope_key"])

    async with await registry.open_game(record.game_title) as session:
        _ = await session.require_current_text_fact_scope(scope_key)
        facts = await session.read_text_facts(
            TextFactReadFilter(scope_key=scope_key, domain="mv_virtual_namebox")
        )
        assert len(facts) == 1
        fact = facts[0]
        assert fact.raw_text == r"  \n<Dan:> Hello  "
        assert fact.visible_text == r"  \n<Dan:> Hello  "
        assert fact.translatable_text == "Hello"
        assert fact.role == "Dan"
        parts = await session.read_text_fact_render_parts([fact.fact_id])

    assert [part.part_kind for part in parts] == [
        "literal",
        "speaker",
        "literal",
        "translated_body",
        "literal",
    ]
    assert "".join(part.raw_text for part in parts) == r"  \n<Dan:> Hello  "


@pytest.mark.asyncio
async def test_native_rebuild_persists_mv_virtual_namebox_v2_fact_for_standalone_speaker(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷重建把独立 speaker 行和下一行正文保存为 MV 虚拟名字框 fact。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 92,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["  <受付>  "]},
                {"code": 401, "parameters": ["独立行の本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_mv_virtual_namebox_rules(
            [
                MvVirtualNameboxRuleRecord(
                    rule_order=0,
                    rule_name="angle-standalone",
                    pattern_text=r"^<(?P<speaker>[^\\<>\r\n]{1,80})>\s*$",
                    speaker_group="speaker",
                    body_group="",
                    speaker_policy="translate",
                    render_template="<{speaker}>",
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"
    scope_key = str(report.summary["scope_key"])

    async with await registry.open_game(record.game_title) as session:
        facts = await session.read_text_facts(
            TextFactReadFilter(scope_key=scope_key, domain="mv_virtual_namebox")
        )
        assert len(facts) == 1
        fact = facts[0]
        assert fact.raw_text == "  <受付>  \n独立行の本文です"
        assert fact.visible_text == "  <受付>  \n独立行の本文です"
        assert fact.translatable_text == "独立行の本文です"
        assert fact.role == "受付"
        parts = await session.read_text_fact_render_parts([fact.fact_id])

        rows = await session.read_text_index_items()
        row = next(item for item in rows if item.location_path == fact.location_path)

    assert row.source_line_paths == ["CommonEvents.json/92/2"]
    assert [part.part_kind for part in parts] == [
        "literal",
        "speaker",
        "literal",
        "translated_body",
    ]
    assert "".join(part.raw_text for part in parts) == "  <受付>  \n独立行の本文です"


@pytest.mark.asyncio
async def test_native_rebuild_weak_mv_namebox_rule_splits_colon_inside_angle_speaker(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """既有 YEP 弱规则应自动拆分 <Name:> Body，不要求 Agent 另写 separator 规则。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 93,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": [r"\n<Dan:> Hello"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="en")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_mv_virtual_namebox_rules(_mv_virtual_namebox_rule_records())

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"
    scope_key = str(report.summary["scope_key"])

    async with await registry.open_game(record.game_title) as session:
        facts = await session.read_text_facts(
            TextFactReadFilter(scope_key=scope_key, domain="mv_virtual_namebox")
        )
        fact = next(item for item in facts if item.location_path == "CommonEvents.json/93/0")
        parts = await session.read_text_fact_render_parts([fact.fact_id])

    assert fact.raw_text == r"\n<Dan:> Hello"
    assert fact.role == "Dan"
    assert fact.translatable_text == "Hello"
    assert "".join(part.raw_text for part in parts) == r"\n<Dan:> Hello"


@pytest.mark.asyncio
async def test_validate_mv_namebox_rules_rejects_empty_speaker_after_weak_split(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """弱拆分后 speaker 为空的异常候选必须报错，不能导入成空说话人。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    common_events.append(
        {
            "id": 94,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": [r"\n<:> Body"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _rewrite_json(common_events_path, common_events)
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_mv_virtual_namebox_rules(
        game_title=record.game_title,
        rules_text=json.dumps(
            {
                "rules": [
                    {
                        "name": "weak-yep",
                        "pattern": r"^(?P<command>\\(?:[Nn](?:[CcRr])?|[Rr]))<(?P<speaker>[^>\r\n]{0,80})>(?P<body>.*)$",
                        "speaker_group": "speaker",
                        "body_group": "body",
                        "speaker_policy": "translate",
                        "render_template": r"{command}<{speaker}>{body}",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    assert "mv_virtual_namebox_rules_invalid" in {error.code for error in report.errors}
    assert "空说话人" in " ".join(error.message for error in report.errors)


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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
async def test_native_write_back_rebuilds_mv_virtual_name_box_runtime_files(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实写回入口用 Rust 计划重建 MV 虚拟名字框运行文件。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

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
                    {"code": 401, "parameters": ["\\N[1]:役者の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
        ]
    )
    _rewrite_json(common_events_path, common_events)

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    async with await registry.open_game("MVテストゲーム") as session:
        await session.replace_mv_virtual_namebox_rules(_mv_virtual_namebox_rule_records())
        _game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_mv_game_dir,
            registry=TerminologyRegistry(
                speaker_names={"案内人": "向导", "MV勇者": "勇者"},
            ),
            glossary=TerminologyGlossary(terms={"案内人": "向导", "MV勇者": "勇者"}),
        )
        scope = await read_current_text_fact_scope_for_test(session=session)
        custom_translations = {
            "CommonEvents.json/2/0": ["你好"],
            "CommonEvents.json/3/0": ["你好」"],
            "CommonEvents.json/4/0": ["勇者正文"],
        }
        await write_current_translation_items_for_test(
            session,
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=custom_translations.get(
                        item.location_path,
                        [
                            _translated_test_line_preserving_controls(line, text_rules)
                            for line in item.original_lines
                        ],
                    ),
                )
                for item in scope.active_items()
            ]
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_back(
            game_title="MVテストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    written_events = ensure_json_array(_read_test_json(common_events_path), "CommonEvents.json")
    standalone_commands = ensure_json_array(
        ensure_json_object(written_events[2], "CommonEvents[2]")["list"],
        "CommonEvents[2].list",
    )
    inline_commands = ensure_json_array(
        ensure_json_object(written_events[3], "CommonEvents[3]")["list"],
        "CommonEvents[3].list",
    )
    actor_commands = ensure_json_array(
        ensure_json_object(written_events[4], "CommonEvents[4]")["list"],
        "CommonEvents[4].list",
    )

    assert summary.data_item_count >= 3
    assert ensure_json_array(ensure_json_object(standalone_commands[1], "standalone.speaker")["parameters"], "standalone.speaker.parameters")[0] == "向导："
    assert ensure_json_array(ensure_json_object(standalone_commands[2], "standalone.body")["parameters"], "standalone.body.parameters")[0] == "你好"
    assert ensure_json_array(ensure_json_object(inline_commands[1], "inline.speaker")["parameters"], "inline.speaker.parameters")[0] == "向导「你好」"
    assert ensure_json_array(ensure_json_object(actor_commands[1], "actor.speaker")["parameters"], "actor.speaker.parameters")[0] == "勇者:勇者正文"
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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
    assert "MV 译文正文仍包含说话人前缀" in message
    assert "CommonEvents.json/2/0" in message
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
    _create_test_source_snapshot(minimal_mv_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
@pytest.mark.asyncio
async def test_mv_write_back_uses_www_active_and_origin_paths(minimal_mv_game_dir: Path) -> None:
    """MV 外层目录写回只触碰 www 内的 data 和 plugins.js。"""
    _create_test_source_snapshot(minimal_mv_game_dir)
    game_data = await _load_current_runtime_game_data(minimal_mv_game_dir)
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
