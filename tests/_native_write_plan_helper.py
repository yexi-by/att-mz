"""测试中调用 Rust 写回计划的辅助函数。"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import cast

from app.application.file_writer import write_planned_text_files
from app.language import DEFAULT_SOURCE_LANGUAGE, DEFAULT_TARGET_LANGUAGE
from app.native_quality import build_native_text_rules_payload
from app.native_scope_index import (
    build_native_rule_candidate_text_rules_payload,
    rebuild_native_scope_index_storage,
)
from app.native_write_plan import NativePlannedFile, NativeWriteBackPlan, build_native_write_back_plan
from app.nonstandard_data.scanner import build_nonstandard_data_file_hash
from app.persistence.session_utils import current_timestamp_text
from app.persistence.sql import (
    INSERT_SOURCE_SNAPSHOT_FILE,
    current_schema_sql,
)
from app.plugin_text.common import build_plugin_hash
from app.plugin_source_text.scanner import build_plugin_source_candidate_index, build_plugin_source_file_hash
from app.rmmz.schema import (
    EventCommandTextRuleRecord,
    PLUGINS_FILE_NAME,
    GameData,
    MvVirtualNameboxRuleRecord,
    NonstandardDataTextRuleRecord,
    PluginSourceRuntimeWriteMapRecord,
    PluginSourceTextRuleRecord,
    TranslationItem,
)
from app.rmmz.commands import iter_all_commands
from app.rmmz.source_snapshot import collect_source_snapshot_records, validate_source_snapshot_files
from app.rmmz.text_rules import JsonObject, JsonValue, TextRules, coerce_json_value, get_default_text_rules
from app.text_index import (
    TEXT_INDEX_PROMPT_CONTEXT_VERSION,
    source_snapshot_records_fingerprint,
    stable_json_fingerprint,
)
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
    nonstandard_data_rule_records: list[NonstandardDataTextRuleRecord] | None = None,
) -> None:
    """通过 Rust 写回计划写入标准 data 文本。"""
    _ = _apply_native_write_plan(
        game_data=game_data,
        items=items,
        text_rules=text_rules,
        speaker_name_translations=speaker_name_translations,
        terminology_registry=None,
        mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
        nonstandard_data_rule_records=nonstandard_data_rule_records,
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
    nonstandard_data_rule_records: list[NonstandardDataTextRuleRecord] | None = None,
) -> NativeWriteBackPlan:
    """创建测试数据库并调用 Rust 写回计划。"""
    _require_source_snapshot(game_data)
    try:
        db_path = _write_temp_db(
            game_data=game_data,
            content_root=game_data.layout.content_root,
            items=items,
            speaker_name_translations=speaker_name_translations,
            terminology_registry=terminology_registry,
            mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
            plugin_source_rule_records=plugin_source_rule_records,
            text_rules=text_rules,
            nonstandard_data_rule_records=nonstandard_data_rule_records,
        )
    except RuntimeError as error:
        raise ValueError(str(error)) from error
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
    text_rules: TextRules | None = None,
    nonstandard_data_rule_records: list[NonstandardDataTextRuleRecord] | None = None,
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
    connection.row_factory = sqlite3.Row
    try:
        _ = connection.executescript(current_schema_sql())
        source_snapshot_fingerprint = _insert_source_snapshot_records(connection, game_data)
        _insert_inferred_plugin_text_rules(connection, game_data, items)
        _insert_inferred_event_command_rules(connection, game_data, items)
        _insert_inferred_note_tag_rules(connection, items)
        _insert_nonstandard_data_rules(connection, nonstandard_data_rule_records)
        if not nonstandard_data_rule_records:
            _insert_inferred_nonstandard_data_rules(connection, game_data, items)
        _insert_speaker_terms(connection, speaker_name_translations)
        _insert_terminology_registry(connection, terminology_registry)
        _insert_mv_virtual_namebox_rules(connection, mv_virtual_namebox_rule_records)
        _insert_plugin_source_text_rules(connection, plugin_source_rule_records)
        if not plugin_source_rule_records:
            _insert_inferred_plugin_source_text_rules(connection, game_data, items, text_rules)
        connection.commit()
        connection.close()
        _rebuild_current_text_facts_for_temp_db(
            db_path=db_path,
            game_data=game_data,
            source_snapshot_fingerprint=source_snapshot_fingerprint,
            text_rules=text_rules,
            rules_fingerprint=_rules_fingerprint_for_temp_db(
                text_rules=text_rules,
                items=items,
                plugin_source_rule_records=plugin_source_rule_records,
                mv_virtual_namebox_rule_records=mv_virtual_namebox_rule_records,
            ),
        )
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        fact_identity_by_item_index = _current_fact_identity_by_item_index(connection, items)
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
        connection.commit()
    finally:
        connection.close()
    return db_path


def _insert_source_snapshot_records(connection: sqlite3.Connection, game_data: GameData) -> str:
    """把当前测试游戏的可信源快照 manifest 写入临时库并返回指纹。"""
    records = collect_source_snapshot_records(
        layout=game_data.layout,
        updated_at=current_timestamp_text(),
    )
    _ = connection.executemany(
        INSERT_SOURCE_SNAPSHOT_FILE,
        [
            (record.relative_path, record.sha256, record.byte_size, record.updated_at)
            for record in records
        ],
    )
    return source_snapshot_records_fingerprint(records)


def _rebuild_current_text_facts_for_temp_db(
    *,
    db_path: Path,
    game_data: GameData,
    source_snapshot_fingerprint: str,
    text_rules: TextRules | None,
    rules_fingerprint: str,
) -> None:
    """调用 Rust cold rebuild，为测试临时库生成真实 current text facts。"""
    rules = text_rules or get_default_text_rules()
    text_rules_setting = coerce_json_value(cast(object, rules.setting.model_dump(mode="json")))
    if not isinstance(text_rules_setting, dict):
        raise TypeError("text_rules.setting JSON 必须是对象")
    text_rules_setting["prompt_context_version"] = TEXT_INDEX_PROMPT_CONTEXT_VERSION
    rule_candidate_text_rules = build_native_rule_candidate_text_rules_payload(rules)
    rule_candidate_text_rules["source_text_required_pattern"] = rules.setting.source_text_required_pattern
    result = rebuild_native_scope_index_storage(
        {
            "db_path": str(db_path),
            "game_path": str(game_data.layout.game_root),
            "source_snapshot_fingerprint": source_snapshot_fingerprint,
            "rules_fingerprint": rules_fingerprint,
            "source_language": DEFAULT_SOURCE_LANGUAGE,
            "target_language": DEFAULT_TARGET_LANGUAGE,
            "engine_kind": game_data.layout.engine_kind,
            "text_rules_setting": text_rules_setting,
            "rule_candidate_text_rules": rule_candidate_text_rules,
            "event_command_scope_codes": [356] if game_data.layout.engine_kind == "mv" else [357],
            "source_text_required_pattern": rules.setting.source_text_required_pattern,
            "created_at": current_timestamp_text(),
        }
    )
    if result.get("status") != "ok":
        raise RuntimeError("测试临时库 Rust current text fact 重建没有返回成功状态")


def _rules_fingerprint_for_temp_db(
    *,
    text_rules: TextRules | None,
    items: list[TranslationItem],
    plugin_source_rule_records: list[PluginSourceTextRuleRecord] | None,
    mv_virtual_namebox_rule_records: list[MvVirtualNameboxRuleRecord] | None,
) -> str:
    """生成测试临时库的规则指纹输入，避免用固定字符串伪装当前规则。"""
    rules = text_rules or get_default_text_rules()
    payload: JsonObject = {
        "prompt_context_version": TEXT_INDEX_PROMPT_CONTEXT_VERSION,
        "text_rules": coerce_json_value(cast(object, rules.setting.model_dump(mode="json"))),
        "item_locations": [item.location_path for item in items],
        "plugin_source_rule_records": [
            {
                "file_name": record.file_name,
                "file_hash": record.file_hash,
                "selectors": [selector for selector in record.selectors],
                "excluded_selectors": [selector for selector in record.excluded_selectors],
            }
            for record in plugin_source_rule_records or []
        ],
        "mv_virtual_namebox_rule_records": [
            coerce_json_value(cast(object, record.model_dump(mode="json")))
            for record in mv_virtual_namebox_rule_records or []
        ],
    }
    return stable_json_fingerprint(payload)


def _current_fact_identity_by_item_index(
    connection: sqlite3.Connection,
    items: list[TranslationItem],
) -> dict[int, tuple[str, str, str]]:
    """按 Rust 冷重建生成的 current facts 匹配测试译文身份。"""
    rows = cast(list[sqlite3.Row], connection.execute(
        """
        SELECT fact_id, location_path, item_type, role, translatable_text, raw_hash, translatable_hash
        FROM text_facts
        WHERE scope_key = (
            SELECT scope_key
            FROM text_fact_scope
            ORDER BY created_at DESC, scope_key
            LIMIT 1
        )
        ORDER BY fact_id
        """
    ).fetchall())
    facts_by_path: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        facts_by_path.setdefault(cast(str, row["location_path"]), []).append(row)
    used_fact_ids: set[str] = set()
    identities: dict[int, tuple[str, str, str]] = {}
    for item_index, item in enumerate(items):
        candidates: list[sqlite3.Row] = []
        for fact_path in _fact_identity_candidate_paths(item):
            candidates = [
                row
                for row in facts_by_path.get(fact_path, [])
                if cast(str, row["fact_id"]) not in used_fact_ids
                and row["translatable_text"] == _text_fact_translatable_text(item)
                and row["item_type"] == item.item_type
                and (row["role"] or None) == item.role
            ]
            if candidates:
                break
        if not candidates:
            for fact_path in _fact_identity_candidate_paths(item):
                candidates = [
                    row
                    for row in facts_by_path.get(fact_path, [])
                    if cast(str, row["fact_id"]) not in used_fact_ids
                    and row["translatable_text"] == _text_fact_translatable_text(item)
                ]
                if candidates:
                    break
        if not candidates:
            searched_paths = ", ".join(_fact_identity_candidate_paths(item))
            raise ValueError(
                "已保存译文不再匹配当前文本事实，不能写进游戏文件；请重新运行 rebuild-text-index 后重新翻译或手动导入: "
                + f"index={item_index}, paths=[{searched_paths}], text={_text_fact_translatable_text(item)!r}"
            )
        fact = candidates[0]
        fact_id = cast(str, fact["fact_id"])
        used_fact_ids.add(fact_id)
        identities[item_index] = (
            fact_id,
            cast(str, fact["raw_hash"]),
            cast(str, fact["translatable_hash"]),
        )
    return identities


def _fact_identity_candidate_paths(item: TranslationItem) -> list[str]:
    """返回测试 item 可用于匹配 current fact 的当前路径和原始来源路径。"""
    paths: list[str] = []
    for path in [item.location_path, *item.source_line_paths]:
        if path and path not in paths:
            paths.append(path)
    return paths


def _insert_runtime_rule(
    connection: sqlite3.Connection,
    *,
    domain: str,
    rule_order: int,
    matcher_kind: str,
    matcher_value: str,
    payload_json: JsonObject,
) -> None:
    """按当前统一规则模型写入测试规则。"""
    payload_text = json.dumps(payload_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    rule_hash_input = json.dumps(
        {
            "domain": domain,
            "rule_order": rule_order,
            "matcher_kind": matcher_kind,
            "matcher_value": matcher_value,
            "payload_json": payload_json,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    rule_hash = hashlib.sha256(rule_hash_input.encode("utf-8")).hexdigest()
    rule_id = f"{domain}:{rule_hash}"
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO rules
        (rule_id, domain, rule_order, matcher_kind, matcher_value, payload_json, enabled, source_kind, rule_hash)
        VALUES (?, ?, ?, ?, ?, ?, 1, 'test', ?)
        """,
        (
            rule_id,
            domain,
            rule_order,
            matcher_kind,
            matcher_value,
            payload_text,
            rule_hash,
        ),
    )


