"""Agent 手动导入、修复表和重置业务契约测试。"""

from __future__ import annotations

from dataclasses import replace

from tests.agent_toolkit_contract_fixtures import *
from app.persistence.records import TextFactReadFilter
from app.rmmz.schema import ItemType
from app.text_facts import read_current_text_fact_scope
from app.text_fact_readers import read_writable_text_fact_translation_items_by_paths


async def _current_fact_id_for_path(session: TargetGameSession, location_path: str) -> str:
    """读取测试路径对应的 current fact_id。"""
    async with session.connection.execute(
        "SELECT fact_id FROM text_facts WHERE location_path = ? ORDER BY fact_id LIMIT 1",
        (location_path,),
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return cast(str, row["fact_id"])


def _quality_fix_template_entry_by_text_position(
    template: dict[str, object],
    text_position: str,
) -> JsonObject:
    """按显示位置读取 fact-id keyed 质量修复模板条目。"""
    for raw_entry in template.values():
        entry = ensure_json_object(coerce_json_value(raw_entry), text_position)
        if entry.get("text_position") == text_position:
            return entry
    raise AssertionError(f"质量修复模板缺少文本位置: {text_position}")


@pytest.mark.asyncio
async def test_export_quality_fix_template_stops_on_text_scope_blocker(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量修复表暴露当前索引写回能力字段。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "quality-fix.json"

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=output_path,
        include_write_probe=True,
    )

    assert report.status in {"ok", "warning", "error"}
    assert "coverage_unwritable" not in {error.code for error in report.errors}
    assert "write_probe_failed" not in {error.code for error in report.errors}
    assert report.summary["write_back_probe_requested"] is True
    assert report.summary["write_back_probe_executed"] is False
    assert report.summary["write_back_probe_mode"] == "index_writable"
    assert report.summary["write_back_probe_enabled"] is False
@pytest.mark.asyncio
async def test_english_profile_exports_visible_pending_text_without_protocol_noise(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """英文档案能提取玩家可见英文，并跳过资源路径、公式和布尔值。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-english.json"
    workspace_path = tmp_path / "workspace"

    async with await registry.open_game("English Fixture Game") as session:
        game_data = await load_active_runtime_game_data(session.game_path)
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="VisiblePlugin",
                    plugin_hash=build_plugin_hash(game_data.plugins_js[0]),
                    path_templates=[
                        "$['parameters']['Message']",
                        "$['parameters']['Title']",
                        "$['parameters']['Image']",
                        "$['parameters']['Formula']",
                        "$['parameters']['Enabled']",
                    ],
                )
            ]
        )

    workspace_report = await service.prepare_agent_workspace(
        game_title="English Fixture Game",
        output_dir=workspace_path,
        command_codes=None,
    )
    export_report = await service.export_pending_translations(
        game_title="English Fixture Game",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    exported_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        exported_lines.extend(
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        )

    assert workspace_report.status in {"ok", "warning"}
    assert workspace_report.summary["source_language"] == "en"
    assert export_report.status == "ok"
    assert "Are you really going in there?" in exported_lines
    assert "Open the door" in exported_lines
    assert "Welcome to the old gate." in exported_lines
    assert "Gate Menu" in exported_lines
    assert "img/pictures/Gate.png" not in exported_lines
    assert "a.hpRate() >= 0.5" not in exported_lines
    assert "true" not in exported_lines
@pytest.mark.asyncio
async def test_build_placeholder_rules_requires_manual_boundary_for_joined_control_text(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """英文正文紧贴无参数控制符时，草稿不自动猜测短前缀。"""
    common_events_path = minimal_english_game_dir / "data" / "CommonEvents.json"
    raw_value = coerce_json_value(cast(object, json.loads(common_events_path.read_text(encoding="utf-8"))))
    common_events = ensure_json_array(raw_value, "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands[1:1] = [
        {"code": 401, "parameters": [r"\ShakeStop this!!!"]},
        {"code": 401, "parameters": [r"\ShakeNo, NO!!!"]},
        {"code": 401, "parameters": [r"\ShakeAhhh..."]},
        {"code": 401, "parameters": [r"\FXStop this!!!"]},
        {"code": 401, "parameters": [r"\ScreenShake"]},
        {"code": 401, "parameters": [r"\ScreenFlash"]},
    ]
    _ = common_events_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="English Fixture Game", output_path=output_path)
    rules = load_json_object(output_path)
    warning_codes = {warning.code for warning in report.warnings}
    manual_coverage_report = await service.scan_placeholder_candidates(
        game_title="English Fixture Game",
        custom_placeholder_rules_text=json.dumps(
            {r"\\Shake": "[CUSTOM_PLUGIN_SHAKE_MARKER_{index}]"},
            ensure_ascii=False,
        ),
    )
    manual_coverage_json = manual_coverage_report.to_json_text()

    assert report.status == "warning"
    assert rules == {}
    assert report.summary["manual_boundary_candidate_count"] == 6
    assert report.summary["uncovered_count_after_draft_preview"] == report.summary["uncovered_count_before_draft"]
    assert "placeholder_boundary_needs_review" in warning_codes
    assert r"\Screen" not in json.dumps(rules, ensure_ascii=False)
    assert r"\FXStop" not in json.dumps(rules, ensure_ascii=False)
    assert manual_coverage_report.summary["uncovered_count"] == 3
    assert r"\ShakeStop" not in manual_coverage_json
    assert r"\Shake" in manual_coverage_json


@pytest.mark.asyncio
async def test_build_placeholder_rules_uses_native_candidate_details_for_draft(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通占位符草稿生成使用 native 明细，不依赖 Python 候选扫描。"""
    native_calls: list[str] = []

    def fake_native_placeholder_details(
        *,
        entries: object,
        text_rules: TextRules,
    ) -> JsonArray:
        """返回只存在于 native 侧的草稿候选。"""
        _ = (entries, text_rules)
        native_calls.append("called")
        return [
            {
                "marker": r"\NATIVEONLY[1]",
                "count": 1,
                "sources": ["CommonEvents.json"],
                "standard_covered": False,
                "custom_covered": False,
                "covered": False,
            }
        ]

    monkeypatch.setattr(
        "app.agent_toolkit.services.placeholder_rules.collect_native_placeholder_candidate_details_from_entries",
        fake_native_placeholder_details,
        raising=False,
    )

    def empty_placeholder_candidates(
        translation_data_map: dict[str, TranslationData],
        text_rules: TextRules,
    ) -> list[object]:
        """Python scanner 返回空候选，验证草稿不依赖它。"""
        _ = (translation_data_map, text_rules)
        return []

    monkeypatch.setattr(
        "app.agent_toolkit.services.placeholder_rules.scan_placeholder_candidates",
        empty_placeholder_candidates,
        raising=False,
    )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="English Fixture Game", output_path=output_path)
    rules = load_json_object(output_path)

    assert native_calls == ["called", "called"]
    assert rules == {
        r"(?i)\\NATIVEONLY\d*\[[^\]\r\n]+\]": "[CUSTOM_PLUGIN_NATIVEONLY_MARKER_{index}]",
    }
    assert report.summary["candidate_count"] == 1
    assert report.summary["uncovered_count_before_draft"] == 1


@pytest.mark.asyncio
async def test_build_placeholder_rules_uses_native_details_for_preview_and_boundary(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """草稿预览和手动边界统计也使用 native 明细，不调用 Python scanner。"""
    native_calls: list[str] = []

    def fake_native_placeholder_details(
        *,
        entries: object,
        text_rules: TextRules,
    ) -> JsonArray:
        """按调用顺序模拟草稿前和草稿后的 native 候选。"""
        _ = (entries, text_rules)
        if not native_calls:
            native_calls.append("before")
            return [
                {
                    "marker": r"\NATIVEPREVIEW[1]",
                    "count": 1,
                    "sources": ["CommonEvents.json"],
                    "standard_covered": False,
                    "custom_covered": False,
                    "covered": False,
                },
                {
                    "marker": r"\ShakeStop",
                    "count": 3,
                    "sources": ["CommonEvents.json"],
                    "standard_covered": False,
                    "custom_covered": False,
                    "covered": False,
                },
            ]
        native_calls.append("after")
        return [
            {
                "marker": r"\NATIVEPREVIEW[1]",
                "count": 1,
                "sources": ["CommonEvents.json"],
                "standard_covered": False,
                "custom_covered": True,
                "covered": True,
            },
            {
                "marker": r"\ShakeStop",
                "count": 3,
                "sources": ["CommonEvents.json"],
                "standard_covered": False,
                "custom_covered": False,
                "covered": False,
            },
        ]

    def forbidden_placeholder_scan(
        translation_data_map: dict[str, TranslationData],
        text_rules: TextRules,
    ) -> NoReturn:
        """build-placeholder-rules 预览和边界统计不应调用 Python scanner。"""
        _ = (translation_data_map, text_rules)
        raise AssertionError("build-placeholder-rules 预览/手动边界不应调用 Python scanner")

    monkeypatch.setattr(
        "app.agent_toolkit.services.placeholder_rules.collect_native_placeholder_candidate_details_from_entries",
        fake_native_placeholder_details,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.placeholder_rules.scan_placeholder_candidates",
        forbidden_placeholder_scan,
        raising=False,
    )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="English Fixture Game", output_path=output_path)
    rules = load_json_object(output_path)
    warning_codes = {warning.code for warning in report.warnings}

    assert native_calls == ["before", "after"]
    assert rules == {
        r"(?i)\\NATIVEPREVIEW\d*\[[^\]\r\n]+\]": "[CUSTOM_PLUGIN_NATIVEPREVIEW_MARKER_{index}]",
    }
    assert report.summary["candidate_count"] == 2
    assert report.summary["uncovered_count_before_draft"] == 2
    assert report.summary["uncovered_count_after_draft_preview"] == 1
    assert report.summary["manual_boundary_candidate_count"] == 1
    assert report.details["manual_boundary_candidates"] == [r"\ShakeStop"]
    assert "placeholder_boundary_needs_review" in warning_codes
@pytest.mark.asyncio
async def test_manual_export_and_status_commands_report_long_task_stages(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动修复表和刷新状态查询向 CLI 报告可观测阶段。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    quality_fix_path = tmp_path / "quality-fix.json"
    progress_updates: list[tuple[int, int]] = []
    advanced_steps: list[int] = []
    statuses: list[str] = []

    def set_progress(current: int, total: int) -> None:
        """记录绝对进度。"""
        progress_updates.append((current, total))

    def advance_progress(count: int) -> None:
        """记录阶段推进。"""
        advanced_steps.append(count)

    def set_status(status: str) -> None:
        """记录阶段状态。"""
        statuses.append(status)

    async with await registry.open_game("テストゲーム") as session:
        _ = await session.start_translation_run(
            total_extracted=12,
            pending_count=8,
            deduplicated_count=7,
            batch_count=2,
        )

    pending_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=3,
        callbacks=(set_progress, advance_progress, set_status),
    )
    status_report = await service.translation_status(
        game_title="テストゲーム",
        refresh_scope=True,
        callbacks=(set_progress, advance_progress, set_status),
    )
    quality_fix_report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=quality_fix_path,
        callbacks=(set_progress, advance_progress, set_status),
    )

    assert pending_report.status == "ok"
    assert status_report.status == "ok"
    assert quality_fix_report.status in {"ok", "warning"}
    assert pending_path.exists()
    assert quality_fix_path.exists()
    assert progress_updates[0] == (0, 5)
    assert advanced_steps
    for expected_status in [
        "加载配置和规则",
        "检查持久文本范围索引",
        "读取还没成功保存译文的索引条目",
        "手动填写译文表已完成",
        "读取持久文本范围索引",
        "正文翻译状态已完成",
        "调用 Rust 原生质检核心（",
        "质量修复表已完成",
    ]:
        assert any(status.startswith(expected_status) for status in statuses)
