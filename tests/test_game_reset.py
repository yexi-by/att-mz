"""游戏注册回溯命令测试。"""

from pathlib import Path

import aiosqlite
import pytest

from app.game_reset import reset_registered_game
from app.persistence import GameRegistry


@pytest.mark.asyncio
async def test_reset_game_requires_title_confirmation(tmp_path: Path, minimal_game_dir: Path) -> None:
    """真正执行 reset-game 前必须用完整游戏标题确认。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    report = await reset_registered_game(
        game_title=record.game_title,
        dry_run=False,
        confirm_game_title=None,
        game_registry=registry,
    )

    assert report.status == "error"
    assert report.summary["mode"] == "confirmation_required"
    assert record.db_path.exists()
    assert (minimal_game_dir / "data_origin").exists()


@pytest.mark.asyncio
async def test_reset_game_restores_runtime_and_deletes_registration(
    tmp_path: Path,
    minimal_game_dir: Path,
) -> None:
    """reset-game 恢复运行文件，再删除数据库和注册快照。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with aiosqlite.connect(record.db_path) as connection:
        _ = await connection.execute("DROP TABLE nonstandard_data_text_rules")
        await connection.commit()
    data_path = minimal_game_dir / "data" / "System.json"
    data_origin_path = minimal_game_dir / "data_origin" / "System.json"
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    plugins_origin_path = minimal_game_dir / "js" / "plugins_origin.js"
    plugin_source_path = minimal_game_dir / "js" / "plugins" / "TestPlugin.js"
    plugin_source_origin_path = minimal_game_dir / "js" / "plugins_source_origin" / "TestPlugin.js"
    extra_plugin_source_path = minimal_game_dir / "js" / "plugins" / "ExtraPlugin.js"
    fonts_dir = minimal_game_dir / "fonts"
    gamefont_css_path = fonts_dir / "gamefont.css"
    gamefont_origin_css_path = fonts_dir / "gamefont_origin.css"
    origin_data_text = data_origin_path.read_text(encoding="utf-8")
    origin_plugins_text = plugins_origin_path.read_text(encoding="utf-8")
    origin_plugin_source_text = plugin_source_origin_path.read_text(encoding="utf-8")

    _ = data_path.write_text('{"gameTitle": "壊れた"}\n', encoding="utf-8")
    _ = plugins_path.write_text("var $plugins = [];\n", encoding="utf-8")
    _ = plugin_source_path.write_text("console.log('changed');\n", encoding="utf-8")
    _ = extra_plugin_source_path.write_text("console.log('extra');\n", encoding="utf-8")
    fonts_dir.mkdir(exist_ok=True)
    _ = gamefont_css_path.write_text("@font-face { src: url('NewFont.ttf'); }\n", encoding="utf-8")
    _ = gamefont_origin_css_path.write_text("@font-face { src: url('OldFont.ttf'); }\n", encoding="utf-8")

    dry_run_report = await reset_registered_game(
        game_path=minimal_game_dir,
        dry_run=True,
        confirm_game_title=None,
        game_registry=registry,
    )

    assert dry_run_report.summary["changed"] is False
    assert data_path.read_text(encoding="utf-8") != origin_data_text
    assert record.db_path.exists()

    report = await reset_registered_game(
        game_path=minimal_game_dir,
        dry_run=False,
        confirm_game_title=record.game_title,
        game_registry=registry,
    )

    assert report.status == "warning"
    assert report.summary["mode"] == "reset"
    assert report.summary["changed"] is True
    assert data_path.read_text(encoding="utf-8") == origin_data_text
    assert plugins_path.read_text(encoding="utf-8") == origin_plugins_text
    assert plugin_source_path.read_text(encoding="utf-8") == origin_plugin_source_text
    assert not extra_plugin_source_path.exists()
    assert gamefont_css_path.read_text(encoding="utf-8") == "@font-face { src: url('OldFont.ttf'); }\n"
    assert not gamefont_origin_css_path.exists()
    assert not (minimal_game_dir / "data_origin").exists()
    assert not (minimal_game_dir / "js" / "plugins_origin.js").exists()
    assert not (minimal_game_dir / "js" / "plugins_source_origin").exists()
    assert not record.db_path.exists()
