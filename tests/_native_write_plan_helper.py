"""测试中调用 Rust 写回计划的辅助函数。"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from string import Formatter
from typing import cast

from app.application.file_writer import write_planned_text_files
from app.native_quality import build_native_text_rules_payload
from app.native_write_plan import NativePlannedFile, NativeWriteBackPlan, build_native_write_back_plan
from app.plugin_source_text.scanner import scan_plugin_source_runtime_files_text_strict
from app.rmmz.commands import iter_all_commands
from app.rmmz.mv_namebox import (
    MvVirtualSpeaker,
    parse_mv_virtual_speaker_line,
    runtime_mv_virtual_namebox_rules,
)
from app.persistence.sql import (
    CREATE_FIELD_TRANSLATION_TERMS_TABLE,
    CREATE_LLM_FAILURES_TABLE,
    CREATE_MV_VIRTUAL_NAMEBOX_RULES_TABLE,
    CREATE_PLUGIN_SOURCE_TEXT_RULES_TABLE,
    CREATE_SOURCE_RESIDUAL_RULES_TABLE,
    CREATE_TEXT_FACT_RENDER_PARTS_TABLE,
    CREATE_TEXT_FACT_SCOPE_TABLE,
    CREATE_TEXT_FACTS_TABLE,
    CREATE_TEXT_INDEX_ITEMS_TABLE,
    CREATE_TRANSLATION_QUALITY_ERRORS_TABLE,
    CREATE_TRANSLATION_RUNS_TABLE,
    CREATE_TRANSLATION_TABLE,
    INSERT_TEXT_FACT_RENDER_PART,
    INSERT_TEXT_FACT_SCOPE,
    INSERT_TEXT_FACT,
    INSERT_TEXT_INDEX_ITEM,
    CURRENT_TEXT_FACT_CONTRACT_VERSION,
)
from app.rmmz.schema import (
    Code,
    PLUGINS_FILE_NAME,
    GameData,
    MvVirtualNameboxRuleRecord,
    PluginSourceRuntimeWriteMapRecord,
    PluginSourceTextRuleRecord,
    TranslationItem,
)
from app.rmmz.source_snapshot import validate_source_snapshot_files
from app.rmmz.text_rules import JsonValue, TextRules, coerce_json_value, get_default_text_rules
from app.terminology import TerminologyRegistry


def reset_writable_copies(game_data: GameData) -> None:
    """重置测试内存副本。"""
    game_data.writable_data = copy.deepcopy(game_data.data)
    game_data.writable_plugins_js = copy.deepcopy(game_data.plugins_js)
    game_data.writable_plugin_source_files = dict(game_data.plugin_source_files)


def write_data_text(
    game_data: GameData,
    items: list[TranslationItem],
    text_rules: TextRules | None = None,
    speaker_name_translations: dict[str, str] | None = None,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None = None,
) -> None:
    """通过 Rust 写回计划写入标准 data 文本。"""
    _ = _apply_native_write_plan(
        game_data=game_data,
        items=items,
        text_rules=text_rules,
        speaker_name_translations=speaker_name_translations,
        terminology_registry=None,
        mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
    )


def write_plugin_text(
    game_data: GameData,
    items: list[TranslationItem],
) -> None:
    """通过 Rust 写回计划写入插件配置文本。"""
    _ = _apply_native_write_plan(
        game_data=game_data,
        items=items,
        text_rules=None,
        speaker_name_translations=None,
        terminology_registry=None,
        mv_virtual_namebox_rule_records=None,
    )


def write_plugin_source_text(
    game_data: GameData,
    items: list[TranslationItem],
    text_rules: TextRules | None = None,
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None = None,
) -> list[PluginSourceRuntimeWriteMapRecord]:
    """通过 Rust 写回计划写入插件源码文本并返回当前运行映射。"""
    plan = _apply_native_write_plan(
        game_data=game_data,
        items=items,
        text_rules=text_rules,
        speaker_name_translations=None,
        terminology_registry=None,
        mv_virtual_namebox_rule_records=None,
        plugin_source_rule_records=plugin_source_rule_records,
    )
    return plan.plugin_source_runtime_write_maps


def write_terminology_text(
    game_data: GameData,
    registry: TerminologyRegistry,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None = None,
) -> int:
    """通过 Rust 写回计划写入字段术语。"""
    plan = _apply_native_write_plan(
        game_data=game_data,
        items=[],
        text_rules=None,
        speaker_name_translations=None,
        terminology_registry=registry,
        mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
    )
    return plan.summary.terminology_written_count


def write_game_files(
    game_data: GameData,
    game_root: Path | None = None,
    *,
    force_full_restore: bool = False,
) -> None:
    """测试专用磁盘替换入口。"""
    _ = game_root
    _require_source_snapshot(game_data)
    files: list[tuple[Path, str]] = []
    for file_name, value in sorted(game_data.writable_data.items()):
        if file_name == PLUGINS_FILE_NAME:
            continue
        files.append(
            (
                game_data.layout.data_dir / file_name,
                f"{json.dumps(value, ensure_ascii=False, indent=2)}\n",
            )
        )
        if not force_full_restore and game_data.data.get(file_name) == value:
            _ = files.pop()
    plugin_content = _serialize_plugins_content(game_data.writable_data.get(PLUGINS_FILE_NAME))
    if force_full_restore or plugin_content != game_data.layout.plugins_path.read_text(encoding="utf-8"):
        files.append((game_data.layout.plugins_path, plugin_content))
    for file_name, source in sorted(game_data.writable_plugin_source_files.items()):
        target_path = game_data.layout.js_dir / "plugins" / file_name
        if force_full_restore or not target_path.is_file() or target_path.read_text(encoding="utf-8") != source:
            files.append((target_path, source))
    write_planned_text_files(files=files, rollback_dir_parent=game_data.layout.content_root)


def _apply_native_write_plan(
    *,
    game_data: GameData,
    items: list[TranslationItem],
    text_rules: TextRules | None,
    speaker_name_translations: dict[str, str] | None,
    terminology_registry: TerminologyRegistry | None,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None,
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None = None,
) -> NativeWriteBackPlan:
    """创建测试数据库并调用 Rust 写回计划。"""
    _require_source_snapshot(game_data)
    db_path = _write_temp_db(
        game_data=game_data,
        content_root=game_data.layout.content_root,
        items=items,
        speaker_name_translations=speaker_name_translations,
        terminology_registry=terminology_registry,
        mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
        plugin_source_rule_records=plugin_source_rule_records,
    )
    try:
        plan = build_native_write_back_plan(
            game_path=game_data.layout.game_root,
            content_root=game_data.layout.content_root,
            db_path=db_path,
            mode="write_back",
            confirm_font_overwrite=False,
            setting_payload=_build_setting_payload(text_rules, items),
        )
    except RuntimeError as error:
        raise ValueError(str(error)) from error
    finally:
        db_path.unlink(missing_ok=True)
    _apply_plan_to_memory(game_data=game_data, plan=plan)
    write_planned_text_files(
        files=[(file.target_path, _planned_file_content(file)) for file in plan.files],
        rollback_dir_parent=game_data.layout.content_root,
    )
    return plan


def _build_setting_payload(text_rules: TextRules | None, items: list[TranslationItem]) -> dict[str, JsonValue]:
    """构造 Rust 写回计划所需的文本规则配置。"""
    rules = text_rules or get_default_text_rules()
    allowed_translation_paths: list[JsonValue] = [
        path
        for path in sorted({item.location_path for item in items})
    ]
    return {
        "allowed_translation_paths": allowed_translation_paths,
        "long_text_line_width_limit": rules.setting.long_text_line_width_limit,
        "line_width_count_pattern": rules.setting.line_width_count_pattern,
        "line_split_punctuations": [punctuation for punctuation in rules.setting.line_split_punctuations],
        "preserve_wrapping_punctuation_pairs": [
            [left, right]
            for left, right in rules.setting.preserve_wrapping_punctuation_pairs
        ],
        "quality_text_rules": build_native_text_rules_payload(rules),
    }


def _write_temp_db(
    *,
    game_data: GameData,
    content_root: Path,
    items: list[TranslationItem],
    speaker_name_translations: dict[str, str] | None,
    terminology_registry: TerminologyRegistry | None,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None,
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None,
) -> Path:
    """把测试条目写入临时 SQLite 数据库。"""
    with tempfile.NamedTemporaryFile(
        prefix="att_mz_native_write_test_",
        suffix=".db",
        dir=content_root,
        delete=False,
    ) as temp_file:
        db_path = Path(temp_file.name)
    connection = sqlite3.connect(db_path)
    try:
        _ = connection.executescript(
            "\n".join(
                [
                    CREATE_TRANSLATION_TABLE,
                    CREATE_TRANSLATION_RUNS_TABLE,
                    CREATE_LLM_FAILURES_TABLE,
                    CREATE_TRANSLATION_QUALITY_ERRORS_TABLE,
                    CREATE_FIELD_TRANSLATION_TERMS_TABLE,
                    CREATE_MV_VIRTUAL_NAMEBOX_RULES_TABLE,
                    CREATE_PLUGIN_SOURCE_TEXT_RULES_TABLE,
                    CREATE_SOURCE_RESIDUAL_RULES_TABLE,
                    CREATE_TEXT_INDEX_ITEMS_TABLE,
                    CREATE_TEXT_FACTS_TABLE,
                    CREATE_TEXT_FACT_RENDER_PARTS_TABLE,
                    CREATE_TEXT_FACT_SCOPE_TABLE,
                ]
            )
        )
        fact_identity_by_item_index = _insert_current_text_fact_contract(
            connection,
            items,
            game_data,
            speaker_name_translations,
            terminology_registry,
            mv_virtual_namebox_rule_records,
        )
        _ = connection.executemany(
            """
            INSERT INTO translation_items
            (
                fact_id,
                location_path,
                item_type,
                role,
                original_lines,
                source_line_paths,
                source_fact_raw_hash,
                source_fact_translatable_hash,
                translation_lines
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _translation_item_row_for_temp_db(item, item_index, fact_identity_by_item_index)
                for item_index, item in enumerate(items)
            ],
        )
        _insert_speaker_terms(connection, speaker_name_translations)
        _insert_terminology_registry(connection, terminology_registry)
        _insert_mv_virtual_namebox_rules(connection, mv_virtual_namebox_rule_records)
        _insert_plugin_source_text_rules(connection, plugin_source_rule_records)
        connection.commit()
    finally:
        connection.close()
    return db_path


