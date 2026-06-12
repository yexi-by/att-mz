"""SQLite 持久化层测试。"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import cast

import pytest

from tests.native_rule_seed import (
    seed_native_empty_rule_review_state,
    seed_native_event_command_text_rules,
    seed_native_nonstandard_data_text_rules,
    seed_native_placeholder_rules,
    seed_native_plugin_text_rules,
    seed_native_source_residual_rules,
    seed_native_structured_placeholder_rules,
)

from app.terminology import TerminologyGlossary, TerminologyRegistry
from app.persistence import GameRegistry
from app.persistence.records import (
    TextFactDomainPayloadRecord,
    TextFactRenderPartRecord,
    TextFactScopeRecord,
    TextFactReadFilter,
    TextFactRecord,
    TextIndexDomainSummaryRecord,
    TextIndexInvalidationRecord,
    TextIndexItemRecord,
    TextIndexMetadata,
    TextIndexRuleHitSummaryRecord,
    TextIndexScopeSummaryRecord,
)
from app.persistence.sql import (
    CURRENT_SCHEMA_VERSION,
    EXPECTED_STATIC_TABLE_NAMES,
    CURRENT_TEXT_FACT_CONTRACT_VERSION,
    canonical_schema_sql_text,
    current_schema_fingerprint,
    current_schema_sql,
)
from app.plugin_source_text.native_scan import (
    PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION,
    PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION,
)
from app.plugin_source_text.runtime_audit import PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION
from app.rule_review import PLUGIN_TEXT_RULE_DOMAIN
from app.rmmz.schema import (
    EventCommandParameterFilter,
    EventCommandTextRuleRecord,
    ItemType,
    LlmFailureRecord,
    NonstandardDataTextRuleRecord,
    PlaceholderRuleRecord,
    PluginSourceRuntimeScanCacheRecord,
    PluginSourceRuntimeStringLiteralCacheRecord,
    PluginSourceRuntimeWriteMapRecord,
    PluginTextRuleRecord,
    SourceResidualRuleRecord,
    StructuredPlaceholderRuleRecord,
    TranslationErrorItem,
    TranslationItem,
)
from app.rmmz.text_rules import JsonValue, ensure_json_object


def read_sqlite_table_names(db_path: Path) -> set[str]:
    """读取测试数据库中的表名集合。"""
    with sqlite3.connect(db_path) as connection:
        table_rows = cast(
            list[tuple[str]],
            connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall(),
        )
    return {row[0] for row in table_rows}


def make_text_fact_scope(
    *,
    scope_key: str = "scope-current",
) -> TextFactScopeRecord:
    """构造测试用 当前文本事实 scope。"""
    return TextFactScopeRecord(
        scope_key=scope_key,
        schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
        scope_hash="scope-hash",
        source_snapshot_hash="source-snapshot-hash",
        rule_hash="rule-hash",
        text_rules_hash="text-rules-hash",
        created_at="2026-06-07T00:00:00",
    )


def make_text_fact_record(
    index: int,
    *,
    scope_key: str = "scope-current",
    domain: str = "event_command",
) -> TextFactRecord:
    """构造测试用 当前文本事实。"""
    suffix = f"{index:04d}"
    raw_text = f"  Text {suffix}  "
    return TextFactRecord(
        fact_id=f"fact-{suffix}",
        schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
        domain=domain,
        location_path=f"Map001.json/events/1/pages/0/list/{suffix}",
        source_file="Map001.json",
        source_type="event_command",
        item_type="long_text",
        role="",
        selector=f"event:1:0:{suffix}",
        raw_text=raw_text,
        visible_text=raw_text,
        translatable_text=f"Text {suffix}",
        raw_hash=f"raw-{suffix}",
        visible_hash=f"visible-{suffix}",
        translatable_hash=f"translatable-{suffix}",
        scope_key=scope_key,
    )


def make_saved_translation_item(
    *,
    fact_id: str,
    location_path: str,
    item_type: ItemType = "short_text",
    role: str | None = None,
    original_lines: list[str] | None = None,
    source_line_paths: list[str] | None = None,
    translation_lines: list[str] | None = None,
    source_fact_raw_hash: str | None = None,
    source_fact_translatable_hash: str | None = None,
) -> TranslationItem:
    """构造带当前文本事实身份的已保存译文测试对象。"""
    return TranslationItem(
        fact_id=fact_id,
        source_fact_raw_hash=source_fact_raw_hash or f"raw:{fact_id}",
        source_fact_translatable_hash=source_fact_translatable_hash or f"translatable:{fact_id}",
        location_path=location_path,
        item_type=item_type,
        role=role,
        original_lines=original_lines or ["原文"],
        source_line_paths=[location_path] if source_line_paths is None else source_line_paths,
        translation_lines=translation_lines or ["译文"],
    )


def make_text_fact_render_part(
    fact_id: str,
    *,
    part_order: int = 0,
) -> TextFactRenderPartRecord:
    """构造测试用 当前渲染片段。"""
    return TextFactRenderPartRecord(
        fact_id=fact_id,
        part_order=part_order,
        part_kind="translated_body",
        raw_text="raw",
        semantic_text="semantic",
        template_key="body",
    )


def make_text_fact_domain_payload(fact_id: str) -> TextFactDomainPayloadRecord:
    """构造测试用 当前领域 payload。"""
    return TextFactDomainPayloadRecord(
        fact_id=fact_id,
        payload_json='{"command_code":401}',
    )


def read_sqlite_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[int, str, str, int, str | None, int], ...]:
    """读取测试库中的 SQLite 表列签名。"""
    rows = cast(
        list[tuple[int, str, str, int, str | None, int]],
        connection.execute(f"PRAGMA table_info([{table_name}])").fetchall(),
    )
    return tuple(rows)


def read_sqlite_foreign_keys(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[int, int, str, str, str, str, str, str], ...]:
    """读取测试库中的 SQLite 外键签名。"""
    rows = cast(
        list[tuple[int, int, str, str, str, str, str, str]],
        connection.execute(f"PRAGMA foreign_key_list([{table_name}])").fetchall(),
    )
    return tuple(rows)


def read_sqlite_declared_index_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> dict[str, tuple[str, ...]]:
    """读取测试库中显式声明索引的列集合。"""
    rows = cast(
        list[tuple[str]],
        connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
            (table_name,),
        ).fetchall(),
    )
    index_columns: dict[str, tuple[str, ...]] = {}
    for (index_name,) in rows:
        column_rows = cast(
            list[tuple[int, int, str]],
            connection.execute(f"PRAGMA index_info([{index_name}])").fetchall(),
        )
        index_columns[index_name] = tuple(row[2] for row in column_rows)
    return index_columns


def test_shared_current_schema_resource_creates_declared_static_table_set() -> None:
    """共享 schema 资源必须能创建当前声明的完整静态表集合。"""
    with sqlite3.connect(":memory:") as connection:
        _ = connection.execute("PRAGMA foreign_keys = ON")
        _ = connection.executescript(current_schema_sql())
        table_rows = cast(
            list[tuple[str]],
            connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall(),
        )
        version_row = cast(
            tuple[int] | None,
            connection.execute(
                "SELECT version FROM schema_version WHERE schema_key = 'current'"
            ).fetchone(),
        )
        text_fact_columns = read_sqlite_table_columns(connection, "text_facts")
        render_part_columns = read_sqlite_table_columns(connection, "text_fact_render_parts")
        domain_payload_columns = read_sqlite_table_columns(connection, "text_fact_domain_payloads")
        scope_columns = read_sqlite_table_columns(connection, "text_fact_scope")
        render_part_foreign_keys = read_sqlite_foreign_keys(connection, "text_fact_render_parts")
        domain_payload_foreign_keys = read_sqlite_foreign_keys(connection, "text_fact_domain_payloads")
        text_fact_declared_indexes = read_sqlite_declared_index_columns(connection, "text_facts")
        translation_item_columns = read_sqlite_table_columns(connection, "translation_items")
        translation_item_declared_indexes = read_sqlite_declared_index_columns(connection, "translation_items")

    assert {row[0] for row in table_rows} - {"sqlite_sequence"} == set(EXPECTED_STATIC_TABLE_NAMES)
    assert CURRENT_SCHEMA_VERSION == 20
    assert version_row == (CURRENT_SCHEMA_VERSION,)
    assert len(current_schema_fingerprint()) == 64
    assert translation_item_columns == (
        (0, "fact_id", "TEXT", 0, None, 1),
        (1, "location_path", "TEXT", 1, None, 0),
        (2, "item_type", "TEXT", 1, None, 0),
        (3, "role", "TEXT", 0, None, 0),
        (4, "original_lines", "TEXT", 1, None, 0),
        (5, "source_line_paths", "TEXT", 1, None, 0),
        (6, "source_fact_raw_hash", "TEXT", 1, None, 0),
        (7, "source_fact_translatable_hash", "TEXT", 1, None, 0),
        (8, "translation_lines", "TEXT", 1, None, 0),
    )
    assert translation_item_declared_indexes == {
        "idx_translation_items_location_path": ("location_path",),
        "idx_translation_items_source_fact_raw_hash": ("source_fact_raw_hash",),
        "idx_translation_items_source_fact_translatable_hash": ("source_fact_translatable_hash",),
    }
    assert text_fact_columns == (
        (0, "fact_id", "TEXT", 0, None, 1),
        (1, "schema_version", "INTEGER", 1, None, 0),
        (2, "domain", "TEXT", 1, None, 0),
        (3, "location_path", "TEXT", 1, None, 0),
        (4, "source_file", "TEXT", 1, None, 0),
        (5, "source_type", "TEXT", 1, None, 0),
        (6, "item_type", "TEXT", 1, None, 0),
        (7, "role", "TEXT", 1, None, 0),
        (8, "selector", "TEXT", 1, None, 0),
        (9, "raw_text", "TEXT", 1, None, 0),
        (10, "visible_text", "TEXT", 1, None, 0),
        (11, "translatable_text", "TEXT", 1, None, 0),
        (12, "raw_hash", "TEXT", 1, None, 0),
        (13, "visible_hash", "TEXT", 1, None, 0),
        (14, "translatable_hash", "TEXT", 1, None, 0),
        (15, "scope_key", "TEXT", 1, None, 0),
    )
    assert render_part_columns == (
        (0, "fact_id", "TEXT", 1, None, 1),
        (1, "part_order", "INTEGER", 1, None, 2),
        (2, "part_kind", "TEXT", 1, None, 0),
        (3, "raw_text", "TEXT", 1, None, 0),
        (4, "semantic_text", "TEXT", 1, None, 0),
        (5, "template_key", "TEXT", 1, None, 0),
    )
    assert domain_payload_columns == (
        (0, "fact_id", "TEXT", 0, None, 1),
        (1, "payload_json", "TEXT", 1, None, 0),
    )
    assert scope_columns == (
        (0, "scope_key", "TEXT", 0, None, 1),
        (1, "schema_version", "INTEGER", 1, None, 0),
        (2, "scope_hash", "TEXT", 1, None, 0),
        (3, "source_snapshot_hash", "TEXT", 1, None, 0),
        (4, "rule_hash", "TEXT", 1, None, 0),
        (5, "text_rules_hash", "TEXT", 1, None, 0),
        (6, "created_at", "TEXT", 1, None, 0),
    )
    assert render_part_foreign_keys == (
        (0, 0, "text_facts", "fact_id", "fact_id", "NO ACTION", "CASCADE", "NONE"),
    )
    assert domain_payload_foreign_keys == (
        (0, 0, "text_facts", "fact_id", "fact_id", "NO ACTION", "CASCADE", "NONE"),
    )
    assert text_fact_declared_indexes == {
        "idx_text_facts_domain_location": ("domain", "location_path"),
        "idx_text_facts_domain_source_file": ("domain", "source_file"),
        "idx_text_facts_scope_key": ("scope_key",),
        "idx_text_facts_selector": ("selector",),
        "idx_text_facts_translatable_hash": ("translatable_hash",),
        "idx_text_facts_visible_hash": ("visible_hash",),
    }


def create_database_with_invalid_table_shapes(db_path: Path, tmp_path: Path) -> None:
    """创建表名完整但业务表结构错误的测试数据库。"""
    with sqlite3.connect(db_path) as connection:
        for table_name in EXPECTED_STATIC_TABLE_NAMES:
            if table_name == "schema_version":
                _ = connection.execute(
                    "CREATE TABLE schema_version (schema_key TEXT PRIMARY KEY, version INTEGER NOT NULL)"
                )
                _ = connection.execute(
                    "INSERT INTO schema_version (schema_key, version) VALUES ('current', ?)",
                    (CURRENT_SCHEMA_VERSION,),
                )
                continue
            if table_name == "metadata":
                _ = connection.execute(
                    """
                    CREATE TABLE metadata (
                        metadata_key TEXT PRIMARY KEY,
                        game_title TEXT NOT NULL,
                        game_path TEXT NOT NULL,
                        engine_kind TEXT NOT NULL,
                        content_root TEXT NOT NULL,
                        engine_version TEXT NOT NULL
                    )
                    """
                )
                _ = connection.execute(
                    """
                    INSERT INTO metadata (
                        metadata_key,
                        game_title,
                        game_path,
                        engine_kind,
                        content_root,
                        engine_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "current_game",
                        "BrokenSchema",
                        str(tmp_path),
                        "mz",
                        str(tmp_path),
                        "1.0.0",
                    ),
                )
                continue
            if table_name == "language_settings":
                _ = connection.execute(
                    """
                    CREATE TABLE language_settings (
                        settings_key TEXT PRIMARY KEY,
                        source_language TEXT NOT NULL,
                        target_language TEXT NOT NULL
                    )
                    """
                )
                _ = connection.execute(
                    "INSERT INTO language_settings (settings_key, source_language, target_language) VALUES ('current', 'ja', 'zh-Hans')"
                )
                continue
            _ = connection.execute(f"CREATE TABLE [{table_name}] (wrong_column TEXT)")


