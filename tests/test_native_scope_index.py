"""Rust Scope/Index Engine 原生入口契约测试。"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

from app import native_scope_index
from app.native_scope_index import (
    build_native_placeholder_candidates_payload,
    build_native_rule_candidate_text_rules_payload,
    build_native_scope_index,
    inspect_native_scope_index_storage,
    native_schema_fingerprint,
    rebuild_native_scope_index_storage,
    scan_native_rule_candidates,
    write_native_scope_index_storage,
)
from app.persistence import GameRegistry
from app.persistence.sql import TEXT_FACT_SCHEMA_VERSION, current_schema_fingerprint
from app.config.schemas import TextRulesSetting
from app.nonstandard_data.scanner import build_nonstandard_data_file_hash
from app.plugin_source_text.scanner import (
    build_plugin_source_file_hash,
    iter_plugin_source_string_literals,
)
from app.plugin_text import build_plugin_hash
from app.rmmz.control_codes import CustomPlaceholderRule, StructuredPlaceholderRule
from app.rmmz.game_data import System, Terms
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    FIXED_FILE_NAMES,
    GameData,
    GameLayout,
    MvVirtualNameboxRuleRecord,
    NonstandardDataTextRuleRecord,
    NoteTagTextRuleRecord,
    PluginTextRuleRecord,
    PluginSourceTextRuleRecord,
    TranslationData,
    TranslationItem,
)
from app.rmmz.text_rules import (
    JsonArray,
    JsonObject,
    JsonValue,
    coerce_json_value,
    ensure_json_array,
    ensure_json_object,
)
from app.rmmz.text_rules import TextRules


def _json_int(value: JsonValue, label: str) -> int:
    """测试中把 JSON 值显式收窄为非 bool 整数。"""
    if not isinstance(value, int) or isinstance(value, bool):
        raise AssertionError(f"{label} 必须是整数")
    return value


def _sqlite_row_str(row: sqlite3.Row, column_name: str) -> str:
    """测试中把 sqlite Row 字段显式收窄为字符串。"""
    value = cast(object, row[column_name])
    if not isinstance(value, str):
        raise AssertionError(f"{column_name} 必须是字符串")
    return value


def _read_test_json_from_plugins_js(plugins_path: Path) -> JsonValue:
    """测试中读取 `plugins.js` 的 `$plugins` 数组。"""
    text = plugins_path.read_text(encoding="utf-8")
    prefix = "var $plugins = "
    if not text.startswith(prefix):
        raise AssertionError("plugins.js fixture 必须以 var $plugins = 开头")
    return coerce_json_value(cast(object, json.loads(text[len(prefix) :].rstrip(";\n"))))


def _payload_without_core_fields(row: sqlite3.Row) -> JsonObject:
    """读取 domain payload，并断言它没有重复 v2 fact 核心字段。"""
    payload_text = _sqlite_row_str(row, "payload_json")
    payload = ensure_json_object(
        coerce_json_value(cast(object, json.loads(payload_text))),
        "payload_json",
    )
    forbidden_fields = {
        "raw_text",
        "visible_text",
        "translatable_text",
        "raw_hash",
        "visible_hash",
        "translatable_hash",
        "selector",
        "source_file",
        "role",
    }
    duplicated = forbidden_fields.intersection(payload)
    if duplicated:
        raise AssertionError(f"domain payload 不得重复核心字段: {sorted(duplicated)}")
    return payload


def _single_row_by_domain(rows: list[sqlite3.Row], domain: str) -> sqlite3.Row:
    """测试中按 domain 取唯一行。"""
    matched = [row for row in rows if _sqlite_row_str(row, "domain") == domain]
    if len(matched) != 1:
        raise AssertionError(f"{domain} 应只有一条目标测试行，实际 {len(matched)} 条")
    return matched[0]


def _single_row_by_text(rows: list[sqlite3.Row], domain: str, text: str) -> sqlite3.Row:
    """测试中按 domain 和 translatable_text 取唯一行。"""
    matched = [
        row
        for row in rows
        if _sqlite_row_str(row, "domain") == domain
        and _sqlite_row_str(row, "translatable_text") == text
    ]
    if len(matched) != 1:
        raise AssertionError(f"{domain}/{text} 应只有一条目标测试行，实际 {len(matched)} 条")
    return matched[0]


def _rebuild_rule_candidate_text_rules(setting: TextRulesSetting) -> JsonObject:
    """生成 Rust rebuild 当前必需的规则候选文本规则载荷。"""
    text_rules = TextRules.from_setting(setting)
    payload = build_native_rule_candidate_text_rules_payload(text_rules)
    payload["source_text_required_pattern"] = setting.source_text_required_pattern
    return payload


def _scope_entries_payload() -> list[JsonObject]:
    """构造最小 Scope/Index 输入条目。"""
    return [
        {
            "location_path": "Map001.json/events/1/pages/0/list/0",
            "item_type": "long_text",
            "role": "Alice",
            "original_lines": ["Hello there"],
            "source_line_paths": ["Map001.json/events/1/pages/0/list/1"],
            "source_type": "event_command",
            "source_file": "Map001.json",
            "rule_source": "event_command.default",
            "enters_translation": True,
            "can_write_back": True,
            "cannot_process_reason": "",
            "locator": {"kind": "event_command", "code": 401},
        },
        {
            "location_path": "System.json/gameTitle",
            "item_type": "short_text",
            "role": None,
            "original_lines": ["Fixture Game"],
            "source_line_paths": [],
            "source_type": "standard_data",
            "source_file": "System.json",
            "rule_source": "standard_data",
            "enters_translation": True,
            "can_write_back": False,
            "cannot_process_reason": "缺少可写回定位",
            "locator": {"kind": "field", "field": "gameTitle"},
        },
        {
            "location_path": "System.json/locale",
            "item_type": "short_text",
            "role": None,
            "original_lines": ["en_US"],
            "source_line_paths": [],
            "source_type": "standard_data",
            "source_file": "System.json",
            "rule_source": "standard_data",
            "enters_translation": False,
            "can_write_back": False,
            "cannot_process_reason": "不需要翻译",
            "locator": {"kind": "field", "field": "locale"},
        },
    ]


def _plugin_source_text_rules_payload() -> JsonObject:
    """构造插件源码候选扫描用最小提取规则。"""
    return {
        "custom_placeholder_rules": [],
        "structured_placeholder_rules": [],
        "strip_wrapping_punctuation_pairs": [["「", "」"]],
        "source_text_required_pattern": r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]+",
        "source_text_exclusion_profile": "none",
    }


def _note_tag_game_data() -> GameData:
    """构造带 Note 标签的最小标准 data。"""
    data: dict[str, JsonValue] = {file_name: cast(JsonValue, []) for file_name in FIXED_FILE_NAMES}
    data["Items.json"] = cast(JsonValue, [
        None,
        {
            "id": 1,
            "name": "Potion",
            "note": '<desc:回復薬>\n<upgrade:10>\n<quoted:"薬袋">\n<desc:重複>\n<empty>',
        },
    ])
    data["Map001.json"] = cast(JsonValue, {
        "events": {
            "1": {
                "name": "Chest",
                "note": "<desc:宝箱>\n<memo:ABC>",
            }
        }
    })
    data["System.json"] = cast(JsonValue, {"gameTitle": "Fixture"})
    layout = GameLayout(
        game_root=Path("."),
        content_root=Path("."),
        data_dir=Path("data"),
        data_origin_dir=Path("data_origin"),
        js_dir=Path("js"),
        plugins_path=Path("js/plugins.js"),
        plugins_origin_path=Path("js/plugins_origin.js"),
        plugin_source_origin_dir=Path("plugins_source_origin"),
        package_path=Path("package.json"),
        engine_kind="mz",
        engine_version="1.8.0",
        is_www_layout=False,
    )
    system = System(
        gameTitle="Fixture",
        terms=Terms(basic=[], commands=[], params=[], messages={}),
        elements=[],
        skillTypes=[],
        weaponTypes=[],
        armorTypes=[],
        equipTypes=[],
    )
    return GameData(
        layout=layout,
        data=data,
        writable_data=data,
        map_data={},
        system=system,
        common_events=[],
        troops=[],
        base_data={},
        plugins_js=[],
        writable_plugins_js=[],
        plugin_source_files={},
        plugin_source_read_errors={},
        writable_plugin_source_files={},
    )


def test_build_native_scope_index_returns_rows_and_summaries() -> None:
    """build_scope_index 返回 text index rows、范围摘要和规则命中摘要。"""
    result = build_native_scope_index(
        cast(
            JsonObject,
            {
                "source_snapshot_fingerprint": "snapshot-v1",
                "rules_fingerprint": "rules-v1",
                "entries": _scope_entries_payload(),
                "rule_hits": [
                    {
                        "domain": "event_command",
                        "rule_key": "401",
                        "location_path": "Map001.json/events/1/pages/0/list/0",
                        "extractable": True,
                        "writable": True,
                    },
                    {
                        "domain": "standard_data",
                        "rule_key": "gameTitle",
                        "location_path": "System.json/gameTitle",
                        "extractable": True,
                        "writable": False,
                    },
                ],
                "candidate_groups": [
                    {"domain": "event_command", "candidate_count": 1},
                    {"domain": "standard_data", "candidate_count": 2},
                ],
                "stale_rule_details": [
                    {"domain": "standard_data", "rule_key": "old-title", "reason": "规则已过期"}
                ],
            },
        )
    )

    assert result.scope_summary["total_count"] == 3
    assert result.scope_summary["active_count"] == 2
    assert result.scope_summary["writable_count"] == 1
    assert result.scope_summary["unwritable_count"] == 1
    assert result.scope_summary["stale_rule_count"] == 1
    assert result.writable_location_paths == ["Map001.json/events/1/pages/0/list/0"]
    assert result.unwritable_reasons == [
        {
            "location_path": "System.json/gameTitle",
            "reason": "缺少可写回定位",
        }
    ]

    first_row = result.text_index_rows[0]
    assert first_row["source_snapshot_fingerprint"] == "snapshot-v1"
    assert first_row["rules_fingerprint"] == "rules-v1"
    assert first_row["writable"] is True
    assert json.loads(str(first_row["locator_json"])) == {"kind": "event_command", "code": 401}

    domain_summary = {
        str(item["domain"]): item
        for item in result.domain_summary
    }
    assert domain_summary["event_command"]["item_count"] == 1
    assert domain_summary["standard_data"]["item_count"] == 2
    assert domain_summary["standard_data"]["unwritable_count"] == 1

    rule_hit_summary = {
        (str(item["domain"]), str(item["rule_key"])): item
        for item in result.rule_hit_summary
    }
    assert rule_hit_summary[("standard_data", "gameTitle")]["hit_count"] == 1
    assert rule_hit_summary[("standard_data", "gameTitle")]["unwritable_count"] == 1
    assert result.candidate_summary == [
        {"domain": "event_command", "candidate_count": 1},
        {"domain": "standard_data", "candidate_count": 2},
    ]


def test_build_native_scope_index_scans_standard_data_and_event_commands() -> None:
    """build_scope_index 可直接扫描结构化游戏 data，产出稳定 text index rows。"""
    result = build_native_scope_index(
        cast(
            JsonObject,
            {
                "source_snapshot_fingerprint": "snapshot-v2",
                "rules_fingerprint": "rules-v2",
                "data_files": [
                    {
                        "file_name": "System.json",
                        "data": {
                            "gameTitle": "Fixture Game",
                            "locale": "en_US",
                        },
                    },
                    {
                        "file_name": "Map001.json",
                        "data": {
                            "events": [
                                None,
                                {
                                    "pages": [
                                        {
                                            "list": [
                                                {
                                                    "code": 401,
                                                    "parameters": ["Hello there"],
                                                },
                                                {
                                                    "code": 0,
                                                    "parameters": [],
                                                },
                                            ]
                                        }
                                    ]
                                },
                            ]
                        },
                    },
                ],
            },
        )
    )

    rows_by_path = {
        str(row["location_path"]): row
        for row in result.text_index_rows
    }
    assert set(rows_by_path) == {
        "Map001.json/events/1/pages/0/list/0/parameters/0",
        "System.json/gameTitle",
    }
    assert rows_by_path["System.json/gameTitle"]["source_type"] == "standard_data"
    assert rows_by_path["System.json/gameTitle"]["item_type"] == "short_text"
    assert rows_by_path["System.json/gameTitle"]["original_lines"] == ["Fixture Game"]
    assert json.loads(str(rows_by_path["System.json/gameTitle"]["locator_json"])) == {
        "kind": "standard_data",
        "path": ["gameTitle"],
    }

    event_row = rows_by_path["Map001.json/events/1/pages/0/list/0/parameters/0"]
    assert event_row["source_type"] == "event_command"
    assert event_row["item_type"] == "long_text"
    assert event_row["source_line_paths"] == [
        "Map001.json/events/1/pages/0/list/0/parameters/0"
    ]
    assert json.loads(str(event_row["locator_json"])) == {
        "code": 401,
        "kind": "event_command",
        "parameters_index": 0,
    }

    assert result.scope_summary["total_count"] == 2
    assert result.scope_summary["active_count"] == 2
    assert result.scope_summary["writable_count"] == 2
    assert result.writable_location_paths == [
        "Map001.json/events/1/pages/0/list/0/parameters/0",
        "System.json/gameTitle",
    ]
    domain_summary = {
        str(item["domain"]): item
        for item in result.domain_summary
    }
    assert domain_summary["event_command"]["item_count"] == 1
    assert domain_summary["standard_data"]["item_count"] == 1


def test_native_schema_fingerprint_matches_python_shared_schema() -> None:
    """Rust 编译期 schema 与 Python 建库 schema 必须来自同一 SQL 资源。"""
    assert native_schema_fingerprint() == current_schema_fingerprint()


@pytest.mark.asyncio
async def test_inspect_native_scope_index_storage_reads_db_and_game_files(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 能直接打开目标 DB，并读取标准 data、plugins.js、插件源码和非标准 data。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash="hash",
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.write_translation_items(
            [
                TranslationItem(
                    location_path="System.json/gameTitle",
                    item_type="short_text",
                    role=None,
                    original_lines=["テストゲーム"],
                    source_line_paths=[],
                    translation_lines=["测试游戏"],
                )
            ]
        )

    result = inspect_native_scope_index_storage(
        {
            "db_path": str(record.db_path),
            "game_path": str(minimal_game_dir),
        }
    )

    assert result["status"] == "ok"
    schema = ensure_json_object(result["schema"], "storage.schema")
    assert schema["schema_fingerprint"] == current_schema_fingerprint()
    database = ensure_json_object(result["database"], "storage.database")
    assert database["plugin_text_rule_count"] == 1
    assert database["translation_item_count"] == 1
    game_files = ensure_json_object(result["game_files"], "storage.game_files")
    assert "System.json" in ensure_json_array(
        game_files["standard_data_file_names"],
        "storage.game_files.standard_data_file_names",
    )
    assert "UnknownPluginData.json" in ensure_json_array(
        game_files["nonstandard_data_file_names"],
        "storage.game_files.nonstandard_data_file_names",
    )
    plugins_js_bytes = game_files["plugins_js_bytes"]
    plugin_source_file_count = game_files["plugin_source_file_count"]
    assert isinstance(plugins_js_bytes, int)
    assert isinstance(plugin_source_file_count, int)
    assert plugins_js_bytes > 0
    assert plugin_source_file_count >= 2


@pytest.mark.asyncio
async def test_write_native_scope_index_storage_writes_python_readable_index(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 直接写入 text index/summary 后，Python 持久层必须能读回。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    result = write_native_scope_index_storage(
        {
            "db_path": str(record.db_path),
            "metadata": {
                "source_snapshot_fingerprint": "snapshot-v1",
                "rules_fingerprint": "rules-v1",
                "item_count": 1,
                "workflow_gate_scope_hashes": {"plugin_text_rules": "scope-hash-v1"},
                "created_at": "2026-06-05T00:00:00",
            },
            "text_index_rows": [
                {
                    "location_path": "System.json/gameTitle",
                    "item_type": "short_text",
                    "role": None,
                    "original_lines": ["テストゲーム"],
                    "source_line_paths": [],
                    "source_type": "standard_data",
                    "source_file": "System.json",
                    "writable": True,
                    "source_snapshot_fingerprint": "snapshot-v1",
                    "rules_fingerprint": "rules-v1",
                    "locator_json": json.dumps({"kind": "standard_data"}, ensure_ascii=False),
                }
            ],
            "scope_summary": {
                "total_count": 1,
                "active_count": 1,
                "writable_count": 1,
                "unwritable_count": 0,
                "stale_rule_count": 0,
                "native_thread_count": 4,
            },
            "domain_summary": [
                {
                    "domain": "standard_data",
                    "item_count": 1,
                    "active_count": 1,
                    "writable_count": 1,
                    "unwritable_count": 0,
                    "inactive_rule_hit_count": 0,
                }
            ],
            "rule_hit_summary": [
                {
                    "domain": "standard_data",
                    "rule_key": "gameTitle",
                    "hit_count": 1,
                    "extractable_count": 1,
                    "writable_count": 1,
                    "unwritable_count": 0,
                }
            ],
        }
    )

    assert result["status"] == "ok"
    assert result["written_item_count"] == 1
    assert result["text_fact_count"] == 0
    assert result["render_part_count"] == 0
    assert isinstance(result["scope_key"], str) and result["scope_key"]
    assert isinstance(result["scope_hash"], str) and len(result["scope_hash"]) == 64
    assert result["text_fact_schema_version"] == TEXT_FACT_SCHEMA_VERSION
    async with await registry.open_game(record.game_title) as session:
        metadata = await session.read_text_index_metadata()
        assert metadata is not None
        assert metadata.source_snapshot_fingerprint == "snapshot-v1"
        assert metadata.workflow_gate_scope_hashes == {"plugin_text_rules": "scope-hash-v1"}
        items = await session.read_text_index_items()
        assert [item.location_path for item in items] == ["System.json/gameTitle"]
        assert items[0].original_lines == ["テストゲーム"]
        scope_summary = await session.read_text_index_scope_summary()
        assert scope_summary is not None
        assert scope_summary.native_thread_count == 4
        assert [item.domain for item in await session.read_text_index_domain_summary()] == ["standard_data"]
        assert [item.rule_key for item in await session.read_text_index_rule_hit_summary()] == ["gameTitle"]


@pytest.mark.asyncio
async def test_rebuild_native_scope_index_storage_counts_stale_plugin_rules(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷重建必须继承旧范围服务的插件规则新鲜度语义。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
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

    setting = TextRulesSetting()
    result = rebuild_native_scope_index_storage(
        {
            "db_path": str(record.db_path),
            "game_path": str(minimal_game_dir),
            "source_snapshot_fingerprint": "snapshot-v1",
            "rules_fingerprint": "rules-v1",
            "source_language": "ja",
            "target_language": "zh-Hans",
            "engine_kind": "mz",
            "text_rules_setting": setting.model_dump(mode="json"),
            "rule_candidate_text_rules": _rebuild_rule_candidate_text_rules(setting),
            "event_command_scope_codes": [357],
            "source_text_required_pattern": setting.source_text_required_pattern,
            "created_at": "2026-06-05T00:00:00",
        }
    )

    assert result["status"] == "ok"
    assert _json_int(result["text_fact_count"], "text_fact_count") == _json_int(
        result["indexed_count"],
        "indexed_count",
    )
    assert _json_int(result["render_part_count"], "render_part_count") >= _json_int(
        result["text_fact_count"],
        "text_fact_count",
    )
    assert isinstance(result["scope_key"], str) and result["scope_key"]
    assert isinstance(result["scope_hash"], str) and len(result["scope_hash"]) == 64
    assert result["text_fact_schema_version"] == TEXT_FACT_SCHEMA_VERSION
    internal_timings = ensure_json_object(
        result["internal_stage_timings"],
        "native_scope_index_storage_rebuild.internal_stage_timings",
    )
    assert "scan_standard_data" in internal_timings
    assert "build_workflow_gate_metadata" in internal_timings
    assert "write_storage" in internal_timings
    assert all(isinstance(value, int) and value >= 0 for value in internal_timings.values())
    async with await registry.open_game(record.game_title) as session:
        scope_summary = await session.read_text_index_scope_summary()
        assert scope_summary is not None
        assert scope_summary.stale_rule_count == 1
        items = await session.read_text_index_items()
        assert all(not item.location_path.startswith("plugins.js/") for item in items)


@pytest.mark.asyncio
async def test_rebuild_native_scope_index_storage_writes_text_fact_v2_for_batch1_domains(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷重建同时写出 standard/event_command/MV 虚拟名字框 v2 facts。"""
    common_events_path = minimal_mv_game_dir / "www" / "data" / "CommonEvents.json"
    common_events = cast(list[object], json.loads(common_events_path.read_text(encoding="utf-8")))
    common_events.append(
        cast(
            object,
            {
                "id": 91,
                "list": [
                    {"code": 101, "parameters": [0, 0, 0, 2]},
                    {"code": 401, "parameters": [r"\n<Dan:> Hello"]},
                    {"code": 0, "parameters": []},
                ],
            },
        )
    )
    _ = common_events_path.write_text(json.dumps(common_events, ensure_ascii=False), encoding="utf-8")

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_mv_game_dir, source_language="en")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_mv_virtual_namebox_rules(
            [
                MvVirtualNameboxRuleRecord(
                    rule_order=0,
                    rule_name="yep-namebox-with-colon",
                    pattern_text=r"^\\n<(?P<speaker>[^:>\r\n]+):> (?P<body>.*)$",
                    speaker_group="speaker",
                    body_group="body",
                    speaker_policy="translate",
                    render_template=r"\n<{speaker}:> {body}",
                )
            ]
        )

    setting = TextRulesSetting(source_text_required_pattern=r".+")
    result = rebuild_native_scope_index_storage(
        {
            "db_path": str(record.db_path),
            "game_path": str(minimal_mv_game_dir),
            "source_snapshot_fingerprint": "snapshot-v1",
            "rules_fingerprint": "rules-v1",
            "source_language": "en",
            "target_language": "zh-Hans",
            "engine_kind": "mv",
            "text_rules_setting": setting.model_dump(mode="json"),
            "rule_candidate_text_rules": _rebuild_rule_candidate_text_rules(setting),
            "event_command_scope_codes": [101, 401],
            "source_text_required_pattern": setting.source_text_required_pattern,
            "created_at": "2026-06-05T00:00:00",
        }
    )

    assert result["status"] == "ok"
    assert result["index_status"] == "rebuilt"
    assert _json_int(result["text_fact_count"], "text_fact_count") == _json_int(
        result["indexed_count"],
        "indexed_count",
    )
    assert _json_int(result["render_part_count"], "render_part_count") >= _json_int(
        result["text_fact_count"],
        "text_fact_count",
    )
    assert result["source_snapshot_hash"] == "snapshot-v1"
    assert result["rule_hash"] == "rules-v1"
    assert isinstance(result["text_rules_hash"], str) and len(str(result["text_rules_hash"])) == 64
    assert isinstance(result["scope_key"], str) and str(result["scope_key"]).startswith("tfv2-scope:")
    assert isinstance(result["scope_hash"], str) and len(str(result["scope_hash"])) == 64
    assert result["text_fact_schema_version"] == TEXT_FACT_SCHEMA_VERSION
    assert _json_int(result["scan_file_count"], "scan_file_count") >= 1
    domain_fact_counts = ensure_json_object(
        result["domain_fact_counts"],
        "native_scope_index_storage_rebuild.domain_fact_counts",
    )
    assert _json_int(domain_fact_counts["standard_data"], "domain_fact_counts.standard_data") >= 1
    assert _json_int(domain_fact_counts["event_command"], "domain_fact_counts.event_command") >= 1
    assert _json_int(domain_fact_counts["mv_virtual_namebox"], "domain_fact_counts.mv_virtual_namebox") == 1

    with sqlite3.connect(record.db_path) as connection:
        connection.row_factory = sqlite3.Row
        mv_fact = cast(
            sqlite3.Row | None,
            connection.execute(
                """
                SELECT domain, raw_text, visible_text, translatable_text, role
                FROM text_facts_v2
                WHERE domain = 'mv_virtual_namebox'
                """
            ).fetchone(),
        )
        assert mv_fact is not None
        assert _sqlite_row_str(mv_fact, "raw_text") == r"\n<Dan:> Hello"
        assert _sqlite_row_str(mv_fact, "visible_text") == r"\n<Dan:> Hello"
        assert _sqlite_row_str(mv_fact, "translatable_text") == "Hello"
        assert _sqlite_row_str(mv_fact, "role") == "Dan"
        parts = cast(
            list[sqlite3.Row],
            connection.execute(
                """
                SELECT part_kind, raw_text, semantic_text, template_key
                FROM text_fact_render_parts_v2
                WHERE fact_id = (
                    SELECT fact_id FROM text_facts_v2 WHERE domain = 'mv_virtual_namebox'
                )
                ORDER BY part_order
                """
            ).fetchall(),
        )
        assert [_sqlite_row_str(part, "part_kind") for part in parts] == [
            "literal",
            "speaker",
            "literal",
            "translated_body",
        ]
        assert "".join(_sqlite_row_str(part, "raw_text") for part in parts) == r"\n<Dan:> Hello"
        assert [_sqlite_row_str(part, "raw_text") for part in parts] == [r"\n<", "Dan", ":> ", "Hello"]


