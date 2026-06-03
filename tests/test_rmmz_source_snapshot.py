"""RPG Maker 可信源快照和加载视图业务契约测试。"""

from __future__ import annotations

from tests.rmmz_writeback_contract_fixtures import *

@pytest.mark.asyncio
async def test_loader_only_keeps_standard_rmmz_data_files(minimal_game_dir: Path) -> None:
    """加载器接收官方 data 文件，并跳过未知插件衍生 JSON。"""
    game_data = await load_game_data(minimal_game_dir)

    assert "UnknownPluginData.json" not in game_data.data
    assert "System.json" in game_data.data
    assert "Map001.json" in game_data.map_data
    assert "Map002.json" in game_data.map_data
    assert game_data.plugins_js[0]["name"] == "TestPlugin"
    assert game_data.plugins_js[1]["name"] == "ComplexPlugin"
@pytest.mark.asyncio
async def test_direct_write_back_rejects_missing_source_snapshot_manifest(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native 快路径进入 Rust 前必须校验数据库可信源快照 manifest。"""
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    setting_text = _example_setting_text_with_absolute_prompt_files()
    _ = (app_home / "setting.toml").write_text(setting_text, encoding="utf-8")
    monkeypatch.setenv("ATT_MZ_HOME", str(app_home))

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await _prepare_write_gate_session(session=session, game_dir=minimal_game_dir)
        await session.replace_source_snapshot_records([])

    handler = TranslationHandler(registry, LLMHandler())
    try:
        with pytest.raises(RuntimeError, match="可信源快照 manifest"):
            _ = await handler.write_back(
                game_title="テストゲーム",
                callbacks=(lambda _current, _total: None, lambda _count: None),
            )
    finally:
        await handler.close()
@pytest.mark.asyncio
async def test_add_game_creates_complete_source_snapshot_manifest(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """注册游戏时创建完整可信源快照和数据库 manifest。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")

    assert (minimal_game_dir / "data_origin" / "System.json").is_file()
    assert (minimal_game_dir / "js" / "plugins_origin.js").is_file()
    assert (minimal_game_dir / "js" / "plugins_source_origin" / "TestPlugin.js").is_file()
    async with await registry.open_game("テストゲーム") as session:
        records = await session.read_source_snapshot_records()
    relative_paths = {record.relative_path for record in records}
    assert "data_origin/System.json" in relative_paths
    assert "js/plugins_origin.js" in relative_paths
    assert "js/plugins_source_origin/TestPlugin.js" in relative_paths
@pytest.mark.asyncio
async def test_source_snapshot_manifest_ignores_active_plugin_source_drift(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """可信源 manifest 只校验快照自身，不被当前运行插件源码新增文件影响。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    _ = (minimal_game_dir / "js" / "plugins" / "ExtraRuntimeOnly.js").write_text(
        "const label = '追加実行ファイル';\n",
        encoding="utf-8",
    )

    async with await registry.open_game("テストゲーム") as session:
        records = await session.read_source_snapshot_records()

    validate_source_snapshot_manifest(
        layout=resolve_game_layout(minimal_game_dir),
        records=records,
    )
    game_data = await load_game_data_for_view(
        minimal_game_dir,
        source_view=GameFileView.TRANSLATION_SOURCE,
    )
    assert "ExtraRuntimeOnly.js" not in game_data.plugin_source_files
@pytest.mark.asyncio
async def test_add_game_rejects_existing_source_snapshot_artifacts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """首次注册只接受没有可信源快照文件的干净游戏目录。"""
    _ = shutil.copytree(minimal_game_dir / "data", minimal_game_dir / "data_origin")
    registry = GameRegistry(tmp_path / "db")

    with pytest.raises(FileExistsError, match="干净游戏目录"):
        _ = await registry.register_game(minimal_game_dir, source_language="ja")
@pytest.mark.asyncio
async def test_translation_source_view_requires_source_snapshot(minimal_game_dir: Path) -> None:
    """显式翻译源视图缺少可信源快照时必须 fail-fast。"""
    with pytest.raises(FileNotFoundError, match="原始 data 备份"):
        _ = await load_game_data_for_view(
            minimal_game_dir,
            source_view=GameFileView.TRANSLATION_SOURCE,
        )
@pytest.mark.asyncio
async def test_translation_source_view_ignores_damaged_active_data_when_snapshot_valid(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前运行 data 损坏时，显式翻译源视图仍只读取可信源快照。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    (minimal_game_dir / "data" / "System.json").unlink()

    game_data = await load_game_data_for_view(
        minimal_game_dir,
        source_view=GameFileView.TRANSLATION_SOURCE,
    )

    assert game_data.system.gameTitle == "テストゲーム"
@pytest.mark.asyncio
async def test_active_runtime_loader_skips_writable_copies_by_default(minimal_game_dir: Path) -> None:
    """当前运行只读视图默认不构造写入副本。"""
    read_only_game_data = await load_active_runtime_game_data(minimal_game_dir)
    writable_game_data = await load_active_runtime_game_data(
        minimal_game_dir,
        include_writable_copies=True,
    )

    assert read_only_game_data.data
    assert read_only_game_data.plugins_js
    assert read_only_game_data.writable_data == {}
    assert read_only_game_data.writable_plugins_js == []
    assert read_only_game_data.writable_plugin_source_files == {}
    assert writable_game_data.writable_data
    assert writable_game_data.writable_plugins_js
    assert writable_game_data.writable_data["System.json"] is not writable_game_data.data["System.json"]
    assert writable_game_data.writable_plugins_js[0] is not writable_game_data.plugins_js[0]
@pytest.mark.asyncio
async def test_translation_source_view_uses_lightweight_defaults(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """翻译源显式视图默认不读取插件源码、不构造写入副本、不执行对话探针。"""

    def forbidden_dialogue_probe(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise AssertionError("轻量翻译源加载不应执行全游戏对话探针")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.rmmz.loader.run_dialogue_probe", forbidden_dialogue_probe)

    game_data = await load_game_data_for_view(
        minimal_game_dir,
        source_view=GameFileView.TRANSLATION_SOURCE,
    )

    assert game_data.plugin_source_files == {}
    assert game_data.plugin_source_read_errors == {}
    assert game_data.writable_data == {}
    assert game_data.writable_plugins_js == []
    assert game_data.writable_plugin_source_files == {}
@pytest.mark.asyncio
async def test_translation_source_view_keeps_heavy_capabilities_explicit(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码、写入副本和对话探针仍可通过显式参数启用。"""

    probe_calls = 0

    def count_dialogue_probe(*args: object, **kwargs: object) -> None:
        nonlocal probe_calls
        _ = (args, kwargs)
        probe_calls += 1

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    monkeypatch.setattr("app.rmmz.loader.run_dialogue_probe", count_dialogue_probe)

    game_data = await load_game_data_for_view(
        minimal_game_dir,
        source_view=GameFileView.TRANSLATION_SOURCE,
        include_plugin_source_files=True,
        include_writable_copies=True,
        run_dialogue_probe_check=True,
    )

    assert probe_calls == 1
    assert set(game_data.plugin_source_files) == {"ComplexPlugin.js", "TestPlugin.js"}
    assert game_data.writable_data
    assert game_data.writable_plugins_js
    assert game_data.writable_data["System.json"] is not game_data.data["System.json"]
    assert game_data.writable_plugins_js[0] is not game_data.plugins_js[0]
@pytest.mark.asyncio
async def test_force_full_restore_rewrites_all_runtime_files_from_source_snapshot(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """重建模式必须恢复未发生译文变化但已损坏的当前运行文件。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    system_origin = _read_test_json(minimal_game_dir / "data_origin" / "System.json")
    animation_origin = _read_test_json(minimal_game_dir / "data_origin" / "Animations.json")
    plugins_origin_text = (minimal_game_dir / "js" / "plugins_origin.js").read_text(encoding="utf-8")
    plugin_source_origin_text = (
        minimal_game_dir / "js" / "plugins_source_origin" / "TestPlugin.js"
    ).read_text(encoding="utf-8")

    _ = (minimal_game_dir / "data" / "System.json").write_text("{}", encoding="utf-8")
    (minimal_game_dir / "data" / "Animations.json").unlink()
    _ = (minimal_game_dir / "js" / "plugins.js").write_text("var $plugins = [];\n", encoding="utf-8")
    _ = (minimal_game_dir / "js" / "plugins" / "TestPlugin.js").write_text(
        "const broken = true;\n",
        encoding="utf-8",
    )

    game_data = await load_game_data_for_view(
        minimal_game_dir,
        source_view=GameFileView.TRANSLATION_SOURCE,
        include_plugin_source_files=True,
        include_writable_copies=True,
    )
    write_game_files(
        game_data,
        minimal_game_dir,
        force_full_restore=True,
    )

    assert _read_test_json(minimal_game_dir / "data" / "System.json") == system_origin
    assert _read_test_json(minimal_game_dir / "data" / "Animations.json") == animation_origin
    assert (minimal_game_dir / "js" / "plugins.js").read_text(encoding="utf-8") == plugins_origin_text
    assert (
        (minimal_game_dir / "js" / "plugins" / "TestPlugin.js").read_text(encoding="utf-8")
        == plugin_source_origin_text
    )
@pytest.mark.asyncio
async def test_write_data_text_restores_converted_outer_quote_before_indent(minimal_game_dir: Path) -> None:
    """写回阶段先修复被模型改写的外层引号，再补跨行视觉缩进。"""
    _create_test_source_snapshot(minimal_game_dir)
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.original_lines = ["「甲。", "乙」"]
    item.translation_lines = ["“甲乙丙。", "丁戊己。”"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item], text_rules=get_default_text_rules())

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "「甲乙丙。"
    assert ensure_json_array(ensure_json_object(commands[2], "command2")["parameters"], "command2.parameters")[0] == "　丁戊己。」"
@pytest.mark.asyncio
async def test_write_data_text_restores_mismatched_source_quote_slots(minimal_game_dir: Path) -> None:
    """写回阶段按源文真实引号槽位修复错配引号。"""
    _create_test_source_snapshot(minimal_game_dir)
    game_data = await load_game_data(minimal_game_dir)
    extracted = DataTextExtraction(game_data, get_default_text_rules()).extract_all_text()
    item = next(
        candidate
        for candidate in extracted["CommonEvents.json"].translation_items
        if candidate.location_path == "CommonEvents.json/1/0"
    )
    item.original_lines = ["これが『秒殺テク」……！"]
    item.translation_lines = ["这就是‘秒杀技术’……！"]

    reset_writable_copies(game_data)
    write_data_text(game_data, [item], text_rules=get_default_text_rules())

    common_events = ensure_json_array(game_data.writable_data["CommonEvents.json"], "CommonEvents")
    common_event = ensure_json_object(common_events[1], "CommonEvents[1]")
    commands = ensure_json_array(common_event["list"], "CommonEvents[1].list")

    assert ensure_json_array(ensure_json_object(commands[1], "command1")["parameters"], "command1.parameters")[0] == "这就是『秒杀技术」……！"
@pytest.mark.asyncio
async def test_write_game_files_rejects_missing_source_snapshot(minimal_game_dir: Path) -> None:
    """测试写回 helper 不能把当前运行文件自动复制成可信源快照。"""
    game_data = await load_active_runtime_game_data(
        minimal_game_dir,
        include_plugin_source_files=True,
        include_writable_copies=True,
    )

    with pytest.raises(FileNotFoundError, match="可信源快照|重新注册"):
        write_game_files(game_data, minimal_game_dir)

    assert not (minimal_game_dir / "data_origin").exists()
    assert not (minimal_game_dir / "js" / "plugins_origin.js").exists()
@pytest.mark.asyncio
async def test_loader_rejects_missing_fixed_active_data_file(minimal_game_dir: Path) -> None:
    """激活 data 缺标准文件时禁止加载游戏。"""
    (minimal_game_dir / "data" / "Animations.json").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "激活数据目录" in message
    assert "Animations.json" in message
@pytest.mark.asyncio
async def test_loader_rejects_map_infos_with_missing_map_file(minimal_game_dir: Path) -> None:
    """MapInfos.json 引用不存在的地图文件时禁止加载游戏。"""
    map_infos_path = minimal_game_dir / "data" / "MapInfos.json"
    map_infos = ensure_json_array(_read_test_json(map_infos_path), "MapInfos.json")
    map_infos.append(
        {
            "id": 14,
            "expanded": False,
            "name": "",
            "order": 14,
            "parentId": 0,
            "scrollX": 0,
            "scrollY": 0,
        }
    )
    _rewrite_json(map_infos_path, map_infos)

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "MapInfos.json" in message
    assert "Map014.json" in message
@pytest.mark.asyncio
async def test_loader_rejects_incomplete_data_origin(minimal_game_dir: Path) -> None:
    """data_origin 必须是完整原始 data 备份。"""
    origin_data_dir = minimal_game_dir / "data_origin"
    origin_data_dir.mkdir()
    _ = shutil.copy2(
        minimal_game_dir / "data" / "CommonEvents.json",
        origin_data_dir / "CommonEvents.json",
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data(minimal_game_dir)

    message = str(exc_info.value)
    assert "原始 data 备份" in message
    assert "Animations.json" in message
@pytest.mark.asyncio
async def test_loader_separates_translation_source_and_active_runtime_data(minimal_game_dir: Path) -> None:
    """翻译源读取完整 data_origin，当前运行视图仍报告激活 data 损坏。"""
    _ = shutil.copytree(minimal_game_dir / "data", minimal_game_dir / "data_origin")
    _ = shutil.copy2(minimal_game_dir / "js" / "plugins.js", minimal_game_dir / "js" / "plugins_origin.js")
    (minimal_game_dir / "data" / "Animations.json").unlink()

    translation_source_data = await load_game_data_for_view(
        minimal_game_dir,
        source_view=GameFileView.TRANSLATION_SOURCE,
        include_plugin_source_files=False,
    )

    assert translation_source_data.system.gameTitle == "テストゲーム"
    with pytest.raises(FileNotFoundError) as exc_info:
        _ = await load_game_data_for_view(
            minimal_game_dir,
            source_view=GameFileView.ACTIVE_RUNTIME,
        )

    message = str(exc_info.value)
    assert "激活数据目录" in message
    assert "Animations.json" in message
