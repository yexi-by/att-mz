"""Agent 试玩反馈和激活运行态诊断业务契约测试。"""

from __future__ import annotations

from typing import NoReturn

from tests.agent_toolkit_contract_fixtures import *

@pytest.mark.asyncio
async def test_feedback_verification_and_plugin_source_scan_are_structural_only(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """反馈反查能提示源码命中，完整候选只能通过 AST 地图导出。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), str(common_events_path))
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    command_list = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    parameters: JsonArray = ["一行\n二行"]
    command: JsonObject = {"code": 401, "parameters": parameters}
    command_list.insert(2, command)
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "\n".join(
            [
                "Window_Base.prototype.drawText('プラグイン直書き', 0, 0, 320);",
                "Window_Base.prototype.drawText('img/system/日本語.png', 0, 0, 320);",
            ]
        ),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    feedback_path = tmp_path / "feedback-texts.json"
    risk_report_path = tmp_path / "plugin-source-risk-report.json"
    ast_map_path = tmp_path / "plugin-source-ast-map.json"
    _ = feedback_path.write_text(
        json.dumps(["こんにちは", "プラグイン直書き", "一行\n二行"], ensure_ascii=False),
        encoding="utf-8",
    )

    verify_report = await service.verify_feedback_text(game_title="テストゲーム", input_path=feedback_path)
    scan_report = await service.scan_plugin_source_text(game_title="テストゲーム", output_path=risk_report_path)
    ast_report = await service.export_plugin_source_ast_map(game_title="テストゲーム", output_path=ast_map_path)
    risk_report = load_json_object(risk_report_path)
    ast_map = load_json_object(ast_map_path)
    ast_files = ensure_json_array(coerce_json_value(ast_map["files"]), "plugin-source-ast-map.files")
    candidates: JsonArray = []
    for ast_file in ast_files:
        ast_file_object = ensure_json_object(coerce_json_value(ast_file), "plugin-source-ast-map.files[]")
        candidates.extend(
            ensure_json_array(
                coerce_json_value(ast_file_object["candidates"]),
                "plugin-source-ast-map.files[].candidates",
            )
        )
    occurrence_count = verify_report.summary["occurrence_count"]

    assert verify_report.status == "error"
    assert isinstance(occurrence_count, int)
    assert occurrence_count >= 1
    occurrences = ensure_json_array(verify_report.details["occurrences"], "occurrences")
    gap_types: set[str] = set()
    for occurrence in occurrences:
        occurrence_object = ensure_json_object(coerce_json_value(occurrence), "occurrence")
        gap_type = occurrence_object.get("gap_type")
        if isinstance(gap_type, str):
            gap_types.add(gap_type)
    assert "translation_gap" in gap_types
    assert "plugin_source_hardcoded" in gap_types
    assert any(
        ensure_json_object(coerce_json_value(occurrence), "occurrence").get("text") == "一行\n二行"
        for occurrence in occurrences
    )
    assert scan_report.status == "ok"
    assert ast_report.status == "ok"
    assert "candidates" not in risk_report
    assert "files" not in risk_report
    assert risk_report["candidate_count"] == 2
    assert any(
        ensure_json_object(coerce_json_value(candidate), "candidate").get("text") == "プラグイン直書き"
        for candidate in candidates
    )
    resource_candidate = next(
        ensure_json_object(coerce_json_value(candidate), "candidate")
        for candidate in candidates
        if ensure_json_object(coerce_json_value(candidate), "candidate").get("text") == "img/system/日本語.png"
    )
    assert resource_candidate["structural_flags"] == ["resource_path_like"]


@pytest.mark.asyncio
async def test_verify_feedback_text_uses_warm_text_index_without_full_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """反馈反查缺口分类必须消费 warm text_index，不能临时构建完整文本范围。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    feedback_path = tmp_path / "feedback-texts.json"
    _ = feedback_path.write_text(json.dumps(["こんにちは"], ensure_ascii=False), encoding="utf-8")

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("verify-feedback-text must classify gaps from warm text_index")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)

    report = await service.verify_feedback_text(game_title="テストゲーム", input_path=feedback_path)

    assert report.status == "error"
    assert report.summary["text_index_status"] == "used"
    occurrence_count = report.summary["occurrence_count"]
    assert isinstance(occurrence_count, int)
    assert occurrence_count >= 1
    occurrences = ensure_json_array(report.details["occurrences"], "occurrences")
    gap_types: set[str] = set()
    for occurrence in occurrences:
        occurrence_object = ensure_json_object(coerce_json_value(occurrence), "occurrence")
        gap_type = occurrence_object.get("gap_type")
        if isinstance(gap_type, str):
            gap_types.add(gap_type)
    assert "translation_gap" in gap_types


