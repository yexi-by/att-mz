"""持久文本范围索引测试。"""

import json
from dataclasses import replace
from pathlib import Path
from typing import NoReturn, cast

import pytest

from tests.agent_toolkit_contract_fixtures import _install_minimal_workflow_gate_prerequisites

from app.agent_toolkit import AgentToolkitService
from app.application.flow_gate import event_command_rule_scope_hash_for_command_codes
from app.config import SettingOverrides
from app.native_scope_index import build_native_plugin_source_candidates_payload, scan_native_rule_candidates
from app.nonstandard_data.scanner import build_nonstandard_data_file_hash
from app.observability import DebugRuntimeSettings, DiagnosticsContext, bind_diagnostics_context
from app.persistence import GameRegistry
from app.persistence.records import TextIndexMetadata
from app.plugin_source_text.scanner import build_plugin_source_file_hash
from app.rule_review import EVENT_COMMAND_TEXT_RULE_DOMAIN, PLUGIN_TEXT_RULE_DOMAIN
from app.rmmz import load_game_data
from app.rmmz.schema import (
    MvVirtualNameboxRuleRecord,
    NonstandardDataTextRuleRecord,
    PlaceholderRuleRecord,
    PluginSourceTextRuleRecord,
    TranslationErrorItem,
)
from app.rmmz.text_rules import TextRules, coerce_json_value, ensure_json_object
from app.text_index import (
    TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY,
    TEXT_INDEX_PLACEHOLDER_GATE_PREFIX,
    TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY,
    TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX,
    TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE,
    collect_text_index_external_rule_gate_errors,
    collect_text_index_rules_fingerprint,
    detect_text_index_invalidations,
    evaluate_text_index_scope_gate,
    text_index_source_branch_gates_prechecked,
)
from app.text_scope import TextScopeService
from app.utils.config_loader_utils import load_setting

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def build_english_text_rules() -> TextRules:
    """构造测试用英文文本规则。"""
    setting = load_setting(EXAMPLE_SETTING_PATH, source_language="en")
    return TextRules.from_setting(setting.text_rules)


@pytest.mark.asyncio
async def test_rebuild_text_index_persists_current_text_scope(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """公开重建命令会通过 Rust 保存当前文本范围索引。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )

    async with await registry.open_game(record.game_title) as session:
        text_rules = build_english_text_rules()
        missing_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        assert [item.reason_key for item in missing_invalidations] == ["text_index_missing"]

    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        index_items = await session.read_text_index_items()
        assert await session.read_text_index_metadata() == metadata
        assert index_items
        assert metadata.item_count == len(index_items)
        assert all(len(item.source_snapshot_fingerprint) == 64 for item in index_items)
        assert all(len(item.rules_fingerprint) == 64 for item in index_items)
        scope_summary = await session.read_text_index_scope_summary()
        domain_summary = await session.read_text_index_domain_summary()
        rule_hit_summary = await session.read_text_index_rule_hit_summary()
        assert scope_summary is not None
        assert scope_summary.total_count >= metadata.item_count
        assert scope_summary.active_count == metadata.item_count
        assert scope_summary.writable_count == sum(1 for item in index_items if item.writable)
        assert domain_summary
        assert sum(item.active_count for item in domain_summary) == metadata.item_count
        assert isinstance(rule_hit_summary, list)
        locator = ensure_json_object(
            coerce_json_value(cast(object, json.loads(index_items[0].locator_json))),
            "locator_json",
        )
        assert locator["location_path"] == index_items[0].location_path

        assert await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        ) == []


@pytest.mark.asyncio
async def test_text_index_invalidation_detects_rule_and_source_snapshot_changes(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """规则和可信源快照 manifest 变化会让索引显式过期。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        text_rules = build_english_text_rules()
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        assert (await session.read_text_index_metadata()) == metadata

        await session.replace_placeholder_rules(
            [
                PlaceholderRuleRecord(
                    pattern_text=r"<name:[^>]+>",
                    placeholder_template="[CUSTOM_NAME_{index}]",
                )
            ]
        )
        rule_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        assert [item.reason_key for item in rule_invalidations] == ["rules_changed"]

        await session.replace_placeholder_rules([])
        snapshot_records = await session.read_source_snapshot_records()
        assert snapshot_records
        await session.replace_source_snapshot_records(
            [
                replace(snapshot_records[0], sha256="0" * 64),
                *snapshot_records[1:],
            ]
        )
        source_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        assert [item.reason_key for item in source_invalidations] == ["source_snapshot_changed"]


@pytest.mark.asyncio
async def test_prompt_context_version_change_invalidates_text_index(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt context 索引元信息版本变化必须让 warm index 显式过期。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )

    async with await registry.open_game(record.game_title) as session:
        text_rules = build_english_text_rules()
        monkeypatch.setattr("app.text_index.TEXT_INDEX_PROMPT_CONTEXT_VERSION", "legacy-prompt-context-test")
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        text_rules = build_english_text_rules()
        monkeypatch.setattr("app.text_index.TEXT_INDEX_PROMPT_CONTEXT_VERSION", "current-prompt-context-test")
        invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )

    assert [item.reason_key for item in invalidations] == ["rules_changed"]


