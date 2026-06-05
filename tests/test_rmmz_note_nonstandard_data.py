"""RPG Maker Note 与非标准 data 业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *

from app.native_note_tag_scan import collect_native_note_tag_hit_details, collect_native_note_tag_source_details
from app.note_tag_text.sources import collect_note_tag_sources, note_file_pattern_matches
from app.rmmz.text_rules import JsonArray
from app.text_scope.rule_hits import collect_note_tag_rule_hits


def _shadow_note_tag_rule_hit_tuples_from_native_details(
    *,
    native_hit_details: JsonArray,
    note_tag_rules: list[NoteTagTextRuleRecord],
) -> list[tuple[str, str, str, str]]:
    """用 native 逐命中明细模拟旧 Note 标签 text-scope 规则命中。"""
    hits: list[tuple[str, str, str, str]] = []
    seen_paths: set[str] = set()
    for rule in note_tag_rules:
        tag_names = set(rule.tag_names)
        for index, raw_hit in enumerate(native_hit_details):
            hit = ensure_json_object(raw_hit, f"native_note_tag_hit[{index}]")
            file_name = hit.get("file_name")
            tag_name = hit.get("tag_name")
            location_path = hit.get("location_path")
            original_text = hit.get("original_text")
            if not isinstance(file_name, str):
                raise TypeError(f"native_note_tag_hit[{index}].file_name 字段类型无效")
            if not isinstance(tag_name, str):
                raise TypeError(f"native_note_tag_hit[{index}].tag_name 字段类型无效")
            if not isinstance(location_path, str):
                raise TypeError(f"native_note_tag_hit[{index}].location_path 字段类型无效")
            if not isinstance(original_text, str):
                raise TypeError(f"native_note_tag_hit[{index}] 字段类型无效")
            if tag_name not in tag_names:
                continue
            if not note_file_pattern_matches(file_name=file_name, file_pattern=rule.file_name):
                continue
            if location_path in seen_paths:
                continue
            seen_paths.add(location_path)
            hits.append((location_path, "note_tag", "Note 标签规则", original_text))
    return hits


def _shadow_note_tag_translation_item_tuples_from_native_details(
    *,
    native_hit_details: JsonArray,
    rule_records: list[NoteTagTextRuleRecord],
) -> list[tuple[str, str, tuple[str, ...]]]:
    """用 native 逐命中明细模拟成功路径的 Note 标签正文提取。"""
    source_order: list[tuple[str, str]] = []
    hits_by_source_tag: dict[tuple[tuple[str, str], str], list[tuple[str, str, bool]]] = {}
    for index, raw_hit in enumerate(native_hit_details):
        hit = ensure_json_object(raw_hit, f"native_note_tag_extraction_hit[{index}]")
        file_name = hit.get("file_name")
        tag_name = hit.get("tag_name")
        location_path = hit.get("location_path")
        original_text = hit.get("original_text")
        translatable = hit.get("translatable")
        if not isinstance(file_name, str):
            raise TypeError(f"native_note_tag_extraction_hit[{index}].file_name 字段类型无效")
        if not isinstance(tag_name, str):
            raise TypeError(f"native_note_tag_extraction_hit[{index}].tag_name 字段类型无效")
        if not isinstance(location_path, str):
            raise TypeError(f"native_note_tag_extraction_hit[{index}].location_path 字段类型无效")
        if not isinstance(original_text, str):
            raise TypeError(f"native_note_tag_extraction_hit[{index}].original_text 字段类型无效")
        if not isinstance(translatable, bool):
            raise TypeError(f"native_note_tag_extraction_hit[{index}].translatable 字段类型无效")
        source_prefix = location_path.rsplit("/note/", maxsplit=1)[0]
        source_key = (file_name, source_prefix)
        if source_key not in source_order:
            source_order.append(source_key)
        hits_by_source_tag.setdefault((source_key, tag_name), []).append(
            (location_path, original_text, translatable)
        )

    items: list[tuple[str, str, tuple[str, ...]]] = []
    seen_location_paths: set[str] = set()
    for rule_record in rule_records:
        matching_sources = [
            source_key
            for source_key in source_order
            if note_file_pattern_matches(file_name=source_key[0], file_pattern=rule_record.file_name)
        ]
        if not matching_sources:
            raise RuntimeError(
                "native hit_details 不能单独证明规则文件模式仍命中当前游戏 note 字段"
            )
        tag_hit_counts = {tag_name: 0 for tag_name in rule_record.tag_names}
        for source_key in matching_sources:
            for tag_name in rule_record.tag_names:
                values = hits_by_source_tag.get((source_key, tag_name), [])
                if not values:
                    continue
                tag_hit_counts[tag_name] += len(values)
                if len(values) > 1:
                    raise ValueError(f"{source_key[1]}/note/{tag_name} 标签重复，无法生成唯一定位路径")
                location_path, original_text, translatable = values[0]
                if not translatable:
                    continue
                if location_path in seen_location_paths:
                    continue
                seen_location_paths.add(location_path)
                items.append((source_key[0], location_path, (original_text,)))
        for tag_name in rule_record.tag_names:
            if tag_hit_counts[tag_name] == 0:
                raise RuntimeError(
                    f"Note 标签规则已过期: {rule_record.file_name}/{tag_name} 没有命中当前游戏 Note 标签，请重新导出并导入 Note 标签规则"
                )
    return items


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
async def test_note_tag_rules_extract_and_write_back_only_target_values(minimal_game_dir: Path) -> None:
    """Note 标签只有导入规则后才进入正文提取，回写只替换目标标签值。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目\n二行目>\n<upgrade:1,2,3>\n<ExtendDesc:別説明>"
    _rewrite_json(items_path, raw_items)
    _create_test_source_snapshot(minimal_game_dir)

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
async def test_note_tag_extraction_rejects_stale_rule_without_current_tag(minimal_game_dir: Path) -> None:
    """Note 标签被移除后，已保存规则不能静默变成空命中。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:薬草の詳細説明>\n<upgrade:1,2,3>"
    _rewrite_json(items_path, raw_items)

    game_data = await load_game_data(minimal_game_dir)
    rule_records = build_note_tag_rule_records_from_import(
        game_data=game_data,
        import_file={"Items.json": ["拡張説明"]},
        text_rules=get_default_text_rules(),
    )
    item["note"] = "<upgrade:1,2,3>"
    _rewrite_json(items_path, raw_items)
    stale_game_data = await load_game_data(minimal_game_dir)

    with pytest.raises(RuntimeError, match="Note 标签规则已过期"):
        _ = NoteTagTextExtraction(
            game_data=stale_game_data,
            rule_records=rule_records,
            text_rules=get_default_text_rules(),
        ).extract_all_text()


@pytest.mark.asyncio
async def test_note_tag_rule_hits_expand_full_locations_and_normalized_text(minimal_game_dir: Path) -> None:
    """Note 标签 text-scope 命中必须保留完整定位、规范化原文和重复规则去重。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = (
        f"<拡張説明:{json.dumps('薬草の詳細', ensure_ascii=False)}>\n"
        "<ExtendDesc:別説明>\n"
        "<PrivateProtocol:内部コード>"
    )
    _rewrite_json(items_path, raw_items)

    game_data = await load_game_data(minimal_game_dir)
    hits = collect_note_tag_rule_hits(
        game_data=game_data,
        note_tag_rules=[
            NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"]),
            NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明", "ExtendDesc"]),
            NoteTagTextRuleRecord(file_name="Weapons.json", tag_names=["拡張説明"]),
        ],
        text_rules=get_default_text_rules(),
    )

    assert [
        (hit.location_path, hit.source_type, hit.rule_source, hit.original_text)
        for hit in hits
    ] == [
        ("Items.json/1/note/拡張説明", "note_tag", "Note 标签规则", "薬草の詳細"),
        ("Items.json/1/note/ExtendDesc", "note_tag", "Note 标签规则", "別説明"),
    ]


