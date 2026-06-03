"""RPG Maker 写后审计业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *

@pytest.mark.asyncio
async def test_native_write_back_helper_saves_runtime_map_after_post_write_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写入后审计失败时不能提前保存当前运行映射和扫描缓存。"""
    session = _NativePlanSessionStub(tmp_path)
    events: list[str] = []
    runtime_map = PluginSourceRuntimeWriteMapRecord(
        location_path="js/plugins/Broken.js/ast:string:0:1:dummy",
        source_file_name="Broken.js",
        source_selector="ast:string:0:1:dummy",
        source_file_hash="source-hash",
        source_text_hash="source-text-hash",
        translation_lines_hash="translation-hash",
        runtime_file_name="Broken.js",
        runtime_selector="ast:string:0:1:dummy",
        runtime_file_hash="runtime-hash",
        runtime_text_hash="runtime-text-hash",
        runtime_line=1,
        created_at="2026-01-01T00:00:00",
    )

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """返回会触发写入后审计失败的最小计划。"""
        assert kwargs["mode"] == "write_back"
        content_output_dir = kwargs["content_output_dir"]
        assert isinstance(content_output_dir, Path)
        assert content_output_dir.is_dir()
        return NativeWriteBackPlan(
            files=[
                NativePlannedFile(
                    target_path=session.content_root / "js" / "plugins" / "Broken.js",
                    relative_path="js/plugins/Broken.js",
                    content="if (\n",
                )
            ],
            plugin_source_runtime_write_maps=[runtime_map],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=0,
                plugin_item_count=1,
                terminology_written_count=0,
                target_font_name=None,
                source_font_count=0,
                replaced_font_reference_count=0,
                font_copied=False,
                planned_file_count=1,
                skipped_file_count=0,
            ),
            timings_ms={"total": 1, "active_runtime_audit": 999},
        )

    def fake_apply_files(self: WritePlanApplier, plan: RuntimeWritePlan) -> None:
        """记录文件替换已经发生。"""
        _ = self
        for operation in plan.file_operations:
            assert operation.content is not None
            assert operation.source_path is None
        events.append("write")

    async def fake_load_active_runtime_game_data(game_path: Path, **kwargs: object) -> GameData:
        """记录写入后重新加载当前运行视图。"""
        assert game_path == session.game_path
        assert kwargs == {"include_plugin_source_files": True}
        events.append("load")
        return cast(GameData, cast(object, SimpleNamespace()))

    refreshed_cache_record = object()

    def fake_audit_active_runtime_plugin_source_with_scan_cache(
        *,
        game_data: GameData,
        text_rules: TextRules,
        cache_records: list[object],
        created_at: str,
        runtime_write_map_records: list[PluginSourceRuntimeWriteMapRecord],
        audit_text_issues: bool,
        text_issue_scope_keys: frozenset[tuple[str, str]] | None,
    ) -> tuple[ActiveRuntimePluginSourceAudit, list[object]]:
        """模拟当前运行文件审计发现 JS 语法错误。"""
        _ = game_data
        _ = text_rules
        assert cache_records == []
        assert created_at
        assert runtime_write_map_records == [runtime_map]
        assert audit_text_issues is True
        assert text_issue_scope_keys == {("Broken.js", "ast:string:0:1:dummy")}
        events.append("audit")
        return (
            ActiveRuntimePluginSourceAudit(
                issues=(
                    ActiveRuntimePluginSourceIssue(
                        code="active_runtime_syntax_error",
                        message="当前游戏运行文件里的插件源码无法完成 JS 语法检查",
                        file_name="Broken.js",
                        blocking=True,
                        syntax_error="RuntimeError: 原生 AST 解析报告 JS 语法错误",
                    ),
                ),
                text_issue_audit_enabled=True,
                scanned_file_count=1,
                active_file_count=1,
                literal_count=0,
                active_literal_count=0,
                read_error_file_count=0,
            ),
            [refreshed_cache_record],
        )

    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)
    monkeypatch.setattr("app.application.handler.WritePlanApplier.apply_files", fake_apply_files)
    monkeypatch.setattr("app.application.handler.load_active_runtime_game_data", fake_load_active_runtime_game_data)
    monkeypatch.setattr(
        "app.application.handler.audit_active_runtime_plugin_source_with_scan_cache",
        fake_audit_active_runtime_plugin_source_with_scan_cache,
    )

    async def fake_replace_runtime_maps(records: list[object]) -> None:
        """审计通过后才允许保存当前运行映射。"""
        events.append("save_runtime_map")
        session.runtime_map_replace_calls += 1
        session.runtime_map_replace_count = len(records)

    async def fake_replace_scan_cache(records: list[object]) -> None:
        """审计通过后才允许保存当前运行扫描缓存。"""
        events.append("save_scan_cache")
        session.runtime_scan_cache_replace_count = len(records)

    session.replace_plugin_source_runtime_write_maps = fake_replace_runtime_maps
    session.replace_plugin_source_runtime_scan_cache = fake_replace_scan_cache

    handler = TranslationHandler(GameRegistry(tmp_path / "db"), LLMHandler())
    try:
        with pytest.raises(WriteBackGateError, match="写入后当前运行文件审计未通过"):
            _ = await handler.write_runtime_files_with_native_plan(
                session=cast(TargetGameSession, cast(object, session)),
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
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

    assert events == ["write", "load", "audit"]
    assert session.runtime_map_replace_calls == 0
    assert session.runtime_map_replace_count == 0
    assert session.runtime_scan_cache_replace_count == 0
    assert session.runtime_scan_cache_read_calls == 1
@pytest.mark.asyncio
async def test_direct_write_back_rejects_active_runtime_read_error_before_writing_data(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行插件源码读取失败时，Rust 计划阶段直接失败且不写 data。"""
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
    plugins.append({"name": "BrokenEncoding", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    broken_source_path = plugin_source_dir / "BrokenEncoding.js"
    _ = broken_source_path.write_text(
        "const Messages = { title: 'origin only' };\n",
        encoding="utf-8",
    )
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    original_events = _read_test_json(common_events_path)

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = broken_source_path.write_bytes(b"\xff\xfe\xff")
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
                    translation_lines=["但是——"]
                    if item.location_path == "CommonEvents.json/3/0"
                    else [
                        _translated_test_line_preserving_controls(line, text_rules)
                        for line in item.original_lines
                    ],
                )
                for item in scope.active_items()
            ]
        )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="插件源码读取失败"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()

    assert _read_test_json(common_events_path) == original_events