@pytest.mark.asyncio
async def test_verify_feedback_text_uses_runtime_literal_scan_for_plugin_source(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """反馈反查源码残留必须走 Rust runtime literal scan，不能回退旧 regex 候选扫描。"""
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "Window_Base.prototype.drawText('プラグイン直書き', 0, 0, 320);",
        encoding="utf-8",
    )
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "HardcodedText", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)
    feedback_path = tmp_path / "feedback-texts.json"
    _ = feedback_path.write_text(json.dumps(["プラグイン直書き"], ensure_ascii=False), encoding="utf-8")

    async def forbidden_legacy_plugin_source_scan(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("feedback plugin source lookup must use Rust runtime literal scan")

    monkeypatch.setattr(
        "app.agent_toolkit.services.common._collect_plugin_source_text_candidates",
        forbidden_legacy_plugin_source_scan,
        raising=False,
    )

    report = await service.verify_feedback_text(game_title="テストゲーム", input_path=feedback_path)

    assert report.status == "error"
    assert report.summary["text_index_status"] == "used"
    assert report.summary["plugin_source_hardcoded_count"] == 1
    occurrences = ensure_json_array(report.details["occurrences"], "occurrences")
    assert any(
        ensure_json_object(coerce_json_value(occurrence), "occurrence").get("gap_type") == "plugin_source_hardcoded"
        for occurrence in occurrences
    )
@pytest.mark.asyncio
async def test_feedback_verification_reads_active_files_not_origin_backups(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """反馈反查必须检查当前激活文件，不能把原始备份误报成激活文件残留。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    source_items = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    source_item = ensure_json_object(ensure_json_array(source_items, "source Items.json")[1], "source Items.json[1]")
    source_item["description"] = "With this rope..."
    _ = items_path.write_text(json.dumps(source_items, ensure_ascii=False, indent=2), encoding="utf-8")

    active_plugins = [
        {
            "name": "OriginOnlyPlugin",
            "status": True,
            "description": "已修复",
            "parameters": {"message": "是否读取此存档文件？"},
        }
    ]
    origin_plugins = [
        {
            "name": "OriginOnlyPlugin",
            "status": True,
            "description": "original",
            "parameters": {"message": "Whether to load this save file?"},
        }
    ]
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    _ = plugins_path.write_text(f"var $plugins = {json.dumps(origin_plugins, ensure_ascii=False, indent=2)};\n", encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="en")
    active_items = coerce_json_value(cast(object, json.loads(items_path.read_text(encoding="utf-8"))))
    active_item = ensure_json_object(ensure_json_array(active_items, "active Items.json")[1], "active Items.json[1]")
    active_item["description"] = "有了这根绳子，说不定能到达世界的中心。"
    _ = items_path.write_text(json.dumps(active_items, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = plugins_path.write_text(f"var $plugins = {json.dumps(active_plugins, ensure_ascii=False, indent=2)};\n", encoding="utf-8")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    feedback_path = tmp_path / "feedback-texts.json"
    _ = feedback_path.write_text(
        json.dumps(["With this rope...", "Whether to load this save file?"], ensure_ascii=False),
        encoding="utf-8",
    )

    report = await service.verify_feedback_text(game_title="テストゲーム", input_path=feedback_path)

    assert report.status == "ok"
    assert report.summary["occurrence_count"] == 0
    assert report.details["occurrences"] == []
@pytest.mark.asyncio
async def test_default_active_runtime_audit_skips_plugin_source_text_branch(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """未启动插件源码支线时，当前运行审计只做运行完整性检查。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    bad_source_path = plugin_source_dir / "BadSource.js"
    _ = bad_source_path.write_text(
        "const Messages = { param2: ['頑張ってガマンする\\\\nn[0]くん…素敵よ♥'] };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = bad_source_path.write_text(
        "const Messages = { param2: ['努力忍耐着的\\nn[0]君…真棒哦♥'] };\n",
        encoding="utf-8",
    )
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        game_data = await load_game_data(session.game_path)
        text_rules = TextRules.from_setting(setting.text_rules)
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
                original_lines=list(item.original_lines),
                source_line_paths=list(item.source_line_paths),
                translation_lines=[
                    _translated_test_line_preserving_controls(line, text_rules)
                    for line in item.original_lines
                ],
            )
            for item in scope.active_items()
            if item.location_path in scope.writable_paths
        ]
        await session.write_translation_items(translated_items)

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    quality_report = await service.quality_report(game_title="テストゲーム")
    runtime_report = await service.audit_active_runtime(game_title="テストゲーム")

    assert runtime_report.status == "ok"
    assert "active_runtime_placeholder_risk" not in {error.code for error in quality_report.errors}
    assert "active_runtime_placeholder_risk" not in {error.code for error in runtime_report.errors}
    assert "active_runtime_placeholder_risk_count" not in quality_report.summary
    assert runtime_report.summary["active_runtime_text_issue_audit_enabled"] is False
    assert runtime_report.summary["active_runtime_placeholder_risk_count"] == 0