@pytest.mark.asyncio
async def test_note_tag_rule_validation_import_and_pending_export(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签规则校验后会让目标标签值进入 pending，机器协议标签会被拒绝。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目\n二行目>\n<upgrade:1,2,3>\n<ExtendDesc:別説明>"
    items.append({"id": 2, "name": "空タグ項目", "note": "<拡張説明:>", "description": ""})
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    candidates_path = tmp_path / "note-tag-candidates.json"
    pending_path = tmp_path / "pending-translations.json"
    rules_text = json.dumps(
        {"Items.json": ["拡張説明", "ExtendDesc"]},
        ensure_ascii=False,
    )
    machine_rules_text = json.dumps({"Items.json": ["upgrade"]}, ensure_ascii=False)

    candidate_report = await service.export_note_tag_candidates(
        game_title="テストゲーム",
        output_path=candidates_path,
    )
    validate_report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    rejected_report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=machine_rules_text,
    )
    import_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )

    payload = load_json_object(pending_path)
    assert candidate_report.status == "ok"
    assert candidates_path.exists()
    assert validate_report.status == "ok"
    assert validate_report.summary["hit_count"] == 2
    assert rejected_report.status == "error"
    assert "机器协议" in rejected_report.errors[0].message
    assert import_report.status == "ok"
    assert export_report.status == "ok"
    assert "Items.json/1/note/拡張説明" in payload
    assert "Items.json/1/note/ExtendDesc" in payload
    assert "Items.json/2/note/拡張説明" not in payload