@pytest.mark.asyncio
async def test_native_note_tag_hit_details_can_shadow_text_scope_rule_hits(minimal_game_dir: Path) -> None:
    """native Note 标签逐命中明细必须足够复刻 text-scope 规则筛选和去重语义。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = (
        f"<拡張説明:{json.dumps('薬草の詳細', ensure_ascii=False)}>\n"
        "<拡張説明:二度目>\n"
        "<ExtendDesc:別説明>\n"
        "<PrivateProtocol:ABC>"
    )
    _rewrite_json(items_path, raw_items)

    map_path = minimal_game_dir / "data" / "Map001.json"
    raw_map = _read_test_json(map_path)
    map_object = ensure_json_object(raw_map, "Map001.json")
    events = ensure_json_array(map_object["events"], "Map001.json.events")
    event = ensure_json_object(events[2], "Map001.json.events[2]")
    event["note"] = "<namePop:案内人>"
    _rewrite_json(map_path, raw_map)

    game_data = await load_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()
    note_tag_rules = [
        NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"]),
        NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明", "ExtendDesc", "PrivateProtocol"]),
        NoteTagTextRuleRecord(file_name="Items*.json", tag_names=["ExtendDesc"]),
        NoteTagTextRuleRecord(file_name="Map001.json", tag_names=["namePop"]),
        NoteTagTextRuleRecord(file_name="Map*.json", tag_names=["namePop"]),
    ]

    python_hits = collect_note_tag_rule_hits(
        game_data=game_data,
        note_tag_rules=note_tag_rules,
        text_rules=text_rules,
    )
    native_hit_details = collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules)
    native_shadow_hits = _shadow_note_tag_rule_hit_tuples_from_native_details(
        native_hit_details=native_hit_details,
        note_tag_rules=note_tag_rules,
    )

    assert native_shadow_hits == [
        (hit.location_path, hit.source_type, hit.rule_source, hit.original_text)
        for hit in python_hits
    ]
    assert native_shadow_hits == [
        ("Items.json/1/note/拡張説明", "note_tag", "Note 标签规则", "薬草の詳細"),
        ("Items.json/1/note/ExtendDesc", "note_tag", "Note 标签规则", "別説明"),
        ("Items.json/1/note/PrivateProtocol", "note_tag", "Note 标签规则", "ABC"),
        ("Map001.json/events/2/note/namePop", "note_tag", "Note 标签规则", "案内人"),
    ]
    native_hit_objects = [
        ensure_json_object(hit, f"native hit {index}")
        for index, hit in enumerate(native_hit_details)
    ]
    assert [
        str(hit["location_path"])
        for hit in native_hit_objects
        if str(hit["location_path"]) == "Items.json/1/note/拡張説明"
    ] == [
        "Items.json/1/note/拡張説明",
        "Items.json/1/note/拡張説明",
    ]
    assert any(
        str(hit["tag_name"]) == "PrivateProtocol"
        and hit["translatable"] is False
        for hit in native_hit_objects
    )


@pytest.mark.asyncio
async def test_native_note_tag_hit_details_can_shadow_successful_note_tag_extraction(
    minimal_game_dir: Path,
) -> None:
    """native 明细必须足够复刻 NoteTagTextExtraction 的成功输出。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = (
        "<PrivateProtocol:ABC>\n"
        "<BlankValue:>\n"
        "<ExtendDesc:別説明>\n"
        f"<拡張説明:{json.dumps('薬草の詳細', ensure_ascii=False)}>"
    )
    _rewrite_json(items_path, raw_items)

    map_path = minimal_game_dir / "data" / "Map001.json"
    raw_map = _read_test_json(map_path)
    map_object = ensure_json_object(raw_map, "Map001.json")
    events = ensure_json_array(map_object["events"], "Map001.json.events")
    event = ensure_json_object(events[2], "Map001.json.events[2]")
    event["note"] = "<namePop:案内人>"
    _rewrite_json(map_path, raw_map)

    game_data = await load_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()
    rule_records = [
        NoteTagTextRuleRecord(
            file_name="Items.json",
            tag_names=["拡張説明", "PrivateProtocol", "BlankValue", "ExtendDesc"],
        ),
        NoteTagTextRuleRecord(file_name="Map*.json", tag_names=["namePop"]),
    ]

    note_extracted = NoteTagTextExtraction(
        game_data=game_data,
        rule_records=rule_records,
        text_rules=text_rules,
    ).extract_all_text()
    native_hit_details = collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules)

    actual_items = [
        (file_name, item.location_path, tuple(item.original_lines))
        for file_name, data in note_extracted.items()
        for item in data.translation_items
    ]
    shadow_items = _shadow_note_tag_translation_item_tuples_from_native_details(
        native_hit_details=native_hit_details,
        rule_records=rule_records,
    )

    assert shadow_items == actual_items
    assert shadow_items == [
        ("Items.json", "Items.json/1/note/拡張説明", ("薬草の詳細",)),
        ("Items.json", "Items.json/1/note/ExtendDesc", ("別説明",)),
        ("Map001.json", "Map001.json/events/2/note/namePop", ("案内人",)),
    ]
    native_hit_objects = [
        ensure_json_object(hit, f"native extraction hit {index}")
        for index, hit in enumerate(native_hit_details)
    ]
    assert any(
        str(hit["tag_name"]) == "PrivateProtocol"
        and hit["translatable"] is False
        for hit in native_hit_objects
    )
    assert any(
        str(hit["tag_name"]) == "BlankValue"
        and hit["translatable"] is False
        for hit in native_hit_objects
    )