@pytest.mark.asyncio
async def test_agent_service_rebuild_text_index_writes_database_index(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent 服务重建文本范围索引后，数据库可读取同一份元信息。"""

    async def forbidden_text_scope_build(*args: object, **kwargs: object) -> NoReturn:
        """生产 rebuild-text-index 冷路径不应构建 Python 完整 scope。"""
        _ = (args, kwargs)
        raise AssertionError("rebuild-text-index 冷路径不应调用 TextScopeService.build")

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """首次冷重建不应为了 gate 加载 Python GameData。"""
        _ = (args, kwargs)
        raise AssertionError("rebuild-text-index 冷路径不应加载 Python GameData")

    def forbidden_scope_restore(*args: object, **kwargs: object) -> NoReturn:
        """首次冷重建不应把 text_index_items 还原成完整 scope 只为补 gate。"""
        _ = (args, kwargs)
        raise AssertionError("rebuild-text-index 冷路径不应还原完整 scope")

    from app.agent_toolkit.services import text_index as text_index_service_module

    assert not hasattr(text_index_service_module, "collect_workflow_gate_errors")
    assert not hasattr(text_index_service_module, "refresh_text_index_external_rule_gate_metadata")
    assert not hasattr(text_index_service_module, "text_index_items_to_scope")
    monkeypatch.setattr(TextScopeService, "build", forbidden_text_scope_build)
    monkeypatch.setattr(
        AgentToolkitService,
        "_load_translation_source_game_data",
        forbidden_game_data_load,
    )
    monkeypatch.setattr(
        "app.text_index.text_index_items_to_scope",
        forbidden_scope_restore,
    )

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )

    diagnostics = DiagnosticsContext.create_for_command(
        command="rebuild-text-index",
        settings=DebugRuntimeSettings(enabled=True, timings_enabled=True),
        diagnostics_dir=tmp_path / "diagnostics",
    )
    with bind_diagnostics_context(diagnostics):
        report = await service.rebuild_text_index(game_title=record.game_title)

    assert report.status == "ok"
    indexed_count = report.summary["indexed_count"]
    assert isinstance(indexed_count, int)
    assert indexed_count > 0
    assert report.summary["index_item_count"] == indexed_count
    assert report.summary["index_status"] == "rebuilt"
    assert report.summary["text_fact_count"] == indexed_count
    assert isinstance(report.summary["render_part_count"], int)
    assert report.summary["render_part_count"] >= indexed_count
    assert isinstance(report.summary["scope_key"], str)
    assert str(report.summary["scope_key"]).startswith("tfv2-scope:")
    assert isinstance(report.summary["scope_hash"], str)
    assert len(str(report.summary["scope_hash"])) == 64
    assert isinstance(report.summary["source_snapshot_hash"], str)
    assert len(str(report.summary["source_snapshot_hash"])) == 64
    assert isinstance(report.summary["rule_hash"], str)
    assert len(str(report.summary["rule_hash"])) == 64
    assert isinstance(report.summary["text_rules_hash"], str)
    assert len(str(report.summary["text_rules_hash"])) == 64
    assert isinstance(report.summary["domain_fact_counts"], dict)
    domain_fact_counts = cast(dict[str, object], report.summary["domain_fact_counts"])
    standard_data_fact_count = domain_fact_counts.get("standard_data")
    assert isinstance(standard_data_fact_count, int)
    assert not isinstance(standard_data_fact_count, bool)
    assert standard_data_fact_count >= 1
    assert isinstance(report.summary["scan_file_count"], int)
    assert report.summary["scan_file_count"] >= 1
    assert "elapsed_ms" not in report.summary
    assert "native_thread_count" not in report.summary
    assert "stage_timings" not in report.summary
    assert "rust_stage_timings" not in report.summary
    timings = diagnostics.timings
    assert "text_index.rebuild.load_config_and_rules" in timings
    assert "text_index.rebuild.rust" in timings
    assert "text_index.rebuild.rust.internal.scan_standard_data" in timings
    assert "text_index.rebuild.rust.internal.build_workflow_gate_metadata" in timings
    assert "text_index.rebuild.rust.internal.write_storage" in timings
    async with await registry.open_game(record.game_title) as session:
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        assert metadata.item_count == indexed_count
        assert text_index_source_branch_gates_prechecked(metadata)
        assert PLUGIN_TEXT_RULE_DOMAIN in metadata.workflow_gate_scope_hashes
        assert any(
            key.startswith(f"{TEXT_INDEX_PLACEHOLDER_GATE_PREFIX}:")
            for key in metadata.workflow_gate_scope_hashes
        )
        assert any(
            key.startswith(f"{TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX}:")
            for key in metadata.workflow_gate_scope_hashes
        )
        assert len(await session.read_text_index_items()) == indexed_count
        scope_summary = await session.read_text_index_scope_summary()
        assert scope_summary is not None
        assert scope_summary.active_count == indexed_count
        assert diagnostics.counters["runtime.native_thread_count"] == scope_summary.native_thread_count


@pytest.mark.asyncio
async def test_rebuild_text_index_recomputes_gate_metadata_without_python_fallback(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续重建同一索引时，也只能由 Rust 重建当前 gate 元信息。"""

    async def forbidden_game_data_load(*args: object, **kwargs: object) -> NoReturn:
        """源快照和规则未变时不应加载完整 GameData 做 gate。"""
        _ = (args, kwargs)
        raise AssertionError("连续 rebuild-text-index 不应重新加载完整 GameData")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title=record.game_title,
        game_dir=minimal_english_game_dir,
    )
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    first_report = await service.rebuild_text_index(game_title=record.game_title)
    assert first_report.status == "ok"
    async with await registry.open_game(record.game_title) as session:
        first_metadata = await session.read_text_index_metadata()
    assert first_metadata is not None
    assert text_index_source_branch_gates_prechecked(first_metadata)
    placeholder_hashes = {
        key: value
        for key, value in first_metadata.workflow_gate_scope_hashes.items()
        if key.startswith(f"{TEXT_INDEX_PLACEHOLDER_GATE_PREFIX}:")
        or key.startswith(f"{TEXT_INDEX_STRUCTURED_PLACEHOLDER_GATE_PREFIX}:")
    }
    assert placeholder_hashes

    from app.agent_toolkit.services import text_index as text_index_service_module

    assert not hasattr(text_index_service_module, "collect_workflow_gate_errors")
    assert not hasattr(text_index_service_module, "refresh_text_index_external_rule_gate_metadata")
    monkeypatch.setattr(
        AgentToolkitService,
        "_load_translation_source_game_data",
        forbidden_game_data_load,
    )

    second_report = await service.rebuild_text_index(game_title=record.game_title)

    assert second_report.status == "ok"
    assert second_report.summary["source_branch_gate_status"] == "prechecked"
    assert "stage_timings" not in second_report.summary
    assert "rust_stage_timings" not in second_report.summary
    async with await registry.open_game(record.game_title) as session:
        second_metadata = await session.read_text_index_metadata()
    assert second_metadata is not None
    assert text_index_source_branch_gates_prechecked(second_metadata)
    assert {
        key: second_metadata.workflow_gate_scope_hashes[key]
        for key in placeholder_hashes
    } == placeholder_hashes


