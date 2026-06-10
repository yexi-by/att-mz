"""规则导入事务边界测试。"""
# pyright: reportPrivateUsage=false

import json
from pathlib import Path
from typing import cast

import pytest

from tests.agent_toolkit_contract_fixtures import write_current_translation_items_for_test

from app.agent_toolkit import AgentToolkitService
from app.config.schemas import TextRulesSetting
from app.persistence import GameRegistry, TargetGameSession
from app.plugin_source_text import (
    build_native_plugin_source_scan,
    build_plugin_source_rule_records_from_import,
    parse_plugin_source_rule_import_text,
)
from app.plugin_source_text.extraction import _PluginSourceTextExtraction
from app.rmmz.loader import load_active_runtime_game_data
from app.rmmz.schema import PluginSourceRuntimeWriteMapRecord
from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value, ensure_json_array

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def _rewrite_plugins_js(path: Path, plugins: list[JsonValue]) -> None:
    """把插件数组写回测试用 plugins.js。"""
    _ = path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_plugin_source_rule_import_rolls_back_when_tail_step_fails(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """插件源码规则导入尾部失败时，规则、译文和运行映射必须同回滚。"""
    plugins_path = minimal_game_dir / "js" / "plugins.js"
    raw_plugins = cast(
        object,
        json.loads(plugins_path.read_text(encoding="utf-8").removeprefix("var $plugins = ").rstrip(";\n")),
    )
    plugins = ensure_json_array(
        coerce_json_value(raw_plugins),
        "plugins.js",
    )
    plugins.append({"name": "RuleSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "RuleSource.js").write_text(
        "const Messages = { oldText: '古い本文', newText: '新しい本文' };\n",
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    game_data = await load_active_runtime_game_data(
        minimal_game_dir,
        include_plugin_source_files=True,
        include_writable_copies=True,
        run_dialogue_probe_check=True,
    )
    text_rules = TextRules.from_setting(TextRulesSetting())
    scan = build_native_plugin_source_scan(game_data=game_data, text_rules=text_rules)
    old_candidate = next(candidate for candidate in scan.candidates if candidate.text == "古い本文")
    new_candidate = next(candidate for candidate in scan.candidates if candidate.text == "新しい本文")
    old_records = build_plugin_source_rule_records_from_import(
        game_data=game_data,
        import_file=parse_plugin_source_rule_import_text(
                json.dumps(
                    [
                        {
                            "file": "RuleSource.js",
                            "selectors": [old_candidate.selector],
                            "excluded_selectors": [new_candidate.selector],
                        }
                    ],
                    ensure_ascii=False,
                )
            ),
        text_rules=text_rules,
        scan=scan,
    )
    old_item = _PluginSourceTextExtraction(game_data, old_records, text_rules, scan=scan).extract_all_text()[
        "js/plugins/RuleSource.js"
    ].translation_items[0]
    old_item.translation_lines = ["旧译文"]
    runtime_map = PluginSourceRuntimeWriteMapRecord(
        location_path=old_item.location_path,
        source_file_name="RuleSource.js",
        source_selector=old_candidate.selector,
        source_file_hash=old_records[0].file_hash,
        source_text_hash="old-source-text",
        translation_lines_hash="old-translation",
        runtime_file_name="RuleSource.js",
        runtime_selector=old_candidate.selector,
        runtime_file_hash="old-runtime-file",
        runtime_text_hash="old-runtime-text",
        runtime_line=1,
        created_at="2026-06-03T00:00:00",
    )
    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(old_records)
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        await write_current_translation_items_for_test(session, [old_item])
        await session.replace_plugin_source_runtime_write_maps([runtime_map])

    async def failing_clear_runtime_maps(
        self: TargetGameSession,
    ) -> None:
        """模拟规则替换后、运行映射清理前的尾部失败。"""
        _ = self
        raise RuntimeError("forced rule import tail failure")

    monkeypatch.setattr(TargetGameSession, "clear_plugin_source_runtime_write_maps", failing_clear_runtime_maps)
    new_rules_text = json.dumps(
        [
            {
                "file": "RuleSource.js",
                "selectors": [new_candidate.selector],
                "excluded_selectors": [old_candidate.selector],
            }
        ],
        ensure_ascii=False,
    )

    report = await service.import_plugin_source_rules(
        game_title="テストゲーム",
        rules_text=new_rules_text,
    )

    assert report.status == "error"
    assert "forced rule import tail failure" in report.errors[0].message
    async with await registry.open_game("テストゲーム") as session:
        assert await session.read_plugin_source_text_rules() == old_records
        assert [item.location_path for item in await session.read_translated_items()] == [old_item.location_path]
        assert await session.read_plugin_source_runtime_write_maps() == [runtime_map]