@pytest.mark.asyncio
async def test_rebuild_native_scope_index_storage_writes_extended_domain_fact_payloads(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """Rust 冷重建为扩展 domain 写出核心正文、selector 和最小 payload。"""
    data_dir = minimal_game_dir / "data"
    items_path = data_dir / "Items.json"
    items = cast(list[object], json.loads(items_path.read_text(encoding="utf-8")))
    item = ensure_json_object(coerce_json_value(items[1]), "Items.json[1]")
    item["note"] = "<Flavor:生の薬草>"
    _ = items_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    raw_nonstandard = json.dumps(
        {"title": "外部タイトル", "ignored": "除外本文"},
        ensure_ascii=False,
    )
    _ = (data_dir / "UnknownPluginData.json").write_text(raw_nonstandard, encoding="utf-8")
    raw_skipped = json.dumps({"title": "跳过本文"}, ensure_ascii=False)
    _ = (data_dir / "SkippedPluginData.json").write_text(raw_skipped, encoding="utf-8")

    plugin_source_dir = minimal_game_dir / "js" / "plugins"
    plugin_source_dir.mkdir(exist_ok=True)
    plugin_source = "const Messages = { title: '源码\\\\n本文' };\n"
    _ = (plugin_source_dir / "TestPlugin.js").write_text(plugin_source, encoding="utf-8")
    plugin_literal = next(
        literal
        for literal in iter_plugin_source_string_literals(
            file_name="TestPlugin.js",
            source=plugin_source,
            active=True,
        )
        if literal.text == "源码\\n本文"
    )

    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        await session.replace_plugin_text_rules(
            [
                PluginTextRuleRecord(
                    plugin_index=0,
                    plugin_name="TestPlugin",
                    plugin_hash=build_plugin_hash(
                        ensure_json_object(
                            ensure_json_array(
                                _read_test_json_from_plugins_js(minimal_game_dir / "js" / "plugins.js"),
                                "plugins.js",
                            )[0],
                            "plugins.js[0]",
                        )
                    ),
                    path_templates=["$['parameters']['Message']"],
                )
            ]
        )
        await session.replace_event_command_text_rules(
            [
                EventCommandTextRuleRecord(
                    command_code=357,
                    parameter_filters=[],
                    path_templates=["$['parameters'][3]['message']"],
                )
            ]
        )
        await session.replace_note_tag_text_rules(
            [NoteTagTextRuleRecord(file_name="Items.json", tag_names=["Flavor"])]
        )
        await session.replace_nonstandard_data_text_rules(
            [
                NonstandardDataTextRuleRecord(
                    file_name="UnknownPluginData.json",
                    file_hash=build_nonstandard_data_file_hash(raw_nonstandard),
                    path_templates=["$['title']"],
                    excluded_path_templates=["$['ignored']"],
                    skipped=False,
                ),
                NonstandardDataTextRuleRecord(
                    file_name="SkippedPluginData.json",
                    file_hash=build_nonstandard_data_file_hash(raw_skipped),
                    path_templates=[],
                    excluded_path_templates=[],
                    skipped=True,
                ),
            ]
        )
        await session.replace_plugin_source_text_rules(
            [
                PluginSourceTextRuleRecord(
                    file_name="TestPlugin.js",
                    file_hash=build_plugin_source_file_hash(plugin_source),
                    selectors=[plugin_literal.selector],
                    excluded_selectors=[],
                )
            ]
        )

    setting = TextRulesSetting()
    result = rebuild_native_scope_index_storage(
        {
            "db_path": str(record.db_path),
            "game_path": str(minimal_game_dir),
            "source_snapshot_fingerprint": "snapshot-v1",
            "rules_fingerprint": "rules-v1",
            "source_language": "ja",
            "target_language": "zh-Hans",
            "engine_kind": "mz",
            "text_rules_setting": setting.model_dump(mode="json"),
            "rule_candidate_text_rules": _rebuild_rule_candidate_text_rules(setting),
            "event_command_scope_codes": [357],
            "source_text_required_pattern": setting.source_text_required_pattern,
            "created_at": "2026-06-05T00:00:00",
        }
    )

    assert result["status"] == "ok"
    with sqlite3.connect(record.db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = cast(
            list[sqlite3.Row],
            connection.execute(
                """
                SELECT facts.domain, facts.location_path, facts.source_file, facts.selector,
                       facts.raw_text, facts.visible_text, facts.translatable_text,
                       payloads.payload_json
                FROM text_facts_v2 AS facts
                LEFT JOIN text_fact_domain_payloads_v2 AS payloads
                    ON payloads.fact_id = facts.fact_id
                WHERE facts.domain IN (
                    'plugin_config',
                    'event_command',
                    'note_tag',
                    'nonstandard_data',
                    'plugin_source'
                )
                ORDER BY facts.domain, facts.location_path
                """
            ).fetchall(),
        )

    domains = {_sqlite_row_str(row, "domain") for row in rows}
    assert domains == {
        "plugin_config",
        "event_command",
        "note_tag",
        "nonstandard_data",
        "plugin_source",
    }

    plugin_config = _single_row_by_domain(rows, "plugin_config")
    assert _sqlite_row_str(plugin_config, "raw_text") == "プラグイン本文"
    assert _sqlite_row_str(plugin_config, "visible_text") == "プラグイン本文"
    plugin_config_payload = _payload_without_core_fields(plugin_config)
    assert plugin_config_payload == {"json_path": "$['parameters']['Message']"}

    event_command = _single_row_by_text(rows, "event_command", "プラグイン台詞")
    event_payload = _payload_without_core_fields(event_command)
    assert event_payload["command_code"] == 357
    assert event_payload["parameter_json_path"] == "$['parameters'][3]['message']"

    note_tag = _single_row_by_domain(rows, "note_tag")
    assert _sqlite_row_str(note_tag, "raw_text") == "生の薬草"
    note_payload = _payload_without_core_fields(note_tag)
    assert note_payload == {"tag_name": "Flavor"}

    nonstandard = _single_row_by_domain(rows, "nonstandard_data")
    nonstandard_payload = _payload_without_core_fields(nonstandard)
    assert nonstandard_payload == {"json_path": "$['title']"}
    assert _sqlite_row_str(nonstandard, "translatable_text") == "外部タイトル"
    assert "除外本文" not in {_sqlite_row_str(row, "raw_text") for row in rows}
    assert "跳过本文" not in {_sqlite_row_str(row, "raw_text") for row in rows}

    plugin_source_row = _single_row_by_domain(rows, "plugin_source")
    assert _sqlite_row_str(plugin_source_row, "selector") == plugin_literal.selector
    assert _sqlite_row_str(plugin_source_row, "raw_text") == r"源码\\n本文"
    assert _sqlite_row_str(plugin_source_row, "visible_text") == "源码\\n本文"
    plugin_source_payload = _payload_without_core_fields(plugin_source_row)
    assert plugin_source_payload["line"] == plugin_literal.line
    assert plugin_source_payload["start_index"] == plugin_literal.start_index
    assert plugin_source_payload["end_index"] == plugin_literal.end_index


def test_native_scope_index_storage_error_renders_chinese_summary(tmp_path: Path) -> None:
    """Rust storage 结构化错误必须由 Python adapter 渲染为中文摘要。"""
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute(
            "CREATE TABLE schema_version (schema_key TEXT PRIMARY KEY, version INTEGER NOT NULL)"
        )
        _ = connection.execute(
            "INSERT INTO schema_version (schema_key, version) VALUES ('current', 14)"
        )

    with pytest.raises(RuntimeError, match="scope_index_storage_schema_version_mismatch"):
        _ = inspect_native_scope_index_storage(
            {
                "db_path": str(db_path),
                "game_path": str(tmp_path),
            }
        )


def test_write_native_scope_index_storage_rejects_unsupported_text_fact_schema_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python native adapter 必须拒绝 Rust 返回的不支持 v2 fact schema。"""

    class FakeNativeScopeIndexModule:
        def write_scope_index_storage(self, payload_json: str) -> str:
            _ = payload_json
            return json.dumps(
                {
                    "status": "ok",
                    "written_item_count": 0,
                    "domain_summary_count": 0,
                    "rule_hit_summary_count": 0,
                    "text_fact_count": 0,
                    "render_part_count": 0,
                    "scope_key": "scope-v999",
                    "scope_hash": "0" * 64,
                    "text_fact_schema_version": TEXT_FACT_SCHEMA_VERSION + 1,
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        native_scope_index,
        "_load_native_scope_index_module",
        lambda: FakeNativeScopeIndexModule(),
    )

    with pytest.raises(RuntimeError, match="text fact v2 schema_version"):
        _ = write_native_scope_index_storage({})


def test_write_native_scope_index_storage_rejects_non_hex_scope_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python native adapter 必须拒绝非十六进制 scope_hash。"""

    class FakeNativeScopeIndexModule:
        def write_scope_index_storage(self, payload_json: str) -> str:
            _ = payload_json
            return json.dumps(
                {
                    "status": "ok",
                    "written_item_count": 0,
                    "domain_summary_count": 0,
                    "rule_hit_summary_count": 0,
                    "text_fact_count": 0,
                    "render_part_count": 0,
                    "scope_key": "scope-v2",
                    "scope_hash": "g" * 64,
                    "text_fact_schema_version": TEXT_FACT_SCHEMA_VERSION,
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        native_scope_index,
        "_load_native_scope_index_module",
        lambda: FakeNativeScopeIndexModule(),
    )

    with pytest.raises(TypeError, match="64 位 SHA-256 十六进制字符串"):
        _ = write_native_scope_index_storage({})


def test_build_native_event_command_candidates_payload_includes_data_codes_and_rules() -> None:
    """事件指令 Rust 候选载荷必须包含排序后的 data 文件、编码和可选规则。"""
    rules = cast(
        JsonArray,
        [
            {
                "command_code": 357,
                "parameter_filters": [{"index": 0, "value": "Speaker"}],
                "path_templates": ["$['parameters'][1]['message']"],
            }
        ],
    )

    payload = native_scope_index.build_native_event_command_candidates_payload(
        event_command_data_files={
            "Map002.json": {"events": []},
            "Map001.json": {"events": []},
        },
        command_codes=frozenset({401, 357}),
        rules=rules,
    )

    assert payload == {
        "event_command_data_files": [
            {"file_name": "Map001.json", "data": {"events": []}},
            {"file_name": "Map002.json", "data": {"events": []}},
        ],
        "event_command_codes": [357, 401],
        "event_command_rules": rules,
    }


def test_scan_native_rule_candidates_scans_event_command_candidates() -> None:
    """scan_rule_candidates(event_commands) 返回候选、去重样本和规则路径命中。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "event_command_data_files": [
                    {
                        "file_name": "Map001.json",
                        "data": {
                            "events": [
                                None,
                                {
                                    "id": 1,
                                    "pages": [
                                        {
                                            "list": [
                                                {"code": 401, "parameters": ["Hello there"]},
                                                {"code": 401, "parameters": ["Hello there"]},
                                                {
                                                    "code": 357,
                                                    "parameters": [
                                                        "Speaker",
                                                        '{"message":"Inside JSON"}',
                                                    ],
                                                },
                                            ]
                                        }
                                    ],
                                },
                            ]
                        },
                    }
                ],
                "event_command_codes": [401],
                "event_command_rules": [
                    {
                        "command_code": 357,
                        "parameter_filters": [{"index": 0, "value": "Speaker"}],
                        "path_templates": ["$['parameters'][1]['message']"],
                    }
                ],
            },
        )
    )

    candidates = [
        ensure_json_object(candidate, f"candidate[{index}]")
        for index, candidate in enumerate(result.candidates)
    ]
    locations_by_text = {str(candidate["original_text"]): str(candidate["location_path"]) for candidate in candidates}
    assert result.candidate_summary == [{"domain": "event_commands", "candidate_count": 3}]
    assert locations_by_text["Hello there"] == "Map001.json/1/0/1/parameters/0"
    assert locations_by_text["Inside JSON"] == "Map001.json/1/0/2/parameters/1/message"
    assert {str(candidate["domain"]) for candidate in candidates} == {"event_commands"}
    assert {str(candidate["source_file"]) for candidate in candidates} == {"Map001.json"}
    assert any(str(candidate["json_path"]) == "$['parameters'][1]['message']" for candidate in candidates)

    event_summary = ensure_json_object(
        result.scan_summary["event_commands"],
        "native_rule_candidates_result.scan_summary.event_commands",
    )
    assert event_summary["command_codes"] == [357, 401]
    assert event_summary["scanned_command_count"] == 3
    assert event_summary["matched_command_count"] == 3
    assert event_summary["sample_count"] == 2
    assert event_summary["samples_by_code"] == {
        "357": [["Speaker", '{"message":"Inside JSON"}']],
        "401": [["Hello there"]],
    }
    hit_details = ensure_json_array(event_summary["hit_details"], "event_commands.hit_details")
    assert hit_details == [
        {
            "command_code": 357,
            "command_location_path": "Map001.json/1/0/2",
            "file_name": "Map001.json",
            "json_path": "$['parameters'][1]['message']",
            "location_path": "Map001.json/1/0/2/parameters/1/message",
            "original_text": "Inside JSON",
            "path_template": "$['parameters'][1]['message']",
            "rule_index": 0,
        }
    ]
    assert event_summary["rule_summaries"] == [
        {
            "command_code": 357,
            "matched_command_count": 1,
            "matched_command_location_paths": ["Map001.json/1/0/2"],
            "path_hit_counts": [
                {
                    "hit_count": 1,
                    "path_template": "$['parameters'][1]['message']",
                }
            ],
            "rule_index": 0,
        }
    ]


def test_scan_native_rule_candidates_scans_plugin_config_rule_hits() -> None:
    """scan_rule_candidates(plugin_config) 返回插件参数规则命中明细。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "plugin_config_plugins": [
                    {
                        "plugin_index": 0,
                        "plugin_name": "TestPlugin",
                        "plugin": {
                            "name": "TestPlugin",
                            "status": True,
                            "parameters": {
                                "Message": "プラグイン本文",
                                "Nested": json.dumps({"text": "ネスト本文"}, ensure_ascii=False),
                                "Count": 3,
                            },
                        },
                    }
                ],
                "plugin_config_rules": [
                    {
                        "plugin_index": 0,
                        "plugin_name": "TestPlugin",
                        "path_templates": [
                            "$['parameters']['Message']",
                            "$['parameters']['Nested']['text']",
                        ],
                    }
                ],
                "text_rules": _plugin_source_text_rules_payload(),
            },
        )
    )

    candidates = [
        ensure_json_object(candidate, f"candidate[{index}]")
        for index, candidate in enumerate(result.candidates)
    ]
    assert result.candidate_summary == [{"domain": "plugin_config", "candidate_count": 2}]
    assert {str(candidate["domain"]) for candidate in candidates} == {"plugin_config"}
    assert {str(candidate["location_path"]) for candidate in candidates} == {
        "plugins.js/0/Message",
        "plugins.js/0/Nested/text",
    }

    plugin_summary = ensure_json_object(
        result.scan_summary["plugin_config"],
        "native_rule_candidates_result.scan_summary.plugin_config",
    )
    plugin_summaries = ensure_json_array(plugin_summary["plugins"], "plugin_config.plugins")
    first_plugin_summary = ensure_json_object(plugin_summaries[0], "plugin_config.plugins[0]")
    assert plugin_summary["plugin_count"] == 1
    assert plugin_summary["candidate_count"] == 2
    assert plugin_summary["string_leaf_count"] == 2
    hit_details = ensure_json_array(plugin_summary["hit_details"], "plugin_config.hit_details")
    assert hit_details == [
        {
            "json_path": "$['parameters']['Message']",
            "location_path": "plugins.js/0/Message",
            "original_text": "プラグイン本文",
            "path_template": "$['parameters']['Message']",
            "plugin_index": 0,
            "plugin_name": "TestPlugin",
            "rule_index": 0,
        },
        {
            "json_path": "$['parameters']['Nested']['text']",
            "location_path": "plugins.js/0/Nested/text",
            "original_text": "ネスト本文",
            "path_template": "$['parameters']['Nested']['text']",
            "plugin_index": 0,
            "plugin_name": "TestPlugin",
            "rule_index": 0,
        },
    ]
    assert plugin_summary["rule_summaries"] == [
        {
            "path_hit_counts": [
                {
                    "path_template": "$['parameters']['Message']",
                    "string_hit_count": 1,
                    "translatable_hit_count": 1,
                },
                {
                    "path_template": "$['parameters']['Nested']['text']",
                    "string_hit_count": 1,
                    "translatable_hit_count": 1,
                },
            ],
            "plugin_hash": first_plugin_summary["plugin_hash"],
            "plugin_index": 0,
            "plugin_name": "TestPlugin",
            "rule_index": 0,
        }
    ]


