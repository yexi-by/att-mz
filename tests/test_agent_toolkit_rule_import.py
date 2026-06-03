"""Agent 规则导入、规则审查和规则校验业务契约测试。"""

from __future__ import annotations

from tests.agent_toolkit_contract_fixtures import *

@pytest.mark.asyncio
async def test_agent_translation_source_load_skips_writable_copies_by_default(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 只读翻译源加载默认不读取插件源码，也不构造大型可写副本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = _AgentToolkitServiceProbe(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    async with await registry.open_game("テストゲーム") as session:
        game_data = await service.load_translation_source_for_test(session)
        writable_game_data = await service.load_translation_source_for_test(
            session,
            include_writable_copies=True,
        )
        plugin_source_game_data = await service.load_translation_source_for_test(
            session,
            include_plugin_source_files=True,
        )

    assert game_data.data
    assert game_data.plugin_source_files == {}
    assert game_data.writable_data == {}
    assert game_data.writable_plugins_js == []
    assert game_data.writable_plugin_source_files == {}
    assert writable_game_data.writable_data
    assert writable_game_data.writable_plugins_js
    assert set(plugin_source_game_data.plugin_source_files) == {"ComplexPlugin.js", "TestPlugin.js"}
@pytest.mark.asyncio
async def test_import_empty_plugin_rules_requires_explicit_empty_confirmation(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则为空时默认报错；显式确认后允许保存当前插件范围的空结果。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    rules_path = tmp_path / "plugin-rules.json"
    empty_rules_path = tmp_path / "plugin-rules-empty.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Message']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _ = empty_rules_path.write_text("[]\n", encoding="utf-8")

    _ = await handler.import_plugin_rules(game_title="テストゲーム", input_path=rules_path)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="plugins.js/0/Message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["插件译文"],
                )
            ]
        )

    with pytest.raises(RuntimeError, match="--confirm-empty"):
        _ = await handler.import_plugin_rules(game_title="テストゲーム", input_path=empty_rules_path)
    summary = await handler.import_plugin_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        state = await session.read_rule_review_state(rule_domain=PLUGIN_TEXT_RULE_DOMAIN)

    assert summary.imported_plugin_count == 0
    assert summary.imported_rule_count == 0
    assert summary.deleted_translation_items == 1
    assert summary.deleted_translation_backup_path
    assert translated_items == []
    assert state is not None
    assert state.scope_hash == plugin_rule_scope_hash(await load_game_data(minimal_game_dir))