@pytest.mark.asyncio
async def test_export_note_tag_candidates_uses_native_candidate_scan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签候选导出必须消费 native note_tags 候选摘要。"""

    def forbidden_python_note_tag_candidates(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("export-note-tag-candidates 不应调用 Python collect_note_tag_candidates")

    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = f"<拡張説明:{json.dumps('薬草の詳細', ensure_ascii=False)}>\n<upgrade:1,2,3>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "app.note_tag_text.exporter.collect_note_tag_candidates",
        forbidden_python_note_tag_candidates,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    candidates_path = tmp_path / "note-tag-candidates.json"

    candidate_report = await service.export_note_tag_candidates(
        game_title="テストゲーム",
        output_path=candidates_path,
    )

    payload = load_json_object(candidates_path)
    details = ensure_json_object(coerce_json_value(payload["details"]), "note_tag_candidates.details")
    candidates = [
        ensure_json_object(candidate, f"note_tag_candidates[{index}]")
        for index, candidate in enumerate(ensure_json_array(details["candidates"], "note_tag_candidates"))
    ]
    candidates_by_key = {
        (candidate["file_name"], candidate["tag_name"]): candidate
        for candidate in candidates
    }
    description = candidates_by_key[("Items.json", "拡張説明")]
    assert candidate_report.status == "ok"
    assert candidate_report.summary["candidate_tag_count"] == len(candidates)
    assert description["sample_values"] == ["薬草の詳細"]
    assert description["sample_locations"] == ["Items.json/1/note/拡張説明"]
    assert description["translatable_hit_count"] == 1


@pytest.mark.asyncio
async def test_manual_pending_translation_export_and_import(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 可以导出少量待翻译条目，人工补齐后再由工具校验入库。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=10,
    )

    assert export_report.status == "ok"
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        if original_lines == ["こんにちは"]:
            target_path = location_path
            entry["translation_lines"] = ["　你好　"]
            payload[location_path] = entry
            break
    assert target_path
    _ = pending_path.write_text(json.dumps({target_path: payload[target_path]}, ensure_ascii=False, indent=2), encoding="utf-8")
    async with await registry.open_game("テストゲーム") as session:
        run_record = await session.start_translation_run(
            total_extracted=10,
            pending_count=10,
            deduplicated_count=10,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=await _current_fact_id_for_path(session, target_path),
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=["こんにちは"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["人工补译前的历史错误"],
                    model_response='{"bad": true}',
                )
            ],
        )

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    status_report = await service.translation_status(game_title="テストゲーム", refresh_scope=True)
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert import_report.status == "ok"
    assert status_report.summary["pending_count"] == quality_report.summary["pending_count"]
    assert status_report.summary["run_pending_count"] == 10
    assert status_report.summary["quality_error_count"] == 0
    assert status_report.summary["run_quality_error_count"] == 0
    assert quality_report.summary["quality_error_count"] == 0
    assert quality_report.summary["run_quality_error_count"] == 0
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        quality_errors = await session.read_translation_quality_errors(run_record.run_id)
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["你好"]
    assert quality_errors == []


@pytest.mark.asyncio
async def test_manual_translation_import_normalizes_integer_translation_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文导入中的整数译文行按外部文本规范化为字符串。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    assert export_report.status == "ok"

    payload = load_json_object(pending_path)
    first_key = next(iter(payload))
    entry = ensure_json_object(coerce_json_value(payload[first_key]), first_key)
    entry["translation_lines"] = [1]
    payload[first_key] = entry
    _ = pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    assert any(item.translation_lines == ["1"] for item in translated_items)


@pytest.mark.asyncio
async def test_manual_translation_import_rejects_boolean_translation_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文导入中的布尔译文行无效。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    assert export_report.status == "ok"

    payload = load_json_object(pending_path)
    first_key = next(iter(payload))
    entry = ensure_json_object(coerce_json_value(payload[first_key]), first_key)
    entry["translation_lines"] = [True]
    payload[first_key] = entry
    _ = pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert any("bool" in error.message for error in report.errors)


@pytest.mark.asyncio
async def test_manual_translation_import_normalizes_integer_fact_id(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文导入中的整数 fact_id 按外部文本规范化。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    assert export_report.status == "ok"

    payload = load_json_object(pending_path)
    first_key = next(iter(payload))
    entry = ensure_json_object(coerce_json_value(payload[first_key]), first_key)
    entry["fact_id"] = 123
    entry["translation_lines"] = ["你好"]
    payload[first_key] = entry
    _ = pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"manual_translation_location"}
    assert "fact_id 不属于当前可写" in report.errors[0].message
    assert "bool" not in report.errors[0].message


@pytest.mark.asyncio
async def test_manual_translation_import_reports_boolean_fact_id(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动译文导入中的布尔 fact_id 无效，并进入导入报告。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    assert export_report.status == "ok"

    payload = load_json_object(pending_path)
    first_key = next(iter(payload))
    entry = ensure_json_object(coerce_json_value(payload[first_key]), first_key)
    entry["fact_id"] = True
    entry["translation_lines"] = ["你好"]
    payload[first_key] = entry
    _ = pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"manual_translation_invalid"}
    assert "fact_id" in report.errors[0].message
    assert "bool" in report.errors[0].message


@pytest.mark.asyncio
async def test_manual_quality_fix_import_uses_current_fact_scope_without_full_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """质量修复导入已有译文时也必须用 current_text_fact 身份校验。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """质量修复快路径不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("质量修复导入不应加载完整游戏数据")

    async def forbidden_full_quality_error_read(*args: object, **kwargs: object) -> NoReturn:
        """质量修复快路径不应读取最新运行的全部质量错误。"""
        _ = (args, kwargs)
        raise AssertionError("质量修复导入不应读取全部质量错误")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    target_path = "CommonEvents.json/1/0"
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=target_path,
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["こんにちは"],
                )
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=10,
            pending_count=8,
            deduplicated_count=10,
            batch_count=1,
        )
        target_fact_id = await _current_fact_id_for_path(session, target_path)
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=target_fact_id,
                    location_path=target_path,
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは"],
                    translation_lines=["こんにちは"],
                    error_type="源文残留",
                    error_detail=["发现日文残留"],
                    model_response="",
                ),
                TranslationErrorItem(
                    fact_id="fact-ghost-quality-error",
                    location_path="Map999.json/ghost",
                    item_type="long_text",
                    role=None,
                    original_lines=["別の原文"],
                    translation_lines=["別の原文"],
                    error_type="源文残留",
                    error_detail=["另一个质量错误"],
                    model_response="",
                ),
            ],
        )
    input_path = tmp_path / "quality-fix.json"
    _ = input_path.write_text(
        json.dumps(
            {
                target_path: {
                    "fact_id": target_fact_id,
                    "item_type": "long_text",
                    "role": "アリス",
                    "original_lines": ["こんにちは"],
                    "translation_lines": ["你好"],
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors",
        forbidden_full_quality_error_read,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert import_report.status == "ok"
    assert import_report.summary["scope_mode"] == "current_text_fact"
    assert "text_index_status" not in import_report.summary
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        remaining_quality_error_count = await session.count_translation_quality_errors(run_record.run_id)
        target_quality_errors = await session.read_translation_quality_errors_by_paths(
            run_record.run_id,
            {target_path},
        )
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["你好"]
    assert translated_by_path[target_path].source_line_paths == ["CommonEvents.json/1/1"]
    assert remaining_quality_error_count == 1
    assert target_quality_errors == []
@pytest.mark.asyncio
async def test_manual_pending_import_uses_text_index_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通手动导入在 warm index 存在时只按输入路径读取索引。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 导入不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("warm index 手动导入不应加载完整游戏数据")

    async def forbidden_full_text_index_path_read(*args: object, **kwargs: object) -> NoReturn:
        """warm index 导入不应读取完整索引路径集合。"""
        _ = (args, kwargs)
        raise AssertionError("warm index 手动导入不应读取完整索引路径集合")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=10,
    )
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    indexed_count = rebuild_report.summary["indexed_count"]
    assert isinstance(indexed_count, int)
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.start_translation_run(
            total_extracted=indexed_count,
            pending_count=indexed_count,
            deduplicated_count=indexed_count,
            batch_count=1,
        )
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        if entry["item_type"] != "array":
            target_path = location_path
            break
    assert target_path
    target_entry = ensure_json_object(coerce_json_value(payload[target_path]), target_path)
    target_entry["translation_lines"] = ["手动译文"]
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(
        "app.persistence.text_index_records.TextIndexRecordSessionMixin.read_text_index_location_paths",
        forbidden_full_text_index_path_read,
    )

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert import_report.status == "ok"
    assert import_report.summary["scope_mode"] == "current_text_fact"
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines


@pytest.mark.asyncio
async def test_export_pending_translations_warm_index_uses_sql_limit_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 导出 pending 时必须在 SQLite 层应用 limit，不再构建完整 scope。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index pending 导出不应触碰完整游戏数据加载。"""
        _ = (args, kwargs)
        raise AssertionError("warm index pending 导出不应加载完整游戏数据")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    pending_path = tmp_path / "pending-translations.json"
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )

    payload = load_json_object(pending_path)
    assert export_report.status == "ok"
    assert export_report.summary["text_index_status"] == "used"
    assert export_report.summary["pending_exported_count"] == 1
    assert len(payload) == 1