def _insert_current_text_fact_contract(
    connection: sqlite3.Connection,
    items: list[TranslationItem],
    game_data: GameData,
    speaker_name_translations: dict[str, str] | None,
    terminology_registry: TerminologyRegistry | None,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None,
) -> dict[int, tuple[str, str, str]]:
    """让测试临时库满足 Rust 写回的 current text fact scope 契约。"""
    scope_key = "test-helper-current"
    _ = connection.execute(
        INSERT_TEXT_FACT_SCOPE,
        (
            scope_key,
            CURRENT_TEXT_FACT_CONTRACT_VERSION,
            "test-helper-scope-hash",
            "test-helper-source-snapshot-hash",
            "test-helper-rule-hash",
            "test-helper-text-rules-hash",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    index_rows: list[tuple[str, str, str | None, str, str, str, str, int, str, str, str]] = []
    fact_rows: list[tuple[str, int, str, str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
    render_rows: list[tuple[str, int, str, str, str, str]] = []
    fact_identity_by_item_index: dict[int, tuple[str, str, str]] = {}
    plugin_source_literals = _plugin_source_literals_by_location_path(game_data)
    source_line_paths_by_location = {
        item.location_path: list(item.source_line_paths)
        for item in items
    }
    mv_virtual_namebox_candidates = _mv_virtual_namebox_fact_candidates(
        game_data=game_data,
        speaker_name_translations=speaker_name_translations,
        terminology_registry=terminology_registry,
        mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
    )
    mv_virtual_namebox_location_paths = {
        candidate_location_path
        for (
            _source_file,
            candidate_location_path,
            _source_line_path,
            _raw_text,
            _virtual_speaker,
        ) in mv_virtual_namebox_candidates
    }
    mv_virtual_namebox_items_by_location_path: dict[str, list[tuple[int, TranslationItem]]] = {}
    for item_index, item in enumerate(items):
        if item.location_path in mv_virtual_namebox_location_paths:
            mv_virtual_namebox_items_by_location_path.setdefault(item.location_path, []).append(
                (item_index, item)
            )
            continue
        fact_id = item.fact_id or f"test-helper-fact-{item_index:04d}"
        domain = _text_fact_domain_for_helper(item.location_path)
        source_file = _source_file_for_helper(item.location_path)
        source_type = domain
        translatable_text = _text_fact_translatable_text(item)
        raw_text = translatable_text
        visible_text = translatable_text
        raw_hash = _sha256_text(raw_text)
        visible_hash = _sha256_text(visible_text)
        if domain == "plugin_source":
            literal_identity = plugin_source_literals.get(item.location_path)
            if literal_identity is not None:
                raw_text, visible_text = literal_identity
                raw_hash = _sha256_text(raw_text)
                visible_hash = _sha256_text(visible_text)
        if _helper_domain_requires_render_parts(domain):
            render_rows.append((fact_id, 0, "translated_body", raw_text, translatable_text, "body"))
        translatable_hash = _sha256_text(translatable_text)
        fact_identity_by_item_index[item_index] = (fact_id, raw_hash, translatable_hash)
        index_rows.append(
            (
                item.location_path,
                item.item_type,
                item.role,
                json.dumps(item.original_lines, ensure_ascii=False),
                json.dumps(item.source_line_paths, ensure_ascii=False),
                source_type,
                source_file,
                1,
                "test-helper-source-snapshot-hash",
                "test-helper-rules-fingerprint",
                "{}",
            )
        )
        fact_rows.append(
            (
                fact_id,
                CURRENT_TEXT_FACT_CONTRACT_VERSION,
                domain,
                item.location_path,
                source_file,
                source_type,
                item.item_type,
                item.role or "",
                _selector_for_helper(item.location_path),
                raw_text,
                visible_text,
                translatable_text,
                raw_hash,
                visible_hash,
                translatable_hash,
                scope_key,
            )
        )
    _append_mv_virtual_namebox_fact_rows(
        scope_key=scope_key,
        first_fact_index=len(items),
        candidates=mv_virtual_namebox_candidates,
        source_line_paths_by_location=source_line_paths_by_location,
        index_rows=index_rows,
        fact_rows=fact_rows,
        render_rows=render_rows,
        mv_virtual_namebox_items_by_location_path=mv_virtual_namebox_items_by_location_path,
        fact_identity_by_item_index=fact_identity_by_item_index,
    )
    if index_rows:
        _ = connection.executemany(INSERT_TEXT_INDEX_ITEM, index_rows)
    if fact_rows:
        _ = connection.executemany(INSERT_TEXT_FACT, fact_rows)
    if render_rows:
        _ = connection.executemany(INSERT_TEXT_FACT_RENDER_PART, render_rows)
    return fact_identity_by_item_index


def _translation_item_row_for_temp_db(
    item: TranslationItem,
    item_index: int,
    fact_identity_by_item_index: dict[int, tuple[str, str, str]],
) -> tuple[str, str, str, str | None, str, str, str, str, str]:
    """按测试临时 current text fact 身份序列化保存译文行。"""
    identity = fact_identity_by_item_index.get(item_index)
    if identity is None:
        raise AssertionError(f"测试临时库缺少当前文本事实: index={item_index}, path={item.location_path}")
    fact_id, raw_hash, translatable_hash = identity
    return (
        fact_id,
        item.location_path,
        item.item_type,
        item.role,
        json.dumps(item.original_lines, ensure_ascii=False),
        json.dumps(item.source_line_paths, ensure_ascii=False),
        raw_hash,
        translatable_hash,
        json.dumps(item.translation_lines, ensure_ascii=False),
    )


def _text_fact_domain_for_helper(location_path: str) -> str:
    """推断测试 helper 需要进入真实迁移写回域的最小集合。"""
    if location_path.startswith("js/plugins/"):
        return "plugin_source"
    if location_path.startswith("plugins.js/"):
        return "plugin_config"
    if location_path.startswith("nonstandard-data/"):
        return "nonstandard_data"
    if _is_note_tag_location_path(location_path):
        return "note_tag"
    if _is_event_command_location_path(location_path):
        return "event_command"
    if _is_json_data_location_path(location_path):
        return "standard_data"
    raise AssertionError(f"测试 helper 不支持的当前文本事实路径: {location_path}")


def _helper_domain_requires_render_parts(domain: str) -> bool:
    """测试 helper 中需要当前写回所需源文结构的写回域。"""
    return domain in {
        "standard_data",
        "plugin_config",
        "event_command",
        "note_tag",
        "nonstandard_data",
        "plugin_source",
    }


def _is_note_tag_location_path(location_path: str) -> bool:
    """按 Rust note writer 的路径形状识别 Note 标签写回域。"""
    parts = location_path.split("/")
    return len(parts) >= 3 and parts[-2] == "note"


def _is_event_command_location_path(location_path: str) -> bool:
    """按 Rust event command writer 的文件路由识别事件指令写回域。"""
    file_name = location_path.split("/", 1)[0]
    return (
        file_name == "CommonEvents.json"
        or file_name == "Troops.json"
        or _is_map_file_name_for_helper(file_name)
    )


def _is_map_file_name_for_helper(file_name: str) -> bool:
    """识别 RPG Maker 地图 data 文件名。"""
    if not file_name.startswith("Map") or not file_name.endswith(".json"):
        return False
    number_text = file_name.removeprefix("Map").removesuffix(".json")
    return bool(number_text) and number_text.isdigit()


def _is_json_data_location_path(location_path: str) -> bool:
    """识别标准 data JSON 文本路径。"""
    file_name = location_path.split("/", 1)[0]
    return file_name.endswith(".json")


def _plugin_source_literals_by_location_path(game_data: GameData) -> dict[str, tuple[str, str]]:
    """从测试插件源码 AST 字符串节点构造 current text fact 的 raw/visible 身份。"""
    if not game_data.plugin_source_files:
        return {}
    scan = scan_plugin_source_runtime_files_text_strict(
        files=game_data.plugin_source_files,
        active_file_names=frozenset(game_data.plugin_source_files),
    )
    literals: dict[str, tuple[str, str]] = {}
    for file_name, file_scan in scan.file_scans.items():
        for literal in file_scan.literals:
            location_path = f"js/plugins/{file_name}/{literal.selector}"
            literals[location_path] = (literal.raw_text, literal.text)
    return literals


def _append_mv_virtual_namebox_fact_rows(
    *,
    scope_key: str,
    first_fact_index: int,
    candidates: list[tuple[str, str, str, str, MvVirtualSpeaker]],
    source_line_paths_by_location: dict[str, list[str]],
    index_rows: list[tuple[str, str, str | None, str, str, str, str, int, str, str, str]],
    fact_rows: list[tuple[str, int, str, str, str, str, str, str, str, str, str, str, str, str, str, str]],
    render_rows: list[tuple[str, int, str, str, str, str]],
    mv_virtual_namebox_items_by_location_path: dict[str, list[tuple[int, TranslationItem]]],
    fact_identity_by_item_index: dict[int, tuple[str, str, str]],
) -> None:
    """为 MV 虚拟名字框术语写回补当前文本事实/render parts 测试契约。"""
    next_fact_index = first_fact_index
    for source_file, location_path, source_line_path, raw_text, virtual_speaker in candidates:
        pending_items = mv_virtual_namebox_items_by_location_path.get(location_path) or []
        if pending_items:
            item_index, item = pending_items.pop(0)
            source_line_paths = [path for path in item.source_line_paths] or [source_line_path]
            fact_id = item.fact_id or f"test-helper-mv-namebox-{next_fact_index:04d}"
        else:
            item_index = None
            source_line_paths = source_line_paths_by_location.get(location_path) or [source_line_path]
            fact_id = f"test-helper-mv-namebox-{next_fact_index:04d}"
        next_fact_index += 1
        _append_single_mv_virtual_namebox_fact_row(
            fact_id=fact_id,
            item_index=item_index,
            scope_key=scope_key,
            source_file=source_file,
            location_path=location_path,
            source_line_paths=source_line_paths,
            raw_text=raw_text,
            virtual_speaker=virtual_speaker,
            index_rows=index_rows,
            fact_rows=fact_rows,
            render_rows=render_rows,
            fact_identity_by_item_index=fact_identity_by_item_index,
        )


def _mv_virtual_namebox_fact_candidates(
    *,
    game_data: GameData,
    speaker_name_translations: dict[str, str] | None,
    terminology_registry: TerminologyRegistry | None,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None,
) -> list[tuple[str, str, str, str, MvVirtualSpeaker]]:
    """找出应由 MV virtual namebox 专用 render parts 表示的测试 fact。"""
    speaker_terms = _speaker_terms_for_mv_virtual_namebox_facts(
        speaker_name_translations=speaker_name_translations,
        terminology_registry=terminology_registry,
    )
    if game_data.layout.engine_kind != "mv" or not speaker_terms or not mv_virtual_namebox_rule_records:
        return []
    rules = runtime_mv_virtual_namebox_rules(mv_virtual_namebox_rule_records)
    pending_name_path: str | None = None
    pending_list_path: tuple[str | int, ...] | None = None
    candidates: list[tuple[str, str, str, str, MvVirtualSpeaker]] = []
    for path, _display_name, command in iter_all_commands(game_data):
        location_path = "/".join(map(str, path))
        if command.code == Code.NAME:
            pending_name_path = location_path
            pending_list_path = tuple(path[:-1])
            continue
        if command.code != Code.TEXT:
            pending_name_path = None
            pending_list_path = None
            continue
        if pending_name_path is None or pending_list_path != tuple(path[:-1]):
            continue
        fact_location_path = pending_name_path
        pending_name_path = None
        pending_list_path = None
        if not command.parameters or not isinstance(command.parameters[0], str):
            continue
        raw_text = command.parameters[0]
        try:
            virtual_speaker = parse_mv_virtual_speaker_line(
                text=raw_text,
                game_data=game_data,
                rules=rules,
                location_path=location_path,
            )
        except ValueError:
            continue
        if virtual_speaker is None or virtual_speaker.speaker not in speaker_terms:
            continue
        candidates.append((str(path[0]), fact_location_path, location_path, raw_text, virtual_speaker))
    return candidates


def _speaker_terms_for_mv_virtual_namebox_facts(
    *,
    speaker_name_translations: dict[str, str] | None,
    terminology_registry: TerminologyRegistry | None,
) -> dict[str, str]:
    """收集本次术语写回会尝试更新的 speaker_names。"""
    speaker_terms: dict[str, str] = {}
    if speaker_name_translations:
        speaker_terms.update(speaker_name_translations)
    if terminology_registry is not None:
        speaker_terms.update(terminology_registry.speaker_names)
    return speaker_terms


def _append_single_mv_virtual_namebox_fact_row(
    *,
    fact_id: str,
    item_index: int | None,
    scope_key: str,
    source_file: str,
    location_path: str,
    source_line_paths: list[str],
    raw_text: str,
    virtual_speaker: MvVirtualSpeaker,
    index_rows: list[tuple[str, str, str | None, str, str, str, str, int, str, str, str]],
    fact_rows: list[tuple[str, int, str, str, str, str, str, str, str, str, str, str, str, str, str, str]],
    render_rows: list[tuple[str, int, str, str, str, str]],
    fact_identity_by_item_index: dict[int, tuple[str, str, str]],
) -> None:
    """追加单条 MV virtual namebox current text fact 测试行。"""
    render_parts = _mv_virtual_namebox_render_parts(raw_text, virtual_speaker)
    translatable_text = virtual_speaker.body_text
    raw_hash = _sha256_text(raw_text)
    translatable_hash = _sha256_text(translatable_text)
    if item_index is not None:
        fact_identity_by_item_index[item_index] = (fact_id, raw_hash, translatable_hash)
    index_rows.append(
        (
            location_path,
            "long_text",
            virtual_speaker.speaker,
            json.dumps([translatable_text], ensure_ascii=False),
            json.dumps(source_line_paths, ensure_ascii=False),
            "event_command",
            source_file,
            1,
            "test-helper-source-snapshot-hash",
            "test-helper-rules-fingerprint",
            "{}",
        )
    )
    fact_rows.append(
        (
            fact_id,
            CURRENT_TEXT_FACT_CONTRACT_VERSION,
            "mv_virtual_namebox",
            location_path,
            source_file,
            "event_command",
            "long_text",
            virtual_speaker.speaker,
            location_path,
            raw_text,
            raw_text,
            translatable_text,
            raw_hash,
            raw_hash,
            translatable_hash,
            scope_key,
        )
    )
    render_rows.extend(
        (
            fact_id,
            part_order,
            part_kind,
            part_raw_text,
            semantic_text,
            template_key,
        )
        for part_order, (part_kind, part_raw_text, semantic_text, template_key) in enumerate(render_parts)
    )


def _mv_virtual_namebox_render_parts(
    raw_text: str,
    virtual_speaker: MvVirtualSpeaker,
) -> list[tuple[str, str, str, str]]:
    """按 current text fact render parts 形状拆分 MV 虚拟名字框源文本。"""
    parts: list[tuple[str, str, str, str]] = []
    formatter = Formatter()
    for literal_text, field_name, _format_spec, _conversion in formatter.parse(virtual_speaker.render_template):
        if literal_text:
            parts.append(("literal", literal_text, literal_text, "literal"))
        if field_name is None:
            continue
        normalized_field = field_name.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]
        if normalized_field == "speaker" or normalized_field == virtual_speaker.speaker_group:
            parts.append(
                (
                    "speaker",
                    virtual_speaker.source_speaker_text,
                    virtual_speaker.speaker,
                    "speaker",
                )
            )
            continue
        if normalized_field == "body" or (
            virtual_speaker.body_group and normalized_field == virtual_speaker.body_group
        ):
            parts.append(
                (
                    "translated_body",
                    virtual_speaker.body_text,
                    virtual_speaker.body_text,
                    "body",
                )
            )
            continue
        value = virtual_speaker.group_values.get(normalized_field, "")
        parts.append(("literal", value, value, normalized_field))
    if not any(part_kind == "translated_body" for part_kind, _raw, _semantic, _key in parts):
        parts.append(("translated_body", "", "", "body"))
    return _reconcile_mv_virtual_namebox_render_parts(raw_text, parts)


def _reconcile_mv_virtual_namebox_render_parts(
    raw_text: str,
    parts: list[tuple[str, str, str, str]],
) -> list[tuple[str, str, str, str]]:
    """保留规则模板外的原始空白外壳。"""
    rebuilt = "".join(part_raw_text for _part_kind, part_raw_text, _semantic_text, _template_key in parts)
    if rebuilt == raw_text:
        return parts
    start_index = raw_text.find(rebuilt)
    if start_index < 0:
        return parts
    end_index = start_index + len(rebuilt)
    prefix = raw_text[:start_index]
    suffix = raw_text[end_index:]
    reconciled = list(parts)
    if prefix:
        reconciled.insert(0, ("literal", prefix, prefix, "literal"))
    if suffix:
        reconciled.append(("literal", suffix, suffix, "literal"))
    return reconciled


def _text_fact_translatable_text(item: TranslationItem) -> str:
    """按 current text fact 的 item_type 语义序列化可译正文。"""
    if item.item_type == "short_text":
        return item.original_lines[0] if item.original_lines else ""
    return "\n".join(item.original_lines)


def _source_file_for_helper(location_path: str) -> str:
    """从测试 location_path 提取最小 source_file 字段。"""
    if location_path.startswith("js/plugins/"):
        parts = location_path.split("/")
        return "/".join(parts[:3]) if len(parts) >= 3 else location_path
    if location_path.startswith("nonstandard-data/"):
        parts = location_path.split("/", 2)
        return parts[1] if len(parts) >= 2 else location_path
    return location_path.split("/", 1)[0]


def _selector_for_helper(location_path: str) -> str:
    """从插件源码 location_path 提取 selector，其余测试路径保持为空。"""
    if not location_path.startswith("js/plugins/"):
        return ""
    parts = location_path.split("/", 3)
    if len(parts) < 4:
        return ""
    return parts[3]


def _sha256_text(text: str) -> str:
    """计算与 Rust current text fact 一致的 UTF-8 SHA-256。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _insert_speaker_terms(
    connection: sqlite3.Connection,
    speaker_name_translations: dict[str, str] | None,
) -> None:
    """写入测试说话人术语。"""
    if not speaker_name_translations:
        return
    _ = connection.executemany(
        """
        INSERT INTO terminology_field_terms (category, source_text, translated_text)
        VALUES ('speaker_names', ?, ?)
        """,
        sorted(speaker_name_translations.items()),
    )


def _insert_terminology_registry(
    connection: sqlite3.Connection,
    registry: TerminologyRegistry | None,
) -> None:
    """写入测试字段术语表。"""
    if registry is None:
        return
    rows: list[tuple[str, str, str]] = []
    for category, entries in registry.as_category_map().items():
        for source_text, translated_text in sorted(entries.items()):
            if not source_text.strip() or not translated_text.strip():
                continue
            rows.append((category, source_text, translated_text))
    if not rows:
        return
    _ = connection.executemany(
        """
        INSERT INTO terminology_field_terms (category, source_text, translated_text)
        VALUES (?, ?, ?)
        """,
        rows,
    )


def _insert_mv_virtual_namebox_rules(
    connection: sqlite3.Connection,
    records: list[MvVirtualNameboxRuleRecord] | None,
) -> None:
    """写入测试 MV 虚拟名字框规则。"""
    if not records:
        return
    _ = connection.executemany(
        """
        INSERT INTO mv_virtual_namebox_rules
        (rule_order, rule_name, pattern_text, speaker_group, body_group, speaker_policy, render_template)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record.rule_order,
                record.rule_name,
                record.pattern_text,
                record.speaker_group,
                record.body_group,
                record.speaker_policy,
                record.render_template,
            )
            for record in records
        ],
    )