def create_incomplete_registry_database(
    *,
    db_path: Path,
    game_title: str,
    game_path: Path,
    content_root: Path,
) -> None:
    """创建能读取 metadata 但缺少当前必需表的无效注册库。"""
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute("CREATE TABLE schema_version (schema_key TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        _ = connection.execute(
            "INSERT INTO schema_version (schema_key, version) VALUES ('current', ?)",
            (CURRENT_SCHEMA_VERSION,),
        )
        _ = connection.execute(
            """
            CREATE TABLE metadata (
                metadata_key TEXT PRIMARY KEY,
                game_title TEXT NOT NULL,
                game_path TEXT NOT NULL,
                engine_kind TEXT NOT NULL,
                content_root TEXT NOT NULL,
                engine_version TEXT NOT NULL
            )
            """
        )
        _ = connection.execute(
            """
            INSERT INTO metadata (
                metadata_key,
                game_title,
                game_path,
                engine_kind,
                content_root,
                engine_version
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "current_game",
                game_title,
                str(game_path),
                "mz",
                str(content_root),
                "1.0.0",
            ),
        )


def test_current_schema_fingerprint_uses_canonical_line_endings() -> None:
    """schema 指纹必须忽略 Git 工作区换行差异。"""
    lf_sql = "CREATE TABLE test_table (id INTEGER);\nINSERT INTO test_table VALUES (1);\n"
    crlf_sql = lf_sql.replace("\n", "\r\n")
    cr_sql = lf_sql.replace("\n", "\r")

    assert canonical_schema_sql_text(crlf_sql) == lf_sql
    assert canonical_schema_sql_text(cr_sql) == lf_sql
    assert current_schema_fingerprint() == hashlib.sha256(
        canonical_schema_sql_text(current_schema_sql()).encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_registry_and_target_session_use_injected_directory(minimal_game_dir: Path, tmp_path: Path) -> None:
    """注册表支持测试注入目录，单游戏会话能读写核心表并关闭连接。"""
    db_dir = tmp_path / "db"
    registry = GameRegistry(db_dir)
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    assert record.game_title == "テストゲーム"
    assert record.engine_kind == "mz"
    assert record.content_root == minimal_game_dir
    assert record.source_language == "ja"
    assert record.target_language == "zh-Hans"
    assert [item.game_title for item in await registry.list_games()] == ["テストゲーム"]

    async with await registry.open_game("テストゲーム") as session:
        assert session.source_language == "ja"
        assert session.target_language == "zh-Hans"
        await session.write_translation_items(
            [
                make_saved_translation_item(
                    fact_id="tf:rawhash:system-title",
                    location_path="System.json/gameTitle",
                    item_type="short_text",
                    role=None,
                    original_lines=["テストゲーム"],
                    source_line_paths=[],
                    translation_lines=["测试游戏"],
                )
            ],
        )
        translated_items = await session.read_translated_items()
        assert translated_items[0].translation_lines == ["测试游戏"]
        assert translated_items[0].source_line_paths == []
        await session.write_translation_items(
            [
                make_saved_translation_item(
                    fact_id="tf:rawhash:common-event",
                    location_path="CommonEvents.json/1/0",
                    item_type="long_text",
                    role="アリス",
                    original_lines=["こんにちは"],
                    source_line_paths=["CommonEvents.json/1/1"],
                    translation_lines=["你好"],
                )
            ],
        )
        translated_long_item = next(
            item
            for item in await session.read_translated_items()
            if item.location_path == "CommonEvents.json/1/0"
        )
        assert translated_long_item.source_line_paths == ["CommonEvents.json/1/1"]
        await session.write_translation_items(
            [
                make_saved_translation_item(
                    fact_id="tf:rawhash:plugin-title",
                    location_path="plugins.js/0/Title",
                    item_type="short_text",
                    role=None,
                    original_lines=["Untitled"],
                    source_line_paths=[],
                    translation_lines=["无标题"],
                )
            ],
        )
        deleted_by_paths_count = await session.delete_translation_items_by_paths(
            ["plugins.js/0/Title", "missing/path", "plugins.js/0/Title"]
        )
        assert deleted_by_paths_count == 1
        deleted_count = await session.delete_translation_items_by_paths(["CommonEvents.json/1/0"])
        assert deleted_count == 1
        remaining_paths = {item.location_path for item in await session.read_translated_items()}
        assert remaining_paths == {
            "System.json/gameTitle"
        }
        assert session.engine_kind == "mz"
        assert session.content_root == minimal_game_dir

        rule = PluginTextRuleRecord(
            plugin_index=0,
            plugin_name="TestPlugin",
            plugin_hash="hash",
            path_templates=["$['parameters']['Message']"],
        )
        await seed_native_plugin_text_rules(session, [rule])
        assert await session.read_plugin_text_rules() == [rule]

        runtime_write_map = PluginSourceRuntimeWriteMapRecord(
            location_path="js/plugins/Source.js/ast:string:1:10:aaaa",
            source_file_name="Source.js",
            source_selector="ast:string:1:10:aaaa",
            source_file_hash="source-file-hash",
            source_text_hash="source-text-hash",
            translation_lines_hash="translation-lines-hash",
            runtime_file_name="Source.js",
            runtime_selector="ast:string:1:10:bbbb",
            runtime_file_hash="runtime-file-hash",
            runtime_text_hash="runtime-text-hash",
            runtime_line=1,
            created_at="2026-05-24T00:00:00",
        )
        await session.replace_plugin_source_runtime_write_maps([runtime_write_map])
        assert await session.read_plugin_source_runtime_write_maps() == [runtime_write_map]
        runtime_scan_cache = PluginSourceRuntimeScanCacheRecord(
            file_name="Source.js",
            file_hash="runtime-file-hash",
            rust_contract_version=PLUGIN_SOURCE_RUNTIME_SCAN_RUST_CONTRACT_VERSION,
            parser_contract_version=PLUGIN_SOURCE_RUNTIME_SCAN_PARSER_CONTRACT_VERSION,
            audit_contract_version=PLUGIN_SOURCE_RUNTIME_AUDIT_CONTRACT_VERSION,
            literals=[
                PluginSourceRuntimeStringLiteralCacheRecord(
                    selector="ast:string:1:10:bbbb",
                    text="当前运行文本",
                    raw_text="当前运行文本",
                    line=1,
                    start_index=1,
                    end_index=10,
                    context="property:title",
                    literal_kind="user_visible_candidate",
                    audit_default_severity="blocking",
                )
            ],
            created_at="2026-05-24T00:00:01",
        )
        await session.replace_plugin_source_runtime_scan_cache([runtime_scan_cache])
        assert await session.read_plugin_source_runtime_scan_cache() == [runtime_scan_cache]

        nonstandard_rule = NonstandardDataTextRuleRecord(
            file_name="Recipes.json",
            file_hash="recipes-hash",
            path_templates=["$[*]['name']"],
            excluded_path_templates=["$[*]['icon']"],
            skipped=False,
        )
        skipped_nonstandard_rule = NonstandardDataTextRuleRecord(
            file_name="Disciplines.json",
            file_hash="disciplines-hash",
            skipped=True,
        )
        await seed_native_nonstandard_data_text_rules(session, [nonstandard_rule, skipped_nonstandard_rule])
        assert await session.read_nonstandard_data_text_rules() == [
            skipped_nonstandard_rule,
            nonstandard_rule,
        ]

        event_rule = EventCommandTextRuleRecord(
            command_code=357,
            parameter_filters=[
                EventCommandParameterFilter(index=0, value="TestPlugin"),
            ],
            path_templates=["$['parameters'][3]['message']"],
        )
        await seed_native_event_command_text_rules(session, [event_rule])
        assert await session.read_event_command_text_rules() == [event_rule]

        terminology_registry = TerminologyRegistry(
            speaker_names={"アリス": "爱丽丝"},
            map_display_names={"始まりの町": "起始之镇"},
            skill_names={"火の術": "火术"},
        )
        terminology_glossary = TerminologyGlossary(
            terms={"アリス": "爱丽丝"},
        )
        await session.replace_terminology_bundle(
            registry=terminology_registry,
            glossary=terminology_glossary,
        )
        assert await session.read_terminology_registry() == terminology_registry
        assert await session.read_terminology_glossary() == terminology_glossary
        empty_terminology_registry = TerminologyRegistry()
        empty_terminology_glossary = TerminologyGlossary()
        await session.replace_terminology_bundle(
            registry=empty_terminology_registry,
            glossary=empty_terminology_glossary,
        )
        assert await session.read_terminology_registry() == empty_terminology_registry
        assert await session.read_terminology_glossary() == empty_terminology_glossary

        placeholder_rule = PlaceholderRuleRecord(
            pattern_text=r"\\F\[[^\]]+\]",
            placeholder_template="[CUSTOM_FACE_PORTRAIT_{index}]",
        )
        await seed_native_placeholder_rules(session, [placeholder_rule])
        assert await session.read_placeholder_rules() == [placeholder_rule]

        structured_placeholder_rule = StructuredPlaceholderRuleRecord(
            rule_name="MINI_LABEL",
            rule_type="paired_shell",
            pattern_text=r"(?<open><Mini\s+Label:\s*)(?<text>[^<>\r\n]*?)(?<close>>)",
            translatable_group="text",
            protected_groups={
                "open": "[CUSTOM_MINI_LABEL_OPEN_{index}]",
                "close": "[CUSTOM_MINI_LABEL_CLOSE_{index}]",
            },
        )
        await seed_native_structured_placeholder_rules(session, [structured_placeholder_rule])
        assert await session.read_structured_placeholder_rules() == [structured_placeholder_rule]

        source_residual_rule = SourceResidualRuleRecord(
            rule_id="position:Map001.json/1/0/0",
            rule_type="position",
            location_path="Map001.json/1/0/0",
            allowed_terms=["Alice"],
            reason="专名保留",
        )
        await seed_native_source_residual_rules(session, [source_residual_rule])
        assert await session.read_source_residual_rules() == [source_residual_rule]

        await seed_native_empty_rule_review_state(
            session,
            rule_domain=PLUGIN_TEXT_RULE_DOMAIN,
            scope_hash="hash-before",
        )
        review_state = await session.read_rule_review_state(rule_domain=PLUGIN_TEXT_RULE_DOMAIN)
        assert review_state is not None
        assert review_state.scope_hash == "hash-before"
        assert review_state.reviewed_candidates is True
        assert review_state.confirmed_empty is True
        await seed_native_plugin_text_rules(session, [rule])
        assert await session.read_rule_review_state(rule_domain=PLUGIN_TEXT_RULE_DOMAIN) is None

        run_record = await session.start_translation_run(
            total_extracted=10,
            pending_count=4,
            deduplicated_count=3,
            batch_count=2,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id="fact-quality-error-1",
                    location_path="Map001.json/1/0/0",
                    item_type="long_text",
                    role=None,
                    original_lines=["原文"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析"],
                    model_response="模型原始返回",
                ),
                TranslationErrorItem(
                    fact_id="fact-quality-error-2",
                    location_path="Map002.json/1/0/0",
                    item_type="long_text",
                    role=None,
                    original_lines=["別原文"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["另一个错误"],
                    model_response="另一个模型原始返回",
                ),
            ],
        )
        quality_errors = await session.read_translation_quality_errors(run_record.run_id)
        assert quality_errors[0].model_response == "模型原始返回"
        assert await session.count_translation_quality_errors(run_record.run_id) == 2
        quality_errors_by_paths = await session.read_translation_quality_errors_by_paths(
            run_record.run_id,
            {"Map002.json/1/0/0", "missing/path"},
        )
        assert [item.location_path for item in quality_errors_by_paths] == ["Map002.json/1/0/0"]
        quality_errors_by_fact_ids = await session.read_translation_quality_errors_by_fact_ids(
            run_record.run_id,
            {"fact-quality-error-1", "missing-fact"},
        )
        assert [item.fact_id for item in quality_errors_by_fact_ids] == ["fact-quality-error-1"]
        await session.write_translation_run(
            run_record.model_copy(
                update={
                    "success_count": 2,
                    "quality_error_count": 1,
                }
            )
        )
        quality_errors_after_progress_update = await session.read_translation_quality_errors(
            run_record.run_id
        )
        assert quality_errors_after_progress_update[0].model_response == "模型原始返回"
        deleted_quality_errors = await session.delete_translation_quality_errors_by_fact_ids(
            {"fact-quality-error-1"}
        )
        assert deleted_quality_errors == 1
        assert await session.count_translation_quality_errors(run_record.run_id) == 1

        await session.write_llm_failure(
            LlmFailureRecord(
                run_id=run_record.run_id,
                category="rate_limit",
                error_type="RateLimitError",
                error_message="请求过于频繁",
                retryable=True,
                attempt_count=3,
                created_at="2026-01-01T00:00:00",
            )
        )
        llm_failures = await session.read_llm_failures(run_record.run_id)
        assert llm_failures[0].category == "rate_limit"


@pytest.mark.asyncio
async def test_translation_quality_errors_require_fact_id(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """质量错误属于当前文本事实，缺 fact_id 必须显式失败。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        run_record = await session.start_translation_run(
            total_extracted=1,
            pending_count=0,
            deduplicated_count=1,
            batch_count=1,
        )
        with pytest.raises(ValueError, match="质量错误缺少 fact_id"):
            await session.write_translation_quality_errors(
                run_record.run_id,
                [
                    TranslationErrorItem(
                        fact_id="",
                        location_path="Items.json/1/name",
                        item_type="short_text",
                        role=None,
                        original_lines=["原文"],
                        translation_lines=["译文"],
                        error_type="AI漏翻",
                        error_detail=[],
                        model_response="{}",
                    )
                ],
            )


@pytest.mark.asyncio
async def test_translation_quality_errors_by_paths_preserve_same_path_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """按路径过滤质量错误时不能折叠同一路径的不同 fact。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game(record.game_title) as session:
        run_record = await session.start_translation_run(
            total_extracted=2,
            pending_count=0,
            deduplicated_count=2,
            batch_count=1,
        )
        await session.write_translation_quality_errors(
            run_record.run_id,
            [
                TranslationErrorItem(
                    fact_id="fact-a",
                    location_path="Items.json/1/note/desc",
                    item_type="short_text",
                    role=None,
                    original_lines=["一"],
                    translation_lines=["A"],
                    error_type="AI漏翻",
                    error_detail=[],
                    model_response="{}",
                ),
                TranslationErrorItem(
                    fact_id="fact-b",
                    location_path="Items.json/1/note/desc",
                    item_type="short_text",
                    role=None,
                    original_lines=["二"],
                    translation_lines=["B"],
                    error_type="AI漏翻",
                    error_detail=[],
                    model_response="{}",
                ),
            ],
        )
        items = await session.read_translation_quality_errors_by_paths(
            run_record.run_id,
            {"Items.json/1/note/desc"},
        )
    assert [item.fact_id for item in items] == ["fact-a", "fact-b"]


@pytest.mark.asyncio
async def test_translation_items_require_current_fact_identity(minimal_game_dir: Path, tmp_path: Path) -> None:
    """已保存译文必须以当前文本事实身份作为主身份。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    async with await registry.open_game(record.game_title) as session:
        item = TranslationItem(
            fact_id="tf:rawhash:identity",
            source_fact_raw_hash="rawhash",
            source_fact_translatable_hash="transhash",
            location_path="System.json/gameTitle",
            item_type="short_text",
            original_lines=["原文"],
            source_line_paths=["System.json/gameTitle"],
            translation_lines=["译文"],
        )
        await session.write_translation_items([item])

        saved_items = await session.read_translated_items()

        assert [saved.fact_id for saved in saved_items] == ["tf:rawhash:identity"]
        assert saved_items[0].source_fact_raw_hash == "rawhash"
        assert saved_items[0].source_fact_translatable_hash == "transhash"

        missing_identity_items = [
            item.model_copy(update={"fact_id": None}),
            item.model_copy(update={"source_fact_raw_hash": None}),
            item.model_copy(update={"source_fact_translatable_hash": None}),
        ]
        for missing_identity_item in missing_identity_items:
            with pytest.raises(ValueError, match="当前文本事实身份"):
                await session.write_translation_items([missing_identity_item])


@pytest.mark.asyncio
async def test_list_games_with_issues_skips_invalid_schema_database(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """列注册游戏时无效库进入 warning，不拖死可用游戏。"""
    db_dir = tmp_path / "db"
    registry = GameRegistry(db_dir)
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    create_incomplete_registry_database(
        db_path=db_dir / "AAA-invalid-schema.db",
        game_title="无效库",
        game_path=tmp_path / "invalid-game",
        content_root=tmp_path / "invalid-game",
    )

    records, issues = await registry.list_games_with_issues()

    assert [item.game_title for item in records] == [record.game_title]
    assert len(issues) == 1
    assert issues[0].db_path.name == "AAA-invalid-schema.db"
    assert "数据库结构不符合当前版本" in issues[0].message


@pytest.mark.asyncio
async def test_resolve_registered_title_by_path_ignores_unrelated_invalid_database(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """--game-path 定位目标游戏时，不被无关无效库 schema 拖死。"""
    db_dir = tmp_path / "db"
    registry = GameRegistry(db_dir)
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    create_incomplete_registry_database(
        db_path=db_dir / "AAA-invalid-schema.db",
        game_title="无效库",
        game_path=tmp_path / "invalid-game",
        content_root=tmp_path / "invalid-game",
    )

    game_title = await registry.resolve_registered_title_by_path(minimal_game_dir)

    assert game_title == record.game_title


@pytest.mark.asyncio
async def test_register_game_creates_declared_static_table_set(minimal_game_dir: Path, tmp_path: Path) -> None:
    """注册新游戏时创建的静态表集合必须等于项目声明。"""
    registry = GameRegistry(tmp_path / "db")

    record = await registry.register_game(minimal_game_dir, source_language="ja")

    table_names = read_sqlite_table_names(record.db_path)
    assert table_names - {"sqlite_sequence"} == set(EXPECTED_STATIC_TABLE_NAMES)


@pytest.mark.asyncio
async def test_text_fact_records_replace_read_and_require_scope(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前文本事实支持整批替换、稳定读取和当前 scope 显式校验。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="en")
    assert CURRENT_TEXT_FACT_CONTRACT_VERSION == 2
    assert CURRENT_SCHEMA_VERSION == 20
    scope = make_text_fact_scope()
    namebox_fact = TextFactRecord(
        fact_id="fact-namebox",
        schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
        domain="mv_virtual_namebox",
        location_path="Map001.json/events/1/pages/0/list/0",
        source_file="Map001.json",
        source_type="event_command",
        item_type="long_text",
        role="Dan",
        selector="event:1:0:0",
        raw_text="\n<Dan:> Hello  ",
        visible_text="\n<Dan:> Hello  ",
        translatable_text="Hello",
        raw_hash="raw-namebox",
        visible_hash="visible-namebox",
        translatable_hash="translatable-namebox",
        scope_key=scope.scope_key,
    )
    event_fact = TextFactRecord(
        fact_id="fact-event",
        schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
        domain="event_command",
        location_path="Map001.json/events/1/pages/0/list/1",
        source_file="Map001.json",
        source_type="event_command",
        item_type="long_text",
        role="",
        selector="event:1:0:1",
        raw_text="  Welcome back  ",
        visible_text="  Welcome back  ",
        translatable_text="Welcome back",
        raw_hash="raw-event",
        visible_hash="visible-event",
        translatable_hash="translatable-event",
        scope_key=scope.scope_key,
    )
    render_parts = [
        TextFactRenderPartRecord(
            fact_id=namebox_fact.fact_id,
            part_order=3,
            part_kind="translated_body",
            raw_text=" Hello  ",
            semantic_text="Hello",
            template_key="body",
        ),
        TextFactRenderPartRecord(
            fact_id=namebox_fact.fact_id,
            part_order=0,
            part_kind="literal",
            raw_text="\n<",
            semantic_text="\n<",
            template_key="prefix",
        ),
        TextFactRenderPartRecord(
            fact_id=namebox_fact.fact_id,
            part_order=2,
            part_kind="literal",
            raw_text=":> ",
            semantic_text=":> ",
            template_key="separator",
        ),
        TextFactRenderPartRecord(
            fact_id=namebox_fact.fact_id,
            part_order=1,
            part_kind="speaker",
            raw_text="Dan",
            semantic_text="Dan",
            template_key="speaker",
        ),
    ]
    payloads = [
        TextFactDomainPayloadRecord(
            fact_id=namebox_fact.fact_id,
            payload_json='{"speaker_policy":"translate"}',
        ),
        TextFactDomainPayloadRecord(
            fact_id=event_fact.fact_id,
            payload_json='{"command_code":401}',
        ),
    ]

    async with await registry.open_game(record.game_title) as session:
        with pytest.raises(RuntimeError, match="rebuild-text-index") as missing_scope_error:
            _ = await session.require_current_text_fact_scope(scope.scope_key)
        assert "当前命令" in str(missing_scope_error.value)
        assert "下一步" in str(missing_scope_error.value)

        await session.replace_text_facts(
            scope=scope,
            facts=[namebox_fact, event_fact],
            render_parts=render_parts,
            domain_payloads=payloads,
        )

        assert await session.count_text_facts() == 2
        assert await session.read_text_fact_scope(scope.scope_key) == scope
        assert await session.require_current_text_fact_scope(scope.scope_key) == scope
        assert await session.read_text_fact_scope("missing-scope") is None
        assert await session.read_text_facts() == [event_fact, namebox_fact]
        assert await session.read_text_facts(
            TextFactReadFilter(domain="mv_virtual_namebox")
        ) == [namebox_fact]
        assert await session.read_text_facts(
            TextFactReadFilter(source_file="Map001.json", scope_key=scope.scope_key)
        ) == [event_fact, namebox_fact]
        assert await session.read_text_facts(
            TextFactReadFilter(
                location_paths=(namebox_fact.location_path, event_fact.location_path),
            )
        ) == [event_fact, namebox_fact]
        assert await session.read_text_fact_render_parts([namebox_fact.fact_id]) == [
            render_parts[1],
            render_parts[3],
            render_parts[2],
            render_parts[0],
        ]
        assert await session.read_text_fact_domain_payloads(
            [namebox_fact.fact_id, event_fact.fact_id]
        ) == [payloads[1], payloads[0]]

        _ = await session.connection.execute(
            "UPDATE text_fact_scope SET schema_version = ? WHERE scope_key = ?",
            (CURRENT_TEXT_FACT_CONTRACT_VERSION + 1, scope.scope_key),
        )
        await session.connection.commit()
        with pytest.raises(RuntimeError, match="rebuild-text-index") as unsupported_version_error:
            _ = await session.require_current_text_fact_scope(scope.scope_key)
            assert "当前文本事实范围不符合当前要求" in str(unsupported_version_error.value)
        assert "当前命令" in str(unsupported_version_error.value)
        assert "下一步" in str(unsupported_version_error.value)

        _ = await session.connection.execute(
            "UPDATE text_fact_scope SET schema_version = ? WHERE scope_key = ?",
            (CURRENT_TEXT_FACT_CONTRACT_VERSION, scope.scope_key),
        )
        _ = await session.connection.execute(
            "UPDATE text_facts SET scope_key = ? WHERE fact_id = ?",
            ("other-scope", event_fact.fact_id),
        )
        await session.connection.commit()
        with pytest.raises(RuntimeError, match="rebuild-text-index") as mismatched_scope_error:
            _ = await session.require_current_text_fact_scope(scope.scope_key)
        assert "scope 不一致" in str(mismatched_scope_error.value)
        assert "当前命令" in str(mismatched_scope_error.value)
        assert "下一步" in str(mismatched_scope_error.value)

        _ = await session.connection.execute("DROP TABLE text_fact_scope")
        await session.connection.commit()
        with pytest.raises(RuntimeError, match="rebuild-text-index") as missing_table_error:
            _ = await session.require_current_text_fact_scope(scope.scope_key)
        assert "text_fact_scope" in str(missing_table_error.value)
        assert "当前命令" in str(missing_table_error.value)
        assert "下一步" in str(missing_table_error.value)


@pytest.mark.asyncio
async def test_text_fact_large_filter_reads_are_batched(
    minimal_game_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """current 大批量 fact/path 读取按 500 分块，并保持稳定排序。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="en")
    scope = make_text_fact_scope()
    facts = [make_text_fact_record(index, scope_key=scope.scope_key) for index in range(620)]
    render_parts = [
        make_text_fact_render_part(fact.fact_id, part_order=1)
        for fact in facts
    ] + [
        make_text_fact_render_part(fact.fact_id, part_order=0)
        for fact in facts
    ]
    payloads = [make_text_fact_domain_payload(fact.fact_id) for fact in facts]

    async with await registry.open_game(record.game_title) as session:
        await session.replace_text_facts(
            scope=scope,
            facts=list(reversed(facts)),
            render_parts=list(reversed(render_parts)),
            domain_payloads=list(reversed(payloads)),
        )
        original_execute = session.connection.execute
        parameter_counts: list[int] = []

        def recording_execute(sql: str, parameters: object = None) -> object:
            """记录读取 SQL 的参数数量，证明 IN 查询被分块。"""
            if isinstance(parameters, tuple) and (
                "text_facts" in sql
                or "text_fact_render_parts" in sql
                or "text_fact_domain_payloads" in sql
            ):
                tuple_parameters = cast(tuple[object, ...], parameters)
                parameter_counts.append(len(tuple_parameters))
            if parameters is None:
                return original_execute(sql)
            return original_execute(sql, parameters)

        monkeypatch.setattr(session.connection, "execute", recording_execute)

        filtered_facts = await session.read_text_facts(
            TextFactReadFilter(
                location_paths=[fact.location_path for fact in reversed(facts)],
            )
        )
        read_render_parts = await session.read_text_fact_render_parts(
            [fact.fact_id for fact in reversed(facts)]
        )
        read_payloads = await session.read_text_fact_domain_payloads(
            [fact.fact_id for fact in reversed(facts)]
        )

    assert filtered_facts == facts
    assert read_render_parts == sorted(render_parts, key=lambda part: (part.fact_id, part.part_order))
    assert read_payloads == payloads
    assert parameter_counts
    assert max(parameter_counts) <= 500
    assert parameter_counts.count(500) >= 3


@pytest.mark.asyncio
async def test_text_fact_replace_rejects_duplicate_payloads(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """当前整批替换在写库前拒绝会被 OR REPLACE 静默覆盖的重复输入。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="en")
    scope = make_text_fact_scope()
    fact = make_text_fact_record(0, scope_key=scope.scope_key)
    duplicate_fact = make_text_fact_record(0, scope_key=scope.scope_key)
    render_part = make_text_fact_render_part(fact.fact_id)
    duplicate_render_part = make_text_fact_render_part(fact.fact_id)
    payload = make_text_fact_domain_payload(fact.fact_id)
    duplicate_payload = make_text_fact_domain_payload(fact.fact_id)

    async with await registry.open_game(record.game_title) as session:
        with pytest.raises(ValueError, match="fact_id 重复"):
            await session.replace_text_facts(
                scope=scope,
                facts=[fact, duplicate_fact],
            )
        with pytest.raises(ValueError, match="渲染片段重复"):
            await session.replace_text_facts(
                scope=scope,
                facts=[fact],
                render_parts=[render_part, duplicate_render_part],
            )
        with pytest.raises(ValueError, match="领域 payload 重复"):
            await session.replace_text_facts(
                scope=scope,
                facts=[fact],
                domain_payloads=[payload, duplicate_payload],
            )


@pytest.mark.asyncio
async def test_text_index_records_replace_read_subset_and_invalidate(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """文本范围索引支持整批替换、精确读取和显式失效记录。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="en")
    first_item = TextIndexItemRecord(
        location_path="Map001.json/events/1/pages/0/list/0",
        item_type="long_text",
        role="Alice",
        original_lines=["Hello there", "Welcome back"],
        source_line_paths=["Map001.json/events/1/pages/0/list/1"],
        source_type="event_command",
        source_file="Map001.json",
        writable=True,
        source_snapshot_fingerprint="snapshot-v1",
        rules_fingerprint="rules-v1",
        locator_json='{"kind":"event_command","code":401}',
    )
    second_item = TextIndexItemRecord(
        location_path="System.json/gameTitle",
        item_type="short_text",
        role=None,
        original_lines=["Fixture Game"],
        source_line_paths=[],
        source_type="standard_data",
        source_file="System.json",
        writable=False,
        source_snapshot_fingerprint="snapshot-v1",
        rules_fingerprint="rules-v1",
        locator_json='{"kind":"field","field":"gameTitle"}',
    )
    third_item = TextIndexItemRecord(
        location_path="Map002.json/events/1/pages/0/list/0",
        item_type="long_text",
        role="Bob",
        original_lines=["Good morning"],
        source_line_paths=["Map002.json/events/1/pages/0/list/1"],
        source_type="event_command",
        source_file="Map002.json",
        writable=True,
        source_snapshot_fingerprint="snapshot-v1",
        rules_fingerprint="rules-v1",
        locator_json='{"kind":"event_command","code":401}',
    )
    metadata = TextIndexMetadata(
        source_snapshot_fingerprint="snapshot-v1",
        rules_fingerprint="rules-v1",
        item_count=3,
        workflow_gate_facts={},
        rust_contract_version=1,
        parser_contract_version=1,
        source_branch_contract_version=1,
        text_fact_schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
        created_at="2026-06-02T00:00:00",
    )

    async with await registry.open_game(record.game_title) as session:
        assert await session.read_text_index_metadata() is None
        assert await session.read_text_index_items_by_paths(["System.json/gameTitle"]) == []

        await session.replace_text_index(metadata=metadata, items=[second_item, third_item, first_item])

        assert await session.read_text_index_metadata() == metadata
        assert await session.read_text_index_location_paths() == {
            first_item.location_path,
            second_item.location_path,
            third_item.location_path,
        }
        assert await session.read_writable_text_index_location_paths() == [
            first_item.location_path,
            third_item.location_path,
        ]
        assert await session.count_text_index_items() == 3
        assert await session.read_text_index_items() == [first_item, third_item, second_item]
        assert await session.read_text_index_items_by_paths(
            [
                "missing/path",
                second_item.location_path,
                first_item.location_path,
                first_item.location_path,
            ]
        ) == [first_item, second_item]
        assert await session.count_pending_text_index_items() == 2
        assert await session.read_pending_text_index_items(limit=1) == [first_item]
        assert await session.read_text_index_scope_summary() is None
        assert await session.read_text_index_domain_summary() == []
        assert await session.read_text_index_rule_hit_summary() == []

        await session.write_translation_items(
            [
                make_saved_translation_item(
                    fact_id="tf:rawhash:first-index-item",
                    location_path=first_item.location_path,
                    item_type=first_item.item_type,
                    role=first_item.role,
                    original_lines=first_item.original_lines,
                    source_line_paths=first_item.source_line_paths,
                    translation_lines=["你好"],
                )
            ]
        )
        assert await session.count_pending_text_index_items() == 1
        assert [
            item.location_path for item in await session.read_translated_items_for_writable_text_index()
        ] == [first_item.location_path]
        assert await session.read_writable_text_index_location_paths() == [
            first_item.location_path,
            third_item.location_path,
        ]
        assert await session.read_pending_text_index_items(limit=None) == [third_item]

        await session.write_translation_items(
            [
                make_saved_translation_item(
                    fact_id="tf:rawhash:unwritable-index-item",
                    location_path=second_item.location_path,
                    item_type=second_item.item_type,
                    role=second_item.role,
                    original_lines=second_item.original_lines,
                    source_line_paths=second_item.source_line_paths,
                    translation_lines=["不可写路径译文"],
                ),
                make_saved_translation_item(
                    fact_id="tf:rawhash:index-mismatch-item",
                    location_path="missing/from/current/index",
                    item_type="short_text",
                    role=None,
                    original_lines=["Index mismatch source"],
                    source_line_paths=[],
                    translation_lines=["索引外译文"],
                ),
            ]
        )
        assert [
            item.location_path for item in await session.read_translated_items_for_writable_text_index()
        ] == [first_item.location_path]

        invalidations = [
            TextIndexInvalidationRecord(
                reason_key="source_snapshot_changed",
                detail="可信源快照变化",
                created_at="2026-06-02T00:01:00",
            )
        ]
        await session.replace_text_index_invalidations(invalidations)
        assert await session.read_text_index_invalidations() == invalidations

        rebuilt_metadata = TextIndexMetadata(
            source_snapshot_fingerprint="snapshot-current-next",
            rules_fingerprint="rules-current-next",
            item_count=0,
            workflow_gate_facts={},
            rust_contract_version=1,
            parser_contract_version=1,
            source_branch_contract_version=1,
            text_fact_schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
            created_at="2026-06-02T00:02:00",
        )
        scope_summary = TextIndexScopeSummaryRecord(
            total_count=3,
            active_count=2,
            writable_count=1,
            unwritable_count=1,
            stale_rule_count=1,
            native_thread_count=4,
        )
        domain_summary = [
            TextIndexDomainSummaryRecord(
                domain="event_command",
                item_count=2,
                active_count=2,
                writable_count=1,
                unwritable_count=1,
                inactive_rule_hit_count=0,
            )
        ]
        rule_hit_summary = [
            TextIndexRuleHitSummaryRecord(
                domain="event_command",
                rule_key="401",
                hit_count=2,
                extractable_count=2,
                writable_count=1,
                unwritable_count=1,
            )
        ]
        await session.replace_text_index(
            metadata=rebuilt_metadata,
            items=[],
            scope_summary=scope_summary,
            domain_summary=domain_summary,
            rule_hit_summary=rule_hit_summary,
        )
        assert await session.read_text_index_metadata() == rebuilt_metadata
        assert await session.read_text_index_items() == []
        assert await session.read_text_index_invalidations() == []
        assert await session.read_text_index_scope_summary() == scope_summary
        assert await session.read_text_index_domain_summary() == domain_summary
        assert await session.read_text_index_rule_hit_summary() == rule_hit_summary

        await session.clear_text_index()
        assert await session.read_text_index_scope_summary() is None
        assert await session.read_text_index_domain_summary() == []
        assert await session.read_text_index_rule_hit_summary() == []


@pytest.mark.asyncio
async def test_text_index_metadata_round_trips_contract_gate_facts(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    metadata = TextIndexMetadata(
        source_snapshot_fingerprint="source-v1",
        rules_fingerprint="rules-v1",
        item_count=0,
        workflow_gate_scope_hashes={},
        workflow_gate_facts={
            "plugin_source_text": {
                "source_branch": "plugin_source_text",
                "status": "pass",
                "scope_hash": "a" * 64,
                "error_codes": [],
                "stale_reasons": [],
            }
        },
        rust_contract_version=1,
        parser_contract_version=1,
        source_branch_contract_version=1,
        text_fact_schema_version=2,
        created_at="2026-06-11T00:00:00+00:00",
    )

    async with await registry.open_game(record.game_title) as session:
        await session.replace_text_index(metadata=metadata, items=[])

        saved = await session.read_text_index_metadata()

    assert saved is not None
    assert saved.workflow_gate_facts["plugin_source_text"]["status"] == "pass"
    assert saved.rust_contract_version == 1


@pytest.mark.asyncio
async def test_text_index_replace_rejects_mismatched_item_count(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """文本范围索引元信息和实际项数不一致时显式失败。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="en")

    async with await registry.open_game(record.game_title) as session:
        with pytest.raises(ValueError, match="item_count"):
            await session.replace_text_index(
                metadata=TextIndexMetadata(
                    source_snapshot_fingerprint="snapshot-v1",
                    rules_fingerprint="rules-v1",
                    item_count=1,
                    workflow_gate_facts={},
                    rust_contract_version=1,
                    parser_contract_version=1,
                    source_branch_contract_version=1,
                    text_fact_schema_version=CURRENT_TEXT_FACT_CONTRACT_VERSION,
                    created_at="2026-06-02T00:00:00",
                ),
                items=[],
            )


@pytest.mark.asyncio
async def test_register_game_updates_source_language_setting(
    minimal_english_game_dir: Path,
    tmp_path: Path,
) -> None:
    """重复注册同一游戏时会按本次参数更新源语言设置。"""
    registry = GameRegistry(tmp_path / "db")

    english_record = await registry.register_game(minimal_english_game_dir, source_language="en")
    japanese_record = await registry.register_game(minimal_english_game_dir, source_language="ja")

    assert english_record.source_language == "en"
    assert japanese_record.source_language == "ja"
    async with await registry.open_game("English Fixture Game") as session:
        assert session.source_language == "ja"
        assert session.target_language == "zh-Hans"


@pytest.mark.asyncio
async def test_register_game_reuses_registered_path_after_active_title_changes(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """重复注册已绑定目录时，当前运行标题变化不能创建新数据库。"""
    package_path = minimal_game_dir / "package.json"
    package_data = ensure_json_object(
        cast(JsonValue, json.loads(package_path.read_text(encoding="utf-8"))),
        "package.json",
    )
    window_data = ensure_json_object(package_data.get("window"), "package.json.window")
    window_data["title"] = ""
    _ = package_path.write_text(
        json.dumps(package_data, ensure_ascii=False),
        encoding="utf-8",
    )
    registry = GameRegistry(tmp_path / "db")
    first_record = await registry.register_game(minimal_game_dir, source_language="ja")

    system_path = minimal_game_dir / "data" / "System.json"
    system_data = ensure_json_object(
        cast(JsonValue, json.loads(system_path.read_text(encoding="utf-8"))),
        "System.json",
    )
    system_data["gameTitle"] = "测试游戏"
    _ = system_path.write_text(
        json.dumps(system_data, ensure_ascii=False),
        encoding="utf-8",
    )
    second_record = await registry.register_game(minimal_game_dir, source_language="en")

    assert second_record.db_path == first_record.db_path
    assert second_record.game_title == first_record.game_title
    async with await registry.open_game(first_record.game_title) as session:
        assert session.source_language == "en"
        assert session.target_language == "zh-Hans"


@pytest.mark.asyncio
async def test_register_game_rejects_att_mz_database_with_broken_metadata(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """路径匹配扫描遇到项目数据库元数据损坏时不能静默跳过。"""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "BrokenMetadata.db"
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute("CREATE TABLE schema_version (schema_key TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        _ = connection.execute(
            "INSERT INTO schema_version (schema_key, version) VALUES ('current', ?)",
            (CURRENT_SCHEMA_VERSION,),
        )
    registry = GameRegistry(db_dir)

    with pytest.raises(RuntimeError, match="metadata"):
        _ = await registry.register_game(minimal_game_dir, source_language="ja")

    assert sorted(path.name for path in db_dir.glob("*.db")) == ["BrokenMetadata.db"]


@pytest.mark.asyncio
async def test_register_game_ignores_unrelated_sqlite_database(
    minimal_game_dir: Path,
    tmp_path: Path,
) -> None:
    """路径匹配扫描可以跳过不含项目业务表的外部 SQLite 文件。"""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    with sqlite3.connect(db_dir / "ExternalTool.db") as connection:
        _ = connection.execute("CREATE TABLE external_cache (id INTEGER PRIMARY KEY)")
    registry = GameRegistry(db_dir)

    record = await registry.register_game(minimal_game_dir, source_language="ja")

    assert record.game_title == "テストゲーム"
    assert sorted(path.name for path in db_dir.glob("*.db")) == ["ExternalTool.db", "テストゲーム.db"]


@pytest.mark.asyncio
async def test_source_residual_rule_type_must_be_known(minimal_game_dir: Path, tmp_path: Path) -> None:
    """数据库里的源文残留例外规则类型损坏时必须立刻报错。"""
    registry = GameRegistry(tmp_path / "db")
    _ = await registry.register_game(minimal_game_dir, source_language="ja")
    async with await registry.open_game("テストゲーム") as session:
        _ = await session.connection.execute(
            """
            INSERT INTO rules
            (rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rule:broken",
                "source_residual",
                0,
                "literal",
                "Map001.json/1/0/0",
                json.dumps(
                    {
                        "rule_id": "broken:1",
                        "rule_type": "unknown",
                        "location_path": "Map001.json/1/0/0",
                        "allowed_terms": [],
                        "reason": "损坏测试",
                    },
                    ensure_ascii=False,
                ),
                1,
                "external_import",
                "broken",
            ),
        )
        await session.connection.commit()
        with pytest.raises(RuntimeError, match="rule_type"):
            _ = await session.read_source_residual_rules()


@pytest.mark.asyncio
async def test_open_game_rejects_incomplete_schema_without_creating_missing_tables(tmp_path: Path) -> None:
    """数据库表集合不完整时直接报错，运行时不会补建缺失表。"""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "Incomplete.db"
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute("CREATE TABLE schema_version (schema_key TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        _ = connection.execute(
            "INSERT INTO schema_version (schema_key, version) VALUES ('current', ?)",
            (CURRENT_SCHEMA_VERSION,),
        )
        _ = connection.execute(
            """
            CREATE TABLE metadata (
                metadata_key TEXT PRIMARY KEY,
                game_title TEXT NOT NULL,
                game_path TEXT NOT NULL,
                engine_kind TEXT NOT NULL,
                content_root TEXT NOT NULL,
                engine_version TEXT NOT NULL
            )
            """
        )
        _ = connection.execute(
            """
            INSERT INTO metadata (
                metadata_key,
                game_title,
                game_path,
                engine_kind,
                content_root,
                engine_version
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "current_game",
                "Incomplete",
                str(tmp_path),
                "mz",
                str(tmp_path),
                "1.0.0",
            ),
        )
    registry = GameRegistry(db_dir)

    with pytest.raises(RuntimeError, match="数据库结构不符合当前版本"):
        _ = await registry.open_game("Incomplete")

    table_names = read_sqlite_table_names(db_path)
    assert "language_settings" not in table_names
    assert "translation_items" not in table_names


@pytest.mark.asyncio
async def test_open_game_rejects_database_with_undeclared_table(minimal_game_dir: Path, tmp_path: Path) -> None:
    """数据库包含项目未声明的业务表时必须拒绝打开。"""
    registry = GameRegistry(tmp_path / "db")
    record = await registry.register_game(minimal_game_dir, source_language="ja")
    db_path = record.db_path
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute("CREATE TABLE external_debug_table (id INTEGER PRIMARY KEY)")

    with pytest.raises(RuntimeError, match="数据库结构不符合当前版本"):
        _ = await registry.open_game(record.game_title)


@pytest.mark.asyncio
async def test_open_game_rejects_database_with_invalid_table_shapes(tmp_path: Path) -> None:
    """数据库表名完整但表结构不匹配时必须拒绝打开。"""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "BrokenSchema.db"
    create_database_with_invalid_table_shapes(db_path=db_path, tmp_path=tmp_path)
    registry = GameRegistry(db_dir)

    with pytest.raises(RuntimeError, match="表结构不匹配"):
        _ = await registry.open_game("BrokenSchema")


@pytest.mark.asyncio
async def test_registry_stores_mv_engine_and_content_root(
    minimal_mv_game_dir: Path,
    tmp_path: Path,
) -> None:
    """MV 外层目录注册时会保存引擎类型和真实内容目录。"""
    registry = GameRegistry(tmp_path / "db")

    record = await registry.register_game(minimal_mv_game_dir, source_language="ja")

    assert record.game_title == "MVテストゲーム"
    assert record.engine_kind == "mv"
    assert record.engine_version == "1.6.1"
    assert record.content_root == minimal_mv_game_dir / "www"
    async with await registry.open_game("MVテストゲーム") as session:
        assert session.engine_kind == "mv"
        assert session.content_root == minimal_mv_game_dir / "www"


@pytest.mark.asyncio
async def test_start_translation_run_clears_previous_quality_errors(minimal_game_dir: Path, tmp_path: Path) -> None:
    """新一轮正文翻译开始时清空上一轮检查失败明细。"""
    db_dir = tmp_path / "db"
    registry = GameRegistry(db_dir)
    record = await registry.register_game(minimal_game_dir, source_language="ja")

    async with await registry.open_game(record.game_title) as session:
        first_run = await session.start_translation_run(
            total_extracted=10,
            pending_count=4,
            deduplicated_count=3,
            batch_count=2,
        )
        await session.write_translation_quality_errors(
            first_run.run_id,
            [
                TranslationErrorItem(
                    fact_id="fact-previous-quality-error",
                    location_path="Map001.json/1/0/0",
                    item_type="long_text",
                    role=None,
                    original_lines=["原文"],
                    translation_lines=[],
                    error_type="AI漏翻",
                    error_detail=["无法解析"],
                    model_response="上一轮模型原始返回",
                )
            ],
        )
        assert len(await session.read_translation_quality_errors(first_run.run_id)) == 1

        second_run = await session.start_translation_run(
            total_extracted=10,
            pending_count=3,
            deduplicated_count=2,
            batch_count=1,
        )

        assert await session.read_translation_quality_errors(first_run.run_id) == []
        assert await session.read_translation_quality_errors(second_run.run_id) == []