@pytest.mark.asyncio
async def test_native_note_tag_hit_details_expose_duplicate_locations_for_extraction_error(
    minimal_game_dir: Path,
) -> None:
    """native 明细必须保留 NoteTagTextExtraction 重复标签错误所需事实。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一度目>\n<拡張説明:二度目>"
    _rewrite_json(items_path, raw_items)

    game_data = await load_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()
    rule_records = [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
    native_hit_details = collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules)

    with pytest.raises(ValueError, match="タグ重复|标签重复"):
        _ = NoteTagTextExtraction(
            game_data=game_data,
            rule_records=rule_records,
            text_rules=text_rules,
        ).extract_all_text()
    with pytest.raises(ValueError, match="标签重复"):
        _ = _shadow_note_tag_translation_item_tuples_from_native_details(
            native_hit_details=native_hit_details,
            rule_records=rule_records,
        )

    duplicate_locations = [
        str(ensure_json_object(hit, "native duplicate hit")["location_path"])
        for hit in native_hit_details
        if ensure_json_object(hit, "native duplicate hit").get("location_path")
        == "Items.json/1/note/拡張説明"
    ]
    assert duplicate_locations == [
        "Items.json/1/note/拡張説明",
        "Items.json/1/note/拡張説明",
    ]


@pytest.mark.asyncio
async def test_native_note_tag_source_details_prove_matching_sources_without_value_hits(
    minimal_game_dir: Path,
) -> None:
    """native 来源摘要必须覆盖没有带值标签命中的 note 来源。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = _read_test_json(items_path)
    items = ensure_json_array(raw_items, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<MarkerOnly>"
    _rewrite_json(items_path, raw_items)

    map_path = minimal_game_dir / "data" / "Map001.json"
    raw_map = _read_test_json(map_path)
    map_object = ensure_json_object(raw_map, "Map001.json")
    events = ensure_json_array(map_object["events"], "Map001.json.events")
    event = ensure_json_object(events[2], "Map001.json.events[2]")
    event["note"] = "<MapMarkerOnly>"
    _rewrite_json(map_path, raw_map)

    game_data = await load_game_data(minimal_game_dir)
    text_rules = get_default_text_rules()
    python_source_pairs = [
        (source.file_name, source.location_prefix)
        for source in collect_note_tag_sources(game_data=game_data)
    ]
    native_source_details = collect_native_note_tag_source_details(game_data=game_data, text_rules=text_rules)
    native_source_pairs = [
        (
            str(ensure_json_object(source, f"native source {index}")["file_name"]),
            str(ensure_json_object(source, f"native source {index}")["location_prefix"]),
        )
        for index, source in enumerate(native_source_details)
    ]
    native_hit_details = collect_native_note_tag_hit_details(game_data=game_data, text_rules=text_rules)

    assert native_source_pairs == python_source_pairs
    assert ("Items.json", "Items.json/1") in native_source_pairs
    assert ("Map001.json", "Map001.json/events/2") in native_source_pairs
    assert all(
        ensure_json_object(source, f"native source {index}").keys() == {"file_name", "location_prefix"}
        for index, source in enumerate(native_source_details)
    )
    assert not any(
        str(ensure_json_object(hit, f"native marker hit {index}")["location_path"]).startswith(
            "Items.json/1/note/MarkerOnly"
        )
        or str(ensure_json_object(hit, f"native marker hit {index}")["location_path"]).startswith(
            "Map001.json/events/2/note/MapMarkerOnly"
        )
        for index, hit in enumerate(native_hit_details)
    )


@pytest.mark.asyncio
async def test_note_tag_rule_hits_use_native_details_without_python_note_scan(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签 text-scope 命中必须消费 native 明细，不再重复 Python 扫描 Note。"""
    from app.text_scope import rule_hits

    native_hit_details: JsonArray = [
        {
            "file_name": "Items.json",
            "tag_name": "拡張説明",
            "location_path": "Items.json/1/note/拡張説明",
            "original_text": "薬草の詳細",
            "translatable": True,
        },
        {
            "file_name": "Items.json",
            "tag_name": "拡張説明",
            "location_path": "Items.json/1/note/拡張説明",
            "original_text": "二度目",
            "translatable": True,
        },
        {
            "file_name": "Items.json",
            "tag_name": "PrivateProtocol",
            "location_path": "Items.json/1/note/PrivateProtocol",
            "original_text": "ABC",
            "translatable": False,
        },
        {
            "file_name": "Items.json",
            "tag_name": "BlankValue",
            "location_path": "Items.json/1/note/BlankValue",
            "original_text": "",
            "translatable": False,
        },
        {
            "file_name": "Map001.json",
            "tag_name": "namePop",
            "location_path": "Map001.json/events/2/note/namePop",
            "original_text": "案内人",
            "translatable": True,
        },
    ]

    def forbidden_collect_note_tag_sources(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("collect_note_tag_rule_hits 不应再调用 Python collect_note_tag_sources")

    def forbidden_iter_note_tag_matches(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("collect_note_tag_rule_hits 不应再调用 Python iter_note_tag_matches")

    def fake_collect_native_note_tag_hit_details(*args: object, **kwargs: object) -> JsonArray:
        _ = (args, kwargs)
        return native_hit_details

    monkeypatch.setattr(rule_hits, "collect_note_tag_sources", forbidden_collect_note_tag_sources, raising=False)
    monkeypatch.setattr(rule_hits, "iter_note_tag_matches", forbidden_iter_note_tag_matches, raising=False)
    monkeypatch.setattr(
        rule_hits,
        "collect_native_note_tag_hit_details",
        fake_collect_native_note_tag_hit_details,
        raising=False,
    )

    game_data = await load_game_data(minimal_game_dir)
    hits = collect_note_tag_rule_hits(
        game_data=game_data,
        note_tag_rules=[
            NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"]),
            NoteTagTextRuleRecord(file_name="Items*.json", tag_names=["PrivateProtocol", "BlankValue"]),
            NoteTagTextRuleRecord(file_name="Map001.json", tag_names=["namePop"]),
            NoteTagTextRuleRecord(file_name="Map*.json", tag_names=["namePop"]),
        ],
        text_rules=get_default_text_rules(),
    )

    assert [
        (hit.location_path, hit.source_type, hit.rule_source, hit.original_text)
        for hit in hits
    ] == [
        ("Items.json/1/note/拡張説明", "note_tag", "Note 标签规则", "薬草の詳細"),
        ("Items.json/1/note/PrivateProtocol", "note_tag", "Note 标签规则", "ABC"),
        ("Items.json/1/note/BlankValue", "note_tag", "Note 标签规则", ""),
        ("Map001.json/events/2/note/namePop", "note_tag", "Note 标签规则", "案内人"),
    ]


@pytest.mark.asyncio
async def test_note_tag_extraction_uses_native_details_without_python_note_scan(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签正文提取必须消费同一次 native 来源和命中明细。"""
    from app.note_tag_text import extraction as extraction_module

    native_source_details: JsonArray = [
        {"file_name": "Items.json", "location_prefix": "Items.json/1"},
        {"file_name": "Map001.json", "location_prefix": "Map001.json/events/2"},
    ]
    native_hit_details: JsonArray = [
        {
            "file_name": "Items.json",
            "tag_name": "PrivateProtocol",
            "location_path": "Items.json/1/note/PrivateProtocol",
            "original_text": "ABC",
            "translatable": False,
        },
        {
            "file_name": "Items.json",
            "tag_name": "BlankValue",
            "location_path": "Items.json/1/note/BlankValue",
            "original_text": "",
            "translatable": False,
        },
        {
            "file_name": "Items.json",
            "tag_name": "ExtendDesc",
            "location_path": "Items.json/1/note/ExtendDesc",
            "original_text": "別説明",
            "translatable": True,
        },
        {
            "file_name": "Items.json",
            "tag_name": "拡張説明",
            "location_path": "Items.json/1/note/拡張説明",
            "original_text": "薬草の詳細",
            "translatable": True,
        },
        {
            "file_name": "Map001.json",
            "tag_name": "namePop",
            "location_path": "Map001.json/events/2/note/namePop",
            "original_text": "案内人",
            "translatable": True,
        },
    ]
    native_call_count = 0

    def forbidden_collect_note_tag_sources(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("NoteTagTextExtraction 不应再调用 Python collect_note_tag_sources")

    def forbidden_iter_note_tag_matches(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("NoteTagTextExtraction 不应再调用 Python iter_note_tag_matches")

    def fake_collect_native_note_tag_extraction_details(
        *args: object,
        **kwargs: object,
    ) -> tuple[JsonArray, JsonArray]:
        nonlocal native_call_count
        _ = (args, kwargs)
        native_call_count += 1
        return native_source_details, native_hit_details

    monkeypatch.setattr(extraction_module, "collect_note_tag_sources", forbidden_collect_note_tag_sources, raising=False)
    monkeypatch.setattr(extraction_module, "iter_note_tag_matches", forbidden_iter_note_tag_matches, raising=False)
    monkeypatch.setattr(
        extraction_module,
        "collect_native_note_tag_extraction_details",
        fake_collect_native_note_tag_extraction_details,
        raising=False,
    )

    game_data = await load_game_data(minimal_game_dir)
    extracted = NoteTagTextExtraction(
        game_data=game_data,
        rule_records=[
            NoteTagTextRuleRecord(
                file_name="Items*.json",
                tag_names=["拡張説明", "PrivateProtocol", "BlankValue", "ExtendDesc"],
            ),
            NoteTagTextRuleRecord(file_name="Map*.json", tag_names=["namePop"]),
        ],
        text_rules=get_default_text_rules(),
    ).extract_all_text()

    assert native_call_count == 1
    assert [
        (file_name, item.location_path, tuple(item.original_lines))
        for file_name, data in extracted.items()
        for item in data.translation_items
    ] == [
        ("Items.json", "Items.json/1/note/拡張説明", ("薬草の詳細",)),
        ("Items.json", "Items.json/1/note/ExtendDesc", ("別説明",)),
        ("Map001.json", "Map001.json/events/2/note/namePop", ("案内人",)),
    ]


@pytest.mark.asyncio
async def test_note_tag_extraction_native_details_keep_duplicate_error_before_filter(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native 薄适配仍必须先报重复标签，再执行不可翻译过滤。"""
    from app.note_tag_text import extraction as extraction_module

    native_source_details: JsonArray = [{"file_name": "Items.json", "location_prefix": "Items.json/1"}]
    native_hit_details: JsonArray = [
        {
            "file_name": "Items.json",
            "tag_name": "PrivateProtocol",
            "location_path": "Items.json/1/note/PrivateProtocol",
            "original_text": "ABC",
            "translatable": False,
        },
        {
            "file_name": "Items.json",
            "tag_name": "PrivateProtocol",
            "location_path": "Items.json/1/note/PrivateProtocol",
            "original_text": "DEF",
            "translatable": False,
        },
    ]

    def forbidden_collect_note_tag_sources(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("NoteTagTextExtraction 不应再调用 Python collect_note_tag_sources")

    def forbidden_iter_note_tag_matches(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("NoteTagTextExtraction 不应再调用 Python iter_note_tag_matches")

    def fake_collect_native_note_tag_extraction_details(
        *args: object,
        **kwargs: object,
    ) -> tuple[JsonArray, JsonArray]:
        _ = (args, kwargs)
        return native_source_details, native_hit_details

    monkeypatch.setattr(extraction_module, "collect_note_tag_sources", forbidden_collect_note_tag_sources, raising=False)
    monkeypatch.setattr(extraction_module, "iter_note_tag_matches", forbidden_iter_note_tag_matches, raising=False)
    monkeypatch.setattr(
        extraction_module,
        "collect_native_note_tag_extraction_details",
        fake_collect_native_note_tag_extraction_details,
        raising=False,
    )

    game_data = await load_game_data(minimal_game_dir)
    with pytest.raises(ValueError, match="标签重复"):
        _ = NoteTagTextExtraction(
            game_data=game_data,
            rule_records=[NoteTagTextRuleRecord(file_name="Items.json", tag_names=["PrivateProtocol"])],
            text_rules=get_default_text_rules(),
        ).extract_all_text()
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
    note_items[0].translation_lines = ["说明\n「甲乙，丙丁」"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [note_items[0]], text_rules)

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
    note_items[0].translation_lines = [translated_note.strip()]
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
    _create_test_source_snapshot(minimal_game_dir)

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
