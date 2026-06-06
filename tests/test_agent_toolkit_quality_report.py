"""Agent 质量报告和质量门禁业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *

@pytest.mark.asyncio
async def test_mv_virtual_namebox_validation_reports_overwide_angle_rule_hits(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """校验会指出尖括号宽规则误吞动态控制符，并列出新命中的候选。"""
    mv_common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    raw_value = coerce_json_value(cast(object, json.loads(mv_common_events_path.read_text(encoding="utf-8"))))
    mv_common_events = ensure_json_array(raw_value, "CommonEvents.json")
    mv_common_events.extend(
        [
            {
                "id": 2,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<\\n[1]>"]},
                    {"code": 401, "parameters": ["動的名の本文です"]},
                    {"code": 0, "parameters": []},
                ],
            },
            {
                "id": 3,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": ["<シナリオ>"]},
                    {"code": 401, "parameters": ["制作表示です"]},
                    {"code": 0, "parameters": []},
                ],
            },
        ]
    )
    _ = mv_common_events_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    validate_report = await service.validate_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_broad_mv_angle_namebox_rules_text(),
    )
    import_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_broad_mv_angle_namebox_rules_text(),
    )
    details = ensure_json_object(validate_report.details, "details")
    newly_matched_candidates = ensure_json_array(
        details["newly_matched_candidates"],
        "details.newly_matched_candidates",
    )
    newly_matched_texts: set[str] = set()
    for index, raw_detail in enumerate(newly_matched_candidates):
        detail = ensure_json_object(raw_detail, f"details.newly_matched_candidates[{index}]")
        text = detail.get("text")
        if isinstance(text, str):
            newly_matched_texts.add(text)
    validate_json = validate_report.to_json_text()
    newly_matched_count = validate_report.summary["newly_matched_candidate_count"]

    assert validate_report.status == "error"
    assert import_report.status == "error"
    assert "broad-angle" in validate_json
    assert "标准角色名控制符被 translate 规则命中" in validate_json
    assert isinstance(newly_matched_count, int)
    assert newly_matched_count >= 2
    assert "<\\n[1]>" in newly_matched_texts
    assert "<シナリオ>" in newly_matched_texts
@pytest.mark.asyncio
async def test_write_back_probe_uses_shallow_probe_items(
    minimal_game_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写入探针只替换译文行，不深拷贝原文和定位结构。"""
    game_data = await load_game_data(minimal_game_dir)
    source_item = TranslationItem(
        location_path="Items.json/1/name",
        item_type="short_text",
        role="item_name",
        original_lines=["薬草"],
        source_line_paths=["Items.json/1/name"],
        translation_lines=["既存译文"],
        placeholder_map={"[RMMZ_TEST_1]": "\\C[1]"},
    )
    received_items: list[TranslationItem] = []

    def fake_collect_native_write_protocol_details(
        *,
        game_data: JsonObject,
        plugins_js: list[JsonValue],
        items: list[TranslationItem],
    ) -> list[JsonValue]:
        """捕获探针条目，避免测试依赖 Rust 写入协议结果。"""
        _ = (game_data, plugins_js)
        received_items.extend(items)
        return []

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        fake_collect_native_write_protocol_details,
    )

    reasons = collect_write_back_probe_reasons(
        game_data=game_data,
        active_items=[source_item],
    )

    assert reasons == {}
    assert len(received_items) == 1
    probe_item = received_items[0]
    assert probe_item is not source_item
    assert probe_item.original_lines is source_item.original_lines
    assert probe_item.source_line_paths is source_item.source_line_paths
    assert probe_item.placeholder_map is source_item.placeholder_map
    assert probe_item.translation_lines == ["回写校验"]
    assert source_item.translation_lines == ["既存译文"]
