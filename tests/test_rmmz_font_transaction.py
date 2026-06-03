"""RPG Maker 字体事务业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *

@pytest.mark.asyncio
async def test_direct_write_back_rejects_active_runtime_read_error_before_font_side_effects(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前运行源码读取失败时，Rust 计划阶段直接失败且不改字体。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    fonts_dir = minimal_game_dir / "fonts"
    fonts_dir.mkdir()
    old_font = "OldFont.woff"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    gamefont_css_path = fonts_dir / "gamefont.css"
    original_css = (
        "@font-face { font-family: GameFont; src: url('OldFont.woff'); }\n"
    )
    _ = gamefont_css_path.write_text(original_css, encoding="utf-8")
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

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
        with pytest.raises(RuntimeError, match="插件源码读取失败"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
                setting_overrides=SettingOverrides(
                    write_back_replacement_font_path=str(replacement_font),
                ),
                confirm_font_overwrite=True,
            )
    finally:
        await handler.close()

    assert not (fonts_dir / replacement_font.name).exists()
    assert not (fonts_dir / "gamefont_origin.css").exists()
    assert gamefont_css_path.read_text(encoding="utf-8") == original_css
@pytest.mark.asyncio
async def test_restore_font_references_restores_mv_gamefont_css_without_rolling_back_other_css(
    minimal_mv_game_dir: Path,
) -> None:
    """字体还原会按 gamefont.css 原始备份恢复 MV 字体族入口。"""
    fonts_dir = minimal_mv_game_dir / "www" / "fonts"
    fonts_dir.mkdir()
    old_font = "YujiSyuku-Regular.ttf"
    css_only_font = "衡山毛筆フォント_0.TTF"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    gamefont_css_path = fonts_dir / "gamefont.css"
    origin_css = (
        "\n".join(
            [
                "@font-face {",
                "  font-family: GameFont;",
                "  src: url('YujiSyuku-Regular.ttf');",
                "}",
                "@font-face {",
                "  font-family: 'GameFont2';",
                f"  src: url(\"{css_only_font}\");",
                "}",
                "",
            ]
        )
    )
    replacement_name = "NotoSansSC-Regular.ttf"
    _ = gamefont_css_path.with_name("gamefont_origin.css").write_text(origin_css, encoding="utf-8")
    _ = gamefont_css_path.write_text(
        origin_css.replace(old_font, replacement_name).replace(css_only_font, replacement_name)
        + "\n/* 已写入译文后新增的样式 */\n",
        encoding="utf-8",
    )

    restore_summary = restore_font_references_from_origin_backups(
        game_root=minimal_mv_game_dir,
        replacement_font_names=[replacement_name],
    )

    restored_css = gamefont_css_path.read_text(encoding="utf-8")
    assert restore_summary.restored_field_count == 2
    assert restore_summary.restored_reference_count == 2
    assert "url('YujiSyuku-Regular.ttf')" in restored_css
    assert "url(\"衡山毛筆フォント_0.TTF\")" in restored_css
    assert replacement_name not in restored_css
    assert "已写入译文后新增的样式" in restored_css
@pytest.mark.asyncio
async def test_restore_font_references_uses_origin_backups_without_rolling_back_text(
    minimal_game_dir: Path,
) -> None:
    """字体还原按原始备份替回旧字体引用，不回滚已经写入的译文。"""
    fonts_dir = minimal_game_dir / "fonts"
    fonts_dir.mkdir()
    old_font = "OldFont.woff"
    another_font = "AnotherFont.woff"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    _ = (fonts_dir / another_font).write_bytes(b"another font")
    replacement_name = "NotoSansSC-Regular.ttf"

    system_path = minimal_game_dir / "data" / "System.json"
    raw_system = _read_test_json(system_path)
    system = ensure_json_object(raw_system, "System.json")
    system["advanced"] = {
        "mainFontFilename": old_font,
        "numberFontFilename": another_font,
    }
    _rewrite_json(system_path, raw_system)
    base_game_data = await load_game_data(minimal_game_dir)

    data_origin_dir = minimal_game_dir / "data_origin"
    data_origin_dir.mkdir()
    _rewrite_json(data_origin_dir / "System.json", raw_system)

    plugin = ensure_json_object(base_game_data.plugins_js[0], "plugins[0]")
    parameters = ensure_json_object(plugin["parameters"], "plugins[0].parameters")
    parameters["FontFace"] = old_font
    parameters["FontStem"] = Path(old_font).stem
    parameters["Nested"] = json.dumps(
        {"font": another_font, "text": "プラグイン本文"},
        ensure_ascii=False,
    )
    parameters["HelpText"] = f"请在设置中选择 {old_font} 字体。"
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(base_game_data.plugins_js, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    plugins_origin_path = minimal_game_dir / "js" / "plugins_origin.js"
    _ = plugins_origin_path.write_text(plugins_path.read_text(encoding="utf-8"), encoding="utf-8")

    active_system = ensure_json_object(_read_test_json(system_path), "System.json")
    active_system["gameTitle"] = "翻译标题"
    active_advanced = ensure_json_object(active_system["advanced"], "System.advanced")
    active_advanced["mainFontFilename"] = replacement_name
    active_advanced["numberFontFilename"] = replacement_name
    _rewrite_json(system_path, active_system)

    active_plugins = read_plugins_js_file(plugins_path)
    active_plugin = ensure_json_object(active_plugins[0], "plugins[0]")
    active_parameters = ensure_json_object(active_plugin["parameters"], "plugins[0].parameters")
    active_parameters["FontFace"] = replacement_name
    active_parameters["FontStem"] = Path(replacement_name).stem
    active_parameters["Nested"] = json.dumps(
        {"font": another_font, "text": "插件正文"},
        ensure_ascii=False,
    )
    active_parameters["Nested"] = active_parameters["Nested"].replace(another_font, replacement_name)
    active_parameters["HelpText"] = f"请在设置中选择 {replacement_name} 字体。"
    _ = plugins_path.write_text(
        f"var $plugins = {json.dumps(active_plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )

    restore_summary = restore_font_references_from_origin_backups(
        game_root=minimal_game_dir,
        replacement_font_names=[replacement_name],
    )

    assert restore_summary.restored_reference_count == 5
    active_system = ensure_json_object(_read_test_json(system_path), "System.json")
    active_advanced = ensure_json_object(active_system["advanced"], "System.advanced")
    assert active_system["gameTitle"] == "翻译标题"
    assert active_advanced["mainFontFilename"] == old_font
    assert active_advanced["numberFontFilename"] == another_font

    restored_plugins = read_plugins_js_file(plugins_path)
    restored_plugin = ensure_json_object(restored_plugins[0], "plugins[0]")
    restored_parameters = ensure_json_object(restored_plugin["parameters"], "plugins[0].parameters")
    assert restored_parameters["FontFace"] == old_font
    assert restored_parameters["FontStem"] == Path(old_font).stem
    nested_text = restored_parameters["Nested"]
    assert isinstance(nested_text, str)
    nested_value = ensure_json_object(coerce_json_value(cast(object, json.loads(nested_text))), "Nested")
    assert nested_value["font"] == another_font
    assert nested_value["text"] == "插件正文"
    assert restored_parameters["HelpText"] == f"请在设置中选择 {replacement_name} 字体。"