@pytest.mark.asyncio
async def test_export_pending_translations_uses_current_text_fact_translatable_text(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """pending 导出必须使用 current_text_fact 的可译正文，不读取非当前 index original_lines。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        async with session.connection.execute(
            """
--sql
            SELECT facts.location_path, facts.translatable_text
                , facts.fact_id
            FROM text_facts AS facts
            INNER JOIN text_index_items AS indexed
                ON indexed.location_path = facts.location_path
            LEFT JOIN translation_items AS translations
                ON translations.location_path = facts.location_path
            WHERE indexed.writable = 1
                AND translations.location_path IS NULL
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
            LIMIT 1
            ;
            """
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        target_path = cast(str, row["location_path"])
        expected_text = cast(str, row["translatable_text"])
        expected_fact_id = cast(str, row["fact_id"])
        polluted_lines = json.dumps(
            ["RAW_SHELL_SHOULD_NOT_BE_EXPORTED location_path translated_text 位置:"],
            ensure_ascii=False,
        )
        _ = await session.connection.execute(
            "UPDATE text_index_items SET original_lines = ? WHERE location_path = ?",
            (polluted_lines, target_path),
        )
        await session.connection.commit()
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )

    payload = load_json_object(pending_path)
    entry = ensure_json_object(coerce_json_value(payload[target_path]), target_path)
    assert export_report.status == "ok"
    assert entry["fact_id"] == expected_fact_id
    assert entry["original_lines"] == [expected_text]
    assert entry["text_for_model_lines"] == [expected_text]
    exported_text = json.dumps(payload, ensure_ascii=False)
    assert "RAW_SHELL_SHOULD_NOT_BE_EXPORTED" not in exported_text
    assert "translated_text" not in exported_text
    assert "位置:" not in exported_text


@pytest.mark.asyncio
async def test_export_quality_fix_template_uses_current_text_fact_translatable_text(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量修复模板源文必须来自 current_text_fact，不读取非当前 index original_lines。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    template_path = tmp_path / "quality-fix-template.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = sorted(payload)[0]
    target_entry = ensure_json_object(coerce_json_value(payload[target_path]), target_path)
    expected_original_lines = [
        line
        for line in ensure_json_array(target_entry["original_lines"], f"{target_path}.original_lines")
        if isinstance(line, str)
    ]
    assert export_report.status == "ok"
    assert expected_original_lines

    async with await registry.open_game("テストゲーム") as session:
        target_fact_id = await _current_fact_id_for_path(session, target_path)
        polluted_lines = json.dumps(
            ["NON_CURRENT_INDEX_TEXT_SHOULD_NOT_FEED_QUALITY_FIX_TEMPLATE translated_text 位置:"],
            ensure_ascii=False,
        )
        _ = await session.connection.execute(
            "UPDATE text_index_items SET original_lines = ? WHERE location_path = ?",
            (polluted_lines, target_path),
        )
        run_record = await session.start_translation_run(
            total_extracted=len(payload),
            pending_count=len(payload),
            deduplicated_count=len(payload),
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=target_fact_id,
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=list(expected_original_lines),
                    translation_lines=["候选译文"],
                    error_type="AI漏翻",
                    error_detail=["测试质量错误"],
                    model_response='{"translation_lines":["候选译文"]}',
                )
            ],
        )
        await session.connection.commit()

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=template_path,
    )

    template = load_json_object(template_path)
    exported_entry = ensure_json_object(coerce_json_value(template[target_fact_id]), target_fact_id)
    assert report.status == "ok"
    assert exported_entry["text_position"] == target_path
    assert exported_entry["original_lines"] == expected_original_lines
    exported_text = json.dumps(template, ensure_ascii=False)
    assert "NON_CURRENT_INDEX_TEXT_SHOULD_NOT_FEED_QUALITY_FIX_TEMPLATE" not in exported_text
    assert "translated_text" not in exported_text
    assert "位置:" not in exported_text


@pytest.mark.asyncio
async def test_export_quality_fix_template_hard_stop_does_not_leak_non_current_index_text(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量修复表阻断明细不能暴露非当前 index original_lines。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "quality-fix-template.json"
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.connection.execute(
            "UPDATE text_index_items SET original_lines = ?",
            (
                json.dumps(
                    ["NON_CURRENT_INDEX_TEXT_SHOULD_NOT_APPEAR_IN_COVERAGE_DETAIL translated_text 位置:"],
                    ensure_ascii=False,
                ),
            ),
        )
        await insert_invalid_fact_translation_row_for_test(
            session,
            location_path="Removed.json/ghost",
            item_type="short_text",
            role=None,
            original_lines=["superseded saved source"],
            source_line_paths=["Removed.json/ghost"],
            translation_lines=["superseded saved translation"],
        )
        await session.connection.commit()

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=output_path,
    )

    assert report.status == "error"
    assert "stale_saved_translations" in {error.code for error in report.errors}
    report_text = report.to_json_text()
    assert "NON_CURRENT_INDEX_TEXT_SHOULD_NOT_APPEAR_IN_COVERAGE_DETAIL" not in report_text
    assert "translated_text" not in report_text
    assert "位置:" not in report_text


@pytest.mark.asyncio
async def test_export_pending_translations_cold_rebuilds_missing_text_index_then_uses_limit(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """缺少 text index 时 pending 导出只重建一次索引，再读取受 limit 限制的条目。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )

    payload = load_json_object(pending_path)
    rebuild_summary = ensure_json_object(
        coerce_json_value(export_report.summary["text_index_rebuild_summary"]),
        "text_index_rebuild_summary",
    )
    assert export_report.status == "ok"
    assert export_report.summary["text_index_status"] == "cold_rebuilt"
    assert export_report.summary["pending_exported_count"] == 1
    assert export_report.summary["pending_total_count"] == rebuild_summary["indexed_count"]
    assert rebuild_summary["index_status"] == "rebuilt"
    assert rebuild_summary["include_write_probe"] is False
    assert len(payload) == 1


