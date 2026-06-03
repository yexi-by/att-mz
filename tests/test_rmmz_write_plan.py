"""RPG Maker 写回计划和 native 写回助手业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *

@pytest.mark.asyncio
async def test_direct_write_back_delegates_native_quality_to_rust_plan(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写回不再在 Python 侧重复执行 native 质量检查，由 Rust 计划统一拦截。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    _ = (app_home / "setting.toml").write_text(
        _example_setting_text_with_absolute_prompt_files(),
        encoding="utf-8",
    )
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        game_data, _setting, text_rules = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        translated_items: list[TranslationItem] = []
        for item in scope.active_items():
            translation_lines = [
                _translated_test_line_preserving_controls(line, text_rules)
                for line in item.original_lines
            ]
            if item.location_path == "CommonEvents.json/2/0":
                translation_lines = ["测试"]
            translated_items.append(
                TranslationItem(
                    location_path=item.location_path,
                    item_type=item.item_type,
                    role=item.role,
                    original_lines=[line for line in item.original_lines],
                    source_line_paths=[path for path in item.source_line_paths],
                    translation_lines=translation_lines,
                )
            )
        await session.write_translation_items(translated_items)

    def forbidden_python_native_check(*args: object, **kwargs: object) -> NoReturn:
        """Python 写回前置不应再重复执行 Rust 已覆盖的 native 质量检查。"""
        _ = (args, kwargs)
        raise AssertionError("Python 写回前置不应重复执行 native 质量或协议检查")

    rust_plan_called = False

    def fake_rust_plan(*args: object, **kwargs: object) -> object:
        """模拟 Rust 写回计划统一返回质量 gate 失败。"""
        nonlocal rust_plan_called
        rust_plan_called = True
        _ = (args, kwargs)
        raise RuntimeError("写进游戏文件前检查没通过：发现 1 条译文里的游戏控制符可能被改坏")

    monkeypatch.setattr("app.application.write_back_gate.collect_native_quality_counts", forbidden_python_native_check)
    monkeypatch.setattr("app.application.write_back_gate.count_native_write_protocol_issues", forbidden_python_native_check)
    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_rust_plan)
    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="游戏控制符可能被改坏"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()

    assert rust_plan_called is True
@pytest.mark.asyncio
async def test_native_write_back_helper_applies_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通写回快路径必须应用 Rust 计划并执行事务替换。"""
    session = _NativePlanSessionStub(tmp_path)
    written_files: list[tuple[Path, str]] = []
    statuses: list[str] = []

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """返回最小 Rust 写回计划，并记录调用模式。"""
        assert kwargs["mode"] == "write_back"
        content_output_dir = kwargs["content_output_dir"]
        assert isinstance(content_output_dir, Path)
        assert content_output_dir.is_dir()
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
            timings_ms={"total": 1, "active_runtime_audit": 12345},
        )

    def fake_apply_files(self: WritePlanApplier, plan: RuntimeWritePlan) -> None:
        """记录事务写入计划。"""
        _ = self
        for operation in plan.file_operations:
            assert operation.content is not None
            assert operation.source_path is None
            written_files.append((operation.target_path, operation.content))

    async def fake_load_active_runtime_game_data(game_path: Path, **kwargs: object) -> GameData:
        """无插件源码映射和非标准 data 规则时不应加载当前运行视图。"""
        _ = (game_path, kwargs)
        raise AssertionError("无写后审计目标时不应加载当前运行视图")

    def fake_audit_active_runtime_plugin_source_with_scan_cache(
        *args: object,
        **kwargs: object,
    ) -> NoReturn:
        """无插件源码映射时不应执行插件源码审计。"""
        _ = (args, kwargs)
        raise AssertionError("无插件源码映射时不应执行插件源码审计")

    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)
    monkeypatch.setattr("app.application.handler.WritePlanApplier.apply_files", fake_apply_files)
    monkeypatch.setattr("app.application.handler.load_active_runtime_game_data", fake_load_active_runtime_game_data)
    monkeypatch.setattr(
        "app.application.handler.audit_active_runtime_plugin_source_with_scan_cache",
        fake_audit_active_runtime_plugin_source_with_scan_cache,
    )

    handler = TranslationHandler(GameRegistry(tmp_path / "db"), LLMHandler())
    try:
        summary = await handler.write_runtime_files_with_native_plan(
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

    assert summary.data_item_count == 1
    assert written_files == [(session.content_root / "data" / "System.json", "{\"gameTitle\":\"测试\"}\n")]
    assert summary.post_write_audit_ms < 12345
    assert statuses == [
        "准备 Rust 写回计划输入",
        "生成 Rust 写回计划",
        "替换游戏运行文件",
        "跳过写入后的当前运行文件审计",
        "保存写入诊断映射",
    ]
    assert session.runtime_map_replace_calls == 1
    assert session.runtime_map_replace_count == 0
@pytest.mark.asyncio
async def test_direct_write_back_rejects_latest_quality_errors(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接调用业务写回也必须拦截模型翻了但项目检查没通过的译文。"""

    async def forbidden_full_quality_error_read(*args: object, **kwargs: object) -> NoReturn:
        """写回前检查不应读取最新运行的全部质量错误明细。"""
        _ = (args, kwargs)
        raise AssertionError("写回前检查不应读取全部质量错误")

    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
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
    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors",
        forbidden_full_quality_error_read,
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
async def test_direct_write_back_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接写入游戏文件不能在外部规则未完成时静默成功。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="检查没通过"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_direct_rebuild_active_runtime_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重建当前运行文件也是写文件操作，必须受同一前置规则约束。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="检查没通过"):
            _ = await handler.rebuild_active_runtime(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_direct_rebuild_active_runtime_uses_real_native_success_path(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重建当前运行文件成功路径必须穿过真实 handler 和 Rust 写回计划。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
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
                for item in scope.active_items()
            ]
        )

    _rewrite_json(
        minimal_game_dir / "data" / "System.json",
        {
            "gameTitle": "损坏的当前运行文件",
            "terms": {},
        },
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.rebuild_active_runtime(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    rebuilt_system = ensure_json_object(
        _read_test_json(minimal_game_dir / "data" / "System.json"),
        "System.json",
    )
    assert rebuilt_system["gameTitle"] == "测试"
    assert summary.data_item_count > 0
    assert summary.planned_file_count > 0
    assert summary.rust_plan_ms >= 0
    assert summary.file_replacement_ms >= 0
    assert summary.post_write_audit_ms >= 0
@pytest.mark.asyncio
async def test_write_terminology_allows_pending_body_translation_run(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """术语写回只要求术语和写入协议可用，不因正文译文未完成而失败。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await _prepare_write_gate_session(
            session=session,
            game_dir=minimal_game_dir,
            registry=TerminologyRegistry(speaker_names={"アリス": "爱丽丝"}),
            glossary=TerminologyGlossary(terms={"アリス": "爱丽丝"}),
        )
        _ = await session.start_translation_run(
            total_extracted=100,
            pending_count=100,
            deduplicated_count=100,
            batch_count=1,
        )

    async def forbidden_quality_error_path_read(*args: object, **kwargs: object) -> NoReturn:
        """术语写回不要求正文译文完整，不应读取待翻译正文路径上的质量错误。"""
        _ = (args, kwargs)
        raise AssertionError("术语写回不应读取待翻译正文路径上的质量错误")

    monkeypatch.setattr(
        "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors_by_paths",
        forbidden_quality_error_path_read,
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_terminology(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    common_events = ensure_json_array(_read_test_json(minimal_game_dir / "data" / "CommonEvents.json"), "CommonEvents")
    first_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(first_event["list"], "CommonEvents[1].list")
    name_parameters = ensure_json_array(
        ensure_json_object(commands[0], "CommonEvents[1].list[0]")["parameters"],
        "CommonEvents[1].list[0].parameters",
    )
    assert summary.written_count > 0
    assert name_parameters[4] == "爱丽丝"
@pytest.mark.asyncio
async def test_direct_write_back_ignores_excluded_plugin_source_text_issues_during_plan_audit(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust 计划检查不把已排除的插件源码内部字符串当正文漏翻。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

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
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HardcodedText.js").write_text(
        "const Messages = { category: 'カテゴリ', protocol: '\\\\TRP' };\n",
        encoding="utf-8",
    )
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    original_events = _read_test_json(common_events_path)

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
        candidate = next(
            candidate
            for candidate in build_plugin_source_scan(game_data=game_data, text_rules=text_rules).candidates
            if candidate.file_name == "HardcodedText.js" and candidate.text == "カテゴリ"
        )
        plugin_source_records = build_plugin_source_rule_records_from_import(
            game_data=game_data,
            import_file=parse_plugin_source_rule_import_text(
                json.dumps(
                    [
                        {
                            "file": "HardcodedText.js",
                            "selectors": [],
                            "excluded_selectors": [candidate.selector],
                        }
                    ],
                    ensure_ascii=False,
                )
            ),
            text_rules=text_rules,
        )
        await session.replace_plugin_source_text_rules(plugin_source_records)
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
                for item in scope.active_items()
            ]
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    assert summary.data_item_count > 0
    assert _read_test_json(common_events_path) != original_events
@pytest.mark.asyncio
async def test_direct_write_terminology_rejects_missing_workflow_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接调用术语写回也必须经过写入前流程检查。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
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
async def test_rebuild_active_runtime_uses_native_rebuild_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重建入口必须直接调用 Rust 重建 helper。"""
    captured_calls: list[tuple[str, bool]] = []

    async def fake_rebuild_with_native_plan(
        self: TranslationHandler,
        game_title: str,
        callbacks: tuple[object, object],
        setting_overrides: SettingOverrides | None = None,
        confirm_font_overwrite: bool = False,
    ) -> WriteBackSummary:
        """记录重建入口传入的 native helper 参数。"""
        _ = self
        _ = callbacks
        _ = setting_overrides
        captured_calls.append((game_title, confirm_font_overwrite))
        return WriteBackSummary(
            data_item_count=0,
            plugin_item_count=0,
            terminology_written_count=0,
            target_font_name=None,
            source_font_count=0,
            replaced_font_reference_count=0,
            font_copied=False,
        )

    monkeypatch.setattr(
        TranslationHandler,
        "_rebuild_active_runtime_with_native_plan",
        fake_rebuild_with_native_plan,
    )
    handler = TranslationHandler(GameRegistry(tmp_path / "db"), LLMHandler())
    try:
        _ = await handler.rebuild_active_runtime(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
            confirm_font_overwrite=True,
        )
    finally:
        await handler.close()

    assert captured_calls == [("テストゲーム", True)]