def _insert_plugin_source_text_rules(
    connection: sqlite3.Connection,
    records: list[PluginSourceTextRuleRecord] | None,
) -> None:
    """写入测试插件源码规则。"""
    if not records:
        return
    rows: list[tuple[str, str, str, str]] = []
    for record in records:
        rows.extend(
            (record.file_name, record.file_hash, selector, "translate")
            for selector in record.selectors
        )
        rows.extend(
            (record.file_name, record.file_hash, selector, "excluded")
            for selector in record.excluded_selectors
        )
    if not rows:
        return
    _ = connection.executemany(
        """
        INSERT INTO plugin_source_text_rules
        (file_name, file_hash, selector, selector_kind)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def _require_source_snapshot(game_data: GameData) -> None:
    """测试写回入口只能使用注册流程已经创建的可信源快照。"""
    try:
        validate_source_snapshot_files(game_data.layout)
    except Exception as error:
        raise FileNotFoundError(
            "缺少可信源快照，测试写回不能把当前运行文件自动补成源文；"
            + "请先通过 register_game/add-game 创建可信源快照后再写回"
        ) from error


def _apply_plan_to_memory(
    *,
    game_data: GameData,
    plan: NativeWriteBackPlan,
) -> None:
    """把 Rust 计划结果同步到测试内存副本。"""
    for file in plan.files:
        content = _planned_file_content(file)
        if file.relative_path.startswith("data/"):
            file_name = file.relative_path.removeprefix("data/")
            game_data.writable_data[file_name] = coerce_json_value(
                cast(object, json.loads(content))
            )
            continue
        if file.relative_path == "js/plugins.js":
            plugins_js = _parse_plugins_content(content)
            game_data.writable_plugins_js = plugins_js
            game_data.writable_data[PLUGINS_FILE_NAME] = content
            continue
        if file.relative_path.startswith("js/plugins/"):
            file_name = file.relative_path.removeprefix("js/plugins/")
            game_data.writable_plugin_source_files[file_name] = content


def _planned_file_content(file: NativePlannedFile) -> str:
    """读取 Rust 计划文件内容，兼容 inline content 与 sidecar content_path。"""
    if file.content is not None:
        return file.content
    if file.content_path is not None:
        return file.content_path.read_text(encoding="utf-8")
    raise RuntimeError("Rust 写回计划文件缺少 content 或 content_path")


def _serialize_plugins_content(value: JsonValue | None) -> str:
    """序列化插件配置文件。"""
    if isinstance(value, str):
        return value
    return f"var $plugins = {json.dumps(value, ensure_ascii=False, indent=2)};\n"


def _parse_plugins_content(content: str) -> list[dict[str, JsonValue]]:
    """解析 `$plugins` 文件内容。"""
    start = content.index("[")
    end = content.rindex("]") + 1
    value = coerce_json_value(cast(object, json.loads(content[start:end])))
    if not isinstance(value, list):
        raise TypeError("plugins.js 顶层必须是数组")
    plugins: list[dict[str, JsonValue]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"plugins.js[{index}] 必须是对象")
        plugins.append(item)
    return plugins