@pytest.mark.asyncio
async def test_quality_report_stops_on_coverage_error_before_native_checks(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include_write_probe 不应回退旧 Python 文本范围写入探针。"""

    def forbidden_scope_write_protocol(*args: object, **kwargs: object) -> NoReturn:
        """质量报告不应再通过 TextScopeService 的写入探针制造覆盖错误。"""
        _ = (args, kwargs)
        raise AssertionError("quality-report 不应回退 app.text_scope.write_probe")

    monkeypatch.setattr(
        "app.text_scope.write_probe.collect_native_write_protocol_details",
        forbidden_scope_write_protocol,
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.quality_report(game_title="テストゲーム", include_write_probe=True)

    assert report.status == "error"
    assert "coverage_unwritable" not in {error.code for error in report.errors}
    assert "write_probe_failed" not in {error.code for error in report.errors}
    assert report.summary["write_back_probe_requested"] is True
    assert report.summary["write_back_probe_executed"] is True
    assert report.summary["write_back_probe_mode"] == "rust_write_gate"
    assert report.summary["write_back_probe_enabled"] is True
    assert report.summary["write_back_protocol_count"] == 0
@pytest.mark.asyncio
async def test_quality_report_include_write_probe_uses_rust_quality_gate(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回级质量报告必须输出 Rust quality gate 的结构化结果。"""

    rust_gate_calls: list[dict[str, object]] = []
    quality_detail_calls = 0
    protocol_detail_calls = 0

    def fake_native_quality_details(**kwargs: object) -> NativeQualityDetails:
        """记录结构化原生质量明细调用。"""
        nonlocal quality_detail_calls
        _ = kwargs
        quality_detail_calls += 1
        return NativeQualityDetails(
            source_residual_items=[],
            text_structure_items=[],
            placeholder_risk_items=[],
            overwide_line_items=[],
        )

    def fake_write_protocol_details(**kwargs: object) -> JsonArray:
        """记录结构化写回协议明细调用。"""
        nonlocal protocol_detail_calls
        _ = kwargs
        protocol_detail_calls += 1
        return []

    def fake_rust_quality_gate(**kwargs: object) -> object:
        rust_gate_calls.append(dict(kwargs))
        assert kwargs["mode"] == "quality_gate"
        assert "content_output_dir" not in kwargs
        return SimpleNamespace(
            summary=SimpleNamespace(
                data_item_count=1,
                plugin_item_count=0,
                terminology_written_count=0,
                plugin_source_runtime_map_count=0,
            ),
            timings_ms={"quality_gate": 1, "total": 2},
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        game_data = await load_game_data(minimal_game_dir)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        translated_items = [
            TranslationItem(
                location_path=item.location_path,
                item_type=item.item_type,
                role=item.role,
                original_lines=[line for line in item.original_lines],
                source_line_paths=[path for path in item.source_line_paths],
                translation_lines=[
                    _translated_test_line_preserving_controls(line, text_rules)
                    for line in item.original_lines
                ],
            )
            for item in scope.active_items()
        ]
        await session.write_translation_items(translated_items)

    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.collect_agent_service_native_quality_details",
        fake_native_quality_details,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.collect_agent_service_native_write_protocol_details",
        fake_write_protocol_details,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.build_native_write_back_plan",
        fake_rust_quality_gate,
    )

    report = await service.quality_report(game_title="テストゲーム", include_write_probe=True)

    assert rust_gate_calls
    assert quality_detail_calls == 1
    assert protocol_detail_calls == 1
    assert report.summary["write_back_probe_requested"] is True
    assert report.summary["write_back_probe_executed"] is True
    assert report.summary["write_back_probe_mode"] == "rust_write_gate"
    assert report.summary["write_back_probe_enabled"] is True
    write_back_gate = ensure_json_object(report.summary["write_back_gate"], "write_back_gate")
    assert write_back_gate["status"] == "ok"
    assert write_back_gate["mode"] == "quality_gate"
@pytest.mark.asyncio
async def test_quality_report_write_probe_and_write_back_share_rust_gate_error(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一坏译文在质量报告和写回中必须由同一 Rust 写回级 gate 阻断。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    _ = (app_home / "setting.toml").write_text(
        example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        placeholder_record = PlaceholderRuleRecord(
            pattern_text=r"(?i)\\F\d*\[[^\]\r\n]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
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
        )
        game_data = await load_game_data(minimal_game_dir)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        writable_items = [
            item
            for item in scope.active_items()
            if item.location_path in scope.writable_paths
        ]
        bad_location_path = next(
            item.location_path
            for item in writable_items
            if any(list(text_rules.iter_control_sequence_spans(line)) for line in item.original_lines)
        )
        translated_items = [
            TranslationItem(
                location_path=item.location_path,
                item_type=item.item_type,
                role=item.role,
                original_lines=[line for line in item.original_lines],
                source_line_paths=[path for path in item.source_line_paths],
                translation_lines=(
                    ["测试" for _line in item.original_lines]
                    if item.location_path == bad_location_path
                    else [
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ]
                ),
            )
            for item in writable_items
        ]
        await session.write_translation_items(translated_items)

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム", include_write_probe=True)
    write_back_gate = ensure_json_object(report.summary["write_back_gate"], "write_back_gate")
    gate_message = write_back_gate["message"]
    assert report.status == "error"
    assert "write_back_gate" in {error.code for error in report.errors}
    assert write_back_gate["status"] == "error"
    assert isinstance(gate_message, str)
    assert gate_message

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError) as error_info:
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()

    write_back_message = str(error_info.value)
    assert "游戏控制符可能被改坏" in write_back_message
    assert "占位符" in write_back_message
    assert "游戏控制符可能被改坏" in gate_message
    assert "占位符" in gate_message
@pytest.mark.asyncio
async def test_validate_source_residual_rules_rejects_rust_incompatible_structural_regex(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """源文残留结构规则导入前必须通过 Rust regex 预检。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "position_rules": {},
            "structural_rules": [
                {
                    "pattern": r"(?<=<label>)(?P<visible>[^<]+)(?=</label>)",
                    "allowed_terms": ["label"],
                    "check_group": "visible",
                    "reason": "protocol_label",
                }
            ],
        },
        ensure_ascii=False,
    )

    report = await service.validate_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert report.status == "error"
    assert "source_residual_rules_invalid" in {error.code for error in report.errors}
    assert "Rust regex" in report.errors[0].message
@pytest.mark.asyncio
async def test_quality_report_cold_rebuilds_missing_text_index(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """普通 quality-report 缺索引时自动 cold rebuild，并报告重建阶段信息。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["text_index_status"] == "cold_rebuilt"
    rebuild_summary = ensure_json_object(report.summary["text_index_rebuild_summary"], "text_index_rebuild_summary")
    assert rebuild_summary["index_status"] == "rebuilt"
    assert "stage_timings" in rebuild_summary
    async with await registry.open_game("テストゲーム") as session:
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        assert metadata.item_count == report.summary["extractable_count"]
@pytest.mark.asyncio
async def test_quality_report_uses_text_index_without_full_scope_load(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通 quality-report 在 warm index 存在时不加载完整游戏数据。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """warm index 质量报告不应触碰游戏文件加载。"""
        _ = (args, kwargs)
        raise AssertionError("warm index quality-report 不应加载完整游戏数据")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    monkeypatch.setattr(
        "app.agent_toolkit.services.core.CoreAgentMixin._load_translation_source_game_data",
        forbidden_game_data_load,
    )

    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["text_index_status"] == "used"
    assert report.summary["extractable_count"] == rebuild_report.summary["indexed_count"]
    stage_timings = ensure_json_object(report.summary["stage_timings"], "stage_timings")
    assert "read_index_and_state" in stage_timings
    assert "total" in stage_timings
    assert isinstance(report.summary["native_thread_count"], int)
    assert report.summary["native_quality_payload_item_count"] == report.summary["translated_count"]
    coverage = ensure_json_object(report.details["coverage"], "coverage")
    assert coverage["detail_mode"] == "sampled"
    pending_paths = ensure_json_object(coverage["pending_location_paths"], "pending_location_paths")
    assert set(pending_paths) == {"count", "samples", "omitted_count"}


@pytest.mark.asyncio
async def test_quality_report_large_warm_index_uses_count_fast_path(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """大库 warm index 质量报告不得读取全量索引和全量译文。"""

    async def forbidden_index_items_read(self: TargetGameSession) -> NoReturn:
        """count 快路径不应读取全量文本范围索引。"""
        _ = self
        raise AssertionError("大库 quality-report 不应读取全量文本范围索引")

    async def forbidden_translated_items_read(self: TargetGameSession) -> NoReturn:
        """count 快路径不应读取全量译文。"""
        _ = self
        raise AssertionError("大库 quality-report 不应读取全量译文")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        index_records = await session.read_text_index_items()
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=[
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in index_records
                if item.writable
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=len(index_records),
            pending_count=0,
            deduplicated_count=len(index_records),
            batch_count=1,
        )
        await session.write_translation_run(
            run_record.model_copy(
                update={
                    "status": "completed",
                    "success_count": len(index_records),
                    "finished_at": run_record.updated_at,
                }
            )
        )

    monkeypatch.setattr("app.agent_toolkit.services.quality.QUALITY_REPORT_FULL_RECHECK_LIMIT", 0)
    monkeypatch.setattr(TargetGameSession, "read_text_index_items", forbidden_index_items_read)
    monkeypatch.setattr(TargetGameSession, "read_translated_items", forbidden_translated_items_read)

    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["native_quality_payload_item_count"] == 0
    assert report.summary["native_quality_recheck_mode"] == "saved_error_records"
    coverage = ensure_json_object(report.details["coverage"], "coverage")
    assert coverage["detail_mode"] == "count_only"
@pytest.mark.asyncio
async def test_quality_report_treats_source_residual_as_error(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告把未放行的源文残留风险作为禁止写进游戏文件的问题。"""
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
    residual_path = ""
    residual_original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if any(_contains_japanese_test_char(line) for line in original_lines):
            residual_path = location_path
            residual_original_lines = original_lines
            break
    assert residual_path

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=residual_path,
                    item_type="short_text",
                    role=None,
                    original_lines=residual_original_lines,
                    source_line_paths=[],
                    translation_lines=residual_original_lines,
                )
            ]
        )

    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    warning_codes = {warning.code for warning in report.warnings}
    assert report.status == "error"
    assert "source_residual" in error_codes
    assert "source_residual" not in warning_codes
    assert report.summary["source_residual_count"] == 1
@pytest.mark.asyncio
async def test_quality_report_structural_source_residual_rule_is_line_scoped(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构性源文例外在原生质检中只遮蔽协议词，不放行显示文本残留。"""
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
    original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        entry_original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if len(entry_original_lines) == 1:
            target_path = location_path
            original_lines = entry_original_lines
            break
    assert target_path
    rules_text = json.dumps(
        {
            "position_rules": {},
            "structural_rules": [
                {
                    "pattern": r"^(?P<protocol>なまえ):(?P<visible>.*)$",
                    "allowed_terms": ["なまえ"],
                    "check_group": "visible",
                    "reason": "protocol_label",
                }
            ],
        },
        ensure_ascii=False,
    )

    import_rules_report = await service.import_source_residual_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=original_lines,
                    source_line_paths=[],
                    translation_lines=["なまえ:你好"],
                )
            ]
        )
    protocol_report = await service.quality_report(game_title="テストゲーム")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=target_path,
                    item_type="short_text",
                    role=None,
                    original_lines=original_lines,
                    source_line_paths=[],
                    translation_lines=["なまえ:なまえ"],
                )
            ]
        )
    leaked_report = await service.quality_report(game_title="テストゲーム")

    assert import_rules_report.status == "ok"
    assert protocol_report.summary["source_residual_count"] == 0
    assert leaked_report.summary["source_residual_count"] == 1
