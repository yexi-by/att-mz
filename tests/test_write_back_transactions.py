"""写回计划文件和数据库副作用事务测试。"""

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from app.application.errors import WriteBackGateError
from app.application.handler import TranslationHandler
from app.config.schemas import Setting, TextRulesSetting, WriteBackSetting
from app.llm import LLMHandler
from app.native_write_plan import NativePlannedFile, NativeWriteBackPlan, NativeWriteBackSummary
from app.persistence import GameRegistry
from app.plugin_source_text import ActiveRuntimePluginSourceAudit, ActiveRuntimePluginSourceIssue
from app.plugin_source_text.native_scan import (
    PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION,
    PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION,
)
from app.plugin_source_text.runtime_audit import PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION
from app.rmmz.schema import GameData, PluginSourceRuntimeScanCacheRecord, PluginSourceRuntimeWriteMapRecord
from app.rmmz.text_rules import TextRules


@pytest.mark.asyncio
async def test_write_back_post_write_audit_failure_rolls_back_files_fonts_and_records(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写后审计失败时，文件、字体副作用和 DB 记录必须一起回滚。"""
    fonts_dir = minimal_game_dir / "fonts"
    fonts_dir.mkdir()
    old_font = "OldFont.woff"
    _ = (fonts_dir / old_font).write_bytes(b"old font")
    gamefont_css_path = fonts_dir / "gamefont.css"
    original_css = "@font-face { font-family: GameFont; src: url('OldFont.woff'); }\n"
    _ = gamefont_css_path.write_text(original_css, encoding="utf-8")
    replacement_font = tmp_path / "NotoSansSC-Regular.ttf"
    _ = replacement_font.write_bytes(b"new font")

    system_path = minimal_game_dir / "data" / "System.json"
    original_system_text = system_path.read_text(encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
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
    refreshed_cache = PluginSourceRuntimeScanCacheRecord(
        file_name="Broken.js",
        file_hash="runtime-hash",
        rust_contract_version=PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION,
        parser_contract_version=PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION,
        audit_contract_version=PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION,
        syntax_error="",
        literals=[],
        created_at="2026-01-01T00:00:00",
    )

    def fake_build_native_write_back_plan(**kwargs: object) -> NativeWriteBackPlan:
        """返回会先写文件和字体、再触发写后审计失败的计划。"""
        assert kwargs["mode"] == "write_back"
        return NativeWriteBackPlan(
            files=[
                NativePlannedFile(
                    target_path=system_path,
                    relative_path="data/System.json",
                    content='{"gameTitle":"已写入但应回滚"}\n',
                )
            ],
            plugin_source_runtime_write_maps=[runtime_map],
            font_replacement_records=[],
            summary=NativeWriteBackSummary(
                data_item_count=1,
                plugin_item_count=1,
                terminology_written_count=0,
                target_font_name=replacement_font.name,
                source_font_count=1,
                replaced_font_reference_count=0,
                font_copied=True,
                planned_file_count=1,
                skipped_file_count=0,
                plugin_source_runtime_map_count=1,
            ),
            timings_ms={"total": 1},
        )

    async def fake_load_active_runtime_game_data(game_path: Path, **kwargs: object) -> GameData:
        """写后审计只需要进入失败分支，不依赖真实 GameData 内容。"""
        assert game_path == minimal_game_dir
        assert kwargs == {"include_plugin_source_files": True}
        return cast(GameData, cast(object, SimpleNamespace()))

    def fake_audit_active_runtime_plugin_source_with_scan_cache(
        **kwargs: object,
    ) -> tuple[ActiveRuntimePluginSourceAudit, list[PluginSourceRuntimeScanCacheRecord]]:
        """模拟写后审计发现当前运行插件源码语法错误。"""
        assert kwargs["runtime_write_map_records"] == [runtime_map]
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
            [refreshed_cache],
        )

    monkeypatch.setattr("app.application.handler.build_native_write_back_plan", fake_build_native_write_back_plan)
    monkeypatch.setattr("app.application.handler.load_active_runtime_game_data", fake_load_active_runtime_game_data)
    monkeypatch.setattr(
        "app.application.handler.audit_active_runtime_plugin_source_with_scan_cache",
        fake_audit_active_runtime_plugin_source_with_scan_cache,
    )

    handler = TranslationHandler(registry, LLMHandler())
    try:
        async with await registry.open_game("テストゲーム") as session:
            with pytest.raises(WriteBackGateError, match="写入后当前运行文件审计未通过"):
                _ = await handler.write_runtime_files_with_native_plan(
                    session=session,
                    game_title="テストゲーム",
                    callbacks=(lambda _current, _total: None, lambda _count: None),
                    setting=cast(
                        Setting,
                        cast(
                            object,
                            SimpleNamespace(
                                text_rules=TextRulesSetting(),
                                write_back=WriteBackSetting(replacement_font_path=str(replacement_font)),
                            ),
                        ),
                    ),
                    text_rules=TextRules.from_setting(TextRulesSetting()),
                    mode="write_back",
                    writable_location_paths=[],
                    confirm_font_overwrite=True,
                    success_phase="游戏文本回写完成",
                )
    finally:
        await handler.close()

    assert system_path.read_text(encoding="utf-8") == original_system_text
    assert not (fonts_dir / replacement_font.name).exists()
    assert not (fonts_dir / "gamefont_origin.css").exists()
    assert gamefont_css_path.read_text(encoding="utf-8") == original_css
    async with await registry.open_game("テストゲーム") as session:
        assert await session.read_font_replacement_records() == []
        assert await session.read_plugin_source_runtime_write_maps() == []
        assert await session.read_plugin_source_runtime_scan_cache() == []