def _insert_inferred_plugin_text_rules(
    connection: sqlite3.Connection,
    game_data: GameData,
    items: list[TranslationItem],
) -> None:
    """按测试写回 item 精确补插件参数规则，让 Rust cold rebuild 生成对应 facts。"""
    rows: list[tuple[int, str, str, str]] = []
    for item in items:
        parsed = _parse_plugin_parameter_location_path(item.location_path)
        if parsed is None:
            continue
        plugin_index, path_segments = parsed
        if plugin_index >= len(game_data.plugins_js):
            raise AssertionError(f"测试插件参数路径索引超出范围: {item.location_path}")
        plugin = game_data.plugins_js[plugin_index]
        raw_name = plugin.get("name")
        plugin_name = raw_name if isinstance(raw_name, str) and raw_name else f"plugin_{plugin_index}"
        rows.append(
            (
                plugin_index,
                plugin_name,
                build_plugin_hash(plugin),
                _plugin_parameter_path_template(path_segments),
            )
        )
    if rows:
        for rule_order, (plugin_index, plugin_name, plugin_hash, path_template) in enumerate(
            sorted(set(rows))
        ):
            _insert_runtime_rule(
                connection,
                domain="plugin_config",
                rule_order=rule_order,
                matcher_kind="json_path_template",
                matcher_value=path_template,
                payload_json={
                    "plugin_index": plugin_index,
                    "plugin_name": plugin_name,
                    "plugin_hash": plugin_hash,
                    "path": path_template,
                },
            )


