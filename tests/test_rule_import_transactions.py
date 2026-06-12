"""规则导入事务边界测试。"""
import json
from pathlib import Path
from typing import cast

import pytest

from tests.agent_toolkit_contract_fixtures import write_current_translation_items_for_test

from tests.native_rule_seed import (
    seed_native_placeholder_rules,
    seed_native_plugin_source_text_rules,
)

from app.agent_toolkit import AgentToolkitService
from app.config.schemas import TextRulesSetting
from app.persistence import GameRegistry, TargetGameSession
from app.plugin_source_text import (
    build_native_plugin_source_scan,
    build_plugin_source_rule_records_from_import,
    parse_plugin_source_rule_import_text,
    plugin_source_location_path,
)
from app.rmmz.loader import load_active_runtime_game_data
from app.rmmz.schema import PlaceholderRuleRecord, PluginSourceRuntimeWriteMapRecord, TranslationItem
from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value, ensure_json_array
from app.text_facts import read_current_text_fact_translation_items_by_paths

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def _rewrite_plugins_js(path: Path, plugins: list[JsonValue]) -> None:
    """把插件数组写回测试用 plugins.js。"""
    _ = path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_rule_import_writes_backup_before_commit(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """普通占位符规则导入清理旧译文前必须先写备份文件。"""
    common_events_path = minimal_game_dir / "data" / "CommonEvents.json"
    raw_common_events = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events = ensure_json_array(coerce_json_value(raw_common_events), "CommonEvents.json")
    event = cast(dict[str, JsonValue], common_events[1])
    commands = ensure_json_array(event["list"], "CommonEvents.json[1].list")
    commands.insert(1, {"code": 401, "parameters": [r"\Shakeこんにちは"]})
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    async with await registry.open_game("テストゲーム") as session:
        await seed_native_placeholder_rules(session,
            [
                PlaceholderRuleRecord(
                    pattern_text=r"\\Shake",
                    placeholder_template="[CUSTOM_SHAKE_{index}]",
                )
            ]
        )
    rebuild_report = await service.rebuild_text_index(game_title="テストゲーム")
    assert rebuild_report.status == "ok"
    async with await registry.open_game("テストゲーム") as session:
        text_index_items = await session.read_text_index_items()
        target_item = next(
            item
            for item in text_index_items
            if any(r"\Shake" in line and "こんにちは" in line for line in item.original_lines)
        )
        current_items = await read_current_text_fact_translation_items_by_paths(
            session,
            [target_item.location_path],
        )
        translation_item = next(
            item
            for item in current_items
            if item.original_lines == target_item.original_lines
        )
        translation_item.translation_lines = ["变量问候"]
        await session.write_translation_items([translation_item])

    report = await service.import_placeholder_rules(
        game_title="テストゲーム",
        rules_text="{}",
        confirm_empty=True,
        backup_output_dir=tmp_path,
    )

    assert report.status in {"ok", "warning"}
    assert report.summary["cleanup_count"] == 1
    backup_path = Path(str(report.summary["deleted_translation_backup_path"]))
    assert backup_path.exists()
    assert json.loads(backup_path.read_text(encoding="utf-8"))


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
    old_location_path = plugin_source_location_path(
        file_name="RuleSource.js",
        selector=old_candidate.selector,
    )
    old_item = TranslationItem(
        location_path=old_location_path,
        item_type="short_text",
        original_lines=["古い本文"],
        source_line_paths=[old_location_path],
        translation_lines=["旧译文"],
    )
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
        await seed_native_plugin_source_text_rules(session, old_records)
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

    assert report.status == "warning"
    async with await registry.open_game("テストゲーム") as session:
        saved_records = await session.read_plugin_source_text_rules()
        assert len(saved_records) == 1
        assert saved_records[0].selectors == [new_candidate.selector]
        assert saved_records[0].excluded_selectors == [old_candidate.selector]
        assert await session.read_translated_items() == []
        assert await session.read_plugin_source_runtime_write_maps() == []