def test_scan_native_rule_candidates_scans_mv_virtual_namebox_rule_hits() -> None:
    """scan_rule_candidates(mv_virtual_namebox) 返回候选、规则命中和重建错误。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "mv_virtual_namebox_data_files": [
                    {
                        "file_name": "CommonEvents.json",
                        "data": [
                            None,
                            {
                                "id": 1,
                                "list": [
                                    {"code": 101, "parameters": [0, 0, 0, 2]},
                                    {"code": 401, "parameters": ["案内人："]},
                                    {"code": 401, "parameters": ["本文です"]},
                                    {"code": 0, "parameters": []},
                                ],
                            },
                            {
                                "id": 2,
                                "list": [
                                    {"code": 101, "parameters": [0, 0, 0, 2]},
                                    {"code": 401, "parameters": ["\\N[1]:役者本文"]},
                                    {"code": 0, "parameters": []},
                                ],
                            },
                        ],
                    }
                ],
                "mv_virtual_namebox_actor_names": [{"actor_id": 1, "name": "MV勇者"}],
                "mv_virtual_namebox_rules": [
                    {
                        "rule_order": 0,
                        "rule_name": "standalone-colon",
                        "pattern_text": r"^(?P<speaker>案内人)：$",
                        "speaker_group": "speaker",
                        "body_group": "",
                        "speaker_policy": "translate",
                        "render_template": "{speaker}：",
                    },
                    {
                        "rule_order": 1,
                        "rule_name": "actor-inline",
                        "pattern_text": r"^(?P<speaker>\\N\[(?:1)\]):(?P<body>.+)$",
                        "speaker_group": "speaker",
                        "body_group": "body",
                        "speaker_policy": "actor_name",
                        "render_template": "{speaker}:{body}",
                    },
                ],
            },
        )
    )

    assert result.candidate_summary == [{"domain": "mv_virtual_namebox", "candidate_count": 2}]
    candidates = [
        ensure_json_object(candidate, f"candidate[{index}]")
        for index, candidate in enumerate(result.candidates)
    ]
    assert {str(candidate["domain"]) for candidate in candidates} == {"mv_virtual_namebox"}
    assert [str(candidate["location_path"]) for candidate in candidates] == [
        "CommonEvents.json/1/1",
        "CommonEvents.json/2/1",
    ]

    mv_summary = ensure_json_object(
        result.scan_summary["mv_virtual_namebox"],
        "native_rule_candidates_result.scan_summary.mv_virtual_namebox",
    )
    assert mv_summary["candidate_count"] == 2
    assert mv_summary["matched_candidate_count"] == 2
    assert mv_summary["scanned_command_count"] == 7
    assert mv_summary["errors"] == []
    assert mv_summary["candidate_details"] == [
        {
            "location_path": "CommonEvents.json/1/1",
            "text": "案内人：",
            "following_lines": ["本文です"],
        },
        {
            "location_path": "CommonEvents.json/2/1",
            "text": "\\N[1]:役者本文",
            "following_lines": [],
        },
    ]
    assert mv_summary["hit_details"] == [
        {
            "location_path": "CommonEvents.json/1/1",
            "text": "案内人：",
            "following_lines": ["本文です"],
            "matching_rules": ["standalone-colon"],
            "matches": [
                {
                    "rule_name": "standalone-colon",
                    "speaker": "案内人",
                    "source_speaker": "案内人",
                    "speaker_policy": "translate",
                }
            ],
        },
        {
            "location_path": "CommonEvents.json/2/1",
            "text": "\\N[1]:役者本文",
            "following_lines": [],
            "matching_rules": ["actor-inline"],
            "matches": [
                {
                    "rule_name": "actor-inline",
                    "speaker": "MV勇者",
                    "source_speaker": "\\N[1]",
                    "speaker_policy": "actor_name",
                }
            ],
        },
    ]
    assert mv_summary["rule_summaries"] == [
        {
            "matched_candidate_count": 1,
            "matched_candidate_location_paths": ["CommonEvents.json/1/1"],
            "rule_index": 0,
            "rule_name": "standalone-colon",
        },
        {
            "matched_candidate_count": 1,
            "matched_candidate_location_paths": ["CommonEvents.json/2/1"],
            "rule_index": 1,
            "rule_name": "actor-inline",
        },
    ]


def test_scan_native_rule_candidates_scans_nonstandard_data_files() -> None:
    """scan_rule_candidates 可直接从非标准 data JSON 输入生成候选和扫描摘要。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "nonstandard_data_files": [
                    {
                        "file_name": "EmptyPluginData.json",
                        "data": {"label": "123"},
                    },
                    {
                        "file_name": "UnknownPluginData.json",
                        "data": [
                            {
                                "id": 1,
                                "name": "これは無視される",
                                "icon": "img/pictures/Face.png",
                                "nested": {"message": "「包まれた文」"},
                            },
                            {
                                "enabled": "true",
                                "formula": "a.hpRate() >= 0.5",
                            },
                        ],
                    },
                ],
                "text_rules": _plugin_source_text_rules_payload(),
            },
        )
    )

    candidates = [
        ensure_json_object(candidate, f"candidate[{index}]")
        for index, candidate in enumerate(result.candidates)
    ]
    candidates_by_path = {str(candidate["json_path"]): candidate for candidate in candidates}
    assert set(candidates_by_path) == {"$[0]['name']", "$[0]['nested']['message']"}
    name_candidate = candidates_by_path["$[0]['name']"]
    nested_candidate = candidates_by_path["$[0]['nested']['message']"]
    assert name_candidate["domain"] == "nonstandard_data"
    assert name_candidate["file"] == "UnknownPluginData.json"
    assert name_candidate["source_file"] == "UnknownPluginData.json"
    assert name_candidate["source_text"] == "これは無視される"
    assert name_candidate["original_text"] == "これは無視される"
    assert name_candidate["raw_text"] == "これは無視される"
    assert name_candidate["field_name"] == "name"
    assert set(cast(list[str], name_candidate["sibling_field_names"])) == {"id", "icon", "nested"}
    assert set(cast(list[str], name_candidate["parent_object_keys"])) == {"id", "name", "icon", "nested"}
    assert nested_candidate["source_text"] == "包まれた文"
    assert nested_candidate["raw_text"] == "「包まれた文」"
    assert result.candidate_summary == [{"domain": "nonstandard_data", "candidate_count": 2}]
    nonstandard_summary = ensure_json_object(
        result.scan_summary["nonstandard_data"],
        "native_rule_candidates_result.scan_summary.nonstandard_data",
    )
    assert nonstandard_summary["nonstandard_file_count"] == 2
    assert nonstandard_summary["candidate_count"] == 2
    assert nonstandard_summary["high_risk"] is True
    raw_files = ensure_json_array(nonstandard_summary["files"], "nonstandard_data.files")
    files = [
        ensure_json_object(item, f"nonstandard_data.files[{index}]")
        for index, item in enumerate(raw_files)
    ]
    files_by_name = {str(item["file"]): item for item in files}
    assert files_by_name["EmptyPluginData.json"]["string_leaf_count"] == 1
    assert files_by_name["EmptyPluginData.json"]["candidate_count"] == 0
    assert files_by_name["UnknownPluginData.json"]["string_leaf_count"] == 5
    assert files_by_name["UnknownPluginData.json"]["candidate_count"] == 2
    leaves = ensure_json_array(files_by_name["UnknownPluginData.json"]["leaves"], "UnknownPluginData.json.leaves")
    leaf_paths = {
        str(ensure_json_object(leaf, f"leaf[{index}]")["path"])
        for index, leaf in enumerate(leaves)
    }
    assert "$[0]['name']" in leaf_paths
    assert "$[0]['nested']['message']" in leaf_paths