def _insert_inferred_note_tag_rules(
    connection: sqlite3.Connection,
    items: list[TranslationItem],
) -> None:
    """按测试写回 item 精确补 Note 标签规则，让 Rust cold rebuild 生成对应 facts。"""
    rows: list[tuple[str, str]] = []
    for item in items:
        parsed = _parse_note_tag_location_path(item.location_path)
        if parsed is not None:
            rows.append(parsed)
    if rows:
        for rule_order, (file_name, tag_name) in enumerate(sorted(set(rows))):
            _insert_runtime_rule(
                connection,
                domain="note_tags",
                rule_order=rule_order,
                matcher_kind="literal",
                matcher_value=f"{file_name}:{tag_name}",
                payload_json={
                    "file_name": file_name,
                    "tag_name": tag_name,
                },
            )


def _insert_inferred_event_command_rules(
    connection: sqlite3.Connection,
    game_data: GameData,
    items: list[TranslationItem],
) -> None:
    """按测试写回 item 精确补事件指令路径规则，让 Rust cold rebuild 生成对应 facts。"""
    rule_records: dict[tuple[int, str], EventCommandTextRuleRecord] = {}
    for item in items:
        for location_path in _fact_identity_candidate_paths(item):
            parsed = _parse_event_command_rule_location_path(game_data, location_path)
            if parsed is None:
                continue
            command_code, path_template = parsed
            rule_records[(command_code, path_template)] = EventCommandTextRuleRecord(
                command_code=command_code,
                path_templates=[path_template],
            )
    if not rule_records:
        return

    rows: list[tuple[int, str]] = []
    for record in rule_records.values():
        rows.extend((record.command_code, path_template) for path_template in record.path_templates)
    for rule_order, (command_code, path_template) in enumerate(sorted(set(rows))):
        _insert_runtime_rule(
            connection,
            domain="event_commands",
            rule_order=rule_order,
            matcher_kind="json_path_template",
            matcher_value=path_template,
            payload_json={
                "command_code": command_code,
                "parameter_filters": [],
                "path": path_template,
            },
        )