@pytest.mark.asyncio
async def test_quality_report_errors_on_corrupt_source_residual_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告遇到损坏的源文残留例外规则时返回明确业务错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_source_residual_rules(
            [
                SourceResidualRuleRecord(
                    rule_id="structural:broken",
                    rule_type="structural",
                    pattern_text="[",
                    allowed_terms=["なまえ"],
                    check_group="visible",
                    reason="broken",
                )
            ]
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert "source_residual_rules_invalid" in {error.code for error in report.errors}
@pytest.mark.asyncio
async def test_quality_report_ignores_stale_saved_translation_quality_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告把当前不可写的已保存译文作为必须处理的问题。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Removed.json/1/name",
                    item_type="short_text",
                    role=None,
                    original_lines=["こんにちは"],
                    source_line_paths=[],
                    translation_lines=["こんにちは"],
                )
            ]
        )

    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    warning_codes = {warning.code for warning in report.warnings}
    assert "source_residual" not in error_codes
    assert "stale_saved_translations" in error_codes
    assert "stale_saved_translations" not in warning_codes
    assert report.summary["stale_translation_count"] == 1
    assert report.summary["source_residual_count"] == 0
    assert report.details["source_residual_items"] == []
@pytest.mark.asyncio
async def test_quality_report_uses_command_setting_overrides(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """写入前质量报告使用本次命令传入的文本规则覆盖。"""
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
    residual_path = ""
    residual_original_lines: list[str] = []
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = [
            line
            for line in ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
            if isinstance(line, str)
        ]
        if any(_contains_japanese_test_char(line) for line in original_lines):
            residual_path = location_path
            residual_original_lines = original_lines
            break
    assert residual_path

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=residual_path,
                    item_type="short_text",
                    role=None,
                    original_lines=residual_original_lines,
                    source_line_paths=[],
                    translation_lines=["中カ"],
                )
            ]
        )

    default_report = await service.quality_report(game_title="テストゲーム")
    override_report = await service.quality_report(
        game_title="テストゲーム",
        setting_overrides=SettingOverrides(source_residual_allowed_chars=["カ"]),
    )

    default_error_codes = {error.code for error in default_report.errors}
    override_error_codes = {error.code for error in override_report.errors}
    assert "source_residual" in default_error_codes
    assert "source_residual" not in override_error_codes
    assert default_report.summary["source_residual_count"] == 1
    assert override_report.summary["source_residual_count"] == 0
