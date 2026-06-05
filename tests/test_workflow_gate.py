"""Workflow Gate 单一事实来源测试。"""

import json
from pathlib import Path
from typing import NoReturn, cast

import pytest

from app.agent_toolkit import AgentToolkitService
from app.application.handler import TranslationHandler, TranslationRunLimits
from app.utils.config_loader_utils import load_setting
from app.llm import LLMHandler
from app.note_tag_text.exporter import collect_note_tag_candidates
from app.persistence import GameRegistry
from app.plugin_text import build_plugin_hash
from app.rmmz import load_game_data
from app.rmmz.schema import EventCommandParameterFilter, EventCommandTextRuleRecord, PluginTextRuleRecord
from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value, ensure_json_array, ensure_json_object
from app.rule_review import NOTE_TAG_TEXT_RULE_DOMAIN, note_tag_rule_scope_hash_for_candidates
from app.terminology import TerminologyGlossary, TerminologyRegistry

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def _rewrite_plugins_js(path: Path, plugins: list[JsonValue]) -> None:
    """把插件数组写回测试用 plugins.js。"""
    _ = path.write_text(
        f"var $plugins = {json.dumps(plugins, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )


def _read_plugins_js(path: Path) -> list[JsonValue]:
    """读取测试夹具中的 plugins.js 数组。"""
    raw_text = path.read_text(encoding="utf-8")
    raw_json = cast(object, json.loads(raw_text.removeprefix("var $plugins = ").rstrip(";\n")))
    raw_value = coerce_json_value(raw_json)
    return ensure_json_array(raw_value, "plugins.js")


def _add_high_risk_plugin_source(game_dir: Path) -> None:
    """给测试游戏追加一个高风险启用插件源码文件。"""
    plugins_path = game_dir / "js" / "plugins.js"
    plugins = _read_plugins_js(plugins_path)
    plugins.append({"name": "HighRiskSource", "status": True, "description": "", "parameters": {}})
    _rewrite_plugins_js(plugins_path, plugins)
    plugin_source_dir = game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    _ = (plugin_source_dir / "HighRiskSource.js").write_text(
        "\n".join(
            f"Window_Base.prototype.drawText('高リスク{i}', 0, 0, 320);"
            for i in range(301)
        ),
        encoding="utf-8",
    )


def _add_high_risk_nonstandard_data(game_dir: Path) -> None:
    """给测试游戏追加一个高风险非标准 data 文件。"""
    _ = (game_dir / "data" / "UnknownPluginData.json").write_text(
        json.dumps([{"id": 1, "name": "これは未分類です"}], ensure_ascii=False),
        encoding="utf-8",
    )


async def _install_non_plugin_source_gate_prerequisites(
    *,
    registry: GameRegistry,
    game_title: str,
    game_dir: Path,
) -> None:
    """安装除插件源码支线外的最小 workflow gate 前置状态。"""
    game_data = await load_game_data(game_dir)
    first_plugin = ensure_json_object(game_data.plugins_js[0], "plugins[0]")
    plugin_name_value = first_plugin.get("name")
    if not isinstance(plugin_name_value, str):
        raise TypeError("测试插件名必须是字符串")
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="ja")
    text_rules = TextRules.from_setting(setting.text_rules)
    note_candidates = collect_note_tag_candidates(game_data=game_data, text_rules=text_rules)
    async with await registry.open_game(game_title) as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name=plugin_name_value,
                    plugin_hash=build_plugin_hash(first_plugin),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[
                        EventCommandParameterFilter(index=0, value=plugin_name_value),
                        EventCommandParameterFilter(index=1, value="Show"),
                    ],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_rule_review_state(
            rule_domain=NOTE_TAG_TEXT_RULE_DOMAIN,
            scope_hash=note_tag_rule_scope_hash_for_candidates(note_candidates),
            reviewed_empty=True,
        )
        await session.replace_terminology_bundle(
            registry=TerminologyRegistry(),
            glossary=TerminologyGlossary(),
        )


@pytest.mark.asyncio
async def test_translate_max_items_blocks_unreviewed_high_risk_plugin_source(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """小批翻译使用 warm index 时也不能绕过插件源码高风险门禁。"""
    _ = app_home_with_example_setting
    _add_high_risk_plugin_source(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_non_plugin_source_gate_prerequisites(
        registry=registry,
        game_title="テストゲーム",
        game_dir=minimal_game_dir,
    )

    async def forbidden_batches(*args: object, **kwargs: object) -> NoReturn:
        """插件源码高风险未审查时不能进入模型批次。"""
        _ = (args, kwargs)
        raise AssertionError("插件源码高风险未审查时 translate --max-items 不能进入模型批次")

    monkeypatch.setattr(TranslationHandler, "_run_prepared_translation_batches", forbidden_batches)
    monkeypatch.setattr(TranslationHandler, "_run_text_translation_batches", forbidden_batches)
    handler = TranslationHandler(registry, LLMHandler())
    try:
        summary = await handler.translate_text(
            game_title="テストゲーム",
            setting_overrides=None,
            custom_placeholder_rules_text=None,
            run_limits=TranslationRunLimits(max_items=3),
            callbacks=(lambda _current, _total: None, lambda _count: None, lambda _status: None),
        )
    finally:
        await handler.close()

    assert summary.blocked_reason is not None
    assert "插件源码" in summary.blocked_reason
    assert "高风险" in summary.blocked_reason
    assert summary.batch_count == 0


@pytest.mark.asyncio
async def test_rebuild_text_index_blocks_unreviewed_high_risk_plugin_source(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
) -> None:
    """重建文本索引也必须由 gate 自己识别无规则高风险插件源码。"""
    _ = app_home_with_example_setting
    _add_high_risk_plugin_source(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title="テストゲーム")

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"plugin_source_text_high_risk"}


@pytest.mark.asyncio
async def test_rebuild_text_index_blocks_unreviewed_high_risk_nonstandard_data(
    minimal_game_dir: Path,
    tmp_path: Path,
    app_home_with_example_setting: Path,
) -> None:
    """重建文本索引写入前必须阻断未归类的高风险非标准 data。"""
    _ = app_home_with_example_setting
    _add_high_risk_nonstandard_data(minimal_game_dir)
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title="テストゲーム")

    assert report.status == "error"
    assert {error.code for error in report.errors} == {"nonstandard_data_high_risk"}