@pytest.mark.asyncio
async def test_active_runtime_audit_rejects_plugin_source_read_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行插件源码读取失败时必须报错，不能只写进摘要计数。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BrokenEncoding", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "BrokenEncoding.js").write_bytes(b"\xff\xfe\xff")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    runtime_report = await service.audit_active_runtime(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert runtime_report.status == "error"
    assert quality_report.status == "error"
    assert "active_runtime_read_error" in {error.code for error in runtime_report.errors}
    assert "active_runtime_read_error" not in {error.code for error in quality_report.errors}
    runtime_read_error_count = runtime_report.summary["active_runtime_read_error_count"]
    assert isinstance(runtime_read_error_count, int)
    assert runtime_read_error_count >= 1
    assert "BrokenEncoding.js" in json.dumps(runtime_report.details, ensure_ascii=False)
@pytest.mark.asyncio
async def test_active_runtime_audit_rejects_missing_enabled_plugin_source_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行插件配置启用了源码文件但文件不存在时必须报错。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "MissingSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    runtime_report = await service.audit_active_runtime(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert runtime_report.status == "error"
    assert quality_report.status == "error"
    assert "active_runtime_read_error" in {error.code for error in runtime_report.errors}
    assert "active_runtime_read_error" not in {error.code for error in quality_report.errors}
    runtime_read_error_count = runtime_report.summary["active_runtime_read_error_count"]
    assert isinstance(runtime_read_error_count, int)
    assert runtime_read_error_count >= 1
    assert "active_runtime_read_error_count" not in quality_report.summary
    assert "MissingSource.js" in json.dumps(runtime_report.details, ensure_ascii=False)