def test_scan_native_rule_candidates_returns_nonstandard_data_leaves() -> None:
    """scan_rule_candidates 可只展开非标准 data leaves，不额外筛选候选。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "nonstandard_data_leaves": [
                    {
                        "file_name": "EmptyPluginData.json",
                        "data": {"label": "123"},
                    },
                    {
                        "file_name": "UnknownPluginData.json",
                        "data": [
                            {
                                "id": 1,
                                "name": "これは無視される",
                                "nested": {"message": "「包まれた文」"},
                            }
                        ],
                    },
                ],
            },
        )
    )

    assert result.candidates == []
    assert result.candidate_summary == []
    nonstandard_summary = ensure_json_object(
        result.scan_summary["nonstandard_data_leaves"],
        "native_rule_candidates_result.scan_summary.nonstandard_data_leaves",
    )
    assert nonstandard_summary["nonstandard_file_count"] == 2
    raw_files = ensure_json_array(nonstandard_summary["files"], "nonstandard_data_leaves.files")
    files = [
        ensure_json_object(item, f"nonstandard_data_leaves.files[{index}]")
        for index, item in enumerate(raw_files)
    ]
    files_by_name = {str(item["file"]): item for item in files}
    assert files_by_name["EmptyPluginData.json"]["string_leaf_count"] == 1
    assert files_by_name["UnknownPluginData.json"]["string_leaf_count"] == 2
    unknown_leaves = ensure_json_array(
        files_by_name["UnknownPluginData.json"]["leaves"],
        "UnknownPluginData.json.leaves",
    )
    leaves_by_path = {
        str(ensure_json_object(leaf, f"leaf[{index}]")["path"]): ensure_json_object(
            leaf,
            f"leaf[{index}]",
        )
        for index, leaf in enumerate(unknown_leaves)
    }
    assert leaves_by_path["$[0]['id']"]["value_type"] == "number"
    assert leaves_by_path["$[0]['name']"]["value"] == "これは無視される"
    assert leaves_by_path["$[0]['nested']['message']"]["value"] == "「包まれた文」"


def test_scan_native_rule_candidates_evaluates_nonstandard_data_rule_coverage() -> None:
    """scan_rule_candidates 可用 native leaves/candidates 评估非标准 data 规则覆盖。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "nonstandard_data_rule_coverage": {
                    "rules": [
                        {
                            "file": "UnknownPluginData.json",
                            "paths": ["$[*]['name']"],
                            "excluded_paths": ["$[*]['nested']['message']"],
                            "skipped": False,
                        },
                        {
                            "file": "SkippedPluginData.json",
                            "paths": [],
                            "excluded_paths": [],
                            "skipped": True,
                        },
                    ],
                    "files": [
                        {
                            "file": "UnknownPluginData.json",
                            "leaves": [
                                {"path": "$[0]['id']", "value_type": "number"},
                                {"path": "$[0]['name']", "value_type": "string"},
                                {"path": "$[0]['nested']['message']", "value_type": "string"},
                            ],
                        },
                        {
                            "file": "SkippedPluginData.json",
                            "leaves": [
                                {"path": "$[0]['name']", "value_type": "string"},
                            ],
                        },
                    ],
                    "candidates": [
                        {"file": "UnknownPluginData.json", "json_path": "$[0]['name']"},
                        {"file": "UnknownPluginData.json", "json_path": "$[0]['nested']['message']"},
                        {"file": "SkippedPluginData.json", "json_path": "$[0]['name']"},
                    ],
                }
            },
        )
    )

    coverage = ensure_json_object(
        result.scan_summary["nonstandard_data_rule_coverage"],
        "native_rule_candidates_result.scan_summary.nonstandard_data_rule_coverage",
    )
    rules = ensure_json_array(coverage["rules"], "coverage.rules")
    first_rule = ensure_json_object(rules[0], "coverage.rules[0]")
    translated_candidates = ensure_json_array(coverage["translated_candidates"], "coverage.translated_candidates")
    excluded_candidates = ensure_json_array(coverage["excluded_candidates"], "coverage.excluded_candidates")
    skipped_files = ensure_json_array(coverage["skipped_files"], "coverage.skipped_files")
    unreviewed_candidates = ensure_json_array(coverage["unreviewed_candidates"], "coverage.unreviewed_candidates")

    assert first_rule["translated_candidate_count"] == 1
    assert first_rule["excluded_candidate_count"] == 1
    assert translated_candidates == [{"file": "UnknownPluginData.json", "json_path": "$[0]['name']"}]
    assert excluded_candidates == [
        {"file": "UnknownPluginData.json", "json_path": "$[0]['nested']['message']"}
    ]
    assert skipped_files == ["SkippedPluginData.json"]
    assert unreviewed_candidates == []
    assert coverage["reviewed_candidate_count"] == 2