@pytest.mark.asyncio
async def test_rebuild_text_index_event_command_scope_hash_matches_current_confirmation_order(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷索引写入的事件指令 hash 必须等价于当前空规则确认 hash。"""
    setting_path = tmp_path / "setting.toml"
    setting_text = EXAMPLE_SETTING_PATH.read_text(encoding="utf-8")
    setting_text = setting_text.replace(
        "prompts/text_translation_ja_to_zh_system.md",
        (ROOT / "prompts" / "text_translation_ja_to_zh_system.md").as_posix(),
    )
    setting_text = setting_text.replace(
        "prompts/text_translation_en_to_zh_system.md",
        (ROOT / "prompts" / "text_translation_en_to_zh_system.md").as_posix(),
    )
    _ = setting_path.write_text(setting_text.replace("mz = [357]", "mz = [101]"), encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=setting_path,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "ok"
    game_data = await load_game_data(minimal_game_dir)
    expected_hash = event_command_rule_scope_hash_for_command_codes(
        game_data=game_data,
        command_codes=frozenset({101}),
    )
    async with await registry.open_game(record.game_title) as session:
        metadata = await session.read_text_index_metadata()
    assert metadata is not None
    assert metadata.workflow_gate_scope_hashes[EVENT_COMMAND_TEXT_RULE_DOMAIN] == expected_hash


@pytest.mark.asyncio
async def test_agent_service_rebuild_text_index_strips_mv_virtual_namebox_speaker_lines(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷索引必须按 MV 虚拟名字框规则剥离说话人行，避免写回计划必然失败。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events_raw = cast(object, json.loads(common_events_path.read_text(encoding="utf-8")))
    assert isinstance(common_events_raw, list)
    common_events = cast(list[object], common_events_raw)
    common_events.append(
        cast(object, {
            "id": 88,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人："]},
                {"code": 401, "parameters": ["次の本文です"]},
                {"code": 0, "parameters": []},
            ],
        })
    )
    common_events.append(
        cast(object, {
            "id": 89,
            "list": [
                {"code": 101, "parameters": [0, 0, 0, 2]},
                {"code": 401, "parameters": ["案内人「こんにちは」"]},
                {"code": 0, "parameters": []},
            ],
        })
    )
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_mv_virtual_namebox_rules(
            [
                MvVirtualNameboxRuleRecord(
                    rule_order=0,
                    rule_name="standalone-colon",
                    pattern_text=r"^(?P<speaker>[^:：\r\n]+)[:：]$",
                    speaker_group="speaker",
                    body_group="",
                    speaker_policy="translate",
                    render_template="{speaker}：",
                ),
                MvVirtualNameboxRuleRecord(
                    rule_order=1,
                    rule_name="inline-quote",
                    pattern_text=r"^(?P<speaker>[^「\r\n]+)「(?P<body>.*)」$",
                    speaker_group="speaker",
                    body_group="body",
                    speaker_policy="translate",
                    render_template="{speaker}「{body}」",
                ),
            ]
        )

    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        items = {
            item.location_path: item
            for item in await session.read_text_index_items()
        }

    standalone = items["CommonEvents.json/88/0"]
    assert standalone.role == "案内人"
    assert standalone.original_lines == ["次の本文です"]
    assert standalone.source_line_paths == ["CommonEvents.json/88/2"]

    inline = items["CommonEvents.json/89/0"]
    assert inline.role == "案内人"
    assert inline.original_lines == ["こんにちは"]
    assert inline.source_line_paths == ["CommonEvents.json/89/1"]


@pytest.mark.asyncio
async def test_agent_service_rebuild_text_index_includes_nonstandard_data_rule_text(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷索引必须收录受规则管理的非标准 data 文本，供 warm write-back 写回。"""
    recipes_path = minimal_english_game_dir / "data" / "Recipes.json"
    recipes = [
        {"Name": "Clam Chowder and Bread", "Learned": "true"},
        {"Name": "Apple Pie", "Learned": "false"},
    ]
    recipes_raw = json.dumps(recipes, ensure_ascii=False)
    _ = recipes_path.write_text(recipes_raw, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_nonstandard_data_text_rules(
            [
                NonstandardDataTextRuleRecord(
                    file_name="Recipes.json",
                    file_hash=build_nonstandard_data_file_hash(recipes_raw),
                    path_templates=["$[*]['Name']"],
                    excluded_path_templates=["$[*]['Learned']"],
                )
            ]
        )

    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        items = {
            item.location_path: item
            for item in await session.read_text_index_items()
        }

    chowder = items["nonstandard-data/Recipes.json/$[0]['Name']"]
    assert chowder.source_type == "nonstandard_data"
    assert chowder.source_file == "Recipes.json"
    assert chowder.original_lines == ["Clam Chowder and Bread"]
    assert chowder.source_line_paths == ["$[0]['Name']"]

    pie = items["nonstandard-data/Recipes.json/$[1]['Name']"]
    assert pie.original_lines == ["Apple Pie"]
    assert "nonstandard-data/Recipes.json/$[0]['Learned']" not in items


@pytest.mark.asyncio
async def test_agent_service_rebuild_text_index_includes_plugin_source_rule_text(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷索引必须收录已导入插件源码 selector 规则。"""
    source = "\n".join(
        [
            "(() => {",
            "  const message = '冷索引本文';",
            "})();",
        ]
    )
    plugin_source_path = minimal_game_dir / "js" / "plugins" / "TestPlugin.js"
    _ = plugin_source_path.write_text(source, encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    source_for_rules = (minimal_game_dir / "js" / "plugins_source_origin" / "TestPlugin.js").read_bytes().decode(
        "utf-8"
    )
    text_rules = TextRules.from_setting(load_setting(EXAMPLE_SETTING_PATH, source_language="ja").text_rules)
    native_scan = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files={"TestPlugin.js": source_for_rules},
            enabled_plugin_files={"TestPlugin.js"},
            text_rules=text_rules,
        )
    )
    candidate = next(
        ensure_json_object(item, "plugin_source_candidate")
        for item in native_scan.candidates
        if ensure_json_object(item, "plugin_source_candidate")["original_text"] == "冷索引本文"
    )
    selector = candidate["selector"]
    assert isinstance(selector, str)

    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="TestPlugin.js",
                    file_hash=build_plugin_source_file_hash(source_for_rules),
                    selectors=[selector],
                    excluded_selectors=[],
                )
            ]
        )

    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        items = {
            item.location_path: item
            for item in await session.read_text_index_items()
        }

    location_path = f"js/plugins/TestPlugin.js/{selector}"
    plugin_item = items[location_path]
    assert plugin_item.source_type == "plugin_source"
    assert plugin_item.source_file == "TestPlugin.js"
    assert plugin_item.original_lines == ["冷索引本文"]
    assert plugin_item.source_line_paths == [location_path]


@pytest.mark.asyncio
async def test_rebuild_text_index_allows_plugin_source_file_hash_drift_when_selector_still_matches(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码冷索引不应把整文件 hash 漂移当成 selector 规则失效。"""
    source = "\n".join(
        [
            "(() => {",
            "  const message = 'ハッシュ漂移本文';",
            "})();",
        ]
    )
    plugin_source_path = minimal_game_dir / "js" / "plugins" / "TestPlugin.js"
    _ = plugin_source_path.write_text(source, encoding="utf-8", newline="\n")
    source_for_rules = plugin_source_path.read_text(encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    text_rules = TextRules.from_setting(load_setting(EXAMPLE_SETTING_PATH, source_language="ja").text_rules)
    native_scan = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files={"TestPlugin.js": source_for_rules},
            enabled_plugin_files={"TestPlugin.js"},
            text_rules=text_rules,
        )
    )
    candidate = next(
        ensure_json_object(item, "plugin_source_candidate")
        for item in native_scan.candidates
        if ensure_json_object(item, "plugin_source_candidate")["original_text"] == "ハッシュ漂移本文"
    )
    selector = candidate["selector"]
    assert isinstance(selector, str)

    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="TestPlugin.js",
                    file_hash="stale-diagnostic-hash",
                    selectors=[selector],
                    excluded_selectors=[],
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "ok", report.errors[0].message if report.errors else report
    async with await registry.open_game(record.game_title) as session:
        items = {
            item.location_path: item
            for item in await session.read_text_index_items()
        }
    assert f"js/plugins/TestPlugin.js/{selector}" in items


@pytest.mark.asyncio
async def test_rebuild_text_index_reads_only_plugin_source_rule_files(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """有插件源码规则时，冷重建不能读取无关插件源码文件正文。"""
    source = "\n".join(
        [
            "(() => {",
            "  const message = '規則対象本文';",
            "})();",
        ]
    )
    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    _ = (plugin_source_dir / "TestPlugin.js").write_text(source, encoding="utf-8", newline="\n")
    for index in range(300):
        _ = (plugin_source_dir / f"Unused{index:03}.js").write_bytes(b"\xff\xfe\x00\x00")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    await _install_minimal_workflow_gate_prerequisites(
        registry=registry,
        game_title=record.game_title,
        game_dir=minimal_game_dir,
    )

    origin_plugin_source_dir = minimal_game_dir / "js" / "plugins_source_origin"
    _ = origin_plugin_source_dir.mkdir(exist_ok=True)
    _ = (origin_plugin_source_dir / "TestPlugin.js").write_text(source, encoding="utf-8", newline="\n")
    source_for_rules = source
    text_rules = TextRules.from_setting(load_setting(EXAMPLE_SETTING_PATH, source_language="ja").text_rules)
    native_scan = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files={"TestPlugin.js": source_for_rules},
            enabled_plugin_files={"TestPlugin.js"},
            text_rules=text_rules,
        )
    )
    candidate = next(
        ensure_json_object(item, "plugin_source_candidate")
        for item in native_scan.candidates
        if ensure_json_object(item, "plugin_source_candidate")["original_text"] == "規則対象本文"
    )
    selector = candidate["selector"]
    assert isinstance(selector, str)

    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="TestPlugin.js",
                    file_hash=build_plugin_source_file_hash(source_for_rules),
                    selectors=[selector],
                    excluded_selectors=[],
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "ok", report.errors[0].message if report.errors else report
    async with await registry.open_game(record.game_title) as session:
        items = {
            item.location_path: item
            for item in await session.read_text_index_items()
        }
    assert f"js/plugins/TestPlugin.js/{selector}" in items


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_mode", ["file_missing", "selector_missing"])
async def test_rebuild_text_index_rejects_stale_plugin_source_rules_in_rust_path(
    minimal_game_dir: Path,
    tmp_path: Path,
    stale_mode: str,
) -> None:
    """Rust 冷重建遇到过期插件源码规则时返回稳定业务错误码。"""
    source = "\n".join(
        [
            "(() => {",
            "  const message = '古いプラグイン本文';",
            "})();",
        ]
    )
    plugin_source_path = minimal_game_dir / "js" / "plugins" / "TestPlugin.js"
    _ = plugin_source_path.write_text(source, encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    source_for_rules_path = minimal_game_dir / "js" / "plugins_source_origin" / "TestPlugin.js"
    source_for_rules = source_for_rules_path.read_bytes().decode("utf-8")
    text_rules = TextRules.from_setting(load_setting(EXAMPLE_SETTING_PATH, source_language="ja").text_rules)
    native_scan = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files={"TestPlugin.js": source_for_rules},
            enabled_plugin_files={"TestPlugin.js"},
            text_rules=text_rules,
        )
    )
    candidate = next(
        ensure_json_object(item, "plugin_source_candidate")
        for item in native_scan.candidates
        if ensure_json_object(item, "plugin_source_candidate")["original_text"] == "古いプラグイン本文"
    )
    selector = candidate["selector"]
    assert isinstance(selector, str)

    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="TestPlugin.js",
                    file_hash=build_plugin_source_file_hash(source_for_rules),
                    selectors=[
                        f"{selector}-missing"
                        if stale_mode == "selector_missing"
                        else selector
                    ],
                    excluded_selectors=[],
                )
            ]
        )
    if stale_mode == "file_missing":
        source_for_rules_path.unlink()

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "error"
    assert [error.code for error in report.errors] == ["stale_plugin_source_rules"]
    assert "重新导出并导入" in report.errors[0].message