def _parse_event_command_rule_location_path(
    game_data: GameData,
    location_path: str,
) -> tuple[int, str] | None:
    """把事件指令字符串叶子路径转换为 Rust event command path rule。"""
    for command_location_path, command_code, parameters in _event_commands_by_longest_path(game_data):
        if not location_path.startswith(f"{command_location_path}/"):
            continue
        relative_path = location_path.removeprefix(f"{command_location_path}/")
        path_segments = relative_path.split("/")
        if not path_segments or path_segments[0] != "parameters":
            return None
        leaf_value = _resolve_event_command_leaf({"parameters": parameters}, path_segments)
        if not isinstance(leaf_value, str):
            return None
        return command_code, _json_path_template(path_segments)
    return None


def _event_commands_by_longest_path(game_data: GameData) -> list[tuple[str, int, list[JsonValue]]]:
    """按路径长度倒序返回当前游戏事件指令，避免短前缀误匹配。"""
    commands: list[tuple[str, int, list[JsonValue]]] = []
    for path, _display_name, command in iter_all_commands(game_data):
        commands.append(("/".join(map(str, path)), command.code, list(command.parameters)))
    return sorted(commands, key=lambda item: len(item[0]), reverse=True)


def _resolve_event_command_leaf(root: JsonObject, path_segments: list[str]) -> JsonValue | None:
    """解析测试 location path 片段；路径不存在时返回 None。"""
    current_value: JsonValue = root
    for segment in path_segments:
        if isinstance(current_value, dict):
            if segment not in current_value:
                return None
            current_value = current_value[segment]
            continue
        if isinstance(current_value, list):
            if not segment.isdigit():
                return None
            index = int(segment)
            if index >= len(current_value):
                return None
            current_value = current_value[index]
            continue
        return None
    return current_value