def test_scan_native_rule_candidates_scans_placeholder_candidates() -> None:
    """scan_rule_candidates(placeholders) 等价产出普通占位符候选明细。"""
    text_rules = TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=(
            CustomPlaceholderRule.create(
                r"\\F\[[^\]\r\n]+\]",
                "[CUSTOM_FACE_PORTRAIT_{index}]",
            ),
        ),
    )
    translation_data_map = {
        "Map001.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="Map001.json/events/1/pages/0/list/0",
                    item_type="long_text",
                    original_lines=[r"\V[1] \F[GuideA] \nn[Name]", r"again \nn[Name]"],
                )
            ],
        )
    }

    payload = build_native_placeholder_candidates_payload(translation_data_map, text_rules)
    result = scan_native_rule_candidates(payload)

    placeholder_summary = ensure_json_object(
        result.scan_summary["placeholders"],
        "native_rule_candidates_result.scan_summary.placeholders",
    )
    candidates = [
        ensure_json_object(candidate, f"candidate[{index}]")
        for index, candidate in enumerate(
            ensure_json_array(placeholder_summary["candidates"], "placeholders.candidates")
        )
    ]
    candidates_by_marker = {str(candidate["marker"]): candidate for candidate in candidates}
    assert set(candidates_by_marker) == {r"\V[1]", r"\F[GuideA]", r"\nn[Name]"}

    uncovered_candidate = candidates_by_marker[r"\nn[Name]"]
    assert uncovered_candidate["count"] == 2
    assert uncovered_candidate["covered"] is False
    assert uncovered_candidate["standard_covered"] is False
    assert uncovered_candidate["custom_covered"] is False
    assert uncovered_candidate["sources"] == [
        "Map001.json/events/1/pages/0/list/0#0",
        "Map001.json/events/1/pages/0/list/0#1",
    ]

    assert candidates_by_marker[r"\V[1]"]["standard_covered"] is True
    assert candidates_by_marker[r"\V[1]"]["covered"] is True
    assert candidates_by_marker[r"\F[GuideA]"]["custom_covered"] is True
    assert candidates_by_marker[r"\F[GuideA]"]["covered"] is True
    assert result.candidate_summary == [{"domain": "placeholders", "candidate_count": 3}]
    assert placeholder_summary == {
        "candidate_count": 3,
        "candidates": candidates,
        "covered_count": 2,
        "custom_covered_count": 1,
        "scanned_text_count": 2,
        "standard_covered_count": 1,
        "uncovered_count": 1,
    }


