"""RPG Maker Note 与非标准 data 业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *


async def _load_current_runtime_game_data(game_dir: Path) -> GameData:
    """按当前运行视图加载测试游戏数据。"""
    return await load_active_runtime_game_data(
        game_dir,
        include_plugin_source_files=True,
        include_writable_copies=True,
        run_dialogue_probe_check=True,
    )


def _note_tag_translation_item_for_test(location_path: str, original_text: str) -> TranslationItem:
    """由当前 Note 标签定位路径构造测试写回项，避免恢复旧 Python 提取入口。"""
    return TranslationItem(
        location_path=location_path,
        item_type="short_text",
        original_lines=[original_text],
        source_line_paths=[location_path],
    )


@pytest.mark.asyncio
async def test_native_write_back_helper_nonstandard_data_audit_skips_game_data_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只有非标准 data 规则时，写后审计不应加载全量当前运行视图。"""
    session = _NativePlanSessionStub(tmp_path)
    (session.content_root / "data").mkdir(parents=True)
    (session.content_root / "js").mkdir(parents=True)
    _ = (session.content_root / "js" / "plugins.js").write_text("[]", encoding="utf-8")
    session.nonstandard_data_rules = [
        NonstandardDataTextRuleRecord(
            file_name="Extra.json",
            file_hash="source-hash",
            path_templates=["$.name"],
        )
    ]
    statuses: list[str] = []
    audited_rules: list[NonstandardDataTextRuleRecord] = []

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """返回没有插件源码映射的最小 Rust 写回计划。"""
        assert kwargs["mode"] == "write_back"
        return NativeWriteBackPlan(
            files=[
                NativePlannedFile(
                    target_path=session.content_root / "data" / "System.json",
                    relative_path="data/System.json",
                    content="{\"gameTitle\":\"测试\"}\n",
                )
            ],
            plugin_source_runtime_write_maps=[],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=1,
                plugin_item_count=0,
                terminology_written_count=0,
                target_font_name=None,
                source_font_count=0,
                replaced_font_reference_count=0,
                font_copied=False,
                planned_file_count=1,
                skipped_file_count=0,
            ),
            timings_ms={"total": 1},
        )

    def fake_apply_files(self: WritePlanApplier, plan: RuntimeWritePlan) -> None:
        """测试中不实际替换文件。"""
        _ = (self, plan)

    async def fake_load_active_runtime_game_data(game_path: Path, **kwargs: object) -> GameData:
        """非标准 data 审计只需要 layout，不应加载 GameData。"""
        _ = (game_path, kwargs)
        raise AssertionError("只有非标准 data 规则时不应加载当前运行视图")

    def fake_audit_active_runtime_plugin_source_with_scan_cache(
        *args: object,
        **kwargs: object,
    ) -> NoReturn:
        """没有插件源码映射时不应执行插件源码审计。"""
        _ = (args, kwargs)
        raise AssertionError("没有插件源码映射时不应执行插件源码审计")

    def fake_audit_active_runtime_nonstandard_data(
        *,
        layout: object,
        rule_records: list[NonstandardDataTextRuleRecord],
        text_rules: TextRules,
    ) -> ActiveRuntimeNonstandardDataAudit:
        """记录非标准 data 审计输入。"""
        _ = text_rules
        assert getattr(layout, "content_root") == session.content_root
        audited_rules.extend(rule_records)
        return ActiveRuntimeNonstandardDataAudit(
            issues=(),
            audit_enabled=True,
            file_count=1,
            skipped_file_count=0,
            managed_path_count=1,
        )

    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)
    monkeypatch.setattr("app.application.handler.WritePlanApplier.apply_files", fake_apply_files)
    monkeypatch.setattr("app.application.handler.load_active_runtime_game_data", fake_load_active_runtime_game_data)
    monkeypatch.setattr(
        "app.application.handler.audit_active_runtime_plugin_source_with_scan_cache",
        fake_audit_active_runtime_plugin_source_with_scan_cache,
    )
    monkeypatch.setattr("app.application.handler.audit_active_runtime_nonstandard_data", fake_audit_active_runtime_nonstandard_data)

    handler = TranslationHandler(GameRegistry(tmp_path / "db"), LLMHandler())
    try:
        _ = await handler.write_runtime_files_with_native_plan(
            session=cast(TargetGameSession, cast(object, session)),
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None, statuses.append),
            setting=cast(
                Setting,
                cast(
                    object,
                    SimpleNamespace(
                        text_rules=TextRulesSetting(),
                        write_back=WriteBackSetting(),
                    ),
                ),
            ),
            text_rules=TextRules.from_setting(TextRulesSetting()),
            mode="write_back",
            writable_location_paths=[],
            confirm_font_overwrite=False,
            success_phase="游戏文本回写完成",
        )
    finally:
        await handler.close()

    assert audited_rules == session.nonstandard_data_rules
    assert statuses[-2:] == ["审计写入后的当前运行文件", "保存写入诊断映射"]
    assert session.runtime_map_replace_calls == 1
    assert session.runtime_map_replace_count == 0