@pytest.mark.asyncio
async def test_manual_pending_import_with_fact_id_rejects_missing_writable_text_index(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """带 fact_id 的手动导入缺可写索引记录时必须显式失败且不重建 text_index。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=10,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        if entry["item_type"] != "array":
            target_path = location_path
            break
    assert target_path
    target_entry = ensure_json_object(coerce_json_value(payload[target_path]), target_path)
    target_entry["translation_lines"] = ["手动译文"]
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.clear_text_index()

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert import_report.status == "error"
    assert import_report.summary["scope_mode"] == "current_text_fact"
    assert import_report.summary["imported_count"] == 0
    assert "manual_translation_location" in {error.code for error in import_report.errors}
    assert "text_index_status" not in import_report.summary
    assert "text_index_rebuild_summary" not in import_report.summary
    async with await registry.open_game("テストゲーム") as session:
        metadata = await session.read_text_index_metadata()
        translated_items = await session.read_translated_items()
    assert metadata is None
    assert target_path not in {item.location_path for item in translated_items}


@pytest.mark.asyncio
async def test_manual_pending_import_rejects_unwritable_fact_id(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """带 fact_id 的手动导入也必须只接受当前可写 current text fact。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        async with session.connection.execute(
            """
--sql
            SELECT facts.fact_id, facts.location_path
            FROM text_facts AS facts
            INNER JOIN text_index_items AS indexed
                ON indexed.location_path = facts.location_path
            WHERE indexed.writable = 1
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
            LIMIT 1
            ;
            """
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        target_fact_id = cast(str, row["fact_id"])
        target_path = cast(str, row["location_path"])
        _ = await session.connection.execute(
            "UPDATE text_index_items SET writable = 0 WHERE location_path = ?",
            (target_path,),
        )
        await session.connection.commit()
    import_path = tmp_path / "manual-import-unwritable-fact.json"
    _ = import_path.write_text(
        json.dumps(
            {
                target_path: {
                    "fact_id": target_fact_id,
                    "translation_lines": ["不应保存"],
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=import_path,
    )

    assert report.status == "error"
    assert report.summary["imported_count"] == 0
    assert "manual_translation_location" in {error.code for error in report.errors}
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    assert target_path not in {item.location_path for item in translated_items}


@pytest.mark.asyncio
async def test_translation_status_uses_database_fast_path_by_default(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """状态查询默认不能重新加载游戏文件和构建完整文本范围。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """快速状态查询不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("translation-status 默认不应加载游戏文件")

    async def forbidden_full_quality_error_read(*args: object, **kwargs: object) -> NoReturn:
        """快速状态查询不应读取全部质量错误明细。"""
        _ = (args, kwargs)
        raise AssertionError("translation-status 默认不应读取全部质量错误明细")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.start_translation_run(
            total_extracted=12,
            pending_count=8,
            deduplicated_count=7,
            batch_count=2,
        )
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors",
        forbidden_full_quality_error_read,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.translation_status(game_title="テストゲーム")

    assert report.status == "ok"
    assert report.summary["scope_refreshed"] is False
    assert report.summary["pending_count"] == 8
    assert report.summary["extractable_count"] == 12
@pytest.mark.asyncio
async def test_translation_status_refresh_scope_cold_rebuilds_missing_text_index(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """translation-status --refresh-scope 缺索引时自动重建并用索引刷新统计。"""

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.start_translation_run(
            total_extracted=999,
            pending_count=999,
            deduplicated_count=10,
            batch_count=1,
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.translation_status(game_title="テストゲーム", refresh_scope=True)

    assert report.status == "ok"
    assert report.summary["scope_refreshed"] is True
    assert report.summary["text_index_status"] == "cold_rebuilt"
    rebuild_summary = ensure_json_object(report.summary["text_index_rebuild_summary"], "text_index_rebuild_summary")
    assert rebuild_summary["index_status"] == "rebuilt"
    assert report.summary["extractable_count"] == rebuild_summary["indexed_count"]
    assert report.summary["pending_count"] == rebuild_summary["indexed_count"]
    assert report.summary["run_pending_count"] == 999
@pytest.mark.asyncio
async def test_translation_status_refresh_scope_uses_text_index_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """translation-status --refresh-scope 在 warm index 下不加载完整游戏数据。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 状态刷新不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("translation-status --refresh-scope 不应加载完整游戏数据")

    async def forbidden_full_text_index_path_read(*args: object, **kwargs: object) -> NoReturn:
        """warm index 状态刷新不应读取完整索引路径集合。"""
        _ = (args, kwargs)
        raise AssertionError("translation-status --refresh-scope 不应读取完整索引路径集合")

    async def forbidden_full_quality_error_read(*args: object, **kwargs: object) -> NoReturn:
        """warm index 状态刷新不应读取全部质量错误明细。"""
        _ = (args, kwargs)
        raise AssertionError("translation-status --refresh-scope 不应读取全部质量错误明细")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.start_translation_run(
            total_extracted=999,
            pending_count=999,
            deduplicated_count=10,
            batch_count=1,
        )
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(
        "app.persistence.text_index_records.TextIndexRecordSessionMixin.read_text_index_location_paths",
        forbidden_full_text_index_path_read,
    )
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors",
        forbidden_full_quality_error_read,
    )

    report = await service.translation_status(game_title="テストゲーム", refresh_scope=True)

    assert report.status == "ok"
    assert report.summary["scope_refreshed"] is True
    assert report.summary["text_index_status"] == "used"
    assert report.summary["extractable_count"] == rebuild_report.summary["indexed_count"]
    assert report.summary["pending_count"] == rebuild_report.summary["indexed_count"]
    assert report.summary["run_pending_count"] == 999
@pytest.mark.asyncio
async def test_reset_translations_input_deletes_paths_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reset-translations --input 只按输入路径删库，不加载游戏或构建完整范围。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """按路径重置不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("reset --input 不应加载完整游戏数据")

    async def forbidden_full_text_index_path_read(*args: object, **kwargs: object) -> NoReturn:
        """按路径重置不应读取完整索引路径集合。"""
        _ = (args, kwargs)
        raise AssertionError("reset --input 不应读取完整索引路径集合")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    target_path = "CommonEvents.json/1/0"
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=target_path,
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好"],
                )
            ]
        )
    input_path = tmp_path / "reset.json"
    _ = input_path.write_text(
        json.dumps({"location_paths": [target_path]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(
        "app.persistence.text_index_records.TextIndexRecordSessionMixin.read_text_index_location_paths",
        forbidden_full_text_index_path_read,
    )

    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "ok"
    assert report.summary["mode"] == "input"
    assert report.summary["requested_count"] == 1
    assert report.summary["reset_count"] == 1
    assert report.summary["text_index_status"] == "used"
    async with await registry.open_game("テストゲーム") as session:
        assert await session.read_translated_items() == []


@pytest.mark.asyncio
async def test_reset_translations_input_normalizes_integer_location_path(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """reset-translations 输入中的整数定位路径按外部文本规范化。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    input_path = tmp_path / "reset-integer-path.json"
    _ = input_path.write_text(
        json.dumps({"location_paths": [123]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "error"
    assert report.errors[0].code == "reset_translation_location"
    assert report.details["invalid_location_paths"] == ["123"]


@pytest.mark.asyncio
async def test_reset_translations_input_rejects_boolean_location_path(
    tmp_path: Path,
) -> None:
    """reset-translations 输入中的布尔定位路径无效。"""
    service = AgentToolkitService(game_registry=GameRegistry(tmp_path / "db"), setting_path=EXAMPLE_SETTING_PATH)
    input_path = tmp_path / "reset-boolean-path.json"
    _ = input_path.write_text(
        json.dumps({"location_paths": [True]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"reset_translation_file"}
    assert "reset-translations.location_paths[0]" in report.errors[0].message
    assert "bool" in report.errors[0].message
@pytest.mark.asyncio
async def test_reset_translations_input_rejects_unknown_paths_without_partial_delete(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """reset-translations --input 遇到不属于当前范围的路径时整体失败。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    target_path = "CommonEvents.json/1/0"
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=target_path,
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好"],
                )
            ]
        )
    input_path = tmp_path / "reset-invalid.json"
    _ = input_path.write_text(
        json.dumps({"location_paths": [target_path, "missing/path"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "error"
    assert report.errors[0].code == "reset_translation_location"
    assert report.summary["reset_count"] == 0
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    assert len(translated_items) == 1
    assert translated_items[0].location_path == target_path


@pytest.mark.asyncio
async def test_reset_translations_input_rejects_path_missing_current_fact(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """reset --input 的路径归属必须来自 current_text_fact，而不是非当前索引行。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    target_path = "CommonEvents.json/1/0"
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=target_path,
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好"],
                )
            ]
        )
        _ = await session.connection.execute(
            "DELETE FROM text_facts WHERE location_path = ?",
            (target_path,),
        )
        await session.connection.commit()
    input_path = tmp_path / "reset-missing-current-fact.json"
    _ = input_path.write_text(
        json.dumps({"location_paths": [target_path]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "error"
    assert report.errors[0].code == "reset_translation_location"
    assert report.summary["reset_count"] == 0
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    assert len(translated_items) == 1
    assert translated_items[0].location_path == target_path
@pytest.mark.asyncio
async def test_reset_translations_input_cold_rebuilds_missing_text_index(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """reset-translations --input 缺索引时自动重建，再校验和删除输入路径。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    target_path = "CommonEvents.json/1/0"
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=target_path,
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好"],
                )
            ]
        )
        await session.clear_text_index()
    input_path = tmp_path / "reset-cold.json"
    _ = input_path.write_text(
        json.dumps({"location_paths": [target_path]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=input_path,
    )

    assert report.status == "ok"
    assert report.summary["text_index_status"] == "cold_rebuilt"
    rebuild_summary = ensure_json_object(report.summary["text_index_rebuild_summary"], "rebuild_summary")
    assert rebuild_summary["index_status"] == "rebuilt"
    assert report.summary["reset_count"] == 1
    async with await registry.open_game("テストゲーム") as session:
        assert await session.read_text_index_metadata() is not None
        assert await session.read_translated_items() == []
@pytest.mark.asyncio
async def test_manual_translation_keeps_repeated_structured_shell_indices(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工译文里的多个相同结构化外壳按原文顺序映射回各自编号。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["description"] = "慎重に相手のおっぱいを揉んで愛撫する。\n【自身の我慢-5】【MP＋10】【相手の我慢　↑】"
    _ = items_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_structured_placeholder_rules(
            [
                StructuredPlaceholderRuleRecord(
                    rule_name="BRACKET_TITLE",
                    rule_type="paired_shell",
                    pattern_text=r"(?P<open>【)(?P<text>[^【】\r\n]*?)(?P<close>】)",
                    translatable_group="text",
                    protected_groups={
                        "open": "[CUSTOM_BRACKET_TITLE_OPEN_{index}]",
                        "close": "[CUSTOM_BRACKET_TITLE_CLOSE_{index}]",
                    },
                )
            ]
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = "Items.json/1/description"
    target_entry = ensure_json_object(coerce_json_value(payload[target_path]), target_path)
    target_entry["translation_lines"] = [
        "慎重地揉捏对方的胸部进行爱抚。\n【自身忍耐-5】【MP＋10】【对方忍耐　↑】"
    ]
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _ = await _rebuild_text_index_for_test(service)

    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert export_report.status == "ok"
    assert import_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == [
        "慎重地揉捏对方的胸部进行爱抚。\n【自身忍耐-5】【MP＋10】【对方忍耐　↑】"
    ]
@pytest.mark.asyncio
async def test_manual_translation_rejects_changed_unprotected_control_sequence(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工补译不得改写未被占位符规则覆盖的疑似控制符。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    commands.insert(-1, {"code": 101, "parameters": [0, 0, 0, 2, "アリス"]})
    commands.insert(-1, {"code": 401, "parameters": [r"\F3[66」「ふーん……？」"]})
    _ = common_events_path.write_text(
        json.dumps(common_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    target_entry: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        if original_lines == [r"\F3[66」「ふーん……？」"]:
            target_path = location_path
            entry["translation_lines"] = [r"\F3[60」「唔——嗯……？」"]
            target_entry = {key: value for key, value in entry.items()}
            break
    assert export_report.status == "ok"
    assert target_path
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _ = await _rebuild_text_index_for_test(service)

    rejected_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert rejected_report.status == "error"
    assert rejected_report.errors
    assert "疑似控制符不一致" in rejected_report.errors[0].message
    assert r"\F3[66」" in rejected_report.errors[0].message
    assert r"\F3[60」" in rejected_report.errors[0].message
@pytest.mark.asyncio
async def test_manual_translation_uses_source_residual_exception_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """确需保留的源文片段必须先导入显式例外规则才能通过人工补译。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=10,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    target_entry: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        if original_lines == ["こんにちは"]:
            target_path = location_path
            entry["translation_lines"] = ["こんにちは"]
            target_entry = {key: value for key, value in entry.items()}
            break
    assert export_report.status == "ok"
    assert target_path
    _ = pending_path.write_text(
        json.dumps({target_path: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _ = await _rebuild_text_index_for_test(service)

    rejected_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    rules_text = json.dumps(
        {
            "position_rules": {
                target_path: {
                    "allowed_terms": ["こんにちは"],
                    "reason": "proper_noun",
                }
            },
            "structural_rules": [],
        },
        ensure_ascii=False,
    )
    validate_report = await service.validate_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    import_rules_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    accepted_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert rejected_report.status == "error"
    assert "日文残留" in rejected_report.errors[0].message
    assert validate_report.status == "ok"
    assert import_rules_report.status == "ok"
    assert accepted_report.status == "ok"
    assert quality_report.summary["source_residual_rule_count"] == 1
    assert quality_report.summary["source_residual_count"] == 0
    assert quality_report.details["source_residual_items"] == []
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        residual_rules = await session.read_source_residual_rules()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["こんにちは"]
    assert residual_rules[0].rule_type == "position"
    assert residual_rules[0].location_path == target_path
    assert residual_rules[0].allowed_terms == ["こんにちは"]
    assert residual_rules[0].reason == "proper_noun"


@pytest.mark.asyncio
async def test_source_residual_rule_commands_use_current_fact_translatable_text(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """源文残留规则 allowed_terms 校验必须读取 current text fact 可译正文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        async with session.connection.execute(
            """
--sql
            SELECT facts.location_path, facts.translatable_text
            FROM text_facts AS facts
            INNER JOIN text_index_items AS indexed
                ON indexed.location_path = facts.location_path
            WHERE indexed.writable = 1
                AND facts.translatable_text <> ''
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
            ;
            """
        ) as cursor:
            rows = await cursor.fetchall()
        target_path = ""
        allowed_term = ""
        for row in rows:
            candidate_text = cast(str, row["translatable_text"])
            if "\n" in candidate_text:
                continue
            target_path = cast(str, row["location_path"])
            allowed_term = candidate_text
            break
        assert target_path
        assert allowed_term
        polluted_lines = json.dumps(
            ["NON_CURRENT_INDEX_TEXT_SHOULD_NOT_VALIDATE_SOURCE_RESIDUAL"],
            ensure_ascii=False,
        )
        _ = await session.connection.execute(
            "UPDATE text_index_items SET original_lines = ? WHERE location_path = ?",
            (polluted_lines, target_path),
        )
        await session.connection.commit()
    rules_text = json.dumps(
        {
            "position_rules": {
                target_path: {
                    "allowed_terms": [allowed_term],
                    "reason": "proper_noun",
                }
            },
            "structural_rules": [],
        },
        ensure_ascii=False,
    )

    validate_report = await service.validate_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    import_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert validate_report.status == "ok"
    assert import_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        residual_rules = await session.read_source_residual_rules()
    assert residual_rules[0].location_path == target_path
    assert residual_rules[0].allowed_terms == [allowed_term]


@pytest.mark.asyncio
async def test_source_residual_rule_commands_reject_stale_text_fact_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """源文残留规则校验遇到过期 当前文本事实 scope 必须要求重建。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    async with await registry.open_game("テストゲーム") as session:
        async with session.connection.execute(
            """
--sql
            SELECT facts.location_path, facts.translatable_text
            FROM text_facts AS facts
            INNER JOIN text_index_items AS indexed
                ON indexed.location_path = facts.location_path
            WHERE indexed.writable = 1
                AND facts.translatable_text <> ''
            ORDER BY indexed.location_path, facts.domain, facts.fact_id
            LIMIT 1
            ;
            """
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        target_path = cast(str, row["location_path"])
        allowed_term = cast(str, row["translatable_text"])
        _ = await session.connection.execute("DELETE FROM text_index_meta")
        await session.connection.commit()
    rules_text = json.dumps(
        {
            "position_rules": {
                target_path: {
                    "allowed_terms": [allowed_term],
                    "reason": "proper_noun",
                }
            },
            "structural_rules": [],
        },
        ensure_ascii=False,
    )

    validate_report = await service.validate_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    import_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert validate_report.status == "error"
    assert import_report.status == "error"
    assert validate_report.errors[0].code == "source_residual_rules_invalid"
    assert import_report.errors[0].code == "source_residual_rules_invalid"
    assert "rebuild-text-index" in validate_report.errors[0].message
    assert "rebuild-text-index" in import_report.errors[0].message
@pytest.mark.asyncio
async def test_manual_long_text_import_splits_overwide_lines(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工补译 long_text 入库前会按当前行宽配置自动拆短。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    setting_path = tmp_path / "setting.toml"
    setting_text = example_setting_text_with_absolute_prompt_files()
    setting_text = setting_text.replace("long_text_line_width_limit = 26", "long_text_line_width_limit = 3")
    _ = setting_path.write_text(setting_text, encoding="utf-8")
    service = AgentToolkitService(game_registry=registry, setting_path=setting_path)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        if entry["item_type"] == "long_text":
            target_path = location_path
            entry["translation_lines"] = ["甲乙丙丁戊己庚辛"]
            _ = pending_path.write_text(
                json.dumps({target_path: entry}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            break

    _ = await _rebuild_text_index_for_test(service)
    import_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert export_report.status == "ok"
    assert target_path
    assert import_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert translated_by_path[target_path].translation_lines == ["甲乙丙", "丁戊己", "庚辛"]
@pytest.mark.parametrize(
    "translation_lines",
    [
        ["第一行", "第二行"],
        ["第一行\n第二行"],
        [r"第一行\n第二行"],
        ["译文：你好"],
        ["translation_lines: 你好"],
    ],
)
@pytest.mark.asyncio
async def test_manual_translation_import_rejects_text_structure_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
    translation_lines: list[str],
) -> None:
    """人工补译同样拒绝改动单字段结构或混入模型协议文本的译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] == "short_text" and not any("\n" in line or r"\n" in line for line in original_lines):
            target_path = location_path
            entry["translation_lines"] = cast(JsonValue, list(translation_lines))
            _ = pending_path.write_text(
                json.dumps({target_path: entry}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            break
    assert target_path

    _ = await _rebuild_text_index_for_test(service)
    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert report.summary["imported_count"] == 0
    assert report.errors[0].code == "manual_translation_invalid"
    invalid_items = ensure_json_array(report.details["invalid_items"], "invalid_items")
    first_invalid = ensure_json_object(coerce_json_value(invalid_items[0]), "invalid_items[0]")
    assert first_invalid["location_path"] == target_path
    assert "message" in first_invalid
    assert "expected_real_line_break_count" in first_invalid
@pytest.mark.asyncio
async def test_manual_translation_import_reports_all_invalid_items_without_partial_write(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """人工补译导入一次报告所有坏条目，并且不保存任何部分成功结果。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    selected: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] != "short_text" or any("\n" in line or r"\n" in line for line in original_lines):
            continue
        entry["translation_lines"] = ["第一行\n第二行"] if not selected else ["译文：你好"]
        selected[location_path] = entry
        if len(selected) == 2:
            break
    assert len(selected) == 2
    _ = pending_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    _ = await _rebuild_text_index_for_test(service)
    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()

    invalid_items = ensure_json_array(report.details["invalid_items"], "invalid_items")
    assert report.status == "error"
    assert report.summary["imported_count"] == 0
    assert len(invalid_items) == 2
    assert translated_items == []
    assert any(
        ensure_json_object(coerce_json_value(item), "invalid_item")["actual_real_line_break_count"] == 1
        for item in invalid_items
    )


@pytest.mark.asyncio
async def test_manual_translation_import_uses_current_fact_id_when_workspace_key_is_stale(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """手动导入有 fact_id 时按 current_text_fact 身份保存，不信任 superseded workspace 顶层路径。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    assert export_report.status == "ok"
    payload = load_json_object(pending_path)
    target_path = ""
    target_entry: JsonObject = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] == "short_text" and not any("\n" in line or r"\n" in line for line in original_lines):
            target_path = location_path
            target_entry = entry
            break
    assert target_path
    assert isinstance(target_entry.get("fact_id"), str)
    target_entry["translation_lines"] = ["手动译文"]
    stale_workspace_key = "SupersededWorkspace/CommonEvents.json/ghost"
    _ = pending_path.write_text(
        json.dumps({stale_workspace_key: target_entry}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    translated_by_path = {item.location_path: item for item in translated_items}
    assert report.status == "ok"
    assert report.summary["scope_mode"] == "current_text_fact"
    assert stale_workspace_key not in translated_by_path
    assert translated_by_path[target_path].translation_lines == ["手动译文"]


@pytest.mark.asyncio
async def test_manual_translation_import_asks_to_reexport_when_invalid_workspace_lacks_current_fact_id(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """无 fact_id 的无效手动填写文件路径不属于 current_text_fact 时，必须要求重新导出。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "missing-current-fact-pending-translations.json"
    _ = pending_path.write_text(
        json.dumps(
            {
                "MissingCurrentFact/CommonEvents.json/ghost": {
                    "item_type": "short_text",
                    "role": None,
                    "original_lines": ["こんにちは"],
                    "translation_lines": ["你好"],
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
    )

    assert report.status == "error"
    assert report.summary["imported_count"] == 0
    invalid_items = ensure_json_array(report.details["invalid_items"], "invalid_items")
    message = str(ensure_json_object(coerce_json_value(invalid_items[0]), "invalid_items[0]")["message"])
    assert "重新导出 pending translations" in message


@pytest.mark.asyncio
async def test_manual_translation_import_valid_saves_good_items_and_reports_invalid(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """显式部分导入会保存有效译文，并把无效条目写入独立报告。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    invalid_report_path = tmp_path / "invalid-manual-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    selected: JsonObject = {}
    valid_path = ""
    invalid_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] != "short_text" or any("\n" in line or r"\n" in line for line in original_lines):
            continue
        if not valid_path:
            valid_path = location_path
            entry["translation_lines"] = ["手动译文"]
        else:
            invalid_path = location_path
            entry["translation_lines"] = ["第一行\n第二行"]
        selected[location_path] = entry
        if len(selected) == 2:
            break
    assert valid_path
    assert invalid_path
    _ = pending_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    _ = await _rebuild_text_index_for_test(service)
    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
        import_valid=True,
        report_invalid_path=invalid_report_path,
    )

    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
    translated_by_path = {item.location_path: item for item in translated_items}
    invalid_report = load_json_object(invalid_report_path)
    invalid_details = ensure_json_object(coerce_json_value(invalid_report["details"]), "invalid_report.details")
    invalid_items = ensure_json_array(invalid_details["invalid_items"], "invalid_report.invalid_items")

    assert report.status == "warning"
    assert report.summary["imported_count"] == 1
    assert report.summary["invalid_count"] == 1
    assert report.summary["invalid_report"] == str(invalid_report_path)
    assert translated_by_path[valid_path].translation_lines == ["手动译文"]
    assert invalid_path not in translated_by_path
    assert ensure_json_object(coerce_json_value(invalid_items[0]), "invalid_items[0]")["location_path"] == invalid_path


@pytest.mark.asyncio
async def test_manual_translation_import_valid_requires_invalid_report_before_write(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """显式部分导入缺少无效项报告路径时不能先保存有效项。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    selected: JsonObject = {}
    valid_path = ""
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if entry["item_type"] != "short_text" or any("\n" in line or r"\n" in line for line in original_lines):
            continue
        if not valid_path:
            valid_path = location_path
            entry["translation_lines"] = ["手动译文"]
        else:
            entry["translation_lines"] = ["第一行\n第二行"]
        selected[location_path] = entry
        if len(selected) == 2:
            break
    assert valid_path
    assert len(selected) == 2
    _ = pending_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    _ = await _rebuild_text_index_for_test(service)
    report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=pending_path,
        import_valid=True,
    )

    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()

    assert report.status == "error"
    assert "manual_translation_invalid_report_required" in {error.code for error in report.errors}
    assert translated_items == []


@pytest.mark.asyncio
async def test_export_quality_fix_template_collects_repairable_items(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量修复模板会从报告问题导出标准修复表并预填当前译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    template_path = tmp_path / "quality-fix-template.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    sorted_paths = sorted(payload)
    quality_error_path = sorted_paths[0]
    residual_path = ""
    for candidate_path in sorted_paths:
        if candidate_path == quality_error_path:
            continue
        candidate_entry = ensure_json_object(coerce_json_value(payload[candidate_path]), candidate_path)
        candidate_lines = ensure_json_array(candidate_entry["original_lines"], f"{candidate_path}.original_lines")
        if any(isinstance(line, str) and _contains_japanese_test_char(line) for line in candidate_lines):
            residual_path = candidate_path
            break
    assert residual_path
    placeholder_path = ""
    for candidate_path in sorted_paths:
        if candidate_path in {quality_error_path, residual_path}:
            continue
        candidate_entry = ensure_json_object(coerce_json_value(payload[candidate_path]), candidate_path)
        if candidate_entry["item_type"] == "long_text":
            placeholder_path = candidate_path
            break
    assert placeholder_path
    quality_error_entry = ensure_json_object(coerce_json_value(payload[quality_error_path]), quality_error_path)
    residual_entry = ensure_json_object(coerce_json_value(payload[residual_path]), residual_path)
    placeholder_entry = ensure_json_object(coerce_json_value(payload[placeholder_path]), placeholder_path)
    residual_original_lines = [
        line
        for line in ensure_json_array(residual_entry["original_lines"], f"{residual_path}.original_lines")
        if isinstance(line, str)
    ]
    placeholder_original_lines = [
        line
        for line in ensure_json_array(placeholder_entry["original_lines"], f"{placeholder_path}.original_lines")
        if isinstance(line, str)
    ]
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=residual_path,
                    original_lines=residual_original_lines,
                    translation_lines=residual_original_lines,
                ),
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=placeholder_path,
                    original_lines=placeholder_original_lines,
                    translation_lines=[r"\C[4]甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                ),
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=len(sorted_paths),
            pending_count=len(sorted_paths),
            deduplicated_count=len(sorted_paths),
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=await _current_fact_id_for_path(session, quality_error_path),
                    location_path=quality_error_path,
                    item_type="short_text",
                    role=None,
                    original_lines=[
                        line
                        for line in ensure_json_array(
                            quality_error_entry["original_lines"],
                            f"{quality_error_path}.original_lines",
                        )
                        if isinstance(line, str)
                    ],
                    translation_lines=["候选译文"],
                    error_type="AI漏翻",
                    error_detail=["测试质量错误"],
                    model_response='{"translation_lines":["候选译文"]}',
                )
            ],
        )

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=template_path,
    )

    template = load_json_object(template_path)
    assert report.status == "ok"
    assert report.summary["quality_error_count"] == 1
    assert report.summary["quality_error_items_count"] == 1
    quality_error_category_counts = ensure_json_object(
        report.summary["quality_error_category_counts"],
        "quality_error_category_counts",
    )
    assert quality_error_category_counts["missing_translation"] == 1
    assert report.summary["source_residual_count"] == 1
    assert report.summary["placeholder_risk_count"] == 1
    assert report.summary["overwide_line_count"] == 1
    exported_text_positions: set[str] = set()
    for template_key, raw_entry in template.items():
        template_entry = ensure_json_object(coerce_json_value(raw_entry), str(template_key))
        assert template_key == template_entry["fact_id"]
        text_position = template_entry["text_position"]
        assert isinstance(text_position, str)
        exported_text_positions.add(text_position)
    assert exported_text_positions == {quality_error_path, residual_path, placeholder_path}
    quality_template = _quality_fix_template_entry_by_text_position(template, quality_error_path)
    placeholder_template = _quality_fix_template_entry_by_text_position(template, placeholder_path)
    assert quality_template["translation_lines"] == ["候选译文"]
    assert placeholder_template["translation_lines"] == [r"\C[4]甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"]
    categories = ensure_json_object(report.details["problem_categories_by_path"], "problem_categories_by_path")
    assert categories[placeholder_path] == ["placeholder_risk", "overwide_line"]


@pytest.mark.asyncio
async def test_export_quality_fix_template_preserves_same_path_quality_error_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """同一路径下多个质量错误 fact 必须分别导出，不能被路径键覆盖。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    template_path = tmp_path / "quality-fix-template.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = sorted(payload)[0]
    target_entry = ensure_json_object(coerce_json_value(payload[target_path]), target_path)
    target_original_lines = [
        line
        for line in ensure_json_array(target_entry["original_lines"], f"{target_path}.original_lines")
        if isinstance(line, str)
    ]
    assert target_original_lines

    async with await registry.open_game("テストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await session.read_text_facts(TextFactReadFilter(scope_key=scope.scope_key))
        target_fact = next(fact for fact in facts if fact.location_path == target_path)
        duplicate_fact = replace(
            target_fact,
            fact_id=f"{target_fact.fact_id}:same-path-quality-error",
            raw_text=f"{target_fact.raw_text}\n同路径第二事实",
            visible_text=f"{target_fact.visible_text}\n同路径第二事实",
            translatable_text=f"{target_fact.translatable_text}\n同路径第二事实",
            raw_hash=f"{target_fact.raw_hash}:same-path-quality-error",
            visible_hash=f"{target_fact.visible_hash}:same-path-quality-error",
            translatable_hash=f"{target_fact.translatable_hash}:same-path-quality-error",
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, duplicate_fact])
        run_record = await session.start_translation_run(
            total_extracted=len(facts) + 1,
            pending_count=len(facts) + 1,
            deduplicated_count=len(facts) + 1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=target_fact.fact_id,
                    location_path=target_path,
                    item_type=cast(ItemType, target_fact.item_type),
                    role=target_fact.role or None,
                    original_lines=target_original_lines,
                    translation_lines=["第一候选译文"],
                    error_type="AI漏翻",
                    error_detail=["第一条质量错误"],
                    model_response='{"translation_lines":["第一候选译文"]}',
                ),
                TranslationErrorItem(
                    fact_id=duplicate_fact.fact_id,
                    location_path=target_path,
                    item_type=cast(ItemType, duplicate_fact.item_type),
                    role=duplicate_fact.role or None,
                    original_lines=["同路径第二事实"],
                    translation_lines=["第二候选译文"],
                    error_type="AI漏翻",
                    error_detail=["第二条质量错误"],
                    model_response='{"translation_lines":["第二候选译文"]}',
                ),
            ],
        )

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=template_path,
    )

    template = load_json_object(template_path)
    exported_fact_ids = {
        str(entry["fact_id"])
        for entry in (
            ensure_json_object(coerce_json_value(raw_entry), str(template_key))
            for template_key, raw_entry in template.items()
        )
    }
    assert report.status == "ok"
    assert report.summary["quality_error_count"] == 2
    assert report.summary["exported_count"] == 2
    assert exported_fact_ids == {target_fact.fact_id, duplicate_fact.fact_id}
    assert any(
        ensure_json_object(coerce_json_value(raw_entry), str(template_key))["translation_lines"]
        == ["第一候选译文"]
        for template_key, raw_entry in template.items()
    )
    assert any(
        ensure_json_object(coerce_json_value(raw_entry), str(template_key))["translation_lines"]
        == ["第二候选译文"]
        for template_key, raw_entry in template.items()
    )


@pytest.mark.asyncio
async def test_writable_path_reader_preserves_same_path_text_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """按路径读取可写文本时，同一路径多个当前 fact 必须全部返回。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = sorted(payload)[0]

    async with await registry.open_game("テストゲーム") as session:
        scope = await read_current_text_fact_scope(session)
        facts = await session.read_text_facts(TextFactReadFilter(scope_key=scope.scope_key))
        target_fact = next(fact for fact in facts if fact.location_path == target_path)
        duplicate_fact = replace(
            target_fact,
            fact_id=f"{target_fact.fact_id}:same-path-readable",
            raw_text=f"{target_fact.raw_text}\n同路径第二事实",
            visible_text=f"{target_fact.visible_text}\n同路径第二事实",
            translatable_text=f"{target_fact.translatable_text}\n同路径第二事实",
            raw_hash=f"{target_fact.raw_hash}:same-path-readable",
            visible_hash=f"{target_fact.visible_hash}:same-path-readable",
            translatable_hash=f"{target_fact.translatable_hash}:same-path-readable",
        )
        await session.replace_text_facts(scope=scope, facts=[*facts, duplicate_fact])

        items = await read_writable_text_fact_translation_items_by_paths(session, [target_path])

    returned_fact_ids = {item.fact_id for item in items}
    assert returned_fact_ids == {target_fact.fact_id, duplicate_fact.fact_id}
    assert {item.location_path for item in items} == {target_path}


@pytest.mark.asyncio
async def test_quality_fix_template_restores_prefilled_model_placeholders(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """修复表会把模型临时译文里的程序占位符还原为游戏原始控制符。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    template_path = tmp_path / "quality-fix-template.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    payload = load_json_object(pending_path)
    target_path = ""
    target_original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if any(r"\C[4]" in line for line in original_lines):
            target_path = location_path
            target_original_lines = original_lines
            break

    assert target_path
    async with await registry.open_game("テストゲーム") as session:
        target_fact_id = await _current_fact_id_for_path(session, target_path)
        run_record = await session.start_translation_run(
            total_extracted=len(payload),
            pending_count=len(payload),
            deduplicated_count=len(payload),
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=target_fact_id,
                    location_path=target_path,
                    item_type="long_text",
                    role=None,
                    original_lines=target_original_lines,
                    translation_lines=[r"[RMMZ_TEXT_COLOR_4]强调[RMMZ_TEXT_COLOR_0]"],
                    error_type="控制符不匹配",
                    error_detail=["测试程序占位符还原"],
                    model_response='{"translation_lines":["[RMMZ_TEXT_COLOR_4]强调[RMMZ_TEXT_COLOR_0]"]}',
                )
            ],
        )

    report = await service.export_quality_fix_template(
        game_title="テストゲーム",
        output_path=template_path,
    )

    template = load_json_object(template_path)
    exported_entry = ensure_json_object(coerce_json_value(template[target_fact_id]), target_fact_id)
    text_for_model_lines = ensure_json_array(exported_entry["text_for_model_lines"], f"{target_fact_id}.text_for_model_lines")
    manual_fill_note = exported_entry["manual_fill_note"]
    assert report.status == "ok"
    assert exported_entry["text_position"] == target_path
    assert exported_entry["translation_lines"] == [r"\C[4]强调\C[0]"]
    assert any(isinstance(line, str) and "[RMMZ_TEXT_COLOR_4]" in line for line in text_for_model_lines)
    assert isinstance(manual_fill_note, str)
    assert "text_for_model_lines 只供对照" in manual_fill_note
    assert "游戏原始控制符" in manual_fill_note
@pytest.mark.asyncio
async def test_reset_translations_input_deletes_known_paths_and_warns_missing_saved_paths(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """按输入重置只删除请求路径中已保存的译文，并报告不存在的已保存路径。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"
    reset_path = tmp_path / "reset-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=1,
    )
    payload = load_json_object(pending_path)
    target_path = next(iter(payload))
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        index_items = await session.read_text_index_items()
    already_pending_path = next(item.location_path for item in index_items if item.location_path != target_path)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                await make_current_saved_translation_item_for_test(
                    session,
                    location_path=target_path,
                    original_lines=["こんにちは"],
                    translation_lines=["你好"],
                )
            ]
        )

    _ = reset_path.write_text(
        json.dumps({"location_paths": [target_path, already_pending_path]}, ensure_ascii=False),
        encoding="utf-8",
    )
    report = await service.reset_translations(
        game_title="テストゲーム",
        input_path=reset_path,
    )
    async with await registry.open_game("テストゲーム") as session:
        paths_after_reset = {item.location_path for item in await session.read_translated_items()}
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "warning"
    assert report.summary["requested_count"] == 2
    assert report.summary["reset_count"] == 1
    assert report.summary["already_pending_count"] == 1
    assert {warning.code for warning in report.warnings} == {"reset_translation_already_pending"}
    assert target_path not in paths_after_reset
    pending_count = quality_report.summary["pending_count"]
    assert isinstance(pending_count, int)
    assert pending_count >= 1
@pytest.mark.asyncio
async def test_reset_translations_all_deletes_current_active_translation_cache(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """完整重译入口可以清除当前提取范围内全部已入库译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    _ = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=2,
    )
    payload = load_json_object(pending_path)
    target_paths = list(payload)[:2]
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            await make_current_saved_translation_items_for_test(
                session,
                location_paths=target_paths,
                translations_by_path={target_path: ["你好"] for target_path in target_paths},
            )
        )

    report = await service.reset_translations(game_title="テストゲーム", reset_all=True)
    quality_report = await service.quality_report(game_title="テストゲーム")
    async with await registry.open_game("テストゲーム") as session:
        remaining_paths = {item.location_path for item in await session.read_translated_items()}

    assert report.status == "warning"
    assert report.summary["mode"] == "all"
    assert report.summary["reset_count"] == len(target_paths)
    requested_count = report.summary["requested_count"]
    assert isinstance(requested_count, int)
    assert requested_count >= len(target_paths)
    assert all(target_path not in remaining_paths for target_path in target_paths)
    pending_count = quality_report.summary["pending_count"]
    assert isinstance(pending_count, int)
    assert pending_count >= len(target_paths)