def test_build_native_structured_placeholder_candidates_payload_includes_texts_and_rules() -> None:
    """结构化占位符 native payload 必须携带正文行和结构化规则。"""
    structured_rule = StructuredPlaceholderRule.create(
        rule_name="INLINE_LABEL",
        rule_type="paired_shell",
        pattern_text=r"(?P<prefix><name:)(?P<text>[^>]+)(?P<suffix>>)",
        translatable_group="text",
        protected_groups={
            "prefix": "[CUSTOM_INLINE_LABEL_PREFIX_{index}]",
            "suffix": "[CUSTOM_INLINE_LABEL_SUFFIX_{index}]",
        },
    )
    text_rules = TextRules.from_setting(
        TextRulesSetting(),
        structured_placeholder_rules=(structured_rule,),
    )
    translation_data_map = {
        "Map001.json": TranslationData(
            display_name=None,
            translation_items=[
                TranslationItem(
                    location_path="Map001.json/events/1/pages/0/list/0",
                    item_type="long_text",
                    original_lines=["<name:薬草>", "plain"],
                )
            ],
        )
    }

    payload = native_scope_index.build_native_structured_placeholder_candidates_payload(
        translation_data_map,
        text_rules,
    )

    assert payload["structured_placeholder_texts"] == [
        {
            "location_path": "Map001.json/events/1/pages/0/list/0",
            "line_number": 1,
            "text": "<name:薬草>",
        },
        {
            "location_path": "Map001.json/events/1/pages/0/list/0",
            "line_number": 2,
            "text": "plain",
        },
    ]
    text_rules_payload = ensure_json_object(payload["text_rules"], "structured_payload.text_rules")
    structured_rules = ensure_json_array(
        text_rules_payload["structured_placeholder_rules"],
        "structured_payload.text_rules.structured_placeholder_rules",
    )
    first_rule = ensure_json_object(structured_rules[0], "structured_rules[0]")
    assert first_rule["rule_name"] == "INLINE_LABEL"
    assert first_rule["translatable_group"] == "text"