@pytest.mark.asyncio
async def test_active_runtime_audit_rejects_missing_plugin_source_directory(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行插件源码目录缺失时，启用插件必须按缺失源码报错。"""
    shutil.rmtree(minimal_game_dir / "js" / "plugins")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    runtime_report = await service.audit_active_runtime(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert runtime_report.status == "error"
    assert quality_report.status == "error"
    assert "active_runtime_read_error" in {error.code for error in runtime_report.errors}
    assert "active_runtime_read_error" not in {error.code for error in quality_report.errors}
    assert "TestPlugin.js" in json.dumps(runtime_report.details, ensure_ascii=False)
    assert "ComplexPlugin.js" in json.dumps(runtime_report.details, ensure_ascii=False)
@pytest.mark.asyncio
async def test_active_runtime_audit_warns_for_original_plugin_source_syntax_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行插件源码原本坏掉时只告警，不能越界阻断主汉化流程。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BrokenSyntax", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    broken_source_path = plugin_source_dir / "BrokenSyntax.js"
    _ = broken_source_path.write_text(
        "const Messages = { title: '原文' };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = broken_source_path.write_text(
        "const Messages = { title: '坏掉 };\n",
        encoding="utf-8",
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    runtime_report = await service.audit_active_runtime(game_title="テストゲーム")
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert runtime_report.status == "warning"
    assert quality_report.status == "error"
    assert "active_runtime_syntax_error" not in {error.code for error in runtime_report.errors}
    assert "active_runtime_syntax_warning" in {warning.code for warning in runtime_report.warnings}
    assert "active_runtime_syntax_error" not in {error.code for error in quality_report.errors}
    assert runtime_report.summary["active_runtime_syntax_error_count"] == 1
    assert runtime_report.summary["active_runtime_blocking_issue_count"] == 0
    assert "active_runtime_syntax_error_count" not in quality_report.summary
    assert "BrokenSyntax.js" in json.dumps(runtime_report.details, ensure_ascii=False)
@pytest.mark.asyncio
async def test_diagnose_active_runtime_maps_plugin_source_issue_to_translation_cache(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行源码诊断必须用写回映射精确反推已保存译文记录。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    active_source = "const Messages = { line: '努力忍耐着的\\nn[0]君…真棒哦♥' };\n"
    origin_source = "const Messages = { line: '頑張ってガマンする\\\\nn[0]くん…素敵よ♥' };\n"
    bad_source_path = plugin_source_dir / "BadSource.js"
    _ = bad_source_path.write_text(origin_source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = bad_source_path.write_text(active_source, encoding="utf-8")
    origin_source_dir = minimal_game_dir / "js" / "plugins_source_origin"
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        active_game_data = await load_active_runtime_game_data(
            session.game_path,
            include_plugin_source_files=True,
        )
        runtime_source = active_game_data.plugin_source_files["BadSource.js"]
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        source_file_scan = next(file_scan for file_scan in source_scan.files if file_scan.file_name == "BadSource.js")
        source_candidate = next(candidate for candidate in source_scan.candidates if candidate.file_name == "BadSource.js")
        runtime_literal = iter_plugin_source_string_literals(
            file_name="BadSource.js",
            source=runtime_source,
            active=True,
        )[0]
        location_path = f"js/plugins/BadSource.js/{source_candidate.selector}"
        translation_item = TranslationItem(
            location_path=location_path,
            item_type="short_text",
            original_lines=[source_candidate.text],
            source_line_paths=[location_path],
            translation_lines=["努力忍耐着的\nn[0]君…真棒哦♥"],
        )
        await session.write_translation_items([translation_item])
        await session.replace_plugin_source_runtime_write_maps(
            [
                PluginSourceRuntimeWriteMapRecord(
                    location_path=location_path,
                    source_file_name="BadSource.js",
                    source_selector=source_candidate.selector,
                    source_file_hash=source_file_scan.file_hash,
                    source_text_hash=plugin_source_runtime_hash_text(source_candidate.text),
                    translation_lines_hash=plugin_source_runtime_hash_lines(translation_item.translation_lines),
                    runtime_file_name="BadSource.js",
                    runtime_selector=runtime_literal.selector,
                    runtime_file_hash=build_plugin_source_file_hash(runtime_source),
                    runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                    runtime_line=runtime_literal.line,
                    created_at="2026-05-24T00:00:00",
                )
            ]
        )

    output_path = tmp_path / "diagnosis.json"
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.diagnose_active_runtime(game_title="テストゲーム", output_path=output_path)

    assert report.status == "error"
    assert output_path.exists()
    assert report.summary["mapped_translate_count"] == 1
    diagnosis_items = ensure_json_array(report.details["active_runtime_diagnosis_items"], "diagnosis")
    diagnosis_item = next(
        item
        for item in diagnosis_items
        if ensure_json_object(
            ensure_json_object(item, "diagnosis_item")["issue"],
            "diagnosis_item.issue",
        )["file"] == "BadSource.js"
    )
    diagnosis = ensure_json_object(diagnosis_item, "diagnosis_item")
    assert diagnosis["diagnosis_status"] == "mapped_translate"
    assert diagnosis["location_path"] == location_path
    assert diagnosis["current_translation_lines"] == ["努力忍耐着的\nn[0]君…真棒哦♥"]
    assert "无法反推" not in json.dumps(diagnosis, ensure_ascii=False)

    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=location_path,
                    item_type="short_text",
                    original_lines=[source_candidate.text],
                    source_line_paths=[location_path],
                    translation_lines=["已经修复的译文记录"],
                )
            ]
        )
    cache_changed_report = await service.diagnose_active_runtime(
        game_title="テストゲーム",
        output_path=tmp_path / "diagnosis-cache-changed.json",
    )
    cache_changed_items = ensure_json_array(
        cache_changed_report.details["active_runtime_diagnosis_items"],
        "diagnosis",
    )
    cache_changed_item = next(
        ensure_json_object(item, "diagnosis_item")
        for item in cache_changed_items
        if ensure_json_object(
            ensure_json_object(item, "diagnosis_item")["issue"],
            "diagnosis_item.issue",
        )["file"] == "BadSource.js"
    )
    assert cache_changed_item["diagnosis_status"] == "mapped_translate"
    assert cache_changed_item["cache_hash_matches"] is False
    assert cache_changed_item["current_translation_lines"] == ["已经修复的译文记录"]

    _ = (origin_source_dir / "BadSource.js").write_text(
        "const Messages = { line: '源文件已变化' };\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="可信源快照 manifest"):
        _ = await service.diagnose_active_runtime(
            game_title="テストゲーム",
            output_path=tmp_path / "diagnosis-source-changed.json",
        )
@pytest.mark.asyncio
async def test_diagnose_active_runtime_batches_translation_source_scans(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行诊断反推翻译源时必须批量扫描源插件文件。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugin_names = ["BadSourceA", "BadSourceB"]
    for plugin_name in plugin_names:
        plugins.append({"name": plugin_name, "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    origin_sources = {
        "BadSourceA.js": "const Messages = { category: '原文A' };\n",
        "BadSourceB.js": "const Messages = { category: '原文B' };\n",
    }
    active_sources = {
        "BadSourceA.js": "const Messages = { category: 'カテゴリA' };\n",
        "BadSourceB.js": "const Messages = { category: 'カテゴリB' };\n",
    }
    for file_name, source in origin_sources.items():
        _ = (plugin_source_dir / file_name).write_text(source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    for file_name, source in active_sources.items():
        _ = (plugin_source_dir / file_name).write_text(source, encoding="utf-8")

    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        active_game_data = await load_active_runtime_game_data(
            session.game_path,
            include_plugin_source_files=True,
        )
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        translation_items: list[TranslationItem] = []
        runtime_maps: list[PluginSourceRuntimeWriteMapRecord] = []
        for index, file_name in enumerate(sorted(origin_sources)):
            source_file_scan = next(file_scan for file_scan in source_scan.files if file_scan.file_name == file_name)
            source_candidate = next(candidate for candidate in source_scan.candidates if candidate.file_name == file_name)
            runtime_source = active_game_data.plugin_source_files[file_name]
            runtime_literal = iter_plugin_source_string_literals(
                file_name=file_name,
                source=runtime_source,
                active=True,
            )[0]
            location_path = f"js/plugins/{file_name}/{source_candidate.selector}"
            translation_item = TranslationItem(
                location_path=location_path,
                item_type="short_text",
                original_lines=[source_candidate.text],
                source_line_paths=[location_path],
                translation_lines=[runtime_literal.text],
            )
            translation_items.append(translation_item)
            runtime_maps.append(
                PluginSourceRuntimeWriteMapRecord(
                    location_path=location_path,
                    source_file_name=file_name,
                    source_selector=source_candidate.selector,
                    source_file_hash=f"stale-{source_file_scan.file_hash}",
                    source_text_hash=plugin_source_runtime_hash_text(source_candidate.text),
                    translation_lines_hash=plugin_source_runtime_hash_lines(translation_item.translation_lines),
                    runtime_file_name=file_name,
                    runtime_selector=runtime_literal.selector,
                    runtime_file_hash=build_plugin_source_file_hash(runtime_source),
                    runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                    runtime_line=runtime_literal.line,
                    created_at=f"2026-05-24T00:00:0{index}",
                )
            )
        await session.write_translation_items(translation_items)
        await session.replace_plugin_source_runtime_write_maps(runtime_maps)

    batch_calls: list[tuple[str, ...]] = []

    def counting_source_batch_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
    ) -> PluginSourceBatchTextScan:
        """记录诊断反推阶段扫描过的翻译源插件字面量文件。"""
        batch_calls.append(tuple(sorted(files)))
        return real_scan_plugin_source_runtime_files_text_strict(
            files=files,
            active_file_names=active_file_names,
        )

    def forbidden_legacy_strict_scan(*args: object, **kwargs: object) -> PluginSourceBatchTextScan:
        _ = (args, kwargs)
        raise AssertionError("diagnose-active-runtime 不应调用翻译源 strict scan")

    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.scan_plugin_source_files_text_strict",
        forbidden_legacy_strict_scan,
        raising=False,
    )
    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.scan_plugin_source_runtime_files_text_strict",
        counting_source_batch_scan,
        raising=False,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.diagnose_active_runtime(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["mapped_translate_count"] == 2
    assert batch_calls == [("BadSourceA.js", "BadSourceB.js")]
    diagnosis_items = ensure_json_array(report.details["active_runtime_diagnosis_items"], "diagnosis_items")
    mapped_items = [
        ensure_json_object(item, "diagnosis_item")
        for item in diagnosis_items
        if ensure_json_object(item, "diagnosis_item").get("diagnosis_status") == "mapped_translate"
    ]
    assert len(mapped_items) == 2
    assert all(item["source_hash_matches"] is True for item in mapped_items)
    assert all(item["source_file_hash_matches"] is False for item in mapped_items)


@pytest.mark.asyncio
async def test_diagnose_active_runtime_skips_translation_source_scan_when_source_hash_matches(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回映射源文件 hash 未变化时，诊断不能再扫描翻译源插件源码 AST。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    origin_source = "const Messages = { line: '頑張ってガマンする\\\\nn[0]くん…素敵よ♥' };\n"
    active_source = "const Messages = { line: '努力忍耐着的\\nn[0]君…真棒哦♥' };\n"
    bad_source_path = plugin_source_dir / "BadSource.js"
    _ = bad_source_path.write_text(origin_source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = bad_source_path.write_text(active_source, encoding="utf-8")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        active_game_data = await load_active_runtime_game_data(
            session.game_path,
            include_plugin_source_files=True,
        )
        runtime_source = active_game_data.plugin_source_files["BadSource.js"]
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        source_file_scan = next(file_scan for file_scan in source_scan.files if file_scan.file_name == "BadSource.js")
        source_candidate = next(candidate for candidate in source_scan.candidates if candidate.file_name == "BadSource.js")
        runtime_literal = iter_plugin_source_string_literals(
            file_name="BadSource.js",
            source=runtime_source,
            active=True,
        )[0]
        location_path = f"js/plugins/BadSource.js/{source_candidate.selector}"
        translation_item = TranslationItem(
            location_path=location_path,
            item_type="short_text",
            original_lines=[source_candidate.text],
            source_line_paths=[location_path],
            translation_lines=[runtime_literal.text],
        )
        await session.write_translation_items([translation_item])
        await session.replace_plugin_source_runtime_write_maps(
            [
                PluginSourceRuntimeWriteMapRecord(
                    location_path=location_path,
                    source_file_name="BadSource.js",
                    source_selector=source_candidate.selector,
                    source_file_hash=source_file_scan.file_hash,
                    source_text_hash=plugin_source_runtime_hash_text(source_candidate.text),
                    translation_lines_hash=plugin_source_runtime_hash_lines(translation_item.translation_lines),
                    runtime_file_name="BadSource.js",
                    runtime_selector=runtime_literal.selector,
                    runtime_file_hash=build_plugin_source_file_hash(runtime_source),
                    runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                    runtime_line=runtime_literal.line,
                    created_at="2026-05-24T00:00:00",
                )
            ]
        )

    def counting_runtime_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
    ) -> PluginSourceBatchTextScan:
        """允许 active runtime 扫描，禁止 hash 未变时的翻译源扫描。"""
        if any("頑張ってガマンする" in source for source in files.values()):
            raise AssertionError("diagnose-active-runtime must not rescan unchanged translation source files")
        return real_scan_plugin_source_runtime_files_text_strict(
            files=files,
            active_file_names=active_file_names,
        )

    monkeypatch.setattr(
        "app.agent_toolkit.services.quality.scan_plugin_source_runtime_files_text_strict",
        counting_runtime_scan,
        raising=False,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.diagnose_active_runtime(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["mapped_translate_count"] == 1
    diagnosis_items = ensure_json_array(report.details["active_runtime_diagnosis_items"], "diagnosis")
    mapped_item = next(
        ensure_json_object(item, "diagnosis_item")
        for item in diagnosis_items
        if ensure_json_object(item, "diagnosis_item").get("diagnosis_status") == "mapped_translate"
    )
    assert mapped_item["source_hash_matches"] is True
    assert mapped_item["source_file_hash_matches"] is True
@pytest.mark.asyncio
async def test_diagnose_active_runtime_default_mode_never_guesses_without_runtime_map(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """默认模式没有写回映射时，不把源码字符串猜成漏翻诊断。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    active_source = "const Messages = { line: '努力忍耐着的\\nn[0]君…真棒哦♥' };\n"
    bad_source_path = plugin_source_dir / "BadSource.js"
    _ = bad_source_path.write_text(
        "const Messages = { line: '頑張ってガマンする\\\\nn[0]くん…素敵よ♥' };\n",
        encoding="utf-8",
    )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = bad_source_path.write_text(active_source, encoding="utf-8")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        source_candidate = next(candidate for candidate in source_scan.candidates if candidate.file_name == "BadSource.js")
        location_path = f"js/plugins/BadSource.js/{source_candidate.selector}"
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path=location_path,
                    item_type="short_text",
                    original_lines=[source_candidate.text],
                    source_line_paths=[location_path],
                    translation_lines=["努力忍耐着的\nn[0]君…真棒哦♥"],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.diagnose_active_runtime(game_title="テストゲーム", output_path=tmp_path / "diagnosis.json")

    assert report.status == "ok"
    assert report.summary["active_runtime_text_issue_audit_enabled"] is False
    assert report.summary["runtime_mapping_missing_count"] == 0
    diagnosis_items = ensure_json_array(report.details["active_runtime_diagnosis_items"], "diagnosis")
    assert diagnosis_items == []
@pytest.mark.asyncio
async def test_diagnose_active_runtime_default_mode_skips_unmapped_source_residual(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """未启动插件源码支线时，当前运行源码残留不是补译诊断。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    active_source = "const Messages = { line: '未審査テキスト' };\n"
    _ = (plugin_source_dir / "BadSource.js").write_text(active_source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.diagnose_active_runtime(game_title="テストゲーム")

    assert report.status == "ok"
    assert report.summary["active_runtime_text_issue_audit_enabled"] is False
    assert report.summary["runtime_mapping_missing_count"] == 0
    diagnosis_items = ensure_json_array(report.details["active_runtime_diagnosis_items"], "diagnosis")
    assert diagnosis_items == []
@pytest.mark.asyncio
async def test_diagnose_active_runtime_does_not_ignore_excluded_runtime_residual_without_map(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码规则排除 selector 不会让当前运行源文残留从诊断里消失。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    active_source = "const Messages = { category: 'カテゴリ' };\n"
    _ = (plugin_source_dir / "BadSource.js").write_text(active_source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        source_file_scan = next(file_scan for file_scan in source_scan.files if file_scan.file_name == "BadSource.js")
        source_candidate = next(candidate for candidate in source_scan.candidates if candidate.file_name == "BadSource.js")
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="BadSource.js",
                    file_hash=source_file_scan.file_hash,
                    selectors=[],
                    excluded_selectors=[source_candidate.selector],
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.diagnose_active_runtime(game_title="テストゲーム")

    assert report.status == "error"
    assert report.summary["active_runtime_source_residual_count"] == 1
    assert report.summary["runtime_mapping_missing_count"] == 1
    diagnosis_items = ensure_json_array(report.details["active_runtime_diagnosis_items"], "diagnosis")
    assert len(diagnosis_items) == 1
@pytest.mark.asyncio
async def test_active_runtime_audit_ignores_excluded_residual_with_exact_runtime_map(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """已审查排除 selector 有精确 runtime map 时，不再当作插件源码漏翻。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    active_source = "const Messages = { category: 'カテゴリ' };\n"
    _ = (plugin_source_dir / "BadSource.js").write_text(active_source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        active_game_data = await load_active_runtime_game_data(
            session.game_path,
            include_plugin_source_files=True,
        )
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        source_file_scan = next(file_scan for file_scan in source_scan.files if file_scan.file_name == "BadSource.js")
        source_candidate = next(candidate for candidate in source_scan.candidates if candidate.file_name == "BadSource.js")
        runtime_source = active_game_data.plugin_source_files["BadSource.js"]
        runtime_literal = iter_plugin_source_string_literals(
            file_name="BadSource.js",
            source=runtime_source,
            active=True,
        )[0]
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="BadSource.js",
                    file_hash=source_file_scan.file_hash,
                    selectors=[],
                    excluded_selectors=[source_candidate.selector],
                )
            ]
        )
        await session.replace_plugin_source_runtime_write_maps(
            [
                PluginSourceRuntimeWriteMapRecord(
                    mapping_kind="excluded",
                    location_path=f"js/plugins/BadSource.js/{source_candidate.selector}",
                    source_file_name="BadSource.js",
                    source_selector=source_candidate.selector,
                    source_file_hash=source_file_scan.file_hash,
                    source_text_hash=plugin_source_runtime_hash_text(source_candidate.text),
                    translation_lines_hash=plugin_source_runtime_hash_lines([]),
                    runtime_file_name="BadSource.js",
                    runtime_selector=runtime_literal.selector,
                    runtime_file_hash=build_plugin_source_file_hash(runtime_source),
                    runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                    runtime_line=runtime_literal.line,
                    created_at="2026-05-24T00:00:00",
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.audit_active_runtime(game_title="テストゲーム")
    diagnosis = await service.diagnose_active_runtime(game_title="テストゲーム")

    assert report.status == "ok"
    assert report.summary["active_runtime_text_issue_audit_enabled"] is True
    assert report.summary["active_runtime_source_residual_count"] == 0
    assert diagnosis.status == "ok"
    assert diagnosis.summary["diagnosis_issue_count"] == 0
@pytest.mark.asyncio
async def test_active_runtime_audit_reports_unmapped_residual_when_other_runtime_map_exists(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """存在其他精确 runtime map 时，未映射当前运行残留仍要进入诊断。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "BadSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    active_source = "const Messages = { category: 'カテゴリ', leak: '未審査テキスト' };\n"
    _ = (plugin_source_dir / "BadSource.js").write_text(active_source, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        source_game_data = await load_game_data(session.game_path)
        active_game_data = await load_active_runtime_game_data(
            session.game_path,
            include_plugin_source_files=True,
        )
        source_scan = build_native_plugin_source_scan(game_data=source_game_data, text_rules=text_rules)
        source_file_scan = next(file_scan for file_scan in source_scan.files if file_scan.file_name == "BadSource.js")
        source_candidate = next(
            candidate
            for candidate in source_scan.candidates
            if candidate.file_name == "BadSource.js" and candidate.text == "カテゴリ"
        )
        runtime_source = active_game_data.plugin_source_files["BadSource.js"]
        runtime_literal = next(
            literal
            for literal in iter_plugin_source_string_literals(
                file_name="BadSource.js",
                source=runtime_source,
                active=True,
            )
            if literal.text == "カテゴリ"
        )
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="BadSource.js",
                    file_hash=source_file_scan.file_hash,
                    selectors=[],
                    excluded_selectors=[source_candidate.selector],
                )
            ]
        )
        await session.replace_plugin_source_runtime_write_maps(
            [
                PluginSourceRuntimeWriteMapRecord(
                    mapping_kind="excluded",
                    location_path=f"js/plugins/BadSource.js/{source_candidate.selector}",
                    source_file_name="BadSource.js",
                    source_selector=source_candidate.selector,
                    source_file_hash=source_file_scan.file_hash,
                    source_text_hash=plugin_source_runtime_hash_text(source_candidate.text),
                    translation_lines_hash=plugin_source_runtime_hash_lines([]),
                    runtime_file_name="BadSource.js",
                    runtime_selector=runtime_literal.selector,
                    runtime_file_hash=build_plugin_source_file_hash(runtime_source),
                    runtime_text_hash=plugin_source_runtime_hash_text(runtime_literal.text),
                    runtime_line=runtime_literal.line,
                    created_at="2026-05-24T00:00:00",
                )
            ]
        )

    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    report = await service.audit_active_runtime(game_title="テストゲーム")
    diagnosis = await service.diagnose_active_runtime(game_title="テストゲーム")
    diagnosis_items = ensure_json_array(diagnosis.details["active_runtime_diagnosis_items"], "diagnosis")

    assert report.status == "error"
    assert report.summary["active_runtime_source_residual_count"] == 1
    assert diagnosis.status == "error"
    assert diagnosis.summary["runtime_mapping_missing_count"] == 1
    assert len(diagnosis_items) == 1
    diagnosis_item = ensure_json_object(diagnosis_items[0], "diagnosis item")
    assert diagnosis_item["diagnosis_status"] == "runtime_mapping_missing"