@pytest.mark.asyncio
async def test_rebuild_text_index_rejects_incomplete_plugin_source_review_for_referenced_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """已导入插件源码规则必须覆盖同一引用文件内的当前候选。"""
    source = "\n".join(
        [
            "(() => {",
            "  const first = '已归类插件本文';",
            "  const second = '未归类插件本文';",
            "})();",
        ]
    )
    plugin_source_path = minimal_game_dir / "js" / "plugins" / "TestPlugin.js"
    _ = plugin_source_path.write_text(source, encoding="utf-8", newline="\n")
    source_for_rules = plugin_source_path.read_text(encoding="utf-8")
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    text_rules = TextRules.from_setting(load_setting(EXAMPLE_SETTING_PATH, source_language="ja").text_rules)
    native_scan = scan_native_rule_candidates(
        build_native_plugin_source_candidates_payload(
            plugin_source_files={"TestPlugin.js": source_for_rules},
            enabled_plugin_files={"TestPlugin.js"},
            text_rules=text_rules,
        )
    )
    first_candidate = next(
        ensure_json_object(item, "plugin_source_candidate")
        for item in native_scan.candidates
        if ensure_json_object(item, "plugin_source_candidate")["original_text"] == "已归类插件本文"
    )
    selector = first_candidate["selector"]
    assert isinstance(selector, str)

    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="TestPlugin.js",
                    file_hash=build_plugin_source_file_hash(source_for_rules),
                    selectors=[selector],
                    excluded_selectors=[],
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "error"
    assert [error.code for error in report.errors] == ["plugin_source_review_incomplete"]
    assert "补全插件源码规则" in report.errors[0].message