@pytest.mark.asyncio
async def test_quality_report_counts_errors_and_model_response(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告读取译文、质量错误和规则状态，输出阻断级错误摘要。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=[r"\C[4]甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )
        run_record = await session.start_translation_run(
            total_extracted=3,
            pending_count=2,
            deduplicated_count=2,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    location_path="CommonEvents.json/1/2",
                    item_type="array",
                    role=None,
                    original_lines=["はい", "いいえ"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["缺少键"],
                    model_response='{"bad": true}',
                )
            ],
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["quality_error_count"] == 1
    assert report.summary["model_response_error_count"] == 1
    assert report.summary["placeholder_risk_count"] == 1
    assert report.summary["overwide_line_count"] == 1
    assert report.details["error_type_counts"] == {"AI漏翻": 1}
    quality_error_items = ensure_json_array(report.details["quality_error_items"], "quality_error_items")
    placeholder_items = ensure_json_array(report.details["placeholder_risk_items"], "placeholder_risk_items")
    overwide_items = ensure_json_array(report.details["overwide_line_items"], "overwide_line_items")
    quality_error_detail = ensure_json_object(quality_error_items[0], "quality_error_items[0]")
    placeholder_detail = ensure_json_object(placeholder_items[0], "placeholder_risk_items[0]")
    overwide_detail = ensure_json_object(overwide_items[0], "overwide_line_items[0]")
    assert quality_error_detail["location_path"] == "CommonEvents.json/1/2"
    assert quality_error_detail["error_type"] == "AI漏翻"
    assert placeholder_detail["location_path"] == "CommonEvents.json/1/0"
    assert overwide_detail["location_path"] == "CommonEvents.json/1/0"
    assert overwide_detail["line_width"] == 30
@pytest.mark.asyncio
async def test_quality_report_flags_internal_placeholder_leak(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告必须拦截译文里的项目内部占位符。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好[RMMZ_TEXT_COLOR_0]"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["placeholder_risk_count"] == 1
    placeholder_items = ensure_json_array(report.details["placeholder_risk_items"], "placeholder_risk_items")
    placeholder_detail = ensure_json_object(placeholder_items[0], "placeholder_risk_items[0]")
    assert placeholder_detail["location_path"] == "CommonEvents.json/1/0"
    assert "译文残留项目内部占位符" in str(placeholder_detail["reason"])
@pytest.mark.asyncio
async def test_quality_report_accepts_saved_short_text_real_line_breaks(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告复查已保存译文时允许游戏文件需要的真实换行。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/description",
                    item_type="short_text",
                    role=None,
                    original_lines=["説明\n本文"],
                    source_line_paths=["Items.json/1/description"],
                    translation_lines=["说明\n正文"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["placeholder_risk_count"] == 0
@pytest.mark.asyncio
async def test_quality_report_allows_common_english_rpg_abbreviations(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """英文质量检查允许常见 RPG 与系统缩写保留在中文译文中。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    async with await registry.open_game("English Fixture Game") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="Guide",
                    original_lines=["Play the BGM before the NPC raises ATK."],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["在 NPC 提升 ATK 前播放 BGM。"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="English Fixture Game")

    assert report.summary["source_residual_count"] == 0
    assert report.details["source_residual_items"] == []
@pytest.mark.asyncio
async def test_quality_report_accepts_structured_placeholder_shell_and_rejects_changed_shell(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告不把已保护外壳当英文残留，但会拦截被改坏的外壳。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    structured_rule = StructuredPlaceholderRuleRecord(
        rule_name="MINI_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
        translatable_group="text",
        protected_groups={
            "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
            "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
        },
    )
    async with await registry.open_game("English Fixture Game") as session:
        await session.replace_structured_placeholder_rules([structured_rule])
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="Guide",
                    original_lines=["<Mini Label: Alraune>"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["<Mini Label: 阿尔劳娜>"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    accepted_report = await service.quality_report(game_title="English Fixture Game")

    assert accepted_report.summary["placeholder_risk_count"] == 0
    assert accepted_report.summary["source_residual_count"] == 0

    async with await registry.open_game("English Fixture Game") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="Guide",
                    original_lines=["<Mini Label: Alraune>"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["<迷你标签: 阿尔劳娜>"],
                )
            ]
        )

    rejected_report = await service.quality_report(game_title="English Fixture Game")

    assert rejected_report.summary["placeholder_risk_count"] == 1
def test_native_quality_reports_structured_placeholder_conflicts() -> None:
    """Rust 质检核心必须和 Python 文本规则一样拒绝结构化保护范围冲突。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="en")
    text_rules = TextRules.from_setting(
        setting.text_rules,
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                pattern_text=r">",
                placeholder_template="[CUSTOM_CLOSE_{index}]",
            ),
        ),
        structured_placeholder_rules=(
            StructuredPlaceholderRule.create(
                rule_name="MINI_LABEL",
                rule_type="paired_shell",
                pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
                translatable_group="text",
                protected_groups={
                    "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                    "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
                },
            ),
        ),
    )
    items = [
        TranslationItem(
            location_path="CommonEvents.json/1/0",
            item_type="long_text",
            role="Guide",
            original_lines=["<Mini Label: Alraune>"],
            source_line_paths=["CommonEvents.json/1/1"],
            translation_lines=["<Mini Label: 阿尔劳娜>"],
        )
    ]
    details = collect_native_quality_details(
        items=items,
        text_rules=text_rules,
        source_residual_rules=[],
    )
    counts = collect_native_quality_counts(
        items=items,
        text_rules=text_rules,
        source_residual_rules=[],
    )

    assert len(details.placeholder_risk_items) == 1
    assert counts.placeholder_risk_count == 1
    assert counts.source_residual_count == len(details.source_residual_items)
    assert counts.text_structure_count == len(details.text_structure_items)
    assert counts.overwide_line_count == len(details.overwide_line_items)
    assert "结构化占位符保护片段与已有控制符规则重叠" in json.dumps(
        details.placeholder_risk_items,
        ensure_ascii=False,
    )
def test_native_quality_accepts_structured_placeholder_lookahead_pattern() -> None:
    """Python 已校验的结构化正则能力，Rust 质检核心不能再用更窄子集误拒。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="en")
    text_rules = TextRules.from_setting(
        setting.text_rules,
        structured_placeholder_rules=(
            StructuredPlaceholderRule.create(
                rule_name="LOOK_LABEL",
                rule_type="paired_shell",
                pattern_text=r"(?P<open><Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)(?!x)",
                translatable_group="text",
                protected_groups={
                    "open": "[CUSTOM_LOOK_LABEL_OPEN_{index}]",
                    "close": "[CUSTOM_LOOK_LABEL_CLOSE_{index}]",
                },
            ),
        ),
    )
    details = collect_native_quality_details(
        items=[
            TranslationItem(
                location_path="CommonEvents.json/1/0",
                item_type="long_text",
                role="Guide",
                original_lines=["<Label: Alice>"],
                source_line_paths=["CommonEvents.json/1/1"],
                translation_lines=["<Label: 爱丽丝>"],
            )
        ],
        text_rules=text_rules,
        source_residual_rules=[],
    )

    assert details.placeholder_risk_items == []
    assert details.source_residual_items == []
def test_native_quality_rejects_changed_long_control_candidate_hidden_by_standard_prefix() -> None:
    """Rust 质检不能让标准短控制符静默吞掉更长自定义候选。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    details = collect_native_quality_details(
        items=[
            TranslationItem(
                location_path="CommonEvents.json/1/0",
                item_type="long_text",
                role=None,
                original_lines=[r"\nn[Name]OK"],
                source_line_paths=["CommonEvents.json/1/0"],
                translation_lines=[r"\nn[Other]OK"],
            )
        ],
        text_rules=text_rules,
        source_residual_rules=[],
    )

    assert len(details.placeholder_risk_items) == 1
    assert r"\nn[Name]" in json.dumps(details.placeholder_risk_items, ensure_ascii=False)
    assert r"\nn[Other]" in json.dumps(details.placeholder_risk_items, ensure_ascii=False)
def test_native_quality_accepts_repeated_structured_shell_markers() -> None:
    """Rust 质检按原文顺序反查重复结构化外壳，不把所有外壳归到最后编号。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(
        setting.text_rules,
        structured_placeholder_rules=(
            StructuredPlaceholderRule.create(
                rule_name="BRACKET_TITLE",
                rule_type="paired_shell",
                pattern_text=r"(?P<open>【)(?P<text>[^【】\r\n]*?)(?P<close>】)",
                translatable_group="text",
                protected_groups={
                    "open": "[CUSTOM_BRACKET_TITLE_OPEN_{index}]",
                    "close": "[CUSTOM_BRACKET_TITLE_CLOSE_{index}]",
                },
            ),
        ),
    )
    details = collect_native_quality_details(
        items=[
            TranslationItem(
                location_path="Skills.json/282/description",
                item_type="short_text",
                role=None,
                original_lines=["【自身の我慢-5】【MP＋10】【相手の我慢　↑】"],
                source_line_paths=["Skills.json/282/description"],
                translation_lines=["【自身忍耐-5】【MP＋10】【对方忍耐　↑】"],
            )
        ],
        text_rules=text_rules,
        source_residual_rules=[],
    )

    assert details.placeholder_risk_items == []
    assert details.text_structure_items == []
    assert details.source_residual_items == []
def test_native_quality_rejects_extra_repeated_structured_shell_marker() -> None:
    """Rust 质检遇到额外同类结构化外壳时必须报告占位符风险。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(
        setting.text_rules,
        structured_placeholder_rules=(
            StructuredPlaceholderRule.create(
                rule_name="BRACKET_TITLE",
                rule_type="paired_shell",
                pattern_text=r"(?P<open>【)(?P<text>[^【】\r\n]*?)(?P<close>】)",
                translatable_group="text",
                protected_groups={
                    "open": "[CUSTOM_BRACKET_TITLE_OPEN_{index}]",
                    "close": "[CUSTOM_BRACKET_TITLE_CLOSE_{index}]",
                },
            ),
        ),
    )
    details = collect_native_quality_details(
        items=[
            TranslationItem(
                location_path="Skills.json/282/description",
                item_type="short_text",
                role=None,
                original_lines=["【自身の我慢-5】【MP＋10】"],
                source_line_paths=["Skills.json/282/description"],
                translation_lines=["【自身忍耐-5】【MP＋10】【额外】"],
            )
        ],
        text_rules=text_rules,
        source_residual_rules=[],
    )

    assert len(details.placeholder_risk_items) == 1
    assert "CUSTOM_UNEXPECTED_1" in json.dumps(
        details.placeholder_risk_items,
        ensure_ascii=False,
    )
@pytest.mark.asyncio
async def test_quality_report_flags_multiline_short_text_overwide_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告按单值文本的实际显示行检查 Note 标签超宽风险。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_value = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    items = ensure_json_array(raw_value, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:説明\n原文>"
    _ = items_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [
                NoteTagTextRuleRecord(
                    file_name="Items.json",
                    tag_names=["拡張説明"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=["説明\n原文"],
                    translation_lines=["说明\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    overwide_items = ensure_json_array(report.details["overwide_line_items"], "overwide_line_items")
    overwide_detail = ensure_json_object(overwide_items[0], "overwide_line_items[0]")
    assert report.summary["overwide_line_count"] == 1
    assert overwide_detail["location_path"] == "Items.json/1/note/拡張説明"
    assert overwide_detail["item_type"] == "short_text"
    assert overwide_detail["line_index"] == 1
    assert overwide_detail["line_width"] == 30
@pytest.mark.asyncio
async def test_quality_report_flags_literal_line_break_short_text_overwide_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告会把字面量反斜杠 n 也当作游戏显示换行检查行宽。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_value = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    items = ensure_json_array(raw_value, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = r"<拡張説明:説明\n原文>"
    _ = items_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [
                NoteTagTextRuleRecord(
                    file_name="Items.json",
                    tag_names=["拡張説明"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=[r"説明\n原文"],
                    translation_lines=[r"说明\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    overwide_items = ensure_json_array(report.details["overwide_line_items"], "overwide_line_items")
    overwide_detail = ensure_json_object(overwide_items[0], "overwide_line_items[0]")
    assert report.summary["overwide_line_count"] == 1
    assert overwide_detail["location_path"] == "Items.json/1/note/拡張説明"
    assert overwide_detail["item_type"] == "short_text"
    assert overwide_detail["line_index"] == 1
    assert overwide_detail["line_width"] == 30
@pytest.mark.asyncio
async def test_quality_report_allows_original_overwide_short_text_line(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """原文同一显示行本来很长时，单值文本不按普通对话框宽度误报。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_value = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    items = ensure_json_array(raw_value, "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:説明\n原原原原原原原原原原原原原原原原原原原原原原原原原原原原原原>"
    _ = items_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [
                NoteTagTextRuleRecord(
                    file_name="Items.json",
                    tag_names=["拡張説明"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=["説明\n原原原原原原原原原原原原原原原原原原原原原原原原原原原原原原"],
                    translation_lines=["说明\n甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    assert report.summary["overwide_line_count"] == 0
@pytest.mark.asyncio
async def test_quality_report_flags_saved_short_text_structure_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告会拦截已保存译文中改动单字段结构的问题。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/description",
                    item_type="short_text",
                    original_lines=["アイテム説明"],
                    translation_lines=["说明\n额外一行"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    text_structure_items = ensure_json_array(report.details["text_structure_items"], "text_structure_items")
    text_structure_detail = ensure_json_object(text_structure_items[0], "text_structure_items[0]")
    assert "text_structure" in error_codes
    assert report.summary["text_structure_count"] == 1
    assert text_structure_detail["location_path"] == "Items.json/1/description"
@pytest.mark.asyncio
async def test_quality_report_flags_saved_long_text_artifacts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告会拦截已保存 long_text 中的异常空行和转义碎片。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは", "怖がらなくていい"],
                    source_line_paths=["CommonEvents.json/1/1", "CommonEvents.json/1/2"],
                    translation_lines=[
                        "「不用那么害怕也行。",
                        "　看样子你是不习惯吧……？\\",
                        "",
                        "　来，把身体交给我吧。」",
                    ],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.quality_report(game_title="テストゲーム")

    error_codes = {error.code for error in report.errors}
    text_structure_items = ensure_json_array(report.details["text_structure_items"], "text_structure_items")
    text_structure_detail = ensure_json_object(text_structure_items[0], "text_structure_items[0]")
    reason_text = str(text_structure_detail["reason"])
    assert "text_structure" in error_codes
    assert report.summary["text_structure_count"] == 1
    assert text_structure_detail["location_path"] == "CommonEvents.json/1/0"
    assert "原文没有空行" in reason_text
    assert "行尾裸反斜杠" in reason_text
def test_native_quality_accepts_long_text_empty_line_and_standard_controls() -> None:
    """Rust 质检允许原文需要的空行和正常 RPG Maker 控制符。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    details = collect_native_quality_details(
        items=[
            TranslationItem(
                location_path="CommonEvents.json/1/0",
                item_type="long_text",
                role="アリス",
                original_lines=[r"\N[1]\C[4]こんにちは\C[0]\!", "", r"\\"],
                source_line_paths=["CommonEvents.json/1/1"],
                translation_lines=[r"\N[1]\C[4]你好\C[0]\!", "", r"\\"],
            )
        ],
        text_rules=text_rules,
        source_residual_rules=[],
    )

    assert details.text_structure_items == []
    assert details.placeholder_risk_items == []
