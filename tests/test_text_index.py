"""持久文本范围索引测试。"""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from app.agent_toolkit import AgentToolkitService
from app.config.schemas import TextRulesSetting
from app.persistence import GameRegistry
from app.rmmz.game_file_view import GameFileView
from app.rmmz.loader import load_game_data_for_view
from app.rmmz.schema import PlaceholderRuleRecord
from app.rmmz.text_rules import TextRules, coerce_json_value, ensure_json_object
from app.text_index import detect_text_index_invalidations, rebuild_text_index
from app.text_scope import TextScopeService
from app.utils.config_loader_utils import load_setting

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SETTING_PATH = ROOT / "setting.example.toml"


def build_english_text_rules() -> TextRules:
    """构造测试用英文文本规则。"""
    return TextRules.from_setting(
        TextRulesSetting(
            source_language="en",
            source_residual_label="英文",
            source_text_required_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
            source_text_exclusion_profile="english_protocol_noise",
            source_residual_segment_pattern=r"[A-Za-z][A-Za-z0-9'’_-]*",
            source_residual_detection_profile="english_source_copy",
        )
    )


@pytest.mark.asyncio
async def test_rebuild_text_index_persists_current_text_scope(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """重建文本范围索引会保存当前 scope 的 active items。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")

    async with await registry.open_game(record.game_title) as session:
        text_rules = build_english_text_rules()
        game_data = await load_game_data_for_view(
            session.game_path,
            source_view=GameFileView.TRANSLATION_SOURCE,
        )
        scope = await TextScopeService().build(
            session=session,
            game_data=game_data,
            text_rules=text_rules,
        )

        missing_invalidations = await detect_text_index_invalidations(
            session=session,
            text_rules=text_rules,
        )
        assert [item.reason_key for item in missing_invalidations] == ["text_index_missing"]

        metadata = await rebuild_text_index(
            session=session,
            game_data=game_data,
            setting=load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language),
            text_rules=text_rules,
            scope=scope,
        )

        active_items = scope.active_items()
        index_items = await session.read_text_index_items()
        assert await session.read_text_index_metadata() == metadata
        assert metadata.item_count == len(active_items)
        assert index_items
        assert {item.location_path for item in index_items} == {
            item.location_path for item in active_items
        }
        assert all(len(item.source_snapshot_fingerprint) == 64 for item in index_items)
        assert all(len(item.rules_fingerprint) == 64 for item in index_items)
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

    async with await registry.open_game(record.game_title) as session:
        text_rules = build_english_text_rules()
        game_data = await load_game_data_for_view(
            session.game_path,
            source_view=GameFileView.TRANSLATION_SOURCE,
        )
        metadata = await rebuild_text_index(
            session=session,
            game_data=game_data,
            setting=load_setting(EXAMPLE_SETTING_PATH, source_language=session.source_language),
            text_rules=text_rules,
        )
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
async def test_agent_service_rebuild_text_index_writes_database_index(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Agent 服务重建文本范围索引后，数据库可读取同一份元信息。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_english_game_dir, source_language="en")
    service = AgentToolkitService(
        game_registry=registry,
        setting_path=EXAMPLE_SETTING_PATH,
    )

    report = await service.rebuild_text_index(game_title=record.game_title)

    assert report.status == "ok"
    indexed_count = report.summary["indexed_count"]
    assert isinstance(indexed_count, int)
    assert indexed_count > 0
    assert report.summary["index_item_count"] == indexed_count
    elapsed_ms = report.summary["elapsed_ms"]
    assert isinstance(elapsed_ms, int)
    assert elapsed_ms >= 0
    native_threads = report.summary["native_thread_count"]
    assert isinstance(native_threads, int)
    assert native_threads > 0
    stage_timings = ensure_json_object(report.summary["stage_timings"], "stage_timings")
    assert set(stage_timings) == {
        "load_config_and_rules",
        "load_translation_source",
        "build_text_scope",
        "write_text_index",
    }
    assert all(isinstance(value, int) and value >= 0 for value in stage_timings.values())
    async with await registry.open_game(record.game_title) as session:
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        assert metadata.item_count == indexed_count
        assert len(await session.read_text_index_items()) == indexed_count