@pytest.mark.asyncio
async def test_rebuild_text_index_rejects_stale_nonstandard_data_rules_in_rust_path(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷重建遇到过期非标准 data 规则时返回稳定业务错误码。"""
    recipes_path = minimal_game_dir / "data" / "PluginCache.json"
    recipes_raw = json.dumps([{"name": "古い本文"}], ensure_ascii=False)
    _ = recipes_path.write_text(recipes_raw, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_nonstandard_data_text_rules(
            [
                NonstandardDataTextRuleRecord(
                    file_name="PluginCache.json",
                    file_hash="stale-hash",
                    path_templates=["$[*]['name']"],
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "error"
    assert [error.code for error in report.errors] == ["stale_nonstandard_data_rules"]
    assert "重新导出并导入" in report.errors[0].message


@pytest.mark.asyncio
async def test_rebuild_text_index_rejects_incomplete_nonstandard_data_review_for_referenced_file(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """已导入非标准 data 规则必须覆盖同一引用文件内的当前候选。"""
    recipes_path = minimal_game_dir / "data" / "PluginCache.json"
    recipes_raw = json.dumps(
        [{"name": "已归类非标准本文", "desc": "未归类非标准本文"}],
        ensure_ascii=False,
    )
    _ = recipes_path.write_text(recipes_raw, encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_nonstandard_data_text_rules(
            [
                NonstandardDataTextRuleRecord(
                    file_name="PluginCache.json",
                    file_hash=build_nonstandard_data_file_hash(recipes_raw),
                    path_templates=["$[0]['name']"],
                )
            ]
        )

    report = await AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    ).rebuild_text_index(game_title=record.game_title)

    assert report.status == "error"
    assert [error.code for error in report.errors] == ["nonstandard_data_review_incomplete"]
    assert "补全非标准 data 规则" in report.errors[0].message


@pytest.mark.asyncio
async def test_external_rule_gate_rejects_missing_current_scope_hash_even_with_old_confirmation(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """metadata 缺少当前 scope hash 时不能复用旧空规则确认。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        await session.replace_rule_review_state(
            rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
            scope_hash="legacy-confirmed-scope",
            reviewed_empty=True,
        )
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        errors = await collect_text_index_external_rule_gate_errors(
            session=session,
            metadata=replace(metadata, workflow_gate_scope_hashes={}),
        )

    assert "text_index_gate_scope_hash_missing" in {error.code for error in errors}


@pytest.mark.asyncio
async def test_evaluate_text_index_scope_gate_reads_quality_error_paths_from_index_fast_path(
    minimal_english_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rust scope gate 的质量错误输入只读取当前索引内路径，不加载完整错误对象。"""

    async def forbidden_quality_error_records(*args: object, **kwargs: object) -> NoReturn:
        """scope gate 不应读取完整质量错误对象。"""
        _ = (args, kwargs)
        raise AssertionError("evaluate_text_index_scope_gate 应使用 text index 质量错误路径快路径")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )
    report = await service.rebuild_text_index(game_title=record.game_title)
    assert report.status == "ok"

    async with await registry.open_game(record.game_title) as session:
        index_items = await session.read_text_index_items()
        indexed_error_path = index_items[0].location_path
        async with session.connection.execute(
            "SELECT fact_id FROM text_facts_v2 WHERE location_path = ? ORDER BY fact_id LIMIT 1",
            (indexed_error_path,),
        ) as cursor:
            indexed_error_fact_row = await cursor.fetchone()
        assert indexed_error_fact_row is not None
        run_record = await session.start_translation_run(
            total_extracted=len(index_items),
            pending_count=len(index_items),
            deduplicated_count=1,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id=cast(str, indexed_error_fact_row["fact_id"]),
                    location_path=indexed_error_path,
                    item_type="long_text",
                    role=None,
                    original_lines=["Hello"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析"],
                    model_response="模型原始返回",
                ),
                TranslationErrorItem(
                    fact_id="fact-outside-quality-error",
                    location_path="Outside.json/not-in-index",
                    item_type="long_text",
                    role=None,
                    original_lines=["Outside"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["索引外错误"],
                    model_response="索引外模型返回",
                ),
            ],
        )
        monkeypatch.setattr(
            "app.persistence.run_records.RunRecordSessionMixin.read_translation_quality_errors",
            forbidden_quality_error_records,
        )

        result = await evaluate_text_index_scope_gate(session=session, records=index_items)

    assert result.quality_error_count == 1
    assert result.quality_gate["status"] == "error"


@pytest.mark.asyncio
async def test_quality_report_rebuilds_text_index_with_command_setting_overrides(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量报告自动重建索引时必须应用本次命令传入的 setting overrides。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    service = AgentToolkitService(game_registry=registry, setting_path=EXAMPLE_SETTING_PATH)
    overrides = SettingOverrides(source_residual_allowed_chars=["カ"])

    report = await service.quality_report(
        game_title="テストゲーム",
        setting_overrides=overrides,
    )

    assert report.summary["text_index_status"] == "cold_rebuilt"
    async with await registry.open_game("テストゲーム") as session:
        metadata = await session.read_text_index_metadata()
        setting = load_setting(
            EXAMPLE_SETTING_PATH,
            overrides=overrides,
            source_language=session.source_language,
        )
        expected_fingerprint = await collect_text_index_rules_fingerprint(
            session=session,
            text_rules=TextRules.from_setting(setting.text_rules),
        )
    assert metadata is not None
    assert metadata.rules_fingerprint == expected_fingerprint


@pytest.mark.asyncio
async def test_plugin_source_rule_file_hash_does_not_change_text_index_rules_fingerprint(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """插件源码规则 file_hash 是诊断信息，不应单独让文本索引规则指纹过期。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    text_rules = TextRules.from_setting(load_setting(EXAMPLE_SETTING_PATH, source_language="ja").text_rules)

    async with await registry.open_game("テストゲーム") as session:
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="HashOnly.js",
                    file_hash="hash-a",
                    selectors=["ast:string:1:2:aaa"],
                    excluded_selectors=["ast:string:3:4:bbb"],
                )
            ]
        )
        first = await collect_text_index_rules_fingerprint(session=session, text_rules=text_rules)
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="HashOnly.js",
                    file_hash="hash-b",
                    selectors=["ast:string:1:2:aaa"],
                    excluded_selectors=["ast:string:3:4:bbb"],
                )
            ]
        )
        second = await collect_text_index_rules_fingerprint(session=session, text_rules=text_rules)
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="HashOnly.js",
                    file_hash="hash-b",
                    selectors=["ast:string:1:2:changed"],
                    excluded_selectors=["ast:string:3:4:bbb"],
                )
            ]
        )
        changed_selector = await collect_text_index_rules_fingerprint(session=session, text_rules=text_rules)

    assert second == first
    assert changed_selector != first