def _json_path_template(path_segments: list[str]) -> str:
    """把 location path 片段转换为当前 JSONPath 模板。"""
    template = "$"
    for segment in path_segments:
        if segment.isdigit():
            template += f"[{segment}]"
        else:
            escaped_segment = segment.replace("\\", "\\\\").replace("'", "\\'")
            template += f"['{escaped_segment}']"
    return template


def _insert_inferred_nonstandard_data_rules(
    connection: sqlite3.Connection,
    game_data: GameData,
    items: list[TranslationItem],
) -> None:
    """按测试写回 item 精确补非标准 data 规则，让 Rust cold rebuild 生成对应 facts。"""
    rows: list[tuple[str, str, str, str]] = []
    for item in items:
        parsed = _parse_nonstandard_data_location_path(item.location_path)
        if parsed is None:
            continue
        file_name, path_template = parsed
        source_path = game_data.layout.data_origin_dir / file_name
        if not source_path.is_file():
            source_path = game_data.layout.data_dir / file_name
        source_text = source_path.read_text(encoding="utf-8")
        rows.append((file_name, build_nonstandard_data_file_hash(source_text), path_template, "translate"))
    if rows:
        for rule_order, (file_name, file_hash, path_template, path_kind) in enumerate(
            sorted(set(rows))
        ):
            _insert_runtime_rule(
                connection,
                domain="nonstandard_data",
                rule_order=rule_order,
                matcher_kind="json_path_template",
                matcher_value=path_template,
                payload_json={
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "path": path_template,
                    "path_kind": path_kind,
                },
            )


def _insert_nonstandard_data_rules(
    connection: sqlite3.Connection,
    records: list[NonstandardDataTextRuleRecord] | None,
) -> None:
    """把测试已导入的非标准 data 规则写入临时库。"""
    if not records:
        return
    rows: list[tuple[str, str, str, str]] = []
    for record in records:
        rows.extend(
            (record.file_name, record.file_hash, path_template, "translate")
            for path_template in record.path_templates
        )
        rows.extend(
            (record.file_name, record.file_hash, path_template, "excluded")
            for path_template in record.excluded_path_templates
        )
        if record.skipped:
            rows.append((record.file_name, record.file_hash, "", "skipped"))
    if rows:
        for rule_order, (file_name, file_hash, path_template, path_kind) in enumerate(rows):
            _insert_runtime_rule(
                connection,
                domain="nonstandard_data",
                rule_order=rule_order,
                matcher_kind="json_path_template" if path_template else "domain_payload",
                matcher_value=path_template,
                payload_json={
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "path": path_template,
                    "path_kind": path_kind,
                },
            )


def _parse_plugin_parameter_location_path(location_path: str) -> tuple[int, list[str]] | None:
    """解析 `plugins.js/<index>/...` 测试写回路径。"""
    if not location_path.startswith("plugins.js/"):
        return None
    parts = location_path.split("/")
    if len(parts) < 3 or not parts[1].isdigit():
        raise AssertionError(f"测试插件参数路径格式非法: {location_path}")
    return int(parts[1]), parts[2:]


def _plugin_parameter_path_template(path_segments: list[str]) -> str:
    """把插件参数 location path 片段转换为精确 JSONPath 模板。"""
    template = "$['parameters']"
    for segment in path_segments:
        if segment.isdigit():
            template += f"[{segment}]"
        else:
            escaped_segment = segment.replace("\\", "\\\\").replace("'", "\\'")
            template += f"['{escaped_segment}']"
    return template