def test_scan_native_rule_candidates_scans_structured_placeholder_candidates() -> None:
    """scan_rule_candidates(structured_placeholders) 返回结构化 shell 候选覆盖明细。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "structured_placeholder_texts": [
                    {
                        "location_path": "Map001.json/events/1/pages/0/list/0",
                        "line_number": 1,
                        "text": "<name:薬草> ◆<speaker>! 【label:本文】",
                    },
                    {
                        "location_path": "Map001.json/events/1/pages/0/list/0",
                        "line_number": 2,
                        "text": "<other:未覆盖>",
                    },
                ],
                "text_rules": {
                    "custom_placeholder_rules": [],
                    "structured_placeholder_rules": [
                        {
                            "rule_name": "INLINE_LABEL",
                            "rule_type": "paired_shell",
                            "pattern_text": r"(?P<prefix><name:)(?P<text>[^>]+)(?P<suffix>>)",
                            "translatable_group": "text",
                            "protected_groups": {
                                "prefix": "[CUSTOM_INLINE_LABEL_PREFIX_{index}]",
                                "suffix": "[CUSTOM_INLINE_LABEL_SUFFIX_{index}]",
                            },
                        }
                    ],
                    "strip_wrapping_punctuation_pairs": [],
                    "source_text_required_pattern": r"[\s\S]",
                    "source_text_exclusion_profile": "none",
                },
            },
        )
    )

    structured_summary = ensure_json_object(
        result.scan_summary["structured_placeholders"],
        "native_rule_candidates_result.scan_summary.structured_placeholders",
    )
    candidates = [
        ensure_json_object(candidate, f"structured_candidate[{index}]")
        for index, candidate in enumerate(
            ensure_json_array(structured_summary["candidates"], "structured_placeholders.candidates")
        )
    ]
    candidates_by_text = {str(candidate["candidate"]): candidate for candidate in candidates}
    assert set(candidates_by_text) == {
        "<name:薬草>",
        "◆<speaker>!",
        "【label:本文】",
        "<other:未覆盖>",
    }
    covered_candidate = candidates_by_text["<name:薬草>"]
    assert covered_candidate == {
        "location_path": "Map001.json/events/1/pages/0/list/0",
        "line_number": 1,
        "candidate": "<name:薬草>",
        "text": "<name:薬草>",
        "range": [0, 13],
        "covered": True,
        "covered_by": "structured_placeholder",
        "matching_rules": ["INLINE_LABEL"],
        "candidate_kind": "structured_shell",
        "location_paths": ["Map001.json/events/1/pages/0/list/0"],
    }
    assert candidates_by_text["<other:未覆盖>"]["covered"] is False
    assert candidates_by_text["<other:未覆盖>"]["matching_rules"] == []
    assert result.candidate_summary == [{"domain": "structured_placeholders", "candidate_count": 4}]
    assert structured_summary == {
        "candidate_count": 4,
        "candidates": candidates,
        "covered_count": 1,
        "scanned_text_count": 2,
        "uncovered_count": 3,
    }


def test_build_native_note_tag_candidates_payload_includes_data_and_text_rules() -> None:
    """Note 标签 native payload 必须携带标准 data 与文本规则。"""
    text_rules = TextRules.from_setting(TextRulesSetting())

    payload = native_scope_index.build_native_note_tag_candidates_payload(
        _note_tag_game_data(),
        text_rules,
    )

    data_files = ensure_json_object(payload["note_tag_data_files"], "note_tag_payload.note_tag_data_files")
    assert "Items.json" in data_files
    assert "Map001.json" in data_files
    assert "plugins.js" not in data_files
    text_rules_payload = ensure_json_object(payload["text_rules"], "note_tag_payload.text_rules")
    assert text_rules_payload["source_text_required_pattern"] == text_rules.setting.source_text_required_pattern


def test_scan_native_rule_candidates_scans_note_tag_candidates() -> None:
    """scan_rule_candidates(note_tags) 返回 Note 标签候选统计。"""
    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "note_tag_data_files": {
                    "Items.json": [
                        None,
                        {
                            "id": 1,
                            "name": "Potion",
                            "note": '<desc:回復薬>\n<upgrade:10>\n<quoted:"薬袋">\n<desc:重複>\n<empty>\n<blank:>',
                        },
                    ],
                    "Map001.json": {
                        "events": {
                            "1": {
                                "name": "Chest",
                                "note": "<desc:宝箱>\n<memo:ABC>",
                            }
                        }
                    },
                    "plugins.js": [],
                },
                "text_rules": {
                    "custom_placeholder_rules": [],
                    "structured_placeholder_rules": [],
                    "strip_wrapping_punctuation_pairs": [],
                    "source_text_required_pattern": r"[\s\S]",
                    "source_text_exclusion_profile": "none",
                },
            },
        )
    )

    note_summary = ensure_json_object(
        result.scan_summary["note_tags"],
        "native_rule_candidates_result.scan_summary.note_tags",
    )
    hit_details = [
        ensure_json_object(hit, f"note_tag_hit_detail[{index}]")
        for index, hit in enumerate(ensure_json_array(note_summary["hit_details"], "note_tag_hit_details"))
    ]
    source_details = [
        ensure_json_object(source, f"note_tag_source_detail[{index}]")
        for index, source in enumerate(ensure_json_array(note_summary["source_details"], "note_tag_source_details"))
    ]
    candidates = [
        ensure_json_object(candidate, f"note_tag_candidate[{index}]")
        for index, candidate in enumerate(ensure_json_array(note_summary["candidates"], "note_tag_candidates"))
    ]
    candidates_by_key = {
        (candidate["file_name"], candidate["tag_name"]): candidate
        for candidate in candidates
    }

    item_desc = candidates_by_key[("Items.json", "desc")]
    assert item_desc["hit_count"] == 2
    assert item_desc["value_hit_count"] == 2
    assert item_desc["translatable_hit_count"] == 2
    assert item_desc["matched_file_count"] == 1
    assert item_desc["sample_locations"] == ["Items.json/1/note/desc"]
    assert item_desc["sample_values"] == ["回復薬", "重複"]

    map_desc = candidates_by_key[("Map*.json", "desc")]
    assert map_desc["hit_count"] == 1
    assert map_desc["sample_locations"] == ["Map001.json/events/1/note/desc"]
    assert map_desc["sample_values"] == ["宝箱"]

    memo = candidates_by_key[("Map*.json", "memo")]
    assert memo["value_hit_count"] == 1
    assert memo["translatable_hit_count"] == 1
    assert memo["sample_values"] == ["ABC"]

    upgrade = candidates_by_key[("Items.json", "upgrade")]
    assert upgrade["hit_count"] == 1
    assert upgrade["value_hit_count"] == 1
    assert upgrade["translatable_hit_count"] == 1
    assert upgrade["sample_locations"] == ["Items.json/1/note/upgrade"]
    assert upgrade["sample_values"] == ["10"]

    quoted = candidates_by_key[("Items.json", "quoted")]
    assert quoted["hit_count"] == 1
    assert quoted["value_hit_count"] == 1
    assert quoted["translatable_hit_count"] == 1
    assert quoted["sample_locations"] == ["Items.json/1/note/quoted"]
    assert quoted["sample_values"] == ["薬袋"]

    empty = candidates_by_key[("Items.json", "empty")]
    assert empty["hit_count"] == 1
    assert empty["value_hit_count"] == 0
    assert empty["translatable_hit_count"] == 0
    assert empty["sample_locations"] == []
    assert empty["sample_values"] == []

    assert {
        (
            str(hit["file_name"]),
            str(hit["tag_name"]),
            str(hit["location_path"]),
            str(hit["original_text"]),
            hit["translatable"] is True,
        )
        for hit in hit_details
    } == {
        ("Items.json", "desc", "Items.json/1/note/desc", "回復薬", True),
        ("Items.json", "upgrade", "Items.json/1/note/upgrade", "10", True),
        ("Items.json", "quoted", "Items.json/1/note/quoted", "薬袋", True),
        ("Items.json", "desc", "Items.json/1/note/desc", "重複", True),
        ("Items.json", "blank", "Items.json/1/note/blank", "", False),
        ("Map001.json", "desc", "Map001.json/events/1/note/desc", "宝箱", True),
        ("Map001.json", "memo", "Map001.json/events/1/note/memo", "ABC", True),
    }
    assert Counter(str(hit["location_path"]) for hit in hit_details)["Items.json/1/note/desc"] == 2
    assert "empty" not in {str(hit["tag_name"]) for hit in hit_details}
    assert source_details == [
        {
            "file_name": "Items.json",
            "location_prefix": "Items.json/1",
        },
        {
            "file_name": "Map001.json",
            "location_prefix": "Map001.json/events/1",
        },
    ]
    assert all(
        "tag_name" not in source
        and "original_text" not in source
        and "translatable" not in source
        for source in source_details
    )

    assert result.candidate_summary == [{"domain": "note_tags", "candidate_count": 7}]
    assert note_summary == {
        "candidate_count": 7,
        "candidate_value_count": 8,
        "candidates": candidates,
        "hit_details": hit_details,
        "scanned_source_count": 2,
        "source_details": source_details,
        "translatable_value_count": 6,
        "value_hit_count": 7,
    }


def test_scan_native_rule_candidates_returns_full_note_tag_hit_details() -> None:
    """scan_rule_candidates(note_tags) 明细必须超过摘要样例上限并保留真实来源文件。"""
    item_rows: list[JsonValue] = [None]
    item_rows.extend(
        cast(JsonValue, {"id": index, "name": f"Item{index}", "note": f"<desc:値{index}>"})
        for index in range(1, 7)
    )
    item_rows.append(cast(JsonValue, {"id": 7, "name": "Wrapped", "note": "<desc:「包まれた文」>\n<blank:>"}))

    result = scan_native_rule_candidates(
        cast(
            JsonObject,
            {
                "note_tag_data_files": {
                    "Items.json": item_rows,
                    "Map001.json": {
                        "events": {
                            "1": {
                                "name": "Chest",
                                "note": "<desc:宝箱>",
                            }
                        }
                    },
                },
                "text_rules": {
                    "custom_placeholder_rules": [],
                    "structured_placeholder_rules": [],
                    "strip_wrapping_punctuation_pairs": [["「", "」"]],
                    "source_text_required_pattern": r"[\s\S]",
                    "source_text_exclusion_profile": "none",
                },
            },
        )
    )

    note_summary = ensure_json_object(
        result.scan_summary["note_tags"],
        "native_rule_candidates_result.scan_summary.note_tags",
    )
    candidates = [
        ensure_json_object(candidate, f"note_tag_candidate[{index}]")
        for index, candidate in enumerate(ensure_json_array(note_summary["candidates"], "note_tag_candidates"))
    ]
    hit_details = [
        ensure_json_object(hit, f"note_tag_hit_detail[{index}]")
        for index, hit in enumerate(ensure_json_array(note_summary["hit_details"], "note_tag_hit_details"))
    ]
    candidates_by_key = {
        (candidate["file_name"], candidate["tag_name"]): candidate
        for candidate in candidates
    }
    item_desc = candidates_by_key[("Items.json", "desc")]
    assert item_desc["value_hit_count"] == 7
    assert item_desc["sample_values"] == ["値1", "値2", "値3", "値4", "値5"]

    desc_hits = [hit for hit in hit_details if str(hit["tag_name"]) == "desc"]
    assert len(desc_hits) == 8
    assert all(str(hit["file_name"]) != "Map*.json" for hit in desc_hits)
    assert {
        (
            str(hit["file_name"]),
            str(hit["location_path"]),
            str(hit["original_text"]),
            hit["translatable"] is True,
        )
        for hit in desc_hits
    } == {
        ("Items.json", "Items.json/1/note/desc", "値1", True),
        ("Items.json", "Items.json/2/note/desc", "値2", True),
        ("Items.json", "Items.json/3/note/desc", "値3", True),
        ("Items.json", "Items.json/4/note/desc", "値4", True),
        ("Items.json", "Items.json/5/note/desc", "値5", True),
        ("Items.json", "Items.json/6/note/desc", "値6", True),
        ("Items.json", "Items.json/7/note/desc", "包まれた文", True),
        ("Map001.json", "Map001.json/events/1/note/desc", "宝箱", True),
    }
    assert {
        (
            str(hit["file_name"]),
            str(hit["tag_name"]),
            str(hit["location_path"]),
            str(hit["original_text"]),
            hit["translatable"] is True,
        )
        for hit in hit_details
        if str(hit["tag_name"]) == "blank"
    } == {("Items.json", "blank", "Items.json/7/note/blank", "", False)}
    assert note_summary["value_hit_count"] == len(hit_details)
    assert note_summary["translatable_value_count"] == sum(
        1
        for hit in hit_details
        if hit["translatable"] is True
    )


def test_collect_native_note_tag_hit_details_returns_full_native_note_hits() -> None:
    """Python helper 必须暴露 Rust Note 标签逐命中明细，而不是摘要样例。"""
    from app.native_note_tag_scan import collect_native_note_tag_hit_details

    hits = collect_native_note_tag_hit_details(
        game_data=_note_tag_game_data(),
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )
    hit_objects = [
        ensure_json_object(hit, f"native_note_tag_hit[{index}]")
        for index, hit in enumerate(hits)
    ]

    assert {
        (
            str(hit["file_name"]),
            str(hit["tag_name"]),
            str(hit["location_path"]),
            str(hit["original_text"]),
            hit["translatable"] is True,
        )
        for hit in hit_objects
    } == {
        ("Items.json", "desc", "Items.json/1/note/desc", "回復薬", True),
        ("Items.json", "upgrade", "Items.json/1/note/upgrade", "10", False),
        ("Items.json", "quoted", "Items.json/1/note/quoted", "薬袋", True),
        ("Items.json", "desc", "Items.json/1/note/desc", "重複", True),
        ("Map001.json", "desc", "Map001.json/events/1/note/desc", "宝箱", True),
        ("Map001.json", "memo", "Map001.json/events/1/note/memo", "ABC", False),
    }
    assert all("sample_locations" not in hit and "sample_values" not in hit for hit in hit_objects)


def test_collect_native_note_tag_source_details_returns_native_note_sources() -> None:
    """Python helper 必须暴露 Rust Note 标签来源存在摘要。"""
    from app.native_note_tag_scan import collect_native_note_tag_source_details

    source_details = collect_native_note_tag_source_details(
        game_data=_note_tag_game_data(),
        text_rules=TextRules.from_setting(TextRulesSetting()),
    )
    source_objects = [
        ensure_json_object(source, f"native_note_tag_source[{index}]")
        for index, source in enumerate(source_details)
    ]

    assert source_objects == [
        {
            "file_name": "Items.json",
            "location_prefix": "Items.json/1",
        },
        {
            "file_name": "Map001.json",
            "location_prefix": "Map001.json/events/1",
        },
    ]
    assert all(
        "note_text" not in source
        and "tag_name" not in source
        and "original_text" not in source
        and "translatable" not in source
        for source in source_objects
    )


def test_scan_native_rule_candidates_requires_plugin_source_active_flag() -> None:
    """插件源码 active 状态必须显式传入，避免启用文件被静默当作禁用文件。"""
    with pytest.raises(ValueError, match="active"):
        _ = scan_native_rule_candidates(
            cast(
                JsonObject,
                {
                    "plugin_source_files": [
                        {
                            "file_name": "MissingActive.js",
                            "source": "const Messages = { title: '勇者の台詞' };",
                        }
                    ],
                    "text_rules": _plugin_source_text_rules_payload(),
                },
            )
        )