def test_text_index_source_branch_precheck_rejects_legacy_v1_gate_hashes() -> None:
    """旧 passed_v1 scope hash 不能继续代表当前索引源分支已预检。"""
    legacy_metadata = TextIndexMetadata(
        source_snapshot_fingerprint="snapshot",
        rules_fingerprint="rules",
        item_count=0,
        created_at="2026-06-08T00:00:00",
        workflow_gate_scope_hashes={
            TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY: "passed_v1",
            TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY: "passed_v1",
        },
    )
    current_metadata = replace(
        legacy_metadata,
        workflow_gate_scope_hashes={
            TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY: TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE,
            TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY: TEXT_INDEX_WORKFLOW_GATE_PRECHECK_VALUE,
        },
    )

    assert not text_index_source_branch_gates_prechecked(legacy_metadata)
    assert text_index_source_branch_gates_prechecked(current_metadata)


@pytest.mark.asyncio
async def test_read_text_index_metadata_rejects_legacy_v1_gate_hashes(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """旧 workflow gate 元数据必须显式要求重建当前文本范围索引。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    async with await registry.open_game(record.game_title) as session:
        await session.replace_text_index(
            metadata=TextIndexMetadata(
                source_snapshot_fingerprint="snapshot",
                rules_fingerprint="rules",
                item_count=0,
                created_at="2026-06-08T00:00:00",
                workflow_gate_scope_hashes={
                    TEXT_INDEX_PLUGIN_SOURCE_GATE_PRECHECK_KEY: "passed_v1",
                    TEXT_INDEX_NONSTANDARD_DATA_GATE_PRECHECK_KEY: "passed_v1",
                },
            ),
            items=[],
        )

        with pytest.raises(RuntimeError) as error_info:
            _ = await session.read_text_index_metadata()

        message = str(error_info.value)
        assert "rebuild-text-index / workflow gate" in message
        assert "passed_v1" in message
        assert "请运行 rebuild-text-index" in message