def _parse_note_tag_location_path(location_path: str) -> tuple[str, str] | None:
    """解析 `*.json/.../note/<tag>` 测试写回路径。"""
    marker = "/note/"
    if marker not in location_path:
        return None
    file_name = location_path.split("/", maxsplit=1)[0]
    tag_name = location_path.rsplit(marker, maxsplit=1)[1]
    if not file_name or not tag_name:
        raise AssertionError(f"测试 Note 标签路径格式非法: {location_path}")
    return file_name, tag_name


def _parse_nonstandard_data_location_path(location_path: str) -> tuple[str, str] | None:
    """解析 `nonstandard-data/<file>/<json_path>` 测试写回路径。"""
    prefix = "nonstandard-data/"
    if not location_path.startswith(prefix):
        return None
    parts = location_path.removeprefix(prefix).split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise AssertionError(f"测试非标准 data 路径格式非法: {location_path}")
    return parts[0], parts[1]


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


def _text_fact_translatable_text(item: TranslationItem) -> str:
    """按 current text fact 的 item_type 语义序列化可译正文。"""
    if item.item_type == "short_text":
        return item.original_lines[0] if item.original_lines else ""
    return "\n".join(item.original_lines)


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
    for record in records:
        _insert_runtime_rule(
            connection,
            domain="mv_virtual_namebox",
            rule_order=record.rule_order,
            matcher_kind="pcre2_pattern",
            matcher_value=record.pattern_text,
            payload_json={
                "name": record.rule_name,
                "pattern": record.pattern_text,
                "speaker_group": record.speaker_group,
                "body_group": record.body_group,
                "speaker_policy": record.speaker_policy,
                "render_template": record.render_template,
            },
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
    for rule_order, (file_name, file_hash, selector, selector_kind) in enumerate(rows):
        _insert_runtime_rule(
            connection,
            domain="plugin_source",
            rule_order=rule_order,
            matcher_kind="ast_selector",
            matcher_value=selector,
            payload_json={
                "file_name": file_name,
                "file_hash": file_hash,
                "selector": selector,
                "selector_kind": selector_kind,
            },
        )


def _insert_inferred_plugin_source_text_rules(
    connection: sqlite3.Connection,
    game_data: GameData,
    items: list[TranslationItem],
    text_rules: TextRules | None,
) -> None:
    """按测试写回 item 精确补插件源码规则，让 Rust cold rebuild 生成对应 facts。"""
    rules = text_rules or get_default_text_rules()
    selected_selectors_by_file: dict[str, set[str]] = {}
    rows: list[tuple[str, str, str, str]] = []
    for item in items:
        for location_path in _fact_identity_candidate_paths(item):
            parsed = _parse_plugin_source_location_path(location_path)
            if parsed is None:
                continue
            file_name, selector = parsed
            source = game_data.plugin_source_files.get(file_name)
            if source is None:
                continue
            selected_selectors_by_file.setdefault(file_name, set()).add(selector)
    for file_name, selected_selectors in selected_selectors_by_file.items():
        source = game_data.plugin_source_files.get(file_name)
        if source is None:
            continue
        file_hash = build_plugin_source_file_hash(source)
        candidate_index = build_plugin_source_candidate_index(
            file_name=file_name,
            source=source,
            active=True,
            text_rules=rules,
        )
        all_selectors = {candidate.selector for candidate in candidate_index.candidates}
        for selector in selected_selectors:
            rows.append((file_name, file_hash, selector, "translate"))
        for selector in sorted(all_selectors.difference(selected_selectors)):
            rows.append((file_name, file_hash, selector, "excluded"))
    if not rows:
        return
    for rule_order, (file_name, file_hash, selector, selector_kind) in enumerate(sorted(set(rows))):
        _insert_runtime_rule(
            connection,
            domain="plugin_source",
            rule_order=rule_order,
            matcher_kind="ast_selector",
            matcher_value=selector,
            payload_json={
                "file_name": file_name,
                "file_hash": file_hash,
                "selector": selector,
                "selector_kind": selector_kind,
            },
        )


def _parse_plugin_source_location_path(location_path: str) -> tuple[str, str] | None:
    """解析 `js/plugins/<file>/<selector>` 测试写回路径。"""
    prefix = "js/plugins/"
    if not location_path.startswith(prefix):
        return None
    parts = location_path.removeprefix(prefix).split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise AssertionError(f"测试插件源码路径格式非法: {location_path}")
    return parts[0], parts[1]


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