@pytest.mark.asyncio
@pytest.mark.usefixtures("app_home_with_example_setting")
async def test_import_plugin_rules_rejects_english_protocol_value_paths(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则导入会拒绝英文模式下只命中协议值的路径。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    rules_path = tmp_path / "plugin-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "VisiblePlugin",
                    "paths": ["$['parameters']['Enabled']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        with pytest.raises(ValueError, match="没有命中玩家可见可翻译文本"):
            _ = await handler.import_plugin_rules(
                game_title="English Fixture Game",
                input_path=rules_path,
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_import_plugin_rules_uses_configured_text_rules(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则导入按当前配置判断命中文本，不能退回固定语言档案。"""
    configured_text_rules = TextRulesSetting(
        source_language="en",
        source_residual_label="英文",
        source_text_required_pattern="true",
        source_text_exclusion_profile="none",
        source_residual_segment_pattern="true",
    )

    def fake_load_setting(
        setting_path: str | Path | None = None,
        overrides: SettingOverrides | None = None,
        source_language: SourceLanguage = "ja",
    ) -> Setting:
        """返回带测试文本规则的配置。"""
        target_setting_path = EXAMPLE_SETTING_PATH if setting_path is None else Path(setting_path)
        setting = load_setting(target_setting_path, overrides=overrides, source_language=source_language)
        return setting.model_copy(update={"text_rules": configured_text_rules})

    monkeypatch.setattr("app.application.handler.load_setting", fake_load_setting)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    rules_path = tmp_path / "plugin-rules.json"
    _ = rules_path.write_text(
        json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "VisiblePlugin",
                    "paths": ["$['parameters']['Enabled']"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())

    try:
        summary = await handler.import_plugin_rules(
            game_title="English Fixture Game",
            input_path=rules_path,
        )
    finally:
        await handler.close()

    assert summary.imported_rule_count == 1
@pytest.mark.asyncio
async def test_import_empty_event_command_rules_requires_explicit_empty_confirmation(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则为空时默认报错；显式确认后允许保存当前编码范围的空结果。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    rules_path = tmp_path / "event-command-rules.json"
    empty_rules_path = tmp_path / "event-command-rules-empty.json"
    _ = rules_path.write_text(
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
    _ = empty_rules_path.write_text("{}\n", encoding="utf-8")

    _ = await handler.import_event_command_rules(game_title="テストゲーム", input_path=rules_path)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/4/parameters/3/message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["事件指令译文"],
                )
            ]
        )

    with pytest.raises(RuntimeError, match="--confirm-empty"):
        _ = await handler.import_event_command_rules(
            game_title="テストゲーム",
            input_path=empty_rules_path,
        )
    summary = await handler.import_event_command_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
        command_codes={357},
    )
    async with await registry.open_game("テストゲーム") as session:
        translated_items = await session.read_translated_items()
        state = await session.read_rule_review_state(rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN)

    game_data = await load_game_data(minimal_game_dir)
    assert summary.imported_rule_group_count == 0
    assert summary.imported_path_rule_count == 0
    assert summary.deleted_translation_items == 1
    assert summary.deleted_translation_backup_path
    assert translated_items == []
    assert state is not None
    assert state.scope_hash == event_command_rule_scope_hash_for_command_codes(
        game_data=game_data,
        command_codes=frozenset({357}),
    )
@pytest.mark.asyncio
async def test_import_empty_event_command_rules_records_cli_code_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令空规则确认使用 CLI 显式编码计算范围。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    empty_rules_path = tmp_path / "event-command-rules-empty.json"
    _ = empty_rules_path.write_text("{}\n", encoding="utf-8")
    game_data = await load_game_data(minimal_game_dir)

    _ = await handler.import_event_command_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
        command_codes={999},
    )

    async with await registry.open_game("テストゲーム") as session:
        state = await session.read_rule_review_state(rule_domain=EVENT_COMMAND_TEXT_RULE_DOMAIN)

    assert state is not None
    assert state.scope_hash == event_command_rule_scope_hash_for_command_codes(
        game_data=game_data,
        command_codes=frozenset({999}),
    )
@pytest.mark.asyncio
async def test_import_empty_note_tag_rules_uses_prefix_read_for_stale_cleanup(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签规则导入清理旧译文时，只读取旧规则文件前缀。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv(APP_HOME_ENV_NAME, str(app_home))
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    handler = TranslationHandler(game_registry=registry, llm_handler=LLMHandler())
    empty_rules_path = tmp_path / "note-tag-rules-empty.json"
    _ = empty_rules_path.write_text("{}\n", encoding="utf-8")
    stale_item = TranslationItem(
        location_path="Items.json/1/note/MissingTag",
        item_type="short_text",
        original_lines=["古いタグ"],
        translation_lines=["旧标签"],
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["MissingTag"])]
        )
        await session.write_translation_items([stale_item])

    async def forbidden_full_translation_read(_self: TargetGameSession) -> list[TranslationItem]:
        raise AssertionError("Note 标签规则导入不能全量读取已保存译文")

    monkeypatch.setattr(TargetGameSession, "read_translated_items", forbidden_full_translation_read)

    summary = await handler.import_note_tag_rules(
        game_title="テストゲーム",
        input_path=empty_rules_path,
        confirm_empty=True,
    )

    async with await registry.open_game("テストゲーム") as session:
        translated_paths = await session.read_translation_location_paths()
        state = await session.read_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)

    game_data = await load_game_data(minimal_game_dir)
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    assert summary.imported_file_count == 0
    assert summary.imported_tag_count == 0
    assert summary.deleted_translation_items == 1
    assert stale_item.location_path not in translated_paths
    assert state is not None
    assert state.scope_hash == note_tag_rule_scope_hash_for_text_rules(
        game_data=game_data,
        text_rules=TextRules.from_setting(setting.text_rules),
    )
@pytest.mark.asyncio
async def test_mv_virtual_namebox_rule_commands_validate_import_and_reject_mz(
    minimal_mv_game_dir: Path,
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 虚拟名字框规则只能用于 MV，并通过 CLI 服务校验后保存。"""
    mv_common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    mv_common_events = ensure_json_array(
        coerce_json_value(cast(object, json.loads(mv_common_events_path.read_text(encoding="utf-8")))),
        "CommonEvents.json",
    )
    mv_common_events.append(
        {
            "id": 2,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["本文です"]},
                {"code": 0, "parameters": []},
            ],
        }
    )
    _ = mv_common_events_path.write_text(json.dumps(mv_common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    candidates_path = tmp_path / "mv-namebox-candidates.json"

    export_report = await service.export_mv_virtual_namebox_candidates(
        game_title="MVテストゲーム",
        output_path=candidates_path,
    )
    validate_report = await service.validate_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )
    import_report = await service.import_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )
    mz_report = await service.validate_mv_virtual_namebox_rules(
        game_title="テストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )

    assert export_report.status in {"ok", "warning"}
    assert candidates_path.exists()
    candidate_count = export_report.summary["candidate_count"]
    assert isinstance(candidate_count, int)
    assert candidate_count >= 1
    assert validate_report.status == "ok"
    assert validate_report.summary["rule_count"] == 1
    assert validate_report.summary["matched_candidate_count"] == 1
    assert import_report.status == "ok"
    assert import_report.summary["rule_count"] == 1
    assert {error.code for error in mz_report.errors} == {"mv_virtual_namebox_rules_forbidden"}
    async with await registry.open_game("MVテストゲーム") as session:
        records = await session.read_mv_virtual_namebox_rules()
    assert len(records) == 1
    assert records[0].rule_name == "standalone-colon"
@pytest.mark.asyncio
async def test_validate_placeholder_rules_blocks_translatable_text_loss() -> None:
    """自定义占位符规则不能把含源语言正文的样本文本整体吞掉。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    unsafe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps({r"こんにちは": "[CUSTOM_SWALLOW_{index}]"}, ensure_ascii=False),
        sample_texts=["こんにちは"],
    )
    safe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps({r"^◆<[^>]+>ｔ": "[CUSTOM_VOICE_{index}]"}, ensure_ascii=False),
        sample_texts=["◆<アリス>ｔこんにちは"],
    )

    unsafe_error_codes = {error.code for error in unsafe_report.errors}
    safe_error_codes = {error.code for error in safe_report.errors}
    assert "placeholder_rule_loses_translatable_text" in unsafe_error_codes
    assert "placeholder_rule_loses_translatable_text" not in safe_error_codes
@pytest.mark.asyncio
async def test_validate_placeholder_rules_rejects_rust_incompatible_regex() -> None:
    """普通占位符规则不能先通过 Python 校验、再到 Rust 质检阶段失败。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"(?a:@PLUGIN\[[^\]]+\])": "[CUSTOM_PLUGIN_MARKER_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=["@PLUGIN[name]"],
    )

    assert report.status == "error"
    assert "placeholder_rules_invalid" in {error.code for error in report.errors}
    assert "Rust fancy-regex" in report.errors[0].message
@pytest.mark.asyncio
async def test_validate_structured_placeholder_rules_rejects_rust_incompatible_regex(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符规则导入前必须通过 Rust fancy-regex 预检。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "INLINE_LABEL",
                    "type": "paired_shell",
                    "pattern": r"(?a:(?P<prefix><label>))(?P<text>[^<]+)(?P<suffix></label>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "prefix": "[CUSTOM_INLINE_LABEL_PREFIX_{index}]",
                        "suffix": "[CUSTOM_INLINE_LABEL_SUFFIX_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=["<label>薬草</label>"],
    )

    assert report.status == "error"
    assert "structured_placeholder_rules_invalid" in {error.code for error in report.errors}
    assert "Rust fancy-regex" in report.errors[0].message
@pytest.mark.asyncio
async def test_audit_active_runtime_reuses_scan_cache_and_invalidates_changed_files(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行审计跨命令复用 AST 缓存，并在文件 hash 变化时重新扫描。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_text = plugins_path.read_text(encoding="utf-8")
    plugins = ensure_json_array(
        coerce_json_value(cast(object, json.loads(plugins_text[plugins_text.index("["):plugins_text.rindex("]") + 1]))),
        "plugins",
    )
    plugins.append({"name": "CacheSource", "status": True, "description": "", "parameters": {}})
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    source_path = plugin_source_dir / "CacheSource.js"
    _ = source_path.write_text("const Messages = { title: 'カテゴリ' };\n", encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    first_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert first_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        cached_records = await session.read_plugin_source_runtime_scan_cache()
    cached_by_name = {record.file_name: record for record in cached_records}
    assert "CacheSource.js" in cached_by_name
    assert cached_by_name["CacheSource.js"].literals
    cached_file_count = len(cached_records)
    assert first_report.summary["active_runtime_scan_cache_input_record_count"] == 0
    assert first_report.summary["active_runtime_scan_cache_current_file_count"] == cached_file_count
    assert first_report.summary["active_runtime_scan_cache_hit_file_count"] == 0
    assert first_report.summary["active_runtime_scan_cache_miss_file_count"] == cached_file_count
    assert first_report.summary["active_runtime_scan_cache_rescan_file_count"] == cached_file_count

    scan_calls: list[tuple[str, ...]] = []

    def counting_scan(
        *,
        files: dict[str, str],
        active_file_names: frozenset[str],
        text_rules: TextRules | None = None,
    ) -> PluginSourceBatchTextScan:
        """记录真正进入 AST 扫描的文件。"""
        scan_calls.append(tuple(sorted(files)))
        return real_scan_plugin_source_files_text_strict(
            files=files,
            active_file_names=active_file_names,
            text_rules=text_rules,
        )

    monkeypatch.setattr(
        "app.plugin_source_text.runtime_audit.scan_plugin_source_files_text_strict",
        counting_scan,
    )
    second_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert second_report.status == "ok"
    assert second_report.summary["active_runtime_scan_cache_hit_file_count"] == cached_file_count
    assert second_report.summary["active_runtime_scan_cache_miss_file_count"] == 0
    assert second_report.summary["active_runtime_scan_cache_stale_file_count"] == 0
    assert second_report.summary["active_runtime_scan_cache_rescan_file_count"] == 0
    assert scan_calls == []

    _ = source_path.write_text("const Messages = { title: 'カテゴリ変更' };\n", encoding="utf-8")
    third_report = await service.audit_active_runtime(game_title="テストゲーム")
    assert third_report.status == "ok"
    assert third_report.summary["active_runtime_scan_cache_hit_file_count"] == cached_file_count - 1
    assert third_report.summary["active_runtime_scan_cache_stale_file_count"] == 1
    assert third_report.summary["active_runtime_scan_cache_rescan_file_count"] == 1
    assert scan_calls == [("CacheSource.js",)]
@pytest.mark.asyncio
async def test_import_placeholder_rules_runs_validation_before_save(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """占位符规则导入不能绕过可翻译内容损失校验。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({r"こんにちは": "[CUSTOM_SWALLOW_{index}]"}, ensure_ascii=False),
    )

    assert report.status == "error"
    assert "placeholder_rule_loses_translatable_text" in {error.code for error in report.errors}
    async with await registry.open_game("テストゲーム") as session:
        records = await session.read_placeholder_rules()
    assert records == []
@pytest.mark.asyncio
async def test_import_placeholder_rules_loads_translation_source_once(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通占位符规则导入在同一加载上下文内完成验证和覆盖检查。"""
    load_count = 0
    extract_count = 0

    async def counting_load_game_data_for_view(
        game_path: str | Path,
        *,
        source_view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        nonlocal load_count
        load_count += 1
        return await real_load_game_data_for_view(
            game_path,
            source_view=source_view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    class CountingExtractService(AgentToolkitService):
        @override
        async def _extract_active_translation_data_map(
            self,
            *,
            session: TargetGameSession,
            game_data: GameData,
            text_rules: TextRules,
            plugin_source_scan: PluginSourceScan | None = None,
        ) -> dict[str, TranslationData]:
            nonlocal extract_count
            extract_count += 1
            return await super()._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                plugin_source_scan=plugin_source_scan,
            )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", counting_load_game_data_for_view)
    service = CountingExtractService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    assert report.status in {"ok", "warning"}
    assert load_count == 1
    assert extract_count == 1
@pytest.mark.asyncio
async def test_validate_placeholder_rules_uses_warm_text_index_without_full_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 可用时，占位符规则校验不再构建完整文本范围。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("validate-placeholder-rules 命中 warm index 时不应构建完整文本范围")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)

    report = await service.validate_placeholder_rules(
        game_title="テストゲーム",
        custom_placeholder_rules_text="{}",
        sample_texts=[],
    )

    assert report.status in {"ok", "warning"}
    assert report.summary["rule_count"] == 0
@pytest.mark.asyncio
async def test_import_placeholder_rules_uses_warm_text_index_without_full_scope_build(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warm index 可用时，占位符规则导入复用索引完成验证和覆盖检查。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    _ = await _rebuild_text_index_for_test(service)

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("import-placeholder-rules 命中 warm index 时不应构建完整文本范围")

    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    assert report.status in {"ok", "warning"}
    assert report.summary["imported_rule_count"] == 0
@pytest.mark.asyncio
async def test_import_structured_placeholder_rules_saves_separate_records(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符规则单独保存，不混入普通正则占位符规则表。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "MINI_LABEL",
                    "pattern": r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                        "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    validate_report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=["<Mini Label: Alraune>"],
    )
    import_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    async with await registry.open_game("テストゲーム") as session:
        placeholder_records = await session.read_placeholder_rules()
        structured_records = await session.read_structured_placeholder_rules()

    assert validate_report.status == "ok"
    assert import_report.status in {"ok", "warning"}
    assert placeholder_records == []
    assert structured_records == [
        StructuredPlaceholderRuleRecord(
            rule_name="MINI_LABEL",
            rule_type="paired_shell",
            pattern_text=r"(?P<open><Mini\s+Label:\s*)(?P<text>[^<>\r\n]*?)(?P<close>>)",
            translatable_group="text",
            protected_groups={
                "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
            },
        )
    ]
@pytest.mark.asyncio
async def test_import_structured_placeholder_rules_loads_translation_source_once(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """结构化占位符规则导入复用同一正文上下文完成验证和覆盖检查。"""
    load_count = 0
    extract_count = 0

    async def counting_load_game_data_for_view(
        game_path: str | Path,
        *,
        source_view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        nonlocal load_count
        load_count += 1
        return await real_load_game_data_for_view(
            game_path,
            source_view=source_view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    class CountingExtractService(AgentToolkitService):
        @override
        async def _extract_active_translation_data_map(
            self,
            *,
            session: TargetGameSession,
            game_data: GameData,
            text_rules: TextRules,
            plugin_source_scan: PluginSourceScan | None = None,
        ) -> dict[str, TranslationData]:
            nonlocal extract_count
            extract_count += 1
            return await super()._extract_active_translation_data_map(
                session=session,
                game_data=game_data,
                text_rules=text_rules,
                plugin_source_scan=plugin_source_scan,
            )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", counting_load_game_data_for_view)
    service = CountingExtractService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )

    assert report.status in {"ok", "warning"}
    assert load_count == 1
    assert extract_count == 1
@pytest.mark.asyncio
async def test_import_empty_placeholder_rules_confirms_uncovered_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """空普通占位符规则确认后，未覆盖候选不再卡住流程。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    missing_report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
    )
    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )
    doctor_report = await service.doctor(game_title="テストゲーム", check_llm=False)
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
        coverage = build_normal_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            text_rules=text_rules,
            rule_count=0,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert missing_report.status == "error"
    assert "confirm-empty" in missing_report.errors[0].message
    assert report.status == "warning"
    assert {"placeholder_rules_empty", "placeholder_uncovered_reviewed"} <= {warning.code for warning in report.warnings}
    assert report.summary["uncovered_count"] != 0
    assert "placeholder_uncovered_reviewed" in {warning.code for warning in doctor_report.warnings}
    assert state is not None
    assert state.reviewed_empty is True
    assert state.scope_hash == coverage.scope_hash
    assert "placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_import_empty_placeholder_rules_uses_full_candidate_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """普通占位符导入确认必须用完整候选集合计算 hash，不能只用 stdout 样本。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [fr"\ZZCustom{index}[Face{index}] Line {index}" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="English Fixture Game",
        rules_text="{}",
        confirm_empty=True,
    )

    game_data = await load_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
    coverage = build_normal_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        text_rules=text_rules,
        rule_count=0,
    )
    legacy_hash = placeholder_rule_scope_hash(coverage.candidates[:100])

    assert report.status == "warning"
    assert coverage.candidate_count > 100
    assert state is not None
    assert state.scope_hash == coverage.scope_hash
    assert state.scope_hash != legacy_hash
@pytest.mark.asyncio
async def test_confirmed_empty_placeholder_risk_allows_quality_warning_and_write_back(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认空占位符风险后，正确保留协议片段的译文必须能写回。"""
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
    service = AgentToolkitService(game_registry=registry, setting_path=app_home / "setting.toml")
    placeholder_report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )
    structured_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"paired_shell_rules": []}, ensure_ascii=False),
        confirm_empty=True,
    )
    pending_path = tmp_path / "pending-translations.json"
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )

    setting = load_setting(app_home / "setting.toml", source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    payload = load_json_object(pending_path)
    manual_payload: dict[str, object] = {}
    for location_path, raw_entry in payload.items():
        entry = ensure_json_object(coerce_json_value(raw_entry), location_path)
        original_lines = ensure_json_array(entry["original_lines"], f"{location_path}.original_lines")
        translation_lines: list[str] = []
        for raw_line in original_lines:
            if not isinstance(raw_line, str):
                raise TypeError(f"{location_path}.original_lines 必须是字符串数组")
            translation_lines.append(
                _translated_test_line_preserving_protocol_candidates(raw_line, text_rules)
            )
        manual_entry: JsonObject = {key: value for key, value in entry.items()}
        manual_entry["translation_lines"] = [cast(JsonValue, line) for line in translation_lines]
        manual_payload[location_path] = manual_entry
    manual_path = tmp_path / "manual-translations.json"
    _ = manual_path.write_text(json.dumps(manual_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = await _rebuild_text_index_for_test(service)

    manual_report = await service.import_manual_translations(
        game_title="テストゲーム",
        input_path=manual_path,
    )
    quality_report = await service.quality_report(game_title="テストゲーム")
    handler = TranslationHandler(registry, LLMHandler())
    try:
        write_summary = await handler.write_back(
            game_title="テストゲーム",
            callbacks=(lambda _current, _total: None, lambda _count: None),
        )
    finally:
        await handler.close()

    assert placeholder_report.status == "warning"
    assert placeholder_report.summary["uncovered_count"] != 0
    assert structured_report.status in {"ok", "warning"}
    assert export_report.status == "ok"
    assert manual_report.status == "ok"
    assert quality_report.status == "warning", quality_report.to_json_text()
    assert {warning.code for warning in quality_report.warnings} == {"placeholder_uncovered_reviewed"}
    assert quality_report.errors == []
    assert write_summary.data_item_count > 0
@pytest.mark.asyncio
async def test_import_nonempty_placeholder_rules_confirms_remaining_uncovered_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """非空普通占位符规则仍有候选时，保存 reviewed_empty=false 的风险确认。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"NO_MATCH": "[CUSTOM_NO_MATCH_{index}]"}, ensure_ascii=False),
    )
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=PLACEHOLDER_RULE_DOMAIN)
        coverage = build_normal_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            text_rules=text_rules,
            rule_count=1,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert report.status == "warning"
    assert "placeholder_uncovered_reviewed" in {warning.code for warning in report.warnings}
    assert report.summary["imported_rule_count"] == 1
    assert report.summary["uncovered_count"] != 0
    assert state is not None
    assert state.reviewed_empty is False
    assert state.scope_hash == coverage.scope_hash
    assert "placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_import_empty_structured_placeholder_rules_confirms_uncovered_candidates(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """空结构化占位符规则确认后，协议外壳候选不再卡住流程。"""
    _replace_first_common_event_text(minimal_english_game_dir, "<名前: Alraune>")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    missing_report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
    )
    report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )
    doctor_report = await service.doctor(game_title="English Fixture Game", check_llm=False)
    game_data = await load_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
        coverage = build_structured_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=0,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert missing_report.status == "error"
    assert "confirm-empty" in missing_report.errors[0].message
    assert report.status == "warning"
    assert {"structured_placeholder_rules_empty", "structured_placeholder_uncovered_reviewed"} <= {
        warning.code
        for warning in report.warnings
    }
    assert report.summary["uncovered_count"] == 1
    assert "structured_placeholder_uncovered_reviewed" in {warning.code for warning in doctor_report.warnings}
    assert state is not None
    assert state.reviewed_empty is True
    assert state.scope_hash == coverage.scope_hash
    assert "structured_placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_import_empty_structured_placeholder_rules_uses_full_candidate_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符导入确认必须用完整候选集合计算 hash，不能只用前 100 个样本。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [f"<Name{index}: Alice{index}>" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text='{"paired_shell_rules": []}',
        confirm_empty=True,
    )

    game_data = await load_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
    coverage = build_structured_placeholder_coverage_result(
        translation_data_map=scope.translation_data_map,
        structured_rules=text_rules.structured_placeholder_rules,
        rule_count=0,
    )
    legacy_hash = structured_placeholder_rule_scope_hash(coverage.candidates[:100])

    assert report.status == "warning"
    assert coverage.candidate_count > 100
    assert state is not None
    assert state.scope_hash == coverage.scope_hash
    assert state.scope_hash != legacy_hash
@pytest.mark.asyncio
async def test_import_nonempty_structured_placeholder_rules_confirms_remaining_uncovered_candidates(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """非空结构化规则仍未覆盖候选时，保存 reviewed_empty=false 的风险确认。"""
    _replace_first_common_event_text(minimal_english_game_dir, "<名前: Alraune>")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "NEVER",
                    "pattern": r"(?P<open><Never>)(?P<text>[^<>\r\n]+)(?P<close></Never>)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_NEVER_OPEN_{index}]",
                        "close": "[CUSTOM_NEVER_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    report = await service.import_structured_placeholder_rules(
        game_title="English Fixture Game",
        rules_text=rules_text,
    )
    game_data = await load_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        state = await session.read_rule_review_state(rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN)
        coverage = build_structured_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=1,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert report.status == "warning"
    assert "structured_placeholder_uncovered_reviewed" in {warning.code for warning in report.warnings}
    assert report.summary["imported_rule_count"] == 1
    assert report.summary["uncovered_count"] == 1
    assert state is not None
    assert state.reviewed_empty is False
    assert state.scope_hash == coverage.scope_hash
    assert "structured_placeholder_uncovered" not in {error.code for error in errors}
@pytest.mark.asyncio
async def test_placeholder_candidate_review_rejects_legacy_sampled_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """旧版前 100 候选 hash 不再兼容放行，必须按完整候选范围重新审查。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [fr"\ZZLegacy{index}[Face{index}] Line {index}" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    game_data = await load_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        coverage = build_normal_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            text_rules=text_rules,
            rule_count=0,
        )
        legacy_hash = placeholder_rule_scope_hash(coverage.candidates[:100])
        await session.replace_rule_review_state(
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            scope_hash=legacy_hash,
            reviewed_empty=True,
        )
        decisions = await collect_placeholder_candidate_review_decisions(
            session=session,
            scope=scope,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            stage="workflow_gate",
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    placeholder_decision = next(decision for decision in decisions if decision.rule_domain == PLACEHOLDER_RULE_DOMAIN)
    assert coverage.candidate_count > 100
    assert placeholder_decision.confirmation_status == "stale"
    assert placeholder_decision.severity == "error"
    assert placeholder_decision.code == "placeholder_uncovered"
    assert "placeholder_uncovered" in {error.code for error in errors}
@pytest.mark.asyncio
async def test_structured_placeholder_candidate_review_rejects_legacy_sampled_hash(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """结构化占位符旧版前 100 候选 hash 不再兼容放行。"""
    _insert_common_event_texts(
        minimal_english_game_dir,
        [f"<Legacy{index}: Alice{index}>" for index in range(120)],
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="English Fixture Game",
        game_dir=minimal_english_game_dir,
    )
    game_data = await load_game_data(minimal_english_game_dir)
    async with await registry.open_game("English Fixture Game") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        coverage = build_structured_placeholder_coverage_result(
            translation_data_map=scope.translation_data_map,
            structured_rules=text_rules.structured_placeholder_rules,
            rule_count=0,
        )
        legacy_hash = structured_placeholder_rule_scope_hash(coverage.candidates[:100])
        await session.replace_rule_review_state(
            rule_domain=STRUCTURED_PLACEHOLDER_RULE_DOMAIN,
            scope_hash=legacy_hash,
            reviewed_empty=True,
        )
        decisions = await collect_placeholder_candidate_review_decisions(
            session=session,
            scope=scope,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            stage="workflow_gate",
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    structured_decision = next(
        decision
        for decision in decisions
        if decision.rule_domain == STRUCTURED_PLACEHOLDER_RULE_DOMAIN
    )
    assert coverage.candidate_count > 100
    assert structured_decision.confirmation_status == "stale"
    assert structured_decision.severity == "error"
    assert structured_decision.code == "structured_placeholder_uncovered"
    assert "structured_placeholder_uncovered" in {error.code for error in errors}
@pytest.mark.asyncio
async def test_placeholder_candidate_review_state_mismatch_blocks_workflow(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """候选范围变化后，旧的占位符候选风险确认不能继续放行。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )
        await session.replace_rule_review_state(
            rule_domain=PLACEHOLDER_RULE_DOMAIN,
            scope_hash="stale-placeholder-scope",
            reviewed_empty=True,
        )
        errors = await collect_workflow_gate_errors(
            session=session,
            game_data=game_data,
            setting=setting,
            text_rules=text_rules,
            custom_placeholder_rules_supplied=False,
            scope=scope,
        )

    assert "placeholder_uncovered" in {error.code for error in errors}
def test_placeholder_candidate_scan_accepts_custom_span_wrapping_candidate() -> None:
    """自定义规则包住内部标准形态候选时，扫描门禁应认定已覆盖。"""
    translation_data_map = {
        "Items.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="Items.json/293/note/SG説明",
                    item_type="short_text",
                    original_lines=[r"\\v[104] / 5"],
                )
            ],
        )
    }
    text_rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                r"\\\\v\[[0-9]+\]",
                "[CUSTOM_ESCAPED_VARIABLE_{index}]",
            ),
        ),
    )

    candidates = scan_placeholder_candidate_spans(translation_data_map, text_rules)

    assert count_uncovered_candidates(candidates) == 0
    assert candidates[0].marker == r"\\v[104]"
    assert candidates[0].custom_covered is True
@pytest.mark.asyncio
async def test_build_placeholder_rules_groups_similar_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """规则草稿会把同类自定义控制符合并成少量通用正则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=output_path)

    assert report.status == "ok"
    rules = load_json_object(output_path)
    uncovered_before = report.summary["uncovered_count_before_draft"]
    assert rules == {r"(?i)\\F\d*\[[^\]\r\n]+\]": "[CUSTOM_FACE_PORTRAIT_{index}]"}
    assert report.summary["draft_rule_count"] == 1
    assert isinstance(uncovered_before, int)
    assert uncovered_before > 0
    assert report.summary["uncovered_count_after_draft_preview"] == 0
@pytest.mark.asyncio
async def test_build_placeholder_rules_keeps_bare_uppercase_marker_case_sensitive(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """裸大写自定义标记草稿不能忽略大小写误匹配字面量换行。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_value = coerce_json_value(cast(object, json.loads(common_events_path.read_text(encoding="utf-8"))))
    common_events = ensure_json_array(raw_value, "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    text_command = ensure_json_object(commands[1], "CommonEvents.json[1].list[1]")
    parameters = ensure_json_array(text_command["parameters"], "CommonEvents.json[1].list[1].parameters")
    parameters[0] = r"\N<案内人>こんにちは"
    _ = common_events_path.write_text(json.dumps(raw_value, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_external_text_rules(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    output_path = tmp_path / "placeholder-rules.json"

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=output_path)

    assert report.status == "ok"
    rules = load_json_object(output_path)
    assert rules[r"\\N\d*(?![A-Za-z\[])"] == "[CUSTOM_PLUGIN_N_MARKER_{index}]"
    assert r"(?i)\\N\d*(?![A-Za-z\[])" not in rules
@pytest.mark.asyncio
async def test_placeholder_rule_draft_requires_external_rules_and_uses_active_sources(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """占位符草稿必须等外部规则完成后再基于完整文本集合生成。"""
    game_data = await load_game_data(minimal_game_dir)
    plugin_parameters = ensure_json_object(game_data.plugins_js[0]["parameters"], "plugins[0].parameters")
    plugin_parameters["Message"] = r"\PX[PluginFace]プラグイン本文"
    plugins_text = f"var $plugins = {json.dumps(game_data.plugins_js, ensure_ascii=False, indent=2)};\n"
    _ = (minimal_game_dir / "js" / "plugins.js").write_text(plugins_text, encoding="utf-8")

    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    payload = ensure_json_object(parameters[3], "CommonEvents[1].list[4].parameters[3]")
    payload["message"] = r"\EV[CommandFace]プラグイン台詞"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")

    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = r"<拡張説明:\NT[NoteFace]薬草の詳細説明>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    before_rules_path = tmp_path / "before-placeholder-rules.json"
    after_rules_path = tmp_path / "after-placeholder-rules.json"

    blocked_report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=before_rules_path)

    fresh_game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(fresh_game_data.plugins_js[0]),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[
                        EventCommandParameterFilter(index=0, value="TestPlugin"),
                        EventCommandParameterFilter(index=1, value="Show"),
                    ],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["拡張説明"])]
        )

    report = await service.build_placeholder_rules(game_title="テストゲーム", output_path=after_rules_path)
    after_rules = load_json_object(after_rules_path)
    draft_rule_count = report.summary["draft_rule_count"]

    assert blocked_report.status == "error"
    assert {error.code for error in blocked_report.errors} >= {
        "plugin_text_missing",
        "event_command_text_missing",
        "note_tag_text_missing",
    }
    assert not before_rules_path.exists()
    assert isinstance(draft_rule_count, int)
    assert draft_rule_count >= 4
    assert any(r"\\PX" in pattern for pattern in after_rules)
    assert any(r"\\EV" in pattern for pattern in after_rules)
    assert any(r"\\NT" in pattern for pattern in after_rules)
@pytest.mark.asyncio
async def test_validate_plugin_rules_reports_json_string_leaf_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则误指向 JSON 字符串容器时，校验报告提示可写内部字符串叶子。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    rejected_report = await service.validate_plugin_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Nested']"],
                }
            ],
            ensure_ascii=False,
        ),
    )
    accepted_report = await service.validate_plugin_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Nested']['text']"],
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert rejected_report.status == "error"
    assert "解析后的内部字符串叶子" in rejected_report.errors[0].message
    assert "$['parameters']['Nested']['text']" in rejected_report.errors[0].message
    assert accepted_report.status == "ok"
@pytest.mark.asyncio
async def test_validate_plugin_rules_uses_prefix_read_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件规则校验只读取规则插件前缀内的已保存译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="plugins.js/0/Nested/text",
                    item_type="short_text",
                    original_lines=["ネスト本文"],
                    translation_lines=["嵌套正文"],
                ),
                TranslationItem(
                    location_path="Actors.json/1/name",
                    item_type="short_text",
                    original_lines=["関係ない名前"],
                    translation_lines=["无关名字"],
                ),
            ]
        )

    async def forbidden_full_path_read(_self: TargetGameSession) -> set[str]:
        raise AssertionError("插件规则校验不能全量读取已保存路径")

    monkeypatch.setattr(TargetGameSession, "read_translation_location_paths", forbidden_full_path_read)

    report = await service.validate_plugin_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "TestPlugin",
                    "paths": ["$['parameters']['Nested']['text']"],
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(coerce_json_value(report.details["rules"]), "rules")
    first_rule_detail = ensure_json_object(rule_details[0], "rules[0]")
    assert first_rule_detail["translated_count"] == 1
@pytest.mark.asyncio
async def test_validate_plugin_rules_rejects_english_protocol_value_paths(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件规则校验会把英文模式下只命中协议值的路径报告为错误。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_plugin_rules(
        game_title="English Fixture Game",
        rules_text=json.dumps(
            [
                {
                    "plugin_index": 0,
                    "plugin_name": "VisiblePlugin",
                    "paths": ["$['parameters']['Enabled']"],
                }
            ],
            ensure_ascii=False,
        ),
    )

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"plugin_rules_invalid"}
    assert "没有命中玩家可见可翻译文本" in report.errors[0].message
@pytest.mark.asyncio
async def test_plain_rule_validation_skips_plugin_source_file_loading(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件参数、Note 和事件指令规则校验不读取插件源码文件。"""
    load_flags: list[bool] = []

    async def counting_load_game_data_for_view(
        game_path: str | Path,
        *,
        source_view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        load_flags.append(include_plugin_source_files)
        if include_plugin_source_files:
            raise AssertionError("普通规则校验不应读取插件源码文件")
        return await real_load_game_data_for_view(
            game_path,
            source_view=source_view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", counting_load_game_data_for_view)
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    plugin_report = await service.validate_plugin_rules(game_title="テストゲーム", rules_text="[]")
    note_report = await service.validate_note_tag_rules(game_title="テストゲーム", rules_text="{}")
    event_report = await service.validate_event_command_rules(game_title="テストゲーム", rules_text="{}")

    assert plugin_report.summary["rule_count"] == 0
    assert note_report.summary["tag_count"] == 0
    assert event_report.summary["path_rule_count"] == 0
    assert load_flags == [False, False, False]
@pytest.mark.asyncio
async def test_mv_namebox_rule_validation_skips_plugin_source_file_loading(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MV 虚拟名字框规则校验只需要 data 事件，不读取插件源码文件。"""
    load_flags: list[bool] = []

    async def counting_load_game_data_for_view(
        game_path: str | Path,
        *,
        source_view: GameFileView,
        include_plugin_source_files: bool = False,
        include_writable_copies: bool = False,
        run_dialogue_probe_check: bool = False,
    ) -> GameData:
        load_flags.append(include_plugin_source_files)
        if include_plugin_source_files:
            raise AssertionError("MV 虚拟名字框规则校验不应读取插件源码文件")
        return await real_load_game_data_for_view(
            game_path,
            source_view=source_view,
            include_plugin_source_files=include_plugin_source_files,
            include_writable_copies=include_writable_copies,
            run_dialogue_probe_check=run_dialogue_probe_check,
        )

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    monkeypatch.setattr("app.agent_toolkit.services.core.load_game_data_for_view", counting_load_game_data_for_view)
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_mv_virtual_namebox_rules(
        game_title="MVテストゲーム",
        rules_text=_mv_virtual_namebox_rules_text(),
    )

    assert report.summary["rule_count"] == 1
    assert load_flags == [False]
@pytest.mark.asyncio
async def test_validate_note_tag_rules_uses_prefix_read_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Note 标签规则校验只读取规则文件前缀内的已保存译文。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<拡張説明:一行目>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="Items.json/1/note/拡張説明",
                    item_type="short_text",
                    original_lines=["一行目"],
                    translation_lines=["第一行"],
                ),
                TranslationItem(
                    location_path="Actors.json/1/name",
                    item_type="short_text",
                    original_lines=["関係ない名前"],
                    translation_lines=["无关名字"],
                ),
            ]
        )

    async def forbidden_full_path_read(_self: TargetGameSession) -> set[str]:
        raise AssertionError("Note 标签规则校验不能全量读取已保存路径")

    monkeypatch.setattr(TargetGameSession, "read_translation_location_paths", forbidden_full_path_read)

    report = await service.validate_note_tag_rules(
        game_title="テストゲーム",
        rules_text=json.dumps({"Items.json": ["拡張説明"]}, ensure_ascii=False),
    )

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(coerce_json_value(report.details["rules"]), "rules")
    first_rule_detail = ensure_json_object(rule_details[0], "rules[0]")
    assert first_rule_detail["translated_count"] == 1
@pytest.mark.asyncio
async def test_import_empty_note_tag_rules_allows_confirmed_empty_with_candidates(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Note 标签候选经审查没有玩家可见文本时，可以显式保存空结果。"""
    items_path = minimal_game_dir / "data" / "Items.json"
    raw_items = cast(object, json.loads(items_path.read_text(encoding="utf-8")))
    items = ensure_json_array(coerce_json_value(raw_items), "Items.json")
    item = ensure_json_object(items[1], "Items.json[1]")
    item["note"] = "<PrivateProtocol:内部コード>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    missing_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
    )
    confirmed_report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    game_data = await load_game_data(minimal_game_dir)
    async with await registry.open_game("テストゲーム") as session:
        setting = load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language)
        text_rules = TextRules.from_setting(setting.text_rules)
        state = await session.read_rule_review_state(rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN)

    assert missing_report.status == "error"
    assert "confirm-empty" in missing_report.errors[0].message
    assert confirmed_report.status == "warning"
    assert {warning.code for warning in confirmed_report.warnings} == {"note_tag_rules_empty"}
    assert state is not None
    assert state.scope_hash == note_tag_rule_scope_hash_for_text_rules(
        game_data=game_data,
        text_rules=text_rules,
    )
@pytest.mark.asyncio
async def test_import_note_tag_rules_replaces_stale_existing_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧 Note 标签规则过期时，仍然可以导入新规则并清理旧译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    stale_item = TranslationItem(
        location_path="Items.json/1/note/MissingTag",
        item_type="short_text",
        original_lines=["古いタグ"],
        translation_lines=["旧标签"],
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["MissingTag"])]
        )
        await session.write_translation_items([stale_item])

    async def forbidden_full_translation_read(_self: TargetGameSession) -> list[TranslationItem]:
        raise AssertionError("Note 标签规则导入不能全量读取已保存译文")

    monkeypatch.setattr(TargetGameSession, "read_translated_items", forbidden_full_translation_read)

    report = await service.import_note_tag_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
    )

    async with await registry.open_game("テストゲーム") as session:
        rules = await session.read_note_tag_text_rules()
        paths = await session.read_translation_location_paths()

    assert report.status == "warning"
    assert report.summary["deleted_translation_items"] == 1
    assert rules == []
    assert stale_item.location_path not in paths
@pytest.mark.asyncio
async def test_agent_reports_error_on_stale_plugin_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 工具包把过期插件规则作为覆盖审计错误，同时不生成假文本。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash="stale-hash",
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    pending_path = tmp_path / "pending-translations.json"

    quality_report = await service.quality_report(game_title="テストゲーム")
    export_report = await service.export_pending_translations(
        game_title="テストゲーム",
        output_path=pending_path,
        limit=None,
    )
    workspace_report = await service.prepare_agent_workspace(
        game_title="テストゲーム",
        output_dir=tmp_path / "workspace",
        command_codes=None,
    )

    error_codes = {error.code for error in quality_report.errors}
    assert quality_report.summary["text_index_status"] == "rebuild_failed"
    rebuild_summary = ensure_json_object(quality_report.summary["text_index_rebuild_summary"], "rebuild_summary")
    assert rebuild_summary["index_status"] == "not_rebuilt"
    assert "stale_plugin_rules" in error_codes
    assert export_report.status == "error"
    assert {error.code for error in export_report.errors} == {"stale_plugin_rules"}
    assert not pending_path.exists()
    assert workspace_report.status in {"ok", "warning"}
    assert workspace_report.summary["stale_plugin_rule_count"] == 1
    assert (tmp_path / "workspace" / "manifest.json").exists()
@pytest.mark.asyncio
async def test_validate_placeholder_rules_previews_roundtrip() -> None:
    """占位符规则校验报告展示模型可见文本与还原结果。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text='{"\\\\\\\\F\\\\[[^\\\\]]+\\\\]":"[CUSTOM_FACE_PORTRAIT_{index}]"}',
        sample_texts=[r"\F[GuideA]こんにちは\V[1]"],
    )

    assert report.status == "ok"
    assert report.summary["rule_count"] == 1
    samples = report.details["samples"]
    assert isinstance(samples, list)
    first_sample = samples[0]
    assert isinstance(first_sample, dict)
    assert first_sample["text_for_model"] == "[CUSTOM_FACE_PORTRAIT_1]こんにちは[RMMZ_VARIABLE_1]"
    assert first_sample["restored_text"] == r"\F[GuideA]こんにちは\V[1]"
    assert first_sample["roundtrip_ok"] is True
@pytest.mark.asyncio
async def test_validate_placeholder_rules_keeps_dialogue_after_joined_prefix_control() -> None:
    """校验预览能证明无分隔符控制符不会吞掉后面的英文正文。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"\\Shake": "[CUSTOM_PLUGIN_SHAKE_MARKER_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=[r"\ShakeStop this!!!"],
    )

    assert report.status == "ok"
    samples = report.details["samples"]
    assert isinstance(samples, list)
    first_sample = samples[0]
    assert isinstance(first_sample, dict)
    assert first_sample["text_for_model"] == "[CUSTOM_PLUGIN_SHAKE_MARKER_1]Stop this!!!"
    assert first_sample["restored_text"] == r"\ShakeStop this!!!"
@pytest.mark.asyncio
async def test_validate_placeholder_rules_blocks_bare_escape_match() -> None:
    """占位符规则不得误匹配裸 \\n、\\r、\\t 这类常见文本转义。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    unsafe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"(?i)\\N\d*": "[CUSTOM_PLUGIN_N_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=[r"\n"],
    )
    safe_report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text=json.dumps(
            {r"(?i)\\N\d+": "[CUSTOM_PLUGIN_N_{index}]"},
            ensure_ascii=False,
        ),
        sample_texts=[r"\N12"],
    )

    assert unsafe_report.status == "error"
    assert {error.code for error in unsafe_report.errors} == {"placeholder_rule_matches_common_escape"}
    assert safe_report.status == "ok"
@pytest.mark.asyncio
async def test_validate_placeholder_rules_warns_unicode_control_boundary() -> None:
    """占位符校验会提示非 ASCII 控制符边界，避免 Agent 按终端乱码猜测。"""
    service = AgentToolkitService(setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_placeholder_rules(
        game_title=None,
        custom_placeholder_rules_text="{}",
        sample_texts=[r"\F3[66」「ふーん……？」"],
    )

    warning_codes = {warning.code for warning in report.warnings}
    assert "unprotected_control_unicode_boundary" in warning_codes
    assert "U+300D" in report.warnings[0].message
@pytest.mark.asyncio
async def test_validate_event_command_rules_previews_direct_parameter_write_back(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """事件指令规则校验会预演 direct parameters[N] 命中项的回写。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")
    command = ensure_json_object(commands[4], "CommonEvents[1].list[4]")
    parameters = ensure_json_array(command["parameters"], "CommonEvents[1].list[4].parameters")
    parameters[2] = "トップパラメータ"
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False, indent=2), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)

    report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
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
    )

    assert report.status == "ok"
    preview = ensure_json_object(report.details["write_back_preview"], "write_back_preview")
    assert preview["status"] == "ok"
    assert preview["checked_item_count"] == 1
@pytest.mark.asyncio
async def test_validate_event_command_rules_reports_hits_per_rule(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则报告按规则组统计命中数量，避免把总命中数写到每条规则。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "357": [
                {
                    "match": {"0": "TestPlugin", "1": "Show"},
                    "paths": ["$['parameters'][3]['message']"],
                },
                {
                    "match": {"0": "ComplexPlugin", "1": "ShowWindow"},
                    "paths": [
                        "$['parameters'][3]['window']['title']",
                        "$['parameters'][3]['choices'][*]",
                    ],
                },
            ]
        },
        ensure_ascii=False,
    )
    extract_call_count = 0
    real_extract_with_rule_items = EventCommandTextExtraction.extract_all_text_with_rule_items

    def counted_extract_with_rule_items(
        self: EventCommandTextExtraction,
    ) -> tuple[dict[str, TranslationData], list[list[TranslationItem]]]:
        nonlocal extract_call_count
        extract_call_count += 1
        return real_extract_with_rule_items(self)

    def forbidden_extract_all_text(_self: EventCommandTextExtraction) -> dict[str, TranslationData]:
        raise AssertionError("事件指令规则校验不能为每条规则组重复提取")

    monkeypatch.setattr(
        EventCommandTextExtraction,
        "extract_all_text_with_rule_items",
        counted_extract_with_rule_items,
    )
    monkeypatch.setattr(EventCommandTextExtraction, "extract_all_text", forbidden_extract_all_text)

    report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )

    assert report.status == "ok"
    rule_details = ensure_json_array(report.details["rules"], "rules")
    hit_counts = [
        ensure_json_object(coerce_json_value(raw_detail), f"rules[{index}]")["hit_count"]
        for index, raw_detail in enumerate(rule_details)
    ]
    assert hit_counts == [1, 3]
    assert extract_call_count == 1