@pytest.mark.asyncio
async def test_note_tag_write_back_only_target_values(minimal_game_dir: Path) -> None:
    """Note 标签写回只替换目标标签值，不进入标准正文提取。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目\n二行目>\n<upgrade:1,2,3>\n<ExtendDesc:別説明>"
    _rewrite_json(items_path, raw_items)
    _create_test_source_snapshot(minimal_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_game_dir)
    standard_extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    standard_paths = {
        candidate.location_path
        for data in standard_extracted.values()
        for candidate in data.translation_items
    }
    note_items = [
        _note_tag_translation_item_for_test("Items.json/1/note/拡張説明", "一行目\n二行目"),
        _note_tag_translation_item_for_test("Items.json/1/note/ExtendDesc", "別説明"),
    ]

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
    _create_test_source_snapshot(minimal_game_dir)
    text_rules = TextRules.from_setting(
        TextRulesSetting(
            long_text_line_width_limit=8,
            line_split_punctuations=["，", "。"],
        )
    )

    game_data = await _load_current_runtime_game_data(minimal_game_dir)
    note_item = _note_tag_translation_item_for_test(
        "Items.json/1/note/拡張説明",
        "説明\n「原文」",
    )
    note_item.translation_lines = ["说明\n「甲乙，丙丁」"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [note_item], text_rules)

    writable_items = ensure_json_array(game_data.writable_data["Items.json"], "Items.json")
    writable_item = ensure_json_object(writable_items[1], "Items.json[1]")
    assert writable_item["note"] == "<拡張説明:说明\n「甲乙，丙丁」>"


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
    _create_test_source_snapshot(minimal_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_game_dir)
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

    _ = build_note_tag_rule_records_from_import(
        game_data=game_data,
        import_file={"Items.json": ["拡張説明"]},
        text_rules=get_default_text_rules(),
    )
    note_item = _note_tag_translation_item_for_test(
        "Items.json/1/note/拡張説明",
        source_note.strip(),
    )
    assert note_item.original_lines == [source_note.strip()]

    translated_note = "\n　" + r"\C[2]详细说明\C[0]\n下一行" + "　\n"
    note_item.translation_lines = [translated_note.strip()]
    reset_writable_copies(game_data)
    write_data_text(game_data, [note_item])

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
    _create_test_source_snapshot(minimal_game_dir)

    game_data = await _load_current_runtime_game_data(minimal_game_dir)
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

    _ = build_note_tag_rule_records_from_import(
        game_data=game_data,
        import_file={"Map*.json": ["namePop"]},
        text_rules=get_default_text_rules(),
    )
    note_item = _note_tag_translation_item_for_test(
        "Map001.json/events/2/note/namePop",
        "導き手",
    )

    assert note_item.location_path == "Map001.json/events/2/note/namePop"
    assert note_item.original_lines == ["導き手"]

    note_item.translation_lines = ["引导者"]
    reset_writable_copies(game_data)
    write_data_text(game_data, [note_item])
    writable_map = ensure_json_object(game_data.writable_data["Map001.json"], "Map001.json")
    writable_events = ensure_json_array(writable_map["events"], "Map001.json.events")
    writable_event = ensure_json_object(writable_events[2], "Map001.json.events[2]")

    assert writable_event["note"] == "<namePop:引导者>\n<machine:1>"