@pytest.mark.asyncio
async def test_validate_event_command_rules_uses_prefix_read_for_translated_count(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件指令规则校验只读取匹配指令前缀内的已保存译文。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/4/parameters/3/message",
                    item_type="short_text",
                    original_lines=["プラグイン台詞"],
                    translation_lines=["事件指令译文"],
                ),
                TranslationItem(
                    location_path="Actors.json/1/name",
                    item_type="short_text",
                    original_lines=["関係ない名前"],
                    translation_lines=["无关名字"],
                ),
            ]
        )

    async def forbidden_full_path_read(_self: TargetGameSession) -> set[str]:
        raise AssertionError("事件指令规则校验不能全量读取已保存路径")

    monkeypatch.setattr(TargetGameSession, "read_translation_location_paths", forbidden_full_path_read)

    report = await service.validate_event_command_rules(
        game_title="テストゲーム",
        rules_text=json.dumps(
            {
                "357": [
                    {
                        "match": {"0": "TestPlugin", "1": "Show"},
                        "paths": ["$['parameters'][3]['message']"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    assert report.status == "ok"
    assert report.summary["hit_count"] == 1
    assert report.summary["translated_count"] == 1
    rule_details = ensure_json_array(report.details["rules"], "rules")
    first_rule_detail = ensure_json_object(coerce_json_value(rule_details[0]), "rules[0]")
    assert first_rule_detail["translated_count"] == 1
@pytest.mark.asyncio
async def test_structured_placeholder_rule_with_standard_control_passes_validation_and_quality(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """临时游戏副本中结构化壳内的内置控制符应被项目检查放行。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = ensure_json_object(common_events[1], "CommonEvents.json[1]")
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(
        2,
        {
            "code": 401,
            "parameters": [r"D_TEXT \c[17]決定ボタンを連打しろ！ 48"],
        },
    )
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rules_text = json.dumps(
        {
            "paired_shell_rules": [
                {
                    "name": "D_TEXT_LABEL",
                    "pattern": r"(?P<open>^D_TEXT\s+)(?P<text>.*?)(?P<close>\s+48$)",
                    "translatable_group": "text",
                    "protected_groups": {
                        "open": "[CUSTOM_D_TEXT_OPEN_{index}]",
                        "close": "[CUSTOM_D_TEXT_CLOSE_{index}]",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    validate_report = await service.validate_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
        sample_texts=[],
    )
    import_report = await service.import_structured_placeholder_rules(
        game_title="テストゲーム",
        rules_text=rules_text,
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="CommonEvents.json/1/2",
                    item_type="long_text",
                    role="アリス",
                    original_lines=[r"D_TEXT \c[17]決定ボタンを連打しろ！ 48"],
                    source_line_paths=["CommonEvents.json/1/2"],
                    translation_lines=[r"D_TEXT \c[17]狂按决定键！ 48"],
                )
            ]
        )
    quality_report = await service.quality_report(game_title="テストゲーム")

    assert validate_report.errors == []
    assert import_report.errors == []
    assert quality_report.summary["placeholder_risk_count"] == 0
    assert quality_report.summary["source_residual_count"] == 0
